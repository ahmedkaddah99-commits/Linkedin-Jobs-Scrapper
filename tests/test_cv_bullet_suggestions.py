"""Tests for CV bullet suggestions (CP-036R).

Covers:
- Generation from baseline CV + job description + selected verified evidence
- Provenance tracking (evidence_ids, source_ids, baseline_cv_version)
- Evidence beyond visible baseline bullets
- Review actions: Accept, Edit, Reject, Replace
- Edit validation / unsupported edit blocking
- Accepted bullets retain provenance in output history
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.capabilities.cv_bullet_suggestions import (
    accept_suggestion,
    edit_suggestion,
    generate_suggestions,
    get_accepted_bullets,
    get_suggestion,
    get_suggestions,
    reject_suggestion,
    replace_suggestion,
    _reset_suggestions,
)
from backend.domain.cv_bullet_suggestion import (
    BULLET_SUGGESTION_ACTION_ACCEPT,
    BULLET_SUGGESTION_ACTION_EDIT,
    BULLET_SUGGESTION_ACTION_REJECT,
    BULLET_SUGGESTION_ACTION_REPLACE,
    BULLET_SUGGESTION_ACTIONS,
    BULLET_SUGGESTION_STATUS_ACCEPTED,
    BULLET_SUGGESTION_STATUS_EDITED,
    BULLET_SUGGESTION_STATUS_PENDING,
    BULLET_SUGGESTION_STATUS_REJECTED,
    BULLET_SUGGESTION_STATUS_REPLACED,
    BULLET_SUGGESTION_TRANSITIONS,
    CVBulletSuggestion,
    SUPPORTED_EDIT_FIELDS,
)


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

BASELINE_CV = """Senior Operations Manager

ACME Corp, Jan 2020 - Present
- Managed day-to-day support for a fleet of more than 1,600 e-scooters across 7 cities.
- Coordinated logistics using 7 transport vans to keep assets available and operational.
- Reduced operational downtime by 25% through improved preventive maintenance.

