"""Secret redaction for controller payloads, errors, and subprocess output."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any


REDACTED = "[REDACTED]"
_SENSITIVE_KEY = re.compile(
    r"(?:token|secret|password|passwd|api[_-]?key|authorization|credential|private[_-]?key)",
    re.IGNORECASE,
)
_BEARER = re.compile(r"(?i)(\bbearer\s+)[^\s,;]+")
_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:linear|openrouter|codex|opencode)?[_-]?(?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s,;]+"
)
_KNOWN_TOKEN = re.compile(r"(?i)\b(?:sk-[a-z0-9_-]+|lin_api_[a-z0-9_-]+|ghp_[a-z0-9_-]+)\b")


def redact_text(value: str) -> str:
    """Replace common credential forms in arbitrary text."""

    value = _BEARER.sub(rf"\1{REDACTED}", value)
    value = _ASSIGNMENT.sub(rf"\1{REDACTED}", value)
    return _KNOWN_TOKEN.sub(REDACTED, value)


def redact(value: Any, *, _key: str | None = None) -> Any:
    """Return a redacted copy of JSON-like data without mutating the input."""

    if _key is not None and _SENSITIVE_KEY.search(_key):
        return REDACTED
    if isinstance(value, Mapping):
        return {str(key): redact(item, _key=str(key)) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
