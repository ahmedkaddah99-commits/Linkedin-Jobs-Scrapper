import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Tuple
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
}

load_dotenv()
SCRAPEOPS_API_KEY = (os.getenv("SCRAPEOPS_API_KEY") or "").strip()


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


def _proxy_get(url: str, params: Dict, timeout_seconds: int) -> requests.Response | None:
    if not SCRAPEOPS_API_KEY:
        return None
    try:
        prepared_url = requests.Request("GET", url, params=params).prepare().url
        proxy_params = {
            "api_key": SCRAPEOPS_API_KEY,
            "url": prepared_url,
            "residential": "true",
            "country": "de",
        }
        session = requests.Session()
        session.trust_env = False
        response = session.get(
            "https://proxy.scrapeops.io/v1/",
            params=proxy_params,
            headers=DEFAULT_HEADERS,
            timeout=max(5, int(timeout_seconds)),
        )
        return response
    except Exception:
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


__all__ = [
    "build_fallback_job_id",
    "compact_whitespace",
    "extract_query_job_id",
    "normalize_city_from_location",
    "now_utc_iso",
    "repair_mojibake",
    "scrape_arbeitsagentur_jobs",
    "scrape_indeed_jobs",
    "scrape_linkedin_jobs",
    "scrape_stepstone_jobs",
]
