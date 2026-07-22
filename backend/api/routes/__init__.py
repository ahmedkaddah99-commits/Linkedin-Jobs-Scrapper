from __future__ import annotations

from backend.api.routes.admin import register_routes as register_admin_routes
from backend.api.routes.application_bindings import register_routes as register_application_bindings_routes
from backend.api.routes.assisted_apply import register_routes as register_assisted_apply_routes
from backend.api.routes.assisted_apply_packages import register_routes as register_assisted_apply_package_routes
from backend.api.routes.assisted_apply_telemetry import register_routes as register_assisted_apply_telemetry_routes
from backend.api.routes.career_profiles import register_routes as register_career_profiles_routes
from backend.api.routes.career_memory import register_routes as register_career_memory_routes
from backend.api.routes.career_profile_evidence import register_routes as register_career_profile_evidence_routes
from backend.api.routes.evidence_items import register_routes as register_evidence_items_routes
from backend.api.routes.documents import register_routes as register_document_routes
from backend.api.routes.evidence import register_routes as register_evidence_routes
from backend.api.routes.evidence_library import register_routes as register_evidence_library_routes
from backend.api.routes.evidence_recommendation import register_routes as register_evidence_recommendation_routes
from backend.api.routes.source_text_review import register_routes as register_source_text_review_routes
from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.api.routes.system import register_routes as register_system_routes
from backend.api.routes.tracker import register_routes as register_tracker_routes
from backend.api.routes.workspace import register_routes as register_workspace_routes
from backend.api.routes.work_experiences import register_routes as register_work_experiences_routes


def build_route_registry() -> RouteRegistry:
    registry = RouteRegistry()
    register_system_routes(registry)
    register_assisted_apply_routes(registry)
    register_assisted_apply_package_routes(registry)
    register_assisted_apply_telemetry_routes(registry)
    register_admin_routes(registry)
    register_career_profiles_routes(registry)
    register_application_bindings_routes(registry)

    register_career_profile_evidence_routes(registry)
    register_evidence_recommendation_routes(registry)

    register_source_text_review_routes(registry)
    register_career_memory_routes(registry)
    register_evidence_items_routes(registry)
    register_document_routes(registry)
    register_evidence_routes(registry)
    register_evidence_library_routes(registry)

    register_tracker_routes(registry)
    register_work_experiences_routes(registry)
    register_workspace_routes(registry)
    return registry


__all__ = ["ApiRouteContext", "RouteRegistry", "build_route_registry"]
