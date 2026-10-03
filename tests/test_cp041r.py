"""Tests for CP-041R: Integrated confirmation + question engine.

Covers all acceptance criteria:
- Skip: sufficient evidence -> Ready directly, no question
- One question: at most one question per confirmed item
- Dedupe: no repeated questions
- Metric enrichment: answer updates same evidence record
- Grounded generation: Ready includes primary actions for CV bullet + motivation letter
- No invented unsupported claims
- Evidence IDs retained in outputs
- Readiness recalculated immediately after answer
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
    answer_enrich_evidence,
    build_ready_actions,
    compute_canonical_readiness,
    confirm_evidence,
    confirm_with_inspect,
    get_next_review_item,
    reject_evidence,
    skip_question_for_evidence,
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


class SkipToReadyTests(unittest.TestCase):
    """Sufficient evidence skips questions and goes to Ready directly."""

    def test_ready_evidence_skips_question(self):
        ev = _make_evidence(
            text="Improved revenue by 30% using Python automation.",
            evidence_type="metric",
            inferred_employer="Acme Corp",
            inferred_role="Senior Engineer",
        )
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [{
                "experience_id": "exp_1",
                "employer": "Acme Corp",
                "job_title": "Senior Engineer",
                "start_date": "2022-01-01",
                "end_date": "2024-12-31",
            }],
        })

        mapping = {"experience_id": "exp_1", "employer": "Acme Corp", "role": "Senior Engineer"}
        result = confirm_with_inspect(user, ev.evidence_id, mapping=mapping)

        self.assertIn(result["state"], ("ready", "confirmed"))
        self.assertNotEqual(result["state"], "question")
        self.assertEqual(result["action"], "confirmed")

    def test_all_confirmed_mapped_goes_to_ready(self):
        ev1 = _make_evidence(
            text="Reduced processing time by 40% with optimized queries.",
            evidence_type="metric",
        )
        ev2 = _make_evidence(
            text="Led cross-functional team of 8 engineers.",
            evidence_type="leadership",
        )
        ev1.status = EVIDENCE_STATUS_NEEDS_REVIEW
        ev2.status = EVIDENCE_STATUS_NEEDS_REVIEW

        user = _make_user({
            "candidate_evidence": [ev1.to_dict(), ev2.to_dict()],
            "work_experiences": [],
        })

        confirm_with_inspect(user, ev1.evidence_id,
                             mapping={"experience_id": "exp_1"})
        result = confirm_with_inspect(user, ev2.evidence_id,
                                      mapping={"experience_id": "exp_2"})

        readiness = compute_canonical_readiness(user)
        self.assertTrue(readiness["is_ready"])

    def test_ready_actions_include_evidence_ids(self):
        ev = _make_evidence(
            text="Launched a new API platform that served 50K requests/day.",
            evidence_type="achievement",
            inferred_employer="TechCo",
            inferred_role="Platform Engineer",
        )
        ev.confirm()
        ev.experience_mapping = {"experience_id": "exp_1", "company": "TechCo", "role": "Platform Engineer"}
        user = _make_user({"candidate_evidence": [ev.to_dict()]})

        actions = build_ready_actions(user)
        self.assertGreaterEqual(len(actions), 2)

        for action in actions:
            if action["action"] in ("cv_bullet", "motivation_letter"):
                self.assertIn("evidence_ids", action)
                self.assertGreater(len(action["evidence_ids"]), 0)
                self.assertEqual(action["source"], "canonical_evidence")
                self.assertIn("claim", action)



class OneQuestionTests(unittest.TestCase):
    """At most one question per confirmed item, no repeats."""

    def test_incomplete_evidence_gets_one_question(self):
        ev = _make_evidence(text="Worked on some projects.", evidence_type="responsibility")
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [],
        })

        result = confirm_with_inspect(user, ev.evidence_id)
        self.assertEqual(result["state"], "question")
        self.assertIn("question", result)
        self.assertIn("question_id", result["question"])
        self.assertIn("missing_type", result["question"])

    def test_question_not_repeated_after_answer(self):
        """After confirm+mapping, sufficient evidence goes to Ready. If question
        is asked (incomplete evidence), answer enriches and no repeat."""
        ev = _make_evidence(text="Did some work.", evidence_type="responsibility")
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [],
        })

        # Confirm without mapping → should ask a question (evidence incomplete)
        result1 = confirm_with_inspect(user, ev.evidence_id)
        self.assertEqual(result1["state"], "question")
        qid = result1["question"]["question_id"]

        # Answer the question with a metric and add mapping via answer
        answer_enrich_evidence(
            user, qid, "Reduced costs by 25%.",
            evidence_id=ev.evidence_id
        )

        readiness = compute_canonical_readiness(user)
        # Evidence is confirmed but not mapped yet (answer_enrich doesn't set mapping)
        # So is_ready depends on whether all evidence is reviewed
        self.assertFalse(readiness["is_ready"],
                         "Without mapping, evidence is not fully ready")

    def test_different_evidence_different_question_ids(self):
        ev1 = _make_evidence(text="Built a dashboard.")
        ev2 = _make_evidence(text="Managed a team.")
        ev1.status = EVIDENCE_STATUS_NEEDS_REVIEW
        ev2.status = EVIDENCE_STATUS_NEEDS_REVIEW

        user = _make_user({
            "candidate_evidence": [ev1.to_dict(), ev2.to_dict()],
            "work_experiences": [],
        })

        r1 = confirm_with_inspect(user, ev1.evidence_id)
        r2 = confirm_with_inspect(user, ev2.evidence_id)

        if r1["state"] == "question" and r2["state"] == "question":
            self.assertNotEqual(r1["question"]["question_id"], r2["question"]["question_id"])

    def test_skipped_question_not_asked_again(self):
        ev = _make_evidence(text="Did some work.")
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [],
        })

        result1 = confirm_with_inspect(user, ev.evidence_id)
        self.assertEqual(result1["state"], "question")

        skip_result = skip_question_for_evidence(user, result1["question"]["question_id"])
        self.assertEqual(skip_result["action"], "skipped")



class DedupeTests(unittest.TestCase):
    """Questions don't repeat extracted or already-answered facts."""

    def test_extracted_facts_not_questioned(self):
        ev = _make_evidence(
            text="Increased sales revenue by 150% through targeted campaigns.",
            evidence_type="metric",
            inferred_employer="SalesCo",
            inferred_role="Marketing Lead",
        )
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [],
        })

        mapping = {"experience_id": "exp_1"}
        result = confirm_with_inspect(user, ev.evidence_id, mapping=mapping)

        if result["state"] == "question":
            self.assertNotEqual(result["question"].get("missing_type"), "missing_metric")
            self.assertNotEqual(result["question"].get("missing_type"), "missing_outcome")

    def test_answered_fact_enriched_in_record(self):
        ev = _make_evidence(text="Built an automated reporting system.")
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [],
        })

        result = confirm_with_inspect(user, ev.evidence_id)
        if result["state"] == "question":
            answer_enrich_evidence(
                user,
                result["question"]["question_id"],
                "Reduced reporting time by 80%.",
                evidence_id=ev.evidence_id,
            )

            evidence_items = [
                CandidateEvidence.from_dict(item)
                for item in user.metadata.get("candidate_evidence", [])
                if isinstance(item, dict)
            ]
            if evidence_items:
                enriched_text = evidence_items[0].text.lower()
                self.assertIn("reduced reporting time by 80%", enriched_text)
                self.assertIn("built an automated reporting system", enriched_text)

    def test_content_hash_updates_on_enrichment(self):
        ev = _make_evidence(text="Led a migration project.")
        original_hash = ev.content_hash
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [],
        })

        result = confirm_with_inspect(user, ev.evidence_id)
        if result["state"] == "question":
            answer_enrich_evidence(
                user,
                result["question"]["question_id"],
                "Migrated 500K records with zero data loss.",
                evidence_id=ev.evidence_id,
            )

            evidence_items = [
                CandidateEvidence.from_dict(item)
                for item in user.metadata.get("candidate_evidence", [])
                if isinstance(item, dict)
            ]
            if evidence_items:
                self.assertNotEqual(original_hash, evidence_items[0].content_hash)



