import json
import logging
import shutil
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend import create_backend
from backend.application.run_services import WorkerLeaseLostError
from backend.domain.models import JobRecord, StageDefinition, StageResult, WorkerRecord
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


class _CancellationAwareStage(BaseStage):
    def can_run(self, context, definition) -> bool:
        return True

    def execute(self, context, definition) -> StageOutcome:
        persisted_run = context.repositories.run_repository.get(context.run.id)
        persisted_run.status = "cancel_requested"
        context.repositories.run_repository.save(persisted_run)
        raise RuntimeError("Run cancellation requested.")


class PanicException(BaseException):
    pass


PanicException.__module__ = "pyo3_runtime"


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
                "owner_user_id": "worker_test_user",
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

    def test_worker_loop_survives_transient_database_failure(self):
        application = Mock()
        worker = WorkerService(
            application=application,
            worker_id="worker_service_transient_database",
            poll_interval_seconds=0.1,
            logger=Mock(),
        )
        recovered_run = object()

        with patch.object(
            WorkerService,
            "process_next",
            side_effect=[
                RuntimeError("Hrana returned HTTP 502: upstream forward failed"),
                recovered_run,
            ],
        ) as process_next:
            processed = worker.run_loop(max_runs=1)

        self.assertEqual(processed, 1)
        self.assertEqual(process_next.call_count, 2)
        application.stop_worker.assert_called_once_with(worker.worker_id)

    def test_worker_loop_stop_panic_does_not_mask_fatal_primary_error(self):
        for fatal_error in (KeyboardInterrupt("stop"), SystemExit(2)):
            with self.subTest(error=type(fatal_error).__name__):
                application = Mock()
                application.stop_worker.side_effect = PanicException("libsql stop cleanup panic")
                worker = WorkerService(
                    application=application,
                    worker_id=f"worker_stop_cleanup_{type(fatal_error).__name__.lower()}",
                    logger=Mock(),
                )

                with (
                    patch.object(WorkerService, "process_next", side_effect=fatal_error),
                    self.assertRaises(type(fatal_error)) as raised,
                ):
                    worker.run_loop()

                self.assertIs(raised.exception, fatal_error)
                application.stop_worker.assert_called_once_with(worker.worker_id)

    def test_worker_release_failure_does_not_mask_task_failure(self):
        application = Mock()
        application.recover_stale_workers.return_value = []
        claimed_run = Mock(
            id="run_transient_failure",
            workspace_id="workspace",
            status="running",
            attempt_count=1,
            max_attempts=3,
            queued_at="",
            started_at="",
            finished_at="",
            last_error="",
            stage_results=[],
            final_job_set_keys=[],
        )
        application.claim_next_queued_run.return_value = claimed_run
        application.execute_claimed_run.side_effect = RuntimeError(
            "HTTP 502 primary upstream forward failed"
        )
        application.release_worker.side_effect = RuntimeError("HTTP 503 cleanup failure")
        worker = WorkerService(
            application=application,
            worker_id="worker_service_cleanup_masking",
            lease_seconds=1,
            logger=Mock(),
        )

        with self.assertRaisesRegex(RuntimeError, "primary upstream"):
            worker.process_next()

    def test_worker_release_failure_does_not_mask_driver_panic(self):
        application = Mock()
        application.recover_stale_workers.return_value = []
        claimed_run = Mock(
            id="run_driver_panic",
            workspace_id="workspace",
            status="running",
            attempt_count=1,
            max_attempts=2,
            queued_at="",
            started_at="",
            finished_at="",
            last_error="",
            stage_results=[],
            final_job_set_keys=[],
        )
        application.claim_next_queued_run.return_value = claimed_run
        application.execute_claimed_run.side_effect = PanicException("libsql driver panic")
        application.release_worker.side_effect = RuntimeError("HTTP 503 cleanup failure")
        worker = WorkerService(
            application=application,
            worker_id="worker_driver_panic_cleanup",
            lease_seconds=1,
            logger=Mock(),
        )

        with self.assertRaises(PanicException):
            worker.process_next()

        application.release_worker.assert_called_once_with(worker.worker_id)

    def test_worker_heartbeat_continues_after_driver_panic(self):
        application = Mock()
        application.recover_stale_workers.return_value = []
        claimed_run = Mock(
            id="run_heartbeat_driver_panic",
            workspace_id="workspace",
            status="running",
            attempt_count=1,
            max_attempts=2,
            queued_at="",
            started_at="",
            finished_at="",
            last_error="",
            stage_results=[],
            final_job_set_keys=[],
        )
        completed_run = Mock(
            id=claimed_run.id,
            workspace_id="workspace",
            status="completed",
            attempt_count=1,
            max_attempts=2,
            queued_at="",
            started_at="",
            finished_at="2000-01-01T00:00:02+00:00",
            last_error="",
            stage_results=[],
            final_job_set_keys=[],
        )
        application.claim_next_queued_run.return_value = claimed_run
        heartbeat_recovered = threading.Event()
        heartbeat_attempts = 0

        def _heartbeat_worker(**kwargs):
            nonlocal heartbeat_attempts
            heartbeat_attempts += 1
            if heartbeat_attempts == 1:
                raise PanicException("libsql heartbeat panic")
            heartbeat_recovered.set()
            return object()

        def _execute_claimed_run(*args, **kwargs):
            if not heartbeat_recovered.wait(timeout=4):
                raise AssertionError("heartbeat did not retry after driver panic")
            return completed_run

        application.renew_worker_lease.side_effect = _heartbeat_worker
        application.execute_claimed_run.side_effect = _execute_claimed_run
        logger = Mock()
        worker = WorkerService(
            application=application,
            worker_id="worker_heartbeat_driver_panic",
            lease_seconds=1,
            logger=logger,
        )

        result = worker.process_next()

        self.assertIs(result, completed_run)
        self.assertGreaterEqual(heartbeat_attempts, 2)
        self.assertTrue(
            any(call.args == ("worker_heartbeat_failed",) for call in logger.exception.call_args_list)
        )
        application.release_worker.assert_called_once_with(worker.worker_id)

    def test_worker_stops_run_heartbeat_before_slow_completion_logging(self):
        application = Mock()
        application.recover_stale_workers.return_value = []
        claimed_run = Mock(
            id="run_complete_heartbeat",
            workspace_id="workspace",
            status="running",
            attempt_count=1,
            max_attempts=1,
            queued_at="",
            started_at="",
            finished_at="",
            last_error="",
            stage_results=[],
            final_job_set_keys=[],
        )
        completed_run = Mock(
            id=claimed_run.id,
            workspace_id="workspace",
            status="completed",
            attempt_count=1,
            max_attempts=1,
            queued_at="",
            started_at="",
            finished_at="2000-01-01T00:00:02+00:00",
            last_error="",
            stage_results=[],
            final_job_set_keys=[],
        )
        application.claim_next_queued_run.return_value = claimed_run
        application.execute_claimed_run.return_value = completed_run
        application.renew_worker_lease.side_effect = WorkerLeaseLostError("run already completed")
        logger = Mock()
        worker = WorkerService(
            application=application,
            worker_id="worker_completion_heartbeat",
            lease_seconds=1,
            logger=logger,
        )

        with patch.object(WorkerService, "_log_run_completion", side_effect=lambda **_kwargs: time.sleep(1.2)):
            result = worker.process_next()

        self.assertIs(result, completed_run)
        application.renew_worker_lease.assert_not_called()
        self.assertFalse(
            any(call.args == ("worker_lease_lost",) for call in logger.exception.call_args_list)
        )

    def test_worker_reraises_unrelated_base_exceptions_without_logging_them_as_failures(self):
        for failure in (KeyboardInterrupt(), SystemExit(2)):
            with self.subTest(failure=type(failure).__name__):
                application = Mock()
                application.recover_stale_workers.side_effect = failure
                logger = Mock()
                worker = WorkerService(
                    application=application,
                    worker_id=f"worker_{type(failure).__name__.lower()}",
                    logger=logger,
                )

                with self.assertRaises(type(failure)):
                    worker.process_next()

                logger.exception.assert_not_called()

    def test_process_next_can_skip_scheduled_run_scan_without_duplicate_idle_heartbeat(self):
        application = Mock()
        application.recover_stale_workers.return_value = []
        application.claim_next_queued_run.return_value = None
        worker = WorkerService(
            application=application,
            worker_id="worker_service_idle_poll",
            lease_seconds=1,
            logger=Mock(),
        )

        run = worker.process_next(enqueue_scheduled_runs=False)

        self.assertIsNone(run)
        application.claim_next_queued_run.assert_called_once_with(
            worker_id="worker_service_idle_poll",
            host_name=worker.host_name,
            process_id=worker.process_id,
            lease_seconds=1,
            recover_stale_workers=False,
            enqueue_scheduled_runs=False,
        )
        application.heartbeat_worker.assert_not_called()

    def test_worker_loop_throttles_scheduled_run_scan_while_idle(self):
        application = Mock()
        worker = WorkerService(
            application=application,
            worker_id="worker_service_idle_schedule_throttle",
            poll_interval_seconds=0.01,
            scheduled_run_check_interval_seconds=999,
            logger=Mock(),
        )
        scheduled_scan_flags = []

        def _idle_claim_next_queued_run(**kwargs):
            scheduled_scan_flags.append(kwargs.get("enqueue_scheduled_runs"))
            if len(scheduled_scan_flags) >= 2:
                worker.stop()
            return None

        application.recover_stale_workers.return_value = []
        application.claim_next_queued_run.side_effect = _idle_claim_next_queued_run

        with patch("backend.worker.service.time.monotonic", return_value=0.0):
            processed = worker.run_loop(auto_retry_failed=True)

        self.assertEqual(processed, 0)
        self.assertEqual(scheduled_scan_flags, [True, False])
        application.stop_worker.assert_called_once_with(worker.worker_id)

    def test_worker_loop_checks_scheduled_runs_again_after_interval(self):
        application = Mock()
        worker = WorkerService(
            application=application,
            worker_id="worker_service_idle_schedule_recheck",
            poll_interval_seconds=0.02,
            scheduled_run_check_interval_seconds=0.01,
            logger=Mock(),
        )
        scheduled_scan_flags = []

        def _idle_claim_next_queued_run(**kwargs):
            scheduled_scan_flags.append(kwargs.get("enqueue_scheduled_runs"))
            if len(scheduled_scan_flags) >= 2:
                worker.stop()
            return None

        application.recover_stale_workers.return_value = []
        application.claim_next_queued_run.side_effect = _idle_claim_next_queued_run
        with patch("backend.worker.service.time.monotonic", side_effect=[0.0, 0.2]):
            processed = worker.run_loop(auto_retry_failed=True)

        self.assertEqual(processed, 0)
        self.assertEqual(scheduled_scan_flags, [True, True])
        application.stop_worker.assert_called_once_with(worker.worker_id)

    def test_worker_acquisition_kill_switch_poll_is_not_logged_as_cycle_complete(self):
        app = self._create_app("worker_acquisition_kill_switch_logging")
        logger = Mock()
        worker = WorkerService(
            application=app,
            worker_id="worker_acquisition_kill_switch",
            poll_interval_seconds=0.01,
            logger=logger,
        )

        def stop_after_poll(**_kwargs):
            worker.stop()
            return None

        with patch.object(WorkerService, "process_next", side_effect=stop_after_poll):
            self.assertEqual(worker.run_loop(), 0)

        messages = [call.args[0] for call in (*logger.info.call_args_list, *logger.warning.call_args_list)]
        self.assertIn("worker_acquisition_scheduler_poll", messages)
        self.assertIn("worker_acquisition_kill_switch_blocked", messages)
        self.assertNotIn("worker_acquisition_cycle_complete", messages)

    def test_worker_acquisition_noop_poll_is_not_logged_as_cycle_complete(self):
        app = self._create_app("worker_acquisition_noop_logging")
        for key, value in {
            "acquisition.phase_a.kill_switch": False,
            "acquisition.phase_a.scheduler_enabled": True,
            "acquisition.phase_a.global_enabled": True,
        }.items():
            app.repositories.config_store.set_value(key, value)
        logger = Mock()
        worker = WorkerService(
            application=app,
            worker_id="worker_acquisition_noop",
            poll_interval_seconds=0.01,
            logger=logger,
        )

        def stop_after_poll(**_kwargs):
            worker.stop()
            return None

        with patch.object(WorkerService, "process_next", side_effect=stop_after_poll):
            self.assertEqual(worker.run_loop(), 0)

        messages = [call.args[0] for call in (*logger.info.call_args_list, *logger.warning.call_args_list)]
        self.assertIn("worker_acquisition_scheduler_poll", messages)
        self.assertIn("worker_acquisition_scheduler_noop", messages)
        self.assertNotIn("worker_acquisition_cycle_complete", messages)
        self.assertEqual(app.list_acquisition_cycles(), [])

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

    def test_stale_worker_recovery_does_not_overwrite_concurrently_renewed_lease(self):
        app = self._create_app("worker_service_renewed_lease_race")
        run = app.enqueue_run("worker_workspace", requested_by="test-renewed-lease-race")
        worker_id = "renewed_lease_worker"
        claimed = app.claim_next_queued_run(worker_id=worker_id, lease_seconds=5)
        self.assertIsNotNone(claimed)
        stale_run = app.get_run(run.id)
        stale_run.updated_at = "2000-01-01T00:00:00+00:00"
        app.repositories.run_repository.save(stale_run)
        expired_worker = app.get_worker(worker_id)
        expired_worker.lease_expires_at = "2000-01-01T00:00:00+00:00"
        app.repositories.worker_store.upsert_worker(expired_worker)
        original_mark_stale = app.repositories.worker_store.mark_stale_if_expired

        def _renew_then_mark_stale(worker, **kwargs):
            app.renew_worker_lease(
                worker_id=worker_id,
                current_run_id=run.id,
                run_attempt_count=claimed.attempt_count,
                lease_seconds=3600,
            )
            return original_mark_stale(worker, **kwargs)

        with patch.object(
            app.repositories.worker_store,
            "mark_stale_if_expired",
            side_effect=_renew_then_mark_stale,
        ) as mark_stale:
            recovered = app.recover_stale_workers()

        self.assertEqual(recovered, [])
        mark_stale.assert_called_once()
        current_worker = app.get_worker(worker_id)
        self.assertEqual(current_worker.status, "running")
        self.assertEqual(current_worker.current_run_id, run.id)
        self.assertGreater(current_worker.lease_expires_at, expired_worker.lease_expires_at)
        self.assertEqual(app.get_run(run.id).status, "running")

    def test_running_heartbeat_renews_only_the_observed_run_attempt(self):
        app = self._create_app("worker_service_attempt_bound_heartbeat")
        run = app.enqueue_run("worker_workspace", requested_by="test-attempt-bound-heartbeat")
        worker_id = "attempt_bound_worker"
        claimed = app.claim_next_queued_run(worker_id=worker_id, lease_seconds=5)
        self.assertIsNotNone(claimed)
        observed = app.get_worker(worker_id)

        renewed = app.renew_worker_lease(
            worker_id=worker_id,
            current_run_id=run.id,
            run_attempt_count=claimed.attempt_count,
            lease_seconds=3600,
        )

        self.assertEqual(renewed.status, "running")
        self.assertEqual(renewed.current_run_id, run.id)
        self.assertEqual(renewed.metadata["run_attempt_count"], claimed.attempt_count)
        self.assertGreater(renewed.lease_expires_at, observed.lease_expires_at)
        with self.assertRaises(WorkerLeaseLostError):
            app.renew_worker_lease(
                worker_id=worker_id,
                current_run_id=run.id,
                run_attempt_count=claimed.attempt_count + 1,
                lease_seconds=3600,
            )

    def test_stale_worker_recovery_terminally_cancels_cancel_requested_run(self):
        app = self._create_app("worker_service_cancel_requested_recovery")
        run = app.enqueue_run("worker_workspace", requested_by="test-cancel-requested-recovery")
        worker_id = "cancel_requested_worker"
        claimed = app.claim_next_queued_run(worker_id=worker_id, lease_seconds=5)
        self.assertIsNotNone(claimed)
        inflight_run = app.get_run(run.id)
        inflight_run.current_stage_id = "seed_worker_jobs"
        inflight_run.metadata["progress"] = {"message": "working"}
        app.repositories.run_repository.save(inflight_run)
        cancel_requested = app.cancel_run(run.id)
        self.assertEqual(cancel_requested.status, "cancel_requested")
        expired_worker = app.renew_worker_lease(
            worker_id=worker_id,
            current_run_id=run.id,
            run_attempt_count=claimed.attempt_count,
            lease_seconds=60,
        )
        expired_worker.lease_expires_at = "2000-01-01T00:00:00+00:00"
        app.repositories.worker_store.upsert_worker(expired_worker)

        recovered = app.recover_stale_workers()

        self.assertEqual([worker.worker_id for worker in recovered], [worker_id])
        cancelled = app.get_run(run.id)
        self.assertEqual(cancelled.status, "cancelled")
        self.assertEqual(cancelled.current_stage_id, "")
        self.assertEqual(cancelled.last_error, "")
        self.assertTrue(cancelled.finished_at)
        self.assertNotIn("progress", cancelled.metadata)
        self.assertEqual(app.get_worker(worker_id).status, "stale")

    def test_orphan_recovery_terminally_cancels_legacy_run_without_queued_at(self):
        app = self._create_app("worker_service_legacy_cancel_requested_recovery")
        run = app.start_run("worker_workspace", execute=False, requested_by="legacy-sync-run")
        legacy_run = app.get_run(run.id)
        legacy_run.status = "cancel_requested"
        legacy_run.queued_at = ""
        legacy_run.started_at = "2000-01-01T00:00:00+00:00"
        legacy_run.updated_at = "2000-01-01T00:00:00+00:00"
        legacy_run.current_stage_id = "seed_worker_jobs"
        legacy_run.metadata["progress"] = {"message": "stopping"}
        app.repositories.run_repository.save(legacy_run)

        recovered_workers = app.recover_stale_workers()

        self.assertEqual(recovered_workers, [])
        cancelled = app.get_run(run.id)
        self.assertEqual(cancelled.status, "cancelled")
        self.assertEqual(cancelled.current_stage_id, "")
        self.assertTrue(cancelled.finished_at)
        self.assertNotIn("progress", cancelled.metadata)

    def test_stage_cancellation_exception_finishes_as_cancelled_not_failed(self):
        app = self._create_app("worker_service_cooperative_cancellation")
        app.registries.stage_registry.register("test.cancellation_aware", _CancellationAwareStage())
        app.upsert_workflow_template(
            {
                "id": "cancellation_template_v1",
                "name": "Cancellation Template",
                "stages": [
                    StageDefinition(
                        stage_id="wait_for_cancellation",
                        stage_type="test.cancellation_aware",
                        name="Wait for Cancellation",
                    ).to_dict()
                ],
            }
        )
        workspace = app.get_workspace("worker_workspace")
        workspace.workflow_template_id = "cancellation_template_v1"
        app.upsert_workspace(workspace)
        run = app.enqueue_run("worker_workspace", requested_by="test-cooperative-cancellation")

        result = app.process_next_queued_run(auto_retry_failed=False)

        self.assertEqual(result.id, run.id)
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(result.last_error, "")
        self.assertTrue(result.finished_at)
        self.assertEqual(result.stage_results[-1].status, "cancelled")
        self.assertEqual(result.stage_results[-1].metrics, {"reason": "cancel_requested"})

    def test_stale_recovery_requeues_orphaned_running_run_from_beginning(self):
        app = self._create_app("worker_service_orphaned_running")
        run = app.enqueue_run("worker_workspace", requested_by="test-orphaned-running")

        claimed = app.claim_next_queued_run(worker_id="orphaned_worker", lease_seconds=60)
        self.assertIsNotNone(claimed)
        orphaned_run = app.get_run(run.id)
        orphaned_run.updated_at = "2000-01-01T00:00:00+00:00"
        app.repositories.run_repository.save(orphaned_run)
        worker = app.get_worker("orphaned_worker")
        worker.current_run_id = ""
        worker.status = "idle"
        app.repositories.worker_store.upsert_worker(worker)

        recovered_workers = app.recover_stale_workers()

        self.assertEqual(recovered_workers, [])
        recovered_run = app.get_run(run.id)
        self.assertEqual(recovered_run.status, "queued")
        self.assertEqual(recovered_run.current_stage_id, "")
        self.assertEqual(recovered_run.stage_results, [])
        self.assertEqual(recovered_run.started_at, "")
        self.assertEqual(recovered_run.last_error, "Recovered from orphaned running run.")

    def test_stale_recovery_preserves_completed_stage_results_for_orphaned_run(self):
        app = self._create_app("worker_service_orphaned_partial_progress")
        app.upsert_workflow_template(
            {
                "id": "worker_template_v1",
                "name": "Worker Template",
                "stages": [
                    StageDefinition(
                        stage_id="seed_worker_jobs",
                        stage_type="test.worker_seed",
                        name="Seed Worker Jobs",
                        output_key="seeded_jobs",
                    ).to_dict(),
                    StageDefinition(
                        stage_id="finish_worker_jobs",
                        stage_type="test.worker_seed",
                        name="Finish Worker Jobs",
                        output_key="accepted_jobs",
                    ).to_dict(),
                ],
            }
        )
        run = app.enqueue_run("worker_workspace", requested_by="test-orphaned-partial")

        claimed = app.claim_next_queued_run(worker_id="orphaned_partial_worker", lease_seconds=60)
        self.assertIsNotNone(claimed)
        completed_result = StageResult(
            stage_id="seed_worker_jobs",
            stage_type="test.worker_seed",
            status="completed",
            started_at="2000-01-01T00:00:00+00:00",
            finished_at="2000-01-01T00:00:01+00:00",
            metrics={"seeded_jobs": 1},
            output_keys=["seeded_jobs"],
        )
        orphaned_run = app.get_run(run.id)
        orphaned_run.stage_results = [completed_result]
        orphaned_run.current_stage_id = "finish_worker_jobs"
        orphaned_run.updated_at = "2000-01-01T00:00:02+00:00"
        app.repositories.run_repository.save(orphaned_run)
        worker = app.get_worker("orphaned_partial_worker")
        worker.current_run_id = ""
        worker.status = "idle"
        app.repositories.worker_store.upsert_worker(worker)

        app.recover_stale_workers()

        recovered_run = app.get_run(run.id)
        self.assertEqual(recovered_run.status, "queued")
        self.assertEqual(
            [result.to_dict() for result in recovered_run.stage_results],
            [completed_result.to_dict()],
        )
        self.assertEqual(recovered_run.last_error, "Recovered from orphaned running run.")

    def test_stale_recovery_does_not_requeue_run_owned_by_live_worker(self):
        app = self._create_app("worker_service_live_owned_running")
        run = app.enqueue_run("worker_workspace", requested_by="test-live-owned-running")

        claimed = app.claim_next_queued_run(worker_id="live_worker", lease_seconds=3600)
        self.assertIsNotNone(claimed)
        owned_run = app.get_run(run.id)
        owned_run.updated_at = "2000-01-01T00:00:00+00:00"
        app.repositories.run_repository.save(owned_run)
        app.heartbeat_worker(
            worker_id="expired_duplicate_owner",
            status="running",
            current_run_id=run.id,
            lease_seconds=60,
        )
        expired_worker = app.get_worker("expired_duplicate_owner")
        expired_worker.lease_expires_at = "2000-01-01T00:00:00+00:00"
        app.repositories.worker_store.upsert_worker(expired_worker)

        with patch(
            "backend.application.run_services.RunLifecycleService._live_owned_run_ids",
            return_value=set(),
        ):
            recovered_workers = app.recover_stale_workers()

        self.assertEqual(
            [worker.worker_id for worker in recovered_workers],
            ["expired_duplicate_owner"],
        )
        untouched_run = app.get_run(run.id)
        self.assertEqual(untouched_run.status, "running")
        self.assertNotEqual(untouched_run.last_error, "Recovered from orphaned running run.")
        self.assertEqual(app.get_worker("live_worker").current_run_id, run.id)

    def test_stale_recovery_rechecks_live_owners_after_worker_cleanup(self):
        app = self._create_app("worker_service_owner_recheck")
        run = app.enqueue_run("worker_workspace", requested_by="test-owner-recheck")
        claimed = app.claim_next_queued_run(worker_id="owner_recheck_worker", lease_seconds=60)
        self.assertIsNotNone(claimed)
        orphaned_run = app.get_run(run.id)
        orphaned_run.updated_at = "2000-01-01T00:00:00+00:00"
        app.repositories.run_repository.save(orphaned_run)
        worker = app.get_worker("owner_recheck_worker")
        worker.current_run_id = ""
        worker.status = "idle"
        app.repositories.worker_store.upsert_worker(worker)

        with patch(
            "backend.application.run_services.RunLifecycleService._live_owned_run_ids",
            side_effect=[set(), {run.id}],
        ) as live_owner_scan:
            app.recover_stale_workers()

        self.assertEqual(live_owner_scan.call_count, 2)
        self.assertEqual(app.get_run(run.id).status, "running")

    def test_stale_recovery_snapshot_cannot_overwrite_reclaimed_run(self):
        app = self._create_app("worker_service_stale_snapshot_cas")
        run = app.enqueue_run("worker_workspace", requested_by="test-stale-snapshot")
        first_claim = app.claim_next_queued_run(worker_id="orphaned_snapshot_worker", lease_seconds=60)
        self.assertIsNotNone(first_claim)
        stale_snapshot = app.get_run(run.id)
        stale_snapshot.updated_at = "2000-01-01T00:00:00+00:00"
        app.repositories.run_repository.save(stale_snapshot)
        worker = app.get_worker("orphaned_snapshot_worker")
        worker.current_run_id = ""
        worker.status = "idle"
        app.repositories.worker_store.upsert_worker(worker)

        app.recover_stale_workers()
        reclaimed = app.claim_next_queued_run(worker_id="replacement_worker", lease_seconds=3600)
        self.assertIsNotNone(reclaimed)
        self.assertEqual(reclaimed.attempt_count, 2)
        app.stop_worker("replacement_worker")

        with patch.object(app.repositories.run_repository, "list_runs", return_value=[stale_snapshot]):
            app._run_lifecycle_service._recover_orphaned_running_runs(
                now="2030-01-01T00:00:00+00:00",
                live_owned_run_ids=set(),
            )

        current = app.get_run(run.id)
        self.assertEqual(current.status, "running")
        self.assertEqual(current.attempt_count, 2)
        self.assertEqual(current.updated_at, reclaimed.updated_at)
        self.assertEqual(app.get_worker("replacement_worker").current_run_id, "")

    def test_stale_worker_recovery_finalizes_run_with_completed_stage_results(self):
        app = self._create_app("worker_service_completed_stage_recovery")
        run = app.enqueue_run("worker_workspace", requested_by="test-stale-completed")
        worker_id = "stale_completed_worker"

        claimed = app.claim_next_queued_run(worker_id=worker_id, lease_seconds=5)
        self.assertIsNotNone(claimed)
        completed = app.execute_claimed_run(claimed.id)
        self.assertEqual(completed.status, "completed")
        self.assertEqual(len(completed.stage_results), 1)

        stale_run = app.get_run(run.id)
        stale_run.status = "running"
        stale_run.current_stage_id = stale_run.stage_results[-1].stage_id
        stale_run.finished_at = ""
        stale_run.metadata["progress"] = {"message": "final save did not stick"}
        app.repositories.run_repository.save(stale_run)

        worker = app.get_worker(worker_id)
        worker.current_run_id = run.id
        worker.status = "running"
        worker.lease_expires_at = "2000-01-01T00:00:00+00:00"
        app.repositories.worker_store.upsert_worker(worker)

        recovered = app.recover_stale_workers()

        self.assertEqual(len(recovered), 1)
        recovered_run = app.get_run(run.id)
        self.assertEqual(recovered_run.status, "completed")
        self.assertEqual(recovered_run.current_stage_id, "")
        self.assertTrue(recovered_run.finished_at)
        self.assertNotIn("progress", recovered_run.metadata)

    def test_stale_completed_run_rejects_heartbeat_after_recovery_transition(self):
        app = self._create_app("worker_service_completed_renewal_race")
        run = app.enqueue_run("worker_workspace", requested_by="test-completed-renewal-race")
        worker_id = "completed_renewal_worker"
        claimed = app.claim_next_queued_run(worker_id=worker_id, lease_seconds=5)
        self.assertIsNotNone(claimed)
        completed = app.execute_claimed_run(claimed.id)
        self.assertEqual(completed.status, "completed")
        stale_run = app.get_run(run.id)
        stale_run.status = "running"
        stale_run.current_stage_id = stale_run.stage_results[-1].stage_id
        stale_run.finished_at = ""
        stale_run.updated_at = "2000-01-01T00:00:00+00:00"
        stale_run.metadata["progress"] = {"message": "final save did not stick"}
        app.repositories.run_repository.save(stale_run)
        expired_worker = app.get_worker(worker_id)
        expired_worker.current_run_id = run.id
        expired_worker.status = "running"
        expired_worker.lease_expires_at = "2000-01-01T00:00:00+00:00"
        app.repositories.worker_store.upsert_worker(expired_worker)
        original_transition = app.repositories.run_repository.save_recovery_transition_if_stale
        renewal_results = []

        def _transition_then_renew(recovered_run, **kwargs):
            transitioned = original_transition(recovered_run, **kwargs)
            self.assertTrue(transitioned)
            renewed_worker = WorkerRecord.from_dict(expired_worker.to_dict())
            renewed_worker.last_heartbeat_at = "2040-01-01T00:00:00+00:00"
            renewed_worker.lease_expires_at = "2040-01-01T01:00:00+00:00"
            renewal_results.append(
                app.repositories.worker_store.renew_worker_lease_if_owned(
                    expired_worker,
                    renewed_worker,
                    run_attempt_count=claimed.attempt_count,
                )
            )
            return transitioned

        with patch.object(
            app.repositories.run_repository,
            "save_recovery_transition_if_stale",
            side_effect=_transition_then_renew,
        ) as transition:
            recovered = app.recover_stale_workers()

        self.assertEqual([worker.worker_id for worker in recovered], [worker_id])
        transition.assert_called_once()
        self.assertEqual(renewal_results, [False])
        current = app.get_run(run.id)
        self.assertEqual(current.status, "completed")
        self.assertEqual(current.current_stage_id, "")
        self.assertNotIn("progress", current.metadata)
        current_worker = app.get_worker(worker_id)
        self.assertEqual(current_worker.status, "stale")
        self.assertEqual(current_worker.current_run_id, "")

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
