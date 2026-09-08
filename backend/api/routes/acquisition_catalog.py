from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.api.routes.registry import ApiRouteContext, RouteRegistry


def register_routes(registry: RouteRegistry) -> None:
    registry.exact("GET", ("personalized-jobs",), _handle_get, auth_required=True, name="personalized_jobs.read")
    registry.exact("GET", ("personalized-jobs", "preferences"), _handle_preferences, auth_required=True, name="personalized_jobs.preferences.read")
    registry.exact("PUT", ("personalized-jobs", "preferences"), _handle_preferences, auth_required=True, name="personalized_jobs.preferences.write")
    registry.exact("PATCH", ("personalized-jobs", "preferences"), _handle_preferences, auth_required=True, name="personalized_jobs.preferences.patch")
    registry.exact("GET", ("personalized-jobs", "saved-search"), _handle_saved_search, auth_required=True, name="personalized_jobs.saved_search.read")
    registry.exact("PUT", ("personalized-jobs", "saved-search"), _handle_saved_search, auth_required=True, name="personalized_jobs.saved_search.write")
    registry.exact("POST", ("personalized-jobs", "saved-search"), _handle_saved_search, auth_required=True, name="personalized_jobs.saved_search.post")
    registry.exact("GET", ("personalized-jobs", "hidden"), _handle_hidden, auth_required=True, name="personalized_jobs.hidden.read")
    registry.exact("POST", ("personalized-jobs", "report"), _handle_report_without_job, auth_required=True, name="personalized_jobs.report")
    registry.prefix("GET", ("personalized-jobs", "companies", "{company_id}"), _handle_company, auth_required=True, name="personalized_jobs.company.read_prefix")
    registry.prefix("GET", ("personalized-jobs",), _handle_job_or_feed, auth_required=True, name="personalized_jobs.job.read")
    registry.prefix("POST", ("personalized-jobs",), _handle_job_action, auth_required=True, name="personalized_jobs.job.action")
    registry.prefix("DELETE", ("personalized-jobs",), _handle_job_delete, auth_required=True, name="personalized_jobs.job.delete")


def _handle_get(context: ApiRouteContext) -> bool | None:
    if list(context.segments) != ["personalized-jobs"]:
        return None
    # Preserve the Phase A read-only route contract for lightweight route
    # doubles that predate the Phase C application method.
    if not callable(getattr(type(context.application), "get_personalized_jobs", None)):
        context.require_identity()
        query = context.query
        context.send_json(
            context.application.get_public_acquisition_catalog(
                limit=_int_query(query, "limit", 50, 200),
                offset=_int_query(query, "offset", 0, 100000),
            )
        )
        return True
    return _send_feed(context)


def _handle_preferences(context: ApiRouteContext) -> bool | None:
    user_id = _identity_user_id(context)
    if context.method == "GET":
        context.send_json(context.application.get_personalized_preferences(user_id) or {"user_id": user_id, "preferences": None, "revision": 0})
        return True
    body = _body(context)
    expected_revision = body.get("expected_revision")
    if expected_revision is not None:
        try:
            expected_revision = int(expected_revision)
        except (TypeError, ValueError):
            return _error(context, 400, "invalid_revision", "expected_revision must be an integer")
    context.send_json(context.application.save_personalized_preferences(user_id, body, expected_revision=expected_revision))
    return True


def _handle_saved_search(context: ApiRouteContext) -> bool | None:
    user_id = _identity_user_id(context)
    if context.method == "GET":
        context.send_json(context.application.get_personalized_saved_search(user_id) or {"user_id": user_id, "name": "Default search", "filters": {}, "is_default": True})
        return True
    context.send_json(context.application.save_personalized_saved_search(user_id, _body(context)))
    return True


def _handle_hidden(context: ApiRouteContext) -> bool | None:
    user_id = _identity_user_id(context)
    context.send_json(
        context.application.get_hidden_personalized_jobs(
            user_id,
            limit=_int_query(context.query, "limit", 25, 100),
            cursor=_query_value(context.query, "cursor"),
        )
    )
    return True


def _handle_company(context: ApiRouteContext) -> bool | None:
    if len(context.segments) != 3 or context.segments[:2] != ("personalized-jobs", "companies"):
        return False
    company_id = context.segments[2]
    user_id = _identity_user_id(context)
    detail = context.application.get_personalized_company_detail(
        user_id,
        company_id,
        plan_id=_plan_id(context, user_id),
    )
    if detail is None:
        return _error(context, 404, "company_not_found", "Company is not available in the shared catalog")
    context.send_json(detail)
    return True


def _handle_job_or_feed(context: ApiRouteContext) -> bool | None:
    if context.segments == ("personalized-jobs",):
        return _send_feed(context)
    if len(context.segments) != 2 or context.segments[0] != "personalized-jobs":
        return False
    user_id = _identity_user_id(context)
    detail = context.application.get_personalized_job_detail(
        user_id,
        context.segments[1],
        plan_id=_plan_id(context, user_id),
    )
    if detail is None:
        return _error(context, 404, "job_not_found", "Job is not available in the shared catalog")
    context.send_json(detail)
    return True


