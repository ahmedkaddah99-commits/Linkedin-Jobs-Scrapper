"""AA launch preparation: server-derived web packages for Review & Apply."""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import create_backend
from backend.api.routes.assisted_apply_packages import (
    _canonical_application_form_url,
    _phone_from_source_text,
    _prepare_package,
    _supported_portal,
)
from backend.domain.models import (
    ArtifactRecord,
    CAREER_PROFILE_STATUS_READY_FOR_TAILORING,
    CareerProfile,
    JobRecord,
)


PDF_BYTES = b"%PDF-1.4\n% Runr launch package fixture\n%%EOF\n"


class _Context:
    def __init__(self, application, user, payload):
        self.application = application
        self._user = user
        self._payload = payload
        self.response = None

    def require_clerk_identity(self):
        return self._user, None

    def read_json_body(self):
        return dict(self._payload)

    def send_json(self, payload, status=200, **_kwargs):
        self.response = (status, payload)


class AssistedApplyLaunchPrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="runr-aa-launch-")
        self.addCleanup(self.temp_dir.cleanup)
        self.environment = patch.dict(
            os.environ,
            {
                "DATABASE_BACKEND": "sqlite",
                "RUNR_ENV": "test",
                "TURSO_DATABASE_URL": "",
                "TURSO_AUTH_TOKEN": "",
                "OBJECT_STORAGE_BACKEND": "local",
                "OBJECT_STORAGE_LOCAL_ROOT": str(Path(self.temp_dir.name) / "objects"),
                "RUNR_INTERNAL_OBJECT_STORAGE_LOCAL_ROOT": "",
            },
            clear=False,
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.app = create_backend(Path(self.temp_dir.name), storage_backend="sqlite")
        self.user = self.app.upsert_user(
            {
                "email": "launch@example.com",
                "display_name": "Ada Lovelace",
                "role": "admin",
                "metadata": {
                    "profile": {"name": "Ada Lovelace", "email": "ada@example.com", "phone": "+491234"},
                    "candidate_assets": [
                        {
                            "asset_id": "asset_cv_1",
                            "asset_kind": "workspace_cv",
                            "display_name": "Ada CV.pdf",
                            "object_key": "users/launch/workspace_cv/asset_cv_1/Ada CV.pdf",
                            "mime_type": "application/pdf",
                            "metadata": {"content_sha256": hashlib.sha256(PDF_BYTES).hexdigest()},
                        }
                    ],
                },
            }
        )
        self.app.object_storage.put(
            "users/launch/workspace_cv/asset_cv_1/Ada CV.pdf",
            PDF_BYTES,
            content_type="application/pdf",
        )
        self.app.upsert_workspace(
            {
                "id": "aa_launch_workspace",
                "name": "Assisted Apply Test Workspace",
                "workflow_template_id": "search_apply_v1",
                "workspace_type": "custom",
                "sources": [],
                "owner_user_id": self.user.user_id,
            }
        )
        self.run = self.app.start_run(
            "aa_launch_workspace",
            execute=False,
            requested_by="test",
            user_id=self.user.user_id,
        )
        self.app.upsert_job_set(
            self.run.id,
            "accepted_jobs",
            [
                JobRecord(
                    job_id="greenhouse_job_1",
                    title="Engineer",
                    company="Acme",
                    portal="greenhouse",
                    apply_link="https://boards.greenhouse.io/acme/jobs/123",
                    location_raw="Berlin",
                )
            ],
        )

    def _prepare(self, payload):
        context = _Context(self.app, self.user, payload)
        _prepare_package(context)
        self.assertIsNotNone(context.response)
        return context.response

    def _install_ready_career_memory(self):
        metadata = dict(self.user.metadata or {})
        assets = list(metadata.get("candidate_assets") or [])
        assets[0] = {
            **assets[0],
            "metadata": {
                **dict(assets[0].get("metadata") or {}),
                "parsed_profile": {
                    "name": "Ada Lovelace",
                    "email": "ada@example.com",
                    "location": "Berlin, Germany",
                    "linkedin_url": "https://www.linkedin.com/in/ada",
                    "github_url": "https://github.com/ada",
                    "website": "https://ada.example",
                    "summary": "Builds reliable systems.",
                    "competencies": ["Python", "Distributed systems"],
                    "languages": ["English", "German"],
                    "education": [
                        {"institution": "Example University", "degree_title": "BSc Computer Science", "period": "2018 - 2021"},
                    ],
                },
            },
        }
        metadata["candidate_assets"] = assets
        self.user = self.app.upsert_user({
            "user_id": self.user.user_id,
            "email": self.user.email,
            "display_name": self.user.display_name,
            "role": self.user.role,
            "metadata": metadata,
        })
        career_profile = CareerProfile.create(user_id=self.user.user_id, name="Primary Career Memory")
        career_profile.status = CAREER_PROFILE_STATUS_READY_FOR_TAILORING
        career_profile.metadata = {
            "source_asset_ids": ["asset_cv_1"],
            "work_experiences": [
                {
                    "experience_id": "exp_current",
                    "employer": "Analytical Engines",
                    "job_title": "Software Engineer",
                    "location": "Berlin",
                    "start_date": "2024-01",
                    "end_date": "",
                    "description": "Built deterministic application systems.",
                    "status": "active",
                }
            ],
        }
        self.app.repositories.career_profile_store.upsert_profile(career_profile)

    def test_prepares_owned_job_with_confirmed_profile_and_owned_document(self):
        status, response = self._prepare(
            {
                "run_id": self.run.id,
                "job_id": "greenhouse_job_1",
                "document_ids": ["asset::asset_cv_1"],
                "confirm_standard_profile": True,
            }
        )
        self.assertEqual(status, 201)
        self.assertEqual(response["portal"], "greenhouse")
        self.assertEqual(response["application_url"], "https://boards.greenhouse.io/acme/jobs/123")
        package = self.app._assisted_apply_package_service._store.get(response["package_id"])
        self.assertIsNotNone(package)
        self.assertEqual(package.job.job_id, "greenhouse_job_1")
        self.assertEqual(
            package.to_extension_payload()["job"]["url"],
            "https://boards.greenhouse.io/acme/jobs/123",
        )
        self.assertEqual([document.asset_id for document in package.documents], ["asset_cv_1"])
        self.assertEqual([answer.field_intent for answer in package.answers], [
            "candidate.first_name", "candidate.last_name", "candidate.full_name", "candidate.email", "candidate.phone",
        ])
        self.assertTrue(all(answer.source == "profile_verified" for answer in package.answers))
        self.assertTrue(all(not answer.requires_review for answer in package.answers))

    def test_requires_explicit_standard_profile_confirmation(self):
        with self.assertRaisesRegex(ValueError, "Confirm your standard profile facts"):
            self._prepare(
                {
                    "run_id": self.run.id,
                    "job_id": "greenhouse_job_1",
                    "document_ids": [],
                    "confirm_standard_profile": False,
                }
            )

    def test_ready_career_memory_populates_immutable_package_sections_and_standard_answers(self):
        self._install_ready_career_memory()
        _, response = self._prepare(
            {
                "run_id": self.run.id,
                "job_id": "greenhouse_job_1",
                "document_ids": [],
                "confirm_standard_profile": True,
            }
        )
        package = self.app._assisted_apply_package_service._store.get(response["package_id"])
        answers = {answer.field_intent: answer.proposed_value for answer in package.answers}
        self.assertEqual(answers["candidate.location"], "Berlin, Germany")
        self.assertEqual(answers["candidate.current_company"], "Analytical Engines")
        self.assertEqual(answers["candidate.current_title"], "Software Engineer")
        self.assertEqual(answers["candidate.github_url"], "https://github.com/ada")
        self.assertEqual(answers["candidate.website"], "https://ada.example")
        self.assertEqual(package.candidate.provenance, f"career_profile:{package.experiences[0].generation_provenance['profile_id']}")
        self.assertEqual(package.experiences[0].source_experience_id, "exp_current")
        self.assertEqual(package.experiences[0].bullets[0].approved_text, "Built deterministic application systems.")
        self.assertEqual(package.education[0].institution, "Example University")
        self.assertEqual([fact.value for fact in package.skills], ["Python", "Distributed systems"])
        self.assertEqual([fact.value for fact in package.languages], ["English", "German"])
        extension_payload = package.to_extension_payload()
        self.assertEqual(extension_payload["candidate"]["fullName"], "Ada Lovelace")
        self.assertEqual(extension_payload["experiences"][0]["sourceExperienceId"], "exp_current")
        self.assertEqual(extension_payload["education"][0]["institution"], "Example University")
        self.assertEqual([item["value"] for item in extension_payload["skills"]], ["Python", "Distributed systems"])

    def test_recovers_only_a_bounded_international_phone_from_cv_source_text(self):
        self.assertEqual(_phone_from_source_text("Phone: +49 176 12345678\nBerlin"), "+49 176 12345678")
        self.assertEqual(_phone_from_source_text("Employment: 2021-01 - 2024-08"), "")

    def test_accepts_ready_legacy_workspace_docx_stored_as_octet_stream(self):
        docx_bytes = b"PK\x03\x04Runr DOCX fixture"
        object_key = "users/launch/workspace_cv/asset_cv_docx/Ada CV.docx"
        metadata = dict(self.user.metadata or {})
        metadata["candidate_assets"] = [
            {
                "asset_id": "asset_cv_docx",
                "asset_kind": "workspace_cv",
                "display_name": "Ada CV.docx",
                "object_key": object_key,
                "mime_type": "application/octet-stream",
                "metadata": {
                    "status": "ready",
                    "content_sha256": hashlib.sha256(docx_bytes).hexdigest(),
                },
            }
        ]
        self.user = self.app.upsert_user({
            "user_id": self.user.user_id,
            "email": self.user.email,
            "display_name": self.user.display_name,
            "role": self.user.role,
            "metadata": metadata,
        })
        self.app.object_storage.put(object_key, docx_bytes, content_type="application/octet-stream")
        _, response = self._prepare(
            {
                "run_id": self.run.id,
                "job_id": "greenhouse_job_1",
                "document_ids": ["asset::asset_cv_docx"],
                "confirm_standard_profile": True,
            }
        )
        package = self.app._assisted_apply_package_service._store.get(response["package_id"])
        self.assertEqual(package.documents[0].mime_type, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        self.assertEqual(package.documents[0].file_name, "Ada CV.docx")

    def test_refuses_document_identifiers_outside_the_candidate_library(self):
        with self.assertRaisesRegex(PermissionError, "associated with this application run"):
            self._prepare(
                {
                    "run_id": self.run.id,
                    "job_id": "greenhouse_job_1",
                    "document_ids": ["artifact::other-run::document"],
                    "confirm_standard_profile": True,
                }
            )

    def test_accepts_only_owned_exact_job_role_artifacts(self):
        tailored_bytes = b"%PDF-1.4\n% tailored role CV\n%%EOF\n"
        object_key = f"runs/{self.run.id}/greenhouse_job_1/tailored-cv.pdf"
        self.app.object_storage.put(object_key, tailored_bytes, content_type="application/pdf")
        self.app.upsert_artifact(
            self.run.id,
            ArtifactRecord(
                artifact_id="greenhouse_job_1_cv_pdf",
                artifact_type="cv_pdf",
                path="tailored-cv.pdf",
                metadata={
                    "job_id": "greenhouse_job_1",
                    "document_asset_kind": "generated_cv",
                    "document_name": "Tailored CV.pdf",
                    "object_key": object_key,
                    "object_content_type": "application/pdf",
                    "content_sha256": hashlib.sha256(tailored_bytes).hexdigest(),
                },
            ),
        )
        _, response = self._prepare({
            "run_id": self.run.id,
            "job_id": "greenhouse_job_1",
            "document_ids": [f"artifact::{self.run.id}::greenhouse_job_1_cv_pdf"],
            "confirm_standard_profile": True,
        })
        package = self.app._assisted_apply_package_service._store.get(response["package_id"])
        self.assertEqual(package.documents[0].document_kind, "cv")
        self.assertEqual(package.documents[0].file_name, "Tailored CV.pdf")
        self.assertEqual(package.documents[0].object_key, object_key)

        artifact = self.app.get_artifact(self.run.id, "greenhouse_job_1_cv_pdf")
        artifact.metadata["job_id"] = "another-job"
        self.app.upsert_artifact(self.run.id, artifact)
        with self.assertRaisesRegex(PermissionError, "associated with this job"):
            self._prepare({
                "run_id": self.run.id,
                "job_id": "greenhouse_job_1",
                "document_ids": [f"artifact::{self.run.id}::greenhouse_job_1_cv_pdf"],
                "confirm_standard_profile": True,
            })

    def test_accepts_only_https_hosts_covered_by_extension_permissions(self):
        self.assertEqual(_supported_portal("https://boards.greenhouse.io/acme/jobs/123", "greenhouse"), "greenhouse")
        self.assertEqual(_supported_portal("https://jobs.lever.co/acme/123", "lever"), "lever")
        self.assertEqual(_supported_portal("https://hiring.lever.co/acme/123", "lever"), "lever")
        self.assertEqual(_supported_portal("https://jobs.greenhouse.io/acme/123", "greenhouse"), "")
        self.assertEqual(_supported_portal("http://boards.greenhouse.io/acme/jobs/123", "greenhouse"), "")
        self.assertEqual(_supported_portal("https://example.com/acme/123", "greenhouse"), "")

    def test_freezes_the_deterministic_lever_application_form_url(self):
        self.assertEqual(
            _canonical_application_form_url("https://jobs.lever.co/acme/123", "lever"),
            "https://jobs.lever.co/acme/123/apply",
        )
        self.assertEqual(
            _canonical_application_form_url("https://jobs.lever.co/acme/123/apply?source=runr#form", "lever"),
            "https://jobs.lever.co/acme/123/apply?source=runr",
        )
        self.assertEqual(
            _canonical_application_form_url("https://boards.greenhouse.io/acme/jobs/123", "greenhouse"),
            "https://boards.greenhouse.io/acme/jobs/123",
        )


if __name__ == "__main__":
    unittest.main()
