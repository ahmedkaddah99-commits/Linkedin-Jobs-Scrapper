 issue from __future__ import annotations

import base64
import html
import imaplib
import re
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from email.message import Message
from email.policy import default
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any, Mapping

from backend.capabilities.tracker.google_oauth import (
    get_google_gmail_message,
    list_google_gmail_messages,
    tracker_google_oauth_metadata,
)
from backend.domain.phase0_contracts import (
    normalize_application_status,
    normalize_gmail_application_detection,
)
from backend.domain.models import utc_now_iso, utc_plus_seconds
from backend.domain.tracker import (
    ensure_review_placed_in_tracker_at,
    review_is_actionable_tracker_item,
    review_placed_in_tracker_at,
)

TRACKER_EMAIL_INTEGRATION_METADATA_KEY = "tracker_email_integration"

_MAX_PROCESSED_MESSAGE_IDS = 5000
_MAX_PENDING_REVIEW_DETECTIONS = 50
_EMAIL_SYNC_LOCK_EXPIRY_SECONDS = 900  # 15 minutes
_EMAIL_SYNC_COOLDOWN_SECONDS = 120  # 2 minutes between login-triggered syncs
_GMAIL_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class TrackerEmailProviderPreset:
    provider_id: str
    label: str
    imap_host: str
    imap_port: int
    auth_mode: str
    supported: bool
    help_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.provider_id,
            "label": self.label,
            "imap_host": self.imap_host,
            "imap_port": self.imap_port,
            "auth_mode": self.auth_mode,
            "supported": self.supported,
            "help_text": self.help_text,
        }


@dataclass(slots=True)
class TrackerMailboxMessage:
    message_id: str
    subject: str
    from_address: str
    sent_at: str
    text: str


TRACKER_EMAIL_PROVIDER_PRESETS: dict[str, TrackerEmailProviderPreset] = {
    "gmail": TrackerEmailProviderPreset(
        provider_id="gmail",
        label="Gmail",
        imap_host="imap.gmail.com",
        imap_port=993,
        auth_mode="google_oauth",
        supported=True,
        help_text="Connect Gmail with Google sign-in so the tracker can read inbox updates securely.",
    ),
    "yahoo": TrackerEmailProviderPreset(
        provider_id="yahoo",
        label="Yahoo Mail",
        imap_host="imap.mail.yahoo.com",
        imap_port=993,
        auth_mode="app_password",
        supported=True,
        help_text="Use a Yahoo app password for IMAP access.",
    ),
    "outlook": TrackerEmailProviderPreset(
        provider_id="outlook",
        label="Outlook / Hotmail",
        imap_host="outlook.office365.com",
        imap_port=993,
        auth_mode="oauth_required",
        supported=False,
        help_text="This build does not implement Microsoft OAuth yet, so Outlook sync is disabled.",
    ),
    "custom": TrackerEmailProviderPreset(
        provider_id="custom",
        label="Custom IMAP",
        imap_host="",
        imap_port=993,
        auth_mode="password",
        supported=True,
        help_text="Use this only for providers that still require direct IMAP credentials.",
    ),
    "tuta": TrackerEmailProviderPreset(
        provider_id="tuta",
        label="Tuta Mail",
        imap_host="",
        imap_port=993,
        auth_mode="unsupported",
        supported=False,
        help_text="Tuta does not expose IMAP, so this tracker cannot sync it directly.",
    ),
}

_REJECTION_PATTERNS = [
    "regret to inform you",
    "regret informing you",
    "not moving forward",
    "not move forward",
    "not be moving forward",
    "not selected",
    "not proceed",
    "rejection",
    "position has been filled",
    "went with another candidate",
    "internal candidate",
    "absage",
    "leider",
    "haben uns fuer einen anderen kandidaten",
]

_INTERVIEW_PATTERNS = [
    "interview",
    "phone screen",
    "schedule a call",
    "schedule an interview",
    "invite you to",
    "invitation to interview",
    "assessment",
    "take-home",
    "technical interview",
    "onsite",
    "zoom call",
    "teams meeting",
    "vorstellungsgespraech",
    "kennenlerngespraech",
]

_CONFIRMATION_PATTERNS = [
    "application received",
    "received your application",
    "thanks for applying",
    "thank you for applying",
    "thank you for your application",
    "we have received your application",
    "application confirmation",
    "your application has been received",
    "eingang ihrer bewerbung",
    "eingang deiner bewerbung",
    "bewerbung erhalten",
    "danke fuer ihre bewerbung",
]

_OFFER_PATTERNS = [
    "job offer",
    "offer letter",
    "employment offer",
    "we are pleased to offer",
    "we would like to offer",
    "angebot",
]

_APPLICATION_SIGNAL_PATTERNS = [
    "application",
    "applying",
    "applied",
    "candidate",
    "job",
    "position",
    "role",
    "career",
    "recruiting",
    "recruiter",
    "bewerbung",
    "kandidat",
    "stelle",
    "karriere",
]

_ATS_OR_RECRUITING_DOMAIN_HINTS = [
    "greenhouse.io",
    "lever.co",
    "workday",
    "smartrecruiters",
    "ashbyhq",
    "personio",
    "teamtailor",
    "recruitee",
    "jobvite",
    "icims",
    "bamboohr",
    "successfactors",
    "talent",
    "recruit",
    "careers",
    "jobs",
]

_GMAIL_APPLICATION_QUERY_TERMS = [
    "application",
    "interview",
    "recruiter",
    "recruiting",
    "candidate",
    "career",
    "hiring",
    "offer",
    "rejection",
    "bewerbung",
    "angebot",
    "absage",
]


def tracker_email_provider_options() -> list[dict[str, Any]]:
    return [preset.to_dict() for preset in TRACKER_EMAIL_PROVIDER_PRESETS.values()]


def _gmail_detection_key(payload: Mapping[str, Any] | None) -> str:
    detection = normalize_gmail_application_detection(payload)
    detection_id = str(detection.get("detection_id") or "").strip()
    if detection_id:
        return detection_id
    message_id = str(detection.get("source_email", {}).get("message_id") or "").strip()
    if message_id:
        return f"gmail::{message_id}"
    return ""


