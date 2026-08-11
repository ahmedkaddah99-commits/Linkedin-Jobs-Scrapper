"""Shared acquisition normalization, provenance, and report-only quality rules.

This module is intentionally connector-agnostic.  Connectors may provide more
facts, but they do not get to invent a different meaning for an application
URL, a description, or a content version.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any, TypedDict
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Comment

from backend.acquisition.network_policy import hostname_for_url
from backend.acquisition.rule_registry import (
    FIELD_STATE_DESCRIPTIONS,
    FIELD_STATES,
    VALUE_FIELD_STATES,
    canonical_field_state,
    field_state_for,
)
from backend.acquisition.unified_mapping import UNIFIED_RULE_VERSION, map_job_fields
from backend.domain.job_identity import canonicalize_url, compact_whitespace


QUALITY_SCHEMA_VERSION = "acquisition_quality_v1"
DESCRIPTION_SCHEMA_VERSION = "description_representations_v1"
APPLICATION_URL_SCHEMA_VERSION = "application_destination_v1"

URL_EMPLOYER_JOB_DETAIL = "employer_job_detail"
URL_ATS_JOB_DETAIL = "ats_job_detail"
URL_EMPLOYER_APPLICATION = "employer_application"
URL_ATS_APPLICATION = "ats_application"
URL_CAREERS_INDEX = "careers_index"
URL_SEARCH_RESULTS = "search_results"
URL_PORTAL_LISTING = "portal_listing"
URL_UNKNOWN = "unknown"

DIRECT_APPLICATION_CLASSIFICATIONS = {URL_EMPLOYER_APPLICATION, URL_ATS_APPLICATION}
JOB_DETAIL_CLASSIFICATIONS = {URL_EMPLOYER_JOB_DETAIL, URL_ATS_JOB_DETAIL}
LISTING_CLASSIFICATIONS = {URL_CAREERS_INDEX, URL_SEARCH_RESULTS, URL_PORTAL_LISTING}

_ATS_SUFFIXES = {
    "greenhouse": ("greenhouse.io", "greenhouse.com"),
    "lever": ("lever.co",),
    "workday": ("myworkdayjobs.com", "myworkdaysite.com", "workdayjobs.com"),
    "personio": ("personio.de", "personio.com"),
    "recruitee": ("recruitee.com",),
    "smartrecruiters": ("smartrecruiters.com",),
}
_SOURCE_SUFFIXES = ("greenhouse", "lever", "workday", "personio", "recruitee", "smartrecruiters")
_LISTING_TOKENS = (
    "/career", "/careers", "/jobs", "/job-search", "/search", "/open-positions", "/openings",
    "/karriere", "/stellenangebote", "/stellenanzeigen", "/vacancies", "/positions",
)
_APPLICATION_TOKENS = (
    "/apply", "/application", "/bewerben", "/bewerbung", "/submit-application", "/apply-now",
)
_JOB_DETAIL_TOKENS = (
    "/job/", "/jobs/", "/position/", "/positions/", "/opening/", "/openings/", "/vacancy/",
    "/vacancies/", "/stelle/", "/stellenangebot/", "/posting/", "/postings/",
)

_VOLATILE_KEYS = {
    "posted_age_hours", "last_seen_at", "last_verified_at", "observed_at", "observation_timestamp",
    "request_id", "attempt_id", "crawl_duration_ms", "latency_ms", "scrape_cost", "scrapeops_cost",
    "native_credits", "runner_credits", "credits_actual", "credits_estimated", "runtime_metadata",
    "run_timestamp", "run_id", "cycle_id", "task_id", "version_id", "generated_at", "created_at",
    "updated_at", "first_seen_at", "verified_at", "applicant_count", "applicants", "view_count",
    "job_id", "external_job_id", "external_id_source", "posted_time_text", "posted_text", "listed_at_text",
    "posted_at", "source_posted_at", "date_posted", "dateposted", "posting_time", "posting_timestamp",
    "published_at", "publishedat",
}
_PRESERVE_TIMESTAMP_KEYS = {"posted_at", "date_posted", "datePosted", "posting_time", "posting_timestamp"}
_DESCRIPTION_KEYS = {"description", "full_description", "description_raw", "description_html", "description_text"}

_METADATA_FIELDS = (
    "department", "team", "office", "location_collection", "employment_type", "commitment",
    "workplace_arrangement", "language", "salary", "requisition_id", "categories", "custom_fields",
    "seniority", "years_experience", "education", "posted_at", "source_status",
)
_GENERIC_SUPPORTED_FIELDS = frozenset(_METADATA_FIELDS)
_ATS_SUPPORTED_FIELDS = {
    # These are the fields exposed by the public response shape, not fields
    # that happen to exist in another ATS or in an employer enrichment page.
    "greenhouse": frozenset({
        "department", "office", "location_collection", "requisition_id", "categories", "custom_fields",
        "source_status", "posted_at",
    }),
    "lever": frozenset({
        "department", "team", "location_collection", "employment_type", "commitment",
        "workplace_arrangement", "salary", "categories", "custom_fields", "source_status",
        "posted_at",
    }),
    "workday": frozenset(_METADATA_FIELDS),
    "personio": frozenset(_METADATA_FIELDS),
    "recruitee": frozenset(_METADATA_FIELDS),
    "smartrecruiters": frozenset(_METADATA_FIELDS),
}


class UrlCandidate(TypedDict, total=False):
    url: str
    classification: str
    source_field: str
    source: str
    verified: bool


class DescriptionRepresentations(TypedDict):
    schema_version: str
    raw_source: str
    sanitized_html: str
    plain_text: str
    decoding: str


def _provenance(*, source: str, url: str, field: str = "", observation_id: str = "", observed_at: str = "") -> dict[str, Any] | None:
    """Return provenance only when there is an actual source observation."""

    if not any((source, url, field, observation_id, observed_at)):
        return None
    return {
        "source": source or None,
        "url": url or None,
        "field": field or None,
        "source_observation_id": observation_id or None,
        "observed_at": observed_at or None,
    }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _hostname(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return ""
    host = hostname_for_url(raw)
    if host:
        return host
    # Configured host allowlists commonly contain bare names such as
    # ``n26.com`` rather than full URLs.
    if "://" not in raw and "/" not in raw:
        return raw.split(":", 1)[0].casefold().strip(".")
    return ""


def _host_matches(host: str, allowed: Iterable[str]) -> bool:
    normalized = _hostname(host)
    return bool(normalized) and any(
        normalized == _hostname(item) or normalized.endswith(f".{_hostname(item)}")
        for item in allowed if _hostname(item)
    )


def source_employer_name(value: Any, *, connector: str = "", source_token: str = "") -> str:
    """Remove source branding from a display name without changing employers."""

    name = compact_whitespace(_text(value))
    if not name:
        return ""
    connector_token = _text(connector).casefold()
    suffixes = set(_SOURCE_SUFFIXES)
    if connector_token:
        suffixes.add(connector_token)
    suffix_pattern = "|".join(re.escape(item) for item in sorted(suffixes, key=len, reverse=True))
    name = re.sub(rf"\s+(?:{suffix_pattern})(?:\s+(?:api|board|portal))?$", "", name, flags=re.IGNORECASE)
    token = compact_whitespace(_text(source_token))
    if token and name.casefold() == f"{token.casefold()} {connector_token}".strip():
        name = token
    return name or compact_whitespace(_text(value))


def canonical_employer_name(target: Mapping[str, Any], job: Mapping[str, Any] | None = None) -> str:
    config = target.get("config") if isinstance(target.get("config"), Mapping) else {}
    connector = _text(target.get("connector") or config.get("connector"))
    source_token = _text(target.get("source_token") or config.get("source_token"))
    configured = _text(target.get("canonical_company_name") or config.get("canonical_company_name"))
    if configured:
        return source_employer_name(configured, connector=connector, source_token=source_token)
    for candidate in (
        target.get("employer_name"),
        (job or {}).get("employer_name") if isinstance(job, Mapping) else "",
        (job or {}).get("canonical_company_name") if isinstance(job, Mapping) else "",
        target.get("display_name"),
    ):
        candidate_text = _text(candidate)
        if candidate_text:
            return source_employer_name(candidate_text, connector=connector, source_token=source_token)
    return ""


def company_name_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _text(value).casefold()).strip()


def _target_hosts(target: Mapping[str, Any]) -> set[str]:
    config = target.get("config") if isinstance(target.get("config"), Mapping) else {}
    values: list[Any] = [target.get("canonical_target_url"), target.get("request_url"), target.get("provenance_url")]
    values.extend(target.get("official_employer_hosts") or [])
    values.extend(config.get("official_employer_hosts") or [])
    return {_hostname(value) for value in values if _hostname(value)}


def _ats_for_target(target: Mapping[str, Any], url: str = "") -> str:
    configured = _text(target.get("connector") or target.get("source_ats")).casefold()
    host = _hostname(url)
    if configured in _ATS_SUFFIXES and _host_matches(host, _ATS_SUFFIXES[configured]):
        return configured
    for ats, suffixes in _ATS_SUFFIXES.items():
        if _host_matches(host, suffixes):
            return ats
    return ""


def classify_job_url(
    url: Any,
    *,
    target: Mapping[str, Any] | None = None,
    source_ats: str = "",
    explicit_kind: str = "",
) -> str:
    normalized = canonicalize_url(_text(url))
    if not normalized:
        return URL_UNKNOWN
    target = target or {}
    host = _hostname(normalized)
    path = (urlparse(normalized).path or "/").casefold()
    query = (urlparse(normalized).query or "").casefold()
    ats = _ats_for_target({**dict(target), "connector": source_ats or target.get("connector")}, normalized)
    employer_hosts = _target_hosts(target)
    explicit = _text(explicit_kind).casefold()
    if explicit in {"employer_application", "employer_apply", "direct_apply"}:
        return URL_EMPLOYER_APPLICATION
    if explicit in {"ats_application", "ats_apply"}:
        return URL_ATS_APPLICATION
    if "application" in path or any(token in path for token in _APPLICATION_TOKENS):
        return URL_ATS_APPLICATION if ats else URL_EMPLOYER_APPLICATION if host in employer_hosts or not employer_hosts else URL_UNKNOWN
    if any(token in query for token in ("search=", "q=", "keyword=", "page=")) or "/search" in path:
        return URL_SEARCH_RESULTS
    if any(token in path for token in _LISTING_TOKENS) and not any(token in path for token in _JOB_DETAIL_TOKENS[1:]):
        if ats:
            return URL_PORTAL_LISTING
        return URL_CAREERS_INDEX if host in employer_hosts or not employer_hosts else URL_PORTAL_LISTING
    if ats:
        if any(token in path for token in ("/jobs/", "/postings/", "/position/", "/job/")):
            return URL_ATS_JOB_DETAIL
        # Lever hosted URLs are ``/<company-slug>/<posting-id>`` rather than
        # ``/jobs/<id>``. A one-segment ATS path is the board; two or more
        # segments identify a posting detail page.
        ats_segments = [segment for segment in path.split("/") if segment]
        if len(ats_segments) >= 2:
            return URL_ATS_JOB_DETAIL
        if len(ats_segments) == 1:
            return URL_PORTAL_LISTING
    if any(token in path for token in _JOB_DETAIL_TOKENS):
        return URL_EMPLOYER_JOB_DETAIL if host in employer_hosts or not employer_hosts else URL_UNKNOWN
    if host in employer_hosts and path in {"", "/", "/careers", "/career", "/jobs"}:
        return URL_CAREERS_INDEX
    return URL_UNKNOWN


_APPLY_TEXT_TOKENS = (
    "apply", "application", "bewerben", "bewerbung", "submit application", "start application",
)


def extract_application_candidates_from_html(
    raw_html: Any,
    page_url: Any,
    *,
    target: Mapping[str, Any] | None = None,
    source_ats: str = "",
) -> list[UrlCandidate]:
    """Extract direct-application evidence from a fetched job page.

    This is deliberately a small deterministic parser. It does not guess an
    employer URL from a company name and it does not treat a job-detail page
    as an application route. Forms are accepted when their action is an
    application endpoint; anchors/buttons need explicit application intent.
    """

    html_value = "" if raw_html is None else str(raw_html)
    base_url = canonicalize_url(_text(page_url))
    if not html_value or not base_url:
        return []
    soup = BeautifulSoup(html_value, "html.parser")
    target = target or {"canonical_target_url": base_url}
    candidates: list[UrlCandidate] = []
    seen: set[str] = set()
    selector = "a[href], button[data-href], button[data-url], [data-apply-url], form[action]"
    for node in soup.select(selector):
        is_form = node.name == "form"
        raw_href = (
            node.get("href")
            or node.get("data-href")
            or node.get("data-url")
            or node.get("data-apply-url")
            or node.get("action")
        )
        href = canonicalize_url(urljoin(base_url, str(raw_href or "").strip()))
        if not href or href in seen:
            continue
        text_value = compact_whitespace(
            " ".join(
                str(value or "")
                for value in (
                    node.get_text(" ", strip=True),
                    node.get("aria-label"),
                    node.get("title"),
                    node.get("name"),
                )
            )
        ).casefold()
        path = (urlparse(href).path or "").casefold()
        explicit_application = is_form or any(token in text_value for token in _APPLY_TEXT_TOKENS)
        path_application = any(token in path for token in _APPLICATION_TOKENS)
        if not explicit_application and not path_application:
            continue
        classification = classify_job_url(
            href,
            target=target,
            source_ats=source_ats,
            explicit_kind="ats_application" if source_ats in _ATS_SUFFIXES and path_application else "",
        )
        if classification not in DIRECT_APPLICATION_CLASSIFICATIONS:
            # Preserve the evidence for diagnostics, but never promote an
            # off-domain or detail route to a direct destination.
            if classification not in JOB_DETAIL_CLASSIFICATIONS:
                continue
        seen.add(href)
        candidates.append({
            "url": href,
            "classification": classification,
            "source_field": "html_form_action" if is_form else "html_apply_link",
            "source": "employer_page_html",
            "verified": classification in DIRECT_APPLICATION_CLASSIFICATIONS,
        })
    return candidates


def resolve_application_destination(job: Mapping[str, Any], target: Mapping[str, Any]) -> dict[str, Any]:
    """Return direct-apply evidence and a truthful user-facing fallback."""

    fields = (
        ("application_url", "application_url"), ("employer_application_url", "employer_application_url"),
        ("ats_application_url", "ats_application_url"), ("direct_apply_url", "direct_apply_url"),
        ("apply_url", "apply_url"), ("apply_link", "apply_link"), ("applyUrl", "applyUrl"),
        ("hostedUrl", "hostedUrl"), ("absolute_url", "absolute_url"), ("job_detail_url", "job_detail_url"),
        ("url", "url"), ("link", "link"), ("source_url", "source_url"),
    )
    source_ats = _text(job.get("source_ats") or target.get("connector")).casefold()
    candidates: list[UrlCandidate] = []
    seen: set[tuple[str, str]] = set()

    html_values: list[Any] = [
        job.get("source_page_html"), job.get("page_html"), job.get("source_html"), job.get("raw_html"),
    ]
    raw_payload = job.get("source_raw_payload")
    if isinstance(raw_payload, Mapping):
        html_values.extend(raw_payload.get(key) for key in ("source_page_html", "page_html", "source_html", "raw_html", "html"))
    for html_value in html_values:
        if not html_value:
            continue
        for item in extract_application_candidates_from_html(
            html_value,
            job.get("job_detail_url") or job.get("url") or job.get("link") or job.get("source_url"),
            target=target,
            source_ats=source_ats,
        ):
            key = (str(item.get("url") or ""), str(item.get("source_field") or ""))
            if key not in seen:
                seen.add(key)
                candidates.append(item)
    for field_name, source_field in fields:
        value = job.get(field_name)
        if value in (None, "", []):
            continue
        values = value if isinstance(value, (list, tuple, set)) else [value]
        for item in values:
            normalized = canonicalize_url(_text(item))
            if not normalized or (normalized, source_field) in seen:
                continue
            seen.add((normalized, source_field))
            classification = classify_job_url(
                normalized,
                target=target,
                source_ats=source_ats,
                explicit_kind=("employer_application" if field_name == "employer_application_url" else "ats_application" if field_name == "ats_application_url" else ""),
            )
            candidates.append({
                "url": normalized,
                "classification": classification,
                "source_field": source_field,
                "source": _text(job.get("apply_link_source") or source_ats or "connector"),
                "verified": classification in DIRECT_APPLICATION_CLASSIFICATIONS,
            })
    direct = next((item for item in candidates if item["classification"] in DIRECT_APPLICATION_CLASSIFICATIONS), None)
    detail = next((item for item in candidates if item["classification"] in JOB_DETAIL_CLASSIFICATIONS), None)
    listing = next((item for item in candidates if item["classification"] in LISTING_CLASSIFICATIONS), None)
    user_facing = direct or detail or listing or (candidates[0] if candidates else None)
    if direct:
        method = "direct_apply"
        status = "verified"
        warning_codes: list[str] = []
    elif detail:
        method = "job_detail"
        status = "unresolved"
        warning_codes = ["missing_direct_application_url"]
    elif listing:
        method = "listing_fallback"
        status = "unresolved"
        warning_codes = ["listing_fallback_not_direct_apply", "missing_direct_application_url"]
    else:
        method = "unknown"
        status = "missing"
        warning_codes = ["missing_application_url", "missing_application_destination"]
    if detail and detail.get("source_field") in {
        "apply_link", "apply_url", "application_url", "direct_apply_url", "hostedUrl", "absolute_url", "url", "link", "source_url",
    }:
        warning_codes.append("job_detail_url_used_as_application_url")
    return {
        "schema_version": APPLICATION_URL_SCHEMA_VERSION,
        "job_detail_url": detail["url"] if detail else "",
        "resolved_url": direct["url"] if direct else "",
        "user_facing_url": user_facing["url"] if user_facing else "",
        "status": status,
        "classification": direct["classification"] if direct else (detail["classification"] if detail else listing["classification"] if listing else URL_UNKNOWN),
        "application_method": method,
        "destination_type": (
            "dedicated_apply" if direct and not any(str(item.get("source_field") or "").startswith("html_form") for item in candidates if item is direct)
            else "embedded_apply" if direct
            else "job_detail_with_apply" if detail and detail.get("verified")
            else "job_detail_only" if detail
            else "unresolved"
        ),
        "candidate_urls": candidates,
        "validation": {
            "validated_at": _text(job.get("application_validated_at")) or None,
            "final_url": _text(job.get("application_final_url")) or None,
            "http_status": job.get("application_http_status"),
            "evidence_type": _text(job.get("application_evidence_type")) or None,
            "failure_reason": _text(job.get("application_failure_reason")) or ("not_validated" if direct or detail else "missing_destination"),
        },
        "warnings": warning_codes,
        "evidence": "direct employer/ATS application route" if direct else "no verified direct application route in source payload",
    }


_ALLOWED_HTML_TAGS = {
    "a", "b", "blockquote", "br", "code", "div", "em", "h1", "h2", "h3", "h4", "h5", "h6",
    "i", "li", "ol", "p", "pre", "span", "strong", "table", "tbody", "td", "th", "thead", "tr", "u", "ul",
}
_ALLOWED_HTML_ATTRIBUTES = {"a": {"href", "title", "target", "rel"}}


def normalize_description(raw_value: Any) -> DescriptionRepresentations:
    """Decode entities once, sanitize markup, and retain a plain-text view."""

    raw = "" if raw_value is None else str(raw_value)
    decoded_once = html.unescape(raw)
    soup = BeautifulSoup(decoded_once, "html.parser")
    for node in soup.find_all(string=lambda value: isinstance(value, Comment)):
        node.extract()
    for node in soup.find_all(["script", "style", "iframe", "object", "embed", "form", "input", "button"]):
        node.decompose()
    for node in soup.find_all(True):
        if node.name not in _ALLOWED_HTML_TAGS:
            node.unwrap()
            continue
        allowed = _ALLOWED_HTML_ATTRIBUTES.get(node.name, set())
        for attribute in list(node.attrs):
            if attribute not in allowed:
                del node.attrs[attribute]
        if node.name == "a":
            href = canonicalize_url(str(node.get("href") or ""))
            if href:
                node["href"] = href
                node["rel"] = "nofollow noopener"
            else:
                node.unwrap()
    sanitized_html = "".join(str(child) for child in soup.contents).strip()
    plain_lines = [" ".join(line.split()) for line in soup.get_text("\n", strip=True).splitlines()]
    plain_text = "\n".join(line for line in plain_lines if line)
    if not sanitized_html and raw.strip():
        plain_text = "\n".join(line for line in (" ".join(item.split()) for item in decoded_once.splitlines()) if line)
        sanitized_html = f"<p>{escape(plain_text)}</p>" if plain_text else ""
    return {
        "schema_version": DESCRIPTION_SCHEMA_VERSION,
        "raw_source": raw,
        "sanitized_html": sanitized_html,
        "plain_text": plain_text,
        "decoding": "html_entities_decoded_once",
    }


def _state(value: Any, *, supported: bool | None = True) -> str:
    return field_state_for(value, supported=supported, observed=supported is not None)


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", []):
            return value
    return None


def _normalize_timestamp(value: Any) -> str | None:
    if value in (None, "", []):
        return None
    if isinstance(value, (int, float)):
        try:
            numeric = float(value)
            if numeric > 100_000_000_000:
                numeric /= 1000
            return datetime.fromtimestamp(numeric, tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError, OverflowError):
            return None
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


_RELATIVE_POSTED_AGE_RE = re.compile(
    r"(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>minute|min|hour|hr|day|week|month|year)s?\b",
    re.IGNORECASE,
)


def _relative_posted_age_hours(*values: Any) -> float | None:
    """Read a source-reported relative posting age without using Runr time."""

    for value in values:
        if value in (None, "", []):
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            numeric = float(value)
            if numeric >= 0:
                return numeric
            continue
        text = _text(value).casefold()
        if not text:
            continue
        if any(token in text for token in ("just now", "today", "now")):
            return 0.0
        match = _RELATIVE_POSTED_AGE_RE.search(text)
        if not match:
            continue
        amount = float(match.group("amount"))
        multiplier = {
            "minute": 1 / 60,
            "min": 1 / 60,
            "hour": 1,
            "hr": 1,
            "day": 24,
            "week": 7 * 24,
            "month": 30 * 24,
            "year": 365 * 24,
        }[match.group("unit").casefold()]
        return amount * multiplier
    return None


def normalize_source_timestamps(
    job: Mapping[str, Any],
    *,
    source_ats: str = "",
    provenance_url: str = "",
) -> dict[str, Any]:
    """Separate source lifecycle timestamps from Runr observation times."""

    connector = _text(source_ats).casefold()
    raw = job.get("source_raw_payload") if isinstance(job.get("source_raw_payload"), Mapping) else {}
    metadata = job.get("source_metadata") if isinstance(job.get("source_metadata"), Mapping) else {}

    def source_value(*keys: str) -> tuple[str | None, str]:
        for mapping, mapping_name in ((job, "job"), (raw, "source_raw_payload"), (metadata, "source_metadata")):
            for key in keys:
                value = mapping.get(key) if isinstance(mapping, Mapping) else None
                normalized = _normalize_timestamp(value)
                if normalized:
                    return normalized, f"{mapping_name}.{key}"
        return None, ""

    created_at, created_field = source_value("source_created_at", "created_at", "createdAt")
    posted_keys = (
        "source_posted_at", "date_posted", "datePosted", "published_at", "publishedAt", "first_published_at", "firstPublishedAt",
    )
    # ``posted_at`` was historically populated from Lever ``createdAt`` and
    # Greenhouse ``updated_at``. For ATS payloads it is therefore ambiguous;
    # only an explicit publication field is trusted. Generic employer pages
    # may use JSON-LD ``datePosted`` or the already-typed ``posted_at``.
    if connector not in _ATS_SUFFIXES:
        posted_keys = ("source_posted_at", "posted_at", *posted_keys[1:])
    posted_at, posted_field = source_value(*posted_keys)
    posted_age_hours_value = _relative_posted_age_hours(
        job.get("posted_age_hours"),
        job.get("posted_time_text"),
        job.get("posted_text"),
        job.get("listed_at_text"),
    )
    posted_age_estimated = False
    if not posted_at and posted_age_hours_value is not None:
        observed_at = _normalize_timestamp(job.get("observed_at") or job.get("observation_timestamp"))
        if observed_at:
            observed_datetime = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
            posted_at = (observed_datetime - timedelta(hours=posted_age_hours_value)).isoformat()
            posted_field = "posted_time_text" if _text(job.get("posted_time_text") or job.get("posted_text") or job.get("listed_at_text")) else "posted_age_hours"
            posted_age_estimated = True
    updated_at, updated_field = source_value("source_updated_at", "updated_at", "updatedAt", "last_updated_at", "lastUpdatedAt")
    closed_at, closed_field = source_value("source_closed_at", "closed_at", "closedAt", "archived_at", "archivedAt")
    reopened_at, reopened_field = source_value("source_reopened_at", "reopened_at", "reopenedAt")

    observation_id = _text(job.get("source_observation_id") or job.get("observation_id"))
    observed_at = _text(job.get("observed_at") or job.get("observation_timestamp"))
    source_name = connector or "career_site"

    def field(value: str | None, source_field: str, semantic: str, *, inferred: bool = False) -> dict[str, Any]:
        state = field_state_for(value, supported=True, observed=True, inferred=inferred)
        return {
            "value": value,
            "state": state,
            "state_reason": "source_field_inferred" if state == "inferred" else "source_field_present" if state == "present" else "source_field_missing",
            "semantic": semantic,
            "source_field": source_field or None,
            "provenance": _provenance(
                source=source_name if value else "",
                url=provenance_url if value else "",
                field=source_field if value else "",
                observation_id=observation_id if value else "",
                observed_at=observed_at if value else "",
            ),
            "method": "relative_source_age" if inferred else "source_field" if value else None,
        }

    timestamp_state = "known" if posted_at else ("unknown_source_timestamp" if created_at or updated_at else "unknown")
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "fields": {
            "source_created_at": field(created_at, created_field, "source_record_created"),
            "source_posted_at": field(posted_at, posted_field, "source_published", inferred=posted_age_estimated),
            "source_updated_at": field(updated_at, updated_field, "source_record_updated"),
            "source_closed_at": field(closed_at, closed_field, "source_closed"),
            "source_reopened_at": field(reopened_at, reopened_field, "source_reopened"),
        },
        "timestamp_semantics": "source_posted_age_estimate" if posted_age_estimated else "source_posted_at" if posted_at else "unknown_source_timestamp",
        "timestamp_state": "estimated" if posted_age_estimated else timestamp_state,
        "posted_age_hours": posted_age_hours(posted_at) if posted_at else None,
        "observation": {
            "source_observation_id": observation_id or None,
            "observed_at": observed_at or None,
        },
    }


def normalize_source_metadata(job: Mapping[str, Any], *, source_ats: str = "", provenance_url: str = "") -> dict[str, Any]:
    connector = _text(source_ats).casefold()
    capability_known = connector in _ATS_SUPPORTED_FIELDS
    supported = _ATS_SUPPORTED_FIELDS.get(connector, frozenset())
    raw_metadata = job.get("source_metadata") if isinstance(job.get("source_metadata"), Mapping) else {}
    timestamps = normalize_source_timestamps(job, source_ats=connector, provenance_url=provenance_url)
    raw_payload = job.get("source_raw_payload") if isinstance(job.get("source_raw_payload"), Mapping) else {}
    categories = _first(job, "categories") or _first(raw_metadata, "categories") or _first(raw_payload, "categories")
    custom_fields = _first(job, "custom_fields") or _first(raw_metadata, "custom_fields", "metadata") or _first(raw_payload, "custom_fields", "metadata")
    source_values: dict[str, Any] = {
        "department": _first(job, "department", "department_name") or _first(raw_metadata, "department", "Department"),
        "team": _first(job, "team", "team_name") or _first(raw_metadata, "team", "Team"),
        "office": _first(job, "office", "office_name") or _first(raw_metadata, "office", "Office"),
        "location_collection": _first(job, "location_collection", "locations", "offices") or _first(raw_metadata, "locations", "offices"),
        "employment_type": _first(job, "employment_type", "employmentType", "type") or _first(raw_metadata, "employment_type", "type"),
        "commitment": _first(job, "commitment") or _first(raw_metadata, "commitment") or (categories.get("commitment") if isinstance(categories, Mapping) else None),
        "workplace_arrangement": _first(job, "workplace_arrangement", "workplace_type", "workplaceType", "remote_type") or _first(raw_metadata, "workplace_arrangement", "workplace_type"),
        "language": _first(job, "language", "languages", "language_requirements") or _first(raw_metadata, "language", "languages"),
        "salary": _first(job, "salary", "salary_range", "salaryRange", "compensation", "pay") or _first(raw_metadata, "salary", "salary_range"),
        "requisition_id": _first(job, "requisition_id", "requisitionId", "req_id", "reference") or _first(raw_metadata, "requisition_id", "requisitionId", "reference"),
        "categories": categories,
        "custom_fields": custom_fields,
        "seniority": _first(job, "seniority", "experience_level") or _first(raw_metadata, "seniority", "experience_level"),
        "years_experience": _first(job, "years_experience", "experience_years") or _first(raw_metadata, "years_experience", "experience_years"),
        "education": _first(job, "education", "education_requirements") or _first(raw_metadata, "education", "education_requirements"),
        "posted_at": (timestamps.get("fields", {}).get("source_posted_at", {}) or {}).get("value"),
        "source_status": _first(job, "source_status", "status", "job_status", "state"),
    }
    normalized: dict[str, Any] = {}
    for field in _METADATA_FIELDS:
        value = source_values[field]
        field_supported = field in supported if capability_known else None
        field_state = _state(value, supported=field_supported)
        normalized[field] = {
            "value": value if value not in (None, "", []) else None,
            "state": field_state,
            "state_reason": "source_field_present" if field_state == "present" else "source_field_unsupported" if field_state == "unsupported" else "source_field_missing" if field_state == "missing" else "source_capability_unknown",
            "provenance": _provenance(
                source=connector or "career_site" if value not in (None, "", []) else "",
                url=provenance_url if value not in (None, "", []) else "",
                field=field if value not in (None, "", []) else "",
                observation_id=_text(job.get("source_observation_id") or job.get("observation_id")) if value not in (None, "", []) else "",
                observed_at=_text(job.get("observed_at") or job.get("observation_timestamp")) if value not in (None, "", []) else "",
            ),
            "method": "source_metadata" if value not in (None, "", []) else None,
            "observed_at": _text(job.get("observed_at") or job.get("observation_timestamp")) or None,
        }
    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "fields": normalized,
        "raw": dict(raw_metadata),
        "source_capability": "known" if capability_known else "unknown",
        "supported_fields": sorted(supported),
        "source_timestamps": timestamps,
    }


def _stable_key(key: str) -> bool:
    normalized = key.casefold()
    if normalized in _VOLATILE_KEYS:
        return False
    if normalized in _PRESERVE_TIMESTAMP_KEYS:
        return True
    if normalized.endswith(("_request_id", "_attempt_id", "_runtime", "_duration_ms")):
        return False
    if normalized in {"request", "attempt", "runtime", "telemetry", "usage_events", "crawl_metrics"}:
        return False
    return True


def _stable_value(value: Any, *, key: str = "") -> Any:
    if isinstance(value, Mapping):
        return {
            str(item_key): _stable_value(item_value, key=str(item_key))
            for item_key, item_value in sorted(value.items(), key=lambda item: str(item[0]))
            if _stable_key(str(item_key))
        }
    if isinstance(value, (list, tuple, set)):
        return [_stable_value(item, key=key) for item in value]
    if isinstance(value, str):
        return compact_whitespace(value) if key not in _DESCRIPTION_KEYS else value
    return value


def stable_content_payload(job: Mapping[str, Any]) -> dict[str, Any]:
    description = job.get("description_html") or ""
    if not description:
        description = normalize_description(job.get("description_raw") or job.get("full_description") or job.get("description") or "")["sanitized_html"]
    metadata = job.get("normalized_source_metadata") or normalize_source_metadata(job, source_ats=_text(job.get("source_ats")))
    timestamps = job.get("source_timestamps") or metadata.get("source_timestamps") or {}
    application = job.get("application_destination") if isinstance(job.get("application_destination"), Mapping) else resolve_application_destination(job, {})
    fields = {
        "title": compact_whitespace(_text(job.get("title"))),
        "description_html": description,
        "location": compact_whitespace(_text(job.get("location") or job.get("location_raw"))),
        "department": metadata.get("fields", {}).get("department", {}).get("value") if isinstance(metadata.get("fields", {}).get("department"), Mapping) else job.get("department"),
        "team": metadata.get("fields", {}).get("team", {}).get("value") if isinstance(metadata.get("fields", {}).get("team"), Mapping) else job.get("team"),
        "office": metadata.get("fields", {}).get("office", {}).get("value") if isinstance(metadata.get("fields", {}).get("office"), Mapping) else job.get("office"),
        "employment_type": metadata.get("fields", {}).get("employment_type", {}).get("value") if isinstance(metadata.get("fields", {}).get("employment_type"), Mapping) else job.get("employment_type"),
        "workplace_arrangement": metadata.get("fields", {}).get("workplace_arrangement", {}).get("value") if isinstance(metadata.get("fields", {}).get("workplace_arrangement"), Mapping) else job.get("workplace_arrangement"),
        "language": metadata.get("fields", {}).get("language", {}).get("value") if isinstance(metadata.get("fields", {}).get("language"), Mapping) else job.get("language"),
        "salary": metadata.get("fields", {}).get("salary", {}).get("value") if isinstance(metadata.get("fields", {}).get("salary"), Mapping) else job.get("salary"),
        "requisition_id": metadata.get("fields", {}).get("requisition_id", {}).get("value") if isinstance(metadata.get("fields", {}).get("requisition_id"), Mapping) else job.get("requisition_id"),
        "posted_at": metadata.get("fields", {}).get("posted_at", {}).get("value") if isinstance(metadata.get("fields", {}).get("posted_at"), Mapping) else job.get("posted_at"),
        "source_status": metadata.get("fields", {}).get("source_status", {}).get("value") if isinstance(metadata.get("fields", {}).get("source_status"), Mapping) else job.get("source_status"),
        "source_posted_at": (timestamps.get("fields", {}).get("source_posted_at", {}) or {}).get("value"),
        "source_timestamp_semantics": timestamps.get("timestamp_semantics") or "unknown_source_timestamp",
        "source_metadata": _stable_value(job.get("source_metadata") or {}),
        "application_url": application.get("resolved_url") or "",
        "application_classification": application.get("classification") or URL_UNKNOWN,
        "source_ats": _text(job.get("source_ats")),
        # A source-channel change is meaningful even when the normalized
        # title/description/location are identical. Query/runtime/observation
        # IDs are intentionally excluded; the stable host/channel is not.
        "source_channel": f"{_text(job.get('source_ats'))}|{_hostname(job.get('source_url') or job.get('url') or job.get('link'))}",
    }
    return _stable_value(fields)


def posted_age_hours(posted_at: Any, *, now: datetime | None = None) -> float | None:
    value = _text(posted_at)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    return round(max(0.0, (current - parsed.astimezone(timezone.utc)).total_seconds() / 3600), 2)


def posted_age_hours_for_job(
    job: Mapping[str, Any],
    *,
    now: datetime | None = None,
    fallback_at: Any = None,
) -> float | None:
    """Compute age from the source anchor, falling back to first capture."""

    timestamps = job.get("source_timestamps") if isinstance(job.get("source_timestamps"), Mapping) else {}
    fields = timestamps.get("fields") if isinstance(timestamps.get("fields"), Mapping) else {}
    posted = fields.get("source_posted_at") if isinstance(fields.get("source_posted_at"), Mapping) else {}
    value = posted.get("value")
    if not value:
        metadata = job.get("normalized_source_metadata") if isinstance(job.get("normalized_source_metadata"), Mapping) else {}
        metadata_timestamps = metadata.get("source_timestamps") if isinstance(metadata.get("source_timestamps"), Mapping) else {}
        metadata_fields = metadata_timestamps.get("fields") if isinstance(metadata_timestamps.get("fields"), Mapping) else {}
        value = (metadata_fields.get("source_posted_at") or {}).get("value")
    return posted_age_hours(value or fallback_at, now=now)


def completeness_rules(*, job: Mapping[str, Any], company: Mapping[str, Any], source: Mapping[str, Any], admin: Mapping[str, Any]) -> dict[str, Any]:
    application = job.get("application_destination") if isinstance(job.get("application_destination"), Mapping) else {}
    metadata_fields = job.get("normalized_source_metadata", {}).get("fields", {}) if isinstance(job.get("normalized_source_metadata"), Mapping) else {}
    department_record = metadata_fields.get("department") if isinstance(metadata_fields, Mapping) else {}
    employment_record = metadata_fields.get("employment_type") if isinstance(metadata_fields, Mapping) else {}
    workplace_record = metadata_fields.get("workplace_arrangement") if isinstance(metadata_fields, Mapping) else {}
    status_record = metadata_fields.get("source_status") if isinstance(metadata_fields, Mapping) else {}
    timestamps = job.get("source_timestamps") if isinstance(job.get("source_timestamps"), Mapping) else {}
    timestamp_state = str(timestamps.get("timestamp_state") or "unknown")
    observed_at = _text(source.get("observed_at") or job.get("observed_at"))

    def state_present(record: Any) -> bool:
        return isinstance(record, Mapping) and canonical_field_state(record.get("state")) in VALUE_FIELD_STATES

    def field_state(record: Any, passed: bool) -> str:
        if passed:
            return "present"
        if isinstance(record, Mapping) and record.get("state"):
            return canonical_field_state(record.get("state"))
        return field_state_for(None, supported=True, observed=True)

    rules = {
        "job": {
            "canonical_job_identity": bool(job.get("canonical_job_id")),
            "title": bool(_text(job.get("title"))),
            "location_state": bool(_text(job.get("location_raw") or job.get("location"))),
            "full_description": bool(_text(job.get("description_text") or job.get("description") or job.get("full_description"))),
            "job_detail_url": bool(_text(job.get("job_detail_url") or job.get("canonical_url") or job.get("source_url"))),
            "application_url_and_classification": bool(application.get("resolved_url")) and application.get("classification") in DIRECT_APPLICATION_CLASSIFICATIONS,
            "employment_type": state_present(employment_record),
            "workplace_arrangement": state_present(workplace_record),
        },
        "company": {
            "canonical_company_identity": bool(company.get("canonical_company_id") or company.get("company_id") or company.get("name")),
            "company_website": bool(_text(company.get("website"))),
            "company_careers_page": bool(_text(company.get("careers_page"))),
            "company_industry": bool(_text(company.get("industry"))),
            "company_size": bool(_text(company.get("company_size"))),
            "company_headquarters": bool(_text(company.get("headquarters"))),
            "company_logo": bool(_text(company.get("logo_url") or company.get("logo"))),
        },
        "source": {
            "source_provenance": bool(source.get("source_observation_ids") or source.get("target_id") or source.get("source_id")),
            "external_source_id": bool(_text(source.get("external_job_id"))),
            "department_state": canonical_field_state(department_record.get("state")) in VALUE_FIELD_STATES if isinstance(department_record, Mapping) else bool(_text(job.get("department"))),
            "source_timestamp_semantics": timestamp_state in {"known", "estimated"} or bool(_text(admin.get("posting_age_anchor_at") or admin.get("first_seen_at"))),
            "source_status": state_present(status_record),
            "freshness": bool(_text(job.get("last_verified_at") or observed_at or job.get("last_seen_at"))),
        },
        "admin": {"publication_state": bool(_text(admin.get("publication_status") or admin.get("review_state") or admin.get("state")))},
    }
    result: dict[str, Any] = {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "rule_version": "field_matrix_v1",
        "report_only": True,
        "rules": {},
        "categories": {},
    }
    all_rules: list[dict[str, Any]] = []
    for category, category_rules in rules.items():
        rows = []
        for name, passed in category_rules.items():
            record = {
                "employment_type": employment_record,
                "workplace_arrangement": workplace_record,
                "department_state": department_record,
                "source_status": status_record,
            }.get(name)
            state = field_state(record, passed)
            row = {
                "name": name,
                "status": "pass" if passed else "warning",
                "state": state,
                "availability": state,
                "blocking": False,
                "report_only": True,
                "rule_version": "field_matrix_v1",
            }
            rows.append(row)
            all_rules.append({"category": category, **row})
        result["categories"][category] = {
            "present": sum(1 for row in rows if row["status"] == "pass"),
            "total": len(rows),
            "missing_rules": [row["name"] for row in rows if row["status"] != "pass"],
            "missing_fields": [row["name"] for row in rows if row["status"] != "pass"],
            "rules": rows,
        }
        result["rules"][category] = rows
    result["all_rules"] = all_rules
    result["overall"] = {
        "present": sum(1 for row in all_rules if row["status"] == "pass"),
        "total": len(all_rules),
        "status": "pass" if all(row["status"] == "pass" for row in all_rules) else "warning",
    }
    result["shadow_validation"] = {
        "mode": "report_only",
        "would_block": any(row["status"] != "pass" and row["name"] in {"canonical_job_identity", "canonical_company_identity", "title", "full_description", "source_provenance"} for row in all_rules),
        "reasons": [f"{row['category']}.{row['name']}" for row in all_rules if row["status"] != "pass"],
    }
    result["denominator"] = {
        "included_rules": [f"{row['category']}.{row['name']}" for row in all_rules],
        "excluded_available_fields": [],
        "state_vocabulary": list(FIELD_STATES),
        "mode": "report_only",
    }
    result["field_state_counts"] = {
        state: sum(1 for row in all_rules if row["state"] == state)
        for state in FIELD_STATES
    }
    result["field_state_descriptions"] = dict(FIELD_STATE_DESCRIPTIONS)
    return result


def normalize_job_for_ingestion(
    job: Mapping[str, Any],
    target: Mapping[str, Any],
    *,
    observed_at: str = "",
) -> dict[str, Any]:
    """Apply the shared contract while retaining all source fields."""

    normalized = dict(job)
    if observed_at:
        normalized["observed_at"] = observed_at
    # Keep an immutable connector payload alongside typed projections. This
    # is the raw escape hatch for fields that a connector exposes but the
    # shared contract does not yet understand.
    normalized.setdefault("source_raw_payload", dict(job))
    employer = canonical_employer_name(target, job)
    raw_employer = _text(job.get("employer_name") or job.get("company") or job.get("display_name"))
    if employer:
        normalized["company"] = employer
        normalized["employer_name"] = employer
    source_ats = _text(job.get("source_ats") or target.get("connector")).casefold()
    description = normalize_description(job.get("description_raw") if job.get("description_raw") not in (None, "") else job.get("full_description") or job.get("description") or "")
    normalized["description_raw"] = description["raw_source"]
    normalized["description_html"] = description["sanitized_html"]
    normalized["description_text"] = description["plain_text"]
    normalized["description_decoding"] = description["decoding"]
    normalized["normalized_source_metadata"] = normalize_source_metadata(
        normalized,
        source_ats=source_ats,
        provenance_url=_text(job.get("source_url") or job.get("url") or target.get("provenance_url")),
    )
    normalized["source_timestamps"] = normalized["normalized_source_metadata"].get("source_timestamps") or normalize_source_timestamps(
        normalized,
        source_ats=source_ats,
        provenance_url=_text(job.get("source_url") or job.get("url") or target.get("provenance_url")),
    )
    application = resolve_application_destination(normalized, target)
    normalized["application_destination"] = application
    normalized["application_method"] = application["application_method"]
    normalized["application_url"] = application["resolved_url"]
    normalized["job_detail_url"] = application["job_detail_url"] or canonicalize_url(_text(job.get("url") or job.get("link") or job.get("source_url")))
    normalized["apply_link"] = application["user_facing_url"] or normalized.get("apply_link") or normalized.get("job_detail_url") or ""
    # ``apply_url`` is the verified destination only.  A detail/listing
    # fallback is retained in ``apply_link`` and ``application_destination``.
    normalized["apply_url"] = application["resolved_url"] or ""
    normalized["unified_mapping"] = map_job_fields(
        normalized,
        observed_at=_text(normalized.get("observed_at") or normalized.get("observation_timestamp")),
        source_observation_id=_text(normalized.get("source_observation_id") or normalized.get("observation_id")),
        source=source_ats or "source_observation",
    )
    normalized["field_provenance"] = normalized["unified_mapping"].get("fields") or {}
    normalized["unified_rule_version"] = UNIFIED_RULE_VERSION
    normalized["quality_warnings"] = list(dict.fromkeys([*(_text(item) for item in application.get("warnings") or [])]))
    if raw_employer and employer and company_name_key(raw_employer) != company_name_key(employer):
        normalized["quality_warnings"].append("source_labeled_employer_name_normalized")
    if normalized["description_decoding"] == "html_entities_decoded_once":
        raw_description = normalized["description_raw"]
        if "&amp;" in raw_description or "&lt;" in raw_description or "&#" in raw_description:
            normalized["quality_warnings"].append("description_contains_html_entities")
    if canonical_field_state(normalized["normalized_source_metadata"]["fields"]["department"].get("state")) not in VALUE_FIELD_STATES:
        normalized["quality_warnings"].append("department_not_available")
    if normalized["source_timestamps"].get("timestamp_state") == "unknown_source_timestamp":
        normalized["quality_warnings"].append("suspicious_posting_timestamp")
    if not any(_text(normalized.get(key)) for key in ("title", "description_text", "location_raw", "job_detail_url")):
        normalized["quality_warnings"].append("volatile_only_posting_version")
    raw_metadata = normalized.get("source_metadata") if isinstance(normalized.get("source_metadata"), Mapping) else {}
    if raw_metadata and not normalized["normalized_source_metadata"].get("fields"):
        normalized["quality_warnings"].append("available_ats_metadata_not_normalized")
    if normalized.get("description_text") and not normalized.get("description_html"):
        normalized["quality_warnings"].append("escaped_description_not_normalized")
    normalized["quality_warnings"] = list(dict.fromkeys(normalized["quality_warnings"]))
    normalized["content_fingerprint"] = stable_content_payload(normalized)
    return normalized


__all__ = [
    "APPLICATION_URL_SCHEMA_VERSION", "DESCRIPTION_SCHEMA_VERSION", "DIRECT_APPLICATION_CLASSIFICATIONS",
    "JOB_DETAIL_CLASSIFICATIONS", "LISTING_CLASSIFICATIONS", "QUALITY_SCHEMA_VERSION", "URL_ATS_APPLICATION",
    "URL_ATS_JOB_DETAIL", "URL_CAREERS_INDEX", "URL_EMPLOYER_APPLICATION", "URL_EMPLOYER_JOB_DETAIL",
    "URL_PORTAL_LISTING", "URL_SEARCH_RESULTS", "URL_UNKNOWN", "canonical_employer_name", "classify_job_url",
    "company_name_key", "completeness_rules", "extract_application_candidates_from_html", "normalize_description",
    "normalize_job_for_ingestion", "normalize_source_metadata", "normalize_source_timestamps", "posted_age_hours",
    "posted_age_hours_for_job", "resolve_application_destination", "source_employer_name", "stable_content_payload",
]
