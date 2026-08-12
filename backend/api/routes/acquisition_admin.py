from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.api.routes.registry import ApiRouteContext, RouteRegistry


def register_routes(registry: RouteRegistry) -> None:
    registry.prefix("GET", ("admin", "acquisition"), _handle_get, auth_required=True, name="admin.acquisition.get")
    registry.prefix("POST", ("admin", "acquisition"), _handle_post, auth_required=True, name="admin.acquisition.post")


def _handle_get(context: ApiRouteContext) -> bool | None:
    context.require_admin()
    application = context.application
    segments = list(context.segments)
    query = context.query
    if segments == ["admin", "acquisition", "overview"]:
        context.send_json(application.get_admin_job_import_overview())
        return True
    if segments == ["admin", "acquisition", "sources"]:
        context.send_json({"sources": application.list_admin_job_import_sources()})
        return True
    if segments == ["admin", "acquisition", "jobs"]:
        context.send_json(application.list_admin_job_inspections(**_job_query(query)))
        return True
    if len(segments) == 4 and segments[:3] == ["admin", "acquisition", "jobs"]:
        include_history = _flag_query(query, "include_history")
        inspection = application.get_admin_job_inspection(
            segments[3],
            include_history=include_history,
            history_limit=500 if include_history else None,
        )
        if inspection is None:
            return _error(context, 404, "canonical_job_not_found", "Canonical job not found.")
        context.send_json(inspection)
        return True
    if segments == ["admin", "acquisition", "duplicates"]:
        context.send_json({"clusters": application.list_admin_duplicate_clusters(limit=_int_query(query, "limit", 100, 500))})
        return True
    if segments == ["admin", "acquisition", "companies"]:
        context.send_json({"companies": application.list_admin_companies(limit=_int_query(query, "limit", 100, 500), search=_query_value(query, "search"))})
        return True
    if len(segments) == 4 and segments[:3] == ["admin", "acquisition", "companies"]:
        company = application.get_admin_company_detail(segments[3])
        if company is None:
            return _error(context, 404, "company_not_found", "Canonical company not found.")
        context.send_json({"company": company})
        return True
    if segments == ["admin", "acquisition", "connectors", "capabilities"]:
        context.send_json({"connectors": application.list_admin_connector_capabilities(limit=_int_query(query, "limit", 200, 1000))})
        return True
    if segments == ["admin", "acquisition", "retention"]:
        snapshots = application.list_admin_connector_capabilities(limit=_int_query(query, "limit", 200, 1000))
        context.send_json({"snapshots": snapshots, "report_only": True})
        return True
    if segments == ["admin", "acquisition", "rules"]:
        context.send_json(application.get_admin_rules_coverage())
        return True
    if segments == ["admin", "acquisition", "reprocessing"]:
        context.send_json({"runs": application.list_admin_reprocessing_runs(limit=_int_query(query, "limit", 50, 200))})
        return True
    if segments == ["admin", "acquisition", "reprocessing", "plan"]:
        context.send_json(application.get_admin_reprocessing_plan(scope=_scope_query(query)))
        return True
    if segments == ["admin", "acquisition", "publication"]:
        context.send_json(application.get_admin_publication_read_model())
        return True
    if segments == ["admin", "acquisition", "imports"]:
        context.send_json({"imports": application.list_admin_job_imports(limit=_int_query(query, "limit", 50, 200), offset=_int_query(query, "offset", 0, 100000))})
        return True
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
    if len(segments) == 5 and segments[:3] == ["admin", "acquisition", "cycles"] and segments[4] == "evidence":
        context.send_json(application.get_production_rollout_evidence(segments[3]))
        return True
    if len(segments) == 5 and segments[:3] == ["admin", "acquisition", "targets"] and segments[4] == "history":
        context.send_json(application.get_acquisition_target_history(segments[3]))
        return True
    return None


