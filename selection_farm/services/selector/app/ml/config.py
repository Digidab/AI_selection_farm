"""Strict configuration for the isolated ML Selector branch."""

import math
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    ValidationError,
    field_validator,
    model_validator,
)

from ..core.config import (
    DEFAULT_COMMON_CONFIG_PATH,
    CommonConfig,
    load_common_config,
    resolve_project_path,
)
from ..core.schemas import CoreError, ErrorCode, NonEmptyString
from .schemas import FeatureDefinition, MLPipelineDescriptor, PredictionMode

DEFAULT_ML_CONFIG_PATH = Path("configs/selector/ml_v001.yaml")

FiniteFloat = Annotated[float, Field(strict=True)]
Probability = Annotated[float, Field(ge=0.0, le=1.0, strict=True)]


class _StrictMLSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ConfidenceSettings(_StrictMLSettings):
    required: StrictBool
    minimum: Probability

    @field_validator("minimum")
    @classmethod
    def validate_finite_minimum(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Confidence minimum must be finite")
        return value


class ClassificationPredictionSettings(_StrictMLSettings):
    mode: Literal[PredictionMode.CLASSIFICATION]
    allowed_classes: tuple[NonEmptyString, ...]
    confidence: ConfidenceSettings | None = None

    @model_validator(mode="after")
    def validate_allowed_classes(self) -> "ClassificationPredictionSettings":
        if not self.allowed_classes:
            raise ValueError("Classification requires allowed classes")
        if len(set(self.allowed_classes)) != len(self.allowed_classes):
            raise ValueError("Allowed classes must be unique")
        return self


class RegressionPredictionSettings(_StrictMLSettings):
    mode: Literal[PredictionMode.REGRESSION]
    minimum: FiniteFloat
    maximum: FiniteFloat

    @model_validator(mode="after")
    def validate_range(self) -> "RegressionPredictionSettings":
        if not math.isfinite(self.minimum) or not math.isfinite(self.maximum):
            raise ValueError("Regression range must be finite")
        if self.minimum >= self.maximum:
            raise ValueError("Regression minimum must be lower than maximum")
        return self


PredictionSettings = Annotated[
    ClassificationPredictionSettings | RegressionPredictionSettings,
    Field(discriminator="mode"),
]


class MLBranchSettings(_StrictMLSettings):
    config_id: NonEmptyString
    branch: Literal["ml"]
    model_id: NonEmptyString
    dataset_id: Literal["selector_ml_seed_v001"]
    tasks_path: Path
    artifact_path: Path
    pipeline_id: Literal["sklearn_generic"]
    features: tuple[FeatureDefinition, ...]
    prediction: PredictionSettings

    @model_validator(mode="after")
    def validate_feature_contract(self) -> "MLBranchSettings":
        feature_names = tuple(feature.name for feature in self.features)
        if not feature_names:
            raise ValueError("ML config requires at least one feature")
        if len(set(feature_names)) != len(feature_names):
            raise ValueError("Feature names must be unique")
        return self

    def pipeline_descriptor(self) -> MLPipelineDescriptor:
        return MLPipelineDescriptor(
            pipeline_id=self.pipeline_id,
            artifact_formats=frozenset({"joblib"}),
            supported_modes=frozenset({PredictionMode.CLASSIFICATION, PredictionMode.REGRESSION}),
            supported_feature_types=frozenset(feature.data_type for feature in self.features),
            probability_api_optional=True,
        )


class MLConfig(_StrictMLSettings):
    common: CommonConfig
    ml: MLBranchSettings


class MLConfigError(CoreError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.CONFIGURATION, message)


def _resolve_config_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate.resolve() if candidate.is_absolute() else resolve_project_path(candidate)


def load_ml_config(
    path: str | Path = DEFAULT_ML_CONFIG_PATH,
    *,
    common_path: str | Path = DEFAULT_COMMON_CONFIG_PATH,
) -> MLConfig:
    config_path = _resolve_config_path(path)
    try:
        raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise MLConfigError(f"Cannot read ML config: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise MLConfigError(f"Invalid YAML in ML config: {config_path}") from exc

    if not isinstance(raw_config, dict):
        raise MLConfigError(f"ML config must be a mapping: {config_path}")

    try:
        branch_config = MLBranchSettings.model_validate(raw_config)
    except ValidationError as exc:
        raise MLConfigError(f"Invalid ML config contract: {config_path}") from exc

    try:
        branch_config = branch_config.model_copy(
            update={
                "tasks_path": resolve_project_path(branch_config.tasks_path),
                "artifact_path": resolve_project_path(branch_config.artifact_path),
            }
        )
        common_config = load_common_config(common_path)
    except CoreError as exc:
        raise MLConfigError(f"Invalid project path or common config for: {config_path}") from exc

    return MLConfig(common=common_config, ml=branch_config)
