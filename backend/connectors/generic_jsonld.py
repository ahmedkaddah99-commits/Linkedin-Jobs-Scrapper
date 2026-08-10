"""Bounded direct acquisition for generic employer job pages.

The adapter is deliberately conservative: it follows one listing page, reads
at most ``max_job_links`` same-source detail pages, retains the HTML evidence,
and never declares a partial listing safe for source closure.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup


DEFAULT_TIMEOUT_SECONDS = 25
DEFAULT_MAX_JOB_LINKS = 6


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _url(value: object, base_url: str = "") -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    candidate = urljoin(base_url, raw)
    parts = urlsplit(candidate)
    if parts.scheme.casefold() != "https" or not parts.hostname:
        return ""
    return candidate.split("#", 1)[0].rstrip("/")


def _host(value: str) -> str:
    return (urlsplit(value).hostname or "").casefold()


def _allowed_host(host: str, allowed_hosts: Iterable[str]) -> bool:
    normalized = host.casefold().strip().lstrip(".")
    return any(normalized == item or normalized.endswith("." + item) for item in allowed_hosts if item)


def _json_ld_values(soup: BeautifulSoup) -> list[Mapping[str, object]]:
    result: list[Mapping[str, object]] = []
    for script in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        try:
            payload = json.loads(script.get_text("", strip=True))
        except (TypeError, ValueError):
            continue
        candidates = payload if isinstance(payload, list) else [payload]
        if isinstance(payload, Mapping) and isinstance(payload.get("@graph"), list):
            candidates.extend(payload["@graph"])
        for item in candidates:
            if not isinstance(item, Mapping):
                continue
            types = item.get("@type")
            values = types if isinstance(types, list) else [types]
            if any(str(value or "").casefold() == "jobposting" for value in values):
                result.append(item)
    return result


def _json_location(value: object) -> str:
    if isinstance(value, Mapping):
        address = value.get("address")
        if isinstance(address, Mapping):
            return ", ".join(
                _text(address.get(key))
                for key in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry")
                if _text(address.get(key))
            )
        return _text(value.get("name") or value.get("value"))
    return _text(value)


def _job_from_json_ld(item: Mapping[str, object], *, page_url: str, raw_html: str) -> dict[str, object]:
    identifier = item.get("identifier")
    if isinstance(identifier, Mapping):
        identifier = identifier.get("value") or identifier.get("name")
    detail_url = _url(item.get("url"), page_url) or page_url
    location = item.get("jobLocation")
    if isinstance(location, list):
        location = "; ".join(_json_location(value) for value in location if _json_location(value))
    else:
        location = _json_location(location)
    organization = item.get("hiringOrganization")
    company = organization.get("name") if isinstance(organization, Mapping) else ""
    description = str(item.get("description") or "")
    return {
        "job_id": _text(identifier) or detail_url,
        "external_job_id": _text(identifier) or detail_url,
        "title": _text(item.get("title")),
        "url": detail_url,
        "link": detail_url,
        "source_url": detail_url,
        "job_detail_url": detail_url,
        "apply_link": detail_url if item.get("directApply") else "",
        "full_description": description,
        "description": description,
        "location": location,
        "location_raw": location,
        "employment_type": _text(item.get("employmentType")),
        "workplace_arrangement": _text(item.get("jobLocationType") or item.get("workplaceArrangement")),
        "source_posted_at": _text(item.get("datePosted")),
        "source_updated_at": _text(item.get("dateModified")),
        "source_raw_payload": {"format": "json-ld", "job_posting": deepcopy(dict(item)), "html": raw_html},
        "source_ats": "generic_jsonld",
        "company": _text(company),
    }


def _labelled_fields(soup: BeautifulSoup) -> dict[str, str]:
    fields: dict[str, str] = {}
    for node in soup.select(".article__content__view__field"):
        label = _text(node.select_one(".article__content__view__field__label").get_text(" ", strip=True) if node.select_one(".article__content__view__field__label") else "")
        value = node.select_one(".article__content__view__field__value")
        value_text = _text(value.get_text(" ", strip=True) if value else node.get_text(" ", strip=True))
        if label and value_text:
            fields[label.casefold()] = value_text
    return fields


def _job_from_html(*, page_url: str, html: str) -> dict[str, object]:
    soup = BeautifulSoup(html, "html.parser")
    json_jobs = _json_ld_values(soup)
    if json_jobs:
        return _job_from_json_ld(json_jobs[0], page_url=page_url, raw_html=html)
    fields = _labelled_fields(soup)
    title_node = soup.select_one(".article__header__text, h1")
    title = _text(title_node.get_text(" ", strip=True) if title_node else "")
    if not title:
        meta_title = soup.find("meta", attrs={"property": "og:title"}) or soup.find("meta", attrs={"name": re.compile(r"^title$", re.I)})
        title = _text(meta_title.get("content") if meta_title else "")
    def field(*labels: str) -> str:
        for label in labels:
            if fields.get(label):
                return fields[label]
        return ""
    apply_link = ""
    for anchor in soup.find_all("a", href=True):
        label = _text(anchor.get_text(" ", strip=True)).casefold()
        if "apply" in label or "bewerben" in label:
            apply_link = _url(anchor.get("href"), page_url)
            if apply_link:
                break
    main = soup.select_one("main, article, .article__content__view") or soup
    description = _text(main.get_text("\n", strip=True))
    job_id = field("job id", "reference", "requisition id")
    location = field("location(s)", "location", "locations")
    return {
        "job_id": job_id or page_url,
        "external_job_id": job_id or page_url,
        "title": title,
        "url": page_url,
        "link": page_url,
        "source_url": page_url,
        "job_detail_url": page_url,
        "apply_link": apply_link,
        "apply_url": apply_link,
        "full_description": description,
        "description": description,
        "location": location,
        "location_raw": location,
        "department": field("field of work", "organization", "department", "team"),
        "employment_type": field("employment type", "job type", "contract type"),
        "workplace_arrangement": field("work mode", "workplace arrangement", "remote type"),
        "experience_level": field("experience level", "experience"),
        "source_posted_at": field("posted since", "date posted", "published"),
        "source_raw_payload": {"format": "html", "detail_url": page_url, "html": html, "labelled_fields": fields},
        "source_ats": "generic_jsonld",
    }


def _request(requester: Callable[..., object], url: str, timeout_seconds: int) -> object:
    try:
        return requester(url, timeout=timeout_seconds, allow_redirects=True)
    except TypeError:
        return requester(url, timeout=timeout_seconds)


def fetch_generic_snapshot(
    target_url: str,
    *,
    requester: Callable[..., object] | None = None,
    max_job_links: int = DEFAULT_MAX_JOB_LINKS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    allowed_hosts: Iterable[str] = (),
) -> dict[str, object]:
    request = requester or requests.get
    bounded_links = max(1, min(25, int(max_job_links)))
    target_host = _host(target_url)
    hosts = {target_host, *(str(value).casefold().strip() for value in allowed_hosts if str(value).strip())}
    logs: list[dict[str, object]] = []
    try:
        listing_response = _request(request, target_url, timeout_seconds)
        status_code = int(getattr(listing_response, "status_code", 0) or 0)
        if status_code >= 400:
            return {"jobs": [], "status": "failed", "status_code": status_code, "complete_snapshot": False, "credible_evidence": False, "request_url": target_url, "resolved_url": target_url, "error": f"http_{status_code}", "request_log": logs}
        listing_url = str(getattr(listing_response, "url", "") or target_url)
        listing_html = str(getattr(listing_response, "text", "") or "")
        logs.append({"url": target_url, "resolved_url": listing_url, "status_code": status_code, "outcome": "success"})
    except (requests.RequestException, OSError, TypeError, ValueError) as exc:
        return {"jobs": [], "status": "failed", "status_code": 0, "complete_snapshot": False, "credible_evidence": False, "request_url": target_url, "resolved_url": target_url, "error": type(exc).__name__, "request_log": logs}

    listing_soup = BeautifulSoup(listing_html, "html.parser")
    jobs: list[dict[str, object]] = []
    for item in _json_ld_values(listing_soup):
        jobs.append(_job_from_json_ld(item, page_url=listing_url, raw_html=listing_html))
    strong_links: list[str] = []
    fallback_links: list[str] = []
    for anchor in listing_soup.find_all("a", href=True):
        candidate = _url(anchor.get("href"), listing_url)
        path = urlsplit(candidate).path.casefold()
        label = _text(anchor.get_text(" ", strip=True)).casefold()
        if not candidate or not _allowed_host(_host(candidate), hosts) or candidate.rstrip("/") == listing_url.rstrip("/"):
            continue
        if any(token in path for token in ("/faq", "/searchjobs", "/aiRecommendations", "/home")) or any(token in label for token in ("faq", "support", "ai recommendations", "all jobs", "home")):
            continue
        if not any(token in path for token in ("jobdetail", "/job/", "/position/", "/vacanc", "/stellen")):
            if not any(token in path for token in ("/job", "/position", "/career")):
                continue
            if candidate not in fallback_links:
                fallback_links.append(candidate)
            continue
        if candidate not in strong_links:
            strong_links.append(candidate)
        if len(strong_links) >= bounded_links:
            break
    links = (strong_links + fallback_links)[:bounded_links]
    detail_failures: list[dict[str, object]] = []
    for detail_url in links[:bounded_links]:
        try:
            response = _request(request, detail_url, timeout_seconds)
            status_code = int(getattr(response, "status_code", 0) or 0)
            if status_code >= 400:
                detail_failures.append({"url": detail_url, "status_code": status_code, "error": f"http_{status_code}"})
                continue
            html = str(getattr(response, "text", "") or "")
            jobs.append(_job_from_html(page_url=str(getattr(response, "url", "") or detail_url), html=html))
            logs.append({"url": detail_url, "resolved_url": str(getattr(response, "url", "") or detail_url), "status_code": status_code, "outcome": "success"})
        except (requests.RequestException, OSError, TypeError, ValueError, AttributeError) as exc:
            detail_failures.append({"url": detail_url, "error": type(exc).__name__})
    unique: dict[str, dict[str, object]] = {}
    for job in jobs:
        identity = _text(job.get("job_id") or job.get("job_detail_url"))
        if identity and identity not in unique:
            unique[identity] = job
    partial = bool(links) and len(links) >= bounded_links
    return {
        "jobs": list(unique.values()),
        "status": "incomplete" if partial or detail_failures else "completed",
        "status_code": int(getattr(listing_response, "status_code", 200) or 200),
        "complete_snapshot": False,
        "credible_evidence": bool(logs and unique),
        "request_url": target_url,
        "resolved_url": listing_url,
        "redirected": listing_url.rstrip("/") != target_url.rstrip("/"),
        "pages_fetched": 1,
        "requests_made": len(logs),
        "source_reported_count": len(unique),
        "request_log": logs,
        "observation_failures": detail_failures,
        "warnings": ["bounded_detail_limit_reached"] if partial else [],
    }


__all__ = ["DEFAULT_MAX_JOB_LINKS", "fetch_generic_snapshot"]
