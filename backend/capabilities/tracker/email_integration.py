from __future__ import annotations

import base64
import html
import imaplib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
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
from backend.domain.models import utc_now_iso, utc_plus_seconds

TRACKER_EMAIL_INTEGRATION_METADATA_KEY = "tracker_email_integration"

_MAX_PROCESSED_MESSAGE_IDS = 250


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
    "unfortunately",
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


def tracker_email_provider_options() -> list[dict[str, Any]]:
    return [preset.to_dict() for preset in TRACKER_EMAIL_PROVIDER_PRESETS.values()]


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
    try:
        max_messages = max(1, min(100, int(raw.get("max_messages") or 40)))
    except (TypeError, ValueError):
        max_messages = 40
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
        "max_messages": max_messages,
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
        "max_messages": config["max_messages"],
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
    del user
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
    messages = client.fetch_recent_messages(limit=int(normalized["max_messages"]))
    return _process_tracker_messages(
        application=application,
        tracker_items=tracker_items,
        messages=messages,
        normalized=normalized,
    )


def sync_tracker_gmail(
    *,
    application,
    user,
    tracker_items: list[dict[str, Any]],
    config: Mapping[str, Any],
    access_token: str,
) -> dict[str, Any]:
    del user
    normalized = normalize_tracker_email_config(config)
    if normalized["auth_strategy"] != "google_oauth":
        raise ValueError("This inbox is not configured for Google OAuth.")
    if not access_token:
        raise ValueError("A Google access token is required before syncing Gmail.")
    client = GmailMailboxClient(access_token=access_token)
    messages, history_id = client.fetch_recent_messages(limit=int(normalized["max_messages"]))
    result = _process_tracker_messages(
        application=application,
        tracker_items=tracker_items,
        messages=messages,
        normalized=normalized,
    )
    result["history_id"] = history_id
    return result


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

    def fetch_recent_messages(self, *, limit: int) -> list[TrackerMailboxMessage]:
        mailbox = imaplib.IMAP4_SSL(self.host, self.port)
        try:
            mailbox.login(self.email_address, self.password)
            status, _ = mailbox.select(self.folder, readonly=True)
            if status != "OK":
                raise ValueError(f"Unable to open folder '{self.folder}'.")
            search_status, payload = mailbox.search(None, "ALL")
            if search_status != "OK":
                raise ValueError("Unable to search the inbox.")
            message_ids = (payload[0] or b"").split()
            selected_ids = message_ids[-max(1, int(limit)) :]
            messages: list[TrackerMailboxMessage] = []
            for message_id in selected_ids:
                fetch_status, fetched = mailbox.fetch(message_id, "(RFC822)")
                if fetch_status != "OK":
                    continue
                message_bytes = _extract_rfc822_payload(fetched)
                if not message_bytes:
                    continue
                parsed = message_from_bytes(message_bytes, policy=default)
                messages.append(
                    TrackerMailboxMessage(
                        message_id=_build_message_id(parsed, fallback=str(message_id.decode("ascii", "ignore"))),
                        subject=str(parsed.get("subject") or "").strip(),
                        from_address=parseaddr(str(parsed.get("from") or ""))[1],
                        sent_at=_parse_message_date(str(parsed.get("date") or "")),
                        text=_extract_text_body(parsed),
                    )
                )
            return messages
        except imaplib.IMAP4.error as exc:
            raise ValueError(f"IMAP sync failed: {exc}") from exc
        finally:
            try:
                mailbox.logout()
            except Exception:
                pass


class GmailMailboxClient:
    def __init__(self, *, access_token: str) -> None:
        self.access_token = str(access_token or "").strip()

    def fetch_recent_messages(self, *, limit: int) -> tuple[list[TrackerMailboxMessage], str]:
        listing = list_google_gmail_messages(access_token=self.access_token, limit=limit)
        message_refs = listing.get("messages") or []
        messages: list[TrackerMailboxMessage] = []
        latest_history_id = ""
        for item in message_refs:
            if not isinstance(item, Mapping):
                continue
            message_id = str(item.get("id") or "").strip()
            if not message_id:
                continue
            raw_message = get_google_gmail_message(access_token=self.access_token, message_id=message_id)
            message_bytes = _decode_gmail_raw_payload(str(raw_message.get("raw") or ""))
            if not message_bytes:
                continue
            parsed = message_from_bytes(message_bytes, policy=default)
            messages.append(
                TrackerMailboxMessage(
                    message_id=_build_message_id(parsed, fallback=message_id),
                    subject=str(parsed.get("subject") or "").strip(),
                    from_address=parseaddr(str(parsed.get("from") or ""))[1],
                    sent_at=_parse_message_date(str(parsed.get("date") or "")),
                    text=_extract_text_body(parsed),
                )
            )
            latest_history_id = str(raw_message.get("historyId") or latest_history_id or "").strip()
        return messages, latest_history_id


