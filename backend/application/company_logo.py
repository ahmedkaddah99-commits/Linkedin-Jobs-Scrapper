"""Small, worker-side helpers for verified company logo caching."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re


_ALLOWED_CONTENT_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/svg+xml": "svg",
}


class LogoValidationError(ValueError):
    """Raised when a company logo cannot be safely validated or cached."""


@dataclass(frozen=True)
class ValidatedLogo:
    data: bytes
    content_type: str
    content_hash: str
    extension: str
    width: int = 0
    height: int = 0


def validate_logo(data: bytes, content_type: str = "image/png") -> ValidatedLogo:
    normalized_type = str(content_type or "").strip().lower()
    if normalized_type not in _ALLOWED_CONTENT_TYPES:
        raise ValueError("unsupported_company_logo_type")
    payload = bytes(data or b"")
    if not payload:
        raise ValueError("empty_company_logo")
    return ValidatedLogo(
        data=payload,
        content_type=normalized_type,
        content_hash=hashlib.sha256(payload).hexdigest(),
        extension=_ALLOWED_CONTENT_TYPES[normalized_type],
    )


def cache_logo(object_storage, company_id: str, logo: ValidatedLogo) -> tuple[str, bool]:
    key = f"catalog/company-logos/{str(company_id).strip()}/{logo.content_hash[:24]}.{logo.extension}"
    put = getattr(object_storage, "put", None)
    if object_storage is None or not callable(put):
        raise LogoValidationError("company_logo_storage_unavailable")
    exists = getattr(object_storage, "exists", None)
    already_cached = bool(callable(exists) and exists(key))
    if not already_cached:
        put(
            key,
            logo.data,
            content_type=logo.content_type,
            metadata={"company_id": str(company_id), "asset_kind": "canonical_company_logo", "content_sha256": logo.content_hash},
        )
    return key, not already_cached


def deterministic_monogram(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", str(value or ""))
    if not words:
        return "?"
    return (words[0][0] + (words[1][0] if len(words) > 1 else "")).upper()
