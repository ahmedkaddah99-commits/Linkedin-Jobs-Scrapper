"""Tests for evidence review service (CP-040R).

Covers:
- suggest_mapping_for_evidence with employer/role/date overlap
- get_next_review_item with cursor progression
- confirm_evidence with mapping and edited text
- reject_evidence with auto-advance
- edit_evidence with field updates
- compute_canonical_readiness from evidence records
- remove_legacy_memory_spike migration
- reset_review_state cursor reset
"""

from __future__ import annotations

import types
import unittest
from typing import Any

from backend.domain.candidate_evidence import (
    CandidateEvidence,
    EVIDENCE_STATUS_CONFIRMED,
    EVIDENCE_STATUS_NEEDS_REVIEW,
    EVIDENCE_STATUS_REJECTED,
    EVIDENCE_STATUS_REVIEWED,
    compute_content_hash,
)
from backend.evidence.review_service import (
    compute_canonical_readiness,
    confirm_evidence,
    edit_evidence,
    get_next_review_item,
    reject_evidence,
    remove_legacy_memory_spike,
    reset_review_state,
    suggest_mapping_for_evidence,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_user(
    metadata: dict[str, Any] | None = None,
    profile_id: str = "prof_test",
) -> Any:
    """Build a minimal user-like object with metadata."""
    user = types.SimpleNamespace()
    user.metadata = dict(metadata or {})
    user.profile_id = profile_id
    user.updated_at = None
    return user


def _make_evidence(**overrides: Any) -> CandidateEvidence:
    """Create a CandidateEvidence with sane defaults."""
    defaults: dict[str, Any] = {
        "profile_id": "prof_test",
        "text": "Led a team of 5 engineers to deliver a cloud migration project.",
        "evidence_type": "achievement",
        "source_asset": "cv_upload",
        "inferred_employer": "Acme Corp",
        "inferred_role": "Senior Engineer",
        "dates": ["2023-01-01", "2024-12-31"],
    }
    defaults.update(overrides)
    # CandidateEvidence.create() does not accept 'status' — set it post-create.
    status = defaults.pop("status", None)
    ev = CandidateEvidence.create(**{k: v for k, v in defaults.items()
                                     if k in CandidateEvidence.create.__code__.co_varnames})
    if status is not None:
        ev.status = status
    return ev


def _make_experience(**overrides: Any) -> dict[str, Any]:
    """Create an experience dict with sane defaults."""
    defaults: dict[str, Any] = {
        "experience_id": "exp_1",
        "job_title": "Senior Engineer",
        "employer": "Acme Corp",
        "start_date": "2023-01-01",
        "end_date": "2024-12-31",
        "description": "Led cloud migration projects.",
    }
    defaults.update(overrides)
    return defaults


# ── suggest_mapping_for_evidence ─────────────────────────────────────────────



class SuggestMappingTests(unittest.TestCase):
    """Tests for auto-suggested experience mapping."""

    def test_empty_experiences_returns_none(self):
        ev = _make_evidence()
        result = suggest_mapping_for_evidence(ev, [])
        self.assertIsNone(result["suggested_mapping"])
        self.assertFalse(result["is_ambiguous"])
        self.assertEqual(result["match_confidence"], 0.0)

    def test_exact_employer_role_match_is_high_confidence(self):
        ev = _make_evidence(
            inferred_employer="Acme Corp",
            inferred_role="Senior Engineer",
        )
        exps = [_make_experience(employer="Acme Corp", job_title="Senior Engineer")]
        result = suggest_mapping_for_evidence(ev, exps)
        self.assertIsNotNone(result["suggested_mapping"])
        self.assertGreater(result["match_confidence"], 0.5)
        self.assertEqual(result["suggested_mapping"]["experience_id"], "exp_1")

    def test_fuzzy_employer_match(self):
        ev = _make_evidence(inferred_employer="Acme Corporation")
        exps = [_make_experience(employer="Acme Corp")]
        result = suggest_mapping_for_evidence(ev, exps)
        self.assertIsNotNone(result["suggested_mapping"])
        self.assertGreater(result["match_confidence"], 0.0)

    def test_no_match_returns_none(self):
        ev = _make_evidence(
            inferred_employer="zyxwvutsrq",
            inferred_role="abcdefghij",
            dates=[],
        )
        exps = [
            _make_experience(
                employer="Completely Different LLC",
                job_title="Other Role",
            ),
        ]
        result = suggest_mapping_for_evidence(ev, exps)
        self.assertIsNone(result["suggested_mapping"])
        self.assertEqual(result["match_confidence"], 0.0)

    def test_date_overlap_improves_score(self):
        ev = _make_evidence(dates=["2023-06-01", "2024-06-01"])
        exp = _make_experience(start_date="2023-01-01", end_date="2024-12-31")
        result = suggest_mapping_for_evidence(ev, [exp])
        self.assertIsNotNone(result["suggested_mapping"])
        self.assertGreater(result["match_confidence"], 0.0)

    def test_ambiguous_when_multiple_close_matches(self):
        ev = _make_evidence(inferred_employer="Acme", inferred_role="Engineer")
        exps = [
            _make_experience(
                experience_id="exp_1",
                employer="Acme Corp",
                job_title="Senior Engineer",
            ),
            _make_experience(
                experience_id="exp_2",
                employer="Acme Corp",
                job_title="Junior Engineer",
            ),
        ]
        result = suggest_mapping_for_evidence(ev, exps)
        self.assertTrue(result["is_ambiguous"])
        self.assertGreater(len(result["alternatives"]), 0)

    def test_present_date_matches(self):
        ev = _make_evidence(
            inferred_employer="Acme Corp",
            dates=["2024-01-01", "present"],
        )
        exps = [
            _make_experience(
                employer="Acme Corp",
                job_title="Senior Engineer",
                start_date="2023-01-01",
                end_date="present",
            ),
        ]
        result = suggest_mapping_for_evidence(ev, exps)
        self.assertIsNotNone(result["suggested_mapping"])

    def test_suggested_mapping_has_label(self):
        ev = _make_evidence(inferred_employer="Acme Corp")
        exps = [_make_experience(employer="Acme Corp")]
        result = suggest_mapping_for_evidence(ev, exps)
        self.assertIn("label", result["suggested_mapping"])


# ── get_next_review_item ─────────────────────────────────────────────────────


class GetNextReviewItemTests(unittest.TestCase):
    """Tests for one-at-a-time review retrieval."""

    def setUp(self):
        super().setUp()
        self.ev1 = _make_evidence(text="Achieved 150% revenue growth.")
        self.ev2 = _make_evidence(
            text="Managed cross-functional team.",
            inferred_employer="Beta Ltd",
        )

    def test_no_evidence_returns_complete(self):
        user = _make_user({"candidate_evidence": []})
        result = get_next_review_item(user)
        self.assertEqual(result["state"], "complete")

    def test_returns_first_unreviewed_item(self):
        user = _make_user({
            "candidate_evidence": [self.ev1.to_dict(), self.ev2.to_dict()],
        })
        result = get_next_review_item(user)
        self.assertEqual(result["state"], "review")
        self.assertEqual(result["evidence"]["text"], self.ev1.text)

    def test_cursor_advances_after_confirm(self):
        user = _make_user({
            "candidate_evidence": [self.ev1.to_dict(), self.ev2.to_dict()],
        })
        result1 = get_next_review_item(user)
        self.assertEqual(result1["evidence"]["text"], self.ev1.text)
        confirm_evidence(user, result1["evidence"]["evidence_id"])
        result2 = get_next_review_item(user)
        self.assertEqual(result2["evidence"]["text"], self.ev2.text)

    def test_skips_confirmed_and_rejected(self):
        ev3 = _make_evidence(text="Third item.")
        user = _make_user({
            "candidate_evidence": [
                self.ev1.to_dict(),
                self.ev2.to_dict(),
                ev3.to_dict(),
            ],
        })
        # Confirm the first item
        r1 = get_next_review_item(user)
        confirm_evidence(user, r1["evidence"]["evidence_id"])
        # Reject the next item that comes up
        r2 = get_next_review_item(user)
        reject_evidence(user, r2["evidence"]["evidence_id"])
        # Last remaining unreviewed item should be available
        r3 = get_next_review_item(user)
        self.assertIn(r3["evidence"]["text"], [self.ev2.text, ev3.text])

    def test_cursor_wraps_around(self):
        user = _make_user({
            "candidate_evidence": [self.ev1.to_dict(), self.ev2.to_dict()],
        })
        user.metadata["evidence_review_cursor"] = 5
        result = get_next_review_item(user)
        self.assertEqual(result["state"], "review")

    def test_progress_fields_are_present(self):
        user = _make_user({
            "candidate_evidence": [self.ev1.to_dict(), self.ev2.to_dict()],
        })
        result = get_next_review_item(user)
        self.assertIn("progress", result)
        self.assertIn("cursor", result["progress"])
        self.assertIn("remaining", result["progress"])

    def test_provenance_included(self):
        user = _make_user({
            "candidate_evidence": [self.ev1.to_dict()],
        })
        result = get_next_review_item(user)
        self.assertIn("provenance", result)
        self.assertEqual(result["provenance"]["source_asset"], self.ev1.source_asset)

    def test_mapping_suggestion_included(self):
        user = _make_user({
            "candidate_evidence": [self.ev1.to_dict()],
            "work_experiences": [_make_experience()],
        })
        result = get_next_review_item(user)
        self.assertIn("suggested_mapping", result)
        self.assertIn("match_confidence", result)

    def test_skips_merged_items(self):
        merged_ev = _make_evidence(text="Merged item.", status="merged")
        user = _make_user({
            "candidate_evidence": [merged_ev.to_dict(), self.ev1.to_dict()],
        })
        result = get_next_review_item(user)
        self.assertEqual(result["evidence"]["text"], self.ev1.text)



# ── confirm_evidence ─────────────────────────────────────────────────────────


class ConfirmEvidenceTests(unittest.TestCase):
    """Tests for evidence confirmation."""

    def setUp(self):
        super().setUp()
        self.ev = _make_evidence()

    def test_confirm_sets_status(self):
        user = _make_user({"candidate_evidence": [self.ev.to_dict()]})
        result = confirm_evidence(user, self.ev.evidence_id)
        self.assertEqual(result["action"], "confirmed")
        self.assertEqual(result["evidence"]["status"], EVIDENCE_STATUS_CONFIRMED)

    def test_confirm_with_mapping(self):
        user = _make_user({"candidate_evidence": [self.ev.to_dict()]})
        mapping = {"experience_id": "exp_42", "employer": "Acme Corp"}
        result = confirm_evidence(user, self.ev.evidence_id, mapping=mapping)
        self.assertEqual(result["evidence"]["status"], EVIDENCE_STATUS_CONFIRMED)
        persisted = user.metadata["candidate_evidence"][0]
        self.assertIn("experience_mapping", persisted)

    def test_confirm_with_edited_text(self):
        user = _make_user({"candidate_evidence": [self.ev.to_dict()]})
        new_text = "Updated achievement description."
        result = confirm_evidence(
            user, self.ev.evidence_id, edited_text=new_text,
        )
        self.assertEqual(result["evidence"]["text"], new_text)

    def test_confirm_nonexistent_raises_keyerror(self):
        user = _make_user({"candidate_evidence": []})
        with self.assertRaises(KeyError):
            confirm_evidence(user, "nonexistent_id")

    def test_confirm_preserves_existing_fields(self):
        user = _make_user({"candidate_evidence": [self.ev.to_dict()]})
        result = confirm_evidence(user, self.ev.evidence_id)
        self.assertEqual(result["evidence"]["evidence_type"], "achievement")

    def test_confirm_advances_cursor(self):
        ev2 = _make_evidence(text="Second item.")
        user = _make_user({
            "candidate_evidence": [self.ev.to_dict(), ev2.to_dict()],
        })
        confirm_evidence(user, self.ev.evidence_id)
        next_item = get_next_review_item(user)
        self.assertEqual(next_item["evidence"]["text"], ev2.text)

    def test_confirm_with_three_items_does_not_skip(self):
        """CP-041R: Confirm item 1 of 3, verify item 2 (not 3) comes next."""
        ev2 = _make_evidence(text="Item 2.")
        ev3 = _make_evidence(text="Item 3.")
        user = _make_user({
            "candidate_evidence": [
                self.ev.to_dict(), ev2.to_dict(), ev3.to_dict(),
            ],
        })
        result = confirm_evidence(user, self.ev.evidence_id)
        self.assertEqual(result["action"], "confirmed")
        next_item = get_next_review_item(user)
        self.assertEqual(next_item["evidence"]["text"], ev2.text)
        confirm_evidence(user, ev2.evidence_id)
        third_item = get_next_review_item(user)
        self.assertEqual(third_item["evidence"]["text"], ev3.text)



# ── reject_evidence ──────────────────────────────────────────────────────────


class RejectEvidenceTests(unittest.TestCase):
    """Tests for evidence rejection."""

    def setUp(self):
        super().setUp()
        self.ev = _make_evidence()

    def test_reject_sets_status(self):
        user = _make_user({"candidate_evidence": [self.ev.to_dict()]})
        result = reject_evidence(user, self.ev.evidence_id)
        self.assertEqual(result["action"], "rejected")
        self.assertEqual(result["evidence"]["status"], EVIDENCE_STATUS_REJECTED)

    def test_reject_nonexistent_raises_keyerror(self):
        user = _make_user({"candidate_evidence": []})
        with self.assertRaises(KeyError):
            reject_evidence(user, "nonexistent_id")

    def test_reject_advances_cursor(self):
        ev2 = _make_evidence(text="Second item.")
        user = _make_user({
            "candidate_evidence": [self.ev.to_dict(), ev2.to_dict()],
        })
        reject_evidence(user, self.ev.evidence_id)
        next_item = get_next_review_item(user)
        self.assertEqual(next_item["evidence"]["text"], ev2.text)

    def test_reject_with_three_items_does_not_skip(self):
        """CP-041R: Reject item 1 of 3, verify item 2 (not 3) comes next."""
        ev2 = _make_evidence(text="Item 2.")
        ev3 = _make_evidence(text="Item 3.")
        user = _make_user({
            "candidate_evidence": [
                self.ev.to_dict(), ev2.to_dict(), ev3.to_dict(),
            ],
        })
        result = reject_evidence(user, self.ev.evidence_id)
        self.assertEqual(result["action"], "rejected")
        next_item = get_next_review_item(user)
        self.assertEqual(next_item["evidence"]["text"], ev2.text)
        reject_evidence(user, ev2.evidence_id)
        third_item = get_next_review_item(user)
        self.assertEqual(third_item["evidence"]["text"], ev3.text)


# ── edit_evidence ────────────────────────────────────────────────────────────


class EditEvidenceTests(unittest.TestCase):
    """Tests for evidence field editing."""

    def setUp(self):
        super().setUp()
        self.ev = _make_evidence()

    def test_edit_text_updates_hash(self):
        user = _make_user({"candidate_evidence": [self.ev.to_dict()]})
        orig_hash = self.ev.content_hash
        result = edit_evidence(
            user, self.ev.evidence_id, {"text": "Brand new text."},
        )
        self.assertEqual(result["action"], "edited")
        self.assertNotEqual(result["evidence"]["content_hash"], orig_hash)

    def test_edit_updates_employer(self):
        user = _make_user({"candidate_evidence": [self.ev.to_dict()]})
        result = edit_evidence(
            user, self.ev.evidence_id, {"inferred_employer": "NewCo"},
        )
        self.assertEqual(result["evidence"]["inferred_employer"], "NewCo")

    def test_edit_updates_role(self):
        user = _make_user({"candidate_evidence": [self.ev.to_dict()]})
        result = edit_evidence(
            user, self.ev.evidence_id, {"inferred_role": "Staff Engineer"},
        )
        self.assertEqual(result["evidence"]["inferred_role"], "Staff Engineer")

    def test_edit_updates_dates(self):
        user = _make_user({"candidate_evidence": [self.ev.to_dict()]})
        result = edit_evidence(
            user, self.ev.evidence_id,
            {"dates": ["2022-01-01", "2023-06-01"]},
        )
        self.assertEqual(result["evidence"]["dates"], ["2022-01-01", "2023-06-01"])

    def test_edit_marks_reviewed(self):
        user = _make_user({"candidate_evidence": [self.ev.to_dict()]})
        result = edit_evidence(
            user, self.ev.evidence_id, {"evidence_type": "leadership"},
        )
        self.assertEqual(result["evidence"]["status"], EVIDENCE_STATUS_REVIEWED)

    def test_edit_advances_cursor(self):
        ev2 = _make_evidence(text="Second item.")
        user = _make_user({
            "candidate_evidence": [self.ev.to_dict(), ev2.to_dict()],
        })
        edit_evidence(user, self.ev.evidence_id, {"inferred_employer": "NewCo"})
        next_item = get_next_review_item(user)
        self.assertEqual(next_item["evidence"]["text"], ev2.text)

    def test_edit_nonexistent_raises_keyerror(self):
        user = _make_user({"candidate_evidence": []})
        with self.assertRaises(KeyError):
            edit_evidence(user, "nonexistent_id", {"text": "x"})



# ── compute_canonical_readiness ──────────────────────────────────────────────


class ComputeCanonicalReadinessTests(unittest.TestCase):
    """Tests for readiness from canonical evidence records."""

    def test_empty_evidence_returns_zeros(self):
        user = _make_user({"candidate_evidence": []})
        result = compute_canonical_readiness(user)
        self.assertEqual(result["total_evidence"], 0)
        self.assertEqual(result["confirmed"], 0)
        self.assertFalse(result["is_ready"])

    def test_all_confirmed_and_mapped_is_ready(self):
        ev = _make_evidence()
        ev.confirm()
        ev.experience_mapping = {"experience_id": "exp_1"}
        user = _make_user({"candidate_evidence": [ev.to_dict()]})
        result = compute_canonical_readiness(user)
        self.assertEqual(result["confirmed"], 1)
        self.assertEqual(result["mapped_ready"], 1)
        self.assertTrue(result["is_ready"])

    def test_needs_review_not_ready(self):
        ev = _make_evidence(status=EVIDENCE_STATUS_NEEDS_REVIEW)
        user = _make_user({"candidate_evidence": [ev.to_dict()]})
        result = compute_canonical_readiness(user)
        self.assertFalse(result["is_ready"])

    def test_partially_confirmed_not_ready(self):
        ev1 = _make_evidence(
            status=EVIDENCE_STATUS_CONFIRMED,
            experience_mapping={"experience_id": "exp_1"},
        )
        ev2 = _make_evidence(status=EVIDENCE_STATUS_NEEDS_REVIEW)
        user = _make_user({
            "candidate_evidence": [ev1.to_dict(), ev2.to_dict()],
        })
        result = compute_canonical_readiness(user)
        self.assertFalse(result["is_ready"])
        self.assertEqual(result["needs_review"], 1)

    def test_rejected_excluded_from_actionable(self):
        ev1 = _make_evidence(
            status=EVIDENCE_STATUS_CONFIRMED,
            experience_mapping={"experience_id": "exp_1"},
        )
        ev2 = _make_evidence(status=EVIDENCE_STATUS_REJECTED)
        user = _make_user({
            "candidate_evidence": [ev1.to_dict(), ev2.to_dict()],
        })
        result = compute_canonical_readiness(user)
        self.assertTrue(result["is_ready"])
        self.assertEqual(result["rejected"], 1)

    def test_legacy_counters_excluded_flag(self):
        user = _make_user({"candidate_evidence": []})
        result = compute_canonical_readiness(user)
        self.assertTrue(result["legacy_counters_excluded"])
        self.assertEqual(result["computed_from"], "canonical_evidence")


# ── remove_legacy_memory_spike ───────────────────────────────────────────────


class RemoveLegacyMemorySpikeTests(unittest.TestCase):
    """Tests for legacy memory-spike migration."""

    def test_none_metadata_returns_empty(self):
        user = _make_user()
        user.metadata = None
        result = remove_legacy_memory_spike(user)
        self.assertEqual(result["removed_keys"], [])
        self.assertEqual(result["migrated_count"], 0)

    def test_removes_legacy_keys(self):
        user = _make_user({
            "memory_spike": {"step": 3},
            "evidence_progress": 5,
            "evidence_question_index": 2,
            "candidate_evidence": [],
        })
        result = remove_legacy_memory_spike(user)
        self.assertGreaterEqual(len(result["removed_keys"]), 1)
        self.assertNotIn("memory_spike", user.metadata)

    def test_migrates_spike_cache(self):
        user = _make_user({
            "evidence_spike_cache": [
                {
                    "text": "Led migration project.",
                    "type": "achievement",
                    "employer": "Acme",
                    "role": "Lead",
                    "source_asset": "cv",
                },
            ],
            "candidate_evidence": [],
        })
        result = remove_legacy_memory_spike(user)
        self.assertEqual(result["migrated_count"], 1)
        self.assertNotIn("evidence_spike_cache", user.metadata)
        stored = user.metadata.get("candidate_evidence")
        self.assertIsNotNone(stored)
        self.assertEqual(len(stored), 1)

    def test_skips_duplicate_spike_migration(self):
        user = _make_user({
            "evidence_spike_cache": [{"text": "Duplicated item.", "type": "achievement"}],
            "candidate_evidence": [{
                "evidence_id": "ev_existing",
                "profile_id": "prof_test",
                "text": "Duplicated item.",
                "evidence_type": "achievement",
                "status": "needs_review",
                "content_hash": compute_content_hash("Duplicated item."),
            }],
        })
        result = remove_legacy_memory_spike(user)
        self.assertEqual(result["migrated_count"], 0)
        self.assertEqual(len(user.metadata["candidate_evidence"]), 1)

    def test_skips_spike_items_without_text(self):
        user = _make_user({
            "evidence_spike_cache": [{"type": "achievement", "employer": "Acme"}],
            "candidate_evidence": [],
        })
        result = remove_legacy_memory_spike(user)
        self.assertEqual(result["migrated_count"], 0)


# ── reset_review_state ───────────────────────────────────────────────────────


class ResetReviewStateTests(unittest.TestCase):
    """Tests for review cursor reset."""

    def test_resets_cursor_to_zero(self):
        user = _make_user({
            "evidence_review_cursor": 5,
            "candidate_evidence": [],
        })
        result = reset_review_state(user)
        self.assertTrue(result["cursor_reset"])
        self.assertEqual(user.metadata.get("evidence_review_cursor"), 0)

    def test_readiness_included_in_result(self):
        user = _make_user({"candidate_evidence": []})
        result = reset_review_state(user)
        self.assertIn("readiness", result)


if __name__ == "__main__":
    unittest.main()

