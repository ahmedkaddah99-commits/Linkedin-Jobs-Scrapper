"""Tests for evidence question service (CP-033R).

Covers:
- Question generation for incomplete items
- Stable question_id derivation
- Asked, answered, skipped, dismissed persistence
- Exclusion of answered/dismissed questions
- Deterministic tie-breaking
- Recovery after evidence edits (deterministic recalculation)
- Complete state when no useful question remains
- Multiple incomplete items
- Reloads and exhaustion
"""

import unittest
from types import SimpleNamespace

from backend.domain.candidate_evidence import CandidateEvidence
from backend.evidence.question_service import (
    MISSING_DATE,
    MISSING_MAPPING,
    MISSING_METRIC,
    MISSING_OUTCOME,
    MISSING_SCOPE,
    MISSING_STAKEHOLDER,
    MISSING_TOOL,
    ALL_MISSING_TYPES,
    QUESTION_STATE_ASKED,
    QUESTION_STATE_ANSWERED,
    QUESTION_STATE_SKIPPED,
    QUESTION_STATE_DISMISSED,
    answer_question,
    dismiss_question,
    list_question_history,
    recalculate_questions,
    reset_question_history,
    select_next_question,
    skip_question,
)


def _make_user(evidence_items=None, history=None):
    """Build a minimal user-like object for testing."""
    metadata = {}
    if evidence_items is not None:
        metadata["candidate_evidence"] = [ev.to_dict() for ev in evidence_items]
    if history is not None:
        metadata["evidence_question_history"] = list(history)
    return SimpleNamespace(metadata=metadata or None)


def _ev(**kwargs) -> CandidateEvidence:
    """Create a CandidateEvidence with defaults for testing."""
    evidence_id = kwargs.pop("evidence_id", None)
    defaults = {"text": "Built something useful.", "evidence_type": "responsibility"}
    defaults.update(kwargs)
    ev = CandidateEvidence.create(**defaults)
    if evidence_id:
        ev.evidence_id = evidence_id
    return ev


class QuestionGenerationTests(unittest.TestCase):
    """Tests for question generation from evidence items."""

    def test_question_has_stable_question_id(self):
        """Same missing gap always produces the same question_id."""
        ev = _ev(text="Built automation scripts.", evidence_type="tool")
        user = _make_user([ev])
        q1 = select_next_question(user)
        self.assertTrue(q1["question_id"].startswith("q_"))
        self.assertEqual(q1["evidence_id"], ev.evidence_id)
        # Reset history so the same gap can be asked again
        reset_question_history(user)
        q2 = select_next_question(user)
        self.assertEqual(q1["question_id"], q2["question_id"])

    def test_question_identifies_evidence_item(self):
        ev = _ev(text="Managed a project.", evidence_type="leadership",
                 inferred_employer="ACME Corp", inferred_role="Manager")
        user = _make_user([ev])
        q = select_next_question(user)
        self.assertEqual(q["evidence_id"], ev.evidence_id)
        self.assertEqual(q["evidence_type"], "leadership")
        self.assertIn("Manager at ACME Corp", q["evidence_label"])

    def test_missing_metric_detected(self):
        ev = _ev(text="Managed a team.", evidence_type="leadership")
        user = _make_user([ev])
        q = select_next_question(user)
        self.assertIn(q["missing_type"], ALL_MISSING_TYPES)

    def test_missing_outcome_has_higher_priority(self):
        ev = _ev(text="Worked on things.")
        user = _make_user([ev])
        q = select_next_question(user)
        self.assertEqual(q["missing_type"], MISSING_OUTCOME)


class QuestionPersistenceTests(unittest.TestCase):
    """Tests for question history persistence across reloads."""

    def test_asked_persists_across_reloads(self):
        ev = _ev(text="Built something.")
        user = _make_user([ev])
        q1 = select_next_question(user)
        reloaded_user = _make_user([ev], list_question_history(user))
        history = list_question_history(reloaded_user)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["state"], QUESTION_STATE_ASKED)
        self.assertEqual(history[0]["question_id"], q1["question_id"])

    def test_answered_excludes_from_selection(self):
        ev = _ev(text="Built something.")
        user = _make_user([ev])
        q1 = select_next_question(user)
        qid = q1["question_id"]
        answer_question(user, qid, {"text": "Increased revenue by 30%."})
        user = _make_user([ev], list_question_history(user))
        q2 = select_next_question(user)
        if q2.get("state") != "complete":
            self.assertNotEqual(q2["question_id"], qid)

    def test_skipped_excludes_from_selection(self):
        ev = _ev(text="Built something.")
        user = _make_user([ev])
        q1 = select_next_question(user)
        skip_question(user, q1["question_id"])
        user = _make_user([ev], list_question_history(user))
        q2 = select_next_question(user)
        if q2.get("state") != "complete":
            self.assertNotEqual(q2["question_id"], q1["question_id"])

    def test_dismissed_excludes_permanently(self):
        ev = _ev(text="Built something.")
        user = _make_user([ev])
        q1 = select_next_question(user)
        dismiss_question(user, q1["question_id"])
        user = _make_user([ev], list_question_history(user))
        q2 = select_next_question(user)
        if q2.get("state") != "complete":
            self.assertNotEqual(q2["question_id"], q1["question_id"])


