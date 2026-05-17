from __future__ import annotations

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
