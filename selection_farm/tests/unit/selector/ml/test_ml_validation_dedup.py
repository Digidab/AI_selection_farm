import math

import pytest

from services.selector.app.ml.config import RegressionPredictionSettings, load_ml_config
from services.selector.app.ml.deduplicator import (
    DuplicateMLInput,
    MLExactDeduplicator,
)
from services.selector.app.ml.pipelines.interfaces import (
    ClassProbability,
    MLPrediction,
    PredictionEvidence,
)
from services.selector.app.ml.schemas import MLInputError, MLTask, PredictionMode
from services.selector.app.ml.validators import (
    MLCandidateEvaluator,
    MLDecisionValidator,
)


class FakeLookup:
    def __init__(self, duplicate=None) -> None:
        self.duplicate = duplicate
        self.calls = 0
        self.canonical_inputs: list[str] = []

    def find_duplicate(self, *, dataset_id, canonical_input):
        self.calls += 1
        assert dataset_id == "selector_ml_seed_v001"
        self.canonical_inputs.append(canonical_input)
        return self.duplicate


def _probabilities(
    healthy: float = 0.6,
    attention: float = 0.4,
) -> tuple[ClassProbability, ...]:
    return (
        ClassProbability(label="healthy", probability=healthy),
        ClassProbability(label="attention", probability=attention),
    )


_DEFAULT_PROBABILITIES = object()


def _prediction(
    value="healthy",
    *,
    mode=PredictionMode.CLASSIFICATION,
    probabilities=_DEFAULT_PROBABILITIES,
) -> MLPrediction:
    actual_probabilities = (
        _probabilities() if probabilities is _DEFAULT_PROBABILITIES else probabilities
    )
    return MLPrediction(
        task_id="ml_candidate",
        mode=mode,
        prediction=value,
        probabilities=actual_probabilities,
        evidence=PredictionEvidence(
            pipeline_id="sklearn_generic",
            feature_order=("latency_ms", "error_count", "is_cached"),
            used_probability_api=actual_probabilities is not None,
        ),
    )


def _task(**changes: object) -> MLTask:
    values = {"latency_ms": 12.5, "error_count": 0, "is_cached": True}
    values.update(changes)
    return MLTask(task_id="ml_candidate", features=values)


def _candidate_evaluator() -> MLCandidateEvaluator:
    return MLCandidateEvaluator(
        validator=MLDecisionValidator(),
        deduplicator=MLExactDeduplicator(),
    )


def test_classification_confidence_boundary_is_inclusive_and_auditable() -> None:
    settings = load_ml_config().ml
    result = MLDecisionValidator().evaluate(
        _prediction(probabilities=_probabilities(healthy=0.6, attention=0.4)),
        settings.prediction,
    )

    assert result.evidence.passed is True
    assert result.score == pytest.approx(0.6)
    assert result.evidence.details["pipeline_id"] == "sklearn_generic"


def test_classification_below_confidence_is_rejected() -> None:
    result = MLDecisionValidator().evaluate(
        _prediction(probabilities=_probabilities(healthy=0.59, attention=0.41)),
        load_ml_config().ml.prediction,
    )

    assert result.evidence.passed is False
    assert result.evidence.code == "confidence_error"
    assert "message" in result.evidence.details


def test_prediction_mode_mismatch_is_rejected() -> None:
    result = MLDecisionValidator().evaluate(
        _prediction(value=0.5, mode=PredictionMode.REGRESSION, probabilities=None),
        load_ml_config().ml.prediction,
    )

    assert result.evidence.passed is False
    assert result.evidence.code == "wrong_prediction_mode"


def test_missing_pipeline_identity_is_rejected() -> None:
    prediction = _prediction()
    prediction = MLPrediction(
        task_id=prediction.task_id,
        mode=prediction.mode,
        prediction=prediction.prediction,
        probabilities=prediction.probabilities,
        evidence=PredictionEvidence(
            pipeline_id=" ",
            feature_order=prediction.evidence.feature_order,
            used_probability_api=True,
        ),
    )

    result = MLDecisionValidator().evaluate(prediction, load_ml_config().ml.prediction)

    assert result.evidence.passed is False
    assert result.evidence.code == "missing_pipeline_identity"


