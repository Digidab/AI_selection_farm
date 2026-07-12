"""Strict LLM task, component, and runtime records."""

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import orjson
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, field_validator
from pydantic import model_validator

from ..core.schemas import CoreError, ErrorCode, NonEmptyString


class _StrictLLMRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ComponentKind(StrEnum):
    PIPELINE = "pipeline"
    RUNTIME = "runtime"
    MODALITY = "modality"
    OUTPUT_CONTRACT = "output_contract"
    EVALUATOR = "evaluator"


class LLMMessage(_StrictLLMRecord):
    role: MessageRole
    content: NonEmptyString


class LLMTask(_StrictLLMRecord):
    task_id: NonEmptyString
    prompt: NonEmptyString | None = None
    messages: tuple[LLMMessage, ...] | None = None
    expected_schema: dict[str, Any]

    @field_validator("expected_schema")
    @classmethod
    def validate_expected_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            Draft202012Validator.check_schema(value)
        except SchemaError as exc:
            raise ValueError("expected_schema must be a valid JSON Schema") from exc
        return value

    @model_validator(mode="after")
    def validate_input_material(self) -> "LLMTask":
        has_prompt = self.prompt is not None
        has_messages = self.messages is not None
        if has_prompt == has_messages:
            raise ValueError("Exactly one of prompt or messages is required")
        if self.messages is not None and not self.messages:
            raise ValueError("messages must not be empty")
        return self


class CapabilityDescriptor(_StrictLLMRecord):
    component_id: NonEmptyString
    kind: ComponentKind
    capabilities: frozenset[NonEmptyString] = Field(default_factory=frozenset)
    input_modalities: frozenset[NonEmptyString] = Field(default_factory=frozenset)
    output_contracts: frozenset[NonEmptyString] = Field(default_factory=frozenset)
    supports_streaming: StrictBool


class PreparedLLMInput(_StrictLLMRecord):
    """Provider-neutral input prepared by a modality component."""

    prompt: NonEmptyString
    expected_schema: dict[str, Any]


class GenerationResult(_StrictLLMRecord):
    """Normalized result returned by an LLM runtime."""

    model: NonEmptyString
    text: NonEmptyString
    done: Literal[True]


class EmbeddingResult(_StrictLLMRecord):
    """Normalized, dimension-checked embeddings returned by a runtime."""

    model: NonEmptyString
    vectors: tuple[tuple[float, ...], ...]


class LLMInputError(CoreError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.VALIDATION, message)


def load_llm_tasks(path: str | Path) -> tuple[LLMTask, ...]:
    task_path = Path(path)
    try:
        lines = task_path.read_bytes().splitlines()
    except OSError as exc:
        raise LLMInputError(f"Cannot read LLM tasks: {task_path}") from exc

    if not lines:
        raise LLMInputError(f"LLM task file must not be empty: {task_path}")

    tasks: list[LLMTask] = []
    seen_task_ids: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise LLMInputError(f"Blank JSONL record at line {line_number}: {task_path}")
        try:
            raw_task = orjson.loads(line)
            task = LLMTask.model_validate(raw_task)
        except (orjson.JSONDecodeError, ValidationError) as exc:
            raise LLMInputError(f"Invalid LLM task at line {line_number}: {task_path}") from exc
        if task.task_id in seen_task_ids:
            raise LLMInputError(f"Duplicate LLM task_id at line {line_number}: {task.task_id}")
        seen_task_ids.add(task.task_id)
        tasks.append(task)

    return tuple(tasks)
