"""Conservative evidence gate for generic employer pages.

Generic page state contains navigation objects as well as job objects. A title
and URL alone are insufficient evidence that an object is a vacancy.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import parse_qs, unquote, urlsplit


_NAVIGATION_TITLES = {
    "about", "about us", "contact", "contact us", "home", "privacy",
    "privacy policy", "privacy notice", "cookie policy", "cookies",
    "careers", "career", "jobs", "job openings", "career opportunities",
    "career events", "terms of use", "terms and conditions",
}
_DETAIL_PATH = re.compile(
    r"/(?:jobs?|positions?|openings?|vacanc(?:y|ies)|requisitions?|"
    r"stellenangebote?|jobdetail|job-postings?|offers?)/[^/]+",
    re.I,
)
_JOB_QUERY_KEYS = {"jobid", "job_id", "requisitionid", "reqid", "postingid"}


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def is_navigation_title(record: Mapping[str, object]) -> bool:
    title = _text(record.get("job_title") or record.get("title")).casefold()
    return title in _NAVIGATION_TITLES or title.startswith(
        ("about us ", "contact us ", "privacy policy ")
    )


def employer_page_needs_verification(record: Mapping[str, object]) -> bool:
    method = _text(record.get("extraction_method") or record.get("format")).casefold().replace("-", "_")
    raw_payload = record.get("source_raw_payload")
    if not method and isinstance(raw_payload, Mapping):
        method = _text(raw_payload.get("format")).casefold().replace("-", "_")
    return method in {"embedded_json", "browser_rendered", "static_html", "html", "xhr", "json_ld"} or (
        _text(record.get("source_provider") or record.get("source_ats")).casefold() == "generic_employer_site"
    )


def job_detail_url_has_evidence(value: object) -> bool:
    """Require a job-specific URL, not a generic career landing page."""

    try:
        parts = urlsplit(_text(value))
    except ValueError:
        return False
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return False
    if _DETAIL_PATH.search(parts.path.rstrip("/")):
        return True
    return any(key.casefold() in _JOB_QUERY_KEYS for key in parse_qs(parts.query))


def _application_targets_detail(detail_url: object, apply_url: object, title: str) -> bool:
    """An arbitrary application link on a career page is not a job application."""

    try:
        detail = urlsplit(_text(detail_url))
        apply = urlsplit(_text(apply_url))
    except ValueError:
        return False
    if apply.scheme not in {"http", "https"} or not apply.netloc:
        return False
    detail_path = unquote(detail.path).casefold().rstrip("/")
    apply_path = unquote(apply.path).casefold().rstrip("/")
    if (detail.hostname or "").removeprefix("www.") == (apply.hostname or "").removeprefix("www.") and detail_path == apply_path:
        # The detail page itself can host the application form. A category page
        # with an unrelated title must not inherit that privilege.
        slug_words = set(re.findall(r"[a-z0-9]{4,}", detail_path.split("/")[-1]))
        title_words = set(re.findall(r"[a-z0-9]{4,}", title))
        return bool(slug_words & title_words) and not title.endswith(" jobs")
    final_segment = detail_path.split("/")[-1]
    if final_segment and final_segment not in {"jobs", "careers", "career", "stellenangebote", "karriere"}:
        if f"/{final_segment}/" in f"{apply_path}/" or final_segment in unquote(apply.query).casefold():
            return True
    detail_tokens = [token for token in re.findall(r"[a-z0-9]{6,}", final_segment)
                     if token not in {"jobs", "careers", "career", "stellenangebote", "karriere", "detail", "position",
                                          "bewerben", "bewerbung", "application", "apply"}]
    apply_text = unquote(apply_path + "?" + apply.query).casefold()
    # A shared posting ID or distinctive role slug links the application to
    # this posting. Generic /apply and /jobs endpoints fail this test.
    return any(token in apply_text for token in detail_tokens)


def _career_slug_matches_title(url: object, title: str) -> bool:
    """Keep role detail pages with a descriptive career slug."""

    try:
        path = urlsplit(_text(url)).path.casefold().strip("/")
    except ValueError:
        return False
    parts = path.split("/")
    if len(parts) < 2 or parts[-2] not in {"career", "careers", "karriere", "karrieren"}:
        return False
    title_words = {word for word in re.findall(r"[a-z0-9]{4,}", title.casefold())}
    slug_words = {word for word in re.findall(r"[a-z0-9]{4,}", parts[-1])}
    return len(title_words & slug_words) >= 2


def generic_employer_non_job_reason(record: Mapping[str, object]) -> str:
    """Return a hard rejection reason for unverified generic site content."""

    title = _text(record.get("job_title") or record.get("title")).casefold()
    if is_navigation_title(record):
        return "generic_navigation_title"
    description = _text(record.get("description_text") or record.get("description"))
    location = _text(record.get("location_raw") or record.get("location"))
    apply_url = _text(record.get("apply_url_canonical") or record.get("application_url") or record.get("apply_url"))
    detail_url = record.get("source_job_url") or record.get("job_detail_url") or record.get("canonical_url")
    method = _text(record.get("extraction_method") or record.get("format")).casefold().replace("-", "_")
    raw_payload = record.get("source_raw_payload")
    if not method and isinstance(raw_payload, Mapping):
        method = _text(raw_payload.get("format")).casefold().replace("-", "_")
    if method in {"embedded_json", "browser_rendered", "static_html", "html", "xhr"}:
        if not (description and len(description) >= 80 and apply_url
                and job_detail_url_has_evidence(detail_url)):
            return "unverified_generic_page"
        if method in {"static_html", "html", "browser_rendered"} and not _application_targets_detail(
            detail_url, apply_url, title
        ):
            return "unlinked_application"
    if method == "json_ld" and not (len(description) >= 80 and (location or apply_url)):
        return "incomplete_job_posting"
    if not (description or location or apply_url or job_detail_url_has_evidence(detail_url)
            or _career_slug_matches_title(detail_url, title)):
        return "no_job_specific_evidence"
    return ""


__all__ = ["employer_page_needs_verification", "generic_employer_non_job_reason", "is_navigation_title", "job_detail_url_has_evidence"]
