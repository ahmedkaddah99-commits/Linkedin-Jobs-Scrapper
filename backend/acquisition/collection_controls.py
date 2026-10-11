"""Server-owned collection control and result metadata contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

RETRIEVAL_MODES = ("bounded", "custom", "all_available")

# These values are part of the admin/import result contract.  A connector may
# provide a more specific value, but it must remain one of these stable values.
STOP_REASONS = (
    "accepted_job_limit",
    "pagination_complete",
    "max_pages",
    "max_requests",
    "max_credits",
    "connector_safety_ceiling",
    "global_request_ceiling",
    "global_credit_ceiling",
    "connector_pagination_unsupported",
    "provider_error",
    "no_snapshot_page",
    "not_attempted",
)

DEFAULT_JOB_LIMIT = 25
MAX_JOB_LIMIT = 500
DEFAULT_MAX_PAGES = 20
DEFAULT_MAX_REQUESTS = 100
DEFAULT_MAX_CREDITS = 0
GLOBAL_JOB_SAFETY_CEILING = MAX_JOB_LIMIT


def normalize_retrieval_mode(value: Any) -> str:
    normalized = str(value or "bounded").strip().casefold()
    if normalized not in RETRIEVAL_MODES:
        raise ValueError(
            "retrieval_mode must be one of: " + ", ".join(RETRIEVAL_MODES)
        )
    return normalized


def normalize_optional_limit(value: Any, *, default: int = 0, maximum: int) -> int:
    if value in (None, ""):
        return max(0, min(maximum, int(default)))
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("collection limits must be integers") from exc
    if parsed < 0:
        raise ValueError("collection limits cannot be negative")
    return min(maximum, parsed)


def resolve_job_limits(
    scope: Mapping[str, Any] | None,
    capability: Mapping[str, Any] | None = None,
) -> dict[str, int | str]:
    """Resolve requested/effective limits without treating a limit as a yield guarantee."""

    requested = normalize_optional_limit(
        (scope or {}).get("max_jobs"),
        default=0,
        maximum=MAX_JOB_LIMIT,
    )
    capability = capability or {}
    connector_ceiling = normalize_optional_limit(
        capability.get("safety_ceiling"),
        default=GLOBAL_JOB_SAFETY_CEILING,
        maximum=GLOBAL_JOB_SAFETY_CEILING,
    ) or GLOBAL_JOB_SAFETY_CEILING
    safety_ceiling = min(GLOBAL_JOB_SAFETY_CEILING, connector_ceiling)
    effective = min(requested, safety_ceiling) if requested else safety_ceiling
    return {
        "requested_job_limit": requested,
        "effective_job_limit": max(1, effective),
        "safety_ceiling": max(1, safety_ceiling),
    }


def collection_metadata(
    *,
    scope: Mapping[str, Any] | None,
    capability: Mapping[str, Any] | None = None,
    fetched: Mapping[str, Any] | None = None,
    observed_count: int = 0,
    accepted_count: int = 0,
    rejected_count: int = 0,
    complete_snapshot: bool = False,
    closure_safe: bool = False,
    pagination_complete: bool = False,
    stop_reason: str = "not_attempted",
) -> dict[str, Any]:
    scope = scope or {}
    fetched = fetched or {}
    limits = resolve_job_limits(scope, capability)
    requested = int(limits["requested_job_limit"])
    effective = int(limits["effective_job_limit"])
    normalized_reason = str(stop_reason or "not_attempted").strip().casefold()
    if normalized_reason not in STOP_REASONS:
        normalized_reason = "provider_error"
    complete = bool(complete_snapshot and pagination_complete and closure_safe)
    if complete:
        completeness_state = "complete"
    elif str(fetched.get("status") or "").casefold() in {"failed", "blocked", "unsupported"}:
        completeness_state = "failed"
    else:
        completeness_state = "incomplete"
    return {
        "retrieval_mode": normalize_retrieval_mode(scope.get("retrieval_mode")),
        "requested_job_limit": requested,
        "effective_job_limit": effective,
        "safety_ceiling": int(limits["safety_ceiling"]),
        "pagination_complete": bool(pagination_complete),
        "complete_snapshot": complete,
        "closure_safe": bool(closure_safe and complete),
        "completeness_state": completeness_state,
        "stop_reason": normalized_reason,
        "observed_count": max(0, int(observed_count)),
        "accepted_count": max(0, int(accepted_count)),
        "rejected_count": max(0, int(rejected_count)),
    }


def cap_accepted_jobs(
    jobs: list[Mapping[str, Any]],
    *,
    effective_job_limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Keep at most the accepted-role cap and make overflow auditable."""

    limit = max(1, int(effective_job_limit))
    accepted = [dict(job) for job in jobs]
    if len(accepted) <= limit:
        return accepted, [], False
    kept = accepted[:limit]
    overflow = [
        {
            "job_id": str(job.get("job_id") or job.get("external_job_id") or job.get("id") or ""),
            "reason": "accepted_job_limit",
            "details": {"effective_job_limit": limit},
        }
        for job in accepted[limit:]
    ]
    return kept, overflow, True


