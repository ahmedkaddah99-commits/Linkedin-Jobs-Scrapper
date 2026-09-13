"""Contracts and redaction helpers for the unified acquisition audit stream."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from backend.domain.models import utc_now_iso
from backend.security.redaction import REDACTED, redact_sensitive_data


ACQUISITION_AUDIT_DOMAIN = "acquisition"
ACQUISITION_AUDIT_EVENT_FAMILIES = frozenset(
    {
        "import",
        "review",
        "enrichment",
        "reprocessing",
        "duplicate_decision",
        "publication",
        "rollback",
        "provider_change",
        "policy_change",
    }
)

_SENSITIVE_AUDIT_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "authorization_code",
    "client_secret",
    "cookie",
    "credential",
    "credentials",
    "email",
    "email_address",
    "first_name",
    "full_name",
    "last_name",
    "name",
    "password",
    "phone",
    "phone_number",
    "private_key",
    "refresh_token",
    "secret",
    "token",
    "token_hash",
    "user_email",
}
_SENSITIVE_AUDIT_KEY_PARTS = (
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
    "cv_text",
    "document_text",
    "source_text",
    "raw_payload",
    "raw_response",
    "headers",
    "cookies",
)
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)")
_QUERY_SECRET_RE = re.compile(
    r"(?i)(\b(?:access_token|api_key|authorization|client_secret|password|refresh_token|token)\s*[=:]\s*)[^&\s,;]+"
)
_BEARER_TOKEN_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")


def redact_acquisition_audit_payload(value: Any) -> Any:
    """Return a bounded, recursively redacted audit payload."""

    value = redact_sensitive_data(value)

    def redact(item: Any, *, key: str = "") -> Any:
        normalized_key = str(key or "").strip().casefold().replace("-", "_")
        if normalized_key in _SENSITIVE_AUDIT_KEYS or any(
            part in normalized_key for part in _SENSITIVE_AUDIT_KEY_PARTS
        ):
            return REDACTED
        if isinstance(item, Mapping):
            return {str(child_key): redact(child_value, key=str(child_key)) for child_key, child_value in item.items()}
        if isinstance(item, tuple):
            return tuple(redact(child) for child in item)
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            return [redact(child) for child in item]
        if isinstance(item, str):
            redacted = _EMAIL_RE.sub(REDACTED, item)
            redacted = _PHONE_RE.sub(REDACTED, redacted)
            redacted = _BEARER_TOKEN_RE.sub(f"Bearer {REDACTED}", redacted)
            return _QUERY_SECRET_RE.sub(rf"\1{REDACTED}", redacted)
        return item

    return redact(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def acquisition_audit_event_hash(
    *,
    previous_event_hash: str,
    event_id: str,
    domain: str,
    event: str,
    actor: str,
    entity_type: str,
    entity_id: str,
    operation_id: str,
    occurred_at: str,
    payload: Mapping[str, Any],
) -> str:
    material = {
        "previous_event_hash": str(previous_event_hash or ""),
        "event_id": str(event_id or ""),
        "domain": str(domain or ""),
        "event": str(event or ""),
        "actor": str(actor or ""),
        "entity_type": str(entity_type or ""),
        "entity_id": str(entity_id or ""),
        "operation_id": str(operation_id or ""),
        "occurred_at": str(occurred_at or ""),
        "payload": dict(payload),
    }
    return hashlib.sha256(_canonical_json(material).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AcquisitionAuditEvent:
    event_id: str
    domain: str
    event: str
    actor: str
    entity_type: str
    entity_id: str
    operation_id: str
    occurred_at: str
    payload: Mapping[str, Any]
    event_hash: str = ""
    previous_event_hash: str = ""

    @classmethod
    def create(
        cls,
        *,
        event: str,
        actor: str = "",
        entity_type: str = "",
        entity_id: str = "",
        operation_id: str = "",
        occurred_at: str = "",
        payload: Mapping[str, Any] | None = None,
        event_id: str = "",
        domain: str = ACQUISITION_AUDIT_DOMAIN,
    ) -> "AcquisitionAuditEvent":
        return cls(
            event_id=str(event_id or f"acq_audit_{uuid4().hex}"),
            domain=str(domain or ACQUISITION_AUDIT_DOMAIN).strip(),
            event=str(event or "").strip(),
            actor=str(actor or "").strip(),
            entity_type=str(entity_type or "").strip(),
            entity_id=str(entity_id or "").strip(),
            operation_id=str(operation_id or "").strip(),
            occurred_at=str(occurred_at or utc_now_iso()).strip(),
            payload=redact_acquisition_audit_payload(dict(payload or {})),
        )

    @property
    def actor_id(self) -> str:
        return self.actor

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["payload"] = redact_acquisition_audit_payload(dict(self.payload))
        payload["actor_id"] = self.actor
        return payload


@dataclass(frozen=True, slots=True)
class AcquisitionAuditQuery:
    domain: str = ACQUISITION_AUDIT_DOMAIN
    event: str = ""
    actor: str = ""
    entity_type: str = ""
    entity_id: str = ""
    operation_id: str = ""
    occurred_from: str = ""
    occurred_to: str = ""
    limit: int = 100
    offset: int = 0

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | None = None) -> "AcquisitionAuditQuery":
        raw = dict(values or {})
        return cls(
            domain=str(raw.get("domain") or ACQUISITION_AUDIT_DOMAIN).strip(),
            event=str(raw.get("event") or raw.get("event_name") or "").strip(),
            actor=str(raw.get("actor") or raw.get("actor_id") or "").strip(),
            entity_type=str(raw.get("entity_type") or "").strip(),
            entity_id=str(raw.get("entity_id") or "").strip(),
            operation_id=str(raw.get("operation_id") or "").strip(),
            occurred_from=str(
                raw.get("occurred_from") or raw.get("time_from") or raw.get("from") or raw.get("start_at") or ""
            ).strip(),
            occurred_to=str(
                raw.get("occurred_to") or raw.get("time_to") or raw.get("to") or raw.get("end_at") or ""
            ).strip(),
            limit=max(1, min(200, int(raw.get("limit") or 100))),
            offset=max(0, int(raw.get("offset") or 0)),
        )


__all__ = [
    "ACQUISITION_AUDIT_DOMAIN",
    "ACQUISITION_AUDIT_EVENT_FAMILIES",
    "AcquisitionAuditEvent",
    "AcquisitionAuditQuery",
    "acquisition_audit_event_hash",
    "redact_acquisition_audit_payload",
]
