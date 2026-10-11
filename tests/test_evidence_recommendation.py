"""Tests for evidence recommendation (CP-018)."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.capabilities.evidence_recommendation import (
    generate_recommendations,
    get_recommendation,
    set_match_status,
)
from backend.domain.evidence_recommendation import (
    EVIDENCE_RECOMMENDATION_STATUS_EXCLUDED,
    EVIDENCE_RECOMMENDATION_STATUS_INCLUDED,
    EVIDENCE_RECOMMENDATION_STATUS_PENDING,
    EvidenceMatch,
    EvidenceRecommendation,
    RecommendationGroup,
)
from backend.domain.models import UserRecord
from backend.domain.source_text_review import (
    SOURCE_REVIEW_STATUS_CONFIRMED,
    SOURCE_REVIEW_STATUS_PENDING,
    SourceTextReview,
)


class EvidenceMatchModelTests(unittest.TestCase):
    """Unit tests for EvidenceMatch domain model."""

    def test_default_include_status_is_pending(self):
        match = EvidenceMatch(
            match_id="m1",
            requirement_id="r1",
            fact_id="f1",
            evidence_text="Built Python automation for reporting.",
        )
        self.assertEqual(match.include_status, EVIDENCE_RECOMMENDATION_STATUS_PENDING)

    def test_to_dict_and_from_dict_roundtrip(self):
        match = EvidenceMatch(
            match_id="m1",
            requirement_id="r1",
            fact_id="f1",
            evidence_text="Reduced manual review by 40%.",
            fact_type="metric",
            certainty="confirmed",
            source_file_name="CV_2025.pdf",
            source_asset_id="asset_cv",
            verification_state="verified",
            match_reason="Keyword match on: reduced, manual, review",
            linked_experience="Acme Corp / Senior Engineer",
            include_status=EVIDENCE_RECOMMENDATION_STATUS_INCLUDED,
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-02T00:00:00",
        )
        d = match.to_dict()
        restored = EvidenceMatch.from_dict(d)
        self.assertEqual(restored.match_id, "m1")
        self.assertEqual(restored.evidence_text, "Reduced manual review by 40%.")
        self.assertEqual(restored.linked_experience, "Acme Corp / Senior Engineer")
        self.assertEqual(restored.include_status, EVIDENCE_RECOMMENDATION_STATUS_INCLUDED)


class RecommendationGroupModelTests(unittest.TestCase):
    """Unit tests for RecommendationGroup domain model."""

    def test_group_aggregates_matches(self):
        group = RecommendationGroup(
            requirement_id="req_python",
            requirement_label="Python experience",
            requirement_category="technical",
            matches=[
                EvidenceMatch(
                    match_id="m1", requirement_id="req_python",
                    fact_id="f1", evidence_text="Built Python automation.",
                ),
                EvidenceMatch(
                    match_id="m2", requirement_id="req_python",
                    fact_id="f2", evidence_text="Python ETL pipelines.",
                ),
            ],
        )
        self.assertTrue(group.has_matches)
        self.assertEqual(len(group.matches), 2)
        self.assertEqual(group.included_matches, [])

    def test_included_matches_filtered(self):
        group = RecommendationGroup(
            requirement_id="req_python",
            requirement_label="Python experience",
            matches=[
                EvidenceMatch(
                    match_id="m1", requirement_id="req_python",
                    fact_id="f1", evidence_text="e1",
                    include_status=EVIDENCE_RECOMMENDATION_STATUS_INCLUDED,
                ),
                EvidenceMatch(
                    match_id="m2", requirement_id="req_python",
                    fact_id="f2", evidence_text="e2",
                    include_status=EVIDENCE_RECOMMENDATION_STATUS_PENDING,
                ),
            ],
        )
        self.assertEqual(len(group.included_matches), 1)
        self.assertEqual(group.included_matches[0].match_id, "m1")


class EvidenceRecommendationModelTests(unittest.TestCase):
    """Unit tests for EvidenceRecommendation domain model."""

    def test_counts_across_groups(self):
        rec = EvidenceRecommendation(
            recommendation_id="rec1",
            job_id="job_1",
            groups=[
                RecommendationGroup(
                    requirement_id="r1", requirement_label="Req A",
                    matches=[
                        EvidenceMatch(
                            match_id="m1", requirement_id="r1",
                            fact_id="f1", evidence_text="e1",
                            include_status=EVIDENCE_RECOMMENDATION_STATUS_INCLUDED,
                        ),
                        EvidenceMatch(
                            match_id="m2", requirement_id="r1",
                            fact_id="f2", evidence_text="e2",
                            include_status=EVIDENCE_RECOMMENDATION_STATUS_EXCLUDED,
                        ),
                    ],
                ),
                RecommendationGroup(
                    requirement_id="r2", requirement_label="Req B",
                    matches=[
                        EvidenceMatch(
                            match_id="m3", requirement_id="r2",
                            fact_id="f3", evidence_text="e3",
                        ),
                    ],
                ),
            ],
        )
        self.assertEqual(rec.total_matches, 3)
        self.assertEqual(rec.included_count, 1)
        self.assertEqual(rec.excluded_count, 1)


class EvidenceRecommendationServiceTests(unittest.TestCase):
    """Tests for the evidence recommendation service."""

    def setUp(self):
        self.repository = MagicMock()
        self.application = SimpleNamespace(
            repositories=SimpleNamespace(auth_repository=self.repository)
        )
        self.user = UserRecord.create(
            email="candidate@example.com",
            metadata={
                "candidate_assets": [
                    {
                        "asset_id": "asset_cv",
                        "display_name": "CV_2025.pdf",
                        "metadata": {
                            "content_sha256": "sig-cv",
                            "source_text": (
                                "Built Python automation for weekly reporting.\n"
                                "Reduced manual review time by 40 percent.\n"
                                "Led team of 5 engineers on cloud migration."
                            ),
                        },
                    }
                ],
                "career_memory": {
                    "facts": [],
                    "outputs": [],
                    "source_signatures": {},
                },
            },
        )

    def _seed_facts(self):
        from backend.career_memory.service import (
            confirm_fact,
            extract_facts,
        )
        extracted = extract_facts(self.application, self.user, ["asset_cv"])
        for fact in extracted.get("active_facts") or []:
            confirm_fact(
                self.application, self.user, fact["fact_id"],
                {"value": fact["value"], "type": fact.get("type", "action"),
                 "certainty": "confirmed"},
            )
        return extracted.get("active_facts") or []

    def _verify_source(self, profile_id="prof_abc"):
        from backend.capabilities.source_text_review import (
            get_or_create_review,
            confirm_review,
        )
        get_or_create_review(
            profile_id, "asset_cv",
            {
                "source_id": "asset_cv",
                "file_name": "CV_2025.pdf",
                "text": "Built Python automation. Reduced manual review by 40%.",
                "confidence": 0.95,
                "method": "pdf",
                "provider": "pymupdf",
                "model": "",
                "is_ocr": False,
                "is_low_confidence_ocr": False,
                "warnings": [],
                "pages": [],
                "status": "",
            },
        )
        confirm_review(profile_id, "asset_cv")

    def test_generate_with_verified_evidence(self):
        self._seed_facts()
        self._verify_source("prof_abc")
        requirements = [
            {"id": "req_1", "label": "Python programming experience", "category": "technical"},
            {"id": "req_2", "label": "Team leadership skills", "category": "soft"},
        ]
        rec = generate_recommendations(
            self.user, job_id="job_abc", job_title="Senior Engineer",
            job_company="Acme Corp", profile_id="prof_abc",
            requirements=requirements,
            candidate_asset_map={"asset_cv": {"display_name": "CV_2025.pdf"}},
        )
        self.assertEqual(len(rec.groups), 2)
        self.assertTrue(rec.groups[0].has_matches)
        for match in rec.groups[0].matches:
            self.assertEqual(match.verification_state, "verified")
            self.assertEqual(match.include_status, EVIDENCE_RECOMMENDATION_STATUS_PENDING)

    def test_unconfirmed_facts_excluded(self):
        from backend.career_memory.service import extract_facts
        extract_facts(self.application, self.user, ["asset_cv"])
        self._verify_source("prof_x")
        requirements = [{"id": "req_1", "label": "Python programming", "category": "technical"}]
        rec = generate_recommendations(
            self.user, job_id="job_x", profile_id="prof_x",
            requirements=requirements,
            candidate_asset_map={"asset_cv": {"display_name": "CV_2025.pdf"}},
        )
        self.assertEqual(rec.total_matches, 0)

    def test_unverified_sources_excluded(self):
        self._seed_facts()
        requirements = [{"id": "req_1", "label": "Python programming", "category": "technical"}]
        rec = generate_recommendations(
            self.user, job_id="job_x", profile_id="prof_x",
            requirements=requirements,
            candidate_asset_map={"asset_cv": {"display_name": "CV_2025.pdf"}},
        )
        self.assertEqual(rec.total_matches, 0)

    def test_set_match_status_include_exclude(self):
        self._seed_facts()
        self._verify_source("prof_abc")
        requirements = [{"id": "req_1", "label": "Python experience", "category": "technical"}]
        rec = generate_recommendations(
            self.user, job_id="job_abc", profile_id="prof_abc",
            requirements=requirements,
            candidate_asset_map={"asset_cv": {"display_name": "CV_2025.pdf"}},
        )
        self.assertTrue(rec.total_matches > 0)
        match_id = rec.groups[0].matches[0].match_id
        updated = set_match_status(rec.recommendation_id, match_id,
                                    EVIDENCE_RECOMMENDATION_STATUS_INCLUDED)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.included_count, 1)
        updated2 = set_match_status(rec.recommendation_id, match_id,
                                     EVIDENCE_RECOMMENDATION_STATUS_EXCLUDED)
        self.assertIsNotNone(updated2)
        self.assertEqual(updated2.excluded_count, 1)

    def test_get_recommendation_found(self):
        self._seed_facts()
        self._verify_source("prof_abc")
        requirements = [{"id": "req_1", "label": "Python", "category": "tech"}]
        rec = generate_recommendations(
            self.user, job_id="job_abc", profile_id="prof_abc",
            requirements=requirements,
        )
        fetched = get_recommendation(rec.recommendation_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.job_id, "job_abc")

    def test_get_recommendation_missing(self):
        self.assertIsNone(get_recommendation("nonexistent_id"))

    def test_set_match_status_invalid_raises(self):
        self._seed_facts()
        self._verify_source("prof_abc")
        requirements = [{"id": "req_1", "label": "Python", "category": "tech"}]
        rec = generate_recommendations(
            self.user, job_id="job_abc", profile_id="prof_abc",
            requirements=requirements,
        )
        match_id = rec.groups[0].matches[0].match_id
        with self.assertRaises(ValueError):
            set_match_status(rec.recommendation_id, match_id, "invalid_status")

    def test_rejected_source_excluded(self):
        self._seed_facts()
        from backend.capabilities.source_text_review import (
            get_or_create_review,
            reject_review,
        )
        get_or_create_review(
            "prof_reject", "asset_cv",
            {"source_id": "asset_cv", "file_name": "CV.pdf",
             "text": "Test.", "confidence": 0.9},
        )
        reject_review("prof_reject", "asset_cv")
        requirements = [{"id": "req_1", "label": "Python", "category": "tech"}]
        rec = generate_recommendations(
            self.user, job_id="job_x", profile_id="prof_reject",
            requirements=requirements,
            candidate_asset_map={"asset_cv": {"display_name": "CV.pdf"}},
        )
        self.assertEqual(rec.total_matches, 0)

    def test_requirements_without_matches_produce_empty_group(self):
        self._seed_facts()
        self._verify_source("prof_abc")
        requirements = [{"id": "req_nomatch", "label": "COBOL programming", "category": "technical"}]
        rec = generate_recommendations(
            self.user, job_id="job_abc", profile_id="prof_abc",
            requirements=requirements,
        )
        self.assertEqual(len(rec.groups), 1)
        self.assertFalse(rec.groups[0].has_matches)