def _normalize_pending_review_detections(payload: Any) -> list[dict[str, Any]]:
    detections: list[dict[str, Any]] = []
    for item in payload or []:
        if not isinstance(item, Mapping):
            continue
        detection = normalize_gmail_application_detection(item)
        detection_id = _gmail_detection_key(detection)
        if not detection_id or detection["status"]["approval_state"] != "pending_review":
            continue
        detection["detection_id"] = detection_id
        detections.append(detection)
    detections.sort(key=lambda item: str(item.get("source_email", {}).get("sent_at") or ""), reverse=True)
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for detection in detections:
        detection_id = _gmail_detection_key(detection)
        if not detection_id or detection_id in seen:
            continue
        seen.add(detection_id)
        deduped.append(detection)
    return deduped[:_MAX_PENDING_REVIEW_DETECTIONS]


def _validate_email_sync_start_date(value: Any) -> str:
    """Validate and normalize an email sync start date to YYYY-MM-DD format."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = date_type.fromisoformat(text)
    except (ValueError, TypeError):
        raise ValueError("email_sync_start_date must be a valid date in YYYY-MM-DD format.")
    today = date_type.today()
    if parsed > today:
        raise ValueError("email_sync_start_date must not be in the future.")
    return parsed.isoformat()


def normalize_tracker_email_config(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    provider_id = str(raw.get("provider_id") or "gmail").strip().lower() or "gmail"
    preset = TRACKER_EMAIL_PROVIDER_PRESETS.get(provider_id, TRACKER_EMAIL_PROVIDER_PRESETS["custom"])
    has_oauth_tokens = bool(
        str(raw.get("access_token_secret_id") or "").strip()
        or str(raw.get("refresh_token_secret_id") or "").strip()
    )
    auth_strategy = str(raw.get("auth_strategy") or "").strip().lower()
    if auth_strategy not in {"google_oauth", "legacy_imap_password"}:
        auth_strategy = (
            "google_oauth"
            if has_oauth_tokens or (preset.provider_id == "gmail" and not str(raw.get("password_secret_id") or "").strip())
            else "legacy_imap_password"
        )
    imap_host = str(raw.get("imap_host") or preset.imap_host or "").strip()
    try:
        imap_port = int(raw.get("imap_port") or preset.imap_port or 993)
    except (TypeError, ValueError):
        imap_port = preset.imap_port or 993
    email_sync_start_date = str(raw.get("email_sync_start_date") or "").strip()
    if email_sync_start_date:
        try:
            email_sync_start_date = _validate_email_sync_start_date(email_sync_start_date)
        except ValueError:
            email_sync_start_date = ""
    email_sync_enabled = bool(raw.get("email_sync_enabled") or False)
    if email_sync_enabled and not email_sync_start_date:
        email_sync_enabled = False
    processed_message_ids = [
        str(item).strip()
        for item in raw.get("processed_message_ids") or []
        if str(item).strip()
    ][-_MAX_PROCESSED_MESSAGE_IDS:]
    return {
        "provider_id": preset.provider_id,
        "auth_strategy": auth_strategy,
        "authorization_state": str(raw.get("authorization_state") or "not_started").strip() or "not_started",
        "email_address": str(raw.get("email_address") or "").strip(),
        "imap_host": imap_host,
        "imap_port": max(1, imap_port),
        "folder": str(raw.get("folder") or "INBOX").strip() or "INBOX",
        "email_sync_start_date": email_sync_start_date,
        "email_sync_enabled": email_sync_enabled,
        "last_email_sync_at": str(raw.get("last_email_sync_at") or "").strip(),
        "next_email_sync_at": str(raw.get("next_email_sync_at") or "").strip(),
        "email_sync_status": str(raw.get("email_sync_status") or "idle").strip() or "idle",
        "email_sync_error": str(raw.get("email_sync_error") or "").strip(),
        "last_processed_history_id": str(raw.get("last_processed_history_id") or "").strip(),
        "password_secret_id": str(raw.get("password_secret_id") or "").strip(),
        "access_token_secret_id": str(raw.get("access_token_secret_id") or "").strip(),
        "refresh_token_secret_id": str(raw.get("refresh_token_secret_id") or "").strip(),
        "access_token_expires_at": str(raw.get("access_token_expires_at") or "").strip(),
        "oauth_state": str(raw.get("oauth_state") or "").strip(),
        "oauth_state_created_at": str(raw.get("oauth_state_created_at") or "").strip(),
        "oauth_state_expires_at": str(raw.get("oauth_state_expires_at") or "").strip(),
        "oauth_redirect_uri": str(raw.get("oauth_redirect_uri") or "").strip(),
        "oauth_authorization_url": str(raw.get("oauth_authorization_url") or "").strip(),
        "history_id": str(raw.get("history_id") or raw.get("cursor") or "").strip(),
        "connected_at": str(raw.get("connected_at") or ""),
        "updated_at": str(raw.get("updated_at") or ""),
        "last_sync_at": str(raw.get("last_sync_at") or ""),
        "last_error": str(raw.get("last_error") or ""),
        "processed_message_ids": processed_message_ids,
        "last_sync_summary": dict(raw.get("last_sync_summary") or {}),
        "pending_detections": _normalize_pending_review_detections(raw.get("pending_detections")),
    }


def build_public_tracker_email_config(
    payload: Mapping[str, Any] | None,
    *,
    has_password: bool,
    has_access_token: bool = False,
    has_refresh_token: bool = False,
) -> dict[str, Any]:
    config = normalize_tracker_email_config(payload)
    preset = TRACKER_EMAIL_PROVIDER_PRESETS[config["provider_id"]]
    oauth_settings = tracker_google_oauth_metadata()
    uses_google_oauth = config["auth_strategy"] == "google_oauth"
    connected = bool(
        config["email_address"]
        and (
            (uses_google_oauth and (has_access_token or has_refresh_token))
            or (not uses_google_oauth and config["password_secret_id"] and has_password)
        )
    )
    if connected:
        connection_status = "connected"
    elif config["authorization_state"] in {"authorization_url_created", "authorized"}:
        connection_status = "pending_authorization"
    elif config["last_error"]:
        connection_status = "attention_required"
    else:
        connection_status = "disconnected"
    return {
        "provider_id": config["provider_id"],
        "auth_strategy": config["auth_strategy"],
        "authorization_state": config["authorization_state"],
        "connection_status": connection_status,
        "email_address": config["email_address"],
        "imap_host": config["imap_host"],
        "imap_port": config["imap_port"],
        "folder": config["folder"],
        "email_sync_start_date": config["email_sync_start_date"],
        "email_sync_enabled": config["email_sync_enabled"],
        "last_email_sync_at": config["last_email_sync_at"],
        "next_email_sync_at": config["next_email_sync_at"],
        "email_sync_status": config["email_sync_status"],
        "email_sync_error": config["email_sync_error"],
        "connected": connected,
        "has_password": bool(has_password),
        "has_access_token": bool(has_access_token),
        "has_refresh_token": bool(has_refresh_token),
        "oauth_available": bool(oauth_settings["configured"]),
        "authorization_url": config["oauth_authorization_url"],
        "connected_at": config["connected_at"],
        "updated_at": config["updated_at"],
        "last_sync_at": config["last_sync_at"],
        "last_error": config["last_error"],
        "last_sync_summary": dict(config["last_sync_summary"] or {}),
        "pending_detection_count": len(config["pending_detections"]),
        "pending_detections": [dict(item) for item in config["pending_detections"]],
        "history_id": config["history_id"],
        "provider": preset.to_dict(),
    }


def test_tracker_email_connection(config: Mapping[str, Any], password: str) -> dict[str, Any]:
    normalized = normalize_tracker_email_config(config)
    if normalized["auth_strategy"] == "google_oauth":
        raise ValueError("Use Google authorization for Gmail instead of testing a password-based connection.")
    preset = TRACKER_EMAIL_PROVIDER_PRESETS[normalized["provider_id"]]
    if not preset.supported:
        raise ValueError(preset.help_text)
    if not normalized["email_address"]:
        raise ValueError("email_address is required")
    if not normalized["imap_host"]:
        raise ValueError("imap_host is required")
    if not password:
        raise ValueError("A password or app password is required.")
    client = ImapMailboxClient(
        host=normalized["imap_host"],
        port=int(normalized["imap_port"]),
        email_address=normalized["email_address"],
        password=password,
        folder=normalized["folder"],
    )
    return client.probe()


def sync_tracker_email(
    *,
    application,
    user,
    tracker_items: list[dict[str, Any]],
    config: Mapping[str, Any],
    password: str,
) -> dict[str, Any]:
    normalized = normalize_tracker_email_config(config)
    preset = TRACKER_EMAIL_PROVIDER_PRESETS[normalized["provider_id"]]
    if not preset.supported:
        raise ValueError(preset.help_text)
    if normalized["auth_strategy"] == "google_oauth":
        raise ValueError("This inbox uses Google OAuth. Use the Gmail sync path instead.")
    if not password:
        raise ValueError("A password or app password is required before syncing.")

    client = ImapMailboxClient(
        host=normalized["imap_host"],
        port=int(normalized["imap_port"]),
        email_address=normalized["email_address"],
        password=password,
        folder=normalized["folder"],
    )
    messages = client.fetch_all_messages(
        start_date=normalized.get("email_sync_start_date") or "",
        processed_ids=set(normalized.get("processed_message_ids") or []),
    )
    return _process_tracker_messages(
        application=application,
        user=user,
        tracker_items=tracker_items,
        messages=messages,
        normalized=normalized,
    )


def _resolve_email_sync_access_token(application, config: dict[str, Any]) -> str:
    """Resolve or refresh a Google access token and return it."""
    from backend.capabilities.tracker.google_oauth import refresh_google_tracker_access_token

    access_token = str(config.get("_resolved_access_token") or "").strip()
    if access_token:
        expires_at = str(config.get("access_token_expires_at") or "").strip()
        if expires_at:
            try:
                if datetime.fromisoformat(expires_at) > datetime.now(timezone.utc) + timedelta(minutes=1):
                    return access_token
            except (ValueError, TypeError):
                pass

    refresh_token = str(config.get("_resolved_refresh_token") or "").strip()
    if not refresh_token:
        raise ValueError("No refresh token available for Gmail sync.")

    token_payload = refresh_google_tracker_access_token(refresh_token=refresh_token)
    new_access_token = str(token_payload.get("access_token") or "").strip()
    if not new_access_token:
        raise ValueError("Google did not return an access token during refresh.")
    return new_access_token


def sync_user_inbox(
    *,
    application,
    user_id: str,
    trigger: str,
) -> dict[str, Any]:
    """Central sync service for all triggers: manual, login, daily.

    Handles settings loading, OAuth token refresh, lock acquisition,
    date-boundary calculation, paginated Gmail fetch, deduplication,
    tracker updates, checkpoint saving, status updates, and lock release.
    """
    user = application.get_user(user_id)
    current_config = dict((user.metadata or {}).get(TRACKER_EMAIL_INTEGRATION_METADATA_KEY) or {})
    if not current_config:
        raise ValueError("No email integration configured.")

    normalized = normalize_tracker_email_config(current_config)
    if normalized["auth_strategy"] != "google_oauth":
        raise ValueError("Only Google OAuth is supported for automatic inbox sync.")
    if not normalized.get("email_sync_start_date"):
        raise ValueError("A start date must be configured before syncing.")

    # Acquire per-user lock via status check
    current_status = str(normalized.get("email_sync_status") or "idle").strip()
    if current_status == "syncing":
        existing_sync_at = str(normalized.get("last_email_sync_at") or "").strip()
        if existing_sync_at:
            try:
                last_sync_dt = datetime.fromisoformat(existing_sync_at)
                if datetime.now(timezone.utc) - last_sync_dt < timedelta(seconds=_EMAIL_SYNC_LOCK_EXPIRY_SECONDS):
                    return {"status": "already_syncing", "message": "A sync is already in progress."}
            except (ValueError, TypeError):
                pass

    # For login trigger, apply cooldown
    if trigger == "login":
        last_sync = str(normalized.get("last_email_sync_at") or "").strip()
        if last_sync:
            try:
                if datetime.now(timezone.utc) - datetime.fromisoformat(last_sync) < timedelta(seconds=_EMAIL_SYNC_COOLDOWN_SECONDS):
                    return {"status": "cooling_down", "message": "A sync was completed recently. Skipping login-triggered sync."}
            except (ValueError, TypeError):
                pass

    # Set status to syncing
    now_iso = utc_now_iso()
    normalized["email_sync_status"] = "syncing"
    normalized["email_sync_error"] = ""
    normalized["updated_at"] = now_iso
    _persist_config_in_user(application, user, normalized)

    try:
        # Resolve tokens
        from backend.capabilities.tracker.google_oauth import refresh_google_tracker_access_token

        refresh_token_val = _resolve_tracker_email_refresh_token_from_app(application, normalized)
        if not refresh_token_val:
            raise ValueError("No refresh token available. Please reconnect Google.")

        token_payload = refresh_google_tracker_access_token(refresh_token=refresh_token_val)
        access_token = str(token_payload.get("access_token") or "").strip()
        if not access_token:
            raise ValueError("Google did not return an access token during refresh.")

        normalized["access_token_secret_id"] = _upsert_tracker_email_token_secret(
            application, user, normalized, access_token, "access"
        )
        normalized["access_token_expires_at"] = utc_plus_seconds(int(token_payload.get("expires_in") or 3600))

        # Fetch all messages paginated
        start_date = str(normalized.get("email_sync_start_date") or "").strip()
        processed_ids = set(normalized.get("processed_message_ids") or [])
        messages, history_id = _fetch_all_gmail_messages_paginated(
            access_token=access_token,
            start_date=start_date,
            processed_ids=processed_ids,
            last_history_id=str(normalized.get("last_processed_history_id") or ""),
        )

        tracker_items = _collect_tracker_entries(application, user)

        result = _process_tracker_messages(
            application=application,
            user=user,
            tracker_items=tracker_items,
            messages=messages,
            normalized=normalized,
        )

        # Update checkpoints
        updated_config = dict(normalized)
        updated_config["processed_message_ids"] = result["processed_message_ids"]
        updated_config["last_sync_at"] = result["synced_at"]
        updated_config["updated_at"] = result["synced_at"]
        updated_config["last_error"] = ""
        updated_config["last_sync_summary"] = dict(result["summary"] or {})
        updated_config["pending_detections"] = _merge_pending_tracker_detections(
            existing=updated_config.get("pending_detections") or [],
            additions=[
                detection
                for detection in result.get("detections") or []
                if isinstance(detection, dict)
                and str(detection.get("status", {}).get("approval_state") or "") == "pending_review"
            ],
        )
        updated_config["authorization_state"] = "authorized"
        if result.get("history_id"):
            updated_config["history_id"] = str(result.get("history_id") or "")
        updated_config["last_processed_history_id"] = str(history_id or "")
        updated_config["email_sync_status"] = "success"
        updated_config["email_sync_error"] = ""
        updated_config["last_email_sync_at"] = result["synced_at"]
        updated_config["next_email_sync_at"] = utc_plus_seconds(24 * 3600)

        _persist_config_in_user(application, user, updated_config)

        return {
            "status": "success",
            "trigger": trigger,
            "result": result,
        }

    except Exception as exc:
        error_text = str(exc)
        failed_config = dict(normalized)
        failed_config["email_sync_status"] = "error"
        failed_config["email_sync_error"] = error_text
        failed_config["updated_at"] = utc_now_iso()
        if "invalid_grant" in error_text.lower() or "expired or revoked" in error_text.lower():
            failed_config["connected"] = False
            failed_config["authorization_state"] = "reauthorization_required"
        _persist_config_in_user(application, user, failed_config)
        raise


def _resolve_tracker_email_refresh_token_from_app(application, config: dict[str, Any]) -> str:
    """Resolve the refresh token from the secrets store."""
    refresh_token_secret_id = str(config.get("refresh_token_secret_id") or "").strip()
    if not refresh_token_secret_id:
        return ""
    try:
        secret = application.get_secret(refresh_token_secret_id)
        return str(secret.get("value") or "").strip()
    except KeyError:
        return ""


def _upsert_tracker_email_token_secret(
    application,
    user,
    config: dict[str, Any],
    token_value: str,
    kind: str,
) -> str:
    """Store an OAuth token as a secret and return its secret ID."""
    existing_secret_id = str(config.get(f"{kind}_token_secret_id") or "").strip()
    secret = {
        "value": token_value,
        "provider": "google_oauth",
        "workspace_id": "",
        "secret_id": existing_secret_id or f"tracker_{kind}_token_{user.user_id}",
    }
    if existing_secret_id:
        application.upsert_secret(secret)
    else:
        application.create_secret(secret)
    return secret["secret_id"]


def sync_tracker_gmail(
    *,
    application,
    user,
    tracker_items: list[dict[str, Any]],
    config: Mapping[str, Any],
    access_token: str,
) -> dict[str, Any]:
    """Legacy sync path. Prefer sync_user_inbox for all trigger types."""
    normalized = normalize_tracker_email_config(config)
    if normalized["auth_strategy"] != "google_oauth":
        raise ValueError("This inbox is not configured for Google OAuth.")
    if not access_token:
        raise ValueError("A Google access token is required before syncing Gmail.")

    start_date = str(normalized.get("email_sync_start_date") or "").strip()
    processed_ids = set(normalized.get("processed_message_ids") or [])
    messages, history_id = _fetch_all_gmail_messages_paginated(
        access_token=access_token,
        start_date=start_date,
        processed_ids=processed_ids,
        last_history_id=str(normalized.get("last_processed_history_id") or ""),
    )

    result = _process_tracker_messages(
        application=application,
        user=user,
        tracker_items=tracker_items,
        messages=messages,
        normalized=normalized,
    )
    result["history_id"] = history_id
    return result


def _fetch_all_gmail_messages_paginated(
    *,
    access_token: str,
    start_date: str,
    processed_ids: set[str],
    last_history_id: str = "",
) -> tuple[list[TrackerMailboxMessage], str]:
    """Fetch all matching Gmail messages using pagination, from start_date onward.

    Continues fetching pages until no more results are available.
    Returns all messages and the latest history_id seen.
    """
    query_text = _gmail_query_for_start_date(start_date)
    all_messages: list[TrackerMailboxMessage] = []
    latest_history_id = str(last_history_id or "").strip()
    page_token = ""
    page_count = 0

    while True:
        page_count += 1
        try:
            listing = list_google_gmail_messages(
                access_token=access_token,
                limit=_GMAIL_PAGE_SIZE,
                query_text=query_text,
                page_token=page_token,
            )
        except ValueError as exc:
            error_text = str(exc)
            if query_text and ("400" in error_text or "invalid query" in error_text.lower()):
                listing = list_google_gmail_messages(
                    access_token=access_token,
                    limit=_GMAIL_PAGE_SIZE,
                    query_text="",
                    page_token=page_token,
                )
            else:
                raise

        message_refs = listing.get("messages") or []
        for item in message_refs:
            if not isinstance(item, Mapping):
                continue
            message_id = str(item.get("id") or "").strip()
            if not message_id or message_id in processed_ids:
                continue
            try:
                raw_message = get_google_gmail_message(access_token=access_token, message_id=message_id)
            except ValueError:
                continue
            message_bytes = _decode_gmail_raw_payload(str(raw_message.get("raw") or ""))
            if not message_bytes:
                continue
            parsed = message_from_bytes(message_bytes, policy=default)
            message = TrackerMailboxMessage(
                message_id=_build_message_id(parsed, fallback=message_id),
                subject=str(parsed.get("subject") or "").strip(),
                from_address=parseaddr(str(parsed.get("from") or ""))[1],
                sent_at=_parse_message_date(str(parsed.get("date") or "")),
                text=_extract_text_body(parsed),
            )
            if start_date and not _message_on_or_after_date(message, start_date):
                continue
            all_messages.append(message)
            history_id = str(raw_message.get("historyId") or "")
            if history_id:
                latest_history_id = history_id

        page_token = str(listing.get("nextPageToken") or "").strip()
        if not page_token:
            break

    return all_messages, latest_history_id


def _gmail_query_for_start_date(start_date: str) -> str:
    """Build a Gmail search query for emails on or after the start date."""
    keyword_group = "{" + " ".join(_GMAIL_APPLICATION_QUERY_TERMS) + "}"
    start_date = str(start_date or "").strip()
    if not start_date:
        return f"in:inbox {keyword_group}"
    try:
        parsed = date_type.fromisoformat(start_date)
    except (ValueError, TypeError):
        return f"in:inbox {keyword_group}"
    date_str = parsed.strftime("%Y/%m/%d")
    return f"in:inbox after:{date_str} {keyword_group}"


def _message_on_or_after_date(message: TrackerMailboxMessage, start_date: str) -> bool:
    """Check if a message was sent on or after the specified date."""
    if not message.sent_at or not start_date:
        return True
    try:
        start_dt = datetime.fromisoformat(start_date)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        else:
            start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        sent_dt = datetime.fromisoformat(message.sent_at)
        if sent_dt.tzinfo is None:
            sent_dt = sent_dt.replace(tzinfo=timezone.utc)
        return sent_dt >= start_dt
    except (ValueError, TypeError):
        return True


def _collect_tracker_entries(application, user) -> list[dict[str, Any]]:
    """Collect all tracker entries for a user."""
    try:
        from backend.api.routes.tracker import _collect_tracker_entries as _collect
        return _collect(application, user)
    except ImportError:
        return []


def _persist_config_in_user(application, user, config: dict[str, Any]) -> None:
    """Persist the email integration config into the user's metadata."""
    metadata = dict(user.metadata or {})
    metadata[TRACKER_EMAIL_INTEGRATION_METADATA_KEY] = dict(config)
    user.metadata = metadata
    user.updated_at = utc_now_iso()
    application.repositories.auth_repository.upsert_user(user)


