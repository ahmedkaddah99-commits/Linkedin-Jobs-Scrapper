"""Request-level telemetry recording memory, database, and external provider durations.

Integrate into BackendApiHandler._begin_request / _finish_request_log to emit
structured telemetry logs that help diagnose memory pressure, slow database
queries, and slow external HTTP calls.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any
from uuid import uuid4


LOGGER = logging.getLogger("backend.api.telemetry")

_MEMORY_MEASUREMENT_ENABLED = os.name != "nt" or hasattr(os, "getpid")


def _resident_memory_bytes() -> int | None:
    """Best-effort resident set size in bytes.  Returns None when unavailable."""
    try:
        import resource  # noqa: PLC0415
    except ImportError:
        return None
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return usage.ru_maxrss * 1024  # Linux / macOS return KB
    except Exception:
        return None


@dataclass(slots=True)
class RequestTelemetry:
    request_id: str = field(default_factory=lambda: uuid4().hex[:12])
    route: str = ""
    route_name: str = ""
    method: str = ""
    run_id: str = ""
    memory_before_bytes: int | None = None
    memory_after_bytes: int | None = None
    payload_request_bytes: int = 0
    payload_response_bytes: int = 0
    duration_total_ms: float = 0.0

    # Sub-phase durations (ms)
    auth_duration_ms: float | None = None
    database_duration_ms: float | None = None
    artifact_r2_duration_ms: float | None = None
    external_provider_duration_ms: float | None = None

    _started_at: float = field(default_factory=perf_counter, repr=False)
    _phase_starts: dict[str, float] = field(default_factory=dict, repr=False)
    _phase_durations: dict[str, float] = field(default_factory=dict, repr=False)

    @property
    def memory_delta_bytes(self) -> int | None:
        if self.memory_before_bytes is None or self.memory_after_bytes is None:
            return None
        return self.memory_after_bytes - self.memory_before_bytes

    def start_phase(self, name: str) -> None:
        self._phase_starts[name] = perf_counter()

    def end_phase(self, name: str) -> None:
        started = self._phase_starts.pop(name, None)
        if started is None:
            return
        self._phase_durations[name] = round((perf_counter() - started) * 1000, 2)

    def record_database(self, duration_ms: float) -> None:
        previous = self.database_duration_ms or 0.0
        self.database_duration_ms = previous + duration_ms

    def record_artifact_r2(self, duration_ms: float) -> None:
        previous = self.artifact_r2_duration_ms or 0.0
        self.artifact_r2_duration_ms = previous + duration_ms

    def record_external_provider(self, duration_ms: float) -> None:
        previous = self.external_provider_duration_ms or 0.0
        self.external_provider_duration_ms = previous + duration_ms

    def finalise(self) -> None:
        self.duration_total_ms = round((perf_counter() - self._started_at) * 1000, 2)
        self.memory_after_bytes = _resident_memory_bytes()

    def emit(self) -> None:
        payload: dict[str, Any] = {
            "event": "api_request_telemetry",
            "request_id": self.request_id,
            "route": self.route,
            "route_name": self.route_name,
            "method": self.method,
            "duration_total_ms": self.duration_total_ms,
            "payload_request_bytes": self.payload_request_bytes,
            "payload_response_bytes": self.payload_response_bytes,
        }
        if self.run_id:
            payload["run_id"] = self.run_id
        if self.memory_before_bytes is not None:
            payload["memory_before_bytes"] = self.memory_before_bytes
        if self.memory_after_bytes is not None:
            payload["memory_after_bytes"] = self.memory_after_bytes
        if self.memory_delta_bytes is not None:
            payload["memory_delta_bytes"] = self.memory_delta_bytes
        if self.auth_duration_ms is not None:
            payload["auth_duration_ms"] = self.auth_duration_ms
        if self.database_duration_ms is not None:
            payload["database_duration_ms"] = self.database_duration_ms
        if self.artifact_r2_duration_ms is not None:
            payload["artifact_r2_duration_ms"] = self.artifact_r2_duration_ms
        if self.external_provider_duration_ms is not None:
            payload["external_provider_duration_ms"] = self.external_provider_duration_ms
        for phase_name, phase_duration in self._phase_durations.items():
            payload[f"phase_{phase_name}_ms"] = phase_duration
        LOGGER.info(json.dumps(payload, separators=(",", ":")))


def new_telemetry() -> RequestTelemetry:
    t = RequestTelemetry()
    t.memory_before_bytes = _resident_memory_bytes()
    return t
