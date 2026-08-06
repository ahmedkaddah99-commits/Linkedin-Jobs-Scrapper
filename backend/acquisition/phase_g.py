"""Phase G applicant competition and prioritization primitives.

This module is deliberately source-agnostic.  It accepts only explicit applicant
fields from a connector payload, keeps ranges as ranges, and treats portal
connectors as blocked until their audit record is complete.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Mapping


_APPLICANT_KEYS = (
    "applicant_count",
    "applicants",
    "num_applicants",
    "applicantCount",
    "applicant_count_text",
    "applicant_count_label",
    "applicants_range",
    "applicant_count_range",
)
_PORTAL_TARGET_KINDS = {"portal", "job_board", "job_board_collection", "portal_connector"}
_PORTAL_CONNECTORS = {"linkedin", "indeed", "glassdoor", "stepstone", "ziprecruiter", "careerjet"}
_AUDIT_FIELDS = {
    "authorization": ("authorization_passed", "authorized", "authorization_audit_passed"),
    "blocking": ("blocking_passed", "blocking_audit_passed", "blocking_checked"),
    "request_cost": ("request_cost_passed", "cost_passed", "request_cost_audit_passed"),
    "data_quality": ("data_quality_passed", "quality_passed", "data_quality_audit_passed"),
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _iso_epoch(value: Any) -> float | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).timestamp()


def parse_applicant_count(value: Any) -> dict[str, Any] | None:
    """Parse an explicit source count without inventing precision.

    ``exact`` is set only when the source gives an exact number.  Text such as
    ``over 100 applicants`` becomes a lower-bounded range instead.
    """

    label = ""
    exact: int | None = None
    minimum: int | None = None
    maximum: int | None = None
    if isinstance(value, Mapping):
        label = _text(value.get("label") or value.get("text") or value.get("display"))
        exact = _integer(value.get("exact") if "exact" in value else value.get("count"))
        minimum = _integer(value.get("min") if "min" in value else value.get("minimum"))
        maximum = _integer(value.get("max") if "max" in value else value.get("maximum"))
        if exact is not None:
            minimum = maximum = exact
        if exact is None and minimum is None and maximum is None:
            nested = value.get("value")
            return parse_applicant_count(nested) if nested is not None else None
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        exact = _integer(value)
        minimum = maximum = exact
    else:
        label = _text(value)
        if not label:
            return None
        normalized = label.casefold().replace(",", "")
        range_match = re.search(r"(\d+)\s*(?:-|–|—|to)\s*(\d+)", normalized)
        lower_match = re.search(r"(?:over|more than|at least)\s*(\d+)|\b(\d+)\s*\+", normalized)
        exact_match = re.search(r"\b(\d+)\b", normalized)
        if range_match:
            minimum = _integer(range_match.group(1))
            maximum = _integer(range_match.group(2))
        elif lower_match:
            minimum = _integer(lower_match.group(1) or lower_match.group(2))
        elif exact_match:
            exact = _integer(exact_match.group(1))
            minimum = maximum = exact
    if exact is None and minimum is None and maximum is None:
        return None
    if exact is None and minimum is not None and maximum is not None and minimum == maximum:
        exact = minimum
    if exact is not None:
        minimum = maximum = exact
        kind = "exact"
    else:
        kind = "range"
    return {"exact": exact, "min": minimum, "max": maximum, "label": label, "kind": kind}


def explicit_applicant_count(job: Mapping[str, Any]) -> dict[str, Any] | None:
    for key in _APPLICANT_KEYS:
        if key in job and job.get(key) not in (None, "", []):
            parsed = parse_applicant_count(job.get(key))
            if parsed is not None:
                return parsed
    competition = job.get("competition")
    if isinstance(competition, Mapping):
        for key in _APPLICANT_KEYS:
            if key in competition:
                parsed = parse_applicant_count(competition.get(key))
                if parsed is not None:
                    return parsed
    return None


def is_portal_target(target: Mapping[str, Any]) -> bool:
    kind = _text(target.get("target_kind")).casefold()
    connector = _text(target.get("connector")).casefold()
    return kind in _PORTAL_TARGET_KINDS or connector in _PORTAL_CONNECTORS


def portal_audit_gate(target: Mapping[str, Any]) -> dict[str, Any]:
    """Return the explicit Phase G gate for portal sources.

    Employer career sites and official ATS connectors are not portal sources and
    remain governed by their existing Phase A/B controls.
    """

    if not is_portal_target(target):
        return {"required": False, "approved": True, "missing": []}
    config = target.get("config") if isinstance(target.get("config"), Mapping) else {}
    audit = config.get("phase_g_audit") or config.get("portal_audit") or {}
    if not isinstance(audit, Mapping):
        audit = {}
    missing: list[str] = []
    for name, aliases in _AUDIT_FIELDS.items():
        value = next((audit.get(alias) for alias in aliases if alias in audit), False)
        if value not in (True, 1, "1", "true", "passed", "pass", "approved"):
            missing.append(name)
    status = _text(audit.get("status") or audit.get("state")).casefold()
    if status and status not in {"passed", "approved", "complete", "completed"}:
        missing.append("audit_status")
    return {
        "required": True,
        "approved": not missing,
        "missing": sorted(set(missing)),
        "audited_at": _text(audit.get("audited_at") or audit.get("verified_at")),
        "auditor": _text(audit.get("auditor") or audit.get("owner")),
    }


def normalize_applicant_snapshot(
    job: Mapping[str, Any],
    *,
    observed_at: str,
    source_ats: str = "",
    provenance_url: str = "",
    first_seen_at: str = "",
    last_verified_at: str = "",
) -> dict[str, Any] | None:
    count = explicit_applicant_count(job)
    apply_method = _text(job.get("application_method") or job.get("apply_method") or "direct_apply")
    marker = bool(job.get("easy_apply") or job.get("quick_apply") or job.get("easy_apply_marker"))
    if apply_method.casefold() in {"easy_apply", "quick_apply", "quick apply", "easy apply"}:
        marker = True
    if count is None and not marker:
        return None
    posting_time = _text(job.get("posted_at") or job.get("published_at") or job.get("date_posted"))
    freshness = freshness_status(observed_at)
    return {
        "exact": count.get("exact") if count else None,
        "min": count.get("min") if count else None,
        "max": count.get("max") if count else None,
        "label": _text((count or {}).get("label")),
        "posting_time": posting_time,
        "first_seen_at": _text(first_seen_at),
        "last_verified_at": _text(last_verified_at or observed_at),
        "observed_at": _text(observed_at),
        "apply_method": apply_method,
        "easy_apply_marker": marker,
        "freshness_status": freshness,
        "source_ats": _text(source_ats),
        "provenance_url": _text(provenance_url),
        "payload": dict(job),
    }


def freshness_status(observed_at: Any) -> str:
    epoch = _iso_epoch(observed_at)
    if epoch is None:
        return "unknown"
    age_hours = max(0.0, (datetime.now(timezone.utc).timestamp() - epoch) / 3600)
    if age_hours <= 30:
        return "fresh"
    if age_hours <= 72:
        return "aging"
    return "stale"


def _range_value(snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
    if snapshot.get("exact") is not None:
        return None
    minimum = snapshot.get("min")
    maximum = snapshot.get("max")
    if minimum is None and maximum is None:
        return None
    return {"min": minimum, "max": maximum, "label": _text(snapshot.get("label")) or None}


def _competition_score(snapshot: Mapping[str, Any]) -> tuple[int | None, str]:
    count = snapshot.get("exact") if snapshot.get("exact") is not None else snapshot.get("min")
    if count is None:
        return None, "unknown"
    count = int(count)
    if count <= 25:
        score = 90
    elif count <= 75:
        score = 75
    elif count <= 150:
        score = 55
    elif count <= 300:
        score = 35
    else:
        score = 15
    return score, "exact" if snapshot.get("exact") is not None else "lower_bound"


def build_applicant_competition(row: Mapping[str, Any], *, include_pro: bool = False) -> dict[str, Any]:
    latest = {
        "exact": row.get("applicant_latest_exact"),
        "min": row.get("applicant_latest_min"),
        "max": row.get("applicant_latest_max"),
        "label": row.get("applicant_latest_label"),
        "observed_at": row.get("applicant_latest_observed_at"),
        "posting_time": row.get("applicant_latest_posting_time"),
        "first_seen_at": row.get("applicant_latest_first_seen_at"),
        "last_verified_at": row.get("applicant_latest_last_verified_at"),
        "apply_method": row.get("applicant_latest_apply_method"),
        "easy_apply_marker": bool(row.get("applicant_latest_easy_apply_marker")),
        "freshness_status": row.get("applicant_latest_freshness_status"),
        "source_ats": row.get("applicant_latest_source_ats"),
        "provenance_url": row.get("applicant_latest_provenance_url"),
    }
    if latest["observed_at"] in (None, ""):
        return {
            "state": "unknown",
            "visibility": "pro",
            "latest": None,
            "first_observed": None,
            "change": {"state": "unknown", "reason": "no_reliable_snapshot"},
            "freshness": {"state": "unknown", "observed_at": None},
            "apply_method": None,
            "easy_apply_marker": False,
            "pro": None,
        }
    first = {
        "exact": row.get("applicant_first_exact"),
        "min": row.get("applicant_first_min"),
        "max": row.get("applicant_first_max"),
        "label": row.get("applicant_first_label"),
        "observed_at": row.get("applicant_first_observed_at"),
    }
    exact_delta = None
    growth_rate = None
    days_elapsed = None
    if latest["exact"] is not None and first["exact"] is not None:
        exact_delta = int(latest["exact"]) - int(first["exact"])
        if int(first["exact"]) != 0:
            growth_rate = exact_delta / int(first["exact"])
        first_epoch = _iso_epoch(first["observed_at"])
        latest_epoch = _iso_epoch(latest["observed_at"])
        if first_epoch is not None and latest_epoch is not None:
            days_elapsed = max(0.0, (latest_epoch - first_epoch) / 86400)
    change = (
        {"state": "available", "delta": exact_delta, "growth_rate": growth_rate, "days_elapsed": days_elapsed}
        if exact_delta is not None
        else {"state": "unknown", "reason": "range_only_or_missing_first_exact_count"}
    )
    score, confidence = _competition_score(latest)
    public_latest = {
        "count": latest["exact"] if include_pro else None,
        "range": _range_value(latest),
        "label": _text(latest["label"]) or None,
        "observed_at": _text(latest["observed_at"]) or None,
    }
    public_first = {
        "count": first["exact"] if include_pro else None,
        "range": _range_value(first),
        "label": _text(first["label"]) or None,
        "observed_at": _text(first["observed_at"]) or None,
    }
    result = {
        "state": "available",
        "visibility": "pro",
        "latest": public_latest,
        "first_observed": public_first,
        "change": change if include_pro else {"state": "pro_only"},
        "freshness": {
            "state": _text(latest["freshness_status"]) or freshness_status(latest["observed_at"]),
            "observed_at": _text(latest["observed_at"]) or None,
            "last_verified_at": _text(latest["last_verified_at"]) or None,
        },
        "posting_time": _text(latest["posting_time"]) or None,
        "apply_method": _text(latest["apply_method"]) or "unknown",
        "easy_apply_marker": bool(latest["easy_apply_marker"]),
        "provenance": {
            "source": _text(latest["source_ats"]) or "unknown",
            "url": _text(latest["provenance_url"]) or None,
        },
        "pro": None,
    }
    if include_pro:
        alerts: list[dict[str, Any]] = []
        if score is not None and score >= 75:
            alerts.append({"type": "low_competition", "priority": "normal"})
        if result["freshness"]["state"] == "fresh":
            alerts.append({"type": "recently_verified", "priority": "normal"})
        if change.get("state") == "available" and (change.get("delta") or 0) < 0:
            alerts.append({"type": "applicant_count_decreased", "priority": "low"})
        result["pro"] = {
            "latest_count": latest["exact"],
            "latest_range": _range_value(latest),
            "first_observed_count": first["exact"],
            "first_observed_range": _range_value(first),
            "change": change,
            "competition_score": score,
            "competition_score_confidence": confidence,
            "low_competition": score is not None and score >= 75,
            "snapshot_count": int(row.get("applicant_snapshot_count") or 0),
            "opportunity_alerts": alerts,
        }
    return result


def build_priority(row: Mapping[str, Any], match: Mapping[str, Any], competition: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic, explainable ordering score from known evidence."""

    v2 = match.get("v2") if isinstance(match.get("v2"), Mapping) else match
    fit = v2.get("score") if isinstance(v2, Mapping) else None
    try:
        fit_score = max(0.0, min(100.0, float(fit)))
    except (TypeError, ValueError):
        fit_score = 50.0
    verified = _iso_epoch(row.get("last_verified_at") or row.get("first_seen_at"))
    freshness_score = 50.0
    if verified is not None:
        age_hours = max(0.0, (datetime.now(timezone.utc).timestamp() - verified) / 3600)
        freshness_score = max(0.0, 100.0 - min(100.0, age_hours / 2.4))
    non_matches = len(v2.get("apparent_non_matches") or []) if isinstance(v2, Mapping) else 0
    unproven = len(v2.get("unproven_requirements") or []) if isinstance(v2, Mapping) else 0
    eligibility_score = max(0.0, 100.0 - non_matches * 35.0 - unproven * 10.0)
    payload = row.get("version_payload_json")
    if isinstance(payload, str):
        try:
            import json
            payload = json.loads(payload)
        except (TypeError, ValueError):
            payload = {}
    payload = payload if isinstance(payload, Mapping) else {}
    auth = payload.get("work_authorization") or payload.get("authorization") or payload.get("work_permit")
    language = payload.get("languages") or payload.get("language_requirements") or payload.get("required_languages")
    authorization_score = 100.0 if auth not in (None, "", [], {}) else 50.0
    language_score = 100.0 if language not in (None, "", [], {}) else 70.0
    sponsorship = payload.get("sponsorship") or payload.get("visa_sponsorship") or payload.get("sponsors_h1b")
    sponsorship_score = 100.0 if sponsorship not in (None, "", [], {}) else 50.0
    non_match_text = " ".join(str(item) for item in (v2.get("apparent_non_matches") or [])) if isinstance(v2, Mapping) else ""
    if "sponsor" in non_match_text.casefold() or "visa" in non_match_text.casefold():
        sponsorship_score = 0.0
    method = _text(competition.get("apply_method")).casefold()
    apply_method_score = 100.0 if method in {"direct_apply", "official_ats", "employer_site"} else 40.0
    pro = competition.get("pro") if isinstance(competition.get("pro"), Mapping) else {}
    competition_score = pro.get("competition_score")
    if competition_score is None:
        competition_score = 50.0
    change = pro.get("change") if isinstance(pro.get("change"), Mapping) else {}
    growth_rate = change.get("growth_rate") if change.get("state") == "available" else None
    try:
        growth_score = max(0.0, min(100.0, 100.0 - max(0.0, float(growth_rate)) * 100.0))
    except (TypeError, ValueError):
        growth_score = 50.0
    score = round(
        fit_score * 0.32
        + freshness_score * 0.14
        + float(competition_score) * 0.13
        + growth_score * 0.06
        + eligibility_score * 0.14
        + authorization_score * 0.07
        + language_score * 0.04
        + sponsorship_score * 0.04
        + apply_method_score * 0.06,
        2,
    )
    return {
        "score": score,
        "state": "partial" if fit is None or verified is None else "available",
        "components": {
            "user_fit": round(fit_score, 2),
            "freshness": round(freshness_score, 2),
            "competition": competition_score,
            "applicant_growth": round(growth_score, 2),
            "eligibility": round(eligibility_score, 2),
            "work_authorization": authorization_score,
            "language_requirements": language_score,
            "sponsorship": sponsorship_score,
            "apply_method": apply_method_score,
        },
    }


__all__ = [
    "build_applicant_competition",
    "build_priority",
    "explicit_applicant_count",
    "freshness_status",
    "is_portal_target",
    "normalize_applicant_snapshot",
    "parse_applicant_count",
    "portal_audit_gate",
]
