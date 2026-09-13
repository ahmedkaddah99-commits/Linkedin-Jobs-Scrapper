"""Build a resumable, company-scoped LinkedIn Germany jobs catalog.

All target requests use the configured Webshare direct-proxy pool.  The
SQLite database is the durable progress/catalog store; CSV and JSONL are
reconciled projections for downstream use and recovery.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
import threading
import time
from collections import Counter
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup


PROJECT_ROOT = Path(__file__).resolve().parents[1]
JOBS_URLS_DIR = PROJECT_ROOT / "Jobs-Urls"
DEFAULT_INPUT_CSV = (
    PROJECT_ROOT
    / "Company-Urls"
    / "Master-Company-Url"
    / "cleaned"
    / "Master-Company-Url-canonical_cleaned_linkedin_ids.csv"
)
DEFAULT_OUTPUT_DIR = JOBS_URLS_DIR / "master linkedin jobs url"
DEFAULT_PAGINATION_REPORT = JOBS_URLS_DIR / "linkedin_endpoint_pagination_validation.json"
sys.path.insert(0, str(JOBS_URLS_DIR))

SEARCH_ENDPOINT = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_ENDPOINT = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"
GERMANY_LOCATION = "Germany"
GERMANY_GEO_ID = "101282230"
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRY_LIMIT = 2
DEFAULT_BACKOFF_SECONDS = 0.5

CSV_FIELDS = [
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
    "apply_url",
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
    "lifecycle_status",
    "absence_count",
    "content_hash",
    "source_endpoint",
    "transport",
    "search_pagination_start",
    "search_status_code",
    "detail_status_code",
    "company_match_status",
    "company_match_reason",
    "run_id",
    "source_type",
    "source_provider",
    "career_target_url",
    "source_site_url",
    "source_job_id",
    "source_job_url",
    "discovery_method",
    "extraction_method",
    "extraction_endpoint",
    "ats_tenant",
]

PLACEHOLDER_IDS = {"", "/", "//", "-", "none", "null", "nan"}
BLOCK_MARKERS = (
    "captcha",
    "security check",
    "verify you are human",
    "unusual traffic",
    "authwall",
    "checkpoint",
    "challenge",
    "robot check",
    "sign in to linkedin",
)

LOGGER = logging.getLogger("master_linkedin_jobs_url_catalog")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical_company_url(raw_url: str) -> str:
    """Return the canonical LinkedIn company identity URL or an empty string."""

    value = str(raw_url or "").strip()
    if not value:
        return ""
    if value.startswith("//"):
        value = f"https:{value}"
    elif not re.match(r"^[a-z][a-z0-9+.-]*://", value, re.I):
        if value.lower().startswith("linkedin.com/") or value.lower().startswith("www.linkedin.com/"):
            value = f"https://{value}"
        elif value.startswith("/"):
            value = f"https://www.linkedin.com{value}"
        else:
            value = f"https://{value}"
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ""
    host = (parsed.hostname or "").casefold().rstrip(".")
    if host != "linkedin.com" and not host.endswith(".linkedin.com"):
        return ""
    path = parsed.path.rstrip("/")
    match = re.fullmatch(r"/company/([^/]+)", path, re.I)
    if not match:
        return ""
    slug = match.group(1).strip().casefold()
    return f"https://www.linkedin.com/company/{slug}" if slug else ""


@dataclass(frozen=True)
class CompanyGroup:
    linkedin_company_id: str
    source_company_ids: tuple[str, ...]
    source_company_names: tuple[str, ...]
    source_company_urls: tuple[str, ...]
    allowed_company_urls: frozenset[str]
    canonical_company_id: str
    source_company_name: str
    source_company_url: str


def _is_placeholder(value: str) -> bool:
    return str(value or "").strip().casefold() in PLACEHOLDER_IDS


def normalize_company_id(value: str) -> str:
    raw = str(value or "").strip()
    if not re.fullmatch(r"[0-9]+", raw):
        return ""
    normalized = str(int(raw))
    return normalized if normalized != "0" else ""


def load_company_groups(path: Path) -> tuple[dict[str, CompanyGroup], dict[str, int]]:
    """Load valid source rows and group them by numeric LinkedIn company ID."""

    grouped: dict[str, set[tuple[str, str, str]]] = {}
    stats = Counter(input_rows=0, accepted_rows=0, excluded_rows=0)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            stats["input_rows"] += 1
            company_id = normalize_company_id(str(row.get("linkedin_company_id") or ""))
            company_url = canonical_company_url(str(row.get("linkedin_company_url") or ""))
            if not company_id or not company_url:
                stats["excluded_rows"] += 1
                continue
            stats["accepted_rows"] += 1
            grouped.setdefault(company_id, set()).add(
                (
                    str(row.get("canonical_CompanyID") or "").strip(),
                    str(row.get("company_name") or "").strip(),
                    company_url,
                )
            )

    result: dict[str, CompanyGroup] = {}
    for company_id in sorted(grouped, key=lambda value: (int(value), value)):
        mappings = sorted(
            grouped[company_id],
            key=lambda value: (
                1 if _is_placeholder(value[0]) else 0,
                value[0].casefold(),
                value[1].casefold(),
                value[2],
            ),
        )
        ids = tuple(
            sorted(
                {item[0] for item in mappings}, key=lambda value: (1 if _is_placeholder(value) else 0, value.casefold())
            )
        )
        names = tuple(sorted({item[1] for item in mappings if item[1]}, key=str.casefold))
        urls = tuple(sorted({item[2] for item in mappings}))
        primary = next((item for item in mappings if not _is_placeholder(item[0])), mappings[0])
        primary_name = next((item[1] for item in mappings if item[1]), primary[1])
        result[company_id] = CompanyGroup(
            linkedin_company_id=company_id,
            source_company_ids=ids,
            source_company_names=names,
            source_company_urls=urls,
            allowed_company_urls=frozenset(urls),
            canonical_company_id=primary[0],
            source_company_name=primary_name,
            source_company_url=primary[2],
        )
    stats["groups"] = len(result)
    return result, dict(stats)


def build_search_url(company_id: str, start: int) -> str:
    return f"{SEARCH_ENDPOINT}?{urlencode({'location': GERMANY_LOCATION, 'geoId': GERMANY_GEO_ID, 'f_C': str(company_id), 'start': int(start)})}"


def build_detail_url(job_id: str) -> str:
    return f"{DETAIL_ENDPOINT}/{job_id}"


def _clean_text(node: Any) -> str:
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())


def _first_text(soup: BeautifulSoup, selectors: Iterable[str]) -> str:
    for selector in selectors:
        node = soup.select_one(selector)
        value = _clean_text(node)
        if value:
            return value
    return ""


def _first_href(soup: BeautifulSoup, selectors: Iterable[str]) -> str:
    for selector in selectors:
        node = soup.select_one(selector)
        if node is not None:
            value = str(node.get("href") or node.get("data-apply-url") or "").strip()
            if value:
                return value
    return ""


def _numeric_job_id(*values: str) -> str:
    for value in values:
        match = re.search(r"(?:jobPosting:|/jobs/view/|/jobPosting/)(\d+)", str(value or ""), re.I)
        if match:
            return match.group(1)
    return ""


@dataclass(frozen=True)
class SearchPageResult:
    classification: str
    cards: list[dict[str, Any]]
    usable: bool
    error: str = ""


def _explicit_no_results(soup: BeautifulSoup, body: str) -> bool:
    lowered = body.casefold()
    if any(marker in lowered for marker in ("no jobs found", "no jobs", "no results", "no matching jobs")):
        return True
    return bool(soup.select_one(".jobs-search-no-results, .jobs-search__no-results, [data-test-no-results]"))


def parse_search_page(html: str, *, company_id: str, start: int) -> SearchPageResult:
    body = str(html or "")
    lowered = body.casefold()
    soup = BeautifulSoup(body, "html.parser")
    if any(marker in lowered for marker in BLOCK_MARKERS):
        return SearchPageResult("block_page", [], False, "blocked_or_challenge_body")
    items = [item for item in soup.find_all("li") if item.select_one("div.base-search-card, div.base-card")]
    if not items and _explicit_no_results(soup, body):
        return SearchPageResult("legitimate_empty_result", [], True)
    if not items:
        return SearchPageResult("malformed_html", [], False, "no_search_cards_or_explicit_empty_result")

    cards: list[dict[str, Any]] = []
    for item in items:
        base = item.select_one("div.base-search-card, div.base-card")
        urn = str(base.get("data-entity-urn") or "").strip() if base else ""
        job_href = _first_href(item, ("a.base-card__full-link", "a[href*='/jobs/view/']"))
        job_id = _numeric_job_id(urn, job_href)
        company_href = _first_href(item, ("h4.base-search-card__subtitle a", "a[href*='/company/']"))
        company_url = canonical_company_url(urljoin("https://www.linkedin.com", company_href))
        if not job_id or not company_url:
            return SearchPageResult("malformed_card", [], False, "every_card_requires_job_id_and_company_url")
        time_node = item.select_one("time.job-search-card__listdate, time")
        cards.append(
            {
                "job_id": job_id,
                "title": _first_text(item, ("h3.base-search-card__title", "h3")),
                "company_name": _first_text(item, ("h4.base-search-card__subtitle", "h4")),
                "company_url": company_url,
                "location": _first_text(item, ("span.job-search-card__location",)),
                "posted_text": _clean_text(time_node),
                "posted_at_estimated": str(time_node.get("datetime") or "").strip() if time_node else "",
                "job_url": f"https://www.linkedin.com/jobs/view/{job_id}",
                "search_start": int(start),
                "search_status_code": 200,
                "company_id": str(company_id),
            }
        )
    return SearchPageResult("success", cards, True)


def _posted_at_estimated(posted_text: str) -> str:
    value = str(posted_text or "").strip()
    if not value:
        return ""
    if re.search(r"\bjust now\b|\bnow\b", value, re.I):
        age_hours = 0.0
    else:
        match = re.search(r"(\d+(?:\.\d+)?)\s*(minute|hour|day|week|month)s?\s+ago", value, re.I)
        if not match:
            return ""
        amount = float(match.group(1))
        unit = match.group(2).casefold()
        age_hours = amount * {"minute": 1 / 60, "hour": 1, "day": 24, "week": 168, "month": 720}[unit]
    return (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat(timespec="seconds")


def _applicant_count(text: str) -> int | None:
    match = re.search(r"(\d[\d,.\s]*)\+?\s+applicants?", text or "", re.I)
    if not match:
        return None
    digits = re.sub(r"[^\d]", "", match.group(1))
    return int(digits) if digits else None


def _criteria_values(soup: BeautifulSoup) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in soup.select("li.description__job-criteria-item, ul.description__job-criteria-list li"):
        heading = _first_text(item, ("h3", "dt"))
        value = _first_text(item, ("span", "dd"))
        if heading and value:
            values[heading.casefold()] = value
    return values


def parse_detail_page(job_id: str, html: str) -> dict[str, Any]:
    body = str(html or "")
    soup = BeautifulSoup(body, "html.parser")
    company_node = soup.select_one(
        "a.topcard__org-name-link, a.top-card-layout__company-url, span.top-card-layout__second-subline a[href*='/company/']"
    )
    if company_node is None:
        company_node = soup.select_one("a[href*='/company/']")
    company_url = canonical_company_url(
        urljoin("https://www.linkedin.com", str(company_node.get("href") or "")) if company_node else ""
    )
    title = _first_text(soup, ("h2.top-card-layout__title", "h1.top-card-layout__title", "h1"))
    company_name = (
        _clean_text(company_node)
        if company_node
        else _first_text(soup, ("span.topcard__flavor", "a.top-card-layout__company-url"))
    )
    location = _first_text(soup, ("span.topcard__flavor--bullet", "span.top-card-layout__first-subline"))
    description_node = soup.select_one(
        "div.show-more-less-html__markup, div.description__text, section.show-more-less-html"
    )
    description = description_node.get_text("\n", strip=True) if description_node else ""
    apply_url = ""
    apply_source = ""
    linkedin_apply = ""
    for element in soup.select("[data-tracking-control-name*='public_jobs_apply-link'], [data-apply-url], a[href]"):
        href = str(
            element.get("href") or element.get("data-apply-url") or element.get("data-test-apply-url") or ""
        ).strip()
        if not href or href == "#" or href.lower().startswith("javascript:"):
            continue
        href = urljoin("https://www.linkedin.com", href)
        tracking = str(element.get("data-tracking-control-name") or "").casefold()
        if "apply" not in tracking and "apply" not in href.casefold() and "/jobs/view/" not in href.casefold():
            continue
        if "linkedin.com/jobs/view" in href.casefold() and not linkedin_apply:
            linkedin_apply = href
        elif "linkedin.com" not in (urlsplit(href).hostname or "").casefold():
            apply_url, apply_source = href, "external"
            break
    if not apply_url:
        if linkedin_apply:
            apply_url, apply_source = linkedin_apply, "linkedin"
        else:
            apply_url, apply_source = f"https://www.linkedin.com/jobs/view/{job_id}", "linkedin_fallback"
    primary_text = _clean_text(soup.select_one(".top-card-layout__cta--primary")).casefold()
    trackings = " ".join(
        str(node.get("data-tracking-control-name") or "").casefold()
        for node in soup.select("[data-tracking-control-name]")
    )
    if (
        "easy apply" in primary_text
        or "einfach bewerben" in primary_text
        or "easy_apply" in trackings
        or "onsite" in trackings
    ):
        easy_apply_status = "true"
    elif "offsite" in trackings or "apply on company website" in body.casefold():
        easy_apply_status = "false"
    else:
        easy_apply_status = "unknown"
    posted_text = _first_text(soup, (".posted-time-ago__text", "span.posted-time-ago__text", "time"))
    if not posted_text:
        match = re.search(
            r"\b(?:just now|\d+(?:\.\d+)?\s+(?:minute|hour|day|week|month)s?\s+ago)\b",
            soup.get_text(" ", strip=True),
            re.I,
        )
        posted_text = match.group(0) if match else ""
    criteria = _criteria_values(soup)
    page_text = soup.get_text(" ", strip=True)
    return {
        "job_id": str(job_id),
        "title": title,
        "company_name": company_name,
        "company_url": company_url,
        "location": location,
        "description": description,
        "apply_url": apply_url,
        "apply_url_source": apply_source,
        "posted_text": posted_text,
        "posted_at_estimated": _posted_at_estimated(posted_text),
        "applicant_count": _applicant_count(page_text),
        "easy_apply_status": easy_apply_status,
        "employment_type": criteria.get("employment type", ""),
        "workplace_type": criteria.get("workplace type", ""),
    }


def validate_company_ownership(observed_url: str, allowed_urls: Iterable[str]) -> tuple[bool, str]:
    observed = canonical_company_url(observed_url)
    allowed = {canonical_company_url(value) for value in allowed_urls if canonical_company_url(value)}
    if not observed:
        return False, "missing_company_url"
    if observed not in allowed:
        return False, "company_url_mismatch"
    return True, "company_url_exact_match"


def validate_card_and_detail_ownership(card_url: str, detail_url: str, allowed_urls: Iterable[str]) -> tuple[bool, str]:
    card_match, card_reason = validate_company_ownership(card_url, allowed_urls)
    if not card_match:
        return False, card_reason
    detail_match, detail_reason = validate_company_ownership(detail_url, allowed_urls)
    if not detail_match:
        return False, detail_reason
    if canonical_company_url(card_url) != canonical_company_url(detail_url):
        return False, "card_detail_company_url_mismatch"
    return True, "card_and_detail_company_url_exact_match"


def should_reuse_successful_work(saved_run_id: str, current_run_id: str, status: str) -> bool:
    return str(status or "").casefold() == "complete" and bool(saved_run_id) and saved_run_id == current_run_id


def _content_value(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def content_hash_for_job(detail: dict[str, Any], card: dict[str, Any]) -> str:
    payload = {
        "title": _content_value(detail.get("title") or card.get("title")),
        "company_name": _content_value(detail.get("company_name") or card.get("company_name")),
        "company_url": canonical_company_url(str(detail.get("company_url") or card.get("company_url") or "")),
        "apply_url": _content_value(detail.get("apply_url")),
        "description": _content_value(detail.get("description")),
        "location": _content_value(detail.get("location") or card.get("location")),
        "easy_apply_status": _content_value(detail.get("easy_apply_status")),
        "applicant_count": _content_value(detail.get("applicant_count")),
        "employment_type": _content_value(detail.get("employment_type")),
        "workplace_type": _content_value(detail.get("workplace_type")),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _db_columns() -> str:
    return (
        ", ".join(f"{field} TEXT NOT NULL DEFAULT ''" for field in CSV_FIELDS if field != "absence_count")
        + ", absence_count INTEGER NOT NULL DEFAULT 0"
    )


class CatalogState:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock, self.connection:
            self.connection.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS jobs ({_db_columns()}, PRIMARY KEY (linkedin_company_id, linkedin_job_id));
                CREATE TABLE IF NOT EXISTS source_companies (
                    linkedin_company_id TEXT PRIMARY KEY, canonical_company_id TEXT NOT NULL DEFAULT '',
                    source_company_name TEXT NOT NULL DEFAULT '', source_company_url TEXT NOT NULL DEFAULT '',
                    source_company_ids TEXT NOT NULL DEFAULT '', source_company_names TEXT NOT NULL DEFAULT '',
                    source_company_urls TEXT NOT NULL DEFAULT '', allowed_company_urls TEXT NOT NULL DEFAULT '',
                    scan_status TEXT NOT NULL DEFAULT 'pending', last_scan_at TEXT NOT NULL DEFAULT '',
                    last_run_id TEXT NOT NULL DEFAULT '', last_error TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS search_pages (
                    linkedin_company_id TEXT NOT NULL, pagination_start INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                    status_code INTEGER NOT NULL DEFAULT 0, classification TEXT NOT NULL DEFAULT '',
                    cards_json TEXT NOT NULL DEFAULT '[]', last_error TEXT NOT NULL DEFAULT '',
                    retry_at TEXT NOT NULL DEFAULT '', last_run_id TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (linkedin_company_id, pagination_start)
                );
                CREATE TABLE IF NOT EXISTS detail_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, linkedin_company_id TEXT NOT NULL,
                    linkedin_job_id TEXT NOT NULL, run_id TEXT NOT NULL, attempt_number INTEGER NOT NULL,
                    status_code INTEGER NOT NULL DEFAULT 0, outcome TEXT NOT NULL DEFAULT '',
                    company_url TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{{}}', attempted_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS job_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, linkedin_company_id TEXT NOT NULL,
                    linkedin_job_id TEXT NOT NULL, observation_type TEXT NOT NULL, card_company_url TEXT NOT NULL DEFAULT '',
                    detail_company_url TEXT NOT NULL DEFAULT '', status_code INTEGER NOT NULL DEFAULT 0,
                    reason TEXT NOT NULL DEFAULT '', observed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY, status TEXT NOT NULL, started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_detail_success ON detail_attempts(linkedin_company_id, linkedin_job_id, outcome, id DESC);
                """
            )

    def close(self) -> None:
        with self.lock:
            self.connection.close()

    def job_count(self) -> int:
        with self.lock:
            row = self.connection.execute("SELECT COUNT(*) FROM jobs").fetchone()
            return int(row[0] if row else 0)

    def start_run(self) -> tuple[str, bool]:
        with self.lock, self.connection:
            prior = self.connection.execute(
                "SELECT run_id FROM runs WHERE status='running' ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            if prior:
                return str(prior[0]), True
            run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{time.time_ns()}"
            self.connection.execute(
                "INSERT INTO runs (run_id, status, started_at) VALUES (?, 'running', ?)",
                (run_id, utc_now()),
            )
            return run_id, False

    def finish_run(self, run_id: str, status: str = "finished") -> None:
        if not run_id:
            return
        with self.lock, self.connection:
            self.connection.execute(
                "UPDATE runs SET status=?, finished_at=? WHERE run_id=?",
                (status, utc_now(), run_id),
            )

    def import_output_records(self, records: Iterable[dict[str, Any]]) -> None:
        with self.lock, self.connection:
            for incoming in records:
                company_id = str(incoming.get("linkedin_company_id") or "").strip()
                job_id = str(incoming.get("linkedin_job_id") or "").strip()
                if not company_id or not job_id:
                    continue
                values = {field: str(incoming.get(field) or "") for field in CSV_FIELDS}
                try:
                    values["absence_count"] = int(incoming.get("absence_count") or 0)
                except (TypeError, ValueError):
                    values["absence_count"] = 0
                columns = ", ".join(CSV_FIELDS)
                placeholders = ", ".join("?" for _ in CSV_FIELDS)
                self.connection.execute(
                    f"INSERT OR IGNORE INTO jobs ({columns}) VALUES ({placeholders})",
                    tuple(values[field] for field in CSV_FIELDS),
                )

    def upsert_source_company(self, group: CompanyGroup, run_id: str) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """INSERT INTO source_companies (
                    linkedin_company_id, canonical_company_id, source_company_name, source_company_url,
                    source_company_ids, source_company_names, source_company_urls, allowed_company_urls,
                    scan_status, last_run_id, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'in_progress', ?, '')
                ON CONFLICT(linkedin_company_id) DO UPDATE SET
                    canonical_company_id=excluded.canonical_company_id, source_company_name=excluded.source_company_name,
                    source_company_url=excluded.source_company_url, source_company_ids=excluded.source_company_ids,
                    source_company_names=excluded.source_company_names, source_company_urls=excluded.source_company_urls,
                    allowed_company_urls=excluded.allowed_company_urls, scan_status='in_progress',
                    last_run_id=excluded.last_run_id, last_error=''""",
                (
                    group.linkedin_company_id,
                    group.canonical_company_id,
                    group.source_company_name,
                    group.source_company_url,
                    "|".join(group.source_company_ids),
                    "|".join(group.source_company_names),
                    "|".join(group.source_company_urls),
                    "|".join(sorted(group.allowed_company_urls)),
                    run_id,
                ),
            )

    def get_search_page(self, company_id: str, start: int) -> dict[str, Any] | None:
        with self.lock:
            row = self.connection.execute(
                "SELECT * FROM search_pages WHERE linkedin_company_id=? AND pagination_start=?",
                (company_id, int(start)),
            ).fetchone()
            return dict(row) if row else None

    def record_search_page(
        self,
        company_id: str,
        start: int,
        *,
        status: str,
        status_code: int,
        classification: str,
        cards: list[dict[str, Any]],
        error: str,
        retry_at: str,
        run_id: str,
    ) -> None:
        with self.lock, self.connection:
            old = self.connection.execute(
                "SELECT attempts FROM search_pages WHERE linkedin_company_id=? AND pagination_start=?",
                (company_id, int(start)),
            ).fetchone()
            attempts = int(old[0]) if old else 0
            self.connection.execute(
                """INSERT INTO search_pages (
                    linkedin_company_id, pagination_start, status, attempts, status_code, classification,
                    cards_json, last_error, retry_at, last_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(linkedin_company_id, pagination_start) DO UPDATE SET
                    status=excluded.status, attempts=excluded.attempts, status_code=excluded.status_code,
                    classification=excluded.classification, cards_json=excluded.cards_json, last_error=excluded.last_error,
                    retry_at=excluded.retry_at, last_run_id=excluded.last_run_id""",
                (
                    company_id,
                    int(start),
                    status,
                    attempts + 1,
                    int(status_code or 0),
                    classification,
                    json.dumps(cards, ensure_ascii=False),
                    error,
                    retry_at,
                    run_id,
                ),
            )

    def record_detail_attempt(
        self,
        company_id: str,
        job_id: str,
        *,
        run_id: str,
        status_code: int,
        outcome: str,
        company_url: str,
        reason: str,
        payload: dict[str, Any] | None,
        attempted_at: str,
    ) -> None:
        with self.lock, self.connection:
            self._record_detail_attempt_locked(
                company_id,
                job_id,
                run_id=run_id,
                status_code=status_code,
                outcome=outcome,
                company_url=company_url,
                reason=reason,
                payload=payload,
                attempted_at=attempted_at,
            )

    def _record_detail_attempt_locked(
        self,
        company_id: str,
        job_id: str,
        *,
        run_id: str,
        status_code: int,
        outcome: str,
        company_url: str,
        reason: str,
        payload: dict[str, Any] | None,
        attempted_at: str,
    ) -> None:
        prior = self.connection.execute(
            "SELECT COALESCE(MAX(attempt_number), 0) FROM detail_attempts WHERE linkedin_company_id=? AND linkedin_job_id=?",
            (company_id, job_id),
        ).fetchone()
        self.connection.execute(
            """INSERT INTO detail_attempts (
                linkedin_company_id, linkedin_job_id, run_id, attempt_number, status_code, outcome,
                company_url, reason, payload_json, attempted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                company_id,
                job_id,
                run_id,
                int(prior[0] or 0) + 1,
                int(status_code or 0),
                outcome,
                company_url,
                reason,
                json.dumps(payload or {}, ensure_ascii=False),
                attempted_at,
            ),
        )

    def successful_detail(self, company_id: str, job_id: str, run_id: str = "") -> dict[str, Any] | None:
        with self.lock:
            if run_id:
                row = self.connection.execute(
                    "SELECT * FROM detail_attempts WHERE linkedin_company_id=? AND linkedin_job_id=? AND run_id=? AND outcome='accepted' ORDER BY id DESC LIMIT 1",
                    (company_id, job_id, run_id),
                ).fetchone()
            else:
                row = self.connection.execute(
                    "SELECT * FROM detail_attempts WHERE linkedin_company_id=? AND linkedin_job_id=? AND outcome='accepted' ORDER BY id DESC LIMIT 1",
                    (company_id, job_id),
                ).fetchone()
            if not row:
                return None
            value = dict(row)
            try:
                payload = json.loads(value.get("payload_json") or "{}")
            except json.JSONDecodeError:
                payload = {}
            return payload if isinstance(payload, dict) else None

    def record_observation(
        self,
        run_id: str,
        company_id: str,
        job_id: str,
        observation_type: str,
        *,
        card_company_url: str = "",
        detail_company_url: str = "",
        status_code: int = 0,
        reason: str = "",
        observed_at: str,
    ) -> None:
        with self.lock, self.connection:
            self._record_observation_locked(
                run_id,
                company_id,
                job_id,
                observation_type,
                card_company_url=card_company_url,
                detail_company_url=detail_company_url,
                status_code=status_code,
                reason=reason,
                observed_at=observed_at,
            )

    def _record_observation_locked(
        self,
        run_id: str,
        company_id: str,
        job_id: str,
        observation_type: str,
        *,
        card_company_url: str,
        detail_company_url: str,
        status_code: int,
        reason: str,
        observed_at: str,
    ) -> None:
        self.connection.execute(
            """INSERT INTO job_observations (
                run_id, linkedin_company_id, linkedin_job_id, observation_type, card_company_url,
                detail_company_url, status_code, reason, observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                company_id,
                job_id,
                observation_type,
                card_company_url,
                detail_company_url,
                int(status_code or 0),
                reason,
                observed_at,
            ),
        )

    def upsert_accepted_job(
        self,
        group: CompanyGroup,
        card: dict[str, Any],
        detail: dict[str, Any],
        *,
        observed_at: str,
        run_id: str,
        search_start: int,
        search_status_code: int = 200,
        detail_status_code: int = 200,
        source_endpoint: str = "",
    ) -> str:
        with self.lock, self.connection:
            return self._upsert_accepted_job_locked(
                group,
                card,
                detail,
                observed_at=observed_at,
                run_id=run_id,
                search_start=search_start,
                search_status_code=search_status_code,
                detail_status_code=detail_status_code,
                source_endpoint=source_endpoint,
            )

    def _upsert_accepted_job_locked(
        self,
        group: CompanyGroup,
        card: dict[str, Any],
        detail: dict[str, Any],
        *,
        observed_at: str,
        run_id: str,
        search_start: int,
        search_status_code: int = 200,
        detail_status_code: int = 200,
        source_endpoint: str = "",
    ) -> str:
        company_id = group.linkedin_company_id
        job_id = str(card.get("job_id") or detail.get("job_id") or "")
        record = {field: "" for field in CSV_FIELDS}
        record.update(
            {
                "canonical_company_id": group.canonical_company_id,
                "linkedin_company_id": company_id,
                "source_company_name": group.source_company_name,
                "source_company_url": group.source_company_url,
                "source_company_ids": "|".join(group.source_company_ids),
                "source_company_names": "|".join(group.source_company_names),
                "source_company_urls": "|".join(group.source_company_urls),
                "observed_company_name": str(detail.get("company_name") or card.get("company_name") or ""),
                "observed_company_url": canonical_company_url(
                    str(detail.get("company_url") or card.get("company_url") or "")
                ),
                "linkedin_job_id": job_id,
                "job_title": str(detail.get("title") or card.get("title") or ""),
                "linkedin_job_url": str(card.get("job_url") or f"https://www.linkedin.com/jobs/view/{job_id}"),
                "apply_url": str(detail.get("apply_url") or ""),
                "apply_url_source": str(detail.get("apply_url_source") or ""),
                "description": str(detail.get("description") or ""),
                "location": str(detail.get("location") or card.get("location") or ""),
                "posted_text": str(detail.get("posted_text") or card.get("posted_text") or ""),
                "posted_at_estimated": str(detail.get("posted_at_estimated") or card.get("posted_at_estimated") or ""),
                "easy_apply_status": str(detail.get("easy_apply_status") or ""),
                "applicant_count": "" if detail.get("applicant_count") is None else str(detail.get("applicant_count")),
                "employment_type": str(detail.get("employment_type") or ""),
                "workplace_type": str(detail.get("workplace_type") or ""),
                "last_seen_at": observed_at,
                "last_successful_company_scan_at": "",
                "lifecycle_status": "active",
                "absence_count": 0,
                "content_hash": content_hash_for_job(detail, card),
                "source_endpoint": source_endpoint or build_search_url(company_id, search_start),
                "transport": "webshare",
                "search_pagination_start": int(search_start),
                "search_status_code": int(search_status_code),
                "detail_status_code": int(detail_status_code),
                "company_match_status": "matched",
                "company_match_reason": "card_and_detail_company_url_exact_match",
                "run_id": run_id,
                "source_type": "linkedin",
                "source_provider": "linkedin",
                "career_target_url": "",
                "source_site_url": "https://www.linkedin.com/jobs",
                "source_job_id": job_id,
                "source_job_url": str(card.get("job_url") or f"https://www.linkedin.com/jobs/view/{job_id}"),
                "discovery_method": "linkedin_guest_search",
                "extraction_method": "linkedin_guest_search_and_detail_html",
                "extraction_endpoint": build_detail_url(job_id),
                "ats_tenant": "",
            }
        )
        old = self.connection.execute(
            "SELECT * FROM jobs WHERE linkedin_company_id=? AND linkedin_job_id=?",
            (company_id, job_id),
        ).fetchone()
        if old:
            record["first_seen_at"] = str(old["first_seen_at"] or observed_at)
            old_hash = str(old["content_hash"] or "")
            outcome = "unchanged" if old_hash == record["content_hash"] else "updated"
        else:
            record["first_seen_at"] = observed_at
            outcome = "inserted"
        values = [record[field] for field in CSV_FIELDS]
        placeholders = ", ".join("?" for _ in CSV_FIELDS)
        update_clause = ", ".join(
            f"{field}=excluded.{field}"
            for field in CSV_FIELDS
            if field not in {"linkedin_company_id", "linkedin_job_id", "first_seen_at"}
        )
        self.connection.execute(
            f"""INSERT INTO jobs ({", ".join(CSV_FIELDS)}) VALUES ({placeholders})
            ON CONFLICT(linkedin_company_id, linkedin_job_id) DO UPDATE SET {update_clause}""",
            values,
        )
        return outcome

    def accept_job_observation(
        self,
        group: CompanyGroup,
        card: dict[str, Any],
        detail: dict[str, Any],
        *,
        observed_at: str,
        run_id: str,
        search_start: int,
        search_status_code: int = 200,
        detail_status_code: int = 200,
        source_endpoint: str = "",
        record_detail_attempt: bool = True,
    ) -> str:
        """Commit detail acceptance, catalog upsert, and accepted observation together."""

        job_id = str(card.get("job_id") or detail.get("job_id") or "")
        with self.lock, self.connection:
            if record_detail_attempt:
                self._record_detail_attempt_locked(
                    group.linkedin_company_id,
                    job_id,
                    run_id=run_id,
                    status_code=detail_status_code,
                    outcome="accepted",
                    company_url=str(detail.get("company_url") or ""),
                    reason="card_and_detail_company_url_exact_match",
                    payload=detail,
                    attempted_at=observed_at,
                )
            outcome = self._upsert_accepted_job_locked(
                group,
                card,
                detail,
                observed_at=observed_at,
                run_id=run_id,
                search_start=search_start,
                search_status_code=search_status_code,
                detail_status_code=detail_status_code,
                source_endpoint=source_endpoint,
            )
            self._record_observation_locked(
                run_id,
                group.linkedin_company_id,
                job_id,
                "accepted",
                card_company_url=str(card.get("company_url") or ""),
                detail_company_url=str(detail.get("company_url") or ""),
                status_code=detail_status_code,
                reason="card_and_detail_company_url_exact_match",
                observed_at=observed_at,
            )
            return outcome

    def get_job(self, company_id: str, job_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.connection.execute(
                "SELECT * FROM jobs WHERE linkedin_company_id=? AND linkedin_job_id=?",
                (company_id, job_id),
            ).fetchone()
            return dict(row) if row else None

    def finish_company_scan(
        self,
        company_id: str,
        *,
        complete: bool,
        observed_job_ids: set[str],
        scan_at: str,
        run_id: str,
        error: str = "",
    ) -> int:
        inactive = 0
        with self.lock, self.connection:
            if complete:
                rows = self.connection.execute(
                    "SELECT linkedin_job_id, absence_count FROM jobs WHERE linkedin_company_id=? AND lifecycle_status='active'",
                    (company_id,),
                ).fetchall()
                for row in rows:
                    if str(row["linkedin_job_id"]) in observed_job_ids:
                        self.connection.execute(
                            "UPDATE jobs SET last_successful_company_scan_at=?, run_id=? WHERE linkedin_company_id=? AND linkedin_job_id=?",
                            (scan_at, run_id, company_id, row["linkedin_job_id"]),
                        )
                    else:
                        self.connection.execute(
                            "UPDATE jobs SET lifecycle_status='inactive', absence_count=?, last_successful_company_scan_at=?, run_id=? WHERE linkedin_company_id=? AND linkedin_job_id=?",
                            (int(row["absence_count"] or 0) + 1, scan_at, run_id, company_id, row["linkedin_job_id"]),
                        )
                        inactive += 1
            self.connection.execute(
                "UPDATE source_companies SET scan_status=?, last_scan_at=?, last_run_id=?, last_error=? WHERE linkedin_company_id=?",
                ("complete" if complete else "failed", scan_at if complete else "", run_id, error, company_id),
            )
        return inactive

    def get_jobs(self) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT * FROM jobs ORDER BY CAST(linkedin_company_id AS INTEGER), linkedin_company_id, CAST(linkedin_job_id AS INTEGER), linkedin_job_id"
            ).fetchall()
            return [dict(row) for row in rows]


def _read_records_csv(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_records_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(value)
    return records


def reconcile_output_records(csv_path: Path, jsonl_path: Path) -> list[dict[str, Any]]:
    """Reconcile projections by composite company/job ID; JSONL wins ties."""

    records: dict[tuple[str, str], dict[str, Any]] = {}
    for value in _read_records_csv(csv_path):
        key = (str(value.get("linkedin_company_id") or "").strip(), str(value.get("linkedin_job_id") or "").strip())
        if all(key):
            records[key] = value
    for value in _read_records_jsonl(jsonl_path):
        key = (str(value.get("linkedin_company_id") or "").strip(), str(value.get("linkedin_job_id") or "").strip())
        if all(key):
            records[key] = value
    return [records[key] for key in sorted(records)]


def _atomic_replace(path: Path, writer: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    writer(temporary)
    temporary.replace(path)


def write_catalog_outputs(state: CatalogState, csv_path: Path, jsonl_path: Path) -> None:
    records = state.get_jobs()

    def write_csv(path: Path) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            for record in records:
                writer.writerow({field: record.get(field, "") for field in CSV_FIELDS})

    def write_jsonl(path: Path) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            for record in records:
                handle.write(
                    json.dumps({field: record.get(field, "") for field in CSV_FIELDS}, ensure_ascii=False) + "\n"
                )

    _atomic_replace(csv_path, write_csv)
    _atomic_replace(jsonl_path, write_jsonl)


class RequestBudgetExceeded(RuntimeError):
    pass


class InterProcessLock:
    """Hold one output-directory lock across a complete crawler run."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: Any = None

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
            else:  # pragma: no cover - production target is Windows, retained for portability.
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
            else:  # pragma: no cover - production target is Windows, retained for portability.
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


@dataclass(frozen=True)
class HttpResult:
    response: requests.Response | None
    attempts: int
    error: str = ""
    proxy_identifier: str = ""


class WebshareClient:
    def __init__(
        self, proxies: list[dict[str, Any]], *, timeout: float, retry_limit: int, max_requests: int = 0
    ) -> None:
        if not proxies:
            raise ValueError("No Webshare proxies were loaded; refusing direct requests")
        self.proxies = proxies
        self.config = {"proxy_urls": [str(item["proxy_url"]) for item in proxies]}
        self.timeout = float(timeout)
        self.retry_limit = max(0, int(retry_limit))
        self.max_requests = max(0, int(max_requests))
        self.lock = threading.Lock()
        self.request_count = 0
        self.proxy_index = 0

    def _claim(self) -> tuple[int, str]:
        with self.lock:
            if self.max_requests and self.request_count >= self.max_requests:
                raise RequestBudgetExceeded(f"max-requests limit reached ({self.max_requests})")
            index = self.proxy_index % len(self.proxies)
            self.proxy_index += 1
            self.request_count += 1
            return index, str(self.proxies[index].get("identifier") or index)

    def get(self, url: str) -> HttpResult:
        last_error = ""
        for attempt in range(self.retry_limit + 1):
            proxy_index, proxy_identifier = self._claim()
            session = requests.Session()
            try:
                from webshare_linkedin_benchmark import configure_webshare_session

                configure_webshare_session(session, self.config, proxy_index)
                response = session.get(url, headers=_linkedin_headers(), timeout=self.timeout, allow_redirects=False)
                status = int(response.status_code or 0)
                retryable = status == 429 or status >= 500
                if retryable and attempt < self.retry_limit:
                    time.sleep(DEFAULT_BACKOFF_SECONDS * (2**attempt))
                    continue
                return HttpResult(response, attempt + 1, "", proxy_identifier)
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt >= self.retry_limit:
                    return HttpResult(None, attempt + 1, last_error, proxy_identifier)
                time.sleep(DEFAULT_BACKOFF_SECONDS * (2**attempt))
            finally:
                session.close()
        return HttpResult(None, self.retry_limit + 1, last_error, "")


def _linkedin_headers() -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
    }


def load_pagination_evidence(path: Path) -> tuple[int, int]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to read pagination evidence: {path}") from exc
    if payload.get("endpoint") != SEARCH_ENDPOINT:
        raise RuntimeError(f"Pagination evidence endpoint does not match {SEARCH_ENDPOINT}: {path}")
    provider = payload.get("provider") or {}
    if str(provider.get("name") or "").casefold() != "webshare":
        raise RuntimeError(f"Pagination evidence is not Webshare-backed: {path}")
    if int(provider.get("scrapeops_requests") or 0) != 0:
        raise RuntimeError(f"Pagination evidence contains ScrapeOps requests: {path}")
    calibration = payload.get("calibration") or {}
    steps = [
        int(item["observed_page_step_candidate"])
        for item in calibration.values()
        if isinstance(item, dict) and item.get("observed_page_step_candidate")
    ]
    counts = [
        int(item["observed_full_card_count"])
        for item in calibration.values()
        if isinstance(item, dict) and item.get("observed_full_card_count")
    ]
    ceiling = payload.get("ceiling_scan") or {}
    step = Counter(steps).most_common(1)[0][0] if steps else 0
    if not steps or any(candidate != step for candidate in steps):
        raise RuntimeError(f"Pagination evidence has inconsistent page steps: {path}")
    if not counts or any(count != counts[0] or count <= 0 for count in counts):
        raise RuntimeError(f"Pagination evidence has inconsistent card counts: {path}")
    max_start = int(ceiling.get("terminal_http_400_start") or 0)
    max_confirmed_full_start = int(ceiling.get("max_confirmed_full_start") or 0)
    responses = ceiling.get("responses") or []
    has_terminal = any(
        isinstance(item, dict)
        and int(item.get("start") or -1) == max_start
        and int(item.get("status_code") or 0) == 400
        for item in responses
    )
    if (
        step <= 0
        or max_start <= 0
        or max_start % step != 0
        or max_confirmed_full_start != max_start - step
        or not has_terminal
    ):
        raise RuntimeError(f"Validated pagination evidence is incomplete: {path}")
    return step, max_start


class Runner:
    def __init__(
        self,
        *,
        input_csv: Path = DEFAULT_INPUT_CSV,
        output_dir: Path = DEFAULT_OUTPUT_DIR,
        pagination_report: Path = DEFAULT_PAGINATION_REPORT,
        workers: int = 0,
        timeout: float = DEFAULT_TIMEOUT,
        retry_limit: int = DEFAULT_RETRY_LIMIT,
        max_requests: int = 0,
        fresh: bool = False,
        company_id: str = "",
        dry_run: bool = False,
    ) -> None:
        self.input_csv = input_csv
        self.output_dir = output_dir
        self.pagination_report = pagination_report
        self.worker_override = int(workers)
        self.timeout = float(timeout)
        self.retry_limit = int(retry_limit)
        self.max_requests = int(max_requests)
        self.fresh = bool(fresh)
        self.company_id = str(company_id or "").strip()
        self.dry_run = bool(dry_run)

    @property
    def csv_path(self) -> Path:
        return self.output_dir / "master_linkedin_jobs.csv"

    @property
    def jsonl_path(self) -> Path:
        return self.output_dir / "master_linkedin_jobs.jsonl"

    @property
    def state_path(self) -> Path:
        return self.output_dir / "master_linkedin_jobs_state.db"

    @property
    def metrics_path(self) -> Path:
        return self.output_dir / "master_linkedin_jobs_metrics.json"

    def _reset_outputs(self) -> None:
        for path in (self.csv_path, self.jsonl_path, self.state_path, self.metrics_path):
            if path.exists():
                path.unlink()
            for sidecar in (Path(f"{path}-wal"), Path(f"{path}-shm")):
                if sidecar.exists():
                    sidecar.unlink()

    def _base_metrics(
        self, run_id: str, started_at: str, stats: dict[str, int], step: int, max_start: int
    ) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "started_at": started_at,
            "finished_at": "",
            "input": {**stats, "selected_companies": stats.get("groups", 0)},
            "pagination": {
                "page_step": step,
                "max_start": max_start,
                "location": GERMANY_LOCATION,
                "geo_id": GERMANY_GEO_ID,
                "evidence_path": str(self.pagination_report),
            },
            "companies": {"completed": 0, "failed": 0},
            "requests": {"total": 0, "search": 0, "detail": 0},
            "exclusions": {},
            "jobs": {"inserted": 0, "updated": 0, "unchanged": 0, "written": 0, "inactive": 0},
            "proxy": {"transport": "webshare", "scrapeops_requests": 0},
        }

    def run(self) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        groups, stats = load_company_groups(self.input_csv)
        step, max_start = load_pagination_evidence(self.pagination_report)
        if self.company_id:
            if self.company_id not in groups:
                raise ValueError(f"--company-id {self.company_id!r} is not present in the valid source groups")
            groups = {self.company_id: groups[self.company_id]}
        proxies = self._load_proxies()
        run_id = ""
        started_at = utc_now()
        metrics = self._base_metrics("", started_at, stats, step, max_start)
        metrics["input"]["selected_companies"] = len(groups)
        if self.dry_run:
            metrics["proxy"]["proxy_count"] = len(proxies)
            metrics["finished_at"] = utc_now()
            self.metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return metrics
        with InterProcessLock(self.output_dir / ".master_linkedin_jobs.lock"):
            if self.fresh:
                self._reset_outputs()
            existing = reconcile_output_records(self.csv_path, self.jsonl_path)
            state = CatalogState(self.state_path)
            try:
                if state.job_count() == 0:
                    state.import_output_records(existing)
                run_id, resumed = state.start_run()
                metrics["run_id"] = run_id
                metrics["resumed"] = resumed
                client = WebshareClient(
                    proxies, timeout=self.timeout, retry_limit=self.retry_limit, max_requests=self.max_requests
                )
                metrics_lock = threading.Lock()
                workers = self.worker_override if self.worker_override > 0 else len(proxies)
                workers = max(1, workers)
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futures = [
                        executor.submit(
                            self._scan_company, group, state, client, step, max_start, run_id, metrics, metrics_lock
                        )
                        for group in groups.values()
                    ]
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception:
                            LOGGER.exception("Company scan failed unexpectedly")
                            with metrics_lock:
                                metrics["companies"]["failed"] += 1
                write_catalog_outputs(state, self.csv_path, self.jsonl_path)
                metrics["requests"]["total"] = client.request_count
                metrics["jobs"]["written"] = len(state.get_jobs())
                metrics["finished_at"] = utc_now()
                state.finish_run(run_id, "finished")
                self.metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                return metrics
            except Exception:
                state.finish_run(run_id, "failed")
                raise
            finally:
                state.close()

    def _load_proxies(self) -> list[dict[str, Any]]:
        from webshare_linkedin_benchmark import load_webshare_proxies

        return load_webshare_proxies()

    def _scan_company(
        self,
        group: CompanyGroup,
        state: CatalogState,
        client: WebshareClient,
        step: int,
        max_start: int,
        run_id: str,
        metrics: dict[str, Any],
        metrics_lock: threading.Lock,
    ) -> None:
        state.upsert_source_company(group, run_id)
        complete = True
        scan_error = ""
        observed_job_ids: set[str] = set()
        cards_by_job: dict[str, dict[str, Any]] = {}
        for start in range(0, max_start + step, step):
            saved = state.get_search_page(group.linkedin_company_id, start)
            if saved and should_reuse_successful_work(
                str(saved.get("last_run_id") or ""), run_id, str(saved.get("status") or "")
            ):
                try:
                    cards = json.loads(saved.get("cards_json") or "[]")
                except json.JSONDecodeError:
                    cards = []
                if saved.get("classification") == "legitimate_empty_result":
                    break
                for card in cards:
                    cards_by_job.setdefault(str(card.get("job_id") or ""), card)
                if int(start) == max_start:
                    break
                continue
            url = build_search_url(group.linkedin_company_id, start)
            with metrics_lock:
                metrics["requests"]["search"] += 1
            try:
                result = client.get(url)
            except RequestBudgetExceeded as exc:
                with metrics_lock:
                    metrics["requests"]["search"] = max(0, metrics["requests"]["search"] - 1)
                complete = False
                scan_error = str(exc)
                state.record_search_page(
                    group.linkedin_company_id,
                    start,
                    status="failed",
                    status_code=0,
                    classification="request_budget_exhausted",
                    cards=[],
                    error=scan_error,
                    retry_at=utc_now(),
                    run_id=run_id,
                )
                break
            status_code = int(result.response.status_code or 0) if result.response is not None else 0
            if start == max_start and status_code == 400:
                state.record_search_page(
                    group.linkedin_company_id,
                    start,
                    status="complete",
                    status_code=400,
                    classification="validated_terminal_http_400",
                    cards=[],
                    error="",
                    retry_at="",
                    run_id=run_id,
                )
                break
            if result.response is None:
                complete, scan_error = False, result.error or "request_failed"
                state.record_search_page(
                    group.linkedin_company_id,
                    start,
                    status="failed",
                    status_code=0,
                    classification="request_failed",
                    cards=[],
                    error=scan_error,
                    retry_at=utc_now(),
                    run_id=run_id,
                )
                break
            parsed = parse_search_page(result.response.text, company_id=group.linkedin_company_id, start=start)
            if status_code != 200 or not parsed.usable:
                complete = False
                scan_error = parsed.error or f"search_status={status_code}"
                state.record_search_page(
                    group.linkedin_company_id,
                    start,
                    status="failed",
                    status_code=status_code,
                    classification=parsed.classification,
                    cards=[],
                    error=scan_error,
                    retry_at=utc_now(),
                    run_id=run_id,
                )
                break
            state.record_search_page(
                group.linkedin_company_id,
                start,
                status="complete",
                status_code=status_code,
                classification=parsed.classification,
                cards=parsed.cards,
                error="",
                retry_at="",
                run_id=run_id,
            )
            if parsed.classification == "legitimate_empty_result":
                break
            for card in parsed.cards:
                cards_by_job.setdefault(str(card["job_id"]), card)
            if start == max_start:
                break

        for job_id, card in cards_by_job.items():
            if not job_id:
                continue
            matches, reason = validate_company_ownership(card.get("company_url", ""), group.allowed_company_urls)
            if not matches:
                state.record_observation(
                    run_id,
                    group.linkedin_company_id,
                    job_id,
                    "excluded_card",
                    card_company_url=str(card.get("company_url") or ""),
                    reason=reason,
                    observed_at=utc_now(),
                )
                with metrics_lock:
                    metrics["exclusions"][reason] = metrics["exclusions"].get(reason, 0) + 1
                continue
            detail = state.successful_detail(group.linkedin_company_id, job_id, run_id=run_id)
            cached_detail = detail is not None
            detail_status = 200
            if detail is None:
                with metrics_lock:
                    metrics["requests"]["detail"] += 1
                try:
                    detail_result = client.get(build_detail_url(job_id))
                except RequestBudgetExceeded as exc:
                    with metrics_lock:
                        metrics["requests"]["detail"] = max(0, metrics["requests"]["detail"] - 1)
                    complete, scan_error = False, str(exc)
                    break
                detail_status = (
                    int(detail_result.response.status_code or 0) if detail_result.response is not None else 0
                )
                if detail_result.response is None or detail_status != 200:
                    complete, scan_error = False, f"detail_status={detail_status}"
                    state.record_detail_attempt(
                        group.linkedin_company_id,
                        job_id,
                        run_id=run_id,
                        status_code=detail_status,
                        outcome="excluded",
                        company_url="",
                        reason=scan_error,
                        payload={},
                        attempted_at=utc_now(),
                    )
                    with metrics_lock:
                        metrics["exclusions"][scan_error] = metrics["exclusions"].get(scan_error, 0) + 1
                    continue
                detail = parse_detail_page(job_id, detail_result.response.text)
                matches, reason = validate_card_and_detail_ownership(
                    str(card.get("company_url") or ""),
                    str(detail.get("company_url") or ""),
                    group.allowed_company_urls,
                )
                if not matches:
                    state.record_detail_attempt(
                        group.linkedin_company_id,
                        job_id,
                        run_id=run_id,
                        status_code=detail_status,
                        outcome="excluded",
                        company_url=str(detail.get("company_url") or ""),
                        reason=reason,
                        payload=detail,
                        attempted_at=utc_now(),
                    )
                    state.record_observation(
                        run_id,
                        group.linkedin_company_id,
                        job_id,
                        "excluded_detail",
                        card_company_url=str(card.get("company_url") or ""),
                        detail_company_url=str(detail.get("company_url") or ""),
                        status_code=detail_status,
                        reason=reason,
                        observed_at=utc_now(),
                    )
                    with metrics_lock:
                        metrics["exclusions"][reason] = metrics["exclusions"].get(reason, 0) + 1
                    complete, scan_error = False, reason
                    continue
            else:
                matches, reason = validate_card_and_detail_ownership(
                    str(card.get("company_url") or ""),
                    str(detail.get("company_url") or ""),
                    group.allowed_company_urls,
                )
                if not matches:
                    state.record_observation(
                        run_id,
                        group.linkedin_company_id,
                        job_id,
                        "excluded_detail",
                        card_company_url=str(card.get("company_url") or ""),
                        detail_company_url=str(detail.get("company_url") or ""),
                        status_code=detail_status,
                        reason=reason,
                        observed_at=utc_now(),
                    )
                    with metrics_lock:
                        metrics["exclusions"][reason] = metrics["exclusions"].get(reason, 0) + 1
                    complete, scan_error = False, reason
                    continue
            observed_job_ids.add(job_id)
            search_start = int(card.get("search_start") or 0)
            outcome = state.accept_job_observation(
                group,
                card,
                detail,
                observed_at=utc_now(),
                run_id=run_id,
                search_start=search_start,
                detail_status_code=detail_status,
                source_endpoint=build_search_url(group.linkedin_company_id, search_start),
                record_detail_attempt=not cached_detail,
            )
            with metrics_lock:
                metrics["jobs"][outcome] = metrics["jobs"].get(outcome, 0) + 1

        inactive = state.finish_company_scan(
            group.linkedin_company_id,
            complete=complete,
            observed_job_ids=observed_job_ids,
            scan_at=utc_now(),
            run_id=run_id,
            error=scan_error,
        )
        with metrics_lock:
            metrics["jobs"]["inactive"] += inactive
            metrics["companies"]["completed" if complete else "failed"] += 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--pagination-report", type=Path, default=DEFAULT_PAGINATION_REPORT)
    parser.add_argument("--workers", type=int, default=0, help="0 means one worker per loaded Webshare proxy")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--retry-limit", type=int, default=DEFAULT_RETRY_LIMIT)
    parser.add_argument("--max-requests", type=int, default=0, help="0 means unlimited target requests")
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--company-id", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING"), default="INFO")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.output_dir / f"master_linkedin_jobs_run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.log"
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )
    try:
        metrics = Runner(
            input_csv=args.input_csv,
            output_dir=args.output_dir,
            pagination_report=args.pagination_report,
            workers=args.workers,
            timeout=args.timeout,
            retry_limit=args.retry_limit,
            max_requests=args.max_requests,
            fresh=args.fresh,
            company_id=args.company_id,
            dry_run=args.dry_run,
        ).run()
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        LOGGER.error("%s", exc)
        return 2
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
