"""Optional work-email lookup through Hunter; never infer an address locally."""
from __future__ import annotations

import os
from urllib.parse import urlparse

import requests


def linkedin_handle(linkedin_url: str) -> str:
    parsed = urlparse(str(linkedin_url or "").strip())
    if parsed.scheme != "https" or parsed.hostname not in {"linkedin.com", "www.linkedin.com"} or not parsed.path.startswith("/in/"):
        raise ValueError("Enter a LinkedIn profile URL.")
    handle = parsed.path.removeprefix("/in/").strip("/")
    if not handle or "/" in handle or len(handle) > 120:
        raise ValueError("Enter a LinkedIn profile URL.")
    return handle


def find_work_email(linkedin_url: str) -> dict[str, str]:
    handle = linkedin_handle(linkedin_url)
    key = (os.getenv("HUNTER_API_KEY") or "").strip()
    if not key:
        return {"state": "unavailable", "reason": "email_provider_not_configured"}
    response = requests.get(
        "https://api.hunter.io/v2/email-finder/found",
        params={"linkedin_handle": handle, "api_key": key},
        timeout=15,
    )
    if response.status_code in {404, 451}:
        return {"state": "not_found"}
    response.raise_for_status()
    data = response.json().get("data") or {}
    email = str(data.get("email") or "").strip()
    if not email or "@" not in email:
        return {"state": "not_found"}
    return {"state": "found", "email": email, "provider": "hunter"}
