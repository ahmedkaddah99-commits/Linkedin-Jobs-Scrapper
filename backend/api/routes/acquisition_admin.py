from __future__ import annotations

from backend.api.routes.registry import ApiRouteContext, RouteRegistry


def register_routes(registry: RouteRegistry) -> None:
    registry.prefix("GET", ("admin", "acquisition"), _handle_get, auth_required=True, name="admin.acquisition.get")
    registry.prefix("POST", ("admin", "acquisition"), _handle_post, auth_required=True, name="admin.acquisition.post")


def _handle_get(context: ApiRouteContext) -> bool | None:
    context.require_admin()
    application = context.application
    segments = list(context.segments)
    query = context.query
    if segments == ["admin", "acquisition", "cycles"]:
        limit = _int_query(query, "limit", 50, 200)
        offset = _int_query(query, "offset", 0, 100000)
        context.send_json({"cycles": application.list_acquisition_cycles(limit=limit, offset=offset)})
        return True
    if segments == ["admin", "acquisition", "cycles", "latest"]:
        context.send_json(application.get_latest_acquisition_report() or {"cycle": None})
        return True
    if segments == ["admin", "acquisition", "rollout"]:
        context.send_json(application.get_production_rollout_status())
        return True
    if segments == ["admin", "acquisition", "rollout", "health"]:
        context.send_json(application.get_production_rollout_health())
        return True
    if segments == ["admin", "acquisition", "staging"] or (
        len(segments) == 4 and segments[:3] == ["admin", "acquisition", "staging"]
    ):
        publication_id = segments[3] if len(segments) == 4 else ""
        context.send_json(
            application.get_staging_acquisition_catalog(
                publication_id=publication_id,
                limit=_int_query(query, "limit", 50, 200),
                offset=_int_query(query, "offset", 0, 100000),
            )
        )
        return True
    if len(segments) == 4 and segments[:3] == ["admin", "acquisition", "cycles"]:
        context.send_json(application.get_acquisition_cycle_report(segments[3]))
        return True
    if len(segments) == 5 and segments[:3] == ["admin", "acquisition", "cycles"] and segments[4] == "sources":
        context.send_json({"sources": application.get_acquisition_cycle_source_metrics(segments[3])})
        return True
    if len(segments) == 5 and segments[:3] == ["admin", "acquisition", "cycles"] and segments[4] == "targets":
        context.send_json({"targets": application.list_acquisition_cycle_targets(segments[3])})
        return True
    if len(segments) == 5 and segments[:3] == ["admin", "acquisition", "cycles"] and segments[4] == "report":
        context.send_json(application.get_acquisition_cycle_report(segments[3]))
        return True
    if len(segments) == 5 and segments[:3] == ["admin", "acquisition", "targets"] and segments[4] == "history":
        context.send_json(application.get_acquisition_target_history(segments[3]))
        return True
    return None


def _handle_post(context: ApiRouteContext) -> bool | None:
    context.require_admin()
    segments = list(context.segments)
    if segments == ["admin", "acquisition", "rollout", "configure"]:
        payload = context.read_json_body() or {}
        context.send_json(context.application.configure_production_rollout(payload), status=202)
        return True
    if segments == ["admin", "acquisition", "rollout", "advance"]:
        payload = context.read_json_body() or {}
        stage = str(payload.get("stage") or "").strip()
        context.send_json(context.application.advance_production_rollout(stage), status=202)
        return True
    if len(segments) == 5 and segments[:3] == ["admin", "acquisition", "targets"] and segments[4] == "validate":
        payload = context.read_json_body() or {}
        report = context.application.validate_phase_b_target(
            segments[3], validation_key=str(payload.get("validation_key") or "")
        )
        context.send_json(report, status=202)
        return True
    if len(segments) == 5 and segments[:3] == ["admin", "acquisition", "staging"] and segments[4] == "promote":
        publication_id = context.application.promote_staging_acquisition_catalog(segments[3])
        context.send_json({"publication_id": publication_id, "status": "valid"}, status=202)
        return True
    if len(segments) == 5 and segments[:3] == ["admin", "acquisition", "requests"] and segments[4] == "decision":
        payload = context.read_json_body() or {}
        decision = str(payload.get("decision") or "").strip()
        reason = str(payload.get("reason") or "").strip()
        result = context.application.decide_acquisition_request_recovery(
            segments[3], decision=decision, reason=reason
        )
        context.send_json(result, status=202)
        return True
    if segments != ["admin", "acquisition", "recover"]:
        return None
    report = context.application.recover_acquisition_cycle()
    context.send_json(report or {"status": "not_run"}, status=202)
    return True


def _int_query(query, key: str, default: int, maximum: int) -> int:
    try:
        value = int((query.get(key) or [default])[0])
    except (TypeError, ValueError):
        value = default
    return max(0, min(maximum, value))


__all__ = ["register_routes"]
