from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping
from uuid import uuid4

from backend.config.plans import PLANS, normalize_plan_id
from backend.domain.models import utc_now_iso
from backend.integrations.scrapeops import SCRAPEOPS_POLICY_VERSION, SCRAPEOPS_REQUEST_MODES

SCRAPEOPS_ADMIN_POLICY_CONFIG_KEY = "scrapeops.admin_policy"
SCRAPEOPS_LOCALITY_MODE_LOCAL_PREFERRED = "local_preferred"
SCRAPEOPS_LOCALITY_MODE_STRICT_LOCAL_ONLY = "strict_local_only"
SCRAPEOPS_LOCALITY_MODES = {
    SCRAPEOPS_LOCALITY_MODE_LOCAL_PREFERRED,
    SCRAPEOPS_LOCALITY_MODE_STRICT_LOCAL_ONLY,
}
DEFAULT_SITE_REQUEST_MODES = ["basic", "render_js_cheap", "render_js_residential"]
DEFAULT_JOB_DETAIL_REQUEST_MODES = ["basic", "render_js_cheap", "render_js", "render_js_residential"]


def _normalize_limit(value: Any, *, default: int) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return int(default)
    return -1 if normalized == -1 else max(0, normalized)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_bool(value: Any, *, default: bool = True) -> bool:
    if value in {None, ""}:
        return bool(default)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"0", "false", "no", "off"}:
            return False
        if normalized in {"1", "true", "yes", "on"}:
            return True
    return bool(value)


def _normalize_request_modes(value: Any, *, default: list[str]) -> list[str]:
    raw_items = value if isinstance(value, (list, tuple, set)) else default
    normalized: list[str] = []
    for item in raw_items:
        mode = _normalize_text(item)
        if not mode or mode not in SCRAPEOPS_REQUEST_MODES:
            continue
        if mode not in normalized:
            normalized.append(mode)
    return normalized or list(default)


def _default_plan_policies() -> dict[str, dict[str, int]]:
    payload: dict[str, dict[str, int]] = {}
    for plan_id, plan in PLANS.items():
        payload[plan_id] = {
            "runner_credits_per_month": int((plan.get("quotas") or {}).get("runner_credits_per_month") or 0),
            "company_sites_per_run": int((plan.get("limits") or {}).get("company_sites_per_run") or 0),
            "runner_credits_per_run": int((plan.get("limits") or {}).get("runner_credits_per_run") or 0),
        }
    return payload


def default_scrapeops_admin_policy() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "policy_version": SCRAPEOPS_POLICY_VERSION,
        "updated_at": utc_now_iso(),
        "plan_policies": _default_plan_policies(),
        "user_overrides": [],
        "domain_policies": [],
        "alert_policy": {
            "enabled": True,
            "cadence_hours": 6,
            "low_remaining_credits_threshold": 250,
            "discrepancy_threshold": 100,
            "history_days": 30,
        },
    }


def _normalize_plan_policies(payload: Any) -> dict[str, dict[str, int]]:
    normalized = _default_plan_policies()
    if not isinstance(payload, Mapping):
        return normalized
    for raw_plan_id, raw_policy in payload.items():
        plan_id = normalize_plan_id(raw_plan_id)
        if not isinstance(raw_policy, Mapping):
            continue
        default_policy = normalized.get(plan_id, {})
        normalized[plan_id] = {
            "runner_credits_per_month": _normalize_limit(
                raw_policy.get("runner_credits_per_month"),
                default=int(default_policy.get("runner_credits_per_month") or 0),
            ),
            "company_sites_per_run": _normalize_limit(
                raw_policy.get("company_sites_per_run"),
                default=int(default_policy.get("company_sites_per_run") or 0),
            ),
            "runner_credits_per_run": _normalize_limit(
                raw_policy.get("runner_credits_per_run"),
                default=int(default_policy.get("runner_credits_per_run") or 0),
            ),
        }
    return normalized


def _normalize_user_override(item: Mapping[str, Any]) -> dict[str, Any]:
    user_id = _normalize_text(item.get("user_id"))
    if not user_id:
        raise ValueError("user_id is required for a ScrapeOps user override.")
    return {
        "override_id": _normalize_text(item.get("override_id")) or f"user_override_{uuid4().hex[:10]}",
        "user_id": user_id,
        "plan_id": normalize_plan_id(item.get("plan_id") or "free"),
        "runner_credits_per_month": _normalize_limit(item.get("runner_credits_per_month"), default=0),
        "company_sites_per_run": _normalize_limit(item.get("company_sites_per_run"), default=0),
        "runner_credits_per_run": _normalize_limit(item.get("runner_credits_per_run"), default=0),
        "notes": _normalize_text(item.get("notes")),
        "is_active": _normalize_bool(item.get("is_active"), default=True),
    }


