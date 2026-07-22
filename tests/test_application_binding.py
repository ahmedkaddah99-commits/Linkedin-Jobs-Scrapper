"""Tests for job application binding (CP-017)."""

import unittest

from backend.capabilities.profile_matching.application_binding import (
    _build_match_summary,
    _compute_coverage_score,
    _load_verified_evidence,
    _match_requirement,
    analyse_job_requirements,
    create_application_binding,
    delete_application_binding,
    get_application_binding,
    list_application_bindings,
)
from backend.domain.models import (
    APPLICATION_TYPE_TAILORED,
    MATCH_STATUS_MISSING,
    MATCH_STATUS_PARTIAL,
    MATCH_STATUS_STRONG,
    REQUIREMENT_CATEGORY_EXPERIENCE,
    REQUIREMENT_CATEGORY_LANGUAGE,
    REQUIREMENT_CATEGORY_SKILL,
    REQUIREMENT_CATEGORY_TOOL,
    WORK_EXPERIENCE_STATUS_ACTIVE,
    WORK_EXPERIENCE_STATUS_MERGED,
    CareerProfile,
    JobApplicationBinding,
    ProfileRequirementMatch,
    WorkExperienceRecord,
)


class AnalyseJobRequirementsTests(unittest.TestCase):
    def test_extracts_skills_from_description(self):
        desc = "Candidate must be proficient in Python and have experience with React."
        result = analyse_job_requirements(desc)
        skills = [
            r for r in result["requirements"]
            if r["requirement_category"] == REQUIREMENT_CATEGORY_SKILL
        ]
        self.assertTrue(len(skills) > 0)

    def test_extracts_tools_from_description(self):
        desc = "Experience using AWS and tools such as Docker, Kubernetes."
        result = analyse_job_requirements(desc)
        tools = [
            r for r in result["requirements"]
            if r["requirement_category"] == REQUIREMENT_CATEGORY_TOOL
        ]
        self.assertTrue(len(tools) > 0)

    def test_extracts_experience_requirements(self):
        desc = "Must have 5+ years of experience in software development."
        result = analyse_job_requirements(desc)
        exp_reqs = [
            r for r in result["requirements"]
            if r["requirement_category"] == REQUIREMENT_CATEGORY_EXPERIENCE
        ]
        self.assertTrue(len(exp_reqs) > 0)
        self.assertIn("5+", exp_reqs[0]["requirement_text"])

    def test_extracts_language_requirements(self):
        desc = "Must be fluent in English and have German language skills."
        result = analyse_job_requirements(desc)
        lang_reqs = [
            r for r in result["requirements"]
            if r["requirement_category"] == REQUIREMENT_CATEGORY_LANGUAGE
        ]
        self.assertTrue(len(lang_reqs) > 0)

    def test_extracts_themes(self):
        desc = (
            "We are a fast-paced startup looking for a self-driven leader "
            "who thrives in an agile environment and is data-driven."
        )
        result = analyse_job_requirements(desc)
        themes = result["themes"]
        self.assertTrue(len(themes) > 0)
        self.assertIn("leadership", themes)
        self.assertIn("agile", themes)



class EvidenceLoadingTests(unittest.TestCase):
    def test_loads_only_active_evidence(self):
        metadata = {
            "work_experiences": [
                {
                    "experience_id": "exp_1", "profile_id": "prof_1",
                    "employer": "Acme Corp", "job_title": "Engineer",
                    "status": WORK_EXPERIENCE_STATUS_ACTIVE,
                },
                {
                    "experience_id": "exp_2", "profile_id": "prof_1",
                    "employer": "Old Corp", "job_title": "Developer",
                    "status": WORK_EXPERIENCE_STATUS_MERGED,
                },
            ]
        }
        evidence = _load_verified_evidence(metadata)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].experience_id, "exp_1")

    def test_returns_empty_for_no_evidence(self):
        evidence = _load_verified_evidence({})
        self.assertEqual(len(evidence), 0)


class RequirementMatchingTests(unittest.TestCase):
    def test_strong_match_when_evidence_matches(self):
        requirement = {
            "requirement_id": "req_1",
            "requirement_text": "Python development",
            "requirement_category": REQUIREMENT_CATEGORY_SKILL,
        }
        evidence = [
            WorkExperienceRecord(
                experience_id="exp_1", profile_id="prof_1",
                job_title="Senior Python Developer", employer="Tech Corp",
                description="Developed Python applications for enterprise clients",
                status=WORK_EXPERIENCE_STATUS_ACTIVE,
            ),
        ]
        match = _match_requirement(requirement, evidence)
        self.assertEqual(match.match_status, MATCH_STATUS_STRONG)
        self.assertGreater(match.match_score, 0.5)
        self.assertEqual(match.matched_evidence_ids, ["exp_1"])

    def test_missing_match_when_no_evidence(self):


