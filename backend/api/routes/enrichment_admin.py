from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.api.routes.registry import ApiRouteContext, RouteRegistry


def register_routes(registry: RouteRegistry) -> None:
    registry.prefix("GET", ("admin", "enrichment"), _handle_get, auth_required=True, name="admin.enrichment.get")
    registry.prefix("POST", ("admin", "enrichment"), _handle_post, auth_required=True, name="admin.enrichment.post")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _actor_id(value: Any) -> str:
    user = value[0] if isinstance(value, tuple) else value
    if isinstance(user, Mapping):
        return _text(user.get("user_id") or user.get("id"))
    return _text(getattr(user, "user_id", "") or getattr(user, "id", ""))


def _payload(context: ApiRouteContext) -> dict[str, Any]:
    value = context.read_json_body() or {}
    return dict(value) if isinstance(value, Mapping) else {}


def _error(context: ApiRouteContext, status: int, code: str, message: str) -> bool:
    context.send_error(status, code, message)
    return True


def _limit(context: ApiRouteContext, default: int = 100, maximum: int = 500) -> int:
    try:
        value = int((context.query.get("limit") or [default])[0])
    except (TypeError, ValueError):
        value = default
    return max(1, min(maximum, value))


def _handle_get(context: ApiRouteContext) -> bool | None:
    admin = context.require_admin()
    segments = list(context.segments)
    application = context.application
    try:
        if segments == ["admin", "enrichment", "capabilities"]:
            context.send_json(
                application.get_admin_enrichment_capabilities(
                    target_type=_text((context.query.get("target_type") or [""])[0]),
                    selected_fields=(context.query.get("field") or []),
                    provider_id=_text((context.query.get("provider") or [""])[0]),
                )
            )
            return True
        if segments == ["admin", "enrichment", "budgets"]:
            context.send_json(
                {"budgets": application.list_admin_enrichment_budgets(), "default_max_requests": 0, "report_only": True}
            )
            return True
        if segments == ["admin", "enrichment", "plans"]:
            context.send_json({"plans": application.list_admin_enrichment_plans(limit=_limit(context))})
            return True
        if len(segments) == 4 and segments[:3] == ["admin", "enrichment", "plans"]:
            value = application.get_admin_enrichment_plan(segments[3])
            return (
                _error(context, 404, "enrichment_plan_not_found", "Enrichment plan not found.")
                if value is None
                else (context.send_json(value) or True)
            )
        if segments == ["admin", "enrichment", "runs"]:
            context.send_json({"runs": application.list_admin_enrichment_runs(limit=_limit(context))})
            return True
        if len(segments) == 4 and segments[:3] == ["admin", "enrichment", "runs"]:
            value = application.get_admin_enrichment_run(segments[3], include_items=True)
            return (
                _error(context, 404, "enrichment_run_not_found", "Enrichment run not found.")
                if value is None
                else (context.send_json(value) or True)
            )
        if (
            len(segments) == 5
            and segments[:4] == ["admin", "enrichment", "runs", segments[3]]
            and segments[4] == "status"
        ):
            value = application.get_admin_enrichment_run(segments[3], include_items=False)
            return (
                _error(context, 404, "enrichment_run_not_found", "Enrichment run not found.")
                if value is None
                else (context.send_json(value) or True)
            )
        if (
            len(segments) == 5
            and segments[:4] == ["admin", "enrichment", "runs", segments[3]]
            and segments[4] == "result"
        ):
            context.send_json(application.get_admin_enrichment_result(segments[3]))
            return True
        if (
            len(segments) == 5
            and segments[:4] == ["admin", "enrichment", "runs", segments[3]]
            and segments[4] == "audit"
        ):
            context.send_json(
                {
                    "events": application.list_admin_enrichment_audit(
                        run_id=segments[3], limit=_limit(context, 200, 1000)
                    )
                }
            )
            return True
        if segments == ["admin", "enrichment", "proposals"]:
            context.send_json({"proposals": application.list_admin_enrichment_proposals(limit=_limit(context))})
            return True
        if len(segments) == 4 and segments[:3] == ["admin", "enrichment", "proposals"]:
            value = application.get_admin_enrichment_proposal(segments[3])
            return (
                _error(context, 404, "enrichment_proposal_not_found", "Enrichment proposal not found.")
                if value is None
                else (context.send_json(value) or True)
            )
        if (
            len(segments) == 5
            and segments[:4] == ["admin", "enrichment", "proposals", segments[3]]
            and segments[4] == "audit"
        ):
            context.send_json(
                {
                    "events": application.list_admin_enrichment_audit(
                        proposal_id=segments[3], limit=_limit(context, 200, 1000)
                    )
                }
            )
            return True
    except KeyError as exc:
        return _error(context, 404, "enrichment_not_found", str(exc))
    except ValueError as exc:
        return _error(context, 400, "invalid_enrichment_request", str(exc))
    del admin
    return None