def _normalize_domain_policy(item: Mapping[str, Any]) -> dict[str, Any]:
    domain_pattern = _normalize_text(item.get("domain_pattern"))
    company_name_pattern = _normalize_text(item.get("company_name_pattern"))
    if not domain_pattern and not company_name_pattern:
        raise ValueError("A ScrapeOps domain policy needs a domain pattern or company-name pattern.")
    locality_mode = _normalize_text(item.get("locality_mode"))
    if locality_mode and locality_mode not in SCRAPEOPS_LOCALITY_MODES:
        locality_mode = ""
    return {
        "policy_id": _normalize_text(item.get("policy_id")) or f"domain_policy_{uuid4().hex[:10]}",
        "domain_pattern": domain_pattern,
        "company_name_pattern": company_name_pattern,
        "site_request_modes": _normalize_request_modes(
            item.get("site_request_modes"),
            default=DEFAULT_SITE_REQUEST_MODES,
        ),
        "job_detail_request_modes": _normalize_request_modes(
            item.get("job_detail_request_modes"),
            default=DEFAULT_JOB_DETAIL_REQUEST_MODES,
        ),
        "locality_mode": locality_mode,
        "country_code": _normalize_text(item.get("country_code")).upper(),
        "notes": _normalize_text(item.get("notes")),
        "priority": max(0, _normalize_limit(item.get("priority"), default=100)),
        "is_active": _normalize_bool(item.get("is_active"), default=True),
    }


def normalize_scrapeops_admin_policy(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    base = default_scrapeops_admin_policy()
    raw = dict(payload or {})
    normalized = deepcopy(base)
    normalized["schema_version"] = 1
    normalized["policy_version"] = _normalize_text(raw.get("policy_version")) or SCRAPEOPS_POLICY_VERSION
    normalized["updated_at"] = _normalize_text(raw.get("updated_at")) or utc_now_iso()
    normalized["plan_policies"] = _normalize_plan_policies(raw.get("plan_policies"))

    normalized_user_overrides: list[dict[str, Any]] = []
    for item in raw.get("user_overrides") or []:
        if not isinstance(item, Mapping):
            continue
        try:
            normalized_user_overrides.append(_normalize_user_override(item))
        except ValueError:
            continue
    normalized["user_overrides"] = normalized_user_overrides

    normalized_domain_policies: list[dict[str, Any]] = []
    for item in raw.get("domain_policies") or []:
        if not isinstance(item, Mapping):
            continue
        try:
            normalized_domain_policies.append(_normalize_domain_policy(item))
        except ValueError:
            continue
    normalized_domain_policies.sort(key=lambda item: (int(item.get("priority") or 0), str(item.get("policy_id") or "")))
    normalized["domain_policies"] = normalized_domain_policies

    alert_policy = raw.get("alert_policy") if isinstance(raw.get("alert_policy"), Mapping) else {}
    normalized["alert_policy"] = {
        "enabled": _normalize_bool(alert_policy.get("enabled"), default=True),
        "cadence_hours": max(1, _normalize_limit(alert_policy.get("cadence_hours"), default=6)),
        "low_remaining_credits_threshold": max(
            0,
            _normalize_limit(alert_policy.get("low_remaining_credits_threshold"), default=250),
        ),
        "discrepancy_threshold": max(0, _normalize_limit(alert_policy.get("discrepancy_threshold"), default=100)),
        "history_days": max(7, _normalize_limit(alert_policy.get("history_days"), default=30)),
    }
    return normalized


def plan_policy_limits(
    policy: Mapping[str, Any] | None,
    *,
    plan_id: str,
    user_id: str = "",
) -> dict[str, int]:
    normalized_policy = normalize_scrapeops_admin_policy(policy)
    normalized_plan_id = normalize_plan_id(plan_id)
    limits = dict(normalized_policy.get("plan_policies", {}).get(normalized_plan_id) or {})
    normalized_user_id = _normalize_text(user_id)
    if normalized_user_id:
        for override in normalized_policy.get("user_overrides") or []:
            if not isinstance(override, Mapping):
                continue
            if not bool(override.get("is_active")):
                continue
            if _normalize_text(override.get("user_id")) != normalized_user_id:
                continue
            if _normalize_text(override.get("plan_id")):
                limits["plan_id"] = normalize_plan_id(override.get("plan_id"))
            for field_name in ("runner_credits_per_month", "company_sites_per_run", "runner_credits_per_run"):
                override_value = override.get(field_name)
                if override_value not in {None, "", 0}:
                    limits[field_name] = _normalize_limit(override_value, default=int(limits.get(field_name) or 0))
            break
    return {
        "plan_id": normalize_plan_id(limits.get("plan_id") or normalized_plan_id),
        "runner_credits_per_month": int(limits.get("runner_credits_per_month") or 0),
        "company_sites_per_run": int(limits.get("company_sites_per_run") or 0),
        "runner_credits_per_run": int(limits.get("runner_credits_per_run") or 0),
    }


__all__ = [
    "DEFAULT_JOB_DETAIL_REQUEST_MODES",
    "DEFAULT_SITE_REQUEST_MODES",
    "SCRAPEOPS_ADMIN_POLICY_CONFIG_KEY",
    "SCRAPEOPS_LOCALITY_MODE_LOCAL_PREFERRED",
    "SCRAPEOPS_LOCALITY_MODE_STRICT_LOCAL_ONLY",
    "SCRAPEOPS_LOCALITY_MODES",
    "default_scrapeops_admin_policy",
    "normalize_scrapeops_admin_policy",
    "plan_policy_limits",
]
