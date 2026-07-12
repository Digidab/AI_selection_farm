"""Correlation-aware logging for Selector Core."""

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

from .config import LoggingSettings

LOGGER_NAMESPACE = "selection_farm.selector"
_CORRELATION_ID: ContextVar[str] = ContextVar("selector_correlation_id", default="-")


class CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = _CORRELATION_ID.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def configure_logging(settings: LoggingSettings) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAMESPACE)
    logger.setLevel(settings.level)
    logger.propagate = False

    handler = logging.StreamHandler()
    handler.addFilter(CorrelationFilter())
    if settings.json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s "
                "correlation_id=%(correlation_id)s %(message)s"
            )
        )

    logger.handlers.clear()
    logger.addHandler(handler)
    return logger


def get_logger(name: str) -> logging.Logger:
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("Logger name must not be empty")
    return logging.getLogger(f"{LOGGER_NAMESPACE}.{normalized_name}")


def get_correlation_id() -> str:
    return _CORRELATION_ID.get()


@contextmanager
def correlation_context(correlation_id: str) -> Iterator[None]:
    normalized_id = correlation_id.strip()
    if not normalized_id:
        raise ValueError("Correlation ID must not be empty")
    token = _CORRELATION_ID.set(normalized_id)
    try:
        yield
    finally:
        _CORRELATION_ID.reset(token)