def begin_google_tracker_authorization(
    config: Mapping[str, Any],
    *,
    redirect_uri: str,
    authorization_url: str,
) -> dict[str, Any]:
    normalized = normalize_tracker_email_config(config)
    now_iso = utc_now_iso()
    return {
        **normalized,
        "provider_id": "gmail",
        "auth_strategy": "google_oauth",
        "authorization_state": "authorization_url_created",
        "oauth_redirect_uri": redirect_uri,
        "oauth_authorization_url": authorization_url,
        "oauth_state_created_at": now_iso,
        "oauth_state_expires_at": utc_plus_seconds(600),
        "updated_at": now_iso,
        "last_error": "",
    }


def complete_google_tracker_authorization(
    config: Mapping[str, Any],
    *,
    email_address: str,
) -> dict[str, Any]:
    normalized = normalize_tracker_email_config(config)
    now_iso = utc_now_iso()
    return {
        **normalized,
        "provider_id": "gmail",
        "auth_strategy": "google_oauth",
        "authorization_state": "authorized",
        "email_address": str(email_address or normalized["email_address"]).strip(),
        "oauth_state": "",
        "oauth_state_created_at": "",
        "oauth_state_expires_at": "",
        "oauth_authorization_url": "",
        "connected_at": str(normalized.get("connected_at") or now_iso),
        "updated_at": now_iso,
        "last_error": "",
    }