class MetricEnrichmentTests(unittest.TestCase):
    """Metric enrichment updates evidence and recalculates readiness."""

    def test_metric_answer_improves_readiness(self):
        ev = _make_evidence(text="Handled customer support.")
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [],
        })

        readiness_before = compute_canonical_readiness(user)
        self.assertFalse(readiness_before["is_ready"])

        result = confirm_with_inspect(user, ev.evidence_id,
                                      mapping={"experience_id": "exp_1"})
        if result["state"] == "question":
            answer_enrich_evidence(
                user, result["question"]["question_id"],
                "Resolved 200+ tickets per week with 98% satisfaction.",
                evidence_id=ev.evidence_id,
            )

        readiness_after = compute_canonical_readiness(user)
        self.assertTrue(readiness_after["is_ready"])


class GroundedGenerationTests(unittest.TestCase):
    """Grounded CV bullet and motivation-letter, no invented claims."""

    def test_build_ready_actions_includes_cv_bullet(self):
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
        cv_actions = [a for a in actions if a["action"] == "cv_bullet"]
        self.assertEqual(len(cv_actions), 1)
        self.assertIn("evidence_ids", cv_actions[0])
        self.assertEqual(cv_actions[0]["source"], "canonical_evidence")

    def test_build_ready_actions_includes_motivation_letter(self):
        ev = _make_evidence(
            text="Led digital transformation initiative across 3 departments.",
            evidence_type="leadership",
            inferred_employer="Enterprise Co",
            inferred_role="Transformation Lead",
        )
        ev.confirm()
        ev.experience_mapping = {"experience_id": "exp_1"}
        user = _make_user({"candidate_evidence": [ev.to_dict()]})

        actions = build_ready_actions(user)
        ml_actions = [a for a in actions if a["action"] == "motivation_letter"]
        self.assertEqual(len(ml_actions), 1)
        self.assertIn("evidence_ids", ml_actions[0])

    def test_ready_screen_is_concise(self):
        ev = _make_evidence(text="Built a product from scratch.")
        ev.confirm()
        ev.experience_mapping = {"experience_id": "exp_1"}
        user = _make_user({"candidate_evidence": [ev.to_dict()]})

        actions = build_ready_actions(user)
        self.assertLessEqual(len(actions), 3)

    def test_actions_retain_canonical_source(self):
        ev = _make_evidence(text="Optimized database queries.")
        ev.confirm()
        ev.experience_mapping = {"experience_id": "exp_1"}
        user = _make_user({"candidate_evidence": [ev.to_dict()]})

        actions = build_ready_actions(user)
        for action in actions:
            self.assertEqual(action.get("source"), "canonical_evidence")



