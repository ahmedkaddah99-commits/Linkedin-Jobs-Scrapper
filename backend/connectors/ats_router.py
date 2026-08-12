from __future__ import annotations

import logging
from datetime import datetime, timezone
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urlparse

import requests

from backend.domain.pipeline_jobs import stable_manual_job_id
from backend.acquisition.quality import normalize_source_timestamps
from backend.connectors.ats_expansions import EXPANSION_CONNECTORS, fetch_expansion_snapshot


LOGGER = logging.getLogger(__name__)
ATS_REQUEST_TIMEOUT_SECONDS = 20


def _host_matches(host: str, *suffixes: str) -> bool:
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in suffixes)


def detect_ats(url: str) -> str | None:
    host = (urlparse(str(url or "")).hostname or "").casefold()
    if _host_matches(host, "greenhouse.io"):
        return "greenhouse"
    if _host_matches(host, "lever.co"):
        return "lever"
    if _host_matches(host, "myworkdayjobs.com", "myworkdaysite.com", "workdayjobs.com"):
        return "workday"
    if _host_matches(host, "personio.de", "personio.com"):
        return "personio"
    if _host_matches(host, "recruitee.com"):
        return "recruitee"
    if _host_matches(host, "smartrecruiters.com"):
        return "smartrecruiters"
    return None


def _path_segment(url: str, index: int = 0) -> str:
    segments = [segment for segment in urlparse(str(url or "")).path.split("/") if segment]
    if len(segments) <= index:
        return ""
    return segments[index]


def _greenhouse_board_token(url: str) -> str:
    host = (urlparse(str(url or "")).hostname or "").casefold()
    if host == "boards-api.greenhouse.io":
        segments = [segment for segment in urlparse(url).path.split("/") if segment]
        if "boards" in segments:
            board_index = segments.index("boards") + 1
            return segments[board_index] if len(segments) > board_index else ""
    return _path_segment(url)


def _lever_company_slug(url: str) -> str:
    return _path_segment(url)


def _age_hours(posted_at: str) -> float | None:
    if not posted_at:
        return None
    try:
        posted = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)
    return round(max(0.0, (datetime.now(timezone.utc) - posted.astimezone(timezone.utc)).total_seconds() / 3600), 2)


def _normalize_greenhouse_job(job: dict[str, Any], board_token: str) -> dict[str, Any]:
    job_url = str(job.get("absolute_url") or "").strip()
    source_timestamps = normalize_source_timestamps(
        {**job, "source_ats": "greenhouse", "source_raw_payload": dict(job)},
        source_ats="greenhouse",
        provenance_url=job_url,
    )
    posted_at = str((source_timestamps.get("fields", {}).get("source_posted_at") or {}).get("value") or "")
    location_value = job.get("location") or {}
    location = str(location_value.get("name") or "").strip() if isinstance(location_value, dict) else ""
    departments = job.get("departments") if isinstance(job.get("departments"), list) else []
    offices = job.get("offices") if isinstance(job.get("offices"), list) else []
    metadata = job.get("metadata") if isinstance(job.get("metadata"), list) else []
    metadata_map = {
        str(item.get("name") or "").strip().casefold(): item.get("value")
        for item in metadata if isinstance(item, dict) and str(item.get("name") or "").strip()
    }
    return {
        "job_id": str(job.get("id") or stable_manual_job_id(job_url, prefix="greenhouse")),
        "title": str(job.get("title") or "").strip(),
        "url": job_url,
        "link": job_url,
        "source_url": job_url,
        "job_detail_url": job_url,
        "application_url": str(job.get("application_url") or job.get("apply_url") or "").strip(),
        "apply_link": str(job.get("apply_url") or job_url).strip(),
        "apply_link_source": "greenhouse",
        "company": board_token,
        "source_token": board_token,
        "source_display_name": f"{board_token} Greenhouse",
        "location": location,
        "location_raw": location,
        "location_collection": [location] if location else [],
        "department": ", ".join(str(item.get("name") or "").strip() for item in departments if isinstance(item, dict) and item.get("name")),
        "office": ", ".join(str(item.get("name") or "").strip() for item in offices if isinstance(item, dict) and item.get("name")),
        "requisition_id": str(job.get("requisition_id") or metadata_map.get("requisition id") or "").strip(),
        "categories": {"departments": departments, "offices": offices},
        "custom_fields": metadata,
        "source_status": str(job.get("status") or job.get("state") or "").strip(),
        "source_metadata": {
            "departments": departments,
            "offices": offices,
            "metadata": metadata,
            "custom_fields": metadata,
            "metadata_map": metadata_map,
            "categories": {"departments": departments, "offices": offices},
        },
        "source_raw_payload": dict(job),
        "source_posted_at": posted_at,
        "posted_at": posted_at,
        "source_timestamps": source_timestamps,
        "posted_time_text": posted_at,
        "posted_age_hours": _age_hours(posted_at),
        "full_description": str(job.get("content") or ""),
        "source_ats": "greenhouse",
    }


