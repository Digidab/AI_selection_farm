from pathlib import Path

import pytest
import yaml

from services.selector.app.core.config import (
    PROJECT_ROOT,
    CommonConfigError,
    load_common_config,
    resolve_project_path,
)


def _valid_config() -> dict[str, object]:
    return {
        "config_id": "test_common_v001",
        "database": {
            "env_file": "docker/.env",
            "host_env": "POSTGRES_HOST",
            "port_env": "POSTGRES_PORT",
            "name_env": "POSTGRES_DB",
            "user_env": "POSTGRES_USER",
            "password_env": "POSTGRES_PASSWORD",
        },
        "timeouts": {
            "database_connect_seconds": 5.0,
            "operation_seconds": 30.0,
        },
        "batch": {"size": 5},
        "export": {"atomic_replace": True},
        "logging": {"level": "INFO", "json_output": False},
    }


def _write_config(path: Path, config: dict[str, object]) -> Path:
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def test_load_common_config_resolves_project_path(tmp_path: Path) -> None:
    config = load_common_config(_write_config(tmp_path / "common.yaml", _valid_config()))

    assert config.config_id == "test_common_v001"
    assert config.database.env_file == PROJECT_ROOT / "docker" / ".env"
    assert config.batch.size == 5
    assert config.export.atomic_replace is True


def test_default_config_is_cwd_independent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    config = load_common_config()

    assert config.config_id == "common_v001"
    assert config.database.env_file == PROJECT_ROOT / "docker" / ".env"


def test_unknown_top_level_key_is_rejected(tmp_path: Path) -> None:
    raw_config = _valid_config()
    raw_config["pipeline_id"] = "not_common"

    with pytest.raises(CommonConfigError):
        load_common_config(_write_config(tmp_path / "unknown.yaml", raw_config))


def test_unknown_nested_key_is_rejected(tmp_path: Path) -> None:
    raw_config = _valid_config()
    database = raw_config["database"]
    assert isinstance(database, dict)
    database["unexpected"] = "value"

    with pytest.raises(CommonConfigError):
        load_common_config(_write_config(tmp_path / "nested.yaml", raw_config))


def test_missing_required_key_is_rejected(tmp_path: Path) -> None:
    raw_config = _valid_config()
    del raw_config["timeouts"]

    with pytest.raises(CommonConfigError):
        load_common_config(_write_config(tmp_path / "missing.yaml", raw_config))


def test_project_path_cannot_escape_root() -> None:
    with pytest.raises(CommonConfigError):
        resolve_project_path("../outside")


def test_malformed_yaml_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "malformed.yaml"
    config_path.write_text("database: [\n", encoding="utf-8")

    with pytest.raises(CommonConfigError):
        load_common_config(config_path)
