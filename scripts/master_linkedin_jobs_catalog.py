"""Durable Germany-scoped LinkedIn guest-endpoint job catalog.

The module deliberately keeps parsing and identity decisions available as pure
functions.  The command-line runner and network transport are defined below
those helpers so tests can exercise the trust boundary without network access.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup
import requests


SEARCH_ENDPOINT = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_ENDPOINT = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"
COMPANY_ENDPOINT = "https://www.linkedin.com/company"
GERMANY_LOCATION = "Germany"
GERMANY_GEO_ID = "101282230"

COMPANY_MATCH_EXACT_PRIMARY = "EXACT_PRIMARY_MATCH"
COMPANY_MATCH_VERIFIED_ALIAS = "VERIFIED_ALIAS_MATCH"
COMPANY_MATCH_ALIAS_PENDING = "ALIAS_PENDING_VERIFICATION"
COMPANY_MATCH_CARD_DETAIL_MISMATCH = "CARD_DETAIL_MISMATCH"
COMPANY_MATCH_REJECTED = "OWNERSHIP_REJECTED"

LOCATION_GERMANY_CONFIRMED = "GERMANY_CONFIRMED"
LOCATION_REMOTE_GERMANY_ELIGIBLE = "REMOTE_GERMANY_ELIGIBLE"
LOCATION_MULTI_LOCATION_INCLUDES_GERMANY = "MULTI_LOCATION_INCLUDES_GERMANY"
LOCATION_AMBIGUOUS = "LOCATION_AMBIGUOUS"
LOCATION_NOT_GERMANY = "NOT_GERMANY"

CATALOG_FIELDS = (
    "canonical_company_id",
    "linkedin_company_id",
    "source_company_name",
    "source_company_url",
    "source_company_ids",
    "source_company_names",
    "source_company_urls",
    "observed_company_name",
    "observed_company_url",
    "linkedin_job_id",
    "job_title",
    "linkedin_job_url",
    "apply_url_raw",
    "apply_url_canonical",
    "apply_url_source",
    "description",
    "location",
    "posted_text",
    "posted_at_estimated",
    "easy_apply_status",
    "applicant_count",
    "employment_type",
    "workplace_type",
    "first_seen_at",
    "last_seen_at",
    "last_successful_company_scan_at",
    "detail_last_refreshed_at",
    "lifecycle_status",
    "absence_count",
    "inactive_reason",
    "inactive_confirmed_at",
    "content_hash",
    "source_endpoint",
    "transport",
    "search_pagination_start",
    "search_status_code",
    "detail_status_code",
    "company_match_status",
    "ownership_status",
    "ownership_alias_status",
    "location_classification",
    "location_classification_reason",
    "company_scan_status",
    "query_partition_type",
    "query_partition_value",
    "run_id",
)

COMPLETE_SCAN_STATUSES = {"COMPLETE", "COMPLETE_ZERO_CONFIRMED", "SATURATED_RECOVERED"}

_PLACEHOLDERS = {"", "-", "n/a", "na", "none", "null", "unknown", "nan"}
_COMPANY_ID_RE = re.compile(r"^[0-9]+$")
_WHITESPACE_RE = re.compile(r"\s+")
_TRACKING_PARAMS = {
    "trk",
    "trackingid",
    "refid",
    "lipi",
    "lici",
    "eBP",
    "midToken",
    "fromSignIn",
    "originalSubdomain",
}


@dataclass(frozen=True)
class SourceCompany:
    canonical_company_id: str
    company_name: str
    linkedin_company_url: str


@dataclass(frozen=True)
class SourceCompanyGroup:
    linkedin_company_id: str
    primary_canonical_company_id: str
    source_company_names: tuple[str, ...]
    source_company_ids: tuple[str, ...]
    source_company_urls: tuple[str, ...]
    primary_slug: str

    @property
    def primary_company_url(self) -> str:
        return f"https://www.linkedin.com/company/{self.primary_slug}"

    @property
    def source_company_name(self) -> str:
        return self.source_company_names[0] if self.source_company_names else ""

    @property
    def source_slugs(self) -> tuple[str, ...]:
        return tuple(slug for slug in (canonical_company_slug(url) for url in self.source_company_urls) if slug)


@dataclass(frozen=True)
class OwnershipDecision:
    status: str
    canonical_url: str
    reason: str


@dataclass(frozen=True)
class SearchCard:
    linkedin_job_id: str
    title: str
    company_name: str
    company_url: str
    location: str
    posted_text: str = ""
    posted_at_estimated: str = ""
    linkedin_job_url: str = ""
    entity_urn: str = ""


@dataclass(frozen=True)
class SearchPageResult:
    cards: tuple[SearchCard, ...] = ()
    malformed_cards: tuple[str, ...] = ()
    is_usable: bool = False
    is_no_results: bool = False
    is_partial: bool = False
    blocked_reason: str = ""
    body_class: str = ""


@dataclass(frozen=True)
class DetailRecord:
    linkedin_job_id: str
    title: str = ""
    company_name: str = ""
    company_url: str = ""
    location: str = ""
    description: str = ""
    apply_url_raw: str = ""
    apply_url_canonical: str = ""
    apply_url_source: str = ""
    posted_text: str = ""
    posted_at_estimated: str = ""
    applicant_count: str = ""
    easy_apply_status: str = "unknown"
    employment_type: str = ""
    workplace_type: str = ""


@dataclass(frozen=True)
class PaginationEvidence:
    endpoint: str
    page_step: int
    full_card_count: int | None
    max_start: int


@dataclass(frozen=True)
class RecoveryPartition:
    parameter: str
    value: str
    source_dimension: str


class AdaptiveConcurrency:
    def __init__(self, initial: int = 10, minimum: int = 1, maximum: int = 20):
        self.minimum = max(1, int(minimum))
        self.maximum = max(self.minimum, int(maximum))
        self.workers = min(self.maximum, max(self.minimum, int(initial)))
        self._healthy_observations = 0

    def observe(self, *, status_code: int | None, blocked: bool) -> int:
        if blocked or status_code == 429 or (status_code is not None and status_code >= 500):
            self.workers = max(self.minimum, self.workers - 1)
            self._healthy_observations = 0
        elif status_code is not None and 200 <= status_code < 400:
            self._healthy_observations += 1
            if self._healthy_observations >= 20:
                self.workers = min(self.maximum, self.workers + 1)
                self._healthy_observations = 0
        return self.workers


@dataclass(frozen=True)
class ResponseEnvelope:
    status_code: int
    text: str
    proxy_id: str
    elapsed_seconds: float
    error: str = ""


@dataclass(frozen=True)
class WebshareProxy:
    identifier: str
    url: str


@dataclass(frozen=True)
class RunnerConfig:
    input_csv: Path = Path("Company-Urls/Master-Company-Url/cleaned/Master-Company-Url-canonical_cleaned_linkedin_ids.csv")
    output_dir: Path = Path("Jobs-Urls/master linkedin jobs url")
    pagination_report: Path = Path("Jobs-Urls/linkedin_endpoint_pagination_validation.json")
    filters_report: Path = Path("Jobs-Urls/linkedin_guest_endpoint_filter_validation.json")
    mode: str = "full"
    workers: int = 10
    detail_workers: int = 5
    per_proxy_concurrency: int = 1
    min_workers: int = 1
    max_workers: int = 20
    timeout: float = 30.0
    retry_limit: int = 2
    max_requests: int | None = None
    detail_refresh_hours: float = 24.0
    company_id: str | None = None
    resume_run_id: str | None = None
    fresh: bool = False
    dry_run: bool = False
    max_companies: int | None = None


@dataclass
class CompanyRunContext:
    group: SourceCompanyGroup
    scan_id: str
    search_status: str = "RUNNING"
    card_by_job_id: dict[str, SearchCard] | None = None
    card_start_by_job_id: dict[str, int] | None = None
    card_partition_by_job_id: dict[str, str] | None = None
    card_partition_value_by_job_id: dict[str, str] | None = None
    observed_job_ids: set[str] | None = None
    detail_failures: int = 0
    no_results: bool = False

    def __post_init__(self) -> None:
        self.card_by_job_id = self.card_by_job_id or {}
        self.card_start_by_job_id = self.card_start_by_job_id or {}
        self.card_partition_by_job_id = self.card_partition_by_job_id or {}
        self.card_partition_value_by_job_id = self.card_partition_value_by_job_id or {}
        self.observed_job_ids = self.observed_job_ids or set()



def _clean(value: object) -> str:
    return _WHITESPACE_RE.sub(" ", str(value or "")).strip()


def canonical_company_slug(raw_url: object) -> str:
    """Return a LinkedIn company slug, or an empty string for another URL."""

    raw = _clean(raw_url)
    if not raw:
        return ""
    parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or not (host == "linkedin.com" or host.endswith(".linkedin.com")):
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2 or parts[0].lower() != "company":
        return ""
    slug = html.unescape(parts[1]).strip()
    return slug.lower() if slug else ""


def canonical_company_url(raw_url: object) -> str:
    slug = canonical_company_slug(raw_url)
    return f"https://www.linkedin.com/company/{slug}" if slug else ""


def canonical_apply_url(raw_url: object) -> str:
    """Normalize an apply URL while retaining the raw URL elsewhere."""

    raw = _clean(raw_url)
    if not raw:
        return ""
    parsed = urlsplit(raw)
    if parsed.path == "/jobs/view" and parsed.query:
        params = dict(parse_qsl(parsed.query, keep_blank_values=False))
        redirected = params.get("url") or params.get("redirect")
        if redirected:
            return canonical_apply_url(redirected)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key not in _TRACKING_PARAMS and not key.lower().startswith("utm_")]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/") or "/", urlencode(query), ""))


def _is_placeholder(value: str) -> bool:
    return _clean(value).lower() in _PLACEHOLDERS


def normalize_company_id(value: object) -> str:
    raw = _clean(value)
    if not _COMPANY_ID_RE.fullmatch(raw):
        return ""
    normalized = str(int(raw))
    return normalized if normalized != "0" else ""


def load_source_company_groups(
    path: str | Path,
    company_id_filter: str | None = None,
) -> tuple[dict[str, SourceCompanyGroup], dict[str, int]]:
    """Load eligible source rows and group duplicate numeric company IDs."""

    rows_read = 0
    rows_accepted = 0
    rows_rejected = 0
    grouped: dict[str, list[SourceCompany]] = {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"canonical_CompanyID", "company_name", "linkedin_company_url", "linkedin_company_id"}
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"source CSV missing required columns: {', '.join(sorted(missing))}")
        for row in reader:
            rows_read += 1
            company_id = normalize_company_id(row.get("linkedin_company_id"))
            company_url = canonical_company_url(row.get("linkedin_company_url"))
            if not _COMPANY_ID_RE.fullmatch(company_id) or not company_url:
                rows_rejected += 1
                continue
            if company_id_filter and company_id != str(company_id_filter):
                continue
            grouped.setdefault(company_id, []).append(
                SourceCompany(
                    canonical_company_id=_clean(row.get("canonical_CompanyID")),
                    company_name=_clean(row.get("company_name")),
                    linkedin_company_url=company_url,
                )
            )
            rows_accepted += 1

    groups: dict[str, SourceCompanyGroup] = {}
    for company_id, source_rows in grouped.items():
        unique_rows = sorted(
            set(source_rows),
            key=lambda item: (
                _is_placeholder(item.canonical_company_id),
                item.canonical_company_id.lower(),
                item.company_name.lower(),
                item.linkedin_company_url,
            ),
        )
        ids = tuple(dict.fromkeys(row.canonical_company_id for row in unique_rows if not _is_placeholder(row.canonical_company_id)))
        names = tuple(dict.fromkeys(row.company_name for row in unique_rows if row.company_name))
        urls = tuple(dict.fromkeys(row.linkedin_company_url for row in unique_rows))
        primary_url = urls[0] if urls else ""
        groups[company_id] = SourceCompanyGroup(
            linkedin_company_id=company_id,
            primary_canonical_company_id=ids[0] if ids else "",
            source_company_names=names,
            source_company_ids=ids,
            source_company_urls=urls,
            primary_slug=canonical_company_slug(primary_url),
        )
    return groups, {
        "rows_read": rows_read,
        "rows_accepted": rows_accepted,
        "rows_rejected": rows_rejected,
        "groups": len(groups),
    }


def evaluate_ownership(
    observed_url: object,
    group: SourceCompanyGroup,
    verified_aliases: Iterable[str] = (),
) -> OwnershipDecision:
    observed_canonical = canonical_company_url(observed_url)
    if not observed_canonical:
        return OwnershipDecision(COMPANY_MATCH_REJECTED, "", "missing_or_invalid_company_url")
    slug = canonical_company_slug(observed_canonical)
    aliases = {canonical_company_slug(alias) or _clean(alias).lower() for alias in verified_aliases}
    if slug == group.primary_slug:
        return OwnershipDecision(COMPANY_MATCH_EXACT_PRIMARY, observed_canonical, "primary_slug_match")
    if slug in group.source_slugs:
        return OwnershipDecision(COMPANY_MATCH_EXACT_PRIMARY, observed_canonical, "source_mapping_slug_match")
    if slug in aliases:
        return OwnershipDecision(COMPANY_MATCH_VERIFIED_ALIAS, observed_canonical, "verified_alias_match")
    if slug:
        return OwnershipDecision(COMPANY_MATCH_ALIAS_PENDING, observed_canonical, "unverified_company_slug")
    return OwnershipDecision(COMPANY_MATCH_CARD_DETAIL_MISMATCH, observed_canonical, "company_url_mismatch")


def alias_evidence_matches(company_html: object, linkedin_company_id: str) -> bool:
    """Check company-page HTML for an exact numeric LinkedIn company ID."""

    body = str(company_html or "")
    company_id = re.escape(str(linkedin_company_id))
    patterns = (
        rf"urn:li:[^\"']*company:{company_id}(?:\D|$)",
        rf"(?:companyId|company_id)[\"']?\s*[:=]\s*[\"']?{company_id}(?:\D|$)",
        rf"/company/{company_id}(?:\D|$)",
    )
    return any(re.search(pattern, body, flags=re.IGNORECASE) for pattern in patterns)


def build_search_url(
    linkedin_company_id: str,
    *,
    start: int = 0,
    partition_type: str = "base",
    partition_value: str = "",
) -> str:
    """Build a company-scoped Germany query with immutable trust filters."""

    params: list[tuple[str, str]] = [
        ("location", GERMANY_LOCATION),
        ("geoId", GERMANY_GEO_ID),
        ("f_C", str(linkedin_company_id)),
        ("start", str(int(start))),
    ]
    if partition_type != "base" and partition_value:
        params.append((partition_type, partition_value))
    return f"{SEARCH_ENDPOINT}?{urlencode(params)}"


def classify_http_response(status_code: int, body: str) -> str:
    if int(status_code) == 429:
        return "RATE_LIMITED"
    if int(status_code) >= 500:
        return "RETRYABLE"
    if int(status_code) >= 400:
        return "PERMANENT_FAILURE"
    body_class = parse_search_page(body).body_class if body else "unusable"
    if body_class == "blocked":
        return "BLOCKED"
    if body_class in {"usable", "no_results"}:
        return "SUCCESS"
    return "MALFORMED"


def is_suspicious_empty_body(body: object) -> bool:
    value = str(body or "").strip()
    return 0 < len(value) < 200 and not _blocked_body(value)


def redact_proxy_url(proxy_url: object) -> str:
    raw = _clean(proxy_url)
    if not raw:
        return ""
    parsed = urlsplit(raw)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    return urlunsplit((parsed.scheme, f"{host}{port}", parsed.path, "", ""))


def _proxy_from_line(line: str) -> WebshareProxy | None:
    value = _clean(line)
    if not value or value.startswith("#"):
        return None
    if "://" not in value:
        pieces = value.split(":")
        if len(pieces) == 4:
            host, port, username, password = pieces
            value = f"http://{quote(username, safe='')}:{quote(password, safe='')}@{host}:{port}"
        elif len(pieces) == 2:
            value = f"http://{value}"
    parsed = urlsplit(value)
    if not parsed.hostname or not parsed.port:
        return None
    return WebshareProxy(f"{parsed.hostname}:{parsed.port}", value)


def load_webshare_proxies(
    *,
    api_key: str | None = None,
    proxy_file: str | Path | None = None,
    api_url: str = "https://proxy.webshare.io/api/v2/proxy/list/",
) -> tuple[WebshareProxy, ...]:
    """Load the configured Webshare pool without returning credentials in metadata."""

    try:
        from backend.config.job_seeker import load_project_dotenv

        load_project_dotenv()
    except Exception:
        pass
    explicit_file = str(proxy_file or os.environ.get("WEBSHARE_PROXY_FILE") or os.environ.get("WEBSHARE_PROXY_LIST_FILE") or "").strip()
    if explicit_file:
        path = Path(explicit_file)
        proxies = tuple(proxy for line in path.read_text(encoding="utf-8").splitlines() if (proxy := _proxy_from_line(line)))
        if proxies:
            return proxies
    raw_proxy_list = os.environ.get("WEBSHARE_PROXIES", "")
    if raw_proxy_list:
        proxies = tuple(proxy for line in raw_proxy_list.splitlines() if (proxy := _proxy_from_line(line)))
        if proxies:
            return proxies
    key = api_key or os.environ.get("WEBSHARE_API_KEY", "")
    if not key:
        raise ValueError("Webshare proxy configuration is missing")
    session = requests.Session()
    session.trust_env = False
    request_url = api_url if "?" in api_url else f"{api_url}?mode=direct&page=1&page_size=100"
    results: list[object] = []
    seen_urls: set[str] = set()
    while request_url and request_url not in seen_urls:
        seen_urls.add(request_url)
        response = session.get(request_url, headers={"Authorization": f"Token {key}"}, timeout=30)
        if response.status_code != 200:
            raise ValueError(f"Webshare proxy API returned status {response.status_code}")
        payload = response.json()
        page_results = payload.get("results", []) if isinstance(payload, dict) else payload
        results.extend(page_results or [])
        next_url = payload.get("next") if isinstance(payload, dict) else ""
        if next_url:
            request_url = str(next_url)
        elif isinstance(payload, dict) and len(results) < int(payload.get("count") or 0):
            request_url = f"{api_url}?mode=direct&page={len(seen_urls) + 1}&page_size=100"
        else:
            request_url = ""
    proxies: list[WebshareProxy] = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        host = _clean(item.get("proxy_address"))
        port = _clean(item.get("port"))
        username = _clean(item.get("username"))
        password = _clean(item.get("password"))
        if not host or not port:
            continue
        auth = f"{quote(username, safe='')}:{quote(password, safe='')}@" if username or password else ""
        proxies.append(WebshareProxy(f"{host}:{port}", f"http://{auth}{host}:{port}"))
    if not proxies:
        username = _clean(os.environ.get("WEBSHARE_PROXY_USERNAME"))
        password = _clean(os.environ.get("WEBSHARE_PROXY_PASSWORD"))
        if username and password:
            fallback = (
                "31.59.20.176:6754",
                "31.56.127.193:7684",
                "45.38.107.97:6014",
                "198.105.121.200:6462",
                "64.137.96.74:6641",
                "198.23.243.226:6361",
                "38.154.185.97:6370",
                "84.247.60.125:6095",
                "142.111.67.146:5611",
                "191.96.254.138:6185",
            )
            return tuple(_proxy_from_line(f"{host}:{username}:{password}") for host in fallback if _proxy_from_line(f"{host}:{username}:{password}"))
        raise ValueError("Webshare proxy API returned no usable proxies")
    return tuple(proxies)


def _blocked_body(body: str) -> bool:
    lowered = str(body or "").lower()
    if any(marker in lowered for marker in ("sign in to linkedin", "captcha", "verify you are human", "unusual traffic", "authwall", "checkpoint")):
        return True
    return any(marker in lowered for marker in ("challenge-page", "challenge_page", "challenge-container", "challenge_container", "id=\"challenge\""))


class WebshareTransport:
    def __init__(
        self,
        proxies: Iterable[WebshareProxy],
        *,
        timeout: float = 30.0,
        retry_limit: int = 2,
        max_requests: int | None = None,
        per_proxy_concurrency: int = 1,
        sleep=time.sleep,
    ):
        self.proxies = tuple(proxies)
        if not self.proxies:
            raise ValueError("at least one Webshare proxy is required")
        self.timeout = float(timeout)
        self.retry_limit = max(0, int(retry_limit))
        self.max_requests = max_requests
        self.sleep = sleep
        self._next_proxy = 0
        self._request_count = 0
        self._lock = threading.Lock()
        self._proxy_locks = {proxy.identifier: threading.BoundedSemaphore(max(1, int(per_proxy_concurrency))) for proxy in self.proxies}

    def _take_proxy(self) -> WebshareProxy | None:
        with self._lock:
            if self.max_requests is not None and self._request_count >= self.max_requests:
                return None
            proxy = self.proxies[self._next_proxy % len(self.proxies)]
            self._next_proxy += 1
            self._request_count += 1
            return proxy

    def get(self, url: str, *, kind: str) -> ResponseEnvelope:
        last = ResponseEnvelope(0, "", "", 0.0, "request_budget_exhausted")
        for attempt in range(self.retry_limit + 1):
            proxy = self._take_proxy()
            if proxy is None:
                return last
            started = time.monotonic()
            with self._proxy_locks[proxy.identifier]:
                session = requests.Session()
                session.trust_env = False
                session.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml",
                })
                try:
                    response = session.get(url, proxies={"http": proxy.url, "https": proxy.url}, timeout=self.timeout)
                    elapsed = time.monotonic() - started
                    last = ResponseEnvelope(response.status_code, response.text, proxy.identifier, elapsed)
                    should_retry = response.status_code == 429 or response.status_code >= 500 or _blocked_body(response.text)
                except requests.RequestException:
                    elapsed = time.monotonic() - started
                    last = ResponseEnvelope(0, "", proxy.identifier, elapsed, "network_error")
                    should_retry = True
            if not should_retry or attempt >= self.retry_limit:
                return last
            self.sleep(min(30.0, 0.5 * (2**attempt)) + 0.1 * (attempt + 1))
        return last


def _first_text(node, selectors: Iterable[str]) -> str:
    for selector in selectors:
        found = node.select_one(selector)
        if found:
            text = _clean(found.get_text(" ", strip=True))
            if text:
                return text
    return ""


def _job_id_from_card(card) -> str:
    urn = _clean(card.get("data-entity-urn"))
    if not urn:
        nested = card.select_one("[data-entity-urn]")
        urn = _clean(nested.get("data-entity-urn")) if nested else ""
    match = re.search(r"(?:jobPosting|job_posting):?(\d+)", urn, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    for anchor in card.select("a[href]"):
        match = re.search(r"/jobs/(?:view|view/)(\d+)", anchor.get("href", ""))
        if match:
            return match.group(1)
    return ""


def _posted_at_from_card(card) -> str:
    time_node = card.select_one("time[datetime]")
    return _clean(time_node.get("datetime")) if time_node else ""


def parse_search_page(body: str) -> SearchPageResult:
    """Parse a guest search response, retaining usable cards on partial pages."""

    raw_body = str(body or "")
    lowered = raw_body.lower()
    if _blocked_body(raw_body):
        return SearchPageResult(blocked_reason="login_or_challenge", body_class="blocked")
    soup = BeautifulSoup(raw_body, "html.parser")
    visible_text = _clean(soup.get_text(" ", strip=True)).lower()
    if soup.select_one(".jobs-search-no-results, .jobs-search__no-results") or re.search(r"\bno jobs found\b", visible_text):
        return SearchPageResult(is_usable=True, is_no_results=True, body_class="no_results")

    card_nodes = list(soup.select("li.job-card-container, li.base-card, .job-card-container"))
    known_nodes = {id(node) for node in card_nodes}
    for item in soup.find_all("li"):
        if id(item) not in known_nodes and item.select_one("div.base-search-card, div.base-card, [data-entity-urn]"):
            card_nodes.append(item)
    if not card_nodes:
        return SearchPageResult(blocked_reason="unexpected_or_empty_body", body_class="unusable")
    cards: list[SearchCard] = []
    malformed: list[str] = []
    for card in card_nodes:
        job_id = _job_id_from_card(card)
        if not job_id:
            malformed.append("missing_job_id")
            continue
        company_anchor = card.select_one("a[href*='/company/']")
        company_url = canonical_company_url(company_anchor.get("href")) if company_anchor else ""
        if not company_url:
            malformed.append("missing_company_url")
            continue
        job_anchor = card.select_one("a[href*='/jobs/view/']")
        job_url = f"https://www.linkedin.com/jobs/view/{job_id}"
        if job_anchor:
            job_url = f"https://www.linkedin.com/jobs/view/{job_id}"
        cards.append(
            SearchCard(
                linkedin_job_id=job_id,
                title=_first_text(card, (".base-search-card__title", ".job-card-list__title")),
                company_name=_clean(company_anchor.get_text(" ", strip=True)),
                company_url=company_url,
                location=_first_text(card, (".job-search-card__location", ".base-search-card__metadata")),
                posted_text=_first_text(card, ("time", ".job-search-card__listdate")),
                posted_at_estimated=_posted_at_from_card(card),
                linkedin_job_url=job_url,
                entity_urn=_clean(card.get("data-entity-urn")),
            )
        )
    return SearchPageResult(
        cards=tuple(cards),
        malformed_cards=tuple(malformed),
        is_usable=bool(cards),
        is_partial=bool(malformed),
        body_class="usable" if cards else "unusable",
    )


def _detail_location(soup: BeautifulSoup) -> str:
    nodes = soup.select(".top-card-layout__first-subline span, .topcard__flavor--bullet")
    if not nodes:
        nodes = soup.select(".top-card-layout__first-subline, .topcard__flavor")
    candidates = [_clean(node.get_text(" ", strip=True)) for node in nodes]
    for candidate in candidates:
        if any(term in candidate.lower() for term in _GERMAN_TERMS + _FOREIGN_TERMS) or "remote" in candidate.lower():
            return candidate
    return candidates[0] if candidates else ""


def parse_job_detail(linkedin_job_id: str, body: str) -> DetailRecord:
    soup = BeautifulSoup(str(body or ""), "html.parser")
    title = _first_text(soup, (".top-card-layout__title", "h1"))
    company_anchor = soup.select_one(".top-card-layout__second-subline a[href*='/company/'], a[href*='/company/']")
    company_url = canonical_company_url(company_anchor.get("href")) if company_anchor else ""
    company_name = _clean(company_anchor.get_text(" ", strip=True)) if company_anchor else ""
    description = _first_text(soup, (".show-more-less-html__markup", ".description__text", ".description__text--rich"))
    apply_anchor = None
    for anchor in soup.select("a[href]"):
        href = _clean(anchor.get("href"))
        tracking = _clean(anchor.get("data-tracking-control-name"))
        if "apply" in tracking.lower() or "apply" in href.lower() or "/jobs/view/" in href.lower():
            apply_anchor = anchor
            if "offsite" in tracking.lower() or (urlsplit(href).hostname or "").lower() not in {"linkedin.com", "www.linkedin.com"}:
                break
    raw_apply = _clean(apply_anchor.get("href")) if apply_anchor else f"https://www.linkedin.com/jobs/view/{linkedin_job_id}"
    host = (urlsplit(raw_apply).hostname or "").lower()
    if host and not host.endswith("linkedin.com"):
        apply_source = "external"
    elif apply_anchor:
        apply_source = "linkedin"
    else:
        apply_source = "linkedin_fallback"
    info_text = _clean(soup.select_one(".top-card-layout__entity-info").get_text(" ", strip=True) if soup.select_one(".top-card-layout__entity-info") else "")
    applicant_match = re.search(r"([0-9][0-9,]*)\s+applicants?", info_text, flags=re.IGNORECASE)
    posted_text = _first_text(soup, (".top-card-layout__entity-info span", "time"))
    if applicant_match and posted_text == applicant_match.group(0):
        posted_text = ""
    criteria: dict[str, str] = {}
    for item in soup.select(".description__job-criteria-list li"):
        label = _first_text(item, ("h3", "dt")).lower()
        value = _first_text(item, ("span", "dd"))
        if label:
            criteria[label] = value
    detail_text = _clean(soup.get_text(" ", strip=True)).lower()
    if "easy apply" in detail_text or "einfach bewerben" in detail_text:
        easy_apply = "true"
    elif "offsite" in _clean(apply_anchor.get("data-tracking-control-name") if apply_anchor else "").lower() or "apply on company website" in detail_text:
        easy_apply = "false"
    else:
        easy_apply = "unknown"
    return DetailRecord(
        linkedin_job_id=str(linkedin_job_id),
        title=title,
        company_name=company_name,
        company_url=company_url,
        location=_detail_location(soup),
        description=description,
        apply_url_raw=raw_apply,
        apply_url_canonical=canonical_apply_url(raw_apply),
        apply_url_source=apply_source,
        posted_text=posted_text,
        applicant_count=applicant_match.group(1).replace(",", "") if applicant_match else "",
        easy_apply_status=easy_apply,
        employment_type=criteria.get("employment type", ""),
        workplace_type=criteria.get("workplace type", ""),
    )


def evaluate_card_detail_ownership(
    card_url: object,
    detail_url: object,
    group: SourceCompanyGroup,
    verified_aliases: Iterable[str] = (),
) -> OwnershipDecision:
    card = evaluate_ownership(card_url, group, verified_aliases)
    detail = evaluate_ownership(detail_url, group, verified_aliases)
    if not card.canonical_url or not detail.canonical_url:
        return OwnershipDecision(COMPANY_MATCH_REJECTED, detail.canonical_url or card.canonical_url, "missing_card_or_detail_company_url")
    if card.canonical_url != detail.canonical_url:
        return OwnershipDecision(COMPANY_MATCH_CARD_DETAIL_MISMATCH, detail.canonical_url, "card_detail_company_url_mismatch")
    if card.status == COMPANY_MATCH_EXACT_PRIMARY and detail.status == COMPANY_MATCH_EXACT_PRIMARY:
        return OwnershipDecision(COMPANY_MATCH_EXACT_PRIMARY, detail.canonical_url, "card_detail_primary_match")
    if card.status == COMPANY_MATCH_VERIFIED_ALIAS and detail.status == COMPANY_MATCH_VERIFIED_ALIAS:
        return OwnershipDecision(COMPANY_MATCH_VERIFIED_ALIAS, detail.canonical_url, "card_detail_verified_alias_match")
    return OwnershipDecision(COMPANY_MATCH_ALIAS_PENDING, detail.canonical_url, "card_detail_alias_pending_verification")


def load_pagination_evidence(path: str | Path, endpoint: str = SEARCH_ENDPOINT) -> PaginationEvidence:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid pagination evidence: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("endpoint") != endpoint:
        raise ValueError("pagination evidence endpoint is missing or does not match the search endpoint")
    method = payload.get("method") if isinstance(payload.get("method"), dict) else {}
    ceiling = payload.get("ceiling_scan") if isinstance(payload.get("ceiling_scan"), dict) else {}
    starts = method.get("ceiling_starts") or ceiling.get("tested_starts") or []
    starts = [int(value) for value in starts if str(value).isdigit()]
    differences = [right - left for left, right in zip(starts, starts[1:]) if right > left]
    page_step = int(payload.get("page_step") or (min(differences) if differences else 0))
    max_start_value = (
        payload.get("max_start")
        if payload.get("max_start") is not None
        else ceiling.get("terminal_http_400_start")
        if ceiling.get("terminal_http_400_start") is not None
        else ceiling.get("last_nonempty_start")
    )
    try:
        max_start = int(max_start_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("pagination evidence has no numeric max_start") from exc
    full_count_value = payload.get("full_card_count")
    full_count = int(full_count_value) if full_count_value is not None else None
    if page_step <= 0 or max_start < 0:
        raise ValueError("pagination evidence has invalid page_step or max_start")
    return PaginationEvidence(endpoint=endpoint, page_step=page_step, full_card_count=full_count, max_start=max_start)


_FILTER_PARAMETER_MAP = {
    "freshness": ("f_TPR", lambda value: str(value)),
    "job_type": (
        "f_JT",
        {"full-time": "F", "part-time": "P", "contract": "C", "temporary": "T", "volunteer": "V", "internship": "I", "other": "O"}.__getitem__,
    ),
    "experience": (
        "f_E",
        {"internship": "1", "entry-level": "2", "associate": "3", "mid-senior": "4", "director": "5", "executive": "6"}.__getitem__,
    ),
    "workplace": (
        "f_WT",
        {"onsite": "1", "remote": "2", "hybrid": "3"}.__getitem__,
    ),
}


def build_recovery_partitions(path: str | Path, endpoint: str = SEARCH_ENDPOINT) -> tuple[RecoveryPartition, ...]:
    """Return only filter values explicitly marked SUPPORTED by evidence."""

    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid filter validation evidence: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("endpoint") != endpoint or payload.get("status") not in {"COMPLETE", "completed"}:
        raise ValueError("filter validation evidence is missing, incomplete, or for another endpoint")
    allowed_statuses = set(payload.get("enable_only_statuses") or ["SUPPORTED"])
    filters = payload.get("filters")
    if not isinstance(filters, dict):
        return ()
    result: list[RecoveryPartition] = []
    for dimension in ("freshness", "job_type", "experience", "workplace"):
        values = filters.get(dimension)
        if not isinstance(values, dict) or dimension not in _FILTER_PARAMETER_MAP:
            continue
        parameter, converter = _FILTER_PARAMETER_MAP[dimension]
        for raw_value, evidence in values.items():
            if not isinstance(evidence, dict) or evidence.get("status") not in allowed_statuses:
                continue
            try:
                value = converter(raw_value)
            except (KeyError, TypeError):
                continue
            result.append(RecoveryPartition(parameter, value, dimension))
    return tuple(result)


_GERMAN_TERMS = (
    "germany",
    "deutschland",
    "berlin",
    "munich",
    "münchen",
    "hamburg",
    "frankfurt",
    "cologne",
    "köln",
    "stuttgart",
    "düsseldorf",
    "leipzig",
    "dresden",
    "nuremberg",
    "nürnberg",
    "bremen",
    "hanover",
    "hannover",
)
_FOREIGN_TERMS = (
    "austria",
    "vienna",
    "wien",
    "switzerland",
    "zurich",
    "zürich",
    "united states",
    "new york",
    "london",
    "united kingdom",
    "paris",
    "france",
    "amsterdam",
    "netherlands",
)


def classify_germany_location(raw_location: object) -> tuple[str, str]:
    location = _clean(raw_location)
    lowered = location.lower()
    german_hits = [term for term in _GERMAN_TERMS if term in lowered]
    foreign_hits = [term for term in _FOREIGN_TERMS if term in lowered]
    is_remote = "remote" in lowered or "work from home" in lowered
    if german_hits and foreign_hits:
        return LOCATION_MULTI_LOCATION_INCLUDES_GERMANY, f"German location ({german_hits[0]}) and other location ({foreign_hits[0]})"
    if german_hits and is_remote and ("remote" in lowered or "from germany" in lowered):
        return LOCATION_REMOTE_GERMANY_ELIGIBLE, f"remote work explicitly permits Germany ({german_hits[0]})"
    if german_hits:
        return LOCATION_GERMANY_CONFIRMED, f"German location matched ({german_hits[0]})"
    if foreign_hits:
        return LOCATION_NOT_GERMANY, f"foreign location matched ({foreign_hits[0]})"
    if any(term in lowered for term in ("europe", "europa", "emea", "worldwide", "global", "anywhere", "remote")):
        return LOCATION_AMBIGUOUS, "broad region or remote scope does not prove Germany"
    return LOCATION_AMBIGUOUS, "location does not provide Germany evidence"


_HASH_FIELDS = (
    "job_title",
    "description",
    "location",
    "employment_type",
    "workplace_type",
    "canonical_apply_url",
    "observed_company_url",
)


def compute_content_hash(fields: Mapping[str, object]) -> str:
    normalized = {key: _clean(fields.get(key, "")) for key in _HASH_FIELDS}
    normalized["canonical_apply_url"] = canonical_apply_url(normalized["canonical_apply_url"])
    normalized["observed_company_url"] = canonical_company_url(normalized["observed_company_url"])
    payload = "\x1f".join(f"{key}={normalized[key]}" for key in _HASH_FIELDS).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_row(row: Mapping[str, object]) -> dict[str, str]:
    return {field: _clean(row.get(field, "")) for field in CATALOG_FIELDS}


def _redact_payload(value: object, key: str = "") -> object:
    lowered_key = key.lower()
    if any(marker in lowered_key for marker in ("password", "secret", "token", "authorization", "proxy_url")):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(item_key): _redact_payload(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_payload(item, key) for item in value]
    if isinstance(value, str) and "@" in value and "://" in value:
        return redact_proxy_url(value)
    return value


def _parse_timestamp(value: object) -> datetime | None:
    raw = _clean(value)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def detail_refresh_required(
    last_refreshed_at: object,
    now: object,
    refresh_hours: float,
    *,
    card_changed: bool = False,
) -> bool:
    if card_changed:
        return True
    previous = _parse_timestamp(last_refreshed_at)
    current = _parse_timestamp(now)
    if previous is None or current is None:
        return True
    return (current - previous).total_seconds() >= float(refresh_hours) * 3600


def union_job_ids(partitions: Iterable[Iterable[object]]) -> tuple[str, ...]:
    values = {str(value).strip() for partition in partitions for value in partition if str(value).strip()}
    return tuple(sorted(values, key=lambda value: (not value.isdigit(), int(value) if value.isdigit() else value)))


class StateStore:
    """SQLite-backed progress and catalog store.

    The public methods intentionally perform small transactions.  Callers can
    safely resume a run after a process interruption without rebuilding state.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._lock, self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    input_sha256 TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'RUNNING'
                );
                CREATE TABLE IF NOT EXISTS source_company_groups (
                    linkedin_company_id TEXT PRIMARY KEY,
                    primary_canonical_company_id TEXT NOT NULL,
                    source_company_names_json TEXT NOT NULL,
                    source_company_ids_json TEXT NOT NULL,
                    source_company_urls_json TEXT NOT NULL,
                    primary_slug TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS company_slug_aliases (
                    linkedin_company_id TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    status TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    verification_method TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (linkedin_company_id, slug)
                );
                CREATE TABLE IF NOT EXISTS company_scans (
                    company_scan_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    linkedin_company_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'RUNNING',
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL DEFAULT '',
                    observed_job_ids_json TEXT NOT NULL DEFAULT '[]'
                );
                CREATE TABLE IF NOT EXISTS query_partitions (
                    query_partition_id TEXT PRIMARY KEY,
                    company_scan_id TEXT NOT NULL,
                    partition_type TEXT NOT NULL,
                    partition_value TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING'
                );
                CREATE TABLE IF NOT EXISTS search_pages (
                    run_id TEXT NOT NULL,
                    company_scan_id TEXT NOT NULL,
                    linkedin_company_id TEXT NOT NULL,
                    query_partition_type TEXT NOT NULL DEFAULT 'base',
                    page_start INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    job_ids_json TEXT NOT NULL,
                    body_hash TEXT NOT NULL DEFAULT '',
                    detail_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (run_id, linkedin_company_id, query_partition_type, page_start)
                );
                CREATE TABLE IF NOT EXISTS search_cards (
                    run_id TEXT NOT NULL,
                    company_scan_id TEXT NOT NULL,
                    linkedin_company_id TEXT NOT NULL,
                    linkedin_job_id TEXT NOT NULL,
                    card_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, linkedin_company_id, linkedin_job_id)
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    linkedin_job_id TEXT PRIMARY KEY,
                    job_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS job_company_observations (
                    linkedin_company_id TEXT NOT NULL,
                    linkedin_job_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    company_scan_id TEXT NOT NULL DEFAULT '',
                    ownership_status TEXT NOT NULL DEFAULT '',
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    row_json TEXT NOT NULL,
                    PRIMARY KEY (linkedin_company_id, linkedin_job_id)
                );
                CREATE TABLE IF NOT EXISTS detail_queue (
                    run_id TEXT NOT NULL,
                    linkedin_job_id TEXT NOT NULL,
                    linkedin_company_id TEXT NOT NULL,
                    company_scan_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    next_attempt_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (run_id, linkedin_job_id)
                );
                CREATE TABLE IF NOT EXISTS detail_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    linkedin_job_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempted_at TEXT NOT NULL,
                    error_class TEXT NOT NULL DEFAULT '',
                    detail_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS ownership_exclusions (
                    exclusion_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    linkedin_company_id TEXT NOT NULL,
                    linkedin_job_id TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL,
                    observation_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS lifecycle_events (
                    event_id TEXT PRIMARY KEY,
                    linkedin_company_id TEXT NOT NULL,
                    linkedin_job_id TEXT NOT NULL,
                    company_scan_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (linkedin_company_id, linkedin_job_id, company_scan_id)
                );
                CREATE TABLE IF NOT EXISTS proxy_health (
                    proxy_id TEXT PRIMARY KEY,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    rate_limited_count INTEGER NOT NULL DEFAULT 0,
                    blocked_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._repair_duplicate_company_scans()
            self.connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_company_scans_run_company ON company_scans(run_id, linkedin_company_id)"
            )
            self._backfill_observation_scan_ids()

    def _repair_duplicate_company_scans(self) -> None:
        duplicates = self.connection.execute(
            """SELECT run_id, linkedin_company_id
               FROM company_scans
               GROUP BY run_id, linkedin_company_id
               HAVING COUNT(*) > 1"""
        ).fetchall()
        for duplicate in duplicates:
            run_id = str(duplicate[0])
            company_id = str(duplicate[1])
            scans = self.connection.execute(
                """SELECT company_scan_id
                   FROM company_scans
                   WHERE run_id=? AND linkedin_company_id=?
                   ORDER BY started_at, company_scan_id""",
                (run_id, company_id),
            ).fetchall()
            keep_scan_id = str(scans[0][0])
            for scan in scans[1:]:
                duplicate_scan_id = str(scan[0])
                self.connection.execute(
                    "UPDATE query_partitions SET company_scan_id=? WHERE company_scan_id=?",
                    (keep_scan_id, duplicate_scan_id),
                )
                self.connection.execute(
                    "UPDATE search_pages SET company_scan_id=? WHERE company_scan_id=?",
                    (keep_scan_id, duplicate_scan_id),
                )
                self.connection.execute(
                    "UPDATE search_cards SET company_scan_id=? WHERE company_scan_id=?",
                    (keep_scan_id, duplicate_scan_id),
                )
                self.connection.execute(
                    """DELETE FROM detail_queue
                       WHERE run_id=? AND company_scan_id=?
                         AND EXISTS (
                             SELECT 1 FROM detail_queue canonical
                             WHERE canonical.run_id=detail_queue.run_id
                               AND canonical.linkedin_job_id=detail_queue.linkedin_job_id
                               AND canonical.company_scan_id=?
                         )""",
                    (run_id, duplicate_scan_id, keep_scan_id),
                )
                self.connection.execute(
                    "UPDATE detail_queue SET company_scan_id=? WHERE run_id=? AND company_scan_id=?",
                    (keep_scan_id, run_id, duplicate_scan_id),
                )
                self.connection.execute(
                    "DELETE FROM company_scans WHERE company_scan_id=?",
                    (duplicate_scan_id,),
                )

    def _backfill_observation_scan_ids(self) -> None:
        rows = self.connection.execute(
            """SELECT linkedin_company_id, linkedin_job_id, run_id, row_json
               FROM job_company_observations
               WHERE company_scan_id=''"""
        ).fetchall()
        for row in rows:
            scan = self.connection.execute(
                """SELECT company_scan_id
                   FROM company_scans
                   WHERE run_id=? AND linkedin_company_id=?
                   ORDER BY started_at DESC, company_scan_id
                   LIMIT 1""",
                (str(row[2]), str(row[0])),
            ).fetchone()
            if scan is None:
                continue
            data = json.loads(row[3])
            data["company_scan_id"] = str(scan[0])
            self.connection.execute(
                """UPDATE job_company_observations
                   SET company_scan_id=?, row_json=?
                   WHERE linkedin_company_id=? AND linkedin_job_id=?""",
                (str(scan[0]), json.dumps(data, ensure_ascii=False), str(row[0]), str(row[1])),
            )

    def start_run(self, run_id: str, *, mode: str, input_sha256: str, started_at: str | None = None) -> str:
        timestamp = started_at or _utc_now()
        with self._lock, self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO runs(run_id, mode, input_sha256, started_at, status) VALUES (?, ?, ?, ?, 'RUNNING')",
                (run_id, mode, input_sha256, timestamp),
            )
        return run_id

    def finish_run(self, run_id: str, status: str = "FINISHED") -> None:
        with self._lock, self.connection:
            self.connection.execute("UPDATE runs SET status=? WHERE run_id=?", (status, str(run_id)))

    def start_company_scan(self, run_id: str, group: SourceCompanyGroup, *, scan_id: str | None = None, started_at: str | None = None) -> str:
        scan_id = scan_id or uuid.uuid4().hex
        with self._lock, self.connection:
            existing = self.connection.execute(
                "SELECT company_scan_id FROM company_scans WHERE run_id=? AND linkedin_company_id=? ORDER BY started_at, company_scan_id LIMIT 1",
                (str(run_id), group.linkedin_company_id),
            ).fetchone()
            if existing:
                return str(existing[0])
            self.connection.execute(
                "INSERT OR IGNORE INTO source_company_groups VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    group.linkedin_company_id,
                    group.primary_canonical_company_id,
                    json.dumps(group.source_company_names),
                    json.dumps(group.source_company_ids),
                    json.dumps(group.source_company_urls),
                    group.primary_slug,
                    started_at or _utc_now(),
                ),
            )
            self.connection.execute(
                "INSERT OR IGNORE INTO company_scans(company_scan_id, run_id, linkedin_company_id, started_at) VALUES (?, ?, ?, ?)",
                (scan_id, run_id, group.linkedin_company_id, started_at or _utc_now()),
            )
            selected = self.connection.execute(
                "SELECT company_scan_id FROM company_scans WHERE run_id=? AND linkedin_company_id=? ORDER BY started_at, company_scan_id LIMIT 1",
                (str(run_id), group.linkedin_company_id),
            ).fetchone()
        return str(selected[0]) if selected else scan_id

    def existing_company_scan(self, run_id: str, linkedin_company_id: str) -> str | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT company_scan_id FROM company_scans WHERE run_id=? AND linkedin_company_id=? ORDER BY started_at LIMIT 1",
                (str(run_id), str(linkedin_company_id)),
            ).fetchone()
        return str(row[0]) if row else None

    def existing_company_scan_status(self, run_id: str, linkedin_company_id: str) -> str | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT status FROM company_scans WHERE run_id=? AND linkedin_company_id=? ORDER BY started_at LIMIT 1",
                (str(run_id), str(linkedin_company_id)),
            ).fetchone()
        return str(row[0]) if row else None

    def record_search_page(
        self,
        run_id: str,
        company_scan_id: str,
        linkedin_company_id: str,
        page_start: int,
        *,
        status: str,
        job_ids: Iterable[str],
        partition_type: str = "base",
        body_hash: str = "",
        detail: Mapping[str, object] | None = None,
        cards: Iterable[SearchCard] = (),
    ) -> None:
        ids = tuple(dict.fromkeys(str(job_id) for job_id in job_ids if str(job_id)))
        with self._lock, self.connection:
            self.connection.execute(
                """INSERT INTO search_pages(run_id, company_scan_id, linkedin_company_id, query_partition_type, page_start, status, job_ids_json, body_hash, detail_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(run_id, linkedin_company_id, query_partition_type, page_start) DO UPDATE SET
                   status=excluded.status, job_ids_json=excluded.job_ids_json, body_hash=excluded.body_hash, detail_json=excluded.detail_json""",
                (run_id, company_scan_id, linkedin_company_id, partition_type, int(page_start), status, json.dumps(ids), body_hash, json.dumps(detail or {})),
            )
            for card in cards:
                self.connection.execute(
                    "INSERT OR REPLACE INTO search_cards(run_id, company_scan_id, linkedin_company_id, linkedin_job_id, card_json) VALUES (?, ?, ?, ?, ?)",
                    (run_id, company_scan_id, linkedin_company_id, card.linkedin_job_id, json.dumps(card.__dict__)),
                )

    def successful_page_exists(self, run_id: str, linkedin_company_id: str, page_start: int, partition_type: str = "base") -> bool:
        with self._lock:
            row = self.connection.execute(
                "SELECT 1 FROM search_pages WHERE run_id=? AND linkedin_company_id=? AND query_partition_type=? AND page_start=? AND status IN ('COMPLETE', 'COMPLETE_ZERO_CONFIRMED')",
                (run_id, linkedin_company_id, partition_type, int(page_start)),
            ).fetchone()
        return row is not None

    def page_job_ids(self, run_id: str, linkedin_company_id: str, page_start: int, partition_type: str = "base") -> tuple[str, ...]:
        with self._lock:
            row = self.connection.execute(
                "SELECT job_ids_json FROM search_pages WHERE run_id=? AND linkedin_company_id=? AND query_partition_type=? AND page_start=?",
                (run_id, str(linkedin_company_id), partition_type, int(page_start)),
            ).fetchone()
        return tuple(json.loads(row[0])) if row else ()

    def start_query_partition(self, company_scan_id: str, partition_type: str, partition_value: str) -> str:
        partition_id = uuid.uuid4().hex
        with self._lock, self.connection:
            self.connection.execute(
                "INSERT INTO query_partitions(query_partition_id, company_scan_id, partition_type, partition_value, status) VALUES (?, ?, ?, ?, 'RUNNING')",
                (partition_id, company_scan_id, partition_type, partition_value),
            )
        return partition_id

    def finish_query_partition(self, partition_id: str, status: str) -> None:
        with self._lock, self.connection:
            self.connection.execute("UPDATE query_partitions SET status=? WHERE query_partition_id=?", (status, partition_id))

    def search_cards_for_run(self, run_id: str, linkedin_company_id: str) -> tuple[SearchCard, ...]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT card_json FROM search_cards WHERE run_id=? AND linkedin_company_id=? ORDER BY linkedin_job_id",
                (run_id, str(linkedin_company_id)),
            ).fetchall()
        return tuple(SearchCard(**json.loads(row[0])) for row in rows)

    def get_detail_queue_entries(self, run_id: str) -> tuple[sqlite3.Row, ...]:
        with self._lock:
            return tuple(
                self.connection.execute(
                    "SELECT * FROM detail_queue WHERE run_id=? AND status IN ('PENDING', 'RETRY') ORDER BY linkedin_job_id",
                    (run_id,),
                ).fetchall()
            )

    def verified_aliases(self, linkedin_company_id: str) -> tuple[str, ...]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT slug FROM company_slug_aliases WHERE linkedin_company_id=? AND status='VERIFIED_ALIAS_MATCH'",
                (str(linkedin_company_id),),
            ).fetchall()
        return tuple(row[0] for row in rows)

    def record_alias(
        self,
        linkedin_company_id: str,
        slug: str,
        *,
        status: str,
        verification_method: str = "",
        seen_at: str | None = None,
    ) -> None:
        timestamp = seen_at or _utc_now()
        with self._lock, self.connection:
            self.connection.execute(
                """INSERT INTO company_slug_aliases(linkedin_company_id, slug, status, first_seen_at, last_seen_at, verification_method)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(linkedin_company_id, slug) DO UPDATE SET status=excluded.status, last_seen_at=excluded.last_seen_at, verification_method=excluded.verification_method""",
                (str(linkedin_company_id), str(slug), status, timestamp, timestamp, verification_method),
            )

    def record_exclusion(
        self,
        run_id: str,
        linkedin_company_id: str,
        linkedin_job_id: str,
        reason: str,
        observation: Mapping[str, object],
    ) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                "INSERT INTO ownership_exclusions(exclusion_id, run_id, linkedin_company_id, linkedin_job_id, reason, observation_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, str(run_id), str(linkedin_company_id), str(linkedin_job_id or ""), reason, json.dumps(dict(observation), ensure_ascii=False), _utc_now()),
            )

    def enqueue_detail(self, run_id: str, company_scan_id: str, linkedin_company_id: str, linkedin_job_id: str) -> bool:
        with self._lock, self.connection:
            cursor = self.connection.execute(
                "INSERT OR IGNORE INTO detail_queue(run_id, linkedin_job_id, linkedin_company_id, company_scan_id) VALUES (?, ?, ?, ?)",
                (run_id, str(linkedin_job_id), linkedin_company_id, company_scan_id),
            )
            return cursor.rowcount == 1

    def pending_detail_job_ids(self, run_id: str | None = None) -> tuple[str, ...]:
        query = "SELECT DISTINCT linkedin_job_id FROM detail_queue WHERE status='PENDING'"
        params: tuple[object, ...] = ()
        if run_id:
            query += " AND run_id=?"
            params = (run_id,)
        with self._lock:
            rows = self.connection.execute(query, params).fetchall()
        return tuple(row[0] for row in rows)

    def record_detail_attempt(
        self,
        run_id: str,
        linkedin_job_id: str,
        *,
        status: str,
        error_class: str = "",
        detail: Mapping[str, object] | None = None,
        attempt_id: str | None = None,
        attempted_at: str | None = None,
    ) -> str:
        attempt_id = attempt_id or uuid.uuid4().hex
        with self._lock, self.connection:
            self.connection.execute(
                "INSERT INTO detail_attempts(attempt_id, run_id, linkedin_job_id, status, attempted_at, error_class, detail_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (attempt_id, run_id, str(linkedin_job_id), status, attempted_at or _utc_now(), error_class, json.dumps(detail or {})),
            )
            self.connection.execute(
                "UPDATE detail_queue SET status=? WHERE run_id=? AND linkedin_job_id=?",
                ("DONE" if status in {"SUCCESS", "EXCLUDED"} else "RETRY", run_id, str(linkedin_job_id)),
            )
        return attempt_id

    def upsert_catalog_row(self, row: Mapping[str, object]) -> None:
        normalized = _json_row(row)
        company_id = normalized["linkedin_company_id"]
        job_id = normalized["linkedin_job_id"]
        if not company_id or not job_id:
            raise ValueError("catalog rows require company and job IDs")
        now = normalized["last_seen_at"] or _utc_now()
        company_scan_id = _clean(row.get("company_scan_id", ""))
        with self._lock, self.connection:
            previous = self.connection.execute(
                "SELECT row_json FROM job_company_observations WHERE linkedin_company_id=? AND linkedin_job_id=?",
                (company_id, job_id),
            ).fetchone()
            if previous:
                old = json.loads(previous[0])
                company_scan_id = company_scan_id or _clean(old.get("company_scan_id", ""))
                if old.get("first_seen_at"):
                    normalized["first_seen_at"] = old["first_seen_at"]
                if old.get("absence_count") and not normalized["absence_count"]:
                    normalized["absence_count"] = old["absence_count"]
                if old.get("lifecycle_status") and not normalized["lifecycle_status"]:
                    normalized["lifecycle_status"] = old["lifecycle_status"]
            normalized["first_seen_at"] = normalized["first_seen_at"] or now
            normalized["last_seen_at"] = normalized["last_seen_at"] or now
            normalized["absence_count"] = normalized["absence_count"] or "0"
            normalized["lifecycle_status"] = normalized["lifecycle_status"] or "active"
            state_row = dict(normalized)
            if company_scan_id:
                state_row["company_scan_id"] = company_scan_id
            self.connection.execute(
                "INSERT INTO jobs(linkedin_job_id, job_json, updated_at) VALUES (?, ?, ?) ON CONFLICT(linkedin_job_id) DO UPDATE SET job_json=excluded.job_json, updated_at=excluded.updated_at",
                (job_id, json.dumps(normalized, ensure_ascii=False), now),
            )
            self.connection.execute(
                """INSERT INTO job_company_observations(linkedin_company_id, linkedin_job_id, run_id, company_scan_id, ownership_status, first_seen_at, last_seen_at, row_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(linkedin_company_id, linkedin_job_id) DO UPDATE SET
                   run_id=excluded.run_id, company_scan_id=excluded.company_scan_id, ownership_status=excluded.ownership_status,
                   first_seen_at=excluded.first_seen_at, last_seen_at=excluded.last_seen_at, row_json=excluded.row_json""",
                (
                    company_id,
                    job_id,
                    normalized["run_id"],
                    normalized.get("company_scan_id", ""),
                    normalized["ownership_status"],
                    normalized["first_seen_at"],
                    normalized["last_seen_at"],
                    json.dumps(state_row, ensure_ascii=False),
                ),
            )

    def get_catalog_row(self, linkedin_company_id: str, linkedin_job_id: str) -> dict[str, str]:
        with self._lock:
            row = self.connection.execute(
                "SELECT row_json FROM job_company_observations WHERE linkedin_company_id=? AND linkedin_job_id=?",
                (str(linkedin_company_id), str(linkedin_job_id)),
            ).fetchone()
        if row is None:
            raise KeyError((linkedin_company_id, linkedin_job_id))
        return json.loads(row[0])

    def reconcile_lifecycle(
        self,
        linkedin_company_id: str,
        company_scan_id: str,
        scan_status: str,
        observed_job_ids: set[str],
        scan_at: str,
    ) -> int:
        if scan_status not in COMPLETE_SCAN_STATUSES:
            return 0
        newly_inactive = 0
        with self._lock, self.connection:
            rows = self.connection.execute(
                "SELECT linkedin_job_id, row_json FROM job_company_observations WHERE linkedin_company_id=?",
                (str(linkedin_company_id),),
            ).fetchall()
            for row in rows:
                job_id = row[0]
                data = json.loads(row[1])
                event_type = "SEEN" if job_id in observed_job_ids else "ABSENT"
                event_id = uuid.uuid4().hex
                cursor = self.connection.execute(
                    "INSERT OR IGNORE INTO lifecycle_events(event_id, linkedin_company_id, linkedin_job_id, company_scan_id, event_type, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (event_id, str(linkedin_company_id), job_id, company_scan_id, event_type, scan_at),
                )
                if cursor.rowcount != 1:
                    continue
                if event_type == "SEEN":
                    data["last_seen_at"] = scan_at
                    data["last_successful_company_scan_at"] = scan_at
                    data["lifecycle_status"] = "active"
                    data["absence_count"] = "0"
                    data["inactive_reason"] = ""
                    data["inactive_confirmed_at"] = ""
                else:
                    count = int(data.get("absence_count") or 0) + 1
                    data["absence_count"] = str(count)
                    data["last_successful_company_scan_at"] = scan_at
                    if count >= 2 and data.get("lifecycle_status") != "inactive":
                        data["lifecycle_status"] = "inactive"
                        data["inactive_reason"] = "absent_from_two_complete_company_scans"
                        data["inactive_confirmed_at"] = ""
                        newly_inactive += 1
                self.connection.execute(
                    "UPDATE job_company_observations SET row_json=?, last_seen_at=? WHERE linkedin_company_id=? AND linkedin_job_id=?",
                    (
                        json.dumps(
                            {
                                **_json_row(data),
                                **({"company_scan_id": _clean(data.get("company_scan_id", ""))} if data.get("company_scan_id") else {}),
                            },
                            ensure_ascii=False,
                        ),
                        data.get("last_seen_at", ""),
                        str(linkedin_company_id),
                        job_id,
                    ),
                )
        return newly_inactive

    def finish_company_scan(self, company_scan_id: str, status: str, observed_job_ids: Iterable[str], finished_at: str | None = None) -> None:
        with self._lock, self.connection:
            row = self.connection.execute("SELECT linkedin_company_id FROM company_scans WHERE company_scan_id=?", (company_scan_id,)).fetchone()
            if row is None:
                raise KeyError(company_scan_id)
            self.connection.execute(
                "UPDATE company_scans SET status=?, finished_at=?, observed_job_ids_json=? WHERE company_scan_id=?",
                (status, finished_at or _utc_now(), json.dumps(sorted(set(observed_job_ids))), company_scan_id),
            )

    def update_company_scan_status_rows(self, company_scan_id: str, status: str) -> None:
        with self._lock, self.connection:
            rows = self.connection.execute(
                "SELECT linkedin_company_id, linkedin_job_id, row_json FROM job_company_observations WHERE company_scan_id=?",
                (company_scan_id,),
            ).fetchall()
            for row in rows:
                data = json.loads(row[2])
                data["company_scan_status"] = status
                self.connection.execute(
                    "UPDATE job_company_observations SET row_json=? WHERE linkedin_company_id=? AND linkedin_job_id=?",
                    (
                        json.dumps(
                            {
                                **_json_row(data),
                                **({"company_scan_id": _clean(data.get("company_scan_id", ""))} if data.get("company_scan_id") else {}),
                            },
                            ensure_ascii=False,
                        ),
                        row[0],
                        row[1],
                    ),
                )

    def export_catalog_csv(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            rows = self.connection.execute(
                "SELECT row_json FROM job_company_observations ORDER BY linkedin_company_id, linkedin_job_id"
            ).fetchall()
        temporary_name = ""
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False) as handle:
                temporary_name = handle.name
                writer = csv.DictWriter(handle, fieldnames=CATALOG_FIELDS, extrasaction="ignore")
                writer.writeheader()
                for row in rows:
                    data = json.loads(row[0])
                    writer.writerow({field: _clean(data.get(field, "")) for field in CATALOG_FIELDS})
            os.replace(temporary_name, target)
        finally:
            if temporary_name and os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def append_jsonl_records(self, path: str | Path, records: Iterable[Mapping[str, object]]) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            for record in records:
                payload = _redact_payload(dict(record))
                payload.setdefault("schema_version", 1)
                payload.setdefault("record_type", "observation")
                handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def close(self) -> None:
        with self._lock:
            self.connection.close()


def backup_existing_artifacts(output_dir: str | Path) -> tuple[Path, ...]:
    """Copy existing catalog artifacts before a requested rebuild."""

    directory = Path(output_dir)
    if not directory.exists():
        return ()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backed_up: list[Path] = []
    for name in (
        "master_linkedin_jobs.csv",
        "master_linkedin_jobs.jsonl",
        "master_linkedin_jobs_state.db",
        "master_linkedin_jobs_metrics.json",
    ):
        source = directory / name
        if not source.exists():
            continue
        target = directory / f"{name}.backup_{stamp}"
        shutil.copy2(source, target)
        backed_up.append(target)
    return tuple(backed_up)


class InterProcessLock:
    """Prevent overlapping writers for one output catalog."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.handle = None

    def __enter__(self) -> "InterProcessLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        self.handle.seek(0)
        self.handle.write("0")
        self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:  # pragma: no cover - production target is Windows.
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            self.handle.close()
            self.handle = None
            raise RuntimeError(f"Another master LinkedIn jobs run is active: {self.path}") from exc
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - production target is Windows.
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


class CatalogRunner:
    def __init__(self, config: RunnerConfig, *, transport=None, now=_utc_now):
        self.config = config
        self.transport = transport
        self.now = now
        self.store: StateStore | None = None
        self.groups: dict[str, SourceCompanyGroup] = {}
        self.contexts: dict[str, CompanyRunContext] = {}
        self.events: list[dict[str, object]] = []
        self.adaptive = AdaptiveConcurrency(config.workers, config.min_workers, config.max_workers)
        self.metrics: dict[str, object] = {
            "companies_input": 0,
            "companies_selected": 0,
            "companies_completed": 0,
            "companies_partial": 0,
            "companies_failed": 0,
            "requests": 0,
            "proxy_count": 0,
            "valid_cards": 0,
            "malformed_cards": 0,
            "ownership_exclusions": 0,
            "alias_quarantines": 0,
            "detail_successes": 0,
            "detail_failures": 0,
            "jobs_written": 0,
            "inactive_rows": 0,
            "run_id": "",
            "recoverable": True,
        }
        self._metric_lock = threading.Lock()

    def _increment(self, key: str, amount: int = 1) -> None:
        with self._metric_lock:
            self.metrics[key] = int(self.metrics.get(key, 0)) + amount

    def _get(self, url: str, *, kind: str) -> ResponseEnvelope:
        response = self.transport.get(url, kind=kind)
        self._increment("requests")
        if response.status_code == 429:
            self._increment("rate_limited")
        if _blocked_body(response.text):
            self._increment("blocked_responses")
        self.adaptive.observe(status_code=response.status_code, blocked=_blocked_body(response.text))
        return response

    def _persist_exclusion(self, company_id: str, job_id: str, reason: str, observation: Mapping[str, object]) -> None:
        assert self.store is not None
        run_id = str(self.metrics["run_id"])
        self.store.record_exclusion(run_id, company_id, job_id, reason, observation)
        self._increment("ownership_exclusions")
        self.events.append(
            {
                "record_type": "ownership_exclusion",
                "schema_version": 1,
                "run_id": run_id,
                "linkedin_company_id": company_id,
                "linkedin_job_id": job_id,
                "reason": reason,
            }
        )

    def _queue_card(self, context: CompanyRunContext, card: SearchCard) -> None:
        assert self.store is not None
        decision = evaluate_ownership(card.company_url, context.group, self.store.verified_aliases(context.group.linkedin_company_id))
        if decision.status == COMPANY_MATCH_REJECTED:
            self._persist_exclusion(context.group.linkedin_company_id, card.linkedin_job_id, decision.reason, card.__dict__)
            return
        if self.config.mode == "daily" or self.config.resume_run_id:
            try:
                previous = self.store.get_catalog_row(context.group.linkedin_company_id, card.linkedin_job_id)
            except KeyError:
                previous = None
            if previous and previous.get("lifecycle_status") != "inactive" and decision.status in {COMPANY_MATCH_EXACT_PRIMARY, COMPANY_MATCH_VERIFIED_ALIAS}:
                card_changed = any(
                    (
                        previous.get("job_title", "") != card.title,
                        previous.get("location", "") != card.location,
                        previous.get("observed_company_url", "") != decision.canonical_url,
                        previous.get("posted_text", "") != card.posted_text,
                    )
                )
                if not detail_refresh_required(previous.get("detail_last_refreshed_at", ""), self.now(), self.config.detail_refresh_hours, card_changed=card_changed):
                    context.observed_job_ids.add(card.linkedin_job_id)
                    return
        self.store.enqueue_detail(
            str(self.metrics["run_id"]),
            context.scan_id,
            context.group.linkedin_company_id,
            card.linkedin_job_id,
        )

    def _scan_recovery_partition(self, context: CompanyRunContext, partition: RecoveryPartition) -> bool:
        assert self.store is not None
        run_id = str(self.metrics["run_id"])
        partition_id = self.store.start_query_partition(context.scan_id, partition.parameter, partition.value)
        seen_body_hashes: set[str] = set()
        seen_job_sets: set[tuple[str, ...]] = set()
        complete = False
        suspicious_empty_streak = 0
        try:
            for page_start in range(0, self.pagination.max_start + self.pagination.page_step, self.pagination.page_step):
                if self.store.successful_page_exists(run_id, context.group.linkedin_company_id, page_start, partition.parameter):
                    continue
                response = self._get(
                    build_search_url(
                        context.group.linkedin_company_id,
                        start=page_start,
                        partition_type=partition.parameter,
                        partition_value=partition.value,
                    ),
                    kind="search",
                )
                if response.status_code == 400 and page_start >= self.pagination.max_start:
                    complete = True
                    self.store.record_search_page(run_id, context.scan_id, context.group.linkedin_company_id, page_start, status="COMPLETE", job_ids=(), partition_type=partition.parameter, detail={"terminal": "http_400"})
                    break
                if response.status_code == 200 and is_suspicious_empty_body(response.text):
                    body_hash = hashlib.sha256(response.text.encode("utf-8", errors="replace")).hexdigest()
                    self.store.record_search_page(run_id, context.scan_id, context.group.linkedin_company_id, page_start, status="SUSPICIOUS_EMPTY", job_ids=(), partition_type=partition.parameter, body_hash=body_hash, cards=())
                    suspicious_empty_streak += 1
                    if suspicious_empty_streak >= 2:
                        complete = True
                        break
                    continue
                if response.error == "request_budget_exhausted" or classify_http_response(response.status_code, response.text) != "SUCCESS":
                    break
                parsed = parse_search_page(response.text)
                body_hash = hashlib.sha256(response.text.encode("utf-8", errors="replace")).hexdigest()
                if not parsed.is_usable or parsed.is_partial:
                    if is_suspicious_empty_body(response.text):
                        self.store.record_search_page(run_id, context.scan_id, context.group.linkedin_company_id, page_start, status="SUSPICIOUS_EMPTY", job_ids=(), partition_type=partition.parameter, body_hash=body_hash, cards=())
                        suspicious_empty_streak += 1
                        if suspicious_empty_streak >= 2:
                            complete = True
                            break
                        continue
                    self.store.record_search_page(run_id, context.scan_id, context.group.linkedin_company_id, page_start, status="PARTIAL", job_ids=tuple(card.linkedin_job_id for card in parsed.cards), partition_type=partition.parameter, body_hash=body_hash, cards=parsed.cards)
                    for card in parsed.cards:
                        context.card_by_job_id[card.linkedin_job_id] = card
                        context.card_start_by_job_id[card.linkedin_job_id] = page_start
                        context.card_partition_by_job_id[card.linkedin_job_id] = partition.parameter
                        context.card_partition_value_by_job_id[card.linkedin_job_id] = partition.value
                        self._queue_card(context, card)
                    break
                suspicious_empty_streak = 0
                page_job_ids = tuple(sorted(card.linkedin_job_id for card in parsed.cards))
                self.store.record_search_page(run_id, context.scan_id, context.group.linkedin_company_id, page_start, status="COMPLETE", job_ids=page_job_ids, partition_type=partition.parameter, body_hash=body_hash, cards=parsed.cards)
                if not parsed.is_no_results and (body_hash in seen_body_hashes or (page_job_ids and page_job_ids in seen_job_sets)):
                    break
                seen_body_hashes.add(body_hash)
                if page_job_ids:
                    seen_job_sets.add(page_job_ids)
                for card in parsed.cards:
                    context.card_by_job_id[card.linkedin_job_id] = card
                    context.card_start_by_job_id[card.linkedin_job_id] = page_start
                    context.card_partition_by_job_id[card.linkedin_job_id] = partition.parameter
                    context.card_partition_value_by_job_id[card.linkedin_job_id] = partition.value
                    self._queue_card(context, card)
                if parsed.is_no_results or page_start >= self.pagination.max_start:
                    complete = True
                    break
        finally:
            self.store.finish_query_partition(partition_id, "COMPLETE" if complete else "PARTIAL")
        return complete

    def _scan_company(self, group: SourceCompanyGroup) -> CompanyRunContext:
        assert self.store is not None
        run_id = str(self.metrics["run_id"])
        existing_scan_id = self.store.existing_company_scan(run_id, group.linkedin_company_id)
        existing_status = self.store.existing_company_scan_status(run_id, group.linkedin_company_id)
        scan_id = existing_scan_id or self.store.start_company_scan(run_id, group)
        context = CompanyRunContext(group=group, scan_id=scan_id)
        restored_cards = self.store.search_cards_for_run(run_id, group.linkedin_company_id) if existing_scan_id else ()
        for card in restored_cards:
            context.card_by_job_id[card.linkedin_job_id] = card
        if existing_scan_id and existing_status in COMPLETE_SCAN_STATUSES:
            context.search_status = existing_status
            for card in restored_cards:
                context.card_start_by_job_id.setdefault(card.linkedin_job_id, 0)
                context.card_partition_by_job_id.setdefault(card.linkedin_job_id, "base")
                context.card_partition_value_by_job_id.setdefault(card.linkedin_job_id, "")
                self._queue_card(context, card)
            self.contexts[context.scan_id] = context
            return context
        seen_body_hashes: set[str] = set()
        seen_job_sets: set[tuple[str, ...]] = set()
        empty_pages = 0
        suspicious_empty_streak = 0
        candidate_cards = len(context.card_by_job_id)
        try:
            evidence = self.pagination
            for page_start in range(0, evidence.max_start + evidence.page_step, evidence.page_step):
                if self.store.successful_page_exists(run_id, group.linkedin_company_id, page_start):
                    cards = self.store.search_cards_for_run(run_id, group.linkedin_company_id)
                    page_job_ids = set(self.store.page_job_ids(run_id, group.linkedin_company_id, page_start))
                    for card in cards:
                        if page_job_ids and card.linkedin_job_id not in page_job_ids:
                            continue
                        context.card_by_job_id[card.linkedin_job_id] = card
                        context.card_start_by_job_id.setdefault(card.linkedin_job_id, page_start)
                        context.card_partition_by_job_id.setdefault(card.linkedin_job_id, "base")
                        context.card_partition_value_by_job_id.setdefault(card.linkedin_job_id, "")
                        self._queue_card(context, card)
                    continue
                url = build_search_url(group.linkedin_company_id, start=page_start)
                response = self._get(url, kind="search")
                if response.error == "request_budget_exhausted":
                    context.search_status = "BUDGET_EXHAUSTED"
                    self.store.record_search_page(run_id, scan_id, group.linkedin_company_id, page_start, status=context.search_status, job_ids=())
                    break
                if response.status_code == 200 and is_suspicious_empty_body(response.text):
                    body_hash = hashlib.sha256(response.text.encode("utf-8", errors="replace")).hexdigest()
                    self.store.record_search_page(run_id, scan_id, group.linkedin_company_id, page_start, status="SUSPICIOUS_EMPTY", job_ids=(), body_hash=body_hash, detail={"body_class": "suspicious_empty"})
                    suspicious_empty_streak += 1
                    if suspicious_empty_streak >= 2:
                        context.search_status = "COMPLETE" if candidate_cards else "COMPLETE_ZERO_CONFIRMED"
                        break
                    continue
                classification = classify_http_response(response.status_code, response.text)
                if response.status_code == 400 and page_start >= evidence.max_start:
                    context.search_status = "COMPLETE"
                    self.store.record_search_page(run_id, scan_id, group.linkedin_company_id, page_start, status="COMPLETE", job_ids=(), detail={"terminal": "http_400"})
                    break
                if classification != "SUCCESS":
                    context.search_status = {
                        "BLOCKED": "BLOCKED",
                        "RATE_LIMITED": "RATE_LIMITED",
                        "RETRYABLE": "PARTIAL_PAGE_ANOMALY",
                    }.get(classification, "PARTIAL_PAGE_ANOMALY")
                    self.store.record_search_page(run_id, scan_id, group.linkedin_company_id, page_start, status=context.search_status, job_ids=(), detail={"classification": classification})
                    break
                parsed = parse_search_page(response.text)
                body_hash = hashlib.sha256(response.text.encode("utf-8", errors="replace")).hexdigest()
                if not parsed.is_usable:
                    if is_suspicious_empty_body(response.text):
                        self.store.record_search_page(run_id, scan_id, group.linkedin_company_id, page_start, status="SUSPICIOUS_EMPTY", job_ids=(), body_hash=body_hash, detail={"body_class": parsed.body_class})
                        suspicious_empty_streak += 1
                        if suspicious_empty_streak >= 2:
                            context.search_status = "COMPLETE" if candidate_cards else "COMPLETE_ZERO_CONFIRMED"
                            break
                        continue
                    context.search_status = "PARTIAL_PAGE_ANOMALY"
                    self.store.record_search_page(run_id, scan_id, group.linkedin_company_id, page_start, status=context.search_status, job_ids=(), body_hash=body_hash, detail={"body_class": parsed.body_class})
                    break
                suspicious_empty_streak = 0
                self._increment("valid_cards", len(parsed.cards))
                self._increment("malformed_cards", len(parsed.malformed_cards))
                if parsed.is_partial:
                    context.search_status = "PARTIAL_PAGE_ANOMALY"
                elif context.search_status == "RUNNING":
                    context.search_status = "COMPLETE"
                self.store.record_search_page(
                    run_id,
                    scan_id,
                    group.linkedin_company_id,
                    page_start,
                    status="PARTIAL" if parsed.is_partial else "COMPLETE",
                    job_ids=tuple(card.linkedin_job_id for card in parsed.cards),
                    body_hash=body_hash,
                    detail={"no_results": parsed.is_no_results, "malformed_cards": parsed.malformed_cards},
                    cards=parsed.cards,
                )
                page_job_ids = tuple(sorted(card.linkedin_job_id for card in parsed.cards))
                if not parsed.is_no_results and (body_hash in seen_body_hashes or (page_job_ids and page_job_ids in seen_job_sets)):
                    context.search_status = "SATURATED_UNRESOLVED"
                    break
                seen_body_hashes.add(body_hash)
                if page_job_ids:
                    seen_job_sets.add(page_job_ids)
                if parsed.is_no_results:
                    empty_pages += 1
                    context.no_results = candidate_cards == 0
                    if empty_pages >= 2 or page_start >= evidence.max_start:
                        if context.search_status == "COMPLETE":
                            context.search_status = "COMPLETE_ZERO_CONFIRMED" if candidate_cards == 0 else "COMPLETE"
                        break
                    continue
                empty_pages = 0
                candidate_cards = len(context.card_by_job_id)
                for card in parsed.cards:
                    context.card_by_job_id[card.linkedin_job_id] = card
                    context.card_start_by_job_id[card.linkedin_job_id] = page_start
                    context.card_partition_by_job_id[card.linkedin_job_id] = "base"
                    context.card_partition_value_by_job_id[card.linkedin_job_id] = ""
                    self._queue_card(context, card)
                if page_start >= evidence.max_start:
                    context.search_status = "SATURATED_UNRESOLVED"
                    break
            if context.search_status == "RUNNING":
                context.search_status = "COMPLETE_ZERO_CONFIRMED" if not candidate_cards else "COMPLETE"
            base_was_saturated = context.search_status == "SATURATED_UNRESOLVED"
            if context.search_status in {"SATURATED_UNRESOLVED", "PARTIAL_PAGE_ANOMALY"} and self.recovery_partitions:
                recovery_complete = all(self._scan_recovery_partition(context, partition) for partition in self.recovery_partitions)
                if recovery_complete and base_was_saturated:
                    context.search_status = "SATURATED_RECOVERED"
        except Exception as exc:  # the scan remains resumable and is never treated as empty
            context.search_status = "BLOCKED"
            self.events.append(
                {
                    "record_type": "company_scan_error",
                    "schema_version": 1,
                    "run_id": run_id,
                    "linkedin_company_id": group.linkedin_company_id,
                    "error_class": type(exc).__name__,
                }
            )
        self.contexts[context.scan_id] = context
        return context

    def _process_detail(self, entry: sqlite3.Row) -> None:
        assert self.store is not None
        run_id = str(self.metrics["run_id"])
        company_id = str(entry["linkedin_company_id"])
        job_id = str(entry["linkedin_job_id"])
        context = next((item for item in self.contexts.values() if item.group.linkedin_company_id == company_id), None)
        if context is None:
            self.store.record_detail_attempt(run_id, job_id, status="FAILED", error_class="missing_company_context")
            self._increment("detail_failures")
            return
        card = context.card_by_job_id.get(job_id)
        if card is None:
            cards = self.store.search_cards_for_run(run_id, company_id)
            card = next((item for item in cards if item.linkedin_job_id == job_id), None)
        if card is None:
            self.store.record_detail_attempt(run_id, job_id, status="FAILED", error_class="missing_search_card")
            context.detail_failures += 1
            self._increment("detail_failures")
            return
        response = self._get(f"{DETAIL_ENDPOINT}/{job_id}", kind="detail")
        if response.error == "request_budget_exhausted" or response.status_code != 200 or _blocked_body(response.text):
            self.store.record_detail_attempt(run_id, job_id, status="FAILED", error_class=classify_http_response(response.status_code, response.text))
            context.detail_failures += 1
            self._increment("detail_failures")
            return
        detail = parse_job_detail(job_id, response.text)
        aliases = self.store.verified_aliases(company_id)
        decision = evaluate_card_detail_ownership(card.company_url, detail.company_url, context.group, aliases)
        if decision.status == COMPANY_MATCH_ALIAS_PENDING:
            slug = canonical_company_slug(detail.company_url)
            alias_response = self._get(f"{COMPANY_ENDPOINT}/{slug}", kind="company") if slug else ResponseEnvelope(0, "", "", 0.0, "missing_alias_slug")
            if alias_response.status_code == 200 and alias_evidence_matches(alias_response.text, company_id):
                self.store.record_alias(company_id, slug, status=COMPANY_MATCH_VERIFIED_ALIAS, verification_method="company_page_numeric_id", seen_at=self.now())
                decision = evaluate_card_detail_ownership(card.company_url, detail.company_url, context.group, (slug,))
            else:
                self.store.record_alias(company_id, slug, status=COMPANY_MATCH_ALIAS_PENDING, verification_method="company_page_unverified", seen_at=self.now())
                self._increment("alias_quarantines")
        if decision.status not in {COMPANY_MATCH_EXACT_PRIMARY, COMPANY_MATCH_VERIFIED_ALIAS}:
            self.store.record_detail_attempt(run_id, job_id, status="EXCLUDED", error_class=decision.reason, detail=detail.__dict__)
            self._persist_exclusion(company_id, job_id, decision.reason, {"card": card.__dict__, "detail": detail.__dict__})
            return
        location_classification, location_reason = classify_germany_location(detail.location or card.location)
        if location_classification not in {
            LOCATION_GERMANY_CONFIRMED,
            LOCATION_REMOTE_GERMANY_ELIGIBLE,
            LOCATION_MULTI_LOCATION_INCLUDES_GERMANY,
        }:
            self.store.record_detail_attempt(run_id, job_id, status="EXCLUDED", error_class=location_classification, detail=detail.__dict__)
            self._persist_exclusion(company_id, job_id, location_classification, detail.__dict__)
            return
        observed_at = self.now()
        row = {field: "" for field in CATALOG_FIELDS}
        row.update(
            {
                "canonical_company_id": context.group.primary_canonical_company_id,
                "linkedin_company_id": company_id,
                "source_company_name": context.group.source_company_name,
                "source_company_url": context.group.primary_company_url,
                "source_company_ids": "|".join(context.group.source_company_ids),
                "source_company_names": "|".join(context.group.source_company_names),
                "source_company_urls": "|".join(context.group.source_company_urls),
                "observed_company_name": detail.company_name or card.company_name,
                "observed_company_url": decision.canonical_url,
                "linkedin_job_id": job_id,
                "job_title": detail.title or card.title,
                "linkedin_job_url": card.linkedin_job_url or f"https://www.linkedin.com/jobs/view/{job_id}",
                "apply_url_raw": detail.apply_url_raw,
                "apply_url_canonical": detail.apply_url_canonical,
                "apply_url_source": detail.apply_url_source,
                "description": detail.description,
                "location": detail.location or card.location,
                "posted_text": detail.posted_text or card.posted_text,
                "posted_at_estimated": detail.posted_at_estimated or card.posted_at_estimated,
                "easy_apply_status": detail.easy_apply_status,
                "applicant_count": detail.applicant_count,
                "employment_type": detail.employment_type,
                "workplace_type": detail.workplace_type,
                "first_seen_at": observed_at,
                "last_seen_at": observed_at,
                "last_successful_company_scan_at": observed_at,
                "detail_last_refreshed_at": observed_at,
                "lifecycle_status": "active",
                "absence_count": "0",
                "content_hash": compute_content_hash(
                    {
                        "job_title": detail.title or card.title,
                        "description": detail.description,
                        "location": detail.location or card.location,
                        "employment_type": detail.employment_type,
                        "workplace_type": detail.workplace_type,
                        "canonical_apply_url": detail.apply_url_canonical,
                        "observed_company_url": decision.canonical_url,
                    }
                ),
                "source_endpoint": build_search_url(
                    company_id,
                    start=context.card_start_by_job_id.get(job_id, 0),
                    partition_type=context.card_partition_by_job_id.get(job_id, "base"),
                    partition_value=context.card_partition_value_by_job_id.get(job_id, ""),
                ),
                "transport": "webshare",
                "search_pagination_start": str(context.card_start_by_job_id.get(job_id, 0)),
                "search_status_code": "200",
                "detail_status_code": str(response.status_code),
                "company_match_status": decision.status,
                "ownership_status": decision.status,
                "ownership_alias_status": decision.status if decision.status == COMPANY_MATCH_VERIFIED_ALIAS else "",
                "location_classification": location_classification,
                "location_classification_reason": location_reason,
                "company_scan_status": context.search_status,
                "query_partition_type": context.card_partition_by_job_id.get(job_id, "base"),
                "query_partition_value": context.card_partition_value_by_job_id.get(job_id, ""),
                "run_id": run_id,
                "company_scan_id": context.scan_id,
            }
        )
        self.store.upsert_catalog_row(row)
        self.store.record_detail_attempt(run_id, job_id, status="SUCCESS", detail=detail.__dict__)
        context.observed_job_ids.add(job_id)
        self._increment("detail_successes")
        self._increment("jobs_written")
        self.events.append({"record_type": "job_observation", "schema_version": 1, "run_id": run_id, **row})

    def run(self) -> dict[str, object]:
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        if self.config.dry_run:
            return self._run_without_lock()
        with InterProcessLock(output_dir / ".master_linkedin_jobs.lock"):
            return self._run_without_lock()

    def _run_without_lock(self) -> dict[str, object]:
        input_path = Path(self.config.input_csv)
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        if not input_path.exists():
            raise FileNotFoundError(input_path)
        self.groups, source_stats = load_source_company_groups(input_path, self.config.company_id)
        self.metrics.update({"companies_input": source_stats["groups"], "rows_read": source_stats["rows_read"], "rows_accepted": source_stats["rows_accepted"], "rows_rejected": source_stats["rows_rejected"]})
        self.pagination = load_pagination_evidence(self.config.pagination_report)
        if self.config.filters_report and Path(self.config.filters_report).exists():
            self.recovery_partitions = build_recovery_partitions(self.config.filters_report)
        else:
            self.recovery_partitions = ()
        if self.transport is None:
            proxies = load_webshare_proxies()
            self.metrics["proxy_count"] = len(proxies)
            self.transport = WebshareTransport(
                proxies,
                timeout=self.config.timeout,
                retry_limit=self.config.retry_limit,
                max_requests=self.config.max_requests,
                per_proxy_concurrency=self.config.per_proxy_concurrency,
            )
        else:
            self.metrics["proxy_count"] = len(getattr(self.transport, "proxies", ())) or 1
        selected = list(self.groups.values())
        if self.config.max_companies is not None:
            selected = selected[: max(0, int(self.config.max_companies))]
        elif self.config.mode == "smoke":
            selected = selected[:1]
        elif self.config.mode == "pilot":
            selected = selected[:25]
        self.metrics["companies_selected"] = len(selected)
        if self.config.dry_run or self.config.mode in {"validate", "reconcile"}:
            if self.config.mode == "reconcile":
                self.store = StateStore(output_dir / "master_linkedin_jobs_state.db")
                self.store.export_catalog_csv(output_dir / "master_linkedin_jobs.csv")
                self.store.close()
            self.metrics["dry_run"] = bool(self.config.dry_run or self.config.mode == "validate")
            self._write_metrics(output_dir)
            return dict(self.metrics)
        if self.config.fresh:
            backup_existing_artifacts(output_dir)
            for name in ("master_linkedin_jobs_state.db", "master_linkedin_jobs.csv", "master_linkedin_jobs.jsonl", "master_linkedin_jobs_metrics.json"):
                target = output_dir / name
                if target.exists():
                    target.unlink()
        input_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
        run_id = self.config.resume_run_id or datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%S%fZ")
        self.metrics["run_id"] = run_id
        self.store = StateStore(output_dir / "master_linkedin_jobs_state.db")
        self.store.start_run(run_id, mode=self.config.mode, input_sha256=input_hash)
        try:
            if selected:
                worker_count = min(max(1, self.config.workers), len(selected))
                with ThreadPoolExecutor(max_workers=worker_count) as executor:
                    futures = [executor.submit(self._scan_company, group) for group in selected]
                    for future in as_completed(futures):
                        future.result()
            detail_entries = self.store.get_detail_queue_entries(run_id)
            if detail_entries:
                detail_worker_count = min(max(1, self.config.detail_workers), len(detail_entries))
                with ThreadPoolExecutor(max_workers=detail_worker_count) as executor:
                    futures = [executor.submit(self._process_detail, entry) for entry in detail_entries]
                    for future in as_completed(futures):
                        future.result()
            for context in self.contexts.values():
                status = context.search_status
                if context.detail_failures and status in COMPLETE_SCAN_STATUSES:
                    status = "PARTIAL_DETAIL_FAILURES"
                if status == "RUNNING":
                    status = "BLOCKED"
                self.store.finish_company_scan(context.scan_id, status, context.observed_job_ids, self.now())
                self.store.update_company_scan_status_rows(context.scan_id, status)
                self._increment(
                    "inactive_rows",
                    self.store.reconcile_lifecycle(
                        context.group.linkedin_company_id,
                        context.scan_id,
                        status,
                        context.observed_job_ids,
                        self.now(),
                    ),
                )
                if status in COMPLETE_SCAN_STATUSES:
                    self._increment("companies_completed")
                elif status in {"BLOCKED", "RATE_LIMITED", "BUDGET_EXHAUSTED"}:
                    self._increment("companies_failed")
                else:
                    self._increment("companies_partial")
            self.store.export_catalog_csv(output_dir / "master_linkedin_jobs.csv")
            self.store.append_jsonl_records(output_dir / "master_linkedin_jobs.jsonl", self.events)
            self.metrics["requests"] = getattr(self.transport, "_request_count", self.metrics["requests"])
            self.store.finish_run(run_id, "FINISHED")
            self._write_metrics(output_dir)
            log_path = output_dir / f"master_linkedin_jobs_{run_id}.log"
            log_path.write_text(json.dumps({key: value for key, value in self.metrics.items() if "password" not in key.lower() and "secret" not in key.lower()}, sort_keys=True) + "\n", encoding="utf-8")
            return dict(self.metrics)
        except BaseException as exc:
            run_status = "INTERRUPTED" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "FAILED"
            self.store.finish_run(run_id, run_status)
            self.metrics["run_status"] = run_status
            self.metrics["error_class"] = type(exc).__name__
            try:
                self._write_metrics(output_dir)
            except OSError:
                pass
            raise
        finally:
            self.store.close()

    def _write_metrics(self, output_dir: Path) -> None:
        (output_dir / "master_linkedin_jobs_metrics.json").write_text(json.dumps(self.metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect Germany-scoped LinkedIn jobs by verified company ID.")
    parser.add_argument("--input-csv", type=Path, default=RunnerConfig.input_csv)
    parser.add_argument("--output-dir", type=Path, default=RunnerConfig.output_dir)
    parser.add_argument("--pagination-report", type=Path, default=RunnerConfig.pagination_report)
    parser.add_argument("--filters-report", type=Path, default=RunnerConfig.filters_report)
    parser.add_argument("--mode", choices=("validate", "smoke", "pilot", "full", "daily", "reconcile"), default="full")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--detail-workers", type=int, default=5)
    parser.add_argument("--per-proxy-concurrency", type=int, default=1)
    parser.add_argument("--min-workers", type=int, default=1)
    parser.add_argument("--max-workers", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retry-limit", type=int, default=2)
    parser.add_argument("--max-requests", type=int, default=0)
    parser.add_argument("--detail-refresh-hours", type=float, default=24.0)
    parser.add_argument("--company-id")
    parser.add_argument("--resume-run-id")
    parser.add_argument("--max-companies", type=int)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def config_from_args(args: argparse.Namespace) -> RunnerConfig:
    return RunnerConfig(
        input_csv=args.input_csv,
        output_dir=args.output_dir,
        pagination_report=args.pagination_report,
        filters_report=args.filters_report,
        mode=args.mode,
        workers=args.workers,
        detail_workers=args.detail_workers,
        per_proxy_concurrency=args.per_proxy_concurrency,
        min_workers=args.min_workers,
        max_workers=args.max_workers,
        timeout=args.timeout,
        retry_limit=args.retry_limit,
        max_requests=args.max_requests or None,
        detail_refresh_hours=args.detail_refresh_hours,
        company_id=args.company_id,
        resume_run_id=args.resume_run_id,
        fresh=args.fresh,
        dry_run=args.dry_run,
        max_companies=args.max_companies,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    metrics = CatalogRunner(config_from_args(args)).run()
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
