"""Validation and content-addressed caching for canonical company logos."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import hashlib
import ipaddress
import re
import socket
from urllib.parse import urlparse
import warnings
import xml.etree.ElementTree as ET

from PIL import Image, UnidentifiedImageError


ALLOWED_LOGO_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/svg+xml",
}
MAX_LOGO_BYTES = 2 * 1024 * 1024
MAX_LOGO_DIMENSION = 4096
MIN_LOGO_DIMENSION = 32
_IMAGE_FORMATS = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
_BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata",
    "metadata.google.internal",
    "instance-data",
    "instance-data.ec2.internal",
}


class LogoValidationError(ValueError):
    """Raised when a company logo or official asset URL is unsafe."""


@dataclass(frozen=True, slots=True)
class ValidatedLogo:
    data: bytes
    content_type: str
    content_hash: str
    width: int
    height: int

    @property
    def extension(self) -> str:
        return {
            "image/jpeg": "jpg",
            "image/svg+xml": "svg",
            "image/webp": "webp",
        }.get(self.content_type, "png")


def _svg_dimension(value: str) -> int | None:
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)(?:px)?\s*", value or "", flags=re.IGNORECASE)
    if not match:
        return None
    number = float(match.group(1))
    return int(number) if number > 0 and number <= MAX_LOGO_DIMENSION else None


def _svg_dimensions(data: bytes) -> tuple[int, int]:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise LogoValidationError("logo_svg_encoding_invalid") from exc
    lowered = text.casefold()
    if any(
        marker in lowered
        for marker in ("<!doctype", "<!entity", "<script", "<foreignobject", "javascript:", "data:")
    ) or re.search(r"\bon[a-z]+\s*=", lowered) or re.search(r"\b(?:href|xlink:href)\s*=\s*[\"'](?!#)", lowered):
        raise LogoValidationError("logo_svg_unsafe_content")
    if re.search(r"url\(\s*(?!#)", lowered):
        raise LogoValidationError("logo_svg_external_reference")
    try:
        root = ET.fromstring(data)
    except (ET.ParseError, ValueError) as exc:
        raise LogoValidationError("logo_svg_invalid") from exc
    if root.tag.rsplit("}", 1)[-1].casefold() != "svg":
        raise LogoValidationError("logo_svg_root_missing")
    width = _svg_dimension(root.attrib.get("width", ""))
    height = _svg_dimension(root.attrib.get("height", ""))
    view_box = root.attrib.get("viewBox", "")
    view_box_match = re.fullmatch(
        r"\s*[-+]?[0-9]+(?:\.[0-9]+)?\s+[-+]?[0-9]+(?:\.[0-9]+)?\s+([0-9]+(?:\.[0-9]+)?)\s+([0-9]+(?:\.[0-9]+)?)\s*",
        view_box,
    )
    if view_box_match:
        width = width or _svg_dimension(view_box_match.group(1))
        height = height or _svg_dimension(view_box_match.group(2))
    if width is None or height is None:
        raise LogoValidationError("logo_dimensions_unreadable")
    return width, height


def _assert_dimensions(width: int, height: int) -> None:
    if not (
        MIN_LOGO_DIMENSION <= width <= MAX_LOGO_DIMENSION
        and MIN_LOGO_DIMENSION <= height <= MAX_LOGO_DIMENSION
    ):
        raise LogoValidationError("logo_dimensions_out_of_bounds")


def _raster_dimensions(data: bytes, content_type: str) -> tuple[int, int]:
    expected_format = _IMAGE_FORMATS[content_type]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format != expected_format:
                    raise LogoValidationError("logo_content_type_mismatch")
                width, height = image.size
                _assert_dimensions(width, height)
                image.verify()
            # verify() does not decode all pixels. Re-open and load only after
            # dimensions have been bounded to protect the worker from bombs.
            with Image.open(BytesIO(data)) as image:
                image.load()
    except LogoValidationError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        SyntaxError,
        UnidentifiedImageError,
        ValueError,
    ) as exc:
        raise LogoValidationError("logo_image_decode_failed") from exc
    return width, height


def validate_logo(data: bytes, content_type: str = "image/png") -> ValidatedLogo:
    body = bytes(data or b"")
    mime = str(content_type or "").split(";", 1)[0].strip().casefold()
    if mime not in ALLOWED_LOGO_MIME_TYPES:
        raise LogoValidationError("logo_mime_not_allowed")
    if not body or len(body) > MAX_LOGO_BYTES:
        raise LogoValidationError("logo_size_invalid")
    signature_matches = {
        "image/png": body.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": body.startswith(b"\xff\xd8"),
        "image/webp": len(body) >= 12 and body.startswith(b"RIFF") and body[8:12] == b"WEBP",
        "image/svg+xml": body.lstrip().startswith((b"<svg", b"<?xml")),
    }
    if not signature_matches[mime]:
        raise LogoValidationError("logo_content_type_mismatch")
    width, height = _svg_dimensions(body) if mime == "image/svg+xml" else _raster_dimensions(body, mime)
    _assert_dimensions(width, height)
    return ValidatedLogo(body, mime, hashlib.sha256(body).hexdigest(), width, height)


def _normalized_host(value: str) -> str:
    return str(value or "").strip().rstrip(".").casefold()


def validate_official_url(url: str, *, approved_host: str = "") -> str:
    """Validate an HTTPS URL against the canonical official host."""

    try:
        parsed = urlparse(str(url or "").strip())
        host = _normalized_host(parsed.hostname or "")
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise LogoValidationError("official_url_invalid") from exc
    if parsed.scheme.casefold() != "https" or not host or parsed.username or parsed.password:
        raise LogoValidationError("official_url_not_https")
    if port not in (None, 443):
        raise LogoValidationError("official_url_port_not_allowed")
    if host in _BLOCKED_HOSTNAMES or host.endswith(".localhost") or host.endswith(".local"):
        raise LogoValidationError("official_url_host_blocked")
    try:
        parsed_ip = ipaddress.ip_address(host)
    except ValueError:
        parsed_ip = None
    if parsed_ip is not None and not parsed_ip.is_global:
        raise LogoValidationError("official_url_address_blocked")
    allowed_host = _normalized_host(approved_host)
    if allowed_host and host != allowed_host and not host.endswith("." + allowed_host):
        raise LogoValidationError("official_url_host_not_approved")
    return parsed._replace(fragment="").geturl()


def assert_public_official_host(host: str) -> None:
    """Resolve every address and reject local, private, or metadata targets."""

    normalized = _normalized_host(host)
    if not normalized:
        raise LogoValidationError("official_url_host_missing")
    if normalized in _BLOCKED_HOSTNAMES:
        raise LogoValidationError("official_url_host_blocked")
    try:
        addresses = socket.getaddrinfo(normalized, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise LogoValidationError("official_url_dns_failed") from exc
    if not addresses:
        raise LogoValidationError("official_url_dns_empty")
    for address in addresses:
        try:
            resolved = ipaddress.ip_address(address[4][0])
        except (IndexError, ValueError) as exc:
            raise LogoValidationError("official_url_address_invalid") from exc
        if not resolved.is_global:
            raise LogoValidationError("official_url_address_blocked")


def cache_logo(storage: object, company_id: str, logo: ValidatedLogo) -> tuple[str, bool]:
    if storage is None or not callable(getattr(storage, "put", None)):
        raise LogoValidationError("logo_storage_unavailable")
    key = f"catalog/company-logos/{str(company_id).strip()}/{logo.content_hash[:24]}.{logo.extension}"
    exists = getattr(storage, "exists", None)
    already_cached = bool(callable(exists) and exists(key))
    if not already_cached:
        storage.put(
            key,
            logo.data,
            content_type=logo.content_type,
            metadata={
                "company_id": str(company_id),
                "asset_kind": "canonical_company_logo",
                "content_sha256": logo.content_hash,
                "width": str(logo.width),
                "height": str(logo.height),
            },
        )
    return key, not already_cached


def deterministic_monogram(company_name: str) -> str:
    words = [word for word in re.split(r"[^A-Za-z0-9]+", str(company_name or "").strip()) if word]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


__all__ = [
    "ALLOWED_LOGO_MIME_TYPES",
    "LogoValidationError",
    "MAX_LOGO_BYTES",
    "MAX_LOGO_DIMENSION",
    "MIN_LOGO_DIMENSION",
    "ValidatedLogo",
    "assert_public_official_host",
    "cache_logo",
    "deterministic_monogram",
    "validate_logo",
    "validate_official_url",
]
