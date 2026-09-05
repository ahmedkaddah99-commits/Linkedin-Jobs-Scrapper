"""Collect public employer-site jobs into the master jobs folder.

The collector deliberately keeps employer-site rows separate from LinkedIn
rows. It records the career target, provider, discovery path, and the actual
extraction method used for every accepted job.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.connectors.ats_expansions import EXPANSION_CONNECTORS
from backend.connectors.ats_router import detect_ats, fetch_ats_snapshot
from backend.connectors.company_career_discovery import (
    FetchResult,
    canonicalize_url,
    detect_ats_type,
    discover_career_url,
    extract_career_links_from_html,
    requests_fetcher,
)
from backend.config.job_seeker import load_project_dotenv
from backend.connectors.generic_jsonld import fetch_generic_snapshot
from backend.connectors.employer_site_fallbacks import extract_embedded_jobs, fetch_browser_snapshot


DEFAULT_INPUT_CSV = (
    PROJECT_ROOT
    / "Company-Urls"
    / "Master-Company-Url"
    / "cleaned"
    / "Master-Company-Url-canonical_cleaned_linkedin_ids.csv"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "Jobs-Urls" / "master linkedin jobs url"
DEFAULT_TIMEOUT_SECONDS = 25
DEFAULT_LIMIT = 25
NATIVE_ATS_CONNECTORS = {"greenhouse", "lever", *EXPANSION_CONNECTORS}
PLACEHOLDER_IDENTIFIERS = {"", "//", "-", "—", "none", "null", "nan", "n/a"}

EMPLOYER_FIELDS = [
    "canonical_company_id",
    "source_company_name",
    "source_company_url",
    "source_type",
    "source_provider",
    "career_target_url",
    "source_site_url",
    "source_job_id",
    "source_job_url",
    "apply_url_raw",
    "apply_url_canonical",
    "apply_url_source",
    "job_title",
    "title_raw",
    "description_html",
    "description",
    "description_text",
    "location",
    "location_raw",
    "germany_classification",
    "germany_evidence",
    "employment_type",
    "workplace_type",
    "department",
    "date_posted",
    "date_updated",
    "first_seen_at",
    "last_seen_at",
    "discovery_method",
    "extraction_method",
    "extraction_endpoint",
    "ats_tenant",
    "transport",
    "raw_content_hash",
    "collection_status",
]

GERMAN_CITY_ALIASES = {
    "berlin",
    "munich",
    "münchen",
    "hamburg",
    "frankfurt",
    "köln",
    "cologne",
    "stuttgart",
    "düsseldorf",
    "leipzig",
    "dresden",
    "bremen",
    "hannover",
    "nuremberg",
    "nürnberg",
    "bonn",
    "essen",
    "dortmund",
    "heidelberg",
    "karlsruhe",
    "augsburg",
    "wiesbaden",
    "münster",
    "mainz",
    "mannheim",
    "potsdam",
    "saarbrücken",
    "freiburg",
    "regensburg",
    "bochum",
    "lubeck",
    "lübeck",
}
FOREIGN_LOCATION_MARKERS = {
    "london",
    "paris",
    "amsterdam",
    "brussels",
    "zurich",
    "zürich",
    "vienna",
    "wien",
    "milan",
    "madrid",
    "lisbon",
    "dublin",
    "copenhagen",
    "stockholm",
    "warsaw",
    "prague",
    "united kingdom",
    "france",
    "netherlands",
    "switzerland",
    "austria",
}
REMOTE_GERMANY_RE = re.compile(
    r"\b(?:remote|fully remote|work from home)\b[^\n,;|]{0,40}\b(?:germany|deutschland|de)\b|\b(?:germany|deutschland)\b[^\n,;|]{0,40}\bremote\b",
    re.I,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _value_text(value: Any) -> str:
    if isinstance(value, Mapping):
        return _first_value(value, ("name", "value", "location", "addressLocality", "addressCountry"))
    return _text(value)


def _first_value(row: Mapping[str, Any], names: Iterable[str]) -> str:
    for name in names:
        value = _value_text(row.get(name))
        if value:
            return value
    return ""


def _company_identifier(value: Any) -> str:
    identifier = _text(value)
    return "" if identifier.casefold() in PLACEHOLDER_IDENTIFIERS else identifier


def _source_url(raw: str) -> str:
    normalized = canonicalize_url(raw)
    if not normalized:
        return ""
    try:
        parts = urlsplit(normalized)
        host = (parts.hostname or "").casefold().rstrip(".")
        if host.endswith(".linkedin.com") or host == "linkedin.com":
            host = "www.linkedin.com"
        netloc = host
        if parts.port and not (
            (parts.scheme == "https" and parts.port == 443) or (parts.scheme == "http" and parts.port == 80)
        ):
            netloc = f"{host}:{parts.port}"
        path = re.sub(r"/{2,}", "/", parts.path or "/")
        path = "" if path == "/" else path.rstrip("/")
        query = urlencode(
            [
                (key, value)
                for key, value in parse_qsl(parts.query, keep_blank_values=True)
                if key.casefold() not in {"trk", "trackingid", "ref", "source"}
                and not key.casefold().startswith("utm_")
            ]
        )
        return urlunsplit((parts.scheme.casefold(), netloc, path, query, ""))
    except ValueError:
        return ""


@dataclass(frozen=True)
class EmployerCompany:
    canonical_company_id: str
    company_name: str
    website_url: str
    linkedin_company_url: str = ""
    source_row_number: int = 0


@dataclass(frozen=True)
class CollectorLimits:
    max_targets: int = 5
    max_job_links: int = 25
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_pages: int = 20
    max_browser_requests: int = 10
    proxy_url: str = ""


@dataclass
class EmployerCollectionResult:
    company: EmployerCompany
    jobs: list[dict[str, Any]] = field(default_factory=list)
    targets: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    status: str = "discovery_failed"


def load_employer_companies(path: Path) -> tuple[list[EmployerCompany], dict[str, int]]:
    """Load website-bearing company rows with flexible cleaned-CSV columns."""

    companies: list[EmployerCompany] = []
    stats = {"rows_read": 0, "rows_accepted": 0, "rows_rejected": 0}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            stats["rows_read"] += 1
            website = _source_url(_first_value(row, ("website_url", "company_website", "website", "url")))
            if not website:
                stats["rows_rejected"] += 1
                continue
            company = EmployerCompany(
                canonical_company_id=_company_identifier(
                    _first_value(row, ("canonical_CompanyID", "canonical_company_id", "company_id"))
                ),
                company_name=_first_value(row, ("company_name", "name", "company")),
                website_url=website,
                linkedin_company_url=_source_url(_first_value(row, ("linkedin_company_url", "linkedin_url"))),
                source_row_number=row_number,
            )
            companies.append(company)
            stats["rows_accepted"] += 1
    return companies, stats


def classify_germany(location: str) -> tuple[str, str]:
    """Classify a location without treating broad Europe/EMEA as Germany."""

    raw = _text(location)
    lowered = raw.casefold()
    if not raw:
        return "LOCATION_AMBIGUOUS", "location_missing"
    if REMOTE_GERMANY_RE.search(raw):
        return "GERMANY_REMOTE_ELIGIBLE", "explicit_remote_germany"
    germany_signal = bool(
        re.search(r"\b(?:germany|deutschland)\b", lowered)
        or re.search(r"\bde\b", lowered)
        or re.search(r"\b\d{5}\b", raw)
        or any(city in lowered for city in GERMAN_CITY_ALIASES)
    )
    if germany_signal:
        separators = sum(raw.count(token) for token in (";", "|", " / "))
        if (
            separators
            or "," in raw
            and any(marker in lowered for marker in ("remote europe", "remote eu", "emea", "worldwide"))
        ):
            return "MULTI_LOCATION_INCLUDES_GERMANY", "german_location_with_additional_scope"
        return "GERMANY_CONFIRMED", "explicit_country_city_or_postcode_signal"
    if any(marker in lowered for marker in FOREIGN_LOCATION_MARKERS):
        return "NOT_GERMANY", "explicit_foreign_location"
    if re.search(r"\b(?:remote europe|remote eu|emea|worldwide|global)\b", lowered):
        return "LOCATION_AMBIGUOUS", "broad_remote_region_without_germany"
    return "LOCATION_AMBIGUOUS", "no_reliable_germany_signal"


def _description_text(value: Any) -> str:
    raw = str(value or "")
    return _text(BeautifulSoup(raw, "html.parser").get_text(" ", strip=True))


def _provider_tenant(url: str, provider: str) -> str:
    segments = [part for part in urlsplit(url).path.split("/") if part]
    if (
        provider
        in {
            "greenhouse",
            "lever",
            "workday",
            "personio",
            "recruitee",
            "smartrecruiters",
            "ashby",
            "teamtailor",
            "workable",
        }
        and segments
    ):
        return segments[0]
    return ""


def _method_for_job(job: Mapping[str, Any], provider: str) -> str:
    raw_payload = job.get("source_raw_payload")
    if isinstance(raw_payload, Mapping):
        format_name = str(raw_payload.get("format") or "").casefold()
        format_methods = {
            "json-ld": "json_ld",
            "embedded-json": "embedded_json",
            "xhr": "xhr",
            "browser-rendered": "browser_rendered",
            "static-html": "static_html",
        }
        if format_name in format_methods:
            return format_methods[format_name]
    if provider in NATIVE_ATS_CONNECTORS:
        return "ats_api"
    return "static_html"


def _job_key(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    company_id = _text(row.get("canonical_company_id"))
    provider = _text(row.get("source_provider"))
    tenant = _text(row.get("ats_tenant"))
    identity = _text(row.get("source_job_url")) or _text(row.get("source_job_id"))
    return company_id, provider, tenant, identity


def _is_accepted_job_page(job: Mapping[str, Any], provider: str) -> bool:
    title = _first_value(job, ("title", "job_title", "text"))
    if not title:
        return False
    raw_payload = job.get("source_raw_payload")
    format_name = str(raw_payload.get("format") or "").casefold() if isinstance(raw_payload, Mapping) else ""
    if format_name in {"json-ld", "embedded-json", "xhr", "browser-rendered"}:
        return True
    if provider in NATIVE_ATS_CONNECTORS:
        return True
    detail_url = _source_url(
        _first_value(job, ("job_detail_url", "absolute_url", "hostedUrl", "url", "link", "source_url"))
    )
    path = urlsplit(detail_url).path.casefold()
    if path.endswith((".pdf", ".doc", ".docx")):
        return False
    return any(
        token in path
        for token in ("/job/", "/jobs/", "jobdetail", "/position", "/vacan", "/stellen", "requisition", "opening")
    )


def _content_hash(row: Mapping[str, Any]) -> str:
    payload = "|".join(
        _text(row.get(key))
        for key in (
            "job_title",
            "description_text",
            "location_raw",
            "employment_type",
            "workplace_type",
            "apply_url_canonical",
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _annotate_job(
    company: EmployerCompany,
    job: Mapping[str, Any],
    *,
    target_url: str,
    target_source: str,
    provider: str,
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    source_job_url = _source_url(
        _first_value(job, ("job_detail_url", "absolute_url", "hostedUrl", "url", "link", "source_url"))
    )
    apply_raw = _first_value(job, ("application_url", "apply_url", "apply_link"))
    apply_url = _source_url(apply_raw)
    title = _first_value(job, ("title", "job_title", "text"))
    description_html = str(job.get("description_html") or job.get("description") or job.get("full_description") or "")
    location = _first_value(job, ("location_raw", "location"))
    classification, evidence = classify_germany(location)
    row = {field: "" for field in EMPLOYER_FIELDS}
    row.update(
        {
            "canonical_company_id": company.canonical_company_id,
            "source_company_name": company.company_name,
            "source_company_url": company.website_url,
            "source_type": "employer_site",
            "source_provider": provider or "generic_employer_site",
            "career_target_url": target_url,
            "source_site_url": _source_url(str(snapshot.get("resolved_url") or target_url)),
            "source_job_id": _text(job.get("external_job_id") or job.get("job_id") or job.get("id")) or source_job_url,
            "source_job_url": source_job_url,
            "apply_url_raw": apply_raw,
            "apply_url_canonical": apply_url,
            "apply_url_source": "employer_site" if apply_url else "",
            "job_title": title,
            "title_raw": title,
            "description_html": description_html,
            "description": description_html,
            "description_text": _description_text(description_html),
            "location": location,
            "location_raw": location,
            "germany_classification": classification,
            "germany_evidence": evidence,
            "employment_type": _first_value(job, ("employment_type", "employmentType", "commitment")),
            "workplace_type": _first_value(job, ("workplace_type", "workplaceType", "workplace_arrangement")),
            "department": _first_value(job, ("department", "department_name", "team")),
            "date_posted": _first_value(job, ("source_posted_at", "posted_at", "date_posted")),
            "date_updated": _first_value(job, ("source_updated_at", "updated_at", "date_updated")),
            "first_seen_at": utc_now(),
            "last_seen_at": utc_now(),
            "discovery_method": target_source or "career_discovery",
            "extraction_method": _method_for_job(job, provider),
            "extraction_endpoint": _text(job.get("source_endpoint") or snapshot.get("request_url") or target_url),
            "ats_tenant": _provider_tenant(target_url, provider),
            "transport": _text(job.get("source_transport") or snapshot.get("transport") or "direct"),
            "collection_status": "accepted",
        }
    )
    row["raw_content_hash"] = _content_hash(row)
    return row


def _candidate_rows(discovery: Any, limits: CollectorLimits) -> list[Any]:
    candidates = list(getattr(discovery, "candidates", []) or [])
    primary_url = _text(getattr(discovery, "primary_career_url", ""))
    if primary_url and not any(_text(getattr(item, "url", "")) == primary_url for item in candidates):
        candidates.insert(0, SimpleCandidate(primary_url, "career_discovery", ""))
    return candidates[: max(1, int(limits.max_targets))]


def _webshare_proxy_url() -> str:
    explicit = os.getenv("WEBSHARE_PROXY_URL") or os.getenv("WEBSHARE_PROXY") or ""
    if explicit.strip():
        return explicit.strip()
    username = os.getenv("WEBSHARE_PROXY_USERNAME", "").strip()
    password = os.getenv("WEBSHARE_PROXY_PASSWORD", "").strip()
    if not username or not password:
        return ""
    host = os.getenv("WEBSHARE_PROXY_HOST", "p.webshare.io").strip() or "p.webshare.io"
    port = os.getenv("WEBSHARE_PROXY_PORT", "80").strip() or "80"
    return f"http://{quote(username, safe='')}:{quote(password, safe='')}@{host}:{port}"


def _response_needs_proxy(response: Any) -> bool:
    if response is None:
        return True
    try:
        status_code = int(getattr(response, "status_code", 0) or 0)
    except (TypeError, ValueError):
        status_code = 0
    if status_code in {0, 403, 407, 408, 425, 429, 451, 500, 502, 503, 504, 999}:
        return True
    body = str(getattr(response, "text", "") or "")[:12_000].casefold()
    return any(
        marker in body
        for marker in (
            "just a moment",
            "cf-chl-",
            "captcha",
            "access denied",
            "bot verification",
            "enable javascript and cookies",
            "security check",
        )
    )


def _build_network_clients(timeout_seconds: int) -> tuple[Callable[..., FetchResult], Callable[..., Any], str]:
    """Return discovery and response clients with direct-then-Webshare fallback."""

    direct_fetcher = requests_fetcher(timeout_seconds)
    direct_session = requests.Session()
    proxy_url = _webshare_proxy_url()
    proxy_session = requests.Session() if proxy_url else None
    if proxy_session is not None:
        proxy_session.proxies.update({"http": proxy_url, "https": proxy_url})

    def request(url: str, **kwargs: Any) -> Any:
        request_kwargs = dict(kwargs)
        request_kwargs.setdefault("timeout", max(3, int(timeout_seconds)))
        request_kwargs.setdefault("allow_redirects", True)
        method = "POST" if request_kwargs.get("json") is not None else "GET"
        direct_response = None
        direct_error: Exception | None = None
        try:
            direct_response = direct_session.request(method, url, **request_kwargs)
        except requests.RequestException as exc:
            direct_error = exc

        if proxy_session is not None and _response_needs_proxy(direct_response):
            try:
                proxy_response = proxy_session.request(method, url, **request_kwargs)
                proxy_response.transport_used = "webshare"
                request.last_transport = "webshare"
                return proxy_response
            except requests.RequestException:
                pass

        if direct_response is not None:
            direct_response.transport_used = "direct"
            request.last_transport = "direct"
            return direct_response
        request.last_transport = "webshare" if proxy_session is not None else "direct"
        if direct_error is not None:
            raise direct_error
        raise requests.RequestException("request_failed")

    request.last_transport = "direct"

    def fetch(url: str, **_kwargs: Any) -> FetchResult:
        try:
            response = request(url, timeout=timeout_seconds, allow_redirects=True)
            return FetchResult(
                requested_url=url,
                final_url=str(getattr(response, "url", "") or url),
                status_code=int(getattr(response, "status_code", 0) or 0),
                content_type=str(getattr(response, "headers", {}).get("content-type", "") or ""),
                text=str(getattr(response, "text", "") or "")[:1_500_000],
                transport=str(getattr(response, "transport_used", "direct") or "direct"),
            )
        except requests.RequestException as exc:
            return FetchResult(url, url, 0, error=type(exc).__name__, transport=request.last_transport)

    fetch.requester = request
    return fetch, request, proxy_url


def _flush_master_projection(
    output_dir: Path, employer_rows: Iterable[Mapping[str, Any]], metrics: Mapping[str, Any]
) -> None:
    """Persist source catalogs and the combined CSV after every checkpoint."""

    write_employer_outputs(employer_rows, output_dir, metrics=metrics)
    from scripts.build_master_jobs_catalog import build_master_rows, read_csv_rows, write_master_jobs_csv

    linkedin_rows = read_csv_rows(output_dir / "master_linkedin_jobs.csv")
    combined_rows = build_master_rows(linkedin_rows, employer_rows)
    write_master_jobs_csv(combined_rows, output_dir / "master_jobs.csv")


@dataclass(frozen=True)
class SimpleCandidate:
    url: str
    source: str
    ats_type: str = ""


def _jobs_with_source_metadata(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for raw_job in snapshot.get("jobs") or []:
        if not isinstance(raw_job, Mapping):
            continue
        job = dict(raw_job)
        job.setdefault("source_endpoint", _text(snapshot.get("request_url")))
        job.setdefault("source_transport", _text(snapshot.get("transport") or "direct"))
        jobs.append(job)
    return jobs


def collect_company(
    company: EmployerCompany,
    fetcher: Callable[[str], FetchResult],
    limits: CollectorLimits,
) -> EmployerCollectionResult:
    """Discover and fetch one company's public employer job sources."""

    result = EmployerCollectionResult(company=company)
    discovery = discover_career_url(
        homepage_url=company.website_url,
        company_name=company.company_name,
        fetch=fetcher,
        request_timeout_seconds=limits.timeout_seconds,
        shallow_crawl_pages=8,
        use_rendered_fallback=False,
    )
    candidates = _candidate_rows(discovery, limits)
    preloaded_browser_snapshots: dict[str, Mapping[str, Any]] = {}
    rendered_homepage_snapshot: Mapping[str, Any] | None = None
    candidates_from_rendered_discovery = False
    if not candidates:
        homepage_browser = fetch_browser_snapshot(
            company.website_url,
            max_job_links=limits.max_job_links,
            timeout_seconds=limits.timeout_seconds,
            max_requests=limits.max_browser_requests,
            proxy_url=limits.proxy_url,
        )
        rendered_html = str(homepage_browser.get("rendered_html") or "")
        rendered_candidates = extract_career_links_from_html(
            page_url=company.website_url,
            html=rendered_html,
            homepage_url=company.website_url,
            source="browser_rendered_discovery",
        )
        candidates = rendered_candidates[: max(1, int(limits.max_targets))]
        if candidates:
            candidates_from_rendered_discovery = True
            rendered_homepage_snapshot = homepage_browser
            preloaded_browser_snapshots[company.website_url] = homepage_browser
        elif homepage_browser.get("jobs"):
            candidates = [SimpleCandidate(company.website_url, "browser_rendered_discovery", "")]
            candidates_from_rendered_discovery = True
            preloaded_browser_snapshots[company.website_url] = homepage_browser
        else:
            result.failures.append(
                {"stage": "rendered_discovery", "error": str(homepage_browser.get("error") or "not_found")}
            )
    if not candidates:
        result.status = "discovery_failed"
        result.failures.append({"stage": "discovery", "error": getattr(discovery, "crawl_status", "not_found")})
        return result

    seen_keys: set[tuple[str, str, str, str]] = set()
    any_success = False
    for candidate_index, candidate in enumerate(candidates):
        target_url = _source_url(_text(getattr(candidate, "url", "")))
        if not target_url:
            continue
        candidate_source = _text(getattr(candidate, "source", "")) or "career_discovery"
        detected_provider = (
            _text(getattr(candidate, "ats_type", "")) or detect_ats_type(target_url) or detect_ats(target_url) or ""
        )
        provider = detected_provider or "generic_employer_site"
        snapshots: list[Mapping[str, Any]] = []
        direct_page: Any = None
        if candidate_index == 0 and rendered_homepage_snapshot is not None:
            snapshots.append(rendered_homepage_snapshot)
        if detected_provider:
            ats_snapshot = fetch_ats_snapshot(
                target_url,
                detected_provider,
                requester=getattr(fetcher, "requester", None),
                timeout_seconds=limits.timeout_seconds,
                max_pages=limits.max_pages,
                max_requests=limits.max_pages,
                enabled=detected_provider in EXPANSION_CONNECTORS,
            )
            if not ats_snapshot.get("transport"):
                ats_snapshot["transport"] = str(
                    getattr(getattr(fetcher, "requester", None), "last_transport", "direct")
                )
            snapshots.append(ats_snapshot)
            if ats_snapshot.get("jobs"):
                any_success = True
        ats_jobs_found = bool(detected_provider and snapshots and snapshots[0].get("jobs"))
        if not ats_jobs_found:
            direct_page = fetcher(target_url)
        if (not ats_jobs_found or direct_page is not None) and not (
            candidates_from_rendered_discovery and direct_page is None
        ):
            direct_text = str(getattr(direct_page, "text", "") or "") if direct_page else ""
            if direct_text:
                embedded_jobs = extract_embedded_jobs(
                    direct_text,
                    _text(getattr(direct_page, "final_url", "")) or target_url,
                )
                if embedded_jobs:
                    snapshots.append(
                        {
                            "jobs": embedded_jobs,
                            "status": "completed",
                            "request_url": _text(getattr(direct_page, "requested_url", "")) or target_url,
                            "resolved_url": _text(getattr(direct_page, "final_url", "")) or target_url,
                            "transport": _text(getattr(direct_page, "transport", "direct")) or "direct",
                        }
                    )
                    any_success = True
            generic_snapshot = fetch_generic_snapshot(
                target_url,
                requester=getattr(fetcher, "requester", None),
                max_job_links=limits.max_job_links,
                timeout_seconds=limits.timeout_seconds,
            )
            if generic_snapshot.get("jobs") or generic_snapshot.get("status") in {"completed", "incomplete"}:
                snapshots.append(generic_snapshot)
                any_success = True

        accepted_jobs = 0
        for snapshot in snapshots:
            for raw_job in _jobs_with_source_metadata(snapshot):
                if not _is_accepted_job_page(raw_job, provider):
                    continue
                row = _annotate_job(
                    company,
                    raw_job,
                    target_url=target_url,
                    target_source=candidate_source,
                    provider=provider,
                    snapshot=snapshot,
                )
                key = _job_key(row)
                if not key[3] or key in seen_keys:
                    continue
                seen_keys.add(key)
                result.jobs.append(row)
                accepted_jobs += 1

        if not ats_jobs_found and (direct_page is not None or candidates_from_rendered_discovery):
            browser_snapshot = preloaded_browser_snapshots.pop(target_url, None) or fetch_browser_snapshot(
                target_url,
                max_job_links=limits.max_job_links,
                timeout_seconds=limits.timeout_seconds,
                max_requests=limits.max_browser_requests,
                proxy_url=limits.proxy_url,
            )
            snapshots.append(browser_snapshot)
            if browser_snapshot.get("jobs") or browser_snapshot.get("status") == "completed":
                any_success = True
            for raw_job in _jobs_with_source_metadata(browser_snapshot):
                if not _is_accepted_job_page(raw_job, provider):
                    continue
                row = _annotate_job(
                    company,
                    raw_job,
                    target_url=target_url,
                    target_source=candidate_source,
                    provider=provider,
                    snapshot=browser_snapshot,
                )
                key = _job_key(row)
                if not key[3] or key in seen_keys:
                    continue
                seen_keys.add(key)
                result.jobs.append(row)
                accepted_jobs += 1
        final_snapshot = snapshots[-1] if snapshots else {}
        result.targets.append(
            {
                "url": target_url,
                "provider": provider,
                "discovery_method": candidate_source,
                "status": str(final_snapshot.get("status") or "not_attempted"),
                "job_count": accepted_jobs,
                "complete_snapshot": bool(final_snapshot.get("complete_snapshot")),
            }
        )
        for snapshot in snapshots:
            for failure in snapshot.get("observation_failures") or []:
                if isinstance(failure, Mapping):
                    result.failures.append({"stage": "job_detail", **dict(failure)})
            if snapshot.get("error"):
                result.failures.append({"stage": "source", "url": target_url, "error": _text(snapshot.get("error"))})

    if result.jobs:
        result.status = "completed" if not result.failures else "partial"
    elif any_success:
        result.status = "no_jobs"
    else:
        result.status = "source_failed"
    return result