def _normalize_lever_job(job: dict[str, Any], company_slug: str) -> dict[str, Any]:
    job_detail_url = str(job.get("hostedUrl") or "").strip()
    application_url = str(job.get("applyUrl") or "").strip()
    job_url = job_detail_url or application_url
    categories = job.get("categories") or {}
    location = str(categories.get("location") or "").strip() if isinstance(categories, dict) else ""
    source_timestamps = normalize_source_timestamps(
        {**job, "source_ats": "lever", "source_raw_payload": dict(job)},
        source_ats="lever",
        provenance_url=job_detail_url or application_url,
    )
    posted_at = str((source_timestamps.get("fields", {}).get("source_posted_at") or {}).get("value") or "")
    commitment = str(categories.get("commitment") or "").strip() if isinstance(categories, dict) else ""
    return {
        "job_id": str(job.get("id") or stable_manual_job_id(job_url, prefix="lever")),
        "title": str(job.get("text") or "").strip(),
        "url": job_url,
        "link": job_url,
        "source_url": job_url,
        "job_detail_url": job_detail_url,
        "application_url": application_url,
        "apply_link": application_url or job_url,
        "apply_link_source": "lever",
        "company": company_slug,
        "source_token": company_slug,
        "source_display_name": f"{company_slug} Lever",
        "location": location,
        "location_raw": location,
        "location_collection": [location] if location else [],
        "department": str(categories.get("department") or "").strip() if isinstance(categories, dict) else "",
        "team": str(categories.get("team") or "").strip() if isinstance(categories, dict) else "",
        "employment_type": str(categories.get("commitment") or "").strip() if isinstance(categories, dict) else "",
        "commitment": commitment,
        "workplace_arrangement": str(job.get("workplaceType") or "").strip(),
        "salary": job.get("salaryRange") or {},
        "categories": categories,
        "custom_fields": job.get("customFields") or job.get("custom_fields") or {},
        "source_status": str(job.get("state") or job.get("status") or "").strip(),
        "source_metadata": {
            "categories": categories,
            "salaryRange": job.get("salaryRange"),
            "customFields": job.get("customFields") or job.get("custom_fields") or {},
        },
        "source_raw_payload": dict(job),
        "source_posted_at": posted_at,
        "posted_at": posted_at,
        "source_timestamps": source_timestamps,
        "posted_time_text": posted_at,
        "posted_age_hours": _age_hours(posted_at),
        "full_description": str(job.get("descriptionPlain") or job.get("description") or ""),
        "source_ats": "lever",
    }


