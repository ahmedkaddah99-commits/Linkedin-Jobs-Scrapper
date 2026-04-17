from __future__ import annotations

import logging
import os
import socket
import threading
import time
from dataclasses import dataclass, field

from backend.application import BackendApplication
from backend.domain.models import WORKER_STATUS_IDLE, WORKER_STATUS_RUNNING


@dataclass(slots=True)
class WorkerService:
    application: BackendApplication
    worker_id: str
    host_name: str = field(default_factory=socket.gethostname)
    process_id: int = field(default_factory=os.getpid)
    lease_seconds: int = 60
    poll_interval_seconds: float = 5.0
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("backend.worker"))
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False, repr=False)

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
        self.application.recover_stale_workers()
        claimed_run = self.application.claim_next_queued_run(
            worker_id=self.worker_id,
            host_name=self.host_name,
            process_id=self.process_id,
            lease_seconds=self.lease_seconds,
        )
        if claimed_run is None:
            self.heartbeat(status=WORKER_STATUS_IDLE, current_run_id="")
            return None

        heartbeat_stop = threading.Event()

        def _heartbeat_loop() -> None:
            interval = max(1.0, float(self.lease_seconds) / 3.0)
            while not heartbeat_stop.wait(interval):
                try:
                    self.heartbeat(status=WORKER_STATUS_RUNNING, current_run_id=claimed_run.id)
                except Exception:
                    self.logger.exception("Worker heartbeat failed for %s", self.worker_id)

        thread = threading.Thread(target=_heartbeat_loop, daemon=True, name=f"worker-heartbeat-{self.worker_id}")
        thread.start()
        try:
            self.logger.info("Worker %s processing run %s", self.worker_id, claimed_run.id)
            return self.application.execute_claimed_run(claimed_run.id, auto_retry_failed=auto_retry_failed)
        finally:
            heartbeat_stop.set()
            thread.join(timeout=max(1.0, float(self.lease_seconds)))
            self.application.release_worker(self.worker_id)

    def run_loop(self, *, max_runs: int = 0, auto_retry_failed: bool = True) -> int:
        processed = 0
        self.heartbeat(status=WORKER_STATUS_IDLE, current_run_id="")
        try:
            while not self._stop_event.is_set():
                if max_runs > 0 and processed >= max_runs:
                    break
                run = self.process_next(auto_retry_failed=auto_retry_failed)
                if run is None:
                    self._stop_event.wait(max(0.1, float(self.poll_interval_seconds)))
                    continue
                processed += 1
        finally:
            try:
                self.application.stop_worker(self.worker_id)
            except Exception:
                self.logger.exception("Failed to stop worker %s cleanly", self.worker_id)
        return processed
