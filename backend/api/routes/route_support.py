from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


_LOOPBACK_ORIGIN_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _json_bytes(payload) -> bytes:
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")


def _artifact_download_url(run_id: str, artifact_id: str) -> str:
    return f"/v1/runs/{run_id}/artifacts/{artifact_id}/download"


def _file_timestamp_iso(path: Path, *, fallback: str) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    except Exception:
        return str(fallback or "")


def _schedule_interval_days(value) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _extract_bearer_token(header_value: str) -> str:
    value = str(header_value or "").strip()
    if not value.lower().startswith("bearer "):
        return ""
    return value[7:].strip()


def _is_unauthorized_permission_error(exc: PermissionError) -> bool:
    message = str(exc or "").strip().lower()
    if not message:
        return False
    return any(
        fragment in message
        for fragment in (
            "missing bearer token",
            "invalid or expired access token",
            "session token",
            "jwt",
            "authorized party",
            "bearer token",
        )
    )


def _normalize_segments(raw_segments: list[str]) -> list[str]:
    if raw_segments[:1] == ["v1"]:
        return raw_segments[1:]
    return raw_segments


def _parse_int_param(query: dict[str, list[str]], name: str, *, default: int, minimum: int = 0, maximum: int = 1000) -> int:
    raw_value = str((query.get(name) or [str(default)])[0]).strip()
    try:
        value = int(raw_value)
    except Exception as exc:
        raise ValueError(f"{name} must be an integer") from exc
    return max(minimum, min(maximum, value))


def _parse_bool_param(query: dict[str, list[str]], name: str, *, default: bool = False) -> bool:
    raw_value = str((query.get(name) or [str(default)])[0]).strip().lower()
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_origin_value(value: str) -> str:
    origin = str(value or "").strip()
    if not origin:
        return ""
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _normalize_hostname_origin(value: str) -> str:
    hostname = str(value or "").strip()
    if not hostname:
        return ""
    if "://" in hostname:
        return _normalize_origin_value(hostname)
    hostname = hostname.split("/", 1)[0].strip()
    return _normalize_origin_value(f"https://{hostname}")


def _origin_is_loopback(origin: str) -> bool:
    normalized = _normalize_origin_value(origin)
    if not normalized:
        return False
    parsed = urlparse(normalized)
    return str(parsed.hostname or "").strip().lower() in _LOOPBACK_ORIGIN_HOSTS


def _parse_allowed_origins(raw_value: str) -> tuple[set[str], bool]:
    values = {str(item).strip() for item in str(raw_value or "").split(",") if str(item).strip()}
    allow_all = "*" in values
    normalized = {_normalize_origin_value(item) for item in values if item != "*"}
    normalized.discard("")
    return normalized, allow_all


def bind_server_globals(module_globals: dict) -> None:
    from backend.api import server as server_helpers

    reserved = set(module_globals.get("_SERVER_BIND_RESERVED", set()))
    for name, value in vars(server_helpers).items():
        if name.startswith("__") or name in reserved:
            continue
        module_globals[name] = value
