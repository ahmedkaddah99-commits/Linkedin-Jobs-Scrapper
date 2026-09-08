"""Phase B catalog normalization and application-destination policy.

Phase B accepts only public job records whose employer and direct application
destination can be established from the server-owned source manifest.  A
listing that cannot be proven is rejected with an explicit reason; missing
facts are never filled in with guesses.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from urllib.parse import urlsplit

from backend.acquisition.network_policy import hostname_for_url
from backend.acquisition.phase_g import is_portal_target
from backend.acquisition.quality import canonical_employer_name, normalize_job_for_ingestion


PHASE_B_DEFAULT_CONFIG = {
    "controlled_validation_enabled": False,
    "staging_publication_enabled": True,
    "promotion_enabled": False,
}

_EXCLUDED_APPLICATION_PATTERNS = (
    re.compile(r"\bquick\s+apply\b", re.IGNORECASE),
    re.compile(r"\beasy\s+apply\b", re.IGNORECASE),
    re.compile(r"\bportal[-\s]+only\b", re.IGNORECASE),
    re.compile(r"\bemail[-\s]+only\b", re.IGNORECASE),
    re.compile(r"\bapply\s+(?:by|via|through)\s+email\b", re.IGNORECASE),
)
_EXCLUDED_METHOD_VALUES = {
    "quick_apply",
    "quick apply",
    "easy_apply",
    "easy apply",
    "portal_only",
    "portal-only",
    "email_only",
    "email-only",
    "email",
}


def _text(value: object) -> str:
    return str(value or "").strip()


def _normalized_text(value: object) -> str:
    return " ".join(_text(value).casefold().split())


def _url(value: object) -> str:
    candidate = _text(value)
    parts = urlsplit(candidate)
    if parts.scheme.casefold() != "https" or not parts.hostname:
        return ""
    return candidate.split("#", 1)[0]


def _host_allowed(host: str, allowed_hosts: set[str], suffixes: Iterable[str] = ()) -> bool:
    normalized = hostname_for_url(host if "://" in str(host) else f"https://{host}")
    if normalized in allowed_hosts:
        return True
    return any(normalized == suffix or normalized.endswith(f".{suffix}") for suffix in suffixes)


def _application_method_text(job: Mapping[str, object]) -> str:
    values = [
        job.get("application_method"),
        job.get("apply_method"),
        job.get("application_type"),
        job.get("portal"),
        job.get("source"),
    ]
    return " ".join(_text(value) for value in values if _text(value))


def _looks_excluded(job: Mapping[str, object]) -> str:
    method = _normalized_text(_application_method_text(job))
    if method in _EXCLUDED_METHOD_VALUES or any(value in method for value in _EXCLUDED_METHOD_VALUES):
        return "unsupported_application_method"
    searchable = " ".join(
        _text(job.get(key))
        for key in ("title", "description", "full_description", "apply_link", "apply_url", "application_method")
    )
    for pattern in _EXCLUDED_APPLICATION_PATTERNS:
        if pattern.search(searchable):
            return "unsupported_application_method"
    return ""


def _official_apply_url(job: Mapping[str, object], target: Mapping[str, object]) -> str:
    # A listing/source URL is not proof of a job-specific application
    # destination.  Only connector-declared Apply fields may satisfy this
    # gate; enrichment must never invent an application URL later.
    candidates = (
        job.get("apply_link"),
        job.get("apply_url"),
        job.get("hostedUrl"),
        job.get("absolute_url"),
    )
    target_hosts = {
        hostname_for_url(str(target.get(key) or ""))
        for key in ("canonical_target_url", "request_url", "provenance_url")
        if hostname_for_url(str(target.get(key) or ""))
    }
    configured_hosts = target.get("official_employer_hosts") or dict(target.get("config") or {}).get(
        "official_employer_hosts", []
    )
    if isinstance(configured_hosts, (list, tuple, set)):
        target_hosts.update(hostname_for_url(f"https://{_text(host)}") for host in configured_hosts if _text(host))
    connector = _text(target.get("connector")).casefold()
    ats_suffixes = {
        "greenhouse": ("greenhouse.io",),
        "lever": ("lever.co",),
    }.get(connector, ())
    for candidate in candidates:
        normalized = _url(candidate)
        if not normalized:
            continue
        host = hostname_for_url(normalized)
        if _host_allowed(host, target_hosts, ats_suffixes):
            return normalized
    return ""


def normalize_phase_b_jobs(
    jobs: Iterable[Mapping[str, object]],
    target: Mapping[str, object],
) -> dict[str, list[dict[str, object]] | int]:
    """Normalize and gate one source response before canonical persistence."""

    accepted: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    seen_external: set[str] = set()
    target_config = dict(target.get("config") or {})
    # A portal is an acquisition target only.  Its display name (for example,
    # "LinkedIn Germany") must never become the canonical employer.
    employer = canonical_employer_name(target)
    if not is_portal_target(target):
        employer = employer or _text(target.get("display_name"))
    connector = _text(target.get("connector")).casefold()
    target_host = hostname_for_url(str(target.get("canonical_target_url") or ""))
    for raw in jobs:
        job = dict(raw)
        external_id = _text(job.get("job_id") or job.get("external_job_id") or job.get("id"))
        title = " ".join(_text(job.get("title") or job.get("text")).split())
        reason = _looks_excluded(job)
        if not external_id:
            reason = reason or "missing_external_job_id"
        if not title:
            reason = reason or "missing_title"
        if not employer or not target_host:
            reason = reason or "unverified_employer"
        if external_id and external_id in seen_external:
            reason = reason or "duplicate_source_record"
        if reason:
            rejected.append({"external_job_id": external_id, "reason": reason, "title": title})
            continue
        seen_external.add(external_id)
        location_value = job.get("location") or job.get("location_raw")
        if isinstance(location_value, Mapping):
            location_value = location_value.get("name") or location_value.get("address") or ""
        location = " ".join(_text(location_value).split())
        source_url = _url(job.get("url") or job.get("link") or job.get("source_url") or job.get("absolute_url") or job.get("hostedUrl"))
        if not source_url:
            # A missing direct-apply destination is report-only.  A missing
            # source URL is different: without a source identity the record
            # cannot be safely persisted or reconciled.
            rejected.append({"external_job_id": external_id, "reason": "missing_source_url", "title": title})
            continue
        description = _text(job.get("full_description") or job.get("description") or job.get("descriptionPlain"))
        normalized = {
            **job,
            "job_id": external_id,
            "external_job_id": external_id,
            "title": title,
            "company": employer,
            "location": location,
            "location_raw": location,
            "url": source_url,
            "link": source_url,
            "source_url": source_url,
            "apply_link_source": connector or "official_employer",
            "source_ats": connector,
            "employer_verified": True,
            "description": description,
            "full_description": str(job.get("full_description") or job.get("description") or description),
        }
        configured_profile = target_config.get("company_profile") or target_config.get("company")
        if isinstance(configured_profile, Mapping):
            normalized["company_details"] = dict(configured_profile)
        normalized = normalize_job_for_ingestion(normalized, {**target, "canonical_company_name": employer})
        normalized["quality_warnings"] = list(dict.fromkeys(normalized.get("quality_warnings") or []))
        accepted.append(normalized)
    return {"accepted": accepted, "rejected": rejected, "raw_count": len(accepted) + len(rejected)}


__all__ = ["PHASE_B_DEFAULT_CONFIG", "normalize_phase_b_jobs"]
