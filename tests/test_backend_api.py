import base64
import json
import os
import shutil
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from backend import create_backend
from backend.api.server import build_handler
from backend.capabilities.tracker.email_integration import TrackerMailboxMessage
from backend.domain.models import ArtifactRecord, JobRecord, StageDefinition
from backend.orchestration import BaseStage, StageOutcome


class _ApiSeedStage(BaseStage):
    def can_run(self, context, definition) -> bool:
        return True

    def execute(self, context, definition) -> StageOutcome:
        return StageOutcome(
            job_sets={
                definition.output_key or "accepted_jobs": [
                    JobRecord(job_id="api_job_1", title="Engineer", company="ACME API"),
                ]
            },
            artifacts=[
                ArtifactRecord(
                    artifact_id="api_artifact_1",
                    artifact_type="docx",
                    path="generated_docs/api_job_1.docx",
                    metadata={"job_id": "api_job_1"},
                )
            ],
        )


class _ApiDocumentStage(BaseStage):
    def can_run(self, context, definition) -> bool:
        return bool(definition.input_keys and context.get_job_set(definition.input_keys[0]))

    def execute(self, context, definition) -> StageOutcome:
        jobs = context.get_job_dicts(definition.input_keys[0])
        output_root = Path(definition.config.get("output_root") or str(Path(".backend_test_tmp") / context.run.id))
        output_root.mkdir(parents=True, exist_ok=True)
        artifacts = []
        records = []
        for job in jobs:
            file_path = output_root / f"{job['job_id']}_CV.docx"
            file_path.write_bytes(b"requeued-docx-content")
            artifacts.append(
                ArtifactRecord(
                    artifact_id=f"{job['job_id']}_generated_cv",
                    artifact_type="cv_docx",
                    path=str(file_path),
                    metadata={"job_id": job["job_id"], "job_title": job.get("title"), "company": job.get("company")},
                )
            )
            records.append(JobRecord.from_mapping(job))
        return StageOutcome(
            job_sets={definition.output_key or "generated_jobs": records},
            artifacts=artifacts,
            metrics={"generated_jobs": len(records)},
        )


class BackendApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path.cwd() / ".backend_test_tmp" / f"api_tests_{self._testMethodName}"
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))

        self.app = create_backend(self.temp_dir)
        self.app.registries.stage_registry.register("test.api_seed", _ApiSeedStage())
        self.app.registries.stage_registry.register("test.api_generate_documents", _ApiDocumentStage())
        self.app.upsert_workflow_template(
            {
                "id": "api_template_v1",
                "name": "API Template",
                "stages": [
                    StageDefinition(
                        stage_id="api_seed_stage",
                        stage_type="test.api_seed",
                        name="API Seed",
                        output_key="accepted_jobs",
                    ).to_dict()
                ],
            }
        )
        self.app.upsert_workspace(
            {
                "id": "api_workspace",
                "name": "API Workspace",
                "workflow_template_id": "api_template_v1",
                "workspace_type": "custom",
                "sources": [{"id": "manual_source", "connector_id": "curated_job_urls"}],
            }
        )
        self.user = self.app.upsert_user(
            {
                "email": "admin@example.com",
                "display_name": "Admin",
                "role": "admin",
            }
        )
        _, self.access_token = self.app.issue_api_token(user_id=self.user.user_id, name="api-test")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(self.app))
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def _request(self, method: str, path: str, payload=None, *, authenticated: bool = True):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        body = None
        headers = {}
        if payload is not None:
            body = json.dumps(payload)
            headers["Content-Type"] = "application/json"
        if authenticated:
            headers["Authorization"] = f"Bearer {self.access_token}"
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        raw = response.read().decode("utf-8")
        conn.close()
        return response.status, json.loads(raw) if raw else {}

    def _multipart_request(self, path: str, field_name: str, filename: str, file_bytes: bytes):
        boundary = "----runrtestboundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode("latin-1") + file_bytes + f"\r\n--{boundary}--\r\n".encode("latin-1")
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request(
            "POST",
            path,
            body=body,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        response = conn.getresponse()
        raw = response.read().decode("utf-8")
        conn.close()
        return response.status, json.loads(raw) if raw else {}

    def _binary_request(self, method: str, path: str, *, authenticated: bool = True):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.access_token}"
        conn.request(method, path, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        response_headers = dict(response.getheaders())
        conn.close()
        return response.status, response_headers, raw

    def test_api_requires_bearer_auth_for_protected_routes(self):
        status, payload = self._request("GET", "/workspaces", authenticated=False)
        self.assertEqual(status, 401)
        self.assertIn("error", payload)
        self.assertEqual(payload["error"]["code"], "unauthorized")

    def test_api_supports_run_queue_and_resource_endpoints(self):
        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "queued", "max_attempts": 2},
        )
        self.assertEqual(status, 201)
        self.assertEqual(run_payload["status"], "queued")
        run_id = run_payload["id"]

        status, worker_payload = self._request("POST", "/workers/process-next", {})
        self.assertEqual(status, 200)
        self.assertEqual(worker_payload["status"], "processed")
        self.assertEqual(worker_payload["run"]["status"], "completed")

        status, jobs_payload = self._request("GET", f"/runs/{run_id}/jobs")
        self.assertEqual(status, 200)
        self.assertIn("accepted_jobs", jobs_payload["job_sets"])

        status, artifact_payload = self._request(
            "PUT",
            f"/runs/{run_id}/artifacts/api_pdf_1",
            {"artifact_type": "pdf", "path": "generated_docs/api_job_1.pdf", "metadata": {"job_id": "api_job_1"}},
        )
        self.assertEqual(status, 200)
        self.assertEqual(artifact_payload["artifact_id"], "api_pdf_1")

        status, review_payload = self._request(
            "POST",
            f"/runs/{run_id}/reviews",
            {"job_id": "api_job_1", "decision": "approved", "reviewer": "api_tester", "status": "approved"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(review_payload["decision"], "approved")

        status, reviews_payload = self._request("GET", f"/runs/{run_id}/reviews")
        self.assertEqual(status, 200)
        self.assertEqual(len(reviews_payload["reviews"]), 1)

    def test_api_supports_deleting_queued_run(self):
        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "queued", "max_attempts": 1},
        )
        self.assertEqual(status, 201)

        status, delete_payload = self._request("DELETE", f"/runs/{run_payload['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(delete_payload["deleted"], run_payload["id"])

        status, missing_payload = self._request("GET", f"/runs/{run_payload['id']}")
        self.assertEqual(status, 404)
        self.assertEqual(missing_payload["error"]["code"], "not_found")

    def test_api_supports_workspace_and_template_crud(self):
        status, template_payload = self._request(
            "POST",
            "/workflow-templates",
            {"id": "api_custom_template", "name": "API Custom Template", "stages": []},
        )
        self.assertEqual(status, 201)
        self.assertEqual(template_payload["id"], "api_custom_template")

        status, workspace_payload = self._request(
            "POST",
            "/workspaces",
            {
                "id": "api_custom_workspace",
                "name": "API Custom Workspace",
                "workflow_template_id": "api_custom_template",
                "workspace_type": "custom",
                "sources": [],
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(workspace_payload["id"], "api_custom_workspace")

        status, _ = self._request("DELETE", "/workspaces/api_custom_workspace")
        self.assertEqual(status, 200)
        status, _ = self._request("DELETE", "/workflow-templates/api_custom_template")
        self.assertEqual(status, 200)

    def test_api_supports_workspace_builder_catalog_and_create(self):
        status, catalog_payload = self._request("GET", "/workspace-builder/catalog")
        self.assertEqual(status, 200)
        self.assertTrue(catalog_payload["flows"])
        self.assertTrue(catalog_payload["sources"])
        self.assertTrue(catalog_payload["modules"])
        self.assertTrue(catalog_payload["configuration_fields"])
        self.assertIn("builder_sections", catalog_payload)
        user_facing_fields = {
            field["id"]: field for field in catalog_payload["configuration_fields"] if field.get("user_facing")
        }
        self.assertIn("workspace_cv_asset_id", user_facing_fields)
        self.assertIn("country_codes", user_facing_fields)
        self.assertNotIn("geo_id", user_facing_fields)
        self.assertNotIn("candidate_name", user_facing_fields)
        self.assertTrue(
            any(not flow.get("frontend_visible", True) for flow in catalog_payload["flows"] if flow["id"] == "reusable_packages")
        )

        status, workspace_payload = self._request(
            "POST",
            "/workspace-builder/workspaces",
            {
                "name": "Builder Workspace",
                "flow_id": "tailored_documents",
                "source_ids": ["linkedin_jobs"],
                "module_ids": ["screening_filter", "priority_ranking", "tailored_document_generation"],
                "settings": {
                    "keywords": ["analyst"],
                    "geo_id": "101282230",
                    "time_posted_seconds": 86400,
                    "experience_levels": [2, 3],
                    "target_roles": ["Business Analyst", "Consultant"],
                },
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(workspace_payload["workspace_type"], "custom")
        self.assertEqual(workspace_payload["metadata"]["automation_flow"], "tailored_documents")
        self.assertEqual(workspace_payload["settings"]["keywords"], ["analyst"])
        self.assertEqual(workspace_payload["settings"]["experience_levels"], [2, 3])
        self.assertEqual(workspace_payload["settings"]["target_roles"], ["Business Analyst", "Consultant"])

        status, updated_workspace_payload = self._request(
            "PUT",
            f"/workspace-builder/workspaces/{workspace_payload['id']}",
            {
                "name": "Builder Workspace Updated",
                "description": "Updated through API",
                "flow_id": "tailored_documents",
                "source_ids": ["linkedin_jobs", "curated_job_urls"],
                "module_ids": ["screening_filter", "priority_ranking", "tailored_document_generation"],
                "settings": {
                    "keywords": ["designer"],
                    "stage4_max_jobs": 8,
                    "low_applicant_threshold": 55,
                },
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated_workspace_payload["id"], workspace_payload["id"])
        self.assertEqual(updated_workspace_payload["name"], "Builder Workspace Updated")
        self.assertEqual(updated_workspace_payload["description"], "Updated through API")
        self.assertEqual(updated_workspace_payload["settings"]["keywords"], ["designer"])
        self.assertEqual(updated_workspace_payload["metadata"]["source_ids"], ["linkedin_jobs", "curated_job_urls"])

    def test_workspace_builder_source_validation_returns_runtime_hints(self):
        status, payload = self._request(
            "POST",
            "/workspace-builder/source-validation",
            {
                "flow_id": "tailored_documents",
                "source_ids": ["linkedin_jobs", "job_board_collection", "curated_job_urls"],
                "settings": {
                    "keywords": ["analyst"],
                    "country_codes": ["DE"],
                    "manual_url_seed_list": ["https://company.example/jobs/123"],
                    "portals": ["indeed", "stepstone"],
                },
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["derived_runtime_defaults"]["geo_id"], "101282230")
        self.assertIn("cities", payload["derived_runtime_defaults"])
        source_status = {item["source_id"]: item["status"] for item in payload["source_results"]}
        self.assertEqual(source_status["linkedin_jobs"], "valid")
        self.assertEqual(source_status["job_board_collection"], "valid")

    def test_workspace_builder_source_validation_supplies_default_multi_portals(self):
        status, payload = self._request(
            "POST",
            "/workspace-builder/source-validation",
            {
                "flow_id": "tailored_documents",
                "source_ids": ["job_board_collection"],
                "settings": {
                    "keywords": ["analyst"],
                    "country_codes": ["DE"],
                },
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["valid"])
        self.assertTrue(payload["derived_runtime_defaults"]["portals"])
        self.assertIn("cities", payload["derived_runtime_defaults"])

    def test_settings_payload_includes_document_design_options_and_persists_phase2_preferences(self):
        status, settings_payload = self._request("GET", "/settings")
        self.assertEqual(status, 200)
        self.assertTrue(settings_payload["options"]["cv_templates"])
        self.assertTrue(settings_payload["options"]["cv_color_schemes"])
        self.assertTrue(settings_payload["options"]["cv_fonts"])

        status, updated_payload = self._request(
            "PUT",
            "/settings",
            {
                "profile": {
                    "name": "Admin Tester",
                    "languages": ["English - C1", "German - B1/B2"],
                },
                "documents": {
                    "cv_template": "modern",
                    "cv_color_scheme": "ocean_teal",
                    "cv_font": "Georgia",
                    "include_photo": False,
                },
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated_payload["documents"]["cv_template"], "modern")
        self.assertEqual(updated_payload["documents"]["cv_color_scheme"], "ocean_teal")
        self.assertEqual(updated_payload["documents"]["cv_font"], "Georgia")
        self.assertFalse(updated_payload["documents"]["include_photo"])
        self.assertEqual(updated_payload["profile"]["languages"], ["English - C1", "German - B1/B2"])

    def test_profile_photo_upload_endpoint_persists_preview_data(self):
        tiny_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9sXl16AAAAAASUVORK5CYII="
        )
        status, photo_payload = self._multipart_request(
            "/profile-photo-upload",
            "photo_file",
            "profile.png",
            tiny_png,
        )
        self.assertEqual(status, 201)
        self.assertTrue(photo_payload["photo_path"].endswith(".png"))
        self.assertTrue(photo_payload["photo_data_url"].startswith("data:image/png;base64,"))

        status, settings_payload = self._request("GET", "/settings")
        self.assertEqual(status, 200)
        self.assertTrue(settings_payload["profile"]["photo_data_url"].startswith("data:image/png;base64,"))

    def test_documents_endpoint_bulk_export_and_candidate_assets(self):
        status, cv_payload = self._multipart_request(
            "/cv-upload",
            "cv_file",
            "resume.txt",
            b"Summary\nExperienced analyst with operations background.",
        )
        self.assertEqual(status, 201)
        self.assertEqual(cv_payload["asset"]["asset_kind"], "workspace_cv")

        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "sync", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        run_id = run_payload["id"]

        docs_dir = self.temp_dir / "generated_docs" / "2026-04-20" / "api_docs_bundle"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "api_job_1_CV.docx").write_bytes(b"docx-content")
        (docs_dir / "api_job_1_cover_letter.txt").write_text("Cover letter", encoding="utf-8")

        status, _ = self._request(
            "PUT",
            f"/runs/{run_id}/artifacts/api_docs_dir",
            {
                "artifact_type": "stage5_docs_dir",
                "path": str(docs_dir),
                "metadata": {"status": "ready", "ats_score": 92, "ats_attempt_count": 1},
            },
        )
        self.assertEqual(status, 200)

        status, documents_payload = self._request("GET", f"/documents?run_id={run_id}")
        self.assertEqual(status, 200)
        document_ids = {item["document_id"]: item for item in documents_payload["documents"]}
        generated_cv = next(
            (item for item in documents_payload["documents"] if item["asset_kind"] == "generated_cv"),
            None,
        )
        self.assertIsNotNone(generated_cv)
        self.assertEqual(generated_cv["job_id"], "api_job_1")
        self.assertEqual(generated_cv["related_application"]["job_id"], "api_job_1")
        self.assertEqual(generated_cv["related_application"]["title"], "Engineer")
        self.assertEqual(generated_cv["status"], "ready")
        self.assertEqual(generated_cv["display_status"], "ready")
        application_group = next(
            (group for group in documents_payload["groups"] if group["group_kind"] == "application"),
            None,
        )
        self.assertIsNotNone(application_group)
        self.assertEqual(application_group["job_id"], "api_job_1")
        self.assertGreaterEqual(application_group["count"], 1)

        status, uploaded_payload = self._request("GET", "/documents?asset_kind=workspace_cv")
        self.assertEqual(status, 200)
        uploaded_cv = next(
            (item for item in uploaded_payload["documents"] if item["asset_kind"] == "workspace_cv"),
            None,
        )
        self.assertIsNotNone(uploaded_cv)

        status, bundle_payload = self._request(
            "POST",
            "/documents/bulk-export",
            {
                "label": "test_export",
                "document_ids": [uploaded_cv["document_id"], generated_cv["document_id"]],
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(bundle_payload["document_count"], 2)

        status, headers, body = self._binary_request("GET", bundle_payload["download_url"])
        self.assertEqual(status, 200)
        self.assertIn(headers.get("Content-Type"), {"application/zip", "application/x-zip-compressed"})
        self.assertTrue(body.startswith(b"PK"))

    def test_ats_gate_blocks_final_cv_export_until_override_after_warning(self):
        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "sync", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        run_id = run_payload["id"]

        docs_dir = self.temp_dir / "generated_docs" / "2026-04-20" / "blocked_ats_bundle"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "api_job_1_CV.docx").write_bytes(b"blocked-docx-content")

        status, _ = self._request(
            "PUT",
            f"/runs/{run_id}/artifacts/api_blocked_docs_dir",
            {
                "artifact_type": "stage5_docs_dir",
                "path": str(docs_dir),
                "metadata": {
                    "status": "ready",
                    "ats_score": 84,
                    "ats_target_score": 90,
                    "ats_attempt_count": 3,
                    "ats_max_attempts": 3,
                    "missing_requirements": ["SQL", "stakeholder management"],
                },
            },
        )
        self.assertEqual(status, 200)

        status, documents_payload = self._request("GET", f"/documents?run_id={run_id}")
        self.assertEqual(status, 200)
        generated_cv = next(
            (item for item in documents_payload["documents"] if item["asset_kind"] == "generated_cv"),
            None,
        )
        self.assertIsNotNone(generated_cv)
        self.assertTrue(generated_cv["final_export_blocked"])
        self.assertEqual(generated_cv["ats_export_gate"]["best_score"], 84)
        self.assertEqual(generated_cv["display_status"], "export_blocked")
        blocked_group = next(
            (group for group in documents_payload["groups"] if group["group_kind"] == "application"),
            None,
        )
        self.assertIsNotNone(blocked_group)
        self.assertEqual(blocked_group["status_counts"]["export_blocked"], 1)

        status, blocked_payload = self._request(
            "POST",
            "/documents/bulk-export",
            {
                "label": "blocked_export",
                "document_ids": [generated_cv["document_id"]],
            },
        )
        self.assertEqual(status, 400)
        self.assertEqual(blocked_payload["error"]["code"], "ats_export_blocked")
        self.assertEqual(blocked_payload["error"]["details"]["gate"]["best_score"], 84)

        status, headers, body = self._binary_request("GET", generated_cv["download_url"])
        self.assertEqual(status, 400)
        self.assertIn(b"ats_export_blocked", body)

        status, bundle_payload = self._request(
            "POST",
            "/documents/bulk-export",
            {
                "label": "blocked_export",
                "document_ids": [generated_cv["document_id"]],
                "export_anyway": True,
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(bundle_payload["document_count"], 1)

        status, headers, body = self._binary_request("GET", f"{generated_cv['download_url']}?export_anyway=true")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"blocked-docx-content")

    def test_rejected_jobs_endpoint_and_requeue_flow(self):
        requeue_root = self.temp_dir / "requeue_docs"
        self.app.upsert_workflow_template(
            {
                "id": "api_requeue_template",
                "name": "API Requeue Template",
                "stages": [
                    StageDefinition(
                        stage_id="generate_documents",
                        stage_type="test.api_generate_documents",
                        name="Generate Documents",
                        input_keys=["accepted_jobs"],
                        output_key="generated_jobs",
                        config={"output_root": str(requeue_root)},
                        metadata={"supports_requeue": True},
                    ).to_dict()
                ],
            }
        )
        self.app.upsert_workspace(
            {
                "id": "api_requeue_workspace",
                "name": "API Requeue Workspace",
                "workflow_template_id": "api_requeue_template",
                "workspace_type": "custom",
                "sources": [{"id": "manual_source", "connector_id": "curated_job_urls"}],
            }
        )

        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_requeue_workspace", "execution_mode": "planned", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        run_id = run_payload["id"]

        rejected_job = {
            "job_id": "rejected_job_1",
            "title": "Senior Engineer",
            "company": "Rejected Co",
            "apply_link": "https://company.example/jobs/1",
            "stage3_filter_reason": "Rejected because the title looks too senior.",
            "stage3_filter_reasons": ["seniority mismatch"],
        }
        self.app.repositories.job_store.save_blob(run_id, "prioritize_jobs_rejected", [rejected_job])

        status, rejected_payload = self._request("GET", f"/rejected-jobs?run_id={run_id}")
        self.assertEqual(status, 200)
        self.assertEqual(len(rejected_payload["items"]), 1)
        item = rejected_payload["items"][0]
        self.assertEqual(item["job_id"], "rejected_job_1")
        self.assertTrue(item["can_requeue"])

        status, requeue_payload = self._request(
            "POST",
            "/rejected-jobs/requeue",
            {
                "run_id": run_id,
                "job_id": "rejected_job_1",
                "source_stage": item["source_stage"],
                "reason_summary": item["reason_summary"],
                "execution_mode": "sync",
                "notes": "Override this rejection and regenerate documents.",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(requeue_payload["run"]["status"], "completed")

        new_run_id = requeue_payload["run"]["id"]
        status, documents_payload = self._request("GET", f"/documents?run_id={new_run_id}")
        self.assertEqual(status, 200)
        self.assertTrue(any(item["asset_kind"] == "generated_cv" for item in documents_payload["documents"]))

    def test_api_supports_user_and_secret_admin_endpoints(self):
        status, users_payload = self._request("GET", "/users")
        self.assertEqual(status, 200)
        self.assertEqual(len(users_payload["users"]), 1)

        status, token_payload = self._request(
            "POST",
            f"/users/{self.user.user_id}/tokens",
            {"name": "secondary-token"},
        )
        self.assertEqual(status, 201)
        self.assertIn("access_token", token_payload)

        status, secret_payload = self._request(
            "POST",
            "/secrets",
            {"name": "api_secret", "provider": "stored", "workspace_id": "api_workspace", "secret_value": "123"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(secret_payload["name"], "api_secret")
        secret_id = secret_payload["secret_id"]

        status, secrets_payload = self._request("GET", "/secrets?workspace_id=api_workspace")
        self.assertEqual(status, 200)
        self.assertEqual(len(secrets_payload["secrets"]), 1)

        status, _ = self._request("DELETE", f"/secrets/{secret_id}")
        self.assertEqual(status, 200)

    def test_referrals_endpoints_and_review_queue_badges(self):
        status, contact_payload = self._request(
            "POST",
            "/referrals",
            {
                "name": "Jane Referrer",
                "company": "ACME API",
                "linkedin_url": "https://linkedin.com/in/jane-referrer",
                "relationship_note": "Former teammate.",
                "can_refer": True,
            },
        )
        self.assertEqual(status, 201)
        contact_id = contact_payload["contact_id"]

        status, referrals_payload = self._request("GET", "/referrals")
        self.assertEqual(status, 200)
        self.assertEqual(len(referrals_payload["contacts"]), 1)

        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "sync", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        run_id = run_payload["id"]

        status, review_payload = self._request(
            "POST",
            f"/runs/{run_id}/reviews",
            {"job_id": "api_job_1", "decision": "approved", "status": "approved", "reviewer": "tester"},
        )
        self.assertEqual(status, 201)

        status, review_queue_payload = self._request("GET", "/review-queue")
        self.assertEqual(status, 200)
        row = next((item for item in review_queue_payload["items"] if item["job_id"] == "api_job_1"), None)
        self.assertIsNotNone(row)
        self.assertTrue(row["has_referral_contact"])
        self.assertEqual(row["referral_contacts"][0]["contact_id"], contact_id)
        self.assertEqual(row["referral_contacts"][0]["outreach_status"], "Not contacted")

        status, draft_payload = self._request(
            "POST",
            "/outreach/referral-draft",
            {"run_id": run_id, "job_id": "api_job_1", "contact_id": contact_id},
        )
        self.assertEqual(status, 200)
        self.assertIn("Jane Referrer", draft_payload["message"])

        status, outreach_payload = self._request(
            "POST",
            "/referrals/outreach-status",
            {
                "run_id": run_id,
                "job_id": "api_job_1",
                "contact_id": contact_id,
                "outreach_status": "Contacted",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(outreach_payload["outreach_status"], "Contacted")
        self.assertEqual(outreach_payload["contact_name"], "Jane Referrer")

        status, review_queue_payload = self._request("GET", "/review-queue")
        self.assertEqual(status, 200)
        row = next((item for item in review_queue_payload["items"] if item["job_id"] == "api_job_1"), None)
        self.assertIsNotNone(row)
        self.assertEqual(row["referral_contacts"][0]["outreach_status"], "Contacted")

        status, outreach_items_payload = self._request("GET", f"/referrals/outreach-statuses?contact_id={contact_id}")
        self.assertEqual(status, 200)
        self.assertEqual(len(outreach_items_payload["items"]), 1)
        self.assertEqual(outreach_items_payload["items"][0]["job_id"], "api_job_1")
        self.assertEqual(outreach_items_payload["items"][0]["outreach_status"], "Contacted")
        self.assertEqual(outreach_items_payload["items"][0]["contact_linkedin_url"], "https://linkedin.com/in/jane-referrer")

        status, manager_payload = self._request(
            "POST",
            "/outreach/hiring-manager-draft",
            {"run_id": run_id, "job_id": "api_job_1"},
        )
        self.assertEqual(status, 200)
        self.assertIn("hiring_manager", manager_payload)

        status, updated_contact_payload = self._request(
            "PUT",
            f"/referrals/{contact_id}",
            {"name": "Jane Referrer", "company": "ACME API", "can_refer": False},
        )
        self.assertEqual(status, 200)
        self.assertFalse(updated_contact_payload["can_refer"])

        status, delete_payload = self._request("DELETE", f"/referrals/{contact_id}")
        self.assertEqual(status, 200)
        self.assertEqual(delete_payload["deleted"], contact_id)

    def test_referrals_import_endpoint_merges_companies(self):
        status, import_payload = self._request(
            "POST",
            "/referrals/import",
            {
                "csv_text": (
                    "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
                    "Jane,Referrer,https://linkedin.com/in/jane-referrer,,ACME API,Engineering Manager,01 Jan 2024\n"
                    "Jane,Referrer,https://linkedin.com/in/jane-referrer,,Contoso,Director,01 Jan 2024\n"
                ),
                "source_kind": "linkedin_csv",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(import_payload["summary"]["created"], 1)
        self.assertEqual(import_payload["summary"]["updated"], 1)

        status, referrals_payload = self._request("GET", "/referrals")
        self.assertEqual(status, 200)
        self.assertEqual(len(referrals_payload["contacts"]), 1)
        self.assertEqual(
            [entry["company_name"] for entry in referrals_payload["contacts"][0]["companies"]],
            ["ACME API", "Contoso"],
        )
        self.assertEqual(referrals_payload["contacts"][0]["source_kind"], "linkedin_csv")

    def test_api_supports_versioned_routes_pagination_and_worker_visibility(self):
        self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "queued", "max_attempts": 1},
        )
        self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "queued", "max_attempts": 1},
        )

        status, workspaces_payload = self._request("GET", "/v1/workspaces?limit=1&offset=0")
        self.assertEqual(status, 200)
        self.assertEqual(len(workspaces_payload["workspaces"]), 1)
        self.assertEqual(workspaces_payload["meta"]["limit"], 1)

        status, runs_payload = self._request("GET", "/v1/runs?limit=1&offset=0")
        self.assertEqual(status, 200)
        self.assertEqual(len(runs_payload["runs"]), 1)
        self.assertEqual(runs_payload["meta"]["limit"], 1)

        status, worker_payload = self._request(
            "POST",
            "/v1/workers/process-next",
            {"worker_id": "api_worker_test", "lease_seconds": 15},
        )
        self.assertEqual(status, 200)
        self.assertEqual(worker_payload["status"], "processed")

        status, workers_payload = self._request("GET", "/v1/workers?limit=10&offset=0")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(workers_payload["workers"]), 1)
        self.assertEqual(workers_payload["meta"]["offset"], 0)
        worker_ids = {worker["worker_id"] for worker in workers_payload["workers"]}
        self.assertIn("api_worker_test", worker_ids)

    def test_phase0_contracts_endpoint_returns_shared_contract_catalog(self):
        status, payload = self._request("GET", "/contracts/phase0")
        self.assertEqual(status, 200)
        self.assertEqual(payload["version"], "2026-04-20")
        self.assertIn("workspace_configuration_v2", payload)
        self.assertIn("candidate_asset_descriptor", payload)
        self.assertIn("rejected_job_review", payload)
        self.assertIn("mail_connection", payload)
        self.assertIn("referral_relationship", payload)
        self.assertEqual(
            payload["workspace_configuration_v2"]["default"]["schema_version"],
            "workspace_configuration_v2",
        )
        self.assertEqual(
            payload["mail_connection"]["default"]["schema_version"],
            "mail_connection_contract_v1",
        )

    def test_artifacts_endpoint_expands_directory_exports_into_individual_files(self):
        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "sync", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        run_id = run_payload["id"]

        docs_dir = self.temp_dir / "generated_docs" / "2026-04-20" / "api_bundle"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "api_job_1_CV.docx").write_bytes(b"docx-content")
        (docs_dir / "api_job_1_CV.txt").write_text("CV text content", encoding="utf-8")
        (docs_dir / "api_job_1_email.txt").write_text("Email body", encoding="utf-8")
        assets_dir = docs_dir / "_assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        (assets_dir / "profile.png").write_bytes(b"png")

        status, artifact_payload = self._request(
            "PUT",
            f"/runs/{run_id}/artifacts/api_docs_dir",
            {
                "artifact_type": "stage5_docs_dir",
                "path": str(docs_dir),
                "metadata": {"status": "ready", "ats_score": 92, "ats_attempt_count": 1},
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(artifact_payload["artifact_id"], "api_docs_dir")

        status, artifacts_payload = self._request("GET", f"/artifacts?run_id={run_id}")
        self.assertEqual(status, 200)
        entries = artifacts_payload["artifacts"]
        entries_by_name = {item["file_name"]: item for item in entries}
        self.assertIn("api_job_1_CV.docx", entries_by_name)
        self.assertIn("api_job_1_CV.txt", entries_by_name)
        self.assertIn("api_job_1_email.txt", entries_by_name)
        self.assertNotIn("profile.png", entries_by_name)
        self.assertTrue(all(item["artifact_id"] != "api_docs_dir" for item in entries))

        cv_entry = entries_by_name["api_job_1_CV.docx"]
        self.assertEqual(cv_entry["artifact_type"], "cv_docx")
        self.assertTrue(cv_entry["is_virtual"])
        self.assertTrue(cv_entry["is_cv"])
        self.assertEqual(cv_entry["source_artifact_id"], "api_docs_dir")
        self.assertEqual(cv_entry["source_artifact_type"], "stage5_docs_dir")

        status, headers, body = self._binary_request("GET", cv_entry["download_url"])
        self.assertEqual(status, 200)
        self.assertEqual(body, b"docx-content")
        self.assertIn("api_job_1_CV.docx", headers.get("Content-Disposition", ""))

    def test_workspace_settings_take_precedence_over_profile_document_defaults_in_run_overrides(self):
        self.user.metadata = {
            "profile": {
                "name": "Global Profile Name",
                "email": "global@example.com",
                "languages": ["English - C1"],
                "photo_path": "user_config/_profile_from_cv.png",
            },
            "documents": {
                "cv_font": "Calibri",
                "cv_template": "classic",
                "cv_color_scheme": "classic_navy",
                "include_photo": True,
            },
        }
        self.app.upsert_user(self.user)
        self.app.upsert_workspace(
            {
                "id": "api_workspace",
                "name": "API Workspace",
                "workflow_template_id": "api_template_v1",
                "workspace_type": "custom",
                "settings": {
                    "candidate_name": "Workspace Name",
                    "candidate_email": "workspace@example.com",
                    "languages": ["German - B1/B2"],
                    "cv_font": "Georgia",
                    "cv_template": "modern",
                    "cv_color_scheme": "forest",
                    "include_photo": False,
                },
                "sources": [{"id": "manual_source", "connector_id": "curated_job_urls"}],
            }
        )

        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "queued", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        overrides = run_payload["run_input_overrides"]
        self.assertNotIn("candidate_name", overrides)
        self.assertNotIn("candidate_email", overrides)
        self.assertNotIn("languages", overrides)
        self.assertNotIn("cv_font", overrides)
        self.assertNotIn("cv_template", overrides)
        self.assertNotIn("cv_color_scheme", overrides)
        self.assertNotIn("include_photo", overrides)
        self.assertEqual(overrides.get("profile_image"), "")

    def test_tracker_api(self):
        # --- 1. Create and process a run so jobs exist ---
        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "queued", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        run_id = run_payload["id"]
        self._request("POST", "/workers/process-next", {})

        # --- 2. Create an approved review ---
        status, review_payload = self._request(
            "POST",
            f"/runs/{run_id}/reviews",
            {"job_id": "api_job_1", "decision": "approved", "status": "approved", "reviewer": "tester"},
        )
        self.assertEqual(status, 201)
        review_id = review_payload["review_id"]
        user = self.app.get_user(self.user.user_id)
        user.metadata = {
            **dict(user.metadata or {}),
            "candidate_assets": [
                {
                    "asset_id": "asset_cert_api",
                    "asset_kind": "certification",
                    "display_name": "Standard certificate",
                    "download_url": "/documents/assets/asset_cert_api/download",
                    "path": "user_config/candidate_assets/asset_cert_api.pdf",
                }
            ],
        }
        self.app.upsert_user(user)

        # --- 3. GET /tracker returns the approved job (defaulting tracker_status to 'applied') ---
        status, tracker_payload = self._request("GET", "/tracker")
        self.assertEqual(status, 200)
        items = tracker_payload.get("items", [])
        self.assertGreater(len(items), 0)
        item = next((i for i in items if i["review_id"] == review_id), None)
        self.assertIsNotNone(item, "Approved review should appear in tracker")
        self.assertEqual(item["tracker_status"], "applied")
        self.assertFalse(item["email_confirmed"])
        self.assertIn("excel_baseline_columns", tracker_payload)
        self.assertIn("applied?", tracker_payload["excel_baseline_columns"])
        self.assertEqual(item["tracker_table_row"]["Status"], "Applied")
        self.assertEqual(item["tracker_table_row"]["applied?"], "Applied")
        self.assertEqual(item["tracker_table_row"]["company"], item["company"])
        document_labels = [document["label"] for document in item["documents"]]
        self.assertIn("Standard certificate", document_labels)
        self.assertTrue(any(document["source_scope"] == "application" for document in item["documents"]))

        # --- 4. PUT /tracker/:review_id to update status and email_confirmed ---
        status, update_payload = self._request(
            "PUT",
            f"/tracker/{review_id}",
            {"tracker_status": "email_confirmed", "email_confirmed": True, "notes": "Follow up next week."},
        )
        self.assertEqual(status, 200)
        self.assertEqual(update_payload["tracker_status"], "email_confirmed")
        self.assertTrue(update_payload["email_confirmed"])
        self.assertEqual(update_payload["notes"], "Follow up next week.")

        # --- 5. GET /tracker reflects updated fields ---
        status, tracker_payload2 = self._request("GET", "/tracker")
        self.assertEqual(status, 200)
        item2 = next((i for i in tracker_payload2.get("items", []) if i["review_id"] == review_id), None)
        self.assertIsNotNone(item2)
        self.assertEqual(item2["tracker_status"], "email_confirmed")
        self.assertTrue(item2["email_confirmed"])
        self.assertEqual(item2["notes"], "Follow up next week.")

        # --- 6. Move to rejected with a note; rejected_at should be auto-set ---
        status, reject_payload = self._request(
            "PUT",
            f"/tracker/{review_id}",
            {"tracker_status": "rejected", "rejection_note": "They went with an internal candidate."},
        )
        self.assertEqual(status, 200)
        self.assertEqual(reject_payload["tracker_status"], "rejected")
        self.assertEqual(reject_payload["rejection_note"], "They went with an internal candidate.")
        self.assertTrue(reject_payload["rejected_at"])  # should be non-empty ISO timestamp

        # --- 7. Invalid tracker_status raises 400 ---
        status, bad_payload = self._request(
            "PUT",
            f"/tracker/{review_id}",
            {"tracker_status": "flying_high"},
        )
        self.assertEqual(status, 400)
        self.assertIn("tracker_status", bad_payload["error"]["message"])

    def test_tracker_email_integration_api(self):
        class _FakeMailboxClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def probe(self):
                return {"status": "connected", "folder": self.kwargs.get("folder")}

            def fetch_recent_messages(self, *, limit, scan_window="last_1_month"):
                assert limit == 25
                assert scan_window == "last_1_month"
                return [
                    TrackerMailboxMessage(
                        message_id="msg-confirm-1",
                        subject="ACME API application received",
                        from_address="jobs@acmeapi.com",
                        sent_at="2026-04-18T09:00:00+00:00",
                        text="We have received your application for Engineer at ACME API.",
                    ),
                    TrackerMailboxMessage(
                        message_id="msg-interview-1",
                        subject="Interview invitation from ACME API",
                        from_address="recruiting@acmeapi.com",
                        sent_at="2026-04-18T12:00:00+00:00",
                        text="We would like to invite you to interview for the Engineer role at ACME API.",
                    ),
                ]

        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "queued", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        run_id = run_payload["id"]
        self._request("POST", "/workers/process-next", {})

        status, review_payload = self._request(
            "POST",
            f"/runs/{run_id}/reviews",
            {"job_id": "api_job_1", "decision": "approved", "status": "approved", "reviewer": "tester"},
        )
        self.assertEqual(status, 201)
        review_id = review_payload["review_id"]
        email_address = f"candidate+{review_id}@gmail.com"

        with patch("backend.capabilities.tracker.email_integration.ImapMailboxClient", _FakeMailboxClient):
            status, integration_payload = self._request("GET", "/tracker/email-integration")
            self.assertEqual(status, 200)
            self.assertFalse(integration_payload["config"]["connected"])

            status, connect_payload = self._request(
                "PUT",
                "/tracker/email-integration",
                {
                    "provider_id": "gmail",
                    "email_address": email_address,
                    "folder": "INBOX",
                    "max_messages": 25,
                    "password": "app-password-123",
                },
            )
            self.assertEqual(status, 200)
            self.assertTrue(connect_payload["config"]["connected"])
            self.assertEqual(connect_payload["config"]["provider_id"], "gmail")

            status, sync_payload = self._request("POST", "/tracker/email-integration/sync", {})
            self.assertEqual(status, 200)
            self.assertEqual(sync_payload["result"]["summary"]["updated_reviews"], 2)
            self.assertEqual(sync_payload["result"]["summary"]["matched_messages"], 2)
            self.assertEqual(sync_payload["result"]["summary"]["detections"], 2)
            self.assertEqual(sync_payload["result"]["detections"][0]["status"]["confidence"], "high")

        status, tracker_payload = self._request("GET", "/tracker")
        self.assertEqual(status, 200)
        item = next((entry for entry in tracker_payload["items"] if entry["review_id"] == review_id), None)
        self.assertIsNotNone(item)
        self.assertEqual(item["tracker_status"], "interview_invited")
        self.assertTrue(item["email_confirmed"])

        status, delete_payload = self._request("DELETE", "/tracker/email-integration")
        self.assertEqual(status, 200)
        self.assertFalse(delete_payload["integration"]["config"]["connected"])

    def test_tracker_google_email_integration_api(self):
        class _FakeGmailMailboxClient:
            def __init__(self, *, access_token):
                self.access_token = access_token

            def fetch_recent_messages(self, *, limit, scan_window="last_1_month"):
                assert limit == 25
                assert scan_window == "last_1_month"
                return (
                    [
                        TrackerMailboxMessage(
                            message_id="gmail-confirm-1",
                            subject="ACME API application received",
                            from_address="jobs@acmeapi.com",
                            sent_at="2026-04-18T09:00:00+00:00",
                            text="We have received your application for Engineer at ACME API.",
                        ),
                        TrackerMailboxMessage(
                            message_id="gmail-interview-1",
                            subject="Interview invitation from ACME API",
                            from_address="recruiting@acmeapi.com",
                            sent_at="2026-04-18T12:00:00+00:00",
                            text="We would like to invite you to interview for the Engineer role at ACME API.",
                        ),
                        TrackerMailboxMessage(
                            message_id="gmail-false-positive-1",
                            subject="Interview with the Vampire fan club update",
                            from_address="newsletter@movieclub.example",
                            sent_at="2026-04-18T13:00:00+00:00",
                            text="Join our interview series and get a snack-bar offer tonight.",
                        ),
                    ],
                    "history-123",
                )

        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "queued", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        run_id = run_payload["id"]
        self._request("POST", "/workers/process-next", {})

        status, review_payload = self._request(
            "POST",
            f"/runs/{run_id}/reviews",
            {"job_id": "api_job_1", "decision": "approved", "status": "approved", "reviewer": "tester"},
        )
        self.assertEqual(status, 201)
        review_id = review_payload["review_id"]
        email_address = f"candidate+{review_id}@gmail.com"

        with patch.dict(
            os.environ,
            {
                "TRACKER_GOOGLE_OAUTH_CLIENT_ID": "client-id",
                "TRACKER_GOOGLE_OAUTH_CLIENT_SECRET": "client-secret",
            },
            clear=False,
        ):
            with patch("backend.api.server.build_google_tracker_authorization_url", return_value="https://accounts.google.test/auth"), patch(
                "backend.api.server.exchange_google_tracker_oauth_code",
                return_value={
                    "access_token": "google-access-token",
                    "refresh_token": "google-refresh-token",
                    "expires_in": 3600,
                },
            ), patch(
                "backend.api.server.fetch_google_tracker_profile",
                return_value={"emailAddress": email_address},
            ), patch(
                "backend.api.server.refresh_google_tracker_access_token",
                return_value={"access_token": "refreshed-google-token", "expires_in": 3600},
            ), patch(
                "backend.capabilities.tracker.email_integration.GmailMailboxClient",
                _FakeGmailMailboxClient,
            ):
                status, integration_payload = self._request("GET", "/tracker/email-integration")
                self.assertEqual(status, 200)
                self.assertTrue(integration_payload["config"]["oauth_available"])
                self.assertFalse(integration_payload["config"]["connected"])

                status, start_payload = self._request(
                    "POST",
                    "/tracker/email-integration/google/start",
                    {"max_messages": 25, "folder": "INBOX"},
                )
                self.assertEqual(status, 200)
                self.assertEqual(start_payload["authorization_url"], "https://accounts.google.test/auth")
                self.assertEqual(
                    start_payload["integration"]["config"]["authorization_state"],
                    "authorization_url_created",
                )

                stored_config = self.app.get_user(self.user.user_id).metadata["tracker_email_integration"]
                oauth_state = stored_config["oauth_state"]
                callback_path = (
                    f"/tracker/email-integration/google/callback?state={self.user.user_id}:{oauth_state}&code=test-code"
                )
                status, headers, body = self._binary_request("GET", callback_path, authenticated=False)
                self.assertEqual(status, 200)
                self.assertEqual(headers.get("Content-Type"), "text/html; charset=utf-8")
                self.assertIn(b"Google Inbox Connected", body)

                status, connected_payload = self._request("GET", "/tracker/email-integration")
                self.assertEqual(status, 200)
                self.assertTrue(connected_payload["config"]["connected"])
                self.assertEqual(connected_payload["config"]["email_address"], email_address)

                status, sync_payload = self._request("POST", "/tracker/email-integration/sync", {})
                self.assertEqual(status, 200)
                self.assertEqual(sync_payload["result"]["summary"]["updated_reviews"], 2)
                self.assertEqual(sync_payload["result"]["summary"]["matched_messages"], 2)
                self.assertEqual(sync_payload["result"]["summary"]["detections"], 2)
                self.assertEqual(sync_payload["integration"]["config"]["history_id"], "history-123")

    def test_tracker_google_email_review_queue_persists_and_supports_dismiss(self):
        class _FakeGmailMailboxClient:
            def __init__(self, *, access_token):
                self.access_token = access_token

            def fetch_recent_messages(self, *, limit, scan_window="last_1_month"):
                assert limit == 25
                assert scan_window == "last_1_month"
                return (
                    [
                        TrackerMailboxMessage(
                            message_id="gmail-review-1",
                            subject="Interview invitation from ACME API",
                            from_address="updates@acmeapi.com",
                            sent_at="2026-04-18T12:00:00+00:00",
                            text="We would like to speak with you about Engineer at ACME API on Thursday.",
                        ),
                    ],
                    "history-review-123",
                )

        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "queued", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        run_id = run_payload["id"]
        self._request("POST", "/workers/process-next", {})

        status, review_payload = self._request(
            "POST",
            f"/runs/{run_id}/reviews",
            {"job_id": "api_job_1", "decision": "approved", "status": "approved", "reviewer": "tester"},
        )
        self.assertEqual(status, 201)
        review_id = review_payload["review_id"]
        email_address = f"candidate+{review_id}@gmail.com"

        with patch.dict(
            os.environ,
            {
                "TRACKER_GOOGLE_OAUTH_CLIENT_ID": "client-id",
                "TRACKER_GOOGLE_OAUTH_CLIENT_SECRET": "client-secret",
            },
            clear=False,
        ):
            with patch("backend.api.server.build_google_tracker_authorization_url", return_value="https://accounts.google.test/auth"), patch(
                "backend.api.server.exchange_google_tracker_oauth_code",
                return_value={
                    "access_token": "google-access-token",
                    "refresh_token": "google-refresh-token",
                    "expires_in": 3600,
                },
            ), patch(
                "backend.api.server.fetch_google_tracker_profile",
                return_value={"emailAddress": email_address},
            ), patch(
                "backend.api.server.refresh_google_tracker_access_token",
                return_value={"access_token": "refreshed-google-token", "expires_in": 3600},
            ), patch(
                "backend.capabilities.tracker.email_integration.GmailMailboxClient",
                _FakeGmailMailboxClient,
            ):
                self._request(
                    "POST",
                    "/tracker/email-integration/google/start",
                    {"max_messages": 25, "folder": "INBOX"},
                )

                stored_config = self.app.get_user(self.user.user_id).metadata["tracker_email_integration"]
                oauth_state = stored_config["oauth_state"]
                callback_path = (
                    f"/tracker/email-integration/google/callback?state={self.user.user_id}:{oauth_state}&code=test-code"
                )
                status, _, _ = self._binary_request("GET", callback_path, authenticated=False)
                self.assertEqual(status, 200)

                status, sync_payload = self._request("POST", "/tracker/email-integration/sync", {})
                self.assertEqual(status, 200)
                self.assertEqual(sync_payload["result"]["summary"]["updated_reviews"], 0)
                self.assertEqual(sync_payload["result"]["summary"]["detections"], 1)
                self.assertEqual(sync_payload["integration"]["config"]["pending_detection_count"], 1)
                detection = sync_payload["integration"]["config"]["pending_detections"][0]
                self.assertEqual(detection["status"]["approval_state"], "pending_review")
                self.assertEqual(detection["detected_application"]["company"], "ACME API")
                self.assertEqual(detection["detected_application"]["title"], "Engineer")

                status, tracker_payload = self._request("GET", "/tracker")
                self.assertEqual(status, 200)
                tracker_item = next((item for item in tracker_payload["items"] if item["review_id"] == review_id), None)
                self.assertIsNotNone(tracker_item)
                self.assertEqual(tracker_item["tracker_status"], "applied")

                status, integration_payload = self._request("GET", "/tracker/email-integration")
                self.assertEqual(status, 200)
                self.assertEqual(integration_payload["config"]["pending_detection_count"], 1)

                status, dismiss_payload = self._request(
                    "POST",
                    "/tracker/email-integration/detections/dismiss",
                    {"detection": detection},
                )
                self.assertEqual(status, 200)
                self.assertEqual(len(dismiss_payload["dismissed"]), 1)
                self.assertEqual(dismiss_payload["dismissed"][0]["status"]["approval_state"], "dismissed")
                self.assertEqual(dismiss_payload["integration"]["config"]["pending_detection_count"], 0)

                status, integration_payload = self._request("GET", "/tracker/email-integration")
                self.assertEqual(status, 200)
                self.assertEqual(integration_payload["config"]["pending_detection_count"], 0)

    def test_ats_export_gate_evaluate_endpoint_blocks_then_allows_export_anyway(self):
        status, blocked_payload = self._request(
            "POST",
            "/ats/export-gate/evaluate",
            {
                "target_score": 90,
                "best_score": 84,
                "attempt_count": 3,
                "max_attempts": 3,
                "missing_requirements": ["SQL"],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(blocked_payload["gate_state"], "blocked")
        self.assertFalse(blocked_payload["can_export_final"])
        self.assertTrue(blocked_payload["export_anyway_allowed"])
        self.assertIn("Best score reached: 84%", blocked_payload["last_warning"])

        status, export_payload = self._request(
            "POST",
            "/ats/export-gate/evaluate",
            {
                "target_score": 90,
                "best_score": 84,
                "attempt_count": 3,
                "max_attempts": 3,
                "export_anyway": True,
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(export_payload["gate_state"], "exported_anyway")
        self.assertTrue(export_payload["can_export_final"])

    def test_ats_export_gate_evaluate_endpoint_blocks_when_score_stalls_before_max_attempts(self):
        status, stalled_payload = self._request(
            "POST",
            "/ats/export-gate/evaluate",
            {
                "target_score": 90,
                "best_score": 84,
                "attempt_count": 2,
                "max_attempts": 3,
                "missing_requirements": ["SQL"],
                "metadata": {"stop_reason": "score_stalled"},
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(stalled_payload["gate_state"], "blocked")
        self.assertFalse(stalled_payload["can_export_final"])
        self.assertTrue(stalled_payload["export_anyway_allowed"])
        self.assertIn("Best score reached: 84%", stalled_payload["last_warning"])

    def test_gmail_detection_approval_imports_external_application(self):
        status, approve_payload = self._request(
            "POST",
            "/tracker/email-integration/detections/approve",
            {
                "detection": {
                    "detection_id": "gmail::external-1",
                    "scan_window": "last_1_month",
                    "source_email": {
                        "message_id": "external-1",
                        "subject": "Thank you for applying to Example GmbH",
                        "from_address": "jobs@example.com",
                        "sent_at": "2026-04-18T09:00:00+00:00",
                    },
                    "detected_application": {
                        "company": "Example GmbH",
                        "title": "Data Analyst",
                        "application_date": "2026-04-18T09:00:00+00:00",
                        "source_url": "https://jobs.example.com/data-analyst",
                    },
                    "status": {
                        "suggested_application_status": "Applied",
                        "confidence": "medium",
                        "approval_state": "pending_review",
                        "evidence": ["application wording"],
                    },
                }
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(len(approve_payload["approved"]), 1)
        imported = approve_payload["approved"][0]
        self.assertTrue(imported["application_id"].startswith("external_"))
        self.assertEqual(imported["application_status"], "Applied")

        status, tracker_payload = self._request("GET", "/tracker")
        self.assertEqual(status, 200)
        external = next(
            (item for item in tracker_payload["items"] if item.get("application_id") == imported["application_id"]),
            None,
        )
        self.assertIsNotNone(external)
        self.assertTrue(external["external_application"])
        self.assertEqual(external["company"], "Example GmbH")

        status, updated_payload = self._request(
            "PUT",
            f"/tracker/{imported['application_id']}",
            {"application_status": "Interviewing"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated_payload["application_status"], "Interviewing")


if __name__ == "__main__":
    unittest.main()
