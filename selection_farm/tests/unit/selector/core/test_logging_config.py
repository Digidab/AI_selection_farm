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
    record.event = "selector_task_failed"
    record.run_id = "RU_TEST"
    record.task_id = "TA_TEST"
    record.source_id = "source-test"
    record.branch_id = "llm"
    record.error_type = "builtins.RuntimeError"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "message"
    assert payload["correlation_id"] == "TA_TEST"
    assert payload["event"] == "selector_task_failed"
    assert payload["run_id"] == "RU_TEST"
    assert payload["task_id"] == "TA_TEST"
    assert payload["source_id"] == "source-test"
    assert payload["branch_id"] == "llm"
    assert payload["error_type"] == "builtins.RuntimeError"


def test_empty_correlation_id_is_rejected() -> None:
    with pytest.raises(ValueError):
        with correlation_context("  "):
            pass
