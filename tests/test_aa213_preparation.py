from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend import create_backend
from backend.api.routes import build_route_registry
from backend.api.routes.assisted_apply_preparations import _create, _read, _report
from backend.domain.assisted_apply_preparation import (
    PREPARATION_STATE_ACTIVE,
    PREPARATION_STATE_EXPIRED,
    PREPARATION_STATE_NEEDS_ATTENTION,
    PREPARATION_STATE_PERMISSION_REQUIRED,
    PREPARATION_STATE_PREPARING,
    PREPARATION_STATE_READY_FOR_REVIEW,
    PreparationAuthorizationError,
    PreparationFeatureDisabledError,
    PreparationStateError,
)


class AA213PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="runr-aa213-")
        self.addCleanup(self.temp_dir.cleanup)
        self.env = patch.dict(os.environ, {
            "DATABASE_BACKEND": "sqlite", "RUNR_ENV": "test", "TURSO_DATABASE_URL": "",
            "TURSO_AUTH_TOKEN": "", "OBJECT_STORAGE_BACKEND": "local",
            "OBJECT_STORAGE_LOCAL_ROOT": str(Path(self.temp_dir.name) / "objects"),
            "RUNR_INTERNAL_OBJECT_STORAGE_LOCAL_ROOT": "",
            "RUNR_ENABLE_ASSISTED_APPLY_PREPARATION": "1",
        }, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.app = create_backend(Path(self.temp_dir.name), storage_backend="sqlite")
        self.owner = self.app.upsert_user({"email": "owner@example.com", "role": "admin"})
        self.other = self.app.upsert_user({"email": "other@example.com", "role": "admin"})
        self.package = self.app.create_application_package(
            user_id=self.owner.user_id,
            job={"job_id": "job_213", "title": "Engineer", "company": "Acme", "portal": "greenhouse", "url": "https://boards.greenhouse.io/acme/jobs/213"},
            answers=[], documents=[],
        )
        self.service = self.app._assisted_apply_preparation_service
        self.connection = SimpleNamespace(request_id="session_213")
        self.session_patch = patch.object(
            type(self.service.package_service._connection_service),
            "authenticate_session",
            return_value=(self.owner, self.connection),
        )
        self.session_patch.start()
        self.addCleanup(self.session_patch.stop)

    def test_migration_is_additive_and_contains_no_browser_or_raw_value_fields(self):
        with self.app.repositories.auth_repository._connect() as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(assisted_apply_preparations)").fetchall()}
            migration = conn.execute("SELECT migration_id FROM schema_migrations WHERE migration_id = '027_assisted_apply_preparations'").fetchone()
        self.assertIn("application_url", columns)
        self.assertIsNotNone(migration)
        self.assertNotIn("tabId", columns)
        self.assertNotIn("windowId", columns)
        self.assertNotIn("dom_selector", columns)
        self.assertNotIn("raw_field_value", columns)

    def test_invalid_transitions_and_cross_user_access_fail(self):
        preparation = self.service.create(user_id=self.owner.user_id, package_id=self.package.package_id)
        with self.assertRaises(PreparationAuthorizationError):
            self.service.get_for_user(user_id=self.other.user_id, preparation_id=preparation.preparation_id)
        with self.assertRaises(PreparationStateError):
            self.service.apply_action(user_id=self.owner.user_id, preparation_id=preparation.preparation_id, action="activate")
        with self.assertRaises(PreparationStateError):
            self.service.report_from_extension(
                preparation_id=preparation.preparation_id, message_id="m-invalid", report_type="progress",
                raw_session="session", extension_origin="chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            )
        with self.assertRaises(PreparationAuthorizationError):
            self.service.report_from_extension(
                preparation_id=preparation.preparation_id, package_id="wrong-package", message_id="m-wrong-package",
                report_type="permission_required", raw_session="session",
                extension_origin="chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            )

    def test_report_lifecycle_binds_session_and_replay_is_idempotent(self):
        preparation = self.service.create(user_id=self.owner.user_id, package_id=self.package.package_id)
        args = {"preparation_id": preparation.preparation_id, "message_id": "m-permission", "report_type": "permission_required", "raw_session": "session", "extension_origin": "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
        current = self.service.report_from_extension(**args)
        self.assertEqual(current.state, PREPARATION_STATE_PERMISSION_REQUIRED)
        replay = self.service.report_from_extension(**args)
        self.assertEqual(replay.state, PREPARATION_STATE_PERMISSION_REQUIRED)
        with self.assertRaises(PreparationStateError):
            self.service.report_from_extension(**{**args, "report_type": "accepted"})
        current = self.service.report_from_extension(**{**args, "message_id": "m-accepted", "report_type": "accepted"})
        self.assertEqual(current.state, PREPARATION_STATE_PREPARING)
        current = self.service.report_from_extension(**{**args, "message_id": "m-progress", "report_type": "progress", "total_count": 2, "completed_count": 1})
        self.assertEqual((current.total_count, current.completed_count), (2, 1))
        current = self.service.report_from_extension(**{**args, "message_id": "m-ready", "report_type": "ready_for_review", "total_count": 2, "completed_count": 2})
        self.assertEqual(current.state, PREPARATION_STATE_READY_FOR_REVIEW)
        current = self.service.apply_action(user_id=self.owner.user_id, preparation_id=preparation.preparation_id, action="activate")
        self.assertEqual(current.state, PREPARATION_STATE_ACTIVE)

    def test_expiry_and_explicit_retry_increment_attempt_without_submission_state(self):
        preparation = self.service.create(user_id=self.owner.user_id, package_id=self.package.package_id)
        preparation.expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        self.service._repository.save(preparation)
        expired = self.service.get_for_user(user_id=self.owner.user_id, preparation_id=preparation.preparation_id)
        self.assertEqual(expired.state, PREPARATION_STATE_EXPIRED)
        retried = self.service.apply_action(user_id=self.owner.user_id, preparation_id=preparation.preparation_id, action="retry")
        self.assertEqual(retried.attempt_count, 2)
        self.assertEqual(retried.state, "created")
        self.assertNotIn("submitted", retried.to_dict())

    def test_feature_is_disabled_by_default(self):
        disabled = type(self.service)(repositories=self.app.repositories, package_service=self.service.package_service, enabled=False)
        with self.assertRaises(PreparationFeatureDisabledError):
            disabled.create(user_id=self.owner.user_id, package_id=self.package.package_id)

    def test_preparation_routes_are_registered_for_web_and_extension_report(self):
        names = {route.name for route in build_route_registry()._routes}
        self.assertIn("assisted_apply.preparations.create", names)
        self.assertIn("assisted_apply.preparations.read", names)
        self.assertIn("assisted_apply.preparations.action", names)
        self.assertIn("assisted_apply.extension.preparations.report", names)

    def test_authenticated_web_read_and_extension_report_routes_use_sanitized_payloads(self):
        class Context:
            def __init__(self, segments, payload, user=None, token=""):
                self.application = self_outer.app
                self.segments = tuple(segments)
                self.query = {}
                self.payload = payload
                self.user = user
                self.token = token
                self.response = None
            def require_clerk_identity(self):
                return self.user, None
            def read_json_body(self):
                return dict(self.payload)
            def send_json(self, payload, status=200, **_kwargs):
                self.response = (status, payload)
            def send_error(self, status, code, message, **_kwargs):
                self.response = (status, {"code": code, "message": message})
            def bearer_token(self):
                return self.token
            def request_client_origin(self):
                return "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

        self_outer = self
        create_context = Context(("assisted-apply", "preparations"), {"package_id": self.package.package_id}, self.owner)
        _create(create_context)
        preparation_id = create_context.response[1]["preparation_id"]
        self.assertEqual(create_context.response[1]["application_url"], self.package.job.url)
        report_context = Context(
            ("assisted-apply", "extension", "preparations", "report"),
            {"preparation_id": preparation_id, "message_id": "route-1", "type": "permission_required"},
            token="session-token",
        )
        _report(report_context)
        read_context = Context(("assisted-apply", "preparations", preparation_id), {}, self.owner)
        _read(read_context)
        self.assertEqual(read_context.response[1]["state"], PREPARATION_STATE_PERMISSION_REQUIRED)
        with self.assertRaises(ValueError):
            _report(Context(
                ("assisted-apply", "extension", "preparations", "report"),
                {"preparation_id": preparation_id, "message_id": "route-2", "type": "progress", "tabId": 42},
                token="session-token",
            ))


if __name__ == "__main__":
    unittest.main()
