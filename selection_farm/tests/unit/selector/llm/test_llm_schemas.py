from pathlib import Path

import orjson
import pytest
from pydantic import ValidationError

from services.selector.app.core.config import PROJECT_ROOT
from services.selector.app.llm.schemas import (
    CapabilityDescriptor,
    ComponentKind,
    LLMInputError,
    LLMTask,
    load_llm_tasks,
)

TASKS_PATH = PROJECT_ROOT / "datasets/raw/llm/tasks_v001.jsonl"
VALID_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["value"],
    "properties": {"value": {"type": "string"}},
}


def test_fixture_tasks_are_deterministic_and_non_empty() -> None:
    tasks = load_llm_tasks(TASKS_PATH)

    assert [task.task_id for task in tasks] == ["llm_seed_001", "llm_seed_002"]
    assert tasks[0].prompt is not None
    assert tasks[1].messages is not None


def test_task_requires_exactly_one_input_form() -> None:
    with pytest.raises(ValidationError):
        LLMTask(task_id="both", prompt="value", messages=[], expected_schema=VALID_SCHEMA)

    with pytest.raises(ValidationError):
        LLMTask(task_id="neither", expected_schema=VALID_SCHEMA)


def test_task_rejects_invalid_expected_schema() -> None:
    with pytest.raises(ValidationError):
        LLMTask(
            task_id="invalid_schema",
            prompt="value",
            expected_schema={"type": "not-a-json-schema-type"},
        )


def test_task_record_is_frozen() -> None:
    task = LLMTask(task_id="immutable", prompt="value", expected_schema=VALID_SCHEMA)

    with pytest.raises(ValidationError):
        task.task_id = "changed"


def test_capability_descriptor_is_strict() -> None:
    descriptor = CapabilityDescriptor(
        component_id="single_turn",
        kind=ComponentKind.PIPELINE,
        capabilities=frozenset({"non_streaming"}),
        input_modalities=frozenset({"text"}),
        output_contracts=frozenset({"structured_json"}),
        supports_streaming=False,
    )

    assert descriptor.component_id == "single_turn"

    with pytest.raises(ValidationError):
        CapabilityDescriptor(
            component_id="invalid",
            kind=ComponentKind.PIPELINE,
            supports_streaming=False,
            unknown=True,
        )


def test_loader_rejects_malformed_and_duplicate_records(tmp_path: Path) -> None:
    malformed_path = tmp_path / "malformed.jsonl"
    malformed_path.write_bytes(b"{not-json}\n")
    with pytest.raises(LLMInputError):
        load_llm_tasks(malformed_path)

    raw_task = {
        "task_id": "duplicate",
        "prompt": "value",
        "expected_schema": VALID_SCHEMA,
    }
    duplicate_path = tmp_path / "duplicate.jsonl"
    duplicate_path.write_bytes(orjson.dumps(raw_task) + b"\n" + orjson.dumps(raw_task) + b"\n")
    with pytest.raises(LLMInputError):
        load_llm_tasks(duplicate_path)


def test_loader_rejects_blank_record(tmp_path: Path) -> None:
    task_path = tmp_path / "blank.jsonl"
    task_path.write_bytes(
        orjson.dumps(
            {
                "task_id": "valid",
                "prompt": "value",
                "expected_schema": VALID_SCHEMA,
            }
        )
        + b"\n\n"
    )

    with pytest.raises(LLMInputError):
        load_llm_tasks(task_path)
