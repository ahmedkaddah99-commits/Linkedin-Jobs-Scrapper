import hashlib
import json
import logging
import os
import re
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from backend.config.job_seeker import load_project_dotenv


LOGGER = logging.getLogger(__name__)
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Job-board strategies cache env-backed settings at import time, so load the
# project-level dotenv paths first instead of relying on a repo-root .env only.
load_project_dotenv()
SCRAPEOPS_API_KEY = (os.getenv("SCRAPEOPS_API_KEY") or "").strip()
_SCRAPEOPS_PROXY_HEALTH_CONFIRMED: ContextVar[bool] = ContextVar(
    "job_board_scrapeops_proxy_health_confirmed",
    default=False,
)
_SCRAPEOPS_USAGE_CALLBACK: ContextVar[Any] = ContextVar("job_board_scrapeops_usage_callback", default=None)
_SCRAPEOPS_SOURCE_ID: ContextVar[str] = ContextVar("job_board_scrapeops_source_id", default="job_board")


def compact_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def repair_mojibake(text: str) -> str:
    value = str(text or "")
    if "Ã" not in value and "Â" not in value:
        return value
    try:
        repaired = value.encode("latin1").decode("utf-8")
    except Exception:
        return value
    return repaired


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_fallback_job_id(portal: str, text: str) -> str:
    digest = hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]
    return f"{portal}_{digest}"


def extract_query_job_id(url: str, key: str, fallback_portal: str = "") -> str:
    try:
        parsed = urlparse(url)
        value = parse_qs(parsed.query).get(key, [""])[0].strip()
        if value:
            return value
    except Exception:
        pass
    if fallback_portal:
        return build_fallback_job_id(fallback_portal, url)
    return ""


def normalize_city_from_location(location_raw: str) -> str:
    text = compact_whitespace(location_raw)
    if not text:
        return ""
    first = re.split(r"[,|/]", text)[0].strip()
    return compact_whitespace(first)


def _new_session(timeout_seconds: int = 25) -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.headers.update(DEFAULT_HEADERS)
    session.request_timeout = max(5, int(timeout_seconds))
    return session


def reset_scrapeops_proxy_health_gate(*, usage_callback=None) -> None:
    _SCRAPEOPS_PROXY_HEALTH_CONFIRMED.set(False)
    _SCRAPEOPS_USAGE_CALLBACK.set(usage_callback)


def set_scrapeops_proxy_source(source_id: str) -> None:
    _SCRAPEOPS_SOURCE_ID.set(str(source_id or "job_board").strip() or "job_board")


def _proxy_get(url: str, params: Dict, timeout_seconds: int) -> requests.Response | None:
    if not SCRAPEOPS_API_KEY:
        return None
    if not _SCRAPEOPS_PROXY_HEALTH_CONFIRMED.get():
        from backend.integrations.scrapeops import require_scrapeops_proxy_health

        require_scrapeops_proxy_health(SCRAPEOPS_API_KEY, usage_callback=_SCRAPEOPS_USAGE_CALLBACK.get())
        _SCRAPEOPS_PROXY_HEALTH_CONFIRMED.set(True)
    try:
        from backend.integrations.scrapeops import (
            SCRAPEOPS_PROXY_ENDPOINT,
            billed_status_code,
            build_proxy_params,
            build_proxy_usage_record,
            estimate_mode_native_credits,
            parse_proxy_response_envelope,
        )

        prepared_url = requests.Request("GET", url, params=params).prepare().url
        proxy_params = build_proxy_params(
            api_key=SCRAPEOPS_API_KEY,
            url=str(prepared_url or url),
            mode="residential",
            country_code="de",
        )
        session = requests.Session()
        session.trust_env = False
        request_started = time.perf_counter()
        response = session.get(
            SCRAPEOPS_PROXY_ENDPOINT,
            params=proxy_params,
            headers=DEFAULT_HEADERS,
            timeout=max(5, int(timeout_seconds)),
        )
        envelope = parse_proxy_response_envelope(response)
        response.status_code = envelope.target_status_code
        response._content = envelope.body.encode(response.encoding or "utf-8")
        billed = billed_status_code(envelope.target_status_code)
        estimated_credits = estimate_mode_native_credits("residential") if billed else 0
        actual_credits = envelope.billed_credits_actual
        accounted_credits = actual_credits if actual_credits is not None else estimated_credits
        callback = _SCRAPEOPS_USAGE_CALLBACK.get()
        if callable(callback):
            callback(
                {
                    **build_proxy_usage_record(
                        source_id=_SCRAPEOPS_SOURCE_ID.get(),
                        target_url=str(prepared_url or url),
                        request_mode="residential",
                        target_status_code=envelope.target_status_code,
                        provider_status_code=envelope.provider_status_code,
                        latency_ms=round((time.perf_counter() - request_started) * 1000),
                        billed_credits_actual=actual_credits,
                        billed_credits_estimated=estimated_credits,
                        error_category="" if envelope.target_status_code < 400 else "target_http_error",
                    ),
                    "domain": (urlparse(str(prepared_url or url)).netloc or "").lower(),
                    "status_code": envelope.target_status_code,
                    "billed": billed,
                    "native_credits": accounted_credits,
                    "runner_credits": accounted_credits,
                }
            )
        return response
    except Exception as exc:
        callback = _SCRAPEOPS_USAGE_CALLBACK.get()
        if callable(callback) and "request_started" in locals() and "build_proxy_usage_record" in locals():
            callback(
                {
                    **build_proxy_usage_record(
                        source_id=_SCRAPEOPS_SOURCE_ID.get(),
                        target_url=str(locals().get("prepared_url") or url),
                        request_mode="residential",
                        target_status_code=0,
                        provider_status_code=0,
                        latency_ms=round((time.perf_counter() - request_started) * 1000),
                        billed_credits_actual=0,
                        billed_credits_estimated=0,
                        error_category="network_error",
                    ),
                    "domain": (urlparse(str(locals().get("prepared_url") or url)).netloc or "").lower(),
                    "status_code": 0,
                    "billed": False,
                    "native_credits": 0,
                    "runner_credits": 0,
                }
            )
        LOGGER.warning("Job board ScrapeOps fallback failed for %s: %s", url, exc)
        return None


