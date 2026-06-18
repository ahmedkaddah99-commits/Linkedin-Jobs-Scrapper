from __future__ import annotations

from backend.api.routes.registry import ApiRouteContext, RouteRegistry


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
    context.send_json({"status": "ready"})