def fetch_ats_snapshot(
    url: str,
    ats: str,
    *,
    requester: Callable[..., Any] | None = None,
    timeout_seconds: int = ATS_REQUEST_TIMEOUT_SECONDS,
    max_pages: int = 1,
    max_requests: int = 0,
    enabled: bool = False,
    max_retries: int = 0,
    page_size: int = 100,
) -> dict[str, Any]:
    """Fetch one bounded public ATS listing snapshot with request metadata."""

    request = requester or requests.get
    normalized_ats = str(ats or "").strip().casefold()
    if normalized_ats == "greenhouse":
        board_token = _greenhouse_board_token(url)
        if not board_token:
            LOGGER.warning("Unable to derive a Greenhouse board token from %s; falling through to proxy.", url)
            return {
                "jobs": [],
                "status": "invalid_target",
                "complete_snapshot": False,
                "credible_evidence": False,
                "request_url": url,
            }
        request_url = f"https://boards-api.greenhouse.io/v1/boards/{quote(board_token, safe='')}/jobs?content=true"
        jobs: list[dict[str, Any]] = []
        last_response = None
        total_expected = 0
        pages_fetched = 0
        page_limit = max(1, min(20, int(max_pages)))
        if int(max_requests or 0) > 0:
            page_limit = min(page_limit, max(1, int(max_requests)))
        pagination_complete = False
        try:
            for page in range(page_limit, 0, -1):
                page_number = page_limit - page + 1
                page_url = request_url if page_number == 1 else f"{request_url}&page={page_number}"
                response = request(page_url, timeout=timeout_seconds, allow_redirects=False)
                response.raise_for_status()
                payload = response.json()
                last_response = response
                page_jobs = payload.get("jobs") if isinstance(payload, dict) else []
                page_jobs = [item for item in (page_jobs or []) if isinstance(item, dict)]
                jobs.extend(page_jobs)
                pages_fetched += 1
                meta = payload.get("meta") if isinstance(payload, dict) else {}
                total_expected = int(meta.get("total") or 0) if isinstance(meta, dict) else 0
                if not page_jobs or (total_expected and len(jobs) >= total_expected) or len(page_jobs) < 100:
                    pagination_complete = True
                    break
        except (requests.RequestException, ValueError) as exc:
            LOGGER.warning("Greenhouse API request failed for %s; falling through to proxy: %s", url, exc)
            return {
                "jobs": [],
                "status": "failed",
                "complete_snapshot": False,
                "credible_evidence": False,
                "request_url": request_url,
                "error": str(exc),
                "pages_fetched": pages_fetched,
                "requests_made": pages_fetched,
                "pagination_complete": False,
            }
        stop_reason = "pagination_complete" if pagination_complete else (
            "max_requests"
            if int(max_requests or 0) > 0 and int(max_requests) < int(max_pages)
            else "max_pages"
        )
        return {
            "jobs": [_normalize_greenhouse_job(job, board_token) for job in jobs or [] if isinstance(job, dict)],
            "status": "completed",
            "status_code": int(getattr(last_response, "status_code", 200) or 200),
            "complete_snapshot": pages_fetched > 0 and pagination_complete,
            "pagination_complete": pagination_complete,
            "stop_reason": stop_reason,
            "credible_evidence": pages_fetched > 0,
            "request_url": request_url,
            "resolved_url": str(getattr(last_response, "url", "") or request_url),
            "redirected": str(getattr(last_response, "url", "") or request_url).rstrip("/") != request_url.rstrip("/"),
            "pages_fetched": pages_fetched,
            "requests_made": pages_fetched,
            "source_reported_count": total_expected or len(jobs),
        }

    if normalized_ats == "lever":
        company_slug = _lever_company_slug(url)
        if not company_slug:
            LOGGER.warning("Unable to derive a Lever company slug from %s; falling through to proxy.", url)
            return {
                "jobs": [],
                "status": "invalid_target",
                "complete_snapshot": False,
                "credible_evidence": False,
                "request_url": url,
            }
        request_url = f"https://api.lever.co/v0/postings/{quote(company_slug, safe='')}?mode=json"
        postings: list[dict[str, Any]] = []
        last_response = None
        pages_fetched = 0
        page_limit = max(1, min(20, int(max_pages)))
        if int(max_requests or 0) > 0:
            page_limit = min(page_limit, max(1, int(max_requests)))
        pagination_complete = False
        try:
            for page_number in range(1, page_limit + 1):
                page_url = request_url if page_number == 1 else f"{request_url}&skip={100 * (page_number - 1)}"
                response = request(page_url, timeout=timeout_seconds, allow_redirects=False)
                response.raise_for_status()
                payload = response.json()
                last_response = response
                page_postings = payload if isinstance(payload, list) else []
                postings.extend(item for item in page_postings if isinstance(item, dict))
                pages_fetched += 1
                if len(page_postings) < 100:
                    pagination_complete = True
                    break
        except (requests.RequestException, ValueError) as exc:
            LOGGER.warning("Lever API request failed for %s; falling through to proxy: %s", url, exc)
            return {
                "jobs": [],
                "status": "failed",
                "complete_snapshot": False,
                "credible_evidence": False,
                "request_url": request_url,
                "error": str(exc),
                "pages_fetched": pages_fetched,
                "requests_made": pages_fetched,
                "pagination_complete": False,
            }
        stop_reason = "pagination_complete" if pagination_complete else (
            "max_requests"
            if int(max_requests or 0) > 0 and int(max_requests) < int(max_pages)
            else "max_pages"
        )
        return {
            "jobs": [_normalize_lever_job(job, company_slug) for job in postings if isinstance(job, dict)],
            "status": "completed",
            "status_code": int(getattr(last_response, "status_code", 200) or 200),
            "complete_snapshot": pages_fetched > 0 and pagination_complete,
            "pagination_complete": pagination_complete,
            "stop_reason": stop_reason,
            "credible_evidence": pages_fetched > 0,
            "request_url": request_url,
            "resolved_url": str(getattr(last_response, "url", "") or request_url),
            "redirected": str(getattr(last_response, "url", "") or request_url).rstrip("/") != request_url.rstrip("/"),
            "pages_fetched": pages_fetched,
            "requests_made": pages_fetched,
            "source_reported_count": len(postings),
        }

    if normalized_ats in EXPANSION_CONNECTORS:
        return fetch_expansion_snapshot(
            url,
            normalized_ats,
            requester=requester,
            enabled=enabled,
            max_requests=max_requests,
            max_pages=max_pages,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
            page_size=page_size,
        )
    return {
        "jobs": [],
        "status": "unsupported",
        "complete_snapshot": False,
        "credible_evidence": False,
        "request_url": url,
    }


def fetch_ats_jobs(url: str, ats: str) -> list[dict]:
    """Backward-compatible list-only adapter used by existing user-owned flows."""

    return list(fetch_ats_snapshot(url, ats).get("jobs") or [])


__all__ = [
    "ATS_REQUEST_TIMEOUT_SECONDS",
    "detect_ats",
    "fetch_ats_snapshot",
    "fetch_ats_jobs",
]
