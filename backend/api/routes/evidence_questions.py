"""Evidence question API routes (CP-033R).

REST endpoints for the evidence question lifecycle:
- GET  /evidence-items/questions              → get next question
- POST /evidence-items/questions/{qid}/answer → answer a question
- POST /evidence-items/questions/{qid}/skip   → skip a question
- POST /evidence-items/questions/{qid}/dismiss → dismiss a question
- POST /evidence-items/questions/recalculate   → reset and recompute after edits
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.evidence.question_service import (
    answer_question,
    dismiss_question,
    list_question_history,
    recalculate_questions,
    select_next_question,
    skip_question,
)


def register_routes(registry: RouteRegistry) -> None:
    registry.prefix(
        "GET", ("evidence-items", "questions"),
        _handle_get_question, auth_required=True, name="evidence_questions.get",
    )
    registry.prefix(
        "POST", ("evidence-items", "questions", "{question_id}", "answer"),
        _handle_answer, auth_required=True, name="evidence_questions.answer",
    )
    registry.prefix(
        "POST", ("evidence-items", "questions", "{question_id}", "skip"),
        _handle_skip, auth_required=True, name="evidence_questions.skip",
    )
    registry.prefix(
        "POST", ("evidence-items", "questions", "{question_id}", "dismiss"),
        _handle_dismiss, auth_required=True, name="evidence_questions.dismiss",
    )
    registry.prefix(
        "POST", ("evidence-items", "questions", "recalculate"),
        _handle_recalculate, auth_required=True, name="evidence_questions.recalculate",
    )
    registry.prefix(
        "GET", ("evidence-items", "questions", "history"),
        _handle_history, auth_required=True, name="evidence_questions.history",
    )


def _handle_get_question(context: ApiRouteContext) -> dict[str, Any] | None:
    """GET /evidence-items/questions — return the next highest-value question."""
    user, _ = context.require_identity()
    result = select_next_question(user)
    _persist_user(context, user)
    return result


def _handle_answer(context: ApiRouteContext) -> dict[str, Any] | None:
    """POST /evidence-items/questions/{question_id}/answer — record an answer."""
    user, _ = context.require_identity()
    question_id = str(context.segment_params.get("question_id") or "")
    if not question_id:
        context.send_error(HTTPStatus.BAD_REQUEST, "bad_request",
                           "question_id is required.")
        return None
    payload = context.read_json_body()
    result = answer_question(user, question_id, payload)
    _persist_user(context, user)
    return result


def _handle_skip(context: ApiRouteContext) -> dict[str, Any] | None:
    """POST /evidence-items/questions/{question_id}/skip — skip a question."""
    user, _ = context.require_identity()
    question_id = str(context.segment_params.get("question_id") or "")
    if not question_id:
        context.send_error(HTTPStatus.BAD_REQUEST, "bad_request",
                           "question_id is required.")
        return None
    result = skip_question(user, question_id)
    _persist_user(context, user)
    return result


def _handle_dismiss(context: ApiRouteContext) -> dict[str, Any] | None:
    """POST /evidence-items/questions/{question_id}/dismiss — dismiss a question."""
    user, _ = context.require_identity()
    question_id = str(context.segment_params.get("question_id") or "")
    if not question_id:
        context.send_error(HTTPStatus.BAD_REQUEST, "bad_request",
                           "question_id is required.")
        return None
    result = dismiss_question(user, question_id)
    _persist_user(context, user)
    return result


def _handle_recalculate(context: ApiRouteContext) -> dict[str, Any] | None:
    """POST /evidence-items/questions/recalculate — reset history and recompute."""
    user, _ = context.require_identity()
    result = recalculate_questions(user)
    _persist_user(context, user)
    return result


def _handle_history(context: ApiRouteContext) -> dict[str, Any] | None:
    """GET /evidence-items/questions/history — list all question history."""
    user, _ = context.require_identity()
    history = list_question_history(user)
    return {"history": history, "total": len(history)}


def _persist_user(context: ApiRouteContext, user) -> None:
    """Persist user changes back to the repository."""
    from datetime import datetime, timezone
    user.updated_at = datetime.now(timezone.utc).isoformat()
    context.application.repositories.auth_repository.upsert_user(user)
