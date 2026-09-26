from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

CORRECTION_SCOPE_APPLICATION = "application"
CORRECTION_SCOPE_COUNTRY = "country"
CORRECTION_SCOPE_ROLE = "role"
CORRECTION_SCOPE_COMPANY = "company"
CORRECTION_SCOPE_GLOBAL = "global"
CORRECTION_SCOPE_DO_NOT_SAVE = "do_not_save"

CORRECTION_SCOPES = {
    CORRECTION_SCOPE_APPLICATION,
    CORRECTION_SCOPE_COUNTRY,
    CORRECTION_SCOPE_ROLE,
    CORRECTION_SCOPE_COMPANY,
    CORRECTION_SCOPE_GLOBAL,
    CORRECTION_SCOPE_DO_NOT_SAVE,
}
CORRECTION_DURABLE_SCOPES = {
    CORRECTION_SCOPE_COUNTRY,
    CORRECTION_SCOPE_ROLE,
    CORRECTION_SCOPE_COMPANY,
    CORRECTION_SCOPE_GLOBAL,
}

# More specific durable scopes win when more than one matches a future package.
CORRECTION_SCOPE_PRECEDENCE = {
    CORRECTION_SCOPE_GLOBAL: 100,
    CORRECTION_SCOPE_COUNTRY: 200,
    CORRECTION_SCOPE_ROLE: 300,
    CORRECTION_SCOPE_COMPANY: 400,
}


def normalize_correction_key(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def parse_iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class ApplicationCorrection:
    correction_id: str
    user_id: str
    source_package_id: str
    source_job_id: str
    field_intent: str
    corrected_value: str
    scope: str
    scope_key: str
    provenance: str
    created_at: str
    expires_at: str
    superseded_at: str = ""
    superseded_by: str = ""

    @property
    def active(self) -> bool:
        return not self.superseded_at and not self.superseded_by

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ApplicationCorrection":
        return cls(**{field: str(payload.get(field) or "") for field in cls.__dataclass_fields__})

