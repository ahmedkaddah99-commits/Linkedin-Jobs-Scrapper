"""CP-040R: Tests for evidence review service.

Covers: suggestions, ambiguity, rejection, several items, counters, reload.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from backend.domain.candidate_evidence import (
    CandidateEvidence,
    EVIDENCE_STATUS_CONFIRMED,
    EVIDENCE_STATUS_NEEDS_REVIEW,
    EVIDENCE_STATUS_REJECTED,
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


def _make_user(metadata=None):
    user = MagicMock()
    user.metadata = dict(metadata or {})
    user.profile_id = "prof_1"
    user.updated_at = ""
    return user


def _make_evidence(**kwargs):
    return CandidateEvidence.create(
        profile_id=kwargs.get("profile_id", ""),
        text=kwargs.get("text", "Test evidence item."),
        evidence_type=kwargs.get("evidence_type", "achievement"),
        source_asset=kwargs.get("source_asset", "resume.pdf"),
        source_id=kwargs.get("source_id", "src_1"),
        inferred_employer=kwargs.get("inferred_employer", ""),
        inferred_role=kwargs.get("inferred_role", ""),
        dates=kwargs.get("dates", []),
        confidence=kwargs.get("confidence", 0.8),
    )


class TestRemoveLegacyMemorySpike(unittest.TestCase):

    def test_removes_known_legacy_keys(self):
        user = _make_user(metadata={
            "memory_spike": {"count": 5},
            "evidence_progress": 3,
            "career_memory_step": "question",
            "candidate_evidence": [],
        })
        result = remove_legacy_memory_spike(user)
        self.assertGreaterEqual(len(result["removed_keys"]), 1)
        self.assertIn("memory_spike", result["removed_keys"])

    def test_no_metadata_handled_gracefully(self):
        user = _make_user(metadata=None)
        result = remove_legacy_memory_spike(user)
        self.assertEqual(result["migrated_count"], 0)

    def test_migrates_spike_cache(self):
        user = _make_user(metadata={
            "evidence_spike_cache": [{
                "text": "Increased sales by 25%.",
                "type": "metric",
                "source_asset": "cv.docx",
                "employer": "Acme Corp",
                "role": "Sales Lead",
            }],
            "candidate_evidence": [],
        })
        result = remove_legacy_memory_spike(user)
        self.assertEqual(result["migrated_count"], 1)


class TestSuggestMapping(unittest.TestCase):

    def test_suggests_by_employer(self):
        ev = _make_evidence(
            text="Built dashboard.",
            inferred_employer="Microsoft",
            inferred_role="SDE",
        )
        experiences = [{
            "experience_id": "exp_1",
            "employer": "Microsoft Corp",
            "job_title": "Software Engineer",
            "start_date": "2020",
            "end_date": "2022",
        }]
        result = suggest_mapping_for_evidence(ev, experiences)
        self.assertIsNotNone(result["suggested_mapping"])
        self.assertGreater(result["match_confidence"], 0.3)

    def test_detects_ambiguity(self):
        ev = _make_evidence(
            text="Managed team.",
            inferred_employer="Tech Inc",
            inferred_role="Engineering Manager",
            dates=["2021", "2022"],
        )
        experiences = [
            {"experience_id": "exp_a", "employer": "Tech Inc",
             "job_title": "Engineering Manager",
             "start_date": "2020", "end_date": "2022"},
            {"experience_id": "exp_b", "employer": "Tech Inc",
             "job_title": "Senior Engineering Manager",
             "start_date": "2020", "end_date": "2022"},
        ]
        result = suggest_mapping_for_evidence(ev, experiences)
        self.assertTrue(result["is_ambiguous"])
        self.assertGreater(len(result["alternatives"]), 0)

    def test_no_experiences_empty(self):
        ev = _make_evidence(text="Some text.")
        result = suggest_mapping_for_evidence(ev, [])
        self.assertIsNone(result["suggested_mapping"])

    def test_no_match_empty(self):
        ev = _make_evidence(
            text="Data analysis.",
            inferred_employer="Unknown", dates=["2015"],
        )
        experiences = [{
            "experience_id": "exp_x",
            "employer": "Different LLC", "job_title": "CEO",
            "start_date": "2020", "end_date": "2022",
        }]
        result = suggest_mapping_for_evidence(ev, experiences)
        self.assertIsNone(result["suggested_mapping"])


class TestEvidenceReview(unittest.TestCase):

    def test_get_next_review_item(self):
        ev1 = _make_evidence(text="First item.")
        ev1.status = EVIDENCE_STATUS_NEEDS_REVIEW
        ev2 = _make_evidence(text="Second item.")
        ev2.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user(metadata={
            "candidate_evidence": [ev1.to_dict(), ev2.to_dict()],
            "work_experiences": [],
        })
        item = get_next_review_item(user)
        self.assertEqual(item["state"], "review")
        self.assertEqual(item["evidence"]["text"], "First item.")

    def test_complete_when_all_reviewed(self):
        ev1 = _make_evidence(text="Confirmed.")
        ev1.confirm()
        user = _make_user(metadata={
            "candidate_evidence": [ev1.to_dict()],
            "work_experiences": [],
        })
        self.assertEqual(get_next_review_item(user)["state"], "complete")

    def test_confirm_advances_cursor(self):
        ev1 = _make_evidence(text="Item 1.")
        ev1.status = EVIDENCE_STATUS_NEEDS_REVIEW
        ev2 = _make_evidence(text="Item 2.")
        ev2.status = EVIDENCE_STATUS_NEEDS_REVIEW
        ev3 = _make_evidence(text="Item 3.")
        ev3.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user(metadata={
            "candidate_evidence": [ev1.to_dict(), ev2.to_dict(), ev3.to_dict()],
            "work_experiences": [],
        })
        result = confirm_evidence(user, ev1.evidence_id)
        self.assertEqual(result["action"], "confirmed")
        next_item = get_next_review_item(user)
        self.assertEqual(next_item["evidence"]["text"], "Item 2.")
        # CP-041R: Confirm item 2, verify item 3 comes next (no skip)
        confirm_evidence(user, ev2.evidence_id)
        third_item = get_next_review_item(user)
        self.assertEqual(third_item["evidence"]["text"], "Item 3.")

    def test_reject_advances_cursor(self):
        ev1 = _make_evidence(text="Rejected.")
        ev1.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user(metadata={
            "candidate_evidence": [ev1.to_dict()],
            "work_experiences": [],
        })
        result = reject_evidence(user, ev1.evidence_id)
        self.assertEqual(result["action"], "rejected")
        self.assertEqual(get_next_review_item(user)["state"], "complete")

    def test_reject_three_items_no_skip(self):
        """CP-041R: Reject items 1 and 2 of 3, verify item 3 comes next."""
        ev1 = _make_evidence(text="R1.")
        ev1.status = EVIDENCE_STATUS_NEEDS_REVIEW
        ev2 = _make_evidence(text="R2.")
        ev2.status = EVIDENCE_STATUS_NEEDS_REVIEW
        ev3 = _make_evidence(text="R3.")
        ev3.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user(metadata={
            "candidate_evidence": [ev1.to_dict(), ev2.to_dict(), ev3.to_dict()],
            "work_experiences": [],
        })
        first = get_next_review_item(user)
        self.assertEqual(first["evidence"]["text"], "R1.")
        reject_evidence(user, first["evidence"]["evidence_id"])
        second = get_next_review_item(user)
        self.assertEqual(second["evidence"]["text"], "R2.")
        reject_evidence(user, second["evidence"]["evidence_id"])
        third = get_next_review_item(user)
        self.assertEqual(third["evidence"]["text"], "R3.")

    def test_confirm_with_mapping(self):
        ev1 = _make_evidence(text="Mapped.")
        ev1.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user(metadata={
            "candidate_evidence": [ev1.to_dict()],
            "work_experiences": [],
        })
        mapping = {"experience_id": "exp_A", "employer": "Acme", "role": "Dev"}
        result = confirm_evidence(user, ev1.evidence_id, mapping=mapping)
        self.assertEqual(
            result["evidence"]["experience_mapping"]["experience_id"],
            "exp_A",
        )

    def test_confirm_with_edited_text(self):
        ev1 = _make_evidence(text="Original.")
        ev1.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user(metadata={
            "candidate_evidence": [ev1.to_dict()],
            "work_experiences": [],
        })
        result = confirm_evidence(user, ev1.evidence_id, edited_text="Corrected.")
        self.assertEqual(result["evidence"]["text"], "Corrected.")

    def test_review_several_items(self):
        items = []
        for i in range(5):
            ev = _make_evidence(text=f"Item {i+1}.")
            ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
            items.append(ev)
        user = _make_user(metadata={
            "candidate_evidence": [ev.to_dict() for ev in items],
            "work_experiences": [],
        })
        for i in range(4):
            confirm_evidence(user, items[i].evidence_id)
        reject_evidence(user, items[4].evidence_id)
        self.assertEqual(get_next_review_item(user)["state"], "complete")

    def test_raises_keyerror_on_missing(self):
        user = _make_user(metadata={"candidate_evidence": []})
        with self.assertRaises(KeyError):
            confirm_evidence(user, "nonexistent")

    def test_review_item_returns_provenance(self):
        ev1 = _make_evidence(
            text="Provenanced.",
            source_asset="cv_2024.pdf",
            source_confidence=0.85,
            inferred_employer="TCorp",
        )
        ev1.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user(metadata={
            "candidate_evidence": [ev1.to_dict()],
            "work_experiences": [],
        })
        item = get_next_review_item(user)
        self.assertIsNotNone(item["provenance"])
        self.assertEqual(item["provenance"]["source_asset"], "cv_2024.pdf")


class TestCanonicalReadiness(unittest.TestCase):

    def test_all_confirmed_is_ready(self):
        ev1 = _make_evidence(text="Item 1.")
        ev1.confirm()
        ev1.experience_mapping = {"experience_id": "exp_1"}
        ev2 = _make_evidence(text="Item 2.")
        ev2.confirm()
        ev2.experience_mapping = {"experience_id": "exp_2"}
        user = _make_user(metadata={
            "candidate_evidence": [ev1.to_dict(), ev2.to_dict()],
        })
        result = compute_canonical_readiness(user)
        self.assertTrue(result["is_ready"])
        self.assertEqual(result["mapped_ready"], 2)

    def test_needs_review_not_ready(self):
        ev1 = _make_evidence(text="Unreviewed.")
        ev1.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user(metadata={
            "candidate_evidence": [ev1.to_dict()],
        })
        result = compute_canonical_readiness(user)
        self.assertFalse(result["is_ready"])
        self.assertEqual(result["needs_review"], 1)

    def test_mixed_confirmed_rejected(self):
        ev1 = _make_evidence(text="C.")
        ev1.confirm()
        ev2 = _make_evidence(text="R.")
        ev2.reject()
        user = _make_user(metadata={
            "candidate_evidence": [ev1.to_dict(), ev2.to_dict()],
        })
        result = compute_canonical_readiness(user)
        self.assertEqual(result["confirmed"], 1)
        self.assertEqual(result["rejected"], 1)

    def test_legacy_counters_excluded(self):
        ev1 = _make_evidence(text="C.")
        ev1.confirm()
        ev1.experience_mapping = {"experience_id": "e1"}
        user = _make_user(metadata={
            "candidate_evidence": [ev1.to_dict()],
            "memory_spike": {"count": 10},
        })
        result = compute_canonical_readiness(user)
        self.assertTrue(result["legacy_counters_excluded"])
        self.assertEqual(result["computed_from"], "canonical_evidence")

    def test_empty_evidence(self):
        user = _make_user(metadata={"candidate_evidence": []})
        result = compute_canonical_readiness(user)
        self.assertEqual(result["readiness_ratio"], 0.0)

    def test_reset_review_state(self):
        ev1 = _make_evidence(text="Item 1.")
        ev1.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user(metadata={
            "candidate_evidence": [ev1.to_dict()],
        })
        get_next_review_item(user)
        result = reset_review_state(user)
        self.assertTrue(result["cursor_reset"])
        item = get_next_review_item(user)
        self.assertEqual(item["evidence"]["text"], "Item 1.")


if __name__ == "__main__":
    unittest.main()
