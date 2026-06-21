from __future__ import annotations

import os
import time
from uuid import uuid4

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.database import database_target_info
from backend.storage import build_private_object_key


def register_routes(registry: RouteRegistry) -> None:
    registry.exact("GET", (), _get_service_status, auth_required=False, name="system.status")
    registry.exact("GET", ("health",), _get_health, auth_required=False, name="system.health")
    registry.exact("GET", ("health", "live"), _get_liveness, auth_required=False, name="system.health.live")
    registry.exact("GET", ("health", "ready"), _get_readiness, auth_required=False, name="system.health.ready")


def _get_service_status(context: ApiRouteContext) -> None:
    context.send_json({"service": "unified-backend-api", "status": "ok"})


def _get_health(context: ApiRouteContext) -> None:
    context.send_json({"status": "ok"})


def _get_liveness(context: ApiRouteContext) -> None:
    context.send_json({"status": "ok"})


def _get_readiness(context: ApiRouteContext) -> None:
    timings_ms: dict[str, float] = {}
    repositories = getattr(context.application, "repositories", None)
    analytics_store = getattr(repositories, "analytics_store", None) if repositories is not None else None
    query_rows = getattr(analytics_store, "query_rows", None)
    if not callable(query_rows):
        raise RuntimeError("Database readiness check requires a query-capable analytics store.")
    started = time.perf_counter()
    rows = query_rows("SELECT 1 AS ready")
    timings_ms["database_select"] = round((time.perf_counter() - started) * 1000, 2)
    if not rows or int(rows[0].get("ready") or 0) != 1:
        raise RuntimeError("Database readiness check failed.")

    db_path = getattr(analytics_store, "db_path", "")
    database = database_target_info(db_path)
    object_storage = getattr(context.application, "object_storage", None)
    object_storage_class = type(object_storage).__name__ if object_storage is not None else ""
    object_storage_backend = str(os.getenv("OBJECT_STORAGE_BACKEND", "local") or "local").strip().lower()
    runtime_environment = str(database.get("runtime_environment") or "").strip().lower()
    is_production = runtime_environment in {"prod", "production"}

    if is_production and database.get("target_backend") != "libsql":
        raise RuntimeError("Production readiness requires the libSQL/Turso database target.")
    if is_production and object_storage_backend not in {"s3", "r2"}:
        raise RuntimeError("Production readiness requires S3-compatible object storage.")

    probe_enabled = str((context.query.get("probe") or [""])[0]).strip().lower() in {"1", "true", "yes", "full"}
    probes: dict[str, object] = {}
    if probe_enabled:
        config_store = getattr(repositories, "config_store", None) if repositories is not None else None
        set_value = getattr(config_store, "set_value", None)
        get_value = getattr(config_store, "get_value", None)
        delete_value = getattr(config_store, "delete_value", None)
        if not callable(set_value) or not callable(get_value) or not callable(delete_value):
            raise RuntimeError("Database probe requires a writable config store.")

        probe_id = uuid4().hex
        db_key = f"health.ready.probe.{probe_id}"
        db_payload = {"probe_id": probe_id}
        started = time.perf_counter()
        set_value(db_key, db_payload)
        read_payload = get_value(db_key, {})
        delete_value(db_key)
        timings_ms["database_write_read_delete"] = round((time.perf_counter() - started) * 1000, 2)
        if dict(read_payload or {}).get("probe_id") != probe_id:
            raise RuntimeError("Database readiness write/read probe failed.")
        probes["database_write"] = "ok"

        if object_storage is None:
            raise RuntimeError("Object storage probe requires an object storage backend.")
        storage_key = build_private_object_key(
            namespace="health",
            owner_id="ready",
            category="probe",
            object_id=probe_id,
            filename="probe.txt",
        )
        storage_payload = f"runr-readiness:{probe_id}".encode("utf-8")
        started = time.perf_counter()
        object_storage.put(
            storage_key,
            storage_payload,
            content_type="text/plain",
            metadata={"probe": "readiness"},
        )
        stored_payload = object_storage.get(storage_key)
        object_storage.delete(storage_key)
        timings_ms["object_storage_put_get_delete"] = round((time.perf_counter() - started) * 1000, 2)
        if stored_payload != storage_payload:
            raise RuntimeError("Object storage readiness write/read probe failed.")
        probes["object_storage_write"] = "ok"

    context.send_json(
        {
            "status": "ready",
            "database": database,
            "object_storage": {
                "backend": object_storage_backend,
                "class": object_storage_class,
            },
            "probes": probes,
            "timings_ms": timings_ms,
        }
    )
