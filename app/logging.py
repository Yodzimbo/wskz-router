"""JSON log lines: one object per record, so `docker compose logs api` can be grepped and parsed."""

import json
import logging
from datetime import UTC, datetime

# Attributes every LogRecord has; anything else came through `extra=` and is logged as a field.
_STANDARD_ATTRIBUTES = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        entry.update((k, v) for k, v in vars(record).items() if k not in _STANDARD_ATTRIBUTES)
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        # Polish text stays readable in the logs.
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    # Uvicorn configures only its own loggers (access log stays plain text); the app logs via root.
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler])
