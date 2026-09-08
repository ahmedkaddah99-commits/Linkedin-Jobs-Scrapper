from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from typing import Any


CUSTOMER_TASK_EMAIL_SYNC = "tracker_email_sync"
CUSTOMER_TASK_BULK_EXPORT = "bulk_document_export"
CUSTOMER_TASK_TYPES = frozenset({CUSTOMER_TASK_EMAIL_SYNC, CUSTOMER_TASK_BULK_EXPORT})


def customer_tasks_async_enabled() -> bool:
    """Return the explicit rollout flag, defaulting on only in production."""

    raw = str(os.getenv("RUNR_CUSTOMER_TASKS_ASYNC") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return str(os.getenv("RUNR_ENV") or "").strip().lower() in {"prod", "production"}


def customer_task_idempotency_key(*, user_id: str, task_type: str, payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        {"user_id": str(user_id), "task_type": str(task_type), "payload": dict(payload)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return f"{task_type}:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def customer_task_status_url(task_type: str, task_id: str) -> str:
    if task_type == CUSTOMER_TASK_EMAIL_SYNC:
        return f"/tracker/email-integration/sync/{task_id}"
    if task_type == CUSTOMER_TASK_BULK_EXPORT:
        return f"/documents/bulk-exports/{task_id}/status"
    return f"/customer-tasks/{task_id}"


def public_customer_task(task: Mapping[str, Any]) -> dict[str, Any]:
    """Remove ownership/lease internals and local filesystem paths from API payloads."""

    result = dict(task)
    for key in ("user_id", "lease_owner", "lease_token", "lease_expires_at"):
        result.pop(key, None)
    result["status_url"] = customer_task_status_url(
        str(result.get("task_type") or ""), str(result.get("task_id") or "")
    )
    task_result = dict(result.get("result") or {})
    bundle = task_result.get("bundle")
    if isinstance(bundle, Mapping):
        safe_bundle = dict(bundle)
        safe_bundle.pop("path", None)
        task_result["bundle"] = safe_bundle
    result["result"] = task_result
    return result


def execute_customer_task(application, task: Mapping[str, Any]) -> dict[str, Any]:
    task_type = str(task.get("task_type") or "").strip()
    if task_type == CUSTOMER_TASK_BULK_EXPORT:
        return _execute_bulk_export(application, task)
    if task_type == CUSTOMER_TASK_EMAIL_SYNC:
        return _execute_email_sync(application, task)
    raise ValueError(f"Unsupported customer task type: {task_type or 'missing'}")


def _execute_bulk_export(application, task: Mapping[str, Any]) -> dict[str, Any]:
    # Importing the API helper lazily keeps the application/worker layer free
    # of an API-server import cycle. The helper already enforces the same
    # document ownership and export-gate rules used by the synchronous route.
    from backend.api.server import _create_bulk_export_bundle

    user = application.get_user(str(task.get("user_id") or ""))
    payload = dict(task.get("payload") or {})
    bundle = _create_bulk_export_bundle(
        application,
        user,
        [str(item) for item in payload.get("document_ids") or [] if str(item).strip()],
        label=str(payload.get("label") or ""),
        export_anyway=bool(payload.get("export_anyway")),
    )
    return {"operation": "bulk_export", "bundle": bundle}


def _execute_email_sync(application, task: Mapping[str, Any]) -> dict[str, Any]:
    # These helpers are the existing provider/token/lifecycle implementation;
    # this boundary changes only when and by whom it runs.
    from backend.api.server import (
        _collect_tracker_entries,
        _get_tracker_email_config,
        _merge_pending_tracker_detections,
        _persist_tracker_email_config,
        _resolve_tracker_email_access_token,
        _resolve_tracker_email_password,
        _resolve_tracker_email_refresh_token,
        _upsert_tracker_email_access_token_secret,
    )
    from backend.capabilities.tracker import normalize_tracker_email_config, sync_tracker_email, sync_tracker_gmail
    from backend.capabilities.tracker.google_oauth import refresh_google_tracker_access_token
    from backend.capabilities.tracker.email_integration import normalize_gmail_scan_window
    from datetime import datetime, timezone

    user = application.get_user(str(task.get("user_id") or ""))
    payload = dict(task.get("payload") or {})
    current_config = _get_tracker_email_config(user)
    if payload.get("scan_window") is not None:
        current_config["scan_window"] = normalize_gmail_scan_window(payload.get("scan_window"))
    if payload.get("max_messages") is not None:
        current_config["max_messages"] = payload.get("max_messages")
    current_config = normalize_tracker_email_config(current_config)
    tracker_items = _collect_tracker_entries(application, user)
    try:
        updated_config = dict(current_config)
        if str(current_config.get("auth_strategy") or "") == "google_oauth":
            refresh_token = _resolve_tracker_email_refresh_token(application, current_config)
            access_token = _resolve_tracker_email_access_token(application, current_config)
            if refresh_token:
                token_payload = refresh_google_tracker_access_token(refresh_token=refresh_token)
                access_token = str(token_payload.get("access_token") or "").strip()
                if not access_token:
                    raise ValueError("Google did not return an access token during refresh.")
                updated_config["access_token_secret_id"] = _upsert_tracker_email_access_token_secret(
                    application, user, updated_config, access_token
                )
                updated_config["access_token_expires_at"] = _utc_plus_seconds(
                    int(token_payload.get("expires_in") or 3600)
                )
            result = sync_tracker_gmail(
                application=application,
                user=user,
                tracker_items=tracker_items,
                config=updated_config,
                access_token=access_token,
            )
        else:
            password = _resolve_tracker_email_password(application, current_config)
            result = sync_tracker_email(
                application=application,
                user=user,
                tracker_items=tracker_items,
                config=current_config,
                password=password,
            )
    except ValueError as exc:
        failed_config = dict(current_config)
        error_text = str(exc)
        failed_config["last_error"] = error_text
        if "invalid_grant" in error_text.lower() or "expired or revoked" in error_text.lower():
            failed_config["connected"] = False
            failed_config["authorization_state"] = "reauthorization_required"
        failed_config["updated_at"] = datetime.now(timezone.utc).isoformat()
        _persist_tracker_email_config(application, user, failed_config)
        raise

    updated_config["processed_message_ids"] = result["processed_message_ids"]
    updated_config["last_sync_at"] = result["synced_at"]
    updated_config["updated_at"] = result["synced_at"]
    updated_config["last_error"] = ""
    updated_config["last_sync_summary"] = dict(result["summary"] or {})
    updated_config["pending_detections"] = _merge_pending_tracker_detections(
        existing=current_config.get("pending_detections") or [],
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
    refreshed_user = _persist_tracker_email_config(application, user, updated_config)
    from backend.api.server import _tracker_email_integration_payload

    return {
        "operation": "tracker_email_sync",
        "integration": _tracker_email_integration_payload(application, refreshed_user),
        "result": result,
    }


def _utc_plus_seconds(seconds: int) -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) + timedelta(seconds=max(0, int(seconds)))).isoformat()
