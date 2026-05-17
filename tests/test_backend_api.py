import base64
import io
import json
import os
import shutil
import threading
import unittest
import zipfile
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote
from unittest.mock import patch

from backend import create_backend
from backend.api.server import build_handler
from backend.capabilities.networking import build_empty_relevant_people_discovery
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


class _ApiCuratedSourceStage(BaseStage):
    def can_run(self, context, definition) -> bool:
        settings = dict(context.data.get("resolved_run_settings") or {})
        return bool(settings.get("manual_urls_inline") or settings.get("manual_url_seed_list"))

    def execute(self, context, definition) -> StageOutcome:
        settings = dict(context.data.get("resolved_run_settings") or {})
        urls = list(settings.get("manual_urls_inline") or settings.get("manual_url_seed_list") or [])
        jobs = []
        for index, url in enumerate(urls, start=1):
            jobs.append(
                JobRecord(
                    job_id=f"quick_job_{index}",
                    title=f"Quick Role {index}",
                    company="Quick Apply Co",
                    apply_link=str(url),
                    source_url=str(url),
                )
            )
        return StageOutcome(job_sets={definition.output_key or "source_exact_job_links": jobs})


class BackendApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path.cwd() / ".backend_test_tmp" / f"api_tests_{self._testMethodName}"
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        self.deepseek_env_patch = patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}, clear=False)
        self.deepseek_env_patch.start()
        self.addCleanup(self.deepseek_env_patch.stop)

        self.app = create_backend(self.temp_dir)
        self.app.registries.stage_registry.register("test.api_seed", _ApiSeedStage())
        self.app.registries.stage_registry.register("test.api_generate_documents", _ApiDocumentStage())
        self.app.registries.stage_registry.register("jobs.ingest.curated_urls", _ApiCuratedSourceStage())
        self.app.registries.stage_registry.register("applications.generate.documents", _ApiDocumentStage())
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

    def _request_with_headers(self, method: str, path: str, *, headers: dict[str, str] | None = None, payload=None):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        body = None
        request_headers = dict(headers or {})
        if payload is not None:
            body = json.dumps(payload)
            request_headers.setdefault("Content-Type", "application/json")
        conn.request(method, path, body=body, headers=request_headers)
        response = conn.getresponse()
        raw = response.read().decode("utf-8")
        response_headers = dict(response.getheaders())
        conn.close()
        return response.status, response_headers, json.loads(raw) if raw else {}

    def _upload_workspace_cv(
        self,
        *,
        filename: str = "builder-resume.txt",
        file_bytes: bytes = b"Builder CV Snapshot\nAnalyst with workflow-specific experience.",
    ) -> dict:
        status, payload = self._multipart_request("/cv-upload", "cv_file", filename, file_bytes)
        self.assertEqual(status, 201)
        return payload["asset"]

    def test_api_requires_bearer_auth_for_protected_routes(self):
        status, payload = self._request("GET", "/workspaces", authenticated=False)
        self.assertEqual(status, 401)
        self.assertIn("error", payload)
        self.assertEqual(payload["error"]["code"], "unauthorized")

    def test_api_allows_loopback_cors_origin(self):
        status, headers, payload = self._request_with_headers(
            "GET",
            "/health",
            headers={"Origin": "http://127.0.0.1:4173"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "http://127.0.0.1:4173")

    def test_api_rejects_disallowed_cors_origin(self):
        status, headers, payload = self._request_with_headers(
            "OPTIONS",
            "/workspaces",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["code"], "forbidden")
        self.assertNotIn("Access-Control-Allow-Origin", headers)

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

    def test_api_supports_deleting_completed_run(self):
        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "queued", "max_attempts": 1},
        )
        self.assertEqual(status, 201)

        status, worker_payload = self._request("POST", "/workers/process-next", {})
        self.assertEqual(status, 200)
        self.assertEqual(worker_payload["run"]["status"], "completed")

        status, delete_payload = self._request("DELETE", f"/runs/{run_payload['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(delete_payload["deleted"], run_payload["id"])

        status, missing_payload = self._request("GET", f"/runs/{run_payload['id']}")
        self.assertEqual(status, 404)
        self.assertEqual(missing_payload["error"]["code"], "not_found")

    def test_run_customer_view_includes_stage_jobs_and_rejection_reasons(self):
        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "queued", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        run_id = run_payload["id"]

        status, worker_payload = self._request("POST", "/workers/process-next", {})
        self.assertEqual(status, 200)
        self.assertEqual(worker_payload["run"]["status"], "completed")

        self.app.repositories.job_store.save_blob(
            run_id,
            "api_seed_stage_rejected",
            [
                {
                    "job_id": "rejected_api_job_1",
                    "title": "Senior Engineer",
                    "company": "Rejected Co",
                    "apply_link": "https://company.example/jobs/rejected-1",
                    "reason": "Title does not match the saved target role.",
                }
            ],
        )

        status, customer_view = self._request("GET", f"/runs/{run_id}/customer-view")
        self.assertEqual(status, 200)
        self.assertEqual(customer_view["run"]["workspace_name"], "API Workspace")
        self.assertEqual(customer_view["summary"]["included_job_count"], 1)
        self.assertEqual(customer_view["summary"]["excluded_job_count"], 1)
        self.assertEqual(len(customer_view["review"]["included_jobs"]), 1)
        self.assertEqual(len(customer_view["review"]["excluded_jobs"]), 1)
        self.assertEqual(customer_view["review"]["included_jobs"][0]["job_id"], "api_job_1")
        self.assertEqual(customer_view["review"]["excluded_jobs"][0]["job_id"], "rejected_api_job_1")
        self.assertEqual(
            customer_view["review"]["excluded_jobs"][0]["reason_summary"],
            "This role does not match the target role for this workspace.",
        )
        self.assertEqual(len(customer_view["stages"]), 1)
        stage = customer_view["stages"][0]
        self.assertEqual(stage["stage_id"], "api_seed_stage")
        self.assertEqual(stage["included_count"], 1)
        self.assertEqual(stage["excluded_count"], 1)
        self.assertEqual(stage["included_jobs"][0]["job_id"], "api_job_1")
        self.assertEqual(stage["excluded_jobs"][0]["job_id"], "rejected_api_job_1")
        self.assertEqual(
            stage["excluded_jobs"][0]["reason_summary"],
            "This role does not match the target role for this workspace.",
        )

    def test_job_workspace_people_discovery_endpoints_persist_selected_people(self):
        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "queued", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        run_id = run_payload["id"]

        status, worker_payload = self._request("POST", "/workers/process-next", {})
        self.assertEqual(status, 200)
        self.assertEqual(worker_payload["run"]["status"], "completed")

        job = self.app.get_job_set(run_id, "accepted_jobs")[0]
        discovery_payload = build_empty_relevant_people_discovery(
            job=job,
            run_id=run_id,
            workspace_id="api_workspace",
            status="completed",
        )
        discovery_payload["categories"] = {
            "hiring_manager": [
                {
                    "id": "person_hiring_manager_jane",
                    "category": "hiring_manager",
                    "name": "Jane Hiringmanager",
                    "title": "Engineering Manager",
                    "company": "ACME API",
                    "location": "Berlin, Germany",
                    "profileUrl": "https://www.linkedin.com/in/jane-hiringmanager",
                    "source": "public_profile_search",
                    "confidence": 80,
                    "confidenceLabel": "High",
                    "reasoningNote": "Likely relevant because this person appears to manage the same function.",
                    "evidenceSnippets": ["Engineering Manager", "ACME API", "Berlin"],
                    "caveats": [],
                    "searchQueries": ["ACME API Engineering Manager Berlin LinkedIn"],
                    "discoveredSearchQuery": "ACME API Engineering Manager Berlin LinkedIn",
                    "regionScopeCaveat": "",
                    "confidenceBreakdown": None,
                    "status": "unreviewed",
                }
            ],
            "potential_colleague": [],
            "executive": [],
        }

        status, workspace_payload = self._request("GET", f"/runs/{run_id}/jobs/by-id/{job.job_id}")
        self.assertEqual(status, 200)
        self.assertEqual(workspace_payload["job"]["job_id"], job.job_id)
        self.assertEqual(
            workspace_payload["relevant_people_discovery"]["peopleDiscoveryStatus"],
            "not_started",
        )

        with patch(
            "backend.application.services.build_relevant_people_discovery",
            return_value=discovery_payload,
        ):
            status, started_payload = self._request(
                "POST",
                f"/runs/{run_id}/jobs/by-id/{job.job_id}/people-discovery/start",
                {},
            )
        self.assertEqual(status, 200)
        self.assertEqual(started_payload["peopleDiscoveryStatus"], "completed")
        self.assertEqual(started_payload["selectedPeople"], [])

        status, discovery_status_payload = self._request(
            "GET",
            f"/runs/{run_id}/jobs/by-id/{job.job_id}/people-discovery/status",
        )
        self.assertEqual(status, 200)
        self.assertEqual(discovery_status_payload["peopleDiscoveryStatus"], "completed")
        self.assertEqual(discovery_status_payload["selectedPeopleCount"], 0)

        status, confirm_payload = self._request(
            "POST",
            f"/runs/{run_id}/jobs/by-id/{job.job_id}/people-discovery/confirm",
            {"person_id": "person_hiring_manager_jane"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(confirm_payload["categories"]["hiring_manager"][0]["status"], "confirmed")
        self.assertEqual(len(confirm_payload["selectedPeople"]), 1)

        status, results_payload = self._request(
            "GET",
            f"/runs/{run_id}/jobs/by-id/{job.job_id}/people-discovery/results",
        )
        self.assertEqual(status, 200)
        self.assertEqual(results_payload["selectedPeople"][0]["id"], "person_hiring_manager_jane")
        self.assertEqual(results_payload["selectedPeople"][0]["status"], "confirmed")

    def test_run_customer_view_normalizes_language_rejection_messages(self):
        profile = dict(self.user.metadata or {})
        profile["profile"] = {
            **dict(profile.get("profile") or {}),
            "languages": ["English - C1", "German - B2"],
        }
        self.user.metadata = profile
        self.app.upsert_user(self.user)

        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "queued", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        run_id = run_payload["id"]

        status, worker_payload = self._request("POST", "/workers/process-next", {})
        self.assertEqual(status, 200)
        self.assertEqual(worker_payload["run"]["status"], "completed")

        self.app.repositories.job_store.save_blob(
            run_id,
            "api_seed_stage_rejected",
            [
                {
                    "job_id": "rejected_api_job_language_1",
                    "title": "Consultant",
                    "company": "Language Co",
                    "apply_link": "https://company.example/jobs/language-1",
                    "reason": "Rejected because the role requires German C1.",
                },
                {
                    "job_id": "rejected_api_job_language_2",
                    "title": "Analyst",
                    "company": "Language Co",
                    "apply_link": "https://company.example/jobs/language-2",
                    "reason": "Rejected because the role requires Spanish.",
                },
            ],
        )

        status, customer_view = self._request("GET", f"/runs/{run_id}/customer-view")
        self.assertEqual(status, 200)
        excluded_jobs = {item["job_id"]: item for item in customer_view["review"]["excluded_jobs"]}

        self.assertEqual(
            excluded_jobs["rejected_api_job_language_1"]["reason_label"],
            "Language level not yet reached",
        )
        self.assertEqual(
            excluded_jobs["rejected_api_job_language_1"]["reason_summary"],
            "This role requires German at C1 level, which is above your saved level.",
        )
        self.assertIn("Saved level: B2", excluded_jobs["rejected_api_job_language_1"]["details"])

        self.assertEqual(
            excluded_jobs["rejected_api_job_language_2"]["reason_label"],
            "Required language not listed",
        )
        self.assertEqual(
            excluded_jobs["rejected_api_job_language_2"]["reason_summary"],
            "This role requires Spanish, which is not listed in your saved languages.",
        )

    def test_api_supports_deleting_single_job_from_run(self):
        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "queued", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        run_id = run_payload["id"]

        status, worker_payload = self._request("POST", "/workers/process-next", {})
        self.assertEqual(status, 200)
        self.assertEqual(worker_payload["run"]["status"], "completed")

        status, review_payload = self._request(
            "POST",
            f"/runs/{run_id}/reviews",
            {"job_id": "api_job_1", "decision": "approved", "status": "approved", "reviewer": "tester"},
        )
        self.assertEqual(status, 201)
        self.assertTrue(review_payload["review_id"])

        status, delete_payload = self._request("DELETE", f"/runs/{run_id}/jobs/by-id/api_job_1")
        self.assertEqual(status, 200)
        self.assertEqual(delete_payload["deleted"], "api_job_1")

        status, jobs_payload = self._request("GET", f"/runs/{run_id}/jobs")
        self.assertEqual(status, 200)
        self.assertEqual(jobs_payload["job_sets"], {})

        status, reviews_payload = self._request("GET", f"/runs/{run_id}/reviews")
        self.assertEqual(status, 200)
        self.assertEqual(reviews_payload["reviews"], [])

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

    def test_api_updates_workspace_recurring_schedule(self):
        status, schedule_payload = self._request(
            "PUT",
            "/workspaces/api_workspace/schedule",
            {"enabled": True, "interval_days": 3},
        )
        self.assertEqual(status, 200)
        self.assertTrue(schedule_payload["schedule"]["enabled"])
        self.assertEqual(schedule_payload["schedule"]["interval_days"], 3)
        self.assertTrue(schedule_payload["schedule"]["next_run_at"])

        status, workspaces_payload = self._request("GET", "/workspaces?limit=100")
        self.assertEqual(status, 200)
        workspace = next(item for item in workspaces_payload["workspaces"] if item["id"] == "api_workspace")
        self.assertTrue(workspace["schedule"]["enabled"])
        self.assertEqual(workspace["schedule"]["interval_days"], 3)

        status, disabled_payload = self._request(
            "PUT",
            "/workspaces/api_workspace/schedule",
            {"enabled": False},
        )
        self.assertEqual(status, 200)
        self.assertFalse(disabled_payload["schedule"]["enabled"])
        self.assertEqual(disabled_payload["schedule"]["interval_days"], 0)
        self.assertEqual(disabled_payload["schedule"]["next_run_at"], "")

    def test_worker_endpoint_processes_due_scheduled_workspace_runs(self):
        workspace_payload = self.app.get_workspace("api_workspace").to_dict()
        workspace_payload["metadata"] = {
            **dict(workspace_payload.get("metadata") or {}),
            "run_schedule": {
                "enabled": True,
                "interval_days": 2,
                "next_run_at": "2000-01-01T00:00:00+00:00",
            },
        }
        self.app.upsert_workspace(workspace_payload)

        status, worker_payload = self._request("POST", "/workers/process-next", {})
        self.assertEqual(status, 200)
        self.assertEqual(worker_payload["status"], "processed")
        self.assertEqual(worker_payload["run"]["status"], "completed")
        self.assertEqual(worker_payload["run"]["requested_by"], "scheduler")

        scheduled_workspace = self.app.get_workspace("api_workspace")
        schedule = scheduled_workspace.metadata.get("run_schedule") or {}
        self.assertEqual(schedule.get("last_run_id"), worker_payload["run"]["id"])
        self.assertTrue(schedule.get("last_enqueued_at"))
        self.assertTrue(schedule.get("next_run_at"))

    def test_api_supports_workspace_builder_catalog_and_create(self):
        workspace_cv_asset_id = self._upload_workspace_cv()["asset_id"]

        status, catalog_payload = self._request("GET", "/workspace-builder/catalog")
        self.assertEqual(status, 200)
        self.assertTrue(catalog_payload["flows"])
        self.assertTrue(catalog_payload["sources"])
        self.assertTrue(catalog_payload["modules"])
        self.assertTrue(catalog_payload["configuration_fields"])
        self.assertIn("builder_sections", catalog_payload)
        source_by_id = {source["id"]: source for source in catalog_payload["sources"]}
        user_facing_fields = {
            field["id"]: field for field in catalog_payload["configuration_fields"] if field.get("user_facing")
        }
        self.assertIn("academic_career_sites", source_by_id)
        self.assertTrue(source_by_id["academic_career_sites"].get("frontend_visible", True))
        self.assertFalse(source_by_id["linkedin_jobs"].get("frontend_visible", True))
        self.assertTrue(source_by_id["linkedin_jobs"].get("legacy"))
        self.assertIn("workspace_cv_asset_id", user_facing_fields)
        self.assertIn("cv_generation_mode", user_facing_fields)
        self.assertIn("work_arrangement", user_facing_fields)
        self.assertIn("industry", user_facing_fields)
        self.assertIn("country_codes", user_facing_fields)
        self.assertIn("cities", user_facing_fields)
        self.assertIn("target_roles", user_facing_fields)
        self.assertIn("job_filtering_mode", user_facing_fields)
        self.assertIn("academic_career_sites", user_facing_fields)
        self.assertIn("french_special_char_threshold", user_facing_fields)
        self.assertIn("spanish_special_char_threshold", user_facing_fields)
        self.assertIn("low_applicant_threshold", user_facing_fields)
        self.assertIn("stage1_model", user_facing_fields)
        self.assertIn("stage4_model", user_facing_fields)
        self.assertIn("stage4_fallback_model", user_facing_fields)
        self.assertIn("light_customization_extra_prompt", user_facing_fields)
        self.assertIn("light_customization_prompt_override", user_facing_fields)
        self.assertIn("aggressive_customization_extra_prompt", user_facing_fields)
        self.assertIn("aggressive_customization_prompt_override", user_facing_fields)
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
                    "workspace_cv_asset_id": workspace_cv_asset_id,
                    "cv_generation_mode": "standard_cv",
                    "keywords": ["analyst"],
                    "work_arrangement": "hybrid",
                    "industry": "Fintech",
                    "geo_id": "101282230",
                    "time_posted_seconds": 86400,
                    "experience_levels": [2, 3],
                    "target_roles": ["Business Analyst", "Consultant"],
                    "job_filtering_mode": "Strict Match",
                    "cv_template": "compact",
                    "cv_color_scheme": "burgundy",
                    "cv_font": "Aptos",
                    "include_photo": False,
                    "french_special_char_threshold": 9999,
                    "spanish_special_char_threshold": 0,
                    "low_applicant_threshold": 55,
                    "light_customization_extra_prompt": "Only tune summary and skills.",
                    "light_customization_prompt_override": "Use the light override.",
                    "aggressive_customization_extra_prompt": "Tune bullet wording harder.",
                    "aggressive_customization_prompt_override": "Use the aggressive override.",
                    "stage1_model": "deepseek-chat",
                    "stage4_model": "deepseek-chat",
                    "stage4_fallback_model": "gemini-2.5-flash",
                },
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(workspace_payload["workspace_type"], "custom")
        self.assertEqual(workspace_payload["metadata"]["automation_flow"], "tailored_documents")
        self.assertEqual(workspace_payload["settings"]["workspace_cv_asset_id"], workspace_cv_asset_id)
        self.assertEqual(workspace_payload["settings"]["cv_generation_mode"], "standard_cv")
        self.assertEqual(workspace_payload["settings"]["keywords"], ["analyst"])
        self.assertEqual(workspace_payload["settings"]["work_arrangement"], "hybrid")
        self.assertEqual(workspace_payload["settings"]["industry"], "Fintech")
        self.assertEqual(workspace_payload["settings"]["experience_levels"], [2, 3])
        self.assertEqual(workspace_payload["settings"]["target_roles"], ["Business Analyst", "Consultant"])
        self.assertEqual(workspace_payload["settings"]["job_filtering_mode"], "Strict Match")
        self.assertEqual(workspace_payload["settings"]["cv_template"], "compact")
        self.assertEqual(workspace_payload["settings"]["cv_color_scheme"], "burgundy")
        self.assertEqual(workspace_payload["settings"]["cv_font"], "Aptos")
        self.assertFalse(workspace_payload["settings"]["include_photo"])
        self.assertEqual(workspace_payload["settings"]["french_special_char_threshold"], 9999)
        self.assertEqual(workspace_payload["settings"]["low_applicant_threshold"], 55)
        self.assertEqual(
            workspace_payload["settings"]["light_customization_extra_prompt"],
            "Only tune summary and skills.",
        )
        self.assertEqual(
            workspace_payload["settings"]["light_customization_prompt_override"],
            "Use the light override.",
        )
        self.assertEqual(
            workspace_payload["settings"]["aggressive_customization_extra_prompt"],
            "Tune bullet wording harder.",
        )
        self.assertEqual(
            workspace_payload["settings"]["aggressive_customization_prompt_override"],
            "Use the aggressive override.",
        )
        self.assertEqual(workspace_payload["settings"]["stage1_model"], "deepseek-chat")
        self.assertEqual(workspace_payload["settings"]["stage4_model"], "deepseek-chat")
        self.assertEqual(workspace_payload["settings"]["stage4_fallback_model"], "gemini-2.5-flash")
        self.assertEqual(
            workspace_payload["settings"]["workspace_cv_text"],
            "Builder CV Snapshot\nAnalyst with workflow-specific experience.",
        )

        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": workspace_payload["id"], "execution_mode": "planned", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        self.assertEqual(run_payload["run_plan"]["resolved_run_settings"]["workspace_cv_asset_id"], workspace_cv_asset_id)
        self.assertEqual(run_payload["run_plan"]["resolved_run_settings"]["cv_generation_mode"], "standard_cv")
        self.assertEqual(run_payload["run_plan"]["resolved_run_settings"]["work_arrangement"], "hybrid")
        self.assertEqual(run_payload["run_plan"]["resolved_run_settings"]["industry"], "Fintech")
        self.assertEqual(run_payload["run_plan"]["resolved_run_settings"]["job_filtering_mode"], "Strict Match")
        self.assertEqual(run_payload["run_plan"]["resolved_run_settings"]["cv_template"], "compact")
        self.assertEqual(run_payload["run_plan"]["resolved_run_settings"]["cv_color_scheme"], "burgundy")
        self.assertEqual(run_payload["run_plan"]["resolved_run_settings"]["cv_font"], "Aptos")
        self.assertFalse(run_payload["run_plan"]["resolved_run_settings"]["include_photo"])
        self.assertEqual(
            run_payload["run_plan"]["resolved_run_settings"]["light_customization_extra_prompt"],
            "Only tune summary and skills.",
        )
        self.assertEqual(
            run_payload["run_plan"]["resolved_run_settings"]["aggressive_customization_prompt_override"],
            "Use the aggressive override.",
        )
        self.assertEqual(
            run_payload["run_plan"]["resolved_run_settings"]["workspace_cv_text"],
            "Builder CV Snapshot\nAnalyst with workflow-specific experience.",
        )

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
                    "work_arrangement": "remote",
                    "industry": "B2B SaaS",
                    "geo_id": "101282230",
                    "manual_url_seed_list": ["https://company.example/jobs/updated"],
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
        self.assertEqual(updated_workspace_payload["settings"]["work_arrangement"], "remote")
        self.assertEqual(updated_workspace_payload["settings"]["industry"], "B2B SaaS")
        self.assertEqual(updated_workspace_payload["metadata"]["source_ids"], ["linkedin_jobs", "curated_job_urls"])

    def test_builder_run_falls_back_to_shared_document_style_defaults(self):
        status, settings_payload = self._request(
            "PUT",
            "/settings",
            {
                "documents": {
                    "cv_template": "modern",
                    "cv_color_scheme": "forest",
                    "cv_font": "Georgia",
                    "include_photo": False,
                }
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(settings_payload["documents"]["cv_template"], "modern")
        self.assertEqual(settings_payload["documents"]["cv_color_scheme"], "forest")
        self.assertEqual(settings_payload["documents"]["cv_font"], "Georgia")
        self.assertFalse(settings_payload["documents"]["include_photo"])

        workspace_cv_asset_id = self._upload_workspace_cv(filename="shared-style-resume.txt")["asset_id"]
        status, workspace_payload = self._request(
            "POST",
            "/workspace-builder/workspaces",
            {
                "name": "Shared Style Fallback Workspace",
                "flow_id": "tailored_documents",
                "source_ids": ["linkedin_jobs"],
                "module_ids": ["screening_filter", "priority_ranking", "tailored_document_generation"],
                "settings": {
                    "workspace_cv_asset_id": workspace_cv_asset_id,
                    "keywords": ["analyst"],
                    "geo_id": "101282230",
                    "job_filtering_mode": "Strict Match",
                },
            },
        )
        self.assertEqual(status, 201)
        self.assertNotIn("cv_template", workspace_payload["settings"])
        self.assertNotIn("cv_color_scheme", workspace_payload["settings"])
        self.assertNotIn("cv_font", workspace_payload["settings"])
        self.assertNotIn("include_photo", workspace_payload["settings"])

        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": workspace_payload["id"], "execution_mode": "planned", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        self.assertEqual(run_payload["run_plan"]["resolved_run_settings"]["cv_template"], "modern")
        self.assertEqual(run_payload["run_plan"]["resolved_run_settings"]["cv_color_scheme"], "forest")
        self.assertEqual(run_payload["run_plan"]["resolved_run_settings"]["cv_font"], "Georgia")
        self.assertFalse(run_payload["run_plan"]["resolved_run_settings"]["include_photo"])

    def test_workspace_builder_invalid_save_returns_structured_validation_error(self):
        workspace_cv_asset_id = self._upload_workspace_cv(filename="invalid-save-resume.txt")["asset_id"]

        status, payload = self._request(
            "POST",
            "/workspace-builder/workspaces",
            {
                "name": "Invalid Builder Workspace",
                "flow_id": "tailored_documents",
                "source_ids": ["linkedin_jobs"],
                "module_ids": ["screening_filter", "priority_ranking", "tailored_document_generation"],
                "settings": {
                    "workspace_cv_asset_id": workspace_cv_asset_id,
                },
            },
        )

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "workspace_validation_failed")
        self.assertEqual(payload["error"]["details"]["phase"], "save")
        field_error_codes = {
            item["code"]
            for item in payload["error"]["details"]["field_errors"]
        }
        self.assertIn("required", field_error_codes)
        self.assertTrue(
            any(item["field"] == "keywords" for item in payload["error"]["details"]["field_errors"])
        )
        self.assertTrue(
            any(item["field"] == "country_codes" for item in payload["error"]["details"]["field_errors"])
        )

    def test_run_start_with_deleted_workspace_cv_returns_structured_validation_error(self):
        workspace_cv_asset_id = self._upload_workspace_cv(filename="deleted-run-resume.txt")["asset_id"]
        status, workspace_payload = self._request(
            "POST",
            "/workspace-builder/workspaces",
            {
                "name": "Deleted CV Run Workspace",
                "flow_id": "tailored_documents",
                "source_ids": ["linkedin_jobs"],
                "module_ids": ["screening_filter", "priority_ranking", "tailored_document_generation"],
                "settings": {
                    "workspace_cv_asset_id": workspace_cv_asset_id,
                    "keywords": ["analyst"],
                    "geo_id": "101282230",
                },
            },
        )
        self.assertEqual(status, 201)
        Path(workspace_payload["settings"]["workspace_cv_asset_path"]).unlink()

        status, payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": workspace_payload["id"], "execution_mode": "planned", "max_attempts": 1},
        )

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "run_preflight_failed")
        self.assertEqual(payload["error"]["details"]["phase"], "run_preflight")
        self.assertTrue(
            any(
                item["code"] == "workspace_cv_asset_missing_file"
                for item in payload["error"]["details"]["field_errors"]
            )
        )

    def test_api_supports_quick_apply_runs_without_creating_a_workspace(self):
        status, payload = self._request(
            "POST",
            "/quick-apply/runs",
            {
                "workspace_id": "api_workspace",
                "execution_mode": "sync",
                "manual_urls": [
                    "https://company.example/jobs/1",
                    "https://company.example/jobs/1",
                    "https://company.example/jobs/2",
                ],
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(payload["accepted_url_count"], 2)
        self.assertEqual(payload["invalid_entries"], [])
        self.assertEqual(payload["run"]["workspace_id"], "api_workspace")
        self.assertEqual(payload["run"]["metadata"]["run_kind"], "quick_apply")
        self.assertEqual(payload["run"]["status"], "completed")

        status, jobs_payload = self._request("GET", f"/runs/{payload['run']['id']}/jobs")
        self.assertEqual(status, 200)
        self.assertIn("generated_jobs", jobs_payload["job_sets"])

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

    def test_workspace_builder_source_validation_emits_passed_analytics_event(self):
        status, payload = self._request(
            "POST",
            "/workspace-builder/source-validation",
            {
                "flow_id": "tailored_documents",
                "source_ids": ["linkedin_jobs", "job_board_collection"],
                "workspace_id": "api_workspace",
                "settings": {
                    "keywords": ["analyst"],
                    "country_codes": ["DE"],
                    "portals": ["indeed", "stepstone"],
                },
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["valid"])

        event_rows = self.app.repositories.analytics_store.query_rows(
            (
                "SELECT event_name, workspace_id, route, source, payload_json "
                "FROM analytics_events WHERE event_name = ? ORDER BY occurred_at DESC LIMIT 1"
            ),
            ("workspace_source_validation_passed",),
        )
        self.assertEqual(len(event_rows), 1)
        event_payload = json.loads(event_rows[0]["payload_json"])
        self.assertEqual(event_rows[0]["event_name"], "workspace_source_validation_passed")
        self.assertEqual(event_rows[0]["workspace_id"], "api_workspace")
        self.assertEqual(event_rows[0]["route"], "/workspace-builder/source-validation")
        self.assertEqual(event_rows[0]["source"], "api")
        self.assertEqual(event_payload["workspace_id"], "api_workspace")
        self.assertEqual(event_payload["field_errors"], payload["field_errors"])
        self.assertEqual(event_payload["source_results"], payload["source_results"])

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

    def test_workspace_builder_source_validation_flags_regional_portal_country_mismatch(self):
        status, payload = self._request(
            "POST",
            "/workspace-builder/source-validation",
            {
                "flow_id": "tailored_documents",
                "source_ids": ["job_board_collection"],
                "settings": {
                    "keywords": ["analyst"],
                    "country_codes": ["DE"],
                    "portals": ["jobsdb"],
                },
            },
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload["valid"])
        portal_result = next(
            item for item in payload["source_results"] if item["source_id"] == "job_board_collection"
        )
        self.assertEqual(portal_result["status"], "invalid")
        self.assertTrue(
            any(item["code"] == "country_mismatch" for item in portal_result["field_errors"])
        )

    def test_workspace_builder_source_validation_emits_failed_analytics_event(self):
        status, payload = self._request(
            "POST",
            "/workspace-builder/source-validation",
            {
                "flow_id": "tailored_documents",
                "source_ids": ["job_board_collection"],
                "workspace_id": "api_workspace",
                "settings": {
                    "keywords": ["analyst"],
                    "country_codes": ["DE"],
                    "portals": ["jobsdb"],
                },
            },
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload["valid"])

        event_rows = self.app.repositories.analytics_store.query_rows(
            (
                "SELECT event_name, workspace_id, route, source, payload_json "
                "FROM analytics_events WHERE event_name = ? ORDER BY occurred_at DESC LIMIT 1"
            ),
            ("workspace_source_validation_failed",),
        )
        self.assertEqual(len(event_rows), 1)
        event_payload = json.loads(event_rows[0]["payload_json"])
        self.assertEqual(event_rows[0]["event_name"], "workspace_source_validation_failed")
        self.assertEqual(event_rows[0]["workspace_id"], "api_workspace")
        self.assertEqual(event_rows[0]["route"], "/workspace-builder/source-validation")
        self.assertEqual(event_rows[0]["source"], "api")
        self.assertEqual(event_payload["workspace_id"], "api_workspace")
        self.assertEqual(event_payload["field_errors"], payload["field_errors"])
        self.assertEqual(event_payload["source_results"], payload["source_results"])

    def test_settings_payload_includes_document_design_options_and_persists_phase2_preferences(self):
        status, settings_payload = self._request("GET", "/settings")
        self.assertEqual(status, 200)
        self.assertTrue(settings_payload["options"]["cv_templates"])
        self.assertTrue(settings_payload["options"]["cv_color_schemes"])
        self.assertTrue(settings_payload["options"]["cv_fonts"])
        self.assertIn(
            "plain",
            {item["id"] for item in settings_payload["options"]["cv_templates"]},
        )

        status, updated_payload = self._request(
            "PUT",
            "/settings",
            {
                "profile": {
                    "name": "Admin Tester",
                    "industry": "Operations and Analytics",
                    "languages": ["English - C1", "German - B1/B2"],
                    "recent_experience": [
                        {
                            "title": "Business Analyst",
                            "company": "Example GmbH",
                            "period": "2022 - Present",
                            "bulletsText": "Built reporting dashboards",
                        }
                    ],
                    "education": [
                        {
                            "degree_title": "MSc Operations Management",
                            "institution": "Example University",
                            "period": "2019 - 2021",
                            "detailsText": "Thesis on process optimization",
                        }
                    ],
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
        self.assertEqual(updated_payload["profile"]["industry"], "Operations and Analytics")
        self.assertEqual(updated_payload["profile"]["languages"], ["English - C1", "German - B1/B2"])
        self.assertEqual(updated_payload["profile"]["recent_experience"][0]["title"], "Business Analyst")
        self.assertEqual(
            updated_payload["profile"]["recent_experience"][0]["bulletsText"],
            "Built reporting dashboards",
        )
        self.assertEqual(updated_payload["profile"]["education"][0]["degree_title"], "MSc Operations Management")
        self.assertEqual(updated_payload["profile"]["education"][0]["institution"], "Example University")

    def test_settings_round_trip_persists_generated_memory_cards(self):
        memory_cards = [
            {
                "id": "memory_1",
                "title": "Automated weekly tracker",
                "category": "project",
                "source": "user_added",
                "status": "ready_for_tailoring",
                "rawNote": "Automated a weekly spreadsheet update that used to be manual.",
                "structuredNotes": {
                    "change": "Automated a weekly spreadsheet update",
                    "impactEstimate": "Saved 4 hours per week",
                },
                "cvBulletSuggestion": "Reduced manual reporting work by automating a weekly spreadsheet update.",
                "coverLetterAngle": "Shows initiative and practical workflow improvement.",
                "tags": ["automation", "reporting"],
                "missingDetails": [],
                "confidenceLabel": "High confidence",
                "useInCv": True,
                "useInLetter": True,
                "createdAt": "2026-05-15T08:00:00Z",
                "updatedAt": "2026-05-15T09:00:00Z",
            }
        ]
        status, updated_payload = self._request(
            "PUT",
            "/settings",
            {
                "documents": {
                    "master_career_profile_text": "Long-form profile import",
                    "career_highlights_text": "Imported highlight block",
                    "generated_memory_cards": memory_cards,
                }
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated_payload["documents"]["generated_memory_cards"][0]["title"], "Automated weekly tracker")
        self.assertEqual(
            updated_payload["documents"]["generated_memory_cards"][0]["structuredNotes"]["impactEstimate"],
            "Saved 4 hours per week",
        )
        self.assertEqual(updated_payload["documents"]["generated_memory_cards"][0]["tags"], ["automation", "reporting"])

        status, settings_payload = self._request("GET", "/settings")
        self.assertEqual(status, 200)
        self.assertEqual(settings_payload["documents"]["generated_memory_cards"][0]["category"], "project")
        self.assertEqual(settings_payload["documents"]["generated_memory_cards"][0]["status"], "ready_for_tailoring")
        self.assertTrue(settings_payload["documents"]["generated_memory_cards"][0]["useInCv"])
        self.assertTrue(settings_payload["documents"]["generated_memory_cards"][0]["useInLetter"])

    def test_cv_upload_returns_structured_profile_fields_for_settings_population(self):
        status, payload = self._multipart_request(
            "/cv-upload",
            "cv_file",
            "structured_resume.txt",
            (
                b"Jane Candidate\n"
                b"Operations Analyst\n"
                b"jane@example.com | Berlin | https://linkedin.com/in/jane-candidate\n"
                b"Summary\nExperienced operations analyst focused on process improvement.\n"
                b"Skills\nExcel, SQL, Stakeholder communication\n"
                b"Languages\nEnglish - C1\nGerman - B2\n"
                b"Experience\nBusiness Analyst | Example GmbH\n2022 - Present\n"
                b"- Built dashboards\n- Improved workflow\n"
                b"Education\nMSc Operations Management | Example University\n2019 - 2021\n"
                b"- Thesis on process optimization\n"
            ),
        )
        self.assertEqual(status, 201)
        self.assertIn(payload["extraction"]["provider"], {"heuristic_fallback", "deepseek"})
        self.assertEqual(payload["parsed"]["name"], "Jane Candidate")
        self.assertEqual(payload["parsed"]["role_title"], "Operations Analyst")
        self.assertEqual(payload["parsed"]["email"], "jane@example.com")
        self.assertIn("Excel", payload["parsed"]["competencies"])
        self.assertEqual(payload["parsed"]["languages"], ["English - C1", "German - B2"])
        self.assertEqual(payload["parsed"]["recent_experience"][0]["title"], "Business Analyst")
        self.assertEqual(payload["parsed"]["education"][0]["degree_title"], "MSc Operations Management")
        self.assertEqual(payload["parsed"]["education"][0]["institution"], "Example University")

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
            (
                b"Summary\nExperienced analyst with operations background.\n"
                b"Skills\nProcess improvement, Excel, SQL\n"
                b"Experience\nBusiness Analyst | Example GmbH\n2022 - Present\n"
                b"- Built dashboard reporting\n- Improved fulfillment workflow\n"
            ),
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
        (docs_dir / "api_job_1_email.txt").write_text("Email body", encoding="utf-8")
        documents_manifest = self.temp_dir / "stage4_documents.json"
        documents_manifest.write_text("{}", encoding="utf-8")

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
        status, _ = self._request(
            "PUT",
            f"/runs/{run_id}/artifacts/api_documents_manifest",
            {
                "artifact_type": "documents_json",
                "path": str(documents_manifest),
                "metadata": {"status": "ready"},
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
        self.assertEqual(generated_cv["display_name"], "Tailored CV")
        self.assertIn("Cover letter", {item["display_name"] for item in documents_payload["documents"]})
        self.assertNotIn("api_job_1_email.txt", {item["display_name"] for item in documents_payload["documents"]})
        self.assertNotIn("stage4_documents.json", {item["display_name"] for item in documents_payload["documents"]})
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
        self.assertEqual(
            uploaded_cv["preview_profile"]["summary"],
            "Experienced analyst with operations background.",
        )
        self.assertIn("Process improvement", uploaded_cv["preview_profile"]["competencies"])
        self.assertEqual(
            uploaded_cv["preview_profile"]["recent_experience"][0]["title"],
            "Business Analyst",
        )

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

    def test_documents_endpoint_labels_applied_cv_artifacts_truthfully(self):
        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "sync", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        run_id = run_payload["id"]

        applied_cv_path = self.temp_dir / "workspace_cv.pdf"
        applied_cv_path.write_bytes(b"%PDF-1.4 applied workspace cv")

        status, _ = self._request(
            "PUT",
            f"/runs/{run_id}/artifacts/api_applied_cv",
            {
                "artifact_type": "applied_cv",
                "path": str(applied_cv_path),
                "metadata": {
                    "job_id": "api_job_1",
                    "job_title": "Engineer",
                    "company": "ACME API",
                    "document_asset_kind": "applied_cv",
                    "document_display_name": "Applied Workspace CV",
                },
            },
        )
        self.assertEqual(status, 200)

        status, documents_payload = self._request("GET", f"/documents?run_id={run_id}")
        self.assertEqual(status, 200)
        applied_cv = next(
            (item for item in documents_payload["documents"] if item["asset_kind"] == "applied_cv"),
            None,
        )
        self.assertIsNotNone(applied_cv)
        self.assertEqual(applied_cv["document_type"], "Applied CV")
        self.assertEqual(applied_cv["display_name"], "Applied Workspace CV")
        self.assertEqual(applied_cv["job_id"], "api_job_1")
        self.assertFalse(applied_cv["final_export_blocked"])

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
        self.assertIn("workspace_id=api_requeue_workspace", item["workspace_editor_url"])
        self.assertIn("edit=api_requeue_workspace", item["workspace_editor_url"])

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

    def test_run_excluded_job_generate_documents_endpoint_updates_customer_view(self):
        requeue_root = self.temp_dir / "requeue_docs_customer_view"
        self.app.upsert_workflow_template(
            {
                "id": "api_requeue_customer_template",
                "name": "API Requeue Customer Template",
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
                "id": "api_requeue_customer_workspace",
                "name": "API Requeue Customer Workspace",
                "workflow_template_id": "api_requeue_customer_template",
                "workspace_type": "custom",
                "sources": [{"id": "manual_source", "connector_id": "curated_job_urls"}],
            }
        )

        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_requeue_customer_workspace", "execution_mode": "planned", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        run_id = run_payload["id"]

        self.app.repositories.job_store.save_blob(
            run_id,
            "generate_documents_rejected",
            [
                {
                    "job_id": "rejected_job_customer_1",
                    "title": "Senior Engineer",
                    "company": "Rejected Co",
                    "apply_link": "https://company.example/jobs/customer-1",
                    "reason": "Title looks too senior for this workspace.",
                }
            ],
        )

        status, generate_payload = self._request(
            "POST",
            f"/runs/{run_id}/excluded-jobs/rejected_job_customer_1/generate-documents",
            {
                "source_stage": "generate_documents",
                "reason_summary": "Title looks too senior for this workspace.",
                "execution_mode": "sync",
                "notes": "Create documents anyway.",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(generate_payload["run"]["status"], "completed")

        status, customer_view = self._request("GET", f"/runs/{run_id}/customer-view")
        self.assertEqual(status, 200)
        excluded_job = customer_view["review"]["excluded_jobs"][0]
        self.assertEqual(excluded_job["job_id"], "rejected_job_customer_1")
        self.assertEqual(excluded_job["create_documents_run_id"], generate_payload["run"]["id"])
        self.assertEqual(excluded_job["create_documents_run_status"], "completed")
        self.assertTrue(excluded_job["create_documents_run_url"].endswith(generate_payload["run"]["id"]))

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

        status, discovery_payload = self._request(
            "POST",
            "/outreach/target-contact-discovery",
            {"run_id": run_id, "job_id": "api_job_1"},
        )
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(discovery_payload["candidates"]), 4)
        self.assertIn("strategy_summary", discovery_payload)

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

    def test_phase1_analytics_events_and_overview_endpoint(self):
        self.app.upsert_workflow_template(
            {
                "id": "analytics_template_v1",
                "name": "Analytics Template",
                "stages": [
                    StageDefinition(
                        stage_id="analytics_seed_stage",
                        stage_type="test.api_seed",
                        name="Seed Jobs",
                        output_key="accepted_jobs",
                    ).to_dict(),
                    StageDefinition(
                        stage_id="analytics_docs_stage",
                        stage_type="applications.generate.documents",
                        name="Generate Documents",
                        input_keys=["accepted_jobs"],
                        output_key="generated_jobs",
                    ).to_dict(),
                ],
            }
        )
        self.app.upsert_workspace(
            {
                "id": "analytics_workspace",
                "name": "Analytics Workspace",
                "workflow_template_id": "analytics_template_v1",
                "workspace_type": "custom",
                "sources": [{"id": "manual_source", "connector_id": "curated_job_urls"}],
            }
        )

        status, upload_payload = self._multipart_request(
            "/documents/upload?asset_kind=workspace_cv&workspace_id=analytics_workspace",
            "document",
            "resume.txt",
            b"Runr Candidate\nProduct-minded operator with analytics ownership.",
        )
        self.assertEqual(status, 201)
        self.assertEqual(upload_payload["asset"]["asset_kind"], "workspace_cv")

        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "analytics_workspace", "execution_mode": "sync", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        self.assertEqual(run_payload["user_id"], self.user.user_id)
        run_id = run_payload["id"]

        status, review_payload = self._request(
            "POST",
            f"/runs/{run_id}/reviews",
            {"job_id": "api_job_1", "decision": "approved", "status": "approved", "reviewer": "tester"},
        )
        self.assertEqual(status, 201)
        review_id = review_payload["review_id"]

        status, tracker_payload = self._request(
            "PUT",
            f"/tracker/{review_id}",
            {"application_status": "Applied", "email_confirmed": True},
        )
        self.assertEqual(status, 200)
        self.assertTrue(tracker_payload["email_confirmed"])
        self.assertTrue(tracker_payload["is_explicit_application"])

        status, contact_payload = self._request(
            "POST",
            "/referrals",
            {
                "name": "Jane Referrer",
                "company": "ACME API",
                "linkedin_url": "https://linkedin.com/in/jane-referrer",
                "can_refer": True,
            },
        )
        self.assertEqual(status, 201)
        contact_id = contact_payload["contact_id"]

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

        status, overview_payload = self._request("GET", "/analytics/overview")
        self.assertEqual(status, 200)
        self.assertIn("automation_success_rate", overview_payload)
        self.assertIn("applications_per_user", overview_payload)
        self.assertIn("referral_outreach_funnel", overview_payload)
        overview_user_row = next(
            (row for row in overview_payload["applications_per_user"] if row["user_id"] == self.user.user_id),
            None,
        )
        self.assertIsNotNone(overview_user_row)
        self.assertEqual(overview_user_row["approved_reviews"], 1)

        status, snapshot_payload = self._request("GET", "/admin/analytics/snapshot")
        self.assertEqual(status, 200)
        snapshot_user_row = next(
            (
                row
                for row in snapshot_payload["applications_per_user"]["rows"]
                if row["user_id"] == self.user.user_id
            ),
            None,
        )
        self.assertIsNotNone(snapshot_user_row)
        self.assertEqual(snapshot_user_row["run_count"], 1)

        event_rows = self.app.repositories.analytics_store.query_rows(
            "SELECT event_name FROM analytics_events ORDER BY occurred_at ASC"
        )
        event_names = [row["event_name"] for row in event_rows]
        self.assertIn("document_uploaded", event_names)
        self.assertIn("run_started", event_names)
        self.assertIn("run_completed", event_names)
        self.assertIn("cv_generation_completed", event_names)
        self.assertIn("application_status_updated", event_names)
        self.assertIn("referral_draft_generated", event_names)
        self.assertIn("outreach_status_changed", event_names)

    def test_admin_events_endpoint_supports_filters_pagination_and_admin_role(self):
        analytics_store = self.app.repositories.analytics_store
        analytics_store.emit_event(
            event_id="evt_admin_1",
            event_name="page_view",
            occurred_at="2026-01-10T08:00:00+00:00",
            user_id=self.user.user_id,
            payload={"route": "/dashboard"},
        )
        analytics_store.emit_event(
            event_id="evt_admin_2",
            event_name="session_started",
            occurred_at="2026-01-11T08:00:00+00:00",
            user_id="usr_other",
            payload={"session_id": "session_2"},
        )
        analytics_store.emit_event(
            event_id="evt_admin_3",
            event_name="page_view",
            occurred_at="2026-01-12T08:00:00+00:00",
            user_id=self.user.user_id,
            payload={"route": "/tracker"},
        )

        status, payload = self._request("GET", "/admin/events?limit=2&offset=0")
        self.assertEqual(status, 200)
        self.assertEqual(payload["meta"]["limit"], 2)
        self.assertEqual(payload["meta"]["offset"], 0)
        self.assertEqual(payload["meta"]["returned"], 2)
        self.assertEqual(payload["meta"]["total"], 3)
        self.assertEqual([item["event_id"] for item in payload["events"]], ["evt_admin_3", "evt_admin_2"])
        self.assertEqual(payload["events"][0]["payload"]["route"], "/tracker")

        status, second_page_payload = self._request("GET", "/admin/events?limit=2&offset=2")
        self.assertEqual(status, 200)
        self.assertEqual([item["event_id"] for item in second_page_payload["events"]], ["evt_admin_1"])

        occurred_from = quote("2026-01-11T00:00:00+00:00", safe="")
        occurred_to = quote("2026-01-13T00:00:00+00:00", safe="")
        status, filtered_payload = self._request(
            "GET",
            f"/admin/events?event_name=page_view&user_id={self.user.user_id}&occurred_from={occurred_from}&occurred_to={occurred_to}",
        )
        self.assertEqual(status, 200)
        self.assertEqual(filtered_payload["meta"]["total"], 1)
        self.assertEqual([item["event_id"] for item in filtered_payload["events"]], ["evt_admin_3"])

        viewer = self.app.upsert_user(
            {
                "email": "viewer@example.com",
                "display_name": "Viewer",
                "role": "viewer",
            }
        )
        _, viewer_token = self.app.issue_api_token(user_id=viewer.user_id, name="viewer-test")
        status, _, unauthorized_payload = self._request_with_headers(
            "GET",
            "/admin/events",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        self.assertEqual(status, 403)
        self.assertEqual(unauthorized_payload["error"]["code"], "forbidden")

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
        docs_dir = self.temp_dir / "tracker_docs" / run_id
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "api_job_1_CV.docx").write_bytes(b"tracker-docx-content")
        (docs_dir / "api_job_1_cover_letter.txt").write_text("Cover letter", encoding="utf-8")
        (docs_dir / "api_job_1_email.txt").write_text("Email body", encoding="utf-8")
        documents_manifest = self.temp_dir / f"{run_id}_documents.json"
        documents_manifest.write_text("{}", encoding="utf-8")
        status, _ = self._request(
            "PUT",
            f"/runs/{run_id}/artifacts/api_tracker_docs_dir",
            {
                "artifact_type": "stage5_docs_dir",
                "path": str(docs_dir),
                "metadata": {"status": "ready"},
            },
        )
        self.assertEqual(status, 200)
        status, _ = self._request(
            "PUT",
            f"/runs/{run_id}/artifacts/api_tracker_documents_manifest",
            {
                "artifact_type": "documents_json",
                "path": str(documents_manifest),
                "metadata": {"status": "ready"},
            },
        )
        self.assertEqual(status, 200)
        standard_certificate_path = self.temp_dir / "asset_cert_api.pdf"
        standard_certificate_path.write_bytes(b"%PDF-1.4 standard certificate")
        user = self.app.get_user(self.user.user_id)
        user.metadata = {
            **dict(user.metadata or {}),
            "candidate_assets": [
                {
                    "asset_id": "asset_cert_api",
                    "asset_kind": "certification",
                    "display_name": "Standard certificate",
                    "download_url": "/documents/assets/asset_cert_api/download",
                    "path": str(standard_certificate_path),
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
        self.assertFalse(item["is_explicit_application"])
        self.assertIn("excel_baseline_columns", tracker_payload)
        self.assertIn("applied?", tracker_payload["excel_baseline_columns"])
        self.assertEqual(item["tracker_table_row"]["Status"], "Applied")
        self.assertEqual(item["tracker_table_row"]["applied?"], "Applied")
        self.assertEqual(item["tracker_table_row"]["company"], item["company"])
        document_labels = [document["label"] for document in item["documents"]]
        self.assertIn("Tailored CV DOCX", document_labels)
        self.assertIn("Cover letter TXT", document_labels)
        self.assertIn("Standard certificate", document_labels)
        self.assertNotIn("api_job_1_email.txt", document_labels)
        self.assertNotIn(f"{run_id}_documents.json", document_labels)
        self.assertTrue(any(document["source_scope"] == "application" for document in item["documents"]))
        blocked_document = next(
            (document for document in item["documents"] if document["label"] == "Tailored CV DOCX"),
            None,
        )
        self.assertIsNotNone(blocked_document)
        self.assertTrue(blocked_document["final_export_blocked"])
        self.assertEqual(
            [column["label"] for column in tracker_payload.get("columns", [])],
            ["Status", "Company", "Role", "Location", "Application date", "Resource", "Priority", "Notes"],
        )

        exportable_document_ids = [
            str(document["document_id"])
            for document in item["documents"]
            if str(document.get("document_id") or "").strip() and not document.get("final_export_blocked")
        ]
        status, bundle_payload = self._request(
            "POST",
            "/documents/bulk-export",
            {
                "label": "tracker_resource_export",
                "document_ids": exportable_document_ids,
                "export_anyway": True,
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(bundle_payload["document_count"], 2)

        status, headers, body = self._binary_request("GET", bundle_payload["download_url"])
        self.assertEqual(status, 200)
        self.assertIn(headers.get("Content-Type"), {"application/zip", "application/x-zip-compressed"})
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertEqual(
                sorted(archive.namelist()),
                ["Cover letter.txt", "Standard certificate.pdf"],
            )

        status, explicit_tracker_payload = self._request("GET", "/tracker?explicit_only=true")
        self.assertEqual(status, 200)
        self.assertFalse(any(entry["review_id"] == review_id for entry in explicit_tracker_payload.get("items", [])))

        # --- 4. PUT /tracker/:review_id to mark the application explicit without changing visible status ---
        status, update_payload = self._request(
            "PUT",
            f"/tracker/{review_id}",
            {"email_confirmed": True, "notes": "Follow up next week."},
        )
        self.assertEqual(status, 200)
        self.assertTrue(update_payload["email_confirmed"])
        self.assertTrue(update_payload["is_explicit_application"])
        self.assertEqual(update_payload["notes"], "Follow up next week.")
        self.assertEqual(
            self.app.repositories.review_store.list_application_status_history(review_id=review_id),
            [],
        )

        # --- 5. GET /tracker reflects updated fields while preserving the Applied view ---
        status, tracker_payload2 = self._request("GET", "/tracker")
        self.assertEqual(status, 200)
        item2 = next((i for i in tracker_payload2.get("items", []) if i["review_id"] == review_id), None)
        self.assertIsNotNone(item2)
        self.assertEqual(item2["tracker_status"], "applied")
        self.assertTrue(item2["email_confirmed"])
        self.assertTrue(item2["is_explicit_application"])
        self.assertEqual(item2["tracker_table_row"]["Status"], "Applied")
        self.assertEqual(item2["notes"], "Follow up next week.")

        status, explicit_tracker_payload2 = self._request("GET", "/tracker?explicit_only=true")
        self.assertEqual(status, 200)
        explicit_item = next((i for i in explicit_tracker_payload2.get("items", []) if i["review_id"] == review_id), None)
        self.assertIsNotNone(explicit_item)
        self.assertTrue(explicit_item["is_explicit_application"])

        # --- 6. Move to rejected with a note; rejected_at should be auto-set ---
        status, reject_payload = self._request(
            "PUT",
            f"/tracker/{review_id}",
            {"tracker_status": "rejected", "rejection_note": "They went with an internal candidate."},
        )
        self.assertEqual(status, 200)
        self.assertEqual(reject_payload["tracker_status"], "rejected")
        self.assertTrue(reject_payload["is_explicit_application"])
        self.assertEqual(reject_payload["rejection_note"], "They went with an internal candidate.")
        self.assertTrue(reject_payload["rejected_at"])  # should be non-empty ISO timestamp
        self.assertEqual(
            self.app.repositories.review_store.list_application_status_history(review_id=review_id),
            [
                {
                    "review_id": review_id,
                    "user_id": self.user.user_id,
                    "from_status": "Applied",
                    "to_status": "Rejected",
                    "changed_at": reject_payload["updated_at"],
                    "source": "manual",
                }
            ],
        )

        # --- 7. Invalid tracker_status raises 400 ---
        status, bad_payload = self._request(
            "PUT",
            f"/tracker/{review_id}",
            {"tracker_status": "flying_high"},
        )
        self.assertEqual(status, 400)
        self.assertIn("tracker_status", bad_payload["error"]["message"])

        # --- 8. DELETE /tracker/:review_id removes the linked run job and tracker entry ---
        self.app.repositories.job_store.save_blob(
            run_id,
            "stage2_rejected",
            [{"job_id": "api_job_1"}, {"job_id": "api_job_2"}],
        )
        status, delete_payload = self._request("DELETE", f"/tracker/{review_id}")
        self.assertEqual(status, 200)
        self.assertEqual(delete_payload["deleted"], review_id)
        self.assertEqual(delete_payload["job_id"], "api_job_1")

        status, jobs_payload = self._request("GET", f"/runs/{run_id}/jobs")
        self.assertEqual(status, 200)
        self.assertEqual(jobs_payload["job_sets"], {})

        status, reviews_payload = self._request("GET", f"/runs/{run_id}/reviews")
        self.assertEqual(status, 200)
        self.assertEqual(reviews_payload["reviews"], [])

        status, artifacts_payload = self._request("GET", f"/runs/{run_id}/artifacts")
        self.assertEqual(status, 200)
        self.assertEqual(artifacts_payload["artifacts"], [])

        self.assertEqual(
            self.app.repositories.job_store.load_blob(run_id, "stage2_rejected", []),
            [{"job_id": "api_job_2"}],
        )

        status, tracker_payload3 = self._request("GET", "/tracker")
        self.assertEqual(status, 200)
        self.assertFalse(any(item["review_id"] == review_id for item in tracker_payload3.get("items", [])))

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
        self.assertEqual(
            self.app.repositories.review_store.list_application_status_history(
                review_id=imported["application_id"]
            ),
            [
                {
                    "review_id": imported["application_id"],
                    "user_id": self.user.user_id,
                    "from_status": "Applied",
                    "to_status": "Interviewing",
                    "changed_at": updated_payload["updated_at"],
                    "source": "manual",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
