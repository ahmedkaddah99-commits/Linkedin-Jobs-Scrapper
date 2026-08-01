from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from typing import Any, Callable, Mapping

from backend.application.assisted_apply_package_service import ApplicationPackageService
from backend.application.assisted_apply_service import ASSISTED_APPLY_SESSION_TTL_SECONDS
from backend.domain.assisted_apply_preparation import (
    PREPARATION_ERROR_CATEGORIES,
    PREPARATION_STATE_ACTIVE,
    PREPARATION_STATE_CREATED,
    PREPARATION_STATE_EXPIRED,
    PREPARATION_STATE_NEEDS_ATTENTION,
    PREPARATION_STATE_PERMISSION_REQUIRED,
    PREPARATION_STATE_PREPARING,
    PREPARATION_STATE_READY_FOR_REVIEW,
    AssistedApplyPreparation,
    PreparationAuthorizationError,
    PreparationFeatureDisabledError,
    PreparationStateError,
    transition_for_action,
    transition_for_report,
)
from backend.repositories.assisted_apply_preparation import AssistedApplyPreparationRepository
from backend.repositories.contracts import BackendRepositories


ASSISTED_APPLY_PREPARATION_ENABLED_ENV = "RUNR_ENABLE_ASSISTED_APPLY_PREPARATION"
ASSISTED_APPLY_PREPARATION_ID_PREFIX = "aaprep_"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return _as_utc(datetime.fromisoformat(str(value or "")))
    except (TypeError, ValueError):
        return None


def preparation_feature_enabled() -> bool:
    return str(os.getenv(ASSISTED_APPLY_PREPARATION_ENABLED_ENV, "")).strip().lower() in {"1", "true", "yes", "on"}


class PreparationNotFoundError(KeyError):
    pass