class EmployerState:
    """Small SQLite checkpoint store for resumable employer collection."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path))
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS companies (
                company_key TEXT PRIMARY KEY, payload_json TEXT NOT NULL, status TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
                source_key TEXT PRIMARY KEY, payload_json TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def clear(self) -> None:
        """Remove only this collector's generated checkpoints for a fresh run."""

        with self.connection:
            self.connection.execute("DELETE FROM jobs")
            self.connection.execute("DELETE FROM companies")

    def company_status(self, company: EmployerCompany) -> str:
        key = company.canonical_company_id or company.website_url
        row = self.connection.execute("SELECT status FROM companies WHERE company_key=?", (key,)).fetchone()
        return str(row["status"] if row else "")

    def save(self, result: EmployerCollectionResult) -> None:
        company_key = result.company.canonical_company_id or result.company.website_url
        with self.connection:
            self.connection.execute(
                "INSERT INTO companies(company_key,payload_json,status,error,updated_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(company_key) DO UPDATE SET payload_json=excluded.payload_json,status=excluded.status,error=excluded.error,updated_at=excluded.updated_at",
                (
                    company_key,
                    json.dumps(asdict(result), ensure_ascii=False),
                    result.status,
                    json.dumps(result.failures, ensure_ascii=False),
                    utc_now(),
                ),
            )
            for job in result.jobs:
                key = "|".join(_job_key(job))
                self.connection.execute(
                    "INSERT INTO jobs(source_key,payload_json,updated_at) VALUES(?,?,?) ON CONFLICT(source_key) DO UPDATE SET payload_json=excluded.payload_json,updated_at=excluded.updated_at",
                    (key, json.dumps(job, ensure_ascii=False), utc_now()),
                )

    def jobs(self) -> list[dict[str, Any]]:
        rows = self.connection.execute("SELECT payload_json FROM jobs ORDER BY source_key").fetchall()
        return [json.loads(row["payload_json"]) for row in rows]