def mark_google_tracker_authorization_error(config: Mapping[str, Any], *, error_message: str) -> dict[str, Any]:
    normalized = normalize_tracker_email_config(config)
    return {
        **normalized,
        "authorization_state": "not_started",
        "oauth_state": "",
        "oauth_state_created_at": "",
        "oauth_state_expires_at": "",
        "oauth_authorization_url": "",
        "updated_at": utc_now_iso(),
        "last_error": str(error_message or "").strip(),
    }


def tracker_google_oauth_state_is_valid(config: Mapping[str, Any], *, expected_state: str) -> bool:
    normalized = normalize_tracker_email_config(config)
    stored_state = str(normalized.get("oauth_state") or "").strip()
    if not stored_state or stored_state != str(expected_state or "").strip():
        return False
    expires_at = str(normalized.get("oauth_state_expires_at") or "").strip()
    if not expires_at:
        return True
    try:
        return datetime.fromisoformat(expires_at) >= datetime.now(timezone.utc)
    except Exception:
        return False


def tracker_google_oauth_callback_message(*, success: bool, message: str) -> str:
    title = "Google Inbox Connected" if success else "Google Inbox Connection Failed"
    accent = "#0f766e" if success else "#b91c1c"
    safe_message = html.escape(str(message or "").strip() or title)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{title}</title>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "</head><body style=\"margin:0;font-family:Segoe UI,Arial,sans-serif;background:#f5f7fb;color:#111827;\">"
        "<div style=\"min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;\">"
        "<div style=\"max-width:520px;background:white;border:1px solid #dbe4f0;border-radius:20px;padding:28px;"
        "box-shadow:0 16px 40px rgba(15,23,42,0.08);\">"
        f"<div style=\"font-size:14px;font-weight:700;color:{accent};text-transform:uppercase;letter-spacing:.08em;\">Tracker</div>"
        f"<h1 style=\"margin:12px 0 8px;font-size:28px;line-height:1.1;\">{title}</h1>"
        f"<p style=\"margin:0 0 18px;font-size:15px;line-height:1.6;color:#475569;\">{safe_message}</p>"
        "<p style=\"margin:0;font-size:13px;color:#64748b;\">You can close this window and return to the app.</p>"
        "</div></div><script>setTimeout(function(){window.close();},1200);</script></body></html>"
    )


