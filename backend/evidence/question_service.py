"""Evidence question service (CP-033R).

Selects the highest-value missing detail for a specific canonical evidence item
and persists non-repeating question history so that asked, answered, skipped,
and dismissed states survive reloads.

Every question carries a stable question_id derived from the target evidence_id
and the missing-detail type, so the same question is never generated twice.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping

from backend.domain.candidate_evidence import (
    CandidateEvidence,
    EVIDENCE_TYPE_ACHIEVEMENT,
    EVIDENCE_TYPE_METRIC,
    EVIDENCE_TYPE_TOOL,
    EVIDENCE_TYPE_STAKEHOLDER,
)

# ── Question states ──────────────────────────────────────────────────

QUESTION_STATE_ASKED = "asked"
QUESTION_STATE_ANSWERED = "answered"
QUESTION_STATE_SKIPPED = "skipped"
QUESTION_STATE_DISMISSED = "dismissed"

QUESTION_STATES_FINAL = {QUESTION_STATE_ANSWERED, QUESTION_STATE_SKIPPED, QUESTION_STATE_DISMISSED}

# ── Missing-detail types ─────────────────────────────────────────────

MISSING_OUTCOME = "missing_outcome"
MISSING_METRIC = "missing_metric"
MISSING_TOOL = "missing_tool"
MISSING_SCOPE = "missing_scope"
MISSING_STAKEHOLDER = "missing_stakeholder"
MISSING_DATE = "missing_date"
MISSING_MAPPING = "missing_mapping"

ALL_MISSING_TYPES = [
    MISSING_OUTCOME,
    MISSING_METRIC,
    MISSING_TOOL,
    MISSING_SCOPE,
    MISSING_STAKEHOLDER,
    MISSING_DATE,
    MISSING_MAPPING,
]

# ── Priority scoring ─────────────────────────────────────────────────
_MISSING_TYPE_PRIORITY: dict[str, int] = {
    MISSING_OUTCOME: 100,
    MISSING_METRIC: 95,
    MISSING_TOOL: 90,
    MISSING_SCOPE: 70,
    MISSING_STAKEHOLDER: 65,
    MISSING_DATE: 60,
    MISSING_MAPPING: 50,
}

# ── Metadata key ─────────────────────────────────────────────────────
_QUESTION_HISTORY_KEY = "evidence_question_history"


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_history(user_metadata: dict | None) -> list[dict[str, Any]]:
    if not user_metadata:
        return []
    raw = user_metadata.get(_QUESTION_HISTORY_KEY)
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    return []


def _write_history(user_metadata: dict, history: list[dict[str, Any]]) -> None:
    user_metadata[_QUESTION_HISTORY_KEY] = list(history)


def _read_evidence(user) -> list[CandidateEvidence]:
    """Read canonical evidence items from user metadata."""
    metadata = dict(user.metadata or {})
    raw = list(metadata.get("candidate_evidence") or [])
    return [CandidateEvidence.from_dict(item) for item in raw if isinstance(item, dict)]


# ---------------------------------------------------------------------------
# Stable question-id generation
# ---------------------------------------------------------------------------


def _make_question_id(evidence_id: str, missing_type: str) -> str:
    """Generate a deterministic, stable question_id from evidence_id + missing_type."""
    raw = f"{evidence_id}:{missing_type}"
    return f"q_{sha256(raw.encode('utf-8')).hexdigest()[:16]}"


# ---------------------------------------------------------------------------
# Missing-detail detection
# ---------------------------------------------------------------------------


def _detect_missing_details(ev: CandidateEvidence) -> list[str]:
    """Return the list of missing-detail types for a single evidence item."""
    missing: list[str] = []
    text_lower = ev.text.lower() if ev.text else ""
    evidence_type = ev.evidence_type or ""

    # ── Missing metric ──
    has_number = bool(re.search(
        r"(?<!\w)(?:[$€£]\s*)?\d+(?:[.,]\d+)?(?:\s*%|\s*(?:hours?|days?|weeks?|months?|years?))?",
        text_lower, re.I,
    ))
    if evidence_type != EVIDENCE_TYPE_METRIC and not has_number:
        missing.append(MISSING_METRIC)

    # ── Missing outcome ──
    outcome_terms = (
        "improved", "reduced", "increased", "delivered", "achieved", "saved",
        "grew", "accelerated", "decreased", "boosted", "optimised",
        "optimized", "streamlined", "automated", "launched", "led",
        "transformed", "generated", "exceeded",
    )
    first_word = text_lower.split()[0] if text_lower.split() else ""
    has_outcome = first_word in outcome_terms or evidence_type == EVIDENCE_TYPE_ACHIEVEMENT or any(
        term in text_lower.split() for term in outcome_terms
    )
    if not has_outcome and not has_number:
        missing.append(MISSING_OUTCOME)

    # ── Missing tool ──
    tool_terms = (
        "python", "sql", "excel", "power bi", "tableau", "sap", "jira",
        "salesforce", "docker", "kubernetes", "aws", "azure", "gcp",
        "terraform", "jenkins", "git", "react", "angular", "vue",
        "node", "django", "flask", "spring", "spark", "kafka",
        "airflow", "snowflake", "databricks", "figma",
    )
    has_tool = any(t in text_lower for t in tool_terms) or evidence_type == EVIDENCE_TYPE_TOOL
    if not has_tool:
        missing.append(MISSING_TOOL)

    # ── Missing scope ──
    scope_indicators = (
        "team", "department", "organization", "company", "division",
        "cross-functional", "global", "regional", "enterprise",
        "platform", "product", "service", "initiative",
    )
    has_scope = any(ind in text_lower for ind in scope_indicators)
    if not has_scope:
        missing.append(MISSING_SCOPE)

    # ── Missing stakeholder ──
    stakeholder_terms = (
        "stakeholder", "customer", "client", "manager", "leadership",
        "team", "partner", "executive", "director", "vendor",
    )
    has_stakeholder = any(t in text_lower for t in stakeholder_terms) or evidence_type == EVIDENCE_TYPE_STAKEHOLDER
    if not has_stakeholder:
        missing.append(MISSING_STAKEHOLDER)

    # ── Missing date ──
    has_date = bool(ev.dates) or bool(re.search(r"(19|20)\d{2}", text_lower))
    if not has_date:
        missing.append(MISSING_DATE)

    # ── Missing mapping ──
    mapping = ev.experience_mapping or {}
    has_company = bool((mapping.get("company") or "").strip())
    has_role = bool((mapping.get("role") or "").strip())
    has_project = bool((mapping.get("project") or "").strip())
    if not has_company or not has_role or not has_project:
        missing.append(MISSING_MAPPING)

    return missing


# ---------------------------------------------------------------------------
# Question text generation
# ---------------------------------------------------------------------------


def _question_text(ev: CandidateEvidence, missing_type: str) -> str:
    """Generate a human-readable question for a specific missing detail."""
    snippet = ev.text[:80].strip() if ev.text else "this evidence item"
    if snippet and len(ev.text) > 80:
        snippet += "\u2026"

    label = _item_label(ev)

    templates: dict[str, str] = {
        MISSING_OUTCOME: f'What concrete outcome resulted from "{snippet}" at {label}?',
        MISSING_METRIC: f'What measurable result (number, percentage, time) did "{snippet}" achieve at {label}?',
        MISSING_TOOL: f'Which tool, system, or method was central to "{snippet}" at {label}?',
        MISSING_SCOPE: f'What was the scope or scale of "{snippet}" at {label}?',
        MISSING_STAKEHOLDER: f'Who were the key stakeholders or audiences for "{snippet}" at {label}?',
        MISSING_DATE: f'When did "{snippet}" occur at {label}?',
        MISSING_MAPPING: f'Which company, role, or project does "{snippet}" belong to at {label}?',
    }
    return templates.get(missing_type, f'Tell us more about "{snippet}" at {label}.')


def _item_label(ev: CandidateEvidence) -> str:
    """Build a descriptive label for the evidence item."""
    parts: list[str] = []
    employer = ev.inferred_employer or (ev.experience_mapping or {}).get("company", "")
    role = ev.inferred_role or (ev.experience_mapping or {}).get("role", "")
    if employer and role:
        parts.append(f"{role} at {employer}")
    elif employer:
        parts.append(employer)
    elif role:
        parts.append(role)
    else:
        parts.append("your role")
    return " / ".join(parts) if parts else "your role"


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------


def select_next_question(user) -> dict[str, Any]:
    """Select the highest-value unanswered question for any evidence item.

    Returns a question dict with question_id, evidence_id, question text,
    missing_type, priority, and evidence_label.  Returns {"state": "complete"}
    when no useful question remains.
    """
    evidence_items = _read_evidence(user)
    if user.metadata is None:
        user.metadata = {}
    metadata = user.metadata
    history = _read_history(metadata)

    # Build exclusion set: any question_id in a final state
    excluded_ids: set[str] = {
        str(h.get("question_id") or "")
        for h in history
        if str(h.get("state") or "") in QUESTION_STATES_FINAL
    }

    # Also exclude questions currently in "asked" state
    excluded_ids.update(
        str(h.get("question_id") or "")
        for h in history
        if str(h.get("state") or "") == QUESTION_STATE_ASKED
    )

    # Generate candidate questions for every evidence item
    candidates: list[dict[str, Any]] = []
    for ev in evidence_items:
        if ev.is_merged or ev.is_rejected:
            continue
        missing = _detect_missing_details(ev)
        for mt in missing:
            qid = _make_question_id(ev.evidence_id, mt)
            if qid in excluded_ids:
                continue
            candidates.append({
                "question_id": qid,
                "evidence_id": ev.evidence_id,
                "evidence_type": ev.evidence_type,
                "evidence_text": ev.text,
                "evidence_label": _item_label(ev),
                "missing_type": mt,
                "priority": _MISSING_TYPE_PRIORITY.get(mt, 0),
                "question": _question_text(ev, mt),
            })

    if not candidates:
        return {"state": "complete",
                "message": "All evidence items are complete — no useful questions remain."}

    # Sort by priority descending, then evidence_id for deterministic tie-breaking
    candidates.sort(key=lambda c: (-c["priority"], c["evidence_id"], c["missing_type"]))

    selected = candidates[0]

    # Record as "asked" if not already
    existing = next(
        (h for h in history if str(h.get("question_id") or "") == selected["question_id"]),
        None,
    )
    if existing is None:
        history.append({
            "question_id": selected["question_id"],
            "evidence_id": selected["evidence_id"],
            "missing_type": selected["missing_type"],
            "state": QUESTION_STATE_ASKED,
            "created_at": _now(),
            "asked_at": _now(),
        })
        _write_history(metadata, history)

    return selected


def answer_question(user, question_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Record an answer for a question and optionally update the evidence item."""
    if user.metadata is None:
        user.metadata = {}
    metadata = user.metadata
    history = _read_history(metadata)
    target = _find_question(history, question_id)
    target["state"] = QUESTION_STATE_ANSWERED
    target["answer_text"] = str(payload.get("answer_text") or payload.get("text") or "")
    target["answered_at"] = _now()
    _optionally_update_evidence(user, target.get("evidence_id", ""), payload, metadata)
    _write_history(metadata, history)
    return {"question_id": question_id, "state": QUESTION_STATE_ANSWERED}


