from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from backend.domain.job_identity import canonicalize_url, compact_whitespace, dedupe_job_records
from backend.domain.pipeline_jobs import (
    FILTER_STATUS_BYPASSED_MANUAL_APPROVAL,
    SOURCE_TYPE_MANUAL_URL,
    PipelineJob,
    stable_manual_job_id,
)

from .linkedin_connector import build_scrape_requests_client, enrich_job


LOGGER = logging.getLogger(__name__)
DEFAULT_REQUEST_TIMEOUT_SECONDS = 45
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
LINKEDIN_JOB_ID_PATTERN = re.compile(r"/jobs/view/(?:[^/]+/)?(?P<job_id>\d+)")


def is_valid_job_url(raw_url: str) -> bool:
    value = compact_whitespace(raw_url)
    if not value:
        return False

    try:
        parsed = urlparse(value)
    except Exception:
        return False

    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc.strip())


def extract_linkedin_job_id(url: str) -> str | None:
    match = LINKEDIN_JOB_ID_PATTERN.search(url or "")
    if match:
        return match.group("job_id")

    parsed = urlparse(url or "")
    if "linkedin.com" not in (parsed.netloc or "").lower():
        return None

    path_match = re.search(r"/jobs/view/(?P<job_id>\d+)", parsed.path or "")
    if path_match:
        return path_match.group("job_id")
    return None


def load_manual_urls(file_path: str | Path) -> tuple[list[str], list[dict[str, Any]]]:
    path = Path(file_path).expanduser()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Manual URL file not found: {path}")

    return normalize_manual_urls(path.read_text(encoding="utf-8").splitlines())


def normalize_manual_urls(raw_entries: Any) -> tuple[list[str], list[dict[str, Any]]]:
    if isinstance(raw_entries, str):
        iterable = raw_entries.splitlines()
    elif isinstance(raw_entries, (list, tuple, set)):
        iterable = list(raw_entries)
    else:
        iterable = []

    valid_urls: list[str] = []
    invalid_entries: list[dict[str, Any]] = []
    seen = set()

    for line_number, raw_line in enumerate(iterable, start=1):
        stripped_line = str(raw_line or "").strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue
        if not is_valid_job_url(stripped_line):
            invalid_entries.append(
                {
                    "line_number": line_number,
                    "url": stripped_line,
                    "error": "invalid_url_format",
                }
            )
            continue

        canonical_url = canonicalize_url(stripped_line) or stripped_line
        if canonical_url in seen:
            LOGGER.info("Skipping duplicate manual URL on line %s: %s", line_number, stripped_line)
            continue

        seen.add(canonical_url)
        valid_urls.append(stripped_line)

    return valid_urls, invalid_entries


def extract_jobposting_jsonld(soup: BeautifulSoup) -> dict[str, Any]:
    def walk(node: Any) -> dict[str, Any] | None:
        if isinstance(node, list):
            for item in node:
                found = walk(item)
                if found:
                    return found
            return None
        if not isinstance(node, dict):
            return None

        node_type = node.get("@type")
        if node_type == "JobPosting" or (isinstance(node_type, list) and "JobPosting" in node_type):
            return node

        for value in node.values():
            found = walk(value)
            if found:
                return found
        return None

    for script in soup.select("script[type='application/ld+json']"):
        raw_text = compact_whitespace(script.get_text(" ", strip=True))
        if not raw_text:
            continue
        try:
            payload = json.loads(raw_text)
        except Exception:
            continue
        found = walk(payload)
        if found:
            return found

    return {}


def extract_canonical_url(soup: BeautifulSoup, fallback_url: str) -> str:
    canonical_tag = soup.select_one("link[rel='canonical']")
    canonical_href = canonical_tag.get("href") if canonical_tag else ""
    return canonicalize_url(canonical_href) or canonicalize_url(fallback_url) or fallback_url


def extract_text_from_selectors(soup: BeautifulSoup, selectors: list[str]) -> str:
    for selector in selectors:
        node = soup.select_one(selector)
        if not node:
            continue
        text = compact_whitespace(
            node.get("content") or node.get("value") or node.get_text(" ", strip=True)
        )
        if text:
            return text
    return ""


def html_to_text(raw_html: str) -> str:
    if not raw_html:
        return ""
    return compact_whitespace(BeautifulSoup(raw_html, "html.parser").get_text("\n", strip=True))


def extract_generic_description(soup: BeautifulSoup, jsonld_payload: dict[str, Any]) -> str:
    jsonld_description = html_to_text(str(jsonld_payload.get("description") or ""))
    if jsonld_description:
        return jsonld_description

    selectors = [
        "section[class*='description']",
        "div[class*='description']",
        "section[id*='description']",
        "div[id*='description']",
        "main",
        "body",
    ]
    for selector in selectors:
        node = soup.select_one(selector)
        if not node:
            continue
        text = compact_whitespace(node.get_text("\n", strip=True))
        if len(text) >= 80:
            return text
    return ""