class ImapMailboxClient:
    def __init__(self, *, host: str, port: int, email_address: str, password: str, folder: str) -> None:
        self.host = str(host).strip()
        self.port = int(port)
        self.email_address = str(email_address).strip()
        self.password = str(password)
        self.folder = str(folder).strip() or "INBOX"

    def probe(self) -> dict[str, Any]:
        mailbox = imaplib.IMAP4_SSL(self.host, self.port)
        try:
            mailbox.login(self.email_address, self.password)
            status, _ = mailbox.select(self.folder, readonly=True)
            if status != "OK":
                raise ValueError(f"Unable to open folder '{self.folder}'.")
            return {"status": "connected", "folder": self.folder}
        except imaplib.IMAP4.error as exc:
            raise ValueError(f"IMAP login failed: {exc}") from exc
        finally:
            try:
                mailbox.logout()
            except Exception:
                pass

    def fetch_all_messages(
        self,
        *,
        start_date: str = "",
        processed_ids: set[str] | None = None,
    ) -> list[TrackerMailboxMessage]:
        """Fetch all IMAP messages since start_date, excluding already processed IDs."""
        processed = processed_ids or set()
        mailbox = imaplib.IMAP4_SSL(self.host, self.port)
        try:
            mailbox.login(self.email_address, self.password)
            status, _ = mailbox.select(self.folder, readonly=True)
            if status != "OK":
                raise ValueError(f"Unable to open folder '{self.folder}'.")

            if start_date:
                try:
                    since_dt = datetime.fromisoformat(start_date)
                    search_status, payload = mailbox.search(
                        None, "SINCE", since_dt.strftime("%d-%b-%Y")
                    )
                except (ValueError, TypeError):
                    search_status, payload = mailbox.search(None, "ALL")
            else:
                search_status, payload = mailbox.search(None, "ALL")

            if search_status != "OK":
                raise ValueError("Unable to search the inbox.")
            message_ids = (payload[0] or b"").split()
            messages: list[TrackerMailboxMessage] = []
            for message_id in message_ids:
                fetch_status, fetched = mailbox.fetch(message_id, "(RFC822)")
                if fetch_status != "OK":
                    continue
                message_bytes = _extract_rfc822_payload(fetched)
                if not message_bytes:
                    continue
                parsed = message_from_bytes(message_bytes, policy=default)
                msg = TrackerMailboxMessage(
                    message_id=_build_message_id(parsed, fallback=str(message_id.decode("ascii", "ignore"))),
                    subject=str(parsed.get("subject") or "").strip(),
                    from_address=parseaddr(str(parsed.get("from") or ""))[1],
                    sent_at=_parse_message_date(str(parsed.get("date") or "")),
                    text=_extract_text_body(parsed),
                )
                if msg.message_id in processed:
                    continue
                messages.append(msg)
            return messages
        except imaplib.IMAP4.error as exc:
            raise ValueError(f"IMAP sync failed: {exc}") from exc
        finally:
            try:
                mailbox.logout()
            except Exception:
                pass


