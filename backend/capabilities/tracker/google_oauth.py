from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.config.job_seeker import load_project_dotenv


GOOGLE_OAUTH_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_GMAIL_PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
GOOGLE_GMAIL_MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
GOOGLE_GMAIL_MESSAGE_URL_TEMPLATE = "https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}"
TRACKER_GOOGLE_DEFAULT_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
_PLACEHOLDER_ENV_VALUES = {
    "your_google_client_id",
    "your_google_client_secret",
}


def tracker_google_oauth_metadata() -> dict[str, Any]:
    load_project_dotenv(override=True)
    client_id = str(os.getenv("TRACKER_GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    client_secret = str(os.getenv("TRACKER_GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    redirect_uri = str(os.getenv("TRACKER_GOOGLE_OAUTH_REDIRECT_URI") or "").strip()
    if client_id in _PLACEHOLDER_ENV_VALUES:
        client_id = ""
    if client_secret in _PLACEHOLDER_ENV_VALUES:
        client_secret = ""
    scopes_raw = str(os.getenv("TRACKER_GOOGLE_OAUTH_SCOPES") or "").strip()
    scopes = [item.strip() for item in scopes_raw.split() if item.strip()] or list(TRACKER_GOOGLE_DEFAULT_SCOPES)
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri.rstrip("/"),
        "configured": bool(client_id and client_secret),
        "scopes": scopes,
    }


def build_google_tracker_authorization_url(*, state: str, redirect_uri: str) -> str:
    settings = tracker_google_oauth_metadata()
    if not settings["configured"]:
        raise ValueError(
            "Google OAuth is not configured. Set TRACKER_GOOGLE_OAUTH_CLIENT_ID and "
            "TRACKER_GOOGLE_OAUTH_CLIENT_SECRET."
        )
    query = urlencode(
        {
            "client_id": settings["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(settings["scopes"]),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
        }
    )
    return f"{GOOGLE_OAUTH_AUTHORIZE_URL}?{query}"


def exchange_google_tracker_oauth_code(*, code: str, redirect_uri: str) -> dict[str, Any]:
    settings = tracker_google_oauth_metadata()
    if not settings["configured"]:
        raise ValueError(
            "Google OAuth is not configured. Set TRACKER_GOOGLE_OAUTH_CLIENT_ID and "
            "TRACKER_GOOGLE_OAUTH_CLIENT_SECRET."
        )
    return _google_json_request(
        GOOGLE_OAUTH_TOKEN_URL,
        method="POST",
        body=urlencode(
            {
                "code": code,
                "client_id": settings["client_id"],
                "client_secret": settings["client_secret"],
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def refresh_google_tracker_access_token(*, refresh_token: str) -> dict[str, Any]:
    settings = tracker_google_oauth_metadata()
    if not settings["configured"]:
        raise ValueError(
            "Google OAuth is not configured. Set TRACKER_GOOGLE_OAUTH_CLIENT_ID and "
            "TRACKER_GOOGLE_OAUTH_CLIENT_SECRET."
        )
    normalized_refresh_token = str(refresh_token or "").strip()
    if not normalized_refresh_token:
        raise ValueError("A refresh token is required before syncing Gmail.")
    return _google_json_request(
        GOOGLE_OAUTH_TOKEN_URL,
        method="POST",
        body=urlencode(
            {
                "client_id": settings["client_id"],
                "client_secret": settings["client_secret"],
                "refresh_token": normalized_refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def fetch_google_tracker_profile(*, access_token: str) -> dict[str, Any]:
    return _google_json_request(
        GOOGLE_GMAIL_PROFILE_URL,
        headers={"Authorization": f"Bearer {str(access_token or '').strip()}"},
    )


def list_google_gmail_messages(*, access_token: str, limit: int, query_text: str = "") -> dict[str, Any]:
    query_payload = {
        "labelIds": "INBOX",
        "maxResults": max(1, min(100, int(limit))),
    }
    if str(query_text or "").strip():
        query_payload["q"] = str(query_text or "").strip()
    query = urlencode(query_payload)
    return _google_json_request(
        f"{GOOGLE_GMAIL_MESSAGES_URL}?{query}",
        headers={"Authorization": f"Bearer {str(access_token or '').strip()}"},
    )


def get_google_gmail_message(*, access_token: str, message_id: str) -> dict[str, Any]:
    target = GOOGLE_GMAIL_MESSAGE_URL_TEMPLATE.format(message_id=message_id)
    query = urlencode({"format": "raw"})
    return _google_json_request(
        f"{target}?{query}",
        headers={"Authorization": f"Bearer {str(access_token or '').strip()}"},
    )


def _google_json_request(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    request = Request(url, data=body, method=method)
    request.add_header("Accept", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Google API returned an unexpected payload.")
            return payload
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        try:
            payload = json.loads(error_body) if error_body else {}
        except json.JSONDecodeError:
            payload = {}
        error_payload = payload.get("error")
        if isinstance(error_payload, dict):
            error_message = str(error_payload.get("message") or "").strip()
        else:
            error_message = str(payload.get("error_description") or error_payload or "").strip()
        raise ValueError(error_message or f"Google API request failed with HTTP {exc.code}.") from exc
    except URLError as exc:
        raise ValueError(f"Unable to reach Google APIs: {exc.reason}") from exc
