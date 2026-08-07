from __future__ import annotations

import logging
from datetime import datetime, timezone
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urlparse

import requests

from backend.domain.pipeline_jobs import stable_manual_job_id


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
    posted_at = str(job.get("updated_at") or "").strip()
    location_value = job.get("location") or {}
    location = str(location_value.get("name") or "").strip() if isinstance(location_value, dict) else ""
    return {
        "job_id": str(job.get("id") or stable_manual_job_id(job_url, prefix="greenhouse")),
        "title": str(job.get("title") or "").strip(),
        "url": job_url,
        "link": job_url,
        "source_url": job_url,
        "apply_link": job_url,
        "apply_link_source": "greenhouse",
        "company": board_token,
        "location": location,
        "location_raw": location,
        "posted_at": posted_at,
        "posted_time_text": posted_at,
        "posted_age_hours": _age_hours(posted_at),
        "full_description": str(job.get("content") or ""),
        "source_ats": "greenhouse",
    }


def _normalize_lever_job(job: dict[str, Any], company_slug: str) -> dict[str, Any]:
    job_url = str(job.get("hostedUrl") or job.get("applyUrl") or "").strip()
    categories = job.get("categories") or {}
    location = str(categories.get("location") or "").strip() if isinstance(categories, dict) else ""
    created_at = job.get("createdAt")
    posted_at = ""
    if created_at not in (None, ""):
        try:
            posted_at = datetime.fromtimestamp(float(created_at) / 1000, tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            posted_at = ""
    return {
        "job_id": str(job.get("id") or stable_manual_job_id(job_url, prefix="lever")),
        "title": str(job.get("text") or "").strip(),
        "url": job_url,
        "link": job_url,
        "source_url": job_url,
        "apply_link": job_url,
        "apply_link_source": "lever",
        "company": company_slug,
        "location": location,
        "location_raw": location,
        "posted_at": posted_at,
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
        try:
            for page in range(max(1, min(20, int(max_pages))), 0, -1):
                page_number = max(1, min(20, int(max_pages))) - page + 1
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
            }
        return {
            "jobs": [_normalize_greenhouse_job(job, board_token) for job in jobs or [] if isinstance(job, dict)],
            "status": "completed",
            "status_code": int(getattr(last_response, "status_code", 200) or 200),
            "complete_snapshot": pages_fetched > 0,
            "credible_evidence": pages_fetched > 0,
            "request_url": request_url,
            "resolved_url": str(getattr(last_response, "url", "") or request_url),
            "redirected": str(getattr(last_response, "url", "") or request_url).rstrip("/") != request_url.rstrip("/"),
            "pages_fetched": pages_fetched,
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
        try:
            for page_number in range(1, max(1, min(20, int(max_pages))) + 1):
                page_url = request_url if page_number == 1 else f"{request_url}&skip={100 * (page_number - 1)}"
                response = request(page_url, timeout=timeout_seconds, allow_redirects=False)
                response.raise_for_status()
                payload = response.json()
                last_response = response
                page_postings = payload if isinstance(payload, list) else []
                postings.extend(item for item in page_postings if isinstance(item, dict))
                pages_fetched += 1
                if len(page_postings) < 100:
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
            }
        return {
            "jobs": [_normalize_lever_job(job, company_slug) for job in postings if isinstance(job, dict)],
            "status": "completed",
            "status_code": int(getattr(last_response, "status_code", 200) or 200),
            "complete_snapshot": pages_fetched > 0,
            "credible_evidence": pages_fetched > 0,
            "request_url": request_url,
            "resolved_url": str(getattr(last_response, "url", "") or request_url),
            "redirected": str(getattr(last_response, "url", "") or request_url).rstrip("/") != request_url.rstrip("/"),
            "pages_fetched": pages_fetched,
        }

    if normalized_ats in {"workday", "personio", "recruitee", "smartrecruiters"}:
        LOGGER.info(
            "ATS detected but structured API not yet implemented - will fall through to proxy: %s (%s)",
            url,
            normalized_ats,
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