def _plan_kwargs(payload: Mapping[str, Any], *, actor_id: str, forced_company_id: str = "") -> dict[str, Any]:
    scope_type = _text(payload.get("scope_type") or payload.get("operation_scope"))
    scope_id = _text(payload.get("scope_id"))
    if forced_company_id:
        scope_type = "company"
        scope_id = forced_company_id
    if scope_type == "company":
        scope_id = scope_id or _text(payload.get("company_id"))
    elif scope_type == "import":
        scope_id = scope_id or _text(payload.get("import_id"))
    return {
        "requested_by": actor_id,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "target_type": _text(payload.get("target_type") or ("company" if forced_company_id else "job")),
        "selected_fields": payload.get("selected_fields") or payload.get("fields") or [],
        "provider_id": _text(payload.get("provider_id") or payload.get("provider") or "null"),
        "selected_records": payload.get("selected_records") or payload.get("records") or [],
        "record_ids": payload.get("record_ids") or [],
        "query_snapshot": payload.get("query_snapshot") or payload.get("query") or {},
        "exclusions": payload.get("exclusions") or [],
        "policy_version": _text(payload.get("policy_version") or "enrichment_policy_v1"),
        "rule_version": _text(payload.get("rule_version") or "enrichment_foundation_v1"),
        "snapshot_version": _text(payload.get("snapshot_version")),
        "expected_request_count": payload.get("expected_request_count"),
        "expected_cost": payload.get("expected_cost", payload.get("expected_cost_units", 0)),
        "idempotency_key": _text(payload.get("idempotency_key")),
    }


def _handle_post(context: ApiRouteContext) -> bool | None:
    admin = context.require_admin()
    actor_id = _actor_id(admin)
    segments = list(context.segments)
    application = context.application
    payload = _payload(context)
    try:
        if segments == ["admin", "enrichment", "plans"]:
            context.send_json(application.plan_admin_enrichment(**_plan_kwargs(payload, actor_id=actor_id)), status=201)
            return True
        if len(segments) == 5 and segments[:3] == ["admin", "enrichment", "companies"] and segments[4] == "plan":
            context.send_json(
                application.plan_admin_enrichment(
                    **_plan_kwargs(payload, actor_id=actor_id, forced_company_id=segments[3])
                ),
                status=201,
            )
            return True
        if len(segments) == 5 and segments[:3] == ["admin", "enrichment", "companies"] and segments[4] == "enrich":
            plan_id = _text(payload.get("plan_id"))
            plan = application.get_admin_enrichment_plan(plan_id) if plan_id else None
            if not plan or plan.get("scope_type") != "company" or plan.get("scope_id") != segments[3]:
                return _error(
                    context,
                    400,
                    "company_plan_required",
                    "Company enrichment requires a matching company-scoped plan; no batch run was started.",
                )
            context.send_json(
                application.start_admin_enrichment_run(
                    plan_id=plan_id,
                    requested_by=actor_id,
                    idempotency_key=_text(payload.get("idempotency_key")) or f"company:{segments[3]}:plan:{plan_id}",
                    request_budget=int(payload.get("request_budget") or 0),
                    cost_budget=float(payload.get("cost_budget") or 0),
                    retry_policy=payload.get("retry_policy") or {},
                ),
                status=202,
            )
            return True
        if len(segments) == 5 and segments[:3] == ["admin", "enrichment", "plans"] and segments[4] == "start":
            context.send_json(
                application.start_admin_enrichment_run(
                    plan_id=segments[3],
                    requested_by=actor_id,
                    idempotency_key=_text(payload.get("idempotency_key")),
                    request_budget=int(payload.get("request_budget") or 0),
                    cost_budget=float(payload.get("cost_budget") or 0),
                    retry_policy=payload.get("retry_policy") or {},
                ),
                status=202,
            )
            return True
        if len(segments) == 5 and segments[:3] == ["admin", "enrichment", "runs"] and segments[4] == "process":
            context.send_json(
                application.process_admin_enrichment_run(
                    segments[3], worker_id=_text(payload.get("worker_id") or "admin-enrichment-worker")
                ),
                status=202,
            )
            return True
        if len(segments) == 5 and segments[:3] == ["admin", "enrichment", "runs"] and segments[4] == "cancel":
            context.send_json(
                application.cancel_admin_enrichment_run(
                    segments[3], actor_id=actor_id, reason=_text(payload.get("reason"))
                ),
                status=202,
            )
            return True
        if len(segments) == 5 and segments[:3] == ["admin", "enrichment", "runs"] and segments[4] == "pause":
            context.send_json(
                application.pause_admin_enrichment_run(
                    segments[3], actor_id=actor_id, reason=_text(payload.get("reason"))
                ),
                status=202,
            )
            return True
        if len(segments) == 5 and segments[:3] == ["admin", "enrichment", "proposals"]:
            action = segments[4]
            if action not in {"accept", "reject", "undo", "supersede"}:
                return None
            context.send_json(
                application.review_admin_enrichment_proposal(
                    segments[3],
                    action=action,
                    reviewer_id=actor_id,
                    reason=_text(payload.get("reason")),
                    replacement_proposal_id=_text(payload.get("replacement_proposal_id")),
                    idempotency_key=_text(payload.get("idempotency_key")),
                ),
                status=202,
            )
            return True
        if segments == ["admin", "enrichment", "budgets"]:
            provider_id = _text(payload.get("provider_id") or payload.get("provider"))
            context.send_json(
                application.configure_admin_enrichment_budget(
                    provider_id,
                    max_requests=int(payload.get("max_requests") or 0),
                    max_cost_units=float(payload.get("max_cost_units") or payload.get("max_cost") or 0),
                    enabled=bool(payload.get("enabled", True)),
                    actor_id=actor_id,
                ),
                status=202,
            )
            return True
    except KeyError as exc:
        return _error(context, 404, "enrichment_not_found", str(exc))
    except (TypeError, ValueError) as exc:
        return _error(context, 400, "invalid_enrichment_request", str(exc))
    return None


__all__ = ["register_routes"]
