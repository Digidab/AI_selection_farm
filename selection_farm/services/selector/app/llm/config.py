"""Strict configuration for the isolated LLM Selector branch."""

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, model_validator

from ..core.config import (
    DEFAULT_COMMON_CONFIG_PATH,
    CommonConfig,
    load_common_config,
    resolve_project_path,
)
from ..core.schemas import CoreError, ErrorCode, NonEmptyString

DEFAULT_LLM_CONFIG_PATH = Path("configs/selector/llm_v001.yaml")

PositiveInt = Annotated[StrictInt, Field(gt=0)]
Temperature = Annotated[float, Field(ge=0.0, le=2.0, strict=True)]
CosineDistance = Annotated[float, Field(ge=0.0, le=2.0, strict=True)]


class _StrictLLMSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LLMComponentProfile(_StrictLLMSettings):
    pipeline_id: Literal["single_turn"]
    runtime_id: Literal["ollama"]
    modalities: tuple[Literal["text"], ...]
    output_contract: Literal["structured_json"]
    evaluators: tuple[Literal["json_schema", "semantic_dedup"], ...]

    @model_validator(mode="after")
    def validate_v001_profile(self) -> "LLMComponentProfile":
        if self.modalities != ("text",):
            raise ValueError("v001 requires exactly one text modality")
        if self.evaluators != ("json_schema", "semantic_dedup"):
            raise ValueError("v001 requires the ordered json_schema and semantic_dedup evaluators")
        return self


class RuntimeSettings(_StrictLLMSettings):
    endpoint_env: NonEmptyString


class GenerationSettings(_StrictLLMSettings):
    model: NonEmptyString
    temperature: Temperature
    seed: StrictInt
    max_output_tokens: PositiveInt


class EmbeddingSettings(_StrictLLMSettings):
    model: NonEmptyString
    dimension: Literal[768]


class OutputSettings(_StrictLLMSettings):
    max_characters: PositiveInt
    max_json_depth: PositiveInt


class SemanticDedupSettings(_StrictLLMSettings):
    max_cosine_distance: CosineDistance


class LLMBranchSettings(_StrictLLMSettings):
    config_id: NonEmptyString
    branch: Literal["llm"]
    model_id: NonEmptyString
    dataset_id: Literal["selector_llm_seed_v001"]
    tasks_path: Path
    components: LLMComponentProfile
    runtime: RuntimeSettings
    generation: GenerationSettings
    embedding: EmbeddingSettings
    output: OutputSettings
    semantic_dedup: SemanticDedupSettings


class LLMConfig(_StrictLLMSettings):
    common: CommonConfig
    llm: LLMBranchSettings


class LLMConfigError(CoreError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.CONFIGURATION, message)


def _resolve_config_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate.resolve() if candidate.is_absolute() else resolve_project_path(candidate)


def load_llm_config(
    path: str | Path = DEFAULT_LLM_CONFIG_PATH,
    *,
    common_path: str | Path = DEFAULT_COMMON_CONFIG_PATH,
) -> LLMConfig:
    config_path = _resolve_config_path(path)
    try:
        raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise LLMConfigError(f"Cannot read LLM config: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise LLMConfigError(f"Invalid YAML in LLM config: {config_path}") from exc

    if not isinstance(raw_config, dict):
        raise LLMConfigError(f"LLM config must be a mapping: {config_path}")

    try:
        branch_config = LLMBranchSettings.model_validate(raw_config)
    except ValidationError as exc:
        raise LLMConfigError(f"Invalid LLM config contract: {config_path}") from exc

    branch_config = branch_config.model_copy(
        update={"tasks_path": resolve_project_path(branch_config.tasks_path)}
    )
    return LLMConfig(common=load_common_config(common_path), llm=branch_config)
