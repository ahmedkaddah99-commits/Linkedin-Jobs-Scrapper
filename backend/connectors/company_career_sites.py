from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from backend.capabilities.tailored_documents.manual_urls import (
    DEFAULT_HEADERS,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    fetch_and_normalize_manual_job,
    is_valid_job_url,
)
from backend.domain.job_identity import canonicalize_url, compact_whitespace, dedupe_job_records


JOB_LINK_HINTS = (
    "job",
    "jobs",
    "career",
    "careers",
    "vacanc",
    "opening",
    "position",
    "role",
    "opportunit",
    "work-with-us",
)
IGNORED_LINK_HINTS = (
    "mailto:",
    "javascript:",
    "/privacy",
    "/terms",
    "/cookie",
    "/cookies",
    "/contact",
    "/about",
    "/news",
    "/blog",
    "/press",
    "/login",
    "/signin",
    "/sign-in",
)


def _same_host_family(candidate_url: str, base_url: str) -> bool:
    candidate_host = (urlparse(candidate_url).netloc or "").lower().split(":")[0]
    base_host = (urlparse(base_url).netloc or "").lower().split(":")[0]
    if not candidate_host or not base_host:
        return False
    return candidate_host == base_host or candidate_host.endswith(f".{base_host}") or base_host.endswith(f".{candidate_host}")


def _normalize_keywords(raw_keywords: Any) -> list[str]:
    if isinstance(raw_keywords, str):
        values = [item.strip() for item in raw_keywords.split(",") if item.strip()]
    elif isinstance(raw_keywords, (list, tuple, set)):
        values = [str(item).strip() for item in raw_keywords if str(item).strip()]
    else:
        return []
    deduped: list[str] = []
    seen = set()
    for value in values:
        lowered = value.lower()
        if lowered in seen:
            continue
        deduped.append(lowered)
        seen.add(lowered)
    return deduped


def _job_like_link_score(text: str, href: str) -> int:
    haystack = f"{text} {href}".lower()
    score = 0
    for token in JOB_LINK_HINTS:
        if token in haystack:
            score += 1
    return score


def parse_company_site_entries(raw_value: Any) -> list[dict[str, str]]:
    if isinstance(raw_value, str):
        raw_entries = [line.strip() for line in raw_value.splitlines() if line.strip()]
    elif isinstance(raw_value, (list, tuple, set)):
        raw_entries = list(raw_value)
    else:
        return []

    parsed_entries: list[dict[str, str]] = []
    seen_urls = set()
    for entry in raw_entries:
        company_name = ""
        url = ""
        if isinstance(entry, dict):
            company_name = compact_whitespace(str(entry.get("company_name") or entry.get("company") or ""))
            url = compact_whitespace(str(entry.get("url") or entry.get("career_site_url") or ""))
        else:
            text = compact_whitespace(str(entry))
            if not text:
                continue
            if "|" in text:
                left, right = [compact_whitespace(part) for part in text.split("|", 1)]
                if is_valid_job_url(right):
                    company_name, url = left, right
                elif is_valid_job_url(left):
                    company_name, url = right, left
                else:
                    company_name, url = left, right
            else:
                url = text
        if not is_valid_job_url(url):
            continue
        normalized_url = canonicalize_url(url) or url
        if normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        parsed_entries.append(
            {
                "company_name": company_name,
                "url": normalized_url,
            }
        )
    return parsed_entries


def extract_company_job_links_from_html(
    *,
    site_url: str,
    html: str,
    max_links: int = 20,
) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[int, dict[str, str]]] = []
    seen = set()

    for anchor in soup.select("a[href]"):
        raw_href = compact_whitespace(str(anchor.get("href") or ""))
        if not raw_href:
            continue
        lower_href = raw_href.lower()
        if any(token in lower_href for token in IGNORED_LINK_HINTS):
            continue
        href = urljoin(site_url, raw_href)
        if not is_valid_job_url(href):
            continue
        normalized_href = canonicalize_url(href) or href
        if normalized_href == (canonicalize_url(site_url) or site_url):
            continue
        if not _same_host_family(normalized_href, site_url):
            continue
        if normalized_href in seen:
            continue

        text = compact_whitespace(anchor.get_text(" ", strip=True))
        score = _job_like_link_score(text, normalized_href)
        if score <= 0:
            continue

        seen.add(normalized_href)
        candidates.append(
            (
                score,
                {
                    "url": normalized_href,
                    "label": text or normalized_href,
                },
            )
        )

    candidates.sort(key=lambda item: (-item[0], item[1]["label"].lower()))
    return [payload for _, payload in candidates[: max(1, int(max_links))]]


def scrape_company_career_sites(
    *,
    company_sites: Any,
    keywords: Any = None,
    request_timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    max_jobs_per_site: int = 10,
    logger=None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    parsed_sites = parse_company_site_entries(company_sites)
    normalized_keywords = _normalize_keywords(keywords)
    collected_jobs: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for site in parsed_sites:
        company_name = site.get("company_name") or ""
        site_url = site.get("url") or ""
        try:
            response = requests.get(
                site_url,
                headers=DEFAULT_HEADERS,
                timeout=max(5, int(request_timeout_seconds)),
            )
            response.raise_for_status()
        except Exception as exc:
            failures.append(
                {
                    "company_name": company_name,
                    "url": site_url,
                    "error": str(exc),
                    "stage": "fetch_company_site",
                }
            )
            continue

        candidate_links = extract_company_job_links_from_html(
            site_url=site_url,
            html=response.text,
            max_links=max_jobs_per_site,
        )

        if not candidate_links:
            failures.append(
                {
                    "company_name": company_name,
                    "url": site_url,
                    "error": "No job links discovered on career site.",
                    "stage": "discover_company_jobs",
                }
            )
            continue

        for candidate in candidate_links:
            candidate_url = candidate["url"]
            candidate_label = candidate["label"]
            try:
                job = fetch_and_normalize_manual_job(
                    candidate_url,
                    request_timeout_seconds=request_timeout_seconds,
                )
            except Exception as exc:
                failures.append(
                    {
                        "company_name": company_name,
                        "url": candidate_url,
                        "error": str(exc),
                        "stage": "normalize_company_job",
                    }
                )
                continue

            searchable = " ".join(
                [
                    compact_whitespace(str(job.get("title") or "")),
                    compact_whitespace(str(job.get("company") or "")),
                    compact_whitespace(str(job.get("full_description") or ""))[:1200],
                    candidate_label,
                ]
            ).lower()
            if normalized_keywords and not any(keyword in searchable for keyword in normalized_keywords):
                continue

            if not compact_whitespace(str(job.get("title") or "")):
                job["title"] = candidate_label
            if company_name and not compact_whitespace(str(job.get("company") or "")):
                job["company"] = company_name
            job["source_type"] = "company_career_site"
            job["portal"] = "company_career_site"
            job["manual_approved"] = False
            job["career_site_url"] = site_url
            job["career_site_company_name"] = company_name
            collected_jobs.append(job)

    deduped_jobs, dropped_duplicates = dedupe_job_records(collected_jobs, logger=logger)
    for dropped in dropped_duplicates:
        failures.append(
            {
                "company_name": str(dropped.get("company") or dropped.get("career_site_company_name") or ""),
                "url": str(dropped.get("apply_link") or dropped.get("source_url") or dropped.get("link") or ""),
                "error": str(dropped.get("dedupe_reason") or "duplicate_job"),
                "stage": "dedupe_company_jobs",
            }
        )
    return deduped_jobs, failures


__all__ = [
    "extract_company_job_links_from_html",
    "parse_company_site_entries",
    "scrape_company_career_sites",
]