def _normalize_job_record(portal: str, raw: Dict) -> Dict:
    title = compact_whitespace(repair_mojibake(str(raw.get("title") or "")))
    company = compact_whitespace(repair_mojibake(str(raw.get("company") or "")))
    location_raw = compact_whitespace(repair_mojibake(str(raw.get("location_raw") or "")))
    city = normalize_city_from_location(location_raw)
    job_id = str(raw.get("job_id") or "").strip()
    link = str(raw.get("link") or "").strip()
    apply_link = str(raw.get("apply_link") or link).strip()
    description = compact_whitespace(repair_mojibake(str(raw.get("description") or "")))
    snippet = compact_whitespace(repair_mojibake(str(raw.get("snippet") or "")))
    posted_text = compact_whitespace(str(raw.get("posted_text") or ""))

    if not job_id:
        seed = f"{portal}|{title}|{company}|{location_raw}|{link}"
        job_id = build_fallback_job_id(portal, seed)

    return {
        "job_id": job_id,
        "portal": portal,
        "title": title,
        "company": company,
        "location_raw": location_raw,
        "city": city,
        "posted_text": posted_text,
        "description": description,
        "snippet": snippet,
        "link": link,
        "apply_link": apply_link,
        "source_keyword": str(raw.get("source_keyword") or ""),
        "source_city": str(raw.get("source_city") or ""),
        "collected_at_utc": raw.get("collected_at_utc") or now_utc_iso(),
    }


