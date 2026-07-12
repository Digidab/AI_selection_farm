"""Strict structured-JSON output contract for the v001 LLM branch."""

import math
from dataclasses import dataclass
from typing import Any

import orjson

from ...core.schemas import CoreError, ErrorCode
from ..config import OutputSettings
from ..schemas import CapabilityDescriptor, ComponentKind


class StructuredJSONError(CoreError):
    """A candidate failed the declared structured-JSON contract."""

    def __init__(self, failure_code: str, message: str) -> None:
        super().__init__(ErrorCode.VALIDATION, message, context={"failure_code": failure_code})
        self.failure_code = failure_code


@dataclass(frozen=True, slots=True)
class ParsedStructuredJSON:
    contract_id: str
    value: dict[str, Any]
    canonical_text: str


def _maximum_depth(value: Any) -> int:
    maximum = 1
    pending: list[tuple[Any, int]] = [(value, 1)]
    while pending:
        current, depth = pending.pop()
        maximum = max(maximum, depth)
        if isinstance(current, dict):
            pending.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)
    return maximum


def _contains_non_finite_number(value: Any) -> bool:
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, float) and not math.isfinite(current):
            return True
        if isinstance(current, dict):
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return False


class StructuredJSONContract:
    descriptor = CapabilityDescriptor(
        component_id="structured_json",
        kind=ComponentKind.OUTPUT_CONTRACT,
        capabilities=frozenset({"strict_json", "canonical_json"}),
        input_modalities=frozenset({"text"}),
        output_contracts=frozenset({"structured_json"}),
        supports_streaming=False,
    )

    def parse(self, text: str, settings: OutputSettings) -> ParsedStructuredJSON:
        if not isinstance(text, str) or not text.strip():
            raise StructuredJSONError("empty_output", "LLM output must not be empty")
        if len(text) > settings.max_characters:
            raise StructuredJSONError(
                "too_long_output",
                f"LLM output exceeds {settings.max_characters} characters",
            )

        try:
            value = orjson.loads(text)
        except orjson.JSONDecodeError as exc:
            raise StructuredJSONError("invalid_json", "LLM output is not strict JSON") from exc

        if not isinstance(value, dict):
            raise StructuredJSONError("wrong_type", "Structured JSON output must be an object")
        if _contains_non_finite_number(value):
            raise StructuredJSONError("nan_detected", "JSON output contains a non-finite number")
        if _maximum_depth(value) > settings.max_json_depth:
            raise StructuredJSONError(
                "max_depth_exceeded",
                f"JSON output exceeds maximum depth {settings.max_json_depth}",
            )

        canonical_text = orjson.dumps(value, option=orjson.OPT_SORT_KEYS).decode("utf-8")
        return ParsedStructuredJSON(
            contract_id=self.descriptor.component_id,
            value=value,
            canonical_text=canonical_text,
        )
