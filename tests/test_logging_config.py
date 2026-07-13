"""
app/tests/test_logging_config.py

Unit tests for the JSON log formatter (app/core/logging_config.py) —
pure, no DB, no app needed.
"""

import json
import logging
from typing import Any
from types import TracebackType

from app.core.logging_config import JsonFormatter


def _make_record(
    name: str = "app.test",
    level: int = logging.INFO,
    pathname: str = __file__,
    lineno: int = 1,
    msg: str = "test message",
    args: tuple = (),
    exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | tuple[None, None, None] | None = None,

    **extra: Any,
) -> logging.LogRecord:
    record = logging.LogRecord(
        name=name,
        level=level,
        pathname=pathname,
        lineno=lineno,
        msg=msg,
        args=args,
        exc_info=exc_info,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_formats_basic_fields_as_json():
    record = _make_record()
    output = json.loads(JsonFormatter().format(record))
    assert output["level"] == "INFO"
    assert output["logger"] == "app.test"
    assert output["message"] == "test message"
    assert "timestamp" in output


def test_extra_fields_are_merged_flat():
    record = _make_record()
    record.doctor_id = "abc-123"
    output = json.loads(JsonFormatter().format(record))
    assert output["doctor_id"] == "abc-123"


def test_exception_info_is_serialized():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _make_record(level=logging.ERROR, msg="something broke", exc_info=sys.exc_info())

    output = json.loads(JsonFormatter().format(record))
    assert "exception" in output
    assert "ValueError: boom" in output["exception"]