def extract_generic_company(soup: BeautifulSoup, jsonld_payload: dict[str, Any], fallback_title: str) -> str:
    hiring_org = jsonld_payload.get("hiringOrganization")
    if isinstance(hiring_org, dict):
        name = compact_whitespace(str(hiring_org.get("name") or ""))
        if name:
            return name

    site_name = soup.select_one("meta[property='og:site_name']")
    if site_name and compact_whitespace(site_name.get("content", "")):
        return compact_whitespace(site_name.get("content", ""))

    title = compact_whitespace(fallback_title)
    title_match = re.search(r"\s+(?:at|@|\|)\s+(.+)$", title, flags=re.IGNORECASE)
    if title_match:
        return compact_whitespace(title_match.group(1))

    return ""


def extract_generic_location(jsonld_payload: dict[str, Any]) -> str:
    locations = jsonld_payload.get("jobLocation")
    if not locations:
        return ""

    if not isinstance(locations, list):
        locations = [locations]

    location_values: list[str] = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        address = location.get("address")
        if isinstance(address, dict):
            for key in ("addressLocality", "addressRegion", "addressCountry"):
                value = compact_whitespace(str(address.get(key) or ""))
                if value and value not in location_values:
                    location_values.append(value)
        else:
            address_text = compact_whitespace(str(address or ""))
            if address_text and address_text not in location_values:
                location_values.append(address_text)

    return ", ".join(location_values)