class ComputeCoverageTests(unittest.TestCase):
    def test_full_coverage_returns_1(self):
        matches = [
            ProfileRequirementMatch("r1", "a", match_status=MATCH_STATUS_STRONG, match_score=0.9),
            ProfileRequirementMatch("r2", "b", match_status=MATCH_STATUS_STRONG, match_score=0.8),
        ]
        self.assertEqual(_compute_coverage_score(matches), 1.0)

    def test_partial_coverage(self):
        matches = [
            ProfileRequirementMatch("r1", "a", match_status=MATCH_STATUS_STRONG, match_score=0.9),
            ProfileRequirementMatch("r2", "b", match_status=MATCH_STATUS_PARTIAL, match_score=0.4),
            ProfileRequirementMatch("r3", "c", match_status=MATCH_STATUS_MISSING, match_score=0.0),
        ]
        score = _compute_coverage_score(matches)
        self.assertEqual(score, 0.5)

    def test_empty_coverage_returns_0(self):
        self.assertEqual(_compute_coverage_score([]), 0.0)


class BuildMatchSummaryTests(unittest.TestCase):
    def test_includes_all_statuses(self):
        matches = [
            ProfileRequirementMatch("r1", "a", match_status=MATCH_STATUS_STRONG, match_score=0.9),
            ProfileRequirementMatch("r2", "b", match_status=MATCH_STATUS_PARTIAL, match_score=0.4),
            ProfileRequirementMatch("r3", "c", match_status=MATCH_STATUS_MISSING, match_score=0.0),
        ]


class JobApplicationBindingModelTests(unittest.TestCase):
    def test_create_binding_with_minimum_fields(self):
        binding = JobApplicationBinding.create(profile_id="prof_abc", job_id="job_xyz")
        self.assertEqual(binding.profile_id, "prof_abc")
        self.assertEqual(binding.job_id, "job_xyz")
        self.assertTrue(binding.binding_id.startswith("bind_"))
        self.assertEqual(binding.application_type, APPLICATION_TYPE_TAILORED)

    def test_create_binding_with_all_fields(self):
        binding = JobApplicationBinding.create(
            profile_id="prof_abc", job_id="job_xyz",
            run_id="run_123", job_title="Senior Engineer",
            company="Acme Corp", location="Berlin",
            target_role="Backend Lead",
            application_type="tailored",
            description_text="Build robust APIs...",
        )
        self.assertEqual(binding.job_title, "Senior Engineer")
        self.assertEqual(binding.company, "Acme Corp")
        self.assertEqual(binding.location, "Berlin")
        self.assertEqual(binding.target_role, "Backend Lead")

    def test_roundtrip_to_dict_and_from_dict(self):
        binding = JobApplicationBinding.create(
            profile_id="prof_abc", job_id="job_xyz", job_title="Engineer",
        )
        binding.extracted_themes = ["agile", "teamwork"]
        binding.match_summary = "2 requirements matched"
        binding.coverage_score = 0.75
        payload = binding.to_dict()
        restored = JobApplicationBinding.from_dict(payload)
        self.assertEqual(restored.binding_id, binding.binding_id)
        self.assertEqual(restored.job_title, "Engineer")
        self.assertEqual(restored.extracted_themes, ["agile", "teamwork"])
        self.assertEqual(restored.match_summary, "2 requirements matched")
        self.assertEqual(restored.coverage_score, 0.75)


class ProfileRequirementMatchModelTests(unittest.TestCase):
    def test_create_and_roundtrip(self):
        match = ProfileRequirementMatch(
            requirement_id="req_1", requirement_text="Python",
            requirement_category=REQUIREMENT_CATEGORY_SKILL,
            match_status=MATCH_STATUS_STRONG,
            matched_evidence_ids=["exp_1"], match_score=0.85,
            match_detail="Strong evidence match",
            evidence_snippets=[{"experience_id": "exp_1", "snippet": "Dev..."}],
        )
        payload = match.to_dict()
        restored = ProfileRequirementMatch.from_dict(payload)
        self.assertEqual(restored.requirement_id, "req_1")
        self.assertEqual(restored.match_status, MATCH_STATUS_STRONG)
        self.assertEqual(restored.matched_evidence_ids, ["exp_1"])
        self.assertEqual(restored.match_score, 0.85)

    def test_default_match_status_is_missing(self):
        match = ProfileRequirementMatch(requirement_id="req_1", requirement_text="Unknown")
        self.assertEqual(match.match_status, MATCH_STATUS_MISSING)


