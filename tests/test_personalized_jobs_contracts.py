import unittest

from backend.domain.candidate_evidence import CandidateEvidence
from backend.domain.models import JobRecord, ProfileRequirementMatch
from backend.domain.pipeline_jobs import PipelineJob
from backend.domain.personalized_jobs_contracts import (
    CANONICAL_PLAN_IDS,
    CandidateSearchPreferences,
    ContractReference,
    ContractValidationError,
    EligibilityEvaluation,
    EligibilityReason,
    EligibilityStatus,
    FRONTEND_PERSONALIZED_FEATURE_KEY_MAP,
    JobDisposition,
    JobPosting,
    JobSourceObservation,
    MatchEvidenceReference,
    MatchEvaluation,
    PersonalizedFeatureKey,
    WorkAuthorizationPreference,
    adapt_language_rule_reasons,
    canonical_plan_id,
    can_transition_disposition,
    normalize_personalized_feature_key,
)


class PersonalizedJobsContractsTests(unittest.TestCase):
    def test_candidate_search_preferences_round_trip_and_nullable_fields(self):
        preferences = CandidateSearchPreferences(
            profile_id="prof_1",
            user_id="user_1",
            target_roles=["Business Analyst"],
            keywords=["SQL", "sql"],
            preferred_locations=["Berlin"],
            country_codes=["de"],
            work_arrangements=["hybrid"],
            seniority_levels=["mid"],
            employment_types=["full_time"],
            languages=[{"language": "English", "proficiency": "C1"}],
            work_authorization=[WorkAuthorizationPreference(country_code="DE")],
            minimum_salary=None,
            salary_currency=None,
            earliest_start_date=None,
            notice_period_days=None,
            maximum_commute_minutes=45,
            willingness_to_travel=False,
            associated_asset_id="asset_cv_1",
        )

        payload = preferences.to_dict()
        restored = CandidateSearchPreferences.from_dict(payload)

        self.assertEqual(restored, preferences)
        self.assertEqual(payload["keywords"], ["sql"])
        self.assertIsNone(payload["minimum_salary"])
        self.assertEqual(payload["work_authorization"][0]["country_code"], "DE")

    def test_workspace_settings_adapter_does_not_copy_runtime_configuration(self):
        preferences = CandidateSearchPreferences.from_workspace_settings(
            profile_id="prof_1",
            settings={
                "target_roles": ["Analyst"],
                "keywords": ["SQL"],
                "country_codes": ["DE"],
                "work_arrangement": "remote",
                "experience_levels": ["3"],
                "languages": ["English - C1"],
                "workspace_cv_asset_id": "asset_1",
                "linkedin_max_pages": 10,
            },
        )

        self.assertEqual(preferences.target_roles, ["Analyst"])
        self.assertEqual(preferences.languages[0].proficiency, "C1")
        self.assertEqual(preferences.associated_asset_id, "asset_1")
        self.assertNotIn("linkedin_max_pages", preferences.to_dict())

    def test_enum_validation_and_analytics_safe_preference_projection(self):
        with self.assertRaises(ContractValidationError):
            CandidateSearchPreferences(profile_id="prof_1", work_arrangements=["flexible"])

        preferences = CandidateSearchPreferences(
            profile_id="prof_1",
            minimum_salary=90000,
            salary_currency="EUR",
            work_authorization=[{"country_code": "DE", "status": "authorized"}],
            sponsorship_requirement="required",
        )
        analytics = preferences.to_analytics_dict()
        self.assertNotIn("minimum_salary", analytics)
        self.assertNotIn("salary_currency", analytics)
        self.assertNotIn("work_authorization", analytics)
        self.assertNotIn("sponsorship_requirement", analytics)

    def test_source_observation_preserves_run_and_workspace_provenance(self):
        observation = JobSourceObservation(
            source_type="linkedin_search",
            source_identifier="source-job-1",
            original_url="https://example.test/jobs/1?utm_source=runr",
            observed_title="Analyst",
            observed_company=None,
            observed_location=None,
            run_id="run_1",
            workspace_id="workspace_1",
            raw_job_id="run-local-1",
        )

        restored = JobSourceObservation.from_dict(observation.to_dict())
        self.assertEqual(restored, observation)
        self.assertIsNone(restored.observed_company)
        self.assertEqual(restored.to_analytics_dict()["source_type"], "linkedin_search")
        self.assertNotIn("source_metadata", restored.to_analytics_dict())

    def test_job_record_and_pipeline_job_map_to_same_url_based_posting(self):
        raw = {
            "job_id": "run-local-9",
            "title": "Business Analyst",
            "company": "Example GmbH",
            "location_raw": "Berlin",
            "link": "https://example.test/jobs/9?utm_campaign=runr",
            "apply_link": "https://example.test/jobs/9?ref=runr",
            "description_text": "SQL and reporting.",
            "source_type": "linkedin_search",
        }
        job_record_posting = JobPosting.from_job_record(raw, run_id="run_1", workspace_id="workspace_1")
        pipeline_job_posting = JobPosting.from_pipeline_job(
            PipelineJob.from_record(raw), run_id="run_2", workspace_id="workspace_2"
        )

        self.assertEqual(job_record_posting.posting_id, pipeline_job_posting.posting_id)
        self.assertNotEqual(job_record_posting.posting_id, raw["job_id"])
        self.assertEqual(job_record_posting.canonical_apply_url, "https://example.test/jobs/9")
        self.assertEqual(job_record_posting.source_observations[0].raw_job_id, "run-local-9")
        self.assertEqual(job_record_posting.provenance[0].run_id, "run_1")
        self.assertNotIn("source_observations", job_record_posting.to_public_dict())
        self.assertEqual(JobPosting.from_dict(job_record_posting.to_dict()), job_record_posting)

    def test_url_less_legacy_job_is_explicitly_provisional(self):
        posting = JobPosting.from_job_record(
            JobRecord(job_id="run-local-1", title="Analyst", company="Example"),
            run_id="run_1",
        )
        self.assertTrue(posting.posting_id.startswith("provisional_posting_"))

    def test_eligibility_statuses_and_authorization_uncertainty(self):
        for status in (
            "eligible",
            "likely_eligible",
            "ineligible",
            "uncertain",
            "not_evaluated",
        ):
            if status == "not_evaluated":
                evaluation = EligibilityEvaluation(profile_id="prof_1", posting_id="post_1")
            else:
                evaluation = EligibilityEvaluation(
                    profile_id="prof_1",
                    posting_id="post_1",
                    status=status,
                    evaluator_name="rules",
                    evaluator_version="1",
                    evaluated_at="2026-08-04T10:00:00+00:00",
                )
            self.assertEqual(evaluation.status, status)

        uncertain_reason = EligibilityReason(
            reason_code="authorization_unknown",
            category="authorization",
            user_facing_summary="Authorization is not stated.",
            evaluation_outcome="uncertain",
            source_type="job_description",
            candidate_reference=ContractReference("candidate_preference", "pref_auth_1", "prof_1"),
            is_explicit=False,
            evaluator_name="rules",
            evaluator_version="1",
        )
        with self.assertRaises(ContractValidationError):
            EligibilityEvaluation(
                profile_id="prof_1",
                posting_id="post_1",
                status="ineligible",
                reasons=[uncertain_reason],
                evaluator_name="rules",
                evaluator_version="1",
            )

        evaluation = EligibilityEvaluation(
            profile_id="prof_1",
            posting_id="post_1",
            status="uncertain",
            reasons=[uncertain_reason],
            evaluator_name="rules",
            evaluator_version="1",
        )
        self.assertEqual(evaluation.to_dict()["reasons"][0]["evaluation_outcome"], "uncertain")
        self.assertNotIn("authorization_unknown", evaluation.to_analytics_dict().values())

    def test_language_rule_output_can_be_adapted_without_changing_language_rules(self):
        reasons = adapt_language_rule_reasons(["German B2 required"])
        self.assertEqual(reasons[0].category, "language")
        self.assertEqual(reasons[0].source_type, "language_rules")
        self.assertEqual(reasons[0].evaluation_outcome, EligibilityStatus.UNCERTAIN.value)

    def test_match_evidence_is_traceable_and_priority_rank_is_not_match_score(self):
        existing_evidence = CandidateEvidence.create(
            profile_id="prof_1",
            text="Validated SQL reporting experience.",
        )
        existing_match = ProfileRequirementMatch(
            requirement_id="req_1",
            requirement_text="SQL",
            requirement_category="skill",
            match_status="strong",
            matched_evidence_ids=["exp_1"],
            match_score=0.99,
        )
        evaluation = MatchEvaluation.from_profile_requirement_matches(
            profile_id="prof_1",
            posting_id="post_1",
            matches=[existing_match],
        )

        payload = evaluation.to_dict()
        self.assertIsNone(evaluation.overall_score)
        self.assertNotIn("priority_rank", payload)
        self.assertEqual(payload["evidence_references"][0]["reference_type"], "work_experience")
        self.assertEqual(payload["evidence_references"][0]["reference_id"], "exp_1")
        self.assertNotIn("snippet", payload["evidence_references"][0])

        with self.assertRaises(ContractValidationError):
            MatchEvaluation(profile_id="prof_1", posting_id="post_1", overall_score=0.8)

        evidence_reference = MatchEvidenceReference(
            reference_type="candidate_evidence",
            reference_id=existing_evidence.evidence_id,
            profile_id="prof_1",
            record_version=2,
        )
        self.assertEqual(evidence_reference.to_dict()["reference_id"], existing_evidence.evidence_id)

    def test_disposition_transitions_are_separate_from_requeue(self):
        disposition = JobDisposition(user_id="user_1", posting_id="post_1", state="hidden")
        restored = disposition.transition_to("none", source_of_change="user")
        self.assertEqual(restored.state, "none")
        self.assertEqual(restored.version, 2)
        self.assertTrue(can_transition_disposition("saved", "preparing"))
        self.assertTrue(can_transition_disposition("preparing", "applied"))
        self.assertTrue(can_transition_disposition("dismissed", "none"))
        self.assertFalse(can_transition_disposition("hidden", "applied"))
        self.assertNotIn("requeue", JobDisposition(user_id="u", posting_id="p").to_dict())

    def test_feature_keys_and_canonical_plan_ids(self):
        self.assertEqual(
            normalize_personalized_feature_key("ai_eligibility_filter"),
            PersonalizedFeatureKey.AI_ELIGIBILITY_FILTERING.value,
        )
        self.assertEqual(
            FRONTEND_PERSONALIZED_FEATURE_KEY_MAP["multiple_active_searches"],
            "multiple_job_searches",
        )
        self.assertEqual(set(CANONICAL_PLAN_IDS), {"free", "runr_pro"})
        self.assertEqual(canonical_plan_id("runr_pro"), "runr_pro")
        with self.assertRaises(ContractValidationError):
            canonical_plan_id("scale")
        with self.assertRaises(ContractValidationError):
            canonical_plan_id("Pro")


if __name__ == "__main__":
    unittest.main()