def _process_tracker_messages(
    *,
    application,
    user,
    tracker_items: list[dict[str, Any]],
    messages: list[TrackerMailboxMessage],
    normalized: dict[str, Any],
) -> dict[str, Any]:
    processed_ids = set(normalized.get("processed_message_ids") or [])
    matched_updates: list[dict[str, Any]] = []
    unmatched_messages: list[dict[str, Any]] = []
    detections: list[dict[str, Any]] = []
    skipped_messages = 0
    seen_new_ids: list[str] = []

    for message in sorted(messages, key=lambda item: item.sent_at or ""):
        start_date = str(normalized.get("email_sync_start_date") or "").strip()
        if start_date and not _message_on_or_after_date(message, start_date):
            skipped_messages += 1
            continue
        if message.message_id in processed_ids:
            skipped_messages += 1
            continue
        new_status = _classify_tracker_status(message)
        if not new_status:
            continue
        matched_item = _match_tracker_item(message, tracker_items)
        if not _looks_like_application_email(message, status=new_status, matched_item=matched_item):
            continue
        confidence, evidence = _classify_message_confidence(
            message,
            status=new_status,
            matched_item=matched_item,
        )
        if confidence == "low":
            continue
        seen_new_ids.append(message.message_id)
        detection_payload = {
            "detection_id": f"gmail::{message.message_id}",
            "email_sync_start_date": normalized.get("email_sync_start_date"),
            "message_id": message.message_id,
            "subject": message.subject,
            "from_address": message.from_address,
            "sent_at": message.sent_at,
            "status": new_status,
            "suggested_application_status": normalize_application_status(new_status),
            "confidence": confidence,
            "approval_state": "approved" if matched_item and confidence == "high" else "pending_review",
            "company": str((matched_item or {}).get("company") or ""),
            "title": str((matched_item or {}).get("title") or ""),
            "application_date": message.sent_at,
            "evidence": evidence,
            "metadata": {
                "provider_id": normalized["provider_id"],
                "review_id": str((matched_item or {}).get("review_id") or ""),
                "run_id": str((matched_item or {}).get("run_id") or ""),
                "job_id": str((matched_item or {}).get("job_id") or ""),
            },
        }
        detections.append(normalize_gmail_application_detection(detection_payload))
        if matched_item and confidence != "high":
            unmatched_messages.append(
                {
                    "message_id": message.message_id,
                    "subject": message.subject,
                    "from_address": message.from_address,
                    "status": new_status,
                    "application_status": normalize_application_status(new_status),
                    "confidence": confidence,
                    "evidence": evidence,
                    "sent_at": message.sent_at,
                    "review_id": str(matched_item.get("review_id") or ""),
                    "company": str(matched_item.get("company") or ""),
                    "title": str(matched_item.get("title") or ""),
                }
            )
            continue
        if not matched_item:
            unmatched_messages.append(
                {
                    "message_id": message.message_id,
                    "subject": message.subject,
                    "from_address": message.from_address,
                    "status": new_status,
                    "application_status": normalize_application_status(new_status),
                    "confidence": confidence,
                    "evidence": evidence,
                    "sent_at": message.sent_at,
                }
            )
            continue
        review = application.get_review(str(matched_item["review_id"] or ""))
        previously_actionable = review_is_actionable_tracker_item(review)
        existing_placed_in_tracker_at = review_placed_in_tracker_at(
            review,
            include_legacy_fallback=False,
        )
        review_meta = dict(review.metadata or {})
        current_status = str(review_meta.get("tracker_status") or "not_applied")
        current_application_status = normalize_application_status(
            review_meta.get("application_status") or current_status,
            default="Not applied",
        )
        changed = False

        if new_status == "email_confirmed":
            if not review_meta.get("email_confirmed"):
                review_meta["email_confirmed"] = True
                changed = True
            if current_status in {"", "not_applied", "applied"}:
                review_meta["tracker_status"] = "email_confirmed"
                review_meta["application_status"] = normalize_application_status("email_confirmed")
                changed = changed or current_status != "email_confirmed"
            if not review_meta.get("application_date") and not review_meta.get("applied_at"):
                review_meta["application_date"] = message.sent_at or utc_now_iso()
                changed = True
        elif new_status == "interview_invited":
            if current_status != "rejected":
                review_meta["tracker_status"] = "interview_invited"
                review_meta["application_status"] = normalize_application_status("interview_invited")
                changed = changed or current_status != "interview_invited"
            if not review_meta.get("email_confirmed"):
                review_meta["email_confirmed"] = True
                changed = True
        elif new_status == "rejected":
            review_meta["tracker_status"] = "rejected"
            review_meta["application_status"] = normalize_application_status("rejected")
            changed = changed or current_status != "rejected"
            if not review_meta.get("rejected_at"):
                review_meta["rejected_at"] = message.sent_at or utc_now_iso()
                changed = True
        elif new_status == "offer":
            review_meta["tracker_status"] = "offer"
            review_meta["application_status"] = normalize_application_status("offer")
            changed = changed or current_status != "offer"

        review_meta["tracker_email_sync"] = {
            "message_id": message.message_id,
            "subject": message.subject,
            "from_address": message.from_address,
            "status": new_status,
            "synced_at": utc_now_iso(),
            "provider_id": normalized["provider_id"],
        }
        review.metadata = review_meta
        ensure_review_placed_in_tracker_at(
            review,
            previously_actionable=previously_actionable,
            existing_placed_in_tracker_at=existing_placed_in_tracker_at,
        )
        next_application_status = normalize_application_status(
            review_meta.get("application_status") or review_meta.get("tracker_status"),
            default=current_application_status,
        )
        history_entry = None
        if current_application_status != next_application_status:
            history_entry = {
                "review_id": review.review_id,
                "user_id": str(getattr(user, "user_id", "") or ""),
                "from_status": current_application_status,
                "to_status": next_application_status,
                "source": "gmail_sync",
            }
        application.repositories.review_store.upsert_review(
            review,
            application_status_history=history_entry,
        )
        refreshed_review = application.get_review(review.review_id)
        matched_updates.append(
            {
                "review_id": refreshed_review.review_id,
                "title": str(matched_item.get("title") or ""),
                "company": str(matched_item.get("company") or ""),
                "from_status": current_status,
                "to_status": str(review_meta.get("tracker_status") or current_status),
                "application_status": str(review_meta.get("application_status") or ""),
                "confidence": confidence,
                "evidence": evidence,
                "email_confirmed": bool(review_meta.get("email_confirmed") or False),
                "changed": bool(changed),
                "message_id": message.message_id,
                "subject": message.subject,
                "sent_at": message.sent_at,
            }
        )

    processed_message_ids = list(
        dict.fromkeys([*(normalized.get("processed_message_ids") or []), *seen_new_ids])
    )[-_MAX_PROCESSED_MESSAGE_IDS:]
    summary = {
        "checked_messages": len(messages),
        "processed_messages": len(seen_new_ids),
        "skipped_messages": skipped_messages,
        "matched_messages": len(matched_updates),
        "updated_reviews": sum(1 for item in matched_updates if item["changed"]),
        "unmatched_messages": len(unmatched_messages),
        "detections": len(detections),
        "pending_review": sum(1 for item in detections if item["status"]["approval_state"] == "pending_review"),
    }
    return {
        "summary": summary,
        "matched_updates": matched_updates,
        "unmatched_messages": unmatched_messages[:20],
        "detections": detections[:50],
        "processed_message_ids": processed_message_ids,
        "synced_at": utc_now_iso(),
    }


