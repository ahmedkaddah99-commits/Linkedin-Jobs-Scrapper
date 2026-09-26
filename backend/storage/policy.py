from __future__ import annotations

import mimetypes
import os
from pathlib import Path


DEFAULT_MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024

# Runr creates/accepts these document types. Unknown binary content is
# allowed only when its filename has a known safe document extension.
_ALLOWED_MIME_TYPES = frozenset(
    {
        "application/json",
        "application/msword",
        "application/octet-stream",
        "application/pdf",
        "application/rtf",
        "application/vnd.ms-excel",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/zip",
        "text/csv",
        "text/plain",
        "text/tab-separated-values",
        "text/xml",
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/webp",
    }
)
_ALLOWED_SUFFIXES = frozenset(
    {
        ".csv",
        ".doc",
        ".docx",
        ".json",
        ".gif",
        ".jpeg",
        ".jpg",
        ".pdf",
        ".rtf",
        ".txt",
        ".tsv",
        ".xls",
        ".xlsx",
        ".xml",
        ".zip",
        ".webp",
    }
)


class ObjectDownloadRejected(ValueError):
    """Raised before a local file or signed object URL is exposed."""


def _positive_env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default)) or str(default)))
    except (TypeError, ValueError):
        return default


def max_object_download_bytes() -> int:
    return _positive_env_int("OBJECT_STORAGE_MAX_DOWNLOAD_BYTES", DEFAULT_MAX_DOWNLOAD_BYTES)


def validate_object_download(
    *,
    content_type: str = "",
    size: int | None = None,
    filename: str = "",
) -> None:
    """Validate metadata before serving bytes or issuing a signed URL."""

    normalized_filename = Path(str(filename or "")).name
    normalized_type = str(content_type or "").split(";", 1)[0].strip().lower()
    if not normalized_type and normalized_filename:
        normalized_type = str(mimetypes.guess_type(normalized_filename)[0] or "").lower()

    if size is not None:
        try:
            normalized_size = int(size)
        except (TypeError, ValueError) as exc:
            raise ObjectDownloadRejected("Object size metadata is invalid.") from exc
        if normalized_size < 0:
            raise ObjectDownloadRejected("Object size metadata is invalid.")
        maximum = max_object_download_bytes()
        if normalized_size > maximum:
            raise ObjectDownloadRejected(f"Object exceeds the {maximum} byte download limit.")

    if normalized_type.startswith("text/"):
        return
    if normalized_type in _ALLOWED_MIME_TYPES:
        if normalized_type != "application/octet-stream":
            return
        if Path(normalized_filename).suffix.lower() in _ALLOWED_SUFFIXES:
            return
    if Path(normalized_filename).suffix.lower() in _ALLOWED_SUFFIXES:
        return
    raise ObjectDownloadRejected(
        f"Object MIME type is not approved for download: {normalized_type or 'unknown'}."
    )