def scrape_indeed_jobs(
    keyword: str,
    city: str,
    max_pages: int,
    posted_within_days: int,
    timeout_seconds: int,
) -> Tuple[List[Dict], List[str]]:
    portal = "indeed"
    errors: List[str] = []
    jobs: List[Dict] = []
    session = _new_session(timeout_seconds=timeout_seconds)

    for page in range(max_pages):
        params = {
            "q": keyword,
            "l": city,
            "sort": "date",
            "start": page * 10,
        }
        if posted_within_days > 0:
            params["fromage"] = posted_within_days

        try:
            response = session.get(
                "https://de.indeed.com/jobs",
                params=params,
                timeout=session.request_timeout,
            )
        except Exception as exc:
            errors.append(f"{portal} page={page + 1} error={exc}")
            continue

        if response.status_code in (403, 429):
            proxy_response = _proxy_get(
                url="https://de.indeed.com/jobs",
                params=params,
                timeout_seconds=session.request_timeout,
            )
            if proxy_response is not None:
                response = proxy_response

        if response.status_code != 200:
            errors.append(f"{portal} page={page + 1} status={response.status_code}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        cards = soup.select("div.job_seen_beacon")

        if not cards:
            cards = []
            for anchor in soup.select("a[href*='/viewjob']"):
                parent = anchor.find_parent("div")
                if parent:
                    cards.append(parent)

        if not cards and page > 0:
            break

        seen_on_page = 0
        for card in cards:
            title_link = card.select_one("h2.jobTitle a") or card.select_one("a[href*='/viewjob']")
            if not title_link:
                continue

            title = compact_whitespace(title_link.get_text(" ", strip=True))
            if not title:
                continue

            href = str(title_link.get("href") or "").strip()
            if not href:
                continue

            link = urljoin("https://de.indeed.com", href)
            company = compact_whitespace(
                (card.select_one("span[data-testid='company-name']") or {}).get_text(" ", strip=True)
                if card.select_one("span[data-testid='company-name']")
                else ""
            )
            location_raw = compact_whitespace(
                (card.select_one("div[data-testid='text-location']") or {}).get_text(" ", strip=True)
                if card.select_one("div[data-testid='text-location']")
                else city
            )
            posted_text = compact_whitespace(
                (card.select_one("span.date") or {}).get_text(" ", strip=True)
                if card.select_one("span.date")
                else ""
            )
            snippet = compact_whitespace(
                (card.select_one("div[data-testid='job-snippet']") or {}).get_text(" ", strip=True)
                if card.select_one("div[data-testid='job-snippet']")
                else ""
            )
            job_id = (
                str(title_link.get("data-jk") or "").strip()
                or extract_query_job_id(link, "jk", fallback_portal=portal)
            )

            jobs.append(
                _normalize_job_record(
                    portal=portal,
                    raw={
                        "job_id": job_id,
                        "title": title,
                        "company": company,
                        "location_raw": location_raw,
                        "posted_text": posted_text,
                        "description": snippet,
                        "snippet": snippet,
                        "link": link,
                        "apply_link": link,
                        "source_keyword": keyword,
                        "source_city": city,
                    },
                )
            )
            seen_on_page += 1

        if seen_on_page == 0 and page > 0:
            break

    return jobs, errors


def _extract_aa_location(item: Dict) -> str:
    location = item.get("arbeitsort") or {}
    if isinstance(location, dict):
        parts = [
            str(location.get("ort") or "").strip(),
            str(location.get("region") or "").strip(),
        ]
        compact = [part for part in parts if part]
        if compact:
            return ", ".join(compact)
    return str(item.get("arbeitsortText") or "").strip()


def _fetch_aa_job_detail(
    session: requests.Session,
    headers: Dict[str, str],
    hash_id: str,
) -> str:
    if not hash_id:
        return ""
    detail_url = f"https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v2/jobdetails/{hash_id}"
    try:
        response = session.get(detail_url, headers=headers, timeout=session.request_timeout)
    except Exception:
        return ""
    if response.status_code != 200:
        return ""
    try:
        payload = response.json()
    except Exception:
        return ""

    candidates = []
    for key in [
        "stellenbeschreibung",
        "aufgaben",
        "anforderungen",
        "beruflicheAnforderungen",
        "arbeitgeberbeschreibung",
    ]:
        value = payload.get(key)
        if isinstance(value, str):
            candidates.append(value)
    return compact_whitespace("\n".join(candidates))


def scrape_arbeitsagentur_jobs(
    keyword: str,
    city: str,
    max_pages: int,
    posted_within_days: int,
    timeout_seconds: int,
    radius_km: int,
    detail_fetch_limit: int = 20,
) -> Tuple[List[Dict], List[str]]:
    portal = "arbeitsagentur"
    errors: List[str] = []
    jobs: List[Dict] = []
    session = _new_session(timeout_seconds=timeout_seconds)
    endpoint = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
    headers = {
        **DEFAULT_HEADERS,
        "Accept": "application/json",
        "X-API-Key": "jobboerse-jobsuche",
    }

    detail_attempts = 0
    for page in range(1, max_pages + 1):
        params = {
            "was": keyword,
            "wo": city,
            "umkreis": max(0, int(radius_km)),
            "page": page,
            "size": 50,
            "angebotsart": 1,
            "sort": "veroeffdatum",
        }
        if posted_within_days > 0:
            params["veroeffentlichtseit"] = min(365, max(1, int(posted_within_days)))

        try:
            response = session.get(endpoint, headers=headers, params=params, timeout=session.request_timeout)
        except Exception as exc:
            errors.append(f"{portal} page={page} error={exc}")
            continue

        if response.status_code != 200:
            errors.append(f"{portal} page={page} status={response.status_code}")
            continue

        try:
            payload = response.json()
        except Exception as exc:
            errors.append(f"{portal} page={page} invalid_json={exc}")
            continue

        offers = payload.get("stellenangebote") or []
        if not isinstance(offers, list) or not offers:
            if page > 1:
                break
            continue

        for item in offers:
            if not isinstance(item, dict):
                continue

            job_hash = (
                str(item.get("hashId") or "").strip()
                or str(item.get("externeReferenznummer") or "").strip()
                or str(item.get("referenznummer") or "").strip()
            )
            title = compact_whitespace(str(item.get("titel") or item.get("beruf") or ""))
            company = compact_whitespace(str(item.get("arbeitgeber") or item.get("betrieb") or ""))
            location_raw = compact_whitespace(_extract_aa_location(item) or city)
            posted_text = compact_whitespace(
                str(item.get("aktuelleVeroeffentlichungsdatum") or item.get("eintrittsdatum") or "")
            )
            snippet = compact_whitespace(
                str(item.get("beruf") or item.get("arbeitszeitmodell") or item.get("eintrittsdatum") or "")
            )
            link = (
                f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{job_hash}"
                if job_hash
                else "https://www.arbeitsagentur.de/jobsuche/"
            )

            description = ""
            if detail_attempts < max(0, int(detail_fetch_limit)):
                description = _fetch_aa_job_detail(session=session, headers=headers, hash_id=job_hash)
                detail_attempts += 1

            jobs.append(
                _normalize_job_record(
                    portal=portal,
                    raw={
                        "job_id": job_hash or build_fallback_job_id(portal, f"{title}|{company}|{location_raw}"),
                        "title": title,
                        "company": company,
                        "location_raw": location_raw,
                        "posted_text": posted_text,
                        "description": description or snippet,
                        "snippet": snippet,
                        "link": link,
                        "apply_link": link,
                        "source_keyword": keyword,
                        "source_city": city,
                    },
                )
            )

    return jobs, errors


def _load_stepstone_next_data(soup: BeautifulSoup) -> Dict:
    script = soup.select_one("script#__NEXT_DATA__")
    if not script:
        return {}
    raw = (script.string or script.get_text() or "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload
    except Exception:
        return {}
    return {}


def _walk_for_stepstone_jobs(node, collector: List[Dict]) -> None:
    if isinstance(node, dict):
        title = node.get("jobTitle") or node.get("title")
        company = node.get("companyName") or node.get("company")
        job_url = node.get("jobUrl") or node.get("url")
        location = node.get("location") or node.get("locationName")
        if title and job_url and isinstance(job_url, str):
            if "/stellenangebote--" in job_url or "/jobs/" in job_url:
                collector.append(
                    {
                        "title": str(title),
                        "company": str(company or ""),
                        "link": str(job_url),
                        "location_raw": str(location or ""),
                        "snippet": str(node.get("teaser") or node.get("jobDescription") or ""),
                    }
                )
        for value in node.values():
            _walk_for_stepstone_jobs(value, collector)
    elif isinstance(node, list):
        for value in node:
            _walk_for_stepstone_jobs(value, collector)


def scrape_stepstone_jobs(
    keyword: str,
    city: str,
    max_pages: int,
    radius_km: int,
    timeout_seconds: int,
) -> Tuple[List[Dict], List[str]]:
    portal = "stepstone"
    errors: List[str] = []
    jobs: List[Dict] = []
    session = _new_session(timeout_seconds=timeout_seconds)

    for page in range(1, max_pages + 1):
        params = {
            "ke": keyword,
            "ws": city,
            "radius": max(0, int(radius_km)),
            "page": page,
            "sort": "2",
        }
        try:
            response = session.get(
                "https://www.stepstone.de/jobs",
                params=params,
                timeout=session.request_timeout,
            )
        except Exception as exc:
            errors.append(f"{portal} page={page} error={exc}")
            continue

        if response.status_code in (403, 429):
            proxy_response = _proxy_get(
                url="https://www.stepstone.de/jobs",
                params=params,
                timeout_seconds=session.request_timeout,
            )
            if proxy_response is not None:
                response = proxy_response

        if response.status_code != 200:
            errors.append(f"{portal} page={page} status={response.status_code}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        page_candidates: List[Dict] = []

        next_data = _load_stepstone_next_data(soup)
        if next_data:
            _walk_for_stepstone_jobs(next_data, page_candidates)

        if not page_candidates:
            for anchor in soup.select("a[href*='/stellenangebote--']"):
                title = compact_whitespace(anchor.get_text(" ", strip=True))
                href = str(anchor.get("href") or "").strip()
                if not title or not href:
                    continue
                card = anchor.find_parent(["article", "li", "div"])
                company = ""
                location_raw = city
                snippet = ""
                if card:
                    company_tag = card.select_one("[data-at='job-item-company-name']") or card.select_one("span")
                    location_tag = card.select_one("[data-at='job-item-location']") or card.select_one("p")
                    snippet_tag = card.select_one("[data-at='job-item-teaser']")
                    if company_tag:
                        company = compact_whitespace(company_tag.get_text(" ", strip=True))
                    if location_tag:
                        location_raw = compact_whitespace(location_tag.get_text(" ", strip=True)) or city
                    if snippet_tag:
                        snippet = compact_whitespace(snippet_tag.get_text(" ", strip=True))
                page_candidates.append(
                    {
                        "title": title,
                        "company": company,
                        "link": href,
                        "location_raw": location_raw,
                        "snippet": snippet,
                    }
                )

        if not page_candidates and page > 1:
            break

        seen_on_page = 0
        for item in page_candidates:
            title = compact_whitespace(str(item.get("title") or ""))
            href = str(item.get("link") or "").strip()
            if not title or not href:
                continue
            link = urljoin("https://www.stepstone.de", href)
            location_raw = compact_whitespace(str(item.get("location_raw") or city))
            company = compact_whitespace(str(item.get("company") or ""))
            snippet = compact_whitespace(str(item.get("snippet") or ""))
            job_id = extract_query_job_id(link, "id")
            if not job_id:
                match = re.search(r"--([0-9]+)\?", link)
                if match:
                    job_id = match.group(1)
            if not job_id:
                job_id = build_fallback_job_id(portal, link)

            jobs.append(
                _normalize_job_record(
                    portal=portal,
                    raw={
                        "job_id": job_id,
                        "title": title,
                        "company": company,
                        "location_raw": location_raw,
                        "posted_text": "",
                        "description": snippet,
                        "snippet": snippet,
                        "link": link,
                        "apply_link": link,
                        "source_keyword": keyword,
                        "source_city": city,
                    },
                )
            )
            seen_on_page += 1

        if seen_on_page == 0 and page > 1:
            break

    return jobs, errors


def scrape_linkedin_jobs(
    keyword: str,
    city: str,
    max_pages: int,
    posted_within_days: int,
    timeout_seconds: int,
) -> Tuple[List[Dict], List[str]]:
    portal = "linkedin"
    errors: List[str] = []
    jobs: List[Dict] = []
    session = _new_session(timeout_seconds=timeout_seconds)
    endpoint = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

    for page in range(max_pages):
        params = {
            "keywords": keyword,
            "location": city,
            "start": page * 25,
        }
        if posted_within_days > 0:
            params["f_TPR"] = f"r{int(posted_within_days) * 86400}"

        try:
            response = session.get(endpoint, params=params, timeout=session.request_timeout)
        except Exception as exc:
            errors.append(f"{portal} page={page + 1} error={exc}")
            continue

        if response.status_code in (403, 429):
            proxy_response = _proxy_get(
                url=endpoint,
                params=params,
                timeout_seconds=session.request_timeout,
            )
            if proxy_response is not None:
                response = proxy_response

        if response.status_code != 200:
            errors.append(f"{portal} page={page + 1} status={response.status_code}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        items = soup.find_all("li")
        if not items and page > 0:
            break

        seen_on_page = 0
        for item in items:
            card = item.find("div", {"class": "base-card"})
            title_tag = item.find("h3", {"class": "base-search-card__title"})
            company_tag = item.find("h4", {"class": "base-search-card__subtitle"})
            location_tag = item.find("span", {"class": "job-search-card__location"})
            if not card or not title_tag:
                continue

            urn = str(card.get("data-entity-urn") or "")
            job_id = urn.split(":")[-1].strip() if ":" in urn else ""
            title = compact_whitespace(title_tag.get_text(" ", strip=True))
            company = compact_whitespace(company_tag.get_text(" ", strip=True) if company_tag else "")
            location_raw = compact_whitespace(location_tag.get_text(" ", strip=True) if location_tag else city)
            link = f"https://www.linkedin.com/jobs/view/{job_id}" if job_id else ""
            snippet = compact_whitespace(item.get_text(" ", strip=True))[:500]

            jobs.append(
                _normalize_job_record(
                    portal=portal,
                    raw={
                        "job_id": job_id or build_fallback_job_id(portal, f"{title}|{company}|{location_raw}"),
                        "title": title,
                        "company": company,
                        "location_raw": location_raw,
                        "posted_text": "",
                        "description": snippet,
                        "snippet": snippet,
                        "link": link,
                        "apply_link": link,
                        "source_keyword": keyword,
                        "source_city": city,
                    },
                )
            )
            seen_on_page += 1

        if seen_on_page == 0 and page > 0:
            break

    return jobs, errors


def _slugify_board_search_segment(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", compact_whitespace(value).lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized or "jobs"


def _select_first_text(node: BeautifulSoup | None, selectors: List[str]) -> str:
    if node is None:
        return ""
    for selector in selectors:
        try:
            match = node.select_one(selector)
        except Exception:
            match = None
        if match:
            text = compact_whitespace(match.get_text(" ", strip=True))
            if text:
                return text
    return ""


def _collect_json_ld_job_postings(node, collector: List[Dict]) -> None:
    if isinstance(node, dict):
        raw_type = node.get("@type")
        type_values = raw_type if isinstance(raw_type, list) else [raw_type]
        if any(str(item or "").strip().lower() == "jobposting" for item in type_values):
            collector.append(node)
        for value in node.values():
            _collect_json_ld_job_postings(value, collector)
    elif isinstance(node, list):
        for item in node:
            _collect_json_ld_job_postings(item, collector)


def _json_ld_company_name(value) -> str:
    if isinstance(value, dict):
        return compact_whitespace(str(value.get("name") or ""))
    if isinstance(value, list):
        for item in value:
            company = _json_ld_company_name(item)
            if company:
                return company
    return compact_whitespace(str(value or ""))


def _json_ld_location_name(value) -> str:
    if isinstance(value, dict):
        address = value.get("address")
        if isinstance(address, dict):
            parts = [
                compact_whitespace(str(address.get("addressLocality") or "")),
                compact_whitespace(str(address.get("addressRegion") or "")),
                compact_whitespace(str(address.get("addressCountry") or "")),
            ]
            filtered = [item for item in parts if item]
            if filtered:
                return ", ".join(filtered)
        parts = [
            compact_whitespace(str(value.get("name") or "")),
            compact_whitespace(str(value.get("addressLocality") or "")),
            compact_whitespace(str(value.get("addressRegion") or "")),
            compact_whitespace(str(value.get("addressCountry") or "")),
        ]
        filtered = [item for item in parts if item]
        if filtered:
            return ", ".join(filtered)
    if isinstance(value, list):
        for item in value:
            location = _json_ld_location_name(item)
            if location:
                return location
    return compact_whitespace(str(value or ""))


def _json_ld_url(value, base_url: str) -> str:
    if isinstance(value, dict):
        for key in ("url", "@id"):
            if str(value.get(key) or "").strip():
                return urljoin(base_url, str(value.get(key) or "").strip())
        return ""
    return urljoin(base_url, str(value or "").strip()) if str(value or "").strip() else ""


def _extract_json_ld_jobs_from_soup(
    *,
    soup: BeautifulSoup,
    portal: str,
    keyword: str,
    city: str,
    base_url: str,
) -> List[Dict]:
    collected: List[Dict] = []
    seen = set()
    for script in soup.select("script[type='application/ld+json']"):
        raw_text = (script.string or script.get_text() or "").strip()
        if not raw_text:
            continue
        try:
            payload = json.loads(raw_text)
        except Exception:
            continue
        postings: List[Dict] = []
        _collect_json_ld_job_postings(payload, postings)
        for posting in postings:
            title = compact_whitespace(str(posting.get("title") or posting.get("name") or ""))
            link = (
                _json_ld_url(posting.get("url"), base_url)
                or _json_ld_url(posting.get("mainEntityOfPage"), base_url)
                or _json_ld_url(posting.get("sameAs"), base_url)
            )
            if not title or not link:
                continue
            dedupe_key = link.casefold()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            identifier = posting.get("identifier")
            job_id = ""
            if isinstance(identifier, dict):
                job_id = compact_whitespace(str(identifier.get("value") or identifier.get("name") or ""))
            elif isinstance(identifier, str):
                job_id = compact_whitespace(identifier)
            if not job_id:
                job_id = extract_query_job_id(link, "id", fallback_portal=portal)
            collected.append(
                _normalize_job_record(
                    portal=portal,
                    raw={
                        "job_id": job_id or build_fallback_job_id(portal, link),
                        "title": title,
                        "company": _json_ld_company_name(posting.get("hiringOrganization")),
                        "location_raw": _json_ld_location_name(posting.get("jobLocation") or posting.get("jobLocationType")) or city,
                        "posted_text": compact_whitespace(str(posting.get("datePosted") or "")),
                        "description": compact_whitespace(str(posting.get("description") or "")),
                        "snippet": compact_whitespace(str(posting.get("description") or ""))[:500],
                        "link": link,
                        "apply_link": link,
                        "source_keyword": keyword,
                        "source_city": city,
                    },
                )
            )
    return collected


def _extract_anchor_jobs_from_soup(
    *,
    soup: BeautifulSoup,
    portal: str,
    keyword: str,
    city: str,
    base_url: str,
    link_hints: List[str],
    title_selectors: List[str] | None = None,
    company_selectors: List[str] | None = None,
    location_selectors: List[str] | None = None,
    snippet_selectors: List[str] | None = None,
) -> List[Dict]:
    jobs: List[Dict] = []
    seen = set()
    title_selectors = title_selectors or []
    company_selectors = company_selectors or []
    location_selectors = location_selectors or []
    snippet_selectors = snippet_selectors or []

    for anchor in soup.select("a[href]"):
        raw_href = compact_whitespace(str(anchor.get("href") or ""))
        if not raw_href or raw_href.startswith("mailto:") or raw_href.startswith("javascript:"):
            continue
        href = urljoin(base_url, raw_href)
        haystack = f"{href} {anchor.get_text(' ', strip=True)}".lower()
        if link_hints and not any(hint in haystack for hint in link_hints):
            continue
        dedupe_key = href.casefold()
        if dedupe_key in seen:
            continue
        container = anchor.find_parent(["article", "li", "div"])
        title = (
            _select_first_text(container, title_selectors)
            or compact_whitespace(anchor.get_text(" ", strip=True))
        )
        if not title or len(title) < 3:
            continue
        company = _select_first_text(container, company_selectors)
        location_raw = _select_first_text(container, location_selectors) or city
        snippet = _select_first_text(container, snippet_selectors)
        job_id = (
            extract_query_job_id(href, "id")
            or extract_query_job_id(href, "jk")
            or build_fallback_job_id(portal, href)
        )
        jobs.append(
            _normalize_job_record(
                portal=portal,
                raw={
                    "job_id": job_id,
                    "title": title,
                    "company": company,
                    "location_raw": location_raw,
                    "posted_text": "",
                    "description": snippet,
                    "snippet": snippet,
                    "link": href,
                    "apply_link": href,
                    "source_keyword": keyword,
                    "source_city": city,
                },
            )
        )
        seen.add(dedupe_key)
    return jobs


def _generic_job_board_fetch(
    *,
    portal: str,
    keyword: str,
    city: str,
    max_pages: int,
    timeout_seconds: int,
    request_builder,
    link_hints: List[str],
    posted_within_days: int = 0,
    title_selectors: List[str] | None = None,
    company_selectors: List[str] | None = None,
    location_selectors: List[str] | None = None,
    snippet_selectors: List[str] | None = None,
) -> Tuple[List[Dict], List[str]]:
    errors: List[str] = []
    jobs: List[Dict] = []
    seen_links = set()
    session = _new_session(timeout_seconds=timeout_seconds)

    for page in range(1, max_pages + 1):
        url, params = request_builder(keyword, city, page, posted_within_days)
        try:
            response = session.get(url, params=params, timeout=session.request_timeout)
        except Exception as exc:
            errors.append(f"{portal} page={page} error={exc}")
            continue

        if response.status_code in (403, 429):
            proxy_response = _proxy_get(url=url, params=params, timeout_seconds=session.request_timeout)
            if proxy_response is not None:
                response = proxy_response

        if response.status_code != 200:
            errors.append(f"{portal} page={page} status={response.status_code}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        page_jobs = _extract_json_ld_jobs_from_soup(
            soup=soup,
            portal=portal,
            keyword=keyword,
            city=city,
            base_url=response.url or url,
        )
        if not page_jobs:
            page_jobs = _extract_anchor_jobs_from_soup(
                soup=soup,
                portal=portal,
                keyword=keyword,
                city=city,
                base_url=response.url or url,
                link_hints=link_hints,
                title_selectors=title_selectors,
                company_selectors=company_selectors,
                location_selectors=location_selectors,
                snippet_selectors=snippet_selectors,
            )

        page_count = 0
        for job in page_jobs:
            link = str(job.get("link") or "").casefold()
            if link and link in seen_links:
                continue
            if link:
                seen_links.add(link)
            jobs.append(job)
            page_count += 1

        if page_count == 0 and page > 1:
            break

    return jobs, errors


def _glassdoor_request(keyword: str, city: str, page: int, posted_within_days: int) -> Tuple[str, Dict]:
    params = {
        "sc.keyword": keyword,
        "locT": "C",
        "locKeyword": city,
    }
    if page > 1:
        params["p"] = page
    if posted_within_days > 0:
        params["fromAge"] = posted_within_days
    return "https://www.glassdoor.com/Job/jobs.htm", params


def _ziprecruiter_request(keyword: str, city: str, page: int, posted_within_days: int) -> Tuple[str, Dict]:
    params = {
        "search": keyword,
        "location": city,
        "page": page,
    }
    if posted_within_days > 0:
        params["days"] = posted_within_days
    return "https://www.ziprecruiter.com/jobs-search", params


def _monster_request(keyword: str, city: str, page: int, posted_within_days: int) -> Tuple[str, Dict]:
    params = {
        "q": keyword,
        "where": city,
        "page": page,
    }
    if posted_within_days > 0:
        params["tm"] = posted_within_days
    return "https://www.monster.com/jobs/search/", params


def _careerbuilder_request(keyword: str, city: str, page: int, posted_within_days: int) -> Tuple[str, Dict]:
    params = {
        "keywords": keyword,
        "location": city,
        "page_number": page,
    }
    if posted_within_days > 0:
        params["posted"] = posted_within_days
    return "https://www.careerbuilder.com/jobs", params


def _careerjet_request(keyword: str, city: str, page: int, posted_within_days: int) -> Tuple[str, Dict]:
    params = {
        "s": keyword,
        "l": city,
        "p": max(0, page - 1),
    }
    if posted_within_days > 0:
        params["nw"] = posted_within_days
    return "https://www.careerjet.com/search/jobs", params


def _reed_request(keyword: str, city: str, page: int, posted_within_days: int) -> Tuple[str, Dict]:
    params = {
        "keywords": keyword,
        "locationName": city,
        "pageno": page,
    }
    if posted_within_days > 0:
        params["datecreatedoffered"] = posted_within_days
    return "https://www.reed.co.uk/jobs", params


def _totaljobs_request(keyword: str, city: str, page: int, posted_within_days: int) -> Tuple[str, Dict]:
    params = {
        "keywords": keyword,
        "location": city,
        "page": page,
    }
    if posted_within_days > 0:
        params["sort"] = "date"
    return "https://www.totaljobs.com/jobs", params


def _jobsdb_request(keyword: str, city: str, page: int, posted_within_days: int) -> Tuple[str, Dict]:
    params = {
        "key": keyword,
        "location": city,
        "page": page,
    }
    if posted_within_days > 0:
        params["daterange"] = posted_within_days
    return "https://hk.jobsdb.com/hk/search-jobs", params


def scrape_glassdoor_jobs(
    keyword: str,
    city: str,
    max_pages: int,
    posted_within_days: int,
    timeout_seconds: int,
) -> Tuple[List[Dict], List[str]]:
    return _generic_job_board_fetch(
        portal="glassdoor",
        keyword=keyword,
        city=city,
        max_pages=max_pages,
        timeout_seconds=timeout_seconds,
        posted_within_days=posted_within_days,
        request_builder=_glassdoor_request,
        link_hints=["/job-listing/", "joblisting"],
        company_selectors=["[data-test='employer-name']", "[data-test='employerName']", ".EmployerProfile_employerName__"],
        location_selectors=["[data-test='emp-location']", ".JobCard_location__"],
        snippet_selectors=["[data-test='job-description-teaser']", ".JobCard_jobDescriptionSnippet__"],
    )


def scrape_ziprecruiter_jobs(
    keyword: str,
    city: str,
    max_pages: int,
    posted_within_days: int,
    timeout_seconds: int,
) -> Tuple[List[Dict], List[str]]:
    return _generic_job_board_fetch(
        portal="ziprecruiter",
        keyword=keyword,
        city=city,
        max_pages=max_pages,
        timeout_seconds=timeout_seconds,
        posted_within_days=posted_within_days,
        request_builder=_ziprecruiter_request,
        link_hints=["/jobs/", "ziprecruiter.com/jobs/"],
        company_selectors=["[data-testid='job-card-company']", ".hiring_company_text", ".job_content .hiring_company_name"],
        location_selectors=["[data-testid='job-card-location']", ".location", ".job_content .location"],
        snippet_selectors=["[data-testid='job-card-snippet']", ".job_snippet"],
    )


def scrape_monster_jobs(
    keyword: str,
    city: str,
    max_pages: int,
    posted_within_days: int,
    timeout_seconds: int,
) -> Tuple[List[Dict], List[str]]:
    return _generic_job_board_fetch(
        portal="monster",
        keyword=keyword,
        city=city,
        max_pages=max_pages,
        timeout_seconds=timeout_seconds,
        posted_within_days=posted_within_days,
        request_builder=_monster_request,
        link_hints=["/job-openings/", "/job/"],
        company_selectors=["[data-testid='company-name']", ".company", ".companyName"],
        location_selectors=["[data-testid='jobDetailLocation']", ".location", ".details__at"],
        snippet_selectors=["[data-testid='jobCardDescription']", ".summary", ".mux-job-card__summary"],
    )


def scrape_careerbuilder_jobs(
    keyword: str,
    city: str,
    max_pages: int,
    posted_within_days: int,
    timeout_seconds: int,
) -> Tuple[List[Dict], List[str]]:
    return _generic_job_board_fetch(
        portal="careerbuilder",
        keyword=keyword,
        city=city,
        max_pages=max_pages,
        timeout_seconds=timeout_seconds,
        posted_within_days=posted_within_days,
        request_builder=_careerbuilder_request,
        link_hints=["/job/", "/jobs/detail/"],
        company_selectors=["[data-testid='company-name']", ".data-results-company", ".company-name"],
        location_selectors=["[data-testid='job-location']", ".data-results-location", ".job-location"],
        snippet_selectors=["[data-testid='job-description']", ".data-results-content", ".job-snippet"],
    )


def scrape_careerjet_jobs(
    keyword: str,
    city: str,
    max_pages: int,
    posted_within_days: int,
    timeout_seconds: int,
) -> Tuple[List[Dict], List[str]]:
    return _generic_job_board_fetch(
        portal="careerjet",
        keyword=keyword,
        city=city,
        max_pages=max_pages,
        timeout_seconds=timeout_seconds,
        posted_within_days=posted_within_days,
        request_builder=_careerjet_request,
        link_hints=["/jobad/", "/job/"],
        company_selectors=[".company", "[data-company]"],
        location_selectors=[".locations", ".location"],
        snippet_selectors=[".desc", ".snippet"],
    )


def scrape_reed_jobs(
    keyword: str,
    city: str,
    max_pages: int,
    posted_within_days: int,
    timeout_seconds: int,
) -> Tuple[List[Dict], List[str]]:
    return _generic_job_board_fetch(
        portal="reed",
        keyword=keyword,
        city=city,
        max_pages=max_pages,
        timeout_seconds=timeout_seconds,
        posted_within_days=posted_within_days,
        request_builder=_reed_request,
        link_hints=["/jobs/"],
        company_selectors=["[data-qa='company-name']", ".gtmJobListingPostedBy", ".job-result-company"],
        location_selectors=["[data-qa='job-metadata-location']", ".job-result-location"],
        snippet_selectors=["[data-qa='job-description']", ".job-result-description"],
    )


def scrape_totaljobs_jobs(
    keyword: str,
    city: str,
    max_pages: int,
    posted_within_days: int,
    timeout_seconds: int,
) -> Tuple[List[Dict], List[str]]:
    return _generic_job_board_fetch(
        portal="totaljobs",
        keyword=keyword,
        city=city,
        max_pages=max_pages,
        timeout_seconds=timeout_seconds,
        posted_within_days=posted_within_days,
        request_builder=_totaljobs_request,
        link_hints=["/job/"],
        company_selectors=["[data-at='job-item-company-name']", ".job-item-company-name", ".company"],
        location_selectors=["[data-at='job-item-location']", ".job-item-location", ".location"],
        snippet_selectors=["[data-at='job-item-teaser']", ".job-item-teaser", ".description"],
    )


def scrape_jobsdb_jobs(
    keyword: str,
    city: str,
    max_pages: int,
    posted_within_days: int,
    timeout_seconds: int,
) -> Tuple[List[Dict], List[str]]:
    return _generic_job_board_fetch(
        portal="jobsdb",
        keyword=keyword,
        city=city,
        max_pages=max_pages,
        timeout_seconds=timeout_seconds,
        posted_within_days=posted_within_days,
        request_builder=_jobsdb_request,
        link_hints=["/job/"],
        company_selectors=["[data-automation='job-company-name']", ".job-card-company-name", ".company"],
        location_selectors=["[data-automation='job-detail-location']", ".job-card-location", ".location"],
        snippet_selectors=["[data-automation='jobShortDescription']", ".job-card-teaser", ".description"],
    )


__all__ = [
    "build_fallback_job_id",
    "compact_whitespace",
    "extract_query_job_id",
    "normalize_city_from_location",
    "now_utc_iso",
    "repair_mojibake",
    "scrape_careerbuilder_jobs",
    "scrape_careerjet_jobs",
    "scrape_arbeitsagentur_jobs",
    "scrape_glassdoor_jobs",
    "scrape_indeed_jobs",
    "scrape_jobsdb_jobs",
    "scrape_linkedin_jobs",
    "scrape_monster_jobs",
    "scrape_reed_jobs",
    "scrape_stepstone_jobs",
    "scrape_totaljobs_jobs",
    "scrape_ziprecruiter_jobs",
]
