from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

DEFAULT_PLAN_ID = "free"
PLAN_ORDER = ("free", "pro", "business")

PLANS: dict[str, dict[str, Any]] = {
    "free": {
        "display_name": "Free",
        "price_eur": 0,
        "quotas": {
            "runs_per_month": 5,
            "applications_per_month": 10,
            "cv_exports_per_month": 3,
            "referral_drafts_per_month": 5,
            "runner_credits_per_month": 1000,
            "workspaces": 1,
        },
        "limits": {
            "company_sites_per_run": 10,
            "runner_credits_per_run": 150,
        },
    },
    "pro": {
        "display_name": "Pro",
        "price_eur": 29,
        "creem_product_id": "",
        "quotas": {
            "runs_per_month": 100,
            "applications_per_month": 200,
            "cv_exports_per_month": 50,
            "referral_drafts_per_month": 100,
            "runner_credits_per_month": 25000,
            "workspaces": 5,
        },
        "limits": {
            "company_sites_per_run": 250,
            "runner_credits_per_run": 5000,
        },
    },
    "business": {
        "display_name": "Business",
        "price_eur": 79,
        "creem_product_id": "",
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
    "pro": "CREEM_PRO_PRODUCT_ID",
    "business": "CREEM_BUSINESS_PRODUCT_ID",
}


def _with_runtime_plan_values(plan_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(plan)
    product_env_var = PLAN_CREEM_PRODUCT_ENV_VARS.get(plan_id)
    if product_env_var:
        item["creem_product_id"] = str(os.getenv(product_env_var) or item.get("creem_product_id") or "").strip()
    return item


def normalize_plan_id(plan_id: str | None) -> str:
    normalized = str(plan_id or "").strip().lower()
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


def get_plan_for_product_id(product_id: str | int | None) -> str:
    normalized_product_id = str(product_id or "").strip()
    if not normalized_product_id:
        return DEFAULT_PLAN_ID
    for plan_id in PLANS:
        plan = get_plan(plan_id)
        if str(plan.get("creem_product_id") or "").strip() == normalized_product_id:
            return plan_id
    return DEFAULT_PLAN_ID


def compare_plan_tiers(left_plan_id: str | None, right_plan_id: str | None) -> int:
    left_price = int(get_plan(left_plan_id).get("price_eur") or 0)
    right_price = int(get_plan(right_plan_id).get("price_eur") or 0)
    if left_price < right_price:
        return -1
    if left_price > right_price:
        return 1
    return 0


def list_plans() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for plan_id in PLAN_ORDER:
        plan = get_plan(plan_id)
        plan["plan_id"] = plan_id
        items.append(plan)
    return items