Previous Role Inc, Jun 2017 - Dec 2019
- Led a team of 12 in fast-paced warehouse operations.
- Implemented new inventory tracking system reducing errors by 40%.
"""

JOB_DESC = "Looking for an Operations Director who can scale logistics across multiple regions, improve fleet uptime, and lead teams."

VERIFIED_EVIDENCE = [
    {
        "evidence_id": "ev_001",
        "status": "confirmed",
        "text": "Managed 1,600+ scooter fleet across 7 cities with 99% uptime.",
        "source_asset": "asset_cv_001",
        "evidence_type": "achievement",
        "certainty": "confirmed",
        "version": 1,
    },
    {
        "evidence_id": "ev_002",
        "status": "confirmed",
        "text": "Coordinated 7 transport vans for daily logistics operations.",
        "source_asset": "asset_cv_001",
        "evidence_type": "responsibility",
        "certainty": "confirmed",
        "version": 1,
    },
    {
        "evidence_id": "ev_003",
        "status": "needs_review",
        "text": "Saved company $500k per year through vendor renegotiation.",
        "source_asset": "asset_linkedin",
        "evidence_type": "achievement",
        "certainty": "estimated",
        "version": 1,
    },
]

EXTRA_EVIDENCE = [
    {
        "evidence_id": "ev_100",
        "status": "confirmed",
        "text": "Led cross-functional team of 25 across 3 regional hubs delivering 99.5% SLA.",
        "source_asset": "asset_extra_001",
        "evidence_type": "leadership",
        "certainty": "confirmed",
        "version": 1,
    },
]


def _make_user(evidence_items=None):
    """Create a mock user with candidate_evidence in metadata."""
    user = SimpleNamespace()
    user.user_id = "user_test"
    user.metadata = {
        "candidate_evidence": list(evidence_items or VERIFIED_EVIDENCE),
    }
    return user


def _baseline_kwargs(user=None, **overrides):
    """Return standard kwargs for generate_suggestions."""
    base = {
        "profile_id": "prof_test_001",
        "baseline_cv_text": BASELINE_CV,
        "baseline_cv_version": "v2.1",
        "baseline_cv_asset_id": "asset_cv_main",
        "target_job_id": "job_001",
        "target_job_title": "Operations Director",
        "target_job_description": JOB_DESC,
        "evidence_ids": ["ev_001", "ev_002"],
    }
    if user is not None:
        base["user"] = user
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Domain model tests
# ---------------------------------------------------------------------------


class CVBulletSuggestionModelTests(unittest.TestCase):
    """Unit tests for CVBulletSuggestion domain model."""

    def setUp(self):
        _reset_suggestions()

    def tearDown(self):
        _reset_suggestions()

    def test_create_with_all_provenance_fields(self):
        suggestion = CVBulletSuggestion.create(
            profile_id="prof_1",
            target_job_id="job_1",
            target_job_title="Senior Engineer",
            target_job_description="We need Python expertise.",
            baseline_cv_version="v3.0",
            baseline_cv_asset_id="asset_bcv",
            evidence_ids=["ev_a", "ev_b"],
            source_ids=["src_1"],
            bullet_text="Built Python automation reducing manual work by 50%.",
            linked_experience_id="exp_1",
            label="ACME Corp / Senior Engineer",
        )
        self.assertTrue(suggestion.suggestion_id.startswith("cvsug_"))
        self.assertEqual(suggestion.profile_id, "prof_1")
        self.assertEqual(suggestion.baseline_cv_version, "v3.0")
        self.assertEqual(suggestion.baseline_cv_asset_id, "asset_bcv")
        self.assertEqual(suggestion.evidence_ids, ["ev_a", "ev_b"])
        self.assertEqual(suggestion.source_ids, ["src_1"])
        self.assertEqual(suggestion.target_job_id, "job_1")
        self.assertEqual(suggestion.status, BULLET_SUGGESTION_STATUS_PENDING)
        self.assertTrue(suggestion.is_pending)
        self.assertFalse(suggestion.is_accepted)

    def test_default_status_is_pending(self):
        suggestion = CVBulletSuggestion(suggestion_id="test_001")
        self.assertEqual(suggestion.status, BULLET_SUGGESTION_STATUS_PENDING)

    def test_to_dict_and_from_dict_roundtrip(self):
        suggestion = CVBulletSuggestion.create(
            profile_id="prof_1",
            baseline_cv_version="v1.0",
            evidence_ids=["ev_1"],
            source_ids=["src_1"],
            bullet_text="Test bullet.",
        )
        d = suggestion.to_dict()
        restored = CVBulletSuggestion.from_dict(d)
        self.assertEqual(restored.suggestion_id, suggestion.suggestion_id)
        self.assertEqual(restored.bullet_text, "Test bullet.")
        self.assertEqual(restored.suggested_bullet_text, "Test bullet.")
        self.assertEqual(restored.evidence_ids, ["ev_1"])
        self.assertEqual(restored.source_ids, ["src_1"])

    def test_effective_text_returns_bullet_text(self):
        suggestion = CVBulletSuggestion.create(
            profile_id="p",
            bullet_text="The edited bullet.",
        )
        self.assertEqual(suggestion.effective_text, "The edited bullet.")

    def test_effective_text_falls_back_to_suggested(self):
        suggestion = CVBulletSuggestion(
            suggestion_id="s1",
            suggested_bullet_text="Original suggestion.",
        )
        self.assertEqual(suggestion.effective_text, "Original suggestion.")

    def test_can_transition_to(self):
        suggestion = CVBulletSuggestion(suggestion_id="s1")
        self.assertTrue(suggestion.can_transition_to(BULLET_SUGGESTION_STATUS_ACCEPTED))
        self.assertTrue(suggestion.can_transition_to(BULLET_SUGGESTION_STATUS_REJECTED))
        self.assertFalse(suggestion.can_transition_to("invalid_status"))


class CVBulletSuggestionActionTests(unittest.TestCase):
    """Tests for Accept, Edit, Reject, Replace actions."""

    def setUp(self):
        _reset_suggestions()
        self.suggestion = CVBulletSuggestion.create(
            profile_id="prof_1",
            bullet_text="Original bullet text.",
            evidence_ids=["ev_1"],
            source_ids=["src_1"],
        )

    def tearDown(self):
        _reset_suggestions()

    def test_accept_transitions_to_accepted(self):
        self.suggestion.accept()
        self.assertEqual(self.suggestion.status, BULLET_SUGGESTION_STATUS_ACCEPTED)
        self.assertTrue(self.suggestion.is_accepted)
        self.assertEqual(self.suggestion.bullet_text, "Original bullet text.")
        self.assertEqual(self.suggestion.evidence_ids, ["ev_1"])

    def test_edit_transitions_to_edited_and_preserves_provenance(self):
        self.suggestion.edit("Edited bullet text.")
        self.assertEqual(self.suggestion.status, BULLET_SUGGESTION_STATUS_EDITED)
        self.assertTrue(self.suggestion.is_edited)
        self.assertEqual(self.suggestion.bullet_text, "Edited bullet text.")
        self.assertEqual(self.suggestion.suggested_bullet_text, "Original bullet text.")
        # Provenance preserved after edit
        self.assertEqual(self.suggestion.evidence_ids, ["ev_1"])
        self.assertEqual(self.suggestion.source_ids, ["src_1"])
        self.assertEqual(len(self.suggestion.edit_history), 1)
        self.assertEqual(
            self.suggestion.edit_history[0]["previous_text"],
            "Original bullet text.",
        )
        self.assertEqual(
            self.suggestion.edit_history[0]["new_text"],
            "Edited bullet text.",
        )

    def test_reject_transitions_to_rejected(self):
        self.suggestion.reject()
        self.assertEqual(self.suggestion.status, BULLET_SUGGESTION_STATUS_REJECTED)
        self.assertTrue(self.suggestion.is_rejected)

    def test_replace_transitions_to_replaced(self):
        self.suggestion.replace("Completely new bullet.")
        self.assertEqual(self.suggestion.status, BULLET_SUGGESTION_STATUS_REPLACED)
        self.assertTrue(self.suggestion.is_replaced)
        self.assertEqual(self.suggestion.bullet_text, "Completely new bullet.")
        # Evidence provenance preserved even on replace
        self.assertEqual(self.suggestion.evidence_ids, ["ev_1"])

    def test_has_been_edited_flags_true_after_edit(self):
        self.assertFalse(self.suggestion.has_been_edited)
        self.suggestion.edit("Edited.")
        self.assertTrue(self.suggestion.has_been_edited)

    def test_accepted_after_edit_works(self):
        self.suggestion.edit("Edited.")
        self.assertEqual(self.suggestion.status, BULLET_SUGGESTION_STATUS_EDITED)
        self.assertTrue(self.suggestion.can_transition_to(BULLET_SUGGESTION_STATUS_ACCEPTED))
        self.suggestion.accept()
        self.assertEqual(self.suggestion.status, BULLET_SUGGESTION_STATUS_ACCEPTED)

    def test_cannot_transition_from_accepted_to_pending(self):
        self.suggestion.accept()
        self.assertFalse(self.suggestion.can_transition_to(BULLET_SUGGESTION_STATUS_PENDING))


# ---------------------------------------------------------------------------
# Generation tests
# ---------------------------------------------------------------------------


class CVBulletSuggestionGenerationTests(unittest.TestCase):
    """Tests for suggestion generation from baseline CV + evidence."""

    def setUp(self):
        _reset_suggestions()
        self.user = _make_user()

    def tearDown(self):
        _reset_suggestions()

    def test_generates_suggestions_from_baseline_cv(self):
        suggestions = generate_suggestions(
            self.user, **_baseline_kwargs()
        )
        self.assertGreater(len(suggestions), 0)
        for s in suggestions:
            self.assertEqual(s.status, BULLET_SUGGESTION_STATUS_PENDING)

    def test_suggestions_carry_baseline_cv_version(self):
        suggestions = generate_suggestions(
            self.user, **_baseline_kwargs(baseline_cv_version="v4.2")
        )
        for s in suggestions:
            self.assertEqual(s.baseline_cv_version, "v4.2")

    def test_suggestions_carry_target_job_description(self):
        suggestions = generate_suggestions(
            self.user, **_baseline_kwargs(target_job_description=JOB_DESC)
        )
        for s in suggestions:
            self.assertEqual(s.target_job_description, JOB_DESC)
            self.assertEqual(s.target_job_id, "job_001")

    def test_suggestions_store_evidence_ids_and_source_ids(self):
        suggestions = generate_suggestions(
            self.user,
            **_baseline_kwargs(evidence_ids=["ev_001", "ev_002"])
        )
        for s in suggestions:
            self.assertEqual(s.evidence_ids, ["ev_001", "ev_002"])
            self.assertIn("asset_cv_001", s.source_ids)

    def test_raises_when_no_evidence_selected(self):
        with self.assertRaises(ValueError) as ctx:
            generate_suggestions(
                self.user,
                **_baseline_kwargs(evidence_ids=[])
            )
        self.assertIn("verified evidence", str(ctx.exception))

    def test_raises_when_baseline_cv_empty(self):
        with self.assertRaises(ValueError) as ctx:
            generate_suggestions(
                self.user,
                **_baseline_kwargs(baseline_cv_text="   ")
            )
        self.assertIn("Baseline CV", str(ctx.exception))

    def test_raises_when_evidence_not_verified(self):
        with self.assertRaises(ValueError) as ctx:
            generate_suggestions(
                self.user,
                **_baseline_kwargs(evidence_ids=["ev_003"])  # not verified
            )
        self.assertIn("not verified", str(ctx.exception))

    def test_raises_when_evidence_not_found(self):
        with self.assertRaises(ValueError) as ctx:
            generate_suggestions(
                self.user,
                **_baseline_kwargs(evidence_ids=["ev_nonexistent"])
            )
        self.assertIn("not found", str(ctx.exception))

    def test_evidence_beyond_baseline_bullets_is_eligible(self):
        """Evidence items beyond those visible in baseline CV can be selected."""
        user = _make_user(VERIFIED_EVIDENCE + EXTRA_EVIDENCE)
        kwargs = {
            "profile_id": "prof_test_001",
            "baseline_cv_text": BASELINE_CV,
            "baseline_cv_version": "v2.1",
            "baseline_cv_asset_id": "asset_cv_main",
            "target_job_id": "job_001",
            "target_job_title": "Operations Director",
            "target_job_description": JOB_DESC,
            "evidence_ids": ["ev_100"],
        }
        suggestions = generate_suggestions(user, **kwargs)
        self.assertGreater(len(suggestions), 0)
        for s in suggestions:
            self.assertEqual(s.evidence_ids, ["ev_100"])
            self.assertIn("asset_extra_001", s.source_ids)

    def test_suggestions_include_relevance_metadata(self):
        suggestions = generate_suggestions(
            self.user, **_baseline_kwargs()
        )
        for s in suggestions:
            self.assertIn("relevance_score", s.metadata)
            self.assertIn("generation_method", s.metadata)
            self.assertEqual(s.metadata["generation_method"], "baseline_plus_evidence")


# ---------------------------------------------------------------------------
# Service action tests (Accept, Edit, Reject, Replace via service)
# ---------------------------------------------------------------------------


class CVBulletSuggestionServiceActionTests(unittest.TestCase):
    """Tests for service-level review actions."""

    def setUp(self):
        _reset_suggestions()
        self.user = _make_user()
        suggestions = generate_suggestions(
            self.user, **_baseline_kwargs()
        )
        self.suggestion = suggestions[0]
        self.sid = self.suggestion.suggestion_id

    def tearDown(self):
        _reset_suggestions()

    def test_accept_suggestion_via_service(self):
        updated = accept_suggestion(self.sid)
        self.assertEqual(updated.status, BULLET_SUGGESTION_STATUS_ACCEPTED)

    def test_edit_suggestion_via_service(self):
        updated = edit_suggestion(
            self.sid, {"bullet_text": "Refined bullet."}
        )
        self.assertEqual(updated.status, BULLET_SUGGESTION_STATUS_EDITED)
        self.assertEqual(updated.bullet_text, "Refined bullet.")

    def test_reject_suggestion_via_service(self):
        updated = reject_suggestion(self.sid)
        self.assertEqual(updated.status, BULLET_SUGGESTION_STATUS_REJECTED)

    def test_replace_suggestion_via_service(self):
        updated = replace_suggestion(
            self.sid, {"bullet_text": "Brand new bullet."}
        )
        self.assertEqual(updated.status, BULLET_SUGGESTION_STATUS_REPLACED)
        self.assertEqual(updated.bullet_text, "Brand new bullet.")

    def test_edit_rejects_unsupported_fields(self):
        with self.assertRaises(ValueError) as ctx:
            edit_suggestion(
                self.sid,
                {"bullet_text": "ok", "baseline_cv_version": "hacked"},
            )
        self.assertIn("Unsupported edit fields", str(ctx.exception))
        self.assertIn("baseline_cv_version", str(ctx.exception))

    def test_edit_rejects_multiple_unsupported_fields(self):
        with self.assertRaises(ValueError) as ctx:
            edit_suggestion(
                self.sid,
                {
                    "bullet_text": "ok",
                    "evidence_ids": ["ev_malicious"],
                    "status": "accepted",
                },
            )
        self.assertIn("Unsupported edit fields", str(ctx.exception))
        self.assertIn("evidence_ids", str(ctx.exception))
        self.assertIn("status", str(ctx.exception))

    def test_edit_requires_non_empty_bullet_text(self):
        with self.assertRaises(ValueError) as ctx:
            edit_suggestion(self.sid, {"bullet_text": "  "})
        self.assertIn("non-empty", str(ctx.exception))

    def test_replace_requires_non_empty_bullet_text(self):
        with self.assertRaises(ValueError) as ctx:
            replace_suggestion(self.sid, {"bullet_text": ""})
        self.assertIn("non-empty", str(ctx.exception))

    def test_accept_unknown_suggestion_raises(self):
        with self.assertRaises(ValueError) as ctx:
            accept_suggestion("nonexistent_id")
        self.assertIn("not found", str(ctx.exception))

    def test_edit_unknown_suggestion_raises(self):
        with self.assertRaises(ValueError) as ctx:
            edit_suggestion("nonexistent_id", {"bullet_text": "ok"})
        self.assertIn("not found", str(ctx.exception))

    def test_reject_unknown_suggestion_raises(self):
        with self.assertRaises(ValueError) as ctx:
            reject_suggestion("nonexistent_id")
        self.assertIn("not found", str(ctx.exception))

    def test_replace_unknown_suggestion_raises(self):
        with self.assertRaises(ValueError) as ctx:
            replace_suggestion("nonexistent_id", {"bullet_text": "ok"})
        self.assertIn("not found", str(ctx.exception))


# ---------------------------------------------------------------------------
# Accepted bullets / output history tests
# ---------------------------------------------------------------------------


class AcceptedBulletsTests(unittest.TestCase):
    """Tests for accepted bullets retaining provenance in output history."""

    def setUp(self):
        _reset_suggestions()
        self.user = _make_user()
        suggestions = generate_suggestions(
            self.user, **_baseline_kwargs()
        )
        self.s1 = suggestions[0]
        self.s2 = suggestions[1] if len(suggestions) > 1 else suggestions[0]

    def tearDown(self):
        _reset_suggestions()

    def test_accepted_bullets_include_accepted_items(self):
        accept_suggestion(self.s1.suggestion_id)
        bullets = get_accepted_bullets("prof_test_001")
        self.assertGreaterEqual(len(bullets), 1)
        self.assertTrue(any(
            b.suggestion_id == self.s1.suggestion_id for b in bullets
        ))

    def test_edited_bullets_appear_in_accepted(self):
        edit_suggestion(
            self.s1.suggestion_id,
            {"bullet_text": "Edited and accepted."},
        )
        bullets = get_accepted_bullets("prof_test_001")
        self.assertGreaterEqual(len(bullets), 1)
        self.assertTrue(any(
            b.suggestion_id == self.s1.suggestion_id for b in bullets
        ))

    def test_rejected_bullets_not_in_accepted(self):
        reject_suggestion(self.s1.suggestion_id)
        bullets = get_accepted_bullets("prof_test_001")
        self.assertFalse(any(
            b.suggestion_id == self.s1.suggestion_id for b in bullets
        ))

    def test_pending_bullets_not_in_accepted(self):
        bullets = get_accepted_bullets("prof_test_001")
        self.assertFalse(any(
            b.suggestion_id == self.s1.suggestion_id for b in bullets
        ))

    def test_accepted_bullets_retain_provenance(self):
        accept_suggestion(self.s1.suggestion_id)
        bullets = get_accepted_bullets("prof_test_001")
        for b in bullets:
            if b.suggestion_id == self.s1.suggestion_id:
                self.assertGreater(len(b.evidence_ids), 0)
                self.assertGreater(len(b.source_ids), 0)
                self.assertNotEqual(b.baseline_cv_version, "")

    def test_accepted_bullets_filter_by_target_job(self):
        accept_suggestion(self.s1.suggestion_id)
        bullets = get_accepted_bullets(
            "prof_test_001", target_job_id="job_001"
        )
        self.assertGreaterEqual(len(bullets), 1)
        bullets_other = get_accepted_bullets(
            "prof_test_001", target_job_id="other_job"
        )
        self.assertEqual(len(bullets_other), 0)


# ---------------------------------------------------------------------------
# Query tests
# ---------------------------------------------------------------------------


class CVBulletSuggestionQueryTests(unittest.TestCase):
    """Tests for get_suggestions and get_suggestion."""

    def setUp(self):
        _reset_suggestions()
        self.user = _make_user()
        self.generated = generate_suggestions(
            self.user, **_baseline_kwargs()
        )

    def tearDown(self):
        _reset_suggestions()

    def test_get_suggestions_returns_all_for_profile(self):
        results = get_suggestions("prof_test_001")
        self.assertEqual(len(results), len(self.generated))

    def test_get_suggestions_filters_by_target_job(self):
        results = get_suggestions(
            "prof_test_001", target_job_id="job_001"
        )
        self.assertEqual(len(results), len(self.generated))
        results_none = get_suggestions(
            "prof_test_001", target_job_id="nonexistent"
        )
        self.assertEqual(len(results_none), 0)

    def test_get_suggestion_returns_single(self):
        sid = self.generated[0].suggestion_id
        result = get_suggestion(sid)
        self.assertIsNotNone(result)
        self.assertEqual(result.suggestion_id, sid)

    def test_get_suggestion_returns_none_for_unknown(self):
        result = get_suggestion("nonexistent")
        self.assertIsNone(result)




