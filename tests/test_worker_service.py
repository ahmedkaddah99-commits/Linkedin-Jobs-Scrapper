import shutil
import unittest
from pathlib import Path

from backend import create_backend
from backend.domain.models import JobRecord, StageDefinition
from backend.orchestration import BaseStage, StageOutcome
from backend.worker import WorkerService


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
                "workspace_type": "white_collar",
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


if __name__ == "__main__":
    unittest.main()
