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
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager, nullcontext
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
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
EMPLOYER_OUTCOMES = {
    "complete_with_jobs",
    "confirmed_zero",
    "partial",
    "failed",
    "unsupported",
    "blocked",
    "skipped",
}
LEGACY_STATUS_BY_OUTCOME = {
    "complete_with_jobs": "completed",
    "confirmed_zero": "no_jobs",
    "partial": "partial",
    "failed": "source_failed",
    "unsupported": "source_failed",
    "blocked": "source_failed",
    "skipped": "skipped_resume",
}
OUTCOME_BY_LEGACY_STATUS = {
    "completed": "complete_with_jobs",
    "no_jobs": "confirmed_zero",
    "partial": "partial",
    "source_failed": "failed",
    "skipped_resume": "skipped",
    "discovery_failed": "failed",
    "collector_error": "failed",
}

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


class RequestAccounting:
    """Thread-safe counters for actual transport attempts and in-flight work."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._attempts = 0
        self._inflight = 0
        self._peak_inflight = 0
        self._by_kind: dict[str, int] = {}
        self._by_transport: dict[str, int] = {}
        self._by_origin: dict[str, int] = {}

    def start(self, *, kind: str, url: str, transport: str = "direct") -> None:
        origin = (urlsplit(url).hostname or "").casefold() or "unknown"
        with self._lock:
            self._attempts += 1
            self._inflight += 1
            self._peak_inflight = max(self._peak_inflight, self._inflight)
            self._by_kind[kind] = self._by_kind.get(kind, 0) + 1
            self._by_transport[transport] = self._by_transport.get(transport, 0) + 1
            self._by_origin[origin] = self._by_origin.get(origin, 0) + 1

    def finish(self) -> None:
        with self._lock:
            self._inflight = max(0, self._inflight - 1)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            by_kind = dict(sorted(self._by_kind.items()))
            by_transport = dict(sorted(self._by_transport.items()))
            return {
                "total_attempts": self._attempts,
                "inflight": self._inflight,
                "peak_inflight": self._peak_inflight,
                "fallback_attempts": by_transport.get("webshare", 0),
                "browser_navigations": by_kind.get("browser_navigation", 0),
                "by_kind": by_kind,
                "by_transport": by_transport,
                "by_origin": dict(sorted(self._by_origin.items())),
            }


class TransportGate:
    """Bound HTTP/browser/account/origin work shared by all company workers."""

    def __init__(
        self,
        *,
        accounting: RequestAccounting,
        http_concurrency: int = 4,
        browser_concurrency: int = 1,
        account_concurrency: int = 4,
        per_origin_concurrency: int = 1,
    ) -> None:
        self.accounting = accounting
        self.http_semaphore = threading.BoundedSemaphore(max(1, int(http_concurrency)))
        self.browser_semaphore = threading.BoundedSemaphore(max(1, int(browser_concurrency)))
        self.account_semaphore = threading.BoundedSemaphore(max(1, int(account_concurrency)))
        self.per_origin_concurrency = max(1, int(per_origin_concurrency))
        self._origin_lock = threading.Lock()
        self._origin_semaphores: dict[str, threading.BoundedSemaphore] = {}

    def _origin_semaphore(self, url: str) -> threading.BoundedSemaphore:
        origin = (urlsplit(url).hostname or "").casefold() or "unknown"
        with self._origin_lock:
            semaphore = self._origin_semaphores.get(origin)
            if semaphore is None:
                semaphore = threading.BoundedSemaphore(self.per_origin_concurrency)
                self._origin_semaphores[origin] = semaphore
            return semaphore

    @contextmanager
    def http_request(self, url: str, *, transport: str = "direct") -> Iterable[None]:
        origin = self._origin_semaphore(url)
        semaphores = (self.account_semaphore, self.http_semaphore, origin)
        for semaphore in semaphores:
            semaphore.acquire()
        self.accounting.start(kind="http_attempt", url=url, transport=transport)
        try:
            yield
        finally:
            self.accounting.finish()
            for semaphore in reversed(semaphores):
                semaphore.release()

    @contextmanager
    def browser_process(self, url: str) -> Iterable[None]:
        del url
        self.browser_semaphore.acquire()
        try:
            yield
        finally:
            self.browser_semaphore.release()

    @contextmanager
    def browser_request(self, url: str, kind: str = "browser_request") -> Iterable[None]:
        origin = self._origin_semaphore(url)
        semaphores = (self.account_semaphore, origin)
        for semaphore in semaphores:
            semaphore.acquire()
        self.accounting.start(kind=kind, url=url, transport="browser")
        try:
            yield
        finally:
            self.accounting.finish()
            for semaphore in reversed(semaphores):
                semaphore.release()


@dataclass(frozen=True)
class CollectorLimits:
    max_targets: int = 5
    max_job_links: int = 25
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_pages: int = 20
    max_browser_requests: int = 10
    proxy_url: str = ""
    transport_gate: TransportGate | None = field(default=None, compare=False, repr=False)


@dataclass
class EmployerCollectionResult:
    company: EmployerCompany
    jobs: list[dict[str, Any]] = field(default_factory=list)
    targets: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    status: str = "discovery_failed"
    outcome: str = ""
    coverage: dict[str, Any] = field(default_factory=dict)

    def resolved_outcome(self) -> str:
        outcome = _text(self.outcome).casefold()
        if outcome in EMPLOYER_OUTCOMES:
            return outcome
        return OUTCOME_BY_LEGACY_STATUS.get(self.status, "failed")


def load_employer_companies(path: Path) -> tuple[list[EmployerCompany], dict[str, int]]:
    """Load website-bearing company rows with flexible cleaned-CSV columns."""

    companies: list[EmployerCompany] = []
    stats = {"rows_read": 0, "rows_accepted": 0, "rows_rejected": 0}
    seen_keys: set[tuple[str, str]] = set()
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
            identity_key = (company.canonical_company_id, company.website_url)
            if identity_key in seen_keys:
                stats["duplicate_rows"] = stats.get("duplicate_rows", 0) + 1
                continue
            seen_keys.add(identity_key)
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


def _build_network_clients(
    timeout_seconds: int,
    *,
    transport_gate: TransportGate | None = None,
) -> tuple[Callable[..., FetchResult], Callable[..., Any], str]:
    """Return discovery and response clients with direct-then-Webshare fallback."""

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

        def attempt(session: requests.Session, transport: str) -> Any:
            guard = (
                transport_gate.http_request(url, transport=transport)
                if transport_gate is not None
                else nullcontext()
            )
            with guard:
                return session.request(method, url, **request_kwargs)

        try:
            direct_response = attempt(direct_session, "direct")
        except requests.RequestException as exc:
            direct_error = exc

        if proxy_session is not None and _response_needs_proxy(direct_response):
            try:
                proxy_response = attempt(proxy_session, "webshare")
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

    def close() -> None:
        direct_session.close()
        if proxy_session is not None:
            proxy_session.close()

    request.close = close

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
    fetch.close = close
    return fetch, request, proxy_url


def _flush_master_projection(
    output_dir: Path, employer_rows: Iterable[Mapping[str, Any]], metrics: Mapping[str, Any]
) -> None:
    """Compatibility helper for callers that explicitly request an employer snapshot."""

    write_employer_outputs(employer_rows, output_dir, metrics=metrics)


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


def _snapshot_status(snapshot: Mapping[str, Any]) -> str:
    return _text(snapshot.get("status") or "not_attempted").casefold()


def _snapshot_is_complete(snapshot: Mapping[str, Any], *, source_kind: str = "generic") -> bool:
    """Require explicit pagination/completeness evidence before suppressing fallback."""

    if source_kind == "discovery":
        return False
    status = _snapshot_status(snapshot)
    if status in {"failed", "error", "incomplete", "partial", "blocked", "challenge", "unsupported"}:
        return False
    if snapshot.get("error") or snapshot.get("observation_failures"):
        return False
    if snapshot.get("complete_snapshot") is True or snapshot.get("pagination_complete") is True:
        return True
    # Older native ATS adapters returned a completed snapshot before the explicit
    # pagination fields were added. Keep that compatibility only for native ATS
    # responses; generic HTTP/JSON responses must carry explicit evidence.
    return source_kind == "ats" and status in {"completed", "complete", "success"}


def _snapshot_outcome(snapshot: Mapping[str, Any], *, source_kind: str = "generic") -> str:
    status = _snapshot_status(snapshot)
    error = _text(snapshot.get("error")).casefold()
    if status in {"blocked", "challenge", "captcha"} or any(
        marker in error for marker in ("captcha", "challenge", "bot", "access_denied", "security")
    ):
        return "blocked"
    if status in {"unsupported", "disabled", "invalid_target"}:
        return "unsupported"
    if status in {"incomplete", "partial"} or snapshot.get("observation_failures"):
        return "partial"
    if status in {"failed", "error", "browser_failed", "browser_unavailable"} or error:
        return "failed"
    if _snapshot_is_complete(snapshot, source_kind=source_kind):
        return "complete_with_jobs" if snapshot.get("jobs") else "confirmed_zero"
    if status in {"completed", "complete", "success"}:
        return "partial" if snapshot.get("jobs") or snapshot.get("credible_evidence") else "failed"
    return "failed"


def _snapshot_request_count(snapshot: Mapping[str, Any]) -> int:
    explicit = snapshot.get("requests_made")
    if explicit is not None:
        try:
            return max(0, int(explicit))
        except (TypeError, ValueError):
            pass
    request_log = snapshot.get("request_log")
    return len(request_log) if isinstance(request_log, list) else 0


def _coverage_target(
    *,
    target_url: str,
    provider: str,
    discovery_method: str,
    snapshots: list[Mapping[str, Any]],
    accepted_jobs: int,
    extraction_methods: set[str],
) -> tuple[dict[str, Any], list[str]]:
    coverage_snapshots = [
        snapshot for snapshot in snapshots if _text(snapshot.get("_source_kind")) != "discovery"
    ]
    snapshot_outcomes = [
        _snapshot_outcome(
            snapshot,
            source_kind=_text(snapshot.get("_source_kind"))
            or ("ats" if provider in NATIVE_ATS_CONNECTORS else "generic"),
        )
        for snapshot in coverage_snapshots
    ]
    observed_jobs = sum(len(_jobs_with_source_metadata(snapshot)) for snapshot in coverage_snapshots)
    request_count = sum(_snapshot_request_count(snapshot) for snapshot in coverage_snapshots)
    pages_fetched = sum(max(0, int(snapshot.get("pages_fetched") or 0)) for snapshot in coverage_snapshots)
    detail_failures = sum(len(snapshot.get("observation_failures") or []) for snapshot in coverage_snapshots)
    complete = any(
        _snapshot_is_complete(
            snapshot,
            source_kind=_text(snapshot.get("_source_kind"))
            or ("ats" if provider in NATIVE_ATS_CONNECTORS else "generic"),
        )
        for snapshot in coverage_snapshots
    )
    pagination_complete = any(bool(snapshot.get("pagination_complete")) for snapshot in snapshots)
    credible = any(bool(snapshot.get("credible_evidence")) for snapshot in snapshots)
    stop_reason = next(
        (
            _text(snapshot.get("stop_reason"))
            for snapshot in reversed(coverage_snapshots)
            if _text(snapshot.get("stop_reason"))
        ),
        snapshot_outcomes[-1] if snapshot_outcomes else "not_attempted",
    )
    if accepted_jobs:
        target_outcome = "complete_with_jobs" if complete and not any(
            outcome in {"partial", "failed", "blocked"} for outcome in snapshot_outcomes
        ) else "partial"
    elif "blocked" in snapshot_outcomes:
        target_outcome = "blocked"
    elif "unsupported" in snapshot_outcomes and not any(
        outcome in {"confirmed_zero", "complete_with_jobs", "partial"} for outcome in snapshot_outcomes
    ):
        target_outcome = "unsupported"
    elif "confirmed_zero" in snapshot_outcomes and not any(
        outcome in {"partial", "failed", "blocked"} for outcome in snapshot_outcomes
    ):
        target_outcome = "confirmed_zero"
    elif "partial" in snapshot_outcomes:
        target_outcome = "partial"
    else:
        target_outcome = "failed"
    target = {
        "url": target_url,
        "provider": provider,
        "detected_ats": provider if provider in NATIVE_ATS_CONNECTORS else "",
        "discovery_method": discovery_method,
        "status": target_outcome,
        "job_count": accepted_jobs,
        "counts": {
            "jobs_observed": observed_jobs,
            "jobs_accepted": accepted_jobs,
            "requests": request_count,
            "pages": pages_fetched,
            "detail_failures": detail_failures,
        },
        "extraction_methods": sorted(extraction_methods),
        "stop_reason": stop_reason,
        "complete_snapshot": complete,
        "completeness_evidence": {
            "complete_snapshot": complete,
            "pagination_complete": pagination_complete,
            "credible_evidence": credible,
            "snapshot_statuses": [_snapshot_status(snapshot) for snapshot in coverage_snapshots],
        },
    }
    return target, snapshot_outcomes


def _finalize_coverage(result: EmployerCollectionResult, target_outcomes: list[str]) -> None:
    if result.jobs:
        outcome = "partial" if result.failures or any(
            value in {"partial", "failed", "blocked", "unsupported"} for value in target_outcomes
        ) else "complete_with_jobs"
    elif "blocked" in target_outcomes:
        outcome = "blocked"
    elif "unsupported" in target_outcomes and not any(
        value in {"confirmed_zero", "complete_with_jobs", "partial", "blocked"}
        for value in target_outcomes
    ):
        outcome = "unsupported"
    elif "confirmed_zero" in target_outcomes and not any(
        value in {"partial", "failed", "blocked", "unsupported"} for value in target_outcomes
    ):
        outcome = "confirmed_zero"
    elif "partial" in target_outcomes:
        outcome = "partial"
    else:
        outcome = "failed"
    result.outcome = outcome
    result.status = LEGACY_STATUS_BY_OUTCOME[outcome]
    result.coverage = {
        "outcome": outcome,
        "detected_ats": sorted(
            {
                _text(target.get("detected_ats"))
                for target in result.targets
                if _text(target.get("detected_ats"))
            }
        ),
        "discovered_targets": [target.get("url", "") for target in result.targets],
        "extraction_methods": sorted(
            {
                method
                for target in result.targets
                for method in target.get("extraction_methods", [])
                if method
            }
        ),
        "counts": {
            "targets": len(result.targets),
            "jobs_accepted": len(result.jobs),
            "requests": sum(int(target.get("counts", {}).get("requests") or 0) for target in result.targets),
            "failures": len(result.failures),
        },
        "stop_reason": (
            "collection_completed" if outcome in {"complete_with_jobs", "confirmed_zero"} else "collection_uncertain"
        ),
        "completeness_evidence": {
            "complete_snapshot": all(
                bool(target.get("complete_snapshot")) for target in result.targets
            ) if result.targets else False,
            "targets": [target.get("completeness_evidence", {}) for target in result.targets],
        },
        "recheck_policy": {
            "recheck_required": outcome in {"confirmed_zero", "unsupported", "blocked", "partial", "failed"},
            "bounded_recovery": True,
            "reason": (
                "verified_complete_snapshot" if outcome == "confirmed_zero" else "coverage_requires_revalidation"
            ),
        },
    }


def collect_company(
    company: EmployerCompany,
    fetcher: Callable[[str], FetchResult],
    limits: CollectorLimits,
) -> EmployerCollectionResult:
    """Discover and fetch one company's public employer job sources."""

    result = EmployerCollectionResult(company=company)

    def browser_snapshot(url: str) -> Mapping[str, Any]:
        browser_kwargs: dict[str, Any] = {
            "max_job_links": limits.max_job_links,
            "timeout_seconds": limits.timeout_seconds,
            "max_requests": limits.max_browser_requests,
            "proxy_url": limits.proxy_url,
        }
        if limits.transport_gate is not None:
            browser_kwargs["request_guard"] = limits.transport_gate.browser_request
            browser_kwargs["browser_process_guard"] = limits.transport_gate.browser_process
        return fetch_browser_snapshot(url, **browser_kwargs)

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
        homepage_browser = browser_snapshot(company.website_url)
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
            rendered_homepage_snapshot = {**homepage_browser, "_source_kind": "discovery"}
            preloaded_browser_snapshots[company.website_url] = {**homepage_browser, "_source_kind": "browser"}
        elif homepage_browser.get("jobs"):
            candidates = [SimpleCandidate(company.website_url, "browser_rendered_discovery", "")]
            candidates_from_rendered_discovery = True
            preloaded_browser_snapshots[company.website_url] = {**homepage_browser, "_source_kind": "browser"}
        else:
            result.failures.append(
                {"stage": "rendered_discovery", "error": str(homepage_browser.get("error") or "not_found")}
            )
    if not candidates:
        result.failures.append({"stage": "discovery", "error": getattr(discovery, "crawl_status", "not_found")})
        _finalize_coverage(result, [])
        # Retain the historical checkpoint status while exposing the canonical
        # outcome in coverage/outcome for new consumers.
        result.status = "discovery_failed"
        return result

    seen_keys: set[tuple[str, str, str, str]] = set()
    target_outcomes: list[str] = []
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
            ats_snapshot = dict(fetch_ats_snapshot(
                target_url,
                detected_provider,
                requester=getattr(fetcher, "requester", None),
                timeout_seconds=limits.timeout_seconds,
                max_pages=limits.max_pages,
                max_requests=limits.max_pages,
                enabled=detected_provider in EXPANSION_CONNECTORS,
            ))
            ats_snapshot.setdefault("_source_kind", "ats")
            if not ats_snapshot.get("transport"):
                ats_snapshot["transport"] = str(
                    getattr(getattr(fetcher, "requester", None), "last_transport", "direct")
                )
            snapshots.append(ats_snapshot)
        ats_snapshot_complete = bool(
            detected_provider
            and snapshots
            and _snapshot_is_complete(snapshots[-1], source_kind="ats")
        )
        if not ats_snapshot_complete:
            direct_page = fetcher(target_url)
        if (not ats_snapshot_complete or direct_page is not None) and not (
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
                            "complete_snapshot": True,
                            "pagination_complete": True,
                            "credible_evidence": True,
                            "stop_reason": "embedded_payload_complete",
                            "request_url": _text(getattr(direct_page, "requested_url", "")) or target_url,
                            "resolved_url": _text(getattr(direct_page, "final_url", "")) or target_url,
                            "transport": _text(getattr(direct_page, "transport", "direct")) or "direct",
                        }
                    )
            generic_snapshot = dict(fetch_generic_snapshot(
                target_url,
                requester=getattr(fetcher, "requester", None),
                max_job_links=limits.max_job_links,
                timeout_seconds=limits.timeout_seconds,
            ))
            generic_snapshot.setdefault("_source_kind", "generic")
            if generic_snapshot:
                snapshots.append(generic_snapshot)

        accepted_jobs = 0
        extraction_methods: set[str] = set()
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
                extraction_methods.add(_text(row.get("extraction_method")))

        complete_snapshot_available = any(
            _snapshot_is_complete(
                snapshot,
                source_kind=_text(snapshot.get("_source_kind")) or "generic",
            )
            for snapshot in snapshots
        )
        if not complete_snapshot_available and (direct_page is not None or candidates_from_rendered_discovery):
            rendered_snapshot = dict(preloaded_browser_snapshots.pop(target_url, None) or browser_snapshot(target_url))
            rendered_snapshot.setdefault("_source_kind", "browser")
            snapshots.append(rendered_snapshot)
            for raw_job in _jobs_with_source_metadata(rendered_snapshot):
                if not _is_accepted_job_page(raw_job, provider):
                    continue
                row = _annotate_job(
                    company,
                    raw_job,
                    target_url=target_url,
                    target_source=candidate_source,
                    provider=provider,
                    snapshot=rendered_snapshot,
                )
                key = _job_key(row)
                if not key[3] or key in seen_keys:
                    continue
                seen_keys.add(key)
                result.jobs.append(row)
                accepted_jobs += 1
                extraction_methods.add(_text(row.get("extraction_method")))
        target, _snapshot_outcomes = _coverage_target(
            target_url=target_url,
            provider=provider,
            discovery_method=candidate_source,
            snapshots=snapshots,
            accepted_jobs=accepted_jobs,
            extraction_methods=extraction_methods,
        )
        result.targets.append(target)
        target_outcomes.append(target["status"])
        for snapshot in snapshots:
            for failure in snapshot.get("observation_failures") or []:
                if isinstance(failure, Mapping):
                    result.failures.append({"stage": "job_detail", **dict(failure)})
            if snapshot.get("error"):
                result.failures.append({"stage": "source", "url": target_url, "error": _text(snapshot.get("error"))})

    _finalize_coverage(result, target_outcomes)
    return result


