"""Resolve LinkedIn organization IDs for every unique normalized LinkedIn URL.

This runner is intentionally ID-only. It does not discover URLs, enrich company
metadata, validate jobs, or modify the source CSV. Work is keyed by normalized
LinkedIn URL and checkpointed in SQLite so a later invocation resumes unfinished
URLs rather than restarting the source file.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sqlite3
import sys
import tempfile
import threading
import time
from collections import Counter, OrderedDict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

from bs4 import BeautifulSoup

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.integrations.scrapeops import estimate_mode_native_credits
from backend.application.company_enrichment_resolution import (
    ACCESS_FAILURES,
    PersistentResolverSafety,
    SafetyConfig,
    evidence_fingerprint,
)
from scripts.linkedin_company_enrichment_pipeline import (
    CachedWebshareFetcher,
    FetchResponse,
    ScrapeOpsFetcher,
    StateStore,
    classify_transport_response,
    extract_f_c_ids,
    linkedin_page_type,
    linkedin_slug,
    normalize_linkedin_url,
    read_csv,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DEFAULT = ROOT / "Company-Urls" / "Master-Company-Url" / "cleaned" / "Master-Company-Url-canonical_cleaned.csv"
OUTPUT_DEFAULT = SOURCE_DEFAULT.with_name("Master-Company-Url-canonical_cleaned_linkedin_ids.csv")
STATE_DEFAULT = SOURCE_DEFAULT.parent / "linkedin_company_enrichment_state" / "linkedin_id_resolution"
REPORT_DEFAULT = SOURCE_DEFAULT.with_name("Master-Company-Url-canonical_cleaned_linkedin_ids_report.json")
MARKDOWN_REPORT_DEFAULT = SOURCE_DEFAULT.with_name("Master-Company-Url-canonical_cleaned_linkedin_ids_report.md")
REQUEST_LOG_DEFAULT = STATE_DEFAULT / "linkedin_id_resolution_request_log.csv"

OUTPUT_COLUMNS = (
    "linkedin_company_id",
    "linkedin_company_id_status",
    "linkedin_company_id_source",
    "linkedin_company_id_confidence",
    "linkedin_company_id_resolved_at",
    "linkedin_company_id_evidence_json",
    "linkedin_company_id_transport",
    "linkedin_company_id_url_used",
)
SUPPORTED_PAGE_TYPES = {"company", "school", "showcase"}
TERMINAL_STATUSES = {"RESOLVED", "HIGH_CONFIDENCE", "AMBIGUOUS", "UNRESOLVED", "INVALID_LINKEDIN_URL"}
SCRAPEOPS_MODES = ("basic", "residential", "render_js_residential")
CHALLENGE_CLASSIFICATIONS = {"challenge", "blocked", "rate_limited", "http_999"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def numeric_id(value: Any) -> str:
    text = str(value or "").strip()
    return text if re.fullmatch(r"\d+", text) else ""


def company_jobs_href(page_source: str, base_url: str) -> str:
    """Return the company's rendered Jobs-tab URL, excluding global Jobs links."""
    soup = BeautifulSoup(str(page_source or ""), "html.parser")
    candidates: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, str(anchor.get("href") or "").strip())
        path = urlsplit(href).path.casefold().rstrip("/")
        if not re.search(r"/company/[^/]+/jobs$", path):
            continue
        label = " ".join(
            str(value or "")
            for value in (
                anchor.get_text(" ", strip=True),
                anchor.get("aria-label", ""),
                anchor.get("title", ""),
            )
        ).casefold()
        score = 20 if re.search(r"\bjobs\b", label) else 10
        candidates.append((score, href))
    if not candidates:
        return ""
    return max(candidates, key=lambda item: item[0])[1]


def all_jobs_href(page_source: str, base_url: str) -> str:
    """Return the rendered All jobs link, preferring the explicit call to action."""
    soup = BeautifulSoup(str(page_source or ""), "html.parser")
    candidates: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, str(anchor.get("href") or "").strip())
        if not href or "/jobs" not in urlsplit(href).path.casefold():
            continue
        label = " ".join(
            str(value or "")
            for value in (
                anchor.get_text(" ", strip=True),
                anchor.get("aria-label", ""),
                anchor.get("title", ""),
            )
        ).casefold()
        score = 0
        if re.search(r"\b(?:see|view|show)\s+all\s+jobs\b", label):
            score = 30
        elif re.search(r"\ball\s+jobs\b", label):
            score = 20
        elif re.search(r"\b(?:see|view)\s+jobs\b", label):
            score = 10
        candidates.append((score, href))
    if not candidates:
        return ""
    best_score, best_href = max(candidates, key=lambda item: item[0])
    return best_href if best_score > 0 else ""


def atomic_write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f"{path.stem}.", suffix=".tmp", dir=str(path.parent))
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        with temp_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\r\n")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def contextual_company_ids(body: str, requested_url: str) -> tuple[list[str], list[str]]:
    """Extract only IDs tied to known LinkedIn company structures."""
    decoded = html.unescape(str(body or ""))
    url_text = html.unescape(str(requested_url or ""))
    searchable = f"{decoded}\n{url_text}"
    ids: set[str] = set(extract_f_c_ids(searchable))
    evidence: list[str] = []
    jobs = "/jobs/" in url_text.casefold()
    f_c_count = len(re.findall(r"(?:[?&]|%3[fF])f_[cC](?:=|%3[dD])\d+", searchable))
    if f_c_count or re.search(r"\bf_[cC]\s*[=:]\s*\d+", searchable):
        evidence.append("linkedin_jobs_f_C" if jobs else "linkedin_page_f_C")
    patterns = (
        (r"urn:li:(?:fsd_)?company:(\d+)", "linkedin_company_urn"),
        (r"(?:companyUniversalId|companyId|company_id)\s*[\"']?\s*[:=]\s*[\"']?(\d+)", "linkedin_company_structured_id"),
    )
    for pattern, source in patterns:
        matches = re.findall(pattern, searchable, flags=re.IGNORECASE)
        if matches:
            ids.update(str(item) for item in matches)
            evidence.append(source)
    evidence = list(dict.fromkeys(evidence))
    if ids and not evidence:
        evidence.append("linkedin_parser_company_context")
    return sorted(ids), evidence


def classify_fetch(response: FetchResponse | None, body: str = "") -> str:
    if response is None:
        return "network_error"
    classification = classify_transport_response(response)
    if classification:
        return classification
    return "valid_html" if body.strip() else "malformed"


class CreditLedger:
    """Conservatively reserve native credits before paid requests."""

    def __init__(self, limit: float):
        self.limit = max(0.0, float(limit))
        self.reserved = 0.0
        self.actual = 0.0
        self.estimated = 0.0
        self.billing_unknown = 0.0
        self.conservative = 0.0
        self.request_count = 0
        self._lock = threading.Lock()

    def reserve(self, mode: str) -> float | None:
        estimate = float(estimate_mode_native_credits(mode))
        with self._lock:
            if self.reserved + estimate > self.limit:
                return None
            self.reserved += estimate
            self.request_count += 1
            return estimate

    def restore(self, *, actual: float, estimated: float, billing_unknown: float) -> None:
        with self._lock:
            self.actual = float(actual)
            self.estimated = float(estimated)
            self.billing_unknown = float(billing_unknown)
            self.conservative = self.actual + self.estimated + self.billing_unknown
            self.reserved = self.conservative

    def settle(self, reserved: float, record: dict[str, Any]) -> None:
        basis = str(record.get("cost_status") or "")
        actual = record.get("actual_credits")
        estimated = float(record.get("estimated_credits") or 0)
        conservative = float(actual) if actual not in (None, "") else (estimated if basis in {"estimated", "billing_unknown"} else 0.0)
        with self._lock:
            if actual not in (None, ""):
                self.actual += float(actual)
            elif basis == "estimated":
                self.estimated += estimated
            elif basis == "billing_unknown":
                self.billing_unknown += estimated
            self.conservative += conservative
            self.reserved += max(0.0, conservative - float(reserved))

    def exhausted(self) -> bool:
        with self._lock:
            return self.reserved >= self.limit

    def snapshot(self) -> dict[str, float | int]:
        with self._lock:
            return {
                "limit": self.limit,
                "reserved": round(self.reserved, 3),
                "actual": round(self.actual, 3),
                "estimated": round(self.estimated, 3),
                "billing_unknown": round(self.billing_unknown, 3),
                "conservative": round(self.conservative, 3),
                "request_count": self.request_count,
            }


