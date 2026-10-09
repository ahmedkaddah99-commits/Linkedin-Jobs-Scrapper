from __future__ import annotations

import base64
import hmac
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe
from typing import Any, Callable, Mapping
from urllib.parse import urlencode

from backend.domain.assisted_apply import (
    ASSISTED_APPLY_PREFERENCES_METADATA_KEY,
    ASSISTED_APPLY_STATUS_ACTIVE,
    ASSISTED_APPLY_STATUS_AUTHORIZED,
    ASSISTED_APPLY_STATUS_PENDING,
    AssistedApplyConnectionRecord,
    AssistedApplyPreferences,
)
from backend.domain.models import UserRecord
from backend.repositories.contracts import BackendRepositories
from backend.security.auth import hash_token_value, verify_token_value


ASSISTED_APPLY_REQUEST_TTL_SECONDS = 10 * 60
ASSISTED_APPLY_AUTHORIZATION_CODE_TTL_SECONDS = 2 * 60
ASSISTED_APPLY_SESSION_TTL_SECONDS = 8 * 60 * 60

ASSISTED_APPLY_REQUEST_ID_PREFIX = "aareq_"
ASSISTED_APPLY_AUTHORIZATION_CODE_PREFIX = "aaac_"
ASSISTED_APPLY_SESSION_TOKEN_PREFIX = "aases_"
ASSISTED_APPLY_SESSION_LOOKUP_PREFIX_LENGTH = 20
ASSISTED_APPLY_CALLBACK_PATH = "/runr/connect"

_EXTENSION_ORIGIN_PATTERN = re.compile(r"^chrome-extension://([a-p]{32})$")
_PKCE_CHALLENGE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
_PKCE_VERIFIER_PATTERN = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
_OPAQUE_CLIENT_VALUE_PATTERN = re.compile(r"^[A-Za-z0-9._~-]+$")
_EXTENSION_VERSION_PATTERN = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}$")


class AssistedApplyConnectionStateError(ValueError):
    pass


