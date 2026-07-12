"""Reference adapter for trusted local joblib/scikit-learn artifacts."""

import math
from pathlib import Path
from typing import Any

import joblib

from ...core.schemas import CoreError, ErrorCode
from ..config import ClassificationPredictionSettings, PredictionSettings
from ..schemas import (
    FeatureDefinition,
    FeatureType,
    MLPipelineDescriptor,
    MLTask,
    PredictionMode,
    ordered_feature_values,
)
from .interfaces import (
    ClassProbability,
    MLPrediction,
    PredictionEvidence,
    PredictionValue,
)


class MLPipelineError(CoreError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.EXECUTION, message)


def _plain_value(value: Any, *, field: str) -> PredictionValue:
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            value = item_method()
        except (TypeError, ValueError) as exc:
            raise MLPipelineError(f"{field} is not a scalar value") from exc
    if type(value) not in {str, int, float, bool}:
        raise MLPipelineError(f"{field} must be a JSON-compatible scalar")
    if type(value) is float and not math.isfinite(value):
        raise MLPipelineError(f"{field} must be finite")
    return value


def _plain_sequence(value: Any, *, field: str) -> list[Any]:
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        value = tolist()
    if not isinstance(value, (list, tuple)):
        raise MLPipelineError(f"{field} must be an array")
    return list(value)


def _single_prediction(value: Any) -> PredictionValue:
    values = _plain_sequence(value, field="predict result")
    if len(values) != 1:
        raise MLPipelineError("predict must return exactly one result")
    return _plain_value(values[0], field="prediction")


def _probabilities(estimator: Any, feature_row: list[list[Any]]) -> tuple[ClassProbability, ...]:
    predict_proba = getattr(estimator, "predict_proba", None)
    if not callable(predict_proba):
        raise MLPipelineError("Configured confidence requires callable predict_proba")
    classes = getattr(estimator, "classes_", None)
    if classes is None:
        raise MLPipelineError("Configured confidence requires estimator classes_")

    try:
        raw_probabilities = predict_proba(feature_row)
    except Exception as exc:
        raise MLPipelineError("predict_proba failed") from exc
    rows = _plain_sequence(raw_probabilities, field="predict_proba result")
    if len(rows) != 1:
        raise MLPipelineError("predict_proba must return exactly one row")
    values = _plain_sequence(rows[0], field="probability row")
    labels = _plain_sequence(classes, field="classes_")
    if not values or len(values) != len(labels):
        raise MLPipelineError("Probability count must match estimator classes_")

    normalized: list[ClassProbability] = []
    for label, probability in zip(labels, values, strict=True):
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            raise MLPipelineError("Probability values must be numeric")
        numeric_probability = float(probability)
        if not math.isfinite(numeric_probability):
            raise MLPipelineError("Probability values must be finite")
        normalized.append(
            ClassProbability(
                label=_plain_value(label, field="class label"),
                probability=numeric_probability,
            )
        )
    return tuple(normalized)


class SklearnGenericAdapter:
    descriptor = MLPipelineDescriptor(
        pipeline_id="sklearn_generic",
        artifact_formats=frozenset({"joblib"}),
        supported_modes=frozenset({PredictionMode.CLASSIFICATION, PredictionMode.REGRESSION}),
        supported_feature_types=frozenset(FeatureType),
        probability_api_optional=True,
    )

    def predict(
        self,
        task: MLTask,
        *,
        artifact_path: Path,
        feature_contract: tuple[FeatureDefinition, ...],
        prediction_settings: PredictionSettings,
    ) -> MLPrediction:
        path = Path(artifact_path)
        if path.suffix.lower() != ".joblib" or not path.is_file():
            raise MLPipelineError("ML artifact must be an existing .joblib file")
        if prediction_settings.mode not in self.descriptor.supported_modes:
            raise MLPipelineError(f"Unsupported prediction mode: {prediction_settings.mode}")
        unsupported_types = {
            feature.data_type for feature in feature_contract
        } - self.descriptor.supported_feature_types
        if unsupported_types:
            raise MLPipelineError("Feature contract contains unsupported types")

        feature_values = ordered_feature_values(task, feature_contract)
        feature_row = [list(feature_values)]

        try:
            estimator = joblib.load(path)
        except Exception as exc:
            raise MLPipelineError("Cannot load trusted local ML artifact") from exc
        predict = getattr(estimator, "predict", None)
        if not callable(predict):
            raise MLPipelineError("ML artifact must expose callable predict")

        try:
            prediction = _single_prediction(predict(feature_row))
        except MLPipelineError:
            raise
        except Exception as exc:
            raise MLPipelineError("predict failed") from exc

        requires_probability = (
            isinstance(prediction_settings, ClassificationPredictionSettings)
            and prediction_settings.confidence is not None
            and prediction_settings.confidence.required
        )
        probabilities = _probabilities(estimator, feature_row) if requires_probability else None
        return MLPrediction(
            task_id=task.task_id,
            mode=prediction_settings.mode,
            prediction=prediction,
            probabilities=probabilities,
            evidence=PredictionEvidence(
                pipeline_id=self.descriptor.pipeline_id,
                feature_order=tuple(feature.name for feature in feature_contract),
                used_probability_api=requires_probability,
            ),
        )
