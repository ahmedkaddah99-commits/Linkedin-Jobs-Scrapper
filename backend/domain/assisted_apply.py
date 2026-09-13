from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping


ASSISTED_APPLY_STATUS_PENDING = "pending"
ASSISTED_APPLY_STATUS_AUTHORIZED = "authorized"
ASSISTED_APPLY_STATUS_ACTIVE = "active"
ASSISTED_APPLY_STATUS_REVOKED = "revoked"
ASSISTED_APPLY_STATUS_REJECTED = "rejected"
ASSISTED_APPLY_STATUS_EXPIRED = "expired"

ASSISTED_APPLY_CONNECTION_STATUSES = {
    ASSISTED_APPLY_STATUS_PENDING,
    ASSISTED_APPLY_STATUS_AUTHORIZED,
    ASSISTED_APPLY_STATUS_ACTIVE,
    ASSISTED_APPLY_STATUS_REVOKED,
    ASSISTED_APPLY_STATUS_REJECTED,
    ASSISTED_APPLY_STATUS_EXPIRED,
}

ASSISTED_APPLY_PREFERENCES_METADATA_KEY = "assisted_apply_preferences"
_ASSISTED_APPLY_PREFERENCE_KEYS = {
    "schema_version",
    "permit_sensitive_autofill",
    "permit_demographic_autofill",
    "require_legal_answer_confirmation",
    "revision",
    "updated_at",
}


def _valid_updated_at(value: object, *, revision: int) -> bool:
    if not isinstance(value, str):
        return False
    if revision == 0:
        return value == ""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


@dataclass(frozen=True, slots=True)
class AssistedApplyPreferences:
    schema_version: int = 1
    permit_sensitive_autofill: bool = False
    permit_demographic_autofill: bool = False
    require_legal_answer_confirmation: bool = True
    revision: int = 0
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_stored(cls, payload: Mapping[str, Any] | None) -> "AssistedApplyPreferences":
        values = dict(payload or {})
        if not values:
            return cls()
        schema_version = values.get("schema_version")
        revision = values.get("revision")
        valid = (
            set(values) == _ASSISTED_APPLY_PREFERENCE_KEYS
            and isinstance(schema_version, int)
            and not isinstance(schema_version, bool)
            and schema_version == 1
            and isinstance(values.get("permit_sensitive_autofill"), bool)
            and isinstance(values.get("permit_demographic_autofill"), bool)
            and values.get("require_legal_answer_confirmation") is True
            and isinstance(revision, int)
            and not isinstance(revision, bool)
            and revision >= 0
            and _valid_updated_at(values.get("updated_at"), revision=revision)
        )
        if not valid:
            return cls()
        return cls(
            schema_version=1,
            permit_sensitive_autofill=values["permit_sensitive_autofill"],
            permit_demographic_autofill=values["permit_demographic_autofill"],
            require_legal_answer_confirmation=True,
            revision=revision,
            updated_at=values["updated_at"],
        )

    @classmethod
    def update(
        cls,
        current: "AssistedApplyPreferences",
        payload: Mapping[str, Any] | None,
        *,
        updated_at: str,
    ) -> "AssistedApplyPreferences":
        values = dict(payload or {})
        known_keys = {
            "schema_version",
            "permit_sensitive_autofill",
            "permit_demographic_autofill",
            "require_legal_answer_confirmation",
            "revision",
            "updated_at",
        }
        unknown_keys = sorted(str(key) for key in values if key not in known_keys)
        if unknown_keys:
            raise ValueError(
                "Unsupported Assisted Apply preference keys: " + ", ".join(unknown_keys)
            )
        for key in {
            "permit_sensitive_autofill",
            "permit_demographic_autofill",
            "require_legal_answer_confirmation",
        } & values.keys():
            value = values[key]
            if not isinstance(value, bool):
                raise ValueError(f"Assisted Apply preference '{key}' must be a boolean.")
        if "schema_version" in values:
            schema_version = values["schema_version"]
            if (
                not isinstance(schema_version, int)
                or isinstance(schema_version, bool)
                or schema_version != 1
            ):
                raise ValueError("Unsupported Assisted Apply preference schema version.")
        if "revision" in values:
            revision = values["revision"]
            if (
                not isinstance(revision, int)
                or isinstance(revision, bool)
                or revision != current.revision
            ):
                raise ValueError("Assisted Apply preference revision is stale or invalid.")
        if "updated_at" in values and values["updated_at"] != current.updated_at:
            raise ValueError("Assisted Apply preference timestamp is stale or invalid.")
        if values.get("require_legal_answer_confirmation") is False:
            raise ValueError("Legal-answer confirmation cannot be disabled.")
        return cls(
            schema_version=1,
            permit_sensitive_autofill=values.get(
                "permit_sensitive_autofill",
                current.permit_sensitive_autofill,
            ),
            permit_demographic_autofill=values.get(
                "permit_demographic_autofill",
                current.permit_demographic_autofill,
            ),
            require_legal_answer_confirmation=True,
            revision=current.revision + 1,
            updated_at=str(updated_at or "").strip(),
        )


