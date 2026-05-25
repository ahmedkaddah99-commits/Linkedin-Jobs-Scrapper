from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Mapping

from backend.config.plans import get_quota, normalize_plan_id


class QuotaExceededError(Exception):
    def __init__(
        self,
        quota_type: str,
        used: int,
        limit: int,
        plan_id: str,
        *,
        route: str = "",
    ) -> None:
        self.quota_type = str(quota_type or "").strip()
        self.used = int(used)
        self.limit = int(limit)
        self.plan_id = normalize_plan_id(plan_id)
        self.route = str(route or "").strip()
        super().__init__(
            f"Quota exceeded for '{self.quota_type}': used {self.used} of {self.limit} on plan '{self.plan_id}'."
        )


def _current_period_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _quotas_disabled() -> bool:
    return str(os.getenv("RUNR_DISABLE_QUOTAS") or "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_auth_repository(db: Any):
    if hasattr(db, "repositories") and getattr(db.repositories, "auth_repository", None) is not None:
        return db.repositories.auth_repository
    if getattr(db, "auth_repository", None) is not None:
        return db.auth_repository
    return db


def _resolve_quota_limit(
    plan_id: str,
    quota_type: str,
    quota_overrides: Mapping[str, Any] | None = None,
) -> int:
    override_value = None
    if isinstance(quota_overrides, Mapping):
        override_value = quota_overrides.get(quota_type)
    if override_value not in {None, ""}:
        try:
            return int(override_value)
        except (TypeError, ValueError):
            pass
    return int(get_quota(plan_id, quota_type))


def get_current_usage(db, user_id: str, quota_type: str, period: str) -> int:
    repository = _resolve_auth_repository(db)
    if not hasattr(repository, "get_quota_usage"):
        raise ValueError("The configured repository does not support quota usage persistence.")
    return int(
        repository.get_quota_usage(
            str(user_id or "").strip(),
            str(quota_type or "").strip(),
            str(period or "").strip() or _current_period_key(),
        )
    )


def get_usage_snapshot(
    db,
    user_id: str,
    quota_type: str,
    plan_id: str,
    *,
    quota_overrides: Mapping[str, Any] | None = None,
) -> dict[str, int | str]:
    normalized_user_id = str(user_id or "").strip()
    normalized_quota_type = str(quota_type or "").strip()
    normalized_plan_id = normalize_plan_id(plan_id)
    current_period = _current_period_key()
    limit = _resolve_quota_limit(normalized_plan_id, normalized_quota_type, quota_overrides)
    used = get_current_usage(db, normalized_user_id, normalized_quota_type, current_period)
    return {
        "quota_type": normalized_quota_type,
        "used": int(used),
        "limit": int(limit),
        "remaining": -1 if int(limit) == -1 else max(0, int(limit) - int(used)),
        "period": current_period,
        "plan_id": normalized_plan_id,
    }


def check_and_increment_quota(
    db,
    user_id: str,
    quota_type: str,
    plan_id: str,
    *,
    route: str = "",
    quota_overrides: Mapping[str, Any] | None = None,
) -> dict[str, int | str]:
    repository = _resolve_auth_repository(db)
    if not hasattr(repository, "increment_quota_usage"):
        raise ValueError("The configured repository does not support quota usage persistence.")

    normalized_user_id = str(user_id or "").strip()
    normalized_quota_type = str(quota_type or "").strip()
    normalized_plan_id = normalize_plan_id(plan_id)
    current_period = _current_period_key()
    limit = _resolve_quota_limit(normalized_plan_id, normalized_quota_type, quota_overrides)

    if _quotas_disabled():
        return {
            "quota_type": normalized_quota_type,
            "used": get_current_usage(repository, normalized_user_id, normalized_quota_type, current_period),
            "limit": -1,
            "period": current_period,
            "plan_id": normalized_plan_id,
        }

    used = get_current_usage(repository, normalized_user_id, normalized_quota_type, current_period)

    if limit != -1 and used >= limit:
        if hasattr(db, "emit_event"):
            db.emit_event(
                "quota_limit_hit",
                user_id=normalized_user_id,
                route=route,
                source="api",
                payload={
                    "quota_type": normalized_quota_type,
                    "plan_id": normalized_plan_id,
                    "used": used,
                    "limit": limit,
                    "route": str(route or "").strip(),
                },
            )
        raise QuotaExceededError(
            normalized_quota_type,
            used,
            limit,
            normalized_plan_id,
            route=route,
        )

    used_after_increment = int(
        repository.increment_quota_usage(
            normalized_user_id,
            normalized_quota_type,
            current_period,
            amount=1,
        )
    )
    return {
        "quota_type": normalized_quota_type,
        "used": used_after_increment,
        "limit": limit,
        "period": current_period,
        "plan_id": normalized_plan_id,
    }


def check_and_increment_quota_amount(
    db,
    user_id: str,
    quota_type: str,
    plan_id: str,
    *,
    amount: int,
    route: str = "",
    quota_overrides: Mapping[str, Any] | None = None,
) -> dict[str, int | str]:
    repository = _resolve_auth_repository(db)
    if not hasattr(repository, "increment_quota_usage"):
        raise ValueError("The configured repository does not support quota usage persistence.")

    normalized_user_id = str(user_id or "").strip()
    normalized_quota_type = str(quota_type or "").strip()
    normalized_plan_id = normalize_plan_id(plan_id)
    increment_by = max(1, int(amount))
    snapshot = get_usage_snapshot(
        repository,
        normalized_user_id,
        normalized_quota_type,
        normalized_plan_id,
        quota_overrides=quota_overrides,
    )
    limit = int(snapshot["limit"])
    used = int(snapshot["used"])
    current_period = str(snapshot["period"])

    if _quotas_disabled():
        return {
            "quota_type": normalized_quota_type,
            "used": used,
            "limit": -1,
            "period": current_period,
            "plan_id": normalized_plan_id,
        }

    if limit != -1 and used + increment_by > limit:
        if hasattr(db, "emit_event"):
            db.emit_event(
                "quota_limit_hit",
                user_id=normalized_user_id,
                route=route,
                source="api",
                payload={
                    "quota_type": normalized_quota_type,
                    "plan_id": normalized_plan_id,
                    "used": used,
                    "limit": limit,
                    "attempted_increment": increment_by,
                    "route": str(route or "").strip(),
                },
            )
        raise QuotaExceededError(
            normalized_quota_type,
            used,
            limit,
            normalized_plan_id,
            route=route,
        )

    used_after_increment = int(
        repository.increment_quota_usage(
            normalized_user_id,
            normalized_quota_type,
            current_period,
            amount=increment_by,
        )
    )
    return {
        "quota_type": normalized_quota_type,
        "used": used_after_increment,
        "limit": limit,
        "period": current_period,
        "plan_id": normalized_plan_id,
    }
