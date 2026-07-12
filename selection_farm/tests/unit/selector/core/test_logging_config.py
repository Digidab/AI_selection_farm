import json
import logging

import pytest

from services.selector.app.core.logging_config import (
    CorrelationFilter,
    JsonFormatter,
    correlation_context,
    get_correlation_id,
)


def _record() -> logging.LogRecord:
    return logging.LogRecord("selector.test", logging.INFO, __file__, 1, "message", (), None)


def test_correlation_context_is_added_and_restored() -> None:
    correlation_filter = CorrelationFilter()
    assert get_correlation_id() == "-"

    with correlation_context("RU_TEST"):
        record = _record()
        assert correlation_filter.filter(record) is True
        assert record.correlation_id == "RU_TEST"

    assert get_correlation_id() == "-"


def test_json_formatter_includes_correlation_id() -> None:
    record = _record()
    record.correlation_id = "TA_TEST"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "message"
    assert payload["correlation_id"] == "TA_TEST"


def test_empty_correlation_id_is_rejected() -> None:
    with pytest.raises(ValueError):
        with correlation_context("  "):
            pass
