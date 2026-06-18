import json
import logging
import shutil
import unittest
from pathlib import Path

from backend import create_backend
from backend.domain.models import JobRecord, StageDefinition
from backend.orchestration import BaseStage, StageOutcome
from backend.worker import WorkerService, configure_worker_logging


class _WorkerSeedStage(BaseStage):
    def can_run(self, context, definition) -> bool:
        return True

    def execute(self, context, definition) -> StageOutcome:
        return StageOutcome(
            job_sets={
                definition.output_key or "accepted_jobs": [
                    JobRecord(job_id="worker_job_1", title="Operator", company="ACME Worker"),
                ]
            },
            metrics={"seeded_jobs": 1},
        )


class WorkerServiceTests(unittest.TestCase):
    def _workspace_tempdir(self, name: str) -> Path:
        path = Path.cwd() / ".backend_test_tmp" / name
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return path

    def _create_app(self, name: str):
        temp_dir = self._workspace_tempdir(name)
        app = create_backend(temp_dir)
        app.registries.stage_registry.register("test.worker_seed", _WorkerSeedStage())
        app.upsert_workflow_template(
            {
                "id": "worker_template_v1",
                "name": "Worker Template",
                "stages": [
                    StageDefinition(
                        stage_id="seed_worker_jobs",
                        stage_type="test.worker_seed",
                        name="Seed Worker Jobs",
                        output_key="accepted_jobs",
                    ).to_dict()
                ],
            }
        )
        app.upsert_workspace(
            {
                "id": "worker_workspace",
                "name": "Worker Workspace",
                "workflow_template_id": "worker_template_v1",
                "workspace_type": "custom",
                "sources": [],
            }
        )
        return app

    def test_worker_service_processes_runs_and_stops_cleanly(self):
        app = self._create_app("worker_service_process")
        run = app.enqueue_run("worker_workspace", requested_by="test-worker")

        worker = WorkerService(
            application=app,
            worker_id="worker_service_a",
            lease_seconds=6,
            poll_interval_seconds=0.1,
        )
        processed = worker.run_loop(max_runs=1, auto_retry_failed=True)

        self.assertEqual(processed, 1)
        self.assertEqual(app.get_run(run.id).status, "completed")
        worker_record = app.get_worker("worker_service_a")
        self.assertEqual(worker_record.status, "stopped")
        self.assertEqual(worker_record.current_run_id, "")

    def test_stale_worker_recovery_requeues_running_run(self):
        app = self._create_app("worker_service_recovery")
        run = app.enqueue_run("worker_workspace", requested_by="test-stale")

        claimed = app.claim_next_queued_run(worker_id="stale_worker", lease_seconds=5)
        self.assertIsNotNone(claimed)
        self.assertEqual(app.get_run(run.id).status, "running")

        worker = app.get_worker("stale_worker")
        worker.lease_expires_at = "2000-01-01T00:00:00+00:00"
        app.repositories.worker_store.upsert_worker(worker)

        recovered = app.recover_stale_workers()

        self.assertEqual(len(recovered), 1)
        self.assertEqual(app.get_worker("stale_worker").status, "stale")
        recovered_run = app.get_run(run.id)
        self.assertEqual(recovered_run.status, "queued")
        self.assertEqual(recovered_run.current_stage_id, "")

    def test_worker_service_enqueues_and_processes_due_scheduled_runs(self):
        app = self._create_app("worker_service_schedule")
        workspace_payload = app.get_workspace("worker_workspace").to_dict()
        workspace_payload["metadata"] = {
            **dict(workspace_payload.get("metadata") or {}),
            "run_schedule": {
                "enabled": True,
                "interval_days": 3,
                "next_run_at": "2000-01-01T00:00:00+00:00",
            },
        }
        app.upsert_workspace(workspace_payload)

        worker = WorkerService(
            application=app,
            worker_id="worker_service_schedule_a",
            lease_seconds=6,
            poll_interval_seconds=0.1,
        )
        processed = worker.run_loop(max_runs=1, auto_retry_failed=True)

        self.assertEqual(processed, 1)
        runs = app.list_runs(limit=10, offset=0, status="", workspace_id="worker_workspace")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].requested_by, "scheduler")
        self.assertEqual(runs[0].status, "completed")

        schedule = app.get_workspace("worker_workspace").metadata["run_schedule"]
        self.assertEqual(schedule["last_run_id"], runs[0].id)
        self.assertTrue(schedule["last_enqueued_at"])
        self.assertTrue(schedule["next_run_at"])

    def test_worker_service_writes_structured_lifecycle_logs(self):
        app = self._create_app("worker_service_structured_logging_app")
        run = app.enqueue_run("worker_workspace", requested_by="test-worker-logs")
        log_root = self._workspace_tempdir("worker_service_structured_logging_logs")
        logger = configure_worker_logging(log_dir=log_root / "logs", force=True)

        def _cleanup_worker_logger() -> None:
            for handler in list(logger.handlers):
                if getattr(handler, "_runr_worker_handler", False):
                    logger.removeHandler(handler)
                    handler.close()

        self.addCleanup(_cleanup_worker_logger)

        worker = WorkerService(
            application=app,
            worker_id="worker_service_logs_a",
            lease_seconds=6,
            poll_interval_seconds=0.1,
            logger=logging.getLogger("backend.worker.test"),
        )
        processed = worker.run_loop(max_runs=1, auto_retry_failed=True)

        self.assertEqual(processed, 1)
        log_path = log_root / "logs" / "worker.log"
        self.assertTrue(log_path.exists())
        entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        messages = {entry["message"] for entry in entries}
        self.assertIn("worker_task_start", messages)
        self.assertIn("worker_task_complete", messages)
        self.assertIn("worker_run_summary", messages)
        self.assertIn("worker_loop_stop", messages)

        task_start = next(entry for entry in entries if entry["message"] == "worker_task_start")
        self.assertEqual(task_start["run_id"], run.id)
        self.assertEqual(task_start["workspace_id"], "worker_workspace")
        self.assertEqual(task_start["worker_id"], "worker_service_logs_a")
        self.assertEqual(task_start["task_name"], "execute_run")
        self.assertIn("timestamp", task_start)

        task_complete = next(entry for entry in entries if entry["message"] == "worker_task_complete")
        self.assertEqual(task_complete["status"], "completed")
        self.assertIsInstance(task_complete["duration_ms"], int)


if __name__ == "__main__":
    unittest.main()
