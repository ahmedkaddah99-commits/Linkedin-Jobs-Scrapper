import base64
import hashlib
import io
import json
import os
import shutil
import socket
import threading
import time
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote
from unittest.mock import MagicMock, patch

from backend import create_backend
from backend.api.server import (
    _build_run_input_overrides,
    _build_workspace_cv_preview_profile,
    _clear_auth_context_cache,
    _collect_authorized_runs,
    _customer_excluded_reason,
    _resolve_auth_context,
    _store_candidate_asset_upload,
    build_handler,
)
from backend.capabilities.networking import build_empty_relevant_people_discovery
from backend.capabilities.tracker.email_integration import TrackerMailboxMessage
from backend.domain.models import ArtifactRecord, JobRecord, ReviewRecord, StageDefinition
from backend.orchestration import BaseStage, StageOutcome
from backend.profiles.cv_profile_extraction import extract_cv_profile_fallback


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
    @staticmethod
    def _clerk_jwt_token(*, subject: str = "user_test", session_id: str = "sess_test") -> str:
        def jwt_segment(payload):
            raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

        return ".".join(
            [
                jwt_segment({"alg": "RS256", "kid": "test-key"}),
                jwt_segment(
                    {
                        "iss": "https://resolved-lobster-79.clerk.accounts.dev",
                        "sub": subject,
                        "sid": session_id,
                        "exp": int(time.time()) + 3600,
                    }
                ),
                "signature",
            ]
        )

    def setUp(self):
        self.temp_dir = Path.cwd() / ".backend_test_tmp" / f"api_tests_{self._testMethodName}"
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        _clear_auth_context_cache()
        self.addCleanup(_clear_auth_context_cache)
        self.deepseek_env_patch = patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "",
                "RUNR_ENABLE_LIVE_NETWORKING_DISCOVERY": "",
            },
            clear=False,
        )
        self.deepseek_env_patch.start()
        self.addCleanup(self.deepseek_env_patch.stop)
        self.storage_env_patch = patch.dict(
            os.environ,
            {
                "RUNR_ENV": "development",
                "DATABASE_BACKEND": "sqlite",
                "TURSO_DATABASE_URL": "",
                "TURSO_AUTH_TOKEN": "",
                "OBJECT_STORAGE_BACKEND": "local",
                "OBJECT_STORAGE_LOCAL_ROOT": "",
            },
            clear=False,
        )
        self.storage_env_patch.start()
        self.addCleanup(self.storage_env_patch.stop)
        self.quota_env_patch = patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False)
        self.quota_env_patch.start()
        self.addCleanup(self.quota_env_patch.stop)

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
        api_workspace = self.app.get_workspace("api_workspace")
        api_workspace.owner_user_id = self.user.user_id
        self.app.upsert_workspace(api_workspace)
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

    def _recent_tracker_timestamp(self, *, days_ago: int, hour: int, minute: int = 0) -> str:
        return (
            datetime.now(timezone.utc) - timedelta(days=days_ago)
        ).replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()

    def test_non_admin_users_only_see_their_owned_workspaces_runs_and_tracker_items(self):
        user_a = self.app.upsert_user(
            {
                "email": "owner-a@example.com",
                "display_name": "Owner A",
                "role": "viewer",
            }
        )
        user_b = self.app.upsert_user(
            {
                "email": "owner-b@example.com",
                "display_name": "Owner B",
                "role": "viewer",
            }
        )
        _, token_b = self.app.issue_api_token(user_id=user_b.user_id, name="owner-b-token")

        for user, suffix in ((user_a, "a"), (user_b, "b")):
            workspace_id = f"owned_workspace_{suffix}"
            self.app.upsert_workspace(
                {
                    "id": workspace_id,
                    "name": f"Owned Workspace {suffix.upper()}",
                    "workflow_template_id": "api_template_v1",
                    "workspace_type": "custom",
                    "owner_user_id": user.user_id,
                    "sources": [{"id": "manual_source", "connector_id": "curated_job_urls"}],
                }
            )
            run = self.app.start_run(
                workspace_id,
                execute=False,
                requested_by=f"api:{user.user_id}",
            )
            self.app.upsert_job_set(
                run.id,
                "accepted_jobs",
                [
                    {
                        "job_id": f"job_{suffix}",
                        "title": f"Role {suffix.upper()}",
                        "company": f"Company {suffix.upper()}",
                    }
                ],
            )
            review = ReviewRecord.create(
                run_id=run.id,
                job_id=f"job_{suffix}",
                decision="approved",
                status="approved",
                reviewer=user.user_id,
                metadata={"tracker_status": "applied"},
            )
            self.app.repositories.review_store.upsert_review(review)
            if suffix == "a":
                run_a = run

        self.access_token = token_b

        status, workspace_payload = self._request("GET", "/workspaces")
        self.assertEqual(status, 200)
        self.assertEqual(
            [workspace["id"] for workspace in workspace_payload["workspaces"]],
            ["owned_workspace_b"],
        )

        status, runs_payload = self._request("GET", "/runs")
        self.assertEqual(status, 200)
        self.assertEqual([run["workspace_id"] for run in runs_payload["runs"]], ["owned_workspace_b"])

        status, tracker_payload = self._request("GET", "/tracker")
        self.assertEqual(status, 200)
        self.assertEqual([item["company"] for item in tracker_payload["items"]], ["Company B"])

        status, error_payload = self._request("GET", f"/runs/{run_a.id}")
        self.assertEqual(status, 403)
        self.assertEqual(error_payload["error"]["code"], "forbidden")

    def test_authorized_run_collection_does_not_requery_workspaces_per_run(self):
        user_a = self.app.upsert_user(
            {
                "email": "owner-a@example.com",
                "display_name": "Owner A",
                "role": "viewer",
            }
        )
        user_b = self.app.upsert_user(
            {
                "email": "owner-b@example.com",
                "display_name": "Owner B",
                "role": "viewer",
            }
        )
        for user, suffix in ((user_a, "a"), (user_b, "b")):
            workspace_id = f"collector_workspace_{suffix}"
            self.app.upsert_workspace(
                {
                    "id": workspace_id,
                    "name": f"Collector Workspace {suffix.upper()}",
                    "workflow_template_id": "api_template_v1",
                    "workspace_type": "custom",
                    "owner_user_id": user.user_id,
                    "sources": [{"id": "manual_source", "connector_id": "curated_job_urls"}],
                }
            )
            self.app.start_run(
                workspace_id,
                execute=False,
                requested_by=f"api:{user.user_id}",
            )

        original_get_workspace = self.app.repositories.workspace_repository.get_workspace
        self.app.repositories.workspace_repository.get_workspace = MagicMock(
            side_effect=AssertionError("authorized run collection should use the loaded workspace map")
        )
        self.addCleanup(
            lambda: setattr(
                self.app.repositories.workspace_repository,
                "get_workspace",
                original_get_workspace,
            )
        )

        workspaces, runs = _collect_authorized_runs(self.app, user_a)

        self.assertEqual(set(workspaces), {"collector_workspace_a"})
        self.assertEqual([run.workspace_id for run in runs], ["collector_workspace_a"])

    def test_http_handler_does_not_send_error_response_after_client_disconnect(self):
        handler_class = build_handler(self.app)
        for disconnect_error in (BrokenPipeError(), ConnectionResetError()):
            with self.subTest(error=type(disconnect_error).__name__):
                handler = object.__new__(handler_class)
                handler._enforce_origin_policy = MagicMock()
                handler._parse_request = MagicMock(return_value=("/health", ["health"], {}))
                handler._dispatch_route = MagicMock(side_effect=disconnect_error)
                handler._send_error = MagicMock()

                handler.do_GET()

                handler._send_error.assert_not_called()

    def test_http_handler_swallows_disconnect_while_writing_error_response(self):
        handler_class = build_handler(self.app)
        handler = object.__new__(handler_class)
        handler.headers = {}
        handler.command = "POST"
        handler.path = "/cv-upload"
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.wfile = MagicMock()
        handler.wfile.write.side_effect = BrokenPipeError()

        handler._send_error(500, "internal_error", "safe error")

        self.assertTrue(handler._client_disconnected)
        self.assertTrue(handler.close_connection)
        handler.wfile.write.assert_called_once()

    def _upload_workspace_cv(
        self,
        *,
        filename: str = "builder-resume.txt",
        file_bytes: bytes = b"Builder CV Snapshot\nAnalyst with workflow-specific experience.",
        process: bool = True,
    ) -> dict:
        status, payload = self._multipart_request("/cv-upload", "cv_file", filename, file_bytes)
        self.assertEqual(status, 202)
        if process:
            self.app.process_next_queued_run(auto_retry_failed=False)
            status, ready_payload = self._request("GET", payload["status_url"])
            self.assertEqual(status, 200)
            self.assertEqual(ready_payload["status"], "ready")
            persisted_assets = (self.app.get_user(self.user.user_id).metadata or {}).get("candidate_assets") or []
            self.assertTrue(
                any(asset.get("asset_id") == ready_payload["asset"]["asset_id"] for asset in persisted_assets),
                persisted_assets,
            )
            return ready_payload["asset"]
        return payload["asset"]

    def test_api_requires_bearer_auth_for_protected_routes(self):
        status, payload = self._request("GET", "/workspaces", authenticated=False)
        self.assertEqual(status, 401)
        self.assertIn("error", payload)
        self.assertEqual(payload["error"]["code"], "unauthorized")

    def test_clerk_like_jwt_failure_does_not_try_legacy_token_lookup(self):
        token = self._clerk_jwt_token()

        class LegacyAuthTrap:
            def __init__(self):
                self.called = False

            def authenticate_access_token(self, raw_token):
                self.called = True
                raise AssertionError("legacy token lookup should not run for Clerk JWTs")

        app = LegacyAuthTrap()
        with patch("backend.api.server.verify_session_token", side_effect=ValueError("bad clerk jwt")):
            with self.assertRaises(PermissionError):
                _resolve_auth_context(app, token)
        self.assertFalse(app.called)

    def test_clerk_auth_context_uses_jwt_plan_without_subscription_lookup(self):
        clerk_user_id = "user_clerk_no_subscription_lookup"
        self.app.repositories.auth_repository.set_user_clerk_user_id(self.user.user_id, clerk_user_id)
        token = self._clerk_jwt_token(subject=clerk_user_id)
        claims = SimpleNamespace(
            clerk_user_id=clerk_user_id,
            session_id="sess_no_subscription_lookup",
            role="user",
            plan_id="scale",
            quota_overrides={},
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            raw_claims={},
        )

        subscription_lookup = MagicMock(side_effect=AssertionError("subscription lookup should not run for route auth"))
        with patch.object(
            self.app.repositories.auth_repository,
            "get_current_subscription_by_user_id",
            subscription_lookup,
        ), patch("backend.api.server.verify_session_token", return_value=claims):
            context = _resolve_auth_context(self.app, token)

        self.assertEqual(context.user.user_id, self.user.user_id)
        self.assertEqual(context.plan_id, "scale")
        subscription_lookup.assert_not_called()

    def test_clerk_auth_context_cache_reuses_resolved_context_for_same_token(self):
        clerk_user_id = "user_clerk_cached"
        self.app.repositories.auth_repository.set_user_clerk_user_id(self.user.user_id, clerk_user_id)
        token = self._clerk_jwt_token(subject=clerk_user_id, session_id="sess_cached")
        claims = SimpleNamespace(
            clerk_user_id=clerk_user_id,
            session_id="sess_cached",
            role="user",
            plan_id="scale",
            quota_overrides={},
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            raw_claims={},
        )

        verify = MagicMock(return_value=claims)
        with patch("backend.api.server.verify_session_token", verify):
            first_context = _resolve_auth_context(self.app, token)
            second_context = _resolve_auth_context(self.app, token)

        self.assertEqual(first_context.user.user_id, self.user.user_id)
        self.assertEqual(second_context.user.user_id, self.user.user_id)
        self.assertEqual(verify.call_count, 1)

    def test_api_allows_loopback_cors_origin(self):
        status, headers, payload = self._request_with_headers(
            "GET",
            "/health",
            headers={"Origin": "http://127.0.0.1:4173"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "http://127.0.0.1:4173")

    def test_api_allows_render_frontend_hostname_origin(self):
        with patch.dict(
            os.environ,
            {"RENDER_FRONTEND_EXTERNAL_HOSTNAME": "runr-frontend-pr-42.onrender.com"},
            clear=False,
        ):
            handler_class = build_handler(self.app)

        handler = object.__new__(handler_class)
        handler.headers = {"Origin": "https://runr-frontend-pr-42.onrender.com"}

        self.assertEqual(handler._cors_origin(), "https://runr-frontend-pr-42.onrender.com")

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

    @patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False)
    def test_api_enforces_test_run_limits_and_exposes_test_run_badge_fields(self):
        status, run_payload = self._request(
            "POST",
            "/runs",
            {
                "workspace_id": "api_workspace",
                "execution_mode": "planned",
                "run_mode": "test",
                "run_input_overrides": {
                    "stage4_max_jobs": 99,
                    "max_jobs_total": 99,
                    "company_site_max_sites_per_run": 99,
                },
            },
        )

        self.assertEqual(status, 201)
        self.assertTrue(run_payload["is_test_run"])
        self.assertEqual(run_payload["run_mode"], "test")
        settings = run_payload["run_plan"]["resolved_run_settings"]
        self.assertEqual(settings["stage4_max_jobs"], 1)
        self.assertEqual(settings["max_jobs_total"], 1)
        self.assertEqual(settings["company_site_max_sites_per_run"], 1)
        self.assertEqual(settings["max_enrich_jobs"], 1)
        self.assertEqual(settings["ai_batch_size"], 1)
        self.assertEqual(settings["stage4_retries"], 1)
        self.assertEqual(settings["stage4_retry_sleep"], 0)
        self.assertEqual(settings["stage4_sleep_seconds"], 0)
        self.assertEqual(settings["stage4_ats_max_attempts"], 1)

        status, runs_payload = self._request("GET", "/runs?workspace_id=api_workspace")
        self.assertEqual(status, 200)
        listed_run = next(item for item in runs_payload["runs"] if item["id"] == run_payload["id"])
        self.assertTrue(listed_run["is_test_run"])
        self.assertEqual(listed_run["run_mode"], "test")

    def test_academic_test_run_overrides_do_not_force_one_site_scope(self):
        user = SimpleNamespace(metadata={})

        with patch("backend.api.server.load_job_seeker_config", return_value={}):
            overrides = _build_run_input_overrides(
                user,
                {
                    "run_mode": "test",
                    "run_input_overrides": {
                        "company_site_max_sites_per_run": -1,
                    },
                },
                workspace_settings={"_source_ids": ["academic_career_sites"]},
            )

        self.assertEqual(overrides["run_mode"], "test")
        self.assertEqual(overrides["test_run_job_limit"], 1)
        self.assertEqual(overrides["company_site_max_sites_per_run"], -1)
        self.assertEqual(overrides["company_site_max_job_links_per_site"], 1)
        self.assertEqual(overrides["stage4_max_jobs"], 1)

    def test_tracker_reads_persisted_test_run_review_without_backfilling(self):
        self.app.upsert_workflow_template(
            {
                "id": "api_test_run_tracker_template",
                "name": "API Test Run Tracker Template",
                "stages": [
                    StageDefinition(
                        stage_id="seed_jobs",
                        stage_type="test.api_seed",
                        name="Seed Jobs",
                        output_key="accepted_jobs",
                    ).to_dict(),
                    StageDefinition(
                        stage_id="generate_documents",
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
                "id": "api_test_run_tracker_workspace",
                "name": "API Test Run Tracker Workspace",
                "workflow_template_id": "api_test_run_tracker_template",
                "workspace_type": "custom",
                "sources": [{"id": "manual_source", "connector_id": "curated_job_urls"}],
            }
        )

        with patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False):
            status, run_payload = self._request(
                "POST",
                "/runs",
                {
                    "workspace_id": "api_test_run_tracker_workspace",
                    "execution_mode": "sync",
                    "run_mode": "test",
                },
            )
        self.assertEqual(status, 201)
        reviews = self.app.list_reviews(run_id=run_payload["id"])
        self.assertEqual(len(reviews), 1)

        with patch(
            "backend.application.services.BackendApplication.backfill_completed_test_run_tracker_reviews",
            side_effect=AssertionError("tracker GET must not mutate persisted reviews"),
        ):
            status, tracker_payload = self._request("GET", "/tracker")
        self.assertEqual(status, 200)
        test_run_item = next(
            item for item in tracker_payload["items"]
            if item["run_id"] == run_payload["id"]
        )
        self.assertEqual(test_run_item["job_id"], "api_job_1")
        self.assertTrue(test_run_item["is_test_run"])
        self.assertEqual(test_run_item["run_mode"], "test")
        self.assertEqual(test_run_item["tracker_source_type"], "test_run")
        self.assertTrue(test_run_item["placed_in_tracker_at"])

    def test_dashboard_returns_candidate_action_and_progress_insights(self):
        with patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False):
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
        review = self.app.get_review(review_payload["review_id"])
        old_application_date = (
            datetime.now(timezone.utc) - timedelta(days=20, minutes=1)
        ).replace(microsecond=0).isoformat()
        review.metadata = {
            **dict(review.metadata or {}),
            "tracker_status": "applied",
            "application_status": "Applied",
            "application_date": old_application_date,
        }
        review.updated_at = old_application_date
        self.app.repositories.review_store.upsert_review(review)

        recent_application_date = self._recent_tracker_timestamp(days_ago=2, hour=11)
        user = self.app.get_user(self.user.user_id)
        user.metadata = {
            **dict(user.metadata or {}),
            "external_tracker_applications": [
                {
                    "application_id": "external_dashboard_1",
                    "review_id": "external_dashboard_1",
                    "source": "gmail_detection",
                    "source_label": "Gmail",
                    "title": "Data Analyst",
                    "company": "Example GmbH",
                    "application_date": recent_application_date,
                    "tracker_status": "interview_invited",
                    "application_status": "Interviewing",
                    "created_at": recent_application_date,
                    "updated_at": recent_application_date,
                }
            ],
        }
        self.app.upsert_user(user)

        status, contact_payload = self._request(
            "POST",
            "/referrals",
            {
                "name": "Jane Referrer",
                "company": "ACME API",
                "linkedin_url": "https://linkedin.com/in/jane-referrer",
                "source_kind": "linkedin_csv",
            },
        )
        self.assertEqual(status, 201)
        self.assertTrue(contact_payload["contact_id"])

        status, payload = self._request("GET", "/dashboard")
        self.assertEqual(status, 200)
        self.assertEqual(payload["meta"]["mode"], "full")
        self.assertEqual(payload["analytics"]["outcomes"]["trackerTotal"], 2)
        self.assertEqual(payload["analytics"]["outcomes"]["submittedTotal"], 2)

        insights = payload["analytics"]["candidateInsights"]
        self.assertEqual(
            [stage["label"] for stage in insights["funnel"]["stages"]],
            ["Discovered", "Approved", "Submitted", "Employer responses", "Interviews", "Offers"],
        )
        self.assertTrue(all(stage["conversionRate"] <= 1 for stage in insights["funnel"]["stages"]))
        awaiting_response = next(
            stage for stage in insights["pipelineAging"] if stage["status"] == "Applied"
        )
        self.assertEqual(awaiting_response["count"], 1)
        self.assertEqual(awaiting_response["staleCount"], 1)
        self.assertGreaterEqual(awaiting_response["medianAgeDays"], 20)

        source_labels = [source["label"] for source in insights["sourceEffectiveness"]]
        self.assertIn("Gmail", source_labels)
        self.assertIn("Unknown source", source_labels)
        role_strategy = insights["roleStrategy"]
        self.assertEqual(role_strategy["totalApplications"], 2)
        self.assertIn("Data Analyst", role_strategy["summary"])
        roles_by_label = {role["label"]: role for role in role_strategy["roles"]}
        self.assertEqual(roles_by_label["Data Analyst"]["applications"], 1)
        self.assertEqual(roles_by_label["Data Analyst"]["responses"], 1)
        self.assertEqual(roles_by_label["Data Analyst"]["interviews"], 1)
        self.assertEqual(roles_by_label["Data Analyst"]["applicationShare"], 0.5)
        self.assertEqual(roles_by_label["Data Analyst"]["responseRate"], 1)
        self.assertEqual(roles_by_label["Data Analyst"]["recommendation"], "Test more")
        self.assertEqual(roles_by_label["Engineer"]["applications"], 1)
        self.assertEqual(roles_by_label["Engineer"]["responses"], 0)
        self.assertEqual(insights["weeklySummary"]["current"]["applications"], 1)
        self.assertEqual(insights["weeklySummary"]["current"]["responses"], 1)
        self.assertEqual(insights["weeklySummary"]["current"]["interviews"], 1)
        self.assertGreater(insights["dataQuality"]["issueCount"], 0)
        action_ids = [item["id"] for item in insights["actionPlan"]]
        self.assertIn("stale_applications", action_ids)
        self.assertIn("interviews", action_ids)
        self.assertIn("referral_outreach", action_ids)

    def test_dashboard_summary_mode_returns_fast_shell_payload(self):
        with patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False):
            status, run_payload = self._request(
                "POST",
                "/runs",
                {"workspace_id": "api_workspace", "execution_mode": "sync", "max_attempts": 1},
            )
        self.assertEqual(status, 201)

        status, payload = self._request("GET", "/dashboard?mode=summary")
        self.assertEqual(status, 200)
        self.assertEqual(payload["meta"]["mode"], "summary")
        self.assertTrue(any(run["id"] == run_payload["id"] for run in payload["recent_runs"]))
        self.assertEqual(payload["analytics"]["outcomes"]["trackerTotal"], 0)
        self.assertEqual(payload["analytics"]["candidateInsights"]["funnel"]["stages"], [])

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
        with patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False):
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
        self.app.repositories.job_store.save_blob(
            run_id,
            "capped_sites",
            [{"url": "https://company.example/careers", "links_fetched": 25, "cap_value": 25}],
        )

        with patch("backend.api.server._collect_tracker_entries", side_effect=AssertionError("customer-view must stay run-scoped")), patch(
            "backend.api.server._collect_authorized_runs",
            side_effect=AssertionError("customer-view must not scan all runs"),
        ), patch(
            "backend.api.server._load_candidate_assets",
            side_effect=AssertionError("customer-view must not collect candidate assets"),
        ), patch(
            "backend.api.server._run_jobs_for_document_lookup",
            side_effect=AssertionError("customer-view must reuse its loaded job sets"),
        ), patch(
            "backend.application.services.BackendApplication.backfill_completed_test_run_tracker_reviews",
            side_effect=AssertionError("customer-view GET must not mutate persisted reviews"),
        ):
            status, customer_view = self._request("GET", f"/runs/{run_id}/customer-view")
        self.assertEqual(status, 200)
        self.assertEqual(customer_view["run"]["workspace_name"], "API Workspace")
        self.assertEqual(customer_view["summary"]["included_job_count"], 1)
        self.assertEqual(customer_view["summary"]["excluded_job_count"], 1)
        self.assertEqual(len(customer_view["review"]["included_jobs"]), 1)
        self.assertEqual(len(customer_view["review"]["excluded_jobs"]), 1)
        self.assertEqual(customer_view["review"]["included_jobs"][0]["job_id"], "api_job_1")
        self.assertEqual(customer_view["review"]["excluded_jobs"][0]["job_id"], "rejected_api_job_1")
        self.assertEqual(customer_view["run"]["capped_sites"][0]["cap_value"], 25)
        status, run_detail = self._request("GET", f"/runs/{run_id}")
        self.assertEqual(status, 200)
        self.assertEqual(run_detail["capped_sites"][0]["links_fetched"], 25)
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

    def test_run_customer_view_includes_live_progress_snapshot(self):
        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "queued", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        run_id = run_payload["id"]

        run = self.app.get_run(run_id)
        run.status = "running"
        run.current_stage_id = "api_seed_stage"
        run.metadata["progress"] = {
            "stage_id": "api_seed_stage",
            "stage_type": "jobs.acquire.company_sites",
            "stage_name": "Acquire Company Career Site Jobs",
            "status": "running",
            "message": "Scanning Example Company",
            "started_at": "2026-05-24T18:00:00+00:00",
            "last_progress_at": "2026-05-24T18:10:00+00:00",
            "stage_description": "Scrape backend-prepared company career pages for matching open roles.",
            "counters": {
                "total_sites": 100,
                "processed_sites": 12,
                "failed_sites": 2,
                "jobs_found": 7,
            },
            "current_item": {
                "company_name": "Example Company",
                "site_url": "https://example.com/careers",
            },
            "recent_failures": [{"company_name": "Broken Co", "error": "timeout"}],
        }
        self.app.repositories.run_repository.save(run)

        status, customer_view = self._request("GET", f"/runs/{run_id}/customer-view")
        self.assertEqual(status, 200)
        self.assertEqual(customer_view["run"]["progress"]["stage_id"], "api_seed_stage")
        self.assertEqual(customer_view["run"]["progress"]["counters"]["processed_sites"], 12)
        self.assertEqual(customer_view["run"]["progress"]["current_item"]["company_name"], "Example Company")
        self.assertIn(customer_view["run"]["progress"]["health"], {"active", "slow", "stale"})
        self.assertTrue(customer_view["summary"]["run_health_label"])

        status, runs_payload = self._request("GET", "/runs")
        self.assertEqual(status, 200)
        matching_runs = [item for item in runs_payload["runs"] if item["id"] == run_id]
        self.assertEqual(len(matching_runs), 1)
        self.assertEqual(matching_runs[0]["progress"]["message"], "Scanning Example Company")

    def test_run_detail_infers_completed_status_for_stale_running_row(self):
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

        stale_run = self.app.get_run(run_id)
        stale_run.status = "running"
        stale_run.current_stage_id = stale_run.stage_results[-1].stage_id
        stale_run.finished_at = ""
        stale_run.metadata["progress"] = {"message": "stale progress"}
        self.app.repositories.run_repository.save(stale_run)
        self.app.repositories.job_store.save_blob(run_id, "capped_sites", [{"url": "https://slow.example/jobs"}])

        with patch.object(
            self.app.repositories.job_store,
            "load_blob",
            side_effect=AssertionError("lightweight run status must not load capped_sites"),
        ):
            status, run_detail = self._request("GET", f"/runs/{run_id}?include_capped_sites=0")

        self.assertEqual(status, 200)
        self.assertEqual(run_detail["status"], "completed")
        self.assertEqual(run_detail["current_stage_id"], "")
        self.assertNotIn("capped_sites", run_detail)

        with patch(
            "backend.api.server.build_run_eta",
            side_effect=AssertionError("completed run detail must not scan historical runs for ETA"),
        ):
            status, customer_view = self._request("GET", f"/runs/{run_id}/customer-view")

        self.assertEqual(status, 200)
        self.assertEqual(customer_view["run"]["status"], "completed")
        self.assertEqual(customer_view["run"]["current_stage_id"], "")
        self.assertEqual(customer_view["run"]["eta"]["state"], "unavailable")

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

    def test_job_workspace_people_discovery_reports_not_configured_without_live_discovery(self):
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
        with patch.dict(
            "os.environ",
            {"RUNR_ENABLE_LIVE_NETWORKING_DISCOVERY": ""},
            clear=False,
        ):
            status, started_payload = self._request(
                "POST",
                f"/runs/{run_id}/jobs/by-id/{job.job_id}/people-discovery/start",
                {},
            )

        self.assertEqual(status, 200)
        self.assertEqual(started_payload["peopleDiscoveryStatus"], "not_configured")
        self.assertIn("Live networking discovery is disabled", started_payload["error"])
        self.assertEqual(started_payload["provider"]["search"], "offline_fallback")
        self.assertEqual(started_payload["selectedPeople"], [])

        status, discovery_status_payload = self._request(
            "GET",
            f"/runs/{run_id}/jobs/by-id/{job.job_id}/people-discovery/status",
        )
        self.assertEqual(status, 200)
        self.assertEqual(discovery_status_payload["peopleDiscoveryStatus"], "not_configured")
        self.assertEqual(discovery_status_payload["selectedPeopleCount"], 0)
        self.assertIn("Live networking discovery is disabled", discovery_status_payload["error"])

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
                {
                    "job_id": "rejected_api_job_language_3",
                    "title": "Consultant",
                    "company": "Language Co",
                    "apply_link": "https://company.example/jobs/language-3",
                    "reason": "Listing appears to be written in French above configured threshold (count 2 > threshold 0).",
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
        self.assertEqual(
            excluded_jobs["rejected_api_job_language_3"]["reason_label"],
            "Listing language excluded",
        )
        self.assertEqual(
            excluded_jobs["rejected_api_job_language_3"]["reason_summary"],
            "This listing appears to be written in French, and this workspace is configured to skip that listing language.",
        )

    def test_run_customer_view_uses_first_language_mention_in_rejection_reason(self):
        profile = dict(self.user.metadata or {})
        profile["profile"] = {
            **dict(profile.get("profile") or {}),
            "languages": ["English - C1", "German - B2"],
        }
        self.user.metadata = profile

        reason = _customer_excluded_reason(
            {
                "reason_code": "language_mismatch",
                "reason_summary": (
                    "Rejected because the role requires German C1. "
                    "QA note: do not classify this as French."
                ),
            },
            self.user,
        )

        self.assertEqual(reason["reason_label"], "Language level not yet reached")
        self.assertEqual(
            reason["reason_summary"],
            "This role requires German at C1 level, which is above your saved level.",
        )

    def test_user_cannot_track_same_posting_url_twice_across_workspaces(self):
        self.app.upsert_workspace(
            {
                "id": "api_workspace_duplicate",
                "name": "API Workspace Duplicate",
                "workflow_template_id": "api_template_v1",
                "workspace_type": "custom",
                "sources": [{"id": "manual_source", "connector_id": "curated_job_urls"}],
            }
        )
        posting_url = "https://company.example/jobs/product-owner-123?utm_source=workspace"

        status, first_run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "queued", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        first_run_id = first_run_payload["id"]
        status, worker_payload = self._request("POST", "/workers/process-next", {})
        self.assertEqual(status, 200)
        self.assertEqual(worker_payload["run"]["status"], "completed")
        self.app.upsert_job_set(
            first_run_id,
            "accepted_jobs",
            [
                JobRecord(
                    job_id="posting_first",
                    title="Product Owner",
                    company="Company",
                    apply_link=posting_url,
                    source_url=posting_url,
                )
            ],
        )
        status, first_review = self._request(
            "POST",
            f"/runs/{first_run_id}/reviews",
            {"job_id": "posting_first", "decision": "approved", "status": "approved", "reviewer": "tester"},
        )
        self.assertEqual(status, 201)
        self.assertTrue(first_review["review_id"])

        status, second_run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace_duplicate", "execution_mode": "queued", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        second_run_id = second_run_payload["id"]
        status, worker_payload = self._request("POST", "/workers/process-next", {})
        self.assertEqual(status, 200)
        self.assertEqual(worker_payload["run"]["status"], "completed")
        self.app.upsert_job_set(
            second_run_id,
            "accepted_jobs",
            [
                JobRecord(
                    job_id="posting_second",
                    title="Product Owner",
                    company="Company",
                    apply_link="https://company.example/jobs/product-owner-123",
                    source_url="https://company.example/jobs/product-owner-123",
                )
            ],
        )

        status, duplicate_payload = self._request(
            "POST",
            f"/runs/{second_run_id}/reviews",
            {"job_id": "posting_second", "decision": "approved", "status": "approved", "reviewer": "tester"},
        )
        self.assertEqual(status, 400)
        self.assertIn("already tracked", json.dumps(duplicate_payload))

        status, tracker_payload = self._request("GET", "/tracker")
        self.assertEqual(status, 200)
        tracked_urls = [item["apply_link"] for item in tracker_payload["items"]]
        self.assertEqual(tracked_urls, [posting_url])

    def test_tracker_only_loads_artifacts_for_runs_with_tracker_reviews(self):
        status, tracked_run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "queued", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        tracked_run_id = tracked_run_payload["id"]
        status, worker_payload = self._request("POST", "/workers/process-next", {})
        self.assertEqual(status, 200)
        self.assertEqual(worker_payload["run"]["status"], "completed")
        status, review_payload = self._request(
            "POST",
            f"/runs/{tracked_run_id}/reviews",
            {"job_id": "api_job_1", "decision": "approved", "status": "approved", "reviewer": "tester"},
        )
        self.assertEqual(status, 201)
        self.assertTrue(review_payload["review_id"])

        status, untracked_run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "queued", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        untracked_run_id = untracked_run_payload["id"]
        status, worker_payload = self._request("POST", "/workers/process-next", {})
        self.assertEqual(status, 200)
        self.assertEqual(worker_payload["run"]["status"], "completed")

        original_loader = self.app.repositories.artifact_store.load_artifacts_for_runs
        loaded_run_batches: list[list[str]] = []

        def recording_loader(run_ids):
            batch = [str(run_id) for run_id in run_ids]
            loaded_run_batches.append(batch)
            return original_loader(batch)

        self.app.repositories.artifact_store.load_artifacts_for_runs = MagicMock(side_effect=recording_loader)
        self.addCleanup(
            lambda: setattr(
                self.app.repositories.artifact_store,
                "load_artifacts_for_runs",
                original_loader,
            )
        )

        status, tracker_payload = self._request("GET", "/tracker")
        self.assertEqual(status, 200)
        self.assertTrue(any(item["run_id"] == tracked_run_id for item in tracker_payload["items"]))
        loaded_run_ids = {run_id for batch in loaded_run_batches for run_id in batch}
        self.assertIn(tracked_run_id, loaded_run_ids)
        self.assertNotIn(untracked_run_id, loaded_run_ids)

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
        self.assertIn("posted_within_days", user_facing_fields)
        self.assertEqual(
            [option["value"] for option in user_facing_fields["posted_within_days"]["options"]],
            [0, 60, 30, 14, 7, 1],
        )
        self.assertIn("academic_career_sites", user_facing_fields)
        self.assertIn("french_special_char_threshold", user_facing_fields)
        self.assertIn("spanish_special_char_threshold", user_facing_fields)
        self.assertIn("low_applicant_threshold", user_facing_fields)
        self.assertIn("stage1_model", user_facing_fields)
        self.assertIn("stage4_model", user_facing_fields)
        self.assertIn("cv_template", user_facing_fields)
        self.assertIn(
            "plain",
            {option["value"] for option in user_facing_fields["cv_template"]["options"]},
        )
        self.assertIn(
            "section_bars",
            {option["value"] for option in user_facing_fields["cv_template"]["options"]},
        )
        self.assertEqual(
            {option["value"] for option in user_facing_fields["cv_template"]["options"]},
            {
                "plain",
                "section_bars",
                "modern_minimal",
                "modern_sidebar",
                "classic_executive",
            },
        )
        self.assertNotIn(
            "teal_resume",
            {option["value"] for option in user_facing_fields["cv_template"]["options"]},
        )
        self.assertIn("light_customization_extra_prompt", user_facing_fields)
        self.assertIn("light_customization_prompt_override", user_facing_fields)
        self.assertIn("aggressive_customization_extra_prompt", user_facing_fields)
        self.assertIn("aggressive_customization_prompt_override", user_facing_fields)
        self.assertNotIn("geo_id", user_facing_fields)
        self.assertNotIn("candidate_name", user_facing_fields)
        self.assertTrue(
            any(not flow.get("frontend_visible", True) for flow in catalog_payload["flows"] if flow["id"] == "reusable_packages")
        )

        with patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False):
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
                        "country_codes": ["DE"],
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
                    },
                },
            )
        self.assertEqual(status, 201)
        self.assertEqual(workspace_payload["workspace_type"], "custom")
        self.assertEqual(workspace_payload["owner_user_id"], self.user.user_id)
        self.assertEqual(workspace_payload["metadata"]["automation_flow"], "tailored_documents")
        self.assertEqual(workspace_payload["settings"]["workspace_cv_asset_id"], workspace_cv_asset_id)
        self.assertFalse(workspace_payload["settings"].get("workspace_cv_asset_path"))
        self.assertFalse(workspace_payload["settings"].get("workspace_cv_asset_docx_path"))
        self.assertTrue(workspace_payload["settings"]["workspace_cv_asset_object_key"])
        self.assertTrue(workspace_payload["settings"]["workspace_cv_asset_docx_object_key"])
        self.assertEqual(workspace_payload["settings"]["cv_generation_mode"], "standard_cv")
        self.assertEqual(workspace_payload["settings"]["keywords"], ["analyst"])
        self.assertEqual(workspace_payload["settings"]["work_arrangement"], "hybrid")
        self.assertEqual(workspace_payload["settings"]["industry"], "Fintech")
        self.assertEqual(workspace_payload["settings"]["experience_levels"], [2, 3])
        self.assertEqual(workspace_payload["settings"]["target_roles"], ["Business Analyst", "Consultant"])
        self.assertEqual(workspace_payload["settings"]["job_filtering_mode"], "Strict Match")
        self.assertEqual(workspace_payload["settings"]["country_codes"], ["DE"])
        self.assertEqual(workspace_payload["settings"]["cv_template"], "plain")
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
        self.assertEqual(
            workspace_payload["settings"]["workspace_cv_text"],
            "Builder CV Snapshot\nAnalyst with workflow-specific experience.",
        )

        with patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False):
            status, run_payload = self._request(
                "POST",
                "/runs",
                {"workspace_id": workspace_payload["id"], "execution_mode": "planned", "max_attempts": 1},
            )
        self.assertEqual(status, 201)
        self.assertEqual(run_payload["run_plan"]["resolved_run_settings"]["workspace_cv_asset_id"], workspace_cv_asset_id)
        self.assertFalse(run_payload["run_plan"]["resolved_run_settings"].get("workspace_cv_asset_path"))
        self.assertFalse(run_payload["run_plan"]["resolved_run_settings"].get("workspace_cv_asset_docx_path"))
        self.assertEqual(run_payload["run_plan"]["resolved_run_settings"]["cv_generation_mode"], "standard_cv")
        self.assertEqual(run_payload["run_plan"]["resolved_run_settings"]["work_arrangement"], "hybrid")
        self.assertEqual(run_payload["run_plan"]["resolved_run_settings"]["industry"], "Fintech")
        self.assertEqual(run_payload["run_plan"]["resolved_run_settings"]["job_filtering_mode"], "Strict Match")
        self.assertEqual(run_payload["run_plan"]["resolved_run_settings"]["cv_template"], "plain")
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
                    "country_codes": ["DE"],
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
        self.assertEqual(settings_payload["documents"]["cv_template"], "plain")
        self.assertEqual(settings_payload["documents"]["cv_color_scheme"], "forest")
        self.assertEqual(settings_payload["documents"]["cv_font"], "Georgia")
        self.assertFalse(settings_payload["documents"]["include_photo"])

        workspace_cv_asset_id = self._upload_workspace_cv(filename="shared-style-resume.txt")["asset_id"]
        with patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False):
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
                        "country_codes": ["DE"],
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

        with patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False):
            status, run_payload = self._request(
                "POST",
                "/runs",
                {"workspace_id": workspace_payload["id"], "execution_mode": "planned", "max_attempts": 1},
            )
        self.assertEqual(status, 201)
        self.assertEqual(run_payload["run_plan"]["resolved_run_settings"]["cv_template"], "plain")
        self.assertEqual(run_payload["run_plan"]["resolved_run_settings"]["cv_color_scheme"], "forest")
        self.assertEqual(run_payload["run_plan"]["resolved_run_settings"]["cv_font"], "Georgia")
        self.assertFalse(run_payload["run_plan"]["resolved_run_settings"]["include_photo"])

    def test_builder_preview_and_run_use_candidate_profile_links(self):
        linkedin_url = "https://linkedin.example/admin-tester"
        github_url = "https://github.example/admin-tester"
        status, settings_payload = self._request(
            "PUT",
            "/settings",
            {
                "profile": {
                    "linkedin_url": linkedin_url,
                    "github_url": github_url,
                }
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(settings_payload["profile"]["linkedin_url"], linkedin_url)
        self.assertEqual(settings_payload["profile"]["github_url"], github_url)

        workspace_cv_asset_id = self._upload_workspace_cv(filename="profile-links-resume.txt")["asset_id"]
        status, documents_payload = self._request("GET", "/documents?asset_kind=workspace_cv")
        self.assertEqual(status, 200)
        uploaded_cv = next(
            item
            for item in documents_payload["documents"]
            if item["asset_id"] == workspace_cv_asset_id
        )
        self.assertEqual(uploaded_cv["preview_profile"]["linkedin_url"], linkedin_url)
        self.assertEqual(uploaded_cv["preview_profile"]["github_url"], github_url)

        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "planned", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        self.assertEqual(run_payload["run_input_overrides"]["linkedin_url"], linkedin_url)
        self.assertEqual(run_payload["run_input_overrides"]["github_url"], github_url)

    def test_workspace_cv_document_listing_stays_candidate_asset_scoped(self):
        workspace_cv_asset_id = self._upload_workspace_cv(filename="dropdown-scope-resume.txt")["asset_id"]
        with patch(
            "backend.api.server._collect_authorized_runs",
            side_effect=AssertionError("workspace CV listing must not scan runs"),
        ), patch(
            "backend.api.server._persist_candidate_assets",
            side_effect=AssertionError("workspace CV listing must not mutate candidate assets"),
        ), patch.object(
            self.app.object_storage,
            "get",
            side_effect=AssertionError("workspace CV listing must not download object contents"),
        ):
            status, documents_payload = self._request("GET", "/documents?asset_kind=workspace_cv")

        self.assertEqual(status, 200)
        self.assertTrue(
            any(item["asset_id"] == workspace_cv_asset_id for item in documents_payload["documents"]),
            documents_payload["documents"],
        )
        self.assertTrue(
            all(item["asset_kind"] == "workspace_cv" for item in documents_payload["documents"]),
            documents_payload["documents"],
        )

    def test_settings_and_run_fall_back_to_configured_candidate_profile_links(self):
        linkedin_url = "https://linkedin.example/configured-candidate"
        github_url = "https://github.example/configured-candidate"
        candidate_config = {
            "candidate": {
                "profile_links": {
                    "linkedin": {"url": linkedin_url},
                    "github": {"url": github_url},
                }
            }
        }

        with patch("backend.api.server.load_job_seeker_config", return_value=candidate_config):
            status, settings_payload = self._request("GET", "/settings")
            self.assertEqual(status, 200)
            self.assertEqual(settings_payload["profile"]["linkedin_url"], linkedin_url)
            self.assertEqual(settings_payload["profile"]["github_url"], github_url)

            status, run_payload = self._request(
                "POST",
                "/runs",
                {"workspace_id": "api_workspace", "execution_mode": "planned", "max_attempts": 1},
            )

        self.assertEqual(status, 201)
        self.assertEqual(run_payload["run_input_overrides"]["linkedin_url"], linkedin_url)
        self.assertEqual(run_payload["run_input_overrides"]["github_url"], github_url)

    def test_workspace_builder_invalid_save_returns_structured_validation_error(self):
        workspace_cv_asset_id = self._upload_workspace_cv(filename="invalid-save-resume.txt")["asset_id"]

        with patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False):
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

    def test_workspace_builder_create_requires_workspace_cv_with_structured_field_error(self):
        with patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False):
            status, payload = self._request(
                "POST",
                "/workspace-builder/workspaces",
                {
                    "name": "Missing CV Builder Workspace",
                    "flow_id": "tailored_documents",
                    "source_ids": ["linkedin_jobs"],
                    "module_ids": ["screening_filter", "priority_ranking", "tailored_document_generation"],
                    "settings": {
                        "keywords": ["analyst"],
                        "country_codes": ["DE"],
                    },
                },
            )

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "workspace_validation_failed")
        self.assertEqual(payload["error"]["details"]["phase"], "save")
        self.assertIn(
            {
                "field": "workspace_cv_asset_id",
                "code": "required",
                "message": "Select a workspace CV before saving or running this workspace.",
            },
            payload["error"]["details"]["field_errors"],
        )

    def test_workspace_builder_create_rejects_stale_workspace_cv_id_with_structured_field_error(self):
        with patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False):
            status, payload = self._request(
                "POST",
                "/workspace-builder/workspaces",
                {
                    "name": "Stale CV Builder Workspace",
                    "flow_id": "tailored_documents",
                    "source_ids": ["linkedin_jobs"],
                    "module_ids": ["screening_filter", "priority_ranking", "tailored_document_generation"],
                    "settings": {
                        "workspace_cv_asset_id": "asset_missing_workspace_cv",
                        "keywords": ["analyst"],
                        "country_codes": ["DE"],
                    },
                },
            )

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "workspace_validation_failed")
        self.assertEqual(payload["error"]["details"]["phase"], "save")
        self.assertIn(
            {
                "field": "workspace_cv_asset_id",
                "code": "workspace_cv_asset_unresolved",
                "message": "Select an accessible workspace CV before saving or running this workspace.",
            },
            payload["error"]["details"]["field_errors"],
        )

    def test_generic_workspace_api_cannot_bypass_builder_validation(self):
        status, payload = self._request(
            "POST",
            "/workspaces",
            {
                "id": "malformed_api_builder_workspace",
                "name": "Malformed API Builder Workspace",
                "workflow_template_id": "api_template_v1",
                "workspace_type": "custom",
                "settings": {
                    "automation_flow": "tailored_documents",
                    "keywords": ["analyst"],
                    "country_codes": ["DE"],
                },
                "metadata": {
                    "builder_mode": "scratch",
                    "automation_flow": "tailored_documents",
                    "source_ids": [],
                    "modules": [],
                },
            },
        )

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "workspace_validation_failed")
        field_errors = payload["error"]["details"]["field_errors"]
        self.assertTrue(
            any(item["field"] == "source_ids" and item["code"] == "required" for item in field_errors)
        )
        self.assertTrue(
            any(item["field"] == "module_ids" and item["code"] == "required" for item in field_errors)
        )
        self.assertTrue(
            any(item["field"] == "workspace_cv_asset_id" and item["code"] == "required" for item in field_errors)
        )

    def test_workspace_builder_update_rejects_empty_sources_with_structured_field_error(self):
        workspace_cv_asset_id = self._upload_workspace_cv(filename="empty-update-sources-resume.txt")["asset_id"]
        valid_payload = {
            "name": "Update Validation Workspace",
            "flow_id": "tailored_documents",
            "source_ids": ["linkedin_jobs"],
            "module_ids": ["screening_filter", "priority_ranking", "tailored_document_generation"],
            "settings": {
                "workspace_cv_asset_id": workspace_cv_asset_id,
                "keywords": ["analyst"],
                "country_codes": ["DE"],
            },
        }
        with patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False):
            status, workspace_payload = self._request(
                "POST",
                "/workspace-builder/workspaces",
                valid_payload,
            )
        self.assertEqual(status, 201, workspace_payload)

        status, payload = self._request(
            "PUT",
            f"/workspace-builder/workspaces/{workspace_payload['id']}",
            {
                **valid_payload,
                "source_ids": [],
            },
        )

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "workspace_validation_failed")
        self.assertEqual(payload["error"]["details"]["phase"], "save")
        self.assertTrue(
            any(
                item["field"] == "source_ids" and item["code"] == "required"
                for item in payload["error"]["details"]["field_errors"]
            )
        )

    def test_run_start_with_deleted_workspace_cv_returns_structured_validation_error(self):
        workspace_cv_asset_id = self._upload_workspace_cv(filename="deleted-run-resume.txt")["asset_id"]
        with patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False):
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
                        "country_codes": ["DE"],
                        "geo_id": "101282230",
                    },
                },
            )
        self.assertEqual(status, 201, workspace_payload)
        self.app.object_storage.delete(workspace_payload["settings"]["workspace_cv_asset_object_key"])

        with patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False):
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

    def test_run_start_with_stale_builder_country_uses_run_preflight_error_contract(self):
        workspace_cv_asset_id = self._upload_workspace_cv(filename="stale-country-resume.txt")["asset_id"]
        with patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False):
            status, workspace_payload = self._request(
                "POST",
                "/workspace-builder/workspaces",
                {
                    "name": "Stale Country Workspace",
                    "flow_id": "tailored_documents",
                    "source_ids": ["linkedin_jobs"],
                    "module_ids": ["screening_filter", "priority_ranking", "tailored_document_generation"],
                    "settings": {
                        "workspace_cv_asset_id": workspace_cv_asset_id,
                        "keywords": ["analyst"],
                        "country_codes": ["DE"],
                    },
                },
            )
        self.assertEqual(status, 201, workspace_payload)

        stale_workspace = self.app.get_workspace(workspace_payload["id"])
        stale_workspace.settings["country_codes"] = []
        self.app.repositories.workspace_repository.upsert_workspace(stale_workspace)

        with patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False):
            status, payload = self._request(
                "POST",
                "/runs",
                {"workspace_id": stale_workspace.id, "execution_mode": "planned", "max_attempts": 1},
            )

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "run_preflight_failed")
        self.assertEqual(payload["error"]["details"]["phase"], "run_preflight")
        self.assertTrue(
            any(
                item["field"] == "country_codes" and item["code"] == "required"
                for item in payload["error"]["details"]["field_errors"]
            )
        )

    @patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False)
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
        resolved_settings = payload["run"]["run_plan"]["resolved_run_settings"]
        self.assertEqual(resolved_settings["stage4_retries"], 1)
        self.assertEqual(resolved_settings["stage4_retry_sleep"], 0)
        self.assertEqual(resolved_settings["stage4_sleep_seconds"], 0)
        self.assertEqual(resolved_settings["stage4_ats_max_attempts"], 1)

        status, jobs_payload = self._request("GET", f"/runs/{payload['run']['id']}/jobs")
        self.assertEqual(status, 200)
        self.assertIn("generated_jobs", jobs_payload["job_sets"])

    def test_quick_apply_creates_internal_workspace_when_workspace_id_is_omitted(self):
        with patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False):
            status, payload = self._request(
                "POST",
                "/quick-apply/runs",
                {
                    "execution_mode": "sync",
                    "manual_urls": ["https://company.example/jobs/no-workspace"],
                },
            )
        self.assertEqual(status, 201)
        self.assertEqual(payload["accepted_url_count"], 1)
        self.assertEqual(payload["run"]["metadata"]["run_kind"], "quick_apply")

        workspace = self.app.get_workspace(payload["run"]["workspace_id"])
        self.assertEqual(workspace.workspace_type, "internal")
        self.assertTrue(workspace.metadata["internal"])

    @patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False)
    def test_quick_apply_accepts_cv_generation_and_preview_settings(self):
        workspace_cv_asset = self._upload_workspace_cv(
            filename="quick-apply-resume.txt",
            file_bytes=b"Quick Apply CV Snapshot\nFocused application baseline.",
        )

        status, payload = self._request(
            "POST",
            "/quick-apply/runs",
            {
                "workspace_id": "api_workspace",
                "execution_mode": "planned",
                "manual_urls": ["https://company.example/jobs/quick-settings"],
                "settings": {
                    "workspace_cv_asset_id": workspace_cv_asset["asset_id"],
                    "cv_generation_mode": "light_customization",
                    "personalization_scope": "baseline_plus_selected_assets",
                    "cv_template": "compact",
                    "cv_color_scheme": "forest",
                    "cv_font": "Aptos",
                    "include_photo": False,
                },
            },
        )

        self.assertEqual(status, 201)
        resolved_settings = payload["run"]["run_plan"]["resolved_run_settings"]
        self.assertEqual(resolved_settings["workspace_cv_asset_id"], workspace_cv_asset["asset_id"])
        self.assertEqual(resolved_settings["workspace_cv_text"], "Quick Apply CV Snapshot\nFocused application baseline.")
        self.assertEqual(resolved_settings["cv_generation_mode"], "light_customization")
        self.assertEqual(resolved_settings["personalization_scope"], "baseline_plus_selected_assets")
        self.assertEqual(resolved_settings["cv_template"], "compact")
        self.assertEqual(resolved_settings["cv_color_scheme"], "forest")
        self.assertEqual(resolved_settings["cv_font"], "Aptos")
        self.assertFalse(resolved_settings["include_photo"])
        self.assertEqual(resolved_settings["manual_urls_inline"], ["https://company.example/jobs/quick-settings"])
        self.assertEqual(resolved_settings["stage4_retries"], 1)
        self.assertEqual(resolved_settings["stage4_retry_sleep"], 0)
        self.assertEqual(resolved_settings["stage4_sleep_seconds"], 0)
        self.assertEqual(resolved_settings["stage4_ats_max_attempts"], 1)

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

    def test_workspace_builder_source_validation_includes_company_site_policy_estimate(self):
        with patch(
            "backend.application.services._scrapeops_account_state",
            return_value={
                "available": True,
                "status": "healthy",
                "summary": "ScrapeOps account is healthy.",
                "usage": {"used": 100, "limit": 1000, "remaining": 900},
            },
        ):
            status, payload = self._request(
                "POST",
                "/workspace-builder/source-validation",
                {
                    "flow_id": "tailored_documents",
                    "source_ids": ["company_career_sites"],
                    "settings": {
                        "country_codes": ["DE"],
                        "company_career_sites": [
                            "Acme | https://company.example/de/careers",
                            "Global Co | https://company.example/global/careers",
                        ],
                    },
                },
            )
        self.assertEqual(status, 200)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["company_site_policy"]["policy_version"], "2026-05-26.credit-guard-v2")
        result = next(item for item in payload["source_results"] if item["source_id"] == "company_career_sites")
        self.assertIn("runner_credit_estimate", result)
        self.assertGreaterEqual(result["runner_credit_estimate"]["max_runner_credits"], 0)
        self.assertEqual(payload["policy_run_overrides"]["company_site_locality_mode"], "local_preferred")

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

    def test_billing_subscription_includes_scrapeops_usage_summary(self):
        self.app.repositories.analytics_store.emit_event(
            event_id="evt_scrapeops_usage_1",
            event_name="scrapeops_request",
            occurred_at=datetime.now(timezone.utc).replace(day=15, hour=12, minute=0, second=0, microsecond=0).isoformat(),
            user_id=self.user.user_id,
            workspace_id="api_workspace",
            run_id="run_usage_1",
            route="/runs/run_usage_1",
            source="worker",
            payload={
                "domain": "company.example",
                "request_mode": "basic",
                "billed": True,
                "runner_credits": 3,
                "native_credits": 3,
            },
        )

        status, payload = self._request("GET", "/billing/subscription")
        self.assertEqual(status, 200)
        self.assertIn("scrapeops_usage", payload)
        self.assertEqual(payload["usage"]["quotas"]["runner_credits_per_month"]["limit"], -1)
        self.assertEqual(payload["scrapeops_usage"]["usage"]["totals"]["runner_credits"], 3)
        self.assertEqual(payload["scrapeops_usage"]["policy"]["company_sites_per_run"], 0)

    def test_account_delete_deactivates_current_user_and_cancels_subscription(self):
        account_user = self.app.upsert_user(
            {
                "email": "delete-me@example.com",
                "display_name": "Delete Me",
                "role": "viewer",
            }
        )
        _, account_token = self.app.issue_api_token(user_id=account_user.user_id, name="delete-account")
        self.app.repositories.auth_repository.upsert_subscription(
            {
                "subscription_id": "sub_delete_account",
                "user_id": account_user.user_id,
                "plan_id": "momentum",
                "status": "active",
                "billing_provider": "creem",
                "creem_subscription_id": "sub_delete_account",
                "creem_customer_id": "cust_delete_account",
                "current_period_start": "2026-06-01T00:00:00+00:00",
                "current_period_end": "2026-07-01T00:00:00+00:00",
            }
        )

        status, _, bad_payload = self._request_with_headers(
            "DELETE",
            "/account",
            headers={"Authorization": f"Bearer {account_token}"},
            payload={"confirmation": "wrong"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(bad_payload["error"]["code"], "bad_request")
        self.assertTrue(self.app.get_user(account_user.user_id).is_active)

        status, _, payload = self._request_with_headers(
            "DELETE",
            "/account",
            headers={"Authorization": f"Bearer {account_token}"},
            payload={"confirmation": account_user.email},
        )
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["deleted"], account_user.user_id)
        self.assertEqual(payload["status"], "deactivated")

        deleted_user = self.app.get_user(account_user.user_id)
        self.assertFalse(deleted_user.is_active)
        self.assertEqual(deleted_user.metadata["account_deleted_by"], "self_service")

        subscription = self.app.repositories.auth_repository.get_current_subscription_by_user_id(account_user.user_id)
        self.assertEqual(subscription["status"], "cancelled")
        self.assertTrue(subscription["cancelled_at"])

        event_rows = self.app.repositories.analytics_store.query_rows(
            "SELECT event_name, user_id, payload_json FROM analytics_events WHERE event_name = 'account_deleted'"
        )
        self.assertEqual(len(event_rows), 1)
        self.assertEqual(event_rows[0]["user_id"], account_user.user_id)
        self.assertEqual(json.loads(event_rows[0]["payload_json"])["user_id"], account_user.user_id)

        status, _, inactive_payload = self._request_with_headers(
            "GET",
            "/auth/me",
            headers={"Authorization": f"Bearer {account_token}"},
        )
        self.assertEqual(status, 403)
        self.assertEqual(inactive_payload["error"]["code"], "forbidden")

    def test_run_customer_view_includes_scrapeops_usage_summary(self):
        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "queued", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        run_id = run_payload["id"]
        self.app.repositories.analytics_store.emit_event(
            event_id="evt_scrapeops_usage_2",
            event_name="scrapeops_request",
            occurred_at="2026-05-25T12:10:00+00:00",
            user_id=self.user.user_id,
            workspace_id="api_workspace",
            run_id=run_id,
            route=f"/runs/{run_id}",
            source="worker",
            payload={
                "domain": "company.example",
                "request_mode": "render_js_cheap",
                "billed": True,
                "runner_credits": 5,
                "native_credits": 5,
            },
        )

        status, customer_view = self._request("GET", f"/runs/{run_id}/customer-view")
        self.assertEqual(status, 200)
        self.assertEqual(customer_view["run"]["scrapeops_usage"]["totals"]["runner_credits"], 5)

    def test_admin_scrapeops_policy_can_be_saved_and_loaded(self):
        policy_payload = {
            "plan_policies": {
                "none": {
                    "runner_credits_per_month": 150,
                    "company_sites_per_run": 3,
                    "runner_credits_per_run": 40,
                }
            },
            "user_overrides": [
                {
                    "user_id": self.user.user_id,
                    "plan_id": "scale",
                    "runner_credits_per_month": -1,
                    "company_sites_per_run": -1,
                    "runner_credits_per_run": -1,
                    "notes": "internal admin test",
                }
            ],
            "domain_policies": [
                {
                    "policy_id": "workday_basic_first",
                    "domain_pattern": "*.myworkdayjobs.com",
                    "site_request_modes": ["basic", "render_js_cheap"],
                    "job_detail_request_modes": ["basic"],
                    "locality_mode": "strict_local_only",
                    "country_code": "DE",
                    "priority": 10,
                }
            ],
            "alert_policy": {
                "enabled": True,
                "cadence_hours": 4,
                "low_remaining_credits_threshold": 50,
                "discrepancy_threshold": 25,
                "history_days": 14,
            },
        }

        status, saved = self._request("PUT", "/admin/scrapeops/policy", policy_payload)
        self.assertEqual(status, 200)
        self.assertEqual(saved["plan_policies"]["none"]["company_sites_per_run"], 3)
        self.assertEqual(saved["user_overrides"][0]["user_id"], self.user.user_id)
        self.assertEqual(saved["domain_policies"][0]["policy_id"], "workday_basic_first")
        self.assertEqual(saved["alert_policy"]["cadence_hours"], 4)

        status, fetched = self._request("GET", "/admin/scrapeops/policy")
        self.assertEqual(status, 200)
        self.assertEqual(fetched["domain_policies"][0]["domain_pattern"], "*.myworkdayjobs.com")

    def test_admin_scrapeops_dashboard_returns_trends_policy_and_alerts(self):
        usage_occurred_at = (
            datetime.now(timezone.utc) - timedelta(days=1)
        ).replace(hour=12, minute=10, second=0, microsecond=0).isoformat()
        self.app.repositories.analytics_store.emit_event(
            event_id="evt_scrapeops_admin_usage_1",
            event_name="scrapeops_request",
            occurred_at=usage_occurred_at,
            user_id=self.user.user_id,
            workspace_id="api_workspace",
            run_id="run_usage_admin",
            route="/runs/run_usage_admin",
            source="worker",
            payload={
                "domain": "company.example",
                "request_mode": "basic",
                "billed": True,
                "runner_credits": 2,
                "native_credits": 2,
            },
        )
        with (
            patch(
                "backend.application.services._scrapeops_account_state",
                return_value={
                    "available": True,
                    "status": "healthy",
                    "summary": "ScrapeOps account is healthy.",
                    "usage": {"used": 12, "limit": 1000, "remaining": 988},
                },
            ),
            patch("backend.application.services.fetch_domain_stats", return_value={"results": []}),
        ):
            status, payload = self._request("GET", "/admin/scrapeops/usage")

        self.assertEqual(status, 200)
        self.assertIn("policy", payload)
        self.assertEqual(payload["usage"]["totals"]["runner_credits"], 2)
        self.assertEqual(payload["usage_series"][0]["runner_credits"], 2)
        self.assertIn("reconciliation_series", payload)
        self.assertIn("alerts", payload)

    def test_admin_scrapeops_reconciliation_run_records_alerts(self):
        self.app.save_scrapeops_admin_policy(
            {
                "alert_policy": {
                    "enabled": True,
                    "cadence_hours": 6,
                    "low_remaining_credits_threshold": 100,
                    "discrepancy_threshold": 10,
                    "history_days": 30,
                }
            }
        )
        with (
            patch(
                "backend.application.services._scrapeops_account_state",
                return_value={
                    "available": True,
                    "status": "healthy",
                    "summary": "ScrapeOps account is low on credits.",
                    "usage": {"used": 950, "limit": 1000, "remaining": 50},
                },
            ),
            patch("backend.application.services.fetch_domain_stats", return_value={"results": []}),
        ):
            status, payload = self._request("POST", "/admin/scrapeops/reconciliation/run", {})

        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "completed")
        self.assertTrue(payload["alerts"])
        self.assertEqual(payload["alerts"][0]["alert_type"], "low_remaining_credits")

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
        self.assertIn(
            "section_bars",
            {item["id"] for item in settings_payload["options"]["cv_templates"]},
        )
        self.assertEqual(
            {item["id"] for item in settings_payload["options"]["cv_templates"]},
            {
                "plain",
                "section_bars",
                "modern_minimal",
                "modern_sidebar",
                "classic_executive",
            },
        )
        self.assertNotIn(
            "teal_resume",
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
                    "cv_template": "teal_resume",
                    "cv_color_scheme": "ocean_teal",
                    "cv_font": "Georgia",
                    "include_photo": False,
                    "web_cv_template": "teal_resume",
                },
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated_payload["documents"]["cv_template"], "plain")
        self.assertEqual(updated_payload["documents"]["web_cv_template"], "plain")
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

    def test_settings_and_auth_payload_hide_internal_clerk_fallback_identity(self):
        leaked_user = self.app.get_user(self.user.user_id)
        leaked_user.display_name = "user_3DtxNJbFAnuqOgglJN4MwHY6cRx"
        leaked_user.email = "user_3DtxNJbFAnuqOgglJN4MwHY6cRx@clerk.local"
        leaked_user.metadata = {
            **(leaked_user.metadata or {}),
            "profile": {
                "name": "user_3DtxNJbFAnuqOgglJN4MwHY6cRx",
                "email": "user_3DtxNJbFAnuqOgglJN4MwHY6cRx@clerk.local",
                "industry": "Fintech",
            },
        }
        self.app.repositories.auth_repository.upsert_user(leaked_user)

        status, settings_payload = self._request("GET", "/settings")
        self.assertEqual(status, 200)
        self.assertEqual(settings_payload["account"]["display_name"], "")
        self.assertEqual(settings_payload["account"]["email"], "")
        self.assertEqual(settings_payload["profile"]["name"], "")
        self.assertEqual(settings_payload["profile"]["email"], "")
        self.assertEqual(settings_payload["profile"]["industry"], "Fintech")

        status, auth_payload = self._request("GET", "/auth/me")
        self.assertEqual(status, 200)
        self.assertEqual(auth_payload["user"]["display_name"], "")
        self.assertEqual(auth_payload["user"]["email"], "")

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
                b"Languages\nArabic - Native\nEnglish - C1\nGerman - B2\n"
                b"Experience\nBusiness Analyst | Example GmbH\n2022 - Present\n"
                b"- Built dashboards\n- Improved workflow\n"
                b"Education\nMSc Operations Management | Example University\n2019 - 2021\n"
                b"- Thesis on process optimization\n"
            ),
        )
        self.assertEqual(status, 202)
        self.assertTrue(payload["asset_id"])
        self.assertTrue(payload["job_id"])
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["status_url"], f"/cv-upload/{payload['job_id']}")
        self.assertTrue(payload["asset"]["file"]["object_key"])
        self.assertTrue(self.app.object_storage.exists(payload["asset"]["file"]["object_key"]))
        self.assertEqual(payload["asset"]["file"]["path"], "")
        self.assertGreaterEqual(payload["timings_ms"]["total"], 0)

        status, queued_payload = self._request("GET", payload["status_url"])
        self.assertEqual(status, 200)
        self.assertEqual(queued_payload["status"], "queued")
        self.app.process_next_queued_run(auto_retry_failed=False)
        status, ready_payload = self._request("GET", payload["status_url"])
        self.assertEqual(status, 200)
        self.assertEqual(ready_payload["status"], "ready")
        self.assertIn(ready_payload["extraction"]["provider"], {"heuristic_fallback", "deepseek"})
        self.assertEqual(ready_payload["asset"]["metadata"]["word_companion_path"], "")
        self.assertTrue(ready_payload["asset"]["metadata"]["word_companion_object_key"])
        self.assertTrue(
            self.app.object_storage.exists(ready_payload["asset"]["metadata"]["word_companion_object_key"])
        )
        self.assertEqual(ready_payload["asset"]["metadata"]["text_extraction"]["method"], "plain_text")
        self.assertEqual(ready_payload["parsed"]["name"], "Jane Candidate")
        self.assertEqual(ready_payload["parsed"]["role_title"], "Operations Analyst")
        self.assertEqual(ready_payload["parsed"]["email"], "jane@example.com")
        self.assertIn("Excel", ready_payload["parsed"]["competencies"])
        self.assertEqual(ready_payload["parsed"]["languages"], ["Arabic - Native", "English - C1", "German - B2"])
        self.assertEqual(ready_payload["parsed"]["custom_sections"], [])
        self.assertEqual(ready_payload["parsed"]["recent_experience"][0]["title"], "Business Analyst")
        self.assertEqual(ready_payload["parsed"]["education"][0]["degree_title"], "MSc Operations Management")
        self.assertEqual(ready_payload["parsed"]["education"][0]["institution"], "Example University")

        status, _, downloaded = self._binary_request(
            "GET",
            f"/documents/assets/{payload['asset_id']}/download",
        )
        self.assertEqual(status, 200)
        self.assertIn(b"Jane Candidate", downloaded)

    def test_candidate_asset_upload_rolls_back_objects_when_metadata_persistence_fails(self):
        stored_keys: list[str] = []
        original_put = self.app.object_storage.put

        def tracked_put(key, data, **kwargs):
            stored_keys.append(key)
            return original_put(key, data, **kwargs)

        with patch.object(self.app.object_storage, "put", side_effect=tracked_put), patch.object(
            self.app.repositories.auth_repository,
            "upsert_user",
            side_effect=RuntimeError("metadata write failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "metadata write failed"):
                _store_candidate_asset_upload(
                    self.app,
                    self.user,
                    filename="rollback-resume.txt",
                    file_bytes=b"Rollback Candidate\nOperations Analyst",
                    asset_kind="workspace_cv",
                    metadata={"source_text": "Rollback Candidate\nOperations Analyst"},
                )

        self.assertEqual(len(stored_keys), 2)
        self.assertTrue(all(not self.app.object_storage.exists(key) for key in stored_keys))

    def test_cv_upload_emits_structured_redacted_stage_timings(self):
        sensitive_values = (
            "Private Candidate",
            "private.candidate@example.com",
            "secret-cv-filename.txt",
        )
        with self.assertLogs("backend.api.cv_upload", level="INFO") as captured:
            status, _ = self._multipart_request(
                "/cv-upload",
                "cv_file",
                sensitive_values[2],
                (
                    b"Private Candidate\n"
                    b"private.candidate@example.com\n"
                    b"Summary\nConfidential employment history.\n"
                ),
            )

        self.assertEqual(status, 202)
        timing_record = json.loads(captured.output[-1].split(":", 2)[-1])
        self.assertEqual(timing_record["event"], "cv_upload_timing")
        self.assertEqual(timing_record["route"], "/cv-upload")
        self.assertEqual(timing_record["outcome"], "success")
        self.assertEqual(
            set(timing_record["timings_ms"]),
            {
                "body_read",
                "multipart_parse",
                "dedupe_lookup",
                "r2_storage",
                "turso_write",
                "total",
            },
        )
        serialized_record = json.dumps(timing_record)
        for sensitive_value in sensitive_values:
            self.assertNotIn(sensitive_value, serialized_record)

    def test_cv_upload_emits_stage_timings_when_processing_fails(self):
        with self.assertLogs("backend.api.cv_upload", level="INFO") as captured:
            status, _, payload = self._request_with_headers(
                "POST",
                "/cv-upload",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                payload={"source_text": "must-not-appear-in-timing-log"},
            )

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "bad_request")
        timing_record = json.loads(captured.output[-1].split(":", 2)[-1])
        self.assertEqual(timing_record["outcome"], "failed")
        self.assertEqual(timing_record["error_type"], "ValueError")
        self.assertIsNotNone(timing_record["timings_ms"]["total"])
        self.assertNotIn("must-not-appear-in-timing-log", json.dumps(timing_record))

    def test_cv_upload_rejects_oversized_request_before_processing(self):
        status, payload = self._multipart_request(
            "/cv-upload",
            "cv_file",
            "oversized.bin",
            b"x" * (10 * 1024 * 1024 + 1),
        )

        self.assertEqual(status, 413)
        self.assertEqual(payload["error"]["code"], "request_too_large")

    def test_cv_upload_logs_timings_when_client_disconnects_during_body_read(self):
        boundary = "----runrdisconnectboundary"
        partial_body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="cv_file"; filename="private.txt"\r\n'
            "Content-Type: text/plain\r\n\r\n"
            "private-payload-must-not-be-logged"
        ).encode("latin-1")
        request_headers = (
            "POST /cv-upload HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{self.port}\r\n"
            f"Authorization: Bearer {self.access_token}\r\n"
            f"Content-Type: multipart/form-data; boundary={boundary}\r\n"
            f"Content-Length: {len(partial_body) + 100}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("latin-1")

        with self.assertLogs("backend.api.cv_upload", level="INFO") as captured:
            client = socket.create_connection(("127.0.0.1", self.port), timeout=5)
            client.sendall(request_headers + partial_body)
            client.shutdown(socket.SHUT_WR)
            client.close()
            deadline = time.monotonic() + 5
            while not captured.records and time.monotonic() < deadline:
                time.sleep(0.01)

        self.assertTrue(captured.records)
        timing_record = json.loads(captured.records[-1].getMessage())
        self.assertEqual(timing_record["outcome"], "client_disconnected")
        self.assertEqual(timing_record["error_type"], "ConnectionResetError")
        self.assertIsNotNone(timing_record["timings_ms"]["body_read"])
        self.assertIsNotNone(timing_record["timings_ms"]["total"])
        self.assertNotIn("private-payload-must-not-be-logged", json.dumps(timing_record))

    def test_cv_upload_is_idempotent_for_same_file_content(self):
        file_bytes = (
            b"Jane Candidate\n"
            b"Operations Analyst\n"
            b"Summary\nExperienced operations analyst.\n"
            b"Skills\nExcel, SQL\n"
        )
        first_status, first_payload = self._multipart_request(
            "/cv-upload",
            "cv_file",
            "structured_resume.txt",
            file_bytes,
        )
        self.assertEqual(first_status, 202)
        processed = self.app.process_next_queued_run(auto_retry_failed=False)
        self.assertEqual(processed.status, "completed")

        second_status, second_payload = self._multipart_request(
            "/cv-upload",
            "cv_file",
            "structured_resume_retry.txt",
            file_bytes,
        )

        self.assertEqual(second_status, 202)
        self.assertEqual(first_payload["asset"]["asset_id"], second_payload["asset"]["asset_id"])
        self.assertEqual(second_payload["status"], "ready")
        self.assertEqual(second_payload["job_id"], "")
        self.assertEqual(second_payload["status_url"], "")

        user = self.app.get_user(self.user.user_id)
        metadata = dict(user.metadata or {})
        assets = list(metadata.get("candidate_assets") or [])
        duplicate = json.loads(json.dumps(assets[0]))
        duplicate["asset_id"] = "asset_duplicate_retry"
        assets.append(duplicate)
        metadata["candidate_assets"] = assets
        user.metadata = metadata
        self.app.repositories.auth_repository.upsert_user(user)

        status, documents_payload = self._request("GET", "/documents?asset_kind=workspace_cv")
        self.assertEqual(status, 200)
        self.assertEqual(len(documents_payload["documents"]), 1)
        persisted_user = self.app.get_user(self.user.user_id)
        persisted_assets = (persisted_user.metadata or {}).get("candidate_assets") or []
        self.assertEqual(len(persisted_assets), 2)

    def test_cv_upload_same_filename_different_content_creates_new_asset(self):
        first_status, first_payload = self._multipart_request(
            "/cv-upload",
            "cv_file",
            "resume.txt",
            b"Jane Candidate\nSummary\nOperations analyst.\n",
        )
        self.assertEqual(first_status, 202)

        second_status, second_payload = self._multipart_request(
            "/cv-upload",
            "cv_file",
            "resume.txt",
            b"Jane Candidate\nSummary\nFinance analyst with SQL experience.\n",
        )

        self.assertEqual(second_status, 202)
        self.assertNotEqual(first_payload["asset_id"], second_payload["asset_id"])
        user = self.app.get_user(self.user.user_id)
        assets = (user.metadata or {}).get("candidate_assets") or []
        self.assertEqual(len(assets), 2)

    def test_cv_upload_status_reports_failure_after_background_processing_error(self):
        status, payload = self._multipart_request(
            "/cv-upload",
            "cv_file",
            "scanned.bin",
            b"\x00\x01\x02\x03",
        )
        self.assertEqual(status, 202)

        processed = self.app.process_next_queued_run(auto_retry_failed=False)
        self.assertEqual(processed.status, "failed")
        status, failed_payload = self._request("GET", payload["status_url"])
        self.assertEqual(status, 200)
        self.assertEqual(failed_payload["status"], "failed")
        self.assertIn("Could not extract any text", failed_payload["error"])

    def test_cv_upload_processing_retries_after_transient_extraction_failure(self):
        status, payload = self._multipart_request(
            "/cv-upload",
            "cv_file",
            "retry-resume.txt",
            b"Retry Candidate\nSummary\nReliable analyst.\n",
        )
        self.assertEqual(status, 202)

        with patch(
            "backend.profiles.cv_upload_jobs.extract_document_text",
            side_effect=[
                RuntimeError("temporary extractor outage"),
                {"text": "Retry Candidate\nSummary\nReliable analyst.", "char_count": 42, "method": "plain_text", "warnings": []},
            ],
        ):
            first_attempt = self.app.process_next_queued_run(auto_retry_failed=True)
            self.assertEqual(first_attempt.status, "queued")
            status, queued_payload = self._request("GET", payload["status_url"])
            self.assertEqual(status, 200)
            self.assertEqual(queued_payload["status"], "queued")

            second_attempt = self.app.process_next_queued_run(auto_retry_failed=True)
            self.assertEqual(second_attempt.status, "completed")

        status, ready_payload = self._request("GET", payload["status_url"])
        self.assertEqual(status, 200)
        self.assertEqual(ready_payload["status"], "ready")
        self.assertEqual(ready_payload["parsed"]["name"], "Retry Candidate")

    def test_cv_upload_status_and_documents_refresh_during_processing(self):
        status, payload = self._multipart_request(
            "/cv-upload",
            "cv_file",
            "refresh-resume.txt",
            b"Refresh Candidate\nSummary\nProcessing visibility.\n",
        )
        self.assertEqual(status, 202)

        claimed = self.app.claim_next_queued_run()
        self.assertEqual(claimed.id, payload["job_id"])
        status, processing_payload = self._request("GET", payload["status_url"])
        self.assertEqual(status, 200)
        self.assertEqual(processing_payload["status"], "processing")

        status, documents_payload = self._request("GET", "/documents?asset_kind=workspace_cv")
        self.assertEqual(status, 200)
        uploaded_cv = next(item for item in documents_payload["documents"] if item["asset_id"] == payload["asset_id"])
        self.assertEqual(uploaded_cv["display_status"], "processing")

        completed = self.app.execute_claimed_run(claimed.id, auto_retry_failed=False)
        self.assertEqual(completed.status, "completed")
        status, ready_payload = self._request("GET", payload["status_url"])
        self.assertEqual(status, 200)
        self.assertEqual(ready_payload["status"], "ready")

    def test_workspace_cv_preview_does_not_render_language_entries_as_custom_sections(self):
        preview = _build_workspace_cv_preview_profile(
            "Jane Candidate\nOperations Analyst\nLanguages\nArabic - Native\nEnglish - C1\nGerman - B1/B2\n",
            {},
            parsed_profile={
                "name": "Jane Candidate",
                "role_title": "Operations Analyst",
                "languages": ["English - C1"],
                "custom_sections": [
                    {"section_id": "custom_arabic_native_1", "heading": "Arabic - Native", "lines": []},
                    {"section_id": "custom_german_b1_b2_2", "heading": "German - B1/B2", "lines": []},
                    {
                        "section_id": "custom_publications_3",
                        "heading": "Publications",
                        "lines": ["Runr CV Parser Notes | 2026"],
                    },
                ],
            },
        )

        self.assertEqual(preview["languages"], ["English - C1", "Arabic - Native", "German - B1/B2"])
        self.assertEqual([section["heading"] for section in preview["custom_sections"]], ["Publications"])
        self.assertEqual([section["heading"] for section in preview["detected_custom_sections"]], ["Publications"])

    def test_cv_language_extraction_accepts_localized_and_inline_formats(self):
        profile = extract_cv_profile_fallback(
            "Jane Candidate\n"
            "Operations Analyst\n"
            "Sprachen\n"
            "Arabisch - Muttersprache\n"
            "Englisch - C1\n"
            "Deutsch - B1/B2\n"
            "Experience\n"
            "Business Analyst | Example GmbH\n"
        )
        self.assertEqual(
            profile["languages"],
            ["Arabisch - Muttersprache", "Englisch - C1", "Deutsch - B1/B2"],
        )
        self.assertEqual(profile["custom_sections"], [])

        inline_profile = extract_cv_profile_fallback(
            "Jane Candidate\n"
            "Operations Analyst\n"
            "Sprachkenntnisse: Englisch - C1; Deutsch - B1/B2; Arabisch - Muttersprache\n"
            "Experience\n"
            "Business Analyst | Example GmbH\n"
        )
        self.assertEqual(
            inline_profile["languages"],
            ["Englisch - C1", "Deutsch - B1/B2", "Arabisch - Muttersprache"],
        )
        self.assertEqual(inline_profile["custom_sections"], [])

        preview = _build_workspace_cv_preview_profile(
            "Jane Candidate\n"
            "Operations Analyst\n"
            "Idiomas: English - C1, German - B1/B2, Arabic - Native\n",
            {},
        )
        self.assertEqual(preview["languages"], ["English - C1", "German - B1/B2", "Arabic - Native"])
        self.assertEqual(preview["custom_sections"], [])

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

    def test_documents_upload_rejects_legacy_general_asset_types(self):
        for asset_kind in ("master_career_profile", "motivation_letter"):
            status, payload = self._multipart_request(
                f"/documents/upload?asset_kind={asset_kind}",
                "document",
                "legacy.txt",
                b"Legacy content",
            )

            self.assertEqual(status, 400)
            self.assertIn("legacy asset type", str(payload).lower())

    def test_pdf_supporting_document_uses_background_text_extraction(self):
        import fitz

        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 72), "Searchable supporting document content")
        pdf_bytes = document.tobytes()
        document.close()

        status, upload_payload = self._multipart_request(
            "/documents/upload?asset_kind=uploaded_document",
            "document",
            "supporting.pdf",
            pdf_bytes,
        )
        self.assertEqual(status, 201)
        self.assertTrue(upload_payload["job_id"])
        self.assertEqual(upload_payload["asset"]["metadata"]["status"], "queued")

        self.app.process_next_queued_run(auto_retry_failed=False)
        status, processing_payload = self._request("GET", upload_payload["status_url"])

        self.assertEqual(status, 200)
        self.assertEqual(processing_payload["status"], "ready")
        self.assertEqual(
            processing_payload["asset"]["metadata"]["text_extraction"]["method"],
            "pdf_native",
        )

    @patch.dict(os.environ, {"RUNR_DISABLE_QUOTAS": "1"}, clear=False)
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
                b"Projects\nAI Application Pipeline | 2026\n"
                b"- Automated job discovery and document generation\n"
                b"- Built CV preview extraction for project sections\n"
                b"Publications\nRunr CV Parser Notes | 2026\n"
                b"- Documented custom section handling\n"
            ),
        )
        self.assertEqual(status, 202)
        self.assertEqual(cv_payload["asset"]["asset_kind"], "workspace_cv")
        self.app.process_next_queued_run(auto_retry_failed=False)

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
        self.assertEqual(uploaded_cv["preview_profile"]["projects"][0]["title"], "AI Application Pipeline")
        self.assertEqual(uploaded_cv["preview_profile"]["projects"][0]["period"], "2026")
        self.assertIn(
            "Automated job discovery",
            uploaded_cv["preview_profile"]["projects"][0]["bulletsText"],
        )
        self.assertEqual(uploaded_cv["preview_profile"]["custom_sections"][0]["heading"], "Publications")
        self.assertIn(
            "Runr CV Parser Notes",
            uploaded_cv["preview_profile"]["custom_sections"][0]["content"],
        )

        custom_section = uploaded_cv["preview_profile"]["detected_custom_sections"][0]
        status, section_payload = self._request(
            "PUT",
            f"/documents/assets/{uploaded_cv['asset_id']}/sections",
            {
                "section_decisions": [
                    {
                        "section_id": custom_section["section_id"],
                        "heading": custom_section["heading"],
                        "action": "map",
                        "target_section": "projects",
                    }
                ]
            },
        )
        self.assertEqual(status, 200)
        mapped_profile = section_payload["document"]["preview_profile"]
        self.assertFalse(mapped_profile["custom_sections"])
        self.assertEqual(mapped_profile["detected_custom_sections"][0]["action"], "map")
        self.assertEqual(mapped_profile["projects"][-1]["title"], "Runr CV Parser Notes")
        self.assertEqual(mapped_profile["projects"][-1]["period"], "2026")

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

    def test_bulk_export_prefers_generated_cv_pdf_when_docx_is_also_selected(self):
        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "sync", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        run_id = run_payload["id"]

        docx_path = self.temp_dir / "api_job_1_CV.docx"
        pdf_path = self.temp_dir / "api_job_1_CV.pdf"
        docx_path.write_bytes(b"docx-content")
        pdf_path.write_bytes(b"%PDF-1.4 pdf-content")
        metadata = {
            "job_id": "api_job_1",
            "job_title": "Engineer",
            "company": "ACME API",
            "document_asset_kind": "generated_cv",
            "document_display_name": "Tailored CV",
            "ats_score": 94,
            "ats_target_score": 90,
            "ats_attempt_count": 1,
            "ats_max_attempts": 3,
        }
        status, _ = self._request(
            "PUT",
            f"/runs/{run_id}/artifacts/api_cv_docx",
            {"artifact_type": "cv_docx", "path": str(docx_path), "metadata": metadata},
        )
        self.assertEqual(status, 200)
        status, _ = self._request(
            "PUT",
            f"/runs/{run_id}/artifacts/api_cv_pdf",
            {"artifact_type": "cv_pdf", "path": str(pdf_path), "metadata": metadata},
        )
        self.assertEqual(status, 200)

        status, documents_payload = self._request("GET", f"/documents?run_id={run_id}")
        self.assertEqual(status, 200)
        generated_cvs = [
            item
            for item in documents_payload["documents"]
            if item["asset_kind"] == "generated_cv" and item["job_id"] == "api_job_1"
        ]
        self.assertEqual(len(generated_cvs), 2)

        status, bundle_payload = self._request(
            "POST",
            "/documents/bulk-export",
            {
                "label": "pdf_first",
                "document_ids": [item["document_id"] for item in generated_cvs],
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(bundle_payload["document_count"], 1)

        status, headers, body = self._binary_request("GET", bundle_payload["download_url"])
        self.assertEqual(status, 200)
        self.assertIn(headers.get("Content-Type"), {"application/zip", "application/x-zip-compressed"})
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertEqual(archive.namelist(), ["Tailored CV.pdf"])
            self.assertEqual(archive.read("Tailored CV.pdf"), b"%PDF-1.4 pdf-content")

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

    def test_health_endpoints_distinguish_liveness_and_readiness(self):
        status, payload = self._request("GET", "/health/live")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"status": "ok"})

        status, payload = self._request("GET", "/health/ready")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["database"]["target_backend"], "sqlite")
        self.assertEqual(payload["object_storage"]["backend"], "local")
        self.assertIn("database_select", payload["timings_ms"])

        status, payload = self._request("GET", "/health/ready?probe=1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["probes"]["database_write"], "ok")
        self.assertEqual(payload["probes"]["object_storage_write"], "ok")
        self.assertIn("database_write_read_delete", payload["timings_ms"])
        self.assertIn("object_storage_put_get_delete", payload["timings_ms"])

    def test_frontend_api_request_diagnostic_event_is_persisted(self):
        status, payload = self._request(
            "POST",
            "/analytics/events",
            {
                "event_name": "frontend_api_request_failed",
                "route": "/runs/:run_id/customer-view",
                "source": "frontend_api_request_diagnostic",
                "payload": {
                    "event": "api_request_failed",
                    "method": "GET",
                    "path": "/runs/:run_id/customer-view",
                    "status": 500,
                    "duration_ms": 20001,
                    "timeout_ms": 20000,
                    "error_name": "Error",
                    "error_code": "internal_error",
                    "aborted": False,
                },
            },
        )
        self.assertEqual(status, 202)
        self.assertEqual(payload["event_name"], "frontend_api_request_failed")

        rows = self.app.repositories.analytics_store.query_rows(
            """
            SELECT event_name, route, source, payload_json
            FROM analytics_events
            WHERE event_name = 'frontend_api_request_failed'
            ORDER BY occurred_at DESC
            LIMIT 1
            """
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["route"], "/runs/:run_id/customer-view")
        self.assertEqual(rows[0]["source"], "frontend_api_request_diagnostic")
        event_payload = json.loads(rows[0]["payload_json"])
        self.assertEqual(event_payload["status"], 500)
        self.assertEqual(event_payload["path"], "/runs/:run_id/customer-view")
        self.assertNotIn("Authorization", event_payload)
        self.assertNotIn("body", event_payload)

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

    def test_admin_promo_code_endpoints_proxy_to_creem(self):
        list_response = {
            "discounts": [
                {
                    "discount_id": "disc_1",
                    "name": "Spring campaign",
                    "code": "SPRING25",
                    "amount": 25,
                    "amount_type": "percent",
                    "max_redemptions": 100,
                    "starts_at": "2026-05-01T00:00:00+00:00",
                    "expires_at": "2026-05-31T23:59:59+00:00",
                    "status": "published",
                    "status_formatted": "Published",
                    "created_at": "2026-04-30T10:00:00+00:00",
                }
            ],
            "meta": {"current_page": 1, "per_page": 10, "total": 1},
        }
        created_discount = {
            "discount_id": "disc_2",
            "name": "Launch code",
            "code": "LAUNCH10",
            "amount": 1000,
            "amount_type": "fixed",
            "max_redemptions": 0,
            "starts_at": "",
            "expires_at": "2026-06-30T22:00:00+00:00",
            "status": "published",
            "status_formatted": "Published",
            "created_at": "2026-05-23T08:00:00+00:00",
        }
        viewer = self.app.upsert_user(
            {
                "email": "viewer@example.com",
                "display_name": "Viewer",
                "role": "viewer",
            }
        )
        _, viewer_token = self.app.issue_api_token(user_id=viewer.user_id, name="viewer-test")

        with (
            patch("backend.api.server._configured_paid_plan_product_ids", return_value=["prod_101", "prod_202", "prod_303"]),
            patch("backend.api.server._configured_paid_plan_labels", return_value="Launch, Momentum, Scale"),
            patch("backend.api.server.list_creem_discounts", return_value=list_response),
            patch("backend.api.server.create_creem_discount", return_value=created_discount) as create_mock,
            patch("backend.api.server.delete_creem_discount") as delete_mock,
        ):
            status, list_payload = self._request("GET", "/admin/promo-codes?limit=10&offset=0")
            self.assertEqual(status, 200)
            self.assertEqual(list_payload["meta"]["total"], 1)
            self.assertEqual(list_payload["promo_codes"][0]["code"], "SPRING25")
            self.assertEqual(list_payload["promo_codes"][0]["discount"], "25%")
            self.assertEqual(list_payload["promo_codes"][0]["scope"], "Launch, Momentum, Scale")

            status, create_payload = self._request(
                "POST",
                "/admin/promo-codes",
                {
                    "name": "Launch code",
                    "code": "launch10",
                    "amount_type": "fixed",
                    "amount": "10.00",
                    "expires_at": "2026-07-01T00:00:00+02:00",
                },
            )
            self.assertEqual(status, 201)
            self.assertEqual(create_payload["promo_code"]["code"], "LAUNCH10")
            self.assertEqual(create_payload["promo_code"]["discount"], "EUR 10.00")
            create_mock.assert_called_once_with(
                name="Launch code",
                code="LAUNCH10",
                amount=1000,
                amount_type="fixed",
                starts_at="",
                expires_at="2026-06-30T22:00:00+00:00",
                max_redemptions=0,
                duration="once",
                product_ids=["prod_101", "prod_202", "prod_303"],
            )

            status, delete_payload = self._request("DELETE", "/admin/promo-codes/disc_2")
            self.assertEqual(status, 200)
            self.assertEqual(delete_payload["deleted"], "disc_2")
            delete_mock.assert_called_once_with("disc_2")

            status, _, unauthorized_payload = self._request_with_headers(
                "GET",
                "/admin/promo-codes",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
            self.assertEqual(status, 403)
            self.assertEqual(unauthorized_payload["error"]["code"], "forbidden")

    def test_billing_checkout_accepts_valid_promo_code_without_logging_raw_code(self):
        with (
            patch(
                "backend.api.server.get_plan",
                return_value={
                    "display_name": "Momentum",
                    "price_eur": 25,
                    "creem_product_id": "prod_123",
                    "quotas": {},
                },
            ),
            patch(
                "backend.api.server.get_creem_checkout_url",
                return_value="https://checkout.example/session_123",
            ) as checkout_mock,
            patch.dict(os.environ, {"APP_FRONTEND_ORIGIN": "https://app.userunr.com"}),
        ):
            status, payload = self._request(
                "POST",
                "/billing/checkout",
                {
                    "plan_id": "momentum",
                    "promo_code": "summer10",
                    "source_page": "/pricing",
                },
            )
            self.assertEqual(status, 200)
            self.assertEqual(payload["checkout_url"], "https://checkout.example/session_123")
            checkout_mock.assert_called_once()
            self.assertEqual(checkout_mock.call_args.kwargs["discount_code"], "SUMMER10")
            self.assertNotIn("promo_code", checkout_mock.call_args.kwargs["custom_data"])
            self.assertEqual(
                checkout_mock.call_args.kwargs["redirect_url"],
                "https://app.userunr.com/pricing?checkout=success&plan_id=momentum",
            )

        event_rows = self.app.repositories.analytics_store.query_rows(
            "SELECT payload_json FROM analytics_events WHERE event_name = 'checkout_started'"
        )
        matching_payloads = [
            item
            for item in (json.loads(row["payload_json"]) for row in event_rows)
            if item.get("target_plan_id") == "momentum"
        ]
        self.assertTrue(matching_payloads)
        event_payload = matching_payloads[-1]
        self.assertTrue(event_payload["promo_code_present"])
        self.assertNotIn("promo_code", event_payload)

    def test_billing_checkout_rejects_invalid_promo_code_format(self):
        with patch(
            "backend.api.server.get_plan",
            return_value={
                "display_name": "Momentum",
                "price_eur": 25,
                "creem_product_id": "prod_123",
                "quotas": {},
            },
        ):
            status, payload = self._request(
                "POST",
                "/billing/checkout",
                {
                    "plan_id": "momentum",
                    "promo_code": "bad-code!",
                    "source_page": "/pricing",
                },
            )
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "bad_request")
        self.assertIn("uppercase letters and numbers", payload["error"]["message"])

    def test_billing_checkout_confirm_promotes_signed_creem_redirect(self):
        checkout_user = self.app.upsert_user(
            {
                "email": "checkout-confirm@example.com",
                "display_name": "Checkout Confirm",
                "role": "viewer",
            }
        )
        _, checkout_access_token = self.app.issue_api_token(user_id=checkout_user.user_id, name="checkout-confirm")
        raw_query = (
            "checkout=success&plan_id=momentum&checkout_id=ch_123&subscription_id=sub_123&"
            "product_id=prod_123&customer_id=cust_123&request_id=req_123"
        )
        signed_payload = raw_query.replace("&", "|")
        signature = hashlib.sha256(f"{signed_payload}|salt=creem_test_secret".encode("utf-8")).hexdigest()

        with (
            patch.dict(os.environ, {"CREEM_API_KEY": "creem_test_secret"}),
            patch("backend.api.server.get_plan_for_product_id", return_value="momentum"),
            patch("backend.api.server.update_user_plan_in_clerk"),
        ):
            status, _, payload = self._request_with_headers(
                "POST",
                "/billing/checkout/confirm",
                headers={"Authorization": f"Bearer {checkout_access_token}"},
                payload={"query_string": f"{raw_query}&signature={signature}"},
            )

        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["plan_id"], "momentum")
        subscription = self.app.repositories.auth_repository.get_current_subscription_by_user_id(checkout_user.user_id)
        self.assertEqual(subscription["plan_id"], "momentum")
        self.assertEqual(subscription["creem_subscription_id"], "sub_123")

    def test_creem_webhook_active_subscription_updates_local_subscription(self):
        webhook_user = self.app.upsert_user(
            {
                "email": "creem-webhook-active@example.com",
                "display_name": "Creem Webhook Active",
                "role": "viewer",
            }
        )
        event_payload = {
            "id": "evt_creem_active_1",
            "eventType": "subscription.active",
            "created_at": 1781870400000,
            "object": {
                "id": "sub_creem_123",
                "object": "subscription",
                "product": {"id": "prod_momentum", "name": "Momentum"},
                "customer": {
                    "id": "cust_creem_123",
                    "email": webhook_user.email,
                },
                "status": "active",
                "current_period_start_date": "2026-06-19T12:00:00.000Z",
                "current_period_end_date": "2026-07-19T12:00:00.000Z",
                "created_at": "2026-06-19T12:00:00.000Z",
                "updated_at": "2026-06-19T12:00:00.000Z",
                "metadata": {
                    "user_id": webhook_user.user_id,
                    "plan_id": "momentum",
                },
            },
        }

        with patch("backend.api.server.verify_creem_webhook_signature") as verify_mock:
            status, _, payload = self._request_with_headers(
                "POST",
                "/webhooks/creem",
                headers={"creem-signature": "test-signature"},
                payload=event_payload,
            )

        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["event_type"], "subscription.active")
        verify_mock.assert_called_once()

        subscription = self.app.repositories.auth_repository.get_current_subscription_by_user_id(webhook_user.user_id)
        self.assertEqual(subscription["billing_provider"], "creem")
        self.assertEqual(subscription["creem_subscription_id"], "sub_creem_123")
        self.assertEqual(subscription["creem_customer_id"], "cust_creem_123")
        self.assertEqual(subscription["plan_id"], "momentum")

        event_rows = self.app.repositories.analytics_store.query_rows(
            "SELECT event_name, payload_json FROM analytics_events WHERE event_name = 'subscription_started'"
        )
        matching_payloads = [
            item
            for item in (json.loads(row["payload_json"]) for row in event_rows)
            if item.get("creem_subscription_id") == "sub_creem_123"
        ]
        self.assertTrue(matching_payloads)
        event_payload = matching_payloads[-1]
        self.assertEqual(event_payload["creem_subscription_id"], "sub_creem_123")

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
        self.assertEqual(len(import_payload["contacts"]), 1)

        status, referrals_payload = self._request("GET", "/referrals")
        self.assertEqual(status, 200)
        self.assertEqual(len(referrals_payload["contacts"]), 1)
        self.assertEqual(
            [entry["company_name"] for entry in referrals_payload["contacts"][0]["companies"]],
            ["ACME API", "Contoso"],
        )
        self.assertEqual(referrals_payload["contacts"][0]["source_kind"], "linkedin_csv")

    def test_referrals_import_can_be_cleared_without_deleting_manual_contacts(self):
        status, manual_payload = self._request(
            "POST",
            "/referrals",
            {
                "name": "Manual Contact",
                "company": "Manual Co",
                "companies": [{"company_name": "Manual Co", "role_title": "", "can_refer": True}],
                "source_kind": "manual",
            },
        )
        self.assertEqual(status, 201)

        status, _ = self._request(
            "POST",
            "/referrals/import",
            {
                "csv_text": (
                    "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
                    "Jane,Referrer,https://linkedin.com/in/jane-referrer,,ACME API,Engineering Manager,01 Jan 2024\n"
                ),
                "source_kind": "linkedin_csv",
            },
        )
        self.assertEqual(status, 200)

        status, clear_payload = self._request("DELETE", "/referrals/import")
        self.assertEqual(status, 200)
        self.assertEqual(clear_payload["deleted"], 1)
        self.assertEqual(len(clear_payload["contacts"]), 1)
        self.assertEqual(clear_payload["contacts"][0]["contact_id"], manual_payload["contact_id"])

        status, referrals_payload = self._request("GET", "/referrals")
        self.assertEqual(status, 200)
        self.assertEqual(len(referrals_payload["contacts"]), 1)
        self.assertEqual(referrals_payload["contacts"][0]["source_kind"], "manual")

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

        # --- 3. GET /tracker returns the approved job as not applied until the user applies ---
        status, tracker_payload = self._request("GET", "/tracker")
        self.assertEqual(status, 200)
        items = tracker_payload.get("items", [])
        self.assertGreater(len(items), 0)
        item = next((i for i in items if i["review_id"] == review_id), None)
        self.assertIsNotNone(item, "Approved review should appear in tracker")
        self.assertEqual(item["tracker_status"], "not_applied")
        self.assertEqual(item["application_status"], "Not applied")
        self.assertFalse(item["is_test_run"])
        self.assertEqual(item["run_mode"], "normal")
        self.assertEqual(item["tracker_source_type"], "standard_run")
        self.assertFalse(item["email_confirmed"])
        self.assertFalse(item["is_explicit_application"])
        self.assertIn("excel_baseline_columns", tracker_payload)
        self.assertIn("applied?", tracker_payload["excel_baseline_columns"])
        self.assertEqual(item["tracker_table_row"]["Status"], "Not applied")
        self.assertEqual(item["tracker_table_row"]["applied?"], "Not applied")
        self.assertEqual(item["tracker_table_row"]["company"], item["company"])
        self.assertIn("full_description", item)
        self.assertEqual(item["tracker_table_row"]["full_description"], item["full_description"])
        placed_in_tracker_at = item["placed_in_tracker_at"]
        self.assertTrue(placed_in_tracker_at)
        self.assertEqual(
            self.app.get_review(review_id).metadata["placed_in_tracker_at"],
            placed_in_tracker_at,
        )
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

        # --- 4. PUT /tracker/:review_id supports manually marking the application as applied ---
        status, update_payload = self._request(
            "PUT",
            f"/tracker/{review_id}",
            {"tracker_status": "applied", "notes": "Follow up next week."},
        )
        self.assertEqual(status, 200)
        self.assertEqual(update_payload["tracker_status"], "applied")
        self.assertEqual(update_payload["application_status"], "Applied")
        self.assertFalse(update_payload["email_confirmed"])
        self.assertTrue(update_payload["is_explicit_application"])
        self.assertEqual(update_payload["notes"], "Follow up next week.")
        self.assertEqual(update_payload["placed_in_tracker_at"], placed_in_tracker_at)
        self.assertEqual(
            self.app.repositories.review_store.list_application_status_history(review_id=review_id),
            [
                {
                    "review_id": review_id,
                    "user_id": self.user.user_id,
                    "from_status": "Not applied",
                    "to_status": "Applied",
                    "changed_at": update_payload["updated_at"],
                    "source": "manual",
                }
            ],
        )

        # --- 5. GET /tracker reflects the manual Applied status ---
        status, tracker_payload2 = self._request("GET", "/tracker")
        self.assertEqual(status, 200)
        item2 = next((i for i in tracker_payload2.get("items", []) if i["review_id"] == review_id), None)
        self.assertIsNotNone(item2)
        self.assertEqual(item2["tracker_status"], "applied")
        self.assertFalse(item2["email_confirmed"])
        self.assertTrue(item2["is_explicit_application"])
        self.assertEqual(item2["tracker_table_row"]["Status"], "Applied")
        self.assertEqual(item2["notes"], "Follow up next week.")
        self.assertEqual(item2["placed_in_tracker_at"], placed_in_tracker_at)

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
        self.assertEqual(reject_payload["placed_in_tracker_at"], placed_in_tracker_at)
        self.assertEqual(
            self.app.repositories.review_store.list_application_status_history(review_id=review_id),
            [
                {
                    "review_id": review_id,
                    "user_id": self.user.user_id,
                    "from_status": "Not applied",
                    "to_status": "Applied",
                    "changed_at": update_payload["updated_at"],
                    "source": "manual",
                },
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

    def test_tracker_bulk_delete_only_removes_not_applied_jobs(self):
        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "queued", "max_attempts": 1},
        )
        self.assertEqual(status, 201)
        run_id = run_payload["id"]
        self._request("POST", "/workers/process-next", {})

        self.app.upsert_job_set(
            run_id,
            "accepted_jobs",
            [
                JobRecord(job_id="bulk_job_1", title="Bulk One", company="Bulk Co"),
                JobRecord(job_id="bulk_job_2", title="Bulk Two", company="Bulk Co"),
                JobRecord(job_id="bulk_job_3", title="Bulk Three", company="Keep Co"),
            ],
        )
        review_ids = []
        for job_id in ["bulk_job_1", "bulk_job_2", "bulk_job_3"]:
            status, review_payload = self._request(
                "POST",
                f"/runs/{run_id}/reviews",
                {"job_id": job_id, "decision": "approved", "status": "approved", "reviewer": "tester"},
            )
            self.assertEqual(status, 201)
            review_ids.append(review_payload["review_id"])

        status, applied_payload = self._request(
            "PUT",
            f"/tracker/{review_ids[2]}",
            {"tracker_status": "applied"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(applied_payload["tracker_status"], "applied")

        status, mixed_delete_payload = self._request(
            "DELETE",
            "/tracker/bulk",
            {"review_ids": [review_ids[0], review_ids[2]]},
        )
        self.assertEqual(status, 400)
        self.assertIn("Not Applied", mixed_delete_payload["error"]["message"])

        status, tracker_payload = self._request("GET", "/tracker")
        self.assertEqual(status, 200)
        self.assertTrue(any(item["review_id"] == review_ids[0] for item in tracker_payload["items"]))

        status, delete_payload = self._request(
            "DELETE",
            "/tracker/bulk",
            {"review_ids": [review_ids[0], review_ids[1]]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(delete_payload["deleted_count"], 2)
        self.assertEqual(
            sorted(item["job_id"] for item in delete_payload["deleted"]),
            ["bulk_job_1", "bulk_job_2"],
        )

        status, refreshed_tracker_payload = self._request("GET", "/tracker")
        self.assertEqual(status, 200)
        refreshed_review_ids = {item["review_id"] for item in refreshed_tracker_payload["items"]}
        self.assertNotIn(review_ids[0], refreshed_review_ids)
        self.assertNotIn(review_ids[1], refreshed_review_ids)
        self.assertIn(review_ids[2], refreshed_review_ids)

        status, jobs_payload = self._request("GET", f"/runs/{run_id}/jobs")
        self.assertEqual(status, 200)
        remaining_jobs = [
            job["job_id"]
            for jobs in jobs_payload["job_sets"].values()
            for job in jobs
        ]
        self.assertEqual(remaining_jobs, ["bulk_job_3"])

    def test_tracker_orders_newest_placement_first_after_older_job_updates(self):
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
        review = self.app.get_review(review_id)
        review.metadata = {
            **dict(review.metadata or {}),
            "placed_in_tracker_at": "2026-01-01T09:00:00+00:00",
        }
        self.app.repositories.review_store.upsert_review(review)

        user = self.app.get_user(self.user.user_id)
        user.metadata = {
            **dict(user.metadata or {}),
            "external_tracker_applications": [
                {
                    "application_id": "external_newest_tracker_job",
                    "review_id": "external_newest_tracker_job",
                    "source": "gmail_detection",
                    "title": "Newest tracker role",
                    "company": "Newest Company",
                    "tracker_status": "applied",
                    "application_status": "Applied",
                    "placed_in_tracker_at": "2026-02-01T09:00:00+00:00",
                    "created_at": "2026-02-01T09:00:00+00:00",
                    "updated_at": "2026-02-01T09:00:00+00:00",
                }
            ],
        }
        self.app.upsert_user(user)

        status, tracker_payload = self._request("GET", "/tracker")
        self.assertEqual(status, 200)
        self.assertEqual(tracker_payload["items"][0]["review_id"], "external_newest_tracker_job")

        status, update_payload = self._request(
            "PUT",
            f"/tracker/{review_id}",
            {"tracker_status": "interview_invited"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(update_payload["placed_in_tracker_at"], "2026-01-01T09:00:00+00:00")

        status, refreshed_tracker_payload = self._request("GET", "/tracker")
        self.assertEqual(status, 200)
        self.assertEqual(refreshed_tracker_payload["items"][0]["review_id"], "external_newest_tracker_job")

    def test_tracker_email_integration_api(self):
        confirm_sent_at = self._recent_tracker_timestamp(days_ago=7, hour=9)
        interview_sent_at = self._recent_tracker_timestamp(days_ago=7, hour=12)

        class _FakeMailboxClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def probe(self):
                return {"status": "connected", "folder": self.kwargs.get("folder")}

            def fetch_all_messages(self, *, start_date="", processed_ids=None):
                assert start_date == ""
                assert processed_ids == set()
                return [
                    TrackerMailboxMessage(
                        message_id="msg-confirm-1",
                        subject="ACME API application received",
                        from_address="jobs@acmeapi.com",
                        sent_at=confirm_sent_at,
                        text="We have received your application for Engineer at ACME API.",
                    ),
                    TrackerMailboxMessage(
                        message_id="msg-interview-1",
                        subject="Interview invitation from ACME API",
                        from_address="recruiting@acmeapi.com",
                        sent_at=interview_sent_at,
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
                    "auth_strategy": "legacy_imap_password",
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
            self.assertEqual(sync_payload["result"]["matched_updates"][0]["from_status"], "not_applied")
            self.assertEqual(sync_payload["result"]["matched_updates"][0]["to_status"], "email_confirmed")

        status, tracker_payload = self._request("GET", "/tracker")
        self.assertEqual(status, 200)
        item = next((entry for entry in tracker_payload["items"] if entry["review_id"] == review_id), None)
        self.assertIsNotNone(item)
        self.assertEqual(item["tracker_status"], "interview_invited")
        self.assertTrue(item["email_confirmed"])
        self.assertEqual(item["application_date"], confirm_sent_at)
        email_status_history = self.app.repositories.review_store.list_application_status_history(review_id=review_id)
        self.assertEqual(
            [
                {
                    "from_status": entry["from_status"],
                    "to_status": entry["to_status"],
                    "source": entry["source"],
                }
                for entry in email_status_history
            ],
            [
                {"from_status": "Not applied", "to_status": "Applied", "source": "gmail_sync"},
                {"from_status": "Applied", "to_status": "Interviewing", "source": "gmail_sync"},
            ],
        )
        self.assertTrue(all(entry["changed_at"] for entry in email_status_history))

        status, delete_payload = self._request("DELETE", "/tracker/email-integration")
        self.assertEqual(status, 200)
        self.assertFalse(delete_payload["integration"]["config"]["connected"])

    def test_tracker_google_email_integration_api(self):
        confirm_sent_at = self._recent_tracker_timestamp(days_ago=7, hour=9)
        interview_sent_at = self._recent_tracker_timestamp(days_ago=7, hour=12)
        false_positive_sent_at = self._recent_tracker_timestamp(days_ago=7, hour=13)

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
                            sent_at=confirm_sent_at,
                            text="We have received your application for Engineer at ACME API.",
                        ),
                        TrackerMailboxMessage(
                            message_id="gmail-interview-1",
                            subject="Interview invitation from ACME API",
                            from_address="recruiting@acmeapi.com",
                            sent_at=interview_sent_at,
                            text="We would like to invite you to interview for the Engineer role at ACME API.",
                        ),
                        TrackerMailboxMessage(
                            message_id="gmail-false-positive-1",
                            subject="Interview with the Vampire fan club update",
                            from_address="newsletter@movieclub.example",
                            sent_at=false_positive_sent_at,
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
        interview_sent_at = self._recent_tracker_timestamp(days_ago=7, hour=12)

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
                            sent_at=interview_sent_at,
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
                self.assertEqual(tracker_item["tracker_status"], "not_applied")

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
        self.assertTrue(imported["placed_in_tracker_at"])

        status, reapprove_payload = self._request(
            "POST",
            "/tracker/email-integration/detections/approve",
            {"detection": imported["gmail_detection"]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            reapprove_payload["approved"][0]["placed_in_tracker_at"],
            imported["placed_in_tracker_at"],
        )

        status, tracker_payload = self._request("GET", "/tracker")
        self.assertEqual(status, 200)
        external = next(
            (item for item in tracker_payload["items"] if item.get("application_id") == imported["application_id"]),
            None,
        )
        self.assertIsNotNone(external)
        self.assertTrue(external["external_application"])
        self.assertEqual(external["company"], "Example GmbH")
        self.assertEqual(external["placed_in_tracker_at"], imported["placed_in_tracker_at"])

        status, updated_payload = self._request(
            "PUT",
            f"/tracker/{imported['application_id']}",
            {"application_status": "Interviewing"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated_payload["application_status"], "Interviewing")
        self.assertEqual(updated_payload["placed_in_tracker_at"], imported["placed_in_tracker_at"])
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

    def test_career_memory_endpoints_extract_confirm_generate_and_version_outputs(self):
        user = self.app.get_user(self.user.user_id)
        user.metadata = {
            **dict(user.metadata or {}),
            "candidate_assets": [
                {
                    "asset_id": "asset_career_memory",
                    "asset_kind": "workspace_cv",
                    "metadata": {
                        "content_sha256": "career-memory-signature",
                        "source_text": (
                            "Built Python automation for weekly application reporting.\n"
                            "Reduced manual review time by 40 percent across the recruiting team."
                        ),
                    },
                }
            ],
        }
        self.app.repositories.auth_repository.upsert_user(user)

        status, extracted = self._request(
            "POST",
            "/career-memory/facts/extract",
            {"source_asset_ids": ["asset_career_memory"]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(extracted["created_count"], 2)
        metric = next(fact for fact in extracted["active_facts"] if fact["type"] == "metric")

        status, question = self._request("POST", "/career-memory/questions/next", {})
        self.assertEqual(status, 200)
        self.assertEqual(question["fact_id"], metric["fact_id"])
        self.assertTrue(question["requires_confirmation"])

        status, confirmed = self._request(
            "POST",
            f"/career-memory/facts/{metric['fact_id']}/confirm",
            {
                "value": metric["value"],
                "type": "metric",
                "certainty": "confirmed",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(confirmed["fact"]["version"], 2)

        status, generated = self._request(
            "POST",
            "/career-memory/outputs/generate",
            {"mode": "standard"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(generated["output"]["quality"]["status"], "passed")
        self.assertNotEqual(
            generated["output"]["cv_bullet"],
            generated["output"]["cover_letter"],
        )

        output_id = generated["output"]["output_id"]
        fact_history_before = generated["fact_history"]
        status, edited = self._request(
            "POST",
            f"/career-memory/outputs/{output_id}/regenerate",
            {
                "action": "edit",
                "cv_bullet": "Invented unsupported synergy claim.",
                "cover_letter": generated["output"]["cover_letter"],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(edited["output"]["version"], 2)
        self.assertEqual(edited["fact_history"], fact_history_before)
        self.assertIn(
            "unsupported_phrase",
            {issue["code"] for issue in edited["output"]["quality"]["issues"]},
        )

    def test_tracker_ats_detail_returns_persisted_read_only_diagnostics(self):
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
            {
                "job_id": "api_job_1",
                "decision": "approved",
                "status": "approved",
                "reviewer": "tester",
            },
        )
        self.assertEqual(status, 201)
        review = self.app.get_review(review_payload["review_id"])
        review.metadata = {
            **dict(review.metadata or {}),
            "tracker_status": "applied",
            "application_status": "Applied",
        }
        self.app.repositories.review_store.upsert_review(review)

        cv_path = self.temp_dir / "ats_detail_cv.docx"
        cv_path.write_bytes(b"ats-detail")
        status, _ = self._request(
            "PUT",
            f"/runs/{run_id}/artifacts/api_ats_detail_cv",
            {
                "artifact_type": "cv_docx",
                "path": str(cv_path),
                "metadata": {
                    "job_id": "api_job_1",
                    "job_title": "Engineer",
                    "company": "ACME API",
                    "document_asset_kind": "generated_cv",
                    "ats_best_score": 84,
                    "ats_target_score": 90,
                    "ats_attempt_count": 2,
                    "ats_max_attempts": 3,
                    "ats_stop_reason": "score_stalled",
                    "workspace_cv_asset_id": "asset_source_cv",
                    "scorer_model": "deepseek-test",
                    "prompt_version": "ats-v2",
                    "ats_attempt_history": [
                        {
                            "attempt": 1,
                            "score": 72,
                            "missing_requirements": ["SQL"],
                            "improvement_actions": ["Add grounded SQL evidence."],
                        },
                        {
                            "attempt": 2,
                            "score": 84,
                            "missing_requirements": ["German B2"],
                            "improvement_actions": ["Confirm German proficiency."],
                        },
                    ],
                    "missing_requirements": ["German B2"],
                },
            },
        )
        self.assertEqual(status, 200)

        status, detail = self._request(
            "GET",
            f"/tracker/{review.review_id}/ats",
        )
        self.assertEqual(status, 200)
        self.assertTrue(detail["read_only"])
        self.assertEqual(detail["score"]["best"], 84)
        self.assertEqual(detail["score"]["gate_state"], "blocked")
        self.assertEqual(detail["score"]["stop_reason"], "score_stalled")
        self.assertEqual(len(detail["attempt_history"]), 2)
        self.assertEqual(detail["criteria"]["missing"], ["German B2"])
        self.assertEqual(detail["identifiers"]["cv_asset_id"], "asset_source_cv")
        self.assertEqual(detail["scorer"]["model"], "deepseek-test")
        self.assertEqual(detail["recommendations"], ["Confirm German proficiency."])
        self.assertIn("does not recalculate", detail["diagnostic_limitations"])

    def test_run_customer_view_exposes_server_eta_state(self):
        status, run_payload = self._request(
            "POST",
            "/runs",
            {"workspace_id": "api_workspace", "execution_mode": "sync", "max_attempts": 1},
        )
        self.assertEqual(status, 201)

        status, customer_view = self._request(
            "GET",
            f"/runs/{run_payload['id']}/customer-view",
        )
        self.assertEqual(status, 200)
        self.assertEqual(customer_view["run"]["eta"]["state"], "unavailable")
        self.assertTrue(customer_view["run"]["eta"]["calculated_at"])


if __name__ == "__main__":
    unittest.main()
