from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any


REDACTED = "[REDACTED]"

_SENSITIVE_EXACT_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "candidate_assets",
    "cover_letter",
    "cv_text",
    "document_text",
    "email",
    "email_address",
    "error_message",
    "last_error",
    "letter_text",
    "motivation_letter",
    "password",
    "prompt",
    "prompt_override",
    "raw_prompt",
    "requested_by",
    "secret",
    "secret_value",
    "source_text",
    "system_prompt",
    "stack_trace",
    "phone",
    "phone_number",
    "token_hash",
    "workspace_cv_text",
}
_SENSITIVE_KEY_PARTS = (
    "cover_letter",
    "cv_text",
    "document_content",
    "document_text",
    "motivation_letter",
    "password",
    "private_key",
    "prompt",
    "secret",
    "source_text",
)
_JSON_FIELD_PATTERN = re.compile(
    r'(?P<prefix>"(?:workspace_cv_text|cv_text|source_text|document_text|'
    r'cover_letter|motivation_letter|prompt|system_prompt|secret_value|token_hash)"\s*:\s*)'
    r'(?P<value>"(?:\\.|[^"\\])*"|null|true|false|-?\d+(?:\.\d+)?)',
    flags=re.IGNORECASE,
)


def is_sensitive_key(key: Any) -> bool:
    normalized = str(key or "").strip().lower().replace("-", "_")
    return normalized in _SENSITIVE_EXACT_KEYS or any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def redact_sensitive_data(value: Any) -> Any:
    """Return a recursively redacted copy suitable for logs and CLI output."""

    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if is_sensitive_key(key) else redact_sensitive_data(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in {"{", "["}:
            try:
                return json.dumps(redact_sensitive_data(json.loads(stripped)), ensure_ascii=False)
            except (TypeError, ValueError):
                pass
        return _JSON_FIELD_PATTERN.sub(lambda match: f'{match.group("prefix")}"{REDACTED}"', value)
    return value


class RedactingFilter(logging.Filter):
    """Redact message arguments and custom LogRecord fields before formatting."""

    _STANDARD_FIELDS = set(logging.makeLogRecord({}).__dict__)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_sensitive_data(record.msg)
        record.args = redact_sensitive_data(record.args)
        for field_name, field_value in tuple(record.__dict__.items()):
            if field_name in self._STANDARD_FIELDS:
                continue
            record.__dict__[field_name] = (
                REDACTED if is_sensitive_key(field_name) else redact_sensitive_data(field_value)
            )
        return True


def public_run_summary(run: Any) -> dict[str, Any]:
    return {
        "id": str(getattr(run, "id", "") or ""),
        "workspace_id": str(getattr(run, "workspace_id", "") or ""),
        "workflow_template_id": str(getattr(run, "workflow_template_id", "") or ""),
        "status": str(getattr(run, "status", "") or ""),
        "created_at": str(getattr(run, "created_at", "") or ""),
        "updated_at": str(getattr(run, "updated_at", "") or ""),
        "queued_at": str(getattr(run, "queued_at", "") or ""),
        "started_at": str(getattr(run, "started_at", "") or ""),
        "finished_at": str(getattr(run, "finished_at", "") or ""),
        "current_stage_id": str(getattr(run, "current_stage_id", "") or ""),
        "attempt_count": int(getattr(run, "attempt_count", 0) or 0),
        "max_attempts": int(getattr(run, "max_attempts", 1) or 1),
        "stage_count": len(getattr(run, "stage_results", []) or []),
        "job_set_count": len(getattr(run, "final_job_set_keys", []) or []),
        "has_error": bool(str(getattr(run, "last_error", "") or "").strip()),
    }


__all__ = [
    "REDACTED",
    "RedactingFilter",
    "is_sensitive_key",
    "public_run_summary",
    "redact_sensitive_data",
]
