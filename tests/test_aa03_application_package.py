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
    ApplicationPackageBullet,
    ApplicationPackageCandidate,
    ApplicationPackageDocumentRef,
    ApplicationPackageEducation,
    ApplicationPackageExperience,
    ApplicationPackageFact,
    ApplicationPackageJob,
    ApplicationPackageMutationError,
    ApplicationPackagePolicy,
    ApplicationPackageWarnings,
    new_application_package,
    resolve_approved_value,
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
            return create_backend(Path(self.temp_dir.name), storage_backend="sqlite", test_mode=True)

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

    def test_extension_post_lookup_binds_launched_package(self):
        """The authenticated extension POST completes the launch/bind handshake."""
        app = self._create_app()
        service = app._assisted_apply_package_service
        uid = "user_extension_bind"
        app.upsert_user({"user_id": uid, "email": "bind@t.com", "role": "admin", "is_active": True})
        package = service.create_package(
            user_id=uid,
            job={"job_id": "j_bind", "title": "Bind", "company": "BC", "portal": "lever"},
        )

        with patch.object(
            type(service._connection_service),
            "authenticate_session",
            return_value=(SimpleNamespace(user_id=uid), None),
        ):
            launched = service.launch_package(user_id=uid, package_id=package.package_id)
            payload = service.get_or_bind_package_for_extension(
                package_id=launched.package_id,
                raw_session="session-token",
                extension_origin=EXTENSION_ORIGIN,
            )
            rebound_payload = service.get_or_bind_package_for_extension(
                package_id=launched.package_id,
                raw_session="session-token",
                extension_origin=EXTENSION_ORIGIN,
            )

        self.assertEqual(payload["packageId"], package.package_id)
        self.assertEqual(rebound_payload["packageId"], package.package_id)
        self.assertEqual(service._store.get(package.package_id).status, APPLICATION_PACKAGE_STATUS_BOUND)

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
        self.assertEqual(payload["job"]["url"], package.job.url)
        self.assertEqual(payload["version"], 1)
        self.assertIsInstance(payload["warnings"], list)
        self.assertGreater(len(payload["warnings"]), 0)
        self.assertIn("policy", payload)
        self.assertIn("permitSensitiveAutofill", payload["policy"])

    def test_aa212_package_content_round_trips_with_hashes_and_provenance(self):
        approved_text = "Approved role-specific bullet — unchanged."
        package = new_application_package(
            user_id="u1", job=self._make_job(), answers=[self._make_answer()], documents=[self._make_doc()],
            candidate=ApplicationPackageCandidate(email="candidate@example.com", approved=True, provenance="career_memory"),
            experiences=[ApplicationPackageExperience(
                source_experience_id="exp_1", role_title="Engineer", company="Test Corp",
                bullets=[ApplicationPackageBullet(
                    bullet_id="exp_1:bullet:1", text=approved_text, approved_text=approved_text,
                    source_experience_id="exp_1", provenance_id="prov_1",
                )], selected_cv_version={"version_id": "cvv_2", "version_no": 2},
                generation_provenance={"provenance_id": "prov_1"},
            )],
            education=[ApplicationPackageEducation(institution="Example University", degree="MSc")],
            skills=[ApplicationPackageFact(value="SQL", provenance="career_memory")],
            languages=[ApplicationPackageFact(value="English C1", provenance="career_memory")],
            standard_answers=[self._make_answer(approved=True)],
        )
        payload = package.to_dict()
        self.assertIn("content_hashes", payload)
        self.assertEqual(payload["experiences"][0]["bullets"][0]["approved_text"], approved_text)
        restored = ApplicationPackage.from_payload(json.loads(json.dumps(payload, ensure_ascii=False)))
        self.assertEqual(restored.content_hashes, package.content_hashes)
        self.assertEqual(restored.experiences[0].bullets[0].approved_text, approved_text)
        self.assertEqual(restored.experiences[0].source_experience_id, "exp_1")

    def test_aa212_approval_rejects_in_place_mutation_and_requires_new_version(self):
        package = new_application_package(user_id="u1", job=self._make_job(), answers=[self._make_answer()], documents=[])
        package.mark_approved("2026-08-01T12:00:00+00:00")
        with self.assertRaises(ApplicationPackageMutationError):
            package.replace_content(candidate=ApplicationPackageCandidate(email="changed@example.com", approved=True))
        revision = package.new_version(candidate=ApplicationPackageCandidate(email="changed@example.com", approved=True))
        self.assertEqual(revision.version, package.version + 1)
        self.assertEqual(revision.status, APPLICATION_PACKAGE_STATUS_CREATED)
        self.assertEqual(revision.approved_at, "")

    def test_aa212_direct_mutation_is_rejected_at_serialization_boundary(self):
        package = new_application_package(user_id="u1", job=self._make_job(), answers=[], documents=[])
        package.mark_approved("2026-08-01T12:00:00+00:00")
        with self.assertRaises(ApplicationPackageMutationError):
            package.candidate = ApplicationPackageCandidate(email="tampered@example.com", approved=True)
        package.experiences.append(ApplicationPackageExperience(role_title="Tampered", company="Unapproved"))
        with self.assertRaises(ApplicationPackageMutationError):
            package.to_dict()

    def test_aa212_precedence_is_approved_only_and_sensitive_is_review_gated(self):
        resolved = resolve_approved_value(
            {"value": "Job-specific", "approved": True, "provenance": "tailored"},
            {"value": "Selected CV", "approved": True, "provenance": "cv"},
            {"value": "Memory", "confirmed": True, "provenance": "memory"},
        )
        self.assertEqual((resolved.value, resolved.source), ("Job-specific", "job_specific"))
        self.assertEqual(resolve_approved_value({"value": "unapproved", "approved": False}, {"value": "", "approved": True}, None).source, "unresolved")
        sensitive = resolve_approved_value(None, {"value": "candidate@example.com", "approved": True}, None, sensitive=True)
        self.assertTrue(sensitive.requires_review)
        self.assertEqual(sensitive.value, "candidate@example.com")

    def test_aa212_sensitive_answer_cannot_clear_review_gate(self):
        answer = ApplicationPackageAnswer.from_payload({
            "field_intent": "candidate.email", "label": "Email", "proposed_value": "candidate@example.com",
            "source": "profile_verified", "sensitivity": "personal", "scope": "global", "confidence": 1,
            "requires_review": False, "approved": True,
        })
        self.assertTrue(answer.requires_review)

    def test_aa212_tampered_approved_text_or_hash_is_rejected(self):
        package = new_application_package(
            user_id="u1", job=self._make_job(), answers=[], documents=[],
            experiences=[ApplicationPackageExperience(
                role_title="Engineer", company="Test", source_experience_id="exp_1",
                bullets=[ApplicationPackageBullet(
                    text="Approved", approved_text="Approved", bullet_id="b1",
                )],
            )],
        )
        tampered_text = json.loads(json.dumps(package.to_dict()))
        tampered_text["experiences"][0]["bullets"][0]["approved_text"] = "Changed"
        with self.assertRaises(ValueError):
            ApplicationPackage.from_payload(tampered_text)
        tampered_hash = json.loads(json.dumps(package.to_dict()))
        tampered_hash["content_hashes"]["candidate"] = "0" * 64
        with self.assertRaises(ValueError):
            ApplicationPackage.from_payload(tampered_hash)

    def test_aa212_legacy_v1_payload_is_readable(self):
        package = ApplicationPackage.from_payload({
            "package_id": "aapkg_legacy", "user_id": "u1", "job_id": "j1", "version": 1,
            "status": "created", "schema_version": 1,
            "job": {"job_id": "j1", "title": "Engineer", "company": "Test", "portal": "greenhouse"},
            "answers": [], "documents": [],
            "experiences": [{"role_title": "Engineer", "company": "Test", "bullets": ["Legacy bullet"]}],
        })
        self.assertEqual(package.version, 1)
        self.assertEqual(package.experiences[0].source_experience_id, "")
        self.assertEqual(package.experiences[0].provenance_confidence, "reduced")
        self.assertEqual(package.experiences[0].bullets[0].text, "Legacy bullet")
        self.assertTrue(package.content_hashes)

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