def _handle_post(context: ApiRouteContext) -> bool | None:
    admin = context.require_admin()
    segments = list(context.segments)
    payload = context.read_json_body() or {}
    if not isinstance(payload, Mapping):
        payload = {}
    if segments == ["admin", "acquisition", "imports", "plan"]:
        context.send_json(
            context.application.plan_admin_job_import(
                source_ids=[str(item) for item in payload.get("source_ids") or []],
                scope=dict(payload.get("scope") or {}),
            )
        )
        return True
    if segments == ["admin", "acquisition", "imports"]:
        idempotency_key = _text(payload.get("idempotency_key"))
        if not idempotency_key:
            return _error(context, 400, "idempotency_key_required", "Start import requires an idempotency key.")
        try:
            context.send_json(
                context.application.start_admin_job_import(
                    requested_by=_actor_user_id(admin),
                    idempotency_key=idempotency_key,
                    source_ids=[str(item) for item in payload.get("source_ids") or []],
                    scope=dict(payload.get("scope") or {}),
                ),
                status=202,
            )
        except PermissionError as exc:
            return _error(context, 423, "imports_paused", str(exc))
        except ValueError as exc:
            return _error(context, 400, "invalid_job_import_request", str(exc))
        return True
    if segments in (["admin", "acquisition", "reprocessing", "run"], ["admin", "acquisition", "reprocessing", "apply"]):
        try:
            context.send_json(
                context.application.run_admin_reprocessing(
                    apply=_flag(payload.get("apply")),
                    batch_size=_int_value(payload.get("batch_size"), 100, 1000),
                    idempotency_key=_text(payload.get("idempotency_key")),
                    resume_id=_text(payload.get("resume_id")),
                    scope=dict(payload.get("scope") or {}),
                    allow_remote_additive_rollback=_flag(payload.get("allow_remote_additive_rollback")),
                ),
                status=202,
            )
        except ValueError as exc:
            return _error(context, 400, "invalid_reprocessing_request", str(exc))
        return True
    if segments == ["admin", "acquisition", "publication", "preview"]:
        try:
            context.send_json(
                context.application.preview_admin_job_import(
                    _text(payload.get("import_id")),
                    actor_user_id=_actor_user_id(admin),
                ),
                status=202,
            )
        except ValueError as exc:
            return _error(context, 400, "invalid_publication_request", str(exc))
        return True
    if segments == ["admin", "acquisition", "publication", "publish"]:
        try:
            publication_id = context.application.publish_admin_job_import(
                _text(payload.get("publication_id")),
                actor_user_id=_actor_user_id(admin),
            )
        except ValueError as exc:
            return _error(context, 400, "invalid_publication_request", str(exc))
        context.send_json({"publication_id": publication_id, "status": "published"}, status=202)
        return True
    if segments == ["admin", "acquisition", "publication", "undo"]:
        try:
            context.send_json(
                context.application.undo_admin_job_publication(actor_user_id=_actor_user_id(admin)),
                status=202,
            )
        except ValueError as exc:
            return _error(context, 400, "invalid_publication_request", str(exc))
        return True
    if len(segments) == 5 and segments[:3] == ["admin", "acquisition", "companies"] and segments[4] == "enrich":
        return _error(
            context,
            400,
            "company_scoped_enrichment_required",
            "Use an explicit company-scoped enrichment plan and run.",
        )
    if segments == ["admin", "acquisition", "companies", "enrich"]:
        return _error(
            context,
            400,
            "batch_company_enrichment_disabled",
            "Batch company enrichment is disabled; select a company explicitly.",
        )
    if len(segments) == 5 and segments[:3] == ["admin", "acquisition", "duplicate-clusters"] and segments[4] == "decisions":
        try:
            context.send_json(
                context.application.record_admin_duplicate_decision(
                    segments[3],
                    decision=_text(payload.get("decision") or payload.get("state")),
                    actor_user_id=_actor_user_id(admin),
                    reason=_text(payload.get("reason")),
                    evidence=dict(payload.get("evidence") or {}),
                    affected_ids=[str(item) for item in payload.get("affected_ids") or []] or None,
                    rule_version=_text(payload.get("rule_version")),
                    merge_plan=payload.get("merge_plan") if isinstance(payload.get("merge_plan"), Mapping) else None,
                    split_plan=payload.get("split_plan") if isinstance(payload.get("split_plan"), Mapping) else None,
                    undo_plan=payload.get("undo_plan") if isinstance(payload.get("undo_plan"), Mapping) else None,
                    supersedes_decision_id=_text(payload.get("supersedes_decision_id")),
                ),
                status=202,
            )
        except KeyError as exc:
            return _error(context, 404, "duplicate_cluster_not_found", str(exc))
        except ValueError as exc:
            return _error(context, 400, "invalid_duplicate_decision", str(exc))
        return True
    if len(segments) == 5 and segments[:3] == ["admin", "acquisition", "duplicate-clusters"] and segments[4] == "undo":
        try:
            context.send_json(
                context.application.undo_admin_duplicate_decision(
                    segments[3],
                    actor_user_id=_actor_user_id(admin),
                    reason=_text(payload.get("reason") or "Admin undo"),
                    evidence=dict(payload.get("evidence") or {"source": "admin_review"}),
                    rule_version=_text(payload.get("rule_version")),
                ),
                status=202,
            )
        except (KeyError, ValueError) as exc:
            return _error(context, 400, "invalid_duplicate_undo", str(exc))
        return True
    if segments == ["admin", "acquisition", "connectors", "capabilities", "snapshot"]:
        context.send_json({"connectors": context.application.record_admin_connector_capability_snapshots()}, status=202)
        return True
    if segments == ["admin", "acquisition", "rollout", "configure"]:
        context.send_json(context.application.configure_production_rollout(payload), status=202)
        return True
    if segments == ["admin", "acquisition", "rollout", "advance"]:
        stage = str(payload.get("stage") or "").strip()
        context.send_json(context.application.advance_production_rollout(stage), status=202)
        return True
    if len(segments) == 5 and segments[:3] == ["admin", "acquisition", "targets"] and segments[4] == "validate":
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


