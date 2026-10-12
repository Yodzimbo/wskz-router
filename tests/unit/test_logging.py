import json
import logging
import sys

from app.logging import JsonFormatter


def record(**extra: object) -> logging.LogRecord:
    return logging.makeLogRecord(
        {"name": "app.test", "levelname": "INFO", "msg": "zażółć %s", "args": ("gęślą",), **extra}
    )


def test_json_line_has_base_and_extra_fields() -> None:
    line = JsonFormatter().format(record(request_id="abc", status=200, recipient=None))

    entry = json.loads(line)
    assert entry["level"] == "INFO"
    assert entry["logger"] == "app.test"
    assert entry["msg"] == "zażółć gęślą"
    assert entry["request_id"] == "abc"
    assert entry["status"] == 200
    assert entry["recipient"] is None
    assert "args" not in entry
    assert "zażółć" in line  # not \u-escaped


def test_exception_is_included() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        line = JsonFormatter().format(record(exc_info=sys.exc_info()))

    assert "ValueError: boom" in json.loads(line)["exc"]
