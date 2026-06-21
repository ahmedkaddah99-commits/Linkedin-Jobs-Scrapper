from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from backend.security.redaction import RedactingFilter, redact_sensitive_data


WORKER_LOGGER_NAME = "backend.worker"
DEFAULT_WORKER_LOG_DIR = "logs"
DEFAULT_WORKER_LOG_FILE = "worker.log"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 5


class WorkerJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "process_id": record.process,
            "thread": record.threadName,
        }
        for field_name in (
            "worker_id",
            "worker_process_id",
            "host_name",
            "run_id",
            "workspace_id",
            "task_name",
            "duration_ms",
            "status",
            "attempt_count",
            "max_attempts",
            "stage_count",
            "job_set_count",
            "artifact_count",
            "queued_at",
            "started_at",
            "finished_at",
            "has_error",
            "last_error",
            "error_message",
            "claimed_status",
            "lease_seconds",
            "poll_interval_seconds",
            "max_runs",
            "processed_count",
            "recovered_worker_count",
        ):
            if hasattr(record, field_name):
                payload[field_name] = getattr(record, field_name)
        if record.exc_info:
            payload["stack_trace"] = "".join(traceback.format_exception(*record.exc_info)).strip()
        return json.dumps(redact_sensitive_data(payload), ensure_ascii=False, default=str)


def _worker_handlers(logger: logging.Logger) -> list[logging.Handler]:
    return [handler for handler in logger.handlers if getattr(handler, "_runr_worker_handler", False)]


def configure_worker_logging(
    *,
    log_dir: str | Path = DEFAULT_WORKER_LOG_DIR,
    log_file: str = DEFAULT_WORKER_LOG_FILE,
    level: int | str = logging.INFO,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    force: bool = False,
) -> logging.Logger:
    logger = logging.getLogger(WORKER_LOGGER_NAME)
    normalized_level = getattr(logging, str(level).upper(), level)
    logger.setLevel(int(normalized_level))
    logger.propagate = False

    existing_handlers = _worker_handlers(logger)
    if existing_handlers and not force:
        for handler in existing_handlers:
            handler.setLevel(int(normalized_level))
        return logger
    for handler in existing_handlers:
        logger.removeHandler(handler)
        handler.close()

    formatter = WorkerJsonFormatter()
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(int(normalized_level))
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(RedactingFilter())
    stream_handler._runr_worker_handler = True  # type: ignore[attr-defined]

    log_path = Path(log_dir) / log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max(1, int(max_bytes)),
        backupCount=max(0, int(backup_count)),
        encoding="utf-8",
    )
    file_handler.setLevel(int(normalized_level))
    file_handler.setFormatter(formatter)
    file_handler.addFilter(RedactingFilter())
    file_handler._runr_worker_handler = True  # type: ignore[attr-defined]

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    return logger


__all__ = [
    "DEFAULT_BACKUP_COUNT",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_WORKER_LOG_DIR",
    "DEFAULT_WORKER_LOG_FILE",
    "WORKER_LOGGER_NAME",
    "WorkerJsonFormatter",
    "configure_worker_logging",
]
