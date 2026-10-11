"""Owned-asset CV assistance for the selected published or external job."""
from __future__ import annotations

from collections import OrderedDict
from hashlib import sha256
import json
import os
from threading import Lock
import time

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.domain.models import TOKEN_SCOPE_ARTIFACTS_READ
from backend.profiles.cv_editor import build_cv_editor_payload
from backend.profiles.job_cv_customization import GenerationUnavailable, analyze, generate, normalize_cv

_cache: OrderedDict = OrderedDict()
_lock = Lock()
_active: set[str] = set()


def register_routes(registry: RouteRegistry) -> None:
    for action in ("analyze", "generate"):
        registry.exact("POST", ("cv-customization", action), _handle, auth_required=True,
                       name=f"cv_customization.{action}")


def _handle(context: ApiRouteContext) -> None:
    from backend.api.server import _get_candidate_asset_by_id
    from backend.api.routes.documents import _editor_source_text
    from backend.config.plans import has_runr_pro_access
    user, _ = context.require_scope(TOKEN_SCOPE_ARTIFACTS_READ)
    payload = context.read_json_body()
    if not isinstance(payload, dict) or len(json.dumps(payload)) > 25000:
        context.send_error(422, "invalid_request", "Choose a CV and a job to continue."); return
    action = context.segments[-1]
    preview_allowed = (user.user_id == os.getenv("CV_CUSTOMIZATION_PREVIEW_USER_ID", "")
                       and str(payload.get("job_id") or "") == os.getenv("CV_CUSTOMIZATION_PREVIEW_JOB_ID", "")
                       and bool(os.getenv("CV_CUSTOMIZATION_PREVIEW_JOB_ID")))
    if action == "generate" and not preview_allowed and not has_runr_pro_access(context.application.get_user_plan_id(user.user_id)):
        context.send_error(403, "runr_pro_required", "AI CV customization is included in Runr Pro."); return
    try:
        asset = _get_candidate_asset_by_id(user, str(payload.get("asset_id") or ""))
        if asset.get("asset_kind") != "workspace_cv": raise ValueError("Choose an uploaded CV.")
        job = context.application.get_personalized_job_detail(user.user_id, str(payload.get("job_id") or ""))
        if not job:
            context.send_error(404, "job_not_found", "This job is no longer available."); return
        editor = build_cv_editor_payload(asset, source_text=_editor_source_text(context.application, asset),
                                         shared_profile=dict((user.metadata or {}).get("profile") or {}))
        if payload.get("revision") != editor["revision"]:
            context.send_error(409, "cv_revision_changed", "Your baseline CV changed. Select it again to reload."); return
        cv = normalize_cv(editor["profile"])
        key = sha256(json.dumps([user.user_id, cv, job.get("title"), job.get("description"), job.get("runr_summary"), job.get("structured_description")], sort_keys=True).encode()).hexdigest()
        with _lock:
            cached = _cache.get(key)
            if cached and time.monotonic() - cached[0] > 1800: cached = None
            if user.user_id in _active:
                context.send_error(429, "cv_request_in_progress", "Your CV request is already running. Please wait."); return
            _active.add(user.user_id)
        try:
            requirements = cached[1] if cached else analyze(cv, job)
            with _lock:
                _cache[key] = (time.monotonic(), requirements)
                _cache.move_to_end(key)
                while len(_cache) > 100: _cache.popitem(last=False)
            if action == "analyze":
                context.send_json({"requirements": requirements, "revision": editor["revision"]})
            else:
                options = payload.get("options") or {}
                if not isinstance(options, dict): raise ValueError("Invalid enhancement choices.")
                draft, changes = generate(cv, job, requirements, options)
                context.send_json({"draft": draft, "changes": changes, "requirements": requirements, "generated_by": "deepseek", "revision": editor["revision"]})
        finally:
            with _lock: _active.discard(user.user_id)
    except GenerationUnavailable as exc:
        context.send_error(503, "cv_generation_unavailable", str(exc))
    except (ValueError, TypeError, KeyError) as exc:
        context.send_error(422, "invalid_cv_request", str(exc) if isinstance(exc, ValueError) else "Please reload the CV and try again.")
