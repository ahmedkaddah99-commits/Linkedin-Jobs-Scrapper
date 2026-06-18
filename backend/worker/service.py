from __future__ import annotations

import logging
import os
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from backend.application import BackendApplication
from backend.domain.models import (
    RUN_STATUS_CANCEL_REQUESTED,
    RUN_STATUS_CANCELLED,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    WORKER_STATUS_IDLE,
    WORKER_STATUS_RUNNING,
    RunRecord,
)


@dataclass(slots=True)
class WorkerService:
    application: BackendApplication
    worker_id: str
    host_name: str = field(default_factory=socket.gethostname)
    process_id: int = field(default_factory=os.getpid)
    lease_seconds: int = 60
    poll_interval_seconds: float = 5.0
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
                    "last_error": run.last_error,
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

    def heartbeat(self, *, status: str = WORKER_STATUS_IDLE, current_run_id: str = ""):
        return self.application.heartbeat_worker(
            worker_id=self.worker_id,
            status=status,
            current_run_id=current_run_id,
            host_name=self.host_name,
            process_id=self.process_id,
            lease_seconds=self.lease_seconds,
        )

    def stop(self) -> None:
        self._stop_event.set()

    def process_next(self, *, auto_retry_failed: bool = True):
        try:
            recovered_workers = self.application.recover_stale_workers()
        except Exception:
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

        try:
            claimed_run = self.application.claim_next_queued_run(
                worker_id=self.worker_id,
                host_name=self.host_name,
                process_id=self.process_id,
                lease_seconds=self.lease_seconds,
            )
        except Exception:
            self.logger.exception(
                "worker_claim_failed",
                extra=self._log_extra(task_name="claim_next_queued_run"),
            )
            raise
        if claimed_run is None:
            try:
                self.heartbeat(status=WORKER_STATUS_IDLE, current_run_id="")
            except Exception:
                self.logger.exception(
                    "worker_idle_heartbeat_failed",
                    extra=self._log_extra(task_name="heartbeat_idle"),
                )
                raise
            return None

        heartbeat_stop = threading.Event()

        def _heartbeat_loop() -> None:
            interval = max(1.0, float(self.lease_seconds) / 3.0)
            while not heartbeat_stop.wait(interval):
                try:
                    self.heartbeat(status=WORKER_STATUS_RUNNING, current_run_id=claimed_run.id)
                except Exception:
                    self.logger.exception(
                        "worker_heartbeat_failed",
                        extra=self._log_extra(task_name="heartbeat_running", run=claimed_run),
                    )

        thread = threading.Thread(target=_heartbeat_loop, daemon=True, name=f"worker-heartbeat-{self.worker_id}")
        thread.start()
        started_at = time.perf_counter()
        try:
            if claimed_run.attempt_count > 1:
                self.logger.warning(
                    "worker_task_retry",
                    extra=self._log_extra(task_name="execute_run", run=claimed_run),
                )
            self.logger.info("worker_task_start", extra=self._log_extra(task_name="execute_run", run=claimed_run))
            result = self.application.execute_claimed_run(claimed_run.id, auto_retry_failed=auto_retry_failed)
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            self._log_run_completion(claimed_run=claimed_run, result=result, duration_ms=duration_ms)
            return result
        except Exception as exc:
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
            except Exception:
                self.logger.exception(
                    "worker_release_failed",
                    extra=self._log_extra(task_name="release_worker", run=claimed_run),
                )
                raise

    def run_loop(self, *, max_runs: int = 0, auto_retry_failed: bool = True) -> int:
        processed = 0
        last_maintenance_check = 0.0
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
        except Exception:
            self.logger.exception(
                "worker_initial_heartbeat_failed",
                extra=self._log_extra(task_name="heartbeat_idle"),
            )
            raise
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
                run = self.process_next(auto_retry_failed=auto_retry_failed)
                if run is None:
                    self._stop_event.wait(max(0.1, float(self.poll_interval_seconds)))
                    continue
                processed += 1
        finally:
            duration_ms = int((time.perf_counter() - loop_started_at) * 1000)
            try:
                self.application.stop_worker(self.worker_id)
            except Exception:
                self.logger.exception(
                    "worker_stop_failed",
                    extra=self._log_extra(
                        task_name="stop_worker",
                        processed_count=processed,
                        duration_ms=duration_ms,
                    ),
                )
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