def _process_tracker_messages(
    *,
    application,
    tracker_items: list[dict[str, Any]],
    messages: list[TrackerMailboxMessage],
    normalized: dict[str, Any],
) -> dict[str, Any]:
    processed_ids = set(normalized.get("processed_message_ids") or [])
    matched_updates: list[dict[str, Any]] = []
    unmatched_messages: list[dict[str, Any]] = []
    skipped_messages = 0
    seen_new_ids: list[str] = []

    for message in sorted(messages, key=lambda item: item.sent_at or ""):
        if message.message_id in processed_ids:
            skipped_messages += 1
            continue
        new_status = _classify_tracker_status(message)
        if not new_status:
            continue
        seen_new_ids.append(message.message_id)
        matched_item = _match_tracker_item(message, tracker_items)
        if not matched_item:
            unmatched_messages.append(
                {
                    "message_id": message.message_id,
                    "subject": message.subject,
                    "from_address": message.from_address,
                    "status": new_status,
                    "sent_at": message.sent_at,
                }
            )
            continue
        review = application.get_review(str(matched_item["review_id"] or ""))
        review_meta = dict(review.metadata or {})
        current_status = str(review_meta.get("tracker_status") or "applied")
        changed = False

        if new_status == "email_confirmed":
            if not review_meta.get("email_confirmed"):
                review_meta["email_confirmed"] = True
                changed = True
            if current_status in {"", "applied"}:
                review_meta["tracker_status"] = "email_confirmed"
                changed = changed or current_status != "email_confirmed"
        elif new_status == "interview_invited":
            if current_status != "rejected":
                review_meta["tracker_status"] = "interview_invited"
                changed = changed or current_status != "interview_invited"
            if not review_meta.get("email_confirmed"):
                review_meta["email_confirmed"] = True
                changed = True
        elif new_status == "rejected":
            review_meta["tracker_status"] = "rejected"
            changed = changed or current_status != "rejected"
            if not review_meta.get("rejected_at"):
                review_meta["rejected_at"] = message.sent_at or utc_now_iso()
                changed = True

        review_meta["tracker_email_sync"] = {
            "message_id": message.message_id,
            "subject": message.subject,
            "from_address": message.from_address,
            "status": new_status,
            "synced_at": utc_now_iso(),
            "provider_id": normalized["provider_id"],
        }
        review.metadata = review_meta
        application.repositories.review_store.upsert_review(review)
        refreshed_review = application.get_review(review.review_id)
        matched_updates.append(
            {
                "review_id": refreshed_review.review_id,
                "title": str(matched_item.get("title") or ""),
                "company": str(matched_item.get("company") or ""),
                "from_status": current_status,
                "to_status": str(review_meta.get("tracker_status") or current_status),
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
    }
    return {
        "summary": summary,
        "matched_updates": matched_updates,
        "unmatched_messages": unmatched_messages[:20],
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


def _extract_text_body(message: Message) -> str:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_disposition() == "attachment":
                continue
            content_type = part.get_content_type()
            try:
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="ignore")
            except Exception:
                continue
            if content_type == "text/plain":
                plain_parts.append(text)
            elif content_type == "text/html":
                html_parts.append(text)
    else:
        content_type = message.get_content_type()
        try:
            payload = message.get_payload(decode=True) or b""
            charset = message.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="ignore")
        except Exception:
            text = ""
        if content_type == "text/plain":
            plain_parts.append(text)
        elif content_type == "text/html":
            html_parts.append(text)
    body = "\n".join(part for part in plain_parts if part.strip())
    if body.strip():
        return body
    return _html_to_text("\n".join(part for part in html_parts if part.strip()))


def _html_to_text(value: str) -> str:
    without_breaks = re.sub(r"(?i)<br\s*/?>", "\n", value)
    without_blocks = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", without_breaks)
    without_tags = re.sub(r"<[^>]+>", " ", without_blocks)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def _normalized_text(value: str) -> str:
    return re.sub(r"[\W_]+", " ", str(value or "").casefold()).strip()


def _classify_tracker_status(message: TrackerMailboxMessage) -> str:
    searchable = _normalized_text(f"{message.subject} {message.text}")
    if any(pattern in searchable for pattern in (_normalized_text(item) for item in _REJECTION_PATTERNS)):
        return "rejected"
    if any(pattern in searchable for pattern in (_normalized_text(item) for item in _INTERVIEW_PATTERNS)):
        return "interview_invited"
    if any(pattern in searchable for pattern in (_normalized_text(item) for item in _CONFIRMATION_PATTERNS)):
        return "email_confirmed"
    return ""


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
