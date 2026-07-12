from pathlib import Path

import pytest

from services.selector.app.llm.config import GenerationSettings, LLMComponentProfile
from services.selector.app.llm.interfaces import (
    LLMPipelineAdapter,
    LLMRuntimeAdapter,
    ModalityAdapter,
)
from services.selector.app.llm.evaluators.json_schema import JSONSchemaEvaluator
from services.selector.app.llm.evaluators.semantic_dedup import SemanticDedupEvaluator
from services.selector.app.llm.modalities.text import TextModalityAdapter
from services.selector.app.llm.output_contracts.structured_json import StructuredJSONContract
from services.selector.app.llm.pipelines.single_turn import SingleTurnPipeline
from services.selector.app.llm.registry import LLMComponentRegistry, LLMRegistryError
from services.selector.app.llm.schemas import (
    CapabilityDescriptor,
    ComponentKind,
    EmbeddingResult,
    GenerationResult,
    LLMTask,
)


def _profile(**changes: object) -> LLMComponentProfile:
    values = {
        "pipeline_id": "single_turn",
        "runtime_id": "ollama",
        "modalities": ("text",),
        "output_contract": "structured_json",
        "evaluators": ("json_schema", "semantic_dedup"),
    }
    values.update(changes)
    return LLMComponentProfile.model_construct(**values)


class _Runtime:
    descriptor = CapabilityDescriptor(
        component_id="ollama",
        kind=ComponentKind.RUNTIME,
        capabilities=frozenset({"generation", "embedding"}),
        input_modalities=frozenset({"text"}),
        output_contracts=frozenset({"structured_json"}),
        supports_streaming=False,
    )

    def __init__(self) -> None:
        self.prepared_prompt: str | None = None

    def generate(self, prepared_input, settings) -> GenerationResult:
        self.prepared_prompt = prepared_input.prompt
        return GenerationResult(model=settings.model, text='{"ok":true}', done=True)

    def embed(self, texts, *, model, expected_dimension) -> EmbeddingResult:
        return EmbeddingResult(
            model=model,
            vectors=tuple((0.0,) * expected_dimension for _ in texts),
        )


def _registry(*, pipeline=None) -> LLMComponentRegistry:
    registry = LLMComponentRegistry()
    registry.register_pipeline(pipeline or SingleTurnPipeline())
    registry.register_runtime(_Runtime())
    registry.register_modality(TextModalityAdapter())
    registry.register_output_contract(StructuredJSONContract())
    registry.register_evaluator(JSONSchemaEvaluator())
    registry.register_evaluator(SemanticDedupEvaluator())
    return registry


def test_reference_components_satisfy_runtime_checkable_protocols() -> None:
    assert isinstance(SingleTurnPipeline(), LLMPipelineAdapter)
    assert isinstance(_Runtime(), LLMRuntimeAdapter)
    assert isinstance(TextModalityAdapter(), ModalityAdapter)


def test_text_modality_preserves_prompt_and_renders_messages_deterministically() -> None:
    modality = TextModalityAdapter()
    prompt_task = LLMTask(
        task_id="prompt",
        prompt="Return JSON",
        expected_schema={"type": "object"},
    )
    message_task = LLMTask(
        task_id="messages",
        messages=(
            {"role": "system", "content": "Be exact"},
            {"role": "user", "content": "Return JSON"},
        ),
        expected_schema={"type": "object"},
    )

    assert modality.prepare(prompt_task).prompt == "Return JSON"
    assert modality.prepare(message_task).prompt == (
        "<system>\nBe exact\n</system>\n<user>\nReturn JSON\n</user>"
    )


def test_single_turn_delegates_prepared_input_to_runtime() -> None:
    runtime = _Runtime()
    result = SingleTurnPipeline().run(
        LLMTask(
            task_id="task",
            prompt="Return JSON",
            expected_schema={"type": "object"},
        ),
        runtime=runtime,
        modality=TextModalityAdapter(),
        settings=GenerationSettings(
            model="fixture", temperature=0.0, seed=42, max_output_tokens=32
        ),
    )

    assert runtime.prepared_prompt == "Return JSON"
    assert result.text == '{"ok":true}'


def test_registry_resolves_only_registered_compatible_components() -> None:
    registry = _registry()

    resolved = registry.resolve(_profile())

    assert resolved.pipeline.descriptor.component_id == "single_turn"
    assert resolved.runtime.descriptor.component_id == "ollama"
    assert [item.descriptor.component_id for item in resolved.modalities] == ["text"]
    assert resolved.output_contract.descriptor.component_id == "structured_json"
    assert [item.descriptor.component_id for item in resolved.evaluators] == [
        "json_schema",
        "semantic_dedup",
    ]


def test_registry_rejects_unknown_component_before_execution() -> None:
    registry = _registry()

    with pytest.raises(LLMRegistryError, match="Unknown runtime component: absent"):
        registry.resolve(_profile(runtime_id="absent"))


def test_registry_rejects_duplicate_and_incompatible_components() -> None:
    registry = _registry()
    with pytest.raises(LLMRegistryError, match="Duplicate modality"):
        registry.register_modality(TextModalityAdapter())

    with pytest.raises(LLMRegistryError, match="Unknown output contract.*unknown_contract"):
        registry.resolve(_profile(output_contract="unknown_contract"))


def test_test_only_adapter_registration_requires_no_dispatch_change() -> None:
    class TestPipeline(SingleTurnPipeline):
        descriptor = SingleTurnPipeline.descriptor.model_copy(
            update={"component_id": "test_pipeline"}
        )

    registry = _registry(pipeline=TestPipeline())

    resolved = registry.resolve(_profile(pipeline_id="test_pipeline"))

    assert resolved.pipeline.descriptor.component_id == "test_pipeline"


def test_registry_source_has_no_dynamic_import_or_name_dispatch_chain() -> None:
    source = Path("selection_farm/services/selector/app/llm/registry.py").read_text(
        encoding="utf-8"
    )
    assert "importlib" not in source
    assert "if profile.pipeline_id" not in source
    assert "if profile.runtime_id" not in source
