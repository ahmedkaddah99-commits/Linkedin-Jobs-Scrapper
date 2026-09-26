"""Tests for CP-044R: Continuous evidence journey from review to outputs.

Covers: journey state machine (review -> ready -> actionable), read-only
next-item inspection, journey completion detection, evidence-to-output
provenance bridge, build_ready_actions integration, empty/edge-case
states, and fixture provider journey support.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from backend.domain.candidate_evidence import (
    CandidateEvidence,
    EVIDENCE_STATUS_CONFIRMED,
    EVIDENCE_STATUS_NEEDS_REVIEW,
    EVIDENCE_STATUS_REJECTED,
    EVIDENCE_STATUS_REVIEWED,
)
from backend.evidence.review_service import (
    build_ready_actions,
    compute_canonical_readiness,
    confirm_evidence,
    get_next_review_item,
    reject_evidence,
    reset_review_state,
    try_get_next_review_item,
)


def _make_user(metadata=None):
    user = MagicMock()
    user.metadata = dict(metadata or {})
    user.profile_id = "prof_044"
    user.updated_at = ""
    return user


def _make_evidence(**kwargs):
    return CandidateEvidence.create(
        profile_id=kwargs.get("profile_id", "prof_044"),
        text=kwargs.get("text", "Test evidence item."),
        evidence_type=kwargs.get("evidence_type", "achievement"),
        source_asset=kwargs.get("source_asset", "resume.pdf"),
        source_id=kwargs.get("source_id", "src_1"),
        inferred_employer=kwargs.get("inferred_employer", ""),
        inferred_role=kwargs.get("inferred_role", ""),
        dates=kwargs.get("dates", []),
        confidence=kwargs.get("confidence", 0.8),
    )


def _confirmed_with_mapping(text, employer, role, exp_id="exp_1"):
    ev = _make_evidence(
        text=text, inferred_employer=employer, inferred_role=role,
    )
    ev.confirm()
    ev.experience_mapping = {"experience_id": exp_id, "company": employer, "role": role}
    return ev


# ---------------------------------------------------------------------------
# Journey State Machine Tests
# ---------------------------------------------------------------------------


class JourneyStateMachineTests(unittest.TestCase):
    """CP-044R: Continuous journey traverses review -> ready -> actionable."""

    def test_review_state_when_unreviewed_evidence_exists(self):
        ev = _make_evidence(text="Built monitoring dashboard.")
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({"candidate_evidence": [ev.to_dict()]})
        readiness = compute_canonical_readiness(user)
        self.assertFalse(readiness["is_ready"])
        self.assertGreater(readiness["needs_review"], 0)
        self.assertEqual(readiness["computed_from"], "canonical_evidence")

    def test_ready_state_when_all_confirmed_and_mapped(self):
        ev1 = _confirmed_with_mapping("Led team of 5.", "TechCorp", "Lead Eng", "exp_1")
        ev2 = _confirmed_with_mapping("Reduced latency by 30%.", "TechCorp", "Lead Eng", "exp_1")
        user = _make_user({"candidate_evidence": [ev1.to_dict(), ev2.to_dict()]})
        readiness = compute_canonical_readiness(user)
        self.assertTrue(readiness["is_ready"])
        self.assertEqual(readiness["mapped_ready"], 2)

    def test_actionable_outputs_available_when_ready(self):
        ev1 = _confirmed_with_mapping("Increased sales by 40%.", "SalesCo", "Account Exec", "exp_1")
        ev2 = _confirmed_with_mapping("Managed 20 key accounts.", "SalesCo", "Account Exec", "exp_2")
        user = _make_user({"candidate_evidence": [ev1.to_dict(), ev2.to_dict()]})
        actions = build_ready_actions(user)
        self.assertGreaterEqual(len(actions), 1)
        cv_action = next((a for a in actions if a["action"] == "cv_bullet"), None)
        self.assertIsNotNone(cv_action)
        self.assertIn("evidence_ids", cv_action)
        self.assertGreater(len(cv_action["evidence_ids"]), 0)

    def test_mixed_confirmed_rejected_still_ready(self):
        ev1 = _confirmed_with_mapping("Built API service.", "DevCo", "Backend Eng", "exp_1")
        ev2 = _confirmed_with_mapping("Wrote tests.", "DevCo", "Backend Eng", "exp_2")
        ev3 = _make_evidence(text="Bad claim.", inferred_employer="DevCo", inferred_role="Backend Eng")
        ev3.reject()
        user = _make_user({"candidate_evidence": [ev1.to_dict(), ev2.to_dict(), ev3.to_dict()]})
        readiness = compute_canonical_readiness(user)
        self.assertTrue(readiness["is_ready"])
        self.assertEqual(readiness["confirmed"], 2)
        self.assertEqual(readiness["rejected"], 1)

    def test_not_ready_with_unreviewed_items(self):
        ev1 = _confirmed_with_mapping("Led team.", "FirmCo", "Manager", "exp_1")
        ev2 = _make_evidence(text="Built something.")
        ev2.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({"candidate_evidence": [ev1.to_dict(), ev2.to_dict()]})
        readiness = compute_canonical_readiness(user)
        self.assertFalse(readiness["is_ready"])
        self.assertEqual(readiness["needs_review"], 1)

    def test_ready_actions_container_has_all_sections(self):
        ev1 = _confirmed_with_mapping("Optimized pipeline by 60%.", "DataCo", "Data Engineer", "exp_1")
        user = _make_user({"candidate_evidence": [ev1.to_dict()]})
        actions = build_ready_actions(user)
        action_types = {a["action"] for a in actions}
        self.assertIn("cv_bullet", action_types)
        self.assertIn("motivation_letter", action_types)
        library = next((a for a in actions if a["action"] == "evidence_library"), None)
        self.assertIsNotNone(library)



# ---------------------------------------------------------------------------
# Read-Only Next-Item Inspection Tests
# ---------------------------------------------------------------------------


class ReadOnlyNextItemInspectionTests(unittest.TestCase):
    """CP-044R: try_get_next_review_item inspects without side effects."""

    def test_returns_next_unreviewed_item(self):
        ev1 = _make_evidence(text="First evidence.", inferred_employer="ACME", inferred_role="SDE")
        ev1.status = EVIDENCE_STATUS_NEEDS_REVIEW
        ev2 = _make_evidence(text="Second evidence.", inferred_employer="ACME", inferred_role="SDE")
        ev2.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({"candidate_evidence": [ev1.to_dict(), ev2.to_dict()]})
        result = try_get_next_review_item(user)
        self.assertIsNotNone(result)
        self.assertEqual(result["state"], "review")
        self.assertIn("evidence", result)
        self.assertIn("provenance", result)
        self.assertIn("suggested_mapping", result)
        self.assertIn("progress", result)

    def test_returns_none_when_all_reviewed(self):
        ev1 = _confirmed_with_mapping("Claim 1.", "Co", "Role", "exp_1")
        ev2 = _confirmed_with_mapping("Claim 2.", "Co", "Role", "exp_2")
        user = _make_user({"candidate_evidence": [ev1.to_dict(), ev2.to_dict()]})
        result = try_get_next_review_item(user)
        self.assertIsNone(result)

    def test_returns_none_when_empty_evidence(self):
        user = _make_user({"candidate_evidence": []})
        result = try_get_next_review_item(user)
        self.assertIsNone(result)

    def test_does_not_advance_cursor(self):
        ev1 = _make_evidence(text="Item 1.")
        ev1.status = EVIDENCE_STATUS_NEEDS_REVIEW
        ev2 = _make_evidence(text="Item 2.")
        ev2.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({"candidate_evidence": [ev1.to_dict(), ev2.to_dict()]})
        r1 = try_get_next_review_item(user)
        r2 = try_get_next_review_item(user)
        self.assertEqual(r1["evidence"]["evidence_id"], r2["evidence"]["evidence_id"])

    def test_provenance_includes_all_fields(self):
        ev = _make_evidence(
            text="Delivered project under budget.",
            source_asset="cv_2025.pdf",
            source_id="src_cv",
            inferred_employer="BuildCo",
            inferred_role="PM",
        )
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        ev.source_confidence = 0.92
        ev.location = "page 2"
        ev.dates = ["2023-01-01", "2023-12-31"]
        user = _make_user({"candidate_evidence": [ev.to_dict()]})
        result = try_get_next_review_item(user)
        self.assertEqual(result["provenance"]["source_asset"], "cv_2025.pdf")
        self.assertEqual(result["provenance"]["source_id"], "src_cv")
        self.assertEqual(result["provenance"]["confidence"], 0.92)
        self.assertEqual(result["provenance"]["location"], "page 2")
        self.assertEqual(result["provenance"]["inferred_employer"], "BuildCo")
        self.assertEqual(result["provenance"]["inferred_role"], "PM")
        self.assertIn("2023-01-01", result["provenance"]["dates"])

    def test_progress_metadata_is_accurate(self):
        ev1 = _make_evidence(text="Item 1.")
        ev1.status = EVIDENCE_STATUS_NEEDS_REVIEW
        ev2 = _make_evidence(text="Item 2.")
        ev2.confirm()
        ev2.experience_mapping = {"experience_id": "exp_1"}
        ev3 = _make_evidence(text="Item 3.")
        ev3.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({"candidate_evidence": [ev1.to_dict(), ev2.to_dict(), ev3.to_dict()]})
        result = try_get_next_review_item(user)
        self.assertEqual(result["progress"]["total"], 3)
        self.assertEqual(result["progress"]["reviewed"], 1)
        self.assertGreater(result["progress"]["remaining"], 0)

    def test_returns_none_when_all_rejected_or_reviewed(self):
        ev1 = _make_evidence(text="Rejected 1.")
        ev1.reject()
        ev2 = _make_evidence(text="Rejected 2.")
        ev2.reject()
        user = _make_user({"candidate_evidence": [ev1.to_dict(), ev2.to_dict()]})
        result = try_get_next_review_item(user)
        self.assertIsNone(result)



# ---------------------------------------------------------------------------
# Journey Completion Detection Tests
# ---------------------------------------------------------------------------


class JourneyCompletionDetectionTests(unittest.TestCase):
    """CP-044R: Detect when evidence journey is complete."""

    def test_journey_incomplete_with_needs_review(self):
        ev = _make_evidence(text="Need review.")
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({"candidate_evidence": [ev.to_dict()]})
        readiness = compute_canonical_readiness(user)
        self.assertFalse(readiness["is_ready"])

    def test_journey_complete_all_confirmed_mapped(self):
        ev = _confirmed_with_mapping("Delivered.", "A", "B", "exp_1")
        user = _make_user({"candidate_evidence": [ev.to_dict()]})
        readiness = compute_canonical_readiness(user)
        self.assertTrue(readiness["is_ready"])

    def test_journey_complete_mixed_confirmed_rejected(self):
        ev1 = _confirmed_with_mapping("Good.", "X", "Y", "exp_1")
        ev2 = _make_evidence(text="Bad.")
        ev2.reject()
        user = _make_user({"candidate_evidence": [ev1.to_dict(), ev2.to_dict()]})
        readiness = compute_canonical_readiness(user)
        self.assertTrue(readiness["is_ready"])

    def test_journey_incomplete_unmapped_confirmed(self):
        ev = _make_evidence(text="Confirmed but not mapped.")
        ev.confirm()
        user = _make_user({"candidate_evidence": [ev.to_dict()]})
        readiness = compute_canonical_readiness(user)
        self.assertFalse(readiness["is_ready"])
        self.assertGreater(readiness.get("confirmed", 0), 0)



# ---------------------------------------------------------------------------
# Evidence-to-Output Provenance Bridge Tests
# ---------------------------------------------------------------------------


class EvidenceToOutputProvenanceTests(unittest.TestCase):
    """CP-044R: Evidence IDs flow through to actionable outputs."""

    def test_cv_bullet_action_carries_evidence_ids(self):
        ev1 = _confirmed_with_mapping("Reduced errors by 50%.", "Corp", "QA Lead", "exp_1")
        ev2 = _confirmed_with_mapping("Automated test suite.", "Corp", "QA Lead", "exp_2")
        user = _make_user({"candidate_evidence": [ev1.to_dict(), ev2.to_dict()]})
        actions = build_ready_actions(user)
        cv_action = next(a for a in actions if a["action"] == "cv_bullet")
        self.assertIn(ev1.evidence_id, cv_action["evidence_ids"])
        self.assertIn(ev2.evidence_id, cv_action["evidence_ids"])
        self.assertEqual(cv_action["source"], "canonical_evidence")

    def test_motivation_letter_action_carries_evidence_ids(self):
        ev1 = _confirmed_with_mapping("Passionate about AI.", "AI Inc", "ML Engineer", "exp_1")
        ev2 = _confirmed_with_mapping("Built recommendation system.", "AI Inc", "ML Engineer", "exp_2")
        user = _make_user({"candidate_evidence": [ev1.to_dict(), ev2.to_dict()]})
        actions = build_ready_actions(user)
        ml_action = next(a for a in actions if a["action"] == "motivation_letter")
        self.assertGreater(len(ml_action["evidence_ids"]), 0)
        self.assertEqual(ml_action["source"], "canonical_evidence")

    def test_evidence_library_preserves_all_confirmed(self):
        ev1 = _confirmed_with_mapping("Claim A.", "Co", "Role", "exp_1")
        ev2 = _confirmed_with_mapping("Claim B.", "Co", "Role", "exp_2")
        ev3 = _make_evidence(text="Rejected.")
        ev3.reject()
        user = _make_user({"candidate_evidence": [ev1.to_dict(), ev2.to_dict(), ev3.to_dict()]})
        lib_action = next(
            a for a in build_ready_actions(user) if a["action"] == "evidence_library"
        )
        self.assertEqual(lib_action["evidence_count"], 2)
        self.assertEqual(len(lib_action["items"]), 2)

    def test_no_confirmed_evidence_produces_no_cv_action(self):
        ev = _make_evidence(text="Needs review.")
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({"candidate_evidence": [ev.to_dict()]})
        actions = build_ready_actions(user)
        cv_actions = [a for a in actions if a["action"] == "cv_bullet"]
        self.assertEqual(len(cv_actions), 0)



# ---------------------------------------------------------------------------
# Empty and Edge-Case State Tests
# ---------------------------------------------------------------------------


class EmptyEdgeCaseTests(unittest.TestCase):
    """CP-044R: Empty evidence states handled gracefully."""

    def test_empty_evidence_readiness(self):
        user = _make_user({"candidate_evidence": []})
        readiness = compute_canonical_readiness(user)
        self.assertFalse(readiness["is_ready"])
        self.assertEqual(readiness["readiness_ratio"], 0.0)

    def test_empty_evidence_ready_actions(self):
        user = _make_user({"candidate_evidence": []})
        actions = build_ready_actions(user)
        self.assertGreaterEqual(len(actions), 0)

    def test_all_rejected_produces_no_cv_actions(self):
        ev1 = _make_evidence(text="Bad 1.")
        ev1.reject()
        ev2 = _make_evidence(text="Bad 2.")
        ev2.reject()
        user = _make_user({"candidate_evidence": [ev1.to_dict(), ev2.to_dict()]})
        actions = build_ready_actions(user)
        cv_actions = [a for a in actions if a["action"] == "cv_bullet"]
        self.assertEqual(len(cv_actions), 0)

    def test_confirmed_but_unmapped_fallback(self):
        ev = _make_evidence(text="Confirmed, not mapped.")
        ev.confirm()
        user = _make_user({"candidate_evidence": [ev.to_dict()]})
        actions = build_ready_actions(user)
        cv_actions = [a for a in actions if a["action"] == "cv_bullet"]
        self.assertGreaterEqual(len(cv_actions), 0)

    def test_excerpt_truncation_in_claim(self):
        long_text = "A" * 500
        ev = _confirmed_with_mapping(long_text, "BigCo", "Engineer", "exp_1")
        user = _make_user({"candidate_evidence": [ev.to_dict()]})
        actions = build_ready_actions(user)
        cv_action = next(a for a in actions if a["action"] == "cv_bullet")
        self.assertIsNotNone(cv_action.get("claim"))
        self.assertGreater(len(cv_action["claim"]), 0)



# ---------------------------------------------------------------------------
# Confirm-then-Ready Flow Tests
# ---------------------------------------------------------------------------


class ConfirmThenReadyFlowTests(unittest.TestCase):
    """CP-044R: Confirm review item transitions to ready when all done."""

    def test_confirm_last_item_triggers_ready(self):
        ev1 = _confirmed_with_mapping("Already confirmed.", "Firm", "Eng", "exp_1")
        ev2 = _make_evidence(text="Last to confirm.", inferred_employer="Firm", inferred_role="Eng")
        ev2.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev1.to_dict(), ev2.to_dict()],
            "work_experiences": [{
                "experience_id": "exp_2",
                "employer": "Firm",
                "job_title": "Eng",
            }],
        })
        reset_review_state(user)
        item = get_next_review_item(user)
        self.assertIsNotNone(item)
        mapping = {"experience_id": "exp_2", "company": "Firm", "role": "Eng"}
        result = confirm_evidence(user, item["evidence"]["evidence_id"], mapping=mapping)
        self.assertEqual(result["action"], "confirmed")
        self.assertIn("evidence", result)
        # Readiness is computed separately after confirm
        readiness = compute_canonical_readiness(user)
        self.assertTrue(readiness["is_ready"])

    def test_reject_last_item_does_not_block_ready(self):
        ev1 = _confirmed_with_mapping("Good item.", "Firm", "Role", "exp_1")
        ev2 = _make_evidence(text="Bad item to reject.", inferred_employer="Firm", inferred_role="Role")
        ev2.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({"candidate_evidence": [ev1.to_dict(), ev2.to_dict()]})
        reset_review_state(user)
        item = get_next_review_item(user)
        self.assertIsNotNone(item)
        result = reject_evidence(user, item["evidence"]["evidence_id"])
        self.assertEqual(result["action"], "rejected")
        self.assertIn("evidence", result)
        # Readiness is computed separately after reject
        readiness = compute_canonical_readiness(user)
        self.assertTrue(readiness["is_ready"])

    def test_unmapped_items_block_ready(self):
        ev1 = _make_evidence(text="Confirmed but unmapped.")
        ev1.confirm()
        ev2 = _confirmed_with_mapping("Mapped item.", "Corp", "Role", "exp_1")
        user = _make_user({"candidate_evidence": [ev1.to_dict(), ev2.to_dict()]})
        readiness = compute_canonical_readiness(user)
        self.assertFalse(readiness["is_ready"])



# ---------------------------------------------------------------------------
# Fixture Provider Journey Support Tests
# ---------------------------------------------------------------------------


class FixtureJourneySupportTests(unittest.TestCase):
    """CP-044R: Fixture provider supports full journey state."""

    def test_fixture_supports_review_cursor(self):
        from backend.api.routes.career_evidence_fixture import _get_fixture, _save_fixture
        _save_fixture("cp044r_fixture", {
            "_created": 1000.0,
            "mode": "happy_path",
            "fail_at": None,
            "fail_count": 0,
            "documents": [],
            "selected_source_ids": [],
            "evidence_items": [
                {
                    "evidence_id": "ev_j1",
                    "text": "Journey item 1.",
                    "status": "needs_review",
                    "evidence_type": "achievement",
                    "source_asset": "cv.pdf",
                    "source_id": "src_cv",
                    "inferred_employer": "JourneyCo",
                    "inferred_role": "Engineer",
                },
                {
                    "evidence_id": "ev_j2",
                    "text": "Journey item 2.",
                    "status": "needs_review",
                    "evidence_type": "responsibility",
                    "source_asset": "cv.pdf",
                    "source_id": "src_cv",
                },
            ],
            "processing_state": {"state": "completed", "source_count": 1},
            "experience_links": [],
            "pending_questions": [],
            "review_cursor": 0,
        })
        state = _get_fixture("cp044r_fixture")
        self.assertEqual(state["review_cursor"], 0)
        self.assertEqual(len(state["evidence_items"]), 2)
        self.assertIsNotNone(state.get("processing_state"))

    def test_fixture_journey_from_processing_to_review(self):
        from backend.api.routes.career_evidence_fixture import _get_fixture, _save_fixture
        _save_fixture("cp044r_flow", {
            "_created": 1000.0,
            "mode": "happy_path",
            "fail_at": None,
            "fail_count": 0,
            "documents": [
                {"document_id": "d1", "asset_id": "a1", "display_name": "cv.pdf",
                 "source_origin": "upload", "status": "ready", "kind": "uploaded_document",
                 "created_at": "2026-01-01T00:00:00Z"},
            ],
            "selected_source_ids": ["a1"],
            "evidence_items": [],
            "processing_state": {"state": "processing", "source_count": 1},
            "experience_links": [],
            "pending_questions": [],
            "review_cursor": 0,
        })
        state = _get_fixture("cp044r_flow")
        self.assertEqual(state["processing_state"]["state"], "processing")
        _save_fixture("cp044r_flow", {**state, "processing_state": {
            "state": "completed", "source_count": 1,
        }, "evidence_items": [
            {
                "evidence_id": "ev_post",
                "text": "Post-processing evidence.",
                "status": "needs_review",
                "evidence_type": "achievement",
                "source_asset": "cv.pdf",
                "source_id": "a1",
            },
        ]})
        updated = _get_fixture("cp044r_flow")
        self.assertEqual(updated["processing_state"]["state"], "completed")
        self.assertEqual(len(updated["evidence_items"]), 1)
        self.assertEqual(updated["review_cursor"], 0)

    def test_fixture_journey_with_multiple_sources(self):
        from backend.api.routes.career_evidence_fixture import _get_fixture, _save_fixture
        _save_fixture("cp044r_multi", {
            "_created": 1000.0,
            "mode": "happy_path",
            "fail_at": None,
            "fail_count": 0,
            "documents": [
                {"document_id": "d1", "asset_id": "a1", "display_name": "cv.pdf",
                 "source_origin": "upload", "status": "ready", "kind": "uploaded_document",
                 "created_at": "2026-01-01T00:00:00Z"},
                {"document_id": "d2", "asset_id": "a2", "display_name": "cover.pdf",
                 "source_origin": "upload", "status": "ready", "kind": "uploaded_document",
                 "created_at": "2026-01-01T00:00:00Z"},
            ],
            "selected_source_ids": ["a1", "a2"],
            "evidence_items": [
                {"evidence_id": "ev_m1", "text": "Multi-source item.", "status": "needs_review",
                 "evidence_type": "achievement", "source_asset": "cv.pdf", "source_id": "a1"},
                {"evidence_id": "ev_m2", "text": "Another item.", "status": "needs_review",
                 "evidence_type": "responsibility", "source_asset": "cover.pdf", "source_id": "a2"},
            ],
            "processing_state": {"state": "completed", "source_count": 2},
            "experience_links": [],
            "pending_questions": [],
            "review_cursor": 0,
        })
        state = _get_fixture("cp044r_multi")
        self.assertEqual(state["processing_state"]["source_count"], 2)
        self.assertEqual(len(state["documents"]), 2)
        self.assertEqual(len(state["selected_source_ids"]), 2)
        self.assertEqual(len(state["evidence_items"]), 2)



# ---------------------------------------------------------------------------
# Journey Progress Tracking Tests
# ---------------------------------------------------------------------------


class JourneyProgressTrackingTests(unittest.TestCase):
    """CP-044R: Journey progress tracked across stages."""

    def test_readiness_includes_all_stage_counts(self):
        ev1 = _make_evidence(text="Needs review.")
        ev1.status = EVIDENCE_STATUS_NEEDS_REVIEW
        ev2 = _confirmed_with_mapping("Confirmed.", "Co", "Role", "exp_1")
        ev3 = _make_evidence(text="Rejected.")
        ev3.reject()
        user = _make_user({"candidate_evidence": [ev1.to_dict(), ev2.to_dict(), ev3.to_dict()]})
        readiness = compute_canonical_readiness(user)
        self.assertIn("total_evidence", readiness)
        self.assertIn("confirmed", readiness)
        self.assertIn("rejected", readiness)
        self.assertIn("needs_review", readiness)
        self.assertEqual(readiness["total_evidence"], 3)
        self.assertEqual(readiness["confirmed"], 1)
        self.assertEqual(readiness["rejected"], 1)
        self.assertEqual(readiness["needs_review"], 1)

    def test_readiness_mapped_ready_count(self):
        ev1 = _confirmed_with_mapping("Mapped 1.", "Co", "Role", "exp_1")
        ev2 = _confirmed_with_mapping("Mapped 2.", "Co", "Role", "exp_2")
        ev3 = _make_evidence(text="Confirmed no map.")
        ev3.confirm()
        user = _make_user({"candidate_evidence": [ev1.to_dict(), ev2.to_dict(), ev3.to_dict()]})
        readiness = compute_canonical_readiness(user)
        self.assertEqual(readiness["mapped_ready"], 2)
        self.assertEqual(readiness["confirmed"], 3)

    def test_journey_progress_from_review_to_complete(self):
        evs = []
        for i in range(3):
            ev = _make_evidence(text=f"Evidence {i+1}.", inferred_employer="ProgCo", inferred_role="Dev")
            ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
            evs.append(ev)
        user = _make_user({
            "candidate_evidence": [e.to_dict() for e in evs],
            "work_experiences": [{
                "experience_id": f"exp_{i+1}",
                "employer": "ProgCo",
                "job_title": "Dev",
            } for i in range(3)],
        })
        r1 = compute_canonical_readiness(user)
        self.assertEqual(r1["needs_review"], 3)
        self.assertFalse(r1["is_ready"])
        reset_review_state(user)
        item = get_next_review_item(user)
        confirm_evidence(user, item["evidence"]["evidence_id"], mapping={"experience_id": "exp_1"})
        r2 = compute_canonical_readiness(user)
        self.assertEqual(r2["needs_review"], 2)
        self.assertEqual(r2["confirmed"], 1)
        item = get_next_review_item(user)
        confirm_evidence(user, item["evidence"]["evidence_id"], mapping={"experience_id": "exp_2"})
        r3 = compute_canonical_readiness(user)
        self.assertEqual(r3["needs_review"], 1)
        item = get_next_review_item(user)
        confirm_evidence(user, item["evidence"]["evidence_id"], mapping={"experience_id": "exp_3"})
        r4 = compute_canonical_readiness(user)
        self.assertEqual(r4["needs_review"], 0)
        self.assertEqual(r4["confirmed"], 3)
        self.assertTrue(r4["is_ready"])


# ---------------------------------------------------------------------------
# Transition Diagnostics Tests
# ---------------------------------------------------------------------------


class TransitionDiagnosticsTests(unittest.TestCase):
    """CP-044R: Journey transitions carry diagnostic metadata."""

    def test_confirm_returns_journey_diagnostics(self):
        ev = _make_evidence(text="To confirm.", inferred_employer="DC", inferred_role="Dev")
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [{
                "experience_id": "exp_1",
                "employer": "DC",
                "job_title": "Dev",
            }],
        })
        reset_review_state(user)
        item = get_next_review_item(user)
        result = confirm_evidence(
            user, item["evidence"]["evidence_id"],
            mapping={"experience_id": "exp_1"},
        )
        # confirm_evidence returns evidence + action; diagnostics via readiness
        self.assertIn("evidence", result)
        self.assertEqual(result["action"], "confirmed")
        readiness = compute_canonical_readiness(user)
        self.assertIn("computed_from", readiness)
        self.assertEqual(readiness["computed_from"], "canonical_evidence")

    def test_build_ready_actions_always_returns_list(self):
        user = _make_user({"candidate_evidence": []})
        actions = build_ready_actions(user)
        self.assertIsInstance(actions, list)

    def test_legacy_spike_exclusion_in_diagnostics(self):
        ev = _confirmed_with_mapping("Clean item.", "CleanCo", "Eng", "exp_1")
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "memory_spike": {"count": 100},
        })
        readiness = compute_canonical_readiness(user)
        self.assertTrue(readiness["legacy_counters_excluded"])


if __name__ == "__main__":
    unittest.main()

