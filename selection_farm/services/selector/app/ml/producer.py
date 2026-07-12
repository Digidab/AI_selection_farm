"""Registry-based ML prediction producer without model-family dispatch."""

from .config import MLBranchSettings
from .pipelines.interfaces import MLPrediction
from .pipelines.registry import MLPipelineRegistry
from .schemas import MLTask


class MLProducer:
    def __init__(self, registry: MLPipelineRegistry) -> None:
        self.registry = registry

    def produce(self, task: MLTask, settings: MLBranchSettings) -> MLPrediction:
        adapter = self.registry.resolve(settings.pipeline_id)
        return adapter.predict(
            task,
            artifact_path=settings.artifact_path,
            feature_contract=settings.features,
            prediction_settings=settings.prediction,
        )