@dataclass(slots=True)
class AssistedApplyConnectionRecord:
    request_id: str
    status: str
    extension_id: str
    extension_origin: str
    callback_url: str
    client_state: str
    pkce_challenge: str
    installation_id: str
    extension_version: str
    request_expires_at: str
    created_at: str
    updated_at: str
    user_id: str = ""
    authorization_code_prefix: str = ""
    authorization_code_hash: str = ""
    authorization_code_expires_at: str = ""
    authorized_at: str = ""
    code_consumed_at: str = ""
    session_token_prefix: str = ""
    session_token_hash: str = ""
    session_expires_at: str = ""
    activated_at: str = ""
    last_used_at: str = ""
    rejected_at: str = ""
    revoked_at: str = ""
    expired_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AssistedApplyConnectionRecord":
        status = str(payload.get("status") or ASSISTED_APPLY_STATUS_PENDING).strip()
        if status not in ASSISTED_APPLY_CONNECTION_STATUSES:
            raise ValueError(f"Unsupported Assisted Apply connection status: {status}")
        return cls(
            request_id=str(payload.get("request_id") or "").strip(),
            status=status,
            extension_id=str(payload.get("extension_id") or "").strip(),
            extension_origin=str(payload.get("extension_origin") or "").strip(),
            callback_url=str(payload.get("callback_url") or "").strip(),
            client_state=str(payload.get("client_state") or ""),
            pkce_challenge=str(payload.get("pkce_challenge") or "").strip(),
            installation_id=str(payload.get("installation_id") or "").strip(),
            extension_version=str(payload.get("extension_version") or "").strip(),
            request_expires_at=str(payload.get("request_expires_at") or "").strip(),
            created_at=str(payload.get("created_at") or "").strip(),
            updated_at=str(payload.get("updated_at") or "").strip(),
            user_id=str(payload.get("user_id") or "").strip(),
            authorization_code_prefix=str(payload.get("authorization_code_prefix") or "").strip(),
            authorization_code_hash=str(payload.get("authorization_code_hash") or "").strip(),
            authorization_code_expires_at=str(
                payload.get("authorization_code_expires_at") or ""
            ).strip(),
            authorized_at=str(payload.get("authorized_at") or "").strip(),
            code_consumed_at=str(payload.get("code_consumed_at") or "").strip(),
            session_token_prefix=str(payload.get("session_token_prefix") or "").strip(),
            session_token_hash=str(payload.get("session_token_hash") or "").strip(),
            session_expires_at=str(payload.get("session_expires_at") or "").strip(),
            activated_at=str(payload.get("activated_at") or "").strip(),
            last_used_at=str(payload.get("last_used_at") or "").strip(),
            rejected_at=str(payload.get("rejected_at") or "").strip(),
            revoked_at=str(payload.get("revoked_at") or "").strip(),
            expired_at=str(payload.get("expired_at") or "").strip(),
        )