def _job_query(query: Mapping[str, list[str]]) -> dict[str, Any]:
    values = (
        "search", "function", "subfunction", "employment_type", "workplace", "location",
        "language", "seniority", "source", "freshness", "completeness_state", "warning_type",
        "duplicate_state", "application_method", "publication_state",
    )
    result = {_key: _query_value(query, _key) for _key in values}
    result["limit"] = _int_query(query, "limit", 100, 200)
    result["offset"] = _int_query(query, "offset", 0, 100000)
    return result


def _query_value(query: Mapping[str, list[str]], key: str) -> str:
    values = query.get(key) or []
    return _text(values[0]) if values else ""


def _flag_query(query: Mapping[str, list[str]], key: str) -> bool:
    return _text(_query_value(query, key)).casefold() in {"1", "true", "yes", "on", "enabled"}


def _scope_query(query: Mapping[str, list[str]]) -> dict[str, Any]:
    return {
        key: _query_value(query, key)
        for key in ("country", "city", "department", "category", "freshness")
        if _query_value(query, key)
    }


def _int_value(value: Any, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(maximum, parsed))


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).casefold() in {"1", "true", "yes", "on", "enabled"}


def _actor_user_id(value: Any) -> str:
    user = value[0] if isinstance(value, tuple) else value
    if isinstance(user, Mapping):
        return _text(user.get("user_id") or user.get("id"))
    return _text(getattr(user, "user_id", "") or getattr(user, "id", ""))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _error(context: ApiRouteContext, status: int, code: str, message: str) -> bool:
    context.send_error(status, code, message)
    return True


__all__ = ["register_routes"]