@pytest.mark.parametrize(
    "prediction, code",
    [
        (_prediction(value="unknown"), "invalid_class"),
        (_prediction(value=1), "wrong_type"),
        (_prediction(probabilities=()), "invalid_probability"),
        (
            _prediction(
                probabilities=(
                    ClassProbability(label="healthy", probability=0.5),
                    ClassProbability(label="healthy", probability=0.5),
                )
            ),
            "invalid_probability",
        ),
        (
            _prediction(
                probabilities=(
                    ClassProbability(label="healthy", probability=0.5),
                    ClassProbability(label="other", probability=0.5),
                )
            ),
            "invalid_probability",
        ),
        (_prediction(probabilities=_probabilities(0.7, 0.4)), "invalid_probability"),
        (_prediction(probabilities=_probabilities(math.nan, math.nan)), "invalid_probability"),
        (
            _prediction(
                probabilities=(
                    ClassProbability(label="healthy", probability=True),
                    ClassProbability(label="attention", probability=0.0),
                )
            ),
            "invalid_probability",
        ),
        (_prediction(probabilities=None), "missing_probability"),
    ],
)
def test_classification_contract_failures_are_explicit(
    prediction: MLPrediction,
    code: str,
) -> None:
    result = MLDecisionValidator().evaluate(prediction, load_ml_config().ml.prediction)

    assert result.evidence.passed is False
    assert result.evidence.code == code
    assert result.evidence.details["message"]


@pytest.mark.parametrize("value", [-1.0, 1.0])
def test_regression_range_boundaries_are_inclusive(value: float) -> None:
    settings = RegressionPredictionSettings(mode="regression", minimum=-1.0, maximum=1.0)
    prediction = _prediction(
        value=value,
        mode=PredictionMode.REGRESSION,
        probabilities=None,
    )

    result = MLDecisionValidator().evaluate(prediction, settings)

    assert result.evidence.passed is True
    assert result.score == value


@pytest.mark.parametrize(
    "value, probabilities, code",
    [
        (2.0, None, "range_error"),
        (math.nan, None, "nan_detected"),
        (math.inf, None, "infinity_detected"),
        (True, None, "wrong_type"),
        (0.0, _probabilities(), "invalid_probability"),
    ],
)
def test_regression_contract_failures_are_explicit(value, probabilities, code: str) -> None:
    prediction = _prediction(
        value=value,
        mode=PredictionMode.REGRESSION,
        probabilities=probabilities,
    )
    settings = RegressionPredictionSettings(mode="regression", minimum=-1.0, maximum=1.0)

    result = MLDecisionValidator().evaluate(prediction, settings)

    assert result.evidence.passed is False
    assert result.evidence.code == code


def test_invalid_prediction_stops_before_duplicate_lookup() -> None:
    lookup = FakeLookup()
    result = _candidate_evaluator().evaluate(
        _prediction(value="unknown"),
        _task(),
        load_ml_config().ml,
        lookup,
    )

    assert result.accepted is False
    assert result.failure_code == "invalid_class"
    assert result.failure_reason
    assert lookup.calls == 0
    assert [item.check_id for item in result.evidence] == ["ml_validation"]


def test_canonical_identity_ignores_key_order_and_duplicate_is_auditable() -> None:
    lookup = FakeLookup(DuplicateMLInput(sample_id="sample-1", task_id="task-1"))
    settings = load_ml_config().ml
    first = _task()
    second = MLTask(
        task_id="second",
        features={"is_cached": True, "error_count": 0, "latency_ms": 12.5},
    )

    first_result = MLExactDeduplicator().evaluate(
        first,
        feature_contract=settings.features,
        dataset_id=settings.dataset_id,
        lookup=lookup,
    )
    second_result = MLExactDeduplicator().evaluate(
        second,
        feature_contract=settings.features,
        dataset_id=settings.dataset_id,
        lookup=lookup,
    )

    assert first_result.canonical_input == second_result.canonical_input
    assert lookup.canonical_inputs[0] == lookup.canonical_inputs[1]
    assert first_result.evidence.passed is False
    assert first_result.evidence.code == "duplicate_sample"
    assert first_result.evidence.details["duplicate_sample_id"] == "sample-1"


def test_declared_numeric_types_are_not_interchangeable() -> None:
    settings = load_ml_config().ml
    deduplicator = MLExactDeduplicator()

    with pytest.raises(MLInputError):
        deduplicator.evaluate(
            _task(latency_ms=12),
            feature_contract=settings.features,
            dataset_id=settings.dataset_id,
            lookup=FakeLookup(),
        )
    with pytest.raises(MLInputError):
        deduplicator.evaluate(
            _task(error_count=0.0),
            feature_contract=settings.features,
            dataset_id=settings.dataset_id,
            lookup=FakeLookup(),
        )


def test_valid_unique_candidate_contains_ordered_evidence() -> None:
    result = _candidate_evaluator().evaluate(
        _prediction(),
        _task(),
        load_ml_config().ml,
        FakeLookup(),
    )

    assert result.accepted is True
    assert result.canonical_input == '{"error_count":0,"is_cached":true,"latency_ms":12.5}'
    assert [item.check_id for item in result.evidence] == [
        "ml_validation",
        "ml_exact_dedup",
    ]
    assert all(item.passed for item in result.evidence)