class ResolutionState:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = directory
        self.path = directory / "linkedin_id_resolution.sqlite3"
        self.connection = sqlite3.connect(self.path, check_same_thread=False, timeout=60)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self._lock = threading.RLock()
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS url_resolution (
              normalized_url TEXT PRIMARY KEY,
              linkedin_slug TEXT NOT NULL,
              source_row_numbers_json TEXT NOT NULL,
              canonical_company_ids_json TEXT NOT NULL,
              status TEXT NOT NULL,
              linkedin_company_id TEXT NOT NULL DEFAULT '',
              id_source TEXT NOT NULL DEFAULT '',
              confidence REAL NOT NULL DEFAULT 0,
              transport TEXT NOT NULL DEFAULT '',
              url_used TEXT NOT NULL DEFAULT '',
              stage TEXT NOT NULL DEFAULT '',
              attempts_json TEXT NOT NULL DEFAULT '[]',
              actual_credits REAL NOT NULL DEFAULT 0,
              estimated_credits REAL NOT NULL DEFAULT 0,
              billing_unknown_credits REAL NOT NULL DEFAULT 0,
              last_error TEXT NOT NULL DEFAULT '',
              result_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS request_log (
              request_id INTEGER PRIMARY KEY AUTOINCREMENT,
              normalized_url TEXT NOT NULL,
              requested_url TEXT NOT NULL,
              transport TEXT NOT NULL,
              scrapeops_mode TEXT NOT NULL DEFAULT '',
              status_code INTEGER NOT NULL DEFAULT 0,
              classification TEXT NOT NULL DEFAULT '',
              id_found INTEGER NOT NULL DEFAULT 0,
              id_value TEXT NOT NULL DEFAULT '',
              actual_credits REAL,
              estimated_credits REAL NOT NULL DEFAULT 0,
              billing_known INTEGER NOT NULL DEFAULT 1,
              latency_seconds REAL NOT NULL DEFAULT 0,
              stage TEXT NOT NULL DEFAULT '',
              error TEXT NOT NULL DEFAULT '',
              recorded_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS run_meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def set_meta(self, key: str, value: Any) -> None:
        with self._lock:
            self.connection.execute(
                "INSERT INTO run_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value),
            )
            self.connection.commit()

    def log_request(self, normalized_url: str, record: dict[str, Any]) -> None:
        with self._lock:
            self.connection.execute(
                """INSERT INTO request_log(
                    normalized_url,requested_url,transport,scrapeops_mode,status_code,classification,
                    id_found,id_value,actual_credits,estimated_credits,billing_known,latency_seconds,
                    stage,error,recorded_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    normalized_url,
                    record.get("requested_url", ""),
                    record.get("transport", ""),
                    record.get("scrapeops_mode", ""),
                    int(record.get("status_code") or 0),
                    record.get("classification", ""),
                    int(bool(record.get("ID_found"))),
                    record.get("ID_value", ""),
                    record.get("actual_credits"),
                    float(record.get("estimated_credits") or 0),
                    int(bool(record.get("billing_known", True))),
                    float(record.get("latency_seconds") or 0),
                    record.get("stage", ""),
                    record.get("error", ""),
                    record.get("timestamp", utc_now()),
                ),
            )
            self.connection.commit()

    def put_resolution(self, normalized_url: str, payload: dict[str, Any]) -> None:
        output = payload.get("output_fields", {})
        with self._lock:
            self.connection.execute(
                """INSERT INTO url_resolution(
                    normalized_url,linkedin_slug,source_row_numbers_json,canonical_company_ids_json,status,
                    linkedin_company_id,id_source,confidence,transport,url_used,stage,attempts_json,
                    actual_credits,estimated_credits,billing_unknown_credits,last_error,result_json,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(normalized_url) DO UPDATE SET
                    linkedin_slug=excluded.linkedin_slug,
                    source_row_numbers_json=excluded.source_row_numbers_json,
                    canonical_company_ids_json=excluded.canonical_company_ids_json,
                    status=excluded.status,
                    linkedin_company_id=excluded.linkedin_company_id,
                    id_source=excluded.id_source,
                    confidence=excluded.confidence,
                    transport=excluded.transport,
                    url_used=excluded.url_used,
                    stage=excluded.stage,
                    attempts_json=excluded.attempts_json,
                    actual_credits=excluded.actual_credits,
                    estimated_credits=excluded.estimated_credits,
                    billing_unknown_credits=excluded.billing_unknown_credits,
                    last_error=excluded.last_error,
                    result_json=excluded.result_json,
                    updated_at=excluded.updated_at""",
                (
                    normalized_url,
                    payload.get("linkedin_slug", ""),
                    json.dumps(payload.get("source_row_numbers", [])),
                    json.dumps(payload.get("canonical_company_ids", []), ensure_ascii=False),
                    output.get("linkedin_company_id_status", "UNRESOLVED"),
                    output.get("linkedin_company_id", ""),
                    output.get("linkedin_company_id_source", ""),
                    float(output.get("linkedin_company_id_confidence") or 0),
                    output.get("linkedin_company_id_transport", ""),
                    output.get("linkedin_company_id_url_used", ""),
                    payload.get("stage", ""),
                    json.dumps(payload.get("records", []), ensure_ascii=False),
                    float(payload.get("actual_credits", 0) or 0),
                    float(payload.get("estimated_credits", 0) or 0),
                    float(payload.get("billing_unknown_credits", 0) or 0),
                    payload.get("last_error", ""),
                    json.dumps(payload, ensure_ascii=False),
                    utc_now(),
                ),
            )
            self.connection.commit()

    def get_resolutions(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute("SELECT normalized_url,result_json FROM url_resolution").fetchall()
        result: dict[str, dict[str, Any]] = {}
        for normalized_url, result_json in rows:
            try:
                result[normalized_url] = json.loads(result_json)
            except json.JSONDecodeError:
                continue
        return result

    def get_resolution(self, normalized_url: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT result_json FROM url_resolution WHERE normalized_url = ?",
                (normalized_url,),
            ).fetchone()
        if not row:
            return None
        try:
            value = json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def record_reconciliation_decision(
        self,
        normalized_url: str,
        *,
        selected_id: str,
        reviewer: str,
        reason: str,
    ) -> dict[str, Any]:
        """Record an explicit human decision for contradictory contextual IDs."""

        payload = self.get_resolution(normalized_url) or {}
        payload["reconciliation_decision"] = {
            "selected_id": numeric_id(selected_id),
            "reviewer": str(reviewer or "").strip(),
            "reason": str(reason or "").strip(),
            "recorded_at": utc_now(),
        }
        self.put_resolution(normalized_url, payload)
        return payload

    def get_meta(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self.connection.execute("SELECT value FROM run_meta WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            return row[0]

    def get_credit_totals(self) -> dict[str, float]:
        with self._lock:
            row = self.connection.execute(
                """SELECT
                    COALESCE(SUM(actual_credits),0),
                    COALESCE(SUM(estimated_credits),0),
                    COALESCE(SUM(billing_unknown_credits),0)
                   FROM url_resolution"""
            ).fetchone()
            request_totals = self.connection.execute(
                """SELECT
                    COALESCE(SUM(actual_credits),0),
                    COALESCE(SUM(CASE WHEN actual_credits IS NULL AND billing_known=1 THEN estimated_credits ELSE 0 END),0),
                    COALESCE(SUM(CASE WHEN actual_credits IS NULL AND billing_known=0 THEN estimated_credits ELSE 0 END),0)
                   FROM request_log"""
            ).fetchone()
        # Request-level accounting is authoritative: a process can be stopped
        # after a request is logged but before its URL result is committed.
        return {"actual": float(request_totals[0] or 0), "estimated": float(request_totals[1] or 0), "billing_unknown": float(request_totals[2] or 0)}

    def export_requests(self, path: Path) -> None:
        with self._lock:
            rows = self.connection.execute("SELECT * FROM request_log ORDER BY request_id").fetchall()
            fields = [item[1] for item in self.connection.execute("PRAGMA table_info(request_log)").fetchall() if item[1] != "request_id"]
        records = []
        for row in rows:
            record = dict(zip(["request_id", *fields], row))
            record.pop("request_id", None)
            records.append(record)
        atomic_write_csv(path, fields, records)

    def close(self) -> None:
        with self._lock:
            self.connection.close()


class TransportPool:
    def __init__(
        self,
        state_dir: Path,
        *,
        webshare_timeout: float,
        scrapeops_timeout: int,
        webshare_rotate_each_request: bool = False,
        browser_engine: str = "",
        browser_timeout: float = 45.0,
    ):
        self.state_dir = state_dir
        self.webshare_timeout = webshare_timeout
        self.scrapeops_timeout = scrapeops_timeout
        self.webshare_rotate_each_request = webshare_rotate_each_request
        self.browser_engine = str(browser_engine or "").casefold()
        self.browser_timeout = browser_timeout
        self.local = threading.local()
        self.contexts: list[tuple[StateStore, StateStore | None]] = []
        self.browser: Any | None = None
        self._lock = threading.Lock()

    def _get_browser(self):
        with self._lock:
            if self.browser is None:
                if self.browser_engine != "playwright":
                    return None
                self.browser = PlaywrightWebshareFetcher(timeout=self.browser_timeout, retries=1, rotate_each_request=True)
            return self.browser

    def get(self) -> dict[str, Any]:
        context = getattr(self.local, "context", None)
        if context is not None:
            return context
        worker_name = f"worker-{threading.get_ident()}"
        webshare_state = StateStore(self.state_dir / "transport_cache" / worker_name / "webshare")
        scrapeops_state = StateStore(self.state_dir / "transport_cache" / worker_name / "scrapeops")
        webshare = None
        scrapeops = None
        browser = None
        errors: dict[str, str] = {}
        try:
            webshare = CachedWebshareFetcher(
                webshare_state,
                timeout=self.webshare_timeout,
                retries=0,
                delay=0,
                use_cache=False,
                rotate_each_request=self.webshare_rotate_each_request,
            )
        except Exception as exc:
            errors["webshare"] = f"{type(exc).__name__}:{str(exc)[:200]}"
        try:
            scrapeops = ScrapeOpsFetcher(
                scrapeops_state,
                timeout=self.scrapeops_timeout,
                retries=0,
                max_credit_cost=0,
                credit_budget=0,
                default_mode="basic",
                use_cache=False,
            )
        except Exception as exc:
            errors["scrapeops"] = f"{type(exc).__name__}:{str(exc)[:200]}"
        if self.browser_engine == "playwright":
            try:
                browser = self._get_browser()
            except Exception as exc:
                errors["playwright"] = f"{type(exc).__name__}:{str(exc)[:200]}"
        context = {"webshare": webshare, "scrapeops": scrapeops, "playwright": browser, "errors": errors}
        self.local.context = context
        with self._lock:
            self.contexts.append((webshare_state, scrapeops_state))
        return context

    def close(self) -> None:
        with self._lock:
            contexts = list(self.contexts)
            self.contexts.clear()
        if self.browser is not None:
            try:
                self.browser.close()
            except Exception:
                pass
            self.browser = None
        for webshare_state, scrapeops_state in contexts:
            try:
                webshare_state.close()
            except sqlite3.ProgrammingError:
                pass
            try:
                scrapeops_state.close()
            except sqlite3.ProgrammingError:
                pass


class PlaywrightWebshareFetcher:
    """Use one browser with concurrent authenticated Webshare contexts."""

    def __init__(self, *, timeout: float = 45.0, retries: int = 1, rotate_each_request: bool = True):
        self.timeout_seconds = max(10.0, float(timeout))
        self.retries = max(0, min(int(retries), 2))
        self.rotate_each_request = bool(rotate_each_request)
        self.proxy_pool = self._load_proxy_config()
        self._proxy_lock = threading.Lock()
        self._next_proxy = 0
        self._loop = None
        self._thread = None
        self._ready = threading.Event()
        self._startup_error: Exception | None = None
        self._closed = False
        self._start_service()

    @staticmethod
    def _load_proxy_config() -> list[dict[str, str]]:
        raw_pool = CachedWebshareFetcher._load_proxy_config(max_proxies=100)
        pool: list[dict[str, str]] = []
        for item in raw_pool:
            value = str(item.get("https") or item.get("http") or "").strip()
            parsed = urlsplit(value)
            if not parsed.hostname:
                continue
            proxy: dict[str, str] = {"server": f"{parsed.scheme or 'http'}://{parsed.hostname}:{parsed.port or 80}"}
            if parsed.username:
                proxy["username"] = unquote(parsed.username)
            if parsed.password:
                proxy["password"] = unquote(parsed.password)
            pool.append(proxy)
        if not pool:
            raise RuntimeError("Webshare proxy configuration is missing or invalid for Playwright.")
        return pool

    def _start_service(self) -> None:
        import asyncio

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_service, name="playwright-webshare", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=self.timeout_seconds + 15):
            self.close()
            raise RuntimeError("playwright_service_start_timeout")
        if self._startup_error is not None:
            error = self._startup_error
            self.close()
            raise RuntimeError(f"playwright_service_start_failed:{error}") from error

    def _run_service(self) -> None:
        import asyncio

        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._start_browser())
        except Exception as exc:
            self._startup_error = exc
            self._ready.set()
            return
        self._ready.set()
        self._loop.run_forever()
        try:
            self._loop.run_until_complete(self._stop_browser())
        finally:
            self._loop.close()

    async def _start_browser(self) -> None:
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"],
        )

    async def _stop_browser(self) -> None:
        if getattr(self, "_browser", None) is not None:
            await self._browser.close()
            self._browser = None
        if getattr(self, "_playwright", None) is not None:
            await self._playwright.stop()
            self._playwright = None

    def _proxy(self) -> dict[str, str]:
        with self._proxy_lock:
            proxy = self.proxy_pool[self._next_proxy % len(self.proxy_pool)]
            self._next_proxy += 1
        return proxy

    async def _new_context(self, proxy: dict[str, str] | None):
        options = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36",
            "locale": "en-US",
            "viewport": {"width": 1365, "height": 768},
            "service_workers": "block",
        }
        if proxy is not None:
            options["proxy"] = proxy
        return await self._browser.new_context(**options)

    async def _click_href(self, page, context, href: str):
        """Click one exact rendered link and return the page reached by that click."""
        anchors = page.locator("a")
        selected = None
        for index in range(min(await anchors.count(), 500)):
            anchor = anchors.nth(index)
            candidate = str(await anchor.get_attribute("href") or "").strip()
            if urljoin(page.url, candidate) == href:
                selected = anchor
                break
        if selected is None:
            await page.goto(href, wait_until="domcontentloaded", timeout=int(self.timeout_seconds * 1000))
            await page.wait_for_timeout(750)
            return page
        before = page.url
        target = str(await selected.get_attribute("target") or "").casefold()
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        if target == "_blank":
            try:
                async with context.expect_page(timeout=3000) as popup_info:
                    await selected.click(timeout=int(self.timeout_seconds * 1000))
                popup = await popup_info.value
                await popup.wait_for_load_state("domcontentloaded", timeout=int(self.timeout_seconds * 1000))
                await popup.wait_for_timeout(500)
                return popup
            except PlaywrightTimeoutError:
                pass
        try:
            async with page.expect_navigation(wait_until="domcontentloaded", timeout=8000):
                await selected.click(timeout=int(self.timeout_seconds * 1000))
        except PlaywrightTimeoutError:
            if page.url.rstrip("/") == before.rstrip("/"):
                await page.goto(href, wait_until="domcontentloaded", timeout=int(self.timeout_seconds * 1000))
        await page.wait_for_timeout(500)
        return page

    async def _click_jobs_flow(self, page, context) -> tuple[Any, str]:
        """Follow company page -> Jobs tab -> Show all jobs and return its URL."""
        current_path = urlsplit(page.url).path.casefold().rstrip("/")
        if not re.search(r"/company/[^/]+/jobs$", current_path):
            initial_source = await page.content()
            jobs_tab_href = company_jobs_href(initial_source, page.url)
            if jobs_tab_href:
                page = await self._click_href(page, context, jobs_tab_href)
            else:
                # Guest-page variants may omit the company tab but expose the
                # same company-specific CTA (for example, "See jobs") with the
                # f_C filter already in its destination. Use that rendered CTA
                # before attempting a synthetic /jobs/ navigation.
                guest_all_href = all_jobs_href(initial_source, page.url)
                if guest_all_href:
                    page = await self._click_href(page, context, guest_all_href)
                    await page.wait_for_timeout(750)
                    return page, guest_all_href
                jobs_tab_href = urljoin(page.url.rstrip("/") + "/", "jobs/")
                page = await self._click_href(page, context, jobs_tab_href)
            await page.wait_for_timeout(750)

        all_href = all_jobs_href(await page.content(), page.url)
        if not all_href:
            return page, ""
        page = await self._click_href(page, context, all_href)
        await page.wait_for_timeout(750)
        return page, all_href

    async def _fetch_once(self, url: str, kind: str) -> FetchResponse:
        proxy = self._proxy()
        context = await self._new_context(proxy)
        page = await context.new_page()
        try:
            timeout_ms = int(self.timeout_seconds * 1000)
            page.set_default_timeout(timeout_ms)
            page.set_default_navigation_timeout(timeout_ms)
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_timeout(750)
            if kind == "company_page" and "/authwall" in page.url.casefold():
                # Webshare can reach LinkedIn but still be redirected to the
                # guest authwall. Retry the same browser flow once without a
                # proxy; this is still a browser-rendered, clicked resolution
                # and avoids recording an authwall as a terminal no-ID result.
                await context.close()
                context = await self._new_context(None)
                page = await context.new_page()
                page.set_default_timeout(timeout_ms)
                page.set_default_navigation_timeout(timeout_ms)
                response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                await page.wait_for_timeout(750)
            clicked_all_jobs_href = ""
            if kind == "company_page":
                page, clicked_all_jobs_href = await self._click_jobs_flow(page, context)
            body_text = await page.content()
            if clicked_all_jobs_href:
                body_text += f"\n<!-- clicked_show_all_jobs_href={html.escape(clicked_all_jobs_href)} -->"
            body = body_text.encode("utf-8", errors="replace")
            status = int(response.status) if response is not None else 200
            content_type = str((response.headers if response is not None else {}).get("content-type", "text/html"))
            return FetchResponse(url, page.url, status, content_type, body, 1, transport_used="playwright", transport_level="playwright", webshare_attempts=1)
        finally:
            await context.close()

    async def _fetch(self, url: str, kind: str) -> FetchResponse:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 2):
            try:
                result = await self._fetch_once(url, kind)
                return FetchResponse(
                    result.url,
                    result.final_url,
                    result.status_code,
                    result.content_type,
                    result.body,
                    attempt,
                    transport_used=result.transport_used,
                    transport_level=result.transport_level,
                    webshare_attempts=attempt,
                )
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"playwright_fetch_failed:{url}:{last_error}") from last_error

    def fetch(self, url: str, *, kind: str = "html") -> FetchResponse:
        if self._closed or self._loop is None:
            raise RuntimeError("playwright_service_closed")
        import asyncio

        future = asyncio.run_coroutine_threadsafe(self._fetch(url, kind), self._loop)
        try:
            return future.result(timeout=(self.timeout_seconds * (self.retries + 2)) + 15)
        except Exception:
            future.cancel()
            raise

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._loop is not None and self._thread is not None and self._thread.is_alive():
            import asyncio

            future = asyncio.run_coroutine_threadsafe(self._stop_browser(), self._loop)
            try:
                future.result(timeout=15)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=15)


def request_record(
    *,
    normalized_url: str,
    requested_url: str,
    transport: str,
    mode: str,
    stage: str,
    response: FetchResponse | None,
    body: str,
    error: str = "",
    reserved_credits: float = 0,
) -> tuple[dict[str, Any], list[str], list[str]]:
    started = time.perf_counter()
    ids, evidence = contextual_company_ids(body, requested_url)
    classification = classify_fetch(response, body)
    basis = str(response.scrapeops_credit_cost_basis if response else "")
    actual = None
    estimated = 0.0
    billing_known = True
    if transport == "scrapeops":
        if basis == "actual":
            actual = float(response.scrapeops_credit_cost)
        elif basis in {"estimated", "billing_unknown"}:
            estimated = float(response.scrapeops_estimated_credit_cost or reserved_credits)
        elif basis == "not_billed":
            estimated = 0.0
        else:
            estimated = float(reserved_credits)
            billing_known = False
        if basis == "billing_unknown":
            billing_known = False
    record = {
        "normalized_linkedin_url": normalized_url,
        "requested_url": requested_url,
        "transport": transport,
        "scrapeops_mode": mode,
        "stage": stage,
        "status_code": int(response.status_code if response else 0),
        "classification": classification,
        "ID_found": len(ids) == 1,
        "ID_value": ids[0] if len(ids) == 1 else "",
        "ID_values": ids,
        "ID_evidence_sources": evidence,
        "actual_credits": actual,
        "estimated_credits": round(estimated, 3),
        "billing_known": billing_known,
        "cost_status": basis if transport == "scrapeops" else "not_applicable",
        "latency_seconds": 0.0,
        "timestamp": utc_now(),
        "error": error,
    }
    # The caller measures the network duration and replaces this value.
    record["latency_seconds"] = round(time.perf_counter() - started, 3)
    return record, ids, evidence


def _fetch_one(
    context: dict[str, Any],
    *,
    transport: str,
    mode: str,
    normalized_url: str,
    requested_url: str,
    stage: str,
    reserved_credits: float = 0,
) -> tuple[dict[str, Any], list[str], list[str]]:
    started = time.perf_counter()
    response: FetchResponse | None = None
    error = ""
    body = ""
    fetcher = context.get(transport)
    if fetcher is None:
        error = context.get("errors", {}).get(transport, f"{transport}_unavailable")
    else:
        try:
            if transport == "scrapeops":
                response = fetcher.fetch(requested_url, kind="company_jobs" if "/jobs/" in requested_url else "company_page", mode=mode, fallback_reason=f"full_id_resolution_{stage}")
            else:
                response = fetcher.fetch(requested_url, kind="company_jobs" if "/jobs/" in requested_url else "company_page")
            body = response.body.decode("utf-8", errors="replace")
        except Exception as exc:
            error = f"{type(exc).__name__}:{str(exc)[:200]}"
    record, ids, evidence = request_record(
        normalized_url=normalized_url,
        requested_url=(response.final_url if response is not None and response.final_url else requested_url),
        transport=transport,
        mode=mode,
        stage=stage,
        response=response,
        body=body,
        error=error,
        reserved_credits=reserved_credits,
    )
    record["latency_seconds"] = round(time.perf_counter() - started, 3)
    return record, ids, evidence


def _output_fields(
    *,
    normalized_url: str,
    status: str,
    company_id: str = "",
    source: str = "",
    confidence: float = 0.0,
    resolved_at: str = "",
    evidence: dict[str, Any] | None = None,
    transport: str = "",
    url_used: str = "",
) -> dict[str, str]:
    return {
        "linkedin_company_id": company_id,
        "linkedin_company_id_status": status,
        "linkedin_company_id_source": source,
        "linkedin_company_id_confidence": f"{confidence:.3f}" if confidence else "0.000",
        "linkedin_company_id_resolved_at": resolved_at,
        "linkedin_company_id_evidence_json": json.dumps(evidence or {"normalized_linkedin_url": normalized_url}, ensure_ascii=False, sort_keys=True),
        "linkedin_company_id_transport": transport,
        "linkedin_company_id_url_used": url_used,
    }


def resolve_one(
    group: dict[str, Any],
    *,
    state: ResolutionState,
    pool: TransportPool,
    ledger: CreditLedger,
    webshare_only: bool = False,
    browser_first: bool = False,
    safety: PersistentResolverSafety | None = None,
) -> dict[str, Any]:
    normalized_url = group["normalized_url"]
    jobs_url = normalized_url.rstrip("/") + "/jobs/"
    webshare_plan = [
        ("webshare", "", jobs_url, "webshare_jobs"),
        ("webshare", "", normalized_url, "webshare_company"),
    ]
    browser_plan = [("playwright", "", normalized_url, "playwright_all_jobs")]
    scrapeops_plan = [
        ("scrapeops", "basic", jobs_url, "scrapeops_basic_jobs"),
        ("scrapeops", "basic", normalized_url, "scrapeops_basic_company"),
        ("scrapeops", "residential", jobs_url, "scrapeops_residential_jobs"),
        ("scrapeops", "residential", normalized_url, "scrapeops_residential_company"),
        ("scrapeops", "render_js_residential", jobs_url, "scrapeops_residential_js_jobs"),
        ("scrapeops", "render_js_residential", normalized_url, "scrapeops_residential_js_company"),
    ]
    if browser_first:
        plan = browser_plan + (webshare_plan if webshare_only else webshare_plan + scrapeops_plan)
    else:
        plan = webshare_plan if webshare_only else webshare_plan + scrapeops_plan
    context = pool.get()
    previous = state.get_resolution(normalized_url) or {}
    records: list[dict[str, Any]] = list(previous.get("records") or [])
    all_ids: set[str] = set(str(value) for value in previous.get("observed_contextual_ids") or [] if numeric_id(value))
    for previous_record in records:
        values = previous_record.get("ID_values")
        if isinstance(values, (list, tuple, set)):
            all_ids.update(str(value) for value in values if numeric_id(value))
        if numeric_id(previous_record.get("ID_value")):
            all_ids.add(numeric_id(previous_record.get("ID_value")))
    decision = previous.get("reconciliation_decision") or {}
    selected_reconciliation_id = numeric_id(decision.get("selected_id"))
    all_evidence: list[str] = []
    for previous_record in records:
        all_evidence.extend(str(value) for value in previous_record.get("ID_evidence_sources") or [])
    last_error = ""
    for transport, mode, requested_url, stage in plan:
        reserved = 0.0
        safety_decision = None
        estimated_cost = float(estimate_mode_native_credits(mode)) if transport == "scrapeops" else 0.0
        if safety is not None:
            safety_decision = safety.allow(normalized_url, transport, estimated_cost=estimated_cost)
            if not safety_decision.allowed:
                last_error = f"safety_guard:{safety_decision.reason}"
                continue
        if transport == "scrapeops":
            reservation = ledger.reserve(mode)
            if reservation is None:
                if safety is not None and safety_decision is not None:
                    safety.cancel(safety_decision)
                last_error = "global_scrapeops_credit_budget_exhausted"
                payload = {
                    "linkedin_slug": group["linkedin_slug"],
                    "source_row_numbers": group["source_row_numbers"],
                    "canonical_company_ids": group["canonical_company_ids"],
                    "stage": stage,
                    "records": records,
                    "actual_credits": 0,
                    "estimated_credits": 0,
                    "billing_unknown_credits": 0,
                    "last_error": last_error,
                    "observed_contextual_ids": sorted(all_ids),
                    "input_evidence_fingerprint": group.get("input_evidence_fingerprint", ""),
                    "output_fields": _output_fields(normalized_url=normalized_url, status="CREDIT_BUDGET_EXHAUSTED", evidence={"normalized_linkedin_url": normalized_url, "requests": records, "reason": last_error}),
                }
                state.put_resolution(normalized_url, payload)
                return payload
            reserved = reservation
        record, ids, evidence = _fetch_one(
            context,
            transport=transport,
            mode=mode,
            normalized_url=normalized_url,
            requested_url=requested_url,
            stage=stage,
            reserved_credits=reserved,
        )
        if transport == "scrapeops":
            ledger.settle(reserved, record)
        if safety is not None and safety_decision is not None:
            safety.record(
                safety_decision,
                normalized_url=normalized_url,
                provider=transport,
                classification=str(record.get("classification") or "network_error"),
                success=bool(len(ids) == 1),
                estimated_cost=reserved,
                error=str(record.get("error") or ""),
            )
        state.log_request(normalized_url, record)
        records.append(record)
        all_ids.update(ids)
        all_evidence.extend(evidence)
        if record.get("error"):
            last_error = str(record["error"])
        if len(ids) == 1 and len(all_ids) == 1:
            company_id = ids[0]
            source_evidence = evidence[0] if evidence else "linkedin_company_context"
            source = f"{transport}_{source_evidence}"
            payload = {
                "linkedin_slug": group["linkedin_slug"],
                "source_row_numbers": group["source_row_numbers"],
                "canonical_company_ids": group["canonical_company_ids"],
                "stage": stage,
                "records": records,
                "observed_contextual_ids": sorted(all_ids),
                "input_evidence_fingerprint": group.get("input_evidence_fingerprint", ""),
                "actual_credits": sum(float(item.get("actual_credits") or 0) for item in records),
                "estimated_credits": sum(float(item.get("estimated_credits") or 0) for item in records if item.get("cost_status") == "estimated"),
                "billing_unknown_credits": sum(float(item.get("estimated_credits") or 0) for item in records if item.get("cost_status") == "billing_unknown"),
                "last_error": "",
            }
            payload["output_fields"] = _output_fields(
                normalized_url=normalized_url,
                status="RESOLVED",
                company_id=company_id,
                source=source,
                confidence=1.0 if source_evidence in {"linkedin_jobs_f_C", "linkedin_page_f_C", "linkedin_company_urn"} else 0.95,
                resolved_at=utc_now(),
                transport=transport,
                url_used=requested_url,
                evidence={
                    "normalized_linkedin_url": normalized_url,
                    "linkedin_slug": group["linkedin_slug"],
                    "id": company_id,
                    "id_evidence_sources": list(dict.fromkeys(all_evidence)),
                    "response_classification": record.get("classification", ""),
                    "requests": records,
                },
            )
            state.put_resolution(normalized_url, payload)
            return payload

    if len(all_ids) > 1:
        if selected_reconciliation_id and selected_reconciliation_id in all_ids:
            status = "RESOLVED"
            reason = "explicit_reconciliation_decision"
        else:
            status = "AMBIGUOUS"
            reason = "contradictory_contextual_company_ids_requires_reconciliation"
    else:
        status = "UNRESOLVED"
        reason = last_error or "no_contextual_company_id_found"
    payload = {
        "linkedin_slug": group["linkedin_slug"],
        "source_row_numbers": group["source_row_numbers"],
        "canonical_company_ids": group["canonical_company_ids"],
        "stage": records[-1].get("stage", "") if records else "",
        "records": records,
        "observed_contextual_ids": sorted(all_ids),
        "input_evidence_fingerprint": group.get("input_evidence_fingerprint", ""),
        "actual_credits": sum(float(item.get("actual_credits") or 0) for item in records),
        "estimated_credits": sum(float(item.get("estimated_credits") or 0) for item in records if item.get("cost_status") == "estimated"),
        "billing_unknown_credits": sum(float(item.get("estimated_credits") or 0) for item in records if item.get("cost_status") == "billing_unknown"),
        "last_error": reason,
    }
    payload["output_fields"] = _output_fields(
        normalized_url=normalized_url,
        status=status,
        company_id=selected_reconciliation_id if status == "RESOLVED" and selected_reconciliation_id else "",
        source="reconciliation_decision" if status == "RESOLVED" and selected_reconciliation_id else "",
        confidence=0.9 if status == "RESOLVED" and selected_reconciliation_id else 0.0,
        resolved_at=utc_now() if status == "RESOLVED" and selected_reconciliation_id else "",
        evidence={"normalized_linkedin_url": normalized_url, "requests": records, "reason": reason, "ids_seen": sorted(all_ids), "reconciliation_decision": decision},
        transport=records[-1].get("transport", "") if records else "",
        url_used=records[-1].get("requested_url", "") if records else "",
    )
    state.put_resolution(normalized_url, payload)
    return payload


def budget_payload(group: dict[str, Any]) -> dict[str, Any]:
    normalized_url = group["normalized_url"]
    reason = "global_scrapeops_credit_budget_exhausted"
    return {
        "linkedin_slug": group["linkedin_slug"],
        "source_row_numbers": group["source_row_numbers"],
        "canonical_company_ids": group["canonical_company_ids"],
        "stage": "budget_guard",
        "records": [],
        "observed_contextual_ids": [],
        "input_evidence_fingerprint": group.get("input_evidence_fingerprint", ""),
        "actual_credits": 0,
        "estimated_credits": 0,
        "billing_unknown_credits": 0,
        "last_error": reason,
        "output_fields": _output_fields(normalized_url=normalized_url, status="CREDIT_BUDGET_EXHAUSTED", evidence={"normalized_linkedin_url": normalized_url, "reason": reason}),
    }


def apply_payload(rows: list[dict[str, Any]], indices: list[int], payload: dict[str, Any]) -> None:
    fields = payload.get("output_fields", {})
    for index in indices:
        rows[index].update(fields)


def counts_for_groups(groups: dict[str, dict[str, Any]], results: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(payload.get("output_fields", {}).get("linkedin_company_id_status") or "PENDING") for payload in results.values())
    return {key: int(counts.get(key, 0)) for key in ("RESOLVED", "HIGH_CONFIDENCE", "AMBIGUOUS", "UNRESOLVED", "CREDIT_BUDGET_EXHAUSTED", "INVALID_LINKEDIN_URL", "PENDING")}


def build_report(
    *,
    source_path: Path,
    output_path: Path,
    state: ResolutionState,
    groups: dict[str, dict[str, Any]],
    results: dict[str, dict[str, Any]],
    rows: list[dict[str, Any]],
    source_hash: str,
    ledger: CreditLedger,
    status: str,
    guard_reserved: float | None = None,
    webshare_only: bool = False,
    retry_unresolved: bool = False,
    webshare_rotate_each_request: bool = False,
    browser_first: bool = False,
    browser_engine: str = "",
    browser_timeout: float = 45.0,
    safety: PersistentResolverSafety | None = None,
) -> dict[str, Any]:
    state_counts = counts_for_groups(groups, results)
    resolved_urls = [url for url, payload in results.items() if payload.get("output_fields", {}).get("linkedin_company_id")]
    row_ids = sum(bool(row.get("linkedin_company_id")) for row in rows)
    transport_counts = Counter(
        str(results[url].get("output_fields", {}).get("linkedin_company_id_transport") or "")
        for url in resolved_urls
    )
    challenge_recovered = 0
    unresolved_reasons = Counter()
    for url, payload in results.items():
        output = payload.get("output_fields", {})
        record_classes = {str(record.get("classification") or "").casefold() for record in payload.get("records", [])}
        if output.get("linkedin_company_id") and record_classes & CHALLENGE_CLASSIFICATIONS:
            challenge_recovered += 1
        if output.get("linkedin_company_id_status") in {"UNRESOLVED", "AMBIGUOUS", "CREDIT_BUDGET_EXHAUSTED"}:
            unresolved_reasons[str(payload.get("last_error") or output.get("linkedin_company_id_status"))] += 1
    duplicate_rows_populated = sum(max(0, len(group["source_row_numbers"]) - 1) for url, group in groups.items() if url in resolved_urls)
    ledger_data = ledger.snapshot()
    safety_data = safety.snapshot() if safety is not None else {}
    guard_reserved = float(guard_reserved if guard_reserved is not None else ledger_data["reserved"])
    unique_processed = sum(state_counts[key] for key in ("RESOLVED", "HIGH_CONFIDENCE", "AMBIGUOUS", "UNRESOLVED"))
    all_processed = unique_processed == len(groups)
    return {
        "run_status": status,
        "source_path": str(source_path),
        "output_path": str(output_path),
        "state_path": str(state.path),
        "source_sha256": source_hash,
        "source_unchanged": sha256(source_path) == source_hash,
        "total_source_rows": len(rows),
        "rows_with_valid_linkedin_organization_urls": sum(len(group["source_row_numbers"]) for group in groups.values()),
        "rows_without_valid_linkedin_organization_urls": len(rows) - sum(len(group["source_row_numbers"]) for group in groups.values()),
        "unique_normalized_linkedin_urls": len(groups),
        "unique_urls_processed_terminal": unique_processed,
        "unique_urls_resolved": len(resolved_urls),
        "unique_urls_unresolved_or_ambiguous": state_counts["UNRESOLVED"] + state_counts["AMBIGUOUS"],
        "resolution_rate": round(len(resolved_urls) / len(groups), 6) if groups else 0.0,
        "source_rows_populated_with_ids": row_ids,
        "ids_reused_from_existing_data": transport_counts.get("existing", 0),
        "ids_from_webshare": transport_counts.get("webshare", 0),
        "ids_from_playwright": transport_counts.get("playwright", 0),
        "ids_from_scrapeops_basic": sum(1 for url in resolved_urls if results[url].get("output_fields", {}).get("linkedin_company_id_transport") == "scrapeops" and str(results[url].get("stage", "")).startswith("scrapeops_basic_")),
        "ids_from_residential": sum(1 for url in resolved_urls if results[url].get("output_fields", {}).get("linkedin_company_id_transport") == "scrapeops" and str(results[url].get("stage", "")).startswith("scrapeops_residential_") and "js" not in str(results[url].get("stage", ""))),
        "ids_from_residential_js": sum(1 for url in resolved_urls if results[url].get("output_fields", {}).get("linkedin_company_id_transport") == "scrapeops" and str(results[url].get("stage", "")).startswith("scrapeops_residential_js_")),
        "ids_recovered_from_challenge_or_blocked_pages": challenge_recovered,
        "duplicate_source_rows_populated_from_shared_linkedin_url": duplicate_rows_populated,
        "status_distribution": state_counts,
        "unresolved_reason_distribution": dict(unresolved_reasons),
        "scrapeops_credits_used_actual_known": ledger_data["actual"],
        "scrapeops_credits_estimated": ledger_data["estimated"],
        "scrapeops_credits_billing_unknown_estimate": ledger_data["billing_unknown"],
        "scrapeops_credits_conservative_accounted": ledger_data["conservative"],
        "scrapeops_credit_guard_reserved": round(guard_reserved, 3),
        "scrapeops_credits_remaining_conservative": max(0.0, ledger_data["limit"] - guard_reserved) if status != "BUDGET_EXHAUSTED" else 0.0,
        "scrapeops_credit_budget": ledger_data["limit"],
        "resolver_safety": safety_data,
        "resolver_safety_path": str(safety.path) if safety is not None else "",
        "average_paid_credits_per_newly_resolved_id": round(ledger_data["conservative"] / len(resolved_urls), 3) if resolved_urls else None,
        "all_unique_linkedin_urls_processed": all_processed,
        "processing_stop_reason": "all_unique_urls_terminal" if all_processed else (f"{int(ledger_data['limit']):,}_credit_guard_exhausted" if state_counts["CREDIT_BUDGET_EXHAUSTED"] else "run_incomplete_or_interrupted"),
        "configuration": {
            "id_only": True,
            "webshare_first": True,
            "webshare_only": webshare_only,
            "retry_unresolved": retry_unresolved,
            "webshare_rotate_each_request": webshare_rotate_each_request,
            "browser_first": browser_first,
            "browser_engine": browser_engine,
            "browser_timeout_seconds": browser_timeout,
            "request_order": (["playwright_all_jobs"] if browser_first else []) + (["webshare_jobs", "webshare_company"] if webshare_only else ["webshare_jobs", "webshare_company", "scrapeops_basic_jobs", "scrapeops_basic_company", "scrapeops_residential_jobs", "scrapeops_residential_company", "scrapeops_residential_js_jobs", "scrapeops_residential_js_company"]),
            "webshare_timeout_seconds": 10,
            "scrapeops_timeout_seconds": 30,
            "scrapeops_modes": list(SCRAPEOPS_MODES),
            "max_scrapeops_credit_budget": ledger_data["limit"],
            "cache_bypassed_for_live_transports": True,
            "source_overwrite": False,
            "resolver_safety": {
                "persistent": safety is not None,
                "total_request_limit": safety.config.total_request_limit if safety is not None else None,
                "provider_request_limit": safety.config.provider_request_limit if safety is not None else None,
                "rolling_window_seconds": safety.config.rolling_window_seconds if safety is not None else None,
                "cooldown_base_seconds": safety.config.cooldown_base_seconds if safety is not None else None,
                "cooldown_max_seconds": safety.config.cooldown_max_seconds if safety is not None else None,
                "circuit_failure_threshold": safety.config.circuit_failure_threshold if safety is not None else None,
                "circuit_open_seconds": safety.config.circuit_open_seconds if safety is not None else None,
            },
        },
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# LinkedIn Company ID Resolution Report",
                "",
                f"Status: **{report['run_status']}**",
                f"Source rows: **{report['total_source_rows']}**",
                f"Rows with valid LinkedIn organization URLs: **{report['rows_with_valid_linkedin_organization_urls']}**",
                f"Rows without valid LinkedIn organization URLs: **{report['rows_without_valid_linkedin_organization_urls']}**",
                f"Unique normalized LinkedIn URLs: **{report['unique_normalized_linkedin_urls']}**",
                f"Unique URLs resolved: **{report['unique_urls_resolved']}**",
                f"Resolution rate: **{report['resolution_rate']:.2%}**",
                f"Source rows populated with IDs: **{report['source_rows_populated_with_ids']}**",
                f"Duplicate source rows populated from shared URLs: **{report['duplicate_source_rows_populated_from_shared_linkedin_url']}**",
                "",
                "## Resolution sources",
                "",
                f"- Existing data: {report['ids_reused_from_existing_data']}",
                f"- Webshare: {report['ids_from_webshare']}",
                f"- Playwright browser: {report['ids_from_playwright']}",
                f"- ScrapeOps basic: {report['ids_from_scrapeops_basic']}",
                f"- Residential: {report['ids_from_residential']}",
                f"- Residential + JS: {report['ids_from_residential_js']}",
                f"- IDs recovered from challenge/blocked pages: {report['ids_recovered_from_challenge_or_blocked_pages']}",
                "",
                "## Browser flow",
                "",
                f"- Browser-first: **{report['configuration']['browser_first']}**",
                f"- Engine: **{report['configuration']['browser_engine'] or 'not used in finalized state'}**",
                "- Company page flow: **open company page → click company Jobs tab → click Show all jobs → read f_C from the resulting URL**",
                "",
                "## Statuses",
                "",
                f"```json\n{json.dumps(report['status_distribution'], indent=2)}\n```",
                "",
                "## Credit accounting",
                "",
                f"- Actual credits known: **{report['scrapeops_credits_used_actual_known']}**",
                f"- Estimated credits: **{report['scrapeops_credits_estimated']}**",
                f"- Billing-unknown estimate: **{report['scrapeops_credits_billing_unknown_estimate']}**",
                f"- Conservative accounted credits: **{report['scrapeops_credits_conservative_accounted']}** / **{report['scrapeops_credit_budget']}**",
                f"- Credit-guard reservation at stop: **{report['scrapeops_credit_guard_reserved']}**",
                f"- Conservative credits remaining: **{report['scrapeops_credits_remaining_conservative']}**",
                f"- Average paid credits per newly resolved URL: **{report['average_paid_credits_per_newly_resolved_id']}**",
                "",
                "## Durable resolver safety",
                "",
                f"- Rolling request window: **{report['configuration']['resolver_safety']['rolling_window_seconds']} seconds**",
                f"- Requests recorded in window: **{report.get('resolver_safety', {}).get('total_requests', 0)}**",
                f"- Requests reserved in window: **{report.get('resolver_safety', {}).get('total_reserved_requests', 0)}**",
                f"- Safety database: **{report.get('resolver_safety_path') or 'not configured'}**",
                "- Cooldowns, provider ceilings, circuit state and reservations are persisted in SQLite.",
                "",
                "## Completion",
                "",
                f"- All unique URLs processed: **{report['all_unique_linkedin_urls_processed']}**",
                f"- Stop reason: **{report['processing_stop_reason']}**",
                f"- Source unchanged: **{report['source_unchanged']}**",
                f"- Source SHA-256: `{report['source_sha256']}`",
                "",
                "Unresolved reason distribution:",
                f"```json\n{json.dumps(report['unresolved_reason_distribution'], indent=2, ensure_ascii=False)}\n```",
                "",
            ]
        ),
        encoding="utf-8",
    )


def make_groups(rows: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
    invalid_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        normalized = normalize_linkedin_url(row.get("linkedin_company_url"))
        if not normalized or linkedin_page_type(normalized) not in SUPPORTED_PAGE_TYPES:
            invalid_rows.append({"index": index, "normalized_url": normalized})
            continue
        group = groups.setdefault(
            normalized,
            {
                "normalized_url": normalized,
                "linkedin_slug": linkedin_slug(normalized),
                "source_row_numbers": [],
                "row_indices": [],
                "canonical_company_ids": [],
                "input_evidence_fingerprint": "",
            },
        )
        group["source_row_numbers"].append(index + 2)
        group["row_indices"].append(index)
        canonical = str(row.get("canonical_CompanyID") or "").strip()
        if canonical and canonical not in group["canonical_company_ids"]:
            group["canonical_company_ids"].append(canonical)
        group["input_evidence_fingerprint"] = evidence_fingerprint(
            {
                "normalized_url": normalized,
                "canonical_company_ids": sorted(group["canonical_company_ids"]),
            }
        )
    return dict(groups), invalid_rows


def existing_id_payload(group: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    ids = {numeric_id(rows[index].get("linkedin_company_id")) for index in group["row_indices"]}
    ids.discard("")
    raw_values = {str(rows[index].get("linkedin_company_id") or "").strip() for index in group["row_indices"] if str(rows[index].get("linkedin_company_id") or "").strip()}
    if len(ids) != 1 or len(raw_values) != 1:
        return None
    company_id = next(iter(ids))
    output = _output_fields(
        normalized_url=group["normalized_url"],
        status="RESOLVED",
        company_id=company_id,
        source="existing_data",
        confidence=1.0,
        evidence={"normalized_linkedin_url": group["normalized_url"], "source": "existing_data"},
        transport="existing",
        url_used=group["normalized_url"],
    )
    return {
        "linkedin_slug": group["linkedin_slug"],
        "source_row_numbers": group["source_row_numbers"],
        "canonical_company_ids": group["canonical_company_ids"],
        "stage": "existing_data",
        "records": [],
        "observed_contextual_ids": [],
        "input_evidence_fingerprint": group.get("input_evidence_fingerprint", ""),
        "actual_credits": 0,
        "estimated_credits": 0,
        "billing_unknown_credits": 0,
        "last_error": "",
        "output_fields": output,
    }


def existing_social_id_payload(group: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Reuse one consistent ID already present in the source socials JSON."""
    ids: set[str] = set()
    for index in group["row_indices"]:
        raw = str(rows[index].get("socials_json") or "").strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        entries = parsed if isinstance(parsed, list) else [parsed]
        for entry in entries:
            if isinstance(entry, dict):
                company_id = numeric_id(entry.get("linkedin_id"))
                if company_id:
                    ids.add(company_id)
    if len(ids) != 1:
        return None
    company_id = next(iter(ids))
    output = _output_fields(
        normalized_url=group["normalized_url"],
        status="RESOLVED",
        company_id=company_id,
        source="existing_socials_json",
        confidence=0.95,
        evidence={"normalized_linkedin_url": group["normalized_url"], "source": "socials_json", "id": company_id},
        transport="existing",
        url_used=group["normalized_url"],
    )
    return {
        "linkedin_slug": group["linkedin_slug"],
        "source_row_numbers": group["source_row_numbers"],
        "canonical_company_ids": group["canonical_company_ids"],
        "stage": "existing_socials_json",
        "records": [],
        "observed_contextual_ids": [],
        "input_evidence_fingerprint": group.get("input_evidence_fingerprint", ""),
        "actual_credits": 0,
        "estimated_credits": 0,
        "billing_unknown_credits": 0,
        "last_error": "",
        "output_fields": output,
    }


def progress_line(
    *,
    completed: int,
    total: int,
    results: dict[str, dict[str, Any]],
    ledger: CreditLedger,
    current: str = "",
) -> None:
    counts = counts_for_groups({}, results)
    snapshot = ledger.snapshot()
    message = (
        f"Processed {completed:,}/{total:,} | Resolved {counts['RESOLVED'] + counts['HIGH_CONFIDENCE']:,} | "
        f"Unresolved {counts['UNRESOLVED'] + counts['AMBIGUOUS']:,} | Credit-exhausted {counts['CREDIT_BUDGET_EXHAUSTED']:,} | "
        f"ScrapeOps conservative {snapshot['conservative']:,.0f}/{snapshot['limit']:,.0f}"
    )
    if current:
        message += f" | Current {current[:90]}"
    print("\r" + message.ljust(220), end="", flush=True)


def run(args: argparse.Namespace) -> dict[str, Any]:
    source_path = args.input.resolve()
    output_path = args.output.resolve()
    state_dir = args.state_dir.resolve()
    report_path = args.report.resolve()
    markdown_path = args.markdown_report.resolve()
    request_log_path = args.request_log.resolve()
    if source_path == output_path:
        raise ValueError("source_overwrite_forbidden")
    fields, rows = read_csv(source_path)
    source_hash = sha256(source_path)
    groups, invalid_rows = make_groups(rows)
    state = ResolutionState(state_dir)
    ledger = CreditLedger(args.scrapeops_budget)
    safety = PersistentResolverSafety(
        state_dir / "resolver_safety.sqlite3",
        config=SafetyConfig(
            total_request_limit=max(1, int(getattr(args, "max_requests_total", 50_000))),
            provider_request_limit=max(1, int(getattr(args, "max_requests_per_provider", 25_000))),
            scrapeops_credit_limit=max(0.0, float(args.scrapeops_budget)),
            rolling_window_seconds=max(1.0, float(getattr(args, "rolling_budget_window_seconds", 3600.0))),
            cooldown_base_seconds=max(0.0, float(getattr(args, "retry_cooldown_seconds", 30.0))),
            cooldown_max_seconds=max(0.0, float(getattr(args, "retry_cooldown_max_seconds", 900.0))),
            circuit_failure_threshold=max(1, int(getattr(args, "circuit_failure_threshold", 3))),
            circuit_open_seconds=max(0.0, float(getattr(args, "circuit_open_seconds", 300.0))),
        ),
    )
    state.set_meta("source_sha256", source_hash)
    state.set_meta("source_path", str(source_path))
    state.set_meta("budget", args.scrapeops_budget)
    state.set_meta("resolver_safety_path", str(state_dir / "resolver_safety.sqlite3"))
    state.set_meta(
        "resolver_safety_config",
        {
            "total_request_limit": safety.config.total_request_limit,
            "provider_request_limit": safety.config.provider_request_limit,
            "rolling_window_seconds": safety.config.rolling_window_seconds,
            "cooldown_base_seconds": safety.config.cooldown_base_seconds,
            "cooldown_max_seconds": safety.config.cooldown_max_seconds,
            "circuit_failure_threshold": safety.config.circuit_failure_threshold,
            "circuit_open_seconds": safety.config.circuit_open_seconds,
        },
    )
    state.set_meta("started_at", utc_now())
    state.set_meta("status", "running")

    output_fields = list(dict.fromkeys([*fields, *OUTPUT_COLUMNS]))
    for row in rows:
        for field in OUTPUT_COLUMNS:
            row.setdefault(field, "")
    for invalid in invalid_rows:
        rows[invalid["index"]].update(_output_fields(normalized_url="", status="INVALID_LINKEDIN_URL", evidence={"reason": "missing_or_non_organization_linkedin_url"}))

    results = state.get_resolutions()
    retryable_statuses = {"UNRESOLVED", "AMBIGUOUS", "CREDIT_BUDGET_EXHAUSTED"} if args.retry_unresolved else set()
    restored_credits = state.get_credit_totals()
    ledger.restore(**restored_credits)
    for url, group in groups.items():
        saved = results.get(url)
        saved_status = saved.get("output_fields", {}).get("linkedin_company_id_status") if saved else None
        evidence_unchanged = not saved or not saved.get("input_evidence_fingerprint") or saved.get("input_evidence_fingerprint") == group.get("input_evidence_fingerprint")
        retry_due = args.retry_unresolved and safety.retry_due(url, providers=("webshare", "playwright", "scrapeops"))
        if saved and saved_status in TERMINAL_STATUSES and evidence_unchanged and not (saved_status in retryable_statuses and retry_due):
            apply_payload(rows, group["row_indices"], saved)
            continue
        existing = existing_id_payload(group, rows)
        if existing is not None:
            state.put_resolution(url, existing)
            results[url] = existing
            apply_payload(rows, group["row_indices"], existing)
            continue
        existing_social = existing_social_id_payload(group, rows)
        if existing_social is not None:
            state.put_resolution(url, existing_social)
            results[url] = existing_social
            apply_payload(rows, group["row_indices"], existing_social)

    atomic_write_csv(output_path, output_fields, rows)
    pending = [
        group
        for url, group in groups.items()
        if url not in results
        or results[url].get("output_fields", {}).get("linkedin_company_id_status") not in TERMINAL_STATUSES
        or (
            results[url].get("output_fields", {}).get("linkedin_company_id_status") in retryable_statuses
            and safety.retry_due(url, providers=("webshare", "playwright", "scrapeops"))
        )
    ]
    completed = len(groups) - len(pending)
    pool = TransportPool(
        state_dir,
        webshare_timeout=args.webshare_timeout,
        scrapeops_timeout=args.scrapeops_timeout,
        webshare_rotate_each_request=args.webshare_rotate_each_request,
        browser_engine=args.browser_engine if args.browser_first else "",
        browser_timeout=args.browser_timeout,
    )
    active: dict[Any, dict[str, Any]] = {}
    pending_index = 0
    last_checkpoint = time.monotonic()
    try:
        if ledger.exhausted() and not args.webshare_only:
            for remaining in pending:
                payload = budget_payload(remaining)
                state.put_resolution(remaining["normalized_url"], payload)
                results[remaining["normalized_url"]] = payload
                apply_payload(rows, remaining["row_indices"], payload)
                completed += 1
            pending = []
            atomic_write_csv(output_path, output_fields, rows)
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            while pending_index < len(pending) and len(active) < max(1, args.workers):
                group = pending[pending_index]
                pending_index += 1
                active[executor.submit(resolve_one, group, state=state, pool=pool, ledger=ledger, webshare_only=args.webshare_only, browser_first=args.browser_first, safety=safety)] = group
            while active:
                done, _ = wait(active, timeout=5, return_when=FIRST_COMPLETED)
                if not done:
                    progress_line(completed=completed, total=len(groups), results=results, ledger=ledger, current=next(iter(active.values()))["normalized_url"] if active else "")
                    continue
                for future in done:
                    group = active.pop(future)
                    try:
                        payload = future.result()
                    except Exception as exc:
                        payload = {
                            "linkedin_slug": group["linkedin_slug"],
                            "source_row_numbers": group["source_row_numbers"],
                            "canonical_company_ids": group["canonical_company_ids"],
                            "stage": "worker_exception",
                            "records": [],
                            "actual_credits": 0,
                            "estimated_credits": 0,
                            "billing_unknown_credits": 0,
                            "last_error": f"{type(exc).__name__}:{str(exc)[:200]}",
                            "output_fields": _output_fields(normalized_url=group["normalized_url"], status="UNRESOLVED", evidence={"reason": "worker_exception", "error": f"{type(exc).__name__}:{str(exc)[:200]}"}),
                        }
                        state.put_resolution(group["normalized_url"], payload)
                    results[group["normalized_url"]] = payload
                    apply_payload(rows, group["row_indices"], payload)
                    completed += 1
                    if completed % args.checkpoint_every == 0 or time.monotonic() - last_checkpoint >= args.checkpoint_seconds:
                        atomic_write_csv(output_path, output_fields, rows)
                        state.set_meta("completed_unique_urls", completed)
                        state.set_meta("credit_snapshot", ledger.snapshot())
                        last_checkpoint = time.monotonic()
                    progress_line(completed=completed, total=len(groups), results=results, ledger=ledger)
                    if ledger.exhausted() and not args.webshare_only:
                        for remaining in pending[pending_index:]:
                            payload = budget_payload(remaining)
                            state.put_resolution(remaining["normalized_url"], payload)
                            results[remaining["normalized_url"]] = payload
                            apply_payload(rows, remaining["row_indices"], payload)
                            completed += 1
                        pending_index = len(pending)
                    elif pending_index < len(pending):
                        next_group = pending[pending_index]
                        pending_index += 1
                        active[executor.submit(resolve_one, next_group, state=state, pool=pool, ledger=ledger, webshare_only=args.webshare_only, browser_first=args.browser_first, safety=safety)] = next_group
        atomic_write_csv(output_path, output_fields, rows)
        state.set_meta("status", "completed")
        state.set_meta("finished_at", utc_now())
        final_status = "COMPLETED" if args.webshare_only or not ledger.exhausted() else "BUDGET_EXHAUSTED"
    except KeyboardInterrupt:
        atomic_write_csv(output_path, output_fields, rows)
        state.set_meta("status", "interrupted")
        state.set_meta("interrupted_at", utc_now())
        final_status = "INTERRUPTED"
        raise
    finally:
        pool.close()
    report = build_report(
        source_path=source_path,
        output_path=output_path,
        state=state,
        groups=groups,
        results=results,
        rows=rows,
        source_hash=source_hash,
        ledger=ledger,
        status=final_status,
        webshare_only=args.webshare_only,
        retry_unresolved=args.retry_unresolved,
        webshare_rotate_each_request=args.webshare_rotate_each_request,
        browser_first=args.browser_first,
        browser_engine=args.browser_engine,
        browser_timeout=args.browser_timeout,
        safety=safety,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(report, markdown_path)
    state.export_requests(request_log_path)
    state.set_meta("report_path", str(report_path))
    state.close()
    safety.close()
    print()
    print(json.dumps({"event": "id_resolution_finished", **{key: report[key] for key in ("run_status", "unique_normalized_linkedin_urls", "unique_urls_resolved", "resolution_rate", "scrapeops_credits_conservative_accounted", "processing_stop_reason")}}, ensure_ascii=False, sort_keys=True))
    return report


def finalize_existing_run(args: argparse.Namespace) -> dict[str, Any]:
    """Write final artifacts from durable state without making network calls."""
    source_path = args.input.resolve()
    output_path = args.output.resolve()
    state_dir = args.state_dir.resolve()
    report_path = args.report.resolve()
    markdown_path = args.markdown_report.resolve()
    request_log_path = args.request_log.resolve()
    fields, rows = read_csv(source_path)
    source_hash = sha256(source_path)
    groups, invalid_rows = make_groups(rows)
    state = ResolutionState(state_dir)
    results = state.get_resolutions()
    ledger = CreditLedger(args.scrapeops_budget)
    ledger.restore(**state.get_credit_totals())
    output_fields = list(dict.fromkeys([*fields, *OUTPUT_COLUMNS]))
    for row in rows:
        for field in OUTPUT_COLUMNS:
            row.setdefault(field, "")
    for invalid in invalid_rows:
        rows[invalid["index"]].update(_output_fields(normalized_url="", status="INVALID_LINKEDIN_URL", evidence={"reason": "missing_or_non_organization_linkedin_url"}))
    for url, group in groups.items():
        payload = results.get(url)
        if payload:
            apply_payload(rows, group["row_indices"], payload)
    atomic_write_csv(output_path, output_fields, rows)
    status_counts = counts_for_groups(groups, results)
    final_status = "BUDGET_EXHAUSTED" if status_counts["CREDIT_BUDGET_EXHAUSTED"] else "COMPLETED"
    report = build_report(
        source_path=source_path,
        output_path=output_path,
        state=state,
        groups=groups,
        results=results,
        rows=rows,
        source_hash=source_hash,
        ledger=ledger,
        status=final_status,
        guard_reserved=(state.get_meta("credit_snapshot") or {}).get("reserved") if isinstance(state.get_meta("credit_snapshot"), dict) else None,
        webshare_only=args.webshare_only,
        retry_unresolved=args.retry_unresolved,
        webshare_rotate_each_request=args.webshare_rotate_each_request,
        browser_first=args.browser_first,
        browser_engine=args.browser_engine,
        browser_timeout=args.browser_timeout,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(report, markdown_path)
    state.export_requests(request_log_path)
    state.set_meta("status", "finalized")
    state.set_meta("report_path", str(report_path))
    state.close()
    print(json.dumps({"event": "id_resolution_report_finalized", "report_path": str(report_path), "run_status": final_status, "unique_urls_resolved": report["unique_urls_resolved"], "credits_conservative": report["scrapeops_credits_conservative_accounted"]}, ensure_ascii=False, sort_keys=True))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=SOURCE_DEFAULT)
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    parser.add_argument("--state-dir", type=Path, default=STATE_DEFAULT)
    parser.add_argument("--report", type=Path, default=REPORT_DEFAULT)
    parser.add_argument("--markdown-report", type=Path, default=MARKDOWN_REPORT_DEFAULT)
    parser.add_argument("--request-log", type=Path, default=REQUEST_LOG_DEFAULT)
    parser.add_argument("--workers", type=int, default=25)
    parser.add_argument("--scrapeops-budget", type=float, default=70000.0)
    parser.add_argument("--webshare-timeout", type=float, default=10.0)
    parser.add_argument("--scrapeops-timeout", type=int, default=30)
    parser.add_argument("--checkpoint-every", type=int, default=25)
    parser.add_argument("--checkpoint-seconds", type=float, default=30.0)
    parser.add_argument("--max-requests-total", type=int, default=50000, help="Persistent rolling request ceiling across all providers.")
    parser.add_argument("--max-requests-per-provider", type=int, default=25000, help="Persistent rolling request ceiling per provider.")
    parser.add_argument("--rolling-budget-window-seconds", type=float, default=3600.0, help="Rolling request/credit budget window.")
    parser.add_argument("--retry-cooldown-seconds", type=float, default=30.0, help="Initial durable per-URL/provider retry cooldown.")
    parser.add_argument("--retry-cooldown-max-seconds", type=float, default=900.0, help="Maximum durable retry cooldown/backoff.")
    parser.add_argument("--circuit-failure-threshold", type=int, default=3, help="Provider failures before opening the circuit.")
    parser.add_argument("--circuit-open-seconds", type=float, default=300.0, help="Initial provider circuit-open duration.")
    parser.add_argument("--webshare-only", action="store_true", help="Retry all pending URLs with Webshare only; never call ScrapeOps.")
    parser.add_argument("--retry-unresolved", action="store_true", help="Retry previously terminal unresolved, ambiguous, or budget-exhausted URL groups.")
    parser.add_argument("--webshare-rotate-each-request", action="store_true", help="Round-robin Webshare's active proxy pool for each request.")
    parser.add_argument("--browser-first", action="store_true", help="Render company pages with a browser and click All jobs before HTTP fallbacks.")
    parser.add_argument("--browser-engine", choices=("playwright",), default="playwright")
    parser.add_argument("--browser-timeout", type=float, default=45.0)
    parser.add_argument("--report-only", action="store_true", help="Finalize CSV/report from SQLite state without network requests.")
    args = parser.parse_args(argv)
    if args.report_only:
        finalize_existing_run(args)
    else:
        run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
