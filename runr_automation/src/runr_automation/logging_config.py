"""Local rotating JSON logs with mandatory secret redaction."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .redaction import redact_text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": redact_text(record.getMessage()),
        }
        for key in ("issue_id", "job_id", "fingerprint", "provider"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = redact_text(str(value))
        return json.dumps(payload, sort_keys=True)


def configure_logging(data_dir: str | Path, *, max_bytes: int = 2_000_000, backup_count: int = 7) -> logging.Logger:
    log_dir = Path(data_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("runr_automation")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for existing in logger.handlers:
        existing.close()
    logger.handlers.clear()
    handler = RotatingFileHandler(
        log_dir / "controller.jsonl", maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    return logger
