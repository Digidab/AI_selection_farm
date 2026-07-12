from pathlib import Path

import orjson
import pytest
from pydantic import ValidationError

from services.selector.app.ml.config import load_ml_config
from services.selector.app.ml.schemas import (
    FeatureDefinition,
    FeatureType,
    MLInputError,
    MLPipelineDescriptor,
    MLTask,
    PredictionMode,
    canonical_feature_json,
    load_ml_tasks,
    ordered_feature_values,
    validate_feature_payload,
)


def _contract() -> tuple[FeatureDefinition, ...]:
    return (
        FeatureDefinition(name="latency_ms", data_type=FeatureType.FLOAT),
        FeatureDefinition(name="error_count", data_type=FeatureType.INTEGER),
        FeatureDefinition(name="is_cached", data_type=FeatureType.BOOLEAN),
    )


def _valid_task(**features: object) -> MLTask:
    payload = {"latency_ms": 12.5, "error_count": 0, "is_cached": True}
    payload.update(features)
    return MLTask(task_id="ml_test", features=payload)


def test_fixture_tasks_are_deterministic_and_typed() -> None:
    config = load_ml_config()
    tasks = load_ml_tasks(config.ml.tasks_path, config.ml.features)

    assert [task.task_id for task in tasks] == ["ml_seed_001", "ml_seed_002"]
    assert ordered_feature_values(tasks[0], config.ml.features) == (12.5, 0, True)


@pytest.mark.parametrize(
    "features",
    [
        {"error_count": None},
        {"error_count": True},
        {"latency_ms": 12},
        {"latency_ms": float("nan")},
        {"latency_ms": float("inf")},
        {"is_cached": 1},
    ],
)
def test_wrong_or_non_finite_feature_type_is_rejected(features: dict[str, object]) -> None:
    with pytest.raises(MLInputError):
        validate_feature_payload(_valid_task(**features), _contract())


def test_missing_and_extra_features_are_rejected() -> None:
    missing = MLTask(
        task_id="missing",
        features={"latency_ms": 1.0, "error_count": 0},
    )
    extra = _valid_task(unexpected="value")

    with pytest.raises(MLInputError):
        validate_feature_payload(missing, _contract())
    with pytest.raises(MLInputError):
        validate_feature_payload(extra, _contract())


def test_canonical_identity_ignores_json_key_order() -> None:
    first = MLTask(
        task_id="first",
        features={"latency_ms": 1.5, "error_count": 1, "is_cached": False},
    )
    second = MLTask(
        task_id="second",
        features={"is_cached": False, "error_count": 1, "latency_ms": 1.5},
    )

    assert canonical_feature_json(first, _contract()) == canonical_feature_json(second, _contract())


def test_task_and_pipeline_descriptor_are_strict() -> None:
    task = _valid_task()
    with pytest.raises(ValidationError):
        task.task_id = "changed"

    descriptor = MLPipelineDescriptor(
        pipeline_id="sklearn_generic",
        artifact_formats=frozenset({"joblib"}),
        supported_modes=frozenset({PredictionMode.CLASSIFICATION}),
        supported_feature_types=frozenset(FeatureType),
        probability_api_optional=True,
    )
    assert descriptor.pipeline_id == "sklearn_generic"

    with pytest.raises(ValidationError):
        MLPipelineDescriptor(
            pipeline_id="invalid",
            artifact_formats=frozenset(),
            supported_modes=frozenset(),
            supported_feature_types=frozenset(),
            probability_api_optional=True,
        )


def test_loader_rejects_malformed_duplicate_and_blank_records(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.jsonl"
    malformed.write_bytes(b"{not-json}\n")
    with pytest.raises(MLInputError):
        load_ml_tasks(malformed, _contract())

    raw_task = {
        "task_id": "duplicate",
        "features": {"latency_ms": 1.0, "error_count": 0, "is_cached": True},
    }
    duplicate = tmp_path / "duplicate.jsonl"
    duplicate.write_bytes(orjson.dumps(raw_task) + b"\n" + orjson.dumps(raw_task) + b"\n")
    with pytest.raises(MLInputError):
        load_ml_tasks(duplicate, _contract())

    blank = tmp_path / "blank.jsonl"
    blank.write_bytes(orjson.dumps(raw_task) + b"\n\n")
    with pytest.raises(MLInputError):
        load_ml_tasks(blank, _contract())
