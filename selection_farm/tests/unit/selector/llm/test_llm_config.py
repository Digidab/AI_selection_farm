from pathlib import Path
from typing import Any

import pytest
import yaml

from services.selector.app.core.config import PROJECT_ROOT
from services.selector.app.llm.config import (
    DEFAULT_LLM_CONFIG_PATH,
    LLMConfigError,
    load_llm_config,
)


def _raw_config() -> dict[str, Any]:
    config_path = PROJECT_ROOT / DEFAULT_LLM_CONFIG_PATH
    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert isinstance(raw_config, dict)
    return raw_config


def _write_config(path: Path, config: dict[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def test_default_llm_config_is_explicit_and_cwd_independent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    config = load_llm_config()

    assert config.llm.branch == "llm"
    assert config.llm.model_id == "_tz08_llm_model_fixture"
    assert config.llm.dataset_id == "selector_llm_seed_v001"
    assert config.llm.tasks_path == PROJECT_ROOT / "datasets/raw/llm/tasks_v001.jsonl"
    assert config.llm.components.pipeline_id == "single_turn"
    assert config.llm.components.runtime_id == "ollama"
    assert config.llm.components.modalities == ("text",)
    assert config.llm.components.output_contract == "structured_json"
    assert config.llm.components.evaluators == ("json_schema", "semantic_dedup")


def test_cross_branch_key_is_rejected(tmp_path: Path) -> None:
    raw_config = _raw_config()
    raw_config["artifact_path"] = "forbidden.joblib"

    with pytest.raises(LLMConfigError):
        load_llm_config(_write_config(tmp_path / "cross_branch.yaml", raw_config))


def test_missing_component_identity_is_rejected(tmp_path: Path) -> None:
    raw_config = _raw_config()
    del raw_config["components"]["runtime_id"]

    with pytest.raises(LLMConfigError):
        load_llm_config(_write_config(tmp_path / "missing.yaml", raw_config))


@pytest.mark.parametrize("field", ["branch", "model_id", "dataset_id"])
def test_missing_branch_identity_is_rejected(tmp_path: Path, field: str) -> None:
    raw_config = _raw_config()
    del raw_config[field]

    with pytest.raises(LLMConfigError):
        load_llm_config(_write_config(tmp_path / f"missing_{field}.yaml", raw_config))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pipeline_id", "unknown_pipeline"),
        ("runtime_id", "unknown_runtime"),
        ("output_contract", "unknown_contract"),
    ],
)
def test_unknown_component_identity_is_rejected(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    raw_config = _raw_config()
    raw_config["components"][field] = value

    with pytest.raises(LLMConfigError):
        load_llm_config(_write_config(tmp_path / f"unknown_{field}.yaml", raw_config))


def test_duplicate_or_reordered_evaluators_are_rejected(tmp_path: Path) -> None:
    for evaluators in (
        ["json_schema", "json_schema"],
        ["semantic_dedup", "json_schema"],
    ):
        raw_config = _raw_config()
        raw_config["components"]["evaluators"] = evaluators

        with pytest.raises(LLMConfigError):
            load_llm_config(
                _write_config(tmp_path / f"evaluators_{evaluators[0]}.yaml", raw_config)
            )


def test_incompatible_modality_is_rejected(tmp_path: Path) -> None:
    raw_config = _raw_config()
    raw_config["components"]["modalities"] = ["image"]

    with pytest.raises(LLMConfigError):
        load_llm_config(_write_config(tmp_path / "incompatible.yaml", raw_config))


def test_wrong_dataset_identity_is_rejected(tmp_path: Path) -> None:
    raw_config = _raw_config()
    raw_config["dataset_id"] = "shared_dataset"

    with pytest.raises(LLMConfigError):
        load_llm_config(_write_config(tmp_path / "dataset.yaml", raw_config))


def test_malformed_yaml_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "malformed.yaml"
    config_path.write_text("components: [\n", encoding="utf-8")

    with pytest.raises(LLMConfigError):
        load_llm_config(config_path)
