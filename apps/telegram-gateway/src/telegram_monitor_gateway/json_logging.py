"""Structured JSON logging for the independently deployed gateway."""

import logging
from datetime import UTC, datetime
from typing import Any

from pythonjsonlogger.json import JsonFormatter


class GatewayJsonFormatter(JsonFormatter):
    """Render the repository's standard log fields as JSON."""

    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        """Add the stable timestamp, logger, and level fields to every record."""
        super().add_fields(log_record, record, message_dict)
        log_record.setdefault("timestamp", datetime.now(UTC).isoformat())
        log_record.setdefault("logger", record.name)
        log_record.setdefault("level", record.levelname)


def setup_logging(service_name: str) -> logging.Logger:
    """Configure and return the named service logger."""
    logger = logging.getLogger(service_name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(GatewayJsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger
