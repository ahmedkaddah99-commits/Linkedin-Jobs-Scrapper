"""Durable Germany-scoped LinkedIn guest-endpoint job catalog.

The module deliberately keeps parsing and identity decisions available as pure
functions.  The command-line runner and network transport are defined below
those helpers so tests can exercise the trust boundary without network access.

Refresh policy: search/card evidence is checked every source cycle. New jobs or
changed card evidence fetch detail immediately. Unchanged detail is considered
durable-fresh for seven days by default; applicant/freshness fields are marked
stale after 24 hours but retain their last observation timestamp because the
current guest endpoint has no separate volatile-only detail endpoint. Source
disappearance is reconciled from the search scan independently of detail reuse.
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
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
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
COMPANY_MATCH_AMBIGUOUS = "AMBIGUOUS_OWNERSHIP"

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
    "applicant_count_observed_at",
    "volatile_fields_status",
    "detail_refresh_reason",
    "lifecycle_status",
    "absence_count",
    "inactive_reason",
    "inactive_confirmed_at",
    "content_hash",
    "card_evidence_hash",
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
DEFAULT_DETAIL_ATTEMPT_BUDGET = 3
DEFAULT_ALIAS_VERIFICATION_ATTEMPT_BUDGET = 3
DEFAULT_DURABLE_DETAIL_REFRESH_HOURS = 24.0 * 7
DEFAULT_VOLATILE_DETAIL_REFRESH_HOURS = 24.0

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
    source_company_pairs: tuple[tuple[str, str], ...] = ()

    @property
    def primary_company_url(self) -> str:
        return f"https://www.linkedin.com/company/{self.primary_slug}"

    @property
    def source_company_name(self) -> str:
        return self.source_company_names[0] if self.source_company_names else ""

    @property
    def source_slugs(self) -> tuple[str, ...]:
        return tuple(slug for slug in (canonical_company_slug(url) for url in self.source_company_urls) if slug)

    @property
    def source_slug_to_canonical_ids(self) -> dict[str, tuple[str, ...]]:
        """Map observed source slugs without guessing through a collision."""

        mapping: dict[str, list[str]] = {}
        pairs = self.source_company_pairs or tuple(zip(self.source_company_urls, self.source_company_ids))
        for url, company_id in pairs:
            slug = canonical_company_slug(url)
            if not slug or _is_placeholder(company_id):
                continue
            mapping.setdefault(slug, []).append(company_id)
        return {slug: tuple(dict.fromkeys(ids)) for slug, ids in mapping.items()}

    def canonical_company_id_for_slug(self, slug: object) -> str:
        normalized = canonical_company_slug(slug) or _clean(slug).lower()
        ids = self.source_slug_to_canonical_ids.get(normalized, ())
        return ids[0] if len(ids) == 1 else ""


@dataclass(frozen=True)
class OwnershipDecision:
    status: str
    canonical_url: str
    reason: str
    canonical_company_id: str = ""


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
class DetailRefreshDecision:
    required: bool
    reason: str
    volatile_fields_stale: bool = False


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
    """Shared account limiter whose value gates actual network requests.

    ``workers`` remains the compatibility-facing adaptive account limit.  The
    condition below is the important part: changing that value changes who can
    enter the request path even when caller thread pools already exist.
    Provider limits can be supplied for a shared limiter used by multiple
    collectors; all providers still consume the same account-wide budget.
    """

    def __init__(
        self,
        initial: int = 10,
        minimum: int = 1,
        maximum: int = 20,
        *,
        provider_limits: Mapping[str, int] | None = None,
    ):
        self.minimum = max(1, int(minimum))
        self.maximum = max(self.minimum, int(maximum))
        self._workers = min(self.maximum, max(self.minimum, int(initial)))
        self._provider_limits = {
            str(provider): max(1, min(self.maximum, int(limit)))
            for provider, limit in (provider_limits or {}).items()
        }
        self._healthy_observations = 0
        self._condition = threading.Condition()
        self._in_flight = 0
        self._provider_in_flight: dict[str, int] = {}
        self._peak_in_flight = 0

    @property
    def workers(self) -> int:
        with self._condition:
            return self._workers

    @workers.setter
    def workers(self, value: int) -> None:
        with self._condition:
            self._workers = max(self.minimum, min(self.maximum, int(value)))
            self._condition.notify_all()

    @property
    def in_flight(self) -> int:
        with self._condition:
            return self._in_flight

    @property
    def peak_in_flight(self) -> int:
        with self._condition:
            return self._peak_in_flight

    def set_provider_limit(self, provider: str, limit: int) -> None:
        with self._condition:
            self._provider_limits[str(provider)] = max(1, min(self.maximum, int(limit)))
            self._condition.notify_all()

    def acquire(self, provider: str = "default") -> None:
        provider = str(provider or "default")
        with self._condition:
            while (
                self._in_flight >= self._workers
                or self._provider_in_flight.get(provider, 0)
                >= self._provider_limits.get(provider, self._workers)
            ):
                self._condition.wait()
            self._in_flight += 1
            self._provider_in_flight[provider] = self._provider_in_flight.get(provider, 0) + 1
            self._peak_in_flight = max(self._peak_in_flight, self._in_flight)

    def release(self, provider: str = "default") -> None:
        provider = str(provider or "default")
        with self._condition:
            self._in_flight = max(0, self._in_flight - 1)
            current = max(0, self._provider_in_flight.get(provider, 0) - 1)
            if current:
                self._provider_in_flight[provider] = current
            else:
                self._provider_in_flight.pop(provider, None)
            self._condition.notify_all()

    def observe(self, *, status_code: int | None, blocked: bool, provider: str = "default") -> int:
        provider = str(provider or "default")
        with self._condition:
            if blocked or status_code == 429 or (status_code is not None and status_code >= 500):
                self._workers = max(self.minimum, self._workers - 1)
                if provider in self._provider_limits:
                    self._provider_limits[provider] = max(self.minimum, self._provider_limits[provider] - 1)
                self._healthy_observations = 0
            elif status_code is not None and 200 <= status_code < 400:
                self._healthy_observations += 1
                if self._healthy_observations >= 20:
                    self._workers = min(self.maximum, self._workers + 1)
                    if provider in self._provider_limits:
                        self._provider_limits[provider] = min(self.maximum, self._provider_limits[provider] + 1)
                    self._healthy_observations = 0
            self._condition.notify_all()
            return self._workers


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
    detail_refresh_hours: float = DEFAULT_DURABLE_DETAIL_REFRESH_HOURS
    volatile_refresh_hours: float = DEFAULT_VOLATILE_DETAIL_REFRESH_HOURS
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
    recovery_required: bool = False
    recovery_partition_statuses: dict[str, str] | None = None
    detail_failures: int = 0
    no_results: bool = False

    def __post_init__(self) -> None:
        self.card_by_job_id = self.card_by_job_id or {}
        self.card_start_by_job_id = self.card_start_by_job_id or {}
        self.card_partition_by_job_id = self.card_partition_by_job_id or {}
        self.card_partition_value_by_job_id = self.card_partition_value_by_job_id or {}
        self.observed_job_ids = self.observed_job_ids or set()
        self.recovery_partition_statuses = self.recovery_partition_statuses or {}



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
    numeric_organization_ids: set[str] = set()
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
            if not _COMPANY_ID_RE.fullmatch(company_id):
                rows_rejected += 1
                continue
            if company_id_filter and company_id != str(company_id_filter):
                continue
            numeric_organization_ids.add(company_id)
            if not company_url:
                rows_rejected += 1
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
            source_company_pairs=tuple(
                (row.linkedin_company_url, row.canonical_company_id)
                for row in unique_rows
                if not _is_placeholder(row.canonical_company_id)
            ),
        )
    return groups, {
        "rows_read": rows_read,
        "rows_accepted": rows_accepted,
        "rows_rejected": rows_rejected,
        "groups": len(groups),
        "stored_source_groups": len(groups),
        "unique_numeric_organizations": len(numeric_organization_ids),
    }


def build_input_loader_reconciliation_report(
    reported_numeric_organization_count: int,
    loader_stats: Mapping[str, Any],
    *,
    excluded_count: int = 0,
    unprocessed_count: int = 0,
    historical_count: int = 0,
    scan_count: int | None = None,
) -> dict[str, Any]:
    """Reconcile an input aggregate with loader output without inventing tasks.

    The loader's distinct eligible groups are the current task denominator.
    Aggregate scan totals are retained as historical context only; they never
    become synthetic source groups or retry work.
    """

    reported = max(0, int(reported_numeric_organization_count))
    stored = max(0, int(loader_stats.get("stored_source_groups", loader_stats.get("groups", 0)) or 0))
    difference = reported - stored
    missing = max(0, difference)
    categories = {
        "excluded": min(missing, max(0, int(excluded_count))),
        "unprocessed": min(
            max(0, missing - min(missing, max(0, int(excluded_count)))),
            max(0, int(unprocessed_count)),
        ),
        "historical": min(
            max(
                0,
                missing
                - min(missing, max(0, int(excluded_count)))
                - min(
                    max(0, missing - min(missing, max(0, int(excluded_count)))),
                    max(0, int(unprocessed_count)),
                ),
            ),
            max(0, int(historical_count)),
        ),
    }
    categories["unknown"] = max(0, missing - sum(categories.values()))
    return {
        "schema_version": "linkedin_input_loader_reconciliation_v1",
        "reported_numeric_organizations": reported,
        "stored_source_groups": stored,
        "difference": difference,
        "missing_from_current_loader": missing,
        "delta_classification": categories,
        "loader_stats": dict(loader_stats),
        "scan_count": None if scan_count is None else max(0, int(scan_count)),
        "scan_count_is_current_unique_denominator": False,
        "synthetic_tasks_created": 0,
        "status": (
            "reconciled"
            if difference == 0
            else "classified"
            if difference > 0 and categories["unknown"] == 0
            else "overrepresented_loader"
            if difference < 0
            else "requires_explanation"
        ),
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
    source_ids = group.source_slug_to_canonical_ids.get(slug, ())
    if source_ids:
        if len(source_ids) != 1:
            return OwnershipDecision(COMPANY_MATCH_AMBIGUOUS, observed_canonical, "source_slug_maps_to_multiple_canonical_ids")
        status = COMPANY_MATCH_EXACT_PRIMARY if slug == group.primary_slug else COMPANY_MATCH_EXACT_PRIMARY
        return OwnershipDecision(status, observed_canonical, "primary_slug_match" if slug == group.primary_slug else "source_mapping_slug_match", source_ids[0])
    if slug in aliases:
        if len(group.source_company_ids) > 1:
            return OwnershipDecision(COMPANY_MATCH_AMBIGUOUS, observed_canonical, "verified_alias_has_ambiguous_source_ownership")
        return OwnershipDecision(COMPANY_MATCH_VERIFIED_ALIAS, observed_canonical, "verified_alias_match", group.primary_canonical_company_id)
    if slug:
        if len(group.source_company_ids) > 1:
            return OwnershipDecision(COMPANY_MATCH_AMBIGUOUS, observed_canonical, "unverified_slug_has_ambiguous_source_ownership")
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


def classify_http_response(status_code: int, body: str, error: str = "") -> str:
    if _clean(error):
        if error == "request_budget_exhausted":
            return "BUDGET_EXHAUSTED"
        return "RETRYABLE"
    if int(status_code) <= 0:
        return "RETRYABLE"
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
    if not value or _blocked_body(value):
        return False
    if re.search(r"jobs-search-no-results|no jobs found", value, flags=re.IGNORECASE):
        return False
    return len(value) < 200


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
    try:
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
    finally:
        session.close()
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
        request_limiter: AdaptiveConcurrency | None = None,
        provider: str = "linkedin",
        cooldown_base_seconds: float = 5.0,
    ):
        self.proxies = tuple(proxies)
        if not self.proxies:
            raise ValueError("at least one Webshare proxy is required")
        self.timeout = float(timeout)
        self.retry_limit = max(0, int(retry_limit))
        self.max_requests = max_requests
        self.sleep = sleep
        self.request_limiter = request_limiter or AdaptiveConcurrency(
            initial=max(1, int(per_proxy_concurrency) * len(self.proxies)),
            minimum=1,
            maximum=max(1, int(per_proxy_concurrency) * len(self.proxies)),
        )
        self.provider = str(provider or "linkedin")
        self.cooldown_base_seconds = max(0.1, float(cooldown_base_seconds))
        self._next_proxy = 0
        self._request_count = 0
        self._lock = threading.Lock()
        self._session_lock = threading.Lock()
        self._sessions: dict[tuple[int, str], requests.Session] = {}
        self._proxy_health: dict[str, dict[str, object]] = {
            proxy.identifier: {
                "proxy_id": proxy.identifier,
                "request_count": 0,
                "success_count": 0,
                "rate_limited_count": 0,
                "blocked_count": 0,
                "consecutive_failure_count": 0,
                "cooldown_until": "",
                "last_status_code": 0,
                "last_error_class": "",
                "last_request_at": "",
            }
            for proxy in self.proxies
        }
        self._cooldown_until: dict[str, float] = {proxy.identifier: 0.0 for proxy in self.proxies}
        self._closed = False
        self._proxy_locks = {proxy.identifier: threading.BoundedSemaphore(max(1, int(per_proxy_concurrency))) for proxy in self.proxies}

    def _take_proxy(self) -> WebshareProxy | None:
        while True:
            wait_seconds = 0.0
            with self._lock:
                if self._closed:
                    return None
                if self.max_requests is not None and self._request_count >= self.max_requests:
                    return None
                now = time.monotonic()
                available = [
                    proxy
                    for proxy in self.proxies
                    if self._cooldown_until.get(proxy.identifier, 0.0) <= now
                ]
                if available:
                    proxy = available[self._next_proxy % len(available)]
                    self._next_proxy += 1
                    self._request_count += 1
                    self._proxy_health[proxy.identifier]["request_count"] = int(
                        self._proxy_health[proxy.identifier]["request_count"]
                    ) + 1
                    return proxy
                wait_seconds = max(0.0, min(self._cooldown_until.values()) - now)
            if wait_seconds:
                self.sleep(wait_seconds)

    def _session_for(self, proxy: WebshareProxy) -> requests.Session:
        key = (threading.get_ident(), proxy.identifier)
        with self._session_lock:
            session = self._sessions.get(key)
            if session is None:
                session = requests.Session()
                session.trust_env = False
                session.headers.update(
                    {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml",
                    }
                )
                self._sessions[key] = session
            return session

    def _record_proxy_result(self, proxy: WebshareProxy, response: ResponseEnvelope) -> None:
        blocked = _blocked_body(response.text)
        rate_limited = response.status_code == 429
        failed = bool(response.error) or rate_limited or blocked or response.status_code >= 500
        now = _utc_now()
        with self._lock:
            health = self._proxy_health[proxy.identifier]
            health["last_status_code"] = int(response.status_code)
            health["last_error_class"] = _clean(response.error)
            health["last_request_at"] = now
            if rate_limited:
                health["rate_limited_count"] = int(health["rate_limited_count"]) + 1
            if blocked:
                health["blocked_count"] = int(health["blocked_count"]) + 1
            if 200 <= response.status_code < 400 and not blocked and not response.error:
                health["success_count"] = int(health["success_count"]) + 1
            if failed:
                failures = int(health["consecutive_failure_count"]) + 1
                health["consecutive_failure_count"] = failures
                cooldown_seconds = min(300.0, self.cooldown_base_seconds * (2 ** (failures - 1)))
                self._cooldown_until[proxy.identifier] = time.monotonic() + cooldown_seconds
                health["cooldown_until"] = (
                    datetime.now(timezone.utc) + timedelta(seconds=cooldown_seconds)
                ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            else:
                health["consecutive_failure_count"] = 0
                self._cooldown_until[proxy.identifier] = 0.0
                health["cooldown_until"] = ""

    def proxy_health_snapshot(self) -> tuple[dict[str, object], ...]:
        with self._lock:
            return tuple(dict(value) for value in self._proxy_health.values())

    def get(self, url: str, *, kind: str) -> ResponseEnvelope:
        last = ResponseEnvelope(0, "", "", 0.0, "request_budget_exhausted")
        for attempt in range(self.retry_limit + 1):
            proxy = self._take_proxy()
            if proxy is None:
                return last
            started = time.monotonic()
            with self._proxy_locks[proxy.identifier]:
                self.request_limiter.acquire(self.provider)
                try:
                    session = self._session_for(proxy)
                    try:
                        response = session.get(url, proxies={"http": proxy.url, "https": proxy.url}, timeout=self.timeout)
                        elapsed = time.monotonic() - started
                        last = ResponseEnvelope(response.status_code, response.text, proxy.identifier, elapsed)
                        should_retry = response.status_code == 429 or response.status_code >= 500 or _blocked_body(response.text)
                    except requests.RequestException:
                        elapsed = time.monotonic() - started
                        last = ResponseEnvelope(0, "", proxy.identifier, elapsed, "network_error")
                        should_retry = True
                finally:
                    self.request_limiter.release(self.provider)
            self._record_proxy_result(proxy, last)
            if not should_retry or attempt >= self.retry_limit:
                return last
            self.sleep(min(30.0, 0.5 * (2**attempt)) + 0.1 * (attempt + 1))
        return last

    def close(self) -> None:
        with self._session_lock:
            self._closed = True
            sessions = tuple(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.close()

    def __enter__(self) -> "WebshareTransport":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


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
    if card.status == COMPANY_MATCH_AMBIGUOUS or detail.status == COMPANY_MATCH_AMBIGUOUS:
        return OwnershipDecision(COMPANY_MATCH_AMBIGUOUS, detail.canonical_url, "card_or_detail_ownership_is_ambiguous")
    accepted = {COMPANY_MATCH_EXACT_PRIMARY, COMPANY_MATCH_VERIFIED_ALIAS}
    if card.status in accepted and detail.status in accepted:
        if COMPANY_MATCH_VERIFIED_ALIAS in {card.status, detail.status}:
            return OwnershipDecision(COMPANY_MATCH_VERIFIED_ALIAS, detail.canonical_url, "card_detail_verified_alias_match", card.canonical_company_id or detail.canonical_company_id)
        return OwnershipDecision(COMPANY_MATCH_EXACT_PRIMARY, detail.canonical_url, "card_detail_primary_match", card.canonical_company_id or detail.canonical_company_id)
    return OwnershipDecision(COMPANY_MATCH_ALIAS_PENDING, detail.canonical_url, "card_detail_alias_pending_verification", card.canonical_company_id or detail.canonical_company_id)


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


def compute_card_evidence_hash(card: SearchCard, canonical_observed_company_url: object = "") -> str:
    values = (
        _clean(card.title),
        _clean(card.company_name),
        canonical_company_url(canonical_observed_company_url or card.company_url),
        _clean(card.location),
        _clean(card.posted_text),
        _clean(card.posted_at_estimated),
    )
    return hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _retry_due_at(timestamp: str, attempt_count: int) -> str:
    parsed = _parse_timestamp(timestamp) or datetime.now(timezone.utc)
    delay_seconds = min(3600, 60 * (2 ** max(0, int(attempt_count) - 1)))
    return (parsed + timedelta(seconds=delay_seconds)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def detail_refresh_decision(
    previous: Mapping[str, object] | None,
    card: SearchCard,
    observed_company_url: object,
    now: object,
    *,
    durable_refresh_hours: float = DEFAULT_DURABLE_DETAIL_REFRESH_HOURS,
    volatile_refresh_hours: float = DEFAULT_VOLATILE_DETAIL_REFRESH_HOURS,
) -> DetailRefreshDecision:
    """Choose detail reuse without treating a daily scan as a full refresh.

    The current endpoint returns durable and volatile fields together. Volatile
    fields therefore become explicitly stale after their shorter window and are
    retained with their observation timestamp until the bounded durable refresh.
    """

    if not previous:
        return DetailRefreshDecision(True, "new_job")
    current_card_hash = compute_card_evidence_hash(card, observed_company_url)
    previous_card_hash = _clean(previous.get("card_evidence_hash"))
    card_changed = bool(previous_card_hash and previous_card_hash != current_card_hash)
    if not previous_card_hash:
        return DetailRefreshDecision(True, "card_evidence_missing")
    if card_changed:
        return DetailRefreshDecision(True, "card_changed")
    refreshed = _parse_timestamp(previous.get("detail_last_refreshed_at"))
    current = _parse_timestamp(now)
    if refreshed is None or current is None:
        return DetailRefreshDecision(True, "missing_refresh_timestamp")
    age_hours = (current - refreshed).total_seconds() / 3600
    volatile_observed = _parse_timestamp(previous.get("applicant_count_observed_at")) or refreshed
    volatile_age_hours = (current - volatile_observed).total_seconds() / 3600
    volatile_stale = volatile_age_hours >= float(volatile_refresh_hours)
    if age_hours >= float(durable_refresh_hours):
        return DetailRefreshDecision(True, "durable_ttl_expired", volatile_stale)
    return DetailRefreshDecision(False, "volatile_fields_stale_reused" if volatile_stale else "cache_hit_fresh", volatile_stale)


def union_job_ids(partitions: Iterable[Iterable[object]]) -> tuple[str, ...]:
    values = {str(value).strip() for partition in partitions for value in partition if str(value).strip()}
    return tuple(sorted(values, key=lambda value: (not value.isdigit(), int(value) if value.isdigit() else value)))


class JsonlEventJournal:
    """Append event records in bounded batches instead of retaining a run list."""

    def __init__(self, path: str | Path, *, batch_size: int = 128):
        self.path = Path(path)
        self.batch_size = max(1, int(batch_size))
        self._handle = None
        self._pending = 0
        self.records_written = 0

    def append(self, record: Mapping[str, object]) -> None:
        if self._handle is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self.path.open("a", encoding="utf-8", newline="\n")
        payload = _redact_payload(dict(record))
        if not isinstance(payload, dict):
            payload = {"record": payload}
        payload.setdefault("schema_version", 1)
        payload.setdefault("record_type", "observation")
        self._handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        self._pending += 1
        self.records_written += 1
        if self._pending >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if self._handle is None or not self._pending:
            return
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._pending = 0

    def close(self) -> None:
        if self._handle is None:
            return
        try:
            self.flush()
        finally:
            self._handle.close()
            self._handle = None


GENERATION_POINTER_NAME = "master_linkedin_jobs_generation.json"
GENERATION_DIRECTORY_NAME = "generations"
GENERATION_ARTIFACT_NAMES = (
    "master_linkedin_jobs.csv",
    "master_linkedin_jobs.jsonl",
    "master_linkedin_jobs_metrics.json",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def write_catalog_generation_manifest(
    output_dir: str | Path,
    *,
    generation_id: str,
    run_id: str,
    input_sha256: str,
    status: str,
    run_outcome: str = "",
    published: bool = False,
) -> dict[str, object]:
    """Describe one immutable output generation without changing its files."""

    root = Path(output_dir)
    generation_dir = root / GENERATION_DIRECTORY_NAME / str(generation_id)
    generation_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, object] = {}
    for name in GENERATION_ARTIFACT_NAMES:
        path = generation_dir / name
        if not path.exists():
            path.touch()
        artifacts[name] = {
            "path": str(path.relative_to(root)).replace(os.sep, "/"),
            "sha256": _sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
    manifest = {
        "manifest_schema_version": 1,
        "generation_id": str(generation_id),
        "run_id": str(run_id or ""),
        "input_sha256": str(input_sha256 or ""),
        "status": str(status or "unknown"),
        "run_outcome": str(run_outcome or ""),
        "published": bool(published),
        "created_at": _utc_now(),
        "artifacts": artifacts,
    }
    _atomic_write_json(generation_dir / "manifest.json", manifest)
    return manifest


def publish_catalog_generation(
    output_dir: str | Path,
    *,
    generation_id: str,
    run_id: str,
    input_sha256: str,
    run_status: str,
    run_outcome: str,
) -> dict[str, object]:
    """Publish a complete generation through one pointer transition.

    The generation directory is immutable after this function returns. Root
    artifact names are compatibility aliases; readers that need a coherent
    snapshot must resolve ``master_linkedin_jobs_generation.json`` first.
    """

    root = Path(output_dir)
    generation_dir = root / GENERATION_DIRECTORY_NAME / str(generation_id)
    manifest = write_catalog_generation_manifest(
        root,
        generation_id=generation_id,
        run_id=run_id,
        input_sha256=input_sha256,
        status=run_status,
        run_outcome=run_outcome,
        published=True,
    )
    manifest_path = generation_dir / "manifest.json"
    manifest_hash = _sha256_file(manifest_path)
    pointer = {
        "pointer_schema_version": 1,
        "generation_id": str(generation_id),
        "manifest_path": str(manifest_path.relative_to(root)).replace(os.sep, "/"),
        "manifest_sha256": manifest_hash,
        "published_at": _utc_now(),
    }
    # The pointer is the only publication transition.  Compatibility aliases
    # are copied from already-complete generation files and never form the
    # authoritative read path.
    _atomic_write_json(root / GENERATION_POINTER_NAME, pointer)
    for name in GENERATION_ARTIFACT_NAMES:
        source = generation_dir / name
        target = root / name
        temporary_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                "wb", dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False
            ) as handle:
                temporary_name = handle.name
                with source.open("rb") as source_handle:
                    shutil.copyfileobj(source_handle, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, target)
        finally:
            if temporary_name and os.path.exists(temporary_name):
                os.unlink(temporary_name)
    return {**manifest, "manifest_sha256": manifest_hash, "manifest_path": pointer["manifest_path"]}


def read_current_catalog_generation(output_dir: str | Path) -> dict[str, object] | None:
    """Read and hash-check the generation selected by the publication pointer."""

    root = Path(output_dir)
    pointer_path = root / GENERATION_POINTER_NAME
    if not pointer_path.exists():
        return None
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    manifest_path = root / str(pointer["manifest_path"])
    if _sha256_file(manifest_path) != str(pointer.get("manifest_sha256") or ""):
        raise ValueError("catalog generation pointer hash mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if str(manifest.get("generation_id") or "") != str(pointer.get("generation_id") or ""):
        raise ValueError("catalog generation pointer identity mismatch")
    for item in (manifest.get("artifacts") or {}).values():
        artifact = root / str(item["path"])
        if _sha256_file(artifact) != str(item["sha256"]):
            raise ValueError(f"catalog generation artifact hash mismatch: {artifact.name}")
    return {"pointer": pointer, "manifest": manifest}


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
        self._transaction_state = threading.local()
        self._initialize_schema()

    @contextmanager
    def _write_transaction(self):
        """Serialize writes and let nested operations share one commit."""

        with self._lock:
            depth = int(getattr(self._transaction_state, "depth", 0))
            if depth:
                yield
                return
            self._transaction_state.depth = 1
            try:
                with self.connection:
                    yield
            finally:
                self._transaction_state.depth = 0

    @contextmanager
    def batch(self):
        """Commit a small acknowledged batch atomically.

        Callers should keep the scope to local DB mutations only.  If the
        process fails before the scope exits, SQLite rolls the batch back and
        the durable scan/detail queue can replay it.
        """

        with self._write_transaction():
            yield

    def _initialize_schema(self) -> None:
        with self._lock, self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    input_sha256 TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'RUNNING',
                    finished_at TEXT NOT NULL DEFAULT ''
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
                    verification_attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_verification_attempts INTEGER NOT NULL DEFAULT 3,
                    next_verification_at TEXT NOT NULL DEFAULT '',
                    verification_terminal_status TEXT NOT NULL DEFAULT '',
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
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    last_attempt_at TEXT NOT NULL DEFAULT '',
                    last_error_class TEXT NOT NULL DEFAULT '',
                    terminal_status TEXT NOT NULL DEFAULT '',
                    refresh_reason TEXT NOT NULL DEFAULT '',
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
                    consecutive_failure_count INTEGER NOT NULL DEFAULT 0,
                    cooldown_until TEXT NOT NULL DEFAULT '',
                    last_status_code INTEGER NOT NULL DEFAULT 0,
                    last_error_class TEXT NOT NULL DEFAULT '',
                    last_request_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column("runs", "finished_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("company_slug_aliases", "verification_attempt_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("company_slug_aliases", "max_verification_attempts", "INTEGER NOT NULL DEFAULT 3")
            self._ensure_column("company_slug_aliases", "next_verification_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("company_slug_aliases", "verification_terminal_status", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("detail_queue", "attempt_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("detail_queue", "max_attempts", "INTEGER NOT NULL DEFAULT 3")
            self._ensure_column("detail_queue", "last_attempt_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("detail_queue", "last_error_class", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("detail_queue", "terminal_status", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("detail_queue", "refresh_reason", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("proxy_health", "consecutive_failure_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("proxy_health", "cooldown_until", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("proxy_health", "last_status_code", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("proxy_health", "last_error_class", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("proxy_health", "last_request_at", "TEXT NOT NULL DEFAULT ''")
            self._migrate_retry_dispositions()
            self._repair_duplicate_company_scans()
            self.connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_company_scans_run_company ON company_scans(run_id, linkedin_company_id)"
            )
            self._backfill_observation_scan_ids()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {str(row[1]) for row in self.connection.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            self.connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _migrate_retry_dispositions(self) -> None:
        """Give legacy retry rows an explicit bounded disposition on reopen."""

        rows = self.connection.execute(
            "SELECT run_id, linkedin_job_id, attempt_count, max_attempts, status, next_attempt_at FROM detail_queue WHERE status='RETRY'"
        ).fetchall()
        for row in rows:
            attempts = int(row[2] or 0)
            if attempts == 0:
                attempts = int(
                    self.connection.execute(
                        "SELECT COUNT(*) FROM detail_attempts WHERE run_id=? AND linkedin_job_id=? AND status NOT IN ('SUCCESS', 'EXCLUDED')",
                        (str(row[0]), str(row[1])),
                    ).fetchone()[0]
                    or 0
                )
            max_attempts = max(1, int(row[3] or DEFAULT_DETAIL_ATTEMPT_BUDGET))
            if attempts >= max_attempts:
                self.connection.execute(
                    "UPDATE detail_queue SET attempt_count=?, max_attempts=?, next_attempt_at='', terminal_status='ATTEMPT_BUDGET_EXHAUSTED', status='QUARANTINED' WHERE run_id=? AND linkedin_job_id=?",
                    (attempts, max_attempts, str(row[0]), str(row[1])),
                )
            elif not _clean(row[5]):
                self.connection.execute(
                    "UPDATE detail_queue SET attempt_count=?, max_attempts=?, next_attempt_at=? WHERE run_id=? AND linkedin_job_id=?",
                    (attempts, max_attempts, _utc_now(), str(row[0]), str(row[1])),
                )

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
                "INSERT OR IGNORE INTO runs(run_id, mode, input_sha256, started_at, status, finished_at) VALUES (?, ?, ?, ?, 'RUNNING', '')",
                (run_id, mode, input_sha256, timestamp),
            )
            self.connection.execute(
                "UPDATE runs SET status='RUNNING', finished_at='' WHERE run_id=?",
                (str(run_id),),
            )
        return run_id

    def finish_run(self, run_id: str, status: str = "FINISHED", finished_at: str | None = None) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                "UPDATE runs SET status=?, finished_at=? WHERE run_id=?",
                (status, finished_at or _utc_now(), str(run_id)),
            )

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
        now = _utc_now()
        with self._lock:
            return tuple(
                self.connection.execute(
                    """SELECT * FROM detail_queue
                       WHERE run_id=? AND (
                           status='PENDING'
                           OR (status='RETRY' AND attempt_count < max_attempts AND (next_attempt_at='' OR next_attempt_at<=?))
                       ) ORDER BY linkedin_job_id""",
                    (run_id, now),
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
                   ON CONFLICT(linkedin_company_id, slug) DO UPDATE SET status=excluded.status, last_seen_at=excluded.last_seen_at, verification_method=excluded.verification_method,
                       verification_terminal_status=CASE WHEN excluded.status='VERIFIED_ALIAS_MATCH' THEN '' ELSE company_slug_aliases.verification_terminal_status END""",
                (str(linkedin_company_id), str(slug), status, timestamp, timestamp, verification_method),
            )

    def alias_verification_due(self, linkedin_company_id: str, slug: str, now: str | None = None) -> bool:
        with self._lock:
            row = self.connection.execute(
                "SELECT status, verification_attempt_count, max_verification_attempts, next_verification_at, verification_terminal_status FROM company_slug_aliases WHERE linkedin_company_id=? AND slug=?",
                (str(linkedin_company_id), str(slug)),
            ).fetchone()
        if row is None:
            return True
        if row[0] == COMPANY_MATCH_VERIFIED_ALIAS or row[4]:
            return False
        return int(row[1] or 0) < max(1, int(row[2] or DEFAULT_ALIAS_VERIFICATION_ATTEMPT_BUDGET)) and (
            not _clean(row[3]) or _clean(row[3]) <= (now or _utc_now())
        )

    def begin_alias_verification(self, linkedin_company_id: str, slug: str, *, seen_at: str | None = None) -> bool:
        timestamp = seen_at or _utc_now()
        with self._lock, self.connection:
            row = self.connection.execute(
                "SELECT verification_attempt_count, max_verification_attempts, status, verification_terminal_status FROM company_slug_aliases WHERE linkedin_company_id=? AND slug=?",
                (str(linkedin_company_id), str(slug)),
            ).fetchone()
            attempts = int(row[0] or 0) if row else 0
            maximum = max(1, int(row[1] or DEFAULT_ALIAS_VERIFICATION_ATTEMPT_BUDGET)) if row else DEFAULT_ALIAS_VERIFICATION_ATTEMPT_BUDGET
            if row and (row[2] == COMPANY_MATCH_VERIFIED_ALIAS or row[3] or attempts >= maximum):
                return False
            attempts += 1
            exhausted = attempts >= maximum
            next_at = "" if exhausted else _retry_due_at(timestamp, attempts)
            terminal_status = "ATTEMPT_BUDGET_EXHAUSTED" if exhausted else ""
            self.connection.execute(
                """INSERT INTO company_slug_aliases(linkedin_company_id, slug, status, first_seen_at, last_seen_at, verification_method, verification_attempt_count, max_verification_attempts, next_verification_at, verification_terminal_status)
                   VALUES (?, ?, ?, ?, ?, '', ?, ?, ?, ?)
                   ON CONFLICT(linkedin_company_id, slug) DO UPDATE SET status=excluded.status, last_seen_at=excluded.last_seen_at, verification_attempt_count=excluded.verification_attempt_count, max_verification_attempts=excluded.max_verification_attempts, next_verification_at=excluded.next_verification_at, verification_terminal_status=excluded.verification_terminal_status""",
                (str(linkedin_company_id), str(slug), COMPANY_MATCH_ALIAS_PENDING, timestamp, timestamp, attempts, maximum, next_at, terminal_status),
            )
        return True

    def alias_verification_counts(self) -> dict[str, int]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT status, verification_terminal_status, COUNT(*) FROM company_slug_aliases GROUP BY status, verification_terminal_status"
            ).fetchall()
        counts: dict[str, int] = {}
        for status, terminal, count in rows:
            key = str(terminal or status).lower()
            counts[key] = counts.get(key, 0) + int(count)
        return counts

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

    def upsert_proxy_health(
        self,
        rows: Iterable[Mapping[str, object]],
        *,
        updated_at: str | None = None,
    ) -> int:
        timestamp = updated_at or _utc_now()
        values = []
        for row in rows:
            proxy_id = _clean(row.get("proxy_id"))
            if not proxy_id:
                continue
            values.append(
                (
                    proxy_id,
                    int(row.get("request_count") or 0),
                    int(row.get("success_count") or 0),
                    int(row.get("rate_limited_count") or 0),
                    int(row.get("blocked_count") or 0),
                    int(row.get("consecutive_failure_count") or 0),
                    _clean(row.get("cooldown_until")),
                    int(row.get("last_status_code") or 0),
                    _clean(row.get("last_error_class")),
                    _clean(row.get("last_request_at")),
                    timestamp,
                )
            )
        if not values:
            return 0
        with self._write_transaction():
            self.connection.executemany(
                """INSERT INTO proxy_health(
                       proxy_id, request_count, success_count, rate_limited_count,
                       blocked_count, consecutive_failure_count, cooldown_until,
                       last_status_code, last_error_class, last_request_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(proxy_id) DO UPDATE SET
                       request_count=excluded.request_count,
                       success_count=excluded.success_count,
                       rate_limited_count=excluded.rate_limited_count,
                       blocked_count=excluded.blocked_count,
                       consecutive_failure_count=excluded.consecutive_failure_count,
                       cooldown_until=excluded.cooldown_until,
                       last_status_code=excluded.last_status_code,
                       last_error_class=excluded.last_error_class,
                       last_request_at=excluded.last_request_at,
                       updated_at=excluded.updated_at""",
                values,
            )
        return len(values)

    def enqueue_detail(
        self,
        run_id: str,
        company_scan_id: str,
        linkedin_company_id: str,
        linkedin_job_id: str,
        *,
        refresh_reason: str = "",
    ) -> bool:
        with self._lock, self.connection:
            cursor = self.connection.execute(
                "INSERT OR IGNORE INTO detail_queue(run_id, linkedin_job_id, linkedin_company_id, company_scan_id, refresh_reason) VALUES (?, ?, ?, ?, ?)",
                (run_id, str(linkedin_job_id), linkedin_company_id, company_scan_id, str(refresh_reason or "")),
            )
            return cursor.rowcount == 1

    def pending_detail_job_ids(self, run_id: str | None = None) -> tuple[str, ...]:
        now = _utc_now()
        query = """SELECT DISTINCT linkedin_job_id FROM detail_queue
                   WHERE (status='PENDING' OR (status='RETRY' AND attempt_count < max_attempts AND (next_attempt_at='' OR next_attempt_at<=?)))"""
        params: tuple[object, ...] = (now,)
        if run_id:
            query += " AND run_id=?"
            params = (now, run_id)
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
        max_attempts: int | None = None,
        next_attempt_at: str | None = None,
    ) -> str:
        attempt_id = attempt_id or uuid.uuid4().hex
        timestamp = attempted_at or _utc_now()
        with self._write_transaction():
            queue_row = self.connection.execute(
                "SELECT attempt_count, max_attempts FROM detail_queue WHERE run_id=? AND linkedin_job_id=?",
                (str(run_id), str(linkedin_job_id)),
            ).fetchone()
            current_attempts = int(queue_row[0] or 0) if queue_row else 0
            budget = max(1, int(max_attempts or (queue_row[1] if queue_row else DEFAULT_DETAIL_ATTEMPT_BUDGET) or DEFAULT_DETAIL_ATTEMPT_BUDGET))
            attempt_number = current_attempts + 1 if status not in {"SUCCESS", "EXCLUDED"} else current_attempts
            self.connection.execute(
                "INSERT INTO detail_attempts(attempt_id, run_id, linkedin_job_id, status, attempted_at, error_class, detail_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (attempt_id, run_id, str(linkedin_job_id), status, timestamp, error_class, json.dumps(detail or {})),
            )
            if queue_row:
                if status in {"SUCCESS", "EXCLUDED"}:
                    queue_status = "DONE"
                    terminal_status = status
                    due_at = ""
                elif attempt_number >= budget:
                    queue_status = "QUARANTINED"
                    terminal_status = "ATTEMPT_BUDGET_EXHAUSTED"
                    due_at = ""
                else:
                    queue_status = "RETRY"
                    terminal_status = ""
                    due_at = next_attempt_at or _retry_due_at(timestamp, attempt_number)
                self.connection.execute(
                    """UPDATE detail_queue SET status=?, next_attempt_at=?, attempt_count=?, max_attempts=?, last_attempt_at=?, last_error_class=?, terminal_status=?
                       WHERE run_id=? AND linkedin_job_id=?""",
                    (queue_status, due_at, attempt_number if status not in {"SUCCESS", "EXCLUDED"} else current_attempts, budget, timestamp, error_class, terminal_status, run_id, str(linkedin_job_id)),
                )
        return attempt_id

    def detail_queue_counts(self, run_id: str) -> dict[str, int]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT status, COUNT(*) FROM detail_queue WHERE run_id=? GROUP BY status",
                (str(run_id),),
            ).fetchall()
        return {str(status).lower(): int(count) for status, count in rows}

    def record_detail_cache_hit(
        self,
        linkedin_company_id: str,
        linkedin_job_id: str,
        *,
        refresh_reason: str,
        volatile_fields_stale: bool,
        card_evidence_hash: str = "",
        run_id: str = "",
        company_scan_id: str = "",
        observed_at: str = "",
    ) -> None:
        with self._write_transaction():
            previous = self.connection.execute(
                "SELECT row_json, run_id, company_scan_id, last_seen_at FROM job_company_observations WHERE linkedin_company_id=? AND linkedin_job_id=?",
                (str(linkedin_company_id), str(linkedin_job_id)),
            ).fetchone()
            if previous is None:
                return
            data = json.loads(previous[0])
            data["detail_refresh_reason"] = str(refresh_reason)
            data["volatile_fields_status"] = "STALE" if volatile_fields_stale else "FRESH"
            if card_evidence_hash:
                data["card_evidence_hash"] = card_evidence_hash
            if run_id:
                data["run_id"] = str(run_id)
            if company_scan_id:
                data["company_scan_id"] = str(company_scan_id)
            if observed_at:
                data["last_seen_at"] = str(observed_at)
                data["last_successful_company_scan_at"] = str(observed_at)
            current_run_id = str(run_id or previous[1] or data.get("run_id") or "")
            current_scan_id = str(company_scan_id or previous[2] or data.get("company_scan_id") or "")
            current_last_seen = str(observed_at or previous[3] or data.get("last_seen_at") or "")
            payload = json.dumps(
                {
                    **_json_row(data),
                    **({"company_scan_id": _clean(data.get("company_scan_id", ""))} if data.get("company_scan_id") else {}),
                },
                ensure_ascii=False,
            )
            self.connection.execute(
                "UPDATE jobs SET job_json=? WHERE linkedin_job_id=?",
                (json.dumps(_json_row(data), ensure_ascii=False), str(linkedin_job_id)),
            )
            self.connection.execute(
                "UPDATE job_company_observations SET run_id=?, company_scan_id=?, last_seen_at=?, row_json=? WHERE linkedin_company_id=? AND linkedin_job_id=?",
                (current_run_id, current_scan_id, current_last_seen, payload, str(linkedin_company_id), str(linkedin_job_id)),
            )

    def upsert_catalog_row(self, row: Mapping[str, object]) -> None:
        normalized = _json_row(row)
        company_id = normalized["linkedin_company_id"]
        job_id = normalized["linkedin_job_id"]
        if not company_id or not job_id:
            raise ValueError("catalog rows require company and job IDs")
        now = normalized["last_seen_at"] or _utc_now()
        company_scan_id = _clean(row.get("company_scan_id", ""))
        with self._write_transaction():
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
                        data["inactive_confirmed_at"] = scan_at
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

    def audit_legacy_consistency(self) -> dict[str, object]:
        """Read-only audit of historical scan evidence before expiry is enabled."""

        with self._lock:
            scans = self.connection.execute(
                "SELECT company_scan_id, run_id, linkedin_company_id, status, finished_at, observed_job_ids_json FROM company_scans ORDER BY started_at, company_scan_id"
            ).fetchall()
            suspicious_pages = int(
                self.connection.execute("SELECT COUNT(*) FROM search_pages WHERE status='SUSPICIOUS_EMPTY'").fetchone()[0]
            )
            retry_rows = self.connection.execute(
                "SELECT status, next_attempt_at, attempt_count, max_attempts FROM detail_queue WHERE status IN ('RETRY', 'QUARANTINED')"
            ).fetchall()
            alias_rows = self.connection.execute(
                "SELECT status, verification_terminal_status FROM company_slug_aliases"
            ).fetchall()
            audit_rows: list[dict[str, object]] = []
            for scan in scans:
                scan_id = str(scan[0])
                pages = self.connection.execute(
                    "SELECT query_partition_type, page_start, status, job_ids_json FROM search_pages WHERE company_scan_id=? ORDER BY query_partition_type, page_start",
                    (scan_id,),
                ).fetchall()
                page_statuses = [str(page[2]) for page in pages]
                observed = tuple(json.loads(scan[5] or "[]"))
                is_zero = str(scan[3]) == "COMPLETE_ZERO_CONFIRMED" and not observed
                has_suspicious = any(status == "SUSPICIOUS_EMPTY" for status in page_statuses)
                has_partial = any(status not in {"COMPLETE", "COMPLETE_ZERO_CONFIRMED"} for status in page_statuses)
                explicit_key = bool(scan_id and str(scan[1]) and str(scan[2]))
                qualifying_absence = bool(is_zero and explicit_key and pages and not has_suspicious and not has_partial)
                audit_rows.append(
                    {
                        "scan_key": {
                            "run_id": str(scan[1]),
                            "company_scan_id": scan_id,
                            "linkedin_company_id": str(scan[2]),
                        },
                        "status": str(scan[3]),
                        "finished_at": str(scan[4] or ""),
                        "observed_job_ids": list(observed),
                        "page_count": len(pages),
                        "page_statuses": page_statuses,
                        "qualifying_absence": qualifying_absence,
                        "revalidation_required": bool(is_zero and not qualifying_absence),
                    }
                )
            return {
                "read_only": True,
                "scan_count": len(audit_rows),
                "zero_scan_count": sum(row["status"] == "COMPLETE_ZERO_CONFIRMED" for row in audit_rows),
                "suspicious_empty_page_count": suspicious_pages,
                "qualifying_absence_count": sum(bool(row["qualifying_absence"]) for row in audit_rows),
                "revalidation_required_zero_scan_count": sum(bool(row["revalidation_required"]) for row in audit_rows),
                "scans": audit_rows,
                "detail_retry_count": sum(str(row[0]) == "RETRY" for row in retry_rows),
                "detail_retry_missing_due_count": sum(str(row[0]) == "RETRY" and not _clean(row[1]) for row in retry_rows),
                "detail_quarantined_count": sum(str(row[0]) == "QUARANTINED" for row in retry_rows),
                "alias_pending_count": sum(str(row[0]) == COMPANY_MATCH_ALIAS_PENDING and not str(row[1]) for row in alias_rows),
                "alias_terminal_count": sum(bool(str(row[1])) for row in alias_rows),
            }

    def export_catalog_csv(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_name = ""
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False) as handle:
                temporary_name = handle.name
                writer = csv.DictWriter(handle, fieldnames=CATALOG_FIELDS, extrasaction="ignore")
                writer.writeheader()
                with self._lock:
                    cursor = self.connection.execute(
                        "SELECT row_json FROM job_company_observations ORDER BY linkedin_company_id, linkedin_job_id"
                    )
                    for row in cursor:
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
    def __init__(self, config: RunnerConfig, *, transport=None, request_limiter: AdaptiveConcurrency | None = None, now=_utc_now):
        self.config = config
        self.transport = transport
        self.now = now
        self.store: StateStore | None = None
        self.groups: dict[str, SourceCompanyGroup] = {}
        self.contexts: dict[str, CompanyRunContext] = {}
        self.events = deque(maxlen=256)
        self._event_journal: JsonlEventJournal | None = None
        self._generation_dir: Path | None = None
        self._alias_lock = threading.Lock()
        self.adaptive = request_limiter or AdaptiveConcurrency(config.workers, config.min_workers, config.max_workers)
        self.metrics: dict[str, object] = {
            "companies_input": 0,
            "input_loader_reconciliation": {},
            "companies_selected": 0,
            "companies_completed": 0,
            "companies_partial": 0,
            "companies_failed": 0,
            "companies_zero_confirmed": 0,
            "requests": 0,
            "proxy_count": 0,
            "proxy_health_rows": 0,
            "account_peak_in_flight": 0,
            "valid_cards": 0,
            "malformed_cards": 0,
            "ownership_exclusions": 0,
            "alias_quarantines": 0,
            "detail_successes": 0,
            "detail_failures": 0,
            "detail_requests": 0,
            "detail_cache_hits": 0,
            "detail_avoided_requests": 0,
            "detail_refresh_requests": 0,
            "detail_volatile_stale_rows": 0,
            "detail_refresh_reasons": {},
            "detail_provider_credits": None,
            "detail_provider_cost": None,
            "detail_provider_cost_status": "not_reported_by_transport",
            "jobs_written": 0,
            "inactive_rows": 0,
            "pending_detail_retries": 0,
            "quarantined_detail_rows": 0,
            "suspicious_empty_companies": 0,
            "recovery_partitions_required": 0,
            "recovery_partitions_completed": 0,
            "recovery_partitions_pending": 0,
            "recovery_partitions_partial": 0,
            "scan_status_counts": {},
            "run_status": "RUNNING",
            "run_outcome": "",
            "run_id": "",
            "generation_id": "",
            "generation_manifest_sha256": "",
            "recoverable": True,
        }
        self._metric_lock = threading.Lock()

    def _increment(self, key: str, amount: int = 1) -> None:
        with self._metric_lock:
            self.metrics[key] = int(self.metrics.get(key, 0)) + amount

    def _record_refresh_reason(self, reason: str) -> None:
        with self._metric_lock:
            reasons = self.metrics.setdefault("detail_refresh_reasons", {})
            if isinstance(reasons, dict):
                reasons[reason] = int(reasons.get(reason, 0)) + 1

    def _capture_detail_provider_usage(self) -> None:
        credits = getattr(self.transport, "provider_credits_used", getattr(self.transport, "credits_used", None))
        cost = getattr(self.transport, "provider_cost", getattr(self.transport, "cost", None))
        if credits is not None:
            self.metrics["detail_provider_credits"] = credits
        if cost is not None:
            self.metrics["detail_provider_cost"] = cost
        if credits is not None or cost is not None:
            self.metrics["detail_provider_cost_status"] = "reported_by_transport"

    def _record_event(self, record: Mapping[str, object]) -> None:
        self.events.append(dict(record))
        if self._event_journal is not None:
            self._event_journal.append(record)

    def _persist_proxy_health(self) -> None:
        if self.store is None or self.transport is None:
            return
        snapshot = getattr(self.transport, "proxy_health_snapshot", None)
        if not callable(snapshot):
            return
        self.metrics["proxy_health_rows"] = self.store.upsert_proxy_health(snapshot())

    def _close_transport(self) -> None:
        close = getattr(self.transport, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                self.metrics["transport_close_error"] = True

    def _update_recovery_metrics(self) -> None:
        required_recovery = sum(
            len(self.recovery_partitions)
            for context in self.contexts.values()
            if context.recovery_required
        )
        completed_recovery = sum(
            sum(status == "COMPLETE" for status in context.recovery_partition_statuses.values())
            for context in self.contexts.values()
        )
        attempted_recovery = sum(
            len(context.recovery_partition_statuses)
            for context in self.contexts.values()
        )
        self.metrics["recovery_partitions_required"] = required_recovery
        self.metrics["recovery_partitions_completed"] = completed_recovery
        self.metrics["recovery_partitions_pending"] = max(0, required_recovery - attempted_recovery)
        self.metrics["recovery_partitions_partial"] = max(0, attempted_recovery - completed_recovery)

    def _get(self, url: str, *, kind: str) -> ResponseEnvelope:
        response = self.transport.get(url, kind=kind)
        self._increment("requests")
        if kind == "detail":
            self._increment("detail_requests")
        if response.status_code == 429:
            self._increment("rate_limited")
        if _blocked_body(response.text):
            self._increment("blocked_responses")
        self.adaptive.observe(status_code=response.status_code, blocked=_blocked_body(response.text), provider="linkedin")
        return response

    def _persist_exclusion(self, company_id: str, job_id: str, reason: str, observation: Mapping[str, object]) -> None:
        assert self.store is not None
        run_id = str(self.metrics["run_id"])
        self.store.record_exclusion(run_id, company_id, job_id, reason, observation)
        self._increment("ownership_exclusions")
        self._record_event(
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
        if decision.status in {COMPANY_MATCH_REJECTED, COMPANY_MATCH_AMBIGUOUS}:
            self._persist_exclusion(context.group.linkedin_company_id, card.linkedin_job_id, decision.reason, card.__dict__)
            return
        refresh_reason = "new_job"
        if self.config.mode == "daily" or self.config.resume_run_id:
            try:
                previous = self.store.get_catalog_row(context.group.linkedin_company_id, card.linkedin_job_id)
            except KeyError:
                previous = None
            if previous and previous.get("lifecycle_status") != "inactive" and decision.status in {COMPANY_MATCH_EXACT_PRIMARY, COMPANY_MATCH_VERIFIED_ALIAS}:
                refresh = detail_refresh_decision(
                    previous,
                    card,
                    decision.canonical_url,
                    self.now(),
                    durable_refresh_hours=self.config.detail_refresh_hours,
                    volatile_refresh_hours=self.config.volatile_refresh_hours,
                )
                refresh_reason = refresh.reason
                if not refresh.required:
                    self.store.record_detail_cache_hit(
                        context.group.linkedin_company_id,
                        card.linkedin_job_id,
                        refresh_reason=refresh.reason,
                        volatile_fields_stale=refresh.volatile_fields_stale,
                        card_evidence_hash=compute_card_evidence_hash(card, decision.canonical_url),
                        run_id=str(self.metrics["run_id"]),
                        company_scan_id=context.scan_id,
                        observed_at=self.now(),
                    )
                    context.observed_job_ids.add(card.linkedin_job_id)
                    self._increment("detail_cache_hits")
                    self._increment("detail_avoided_requests")
                    self._record_refresh_reason(refresh.reason)
                    if refresh.volatile_fields_stale:
                        self._increment("detail_volatile_stale_rows")
                    return
            elif previous and previous.get("lifecycle_status") == "inactive":
                refresh_reason = "reactivated_job"
        self._increment("detail_refresh_requests")
        self._record_refresh_reason(refresh_reason)
        self.store.enqueue_detail(
            str(self.metrics["run_id"]),
            context.scan_id,
            context.group.linkedin_company_id,
            card.linkedin_job_id,
            refresh_reason=refresh_reason,
        )

    def _scan_recovery_partition(self, context: CompanyRunContext, partition: RecoveryPartition) -> bool:
        assert self.store is not None
        run_id = str(self.metrics["run_id"])
        partition_id = self.store.start_query_partition(context.scan_id, partition.parameter, partition.value)
        seen_body_hashes: set[str] = set()
        seen_job_sets: set[tuple[str, ...]] = set()
        complete = False
        suspicious_empty_streak = 0
        suspicious_empty_seen = False
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
                    complete = not suspicious_empty_seen
                    self.store.record_search_page(run_id, context.scan_id, context.group.linkedin_company_id, page_start, status="COMPLETE", job_ids=(), partition_type=partition.parameter, detail={"terminal": "http_400"})
                    break
                if response.status_code == 200 and is_suspicious_empty_body(response.text):
                    suspicious_empty_seen = True
                    body_hash = hashlib.sha256(response.text.encode("utf-8", errors="replace")).hexdigest()
                    self.store.record_search_page(run_id, context.scan_id, context.group.linkedin_company_id, page_start, status="SUSPICIOUS_EMPTY", job_ids=(), partition_type=partition.parameter, body_hash=body_hash, cards=())
                    suspicious_empty_streak += 1
                    if suspicious_empty_streak >= 2:
                        break
                    continue
                if response.error or classify_http_response(response.status_code, response.text, response.error) != "SUCCESS":
                    break
                parsed = parse_search_page(response.text)
                body_hash = hashlib.sha256(response.text.encode("utf-8", errors="replace")).hexdigest()
                if not parsed.is_usable or parsed.is_partial:
                    if is_suspicious_empty_body(response.text):
                        suspicious_empty_seen = True
                        self.store.record_search_page(run_id, context.scan_id, context.group.linkedin_company_id, page_start, status="SUSPICIOUS_EMPTY", job_ids=(), partition_type=partition.parameter, body_hash=body_hash, cards=())
                        suspicious_empty_streak += 1
                        if suspicious_empty_streak >= 2:
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
                capped_without_terminal = page_start >= self.pagination.max_start and not parsed.is_no_results
                self.store.record_search_page(
                    run_id,
                    context.scan_id,
                    context.group.linkedin_company_id,
                    page_start,
                    status="PARTIAL" if capped_without_terminal else "COMPLETE",
                    job_ids=page_job_ids,
                    partition_type=partition.parameter,
                    body_hash=body_hash,
                    cards=parsed.cards,
                )
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
                if parsed.is_no_results:
                    complete = not suspicious_empty_seen
                    break
                if capped_without_terminal:
                    complete = False
                    break
        finally:
            partition_status = "COMPLETE" if complete else "PARTIAL"
            self.store.finish_query_partition(partition_id, partition_status)
            context.recovery_partition_statuses[f"{partition.parameter}={partition.value}"] = partition_status
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
                classification = classify_http_response(response.status_code, response.text, response.error)
                if response.error == "request_budget_exhausted":
                    context.search_status = "BUDGET_EXHAUSTED"
                    self.store.record_search_page(run_id, scan_id, group.linkedin_company_id, page_start, status=context.search_status, job_ids=(), detail={"classification": classification})
                    break
                if response.status_code == 200 and is_suspicious_empty_body(response.text):
                    body_hash = hashlib.sha256(response.text.encode("utf-8", errors="replace")).hexdigest()
                    self.store.record_search_page(run_id, scan_id, group.linkedin_company_id, page_start, status="SUSPICIOUS_EMPTY", job_ids=(), body_hash=body_hash, detail={"body_class": "suspicious_empty"})
                    context.search_status = "PARTIAL_SUSPICIOUS_EMPTY"
                    suspicious_empty_streak += 1
                    if suspicious_empty_streak >= 2:
                        break
                    continue
                if response.status_code == 400 and page_start >= evidence.max_start:
                    context.search_status = "COMPLETE"
                    self.store.record_search_page(run_id, scan_id, group.linkedin_company_id, page_start, status="COMPLETE", job_ids=(), detail={"terminal": "http_400"})
                    break
                if classification != "SUCCESS":
                    retry_status = "PARTIAL_TRANSPORT_FAILURE" if candidate_cards else "FAILED"
                    context.search_status = {
                        "BLOCKED": "BLOCKED",
                        "RATE_LIMITED": "RATE_LIMITED",
                        "RETRYABLE": retry_status,
                        "PERMANENT_FAILURE": "FAILED",
                        "BUDGET_EXHAUSTED": "BUDGET_EXHAUSTED",
                    }.get(classification, "PARTIAL_PAGE_ANOMALY")
                    self.store.record_search_page(run_id, scan_id, group.linkedin_company_id, page_start, status=context.search_status, job_ids=(), detail={"classification": classification})
                    break
                parsed = parse_search_page(response.text)
                body_hash = hashlib.sha256(response.text.encode("utf-8", errors="replace")).hexdigest()
                if not parsed.is_usable:
                    if is_suspicious_empty_body(response.text):
                        self.store.record_search_page(run_id, scan_id, group.linkedin_company_id, page_start, status="SUSPICIOUS_EMPTY", job_ids=(), body_hash=body_hash, detail={"body_class": parsed.body_class})
                        context.search_status = "PARTIAL_SUSPICIOUS_EMPTY"
                        suspicious_empty_streak += 1
                        if suspicious_empty_streak >= 2:
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
                if not parsed.is_no_results and not parsed.is_partial and (body_hash in seen_body_hashes or (page_job_ids and page_job_ids in seen_job_sets)):
                    context.search_status = "SATURATED_UNRESOLVED"
                    break
                seen_body_hashes.add(body_hash)
                if page_job_ids:
                    seen_job_sets.add(page_job_ids)
                for card in parsed.cards:
                    context.card_by_job_id[card.linkedin_job_id] = card
                    context.card_start_by_job_id[card.linkedin_job_id] = page_start
                    context.card_partition_by_job_id[card.linkedin_job_id] = "base"
                    context.card_partition_value_by_job_id[card.linkedin_job_id] = ""
                    self._queue_card(context, card)
                candidate_cards = len(context.card_by_job_id)
                if parsed.is_no_results:
                    empty_pages += 1
                    context.no_results = candidate_cards == 0
                    if empty_pages >= 2 or page_start >= evidence.max_start:
                        if context.search_status in {"RUNNING", "COMPLETE"}:
                            context.search_status = "COMPLETE_ZERO_CONFIRMED" if candidate_cards == 0 else "COMPLETE"
                        break
                    continue
                empty_pages = 0
                if page_start >= evidence.max_start:
                    if context.search_status in {"RUNNING", "COMPLETE"}:
                        context.search_status = "SATURATED_UNRESOLVED"
                    break
            if context.search_status == "RUNNING":
                context.search_status = "COMPLETE_ZERO_CONFIRMED" if not candidate_cards else "COMPLETE"
            base_was_saturated = context.search_status == "SATURATED_UNRESOLVED"
            if context.search_status in {"SATURATED_UNRESOLVED", "PARTIAL_PAGE_ANOMALY"} and self.recovery_partitions:
                context.recovery_required = True
                recovery_complete = all(self._scan_recovery_partition(context, partition) for partition in self.recovery_partitions)
                if recovery_complete and base_was_saturated:
                    context.search_status = "SATURATED_RECOVERED"
        except Exception as exc:  # the scan remains resumable and is never treated as empty
            context.search_status = "BLOCKED"
            self._record_event(
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
        refresh_reason = _clean(entry["refresh_reason"]) or "retry"
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
            self.store.record_detail_attempt(run_id, job_id, status="FAILED", error_class=classify_http_response(response.status_code, response.text, response.error))
            context.detail_failures += 1
            self._increment("detail_failures")
            return
        detail = parse_job_detail(job_id, response.text)
        aliases = self.store.verified_aliases(company_id)
        decision = evaluate_card_detail_ownership(card.company_url, detail.company_url, context.group, aliases)
        if decision.status == COMPANY_MATCH_ALIAS_PENDING:
            slug = canonical_company_slug(detail.company_url)
            with self._alias_lock:
                aliases = self.store.verified_aliases(company_id)
                decision = evaluate_card_detail_ownership(card.company_url, detail.company_url, context.group, aliases)
                if decision.status == COMPANY_MATCH_ALIAS_PENDING and slug and self.store.alias_verification_due(company_id, slug, self.now()) and self.store.begin_alias_verification(company_id, slug, seen_at=self.now()):
                    alias_response = self._get(f"{COMPANY_ENDPOINT}/{slug}", kind="company")
                    if alias_response.status_code == 200 and alias_evidence_matches(alias_response.text, company_id):
                        self.store.record_alias(company_id, slug, status=COMPANY_MATCH_VERIFIED_ALIAS, verification_method="company_page_numeric_id", seen_at=self.now())
                        decision = evaluate_card_detail_ownership(card.company_url, detail.company_url, context.group, (slug,))
                    else:
                        self.store.record_alias(company_id, slug, status=COMPANY_MATCH_ALIAS_PENDING, verification_method="company_page_unverified", seen_at=self.now())
                        self._increment("alias_quarantines", 1 if not self.store.alias_verification_due(company_id, slug, self.now()) else 0)
                elif decision.status == COMPANY_MATCH_ALIAS_PENDING:
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
                "canonical_company_id": decision.canonical_company_id or context.group.primary_canonical_company_id,
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
                "applicant_count_observed_at": observed_at,
                "volatile_fields_status": "FRESH",
                "detail_refresh_reason": refresh_reason,
                "lifecycle_status": "active",
                "absence_count": "0",
                "card_evidence_hash": compute_card_evidence_hash(card, decision.canonical_url),
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
        with self.store.batch():
            self.store.upsert_catalog_row(row)
            self.store.record_detail_attempt(run_id, job_id, status="SUCCESS", detail=detail.__dict__)
        context.observed_job_ids.add(job_id)
        self._increment("detail_successes")
        self._increment("jobs_written")
        self._record_event({"record_type": "job_observation", "schema_version": 1, "run_id": run_id, **row})

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
        self.metrics["input_loader_reconciliation"] = build_input_loader_reconciliation_report(
            source_stats["unique_numeric_organizations"],
            source_stats,
        )
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
                request_limiter=self.adaptive,
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
            try:
                if self.config.mode == "reconcile":
                    self.store = StateStore(output_dir / "master_linkedin_jobs_state.db")
                    audit = self.store.audit_legacy_consistency()
                    self.store.export_catalog_csv(output_dir / "master_linkedin_jobs.csv")
                    (output_dir / "master_linkedin_jobs_legacy_audit.json").write_text(
                        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    self.metrics["legacy_audit"] = audit
                    self.store.close()
                self.metrics["dry_run"] = bool(self.config.dry_run or self.config.mode == "validate")
                self._write_metrics(output_dir)
                return dict(self.metrics)
            finally:
                self._close_transport()
        if self.config.fresh:
            backup_existing_artifacts(output_dir)
            for name in ("master_linkedin_jobs_state.db", "master_linkedin_jobs.csv", "master_linkedin_jobs.jsonl", "master_linkedin_jobs_metrics.json"):
                target = output_dir / name
                if target.exists():
                    target.unlink()
        input_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
        run_id = self.config.resume_run_id or datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%S%fZ")
        self.metrics["run_id"] = run_id
        generation_id = f"generation_{run_id}"
        generation_dir = output_dir / GENERATION_DIRECTORY_NAME / generation_id
        generation_dir.mkdir(parents=True, exist_ok=True)
        self._generation_dir = generation_dir
        self.metrics["generation_id"] = generation_id
        self._event_journal = JsonlEventJournal(generation_dir / "master_linkedin_jobs.jsonl")
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
                context.search_status = status
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
                    if status == "COMPLETE_ZERO_CONFIRMED":
                        self._increment("companies_zero_confirmed")
                elif status in {"FAILED", "BLOCKED", "RATE_LIMITED", "BUDGET_EXHAUSTED"}:
                    self._increment("companies_failed")
                else:
                    self._increment("companies_partial")
                if status == "PARTIAL_SUSPICIOUS_EMPTY":
                    self._increment("suspicious_empty_companies")
                status_counts = self.metrics.setdefault("scan_status_counts", {})
                if isinstance(status_counts, dict):
                    status_counts[status] = int(status_counts.get(status, 0)) + 1
            self._update_recovery_metrics()
            queue_counts = self.store.detail_queue_counts(run_id)
            pending_details = queue_counts.get("pending", 0) + queue_counts.get("retry", 0)
            quarantined_details = queue_counts.get("quarantined", 0)
            self.metrics["pending_detail_retries"] = pending_details
            self.metrics["quarantined_detail_rows"] = quarantined_details
            statuses = [context.search_status for context in self.contexts.values()]
            failure_statuses = {"FAILED", "BLOCKED", "RATE_LIMITED", "BUDGET_EXHAUSTED"}
            partial_statuses = set(statuses).difference(COMPLETE_SCAN_STATUSES)
            if not statuses:
                run_status = "FINISHED"
                run_outcome = "COMPLETE"
            elif all(status == "COMPLETE_ZERO_CONFIRMED" for status in statuses) and not pending_details and not quarantined_details:
                run_status = "FINISHED_ZERO"
                run_outcome = "ZERO"
            elif all(status in failure_statuses for status in statuses):
                run_status = "FAILED"
                run_outcome = "FAILURE"
            elif partial_statuses or pending_details or quarantined_details:
                run_status = "PARTIAL"
                run_outcome = "PARTIAL"
            else:
                run_status = "FINISHED"
                run_outcome = "COMPLETE"
            self.metrics["run_status"] = run_status
            self.metrics["run_outcome"] = run_outcome
            self._persist_proxy_health()
            self.store.export_catalog_csv(generation_dir / "master_linkedin_jobs.csv")
            self.metrics["requests"] = getattr(self.transport, "_request_count", self.metrics["requests"])
            self.metrics["account_peak_in_flight"] = self.adaptive.peak_in_flight
            self._capture_detail_provider_usage()
            self.store.finish_run(run_id, run_status, self.now())
            if self._event_journal is not None:
                self._event_journal.close()
                self._event_journal = None
            self._write_metrics(generation_dir)
            published_generation = publish_catalog_generation(
                output_dir,
                generation_id=generation_id,
                run_id=run_id,
                input_sha256=input_hash,
                run_status=run_status,
                run_outcome=run_outcome,
            )
            self.metrics["generation_manifest_sha256"] = published_generation["manifest_sha256"]
            log_path = generation_dir / f"master_linkedin_jobs_{run_id}.log"
            log_path.write_text(json.dumps({key: value for key, value in self.metrics.items() if "password" not in key.lower() and "secret" not in key.lower()}, sort_keys=True) + "\n", encoding="utf-8")
            return dict(self.metrics)
        except BaseException as exc:
            run_status = "INTERRUPTED" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "FAILED"
            self._persist_proxy_health()
            self.store.finish_run(run_id, run_status, self.now())
            self.metrics["run_status"] = run_status
            self.metrics["run_outcome"] = "INTERRUPTED" if run_status == "INTERRUPTED" else "FAILURE"
            self.metrics["error_class"] = type(exc).__name__
            self._update_recovery_metrics()
            if self._event_journal is not None:
                self._event_journal.close()
                self._event_journal = None
            try:
                self._write_metrics(generation_dir)
                write_catalog_generation_manifest(
                    output_dir,
                    generation_id=generation_id,
                    run_id=run_id,
                    input_sha256=input_hash,
                    status=run_status,
                    run_outcome=str(self.metrics.get("run_outcome") or ""),
                    published=False,
                )
            except OSError:
                pass
            raise
        finally:
            if self._event_journal is not None:
                self._event_journal.close()
                self._event_journal = None
            self.store.close()
            self._close_transport()

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
    parser.add_argument("--detail-refresh-hours", type=float, default=DEFAULT_DURABLE_DETAIL_REFRESH_HOURS, help="Durable detail refresh window; default is 168 hours")
    parser.add_argument("--volatile-refresh-hours", type=float, default=DEFAULT_VOLATILE_DETAIL_REFRESH_HOURS, help="Window after which applicant/freshness fields are marked stale")
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
        volatile_refresh_hours=args.volatile_refresh_hours,
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
