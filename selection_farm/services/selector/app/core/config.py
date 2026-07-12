"""Strict loading for branch-neutral Selector configuration."""

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, ValidationError

from .schemas import CoreError, ErrorCode, NonEmptyString

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_COMMON_CONFIG_PATH = Path("configs/selector/common_v001.yaml")

PositiveFloat = Annotated[float, Field(gt=0, strict=True)]
PositiveInt = Annotated[StrictInt, Field(gt=0)]


class _StrictSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DatabaseSettings(_StrictSettings):
    env_file: Path
    host_env: NonEmptyString
    port_env: NonEmptyString
    name_env: NonEmptyString
    user_env: NonEmptyString
    password_env: NonEmptyString


class TimeoutSettings(_StrictSettings):
    database_connect_seconds: PositiveFloat
    operation_seconds: PositiveFloat


class BatchSettings(_StrictSettings):
    size: PositiveInt


class ExportSettings(_StrictSettings):
    atomic_replace: StrictBool


class LoggingSettings(_StrictSettings):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    json_output: StrictBool


class CommonConfig(_StrictSettings):
    config_id: NonEmptyString
    database: DatabaseSettings
    timeouts: TimeoutSettings
    batch: BatchSettings
    export: ExportSettings
    logging: LoggingSettings


class CommonConfigError(CoreError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.CONFIGURATION, message)


def resolve_project_path(path: str | Path) -> Path:
    candidate = Path(path)
    resolved = (
        candidate.resolve() if candidate.is_absolute() else (PROJECT_ROOT / candidate).resolve()
    )
    if not resolved.is_relative_to(PROJECT_ROOT):
        raise CommonConfigError(f"Project path escapes the project root: {path}")
    return resolved


def _resolve_config_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate.resolve() if candidate.is_absolute() else resolve_project_path(candidate)


def load_common_config(
    path: str | Path = DEFAULT_COMMON_CONFIG_PATH,
) -> CommonConfig:
    config_path = _resolve_config_path(path)
    try:
        raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CommonConfigError(f"Cannot read common config: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise CommonConfigError(f"Invalid YAML in common config: {config_path}") from exc

    if not isinstance(raw_config, dict):
        raise CommonConfigError(f"Common config must be a mapping: {config_path}")

    try:
        config = CommonConfig.model_validate(raw_config)
    except ValidationError as exc:
        raise CommonConfigError(f"Invalid common config contract: {config_path}") from exc

    database = config.database.model_copy(
        update={"env_file": resolve_project_path(config.database.env_file)}
    )
    return config.model_copy(update={"database": database})
