"""Classify public job application destinations for the shared catalog."""

from __future__ import annotations

from collections.abc import Mapping

from backend.acquisition.phase_b import _looks_excluded
from backend.acquisition.quality import resolve_application_destination


def classify_application_method(job: Mapping[str, object], target: Mapping[str, object]) -> dict[str, object]:
    """Return a conservative, explainable application-method decision."""

    excluded = _looks_excluded(job)
    if excluded:
        return {"accepted": False, "method": "excluded", "reason": excluded, "apply_url": ""}
    destination = resolve_application_destination(job, target)
    if destination.get("status") != "verified":
        return {
            "accepted": True,
            "method": destination.get("application_method") or "unknown",
            "reason": "quality_warning_missing_direct_application_url",
            "apply_url": destination.get("user_facing_url") or "",
            "application_url": destination.get("resolved_url") or "",
            "application_classification": destination.get("classification") or "unknown",
            "warnings": list(destination.get("warnings") or []),
        }
    return {
        "accepted": True,
        "method": "direct_apply",
        "reason": "official_destination",
        "apply_url": destination.get("user_facing_url") or "",
        "application_url": destination.get("resolved_url") or "",
        "application_classification": destination.get("classification") or "unknown",
        "warnings": [],
    }


__all__ = ["classify_application_method"]
