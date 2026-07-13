"""
app/core/logging_config.py

Structured (JSON) logging. Every log line is one JSON object on
stdout — the format most log aggregators (CloudWatch, Railway's log
viewer, Datadog, etc.) parse natively without extra config on their
end, and what you want if these logs are ever queried/filtered rather
than just read in a terminal.

Deliberately stdlib-only (no structlog/python-json-logger dependency)
given the scope of the project. Swapping in a dedicated library
later is a change to configure_logging() only — call sites go through
get_logger() and never touch formatting directly.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings

_RESERVED_LOG_RECORD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys())


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Fields passed via extra={...} get merged in flat, so
        # logger.info("booked", extra={"doctor_id": ...}) shows up as a
        # top-level "doctor_id" key rather than nested.
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_RECORD_ATTRS and key not in payload:
                payload[key] = value

        return json.dumps(payload, default=str)


def configure_logging() -> None:
    settings = get_settings()
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # SQLAlchemy's engine logger is extremely chatty at INFO (logs every
    # statement) — keep it quiet unless someone's actively debugging.
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.log_level == "DEBUG" else logging.WARNING
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
