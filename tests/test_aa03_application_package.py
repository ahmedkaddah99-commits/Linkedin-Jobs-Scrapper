"""AA-03: Immutable application package tests.

Covers package ownership, expiry, immutability, replay/tab-binding,
web-to-extension launch handshake, side-panel display, data-only
responses, and Python/TypeScript schema compatibility.
"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend import create_backend
from backend.application.assisted_apply_package_service import (
    APPLICATION_PACKAGE_STATUS_BOUND,
    APPLICATION_PACKAGE_STATUS_CREATED,
    APPLICATION_PACKAGE_STATUS_LAUNCHED,
    ApplicationPackageStateError,
)
from backend.domain.application_package import (
    APPLICATION_PACKAGE_BINDING_TTL_SECONDS,
    ApplicationPackage,
    ApplicationPackageAnswer,
    ApplicationPackageDocumentRef,
    ApplicationPackageJob,
    ApplicationPackagePolicy,
    ApplicationPackageWarnings,
    new_application_package,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_PATH = REPO_ROOT / "tests" / "fixtures" / "package_schema_fixtures.json"
EXTENSION_ORIGIN = "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MutableClock:
    def __init__(self, value: datetime | None = None):
        self.value = value or _utc_now()
    def __call__(self) -> datetime:
        return self.value
    def advance(self, **kwargs) -> None:
        self.value += timedelta(**kwargs)


class ApplicationPackageImmutableTests(unittest.TestCase):
    """Test immutability, ownership, expiry, and versioning."""

    def setUp(self):
        self.environ_patch = patch.dict(
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
        self.environ_patch.start()
        self.addCleanup(self.environ_patch.stop)
        self.temp_dir = tempfile.TemporaryDirectory(prefix="runr-aa03-")
        self.addCleanup(self.temp_dir.cleanup)

    def _create_app(self):
        with patch.dict(
            os.environ,
            {"OBJECT_STORAGE_LOCAL_ROOT": str(Path(self.temp_dir.name) / "objects")},
            clear=False,
        ):
            return create_backend()

    def _make_job(self, **overrides):
        base = {"job_id": "job_test_001", "title": "Test Engineer", "company": "Test Corp", "portal": "greenhouse", "url": "", "location": "Remote"}
        base.update(overrides)
        return ApplicationPackageJob(**base)

    def _make_answer(self, **overrides):
        base = {"field_intent": "candidate.name", "label": "Name", "proposed_value": "Jane Doe", "source": "profile_verified", "sensitivity": "standard", "scope": "global", "confidence": 0.95, "requires_review": False, "reasons": []}
        base.update(overrides)
        return ApplicationPackageAnswer(**base)

    def _make_doc(self, **overrides):
        base = {"document_id": "doc_001", "document_kind": "cv", "asset_id": "asset_001", "object_key": "users/u1/cvs/cv.pdf", "mime_type": "application/pdf", "file_name": "cv.pdf", "sha256_hex": "", "document_version": 1}
        base.update(overrides)
        return ApplicationPackageDocumentRef(**base)

    # ---- Section completeness ----

    def test_package_contains_all_required_sections(self):
        """A package must have job, answers, documents, warnings, and policy."""
        package = new_application_package(
            user_id="user_1",
            job=self._make_job(),
            answers=[self._make_answer()],
            documents=[self._make_doc()],
            warnings=ApplicationPackageWarnings(items=["test"]),
            policy=ApplicationPackagePolicy(),
        )
        self.assertTrue(hasattr(package, "job"))
        self.assertTrue(hasattr(package, "answers"))
        self.assertTrue(hasattr(package, "documents"))
        self.assertTrue(hasattr(package, "warnings"))
        self.assertTrue(hasattr(package, "policy"))

    # ---- Ownership ----

    def test_package_belongs_to_one_user_and_job(self):
        """Package user_id and job_id are required."""
        app = self._create_app()
        service = app._assisted_apply_package_service
        uid = "user_owner_001"
        app.upsert_user({"user_id": uid, "email": "owner@t.com", "role": "admin", "is_active": True})
        package = service.create_package(
            user_id=uid,
            job={"job_id": "job_owner_001", "title": "Owner Job", "company": "Owner Co", "portal": "greenhouse"},
        )
        self.assertEqual(package.user_id, uid)
        self.assertEqual(package.job_id, "job_owner_001")

    def test_cross_user_access_is_rejected(self):
        """Another user cannot launch another's package."""
        app = self._create_app()
        service = app._assisted_apply_package_service
        owner_id = "user_owner"
        other_id = "user_other"
        app.upsert_user({"user_id": owner_id, "email": "o@t.com", "role": "admin", "is_active": True})
        app.upsert_user({"user_id": other_id, "email": "r@t.com", "role": "admin", "is_active": True})
        package = service.create_package(
            user_id=owner_id,
            job={"job_id": "j1", "title": "Job", "company": "Co", "portal": "greenhouse"},
        )
        with self.assertRaises(PermissionError):
            service.launch_package(user_id=other_id, package_id=package.package_id)

    # ---- Package expiry ----

    def test_expired_binding_cannot_be_used(self):
        """A package with expired binding rejects bind attempt."""
        app = self._create_app()
        service = app._assisted_apply_package_service
        clock = MutableClock()
        service.now_provider = clock
        uid = "user_exp"
        app.upsert_user({"user_id": uid, "email": "exp@t.com", "role": "admin", "is_active": True})
        package = service.create_package(
            user_id=uid,
            job={"job_id": "j_exp", "title": "Expired", "company": "EC", "portal": "greenhouse"},
        )
        launched = service.launch_package(user_id=uid, package_id=package.package_id)
        clock.advance(seconds=APPLICATION_PACKAGE_BINDING_TTL_SECONDS + 60)
        with self.assertRaises(ApplicationPackageStateError):
            service.bind_package(binding_id=launched.launch_tab_binding_id, extension_origin=EXTENSION_ORIGIN)

    # ---- Immutability ----

    def test_frozen_answers_cannot_be_replaced(self):
        """Individual answer fields on frozen dataclass cannot be replaced."""
        answer = self._make_answer()
        with self.assertRaises(AttributeError):
            answer.proposed_value = "hacked"

    # ---- Stale/replayed binding ----

    def test_nonexistent_binding_id_is_rejected(self):
        """A non-existent binding ID is rejected."""
        app = self._create_app()
        service = app._assisted_apply_package_service
        with self.assertRaises(PermissionError):
            service.bind_package(binding_id="fake", extension_origin=EXTENSION_ORIGIN)

    def test_binding_is_idempotent(self):
        """Binding the same package twice succeeds (idempotent)."""
        app = self._create_app()
        service = app._assisted_apply_package_service
        clock = MutableClock()
        service.now_provider = clock
        uid = "user_idem"
        app.upsert_user({"user_id": uid, "email": "idem@t.com", "role": "admin", "is_active": True})
        package = service.create_package(
            user_id=uid, job={"job_id": "j_idem", "title": "Idem", "company": "IC", "portal": "greenhouse"},
        )
        launched = service.launch_package(user_id=uid, package_id=package.package_id)
        bound = service.bind_package(binding_id=launched.launch_tab_binding_id, extension_origin=EXTENSION_ORIGIN)
        self.assertEqual(bound.status, APPLICATION_PACKAGE_STATUS_BOUND)
        rebound = service.bind_package(binding_id=launched.launch_tab_binding_id, extension_origin=EXTENSION_ORIGIN)
        self.assertEqual(rebound.status, APPLICATION_PACKAGE_STATUS_BOUND)

    def test_extension_retrieval_requires_bound_package(self):
        """The extension can retrieve a package only after the launch binding succeeds."""
        app = self._create_app()
        service = app._assisted_apply_package_service
        uid = "user_extension_retrieval"
        app.upsert_user({"user_id": uid, "email": "retrieve@t.com", "role": "admin", "is_active": True})
        package = service.create_package(
            user_id=uid,
            job={"job_id": "j_retrieve", "title": "Retrieve", "company": "RC", "portal": "greenhouse"},
        )
        with patch.object(
            type(service._connection_service),
            "authenticate_session",
            return_value=(SimpleNamespace(user_id=uid), None),
        ):
            with self.assertRaises(ApplicationPackageStateError):
                service.get_package_for_extension(
                    package_id=package.package_id,
                    raw_session="session-token",
                    extension_origin=EXTENSION_ORIGIN,
                )

            launched = service.launch_package(user_id=uid, package_id=package.package_id)
            with self.assertRaises(ApplicationPackageStateError):
                service.get_package_for_extension(
                    package_id=launched.package_id,
                    raw_session="session-token",
                    extension_origin=EXTENSION_ORIGIN,
                )

            service.bind_package(binding_id=launched.launch_tab_binding_id, extension_origin=EXTENSION_ORIGIN)
            payload = service.get_package_for_extension(
                package_id=package.package_id,
                raw_session="session-token",
                extension_origin=EXTENSION_ORIGIN,
            )
        self.assertEqual(payload["packageId"], package.package_id)

    # ---- Fixed document versions ----

    def test_document_version_is_fixed_and_immutable(self):
        """Documents reference fixed, immutable version numbers."""
        doc = self._make_doc(document_version=3)
        self.assertEqual(doc.document_version, 3)
        package = new_application_package(
            user_id="u1", job=self._make_job(), answers=[self._make_answer()], documents=[doc],
        )
        self.assertEqual(package.documents[0].document_version, 3)

    # ---- Data-only responses ----

    def test_extension_payload_is_data_only(self):
        """Extension payload survives JSON round-trip, no executable code."""
        package = new_application_package(
            user_id="u1", job=self._make_job(), answers=[self._make_answer()],
            documents=[self._make_doc()],
        )
        payload = package.to_extension_payload()
        parsed = json.loads(json.dumps(payload))
        self.assertEqual(parsed, payload)
        self.assertIsInstance(parsed["packageId"], str)
        self.assertIsInstance(parsed["answers"], list)
        self.assertIsInstance(parsed["documents"], list)

    # ---- Schema compatibility fixtures ----

    def test_package_schema_fixtures_are_valid(self):
        """Shared JSON fixtures can be parsed by Python and match counts."""
        from pathlib import Path as _Path
        _fixtures_path = _Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "package_schema_fixtures.json"
        self.assertTrue(_fixtures_path.exists(), f"Fixtures missing at {_fixtures_path}")
        with open(_fixtures_path) as f:
            fixtures = json.load(f)
        self.assertGreater(len(fixtures), 0)
        for item in fixtures:
            with self.subTest(fixture_id=item["id"]):
                package = ApplicationPackage.from_payload(item["python_package"])
                self.assertIsNotNone(package)
                self.assertEqual(len(package.answers), item["expected_answer_count"])
                self.assertEqual(len(package.documents), item["expected_document_count"])

    # ---- Side panel display ----

    def test_extension_payload_has_display_fields(self):
        """Payload includes company, title, portal, version, warnings."""
        package = new_application_package(
            user_id="u1",
            job=self._make_job(company="Display Corp", title="Display Role", portal="greenhouse"),
            answers=[self._make_answer()],
            documents=[self._make_doc()],
            warnings=ApplicationPackageWarnings(items=["test warn"]),
        )
        payload = package.to_extension_payload()
        self.assertEqual(payload["job"]["company"], "Display Corp")
        self.assertEqual(payload["job"]["title"], "Display Role")
        self.assertEqual(payload["job"]["portal"], "greenhouse")
        self.assertEqual(payload["version"], 1)
        self.assertIsInstance(payload["warnings"], list)
        self.assertGreater(len(payload["warnings"]), 0)
        self.assertIn("policy", payload)
        self.assertIn("permitSensitiveAutofill", payload["policy"])

    # ---- Binding secrets not in extension payload ----

    def test_binding_id_not_exposed_in_payload(self):
        """Binding ID must NOT appear in extension payload."""
        clock = MutableClock()
        package = new_application_package(
            user_id="u1", job=self._make_job(), answers=[self._make_answer()], documents=[],
        )
        launched = ApplicationPackage.from_payload({
            **package.to_dict(),
            "status": APPLICATION_PACKAGE_STATUS_LAUNCHED,
            "launch_tab_binding_id": "secret_bind_xyz",
            "launch_tab_binding_expires_at": (clock() + timedelta(minutes=5)).isoformat(),
            "launched_at": clock().isoformat(),
            "updated_at": clock().isoformat(),
        })
        ext = launched.to_extension_payload()
        self.assertNotIn("launchTabBindingId", ext)
        self.assertNotIn("bindingId", ext)
        serialized = json.dumps(ext)
        self.assertNotIn("secret_bind", serialized)


if __name__ == "__main__":
    unittest.main()
