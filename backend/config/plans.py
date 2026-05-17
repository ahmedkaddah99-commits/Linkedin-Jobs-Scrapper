from __future__ import annotations

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
            "workspaces": 1,
        },
    },
    "pro": {
        "display_name": "Pro",
        "price_eur": 29,
        "lemonsqueezy_variant_id": "",
        "quotas": {
            "runs_per_month": 100,
            "applications_per_month": 200,
            "cv_exports_per_month": 50,
            "referral_drafts_per_month": 100,
            "workspaces": 5,
        },
    },
    "business": {
        "display_name": "Business",
        "price_eur": 79,
        "lemonsqueezy_variant_id": "",
        "quotas": {
            "runs_per_month": -1,
            "applications_per_month": -1,
            "cv_exports_per_month": -1,
            "referral_drafts_per_month": -1,
            "workspaces": -1,
        },
    },
}


def normalize_plan_id(plan_id: str | None) -> str:
    normalized = str(plan_id or "").strip().lower()
    return normalized if normalized in PLANS else DEFAULT_PLAN_ID


def get_plan(plan_id: str | None) -> dict[str, Any]:
    return deepcopy(PLANS[normalize_plan_id(plan_id)])


def get_quota(plan_id: str, quota_type: str) -> int:
    plan = PLANS.get(normalize_plan_id(plan_id), PLANS[DEFAULT_PLAN_ID])
    return int(plan["quotas"].get(str(quota_type or "").strip(), 0))


def get_plan_for_variant_id(variant_id: str | int | None) -> str:
    normalized_variant_id = str(variant_id or "").strip()
    if not normalized_variant_id:
        return DEFAULT_PLAN_ID
    for plan_id, plan in PLANS.items():
        if str(plan.get("lemonsqueezy_variant_id") or "").strip() == normalized_variant_id:
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
