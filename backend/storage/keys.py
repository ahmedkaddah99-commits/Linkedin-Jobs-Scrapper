from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import PurePosixPath

from .base import InvalidObjectKeyError


_UNSAFE_SEGMENT = re.compile(r"[^A-Za-z0-9._-]+")
_REPEATED_SEPARATOR = re.compile(r"[_-]{2,}")


def normalize_object_key(key: str) -> str:
    value = str(key or "").strip().replace("\\", "/")
    if not value or "\x00" in value:
        raise InvalidObjectKeyError("Object key must not be empty")
    if value.startswith("/"):
        raise InvalidObjectKeyError("Object key must be relative")

    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise InvalidObjectKeyError("Object key contains an invalid path segment")

    normalized = PurePosixPath(*parts).as_posix()
    if normalized.startswith("../") or normalized == "..":
        raise InvalidObjectKeyError("Object key must stay inside the storage root")
    return normalized


def _safe_segment(value: str, *, fallback: str) -> str:
    original = unicodedata.normalize("NFKC", str(value or "")).strip()
    digest = hashlib.sha256(original.encode("utf-8")).hexdigest()[:10]
    sanitized = _UNSAFE_SEGMENT.sub("_", original)
    sanitized = _REPEATED_SEPARATOR.sub("_", sanitized).strip("._-")
    if not sanitized or sanitized in {".", ".."}:
        sanitized = fallback
    if sanitized != original or len(sanitized) > 120:
        sanitized = f"{sanitized[:109].rstrip('._-')}-{digest}"
    return sanitized


def build_private_object_key(
    *,
    namespace: str,
    owner_id: str,
    category: str,
    object_id: str,
    filename: str,
) -> str:
    basename = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    parts = (
        "private",
        _safe_segment(namespace, fallback="owners"),
        _safe_segment(owner_id, fallback="owner"),
        _safe_segment(category, fallback="objects"),
        _safe_segment(object_id, fallback="object"),
        _safe_segment(basename, fallback="object.bin"),
    )
    return normalize_object_key("/".join(parts))