def skip_question(user, question_id: str) -> dict[str, Any]:
    """Record a skipped question — it will not be asked again."""
    if user.metadata is None:
        user.metadata = {}
    metadata = user.metadata
    history = _read_history(metadata)
    target = _find_question(history, question_id)
    target["state"] = QUESTION_STATE_SKIPPED
    target["skipped_at"] = _now()
    _write_history(metadata, history)
    return {"question_id": question_id, "state": QUESTION_STATE_SKIPPED}


def dismiss_question(user, question_id: str) -> dict[str, Any]:
    """Dismiss a question permanently — it will not be asked again."""
    if user.metadata is None:
        user.metadata = {}
    metadata = user.metadata
    history = _read_history(metadata)
    target = _find_question(history, question_id)
    target["state"] = QUESTION_STATE_DISMISSED
    target["dismissed_at"] = _now()
    _write_history(metadata, history)
    return {"question_id": question_id, "state": QUESTION_STATE_DISMISSED}


def _find_question(history: list[dict[str, Any]], question_id: str) -> dict[str, Any]:
    """Find a question record in history or create a new entry."""
    for item in history:
        if str(item.get("question_id") or "") == question_id:
            return item
    entry = {
        "question_id": question_id,
        "evidence_id": "",
        "missing_type": "",
        "state": QUESTION_STATE_ANSWERED,
        "created_at": _now(),
        "asked_at": _now(),
    }
    history.append(entry)
    return entry


