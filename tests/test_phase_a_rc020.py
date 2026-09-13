import os
import json
import shutil
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from backend import create_backend
from backend.application import BackendApplication
from backend.application.customer_tasks import (
    CUSTOMER_TASK_BULK_EXPORT,
    CUSTOMER_TASK_EMAIL_SYNC,
    customer_task_idempotency_key,
    public_customer_task,
)
from backend.api.server import build_handler
from backend.worker import WorkerService


class CustomerTaskQueueTests(unittest.TestCase):
    def _app(self, name: str):
        path = Path.cwd() / ".backend_test_tmp" / name
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        os.environ.update(
            {
                "RUNR_TEST_MODE": "1",
                "RUNR_ENV": "test",
                "DATABASE_BACKEND": "sqlite",
                "TURSO_DATABASE_URL": " ",
                "TURSO_AUTH_TOKEN": " ",
            }
        )
        return create_backend(path, storage_backend="sqlite", test_mode=True)

    def test_idempotency_is_user_scoped_and_roles_cannot_claim_customer_tasks(self):
        app = self._app("rc020_idempotency")
        payload = {"document_ids": ["doc-1", "doc-2"], "label": "bundle", "export_anyway": False}
        key = customer_task_idempotency_key(
            user_id="user-a",
            task_type=CUSTOMER_TASK_BULK_EXPORT,
            payload=payload,
        )
        first = app.enqueue_customer_task(
            user_id="user-a",
            task_type=CUSTOMER_TASK_BULK_EXPORT,
            idempotency_key=key,
            payload=payload,
        )
        duplicate = app.enqueue_customer_task(
            user_id="user-a",
            task_type=CUSTOMER_TASK_BULK_EXPORT,
            idempotency_key=key,
            payload={"document_ids": ["changed"]},
        )
        other_user = app.enqueue_customer_task(
            user_id="user-b",
            task_type=CUSTOMER_TASK_BULK_EXPORT,
            idempotency_key=key,
            payload=payload,
        )

        self.assertEqual(first["task_id"], duplicate["task_id"])
        self.assertNotEqual(first["task_id"], other_user["task_id"])
        self.assertEqual(duplicate["payload"], payload)
        self.assertIsNone(
            app.repositories.personalized_jobs_store.claim_next_customer_task(
                worker_role="acquisition",
                lease_owner="wrong-role",
            )
        )
        self.assertIsNone(app.get_customer_task(first["task_id"], user_id="user-b"))

    def test_expired_customer_task_requeues_then_fenced_retry_reaches_failure(self):
        app = self._app("rc020_recovery")
        store = app.repositories.personalized_jobs_store
        queued = app.enqueue_customer_task(
            user_id="user-a",
            task_type=CUSTOMER_TASK_BULK_EXPORT,
            idempotency_key="rc020-retry",
            payload={"document_ids": ["doc-1"]},
            max_attempts=2,
        )
        first = store.claim_next_customer_task(lease_owner="worker-a", max_attempts=2)
        self.assertEqual(first["task_id"], queued["task_id"])
        with store._connect() as connection:
            connection.execute(
                "UPDATE customer_tasks SET lease_expires_at = ? WHERE task_id = ?",
                ("2000-01-01T00:00:00+00:00", first["task_id"]),
            )
        recovered = store.recover_stale_customer_tasks(now="2026-09-07T00:00:00+00:00", max_attempts=2)
        self.assertEqual(recovered[0]["state"], "queued")

        second = store.claim_next_customer_task(lease_owner="worker-b", max_attempts=2)
        stale = store.complete_customer_task(
            first["task_id"],
            state="completed",
            result={"stale": True},
            lease_owner=first["lease_owner"],
            lease_token=first["lease_token"],
            attempt_count=first["attempt_count"],
        )
        self.assertEqual(stale["state"], "running")
        self.assertEqual(stale["attempt_count"], 2)

        failed = store.complete_customer_task(
            second["task_id"],
            state="failed",
            error_code="fixture_failure",
            error_message="offline fixture failure",
            lease_owner=second["lease_owner"],
            lease_token=second["lease_token"],
            attempt_count=second["attempt_count"],
            retryable=True,
        )
        self.assertEqual(failed["state"], "failed")
        self.assertEqual(failed["error_code"], "fixture_failure")
        self.assertIsNone(store.claim_next_customer_task(lease_owner="worker-c"))

    def test_customer_worker_executes_queued_task_and_public_payload_hides_lease(self):
        app = self._app("rc020_worker")
        task = app.enqueue_customer_task(
            user_id="user-a",
            task_type=CUSTOMER_TASK_BULK_EXPORT,
            idempotency_key="rc020-worker",
            payload={"document_ids": ["doc-1"]},
        )
        worker = WorkerService(application=app, worker_id="customer-rc020", role="customer")
        with (
            patch.object(BackendApplication, "process_next_personalized_intelligence", return_value=None),
            patch(
                "backend.application.customer_tasks.execute_customer_task",
                return_value={
                    "operation": "bulk_export",
                    "bundle": {"bundle_id": "bundle-fixture", "path": "private/path.zip"},
                },
            ) as execute,
        ):
            result = worker.process_next(enqueue_scheduled_runs=False)

        execute.assert_called_once()
        self.assertEqual(result["task"]["state"], "completed")
        self.assertEqual(result["task"]["task_id"], task["task_id"])
        public = public_customer_task(result["task"])
        self.assertNotIn("lease_token", public)
        self.assertNotIn("user_id", public)
        self.assertNotIn("path", public["result"].get("bundle", {}))
        self.assertEqual(public["result"]["bundle"]["bundle_id"], "bundle-fixture")

    def test_worker_email_task_reuses_existing_provider_sync_and_persists_lifecycle(self):
        app = self._app("rc020_email_dispatch")
        user = app.upsert_user({"email": "rc020-email@example.com", "display_name": "Email", "role": "viewer"})
        task = app.enqueue_customer_task(
            user_id=user.user_id,
            task_type=CUSTOMER_TASK_EMAIL_SYNC,
            idempotency_key="rc020-email-dispatch",
            payload={"scan_window": "last_7_days", "max_messages": 10},
        )
        with (
            patch("backend.api.server._get_tracker_email_config", return_value={"auth_strategy": "legacy_imap_password", "provider_id": "gmail"}),
            patch("backend.api.server._collect_tracker_entries", return_value=[]),
            patch("backend.api.server._resolve_tracker_email_password", return_value="fixture-password"),
            patch("backend.api.server._merge_pending_tracker_detections", return_value=[]),
            patch("backend.api.server._persist_tracker_email_config", return_value=user) as persist,
            patch("backend.api.server._tracker_email_integration_payload", return_value={"config": {"connected": True}}),
            patch(
                "backend.capabilities.tracker.sync_tracker_email",
                return_value={
                    "processed_message_ids": ["message-1"],
                    "synced_at": "2026-09-07T00:00:00+00:00",
                    "summary": {"matched_messages": 1},
                    "detections": [],
                },
            ) as sync,
        ):
            result = app.process_next_customer_task(worker_id="rc020-email-worker")

        sync.assert_called_once()
        persist.assert_called_once()
        self.assertEqual(result["task"]["task_id"], task["task_id"])
        self.assertEqual(result["task"]["state"], "completed")
        self.assertEqual(result["result"]["result"]["summary"]["matched_messages"], 1)

    def test_worker_bulk_task_reuses_existing_bundle_writer(self):
        app = self._app("rc020_bulk_dispatch")
        user = app.upsert_user({"email": "rc020-bulk@example.com", "display_name": "Bulk", "role": "viewer"})
        task = app.enqueue_customer_task(
            user_id=user.user_id,
            task_type=CUSTOMER_TASK_BULK_EXPORT,
            idempotency_key="rc020-bulk-dispatch",
            payload={"document_ids": ["doc-1"], "label": "fixture"},
        )
        with patch(
            "backend.api.server._create_bulk_export_bundle",
            return_value={"bundle_id": "bundle-1", "download_url": "/documents/bulk-exports/bundle-1/download", "path": "private.zip"},
        ) as create_bundle:
            result = app.process_next_customer_task(worker_id="rc020-bulk-worker")

        create_bundle.assert_called_once()
        self.assertEqual(result["task"]["task_id"], task["task_id"])
        self.assertEqual(result["task"]["state"], "completed")
        self.assertEqual(result["result"]["bundle"]["bundle_id"], "bundle-1")

class CustomerTaskApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path.cwd() / ".backend_test_tmp" / "rc020_api"
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        self.environment = patch.dict(
            os.environ,
            {
                "RUNR_TEST_MODE": "1",
                "RUNR_ENV": "test",
                "RUNR_CUSTOMER_TASKS_ASYNC": "true",
                "DATABASE_BACKEND": "sqlite",
                "TURSO_DATABASE_URL": " ",
                "TURSO_AUTH_TOKEN": " ",
                "OBJECT_STORAGE_BACKEND": "local",
                "OBJECT_STORAGE_LOCAL_ROOT": "",
                "RUNR_DISABLE_QUOTAS": "1",
            },
            clear=False,
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.app = create_backend(self.temp_dir, storage_backend="sqlite", test_mode=True)
        self.user = self.app.upsert_user({"email": "rc020-api@example.com", "display_name": "RC020", "role": "admin"})
        _, self.access_token = self.app.issue_api_token(user_id=self.user.user_id, name="rc020-api")
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            build_handler(self.app, allowed_origins=set(), allowed_extension_origins=set()),
        )
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def _request(self, method: str, path: str, payload=None):
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        body = json.dumps(payload) if payload is not None else None
        headers = {"Authorization": f"Bearer {self.access_token}"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read().decode("utf-8")
        connection.close()
        return response.status, json.loads(raw) if raw else {}

    def test_email_sync_is_queued_idempotently_and_status_is_reloadable(self):
        status, first = self._request(
            "POST",
            "/tracker/email-integration/sync",
            {"scan_window": "last_7_days", "max_messages": 10},
        )
        self.assertEqual(status, 202)
        task_id = first["task"]["task_id"]
        self.assertEqual(first["task"]["state"], "queued")

        status, duplicate = self._request(
            "POST",
            "/tracker/email-integration/sync",
            {"scan_window": "last_7_days", "max_messages": 10},
        )
        self.assertEqual(status, 202)
        self.assertEqual(duplicate["task"]["task_id"], task_id)

        status, queued = self._request("GET", f"/tracker/email-integration/sync/{task_id}")
        self.assertEqual(status, 200)
        self.assertEqual(queued["task"]["state"], "queued")
        self.assertNotIn("lease_token", queued["task"])

        with patch(
            "backend.application.customer_tasks.execute_customer_task",
            return_value={"operation": "tracker_email_sync", "result": {"summary": {"fixture": True}}},
        ):
            result = WorkerService(application=self.app, worker_id="rc020-api-worker").process_next(
                enqueue_scheduled_runs=False
            )
        self.assertEqual(result["task"]["state"], "completed")

        status, completed = self._request("GET", f"/tracker/email-integration/sync/{task_id}")
        self.assertEqual(status, 200)
        self.assertEqual(completed["task"]["state"], "completed")
        self.assertTrue(completed["task"]["result"]["result"]["summary"]["fixture"])

    def test_bulk_export_request_is_queued_without_running_export_inline(self):
        with patch("backend.api.server._find_document_entry", side_effect=lambda _application, _user, document_id: {"document_id": document_id}):
            status, payload = self._request(
                "POST",
                "/documents/bulk-export",
                {"document_ids": ["doc-1", "doc-2"], "label": "offline-fixture"},
            )
        self.assertEqual(status, 202)
        task = payload["task"]
        self.assertEqual(task["task_type"], CUSTOMER_TASK_BULK_EXPORT)
        self.assertEqual(task["state"], "queued")
        self.assertEqual(task["status_url"], f"/documents/bulk-exports/{task['task_id']}/status")


if __name__ == "__main__":
    unittest.main()
