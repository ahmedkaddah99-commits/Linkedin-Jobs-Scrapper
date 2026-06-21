from __future__ import annotations

import threading
from dataclasses import dataclass
from time import perf_counter
from typing import Any
from uuid import uuid4

from .base import ObjectStorage
from .keys import build_private_object_key


@dataclass(frozen=True)
class ObjectStorageProbeResult:
    key: str
    elapsed_ms: float


def probe_object_storage(
    storage: ObjectStorage,
    *,
    timeout_seconds: float = 5.0,
) -> ObjectStorageProbeResult:
    """Perform a bounded write/read/delete probe against the configured backend."""

    timeout = min(30.0, max(0.1, float(timeout_seconds)))
    probe_id = uuid4().hex
    key = build_private_object_key(
        namespace="health",
        owner_id="ready",
        category="probe",
        object_id=probe_id,
        filename="probe.txt",
    )
    payload = f"runr-readiness:{probe_id}".encode("utf-8")
    outcome: dict[str, Any] = {}
    completed = threading.Event()
    started = perf_counter()

    def run_probe() -> None:
        try:
            storage.put(
                key,
                payload,
                content_type="text/plain",
                metadata={"probe": "readiness"},
            )
            stored_payload = storage.get(key)
            if stored_payload != payload:
                raise RuntimeError("Object storage readiness write/read probe failed.")
        except BaseException as exc:
            outcome["error"] = exc
        finally:
            try:
                storage.delete(key)
            except BaseException as exc:
                outcome.setdefault("error", exc)
            completed.set()

    thread = threading.Thread(target=run_probe, name="object-storage-readiness", daemon=True)
    thread.start()
    if not completed.wait(timeout):
        raise TimeoutError(f"Object storage readiness probe exceeded {timeout:g} seconds.")
    error = outcome.get("error")
    if error is not None:
        raise RuntimeError("Object storage readiness probe failed.") from error
    return ObjectStorageProbeResult(
        key=key,
        elapsed_ms=round((perf_counter() - started) * 1000, 2),
    )
