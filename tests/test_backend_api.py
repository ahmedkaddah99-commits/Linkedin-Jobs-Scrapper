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
                "workspace_type": "white_collar",
                "sources": [{"id": "manual_source", "connector_id": "manual_url"}],
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
                "workspace_type": "white_collar",
                "sources": [],
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(workspace_payload["id"], "api_custom_workspace")

        status, _ = self._request("DELETE", "/workspaces/api_custom_workspace")
        self.assertEqual(status, 200)
        status, _ = self._request("DELETE", "/workflow-templates/api_custom_template")
        self.assertEqual(status, 200)

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


if __name__ == "__main__":
    unittest.main()
