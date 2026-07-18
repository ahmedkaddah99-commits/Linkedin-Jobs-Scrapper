from __future__ import annotations

from backend.api.routes.admin import register_routes as register_admin_routes
from backend.api.routes.assisted_apply import register_routes as register_assisted_apply_routes
from backend.api.routes.career_memory import register_routes as register_career_memory_routes
from backend.api.routes.documents import register_routes as register_document_routes
from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.api.routes.system import register_routes as register_system_routes
from backend.api.routes.tracker import register_routes as register_tracker_routes
from backend.api.routes.workspace import register_routes as register_workspace_routes


def build_route_registry() -> RouteRegistry:
    registry = RouteRegistry()
    register_system_routes(registry)
    register_assisted_apply_routes(registry)
    register_admin_routes(registry)
    register_career_memory_routes(registry)
    register_document_routes(registry)
    register_tracker_routes(registry)
    register_workspace_routes(registry)
    return registry


__all__ = ["ApiRouteContext", "RouteRegistry", "build_route_registry"]
