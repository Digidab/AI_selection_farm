"""Strict ML feature, task, and pipeline records."""

import math
from enum import StrEnum
from pathlib import Path
from typing import Any, Sequence

import orjson
from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError, model_validator

from ..core.schemas import CoreError, ErrorCode, NonEmptyString


class _StrictMLRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FeatureType(StrEnum):
    FLOAT = "float"
    INTEGER = "integer"
    STRING = "string"
    BOOLEAN = "boolean"


class PredictionMode(StrEnum):
    CLASSIFICATION = "classification"
    REGRESSION = "regression"


class FeatureDefinition(_StrictMLRecord):
    name: NonEmptyString
    data_type: FeatureType


class MLTask(_StrictMLRecord):
    task_id: NonEmptyString
    features: dict[str, Any]


class MLPipelineDescriptor(_StrictMLRecord):
    pipeline_id: NonEmptyString
    artifact_formats: frozenset[NonEmptyString]
    supported_modes: frozenset[PredictionMode]
    supported_feature_types: frozenset[FeatureType]
    probability_api_optional: StrictBool

    @model_validator(mode="after")
    def validate_capabilities(self) -> "MLPipelineDescriptor":
        if (
            not self.artifact_formats
            or not self.supported_modes
            or not self.supported_feature_types
        ):
            raise ValueError("ML pipeline descriptor capabilities must not be empty")
        return self


class MLInputError(CoreError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.VALIDATION, message)


def _matches_feature_type(value: Any, data_type: FeatureType) -> bool:
    if data_type is FeatureType.FLOAT:
        return type(value) is float and math.isfinite(value)
    if data_type is FeatureType.INTEGER:
        return type(value) is int
    if data_type is FeatureType.STRING:
        return type(value) is str
    if data_type is FeatureType.BOOLEAN:
        return type(value) is bool
    return False


def validate_feature_payload(
    task: MLTask,
    feature_contract: Sequence[FeatureDefinition],
) -> None:
    expected_names = tuple(feature.name for feature in feature_contract)
    if not expected_names or len(set(expected_names)) != len(expected_names):
        raise MLInputError("Feature contract must contain unique ordered features")

    expected_set = set(expected_names)
    actual_set = set(task.features)
    missing = sorted(expected_set - actual_set)
    extra = sorted(actual_set - expected_set)
    if missing or extra:
        raise MLInputError(f"Feature keys do not match contract; missing={missing}, extra={extra}")

    for feature in feature_contract:
        value = task.features[feature.name]
        if not _matches_feature_type(value, feature.data_type):
            raise MLInputError(f"Feature {feature.name} must have type {feature.data_type.value}")


def ordered_feature_values(
    task: MLTask,
    feature_contract: Sequence[FeatureDefinition],
) -> tuple[Any, ...]:
    validate_feature_payload(task, feature_contract)
    return tuple(task.features[feature.name] for feature in feature_contract)


def canonical_feature_json(
    task: MLTask,
    feature_contract: Sequence[FeatureDefinition],
) -> bytes:
    validate_feature_payload(task, feature_contract)
    normalized = {feature.name: task.features[feature.name] for feature in feature_contract}
    return orjson.dumps(normalized, option=orjson.OPT_SORT_KEYS)


def load_ml_tasks(
    path: str | Path,
    feature_contract: Sequence[FeatureDefinition],
) -> tuple[MLTask, ...]:
    task_path = Path(path)
    try:
        lines = task_path.read_bytes().splitlines()
    except OSError as exc:
        raise MLInputError(f"Cannot read ML tasks: {task_path}") from exc

    if not lines:
        raise MLInputError(f"ML task file must not be empty: {task_path}")

    tasks: list[MLTask] = []
    seen_task_ids: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise MLInputError(f"Blank JSONL record at line {line_number}: {task_path}")
        try:
            raw_task = orjson.loads(line)
            task = MLTask.model_validate(raw_task)
            validate_feature_payload(task, feature_contract)
        except (orjson.JSONDecodeError, ValidationError, MLInputError) as exc:
            raise MLInputError(f"Invalid ML task at line {line_number}: {task_path}") from exc
        if task.task_id in seen_task_ids:
            raise MLInputError(f"Duplicate ML task_id at line {line_number}: {task.task_id}")
        seen_task_ids.add(task.task_id)
        tasks.append(task)

    return tuple(tasks)
