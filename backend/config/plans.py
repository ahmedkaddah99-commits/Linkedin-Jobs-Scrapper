from __future__ import annotations

import os
from copy import deepcopy
from typing import Any


DEFAULT_PLAN_ID = "free"
RUNR_PRO_PLAN_ID = "runr_pro"
PLAN_ORDER = (DEFAULT_PLAN_ID, RUNR_PRO_PLAN_ID)

RUNR_PRO_OFFER_DEFINITIONS = (
    {
        "offer_id": "one_week",
        "display_name": "1 week",
        "price": 19.99,
        "amount": 1999,
        "currency": "USD",
        "billing_type": "onetime",
        "billing_period": "once",
        "env_var": "CREEM_RUNR_PRO_WEEKLY_PRODUCT_ID",
    },
    {
        "offer_id": "one_month",
        "display_name": "1 month",
        "price": 39.99,
        "amount": 3999,
        "currency": "USD",
        "billing_type": "recurring",
        "billing_period": "every-month",
        "env_var": "CREEM_RUNR_PRO_MONTHLY_PRODUCT_ID",
    },
    {
        "offer_id": "three_months",
        "display_name": "3 months",
        "price": 89.99,
        "amount": 8999,
        "currency": "USD",
        "billing_type": "recurring",
        "billing_period": "every-three-months",
        "env_var": "CREEM_RUNR_PRO_QUARTERLY_PRODUCT_ID",
    },
)

PLANS: dict[str, dict[str, Any]] = {
    DEFAULT_PLAN_ID: {
        "display_name": "Free",
        "price": 0,
        "currency": "USD",
        "price_eur": 0,
        "quotas": {
            "runs_per_month": 0,
            "applications_per_month": 0,
            "cv_exports_per_month": 0,
            "referral_drafts_per_month": 0,
            "runner_credits_per_month": 0,
            "workspaces": 0,
        },
        "limits": {
            "company_sites_per_run": 0,
            "runner_credits_per_run": 0,
        },
    },
    RUNR_PRO_PLAN_ID: {
        "display_name": "Runr Pro",
        "currency": "USD",
        # Retained as a compatibility field for older consumers. New pricing
        # uses the offer amounts below because Pro has multiple durations.
        "price_eur": 0,
        "quotas": {
            "runs_per_month": -1,
            "applications_per_month": -1,
            "cv_exports_per_month": -1,
            "referral_drafts_per_month": -1,
            "runner_credits_per_month": -1,
            "workspaces": -1,
        },
        "limits": {
            "company_sites_per_run": -1,
            "runner_credits_per_run": -1,
        },
    },
}

PLAN_CREEM_PRODUCT_ENV_VARS = {
    RUNR_PRO_PLAN_ID: "CREEM_RUNR_PRO_PRODUCT_ID",
}

LEGACY_CREEM_PRODUCT_ENV_VARS = {
    "launch": "CREEM_LAUNCH_PRODUCT_ID",
    "momentum": "CREEM_MOMENTUM_PRODUCT_ID",
    "scale": "CREEM_SCALE_PRODUCT_ID",
}

LEGACY_PLAN_ALIASES = {
    "none": DEFAULT_PLAN_ID,
    "free": DEFAULT_PLAN_ID,
    "launch": RUNR_PRO_PLAN_ID,
    "momentum": RUNR_PRO_PLAN_ID,
    "scale": RUNR_PRO_PLAN_ID,
    "pro": RUNR_PRO_PLAN_ID,
    "business": RUNR_PRO_PLAN_ID,
}


def _runtime_product_id(env_var: str, *, fallback_env_var: str = "") -> str:
    value = str(os.getenv(env_var) or "").strip()
    if value:
        return value
    return str(os.getenv(fallback_env_var) or "").strip() if fallback_env_var else ""


