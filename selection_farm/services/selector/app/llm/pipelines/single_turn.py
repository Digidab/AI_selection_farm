"""Reference single-turn LLM pipeline component."""

from ..config import GenerationSettings
from ..interfaces import LLMRuntimeAdapter, ModalityAdapter
from ..schemas import CapabilityDescriptor, ComponentKind, GenerationResult, LLMTask


class SingleTurnPipeline:
    descriptor = CapabilityDescriptor(
        component_id="single_turn",
        kind=ComponentKind.PIPELINE,
        capabilities=frozenset(
            {
                "runtime:ollama",
                "evaluator:json_schema",
                "evaluator:semantic_dedup",
            }
        ),
        input_modalities=frozenset({"text"}),
        output_contracts=frozenset({"structured_json"}),
        supports_streaming=False,
    )

    def run(
        self,
        task: LLMTask,
        *,
        runtime: LLMRuntimeAdapter,
        modality: ModalityAdapter,
        settings: GenerationSettings,
    ) -> GenerationResult:
        return runtime.generate(modality.prepare(task), settings)
