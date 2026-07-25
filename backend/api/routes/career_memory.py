"""Legacy career-memory routes — read-only compatibility adapters (CP-032R).

All mutations have been replaced by the canonical evidence-items API.
These routes remain for backward compatibility: GET returns a read-only
view; POST mutation endpoints return 410 Gone with a redirect hint.
"""

from __future__ import annotations

from http import HTTPStatus

from backend.api.routes.registry import ApiRouteContext, RouteRegistry


def register_routes(registry: RouteRegistry) -> None:
    registry.prefix("GET", ("career-memory",), _handle_get, auth_required=True, name="career_memory.get")
    registry.prefix("POST", ("career-memory",), _handle_post, auth_required=True, name="career_memory.post")


def _handle_get(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if segments == ["career-memory"]:
        user, _ = context.require_identity()
        # Return read-only compatibility view from canonical evidence
        metadata = dict(user.metadata or {})
        evidence_list = list(metadata.get("candidate_evidence") or [])
        context.send_json({
            "active_facts": evidence_list,
            "facts": evidence_list,
            "outputs": list(metadata.get("evidence_outputs") or []),
            "fact_history": evidence_list,
            "output_history": list(metadata.get("evidence_outputs") or []),
            "message": "Legacy career-memory is read-only. Use /evidence-items for mutations.",
        }, status=HTTPStatus.OK)
        return True
    return False


def _handle_post(context: ApiRouteContext) -> bool | None:
    """All legacy mutation endpoints are deprecated (CP-032R).

    Returns 410 Gone with a hint to use the canonical evidence-items API.
    """
    segments = list(context.segments)

    if segments[:2] == ["career-memory", "facts"]:
        context.send_json({
            "error": "gone",
            "message": "The /career-memory/facts mutation endpoints have been replaced.",
            "migration_hint": "Use POST /evidence-items/migrate for migration, "
                              "or the canonical evidence-items API for CRUD.",
        }, status=HTTPStatus.GONE)
        return True

    if segments[:2] == ["career-memory", "outputs"]:
        context.send_json({
            "error": "gone",
            "message": "The /career-memory/outputs mutation endpoints have been replaced.",
            "migration_hint": "Use POST /evidence-items/generate for generation, "
                              "or POST /evidence-items/outputs/{id}/regenerate for edits.",
        }, status=HTTPStatus.GONE)
        return True

    if segments[:2] == ["career-memory", "questions"]:
        context.send_json({
            "error": "gone",
            "message": "The /career-memory/questions endpoint has been replaced.",
            "migration_hint": "Use the canonical evidence lifecycle (needs_review -> reviewed -> confirmed).",
        }, status=HTTPStatus.GONE)
        return True

    return False
