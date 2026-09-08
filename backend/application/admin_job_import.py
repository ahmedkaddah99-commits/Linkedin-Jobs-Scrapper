from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
import os
from typing import Any
from urllib.parse import urlsplit

from backend.acquisition.manifest import load_phase_a_manifest
from backend.acquisition.collection_controls import (
    DEFAULT_MAX_CREDITS,
    DEFAULT_MAX_PAGES,
    DEFAULT_MAX_REQUESTS,
    MAX_JOB_LIMIT,
    normalize_optional_limit,
    normalize_retrieval_mode,
    resolve_job_limits,
)
from backend.connectors.company_career_sites import estimate_company_site_runner_credit_range
from backend.connectors.capabilities import get_connector_capabilities


_DEFAULT_MAX_REQUESTS = DEFAULT_MAX_REQUESTS
_DEFAULT_MAX_PAGES = DEFAULT_MAX_PAGES
_DEFAULT_MAX_CREDITS = DEFAULT_MAX_CREDITS
_SUPPORTED_SCOPE_FIELDS = {
    "country",
    "city",
    "cities",
    "remote",
    "department",
    "category",
    "keywords",
    "full_source_import",
    "max_pages",
    "max_requests",
    "max_credits",
    "retrieval_mode",
    "max_jobs",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).casefold() in {"1", "true", "yes", "on", "enabled"}


def _int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return max(0, int(default))


def _list(value: Any) -> list[str]:
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = []
    return list(dict.fromkeys(_text(item) for item in values if _text(item)))


def _host(url: str) -> str:
    return (_text(urlsplit(_text(url)).hostname) or "").casefold()