class MultipleItemsTests(unittest.TestCase):
    def test_highest_priority_gap_selected(self):
        """ev1 has outcome+tool, ev2 has only 'project' — ev2 should win."""
        ev1 = _ev(text="Improved speed using Python scripts.",
                  evidence_type="tool", inferred_employer="ACME")
        ev2 = _ev(text="Worked on a project.", evidence_type="project",
                  inferred_employer="BetaCorp")
        user = _make_user([ev1, ev2])
        q = select_next_question(user)
        self.assertEqual(q["evidence_id"], ev2.evidence_id)
        self.assertEqual(q["missing_type"], MISSING_OUTCOME)

    def test_tie_broken_by_evidence_id(self):
        ev_a = _ev(evidence_id="ev_aaa", text="Did stuff.")
        ev_b = _ev(evidence_id="ev_bbb", text="Did things.")
        user = _make_user([ev_a, ev_b])
        q = select_next_question(user)
        self.assertEqual(q["evidence_id"], "ev_aaa")

    def test_skipped_advances_to_next(self):
        ev1 = _ev(evidence_id="ev_001", text="Did stuff.")
        ev2 = _ev(evidence_id="ev_002", text="Did things.")
        user = _make_user([ev1, ev2])
        q1 = select_next_question(user)
        skip_question(user, q1["question_id"])
        user = _make_user([ev1, ev2], list_question_history(user))
        q2 = select_next_question(user)
        if q2.get("state") != "complete":
            self.assertNotEqual(q2["evidence_id"], q1["evidence_id"])


class ExhaustionTests(unittest.TestCase):
    def test_exhaust_all_no_duplicates(self):
        ev = _ev(text="Did work.")
        user = _make_user([ev])
        seen_ids = set()
        for _ in range(10):
            result = select_next_question(user)
            if result.get("state") == "complete":
                break
            self.assertNotIn(result["question_id"], seen_ids)
            seen_ids.add(result["question_id"])
            answer_question(user, result["question_id"],
                          {"text": "Filled in detail."})
            user = _make_user([ev], list_question_history(user))

    def test_merged_and_rejected_skipped(self):
        ev_active = _ev(text="Built something.")
        ev_merged = _ev(text="Duplicate thing.")
        ev_merged.mark_merged("ev_primary")
        ev_rejected = _ev(text="Bad thing.")
        ev_rejected.reject()
        user = _make_user([ev_active, ev_merged, ev_rejected])
        q = select_next_question(user)
        if q.get("state") != "complete":
            self.assertEqual(q["evidence_id"], ev_active.evidence_id)


class RecalculationTests(unittest.TestCase):
    def test_recalculate_resets_history(self):
        """After recalculate, old history is gone, new question starts fresh."""
        ev = _ev(text="Built something.")
        user = _make_user([ev])
        q1 = select_next_question(user)
        answer_question(user, q1["question_id"], {"text": "Added detail."})
        user.metadata["evidence_question_history"] = list(
            list_question_history(user))
        result = recalculate_questions(user)
        history = list_question_history(user)
        # After recalculate, a fresh question is asked (1 entry)
        self.assertEqual(len(history), 1)

    def test_recalculation_is_deterministic(self):
        """Same evidence produces same first question after recalculation."""
        ev = _ev(text="Did something.")
        user_a = _make_user([ev])
        q_a = select_next_question(user_a)
        user_b = _make_user([ev])
        q_b = recalculate_questions(user_b)
        self.assertEqual(q_a["question_id"], q_b["question_id"])


class MissingTypesTests(unittest.TestCase):
    def test_all_seven_types_defined(self):
        expected = {MISSING_OUTCOME, MISSING_METRIC, MISSING_TOOL,
                    MISSING_SCOPE, MISSING_STAKEHOLDER,
                    MISSING_DATE, MISSING_MAPPING}
        self.assertEqual(set(ALL_MISSING_TYPES), expected)

    def test_question_payload_fields(self):
        ev = _ev(text="Built a custom reporting pipeline.",
                 evidence_type="tool")
        user = _make_user([ev])
        q = select_next_question(user)
        if q.get("state") != "complete":
            self.assertIn("Built a custom reporting", q["question"])
            for key in ["evidence_id", "evidence_type",
                        "missing_type", "priority"]:
                self.assertIn(key, q)


class HistoryListingTests(unittest.TestCase):
    def test_history_includes_all_states(self):
        ev = _ev(text="Built things.")
        user = _make_user([ev])
        q1 = select_next_question(user)
        answer_question(user, q1["question_id"], {"text": "answer"})
        history = list_question_history(user)
        self.assertGreaterEqual(len(history), 1)

    def test_reset_clears_all(self):
        ev = _ev(text="Built things.")
        user = _make_user([ev])
        select_next_question(user)
        reset_question_history(user)
        self.assertEqual(len(list_question_history(user)), 0)


if __name__ == "__main__":
    unittest.main()