def _optionally_update_evidence(
    user, evidence_id: str, payload: Mapping[str, Any], metadata: dict,
) -> None:
    """When an answer is given, update the evidence item with provided fields."""
    if not evidence_id:
        return
    raw = list(metadata.get("candidate_evidence") or [])
    for idx, item in enumerate(raw):
        if str(item.get("evidence_id") or "") == evidence_id:
            ev = CandidateEvidence.from_dict(item)
            updated = False
            if payload.get("text"):
                ev.text = str(payload["text"]).strip()
                from backend.domain.candidate_evidence import compute_content_hash
                ev.content_hash = compute_content_hash(ev.text)
                updated = True
            if payload.get("inferred_employer"):
                ev.inferred_employer = str(payload["inferred_employer"]).strip()
                updated = True
            if payload.get("inferred_role"):
                ev.inferred_role = str(payload["inferred_role"]).strip()
                updated = True
            if payload.get("experience_mapping"):
                ev.experience_mapping = dict(payload["experience_mapping"])
                updated = True
            if payload.get("dates"):
                ev.dates = [str(d) for d in payload["dates"]]
                updated = True
            if updated:
                ev.updated_at = _now()
                raw[idx] = ev.to_dict()
                metadata["candidate_evidence"] = raw
            break


def list_question_history(user) -> list[dict[str, Any]]:
    """Return full question history for the user."""
    metadata = dict(user.metadata or {})
    return _read_history(metadata)


def reset_question_history(user) -> dict[str, Any]:
    """Clear all question history (useful after evidence edits for recalculation)."""
    if user.metadata is not None and _QUESTION_HISTORY_KEY in user.metadata:
        del user.metadata[_QUESTION_HISTORY_KEY]
    return {"reset": True}


def recalculate_questions(user) -> dict[str, Any]:
    """Clear history and recompute the question state after evidence edits."""
    reset_question_history(user)
    return select_next_question(user)


__all__ = [
    "ALL_MISSING_TYPES",
    "MISSING_DATE",
    "MISSING_MAPPING",
    "MISSING_METRIC",
    "MISSING_OUTCOME",
    "MISSING_SCOPE",
    "MISSING_STAKEHOLDER",
    "MISSING_TOOL",
    "QUESTION_STATE_ANSWERED",
    "QUESTION_STATE_ASKED",
    "QUESTION_STATE_DISMISSED",
    "QUESTION_STATE_SKIPPED",
    "QUESTION_STATES_FINAL",
    "answer_question",
    "dismiss_question",
    "list_question_history",
    "recalculate_questions",
    "reset_question_history",
    "select_next_question",
    "skip_question",
]
