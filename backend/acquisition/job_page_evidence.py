"""Conservative evidence gate for generic employer pages.

Generic page state contains navigation objects as well as job objects. A title
and URL alone are insufficient evidence that an object is a vacancy.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import parse_qs, urlsplit


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
    if title in _NAVIGATION_TITLES or title.startswith(("about us ", "contact us ", "privacy policy ")):
        return "generic_navigation_title"
    description = _text(record.get("description_text") or record.get("description"))
    location = _text(record.get("location_raw") or record.get("location"))
    apply_url = _text(record.get("apply_url_canonical") or record.get("application_url") or record.get("apply_url"))
    detail_url = record.get("source_job_url") or record.get("job_detail_url") or record.get("canonical_url")
    if not (description or location or apply_url or job_detail_url_has_evidence(detail_url)
            or _career_slug_matches_title(detail_url, title)):
        return "no_job_specific_evidence"
    return ""


__all__ = ["generic_employer_non_job_reason", "job_detail_url_has_evidence"]
