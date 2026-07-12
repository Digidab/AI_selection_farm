"""Draft 2020-12 JSON Schema evaluator for parsed LLM output."""

from typing import Any

from jsonschema import Draft202012Validator

from ...core.schemas import EvidenceRecord
from ..output_contracts.structured_json import ParsedStructuredJSON
from ..schemas import CapabilityDescriptor, ComponentKind


def _json_path(parts: list[Any]) -> str:
    path = "$"
    for part in parts:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path


class JSONSchemaEvaluator:
    descriptor = CapabilityDescriptor(
        component_id="json_schema",
        kind=ComponentKind.EVALUATOR,
        capabilities=frozenset({"draft_2020_12"}),
        input_modalities=frozenset({"text"}),
        output_contracts=frozenset({"structured_json"}),
        supports_streaming=False,
    )

    def evaluate(
        self,
        candidate: ParsedStructuredJSON,
        expected_schema: dict[str, Any],
    ) -> EvidenceRecord:
        errors = sorted(
            Draft202012Validator(expected_schema).iter_errors(candidate.value),
            key=lambda error: (
                tuple(str(part) for part in error.absolute_path),
                error.message,
            ),
        )
        if not errors:
            return EvidenceRecord(
                check_id=self.descriptor.component_id,
                passed=True,
                details={"validator": "draft_2020_12", "error_count": 0},
            )

        first = errors[0]
        return EvidenceRecord(
            check_id=self.descriptor.component_id,
            passed=False,
            code="schema_error",
            details={
                "validator": "draft_2020_12",
                "error_count": len(errors),
                "path": _json_path(list(first.absolute_path)),
                "message": first.message,
            },
        )
