"""CP-042R: Deterministic provider fixtures for browser-level tests.

Provides fixture endpoints that a Playwright test can control to simulate
the complete Career Evidence journey with deterministic responses.
"""

from __future__ import annotations

import time
from http import HTTPStatus
from typing import Any

from backend.api.routes.registry import ApiRouteContext, RouteRegistry


_fixture_state: dict[str, dict[str, Any]] = {}
_FIXTURE_STATE_TTL = 600


def _session_key(context: ApiRouteContext) -> str:
    user, _ = context.require_identity()
    return getattr(user, "user_id", "unknown")


def _get_fixture(session_key: str) -> dict[str, Any]:
    now = time.monotonic()
    entry = _fixture_state.get(session_key)
    if entry and (now - entry.get("_created", 0)) < _FIXTURE_STATE_TTL:
        return entry
    return {
        "_created": now,
        "mode": "happy_path",
        "fail_at": None,
        "fail_count": 0,
        "documents": [
            {
                "document_id": "fixture_cv_001",
                "asset_id": "fixture_cv_001",
                "display_name": "test_cv.pdf",
                "source_origin": "upload",
                "status": "ready",
                "kind": "uploaded_document",
                "created_at": "2026-01-01T00:00:00Z",
            }
        ],
        "selected_source_ids": ["fixture_cv_001"],
        "evidence_items": [],
        "processing_state": None,
        "experience_links": [],
        "pending_questions": [],
        "review_cursor": 0,
    }


def _save_fixture(session_key: str, data: dict[str, Any]) -> None:
    data["_created"] = time.monotonic()
    _fixture_state[session_key] = data


def _should_fail(entry: dict[str, Any], stage: str) -> bool:
    fail_at = entry.get("fail_at")
    if fail_at and fail_at == stage:
        entry["fail_count"] = entry.get("fail_count", 0) + 1
        return True
    return False


def _inject_failure(context: ApiRouteContext, entry: dict[str, Any]) -> bool | None:
    mode = entry.get("mode", "")
    if mode == "timeout_fixture":
        import time as _time
        _time.sleep(5)
        context.send_error(HTTPStatus.GATEWAY_TIMEOUT, "fixture_timeout",
                           "Simulated gateway timeout for testing.")
        return True
    elif mode == "error_fixture":
        context.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "fixture_error",
                           "Simulated internal server error for testing.")
        return True
    elif mode == "retry_fixture":
        fail_count = entry.get("fail_count", 0)
        if fail_count <= 2:
            context.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "fixture_retry",
                               f"Simulated transient error (attempt {fail_count}).")
        else:
            entry["fail_at"] = None
            context.send_json({"documents": entry.get("documents", [])},
                            status=HTTPStatus.OK)
        return True
    return False


# ── Route registration ───────────────────────────────────────────────────

def register_routes(registry: RouteRegistry) -> None:
    """Register CP-042R fixture control endpoints."""
    registry.prefix(
        "POST", ("fixtures", "career-evidence", "reset"),
        _handle_reset, auth_required=True,
        name="career_evidence_fixture.reset",
    )
    registry.prefix(
        "POST", ("fixtures", "career-evidence", "configure"),
        _handle_configure, auth_required=True,
        name="career_evidence_fixture.configure",
    )
    registry.prefix(
        "GET", ("fixtures", "career-evidence", "state"),
        _handle_get_state, auth_required=True,
        name="career_evidence_fixture.state",
    )
    registry.prefix(
        "GET", ("fixtures", "career-evidence", "documents"),
        _handle_documents, auth_required=True,
        name="career_evidence_fixture.documents",
    )


def _handle_reset(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if segments != ["fixtures", "career-evidence", "reset"]:
        return False
    sk = _session_key(context)
    payload = context.read_json_body() or {}
    mode = str(payload.get("mode") or "happy_path")
    _save_fixture(sk, {
        "_created": time.monotonic(),
        "mode": mode,
        "fail_at": payload.get("fail_at"),
        "fail_count": 0,
        "documents": [
            {
                "document_id": "fixture_cv_001",
                "asset_id": "fixture_cv_001",
                "display_name": "test_cv.pdf",
                "source_origin": "upload",
                "status": "ready",
                "kind": "uploaded_document",
                "created_at": "2026-01-01T00:00:00Z",
            }
        ],
        "selected_source_ids": ["fixture_cv_001"],
        "evidence_items": [],
        "processing_state": None,
        "experience_links": [],
        "pending_questions": [],
        "review_cursor": 0,
    })
    context.send_json({"reset": True, "mode": mode}, status=HTTPStatus.OK)
    return True


def _handle_configure(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if segments != ["fixtures", "career-evidence", "configure"]:
        return False
    sk = _session_key(context)
    entry = _get_fixture(sk)
    payload = context.read_json_body() or {}
    for key in ("mode", "fail_at", "documents", "selected_source_ids",
                "evidence_items", "processing_state", "experience_links",
                "pending_questions"):
        if key in payload:
            entry[key] = payload[key]
    _save_fixture(sk, entry)
    context.send_json({"configured": True}, status=HTTPStatus.OK)
    return True


def _handle_get_state(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if segments != ["fixtures", "career-evidence", "state"]:
        return False
    sk = _session_key(context)
    entry = _get_fixture(sk)
    context.send_json({
        "mode": entry.get("mode"),
        "fail_at": entry.get("fail_at"),
        "fail_count": entry.get("fail_count", 0),
        "document_count": len(entry.get("documents", [])),
        "selected_source_count": len(entry.get("selected_source_ids", [])),
        "evidence_count": len(entry.get("evidence_items", [])),
    }, status=HTTPStatus.OK)
    return True


def _handle_documents(context: ApiRouteContext) -> bool | None:
    segments = list(context.segments)
    if segments != ["fixtures", "career-evidence", "documents"]:
        return False
    sk = _session_key(context)
    entry = _get_fixture(sk)
    if _should_fail(entry, "documents"):
        return _inject_failure(context, entry)
    context.send_json({
        "documents": entry.get("documents", []),
    }, status=HTTPStatus.OK)
    return True
