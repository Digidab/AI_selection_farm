"""Explicit, allowlisted LLM component registry."""

from dataclasses import dataclass
from typing import Any

from ..core.schemas import CoreError, ErrorCode
from .config import LLMComponentProfile
from .evaluators.json_schema import JSONSchemaEvaluator
from .evaluators.semantic_dedup import SemanticDedupEvaluator
from .interfaces import LLMPipelineAdapter, LLMRuntimeAdapter, ModalityAdapter
from .modalities.text import TextModalityAdapter
from .output_contracts.structured_json import StructuredJSONContract
from .pipelines.single_turn import SingleTurnPipeline
from .runtimes.ollama import OllamaRuntimeAdapter
from .schemas import ComponentKind


class LLMRegistryError(CoreError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.CONFIGURATION, message)


@dataclass(frozen=True)
class ResolvedLLMComponents:
    pipeline: LLMPipelineAdapter
    runtime: LLMRuntimeAdapter
    modalities: tuple[ModalityAdapter, ...]
    output_contract: Any
    evaluators: tuple[Any, ...]


class LLMComponentRegistry:
    """Registry populated only by explicit object registration."""

    def __init__(self) -> None:
        self._pipelines: dict[str, LLMPipelineAdapter] = {}
        self._runtimes: dict[str, LLMRuntimeAdapter] = {}
        self._modalities: dict[str, ModalityAdapter] = {}
        self._output_contracts: dict[str, Any] = {}
        self._evaluators: dict[str, Any] = {}

    def register_pipeline(self, component: LLMPipelineAdapter) -> None:
        self._register(self._pipelines, component, ComponentKind.PIPELINE)

    def register_runtime(self, component: LLMRuntimeAdapter) -> None:
        self._register(self._runtimes, component, ComponentKind.RUNTIME)

    def register_modality(self, component: ModalityAdapter) -> None:
        self._register(self._modalities, component, ComponentKind.MODALITY)

    def register_output_contract(self, component: object) -> None:
        self._register(self._output_contracts, component, ComponentKind.OUTPUT_CONTRACT)

    def register_evaluator(self, component: object) -> None:
        self._register(self._evaluators, component, ComponentKind.EVALUATOR)

    @staticmethod
    def _register(registry: dict, component: object, kind: ComponentKind) -> None:
        descriptor = getattr(component, "descriptor", None)
        if descriptor is None or descriptor.kind is not kind:
            raise LLMRegistryError(f"Component must declare kind {kind.value}")
        if descriptor.component_id in registry:
            raise LLMRegistryError(f"Duplicate {kind.value} component: {descriptor.component_id}")
        registry[descriptor.component_id] = component

    def resolve(self, profile: LLMComponentProfile) -> ResolvedLLMComponents:
        pipeline = self._lookup(self._pipelines, profile.pipeline_id, "pipeline")
        runtime = self._lookup(self._runtimes, profile.runtime_id, "runtime")
        modalities = tuple(
            self._lookup(self._modalities, modality_id, "modality")
            for modality_id in profile.modalities
        )
        output_contract = self._lookup(
            self._output_contracts, profile.output_contract, "output contract"
        )
        evaluators = tuple(
            self._lookup(self._evaluators, evaluator_id, "evaluator")
            for evaluator_id in profile.evaluators
        )

        pipeline_descriptor = pipeline.descriptor
        if f"runtime:{profile.runtime_id}" not in pipeline_descriptor.capabilities:
            self._incompatible(profile.pipeline_id, profile.runtime_id)
        for modality_id in profile.modalities:
            if modality_id not in pipeline_descriptor.input_modalities:
                self._incompatible(profile.pipeline_id, modality_id)
            if modality_id not in runtime.descriptor.input_modalities:
                self._incompatible(profile.runtime_id, modality_id)
        if profile.output_contract not in pipeline_descriptor.output_contracts:
            self._incompatible(profile.pipeline_id, profile.output_contract)
        for evaluator_id in profile.evaluators:
            if f"evaluator:{evaluator_id}" not in pipeline_descriptor.capabilities:
                self._incompatible(profile.pipeline_id, evaluator_id)
        for runtime_capability in ("generation", "embedding"):
            if runtime_capability not in runtime.descriptor.capabilities:
                self._incompatible(profile.runtime_id, runtime_capability)
        if profile.output_contract not in runtime.descriptor.output_contracts:
            self._incompatible(profile.runtime_id, profile.output_contract)
        if runtime.descriptor.supports_streaming:
            raise LLMRegistryError("v001 runtime must use non-streaming responses")
        for component in (output_contract, *evaluators):
            descriptor = component.descriptor
            if profile.output_contract not in descriptor.output_contracts:
                self._incompatible(descriptor.component_id, profile.output_contract)
            if any(
                modality_id not in descriptor.input_modalities for modality_id in profile.modalities
            ):
                self._incompatible(descriptor.component_id, "declared modalities")

        return ResolvedLLMComponents(
            pipeline=pipeline,
            runtime=runtime,
            modalities=modalities,
            output_contract=output_contract,
            evaluators=evaluators,
        )

    @staticmethod
    def _lookup(registry: dict, component_id: str, kind: str):
        try:
            return registry[component_id]
        except KeyError as exc:
            raise LLMRegistryError(f"Unknown {kind} component: {component_id}") from exc

    @staticmethod
    def _incompatible(owner: str, dependency: str) -> None:
        raise LLMRegistryError(f"Incompatible LLM components: {owner} -> {dependency}")


def build_reference_registry(runtime: OllamaRuntimeAdapter) -> LLMComponentRegistry:
    """Build the production allowlist without dynamic imports or name dispatch."""

    registry = LLMComponentRegistry()
    registry.register_pipeline(SingleTurnPipeline())
    registry.register_runtime(runtime)
    registry.register_modality(TextModalityAdapter())
    registry.register_output_contract(StructuredJSONContract())
    registry.register_evaluator(JSONSchemaEvaluator())
    registry.register_evaluator(SemanticDedupEvaluator())
    return registry
