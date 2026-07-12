from pathlib import Path
from typing import Any

import pytest
import yaml

from services.selector.app.core.config import PROJECT_ROOT
from services.selector.app.ml.config import (
    DEFAULT_ML_CONFIG_PATH,
    MLConfigError,
    load_ml_config,
)
from services.selector.app.ml.schemas import PredictionMode


def _raw_config() -> dict[str, Any]:
    config_path = PROJECT_ROOT / DEFAULT_ML_CONFIG_PATH
    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert isinstance(raw_config, dict)
    return raw_config


def _write_config(path: Path, config: dict[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def test_default_ml_config_is_explicit_and_cwd_independent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    config = load_ml_config()

    assert config.ml.branch == "ml"
    assert config.ml.model_id == "_tz08_ml_model_fixture"
    assert config.ml.dataset_id == "selector_ml_seed_v001"
    assert config.ml.pipeline_id == "sklearn_generic"
    assert config.ml.tasks_path == PROJECT_ROOT / "datasets/raw/ml/tasks_v001.jsonl"
    assert config.ml.artifact_path == (
        PROJECT_ROOT / "stable/ml_models_stall/_tz08_fixture/model.joblib"
    )
    assert [feature.name for feature in config.ml.features] == [
        "latency_ms",
        "error_count",
        "is_cached",
    ]
    assert config.ml.prediction.mode is PredictionMode.CLASSIFICATION
    assert config.ml.pipeline_descriptor().probability_api_optional is True


@pytest.mark.parametrize("field", ["branch", "model_id", "dataset_id"])
def test_missing_branch_identity_is_rejected(tmp_path: Path, field: str) -> None:
    raw_config = _raw_config()
    del raw_config[field]

    with pytest.raises(MLConfigError):
        load_ml_config(_write_config(tmp_path / f"missing_{field}.yaml", raw_config))


def test_missing_or_unknown_pipeline_is_rejected(tmp_path: Path) -> None:
    missing = _raw_config()
    del missing["pipeline_id"]
    with pytest.raises(MLConfigError):
        load_ml_config(_write_config(tmp_path / "missing_pipeline.yaml", missing))

    unknown = _raw_config()
    unknown["pipeline_id"] = "random_forest"
    with pytest.raises(MLConfigError):
        load_ml_config(_write_config(tmp_path / "unknown_pipeline.yaml", unknown))


@pytest.mark.parametrize("field", ["prompt", "ollama_host", "embedding_model"])
def test_llm_key_is_rejected(tmp_path: Path, field: str) -> None:
    raw_config = _raw_config()
    raw_config[field] = "forbidden"

    with pytest.raises(MLConfigError):
        load_ml_config(_write_config(tmp_path / f"cross_branch_{field}.yaml", raw_config))


def test_duplicate_or_unknown_features_are_rejected(tmp_path: Path) -> None:
    duplicate = _raw_config()
    duplicate["features"].append({"name": "latency_ms", "data_type": "float"})
    with pytest.raises(MLConfigError):
        load_ml_config(_write_config(tmp_path / "duplicate_feature.yaml", duplicate))

    unknown = _raw_config()
    unknown["features"][0]["data_type"] = "number"
    with pytest.raises(MLConfigError):
        load_ml_config(_write_config(tmp_path / "unknown_feature.yaml", unknown))


def test_classification_rules_are_strict(tmp_path: Path) -> None:
    duplicate = _raw_config()
    duplicate["prediction"]["allowed_classes"] = ["healthy", "healthy"]
    with pytest.raises(MLConfigError):
        load_ml_config(_write_config(tmp_path / "duplicate_classes.yaml", duplicate))

    non_finite = _raw_config()
    non_finite["prediction"]["confidence"]["minimum"] = float("nan")
    with pytest.raises(MLConfigError):
        load_ml_config(_write_config(tmp_path / "non_finite_confidence.yaml", non_finite))


def test_regression_range_is_finite_and_ordered(tmp_path: Path) -> None:
    invalid_range = _raw_config()
    invalid_range["prediction"] = {
        "mode": "regression",
        "minimum": 10.0,
        "maximum": 5.0,
    }
    with pytest.raises(MLConfigError):
        load_ml_config(_write_config(tmp_path / "invalid_range.yaml", invalid_range))

    non_finite = _raw_config()
    non_finite["prediction"] = {
        "mode": "regression",
        "minimum": 0.0,
        "maximum": float("inf"),
    }
    with pytest.raises(MLConfigError):
        load_ml_config(_write_config(tmp_path / "non_finite_range.yaml", non_finite))


def test_artifact_path_cannot_escape_project(tmp_path: Path) -> None:
    raw_config = _raw_config()
    raw_config["artifact_path"] = "../outside.joblib"

    with pytest.raises(MLConfigError):
        load_ml_config(_write_config(tmp_path / "unsafe_path.yaml", raw_config))


def test_malformed_yaml_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "malformed.yaml"
    config_path.write_text("features: [\n", encoding="utf-8")

    with pytest.raises(MLConfigError):
        load_ml_config(config_path)
