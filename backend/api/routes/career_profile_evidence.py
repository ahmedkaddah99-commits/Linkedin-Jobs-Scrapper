"""API routes for Career Profile Evidence review (CP-010).

Provides Verify, Edit, Reject, and Ask me later actions for extracted evidence.
"""

from __future__ import annotations

from http import HTTPStatus

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.capabilities.career_profile_evidence import (
    count_evidence_by_status,
    defer_evidence,
    edit_evidence,
    get_evidence,
    get_verified_evidence,
    list_evidence,
    reject_evidence,
    verify_evidence,
)


def register_routes(registry: RouteRegistry) -> None:
    """Register evidence review routes under career-profiles."""

    registry.prefix(
        "GET",
        ("career-profiles", "{profile_id}", "evidence"),
        _handle_list_evidence,
        auth_required=True,
        name="career_profile_evidence.list",
    )
    registry.prefix(
        "GET",
        ("career-profiles", "{profile_id}", "evidence", "{evidence_id}"),
        _handle_get_evidence,
        auth_required=True,
        name="career_profile_evidence.get",
    )
    registry.prefix(
        "POST",
        ("career-profiles", "{profile_id}", "evidence", "{evidence_id}", "verify"),
        _handle_verify,
        auth_required=True,
        name="career_profile_evidence.verify",
    )
    registry.prefix(
        "POST",
        ("career-profiles", "{profile_id}", "evidence", "{evidence_id}", "reject"),
        _handle_reject,
        auth_required=True,
        name="career_profile_evidence.reject",
    )
    registry.prefix(
        "POST",
        ("career-profiles", "{profile_id}", "evidence", "{evidence_id}", "defer"),
        _handle_defer,
        auth_required=True,
        name="career_profile_evidence.defer",
    )
    registry.prefix(
        "PUT",
        ("career-profiles", "{profile_id}", "evidence", "{evidence_id}", "edit"),
        _handle_edit,
        auth_required=True,
        name="career_profile_evidence.edit",
    )


# ── helpers ─────────────────────────────────────────────────────────────


def _extract_params(context: ApiRouteContext):
    segments = list(context.segments)
    profile_id = segments[1] if len(segments) > 1 else ""
    evidence_id = segments[3] if len(segments) > 3 else ""
    return profile_id, evidence_id


def _not_found(context: ApiRouteContext, evidence_id: str) -> bool:
    context.send_error(
        HTTPStatus.NOT_FOUND,
        "evidence_not_found",
        f"Evidence item '{evidence_id}' not found.",
    )
    return True


# ── handlers ────────────────────────────────────────────────────────────


def _handle_list_evidence(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) < 2 or segments[0] != "career-profiles":
        return False
    profile_id = segments[1]
    status_filter = context.query_params.get("status")
    all_items = list_evidence(profile_id, status=status_filter)
    counts = count_evidence_by_status(profile_id)
    context.send_json({
        "evidence": [e.to_dict() for e in all_items],
        "counts": counts,
        "total": len(all_items),
    }, status=HTTPStatus.OK)
    return True


def _handle_get_evidence(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) < 4 or segments[0] != "career-profiles":
        return False
    profile_id, evidence_id = _extract_params(context)
    evidence = get_evidence(profile_id, evidence_id)
    if evidence is None:
        return _not_found(context, evidence_id)
    context.send_json(evidence.to_dict(), status=HTTPStatus.OK)
    return True


def _handle_verify(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) < 5 or segments[0] != "career-profiles":
        return False
    profile_id, evidence_id = _extract_params(context)
    result = verify_evidence(profile_id, evidence_id)
    if result is None:
        return _not_found(context, evidence_id)
    context.send_json(result.to_dict(), status=HTTPStatus.OK)
    return True


def _handle_reject(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) < 5 or segments[0] != "career-profiles":
        return False
    profile_id, evidence_id = _extract_params(context)
    result = reject_evidence(profile_id, evidence_id)
    if result is None:
        return _not_found(context, evidence_id)
    context.send_json(result.to_dict(), status=HTTPStatus.OK)
    return True


def _handle_defer(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) < 5 or segments[0] != "career-profiles":
        return False
    profile_id, evidence_id = _extract_params(context)
    result = defer_evidence(profile_id, evidence_id)
    if result is None:
        return _not_found(context, evidence_id)
    context.send_json(result.to_dict(), status=HTTPStatus.OK)
    return True


def _handle_edit(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if len(segments) < 5 or segments[0] != "career-profiles":
        return False
    profile_id, evidence_id = _extract_params(context)
    payload = context.read_json_body()
    new_text = str(payload.get("edited_text") or "")
    changed_by = str(payload.get("changed_by") or "user")
    result = edit_evidence(profile_id, evidence_id, new_text, changed_by=changed_by)
    if result is None:
        return _not_found(context, evidence_id)
    context.send_json(result.to_dict(), status=HTTPStatus.OK)
    return True
