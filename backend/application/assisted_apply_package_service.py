"""Immutable application-package service for Assisted Apply (AA-03)."""

from __future__ import annotations

import hashlib
import hmac
import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from typing import Any, Callable, Mapping

from backend.domain.application_package import (
    APPLICATION_PACKAGE_BINDING_TTL_SECONDS,
    APPLICATION_PACKAGE_ID_PREFIX,
    APPLICATION_PACKAGE_STATUS_BOUND,
    APPLICATION_PACKAGE_STATUS_CREATED,
    APPLICATION_PACKAGE_STATUS_EXPIRED,
    APPLICATION_PACKAGE_STATUS_LAUNCHED,
    APPLICATION_PACKAGE_TTL_SECONDS,
    ApplicationPackage,
    ApplicationPackageAnswer,
    ApplicationPackageDocumentRef,
    ApplicationPackageJob,
    ApplicationPackagePolicy,
    ApplicationPackageWarnings,
    _require_nonempty_str,
    _utc_now_iso,
    new_application_package,
)
from backend.domain.assisted_apply import AssistedApplyPreferences
from backend.domain.models import UserRecord
from backend.repositories.contracts import BackendRepositories
from backend.security.auth import hash_token_value, verify_token_value


ASSISTED_APPLY_DOCUMENT_GRANT_TTL_SECONDS = 60
ASSISTED_APPLY_DOCUMENT_GRANT_TOKEN_PREFIX = "aadoc_"
ASSISTED_APPLY_DOCUMENT_GRANT_LOOKUP_PREFIX_LENGTH = 20
ASSISTED_APPLY_MAX_CV_BYTES = 10 * 1024 * 1024


class ApplicationPackageStateError(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class ApplicationPackageStore:
    """SQLite-backed storage for ApplicationPackage records.

    Uses the auth_repository connection because application_packages is a
    tightly-scoped Assisted Apply table.  A full PackageRepositoryProtocol
    extraction is deferred to AA-06 which owns the cross-language schema.
    """

    def __init__(self, repositories: BackendRepositories) -> None:
        self._auth_repo = repositories.auth_repository

    @contextmanager
    def connection(self):
        if not hasattr(self._auth_repo, "_connect"):
            raise RuntimeError("ApplicationPackageStore requires a SQLite backend.")
        with self._auth_repo._connect() as connection:
            yield connection

    def save(self, package: ApplicationPackage) -> None:
        with self.connection() as conn:
            conn.execute(
            """
            INSERT INTO application_packages (
                package_id, user_id, job_id, version, status, schema_version,
                launch_tab_binding_id, launch_tab_binding_expires_at,
                created_at, updated_at, launched_at, bound_at,
                expired_at, consumed_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(package_id) DO UPDATE SET
                status=excluded.status,
                launch_tab_binding_id=excluded.launch_tab_binding_id,
                launch_tab_binding_expires_at=excluded.launch_tab_binding_expires_at,
                updated_at=excluded.updated_at,
                launched_at=excluded.launched_at,
                bound_at=excluded.bound_at,
                expired_at=excluded.expired_at,
                consumed_at=excluded.consumed_at,
                payload_json=excluded.payload_json
            """,
            (
                package.package_id,
                package.user_id,
                package.job_id,
                package.version,
                package.status,
                package.schema_version,
                package.launch_tab_binding_id,
                package.launch_tab_binding_expires_at,
                package.created_at,
                package.updated_at,
                package.launched_at,
                package.bound_at,
                package.expired_at,
                package.consumed_at,
                json.dumps(package.to_dict(), ensure_ascii=False),
            ),
        )

    def get(self, package_id: str) -> ApplicationPackage | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT payload_json FROM application_packages WHERE package_id = ?",
                (str(package_id or "").strip(),),
            ).fetchone()
        if row is None:
            return None
        return ApplicationPackage.from_payload(
            json.loads(str(row["payload_json"] or "{}"))
        )

    def get_by_binding(self, binding_id: str) -> ApplicationPackage | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT payload_json FROM application_packages WHERE launch_tab_binding_id = ? AND launch_tab_binding_id != ''",
                (str(binding_id or "").strip(),),
            ).fetchone()
        if row is None:
            return None
        return ApplicationPackage.from_payload(
            json.loads(str(row["payload_json"] or "{}"))
        )

    def expire_stale(self, *, now: str) -> int:
        with self.connection() as conn:
            result = conn.execute(
            """
            UPDATE application_packages
            SET status = ?, expired_at = ?, updated_at = ?
            WHERE status IN (?, ?)
              AND (
                (status = ? AND launched_at != '' AND ? > launch_tab_binding_expires_at)
                OR
                (status = ? AND launched_at = '' AND ? > created_at)
              )
            """,
            (
                APPLICATION_PACKAGE_STATUS_EXPIRED,
                now,
                now,
                APPLICATION_PACKAGE_STATUS_LAUNCHED,
                APPLICATION_PACKAGE_STATUS_BOUND,
                APPLICATION_PACKAGE_STATUS_LAUNCHED,
                now,
                APPLICATION_PACKAGE_STATUS_BOUND,
                now,
            ),
        )
        return result.rowcount if hasattr(result, "rowcount") else 0