def _extract_rfc822_payload(fetched: Any) -> bytes:
    for item in fetched or []:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
            return bytes(item[1])
    return b""


def _decode_gmail_raw_payload(raw_payload: str) -> bytes:
    normalized = str(raw_payload or "").strip()
    if not normalized:
        return b""
    try:
        padding = "=" * (-len(normalized) % 4)
        return base64.urlsafe_b64decode(f"{normalized}{padding}")
    except Exception:
        return b""


def _build_message_id(message: Message, *, fallback: str) -> str:
    candidate = str(message.get("message-id") or "").strip().strip("<>")
    if candidate:
        return candidate
    return fallback or f"message-{utc_now_iso()}"


def _parse_message_date(value: str) -> str:
    try:
        parsed = parsedate_to_datetime(value)
        if parsed is None:
            return ""
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""


def _merge_pending_tracker_detections(
    *,
    existing: list[dict[str, Any]],
    additions: list[dict[str, Any]] | None = None,
    remove_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Merge new detections into the pending list, respecting dedup and limits."""
    seen: set[str] = set()
    for detection in existing:
        detection_id = _gmail_detection_key(detection)
        if detection_id:
            seen.add(detection_id)
    if remove_ids:
        seen.difference_update(remove_ids)
        existing = [
            detection
            for detection in existing
            if _gmail_detection_key(detection) not in remove_ids
        ]
    for detection in additions or []:
        detection_id = _gmail_detection_key(detection)
        if not detection_id or detection_id in seen:
            continue
        seen.add(detection_id)
        existing.append(detection)
    existing.sort(key=lambda item: str(item.get("source_email", {}).get("sent_at") or ""), reverse=True)
    deduped: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for detection in existing:
        detection_id = _gmail_detection_key(detection)
        if not detection_id or detection_id in seen_ids:
            continue
        seen_ids.add(detection_id)
        deduped.append(detection)
    return deduped[:_MAX_PENDING_REVIEW_DETECTIONS]


def _normalized_text(value: str) -> str:
    return re.sub(r"[\W_]+", " ", str(value or "").casefold()).strip()


def _classify_tracker_status(message: TrackerMailboxMessage) -> str:
    searchable = _normalized_text(f"{message.subject} {message.text}")
    if any(pattern in searchable for pattern in (_normalized_text(item) for item in _OFFER_PATTERNS)):
        return "offer"
    if any(pattern in searchable for pattern in (_normalized_text(item) for item in _REJECTION_PATTERNS)):
        return "rejected"
    if any(pattern in searchable for pattern in (_normalized_text(item) for item in _INTERVIEW_PATTERNS)):
        return "interview_invited"
    if any(pattern in searchable for pattern in (_normalized_text(item) for item in _CONFIRMATION_PATTERNS)):
        return "email_confirmed"
    return ""


def _collect_message_evidence(
    message: TrackerMailboxMessage,
    *,
    status: str,
    matched_item: Mapping[str, Any] | None = None,
) -> tuple[list[str], list[str], bool]:
    searchable = _normalized_text(f"{message.subject} {message.text}")
    sender_domain = message.from_address.split("@")[-1].casefold()
    sender_address = message.from_address.casefold()
    evidence: list[str] = []
    signal_hits = [
        pattern
        for pattern in _APPLICATION_SIGNAL_PATTERNS
        if _normalized_text(pattern) in searchable
    ]
    if signal_hits:
        evidence.append("application wording")
    has_recruiting_sender = any(hint in sender_domain or hint in sender_address for hint in _ATS_OR_RECRUITING_DOMAIN_HINTS)
    if has_recruiting_sender:
        evidence.append("recruiting sender")
    if matched_item:
        evidence.append("tracker match")
    if status in {"email_confirmed", "interview_invited", "rejected", "offer"}:
        evidence.append(f"{normalize_application_status(status)} status signal")
    return list(dict.fromkeys(evidence)), signal_hits, has_recruiting_sender


def _looks_like_application_email(
    message: TrackerMailboxMessage,
    *,
    status: str,
    matched_item: Mapping[str, Any] | None = None,
) -> bool:
    evidence, signal_hits, has_recruiting_sender = _collect_message_evidence(
        message,
        status=status,
        matched_item=matched_item,
    )
    has_application_context = bool(has_recruiting_sender or signal_hits or matched_item)
    if not has_application_context:
        return False
    if status == "offer" and not (has_recruiting_sender or matched_item):
        return False
    if status == "rejected" and not (has_recruiting_sender or signal_hits or matched_item):
        return False
    return any(item.endswith("status signal") for item in evidence)


def _classify_message_confidence(
    message: TrackerMailboxMessage,
    *,
    status: str,
    matched_item: Mapping[str, Any] | None = None,
) -> tuple[str, list[str]]:
    evidence, signal_hits, has_recruiting_sender = _collect_message_evidence(
        message,
        status=status,
        matched_item=matched_item,
    )
    has_status_signal = any(item.endswith("status signal") for item in evidence)
    has_tracker_match = "tracker match" in evidence
    if has_status_signal and (has_recruiting_sender or len(signal_hits) >= 2 or (has_tracker_match and signal_hits)):
        return "high", evidence
    if has_status_signal and (has_recruiting_sender or bool(signal_hits) or has_tracker_match):
        return "medium", evidence
    return "low", evidence


def _token_overlap_score(target: str, searchable_tokens: set[str], *, min_length: int) -> int:
    score = 0
    for token in target.split():
        if len(token) >= min_length and token in searchable_tokens:
            score += 1
    return score


def _match_tracker_item(
    message: TrackerMailboxMessage,
    tracker_items: list[dict[str, Any]],
) -> dict[str, Any] | None:
    searchable = _normalized_text(f"{message.subject} {message.text} {message.from_address}")
    searchable_tokens = set(searchable.split())
    sender_domain = message.from_address.split("@")[-1].casefold()
    scored: list[tuple[int, dict[str, Any]]] = []

    for item in tracker_items:
        company = _normalized_text(str(item.get("company") or ""))
        title = _normalized_text(str(item.get("title") or ""))
        score = 0

        if company and company in searchable:
            score += 8
        else:
            score += min(4, _token_overlap_score(company, searchable_tokens, min_length=4))

        if title and title in searchable:
            score += 5
        else:
            score += min(3, _token_overlap_score(title, searchable_tokens, min_length=5))

        if company and any(token and token in sender_domain for token in company.split() if len(token) >= 4):
            score += 2

        if score > 0:
            scored.append((score, item))

    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_item = scored[0]
    if best_score < 6:
        return None
    if len(scored) > 1 and scored[1][0] == best_score:
        return None
    return best_item