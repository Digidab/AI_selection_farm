import os
import sys
from pathlib import Path

import psycopg
import pytest
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]
POSTGRES_ENV_PATH = PROJECT_ROOT / "docker" / ".env"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _postgres_settings() -> dict[str, object]:
    local_defaults = dotenv_values(POSTGRES_ENV_PATH)

    def resolve(name: str, default: str | None = None) -> str | None:
        if name in os.environ:
            return os.environ[name]
        value = local_defaults.get(name, default)
        return value if isinstance(value, str) else default

    values = {
        "POSTGRES_HOST": resolve("POSTGRES_HOST", "127.0.0.1"),
        "POSTGRES_PORT": resolve("POSTGRES_PORT", "5432"),
        "POSTGRES_DB": resolve("POSTGRES_DB"),
        "POSTGRES_USER": resolve("POSTGRES_USER"),
        "POSTGRES_PASSWORD": resolve("POSTGRES_PASSWORD"),
    }
    missing = sorted(name for name, value in values.items() if not value)
    if missing:
        pytest.fail(
            f"Missing PostgreSQL configuration variables: {', '.join(missing)}",
            pytrace=False,
        )

    try:
        port = int(values["POSTGRES_PORT"])
    except (TypeError, ValueError):
        pytest.fail(
            "POSTGRES_PORT must be a valid integer",
            pytrace=False,
        )

    return {
        "host": values["POSTGRES_HOST"],
        "port": port,
        "dbname": values["POSTGRES_DB"],
        "user": values["POSTGRES_USER"],
        "password": values["POSTGRES_PASSWORD"],
    }


@pytest.fixture
def db_connection():
    settings = _postgres_settings()
    try:
        connection = psycopg.connect(**settings, autocommit=False)
    except psycopg.OperationalError:
        pytest.fail(
            "PostgreSQL connectivity or configuration failure",
            pytrace=False,
        )

    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()
