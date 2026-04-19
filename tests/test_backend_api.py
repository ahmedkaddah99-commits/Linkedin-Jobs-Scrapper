import base64
import json
import shutil
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from backend import create_backend
from backend.api.server import build_handler
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


class BackendApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path.cwd() / ".backend_test_tmp" / "api_tests"
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))

        self.app = create_backend(self.temp_dir)
        self.app.registries.stage_registry.register("test.api_seed", _ApiSeedStage())
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

        status, draft_payload = self._request(
            "POST",
            "/outreach/referral-draft",
            {"run_id": run_id, "job_id": "api_job_1", "contact_id": contact_id},
        )
        self.assertEqual(status, 200)
        self.assertIn("Jane Referrer", draft_payload["message"])

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

        # --- 3. GET /tracker returns the approved job (defaulting tracker_status to 'applied') ---
        status, tracker_payload = self._request("GET", "/tracker")
        self.assertEqual(status, 200)
        items = tracker_payload.get("items", [])
        self.assertGreater(len(items), 0)
        item = next((i for i in items if i["review_id"] == review_id), None)
        self.assertIsNotNone(item, "Approved review should appear in tracker")
        self.assertEqual(item["tracker_status"], "applied")
        self.assertFalse(item["email_confirmed"])

        # --- 4. PUT /tracker/:review_id to update status and email_confirmed ---
        status, update_payload = self._request(
            "PUT",
            f"/tracker/{review_id}",
            {"tracker_status": "email_confirmed", "email_confirmed": True},
        )
        self.assertEqual(status, 200)
        self.assertEqual(update_payload["tracker_status"], "email_confirmed")
        self.assertTrue(update_payload["email_confirmed"])

        # --- 5. GET /tracker reflects updated fields ---
        status, tracker_payload2 = self._request("GET", "/tracker")
        self.assertEqual(status, 200)
        item2 = next((i for i in tracker_payload2.get("items", []) if i["review_id"] == review_id), None)
        self.assertIsNotNone(item2)
        self.assertEqual(item2["tracker_status"], "email_confirmed")
        self.assertTrue(item2["email_confirmed"])

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


if __name__ == "__main__":
    unittest.main()
