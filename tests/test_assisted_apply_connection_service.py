import base64
import hashlib
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from backend import create_backend
from backend.application.assisted_apply_service import (
    ASSISTED_APPLY_SESSION_TTL_SECONDS,
    AssistedApplyConnectionService,
    AssistedApplyConnectionStateError,
)
from backend.domain.assisted_apply import (
    ASSISTED_APPLY_PREFERENCES_METADATA_KEY,
    ASSISTED_APPLY_STATUS_ACTIVE,
    ASSISTED_APPLY_STATUS_AUTHORIZED,
    ASSISTED_APPLY_STATUS_EXPIRED,
    ASSISTED_APPLY_STATUS_REJECTED,
    ASSISTED_APPLY_STATUS_REVOKED,
    AssistedApplyPreferences,
)


EXTENSION_ID = "a" * 32
EXTENSION_ORIGIN = f"chrome-extension://{EXTENSION_ID}"
OTHER_EXTENSION_ORIGIN = f"chrome-extension://{'b' * 32}"
VERIFIER = "v" * 43
CHALLENGE = base64.urlsafe_b64encode(
    hashlib.sha256(VERIFIER.encode("ascii")).digest()
).decode("ascii").rstrip("=")


class MutableClock:
    def __init__(self, value: datetime):
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs) -> None:
        self.value += timedelta(**kwargs)


class AssistedApplyConnectionServiceTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(
            os.environ,
            {
                "DATABASE_BACKEND": "sqlite",
                "RUNR_ENV": "test",
                "TURSO_DATABASE_URL": "",
                "TURSO_AUTH_TOKEN": "",
                "OBJECT_STORAGE_BACKEND": "local",
                "RUNR_INTERNAL_OBJECT_STORAGE_LOCAL_ROOT": "",
            },
            clear=False,
        )
        environment.start()
        self.addCleanup(environment.stop)

    def _create_app(self, storage_backend: str, suffix: str):
        temporary_directory = tempfile.TemporaryDirectory(prefix=f"runr-aa-{suffix}-")
        self.addCleanup(temporary_directory.cleanup)
        environment = {
            "DATABASE_BACKEND": "sqlite",
            "RUNR_ENV": "test",
            "TURSO_DATABASE_URL": "",
            "TURSO_AUTH_TOKEN": "",
            "OBJECT_STORAGE_BACKEND": "local",
            "OBJECT_STORAGE_LOCAL_ROOT": str(Path(temporary_directory.name) / "objects"),
            "RUNR_INTERNAL_OBJECT_STORAGE_LOCAL_ROOT": "",
        }
        with patch.dict(os.environ, environment, clear=False):
            return create_backend(
                Path(temporary_directory.name),
                storage_backend=storage_backend,
            )

    @staticmethod
    def _create_user(app, suffix: str):
        return app.upsert_user(
            {
                "email": f"assisted-apply-{suffix}@example.com",
                "display_name": f"Candidate {suffix}",
            }
        )

    @staticmethod
    def _create_request(app):
        return app.create_assisted_apply_connection_request(
            extension_origin=EXTENSION_ORIGIN,
            state="s" * 32,
            challenge=CHALLENGE,
            installation_id="i" * 32,
            version="1.0.0",
        )

    @staticmethod
    def _authorization_code(completion_url: str) -> str:
        return parse_qs(urlparse(completion_url).query)["code"][0]

    def test_full_connection_lifecycle_is_hash_only_user_bound_and_revocable(self):
        for storage_backend in ("file", "sqlite"):
            with self.subTest(storage_backend=storage_backend):
                app = self._create_app(storage_backend, f"lifecycle-{storage_backend}")
                user = self._create_user(app, f"owner-{storage_backend}")
                other_user = self._create_user(app, f"other-{storage_backend}")
                request = self._create_request(app)

                dashboard = app.get_assisted_apply_connection_dashboard(
                    user_id=user.user_id,
                    request_id=request.request_id,
                )
                self.assertEqual(
                    dashboard["preferences"],
                    {
                        "schema_version": 1,
                        "permit_sensitive_autofill": False,
                        "permit_demographic_autofill": False,
                        "require_legal_answer_confirmation": True,
                        "revision": 0,
                        "updated_at": "",
                    },
                )
                self.assertNotIn("client_state", dashboard)
                self.assertNotIn("pkce_challenge", dashboard)

                completion_url = app.authorize_assisted_apply_connection(
                    user_id=user.user_id,
                    request_id=request.request_id,
                    preferences={"permit_sensitive_autofill": True},
                )
                parsed_completion = urlparse(completion_url)
                completion_query = parse_qs(parsed_completion.query)
                self.assertEqual(parsed_completion.scheme, "https")
                self.assertEqual(parsed_completion.netloc, f"{EXTENSION_ID}.chromiumapp.org")
                self.assertEqual(parsed_completion.path, "/runr/connect")
                self.assertEqual(completion_query["request_id"], [request.request_id])
                self.assertEqual(completion_query["state"], ["s" * 32])
                raw_code = completion_query["code"][0]

                authorized = app.repositories.auth_repository.get_assisted_apply_connection(
                    request.request_id
                )
                self.assertEqual(authorized.status, ASSISTED_APPLY_STATUS_AUTHORIZED)
                self.assertEqual(authorized.user_id, user.user_id)
                self.assertTrue(authorized.authorization_code_hash.startswith("120000$"))
                self.assertNotIn(raw_code, json.dumps(authorized.to_dict()))
                with self.assertRaises(PermissionError):
                    app.get_assisted_apply_connection_dashboard(
                        user_id=other_user.user_id,
                        request_id=request.request_id,
                    )

                active, raw_session = app.exchange_assisted_apply_authorization(
                    extension_origin=EXTENSION_ORIGIN,
                    request_id=request.request_id,
                    code=raw_code,
                    verifier=VERIFIER,
                )
                self.assertEqual(active.status, ASSISTED_APPLY_STATUS_ACTIVE)
                self.assertEqual(
                    datetime.fromisoformat(active.session_expires_at)
                    - datetime.fromisoformat(active.activated_at),
                    timedelta(seconds=ASSISTED_APPLY_SESSION_TTL_SECONDS),
                )
                stored_active = app.repositories.auth_repository.get_assisted_apply_connection(
                    request.request_id
                )
                self.assertTrue(stored_active.session_token_hash.startswith("120000$"))
                self.assertNotIn(raw_session, json.dumps(stored_active.to_dict()))
                self.assertEqual(stored_active.authorization_code_hash, "")
                with self.assertRaises(AssistedApplyConnectionStateError):
                    app.exchange_assisted_apply_authorization(
                        extension_origin=EXTENSION_ORIGIN,
                        request_id=request.request_id,
                        code=raw_code,
                        verifier=VERIFIER,
                    )

                authenticated_user, authenticated_connection = (
                    app.authenticate_assisted_apply_session(
                        raw_session=raw_session,
                        extension_origin=EXTENSION_ORIGIN,
                    )
                )
                self.assertEqual(authenticated_user.user_id, user.user_id)
                self.assertEqual(authenticated_connection.request_id, request.request_id)
                with self.assertRaises(PermissionError):
                    app.authenticate_access_token(raw_session)

                revoked = app.revoke_current_assisted_apply_session(
                    raw_session=raw_session,
                    extension_origin=EXTENSION_ORIGIN,
                )
                self.assertEqual(revoked.status, ASSISTED_APPLY_STATUS_REVOKED)
                self.assertEqual(revoked.session_token_hash, "")
                with self.assertRaises(PermissionError):
                    app.authenticate_assisted_apply_session(
                        raw_session=raw_session,
                        extension_origin=EXTENSION_ORIGIN,
                    )

                preferences = app.get_assisted_apply_preferences(user.user_id).to_dict()
                self.assertEqual(preferences["revision"], 1)
                self.assertTrue(preferences["permit_sensitive_autofill"])
                self.assertTrue(preferences["require_legal_answer_confirmation"])
                self.assertTrue(preferences["updated_at"])

    def test_exchange_rejects_wrong_origin_code_verifier_and_cross_user_access(self):
        app = self._create_app("sqlite", "exchange-guards")
        user = self._create_user(app, "exchange-owner")
        request = self._create_request(app)
        completion_url = app.authorize_assisted_apply_connection(
            user_id=user.user_id,
            request_id=request.request_id,
        )
        code = self._authorization_code(completion_url)

        with self.assertRaises(PermissionError):
            app.exchange_assisted_apply_authorization(
                extension_origin=OTHER_EXTENSION_ORIGIN,
                request_id=request.request_id,
                code=code,
                verifier=VERIFIER,
            )
        with self.assertRaises(PermissionError):
            app.exchange_assisted_apply_authorization(
                extension_origin=EXTENSION_ORIGIN,
                request_id=request.request_id,
                code="aaac_wrong-secret",
                verifier=VERIFIER,
            )
        with self.assertRaises(PermissionError):
            app.exchange_assisted_apply_authorization(
                extension_origin=EXTENSION_ORIGIN,
                request_id=request.request_id,
                code=code,
                verifier="w" * 43,
            )

        active, raw_session = app.exchange_assisted_apply_authorization(
            extension_origin=EXTENSION_ORIGIN,
            request_id=request.request_id,
            code=code,
            verifier=VERIFIER,
        )
        self.assertEqual(active.status, ASSISTED_APPLY_STATUS_ACTIVE)
        with self.assertRaises(PermissionError):
            app.authenticate_assisted_apply_session(
                raw_session=raw_session,
                extension_origin=OTHER_EXTENSION_ORIGIN,
            )

        other_user = self._create_user(app, "exchange-other")
        with self.assertRaises(PermissionError):
            app.revoke_owned_assisted_apply_connection(
                user_id=other_user.user_id,
                request_id=request.request_id,
            )

    def test_request_validation_requires_exact_chrome_identity_and_s256_pkce(self):
        app = self._create_app("file", "request-validation")
        valid_payload = {
            "extension_origin": EXTENSION_ORIGIN,
            "state": "s" * 32,
            "challenge": CHALLENGE,
            "installation_id": "i" * 32,
            "version": "1.0.0",
        }
        for invalid_origin in (
            f"{EXTENSION_ORIGIN}/",
            f"chrome-extension://{'A' * 32}",
            f"chrome-extension://{'a' * 31}",
            f"https://{EXTENSION_ID}",
        ):
            with self.subTest(invalid_origin=invalid_origin), self.assertRaises(ValueError):
                app.create_assisted_apply_connection_request(
                    **{**valid_payload, "extension_origin": invalid_origin}
                )
        with self.assertRaisesRegex(ValueError, "S256"):
            app.create_assisted_apply_connection_request(
                **{**valid_payload, "challenge": "not-a-sha256-challenge"}
            )
        with self.assertRaisesRegex(ValueError, "state"):
            app.create_assisted_apply_connection_request(
                **{**valid_payload, "state": "short"}
            )

    def test_rejection_and_each_absolute_expiry_are_terminal(self):
        app = self._create_app("sqlite", "terminal-states")
        user = self._create_user(app, "terminal-owner")
        clock = MutableClock(datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc))
        service = AssistedApplyConnectionService(app.repositories, now_provider=clock)

        pending = service.create_request(
            extension_origin=EXTENSION_ORIGIN,
            state="p" * 32,
            challenge=CHALLENGE,
            installation_id="p" * 32,
            version="1.0.0",
        )
        clock.advance(minutes=10)
        self.assertEqual(
            service.dashboard(user_id=user.user_id, request_id=pending.request_id)["status"],
            ASSISTED_APPLY_STATUS_EXPIRED,
        )

        rejected_request = service.create_request(
            extension_origin=EXTENSION_ORIGIN,
            state="r" * 32,
            challenge=CHALLENGE,
            installation_id="r" * 32,
            version="1.0.0",
        )
        rejected = service.reject(user_id=user.user_id, request_id=rejected_request.request_id)
        self.assertEqual(rejected.status, ASSISTED_APPLY_STATUS_REJECTED)
        with self.assertRaises(AssistedApplyConnectionStateError):
            service.authorize(user_id=user.user_id, request_id=rejected_request.request_id)

        code_request = service.create_request(
            extension_origin=EXTENSION_ORIGIN,
            state="c" * 32,
            challenge=CHALLENGE,
            installation_id="c" * 32,
            version="1.0.0",
        )
        code_url = service.authorize(user_id=user.user_id, request_id=code_request.request_id)
        code = self._authorization_code(code_url)
        clock.advance(minutes=2)
        with self.assertRaises(AssistedApplyConnectionStateError):
            service.exchange(
                extension_origin=EXTENSION_ORIGIN,
                request_id=code_request.request_id,
                code=code,
                verifier=VERIFIER,
            )
        self.assertEqual(
            app.repositories.auth_repository.get_assisted_apply_connection(
                code_request.request_id
            ).status,
            ASSISTED_APPLY_STATUS_EXPIRED,
        )

        session_request = service.create_request(
            extension_origin=EXTENSION_ORIGIN,
            state="x" * 32,
            challenge=CHALLENGE,
            installation_id="x" * 32,
            version="1.0.0",
        )
        session_url = service.authorize(user_id=user.user_id, request_id=session_request.request_id)
        active, raw_session = service.exchange(
            extension_origin=EXTENSION_ORIGIN,
            request_id=session_request.request_id,
            code=self._authorization_code(session_url),
            verifier=VERIFIER,
        )
        clock.value = datetime.fromisoformat(active.session_expires_at)
        with self.assertRaises(PermissionError):
            service.authenticate_session(
                raw_session=raw_session,
                extension_origin=EXTENSION_ORIGIN,
            )
        expired = app.repositories.auth_repository.get_assisted_apply_connection(
            session_request.request_id
        )
        self.assertEqual(expired.status, ASSISTED_APPLY_STATUS_EXPIRED)
        self.assertEqual(expired.session_token_hash, "")

    def test_preferences_are_strict_versioned_and_fail_closed(self):
        app = self._create_app("file", "preferences")
        user = self._create_user(app, "preferences-owner")
        default = app.get_assisted_apply_preferences(user.user_id)
        self.assertEqual(default, AssistedApplyPreferences())

        first = app.update_assisted_apply_preferences(
            user_id=user.user_id,
            preferences={
                **default.to_dict(),
                "permit_demographic_autofill": True,
            },
        )
        self.assertEqual(first.revision, 1)
        self.assertTrue(first.permit_demographic_autofill)
        second = app.update_assisted_apply_preferences(
            user_id=user.user_id,
            preferences={
                **first.to_dict(),
                "permit_sensitive_autofill": True,
            },
        )
        self.assertEqual(second.revision, 2)
        self.assertGreater(second.updated_at, "")

        with self.assertRaisesRegex(ValueError, "stale or invalid"):
            app.update_assisted_apply_preferences(
                user_id=user.user_id,
                preferences=default.to_dict(),
            )
        with self.assertRaisesRegex(ValueError, "cannot be disabled"):
            app.update_assisted_apply_preferences(
                user_id=user.user_id,
                preferences={"require_legal_answer_confirmation": False},
            )
        with self.assertRaisesRegex(ValueError, "must be a boolean"):
            app.update_assisted_apply_preferences(
                user_id=user.user_id,
                preferences={"permit_sensitive_autofill": "yes"},
            )
        with self.assertRaisesRegex(ValueError, "schema version"):
            app.update_assisted_apply_preferences(
                user_id=user.user_id,
                preferences={"schema_version": True},
            )

        valid_stored = second.to_dict()
        malformed_values = (
            {**valid_stored, "updated_at": "forged"},
            {**valid_stored, "unexpected_policy": True},
            {**valid_stored, "schema_version": True},
            {**valid_stored, "revision": 0},
            {
                **valid_stored,
                "require_legal_answer_confirmation": False,
            },
        )
        for malformed_value in malformed_values:
            with self.subTest(malformed_value=malformed_value):
                malformed_user = app.get_user(user.user_id)
                malformed_user.metadata[
                    ASSISTED_APPLY_PREFERENCES_METADATA_KEY
                ] = malformed_value
                app.repositories.auth_repository.upsert_user(malformed_user)
                self.assertEqual(
                    app.get_assisted_apply_preferences(user.user_id),
                    AssistedApplyPreferences(),
                )

    def test_repository_authorize_and_exchange_transitions_have_one_winner(self):
        for storage_backend in ("file", "sqlite"):
            with self.subTest(storage_backend=storage_backend):
                app = self._create_app(storage_backend, f"atomic-{storage_backend}")
                user = self._create_user(app, f"atomic-{storage_backend}")
                request = self._create_request(app)
                repository = app.repositories.auth_repository
                now = datetime.now(timezone.utc)

                preference_candidates = (
                    AssistedApplyPreferences(
                        permit_sensitive_autofill=True,
                        revision=1,
                        updated_at=now.isoformat(),
                    ),
                    AssistedApplyPreferences(
                        permit_demographic_autofill=True,
                        revision=1,
                        updated_at=now.isoformat(),
                    ),
                )

                def update_preferences(preferences: AssistedApplyPreferences):
                    return repository.update_assisted_apply_preferences_metadata(
                        user.user_id,
                        expected_revision=0,
                        preferences=preferences,
                        updated_at=now.isoformat(),
                    )

                with ThreadPoolExecutor(max_workers=2) as executor:
                    preference_results = list(
                        executor.map(update_preferences, preference_candidates)
                    )
                self.assertEqual(sum(preference_results), 1)
                stored_preferences = app.get_assisted_apply_preferences(user.user_id)
                self.assertEqual(stored_preferences.revision, 1)
                self.assertNotEqual(
                    stored_preferences.permit_sensitive_autofill,
                    stored_preferences.permit_demographic_autofill,
                )

                def authorize(index: int):
                    return repository.authorize_assisted_apply_connection(
                        request.request_id,
                        user_id=user.user_id,
                        authorization_code_prefix=f"prefix-{index}",
                        authorization_code_hash=f"hash-{index}",
                        authorization_code_expires_at=(now + timedelta(minutes=2)).isoformat(),
                        authorized_at=now.isoformat(),
                    )

                with ThreadPoolExecutor(max_workers=2) as executor:
                    authorized_results = list(executor.map(authorize, (1, 2)))
                self.assertEqual(sum(result is not None for result in authorized_results), 1)

                def activate(index: int):
                    return repository.activate_assisted_apply_connection(
                        request.request_id,
                        extension_origin=EXTENSION_ORIGIN,
                        session_token_prefix=f"session-prefix-{index}",
                        session_token_hash=f"session-hash-{index}",
                        session_expires_at=(now + timedelta(hours=8)).isoformat(),
                        activated_at=now.isoformat(),
                    )

                with ThreadPoolExecutor(max_workers=2) as executor:
                    active_results = list(executor.map(activate, (1, 2)))
                self.assertEqual(sum(result is not None for result in active_results), 1)
                self.assertEqual(
                    repository.get_assisted_apply_connection(request.request_id).status,
                    ASSISTED_APPLY_STATUS_ACTIVE,
                )


if __name__ == "__main__":
    unittest.main()