class ApplicationBindingCRUDTests(unittest.TestCase):
    def setUp(self):
        self.profile = CareerProfile.create(user_id="user_test", name="Test Profile")
        self.profile.metadata = {
            "work_experiences": [
                {
                    "experience_id": "exp_1",
                    "profile_id": self.profile.profile_id,
                    "employer": "Acme Corp",
                    "job_title": "Senior Python Developer",
                    "description": "Built Python microservices, AWS, Docker",
                    "status": WORK_EXPERIENCE_STATUS_ACTIVE,
                },
                {
                    "experience_id": "exp_2",
                    "profile_id": self.profile.profile_id,
                    "employer": "Old Corp",
                    "job_title": "Legacy Developer",
                    "description": "Maintained legacy COBOL systems",
                    "status": WORK_EXPERIENCE_STATUS_MERGED,
                },
            ]
        }

    def test_list_application_bindings_empty(self):
        bindings = list_application_bindings(self.profile)
        self.assertEqual(len(bindings), 0)

    def test_create_application_binding_with_matching(self):
        binding = create_application_binding(
            self.profile,
            job_id="job_xyz", job_title="Python Engineer",
            company="Tech Corp", location="Berlin",
            target_role="Backend Developer",
            description_text=(
                "We need a Senior Python Developer with experience in AWS and Docker. "
                "Must have strong knowledge of microservices."
            ),
        )
        self.assertTrue(binding.binding_id.startswith("bind_"))
        self.assertEqual(binding.job_title, "Python Engineer")
        self.assertTrue(len(binding.extracted_requirements) > 0)
        self.assertTrue(len(binding.requirement_matches) > 0)
        strong_matches = [m for m in binding.requirement_matches if m.match_status == MATCH_STATUS_STRONG]
        self.assertTrue(len(strong_matches) > 0)

    def test_create_binding_only_matches_verified_evidence(self):
        binding = create_application_binding(
            self.profile,
            job_id="job_abc", job_title="COBOL Developer",
            company="Old Corp",
            description_text="We need a COBOL Developer with legacy systems experience.",
        )
        for match in binding.requirement_matches:
            for evidence_id in match.matched_evidence_ids:
                self.assertNotEqual(evidence_id, "exp_2")

    def test_get_application_binding(self):
        binding = create_application_binding(
            self.profile, job_id="job_test", job_title="Test Role",
        )
        retrieved = get_application_binding(self.profile, binding.binding_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.binding_id, binding.binding_id)

    def test_get_nonexistent_binding_returns_none(self):
        result = get_application_binding(self.profile, "nonexistent")
        self.assertIsNone(result)

    def test_delete_application_binding(self):
        binding = create_application_binding(
            self.profile, job_id="job_delete", job_title="Delete Me",
        )
        delete_application_binding(self.profile, binding.binding_id)
        self.assertIsNone(get_application_binding(self.profile, binding.binding_id))

    def test_delete_nonexistent_binding_raises_key_error(self):
        with self.assertRaises(KeyError):
            delete_application_binding(self.profile, "nonexistent")

    def test_list_bindings_after_create(self):
        create_application_binding(self.profile, job_id="job_1", job_title="Role 1")
        create_application_binding(self.profile, job_id="job_2", job_title="Role 2")
        bindings = list_application_bindings(self.profile)
        self.assertEqual(len(bindings), 2)

    def test_binding_preserves_profile_reference(self):
        binding = create_application_binding(
            self.profile, job_id="job_preserve", job_title="Preserved Role",
        )
        raw = self.profile.metadata.get("application_bindings", [])
        self.assertEqual(len(raw), 1)
        self.assertEqual(raw[0]["binding_id"], binding.binding_id)


if __name__ == "__main__":
    unittest.main()

        self.assertEqual(match.match_score, 0.0)

        summary = _build_match_summary(matches)
        self.assertIn("strongly matched", summary)
        self.assertIn("partially matched", summary)
        self.assertIn("no matching evidence", summary)

    def test_summary_for_empty_matches(self):
        summary = _build_match_summary([])
        self.assertIn("No requirements", summary)

        requirement = {
            "requirement_id": "req_1",
            "requirement_text": "Quantum computing",
            "requirement_category": REQUIREMENT_CATEGORY_SKILL,
        }
        match = _match_requirement(requirement, [])
        self.assertEqual(match.match_status, MATCH_STATUS_MISSING)
        self.assertEqual(match.match_score, 0.0)

    def test_missing_match_when_evidence_unrelated(self):
        requirement = {
            "requirement_id": "req_1",
            "requirement_text": "Quantum computing",
            "requirement_category": REQUIREMENT_CATEGORY_SKILL,
        }
        evidence = [
            WorkExperienceRecord(
                experience_id="exp_1", profile_id="prof_1",
                job_title="Pastry Chef", employer="Bakery",
                description="Baked croissants",
                status=WORK_EXPERIENCE_STATUS_ACTIVE,
            ),
        ]
        match = _match_requirement(requirement, evidence)
        self.assertEqual(match.match_status, MATCH_STATUS_MISSING)

    def test_empty_description_returns_empty(self):
        result = analyse_job_requirements("")
        self.assertEqual(len(result["requirements"]), 0)
        self.assertEqual(len(result["themes"]), 0)