def _handle_job_action(context: ApiRouteContext) -> bool | None:
    if len(context.segments) != 3 or context.segments[0] != "personalized-jobs":
        return False
    posting_id, action = context.segments[1], context.segments[2]
    user_id = _identity_user_id(context)
    body = _body(context)
    try:
        if action == "save":
            result = context.application.set_personalized_job_state(user_id, posting_id, "saved", reason_code=_text(body.get("reason_code")))
        elif action == "hide":
            result = context.application.set_personalized_job_state(user_id, posting_id, "hidden", reason_code=_text(body.get("reason_code")))
        elif action == "restore":
            result = context.application.set_personalized_job_state(user_id, posting_id, "none", reason_code=_text(body.get("reason_code")))
        elif action == "applied":
            result = context.application.set_personalized_job_state(user_id, posting_id, "applied", reason_code=_text(body.get("reason_code")))
        elif action == "report":
            result = context.application.report_personalized_job(user_id, posting_id, reason_code=_text(body.get("reason_code")), payload=body)
        elif action == "precompute":
            result = context.application.enqueue_personalized_job_intelligence(user_id, posting_id)
        elif action == "improve-resume":
            result = context.application.improve_personalized_resume(
                user_id,
                posting_id,
                mode=_text(body.get("mode") or "review"),
                plan_id=_plan_id(context, user_id),
            )
        else:
            return False
    except KeyError:
        return _error(context, 404, "job_not_found", "Job is not available in the shared catalog")
    except ValueError as exc:
        return _error(context, 400, "invalid_job_action", str(exc))
    except PermissionError as exc:
        return _error(context, 403, "runr_pro_required", str(exc))
    context.send_json(result)
    return True


def _handle_job_delete(context: ApiRouteContext) -> bool | None:
    if len(context.segments) != 3 or context.segments[0] != "personalized-jobs" or context.segments[2] != "save":
        return False
    try:
        result = context.application.set_personalized_job_state(_identity_user_id(context), context.segments[1], "none")
    except KeyError:
        return _error(context, 404, "job_not_found", "Job is not available in the shared catalog")
    context.send_json(result)
    return True


def _handle_report_without_job(context: ApiRouteContext) -> bool | None:
    body = _body(context)
    posting_id = _text(body.get("posting_id") or body.get("canonical_job_id"))
    if not posting_id:
        context.send_json(context.application.report_personalized_filter(_identity_user_id(context), reason_code=_text(body.get("reason_code")), payload=body))
        return True
    try:
        result = context.application.report_personalized_job(_identity_user_id(context), posting_id, reason_code=_text(body.get("reason_code")), payload=body)
    except KeyError:
        return _error(context, 404, "job_not_found", "Job is not available in the shared catalog")
    context.send_json(result)
    return True


def _send_feed(context: ApiRouteContext) -> bool:
    user_id = _identity_user_id(context)
    filters = _filters_from_query(context.query)
    context.send_json(
        context.application.get_personalized_jobs(
            user_id,
            filters=filters,
            cursor=_query_value(context.query, "cursor"),
            limit=_int_query(context.query, "limit", 25, 100),
            include_hidden=_bool_query(context.query, "include_hidden", False),
            hidden_only=False,
            plan_id=_plan_id(context, user_id),
            card_view=_query_value(context.query, "view").casefold() == "cards",
        )
    )
    return True


def _filters_from_query(query: Mapping[str, list[str]]) -> dict[str, Any]:
    recognized = {
        "q", "search", "search_text", "role", "roles", "category", "categories", "location",
        "work_arrangement", "employment_type", "experience", "experience_level", "seniority",
        "salary_min", "salary_max", "language", "languages", "work_authorization", "sponsorship",
        "posted_within_days", "company", "industry", "company_size", "company_stage", "funding_stage",
        "funding_min", "funding_max", "founded_year_min", "founded_year_max",
        "funding_year_min", "funding_year_max", "hidden_companies", "excluded_companies",
        "education", "preferred_major", "preferred_majors", "security_clearance",
        "lifting_requirement", "physical_requirement",
        "sort",
    }
    result: dict[str, Any] = {}
    for key in recognized:
        values = query.get(key) or []
        if values:
            result[key] = values if len(values) > 1 else values[0]
    return result


def _plan_id(context: ApiRouteContext, user_id: str) -> str:
    resolver = getattr(context.application, "get_user_plan_id", None)
    if callable(resolver):
        return str(resolver(user_id) or "none")
    return "none"


def _identity_user_id(context: ApiRouteContext) -> str:
    identity = context.require_identity()
    user = identity[0] if isinstance(identity, tuple) else identity
    if isinstance(user, Mapping):
        user_id = user.get("user_id") or user.get("id")
    else:
        user_id = getattr(user, "user_id", None) or getattr(user, "id", None)
    user_id = _text(user_id)
    if not user_id:
        raise PermissionError("Authenticated user identity is required")
    return user_id


def _body(context: ApiRouteContext) -> dict[str, Any]:
    value = context.read_json_body()
    return dict(value) if isinstance(value, Mapping) else {}


def _query_value(query: Mapping[str, list[str]], key: str) -> str:
    values = query.get(key) or []
    return _text(values[0]) if values else ""


def _int_query(query: Mapping[str, list[str]], key: str, default: int, maximum: int) -> int:
    try:
        value = int(_query_value(query, key) or default)
    except (TypeError, ValueError):
        value = default
    return max(0, min(maximum, value))


def _bool_query(query: Mapping[str, list[str]], key: str, default: bool) -> bool:
    value = _query_value(query, key)
    return default if not value else value.casefold() in {"1", "true", "yes", "on"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _error(context: ApiRouteContext, status: int, code: str, message: str) -> bool:
    context.send_error(status, code, message)
    return True


__all__ = ["register_routes"]
