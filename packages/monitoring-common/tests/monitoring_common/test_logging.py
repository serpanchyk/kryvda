"""Tests for JSON logging fields."""

import json
import logging

from monitoring_common.logging import ServiceJsonFormatter


def test_formatter_includes_required_fields() -> None:
    formatter = ServiceJsonFormatter()
    record = logging.LogRecord("test.logger", logging.INFO, "", 0, "ready", (), None)

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "ready"
    assert payload["logger"] == "test.logger"
    assert payload["level"] == "INFO"
    assert "timestamp" in payload
