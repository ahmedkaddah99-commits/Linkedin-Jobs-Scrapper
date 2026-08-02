"""AA launch preparation: server-derived web packages for Review & Apply."""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import create_backend
from backend.api.routes.assisted_apply_packages import _prepare_package, _supported_portal
from backend.domain.models import JobRecord


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

    def test_refuses_document_identifiers_outside_the_candidate_library(self):
        with self.assertRaisesRegex(ValueError, "Runr document library"):
            self._prepare(
                {
                    "run_id": self.run.id,
                    "job_id": "greenhouse_job_1",
                    "document_ids": ["artifact::other-run::document"],
                    "confirm_standard_profile": True,
                }
            )

    def test_accepts_only_https_hosts_covered_by_extension_permissions(self):
        self.assertEqual(_supported_portal("https://boards.greenhouse.io/acme/jobs/123", "greenhouse"), "greenhouse")
        self.assertEqual(_supported_portal("https://jobs.lever.co/acme/123", "lever"), "lever")
        self.assertEqual(_supported_portal("https://hiring.lever.co/acme/123", "lever"), "lever")
        self.assertEqual(_supported_portal("https://jobs.greenhouse.io/acme/123", "greenhouse"), "")
        self.assertEqual(_supported_portal("http://boards.greenhouse.io/acme/jobs/123", "greenhouse"), "")
        self.assertEqual(_supported_portal("https://example.com/acme/123", "greenhouse"), "")


if __name__ == "__main__":
    unittest.main()
