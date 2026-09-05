"""Bounded generic fallbacks for JavaScript-heavy employer job sites."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - exercised when the optional runtime is absent
    PlaywrightTimeoutError = TimeoutError
    sync_playwright = None


MAX_EMBEDDED_BYTES = 2_000_000
MAX_JSON_DEPTH = 8
MAX_JSON_NODES = 10_000
MAX_BROWSER_RESPONSE_BYTES = 2_000_000
JOB_PATH_MARKERS = (
    "/job/",
    "/jobs/",
    "/position",
    "/vacan",
    "/stellen",
    "jobdetail",
    "requisition",
    "opening",
)
GENERIC_LINK_TEXT = {
    "apply",
    "apply now",
    "learn more",
    "view job",
    "view jobs",
    "details",
    "read more",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _lookup(mapping: Mapping[str, Any], names: Iterable[str]) -> Any:
    folded = {str(key).casefold(): value for key, value in mapping.items()}
    for name in names:
        value = folded.get(name.casefold())
        if value not in (None, "", [], {}):
            return value
    return ""


def _value_text(value: Any) -> str:
    if isinstance(value, Mapping):
        return _text(_lookup(value, ("name", "value", "text", "addressLocality", "addressCountry", "city", "country")))
    if isinstance(value, list):
        return "; ".join(part for part in (_value_text(item) for item in value) if part)
    return _text(value)


def _iter_mappings(value: Any, *, depth: int = 0, seen_nodes: list[int] | None = None) -> Iterable[Mapping[str, Any]]:
    if depth > MAX_JSON_DEPTH:
        return
    if seen_nodes is None:
        seen_nodes = [0]
    seen_nodes[0] += 1
    if seen_nodes[0] > MAX_JSON_NODES:
        return
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _iter_mappings(child, depth=depth + 1, seen_nodes=seen_nodes)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_mappings(child, depth=depth + 1, seen_nodes=seen_nodes)


def _payload_from_script(text: str) -> Any:
    raw = text.strip()
    if not raw or len(raw.encode("utf-8")) > MAX_EMBEDDED_BYTES:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        pass
    start_candidates = [index for index in (raw.find("{"), raw.find("[")) if index >= 0]
    if not start_candidates:
        return None
    try:
        return json.JSONDecoder().raw_decode(raw[min(start_candidates) :])[0]
    except (TypeError, ValueError):
        return None


def _assignment_payloads(script_text: str) -> Iterable[Any]:
    for match in re.finditer(
        r"(?:window\.)?(?:__[A-Z0-9_$]+|INITIAL_STATE|NEXT_DATA|NUXT|PRELOADED_STATE)\s*=\s*",
        script_text,
        re.I,
    ):
        payload = _payload_from_script(script_text[match.end() :])
        if payload is not None:
            yield payload


def _job_from_mapping(
    mapping: Mapping[str, Any],
    *,
    page_url: str,
    format_name: str,
    source_endpoint: str,
) -> dict[str, Any] | None:
    title = _value_text(_lookup(mapping, ("title", "jobTitle", "job_title", "positionTitle", "position_title", "text")))
    detail_value = _lookup(
        mapping,
        ("url", "jobUrl", "job_url", "jobDetailUrl", "detailUrl", "absolute_url", "hostedUrl", "link"),
    )
    detail_url = urljoin(page_url, _value_text(detail_value)) if _value_text(detail_value) else ""
    identifier = _lookup(
        mapping,
        (
            "job_id",
            "jobId",
            "jobID",
            "id",
            "externalId",
            "external_id",
            "requisitionId",
            "requisition_id",
            "reqId",
            "identifier",
        ),
    )
    if isinstance(identifier, Mapping):
        identifier = _lookup(identifier, ("value", "name", "id"))
    job_id = _value_text(identifier)
    description = _value_text(
        _lookup(
            mapping,
            (
                "description",
                "descriptionHtml",
                "description_html",
                "jobDescription",
                "full_description",
                "summary",
                "content",
            ),
        )
    )
    location = _value_text(
        _lookup(mapping, ("location", "jobLocation", "locations", "location_raw", "city", "address"))
    )
    apply_url = _value_text(
        _lookup(mapping, ("application_url", "applicationUrl", "apply_url", "applyUrl", "apply_link", "applyLink"))
    )
    evidence = detail_url or job_id or description or location
    if not title or not evidence:
        return None
    return {
        "job_id": job_id,
        "title": title,
        "job_detail_url": detail_url or page_url,
        "description": description,
        "location": location,
        "application_url": urljoin(page_url, apply_url) if apply_url else "",
        "source_endpoint": source_endpoint or page_url,
        "source_raw_payload": {"format": format_name},
    }


def _job_identity(job: Mapping[str, Any]) -> str:
    return "|".join(
        (
            _text(job.get("job_id")),
            _text(job.get("job_detail_url")),
            _text(job.get("title")).casefold(),
        )
    )


def extract_payload_jobs(
    payload: Any,
    page_url: str,
    *,
    format_name: str,
    source_endpoint: str = "",
) -> list[dict[str, Any]]:
    """Normalize job-like mappings from one JSON or embedded-state payload."""

    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for mapping in _iter_mappings(payload):
        job = _job_from_mapping(
            mapping,
            page_url=page_url,
            format_name=format_name,
            source_endpoint=source_endpoint or page_url,
        )
        if not job:
            continue
        identity = _job_identity(job)
        if identity in seen:
            continue
        seen.add(identity)
        jobs.append(job)
    return jobs


def extract_embedded_jobs(html: str, page_url: str) -> list[dict[str, Any]]:
    """Extract job records from bounded JSON state embedded in HTML."""

    soup = BeautifulSoup(str(html or "")[:MAX_EMBEDDED_BYTES], "html.parser")
    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for script in soup.find_all("script"):
        script_type = _text(script.get("type")).casefold()
        script_id = _text(script.get("id")).casefold()
        text = script.get_text("", strip=True)
        if script_type not in {"application/json", "application/ld+json"} and not any(
            token in script_id for token in ("next", "nuxt", "state", "apollo", "data")
        ):
            if not re.search(r"(?:__INITIAL_STATE__|__NEXT_DATA__|__NUXT__|PRELOADED_STATE)\s*=", text, re.I):
                continue
        payloads = [_payload_from_script(text)]
        payloads.extend(_assignment_payloads(text))
        format_name = "json-ld" if script_type == "application/ld+json" else "embedded-json"
        for payload in payloads:
            if payload is None:
                continue
            for job in extract_payload_jobs(payload, page_url, format_name=format_name, source_endpoint=page_url):
                identity = _job_identity(job)
                if identity not in seen:
                    seen.add(identity)
                    jobs.append(job)
    return jobs


def _same_origin_or_subdomain(candidate_url: str, target_url: str) -> bool:
    target_host = (urlsplit(target_url).hostname or "").casefold().rstrip(".")
    candidate_host = (urlsplit(candidate_url).hostname or "").casefold().rstrip(".")
    return bool(
        target_host and candidate_host and (candidate_host == target_host or candidate_host.endswith(f".{target_host}"))
    )


def _job_links_from_rendered_html(html: str, page_url: str, *, max_job_links: int) -> list[dict[str, Any]]:
    soup = BeautifulSoup(str(html or "")[:MAX_EMBEDDED_BYTES], "html.parser")
    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = urljoin(page_url, _text(anchor.get("href")))
        path = urlsplit(href).path.casefold()
        title = _text(anchor.get_text(" ", strip=True))
        if (
            not title
            or title.casefold() in GENERIC_LINK_TEXT
            or not _same_origin_or_subdomain(href, page_url)
            or not any(marker in path for marker in JOB_PATH_MARKERS)
        ):
            continue
        job = {
            "job_id": _text(anchor.get("data-job-id") or anchor.get("data-id")),
            "title": title,
            "job_detail_url": href,
            "description": "",
            "location": "",
            "source_endpoint": page_url,
            "source_raw_payload": {"format": "browser-rendered"},
        }
        identity = _job_identity(job)
        if identity not in seen:
            seen.add(identity)
            jobs.append(job)
        if len(jobs) >= max(1, int(max_job_links)):
            break
    return jobs


def _browser_failure(target_url: str, status: str, error: str) -> dict[str, Any]:
    return {
        "jobs": [],
        "status": status,
        "complete_snapshot": False,
        "credible_evidence": False,
        "request_url": target_url,
        "resolved_url": target_url,
        "transport": "browser",
        "requests_made": 0,
        "pages_fetched": 0,
        "error": error,
    }


def fetch_browser_snapshot(
    target_url: str,
    *,
    max_job_links: int = 25,
    timeout_seconds: int = 25,
    max_requests: int = 10,
    proxy_url: str = "",
) -> dict[str, Any]:
    """Fetch one rendered page and same-origin JSON/XHR responses safely."""

    if sync_playwright is None:
        return _browser_failure(target_url, "browser_unavailable", "playwright_not_installed")
    timeout_ms = max(1_000, min(120_000, int(timeout_seconds) * 1_000))
    response_limit = max(1, min(100, int(max_requests)))
    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    response_count = 0

    def add_jobs(items: Iterable[Mapping[str, Any]]) -> None:
        for job in items:
            identity = _job_identity(job)
            if identity not in seen:
                seen.add(identity)
                jobs.append(dict(job))

    try:
        with sync_playwright() as playwright:
            launch_options: dict[str, Any] = {"headless": True}
            if proxy_url:
                launch_options["proxy"] = {"server": proxy_url}
            browser = playwright.chromium.launch(**launch_options)
            try:
                context = browser.new_context()
                page = context.new_page()

                def handle_response(response: Any) -> None:
                    nonlocal response_count
                    if response_count >= response_limit:
                        return
                    response_url = _text(getattr(response, "url", ""))
                    if not response_url or not _same_origin_or_subdomain(response_url, target_url):
                        return
                    response_type = _text(getattr(getattr(response, "request", None), "resource_type", ""))
                    headers = getattr(response, "headers", {}) or {}
                    content_type = (
                        _text(headers.get("content-type", "")).casefold() if isinstance(headers, Mapping) else ""
                    )
                    if response_type not in {"xhr", "fetch"} and "json" not in content_type:
                        return
                    response_count += 1
                    try:
                        body_reader = getattr(response, "body", None)
                        if callable(body_reader):
                            body = body_reader()
                            if len(body) > MAX_BROWSER_RESPONSE_BYTES:
                                return
                            payload = json.loads(body.decode("utf-8", errors="replace"))
                        else:
                            payload = response.json()
                    except (AttributeError, TypeError, ValueError, OSError):
                        return
                    add_jobs(
                        extract_payload_jobs(
                            payload,
                            response_url,
                            format_name="xhr",
                            source_endpoint=response_url,
                        )
                    )

                page.on("response", handle_response)
                page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(min(2_000, max(250, timeout_ms // 4)))
                rendered_html = page.content()
                add_jobs(extract_embedded_jobs(rendered_html, target_url))
                add_jobs(_job_links_from_rendered_html(rendered_html, target_url, max_job_links=max_job_links))
            finally:
                browser.close()
    except PlaywrightTimeoutError:
        return _browser_failure(target_url, "browser_failed", "timeout")
    except Exception as exc:  # pragma: no cover - provider/browser-specific failures
        return _browser_failure(target_url, "browser_failed", type(exc).__name__)

    return {
        "jobs": jobs,
        "status": "completed",
        "status_code": 200,
        "complete_snapshot": True,
        "credible_evidence": True,
        "request_url": target_url,
        "resolved_url": target_url,
        "transport": "browser",
        "requests_made": response_count + 1,
        "pages_fetched": 1,
        "rendered_html": rendered_html[:MAX_EMBEDDED_BYTES],
        "raw_content_hash": hashlib.sha256(str(rendered_html).encode("utf-8")).hexdigest(),
    }


__all__ = ["extract_embedded_jobs", "extract_payload_jobs", "fetch_browser_snapshot"]
