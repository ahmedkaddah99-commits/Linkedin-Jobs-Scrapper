"""Phase G applicant-intelligence boundary and deterministic ranking primitives.

Applicant intelligence is deliberately inactive in production until a source
decision is documented and approved.  These normalizers preserve explicit
evidence, represent missing values as unknown, and never persist raw payloads.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Mapping


_APPLICANT_KEYS = (
    "applicant_count", "applicants", "num_applicants", "applicantCount",
    "applicant_count_text", "applicant_count_label", "applicants_range",
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

PHASE_G_POLICY_VERSION = "phase_g_applicant_intelligence_v1"
PRIORITY_FORMULA_VERSION = "phase_g_priority_v1"
PRIORITY_WEIGHTS = {"user_fit": 0.60, "freshness": 0.20, "competition": 0.20}

# Deliberately not configurable at runtime.  The initial audit must not activate
# any applicant source in production.
PHASE_G_PRODUCTION_ACTIVATED = False

# Structured job feeds are not applicant-count sources.  These decisions are
# evidence-backed defaults, not a connector allow-list.
APPLICANT_SOURCE_DECISIONS: dict[str, dict[str, Any]] = {
    "linkedin": {"decision": "blocked", "reason": "authorization_unavailable_and_terms_risk"},
    "indeed": {"decision": "blocked", "reason": "authorization_and_cost_billing_unverified"},
    "glassdoor": {"decision": "blocked", "reason": "authorization_and_field_quality_unverified"},
    "stepstone": {"decision": "blocked", "reason": "authorization_and_field_quality_unverified"},
    "ziprecruiter": {"decision": "blocked", "reason": "authorization_and_field_quality_unverified"},
    "careerjet": {"decision": "blocked", "reason": "authorization_and_field_quality_unverified"},
    "greenhouse": {"decision": "blocked", "reason": "no_applicant_count_field"},
    "lever": {"decision": "blocked", "reason": "no_applicant_count_field"},
    "arbeitsagentur": {"decision": "blocked", "reason": "no_applicant_count_field"},
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        if isinstance(value, float) and not value.is_integer():
            return None
        text = str(value).strip()
        if "." in text and not text.endswith(".0"):
            return None
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
    """Parse explicit exact/range evidence without inventing precision."""

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
        range_match = re.search(r"(\d+)\s*(?:[-\u2013\u2014]|to)\s*(\d+)", normalized)
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


def has_applicant_evidence(job: Mapping[str, Any]) -> bool:
    if explicit_applicant_count(job) is not None:
        return True
    competition = job.get("competition")
    return any(
        key in job and job.get(key) not in (None, "", [])
        for key in _APPLICANT_KEYS
    ) or (
        isinstance(competition, Mapping)
        and any(key in competition and competition.get(key) not in (None, "", []) for key in _APPLICANT_KEYS)
    )


def is_portal_target(target: Mapping[str, Any]) -> bool:
    kind = _text(target.get("target_kind")).casefold()
    connector = _text(target.get("connector")).casefold()
    return kind in _PORTAL_TARGET_KINDS or connector in _PORTAL_CONNECTORS


def portal_audit_gate(target: Mapping[str, Any]) -> dict[str, Any]:
    """Return the explicit legacy portal gate; it does not approve Phase G."""

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


def applicant_source_decision(target: Mapping[str, Any]) -> dict[str, Any]:
    """Return the current documented decision for a connector."""

    connector = _text(target.get("connector")).casefold()
    decision = dict(APPLICANT_SOURCE_DECISIONS.get(
        connector,
        {"decision": "blocked", "reason": "source_not_audited"},
    ))
    decision.update({"connector": connector, "policy_version": PHASE_G_POLICY_VERSION})
    return decision


def applicant_source_gate(target: Mapping[str, Any]) -> dict[str, Any]:
    """Enforce the hard initial-audit boundary for applicant observations."""

    config = target.get("config") if isinstance(target.get("config"), Mapping) else {}
    audit = config.get("phase_g_applicant_audit") or {}
    if not isinstance(audit, Mapping):
        audit = {}
    decision = applicant_source_decision(target)
    missing = [] if decision.get("decision") == "approved" else [str(decision.get("reason") or "source_blocked")]
    if not PHASE_G_PRODUCTION_ACTIVATED:
        missing.append("production_activation_disabled")
    for field in (
        "authorization_documented", "data_quality_documented", "request_cost_documented",
        "unattended_behavior_documented", "observation_timestamp_documented",
        "official_apply_destination_documented", "no_candidate_data_documented",
    ):
        if audit.get(field) not in (True, 1, "1", "true", "passed", "pass", "approved"):
            missing.append(field)
    return {
        "approved": not missing,
        "required": True,
        "missing": sorted(set(missing)),
        "policy_version": PHASE_G_POLICY_VERSION,
        "decision": decision,
        "audited_at": _text(audit.get("audited_at") or audit.get("verified_at")),
    }


def normalize_applicant_snapshot(
    job: Mapping[str, Any],
    *,
    observed_at: str,
    source_ats: str = "",
    provenance_url: str = "",
    source_provenance: str = "",
    first_seen_at: str = "",
    last_verified_at: str = "",
) -> dict[str, Any] | None:
    """Normalize one approved-source observation, including unknown values."""

    if _iso_epoch(observed_at) is None:
        return None
    count = explicit_applicant_count(job)
    apply_method = _text(job.get("application_method") or job.get("apply_method")) or "unknown"
    marker = bool(job.get("easy_apply") or job.get("quick_apply") or job.get("easy_apply_marker"))
    if apply_method.casefold() in {"easy_apply", "quick_apply", "quick apply", "easy apply"}:
        marker = True
    posting_time = _text(job.get("posted_at") or job.get("published_at") or job.get("date_posted"))
    apply_url = _text(job.get("apply_url") or job.get("apply_link"))
    source_value = _text(source_provenance or provenance_url)
    # Explicit allow-list: no candidate identity or application-data payload can
    # cross this boundary even if a connector accidentally returns it.
    safe_payload = {
        "applicant_count": count,
        "application_method": apply_method,
        "apply_url": apply_url,
        "posted_at": posting_time,
        "observed_at": _text(observed_at),
        "source_ats": _text(source_ats),
        "source_provenance": source_value,
    }
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
        "apply_url": apply_url,
        "easy_apply_marker": marker,
        "freshness_status": freshness_status(observed_at),
        "source_ats": _text(source_ats),
        "provenance_url": _text(provenance_url),
        "source_provenance": source_value,
        "payload": safe_payload,
    }


def freshness_status(observed_at: Any, *, as_of: Any = None) -> str:
    epoch = _iso_epoch(observed_at)
    if epoch is None:
        return "unknown"
    as_of_epoch = _iso_epoch(as_of) if as_of is not None else datetime.now(timezone.utc).timestamp()
    if as_of_epoch is None:
        as_of_epoch = datetime.now(timezone.utc).timestamp()
    age_hours = max(0.0, (as_of_epoch - epoch) / 3600)
    if age_hours <= 30:
        return "fresh"
    if age_hours <= 72:
        return "aging"
    return "stale"


def _range_value(snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
    if snapshot.get("exact") is not None:
        return None
    minimum, maximum = snapshot.get("min"), snapshot.get("max")
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
        "exact": row.get("applicant_latest_exact"), "min": row.get("applicant_latest_min"),
        "max": row.get("applicant_latest_max"), "label": row.get("applicant_latest_label"),
        "observed_at": row.get("applicant_latest_observed_at"),
        "posting_time": row.get("applicant_latest_posting_time"),
        "first_seen_at": row.get("applicant_latest_first_seen_at"),
        "last_verified_at": row.get("applicant_latest_last_verified_at"),
        "apply_method": row.get("applicant_latest_apply_method"),
        "easy_apply_marker": bool(row.get("applicant_latest_easy_apply_marker")),
        "freshness_status": row.get("applicant_latest_freshness_status"),
        "source_ats": row.get("applicant_latest_source_ats"),
        "provenance_url": row.get("applicant_latest_provenance_url"),
        "apply_url": row.get("applicant_latest_apply_url"),
    }
    if latest["observed_at"] in (None, ""):
        return {
            "state": "unknown", "visibility": "pro", "latest": None, "first_observed": None,
            "change": {"state": "unknown", "reason": "no_reliable_snapshot"},
            "freshness": {"state": "unknown", "observed_at": None, "observation_age_hours": None},
            "apply_method": None, "easy_apply_marker": False, "provenance": None, "pro": None,
        }
    first = {
        "exact": row.get("applicant_first_exact"), "min": row.get("applicant_first_min"),
        "max": row.get("applicant_first_max"), "label": row.get("applicant_first_label"),
        "observed_at": row.get("applicant_first_observed_at"),
    }
    exact_delta = None
    growth_rate = None
    days_elapsed = None
    if latest["exact"] is not None and first["exact"] is not None:
        exact_delta = int(latest["exact"]) - int(first["exact"])
        if int(first["exact"]) != 0:
            growth_rate = exact_delta / int(first["exact"])
        first_epoch, latest_epoch = _iso_epoch(first["observed_at"]), _iso_epoch(latest["observed_at"])
        if first_epoch is not None and latest_epoch is not None:
            days_elapsed = max(0.0, (latest_epoch - first_epoch) / 86400)
    change = (
        {"state": "available", "delta": exact_delta, "growth_rate": growth_rate, "days_elapsed": days_elapsed}
        if exact_delta is not None else {"state": "unknown", "reason": "range_only_or_missing_first_exact_count"}
    )
    current_freshness = freshness_status(latest["observed_at"])
    observation_epoch = _iso_epoch(latest["observed_at"])
    observation_age_hours = round(max(0.0, (datetime.now(timezone.utc).timestamp() - observation_epoch) / 3600), 2) if observation_epoch is not None else None
    score, confidence = _competition_score(latest)
    if current_freshness == "stale":
        score, confidence = None, "stale"
    has_count = latest["exact"] is not None or latest["min"] is not None or latest["max"] is not None
    public_latest = {
        "count": latest["exact"] if include_pro else None,
        "range": _range_value(latest) if include_pro else None,
        "label": _text(latest["label"]) if include_pro and has_count else None,
        "observed_at": _text(latest["observed_at"]) if include_pro else None,
    }
    public_first = {
        "count": first["exact"] if include_pro else None,
        "range": _range_value(first) if include_pro else None,
        "label": _text(first["label"]) if include_pro else None,
        "observed_at": _text(first["observed_at"]) if include_pro else None,
    }
    result: dict[str, Any] = {
        "state": "available" if has_count else "unknown", "visibility": "pro",
        "latest": public_latest, "first_observed": public_first,
        "change": change if include_pro else {"state": "pro_only"},
        "freshness": {
            "state": current_freshness if include_pro else "pro_only",
            "observed_at": _text(latest["observed_at"]) if include_pro else None,
            "last_verified_at": _text(latest["last_verified_at"]) if include_pro else None,
            "observation_age_hours": observation_age_hours if include_pro else None,
        },
        "posting_time": _text(latest["posting_time"]) if include_pro else None,
        "apply_method": _text(latest["apply_method"]) if include_pro else None,
        "easy_apply_marker": bool(latest["easy_apply_marker"]) if include_pro else False,
        "provenance": {"source": "verified source", "url": _text(latest["provenance_url"]) or None} if include_pro else None,
        "pro": None,
    }
    if include_pro:
        alerts: list[dict[str, Any]] = []
        if score is not None and score >= 75:
            alerts.append({"type": "low_competition", "priority": "normal"})
        if current_freshness == "fresh":
            alerts.append({"type": "recently_verified", "priority": "normal"})
        result["pro"] = {
            "latest_count": latest["exact"], "latest_range": _range_value(latest),
            "first_observed_count": first["exact"], "first_observed_range": _range_value(first),
            "change": change, "competition_score": score, "competition_score_confidence": confidence,
            "low_competition": score is not None and score >= 75,
            "snapshot_count": int(row.get("applicant_snapshot_count") or 0),
            "opportunity_alerts": alerts,
        }
    return result


def build_priority(row: Mapping[str, Any], match: Mapping[str, Any], competition: Mapping[str, Any]) -> dict[str, Any]:
    """Build the versioned score; missing applicant data remains neutral."""

    v2 = match.get("v2") if isinstance(match.get("v2"), Mapping) else match
    fit = v2.get("score") if isinstance(v2, Mapping) else None
    try:
        fit_score = max(0.0, min(100.0, float(fit)))
    except (TypeError, ValueError):
        fit_score = 50.0
    observed = row.get("applicant_latest_observed_at") or row.get("last_verified_at") or row.get("first_seen_at")
    observed_epoch = _iso_epoch(observed)
    freshness_score = 50.0
    if observed_epoch is not None:
        age_hours = max(0.0, (datetime.now(timezone.utc).timestamp() - observed_epoch) / 3600)
        freshness_score = max(0.0, 100.0 - min(100.0, age_hours / 2.4))
    latest = {"exact": row.get("applicant_latest_exact"), "min": row.get("applicant_latest_min"), "max": row.get("applicant_latest_max")}
    competition_score, competition_confidence = _competition_score(latest)
    freshness_state = competition.get("freshness", {}).get("state") if isinstance(competition.get("freshness"), Mapping) else ""
    if freshness_state == "stale" or _text(row.get("applicant_latest_freshness_status")).casefold() == "stale":
        competition_score, competition_confidence = None, "stale"
    competition_score = 50.0 if competition_score is None else float(competition_score)
    score = round(
        fit_score * PRIORITY_WEIGHTS["user_fit"]
        + freshness_score * PRIORITY_WEIGHTS["freshness"]
        + competition_score * PRIORITY_WEIGHTS["competition"],
        2,
    )
    return {
        "score": score,
        "state": "partial" if fit is None or observed_epoch is None else "available",
        "formula_version": PRIORITY_FORMULA_VERSION,
        "components": {
            "user_fit": round(fit_score, 2), "freshness": round(freshness_score, 2),
            "competition": round(competition_score, 2), "competition_confidence": competition_confidence,
            "weights": dict(PRIORITY_WEIGHTS),
        },
    }


__all__ = [
    "APPLICANT_SOURCE_DECISIONS", "PHASE_G_POLICY_VERSION", "PHASE_G_PRODUCTION_ACTIVATED",
    "PRIORITY_FORMULA_VERSION", "PRIORITY_WEIGHTS", "applicant_source_decision",
    "applicant_source_gate", "build_applicant_competition", "build_priority",
    "explicit_applicant_count", "freshness_status", "has_applicant_evidence",
    "is_portal_target", "normalize_applicant_snapshot", "parse_applicant_count",
    "portal_audit_gate",
]
