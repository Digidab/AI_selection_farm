"""ML-specific prediction validation and ordered candidate decision boundary."""

import math
from dataclasses import dataclass

from ..core.schemas import EvidenceRecord
from .config import (
    ClassificationPredictionSettings,
    MLBranchSettings,
    PredictionSettings,
    RegressionPredictionSettings,
)
from .deduplicator import AcceptedMLInputLookup, MLExactDeduplicator
from .pipelines.interfaces import ClassProbability, MLPrediction, PredictionValue
from .schemas import MLTask

_PROBABILITY_SUM_TOLERANCE = 1e-6


@dataclass(frozen=True, slots=True)
class MLValidationResult:
    evidence: EvidenceRecord
    score: float | None


@dataclass(frozen=True, slots=True)
class MLCandidateEvaluation:
    accepted: bool
    prediction: PredictionValue
    score: float | None
    canonical_input: str | None
    evidence: tuple[EvidenceRecord, ...]
    failure_code: str | None = None
    failure_reason: str | None = None


def _failed(code: str, message: str, **details: object) -> MLValidationResult:
    return MLValidationResult(
        evidence=EvidenceRecord(
            check_id="ml_validation",
            passed=False,
            code=code,
            details={"message": message, **details},
        ),
        score=None,
    )


def _validate_probabilities(
    probabilities: tuple[ClassProbability, ...] | None,
    settings: ClassificationPredictionSettings,
) -> tuple[dict[str, float] | None, MLValidationResult | None]:
    required = settings.confidence is not None and settings.confidence.required
    if probabilities is None:
        if required:
            return None, _failed(
                "missing_probability",
                "Classification confidence requires probabilities",
            )
        return None, None
    if not probabilities:
        return None, _failed("invalid_probability", "Probability vector must not be empty")

    normalized: dict[str, float] = {}
    for item in probabilities:
        if type(item.label) is not str or item.label in normalized:
            return None, _failed(
                "invalid_probability",
                "Probability labels must be unique strings",
            )
        if isinstance(item.probability, bool) or not isinstance(item.probability, (int, float)):
            return None, _failed(
                "invalid_probability",
                "Probability values must be numeric",
            )
        probability = float(item.probability)
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            return None, _failed(
                "invalid_probability",
                "Probability values must be finite and between zero and one",
            )
        normalized[item.label] = probability

    if set(normalized) != set(settings.allowed_classes):
        return None, _failed(
            "invalid_probability",
            "Probability labels must match configured allowed classes",
        )
    if not math.isclose(
        sum(normalized.values()),
        1.0,
        rel_tol=0.0,
        abs_tol=_PROBABILITY_SUM_TOLERANCE,
    ):
        return None, _failed("invalid_probability", "Probability values must sum to one")
    return normalized, None


