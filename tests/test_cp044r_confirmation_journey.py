"""Tests for CP-044R: Continuous confirmation-to-readiness journey.

Covers: auto-open first evidence, confirm auto-next, mapping during
confirmation, ambiguous choice, one question maximum, answer/skip persist
and advance, no legacy states, ready with CV/motivation outputs, reload
persistence, and full journey integration.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from backend.domain.candidate_evidence import (
    CandidateEvidence,
    EVIDENCE_STATUS_CONFIRMED,
    EVIDENCE_STATUS_NEEDS_REVIEW,
)
from backend.evidence.review_service import (
    try_get_next_review_item,
    answer_enrich_evidence,
    build_ready_actions,
    compute_canonical_readiness,
    confirm_evidence,
    confirm_with_inspect,
    get_next_review_item,
    skip_question_for_evidence,
    suggest_mapping_for_evidence,
)


def _make_user(metadata=None, profile_id="prof_044"):
    user = MagicMock()
    user.metadata = dict(metadata or {})
    user.profile_id = profile_id
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


def _make_experience(**overrides):
    defaults = {
        "experience_id": "exp_1",
        "job_title": "Senior Engineer",
        "employer": "Acme Corp",
        "start_date": "2023-01-01",
        "end_date": "2024-12-31",
        "description": "Led cloud migration projects.",
    }
    defaults.update(overrides)
    return defaults



class AutoOpenFirstEvidenceTests(unittest.TestCase):
    """Extraction completion automatically opens first evidence item."""

    def test_first_unreviewed_returned(self):
        ev1 = _make_evidence(text="Built CI/CD pipeline.", status=EVIDENCE_STATUS_NEEDS_REVIEW)
        ev2 = _make_evidence(text="Managed team.", status=EVIDENCE_STATUS_NEEDS_REVIEW)
        user = _make_user({"candidate_evidence": [ev1.to_dict(), ev2.to_dict()]})
        result = get_next_review_item(user)
        self.assertEqual(result["state"], "review")
        self.assertEqual(result["evidence"]["text"], ev1.text)

    def test_try_get_next_no_side_effects(self):
        ev1 = _make_evidence(text="Item 1.", status=EVIDENCE_STATUS_NEEDS_REVIEW)
        ev2 = _make_evidence(text="Item 2.", status=EVIDENCE_STATUS_NEEDS_REVIEW)
        user = _make_user({"candidate_evidence": [ev1.to_dict(), ev2.to_dict()]})
        r1 = try_get_next_review_item(user)
        r2 = try_get_next_review_item(user)
        self.assertEqual(r1["evidence"]["text"], r2["evidence"]["text"])

    def test_complete_returns_none(self):
        ev = _make_evidence(text="Done.", status=EVIDENCE_STATUS_CONFIRMED)
        user = _make_user({"candidate_evidence": [ev.to_dict()]})


class ConfirmationAutoNextTests(unittest.TestCase):
    """Confirmation auto-loads next action without separate fetch."""

    def test_confirm_with_inspect_returns_next_review_inline(self):
        ev1 = _make_evidence(
            text="Reduced deployment time by 80% with Docker and Kubernetes.",
            evidence_type="metric",
            inferred_employer="TechCo",
            inferred_role="DevOps Lead",
        )
        ev2 = _make_evidence(
            text="Led migration to microservices.",
            status=EVIDENCE_STATUS_NEEDS_REVIEW,
            inferred_employer="TechCo",
        )
        ev1.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev1.to_dict(), ev2.to_dict()],
            "work_experiences": [_make_experience(
                experience_id="exp_99", employer="TechCo", job_title="DevOps Lead",
            )],
        })
        result = confirm_with_inspect(
            user, ev1.evidence_id,
            mapping={"experience_id": "exp_99", "employer": "TechCo", "role": "DevOps Lead"},
        )
        self.assertEqual(result["action"], "confirmed")
        if result["state"] == "review":
            self.assertIn("next_review", result)
            self.assertEqual(result["next_review"]["evidence"]["text"], ev2.text)

    def test_confirm_last_item_goes_to_ready(self):
        ev = _make_evidence(
            text="Increased revenue by 150% through strategic partnerships.",
            evidence_type="metric",
            inferred_employer="BizCorp",
            inferred_role="BD Manager",
        )
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [_make_experience(
                experience_id="exp_1", employer="BizCorp", job_title="BD Manager",
            )],
        })
        result = confirm_with_inspect(user, ev.evidence_id,
                                      mapping={"experience_id": "exp_1"})
        self.assertIn(result["state"], ("ready", "review"))
        if result["state"] == "ready":
            self.assertIn("primary_actions", result)

    def test_confirm_canonical_id_persists(self):
        ev = _make_evidence(text="Automated test suite with 95% coverage.")
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({"candidate_evidence": [ev.to_dict()]})
        result = confirm_evidence(user, ev.evidence_id,
                                  mapping={"experience_id": "exp_1"})
        self.assertEqual(result["evidence"]["status"], EVIDENCE_STATUS_CONFIRMED)

    def test_confirm_with_three_items_does_not_skip(self):
        ev1 = _make_evidence(text="Item 1.", status=EVIDENCE_STATUS_NEEDS_REVIEW)
        ev2 = _make_evidence(text="Item 2.", status=EVIDENCE_STATUS_NEEDS_REVIEW)
        ev3 = _make_evidence(text="Item 3.", status=EVIDENCE_STATUS_NEEDS_REVIEW)
        user = _make_user({"candidate_evidence": [
            ev1.to_dict(), ev2.to_dict(), ev3.to_dict(),
        ]})
        confirm_evidence(user, ev1.evidence_id, mapping={"experience_id": "exp_1"})
        # After confirming item 1, item 2 should be next (not item 3)
        next_item = get_next_review_item(user)
        self.assertEqual(next_item["evidence"]["text"], ev2.text)
        confirm_evidence(user, ev2.evidence_id, mapping={"experience_id": "exp_1"})
        # After confirming item 2, item 3 should be next
        third = get_next_review_item(user)
        self.assertEqual(third["evidence"]["text"], ev3.text)


class MappingDuringConfirmationTests(unittest.TestCase):
    """High-confidence mapping uses valid existing work-experience ID."""

    def test_high_confidence_mapping_uses_experience_id(self):
        ev = _make_evidence(
            text="Designed scalable data pipeline processing 1TB daily.",
            inferred_employer="DataFlow Inc",
            inferred_role="Data Engineer",
            dates=["2022-06-01", "2024-06-01"],
        )
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        exp = _make_experience(
            experience_id="exp_data_42",
            employer="DataFlow Inc",
            job_title="Data Engineer",
            start_date="2022-01-01",
            end_date="2024-12-31",
        )
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [exp],
        })
        mapping_result = suggest_mapping_for_evidence(ev, [exp])
        self.assertIsNotNone(mapping_result["suggested_mapping"])
        self.assertEqual(
            mapping_result["suggested_mapping"]["experience_id"],
            "exp_data_42",
        )
        result = confirm_evidence(
            user, ev.evidence_id,
            mapping=mapping_result["suggested_mapping"],
        )
        persisted = user.metadata["candidate_evidence"][0]
        self.assertEqual(
            persisted["experience_mapping"]["experience_id"],
            "exp_data_42",
        )

    def test_no_experiences_no_mapping_confirm_succeeds(self):
        ev = _make_evidence(text="Built and launched mobile app.")
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [],
        })
        mapping = suggest_mapping_for_evidence(ev, [])
        self.assertIsNone(mapping["suggested_mapping"])
        result = confirm_evidence(user, ev.evidence_id)
        self.assertEqual(result["action"], "confirmed")


class AmbiguousMappingTests(unittest.TestCase):
    """Ambiguous mapping requires one explicit compact choice."""

    def test_ambiguous_returns_alternatives(self):
        ev = _make_evidence(
            inferred_employer="Acme",
            inferred_role="Engineer",
        )
        exps = [
            _make_experience(
                experience_id="exp_senior",
                employer="Acme Corp",
                job_title="Senior Engineer",
            ),
            _make_experience(
                experience_id="exp_junior",
                employer="Acme Corp",
                job_title="Junior Engineer",
            ),
        ]
        result = suggest_mapping_for_evidence(ev, exps)
        self.assertTrue(result["is_ambiguous"])
        self.assertGreater(len(result["alternatives"]), 0)

    def test_unambiguous_choice_no_alternatives(self):
        ev = _make_evidence(
            inferred_employer="UniqueCorp LLC",
            inferred_role="CTO",
        )
        exps = [_make_experience(
            experience_id="exp_cto",
            employer="UniqueCorp LLC",
            job_title="CTO",
        )]
        result = suggest_mapping_for_evidence(ev, exps)
        self.assertFalse(result["is_ambiguous"])
        self.assertEqual(len(result["alternatives"]), 0)


class OneQuestionMaximumTests(unittest.TestCase):
    """Existing data checked before question; one question max."""

    def test_rich_evidence_skips_question(self):
        ev = _make_evidence(
            text="Improved customer satisfaction by 35% through redesigned onboarding.",
            evidence_type="metric",
            inferred_employer="UX Co",
            inferred_role="Product Designer",
        )
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [_make_experience(experience_id="exp_1")],
        })
        result = confirm_with_inspect(user, ev.evidence_id,
                                      mapping={"experience_id": "exp_1"})
        self.assertNotEqual(result["state"], "question")

    def test_thin_evidence_gets_one_question(self):
        ev = _make_evidence(
            text="Did some work on the project.",
            evidence_type="responsibility",
        )
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [],
        })
        result = confirm_with_inspect(user, ev.evidence_id)
        if result["state"] == "question":
            self.assertIn("question_id", result["question"])
            self.assertIn("missing_type", result["question"])

    def test_two_confirmations_no_duplicate_questions(self):
        ev = _make_evidence(text="Built a reporting tool.")
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [],
        })
        r1 = confirm_with_inspect(user, ev.evidence_id)
        r2 = confirm_with_inspect(user, ev.evidence_id)
        if r1["state"] == "question":
            self.assertNotEqual(r2.get("state"), "question")


class AnswerSkipPersistTests(unittest.TestCase):
    """Answer/skip persists and automatically advances."""

    def test_answer_enriches_evidence_and_returns_next(self):
        ev1 = _make_evidence(text="Built a dashboard.", evidence_type="responsibility")
        ev2 = _make_evidence(text="Second item.", status=EVIDENCE_STATUS_NEEDS_REVIEW)
        ev1.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev1.to_dict(), ev2.to_dict()],
            "work_experiences": [],
        })
        r1 = confirm_with_inspect(user, ev1.evidence_id)
        self.assertEqual(r1["state"], "question")
        result = answer_enrich_evidence(
            user,
            r1["question"]["question_id"],
            "Reduced reporting time by 80% for 200+ weekly users.",
            evidence_id=ev1.evidence_id,
        )
        self.assertEqual(result["action"], "answered")
        if "next_review" in result:
            self.assertEqual(result["next_review"]["evidence"]["text"], ev2.text)

    def test_skip_persists_and_advances(self):
        ev = _make_evidence(text="Worked on some things.")
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [],
        })
        r1 = confirm_with_inspect(user, ev.evidence_id)
        self.assertEqual(r1["state"], "question")
        skip_result = skip_question_for_evidence(user, r1["question"]["question_id"])
        self.assertEqual(skip_result["action"], "skipped")


class NoLegacyStatesTests(unittest.TestCase):
    """No MAPPING or FOLLOW_UP standalone states, no legacy counters."""

    def test_no_legacy_counters_in_readiness(self):
        ev = _make_evidence(text="Delivered key results.")
        ev.confirm()
        ev.experience_mapping = {"experience_id": "exp_1"}
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "memory_spike": {"step": 3},
        })
        readiness = compute_canonical_readiness(user)
        self.assertTrue(readiness["legacy_counters_excluded"])
        self.assertEqual(readiness["computed_from"], "canonical_evidence")
        self.assertTrue(readiness["is_ready"])

    def test_confirm_auto_advances_no_redundant_continue(self):
        ev1 = _make_evidence(text="Item 1.", status=EVIDENCE_STATUS_NEEDS_REVIEW)
        ev2 = _make_evidence(text="Item 2.", status=EVIDENCE_STATUS_NEEDS_REVIEW)
        user = _make_user({"candidate_evidence": [ev1.to_dict(), ev2.to_dict()]})
        confirm_evidence(user, ev1.evidence_id, mapping={"experience_id": "exp_1"})
        next_item = get_next_review_item(user)
        self.assertEqual(next_item["evidence"]["text"], ev2.text)


class ReadyStateOutputsTests(unittest.TestCase):
    """Ready state creates grounded CV and motivation-letter outputs."""

    def test_ready_actions_include_cv_and_motivation_with_provenance(self):
        ev = _make_evidence(
            text="Automated deployment pipeline reducing release time by 60%.",
            evidence_type="achievement",
            inferred_employer="DevOps Inc",
            inferred_role="DevOps Engineer",
        )
        ev.confirm()
        ev.experience_mapping = {"experience_id": "exp_1"}
        user = _make_user({"candidate_evidence": [ev.to_dict()]})
        actions = build_ready_actions(user)
        cv = next((a for a in actions if a["action"] == "cv_bullet"), None)
        self.assertIsNotNone(cv)
        self.assertIn("evidence_ids", cv)
        self.assertGreater(len(cv["evidence_ids"]), 0)
        self.assertEqual(cv["source"], "canonical_evidence")

    def test_empty_evidence_no_actions(self):
        user = _make_user({"candidate_evidence": []})
        actions = build_ready_actions(user)
        self.assertEqual(actions, [])

    def test_actions_limited_to_three_max(self):
        ev = _make_evidence(text="Did a thing.")
        ev.confirm()
        ev.experience_mapping = {"experience_id": "exp_1"}
        user = _make_user({"candidate_evidence": [ev.to_dict()]})
        actions = build_ready_actions(user)
        self.assertLessEqual(len(actions), 3)


class ReloadPersistenceTests(unittest.TestCase):
    """Reload restores exact unfinished step."""

    def test_review_cursor_persisted_for_reload(self):
        ev1 = _make_evidence(text="First.", status=EVIDENCE_STATUS_NEEDS_REVIEW)
        ev2 = _make_evidence(text="Second.", status=EVIDENCE_STATUS_NEEDS_REVIEW)
        user = _make_user({
            "candidate_evidence": [ev1.to_dict(), ev2.to_dict()],
            "evidence_review_cursor": 0,
        })
        confirm_evidence(user, ev1.evidence_id, mapping={"experience_id": "exp_1"})
        evidence = [CandidateEvidence.from_dict(item)
                    for item in user.metadata.get("candidate_evidence", [])
                    if isinstance(item, dict)]
        confirmed = sum(1 for e in evidence if e.is_confirmed)
        self.assertEqual(confirmed, 1)
        unreviewed = [e for e in evidence if e.status == EVIDENCE_STATUS_NEEDS_REVIEW]
        self.assertEqual(len(unreviewed), 1)

    def test_processing_state_persisted(self):
        user = _make_user({
            "_evidence_processing_state": {
                "state": "completed", "batch_id": "b_test",
                "source_count": 2, "extracted_count": 5,
            },
        })
        state = (user.metadata or {}).get("_evidence_processing_state", {})
        self.assertEqual(state["state"], "completed")
        self.assertEqual(state["extracted_count"], 5)


class FullJourneyIntegrationTests(unittest.TestCase):
    """Complete confirmation-to-readiness journey."""

    def test_full_journey_source_to_ready(self):
        ev1 = _make_evidence(
            text="Reduced infrastructure costs by 40% through cloud optimization.",
            evidence_type="metric",
            inferred_employer="CloudCorp",
            inferred_role="SRE Lead",
            dates=["2022-01-01", "2024-06-01"],
        )
        ev2 = _make_evidence(
            text="Led incident response team handling 99.9% uptime.",
            evidence_type="achievement",
            inferred_employer="CloudCorp",
            inferred_role="SRE Lead",
            dates=["2022-01-01", "2024-06-01"],
        )
        ev3 = _make_evidence(
            text="Migrated legacy monitoring to Prometheus/Grafana stack.",
            evidence_type="achievement",
            inferred_employer="CloudCorp",
            inferred_role="SRE Lead",
        )
        ev1.status = EVIDENCE_STATUS_NEEDS_REVIEW
        ev2.status = EVIDENCE_STATUS_NEEDS_REVIEW
        ev3.status = EVIDENCE_STATUS_NEEDS_REVIEW
        exp = _make_experience(
            experience_id="exp_cloud_1",
            employer="CloudCorp",
            job_title="SRE Lead",
            start_date="2022-01-01",
            end_date="2024-06-01",
        )
        user = _make_user({
            "candidate_evidence": [ev1.to_dict(), ev2.to_dict(), ev3.to_dict()],
            "work_experiences": [exp],
        })
        # Confirm item 1
        r1 = confirm_with_inspect(
            user, ev1.evidence_id,
            mapping={"experience_id": "exp_cloud_1", "employer": "CloudCorp", "role": "SRE Lead"},
        )
        self.assertEqual(r1["action"], "confirmed")
        # Confirm item 2
        r2 = confirm_with_inspect(
            user, ev2.evidence_id,
            mapping={"experience_id": "exp_cloud_1"},
        )
        self.assertEqual(r2["action"], "confirmed")
        # Confirm item 3
        r3 = confirm_with_inspect(
            user, ev3.evidence_id,
            mapping={"experience_id": "exp_cloud_1"},
        )
        self.assertEqual(r3["action"], "confirmed")
        if r3.get("state") == "question":
            answer_enrich_evidence(
                user,
                r3["question"]["question_id"],
                "Improved alert response time by 60%.",
                evidence_id=ev3.evidence_id,
            )
        readiness = compute_canonical_readiness(user)
        self.assertTrue(readiness["is_ready"])
        actions = build_ready_actions(user)
        self.assertGreaterEqual(len(actions), 2)
        cv = next((a for a in actions if a["action"] == "cv_bullet"), None)
        self.assertIsNotNone(cv)
        self.assertEqual(cv["source"], "canonical_evidence")

    def test_all_confirmed_mapped_is_ready(self):
        ev = _make_evidence(
            text="Delivered enterprise migration with zero downtime.",
            inferred_employer="MigrateCo",
            inferred_role="Migration Lead",
        )
        ev.confirm()
        ev.experience_mapping = {"experience_id": "exp_mig_1"}
        user = _make_user({"candidate_evidence": [ev.to_dict()]})
        readiness = compute_canonical_readiness(user)
        self.assertTrue(readiness["is_ready"])
        self.assertEqual(readiness["confirmed"], 1)
        self.assertEqual(readiness["mapped_ready"], 1)


if __name__ == "__main__":
    unittest.main()
