"""ML-specific serialization boundary."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..core.export import ExportError, ExportRow


def _score(value: Any) -> float | None:
    return None if value is None else float(value)


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExportError(f"ML export requires {field}")
    return value


def _required_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise ExportError(f"ML export requires {field}")
    return value


class MLExportSerializer:
    branch_id = "ml"

    def serialize(self, row: ExportRow) -> Mapping[str, Any]:
        if row.model_type != self.branch_id:
            raise ExportError("ML serializer received a non-ML row")
        decision = row.parsed_output or {}
        pipeline_id = decision.get(
            "pipeline_id",
            row.generation_metadata.get(
                "pipeline_id",
                row.sample_metadata.get("pipeline_id"),
            ),
        )
        artifact_identity = row.generation_metadata.get(
            "artifact_identity",
            row.sample_metadata.get("artifact_identity"),
        )
        pipeline_id = _required_string(pipeline_id, "pipeline identity")
        artifact_identity = _required_string(artifact_identity, "artifact identity")
        if Path(artifact_identity).is_absolute():
            raise ExportError("ML artifact identity must not expose an absolute path")
        validation_evidence = _required_mapping(
            row.validation_details,
            "validation evidence",
        )
        return {
            "sample_type": self.branch_id,
            "sample_id": row.sample_id,
            "dataset_id": row.dataset_id,
            "status": row.sample_status,
            "task": {
                "task_id": row.task_id,
                "features": row.task_input_payload,
            },
            "decision": {
                "prediction": decision.get("prediction"),
                "probabilities": decision.get("probabilities"),
                "score": _score(row.validation_score),
            },
            "validation": {
                "validation_id": row.validation_id,
                "validator_version": row.validator_version,
                "is_valid": row.is_valid,
                "failure_code": row.validation_failure_code,
                "failure_reason": row.validation_failure_reason,
                "evidence": validation_evidence,
            },
            "pipeline": {
                "pipeline_id": pipeline_id,
                "artifact_identity": artifact_identity,
            },
            "model": {
                "model_id": row.model_id,
                "model_name": row.model_name,
                "model_type": row.model_type,
            },
            "provenance": {
                "run_id": row.run_id,
                "generation_id": row.generation_id,
                "config_id": row.config_id,
                "selector_version": row.selector_version,
                "created_at": row.sample_created_at.isoformat(),
            },
            "disposition": {
                "score": _score(row.sample_score),
                "failure_code": row.sample_failure_code,
                "failure_reason": row.sample_failure_reason,
            },
        }