@dataclass(slots=True)
class AssistedApplyPreparationService:
    repositories: BackendRepositories
    package_service: ApplicationPackageService
    now_provider: Callable[[], datetime] = field(default=_utc_now, repr=False)
    enabled: bool = field(default_factory=preparation_feature_enabled)
    _repository: AssistedApplyPreparationRepository = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._repository = AssistedApplyPreparationRepository(self.repositories)

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise PreparationFeatureDisabledError("Assisted Apply preparation status is disabled.")

    def _now(self) -> datetime:
        return _as_utc(self.now_provider())

    def _get(self, preparation_id: str) -> AssistedApplyPreparation:
        preparation = self._repository.get(preparation_id)
        if preparation is None:
            raise PreparationNotFoundError(f"Preparation '{preparation_id}' was not found.")
        return preparation

    @staticmethod
    def _authorize(preparation: AssistedApplyPreparation, user_id: str) -> None:
        if preparation.user_id != str(user_id or "").strip():
            raise PreparationAuthorizationError("Preparation does not belong to this user.")

    def _expire_if_needed(self, preparation: AssistedApplyPreparation) -> AssistedApplyPreparation:
        if preparation.state not in {PREPARATION_STATE_ACTIVE, "cancelled", PREPARATION_STATE_EXPIRED}:
            expires_at = _parse_timestamp(preparation.expires_at)
            if expires_at is not None and self._now() >= expires_at:
                now = self._now().isoformat()
                preparation.state = PREPARATION_STATE_EXPIRED
                preparation.expired_at = now
                preparation.error_category = "expired"
                preparation.updated_at = now
                self._repository.save(preparation)
        return preparation

    def create(self, *, user_id: str, package_id: str) -> AssistedApplyPreparation:
        self._require_enabled()
        package = self.package_service._store.get(package_id)
        if package is None:
            raise PreparationNotFoundError(f"Package '{package_id}' was not found.")
        if package.user_id != str(user_id or "").strip():
            raise PreparationAuthorizationError("Package does not belong to this user.")
        if package.job.portal not in {"greenhouse", "lever"} or not package.job.url:
            raise PreparationStateError("Preparation requires a frozen Greenhouse or Lever application URL.")
        now = self._now()
        preparation = AssistedApplyPreparation(
            preparation_id=f"{ASSISTED_APPLY_PREPARATION_ID_PREFIX}{token_urlsafe(24)}",
            user_id=package.user_id,
            package_id=package.package_id,
            job_id=package.job_id,
            ats=package.job.portal,
            application_url=package.job.url,
            state=PREPARATION_STATE_CREATED,
            total_count=0,
            completed_count=0,
            error_category="",
            attempt_count=1,
            session_id="",
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=ASSISTED_APPLY_SESSION_TTL_SECONDS)).isoformat(),
        )
        self._repository.create(preparation)
        return preparation

    def get_for_user(self, *, user_id: str, preparation_id: str) -> AssistedApplyPreparation:
        self._require_enabled()
        preparation = self._get(preparation_id)
        self._authorize(preparation, user_id)
        return self._expire_if_needed(preparation)

    def list_for_user(self, *, user_id: str) -> list[AssistedApplyPreparation]:
        self._require_enabled()
        return [self._expire_if_needed(item) for item in self._repository.list_for_user(user_id)]

    def report_from_extension(
        self,
        *,
        preparation_id: str,
        package_id: str = "",
        message_id: str,
        report_type: str,
        raw_session: str,
        extension_origin: str,
        total_count: int = 0,
        completed_count: int = 0,
        error_category: str = "",
    ) -> AssistedApplyPreparation:
        self._require_enabled()
        user, connection = self.package_service._connection_service.authenticate_session(
            raw_session=raw_session, extension_origin=extension_origin,
        )
        preparation = self._get(preparation_id)
        self._authorize(preparation, user.user_id)
        if package_id and preparation.package_id != str(package_id).strip():
            raise PreparationAuthorizationError("Preparation is not associated with this package.")
        preparation = self._expire_if_needed(preparation)
        normalized_message = str(message_id or "").strip()
        if not normalized_message:
            raise ValueError("message_id is required for preparation reports.")
        if not isinstance(total_count, int) or isinstance(total_count, bool) or total_count < 0:
            raise ValueError("total_count must be a non-negative integer.")
        if not isinstance(completed_count, int) or isinstance(completed_count, bool) or completed_count < 0:
            raise ValueError("completed_count must be a non-negative integer.")
        if total_count and completed_count > total_count:
            raise ValueError("completed_count cannot exceed total_count.")
        normalized_error = str(error_category or "").strip()
        if normalized_error not in PREPARATION_ERROR_CATEGORIES:
            raise ValueError("Unsupported sanitized preparation error category.")
        fingerprint = hashlib.sha256(json.dumps({
            "preparation_id": preparation_id, "message_id": normalized_message,
            "type": report_type, "total": total_count, "completed": completed_count,
            "error_category": normalized_error,
        }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        existing = self._repository.report_fingerprint(normalized_message)
        if existing is not None:
            if existing != fingerprint:
                raise PreparationStateError("Replayed message ID has different content.")
            return preparation
        if preparation.session_id and preparation.session_id != connection.request_id:
            raise PreparationAuthorizationError("Preparation is bound to a different extension session.")
        next_state = transition_for_report(preparation.state, report_type)
        now = self._now().isoformat()
        preparation.state = next_state
        preparation.session_id = connection.request_id
        preparation.updated_at = now
        preparation.last_report_id = normalized_message
        if total_count:
            preparation.total_count = total_count
        preparation.completed_count = completed_count
        preparation.error_category = normalized_error
        if next_state == PREPARATION_STATE_PREPARING and not preparation.started_at:
            preparation.started_at = now
        elif next_state == PREPARATION_STATE_READY_FOR_REVIEW:
            preparation.ready_at = now
        elif next_state == PREPARATION_STATE_NEEDS_ATTENTION:
            preparation.attention_at = now
        self._repository.record_report(preparation_id, normalized_message, report_type, fingerprint)
        self._repository.save(preparation)
        return preparation

    def apply_action_from_extension(
        self,
        *,
        preparation_id: str,
        package_id: str,
        action: str,
        raw_session: str,
        extension_origin: str,
    ) -> AssistedApplyPreparation:
        self._require_enabled()
        user, _connection = self.package_service._connection_service.authenticate_session(
            raw_session=raw_session, extension_origin=extension_origin,
        )
        preparation = self._get(preparation_id)
        self._authorize(preparation, user.user_id)
        if preparation.package_id != str(package_id or "").strip():
            raise PreparationAuthorizationError("Preparation is not associated with this package.")
        return self.apply_action(user_id=user.user_id, preparation_id=preparation_id, action=action)

    def apply_action(self, *, user_id: str, preparation_id: str, action: str) -> AssistedApplyPreparation:
        self._require_enabled()
        preparation = self._get(preparation_id)
        self._authorize(preparation, user_id)
        preparation = self._expire_if_needed(preparation)
        next_state = transition_for_action(preparation.state, action)
        now = self._now().isoformat()
        preparation.state = next_state
        preparation.updated_at = now
        if action == "cancel":
            preparation.cancelled_at = now
        elif action == "retry":
            preparation.attempt_count += 1
            preparation.error_category = ""
            preparation.completed_count = 0
            preparation.total_count = 0
            preparation.expires_at = (self._now() + timedelta(seconds=ASSISTED_APPLY_SESSION_TTL_SECONDS)).isoformat()
            preparation.started_at = ""
            preparation.ready_at = ""
            preparation.attention_at = ""
            preparation.expired_at = ""
        self._repository.save(preparation)
        return preparation