def _atomic_write(path: Path, writer: Callable[[Path], None]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        writer(temporary)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_employer_outputs(
    rows: Iterable[Mapping[str, Any]], output_dir: Path, *, metrics: Mapping[str, Any] | None = None
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    row_list = [{field: _text(row.get(field)) for field in EMPLOYER_FIELDS} for row in rows]
    csv_path = output_dir / "master_employer_jobs.csv"
    jsonl_path = output_dir / "master_employer_jobs.jsonl"
    metrics_path = output_dir / "master_employer_jobs_metrics.json"

    def write_csv(path: Path) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=EMPLOYER_FIELDS)
            writer.writeheader()
            writer.writerows(row_list)

    def write_jsonl(path: Path) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for row in row_list:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    _atomic_write(csv_path, write_csv)
    _atomic_write(jsonl_path, write_jsonl)
    _atomic_write(
        metrics_path,
        lambda path: path.write_text(
            json.dumps(dict(metrics or {"jobs": len(row_list)}), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        ),
    )
    return {"csv": csv_path, "jsonl": jsonl_path, "metrics": metrics_path}


def _redacted_config() -> dict[str, str]:
    configured = bool(_webshare_proxy_url())
    return {
        "webshare_configured": "yes" if configured else "no",
        "transport": "direct_then_webshare_fallback" if configured else "direct",
    }


def run_collection(
    *,
    input_csv: Path,
    output_dir: Path,
    limit: int,
    company_id: str = "",
    dry_run: bool = False,
    resume: bool = True,
    max_job_links: int = 25,
    max_pages: int = 20,
    max_browser_requests: int = 10,
    max_targets: int = 25,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    load_project_dotenv()
    companies, input_stats = load_employer_companies(input_csv)
    if company_id:
        companies = [company for company in companies if company.canonical_company_id == company_id]
    selected = companies if limit <= 0 else companies[:limit]
    metrics: dict[str, Any] = {
        "input": input_stats,
        "selected_companies": len(selected),
        "requests": 0,
        "jobs_written": 0,
        "company_statuses": {},
        "extraction_methods": {},
        "source_providers": {},
        "config": _redacted_config(),
        "output_dir": str(output_dir),
        "dry_run": dry_run,
    }
    if dry_run:
        return metrics

    state = EmployerState(output_dir / "master_employer_jobs_state.db")
    if not resume:
        state.clear()
    all_rows: list[dict[str, Any]] = state.jobs()
    fetcher, _requester, proxy_url = _build_network_clients(timeout_seconds)
    metrics["config"]["transport"] = "direct_then_webshare_fallback" if proxy_url else "direct"
    _flush_master_projection(output_dir, all_rows, {**metrics, "jobs_written": len(all_rows)})
    try:
        limits = CollectorLimits(
            max_targets=max(1, int(max_targets)),
            max_job_links=max_job_links,
            max_pages=max(1, int(max_pages)),
            max_browser_requests=max(1, int(max_browser_requests)),
            timeout_seconds=timeout_seconds,
            proxy_url=proxy_url,
        )
        for company in selected:
            if resume and state.company_status(company) in {"completed", "no_jobs"}:
                continue
            try:
                result = collect_company(company, fetcher, limits)
            except Exception as exc:  # keep the full population moving after one provider/site failure
                result = EmployerCollectionResult(
                    company=company,
                    status="collector_error",
                    failures=[{"stage": "company", "error": type(exc).__name__}],
                )
            state.save(result)
            all_rows = state.jobs()
            metrics["company_statuses"][result.status] = metrics["company_statuses"].get(result.status, 0) + 1
            metrics["requests"] += sum(int(target.get("job_count") or 0) + 1 for target in result.targets)
            for row in result.jobs:
                metrics["extraction_methods"][row["extraction_method"]] = (
                    metrics["extraction_methods"].get(row["extraction_method"], 0) + 1
                )
                metrics["source_providers"][row["source_provider"]] = (
                    metrics["source_providers"].get(row["source_provider"], 0) + 1
                )
            metrics["jobs_written"] = len(all_rows)
            _flush_master_projection(output_dir, all_rows, metrics)
            print(
                json.dumps(
                    {
                        "company": company.company_name,
                        "status": result.status,
                        "jobs_total": len(all_rows),
                        "company_jobs": len(result.jobs),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    finally:
        state.close()
    metrics["jobs_written"] = len(all_rows)
    _flush_master_projection(output_dir, all_rows, metrics)
    return metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--company-id", default="")
    parser.add_argument("--max-job-links", type=int, default=25)
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--max-browser-requests", type=int, default=10)
    parser.add_argument("--max-targets", type=int, default=25)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--direct-only",
        action="store_true",
        help="Use direct public requests; retained for explicit operational clarity.",
    )
    parser.add_argument("--full", action="store_true", help="Allow an unbounded company selection.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit <= 0 and not args.full:
        raise SystemExit("Refusing an unbounded run without --full.")
    metrics = run_collection(
        input_csv=args.input_csv,
        output_dir=args.output_dir,
        limit=0 if args.full else args.limit,
        company_id=args.company_id,
        dry_run=args.dry_run,
        resume=args.resume,
        max_job_links=args.max_job_links,
        max_pages=args.max_pages,
        max_browser_requests=args.max_browser_requests,
        max_targets=args.max_targets,
        timeout_seconds=args.timeout,
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CollectorLimits",
    "EMPLOYER_FIELDS",
    "EmployerCollectionResult",
    "EmployerCompany",
    "EmployerState",
    "FetchResult",
    "classify_germany",
    "collect_company",
    "load_employer_companies",
    "run_collection",
    "write_employer_outputs",
]
