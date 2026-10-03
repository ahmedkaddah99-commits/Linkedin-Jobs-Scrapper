from __future__ import annotations

from collections.abc import Callable
from typing import Any

import requests


_JOB_SIGNAL_WORDS = ("job", "jobs", "career", "careers", "position", "vacanc", "stellen", "stellenangebot")


def fetch_bounded_probe(
    url: str,
    *,
    requester: Callable[..., Any] | None = None,
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    """Make one inexpensive direct request and report only listing evidence."""

    request = requester or requests.get
    try:
        response = request(url, timeout=timeout_seconds, allow_redirects=False)
        status_code = int(getattr(response, "status_code", 0) or 0)
        body = str(getattr(response, "text", "") or "")
        resolved_url = str(getattr(response, "url", "") or url)
        lowered = f"{resolved_url} {body[:200000]}".casefold()
        credible = status_code == 200 and any(signal in lowered for signal in _JOB_SIGNAL_WORDS)
        return {
            "jobs": [],
            "status": "completed" if status_code == 200 else "blocked",
            "status_code": status_code,
            "complete_snapshot": False,
            "credible_evidence": credible,
            "request_url": url,
            "resolved_url": resolved_url,
            "redirected": resolved_url.rstrip("/") != url.rstrip("/"),
            "resolved_ats": "",
            "evidence": "listing_signal" if credible else "no_credible_listing_signal",
        }
    except requests.RequestException as exc:
        return {
            "jobs": [],
            "status": "failed",
            "complete_snapshot": False,
            "credible_evidence": False,
            "request_url": url,
            "error": str(exc),
        }


__all__ = ["fetch_bounded_probe"]
