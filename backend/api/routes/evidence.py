"""API routes for evidence state visibility (CP-028)."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.domain.evidence import (
    EVIDENCE_ACTION_NEEDED,
    EVIDENCE_KINDS,
    EVIDENCE_STATE_ORDER,
    EVIDENCE_STATES,
    EVIDENCE_TRANSITIONS,
    EvidenceRecord,
    EvidenceStateHistory,
)
from backend.domain.models import utc_now_iso


def register_routes(registry: RouteRegistry) -> None:
    registry.prefix(
        "GET", ("evidence-states",),
        _handle_list_states, auth_required=True, name="evidence.list_states",
    )
    registry.prefix(
        "GET", ("evidence",),
        _handle_list_evidence, auth_required=True, name="evidence.list",
    )
    registry.prefix(
        "POST", ("evidence",),
        _handle_create_evidence, auth_required=True, name="evidence.create",
    )
    registry.prefix(
        "GET", ("evidence", "{evidence_id}"),
        _handle_get_evidence, auth_required=True, name="evidence.get",
    )
    registry.prefix(
        "PUT", ("evidence", "{evidence_id}"),
        _handle_update_evidence, auth_required=True, name="evidence.update",
    )
    registry.prefix(
        "POST", ("evidence", "{evidence_id}", "transition"),
        _handle_transition, auth_required=True, name="evidence.transition",
    )
    registry.prefix(
        "GET", ("evidence", "{evidence_id}", "history"),
        _handle_list_history, auth_required=True, name="evidence.history",
    )
    registry.prefix(
        "DELETE", ("evidence", "{evidence_id}"),
        _handle_delete_evidence, auth_required=True, name="evidence.delete",
    )


def _evidence_store(context: ApiRouteContext):
    store = context.repositories.evidence_store
    if store is None:
        raise RuntimeError("Evidence store is not configured.")
    return store


def _handle_list_states(context: ApiRouteContext) -> dict[str, Any]:
    """Return the evidence state catalogue with transitions and actions."""
    return {
        "states": [
            {
                "state": state,
                "action_needed": EVIDENCE_ACTION_NEEDED.get(state, ""),
                "available_transitions": sorted(EVIDENCE_TRANSITIONS.get(state, set())),
            }
            for state in EVIDENCE_STATE_ORDER
        ],
        "kinds": sorted(EVIDENCE_KINDS),
    }



def _handle_list_evidence(context: ApiRouteContext) -> dict[str, Any]:
    store = _evidence_store(context)
    params = context.query_params
    workspace_id = str(params.get("workspace_id") or "").strip()
    run_id = str(params.get("run_id") or "").strip()
    kind = str(params.get("kind") or "").strip()
    state = str(params.get("state") or "").strip()
    limit = max(1, min(200, int(params.get("limit") or 100)))
    offset = max(0, int(params.get("offset") or 0))
    items = store.list_evidence(
        workspace_id=workspace_id, run_id=run_id,
        kind=kind, state=state, limit=limit, offset=offset,
    )
    return {"evidence": [item.to_dict() for item in items], "count": len(items)}


def _handle_create_evidence(context: ApiRouteContext) -> dict[str, Any]:
    store = _evidence_store(context)
    payload = context.payload or {}
    record = EvidenceRecord.create(
        workspace_id=str(payload.get("workspace_id") or ""),
        run_id=str(payload.get("run_id") or ""),
        kind=str(payload.get("kind") or "evidence"),
        label=str(payload.get("label") or ""),
        description=str(payload.get("description") or ""),
        source_ref=str(payload.get("source_ref") or ""),
        source_type=str(payload.get("source_type") or ""),
        metadata=dict(payload.get("metadata") or {}),
    )
    store.upsert_evidence(record)
    history = EvidenceStateHistory.create(
        evidence_id=record.evidence_id, from_state="", to_state=record.state,
        reason="Evidence created.",
        actor=str(context.user.user_id if context.user else "system"),
    )
    store.append_state_history(history)
    return record.to_dict()


def _handle_get_evidence(context: ApiRouteContext) -> dict[str, Any]:
    store = _evidence_store(context)
    return store.get_evidence(context.path_params["evidence_id"]).to_dict()


def _handle_update_evidence(context: ApiRouteContext) -> dict[str, Any]:
    store = _evidence_store(context)
    evidence_id = context.path_params["evidence_id"]
    existing = store.get_evidence(evidence_id)
    payload = context.payload or {}
    for field in ("label", "description", "source_ref", "source_type"):
        value = payload.get(field)
        if value is not None:
            setattr(existing, field, str(value).strip())
    if "metadata" in payload:
        existing.metadata = dict(payload.get("metadata") or {})
    existing.updated_at = utc_now_iso()
    store.upsert_evidence(existing)
    return store.get_evidence(evidence_id).to_dict()


def _handle_transition(context: ApiRouteContext) -> dict[str, Any]:
    store = _evidence_store(context)
    evidence_id = context.path_params["evidence_id"]
    payload = context.payload or {}
    target_state = str(payload.get("state") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    if target_state not in EVIDENCE_STATES:
        raise ValueError(f"Unknown evidence state: {target_state}")
    record = store.get_evidence(evidence_id)
    if not record.can_transition_to(target_state):
        available = sorted(EVIDENCE_TRANSITIONS.get(record.state, set()))
        raise ValueError(
            f"Cannot transition from '{record.state}' to '{target_state}'. "
            f"Available: {available}"
        )
    previous_state = record.state
    record.state = target_state
    record.updated_at = utc_now_iso()
    store.upsert_evidence(record)
    actor = str(context.user.user_id if context.user else "system")
    history = EvidenceStateHistory.create(
        evidence_id=evidence_id, from_state=previous_state,
        to_state=target_state,
        reason=reason or f"Transitioned '{previous_state}' -> '{target_state}'.",
        actor=actor,
    )
    store.append_state_history(history)
    return record.to_dict()


def _handle_list_history(context: ApiRouteContext) -> dict[str, Any]:
    store = _evidence_store(context)
    evidence_id = context.path_params["evidence_id"]
    limit = max(1, min(200, int(context.query_params.get("limit") or 100)))
    items = store.list_state_history(evidence_id=evidence_id, limit=limit)
    return {"history": [item.to_dict() for item in items], "count": len(items)}


def _handle_delete_evidence(context: ApiRouteContext) -> dict[str, Any]:
    store = _evidence_store(context)
    evidence_id = context.path_params["evidence_id"]
    store.delete_evidence(evidence_id)
    return {"deleted": True, "evidence_id": evidence_id}