class EmployerState:
    """Small SQLite checkpoint store for resumable employer collection."""

    def __init__(self, path: Path, *, create: bool = True) -> None:
        if create:
            path.parent.mkdir(parents=True, exist_ok=True)
        elif not path.is_file():
            raise FileNotFoundError(f"Employer state database not found: {path}")
        self.connection = sqlite3.connect(str(path))
        self.connection.row_factory = sqlite3.Row
        if create:
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
        else:
            self._validate_existing_schema(path)

    @classmethod
    def open_existing(cls, path: Path) -> "EmployerState":
        """Open an existing state database without creating or migrating it."""

        return cls(path, create=False)

    def _validate_existing_schema(self, path: Path) -> None:
        required = {"companies", "jobs"}
        tables = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = sorted(required - tables)
        if missing:
            self.close()
            raise ValueError(f"Employer state database is missing tables {missing}: {path}")
        for table, columns in {
            "companies": {"company_key", "payload_json", "status", "error", "updated_at"},
            "jobs": {"source_key", "payload_json", "updated_at"},
        }.items():
            actual = {
                str(row[1]) for row in self.connection.execute(f"PRAGMA table_info({table})").fetchall()
            }
            missing_columns = sorted(columns - actual)
            if missing_columns:
                self.close()
                raise ValueError(f"Employer state table {table} is missing columns {missing_columns}: {path}")

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

    def company_payload(self, company: EmployerCompany) -> dict[str, Any] | None:
        key = company.canonical_company_id or company.website_url
        row = self.connection.execute("SELECT payload_json FROM companies WHERE company_key=?", (key,)).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def should_skip_resume(self, company: EmployerCompany) -> bool:
        """Skip only a completed positive checkpoint; negative/uncertain rows recheck."""

        return self.company_status(company) == "completed"

    def coverage_audit(self) -> dict[str, Any]:
        """Return a read-only disposition report for existing company checkpoints."""

        status_counts: dict[str, int] = {}
        outcome_counts: dict[str, int] = {}
        dispositions: dict[str, int] = {}
        rows = self.connection.execute("SELECT status, payload_json FROM companies ORDER BY company_key")
        for row in rows:
            status = str(row["status"] or "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {}
            coverage = payload.get("coverage") if isinstance(payload, dict) else None
            outcome = _text(
                coverage.get("outcome") if isinstance(coverage, Mapping) else payload.get("outcome")
                if isinstance(payload, dict)
                else ""
            ) or OUTCOME_BY_LEGACY_STATUS.get(status, "failed")
            outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
            disposition = "recheck_required" if status != "completed" or not isinstance(coverage, Mapping) else "covered"
            dispositions[disposition] = dispositions.get(disposition, 0) + 1
        return {
            "companies": sum(status_counts.values()),
            "status_counts": status_counts,
            "outcome_counts": outcome_counts,
            "recheck_disposition": dispositions,
            "legacy_unverified_negative_rows": sum(
                count for status, count in status_counts.items() if status in {"no_jobs", "discovery_failed", "partial", "source_failed"}
            ),
        }

    def save(self, result: EmployerCollectionResult) -> None:
        company_key = result.company.canonical_company_id or result.company.website_url
        result.outcome = result.resolved_outcome()
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
        return list(self.iter_jobs())

    def iter_jobs(self) -> Iterable[dict[str, Any]]:
        """Yield persisted jobs without materializing the complete jobs table."""

        cursor = self.connection.execute("SELECT payload_json FROM jobs ORDER BY source_key")
        for row in cursor:
            yield json.loads(row["payload_json"])

    def job_count(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) AS count FROM jobs").fetchone()
        return int(row["count"] if row else 0)


def _atomic_write(path: Path, writer: Callable[[Path], None]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        writer(temporary)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _temporary_path(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
    )
    temporary = Path(handle.name)
    handle.close()
    return temporary


def _cleanup_temporary_paths(paths: Iterable[Path]) -> None:
    for path in paths:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _write_employer_rows_temps(
    rows: Iterable[Mapping[str, Any]], csv_path: Path, jsonl_path: Path
) -> int:
    row_count = 0
    with (
        csv_path.open("w", encoding="utf-8-sig", newline="") as csv_handle,
        jsonl_path.open("w", encoding="utf-8") as jsonl_handle,
    ):
        writer = csv.DictWriter(csv_handle, fieldnames=EMPLOYER_FIELDS)
        writer.writeheader()
        for row in rows:
            normalized = {field: _text(row.get(field)) for field in EMPLOYER_FIELDS}
            writer.writerow(normalized)
            jsonl_handle.write(json.dumps(normalized, ensure_ascii=False) + "\n")
            row_count += 1
    return row_count


def _write_metrics_temp(path: Path, metrics: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(dict(metrics), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _validate_employer_temps(
    csv_path: Path, jsonl_path: Path, metrics_path: Path, expected_rows: int
) -> None:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != EMPLOYER_FIELDS:
            raise ValueError(f"employer CSV header mismatch in {csv_path}")
        csv_rows = 0
        for row in reader:
            if None in row:
                raise ValueError(f"employer CSV contains malformed row {csv_rows + 1}")
            csv_rows += 1
    if csv_rows != expected_rows:
        raise ValueError(f"employer CSV row count mismatch: expected {expected_rows}, got {csv_rows}")

    with jsonl_path.open("r", encoding="utf-8") as handle:
        jsonl_rows = 0
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"employer JSONL row {line_number} is not an object")
            jsonl_rows += 1
    if jsonl_rows != expected_rows:
        raise ValueError(f"employer JSONL row count mismatch: expected {expected_rows}, got {jsonl_rows}")

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    if not isinstance(metrics, dict) or int(metrics.get("exported_jobs", -1)) != expected_rows:
        raise ValueError(f"employer metrics row count mismatch in {metrics_path}")


def _promote_temporary_outputs(temporary_to_target: Mapping[Path, Path]) -> None:
    """Promote validated files and restore the previous generation if interrupted."""

    backups: dict[Path, Path] = {}
    promoted: list[Path] = []
    try:
        for temporary, target in temporary_to_target.items():
            if target.exists():
                backup = _temporary_path(target)
                backup.unlink()
                os.replace(target, backup)
                backups[target] = backup
            os.replace(temporary, target)
            promoted.append(target)
    except BaseException:
        for target in reversed(promoted):
            try:
                target.unlink()
            except FileNotFoundError:
                pass
        for target, backup in backups.items():
            if backup.exists():
                os.replace(backup, target)
        raise
    finally:
        _cleanup_temporary_paths(backups.values())


def write_employer_outputs(
    rows: Iterable[Mapping[str, Any]], output_dir: Path, *, metrics: Mapping[str, Any] | None = None
) -> dict[str, Path]:
    targets = {
        "csv": output_dir / "master_employer_jobs.csv",
        "jsonl": output_dir / "master_employer_jobs.jsonl",
        "metrics": output_dir / "master_employer_jobs_metrics.json",
    }
    temporary = {key: _temporary_path(path) for key, path in targets.items()}
    try:
        row_count = _write_employer_rows_temps(rows, temporary["csv"], temporary["jsonl"])
        payload = dict(metrics or {})
        payload.setdefault("jobs", row_count)
        payload["exported_jobs"] = row_count
        _write_metrics_temp(temporary["metrics"], payload)
        _validate_employer_temps(
            temporary["csv"], temporary["jsonl"], temporary["metrics"], row_count
        )
        _promote_temporary_outputs({temporary[key]: targets[key] for key in targets})
        return targets
    finally:
        _cleanup_temporary_paths(temporary.values())


def export_employer_catalog_from_state(
    state: EmployerState,
    output_dir: Path,
    *,
    metrics: Mapping[str, Any],
) -> dict[str, Any]:
    """Build and validate only employer artifacts from authoritative state."""

    generation_id = str(metrics.get("generation_id") or "").strip() or (
        f"employer-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid.uuid4().hex[:12]}"
    )
    export_metrics = dict(metrics)
    export_metrics.update(
        {
            "generation_id": generation_id,
            "source": "employer_state",
            "final_export_completed": True,
        }
    )
    outputs = write_employer_outputs(state.iter_jobs(), output_dir, metrics=export_metrics)
    exported_jobs = int(export_metrics.get("persisted_jobs", state.job_count()) or 0)
    return {
        "exported_jobs": exported_jobs,
        "employer_generation_id": generation_id,
        "employer_export_completed": True,
        "final_export_completed": True,
        "outputs": {
            "employer_csv": str(outputs["csv"]),
            "employer_jsonl": str(outputs["jsonl"]),
            "employer_metrics": str(outputs["metrics"]),
        },
    }


def export_catalogs_from_state(
    state: EmployerState,
    output_dir: Path,
    *,
    metrics: Mapping[str, Any],
    require_linkedin_csv: bool = False,
) -> dict[str, Any]:
    """Compatibility wrapper for the independent employer export.

    ``require_linkedin_csv`` is retained for callers of the pre-RC-007 API, but
    is intentionally ignored: employer artifacts never depend on LinkedIn.
    The combined projection belongs to ``build_master_jobs_catalog.py``.
    """

    del require_linkedin_csv
    return export_employer_catalog_from_state(state, output_dir, metrics=metrics)


def _redacted_config() -> dict[str, str]:
    configured = bool(_webshare_proxy_url())
    return {
        "webshare_configured": "yes" if configured else "no",
        "transport": "direct_then_webshare_fallback" if configured else "direct",
    }


def _collect_company_worker(company: EmployerCompany, limits: CollectorLimits) -> EmployerCollectionResult:
    """Collect one company with a worker-local session and shared transport gates."""

    fetcher: Any = None
    try:
        fetcher, _requester, _proxy_url = _build_network_clients(
            limits.timeout_seconds,
            transport_gate=limits.transport_gate,
        )
        return collect_company(company, fetcher, limits)
    except Exception as exc:  # keep the full population moving after one worker/provider failure
        result = EmployerCollectionResult(
            company=company,
            status="collector_error",
            failures=[{"stage": "company", "error": type(exc).__name__}],
        )
        _finalize_coverage(result, [])
        result.status = "collector_error"
        return result
    finally:
        close = getattr(fetcher, "close", None)
        if callable(close):
            close()


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
    recheck_budget: int = 25,
    company_concurrency: int = 2,
    max_pending: int = 4,
    http_concurrency: int = 4,
    browser_concurrency: int = 1,
    account_concurrency: int = 4,
    per_origin_concurrency: int = 1,
) -> dict[str, Any]:
    load_project_dotenv()
    companies, input_stats = load_employer_companies(input_csv)
    if company_id:
        companies = [company for company in companies if company.canonical_company_id == company_id]
    selected = companies if limit <= 0 else companies[:limit]
    accounting = RequestAccounting()
    metrics: dict[str, Any] = {
        "input": input_stats,
        "selected_companies": len(selected),
        "requests": 0,
        "jobs_written": 0,
        "persisted_jobs": 0,
        "exported_jobs": 0,
        "companies_processed": 0,
        "companies_skipped_resume": 0,
        "rechecks_attempted": 0,
        "rechecks_skipped_budget": 0,
        "recheck_budget": max(0, int(recheck_budget)),
        "request_accounting": accounting.snapshot(),
        "concurrency": {
            "company_workers": max(1, min(32, int(company_concurrency))),
            "max_pending": max(1, min(100, int(max_pending))),
            "http_concurrency": max(1, int(http_concurrency)),
            "browser_concurrency": max(1, int(browser_concurrency)),
            "account_concurrency": max(1, int(account_concurrency)),
            "per_origin_concurrency": max(1, int(per_origin_concurrency)),
        },
        "final_export_completed": False,
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
    transport_gate = TransportGate(
        accounting=accounting,
        http_concurrency=http_concurrency,
        browser_concurrency=browser_concurrency,
        account_concurrency=account_concurrency,
        per_origin_concurrency=per_origin_concurrency,
    )
    worker_count = metrics["concurrency"]["company_workers"]
    pending_limit = max(worker_count, metrics["concurrency"]["max_pending"])
    metrics["concurrency"]["max_pending"] = pending_limit
    try:
        if not resume:
            state.clear()
        proxy_url = _webshare_proxy_url()
        metrics["config"]["transport"] = "direct_then_webshare_fallback" if proxy_url else "direct"
        limits = CollectorLimits(
            max_targets=max(1, int(max_targets)),
            max_job_links=max_job_links,
            max_pages=max(1, int(max_pages)),
            max_browser_requests=max(1, int(max_browser_requests)),
            timeout_seconds=timeout_seconds,
            proxy_url=proxy_url,
            transport_gate=transport_gate,
        )

        work: list[EmployerCompany] = []
        for company in selected:
            prior_status = state.company_status(company)
            if resume and state.should_skip_resume(company):
                metrics["companies_skipped_resume"] += 1
                print(
                    json.dumps(
                        {
                            "company": company.company_name,
                            "status": "skipped_resume",
                            "companies_processed": metrics["companies_processed"],
                            "companies_skipped_resume": metrics["companies_skipped_resume"],
                            "persisted_jobs": state.job_count(),
                            "exported_jobs": metrics["exported_jobs"],
                            "final_export_completed": metrics["final_export_completed"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                continue
            if resume and prior_status:
                if metrics["rechecks_attempted"] >= metrics["recheck_budget"]:
                    metrics["rechecks_skipped_budget"] += 1
                    print(
                        json.dumps(
                            {
                                "company": company.company_name,
                                "status": "skipped",
                                "reason": "recheck_budget_exhausted",
                                "companies_processed": metrics["companies_processed"],
                                "companies_skipped_resume": metrics["companies_skipped_resume"],
                                "persisted_jobs": state.job_count(),
                                "exported_jobs": metrics["exported_jobs"],
                                "final_export_completed": metrics["final_export_completed"],
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                    continue
                metrics["rechecks_attempted"] += 1
            work.append(company)

        def record_checkpoint(result: EmployerCollectionResult) -> None:
            state.save(result)
            metrics["companies_processed"] += 1
            metrics["company_statuses"][result.status] = metrics["company_statuses"].get(result.status, 0) + 1
            for row in result.jobs:
                method = row.get("extraction_method") or "unknown"
                provider = row.get("source_provider") or "unknown"
                metrics["extraction_methods"][method] = metrics["extraction_methods"].get(method, 0) + 1
                metrics["source_providers"][provider] = metrics["source_providers"].get(provider, 0) + 1
            metrics["persisted_jobs"] = state.job_count()
            metrics["jobs_written"] = metrics["persisted_jobs"]
            accounting_snapshot = accounting.snapshot()
            metrics["requests"] = accounting_snapshot["total_attempts"]
            metrics["request_accounting"] = accounting_snapshot
            print(
                json.dumps(
                    {
                        "company": result.company.company_name,
                        "status": result.status,
                        "companies_processed": metrics["companies_processed"],
                        "companies_skipped_resume": metrics["companies_skipped_resume"],
                        "company_jobs": len(result.jobs),
                        "persisted_jobs": metrics["persisted_jobs"],
                        "requests": metrics["requests"],
                        "exported_jobs": metrics["exported_jobs"],
                        "final_export_completed": metrics["final_export_completed"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

        executor = ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="employer")
        pending: dict[Any, EmployerCompany] = {}
        next_index = 0
        aborted = False
        try:
            while next_index < len(work) or pending:
                while next_index < len(work) and len(pending) < pending_limit:
                    company = work[next_index]
                    next_index += 1
                    pending[executor.submit(_collect_company_worker, company, limits)] = company
                if not pending:
                    continue
                done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
                completed_errors: list[BaseException] = []
                for future in done:
                    pending.pop(future)
                    try:
                        result = future.result()
                    except BaseException as exc:
                        # Flush every sibling that completed in the same batch
                        # before propagating interruption/fatal worker errors.
                        completed_errors.append(exc)
                    else:
                        record_checkpoint(result)
                if completed_errors:
                    raise completed_errors[0]
        except BaseException:
            aborted = True
            for future in pending:
                future.cancel()
            raise
        finally:
            executor.shutdown(wait=not aborted, cancel_futures=aborted)

        metrics["persisted_jobs"] = state.job_count()
        metrics["requests"] = accounting.snapshot()["total_attempts"]
        metrics["request_accounting"] = accounting.snapshot()
        export_result = export_catalogs_from_state(
            state,
            output_dir,
            metrics={
                **metrics,
                "persisted_jobs": metrics["persisted_jobs"],
                "exported_jobs": metrics["persisted_jobs"],
                "final_export_completed": True,
            },
        )
        metrics.update(export_result)
        metrics["jobs_written"] = metrics["persisted_jobs"]
        metrics["requests"] = accounting.snapshot()["total_attempts"]
        metrics["request_accounting"] = accounting.snapshot()
        return metrics
    finally:
        state.close()


def export_only(output_dir: Path) -> dict[str, Any]:
    """Export employer artifacts from existing state without scraping or LinkedIn input."""

    state_path = output_dir / "master_employer_jobs_state.db"
    state = EmployerState.open_existing(state_path)
    try:
        persisted_jobs = state.job_count()
        metrics = {
            "mode": "export_only",
            "output_dir": str(output_dir),
            "persisted_jobs": persisted_jobs,
            "exported_jobs": persisted_jobs,
            "companies_processed": 0,
            "companies_skipped_resume": 0,
            "final_export_completed": True,
            "jobs_written": persisted_jobs,
        }
        result = export_catalogs_from_state(state, output_dir, metrics=metrics)
        metrics.update(result)
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
        return metrics
    finally:
        state.close()


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
    parser.add_argument(
        "--recheck-budget",
        type=int,
        default=25,
        help="Bound resumed rechecks of historical uncertain/negative company rows.",
    )
    parser.add_argument("--company-concurrency", type=int, default=2)
    parser.add_argument("--max-pending", type=int, default=4)
    parser.add_argument("--http-concurrency", type=int, default=4)
    parser.add_argument("--browser-concurrency", type=int, default=1)
    parser.add_argument("--account-concurrency", type=int, default=4)
    parser.add_argument("--per-origin-concurrency", type=int, default=1)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--direct-only",
        action="store_true",
        help="Use direct public requests; retained for explicit operational clarity.",
    )
    parser.add_argument("--full", action="store_true", help="Allow an unbounded company selection.")
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Regenerate local catalogs from the existing employer state without network access.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.export_only:
        try:
            export_only(args.output_dir)
        except (OSError, sqlite3.Error, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            print(f"export-only failed: {exc}", file=sys.stderr)
            return 2
        return 0
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
        recheck_budget=args.recheck_budget,
        company_concurrency=args.company_concurrency,
        max_pending=args.max_pending,
        http_concurrency=args.http_concurrency,
        browser_concurrency=args.browser_concurrency,
        account_concurrency=args.account_concurrency,
        per_origin_concurrency=args.per_origin_concurrency,
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CollectorLimits",
    "EMPLOYER_FIELDS",
    "EMPLOYER_OUTCOMES",
    "RequestAccounting",
    "TransportGate",
    "EmployerCollectionResult",
    "EmployerCompany",
    "EmployerState",
    "export_employer_catalog_from_state",
    "export_catalogs_from_state",
    "export_only",
    "FetchResult",
    "classify_germany",
    "collect_company",
    "load_employer_companies",
    "run_collection",
    "write_employer_outputs",
]