def _with_runtime_plan_values(plan_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(plan)
    if plan_id != RUNR_PRO_PLAN_ID:
        return item

    primary_product_id = _runtime_product_id("CREEM_RUNR_PRO_PRODUCT_ID", fallback_env_var="CREEM_RUNR_PRO_MONTHLY_PRODUCT_ID")
    offers: list[dict[str, Any]] = []
    for definition in RUNR_PRO_OFFER_DEFINITIONS:
        offer = dict(definition)
        fallback = "CREEM_RUNR_PRO_PRODUCT_ID" if offer["offer_id"] == "one_month" else ""
        offer["creem_product_id"] = _runtime_product_id(str(definition["env_var"]), fallback_env_var=fallback)
        offers.append(offer)
    item["creem_product_id"] = primary_product_id
    item["offers"] = offers
    return item


def normalize_plan_id(plan_id: str | None) -> str:
    normalized = str(plan_id or "").strip().lower()
    normalized = LEGACY_PLAN_ALIASES.get(normalized, normalized)
    return normalized if normalized in PLANS else DEFAULT_PLAN_ID


def get_plan(plan_id: str | None) -> dict[str, Any]:
    normalized_plan_id = normalize_plan_id(plan_id)
    return _with_runtime_plan_values(normalized_plan_id, PLANS[normalized_plan_id])


def get_quota(plan_id: str, quota_type: str) -> int:
    plan = PLANS.get(normalize_plan_id(plan_id), PLANS[DEFAULT_PLAN_ID])
    return int(plan["quotas"].get(str(quota_type or "").strip(), 0))


def get_limit(plan_id: str, limit_type: str) -> int:
    plan = PLANS.get(normalize_plan_id(plan_id), PLANS[DEFAULT_PLAN_ID])
    return int(plan.get("limits", {}).get(str(limit_type or "").strip(), 0))


def get_runr_pro_offer(offer_id: str | None) -> dict[str, Any] | None:
    normalized_offer_id = str(offer_id or "").strip().lower()
    if not normalized_offer_id:
        normalized_offer_id = "one_month"
    for offer in get_plan(RUNR_PRO_PLAN_ID).get("offers", []):
        if str(offer.get("offer_id") or "").strip().lower() == normalized_offer_id:
            return offer
    return None


def get_plan_for_product_id(product_id: str | int | None) -> str:
    normalized_product_id = str(product_id or "").strip()
    if not normalized_product_id:
        return DEFAULT_PLAN_ID
    runr_pro = get_plan(RUNR_PRO_PLAN_ID)
    product_ids = {str(runr_pro.get("creem_product_id") or "").strip()}
    product_ids.update(str(offer.get("creem_product_id") or "").strip() for offer in runr_pro.get("offers", []))
    product_ids.update(get_legacy_product_ids())
    return RUNR_PRO_PLAN_ID if normalized_product_id in product_ids - {""} else DEFAULT_PLAN_ID


def get_legacy_product_ids() -> list[str]:
    product_ids: list[str] = []
    for env_var in LEGACY_CREEM_PRODUCT_ENV_VARS.values():
        product_id = str(os.getenv(env_var) or "").strip()
        if product_id and product_id not in product_ids:
            product_ids.append(product_id)
    return product_ids


def get_runr_pro_product_ids() -> list[str]:
    product_ids: list[str] = []
    plan = get_plan(RUNR_PRO_PLAN_ID)
    for value in [plan.get("creem_product_id"), *(offer.get("creem_product_id") for offer in plan.get("offers", []))]:
        product_id = str(value or "").strip()
        if product_id and product_id not in product_ids:
            product_ids.append(product_id)
    return product_ids


def has_runr_pro_access(plan_id: str | None) -> bool:
    return normalize_plan_id(plan_id) == RUNR_PRO_PLAN_ID


def compare_plan_tiers(left_plan_id: str | None, right_plan_id: str | None) -> int:
    left = has_runr_pro_access(left_plan_id)
    right = has_runr_pro_access(right_plan_id)
    return (1 if left else 0) - (1 if right else 0)


def list_plans() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for plan_id in PLAN_ORDER:
        plan = get_plan(plan_id)
        plan["plan_id"] = plan_id
        items.append(plan)
    return items
