"""Typed protocol and result records for ML model-family adapters."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..config import PredictionSettings
from ..schemas import FeatureDefinition, MLPipelineDescriptor, MLTask, PredictionMode

PredictionValue = str | int | float | bool


@dataclass(frozen=True, slots=True)
class ClassProbability:
    label: PredictionValue
    probability: float


@dataclass(frozen=True, slots=True)
class PredictionEvidence:
    pipeline_id: str
    feature_order: tuple[str, ...]
    used_probability_api: bool


@dataclass(frozen=True, slots=True)
class MLPrediction:
    task_id: str
    mode: PredictionMode
    prediction: PredictionValue
    probabilities: tuple[ClassProbability, ...] | None
    evidence: PredictionEvidence


@runtime_checkable
class MLPipelineAdapter(Protocol):
    @property
    def descriptor(self) -> MLPipelineDescriptor: ...

    def predict(
        self,
        task: MLTask,
        *,
        artifact_path: Path,
        feature_contract: tuple[FeatureDefinition, ...],
        prediction_settings: PredictionSettings,
    ) -> MLPrediction: ...
