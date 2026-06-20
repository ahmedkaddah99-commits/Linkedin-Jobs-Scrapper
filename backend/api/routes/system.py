from __future__ import annotations

import os

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.database import database_target_info


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
    repositories = getattr(context.application, "repositories", None)
    analytics_store = getattr(repositories, "analytics_store", None) if repositories is not None else None
    query_rows = getattr(analytics_store, "query_rows", None)
    if not callable(query_rows):
        raise RuntimeError("Database readiness check requires a query-capable analytics store.")
    rows = query_rows("SELECT 1 AS ready")
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

    context.send_json(
        {
            "status": "ready",
            "database": database,
            "object_storage": {
                "backend": object_storage_backend,
                "class": object_storage_class,
            },
        }
    )
