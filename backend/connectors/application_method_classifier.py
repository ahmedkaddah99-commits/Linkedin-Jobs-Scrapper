"""Classify public job application destinations for the shared catalog."""

from __future__ import annotations

from collections.abc import Mapping

from backend.acquisition.phase_b import _looks_excluded, _official_apply_url


def classify_application_method(job: Mapping[str, object], target: Mapping[str, object]) -> dict[str, object]:
    """Return a conservative, explainable application-method decision."""

    excluded = _looks_excluded(job)
    if excluded:
        return {"accepted": False, "method": "excluded", "reason": excluded, "apply_url": ""}
    apply_url = _official_apply_url(job, target)
    if not apply_url:
        return {
            "accepted": False,
            "method": "unknown",
            "reason": "unverified_direct_apply_destination",
            "apply_url": "",
        }
    return {"accepted": True, "method": "direct_apply", "reason": "official_destination", "apply_url": apply_url}


__all__ = ["classify_application_method"]
