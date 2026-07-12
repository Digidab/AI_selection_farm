from dataclasses import replace
from datetime import UTC, datetime

import orjson
import pytest

from services.selector.app.core.export import ExportError, ExportRow
from services.selector.app.llm.exporter import LLMExportSerializer
from services.selector.app.ml.exporter import MLExportSerializer


def _row(branch: str, status: str = "accepted") -> ExportRow:
    parsed_output = (
        {"answer": "ok"}
        if branch == "llm"
        else {
            "pipeline_id": "sklearn_generic",
            "prediction": "healthy",
            "probabilities": {"healthy": 0.8, "attention": 0.2},
        }
    )
    return ExportRow(
        sample_id=f"{branch}_sample",
        sample_status=status,
        dataset_id=f"selector_{branch}_seed_v001",
        selector_version="selector_v001",
        sample_score=0.8,
        sample_failure_code=None if status == "accepted" else "logic_error",
        sample_failure_reason=None if status == "accepted" else "fixture rejection",
        sample_metadata={
            "component_profile": {
                "pipeline_id": "single_turn",
                "runtime_id": "ollama",
                "modalities": ["text"],
                "output_contract": "structured_json",
                "evaluators": ["json_schema", "semantic_dedup"],
            },
            "artifact_identity": "model-fixture-v1",
        },
        sample_created_at=datetime(2026, 7, 12, 12, 30, tzinfo=UTC),
        task_id=f"{branch}_task",
        task_input_payload=(
            {"prompt": "Return JSON"}
            if branch == "llm"
            else {"latency_ms": 12.5, "error_count": 0, "is_cached": True}
        ),
        task_expected_schema={"type": "object"} if branch == "llm" else None,
        generation_id=f"{branch}_generation",
        raw_output='{"answer":"ok"}',
        parsed_output=parsed_output,
        generation_metadata={
            "component_profile": {
                "pipeline_id": "single_turn",
                "runtime_id": "ollama",
                "modalities": ["text"],
                "output_contract": "structured_json",
                "evaluators": ["json_schema", "semantic_dedup"],
            },
            "pipeline_id": "sklearn_generic",
            "artifact_identity": "model-fixture-v1",
        },
        validation_id=f"{branch}_validation",
        validator_version="selector_v001",
        is_valid=status == "accepted",
        validation_score=0.8,
        validation_failure_code=None if status == "accepted" else "logic_error",
        validation_failure_reason=None if status == "accepted" else "fixture rejection",
        validation_details={"evidence": [{"check_id": "fixture", "passed": True}]},
        run_id=f"{branch}_run",
        config_id=f"{branch}_v001",
        model_id=f"{branch}_model",
        model_name=f"{branch} fixture",
        model_type=branch,
        base_model="qwen3:0.6b" if branch == "llm" else None,
        completion='{"answer":"ok"}',
    )


def test_llm_serializer_has_llm_specific_golden_shape() -> None:
    payload = LLMExportSerializer().serialize(_row("llm"))

    assert payload["sample_type"] == "llm"
    assert payload["task"]["prompt"] == "Return JSON"
    assert payload["completion"]["structured"] == {"answer": "ok"}
    assert payload["components"]["pipeline_id"] == "single_turn"
    assert payload["components"]["evaluators"] == ["json_schema", "semantic_dedup"]
    assert payload["validation"]["evidence"] == {
        "evidence": [{"check_id": "fixture", "passed": True}]
    }
    assert payload["provenance"]["run_id"] == "llm_run"
    assert "pipeline" not in payload


def test_llm_serializer_uses_neutral_payload_and_validation_resume_fallbacks() -> None:
    row = replace(
        _row("llm"),
        task_input_payload={
            "prompt": "Return JSON",
            "expected_schema": {"type": "object"},
        },
        task_expected_schema=None,
        parsed_output=None,
        validation_details={
            "output_payload": {"answer": "ok"},
            "evidence": [{"check_id": "fixture", "passed": True}],
        },
    )

    payload = LLMExportSerializer().serialize(row)

    assert payload["task"]["expected_schema"] == {"type": "object"}
    assert payload["completion"]["structured"] == {"answer": "ok"}


def test_ml_serializer_has_ml_specific_golden_shape() -> None:
    payload = MLExportSerializer().serialize(_row("ml"))

    assert payload["sample_type"] == "ml"
    assert payload["task"]["features"] == {
        "latency_ms": 12.5,
        "error_count": 0,
        "is_cached": True,
    }
    assert payload["decision"]["prediction"] == "healthy"
    assert payload["decision"]["probabilities"] == {
        "healthy": 0.8,
        "attention": 0.2,
    }
    assert payload["pipeline"] == {
        "pipeline_id": "sklearn_generic",
        "artifact_identity": "model-fixture-v1",
    }
    assert payload["provenance"]["run_id"] == "ml_run"
    assert "components" not in payload


def test_branch_serializers_are_byte_stable_and_keep_rejection_evidence() -> None:
    llm = LLMExportSerializer().serialize(_row("llm", "rejected"))
    ml = MLExportSerializer().serialize(_row("ml", "rejected"))

    assert orjson.dumps(llm, option=orjson.OPT_SORT_KEYS) == orjson.dumps(
        llm, option=orjson.OPT_SORT_KEYS
    )
    assert orjson.dumps(ml, option=orjson.OPT_SORT_KEYS) == orjson.dumps(
        ml, option=orjson.OPT_SORT_KEYS
    )
    assert llm["disposition"]["failure_code"] == "logic_error"
    assert ml["disposition"]["failure_reason"] == "fixture rejection"


def test_branch_serializers_reject_cross_branch_rows() -> None:
    with pytest.raises(ExportError, match="non-LLM"):
        LLMExportSerializer().serialize(_row("ml"))
    with pytest.raises(ExportError, match="non-ML"):
        MLExportSerializer().serialize(_row("llm"))


def test_branch_serializers_fail_closed_on_missing_branch_evidence() -> None:
    llm_row = replace(_row("llm"), sample_metadata={}, generation_metadata={})
    ml_row = replace(_row("ml"), sample_metadata={}, generation_metadata={})
    ml_without_pipeline = replace(
        _row("ml"),
        parsed_output={"prediction": "healthy"},
        generation_metadata={"artifact_identity": "fixture"},
        sample_metadata={},
    )

    with pytest.raises(ExportError, match="component profile"):
        LLMExportSerializer().serialize(llm_row)
    with pytest.raises(ExportError, match="artifact identity"):
        MLExportSerializer().serialize(ml_row)
    with pytest.raises(ExportError, match="pipeline identity"):
        MLExportSerializer().serialize(ml_without_pipeline)

    ml_absolute_artifact = replace(
        _row("ml"),
        generation_metadata={"pipeline_id": "sklearn_generic"},
        sample_metadata={"artifact_identity": "/tmp/model.joblib"},
    )
    with pytest.raises(ExportError, match="absolute path"):
        MLExportSerializer().serialize(ml_absolute_artifact)