def infer_stop_reason(
    *,
    scope: Mapping[str, Any] | None,
    capability: Mapping[str, Any] | None,
    fetched: Mapping[str, Any] | None,
    accepted_count: int = 0,
    accepted_cap_hit: bool,
    actual_credits: int = 0,
    actual_requests: int = 0,
) -> str:
    scope = scope or {}
    fetched = fetched or {}
    capability = capability or {}
    if accepted_cap_hit:
        return "accepted_job_limit"
    connector_reason = str(fetched.get("stop_reason") or "").strip().casefold()
    if bool(fetched.get("global_request_ceiling_hit")):
        return "global_request_ceiling"
    if bool(fetched.get("global_credit_ceiling_hit")):
        return "global_credit_ceiling"
    max_credits = int(scope.get("max_credits") or 0)
    if max_credits and actual_credits >= max_credits:
        return "max_credits"
    max_requests = int(scope.get("max_requests") or 0)
    if max_requests and actual_requests >= max_requests and not bool(fetched.get("pagination_complete")):
        return "max_requests"
    max_pages = int(scope.get("max_pages") or 0)
    pages = int(fetched.get("pages_fetched") or 0)
    if max_pages and pages >= max_pages and not bool(fetched.get("pagination_complete")):
        return "max_pages"
    if bool(fetched.get("connector_safety_ceiling_hit")):
        return "connector_safety_ceiling"
    if connector_reason in {"max_pages", "max_requests", "max_credits", "connector_safety_ceiling"}:
        return connector_reason
    status = str(fetched.get("status") or "").casefold()
    if status in {"failed", "blocked", "unsupported"} or fetched.get("error"):
        return "provider_error"
    if (
        str(scope.get("retrieval_mode") or "bounded") == "all_available"
        and not bool(capability.get("reliable_pagination"))
    ):
        return "connector_pagination_unsupported"
    if bool(fetched.get("pagination_complete")) or bool(fetched.get("complete_snapshot")):
        return "pagination_complete"
    if pages == 0:
        return "no_snapshot_page"
    return "max_pages" if max_pages else "connector_safety_ceiling"


__all__ = [
    "DEFAULT_JOB_LIMIT",
    "DEFAULT_MAX_CREDITS",
    "DEFAULT_MAX_PAGES",
    "DEFAULT_MAX_REQUESTS",
    "GLOBAL_JOB_SAFETY_CEILING",
    "MAX_JOB_LIMIT",
    "RETRIEVAL_MODES",
    "STOP_REASONS",
    "cap_accepted_jobs",
    "collection_metadata",
    "infer_stop_reason",
    "normalize_optional_limit",
    "normalize_retrieval_mode",
    "resolve_job_limits",
]