class AssistedApplyPreferenceConflictError(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return _as_utc(datetime.fromisoformat(str(value or "").strip()))
    except (TypeError, ValueError):
        return None


def _is_expired(value: str, *, now: datetime) -> bool:
    parsed = _parse_timestamp(value)
    return parsed is None or parsed <= now


def normalize_extension_origin(origin: str) -> tuple[str, str]:
    normalized = str(origin or "").strip()
    match = _EXTENSION_ORIGIN_PATTERN.fullmatch(normalized)
    if match is None:
        raise ValueError("extension_origin must be an exact Chrome extension origin.")
    return normalized, match.group(1)


def extension_callback_url(extension_id: str) -> str:
    normalized_id = str(extension_id or "").strip()
    if re.fullmatch(r"[a-p]{32}", normalized_id) is None:
        raise ValueError("extension_id must be an exact 32-character Chrome extension ID.")
    return f"https://{normalized_id}.chromiumapp.org{ASSISTED_APPLY_CALLBACK_PATH}"


def pkce_s256_challenge(verifier: str) -> str:
    normalized = str(verifier or "").strip()
    if _PKCE_VERIFIER_PATTERN.fullmatch(normalized) is None:
        raise ValueError("PKCE verifier must contain 43-128 RFC 7636 unreserved characters.")
    digest = sha256(normalized.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


@dataclass(slots=True)
class AssistedApplyConnectionService:
    repositories: BackendRepositories
    now_provider: Callable[[], datetime] = field(default=_utc_now, repr=False)

    @property
    def _repository(self):
        return self.repositories.auth_repository

    def _now(self) -> datetime:
        return _as_utc(self.now_provider())

    def _get_active_user(self, user_id: str) -> UserRecord:
        normalized_user_id = str(user_id or "").strip()
        if not normalized_user_id:
            raise ValueError("user_id is required.")
        user = self._repository.get_user(normalized_user_id)
        if not user.is_active:
            raise PermissionError("User is inactive.")
        return user

    def _preferences_for_user(self, user: UserRecord) -> AssistedApplyPreferences:
        stored = dict(user.metadata or {}).get(ASSISTED_APPLY_PREFERENCES_METADATA_KEY)
        return AssistedApplyPreferences.from_stored(stored if isinstance(stored, Mapping) else None)

    def get_preferences(self, user_id: str) -> AssistedApplyPreferences:
        return self._preferences_for_user(self._get_active_user(user_id))

    def update_preferences(
        self,
        user_id: str,
        preferences: Mapping[str, Any] | None,
    ) -> AssistedApplyPreferences:
        user = self._get_active_user(user_id)
        now = self._now()
        current = self._preferences_for_user(user)
        updated = AssistedApplyPreferences.update(
            current,
            preferences,
            updated_at=now.isoformat(),
        )
        if not self._repository.update_assisted_apply_preferences_metadata(
            user.user_id,
            expected_revision=current.revision,
            preferences=updated,
            updated_at=now.isoformat(),
        ):
            raise AssistedApplyPreferenceConflictError(
                "Assisted Apply preferences changed concurrently; reload and try again."
            )
        return updated

    def create_request(
        self,
        *,
        extension_origin: str,
        state: str,
        challenge: str,
        installation_id: str,
        version: str,
    ) -> AssistedApplyConnectionRecord:
        normalized_origin, extension_id = normalize_extension_origin(extension_origin)
        normalized_state = str(state or "").strip()
        if not (16 <= len(normalized_state) <= 256) or _OPAQUE_CLIENT_VALUE_PATTERN.fullmatch(
            normalized_state
        ) is None:
            raise ValueError("state must be 16-256 unreserved characters.")
        normalized_challenge = str(challenge or "").strip()
        if _PKCE_CHALLENGE_PATTERN.fullmatch(normalized_challenge) is None:
            raise ValueError("challenge must be an S256 PKCE challenge.")
        normalized_installation_id = str(installation_id or "").strip()
        if not (
            16 <= len(normalized_installation_id) <= 128
        ) or _OPAQUE_CLIENT_VALUE_PATTERN.fullmatch(normalized_installation_id) is None:
            raise ValueError("installation_id must be 16-128 unreserved characters.")
        normalized_version = str(version or "").strip()
        if _EXTENSION_VERSION_PATTERN.fullmatch(normalized_version) is None:
            raise ValueError("version must be a valid extension version identifier.")

        now = self._now()
        record = AssistedApplyConnectionRecord(
            request_id=f"{ASSISTED_APPLY_REQUEST_ID_PREFIX}{token_urlsafe(32)}",
            status=ASSISTED_APPLY_STATUS_PENDING,
            extension_id=extension_id,
            extension_origin=normalized_origin,
            callback_url=extension_callback_url(extension_id),
            client_state=normalized_state,
            pkce_challenge=normalized_challenge,
            installation_id=normalized_installation_id,
            extension_version=normalized_version,
            request_expires_at=(now + timedelta(seconds=ASSISTED_APPLY_REQUEST_TTL_SECONDS)).isoformat(),
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )
        self._repository.create_assisted_apply_connection(record)
        return self._repository.get_assisted_apply_connection(record.request_id)

    def _expire_if_needed(
        self,
        record: AssistedApplyConnectionRecord,
        *,
        now: datetime,
    ) -> AssistedApplyConnectionRecord:
        expiry = ""
        if record.status == ASSISTED_APPLY_STATUS_PENDING:
            expiry = record.request_expires_at
        elif record.status == ASSISTED_APPLY_STATUS_AUTHORIZED:
            expiry = record.authorization_code_expires_at
        elif record.status == ASSISTED_APPLY_STATUS_ACTIVE:
            expiry = record.session_expires_at
        if not expiry or not _is_expired(expiry, now=now):
            return record
        expired = self._repository.expire_assisted_apply_connection(
            record.request_id,
            expected_status=record.status,
            expired_at=now.isoformat(),
        )
        return expired or self._repository.get_assisted_apply_connection(record.request_id)

    def dashboard(self, *, user_id: str, request_id: str) -> dict[str, Any]:
        user = self._get_active_user(user_id)
        now = self._now()
        record = self._expire_if_needed(
            self._repository.get_assisted_apply_connection(str(request_id or "").strip()),
            now=now,
        )
        if record.user_id and record.user_id != user.user_id:
            raise PermissionError("Assisted Apply connection belongs to another user.")
        return {
            "request_id": record.request_id,
            "status": record.status,
            "extension_id": record.extension_id,
            "extension_origin": record.extension_origin,
            "extension_version": record.extension_version,
            "installation_id": record.installation_id,
            "callback_url": record.callback_url,
            "request_expires_at": record.request_expires_at,
            "created_at": record.created_at,
            "preferences": self._preferences_for_user(user).to_dict(),
        }

    def authorize(
        self,
        *,
        user_id: str,
        request_id: str,
        preferences: Mapping[str, Any] | None = None,
    ) -> str:
        user = self._get_active_user(user_id)
        now = self._now()
        normalized_request_id = str(request_id or "").strip()
        record = self._expire_if_needed(
            self._repository.get_assisted_apply_connection(normalized_request_id),
            now=now,
        )
        if record.status != ASSISTED_APPLY_STATUS_PENDING:
            raise AssistedApplyConnectionStateError(
                f"Connection request is {record.status}; only pending requests can be authorized."
            )
        if record.user_id and record.user_id != user.user_id:
            raise PermissionError("Assisted Apply connection belongs to another user.")

        # The user confirmed these policy choices during authorization. Persist
        # them canonically even if a concurrent authorization attempt wins.
        self.update_preferences(user.user_id, preferences)
        raw_code = f"{ASSISTED_APPLY_AUTHORIZATION_CODE_PREFIX}{token_urlsafe(32)}"
        authorized = self._repository.authorize_assisted_apply_connection(
            normalized_request_id,
            user_id=user.user_id,
            authorization_code_prefix=raw_code[:ASSISTED_APPLY_SESSION_LOOKUP_PREFIX_LENGTH],
            authorization_code_hash=hash_token_value(raw_code),
            authorization_code_expires_at=(
                now + timedelta(seconds=ASSISTED_APPLY_AUTHORIZATION_CODE_TTL_SECONDS)
            ).isoformat(),
            authorized_at=now.isoformat(),
        )
        if authorized is None:
            latest = self._repository.get_assisted_apply_connection(normalized_request_id)
            raise AssistedApplyConnectionStateError(
                f"Connection request could not be authorized from state {latest.status}."
            )
        query = urlencode(
            {
                "request_id": authorized.request_id,
                "code": raw_code,
                "state": authorized.client_state,
            }
        )
        return f"{authorized.callback_url}?{query}"

    def reject(self, *, user_id: str, request_id: str) -> AssistedApplyConnectionRecord:
        user = self._get_active_user(user_id)
        now = self._now()
        normalized_request_id = str(request_id or "").strip()
        record = self._expire_if_needed(
            self._repository.get_assisted_apply_connection(normalized_request_id),
            now=now,
        )
        if record.status != ASSISTED_APPLY_STATUS_PENDING:
            raise AssistedApplyConnectionStateError(
                f"Connection request is {record.status}; only pending requests can be rejected."
            )
        rejected = self._repository.reject_assisted_apply_connection(
            normalized_request_id,
            user_id=user.user_id,
            rejected_at=now.isoformat(),
        )
        if rejected is None:
            latest = self._repository.get_assisted_apply_connection(normalized_request_id)
            raise AssistedApplyConnectionStateError(
                f"Connection request could not be rejected from state {latest.status}."
            )
        return rejected

    def exchange(
        self,
        *,
        extension_origin: str,
        request_id: str,
        code: str,
        verifier: str,
    ) -> tuple[AssistedApplyConnectionRecord, str]:
        normalized_origin, _ = normalize_extension_origin(extension_origin)
        now = self._now()
        normalized_request_id = str(request_id or "").strip()
        record = self._expire_if_needed(
            self._repository.get_assisted_apply_connection(normalized_request_id),
            now=now,
        )
        if record.extension_origin != normalized_origin:
            raise PermissionError("Extension origin does not match the connection request.")
        if record.status != ASSISTED_APPLY_STATUS_AUTHORIZED:
            raise AssistedApplyConnectionStateError(
                f"Connection request is {record.status}; authorization cannot be exchanged."
            )
        raw_code = str(code or "").strip()
        if not raw_code or not verify_token_value(raw_code, record.authorization_code_hash):
            raise PermissionError("Invalid Assisted Apply authorization code.")
        expected_challenge = pkce_s256_challenge(verifier)
        if not hmac.compare_digest(expected_challenge, record.pkce_challenge):
            raise PermissionError("PKCE verification failed.")

        raw_session = f"{ASSISTED_APPLY_SESSION_TOKEN_PREFIX}{token_urlsafe(48)}"
        activated = self._repository.activate_assisted_apply_connection(
            normalized_request_id,
            extension_origin=normalized_origin,
            session_token_prefix=raw_session[:ASSISTED_APPLY_SESSION_LOOKUP_PREFIX_LENGTH],
            session_token_hash=hash_token_value(raw_session),
            session_expires_at=(
                now + timedelta(seconds=ASSISTED_APPLY_SESSION_TTL_SECONDS)
            ).isoformat(),
            activated_at=now.isoformat(),
        )
        if activated is None:
            latest = self._repository.get_assisted_apply_connection(normalized_request_id)
            raise AssistedApplyConnectionStateError(
                f"Authorization could not be exchanged from state {latest.status}."
            )
        return activated, raw_session

    def authenticate_session(
        self,
        *,
        raw_session: str,
        extension_origin: str,
    ) -> tuple[UserRecord, AssistedApplyConnectionRecord]:
        token = str(raw_session or "").strip()
        if not token.startswith(ASSISTED_APPLY_SESSION_TOKEN_PREFIX):
            raise PermissionError("Invalid or expired Assisted Apply session.")
        normalized_origin, _ = normalize_extension_origin(extension_origin)
        now = self._now()
        candidates = self._repository.list_assisted_apply_connections_for_session_prefix(
            token[:ASSISTED_APPLY_SESSION_LOOKUP_PREFIX_LENGTH]
        )
        for candidate in candidates:
            if candidate.extension_origin != normalized_origin:
                continue
            candidate = self._expire_if_needed(candidate, now=now)
            if candidate.status != ASSISTED_APPLY_STATUS_ACTIVE:
                continue
            if not verify_token_value(token, candidate.session_token_hash):
                continue
            user = self._get_active_user(candidate.user_id)
            touched = self._repository.touch_assisted_apply_session(
                candidate.request_id,
                last_used_at=now.isoformat(),
            )
            if touched is None:
                raise PermissionError("Invalid or expired Assisted Apply session.")
            return user, touched
        raise PermissionError("Invalid or expired Assisted Apply session.")

    def revoke_current(
        self,
        *,
        raw_session: str,
        extension_origin: str,
    ) -> AssistedApplyConnectionRecord:
        user, connection = self.authenticate_session(
            raw_session=raw_session,
            extension_origin=extension_origin,
        )
        revoked = self._repository.revoke_assisted_apply_connection(
            connection.request_id,
            user_id=user.user_id,
            revoked_at=self._now().isoformat(),
        )
        if revoked is None:
            raise AssistedApplyConnectionStateError("Assisted Apply session could not be revoked.")
        return revoked

    def revoke_owned(
        self,
        *,
        user_id: str,
        request_id: str,
    ) -> AssistedApplyConnectionRecord:
        user = self._get_active_user(user_id)
        now = self._now()
        normalized_request_id = str(request_id or "").strip()
        record = self._expire_if_needed(
            self._repository.get_assisted_apply_connection(normalized_request_id),
            now=now,
        )
        if not record.user_id or record.user_id != user.user_id:
            raise PermissionError("Assisted Apply connection does not belong to this user.")
        revoked = self._repository.revoke_assisted_apply_connection(
            normalized_request_id,
            user_id=user.user_id,
            revoked_at=now.isoformat(),
        )
        if revoked is None:
            raise AssistedApplyConnectionStateError(
                f"Connection cannot be revoked from state {record.status}."
            )
        return revoked