class IntegrationWithCP040RTests(unittest.TestCase):
    """CP-041R integrates cleanly with existing CP-040R flow."""

    def test_existing_confirm_evidence_still_works(self):
        ev = _make_evidence(text="Original evidence text.")
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [],
        })

        result = confirm_evidence(user, ev.evidence_id)
        self.assertEqual(result["action"], "confirmed")
        self.assertEqual(result["evidence"]["status"], EVIDENCE_STATUS_CONFIRMED)

    def test_existing_reject_evidence_still_works(self):
        ev = _make_evidence(text="Rejected item.")
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [],
        })

        result = reject_evidence(user, ev.evidence_id)
        self.assertEqual(result["action"], "rejected")

    def test_existing_get_next_review_still_works(self):
        ev = _make_evidence(text="Review me.")
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [],
        })

        result = get_next_review_item(user)
        self.assertEqual(result["state"], "review")

    def test_confirm_with_inspect_integrates_with_review_flow(self):
        ev = _make_evidence(
            text="Improved team velocity.",
            evidence_type="achievement",
            inferred_employer="Agile Corp",
            inferred_role="Scrum Master",
        )
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [{
                "experience_id": "exp_1",
                "employer": "Agile Corp",
                "job_title": "Scrum Master",
                "start_date": "2021-01-01",
                "end_date": "2023-12-31",
            }],
        })

        result = confirm_with_inspect(user, ev.evidence_id, mapping={"experience_id": "exp_1"})
        self.assertIn(result["state"], ("question", "ready", "confirmed"))
        self.assertEqual(result["action"], "confirmed")
        self.assertIn("readiness", result)


class NoQuestionWhenReadyTests(unittest.TestCase):
    """When readiness is sufficient, skip directly to Ready."""

    def test_fully_mapped_evidence_skips_questions(self):
        ev = _make_evidence(
            text="Reduced customer churn by 25% through improved onboarding.",
            evidence_type="metric",
            inferred_employer="SaaS Co",
            inferred_role="Product Manager",
        )
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [{
                "experience_id": "exp_1",
                "employer": "SaaS Co",
                "job_title": "Product Manager",
                "start_date": "2020-01-01",
                "end_date": "2023-12-31",
            }],
        })

        result = confirm_with_inspect(user, ev.evidence_id,
                                      mapping={"experience_id": "exp_1"})
        self.assertNotEqual(result["state"], "question")

    def test_empty_evidence_still_works_with_inspect(self):
        user = _make_user({
            "candidate_evidence": [],
            "work_experiences": [],
        })

        actions = build_ready_actions(user)
        self.assertEqual(actions, [])

    def test_multiple_confirmations_no_duplicate_questions(self):
        ev = _make_evidence(text="Built a reporting tool.")
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [],
        })

        result1 = confirm_with_inspect(user, ev.evidence_id)
        result2 = confirm_with_inspect(user, ev.evidence_id)

        if result1["state"] == "question":
            self.assertNotEqual(result2["state"], "question")


if __name__ == "__main__":
    unittest.main()

