"""Structured logging configuration using only the standard library.

Every log record is emitted as a single JSON object so log aggregators
(Loki, Datadog, CloudWatch) can parse fields without regex.
"""

import json
import logging
from datetime import datetime, timezone


class _JSONFormatter(logging.Formatter):
    """Formats log records as compact JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Attach the JSON handler to the root logger.

    Safe to call multiple times; ``force=True`` replaces any handlers
    that were added before FastAPI's lifespan runs.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(_JSONFormatter())
    logging.basicConfig(level=level.upper(), handlers=[handler], force=True)
