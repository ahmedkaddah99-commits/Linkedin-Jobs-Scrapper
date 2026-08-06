from __future__ import annotations

import logging
import os
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from backend.application import BackendApplication
from backend.application.run_services import WorkerLeaseLostError
from backend.database.connection import transient_database_error_category
from backend.domain.models import (
    RUN_STATUS_CANCEL_REQUESTED,
    RUN_STATUS_CANCELLED,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    WORKER_STATUS_IDLE,
    WORKER_STATUS_RUNNING,
    RunRecord,
)


def _is_handled_worker_failure(exc: BaseException) -> bool:
    return isinstance(exc, Exception) or transient_database_error_category(exc) is not None


def _direct_database_error_category(exc: BaseException) -> str | None:
    """Classify cleanup itself without a primary exception from its implicit context."""

    cause = exc.__cause__
    context = exc.__context__
    try:
        exc.__cause__ = None
        exc.__context__ = None
        return transient_database_error_category(exc)
    finally:
        exc.__cause__ = cause
        exc.__context__ = context


def _is_handled_worker_cleanup_failure(exc: BaseException) -> bool:
    return isinstance(exc, Exception) or _direct_database_error_category(exc) is not None


@dataclass(slots=True)
class WorkerService:
    application: BackendApplication
    worker_id: str
    host_name: str = field(default_factory=socket.gethostname)
    process_id: int = field(default_factory=os.getpid)
    lease_seconds: int = 60
    poll_interval_seconds: float = 5.0
    scheduled_run_check_interval_seconds: float = 60.0
    company_enrichment_check_interval_seconds: float = 300.0
    slow_task_warning_seconds: float = 300.0
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("backend.worker.service"))
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False, repr=False)

    def _log_extra(
        self,
        *,
        task_name: str,
        run: RunRecord | None = None,
        duration_ms: int | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        extra: dict[str, Any] = {
            "worker_id": self.worker_id,
            "host_name": self.host_name,
            "worker_process_id": self.process_id,
            "task_name": task_name,
            "lease_seconds": self.lease_seconds,
        }
        if duration_ms is not None:
            extra["duration_ms"] = duration_ms
        if run is not None:
            extra.update(
                {
                    "run_id": run.id,
                    "workspace_id": run.workspace_id,
                    "status": run.status,
                    "attempt_count": run.attempt_count,
                    "max_attempts": run.max_attempts,
                    "queued_at": run.queued_at,
                    "started_at": run.started_at,
                    "finished_at": run.finished_at,
                    "has_error": bool(str(run.last_error or "").strip()),
                    "stage_count": len(run.stage_results),
                    "job_set_count": len(run.final_job_set_keys),
                    "artifact_count": sum(len(stage.artifact_ids) for stage in run.stage_results),
                }
            )
        extra.update(fields)
        return extra

    def _log_run_completion(self, *, claimed_run: RunRecord, result: RunRecord, duration_ms: int) -> None:
        extra = self._log_extra(task_name="execute_run", run=result, duration_ms=duration_ms)
        if result.status == RUN_STATUS_COMPLETED:
            self.logger.info("worker_task_complete", extra=extra)
        elif result.status in {RUN_STATUS_CANCEL_REQUESTED, RUN_STATUS_CANCELLED}:
            self.logger.warning("worker_task_cancelled", extra=extra)
        elif result.status == RUN_STATUS_FAILED:
            self.logger.error(
                "worker_task_failed",
                extra={
                    **extra,
                    "error_message": result.last_error or "Run failed without a recorded error.",
                },
            )
        else:
            self.logger.warning("worker_task_finished_unexpected_status", extra=extra)

        if duration_ms >= int(max(0.0, self.slow_task_warning_seconds) * 1000):
            self.logger.warning("worker_task_slow", extra=extra)

        self.logger.info(
            "worker_run_summary",
            extra={
                **self._log_extra(task_name="run_summary", run=result, duration_ms=duration_ms),
                "claimed_status": claimed_run.status,
            },
        )

    def _log_acquisition_result(self, result: dict[str, Any] | None) -> None:
        cycle = result.get("cycle") if isinstance(result, dict) else None
        cycle = cycle if isinstance(cycle, dict) else {}
        cycle_id = str(cycle.get("cycle_id") or "").strip()
        status = str(cycle.get("status") or (result or {}).get("status") or "").strip()
        extra = self._log_extra(
            task_name="scheduled_acquisition",
            acquisition_status=status or "no_op",
            acquisition_cycle_ran=bool(cycle_id),
            acquisition_cycle_id=cycle_id,
        )
        self.logger.info("worker_acquisition_scheduler_poll", extra=extra)

        if not cycle_id:
            if status == "kill_switch":
                self.logger.warning("worker_acquisition_kill_switch_blocked", extra=extra)
            elif status in {"disabled", "scheduler_disabled"}:
                self.logger.info("worker_acquisition_scheduler_disabled", extra=extra)
            else:
                self.logger.info("worker_acquisition_scheduler_noop", extra=extra)
            return

        if status == "recovery_required":
            self.logger.warning("worker_acquisition_cycle_recovery_required", extra=extra)
        elif status in {"completed", "degraded"}:
            self.logger.info("worker_acquisition_cycle_complete", extra=extra)
        else:
            self.logger.error("worker_acquisition_cycle_failed", extra=extra)

    def heartbeat(self, *, status: str = WORKER_STATUS_IDLE, current_run_id: str = ""):
        return self.application.heartbeat_worker(
            worker_id=self.worker_id,
            status=status,
            current_run_id=current_run_id,
            host_name=self.host_name,
            process_id=self.process_id,
            lease_seconds=self.lease_seconds,
        )

    def renew_run_lease(self, run: RunRecord):
        return self.application.renew_worker_lease(
            worker_id=self.worker_id,
            current_run_id=run.id,
            run_attempt_count=run.attempt_count,
            host_name=self.host_name,
            process_id=self.process_id,
            lease_seconds=self.lease_seconds,
        )

    def stop(self) -> None:
        self._stop_event.set()

    def process_next(
        self,
        *,
        auto_retry_failed: bool = True,
        enqueue_scheduled_runs: bool = True,
    ):
        try:
            recovered_workers = self.application.recover_stale_workers()
        except BaseException as exc:
            if not _is_handled_worker_failure(exc):
                raise
            self.logger.exception(
                "worker_recover_stale_failed",
                extra=self._log_extra(task_name="recover_stale_workers"),
            )
            raise
        if recovered_workers:
            self.logger.warning(
                "worker_recovered_stale_runs",
                extra=self._log_extra(
                    task_name="recover_stale_workers",
                    recovered_worker_count=len(recovered_workers),
                ),
            )

        # Personalized job intelligence has its own durable queue.  It is
        # deliberately processed before run claims so GET requests can only
        # enqueue pending work and never execute a model inline.
        if isinstance(self.application, BackendApplication):
            intelligence_result = self.application.process_next_personalized_intelligence()
            if intelligence_result is not None:
                self.logger.info(
                    "worker_intelligence_task_complete",
                    extra=self._log_extra(task_name="personalized_job_intelligence", cache_id=intelligence_result.get("cache_id")),
                )
                return intelligence_result

        try:
            claimed_run = self.application.claim_next_queued_run(
                worker_id=self.worker_id,
                host_name=self.host_name,
                process_id=self.process_id,
                lease_seconds=self.lease_seconds,
                recover_stale_workers=False,
                enqueue_scheduled_runs=enqueue_scheduled_runs,
            )
        except BaseException as exc:
            if not _is_handled_worker_failure(exc):
                raise
            self.logger.exception(
                "worker_claim_failed",
                extra=self._log_extra(task_name="claim_next_queued_run"),
            )
            raise
        if claimed_run is None:
            return None

        heartbeat_stop = threading.Event()

        def _heartbeat_loop() -> None:
            interval = max(1.0, float(self.lease_seconds) / 3.0)
            while not heartbeat_stop.wait(interval):
                try:
                    self.renew_run_lease(claimed_run)
                except WorkerLeaseLostError:
                    self.logger.exception(
                        "worker_lease_lost",
                        extra=self._log_extra(task_name="heartbeat_running", run=claimed_run),
                    )
                    return
                except BaseException as exc:
                    if not _is_handled_worker_failure(exc):
                        raise
                    self.logger.exception(
                        "worker_heartbeat_failed",
                        extra=self._log_extra(
                            task_name="heartbeat_running",
                            run=claimed_run,
                            error_category=transient_database_error_category(exc) or "non_transient",
                        ),
                    )

        thread = threading.Thread(target=_heartbeat_loop, daemon=True, name=f"worker-heartbeat-{self.worker_id}")
        thread.start()
        started_at = time.perf_counter()
        task_error: BaseException | None = None
        try:
            if claimed_run.attempt_count > 1:
                self.logger.warning(
                    "worker_task_retry",
                    extra=self._log_extra(task_name="execute_run", run=claimed_run),
                )
            self.logger.info("worker_task_start", extra=self._log_extra(task_name="execute_run", run=claimed_run))
            result = self.application.execute_claimed_run(claimed_run.id, auto_retry_failed=auto_retry_failed)
            heartbeat_stop.set()
            thread.join(timeout=max(1.0, float(self.lease_seconds)))
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            self._log_run_completion(claimed_run=claimed_run, result=result, duration_ms=duration_ms)
            return result
        except BaseException as exc:
            task_error = exc
            heartbeat_stop.set()
            thread.join(timeout=max(1.0, float(self.lease_seconds)))
            if not _is_handled_worker_failure(exc):
                raise
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            self.logger.exception(
                "worker_task_exception",
                extra=self._log_extra(
                    task_name="execute_run",
                    run=claimed_run,
                    duration_ms=duration_ms,
                    error_message=str(exc),
                ),
            )
            raise
        finally:
            heartbeat_stop.set()
            thread.join(timeout=max(1.0, float(self.lease_seconds)))
            try:
                self.application.release_worker(self.worker_id)
            except BaseException as exc:
                if not _is_handled_worker_cleanup_failure(exc):
                    raise
                self.logger.exception(
                    "worker_release_failed",
                    extra=self._log_extra(task_name="release_worker", run=claimed_run),
                )
                if task_error is None:
                    raise

    def run_loop(self, *, max_runs: int = 0, auto_retry_failed: bool = True) -> int:
        processed = 0
        last_maintenance_check = 0.0
        last_scheduled_run_check: float | None = None
        last_company_enrichment_check: float | None = None
        loop_started_at = time.perf_counter()
        self.logger.info(
            "worker_loop_start",
            extra=self._log_extra(
                task_name="run_loop",
                max_runs=max(0, int(max_runs)),
                poll_interval_seconds=self.poll_interval_seconds,
            ),
        )
        try:
            self.heartbeat(status=WORKER_STATUS_IDLE, current_run_id="")
        except BaseException as exc:
            if not _is_handled_worker_failure(exc):
                raise
            error_category = transient_database_error_category(exc)
            if error_category is None:
                self.logger.exception(
                    "worker_initial_heartbeat_failed",
                    extra=self._log_extra(task_name="heartbeat_idle"),
                )
                raise
            self.logger.warning(
                "worker_transient_database_failure",
                extra=self._log_extra(
                    task_name="heartbeat_idle",
                    operation="initial_heartbeat",
                    error_category=error_category,
                ),
            )
        loop_error: BaseException | None = None
        try:
            while not self._stop_event.is_set():
                now = time.monotonic()
                if now - last_maintenance_check >= 60.0:
                    last_maintenance_check = now
                    maintenance_started_at = time.perf_counter()
                    try:
                        self.application.maybe_run_scheduled_scrapeops_maintenance(source="worker")
                    except Exception:
                        self.logger.exception(
                            "worker_scheduled_maintenance_failed",
                            extra=self._log_extra(task_name="scheduled_scrapeops_maintenance"),
                        )
                    else:
                        maintenance_duration_ms = int((time.perf_counter() - maintenance_started_at) * 1000)
                        if maintenance_duration_ms >= int(max(0.0, self.slow_task_warning_seconds) * 1000):
                            self.logger.warning(
                                "worker_scheduled_maintenance_slow",
                                extra=self._log_extra(
                                    task_name="scheduled_scrapeops_maintenance",
                                    duration_ms=maintenance_duration_ms,
                                ),
                            )
                if max_runs > 0 and processed >= max_runs:
                    self.logger.info(
                        "worker_loop_max_runs_reached",
                        extra=self._log_extra(
                            task_name="run_loop",
                            processed_count=processed,
                            max_runs=max_runs,
                        ),
                    )
                    break
                should_check_scheduled_runs = (
                    last_scheduled_run_check is None
                    or now - last_scheduled_run_check
                    >= max(0.1, float(self.scheduled_run_check_interval_seconds))
                )
                if should_check_scheduled_runs:
                    last_scheduled_run_check = now
                    if isinstance(self.application, BackendApplication):
                        try:
                            acquisition_result = self.application.run_due_acquisition()
                        except BaseException as exc:
                            if not _is_handled_worker_failure(exc):
                                raise
                            self.logger.exception(
                                "worker_acquisition_cycle_failed",
                                extra=self._log_extra(task_name="scheduled_acquisition"),
                            )
                        else:
                            self._log_acquisition_result(acquisition_result)
                should_check_company_enrichment = (
                    last_company_enrichment_check is None
                    or now - last_company_enrichment_check
                    >= max(1.0, float(self.company_enrichment_check_interval_seconds))
                )
                if should_check_company_enrichment and isinstance(self.application, BackendApplication):
                    last_company_enrichment_check = now
                    try:
                        enrichment_result = self.application.run_due_company_enrichment()
                    except BaseException as exc:
                        if not _is_handled_worker_failure(exc):
                            raise
                        self.logger.exception(
                            "worker_company_enrichment_failed",
                            extra=self._log_extra(task_name="scheduled_company_enrichment"),
                        )
                    else:
                        self.logger.info(
                            "worker_company_enrichment_complete",
                            extra=self._log_extra(
                                task_name="scheduled_company_enrichment",
                                **{key: value for key, value in (enrichment_result or {}).items() if key != "cycle_key"},
                            ),
                        )
                try:
                    run = self.process_next(
                        auto_retry_failed=auto_retry_failed,
                        enqueue_scheduled_runs=should_check_scheduled_runs,
                    )
                except BaseException as exc:
                    if not _is_handled_worker_failure(exc):
                        raise
                    error_category = transient_database_error_category(exc)
                    if error_category is None:
                        raise
                    self.logger.warning(
                        "worker_transient_database_failure",
                        extra=self._log_extra(
                            task_name="process_next",
                            operation="worker_loop",
                            error_category=error_category,
                        ),
                    )
                    self._stop_event.wait(max(0.1, float(self.poll_interval_seconds)))
                    continue
                if run is None:
                    self._stop_event.wait(max(0.1, float(self.poll_interval_seconds)))
                    continue
                processed += 1
        except BaseException as exc:
            loop_error = exc
            raise
        finally:
            duration_ms = int((time.perf_counter() - loop_started_at) * 1000)
            try:
                self.application.stop_worker(self.worker_id)
            except BaseException as exc:
                if not _is_handled_worker_cleanup_failure(exc):
                    raise
                self.logger.exception(
                    "worker_stop_failed",
                    extra=self._log_extra(
                        task_name="stop_worker",
                        processed_count=processed,
                        duration_ms=duration_ms,
                    ),
                )
                if loop_error is None and not isinstance(exc, Exception):
                    raise
            else:
                self.logger.info(
                    "worker_loop_stop",
                    extra=self._log_extra(
                        task_name="run_loop",
                        processed_count=processed,
                        duration_ms=duration_ms,
                    ),
                )
        return processed
