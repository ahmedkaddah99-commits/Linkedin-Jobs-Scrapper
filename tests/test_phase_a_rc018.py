import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import create_backend
from backend.application import BackendApplication
from backend.worker import WorkerService


class WorkerRoleContractTests(unittest.TestCase):
    def _app(self, name: str):
        path = Path.cwd() / ".backend_test_tmp" / name
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return create_backend(path)

    def test_customer_worker_does_not_enter_acquisition_claims(self):
        app = self._app("rc018_customer_worker")
        worker = WorkerService(application=app, worker_id="customer-1", role="customer")

        with (
            patch.object(BackendApplication, "process_next_admin_job_import", side_effect=AssertionError("customer claimed admin import")),
            patch.object(BackendApplication, "process_next_personalized_intelligence", return_value=None) as intelligence,
            patch.object(BackendApplication, "claim_next_queued_run", return_value=None) as customer_runs,
        ):
            self.assertIsNone(worker.process_next(enqueue_scheduled_runs=False))

        intelligence.assert_called_once_with(
            worker_role="customer",
            worker_id="customer-1",
            lease_seconds=60,
        )
        customer_runs.assert_called_once()
        self.assertEqual(customer_runs.call_args.kwargs["worker_role"], "customer")

    def test_acquisition_worker_does_not_claim_customer_work(self):
        app = self._app("rc018_acquisition_worker")
        worker = WorkerService(application=app, worker_id="acquisition-1", role="acquisition")
        acquisition_result = {"import_id": "job_import_1", "status": "completed"}

        with (
            patch.object(BackendApplication, "process_next_admin_job_import", return_value=acquisition_result) as imports,
            patch.object(BackendApplication, "process_next_personalized_intelligence", side_effect=AssertionError("acquisition claimed intelligence")),
            patch.object(BackendApplication, "claim_next_queued_run", side_effect=AssertionError("acquisition claimed customer run")),
        ):
            self.assertIs(worker.process_next(), acquisition_result)

        imports.assert_called_once_with(worker_id="acquisition-1", worker_role="acquisition")

    def test_store_claims_reject_wrong_role_before_mutating_queue(self):
        app = self._app("rc018_claim_gates")
        acquisition_store = app.repositories.acquisition_store
        acquisition_store.create_job_import(
            idempotency_key="rc018-import",
            requested_by="test",
            source_ids=["fixture-source"],
            scope={},
            plan={},
        )
        self.assertIsNone(
            acquisition_store.claim_next_job_import(
                lease_owner="customer-1",
                worker_role="customer",
            )
        )
        queued_import = acquisition_store.list_job_imports(limit=10, offset=0)[0]
        self.assertEqual(queued_import["status"], "queued")
        self.assertIsNotNone(
            acquisition_store.claim_next_job_import(
                lease_owner="acquisition-1",
                worker_role="acquisition",
            )
        )

        intelligence_store = app.repositories.personalized_jobs_store
        intelligence_store.enqueue_intelligence(
            {
                "cache_id": "rc018-cache",
                "user_id": "user-1",
                "canonical_job_id": "job-1",
                "job_version_id": "version-1",
                "profile_version_id": "profile-1",
                "cv_version_id": "cv-1",
                "evidence_version_id": "evidence-1",
                "evaluator_version": "rc018",
                "input_hash": "hash-1",
                "intelligence_kind": "description",
            }
        )
        self.assertIsNone(intelligence_store.claim_next_intelligence(worker_role="acquisition"))
        self.assertIsNotNone(intelligence_store.claim_next_intelligence(worker_role="customer"))

    def test_heartbeat_exposes_role_version_capacity_and_active_task(self):
        app = self._app("rc018_heartbeat")
        worker = WorkerService(
            application=app,
            worker_id="acquisition-2",
            role="acquisition",
            worker_version="test-rc018",
            capacity_slots=2,
        )

        record = worker.heartbeat(active_task_family="acquisition")

        self.assertEqual(record.metadata["worker_role"], "acquisition")
        self.assertEqual(record.metadata["worker_version"], "test-rc018")
        self.assertEqual(record.metadata["capacity_slots"], 2)
        self.assertEqual(record.metadata["active_task_family"], "acquisition")
        self.assertEqual(record.metadata["allowed_task_families"], ["acquisition"])

    def test_customer_loop_skips_acquisition_scheduler_and_enrichment(self):
        app = self._app("rc018_customer_loop")
        worker = WorkerService(
            application=app,
            worker_id="customer-loop-1",
            role="customer",
            poll_interval_seconds=0.01,
        )

        def stop_after_poll(**_kwargs):
            worker.stop()
            return None

        with (
            patch.object(WorkerService, "process_next", side_effect=stop_after_poll),
            patch.object(BackendApplication, "maybe_run_scheduled_scrapeops_maintenance", side_effect=AssertionError("customer entered acquisition maintenance")),
            patch.object(BackendApplication, "run_due_acquisition", side_effect=AssertionError("customer entered acquisition scheduler")),
            patch.object(BackendApplication, "run_due_company_enrichment", side_effect=AssertionError("customer entered enrichment")),
        ):
            self.assertEqual(worker.run_loop(), 0)
