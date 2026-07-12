"""Composable LLM component protocol boundary."""

from typing import Protocol, runtime_checkable

from .config import GenerationSettings
from .schemas import (
    CapabilityDescriptor,
    EmbeddingResult,
    GenerationResult,
    LLMTask,
    PreparedLLMInput,
)


@runtime_checkable
class ModalityAdapter(Protocol):
    """Prepare one declared input modality for a pipeline."""

    @property
    def descriptor(self) -> CapabilityDescriptor: ...

    def prepare(self, task: LLMTask) -> PreparedLLMInput: ...


@runtime_checkable
class LLMRuntimeAdapter(Protocol):
    """Perform provider transport and normalize provider responses."""

    @property
    def descriptor(self) -> CapabilityDescriptor: ...

    def generate(
        self,
        prepared_input: PreparedLLMInput,
        settings: GenerationSettings,
    ) -> GenerationResult: ...

    def embed(
        self,
        texts: tuple[str, ...],
        *,
        model: str,
        expected_dimension: int,
    ) -> EmbeddingResult: ...


@runtime_checkable
class LLMPipelineAdapter(Protocol):
    """Compose modality preparation with a declared runtime interaction."""

    @property
    def descriptor(self) -> CapabilityDescriptor: ...

    def run(
        self,
        task: LLMTask,
        *,
        runtime: LLMRuntimeAdapter,
        modality: ModalityAdapter,
        settings: GenerationSettings,
    ) -> GenerationResult: ...