@dataclass(slots=True)
class ApplicationPackageService:
    repositories: BackendRepositories
    object_storage: Any = field(default=None, repr=False)
    now_provider: Callable[[], datetime] = field(default=_utc_now, repr=False)
    _store: ApplicationPackageStore = field(init=False, repr=False)
    _connection_service: Any = field(init=False, repr=False)
    _correction_service: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._store = ApplicationPackageStore(self.repositories)
        from backend.application.assisted_apply_service import AssistedApplyConnectionService
        from backend.application.assisted_apply_correction_service import AssistedApplyCorrectionService

        self._connection_service = AssistedApplyConnectionService(
            repositories=self.repositories,
            now_provider=self.now_provider,
        )
        self._correction_service = AssistedApplyCorrectionService(
            repositories=self.repositories,
            now_provider=self.now_provider,
        )

    def _now(self) -> datetime:
        return _as_utc(self.now_provider())

    def _get_active_user(self, user_id: str) -> UserRecord:
        normalized = str(user_id or "").strip()
        if not normalized:
            raise ValueError("user_id is required.")
        user = self.repositories.auth_repository.get_user(normalized)
        if not user.is_active:
            raise PermissionError("User is inactive.")
        return user

    def _preferences_for_user(self, user: UserRecord) -> AssistedApplyPreferences:
        from backend.domain.assisted_apply import (
            ASSISTED_APPLY_PREFERENCES_METADATA_KEY,
        )

        stored = dict(user.metadata or {}).get(ASSISTED_APPLY_PREFERENCES_METADATA_KEY)
        return AssistedApplyPreferences.from_stored(
            stored if isinstance(stored, Mapping) else None
        )

    def _build_policy(self, preferences: AssistedApplyPreferences) -> ApplicationPackagePolicy:
        return ApplicationPackagePolicy(
            schema_version=1,
            permit_sensitive_autofill=preferences.permit_sensitive_autofill,
            permit_demographic_autofill=preferences.permit_demographic_autofill,
            require_legal_answer_confirmation=preferences.require_legal_answer_confirmation,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_package(
        self,
        *,
        user_id: str,
        job: Mapping[str, Any],
        answers: list[Mapping[str, Any]] | None = None,
        documents: list[Mapping[str, Any]] | None = None,
        warnings_items: list[str] | None = None,
    ) -> ApplicationPackage:
        """Create an immutable, versioned application package.

        The package is created in `created` status and must be explicitly
        launched before the extension can fetch it.
        """
        user = self._get_active_user(user_id)
        preferences = self._preferences_for_user(user)
        now = self._now()

        package = new_application_package(
            user_id=user.user_id,
            job=ApplicationPackageJob.from_payload(job),
            answers=[
                ApplicationPackageAnswer.from_payload(item)
                for item in (answers or [])
                if isinstance(item, Mapping)
            ],
            documents=[
                ApplicationPackageDocumentRef.from_payload(item)
                for item in (documents or [])
                if isinstance(item, Mapping)
            ],
            warnings=(
                ApplicationPackageWarnings(items=list(warnings_items or []))
                if warnings_items
                else None
            ),
            policy=self._build_policy(preferences),
            now=now.isoformat(),
        )
        package.answers = self._correction_service.apply_matching(package, package.answers)
        self._store.save(package)
        return self._store.get(package.package_id)  # type: ignore[return-value]

    def launch_package(
        self,
        *,
        user_id: str,
        package_id: str,
    ) -> ApplicationPackage:
        """Transition a created package to launched, generating a binding ID.

        The binding ID is an opaque token the extension uses in the
        web-to-extension handshake.  It MUST NOT appear in the employer
        page URL or DOM.
        """
        user = self._get_active_user(user_id)
        package = self._store.get(package_id)
        if package is None:
            raise ValueError("Application package not found.")
        if package.user_id != user.user_id:
            raise PermissionError("Application package belongs to another user.")
        if package.status != APPLICATION_PACKAGE_STATUS_CREATED:
            raise ApplicationPackageStateError(
                f"Package is {package.status}; only created packages can be launched."
            )

        now = self._now()
        binding_id = f"{APPLICATION_PACKAGE_ID_PREFIX}bind_{token_urlsafe(32)}"
        launched = ApplicationPackage.from_payload(
            {
                **package.to_dict(),
                "status": APPLICATION_PACKAGE_STATUS_LAUNCHED,
                "launch_tab_binding_id": binding_id,
                "launch_tab_binding_expires_at": (
                    now + timedelta(seconds=APPLICATION_PACKAGE_BINDING_TTL_SECONDS)
                ).isoformat(),
                "launched_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
        )
        self._store.save(launched)
        return self._store.get(package.package_id)  # type: ignore[return-value]

    def bind_package(
        self,
        *,
        binding_id: str,
        extension_origin: str,
    ) -> ApplicationPackage:
        """Bind a launched package to the requesting extension.

        Returns the extension-safe payload subset (no secrets, server-side
        document URLs, or tokens).
        """
        from backend.application.assisted_apply_service import normalize_extension_origin

        normalize_extension_origin(extension_origin)
        package = self._store.get_by_binding(binding_id)
        if package is None:
            raise PermissionError("No launchable application package matches the binding.")

        now = self._now()
        if (
            package.launch_tab_binding_expires_at
            and now.isoformat() > package.launch_tab_binding_expires_at
        ):
            # Expire it
            bound = ApplicationPackage.from_payload(
                {
                    **package.to_dict(),
                    "status": APPLICATION_PACKAGE_STATUS_EXPIRED,
                    "expired_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }
            )
            self._store.save(bound)
            raise ApplicationPackageStateError("The application package binding expired.")

        if package.status == APPLICATION_PACKAGE_STATUS_BOUND:
            return package

        if package.status != APPLICATION_PACKAGE_STATUS_LAUNCHED:
            raise ApplicationPackageStateError(
                f"Package is {package.status}; only launched packages can be bound."
            )

        bound = ApplicationPackage.from_payload(
            {
                **package.to_dict(),
                "status": APPLICATION_PACKAGE_STATUS_BOUND,
                "bound_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
        )
        self._store.save(bound)
        return self._store.get(package.package_id)  # type: ignore[return-value]

    def get_package_for_extension(
        self,
        *,
        package_id: str,
        raw_session: str,
        extension_origin: str,
    ) -> dict[str, Any]:
        """Authenticate the extension session and return the extension payload."""
        user, _connection = self._connection_service.authenticate_session(
            raw_session=raw_session,
            extension_origin=extension_origin,
        )
        package = self._store.get(package_id)
        if package is None:
            raise ValueError("Application package not found.")
        if package.user_id != user.user_id:
            raise PermissionError("Application package belongs to another user.")
        return package.to_extension_payload()

    def save_correction_for_extension(
        self,
        *,
        package_id: str,
        field_intent: str,
        corrected_value: str,
        scope: str,
        raw_session: str,
        extension_origin: str,
    ) -> dict[str, Any]:
        user, _connection = self._connection_service.authenticate_session(
            raw_session=raw_session,
            extension_origin=extension_origin,
        )
        package = self._store.get(package_id)
        if package is None:
            raise ValueError("Application package not found.")
        return self._correction_service.save_correction(
            user_id=user.user_id,
            package=package,
            field_intent=field_intent,
            corrected_value=corrected_value,
            scope=scope,
        )

    def create_document_grant(
        self,
        *,
        package_id: str,
        document_id: str,
        raw_session: str,
        extension_origin: str,
    ) -> dict[str, Any]:
        """Issue a hash-only, short-lived grant for one fixed package document."""
        if self.object_storage is None:
            raise RuntimeError("Document grants require private object storage.")
        user, connection = self._connection_service.authenticate_session(
            raw_session=raw_session,
            extension_origin=extension_origin,
        )
        package = self._store.get(package_id)
        if package is None:
            raise ValueError("Application package not found.")
        if package.user_id != user.user_id:
            raise PermissionError("Application package belongs to another user.")
        if package.status != APPLICATION_PACKAGE_STATUS_BOUND:
            raise ApplicationPackageStateError("Documents require a bound application package.")
        selected = next(
            (item for item in package.documents if item.document_id == str(document_id or "").strip()),
            None,
        )
        if selected is None:
            raise ValueError("The selected document is not in this application package.")
        if selected.document_kind != "cv" or selected.mime_type != "application/pdf":
            raise ValueError("AA-11 supports one selected PDF CV only.")

        file_bytes = self.object_storage.get(selected.object_key)
        actual_size = len(file_bytes)
        actual_sha256 = hashlib.sha256(file_bytes).hexdigest()
        if actual_size <= 0 or actual_size > ASSISTED_APPLY_MAX_CV_BYTES:
            raise ValueError("The selected CV has an unsupported size.")
        if selected.sha256_hex and not hmac.compare_digest(
            selected.sha256_hex.lower(), actual_sha256
        ):
            raise ValueError("The selected CV no longer matches its immutable package version.")
        del file_bytes

        now = self._now()
        grant_id = f"aagrant_{token_urlsafe(24)}"
        raw_grant = f"{ASSISTED_APPLY_DOCUMENT_GRANT_TOKEN_PREFIX}{token_urlsafe(48)}"
        expires_at = (now + timedelta(seconds=ASSISTED_APPLY_DOCUMENT_GRANT_TTL_SECONDS)).isoformat()
        with self._store.connection() as conn:
            conn.execute(
                """
            INSERT INTO assisted_apply_document_grants (
                grant_id, grant_token_prefix, grant_token_hash, user_id,
                connection_request_id, extension_origin, package_id, document_id,
                document_version, asset_id, object_key, file_name, mime_type,
                expected_size, expected_sha256_hex, status, created_at, expires_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'issued', ?, ?, ?)
            """,
            (
                grant_id,
                raw_grant[:ASSISTED_APPLY_DOCUMENT_GRANT_LOOKUP_PREFIX_LENGTH],
                hash_token_value(raw_grant),
                user.user_id,
                connection.request_id,
                extension_origin,
                package.package_id,
                selected.document_id,
                selected.document_version,
                selected.asset_id,
                selected.object_key,
                selected.file_name,
                selected.mime_type,
                actual_size,
                actual_sha256,
                now.isoformat(),
                expires_at,
                now.isoformat(),
                ),
            )
        return {
            "grantToken": raw_grant,
            "file": {
                "documentId": selected.document_id,
                "documentVersion": selected.document_version,
                "fileName": selected.file_name,
                "mimeType": selected.mime_type,
                "size": actual_size,
                "sha256Hex": actual_sha256,
            },
            "expiresAt": expires_at,
        }

    def consume_document_grant(
        self,
        *,
        raw_grant: str,
        raw_session: str,
        extension_origin: str,
    ) -> tuple[bytes, dict[str, Any]]:
        """Atomically consume a grant and return bytes without a URL or disk cache."""
        if self.object_storage is None:
            raise RuntimeError("Document grants require private object storage.")
        user, connection = self._connection_service.authenticate_session(
            raw_session=raw_session,
            extension_origin=extension_origin,
        )
        token = str(raw_grant or "").strip()
        if not token.startswith(ASSISTED_APPLY_DOCUMENT_GRANT_TOKEN_PREFIX):
            raise PermissionError("Invalid or expired document grant.")
        with self._store.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM assisted_apply_document_grants WHERE grant_token_prefix = ?",
                (token[:ASSISTED_APPLY_DOCUMENT_GRANT_LOOKUP_PREFIX_LENGTH],),
            ).fetchall()
            row = next(
                (item for item in rows if verify_token_value(token, str(item["grant_token_hash"] or ""))),
                None,
            )
            now = self._now()
            if row is None:
                raise PermissionError("Invalid or expired document grant.")
            if (
                row["user_id"] != user.user_id
                or row["connection_request_id"] != connection.request_id
                or row["extension_origin"] != extension_origin
            ):
                raise PermissionError("Document grant does not match this extension session.")
            if row["status"] != "issued" or row["consumed_at"]:
                raise PermissionError("Document grant has already been consumed.")
            if now.isoformat() >= str(row["expires_at"]):
                conn.execute(
                    "UPDATE assisted_apply_document_grants SET status='expired', updated_at=? WHERE grant_id=? AND status='issued'",
                    (now.isoformat(), row["grant_id"]),
                )
                raise PermissionError("Document grant expired.")
            claimed = conn.execute(
            """
            UPDATE assisted_apply_document_grants
            SET status='consumed', consumed_at=?, updated_at=?
            WHERE grant_id=? AND status='issued' AND consumed_at=''
            """,
            (now.isoformat(), now.isoformat(), row["grant_id"]),
            )
            if getattr(claimed, "rowcount", 0) != 1:
                raise PermissionError("Document grant has already been consumed.")

        file_bytes = self.object_storage.get(str(row["object_key"]))
        actual_sha256 = hashlib.sha256(file_bytes).hexdigest()
        if len(file_bytes) != int(row["expected_size"]) or not hmac.compare_digest(
            actual_sha256, str(row["expected_sha256_hex"])
        ):
            with self._store.connection() as conn:
                conn.execute(
                    "UPDATE assisted_apply_document_grants SET status='rejected', failure_reason='content_mismatch', updated_at=? WHERE grant_id=?",
                    (now.isoformat(), row["grant_id"]),
                )
            raise ValueError("The document bytes did not match the immutable grant metadata.")
        return file_bytes, {
            "documentId": str(row["document_id"]),
            "documentVersion": int(row["document_version"]),
            "fileName": str(row["file_name"]),
            "mimeType": str(row["mime_type"]),
            "size": int(row["expected_size"]),
            "sha256Hex": str(row["expected_sha256_hex"]),
        }
