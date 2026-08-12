"""Provider-independent company identity and URL reconciliation contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit


CANONICAL_ENTITY_KINDS = (
    "employer",
    "source",
    "fixture",
    "quarantined",
    "unknown",
)
PROFILE_STATUSES = ("present", "absent", "incomplete", "conflicted")
URL_LIFECYCLES = (
    "discovered",
    "configured_official",
    "validated",
    "invalid",
    "rejected",
    "duplicate",
    "unlinked",
    "ignored",
)
CANONICAL_URL_TYPES = (
    "homepage",
    "careers",
    "ats_jobs",
    "job_detail",
    "source",
    "other",
)

_ENTITY_KIND_ALIASES = {
    "employer": "employer",
    "company": "employer",
    "source": "source",
    "source_entity": "source",
    "fixture": "fixture",
    "test": "fixture",
    "quarantine": "quarantined",
    "quarantined": "quarantined",
    "unknown": "unknown",
}

_URL_TYPE_ALIASES = {
    "website": "homepage",
    "homepage_url": "homepage",
    "company_website": "homepage",
    "site": "homepage",
    "careers_page": "careers",
    "careers_url": "careers",
    "career_page": "careers",
    "jobs_url": "careers",
    "employer_jobs": "careers",
    "employer_jobs_url": "careers",
    "ats": "ats_jobs",
    "ats_url": "ats_jobs",
    "ats_board": "ats_jobs",
    "ats_board_url": "ats_jobs",
    "application_host": "ats_jobs",
    "application_host_url": "ats_jobs",
    "job_detail_url": "job_detail",
    "provenance_url": "source",
    "source_url": "source",
    "social_profile": "other",
    "social_url": "other",
    "profile_url": "other",
    "enrichment": "other",
    "enrichment_url": "other",
}

_URL_LIFECYCLE_ALIASES = {
    "valid": "validated",
    "verified": "validated",
    "not_validated": "discovered",
    "unverified": "discovered",
    "configured": "configured_official",
    "official": "configured_official",
    "invalid": "invalid",
    "blocked": "rejected",
}


def canonical_entity_kind(value: Any, *, target_kind: Any = "", quarantined: Any = False) -> str:
    candidate = str(value or target_kind or "unknown").strip().casefold().replace("-", "_")
    if candidate in {"fixture_source", "fixture_target"}:
        candidate = "fixture"
    if candidate == "fixture":
        return "fixture"
    if candidate == "quarantined":
        return "quarantined"
    if quarantined is True or str(quarantined or "").casefold() in {"1", "true", "yes"}:
        return "quarantined"
    if candidate in {"source_target", "job_board", "portal"}:
        candidate = "source"
    return _ENTITY_KIND_ALIASES.get(candidate, "unknown")


def canonical_profile_status(value: Any) -> str:
    candidate = str(value or "").strip().casefold()
    return candidate if candidate in PROFILE_STATUSES else "absent"


def canonical_url_type(value: Any) -> str:
    candidate = str(value or "other").strip().casefold().replace("-", "_").replace(" ", "_")
    if candidate in CANONICAL_URL_TYPES:
        return candidate
    return _URL_TYPE_ALIASES.get(candidate, "other")


def canonical_url_lifecycle(value: Any, *, default: str = "discovered") -> str:
    candidate = str(value or default).strip().casefold().replace("-", "_").replace(" ", "_")
    candidate = _URL_LIFECYCLE_ALIASES.get(candidate, candidate)
    return candidate if candidate in URL_LIFECYCLES else default


def name_key(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def structural_url(value: Any) -> tuple[str, str, str]:
    """Return ``(original, canonical, reason)`` without network access."""

    original = str(value or "").strip()
    if not original:
        return "", "", "url_missing"
    try:
        parsed = urlsplit(original)
        host = (parsed.hostname or "").rstrip(".").casefold()
        port = parsed.port
    except ValueError:
        return original, "", "url_parse_failed"
    if parsed.scheme.casefold() not in {"http", "https"}:
        return original, "", "unsupported_scheme"
    if not host:
        return original, "", "host_missing"
    if parsed.username or parsed.password:
        return original, "", "embedded_credentials"
    if port not in (None, 80, 443):
        return original, "", "non_default_port"
    scheme = parsed.scheme.casefold()
    netloc = host
    if port not in (None, 80 if scheme == "http" else 443):
        netloc = f"{host}:{port}"
    return original, urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, "")), ""


@dataclass(frozen=True, slots=True)
class CompanyLinkDecision:
    decision: str
    review_required: bool
    confidence: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "review_required": self.review_required,
            "confidence": self.confidence,
            "reason": self.reason,
        }


def classify_company_link(
    observed_name: Any,
    candidates: Sequence[Mapping[str, Any]],
    *,
    identity_key: str = "",
    target_id: str = "",
    evidence: Sequence[Mapping[str, Any]] = (),
) -> CompanyLinkDecision:
    """Classify a candidate without ever treating a name as an identity key."""

    if identity_key or target_id:
        matching = [
            item
            for item in candidates
            if (identity_key and str(item.get("identity_key") or "") == identity_key)
            or (target_id and str(item.get("target_id") or "") == target_id)
        ]
        if len(matching) == 1:
            return CompanyLinkDecision("accepted", False, 1.0, "stable_identity_evidence")
        if len(matching) > 1:
            return CompanyLinkDecision("needs_review", True, 0.0, "identity_evidence_conflict")

    observed_key = name_key(observed_name)
    name_matches = [
        item for item in candidates if name_key(item.get("canonical_name")) == observed_key and observed_key
    ]
    if len(name_matches) == 1:
        return CompanyLinkDecision("needs_review", True, 0.5, "name_match_requires_review")
    if len(name_matches) > 1:
        return CompanyLinkDecision("needs_review", True, 0.0, "company_name_collision")
    if candidates or evidence:
        return CompanyLinkDecision("needs_review", True, 0.0, "insufficient_identity_evidence")
    return CompanyLinkDecision("unlinked", True, 0.0, "no_candidate_company")


__all__ = [
    "CANONICAL_ENTITY_KINDS",
    "CANONICAL_URL_TYPES",
    "CompanyLinkDecision",
    "PROFILE_STATUSES",
    "URL_LIFECYCLES",
    "canonical_entity_kind",
    "canonical_profile_status",
    "canonical_url_lifecycle",
    "canonical_url_type",
    "classify_company_link",
    "name_key",
    "structural_url",
]