class AdminJobImportService:
    """Product-facing orchestration over the existing acquisition repository."""

    def __init__(self, *, repositories: Any, scheduler: Any) -> None:
        self.repositories = repositories
        self.scheduler = scheduler

    def _config(self, key: str, default: Any = None) -> Any:
        store = getattr(self.repositories, "config_store", None)
        getter = getattr(store, "get_value", None)
        return getter(key, default) if callable(getter) else default

    def imports_paused(self) -> bool:
        production = _text(os.getenv("RUNR_ENV")).casefold() in {"prod", "production"}
        if _bool(self._config("acquisition.admin_imports.kill_switch", not production)):
            return True
        return not _bool(self._config("acquisition.admin_imports.enabled", production))

    def list_sources(self) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        for target in load_phase_a_manifest():
            target_id = _text(target.get("target_id"))
            connector = _text(target.get("connector")).casefold()
            capabilities = get_connector_capabilities(connector, target=target)
            official = capabilities.get("access_method") == "direct"
            admin_import_enabled = official or _bool(target.get("admin_import_enabled"))
            method = str(capabilities.get("access_method") or "direct")
            source_type = "Official source" if official else "Web import"
            target_url = _text(target.get("request_url") or target.get("canonical_target_url"))
            source_status = "ready" if admin_import_enabled else "source_paused"
            reason = "" if admin_import_enabled else _text(target.get("disabled_reason") or "Source validation required")
            sources.append(
                {
                    "id": target_id,
                    "company": _text(target.get("canonical_company_name") or target.get("display_name")),
                    "name": _text(target.get("display_name") or target_id),
                    "source_type": source_type,
                    "method": method,
                    "connector": connector,
                    "supported_locations": ["Germany"],
                    "last_import": "",
                    "jobs_found": 0,
                    "status": source_status,
                    "reason": reason,
                    "request_hosts": list(dict.fromkeys(filter(None, [_host(target_url), _host(target.get("canonical_target_url", ""))]))),
                    "target_url": target_url,
                    "max_pages": min(
                        int(capabilities.get("max_pages") or _DEFAULT_MAX_PAGES),
                        1 if official and not capabilities.get("supports_all_available") else _DEFAULT_MAX_PAGES,
                    ),
                    "available": True,
                    "retrieval_modes": list(capabilities.get("retrieval_modes") or ("bounded", "custom")),
                    "all_available": {
                        "available": bool(capabilities.get("supports_all_available")),
                        "reliable_pagination": bool(capabilities.get("reliable_pagination")),
                        "reason": "" if capabilities.get("supports_all_available") else "reliable_pagination_unavailable",
                    },
                    "capabilities": capabilities,
                    "advanced": {
                        "target_id": target_id,
                        "provider": _text(target.get("provider")),
                        "request_mode": _text(target.get("request_mode") or "direct"),
                        "policy_version": _text(target.get("policy_version")),
                        "disabled_reason": reason,
                    },
                }
            )
        return sources

    def _manifest(self) -> dict[str, dict[str, Any]]:
        return {_text(item.get("target_id")): dict(item) for item in load_phase_a_manifest()}

    def normalize_scope(self, payload: Mapping[str, Any] | None) -> dict[str, Any]:
        incoming = dict(payload or {})
        unknown = sorted(set(incoming) - _SUPPORTED_SCOPE_FIELDS)
        if unknown:
            raise ValueError(f"Unsupported import filters: {', '.join(unknown)}")
        cities = _list(incoming.get("cities") or incoming.get("city"))
        keywords = _list(incoming.get("keywords"))
        scope = {
            "retrieval_mode": normalize_retrieval_mode(incoming.get("retrieval_mode")),
            "country": _text(incoming.get("country")),
            "cities": cities,
            "remote": _bool(incoming.get("remote")),
            "department": _text(incoming.get("department")),
            "category": _text(incoming.get("category")),
            "keywords": keywords,
            "full_source_import": _bool(incoming.get("full_source_import")),
            "max_pages": max(1, min(_DEFAULT_MAX_PAGES, _int(incoming.get("max_pages"), _DEFAULT_MAX_PAGES))),
            "max_requests": max(1, min(_DEFAULT_MAX_REQUESTS, _int(incoming.get("max_requests"), _DEFAULT_MAX_REQUESTS))),
            "max_credits": _int(incoming.get("max_credits"), _DEFAULT_MAX_CREDITS),
            "max_jobs": normalize_optional_limit(
                incoming.get("max_jobs"),
                default=0,
                maximum=MAX_JOB_LIMIT,
            ),
        }
        if scope["full_source_import"]:
            scope["country"] = ""
            scope["cities"] = []
            scope["remote"] = False
            scope["department"] = ""
            scope["category"] = ""
            scope["keywords"] = []
        return scope

    def plan_import(self, *, source_ids: Iterable[str], scope_payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        manifest = self._manifest()
        normalized_sources = list(dict.fromkeys(_text(item) for item in source_ids if _text(item)))
        if not normalized_sources:
            raise ValueError("Choose at least one source.")
        unknown = [item for item in normalized_sources if item not in manifest]
        if unknown:
            raise ValueError("Unsupported source selection.")
        scope = self.normalize_scope(scope_payload)
        configured_max_requests = _int(self._config("acquisition.admin_imports.max_requests", _DEFAULT_MAX_REQUESTS), _DEFAULT_MAX_REQUESTS)
        configured_max_credits = _int(self._config("acquisition.admin_imports.max_credits", _DEFAULT_MAX_CREDITS), _DEFAULT_MAX_CREDITS)
        requests = 0
        min_credits = 0
        likely_credits = 0
        max_credits = 0
        sources: list[dict[str, Any]] = []
        limit_errors: list[str] = []
        paid_cost_data_missing = False
        for source_id in normalized_sources:
            target = manifest[source_id]
            connector = _text(target.get("connector")).casefold()
            capabilities = get_connector_capabilities(connector, target=target)
            official = capabilities.get("access_method") == "direct"
            connector_max_pages = max(1, _int(capabilities.get("max_pages"), scope["max_pages"]))
            connector_max_requests = max(1, _int(capabilities.get("max_requests"), scope["max_requests"]))
            requested_pages = scope["max_pages"]
            if scope["retrieval_mode"] == "bounded":
                requested_pages = min(requested_pages, 1 if official else requested_pages)
            target_max_pages = min(requested_pages, connector_max_pages)
            target_max_requests = min(scope["max_requests"], connector_max_requests)
            if target.get("max_direct_requests"):
                target_max_requests = min(target_max_requests, max(1, _int(target.get("max_direct_requests"), 1)))
            if scope["retrieval_mode"] == "bounded":
                target_max_requests = min(target_max_requests, target_max_pages)
            if scope["retrieval_mode"] == "all_available" and not capabilities.get("supports_all_available"):
                limit_errors.append(f"all_available_not_supported:{source_id}")
            if official:
                requests += target_max_requests
            else:
                estimate = estimate_company_site_runner_credit_range(
                    site_count=1,
                    locality_mode="local_preferred",
                    has_target_country=bool(scope["country"] or scope["cities"]),
                    run_credit_budget=scope["max_credits"] or configured_max_credits or -1,
                )
                min_credits += int(estimate["min_runner_credits"])
                likely_credits += int(estimate["likely_runner_credits"])
                max_credits += int(estimate["max_runner_credits"])
                requests += max(1, target_max_requests)
                if not scope["max_credits"] and not configured_max_credits:
                    paid_cost_data_missing = True
            job_limits = resolve_job_limits(scope, capabilities)
            sources.append(
                {
                    "id": source_id,
                    "name": _text(target.get("display_name") or source_id),
                    "company": _text(target.get("canonical_company_name") or target.get("display_name")),
                    "method": str(capabilities.get("access_method") or "direct"),
                    "source_type": "Official source" if official else "Web import",
                    "request_hosts": list(dict.fromkeys(filter(None, [_host(target.get("request_url", "")), _host(target.get("canonical_target_url", ""))]))),
                    "maximum_pages": target_max_pages,
                    "maximum_requests": target_max_requests,
                    "retrieval_modes": list(capabilities.get("retrieval_modes") or []),
                    "capabilities": capabilities,
                    "requested_job_limit": int(job_limits["requested_job_limit"]),
                    "effective_job_limit": int(job_limits["effective_job_limit"]),
                    "safety_ceiling": int(job_limits["safety_ceiling"]),
                }
            )
        max_credits = max(max_credits, likely_credits, min_credits)
        # Keep validation in one place after the per-source loop so every
        # source is represented in the plan, including unsupported modes.
        requested_max_requests = scope["max_requests"]
        if requests > min(configured_max_requests or _DEFAULT_MAX_REQUESTS, requested_max_requests):
            limit_errors.append("maximum_requests_exceeded")
        if max_credits and scope["max_credits"] and max_credits > scope["max_credits"]:
            limit_errors.append("maximum_credits_exceeded")
        if max_credits and not scope["max_credits"] and configured_max_credits and max_credits > configured_max_credits:
            limit_errors.append("configured_credit_ceiling_exceeded")
        if paid_cost_data_missing:
            limit_errors.append("paid_source_cost_limit_required")
        return {
            "sources": sources,
            "scope": scope,
            "maximum_requests": requests,
            "maximum_pages": max(int(item["maximum_pages"]) for item in sources),
            "maximum_source_requests": sum(int(item.get("maximum_requests") or 0) for item in sources),
            "minimum_credits": min_credits,
            "likely_credits": likely_credits,
            "maximum_credits": max_credits,
            "estimated_cost": {
                "known": not paid_cost_data_missing,
                "currency": "ScrapeOps credits" if max_credits else "USD",
                "maximum": max_credits,
                "note": (
                    "Direct official sources have no ScrapeOps charge."
                    if not max_credits
                    else "Estimate is bounded by the selected or server-configured ScrapeOps credit ceiling."
                ),
            },
            "limit_errors": limit_errors,
            "can_start": not limit_errors,
            "review_first": True,
            "publishes_automatically": False,
            "retrieval_mode": scope["retrieval_mode"],
            "compatibility": {
                "full_source_import": "Legacy scope reset only; it does not imply reliable pagination or all_available.",
            },
        }

    def start_import(
        self,
        *,
        requested_by: str,
        idempotency_key: str,
        source_ids: Iterable[str],
        scope_payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.imports_paused():
            raise PermissionError("Imports are paused. Enable the server-owned import switch before starting a real request.")
        if not _text(requested_by):
            raise PermissionError("An authenticated administrator is required to start an import.")
        plan = self.plan_import(source_ids=source_ids, scope_payload=scope_payload)
        if not plan["can_start"]:
            raise ValueError("Import plan is outside the server-enforced limits: " + ", ".join(plan["limit_errors"]))
        plan["admin_import_execution_enabled"] = True
        plan["admin_import_allow_proxy"] = True
        return self.repositories.acquisition_store.create_job_import(
            idempotency_key=idempotency_key,
            requested_by=requested_by,
            source_ids=[item["id"] for item in plan["sources"]],
            scope=plan["scope"],
            plan=plan,
        )

    def process_next_import(
        self,
        *,
        worker_id: str = "runr-worker",
        worker_role: str = "acquisition",
    ) -> dict[str, Any] | None:
        if str(worker_role or "").strip().casefold() != "acquisition":
            return None
        store = getattr(self.repositories, "acquisition_store", None)
        if store is None:
            return None
        store.requeue_stale_job_imports()
        store.reconcile_terminal_job_imports()
        queued = store.claim_next_job_import(lease_owner=worker_id, worker_role=worker_role)
        if queued is None:
            return None
        import_id = _text(queued.get("import_id"))
        queued_plan = queued.get("plan") if isinstance(queued.get("plan"), Mapping) else {}
        queued_execution_enabled = _bool(queued_plan.get("admin_import_execution_enabled"))
        if self.imports_paused() and not queued_execution_enabled:
            return store.complete_job_import(
                import_id,
                status="blocked",
                error_code="imports_paused",
                error_message="The server-owned import switch is paused.",
            )
        try:
            report = self.scheduler.run_controlled_import(queued, worker_id=worker_id)
            cycle = report.get("cycle") if isinstance(report, Mapping) else {}
            cycle = cycle if isinstance(cycle, Mapping) else {}
            status = "completed" if str(cycle.get("status") or report.get("status")) == "completed" else "needs_attention"
            completed = store.complete_job_import(
                import_id,
                status=status,
                cycle_id=_text(cycle.get("cycle_id")),
                error_code=_text(cycle.get("error_code")),
                error_message=_text(cycle.get("error_message")),
            )
            return {"import": completed, "report": report}
        except Exception as exc:
            store.complete_job_import(import_id, status="failed", error_code=type(exc).__name__.casefold(), error_message=str(exc))
            raise

    def overview(self) -> dict[str, Any]:
        store = self.repositories.acquisition_store
        imports = store.list_job_imports(limit=20, offset=0) if store is not None else []
        latest = imports[0] if imports else None
        review = store.list_review_jobs(import_id=_text((latest or {}).get("import_id")), status="all", limit=200, offset=0) if latest and store is not None else {"jobs": [], "total": 0}
        jobs = review.get("jobs") or []
        counts = {key: sum(1 for item in jobs if item.get("review_state") == key) for key in ("needs_review", "approved", "not_accepted", "already_live")}
        worker_rows = []
        worker_store = getattr(self.repositories, "worker_store", None)
        if worker_store is not None and hasattr(worker_store, "list_workers"):
            worker_rows = worker_store.list_workers(limit=20, offset=0)
        worker_online = any(_text(getattr(item, "status", item.get("status") if isinstance(item, Mapping) else "")).casefold() in {"idle", "running"} for item in worker_rows)
        current = store.get_public_catalog(limit=1, offset=0) if store is not None else {"total": 0, "publication": None}
        warnings = []
        if self.imports_paused():
            warnings.append("Imports are paused; no external request can start.")
        if latest and _text(latest.get("error_message")):
            warnings.append(_text(latest.get("error_message")))
        return {
            "imports": {
                "status": "Paused" if self.imports_paused() else ("Running" if latest and latest.get("status") == "running" else "Ready"),
                "paused": self.imports_paused(),
                "last": latest,
                "today": sum(1 for item in imports if _text(item.get("created_at", "")).startswith(datetime.now(timezone.utc).date().isoformat())),
            },
            "jobs_found": int((latest or {}).get("plan", {}).get("jobs_found", 0) or 0),
            "review": counts,
            "current_live_jobs": int(current.get("total") or 0),
            "last_publication": current.get("publication"),
            "worker": {"status": "Online" if worker_online else "Offline", "workers": len(worker_rows)},
            "estimated_spend_today": {"credits": 0, "currency": "USD", "known": False},
            "warnings": warnings,
            "history": imports,
        }


__all__ = ["AdminJobImportService"]
