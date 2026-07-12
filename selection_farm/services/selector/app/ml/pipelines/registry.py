"""Explicit allowlist for ML model-family pipeline adapters."""

from ...core.schemas import CoreError, ErrorCode
from ..schemas import MLPipelineDescriptor
from .interfaces import MLPipelineAdapter
from .sklearn_generic import SklearnGenericAdapter


class MLPipelineRegistryError(CoreError):
    """A pipeline is unknown, duplicated, or capability-incompatible."""

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.CONFIGURATION, message)


class MLPipelineRegistry:
    def __init__(self) -> None:
        self._pipelines: dict[str, MLPipelineAdapter] = {}

    def register(self, adapter: MLPipelineAdapter) -> None:
        descriptor = getattr(adapter, "descriptor", None)
        if not isinstance(adapter, MLPipelineAdapter) or not isinstance(
            descriptor, MLPipelineDescriptor
        ):
            raise MLPipelineRegistryError("ML adapter must declare a pipeline descriptor")
        if descriptor.pipeline_id in self._pipelines:
            raise MLPipelineRegistryError(
                f"Duplicate ML pipeline adapter: {descriptor.pipeline_id}"
            )
        self._pipelines[descriptor.pipeline_id] = adapter

    def resolve(self, pipeline_id: str) -> MLPipelineAdapter:
        try:
            return self._pipelines[pipeline_id]
        except KeyError as exc:
            raise MLPipelineRegistryError(f"Unknown ML pipeline: {pipeline_id}") from exc


def build_reference_registry() -> MLPipelineRegistry:
    registry = MLPipelineRegistry()
    registry.register(SklearnGenericAdapter())
    return registry