class MLDecisionValidator:
    def evaluate(
        self,
        prediction: MLPrediction,
        settings: PredictionSettings,
    ) -> MLValidationResult:
        if prediction.mode != settings.mode:
            return _failed(
                "wrong_prediction_mode",
                "Prediction mode does not match configuration",
                expected_mode=settings.mode.value,
                actual_mode=prediction.mode.value,
            )
        if prediction.evidence.pipeline_id.strip() == "":
            return _failed("missing_pipeline_identity", "Pipeline identity must not be empty")

        if isinstance(settings, ClassificationPredictionSettings):
            return self._evaluate_classification(prediction, settings)
        if isinstance(settings, RegressionPredictionSettings):
            return self._evaluate_regression(prediction, settings)
        return _failed("wrong_prediction_mode", "Unsupported prediction settings")

    def _evaluate_classification(
        self,
        prediction: MLPrediction,
        settings: ClassificationPredictionSettings,
    ) -> MLValidationResult:
        if type(prediction.prediction) is not str:
            return _failed("wrong_type", "Classification prediction must be a string")
        if prediction.prediction not in settings.allowed_classes:
            return _failed(
                "invalid_class",
                "Classification prediction is not allowlisted",
                prediction=prediction.prediction,
            )

        probabilities, failure = _validate_probabilities(prediction.probabilities, settings)
        if failure is not None:
            return failure
        confidence = None if probabilities is None else probabilities[prediction.prediction]
        if (
            settings.confidence is not None
            and settings.confidence.required
            and confidence is not None
            and confidence < settings.confidence.minimum
        ):
            return _failed(
                "confidence_error",
                "Prediction confidence is below the configured minimum",
                confidence=confidence,
                minimum=settings.confidence.minimum,
            )

        return MLValidationResult(
            evidence=EvidenceRecord(
                check_id="ml_validation",
                passed=True,
                details={
                    "pipeline_id": prediction.evidence.pipeline_id,
                    "mode": settings.mode.value,
                    "prediction": prediction.prediction,
                    "confidence": confidence,
                },
            ),
            score=confidence,
        )

    def _evaluate_regression(
        self,
        prediction: MLPrediction,
        settings: RegressionPredictionSettings,
    ) -> MLValidationResult:
        value = prediction.prediction
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return _failed("wrong_type", "Regression prediction must be numeric")
        numeric_value = float(value)
        if not math.isfinite(numeric_value):
            code = "nan_detected" if math.isnan(numeric_value) else "infinity_detected"
            return _failed(code, "Regression prediction must be finite")
        if prediction.probabilities is not None:
            return _failed(
                "invalid_probability", "Regression prediction cannot contain probabilities"
            )
        if not settings.minimum <= numeric_value <= settings.maximum:
            return _failed(
                "range_error",
                "Regression prediction is outside the configured range",
                minimum=settings.minimum,
                maximum=settings.maximum,
                prediction=numeric_value,
            )

        return MLValidationResult(
            evidence=EvidenceRecord(
                check_id="ml_validation",
                passed=True,
                details={
                    "pipeline_id": prediction.evidence.pipeline_id,
                    "mode": settings.mode.value,
                    "prediction": numeric_value,
                },
            ),
            score=numeric_value,
        )


class MLCandidateEvaluator:
    """Validate the decision before performing exact input duplicate lookup."""

    def __init__(
        self,
        *,
        validator: MLDecisionValidator,
        deduplicator: MLExactDeduplicator,
    ) -> None:
        self.validator = validator
        self.deduplicator = deduplicator

    def evaluate(
        self,
        prediction: MLPrediction,
        task: MLTask,
        settings: MLBranchSettings,
        lookup: AcceptedMLInputLookup,
    ) -> MLCandidateEvaluation:
        validation = self.validator.evaluate(prediction, settings.prediction)
        evidence = [validation.evidence]
        if not validation.evidence.passed:
            return self._rejected(prediction, validation, tuple(evidence), canonical_input=None)

        duplicate = self.deduplicator.evaluate(
            task,
            feature_contract=settings.features,
            dataset_id=settings.dataset_id,
            lookup=lookup,
        )
        evidence.append(duplicate.evidence)
        if not duplicate.evidence.passed:
            return self._rejected(
                prediction,
                MLValidationResult(duplicate.evidence, validation.score),
                tuple(evidence),
                canonical_input=duplicate.canonical_input,
            )

        return MLCandidateEvaluation(
            accepted=True,
            prediction=prediction.prediction,
            score=validation.score,
            canonical_input=duplicate.canonical_input,
            evidence=tuple(evidence),
        )

    @staticmethod
    def _rejected(
        prediction: MLPrediction,
        result: MLValidationResult,
        evidence: tuple[EvidenceRecord, ...],
        *,
        canonical_input: str | None,
    ) -> MLCandidateEvaluation:
        return MLCandidateEvaluation(
            accepted=False,
            prediction=prediction.prediction,
            score=result.score,
            canonical_input=canonical_input,
            evidence=evidence,
            failure_code=result.evidence.code,
            failure_reason=str(result.evidence.details.get("message", "ML candidate rejected")),
        )
