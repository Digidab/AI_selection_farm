"""LLM-specific serialization boundary."""

from collections.abc import Mapping
from typing import Any

from ..core.export import ExportError, ExportRow


def _score(value: Any) -> float | None:
    return None if value is None else float(value)


def _required_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise ExportError(f"LLM export requires {field}")
    return value


def _component_profile(value: Any) -> Mapping[str, Any]:
    profile = _required_mapping(value, "component profile")
    required_keys = {
        "pipeline_id",
        "runtime_id",
        "modalities",
        "output_contract",
        "evaluators",
    }
    if set(profile) != required_keys:
        raise ExportError("LLM component profile has an invalid identity shape")
    return profile


class LLMExportSerializer:
    branch_id = "llm"

    def serialize(self, row: ExportRow) -> Mapping[str, Any]:
        if row.model_type != self.branch_id:
            raise ExportError("LLM serializer received a non-LLM row")
        component_profile = row.sample_metadata.get(
            "component_profile",
            row.generation_metadata.get("component_profile"),
        )
        component_profile = _component_profile(component_profile)
        validation_evidence = _required_mapping(
            row.validation_details,
            "validation evidence",
        )
        task_prompt = row.task_input_payload.get("prompt")
        task_messages = row.task_input_payload.get("messages")
        expected_schema = row.task_expected_schema or row.task_input_payload.get("expected_schema")
        structured_completion = row.parsed_output
        if structured_completion is None and row.validation_details is not None:
            structured_completion = row.validation_details.get("output_payload")
        return {
            "sample_type": self.branch_id,
            "sample_id": row.sample_id,
            "dataset_id": row.dataset_id,
            "status": row.sample_status,
            "task": {
                "task_id": row.task_id,
                "prompt": task_prompt,
                "messages": task_messages,
                "expected_schema": expected_schema,
            },
            "completion": {
                "raw": row.completion or row.raw_output,
                "structured": structured_completion,
            },
            "validation": {
                "validation_id": row.validation_id,
                "validator_version": row.validator_version,
                "is_valid": row.is_valid,
                "score": _score(row.validation_score),
                "failure_code": row.validation_failure_code,
                "failure_reason": row.validation_failure_reason,
                "evidence": validation_evidence,
            },
            "components": component_profile,
            "model": {
                "model_id": row.model_id,
                "model_name": row.model_name,
                "model_type": row.model_type,
                "base_model": row.base_model,
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