def fetch_generic_manual_job(
    url: str,
    *,
    request_timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    response = requests.get(url, headers=DEFAULT_HEADERS, timeout=request_timeout_seconds)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    jsonld_payload = extract_jobposting_jsonld(soup)
    canonical_url = extract_canonical_url(soup, url)

    title = (
        compact_whitespace(str(jsonld_payload.get("title") or ""))
        or extract_text_from_selectors(soup, ["meta[property='og:title']", "h1", "title"])
    )
    if title and "<" in title:
        title = html_to_text(title)

    if not title:
        og_title = soup.select_one("meta[property='og:title']")
        title = compact_whitespace(og_title.get("content", "")) if og_title else ""

    company = extract_generic_company(soup, jsonld_payload, title)
    location_raw = extract_generic_location(jsonld_payload)
    description = extract_generic_description(soup, jsonld_payload)

    job_record = PipelineJob(
        job_id=stable_manual_job_id(canonical_url),
        title=title or "Manual job",
        company=company,
        location_raw=location_raw,
        source_type=SOURCE_TYPE_MANUAL_URL,
        filter_status=FILTER_STATUS_BYPASSED_MANUAL_APPROVAL,
        source_url=canonical_url,
        link=canonical_url,
        linkedin_link=canonical_url if "linkedin.com" in canonical_url.lower() else "",
        apply_link=canonical_url,
        apply_link_source="manual_url",
        full_description=description,
        easy_apply_status="unknown",
        enrich_error=None if description else "Description container not found",
        enrich_status_code=response.status_code,
        manual_approved=True,
    )
    return job_record.to_record()


def fetch_manual_linkedin_job(
    url: str,
    *,
    so_requests,
    scrapeops_api_key: str,
    debug_enrich_blocks: bool,
    use_proxy_fallback: bool,
    request_timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    job_id = extract_linkedin_job_id(url)
    if not job_id:
        raise ValueError(f"Could not extract LinkedIn job ID from URL: {url}")

    enrich_payload = enrich_job(
        job_id=job_id,
        so_requests=so_requests,
        scrapeops_api_key=scrapeops_api_key,
        debug_enrich_blocks=debug_enrich_blocks,
        use_proxy_fallback=use_proxy_fallback,
    )

    fallback_payload: dict[str, Any] = {}
    if not enrich_payload.get("title") or not enrich_payload.get("company") or not enrich_payload.get("description"):
        try:
            fallback_payload = fetch_generic_manual_job(
                url,
                request_timeout_seconds=request_timeout_seconds,
            )
        except Exception:
            fallback_payload = {}

    canonical_source_url = canonicalize_url(url) or url
    linkedin_url = f"https://www.linkedin.com/jobs/view/{job_id}"
    job_record = PipelineJob(
        job_id=str(job_id),
        title=compact_whitespace(str(enrich_payload.get("title") or fallback_payload.get("title") or "")) or f"LinkedIn job {job_id}",
        company=compact_whitespace(str(enrich_payload.get("company") or fallback_payload.get("company") or "")),
        location_raw=compact_whitespace(
            str(enrich_payload.get("location_raw") or fallback_payload.get("location_raw") or "")
        ),
        source_type=SOURCE_TYPE_MANUAL_URL,
        filter_status=FILTER_STATUS_BYPASSED_MANUAL_APPROVAL,
        source_url=canonical_source_url,
        link=linkedin_url,
        linkedin_link=linkedin_url,
        apply_link=str(enrich_payload.get("apply_link") or fallback_payload.get("apply_link") or linkedin_url),
        apply_link_source=str(enrich_payload.get("apply_link_source") or "manual_url"),
        full_description=str(enrich_payload.get("description") or fallback_payload.get("full_description") or ""),
        easy_apply_status=enrich_payload.get("easy_apply_status", "unknown"),
        posted_time_text=str(enrich_payload.get("posted_time_text") or ""),
        posted_age_hours=enrich_payload.get("posted_age_hours"),
        posted_datetime_estimated_utc=enrich_payload.get("posted_datetime_estimated_utc"),
        applicant_count=enrich_payload.get("applicant_count"),
        enrich_error=enrich_payload.get("enrich_error"),
        enrich_status_code=enrich_payload.get("status_code"),
        manual_approved=True,
    )
    return job_record.to_record()


def fetch_and_normalize_manual_job(
    url: str,
    *,
    so_requests=None,
    scrapeops_api_key: str = "",
    debug_enrich_blocks: bool = False,
    use_proxy_fallback: bool = False,
    request_timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if extract_linkedin_job_id(url):
        if so_requests is None or not scrapeops_api_key:
            scrapeops_api_key, so_requests = build_scrape_requests_client()
        return fetch_manual_linkedin_job(
            url,
            so_requests=so_requests,
            scrapeops_api_key=scrapeops_api_key,
            debug_enrich_blocks=debug_enrich_blocks,
            use_proxy_fallback=use_proxy_fallback,
            request_timeout_seconds=request_timeout_seconds,
        )

    return fetch_generic_manual_job(url, request_timeout_seconds=request_timeout_seconds)


def fetch_manual_jobs_from_file(
    file_path: str | Path,
    *,
    debug_enrich_blocks: bool = False,
    use_proxy_fallback: bool = False,
    request_timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    logger: logging.Logger | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    active_logger = logger or LOGGER
    urls, invalid_entries = load_manual_urls(file_path)
    return fetch_manual_jobs_from_urls(
        urls,
        invalid_entries=invalid_entries,
        debug_enrich_blocks=debug_enrich_blocks,
        use_proxy_fallback=use_proxy_fallback,
        request_timeout_seconds=request_timeout_seconds,
        logger=active_logger,
    )


def fetch_manual_jobs_from_urls(
    urls: list[str],
    *,
    invalid_entries: list[dict[str, Any]] | None = None,
    debug_enrich_blocks: bool = False,
    use_proxy_fallback: bool = False,
    request_timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    logger: logging.Logger | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    active_logger = logger or LOGGER
    failures: list[dict[str, Any]] = list(invalid_entries or [])
    jobs: list[dict[str, Any]] = []

    scrapeops_api_key = ""
    so_requests = None
    if any(extract_linkedin_job_id(url) for url in urls):
        scrapeops_api_key, so_requests = build_scrape_requests_client()

    for index, url in enumerate(urls, start=1):
        active_logger.info("Fetching manual job %s/%s: %s", index, len(urls), url)
        try:
            job = fetch_and_normalize_manual_job(
                url,
                so_requests=so_requests,
                scrapeops_api_key=scrapeops_api_key,
                debug_enrich_blocks=debug_enrich_blocks,
                use_proxy_fallback=use_proxy_fallback,
                request_timeout_seconds=request_timeout_seconds,
            )
            jobs.append(job)
        except Exception as exc:
            active_logger.exception("Manual URL ingestion failed for %s", url)
            failures.append(
                {
                    "url": url,
                    "error": str(exc),
                    "stage": "fetch_parse_normalize",
                }
            )

    deduped_jobs, dropped_duplicates = dedupe_job_records(jobs, logger=active_logger)
    for dropped_record in dropped_duplicates:
        failures.append(
            {
                "url": dropped_record.get("source_url") or dropped_record.get("apply_link") or dropped_record.get("link"),
                "error": dropped_record.get("dedupe_reason"),
                "stage": "dedupe",
            }
        )

    return deduped_jobs, failures


__all__ = [
    "DEFAULT_HEADERS",
    "DEFAULT_REQUEST_TIMEOUT_SECONDS",
    "LINKEDIN_JOB_ID_PATTERN",
    "extract_canonical_url",
    "extract_generic_company",
    "extract_generic_description",
    "extract_generic_location",
    "extract_jobposting_jsonld",
    "extract_linkedin_job_id",
    "extract_text_from_selectors",
    "fetch_and_normalize_manual_job",
    "fetch_generic_manual_job",
    "fetch_manual_jobs_from_file",
    "fetch_manual_jobs_from_urls",
    "fetch_manual_linkedin_job",
    "html_to_text",
    "is_valid_job_url",
    "load_manual_urls",
    "normalize_manual_urls",
]
