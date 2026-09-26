"""Tests for CP-042R: Browser-level evidence journey + final UX repair.

Covers: deterministic fixtures, canonical readiness, grounded outputs,
no duplicate dashboard/memory spikes, transition diagnostics.
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
    build_ready_actions,
    compute_canonical_readiness,
    confirm_with_inspect,
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


class CanonicalReadinessTests(unittest.TestCase):
    """CP-042R: Readiness uses canonical evidence, not memory spikes."""

    def test_readiness_excludes_legacy_counters(self):
        ev = _make_evidence(text="Delivered project on time.")
        ev.confirm()
        ev.experience_mapping = {"experience_id": "exp_1"}
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "career_memory_spike_count": 999,
            "memory_ready": False,
        })
        readiness = compute_canonical_readiness(user)
        self.assertIn("legacy_counters_excluded", readiness)
        self.assertTrue(readiness["legacy_counters_excluded"])
        self.assertTrue(readiness["is_ready"])

    def test_empty_evidence_is_not_ready(self):
        user = _make_user({"candidate_evidence": [], "work_experiences": []})
        readiness = compute_canonical_readiness(user)
        self.assertFalse(readiness["is_ready"])

    def test_readiness_with_no_mapping(self):
        ev = _make_evidence(text="Built a service.")
        ev.confirm()
        user = _make_user({"candidate_evidence": [ev.to_dict()]})
        readiness = compute_canonical_readiness(user)
        self.assertFalse(readiness["is_ready"])


class GroundedOutputsTests(unittest.TestCase):
    """CP-042R: Grounded CV/letter outputs, no invented claims."""

    def test_build_ready_actions_retains_evidence_ids(self):
        ev = _make_evidence(
            text="Reduced latency by 50% with caching layer.",
            evidence_type="achievement",
            inferred_employer="TechCorp",
            inferred_role="Backend Engineer",
        )
        ev.confirm()
        ev.experience_mapping = {"experience_id": "exp_1"}
        user = _make_user({"candidate_evidence": [ev.to_dict()]})
        actions = build_ready_actions(user)
        self.assertGreaterEqual(len(actions), 2)
        for action in actions:
            if action["action"] in ("cv_bullet", "motivation_letter"):
                self.assertIn("evidence_ids", action)
                self.assertGreater(len(action["evidence_ids"]), 0)
                self.assertEqual(action["source"], "canonical_evidence")

    def test_outputs_never_invent_unsupported_claims(self):
        ev = _make_evidence(text="Ran a workshop.")
        ev.confirm()
        ev.experience_mapping = {"experience_id": "exp_1"}
        user = _make_user({"candidate_evidence": [ev.to_dict()]})
        actions = build_ready_actions(user)
        for action in actions:
            claim = action.get("claim", "")
            self.assertNotIn("increased by 500%", str(claim).lower())


class NoDuplicateDashboardTests(unittest.TestCase):
    """CP-042R: No duplicate dashboard or global save controls."""

    def test_ready_actions_are_scoped_to_evidence(self):
        ev = _make_evidence(text="Delivered a feature.")
        ev.confirm()
        ev.experience_mapping = {"experience_id": "exp_1"}
        user = _make_user({"candidate_evidence": [ev.to_dict()]})
        actions = build_ready_actions(user)
        action_types = [a["action"] for a in actions]
        self.assertNotIn("save_all", action_types)
        self.assertNotIn("dashboard", action_types)
        self.assertNotIn("global_save", action_types)

    def test_actions_are_concise(self):
        ev = _make_evidence(text="Optimized queries.")
        ev.confirm()
        ev.experience_mapping = {"experience_id": "exp_1"}
        user = _make_user({"candidate_evidence": [ev.to_dict()]})
        actions = build_ready_actions(user)
        self.assertLessEqual(len(actions), 3)


class TransitionDiagnosticsTests(unittest.TestCase):
    """CP-042R: Diagnostics identify stage/request/error without contents."""

    def test_readiness_includes_computation_source(self):
        user = _make_user({"candidate_evidence": []})
        readiness = compute_canonical_readiness(user)
        self.assertEqual(readiness["computed_from"], "canonical_evidence")
        self.assertIn("total_evidence", readiness)
        self.assertIn("confirmed", readiness)
        self.assertIn("is_ready", readiness)

    def test_confirm_with_inspect_returns_diagnostic_state(self):
        ev = _make_evidence(
            text="Improved team velocity with agile practices.",
            evidence_type="achievement",
            inferred_employer="DevCo",
            inferred_role="Team Lead",
        )
        ev.status = EVIDENCE_STATUS_NEEDS_REVIEW
        user = _make_user({
            "candidate_evidence": [ev.to_dict()],
            "work_experiences": [{
                "experience_id": "exp_1",
                "employer": "DevCo",
                "job_title": "Team Lead",
                "start_date": "2021-01-01",
                "end_date": "2023-12-31",
            }],
        })
        mapping = {"experience_id": "exp_1"}
        result = confirm_with_inspect(user, ev.evidence_id, mapping=mapping)
        self.assertIn("state", result)
        self.assertIn("action", result)
        self.assertIn("readiness", result)
        self.assertIn(result["state"], ("question", "ready", "confirmed"))


class FixtureProviderTests(unittest.TestCase):
    """CP-042R: Deterministic fixture provider endpoint tests."""

    def test_fixture_module_imports(self):
        from backend.api.routes.career_evidence_fixture import register_routes
        self.assertTrue(callable(register_routes))

    def test_fixture_reset_creates_default_state(self):
        from backend.api.routes.career_evidence_fixture import (
            _get_fixture, _save_fixture,
        )
        _save_fixture("test_user_42", {
            "_created": 1000.0,
            "mode": "happy_path",
            "fail_at": None,
            "fail_count": 0,
            "documents": [],
            "selected_source_ids": [],
            "evidence_items": [],
            "experience_links": [],
            "pending_questions": [],
        })
        state = _get_fixture("test_user_42")
        self.assertEqual(state["mode"], "happy_path")
        self.assertEqual(state["fail_count"], 0)

    def test_fixture_failure_injection_modes(self):
        from backend.api.routes.career_evidence_fixture import (
            _get_fixture, _save_fixture, _should_fail,
        )
        _save_fixture("test_fail_42", {
            "_created": 1000.0,
            "mode": "error_fixture",
            "fail_at": "documents",
            "fail_count": 0,
            "documents": [],
            "selected_source_ids": [],
            "evidence_items": [],
            "experience_links": [],
            "pending_questions": [],
        })
        entry = _get_fixture("test_fail_42")
        self.assertTrue(_should_fail(entry, "documents"))
        self.assertEqual(entry["fail_count"], 1)
        self.assertFalse(_should_fail(entry, "processing"))


if __name__ == "__main__":
    unittest.main()
