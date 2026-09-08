import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.domain.models import (
    MERGE_SUGGESTION_STATUS_CONFIRMED,
    MERGE_SUGGESTION_STATUS_DISMISSED,
    MERGE_SUGGESTION_STATUS_PENDING,
    WORK_EXPERIENCE_SOURCE_KIND_EXTRACTED,
    WORK_EXPERIENCE_SOURCE_KIND_MANUAL,
    WORK_EXPERIENCE_STATUS_ACTIVE,
    WORK_EXPERIENCE_STATUS_MERGED,
    CareerProfile,
    WorkExperienceRecord,
    MergeSuggestion,
    utc_now_iso,
)
from backend.work_experience.service import (
    confirm_merge,
    create_experience,
    delete_experience,
    dismiss_merge_suggestion,
    get_experience,
    get_merge_suggestions,
    list_experiences,
    update_experience,
)


def _mock_profile():
    profile = CareerProfile.create(user_id="user_test", name="Test Profile")
    return profile


class WorkExperienceRecordModelTests(unittest.TestCase):
    def test_create_minimal(self):
        record = WorkExperienceRecord.create(profile_id="prof_abc")
        self.assertEqual(record.profile_id, "prof_abc")
        self.assertEqual(record.employer, "")
        self.assertEqual(record.job_title, "")
        self.assertEqual(record.source_kind, WORK_EXPERIENCE_SOURCE_KIND_MANUAL)
        self.assertEqual(record.status, WORK_EXPERIENCE_STATUS_ACTIVE)
        self.assertTrue(record.experience_id.startswith("exp_"))
        self.assertTrue(record.created_at)
        self.assertTrue(record.updated_at)

    def test_create_full(self):
        record = WorkExperienceRecord.create(
            profile_id="prof_abc",
            employer="ACME Corp",
            job_title="Senior Engineer",
            location="San Francisco, CA",
            start_date="Jan 2020",
            end_date="Dec 2023",
            employment_type="full_time",
            description="Led platform team.",
            source_kind=WORK_EXPERIENCE_SOURCE_KIND_MANUAL,
            source_asset_ids=["asset_1"],
            sort_order=0,
        )
        self.assertEqual(record.employer, "ACME Corp")
        self.assertEqual(record.job_title, "Senior Engineer")
        self.assertEqual(record.location, "San Francisco, CA")
        self.assertEqual(record.start_date, "Jan 2020")
        self.assertEqual(record.end_date, "Dec 2023")
        self.assertEqual(record.employment_type, "full_time")
        self.assertEqual(record.description, "Led platform team.")
        self.assertEqual(record.source_asset_ids, ["asset_1"])
        self.assertEqual(record.sort_order, 0)

    def test_to_dict_and_from_dict_roundtrip(self):
        record = WorkExperienceRecord.create(
            profile_id="prof_abc",
            employer="ACME Corp",
            job_title="Engineer",
        )
        d = record.to_dict()
        restored = WorkExperienceRecord.from_dict(d)
        self.assertEqual(restored.experience_id, record.experience_id)
        self.assertEqual(restored.employer, "ACME Corp")
        self.assertEqual(restored.job_title, "Engineer")


class MergeSuggestionModelTests(unittest.TestCase):
    def test_create(self):
        suggestion = MergeSuggestion.create(
            profile_id="prof_abc",
            experience_ids=["exp_1", "exp_2"],
            suggested_merged_record={"employer": "ACME"},
            match_score=0.85,
            match_reason="same employer",
        )
        self.assertEqual(suggestion.profile_id, "prof_abc")
        self.assertEqual(suggestion.experience_ids, ["exp_1", "exp_2"])
        self.assertEqual(suggestion.match_score, 0.85)
        self.assertEqual(suggestion.match_reason, "same employer")
        self.assertEqual(suggestion.status, MERGE_SUGGESTION_STATUS_PENDING)
        self.assertTrue(suggestion.suggestion_id.startswith("merge_"))

    def test_to_dict_and_from_dict(self):
        suggestion = MergeSuggestion.create(
            profile_id="prof_abc",
            experience_ids=["exp_1"],
            match_score=0.5,
        )
        d = suggestion.to_dict()
        restored = MergeSuggestion.from_dict(d)
        self.assertEqual(restored.suggestion_id, suggestion.suggestion_id)
        self.assertEqual(restored.match_score, 0.5)


class WorkExperienceServiceTests(unittest.TestCase):
    def setUp(self):
        self.profile = _mock_profile()

    def test_create_experience(self):
        record = create_experience(self.profile, {"employer": "ACME Corp", "job_title": "Engineer"})
        self.assertEqual(record.employer, "ACME Corp")
        self.assertIn("work_experiences", self.profile.metadata)

    def test_list_experiences(self):
        create_experience(self.profile, {"employer": "First Corp", "sort_order": 0})
        create_experience(self.profile, {"employer": "Second Corp", "sort_order": 1})
        results = list_experiences(self.profile)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].employer, "First Corp")
        self.assertEqual(results[1].employer, "Second Corp")

    def test_list_excludes_merged(self):
        exp = create_experience(self.profile, {"employer": "To Merge"})
        update_experience(self.profile, exp.experience_id, {"status": WORK_EXPERIENCE_STATUS_MERGED})
        results = list_experiences(self.profile)
        self.assertEqual(len(results), 0)

    def test_get_experience(self):
        created = create_experience(self.profile, {"employer": "GetMe"})
        found = get_experience(self.profile, created.experience_id)
        self.assertIsNotNone(found)
        self.assertEqual(found.employer, "GetMe")

    def test_get_nonexistent(self):
        found = get_experience(self.profile, "nonexistent")
        self.assertIsNone(found)

    def test_update_experience(self):
        created = create_experience(self.profile, {"employer": "Old"})
        updated = update_experience(self.profile, created.experience_id,
                                    {"employer": "New", "job_title": "Manager"})
        self.assertEqual(updated.employer, "New")
        self.assertEqual(updated.job_title, "Manager")

    def test_update_nonexistent(self):
        pass


class MergeSuggestionServiceTests(unittest.TestCase):
    def setUp(self):
        self.profile = _mock_profile()

    def test_no_suggestions_for_few_experiences(self):
        create_experience(self.profile, {"employer": "OnlyOne"})
        suggestions = get_merge_suggestions(self.profile)
        self.assertEqual(len(suggestions), 0)

    def test_generates_suggestions_for_similar(self):
        create_experience(self.profile, {
            "employer": "ACME Corp", "job_title": "Software Engineer", "location": "San Francisco"})
        create_experience(self.profile, {
            "employer": "ACME Corporation", "job_title": "Software Engineer II", "location": "San Francisco, CA"})
        suggestions = get_merge_suggestions(self.profile)
        self.assertGreaterEqual(len(suggestions), 1)
        self.assertGreaterEqual(suggestions[0].match_score, 0.5)

    def test_no_suggestions_for_different(self):
        create_experience(self.profile, {"employer": "ACME Corp", "job_title": "Software Engineer"})
        create_experience(self.profile, {"employer": "XYZ Ltd", "job_title": "Barista"})
        suggestions = get_merge_suggestions(self.profile)
        self.assertEqual(len(suggestions), 0)

    def test_confirm_merge(self):
        exp_a = create_experience(self.profile, {
            "employer": "ACME Corp", "job_title": "Engineer", "location": "SF"})
        exp_b = create_experience(self.profile, {
            "employer": "ACME Corporation", "job_title": "Senior Engineer", "location": "SF"})
        suggestions = get_merge_suggestions(self.profile)
        self.assertGreaterEqual(len(suggestions), 1)

        merged = confirm_merge(self.profile, suggestions[0].suggestion_id)
        self.assertIsNotNone(merged)
        for exp_id in [exp_a.experience_id, exp_b.experience_id]:
            found = get_experience(self.profile, exp_id)
            self.assertIsNotNone(found)
            self.assertEqual(found.status, WORK_EXPERIENCE_STATUS_MERGED)
            self.assertEqual(found.merged_into_id, merged.experience_id)

        active = list_experiences(self.profile)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].experience_id, merged.experience_id)

    def test_confirm_merge_already_confirmed(self):
        create_experience(self.profile, {"employer": "ACME Corp", "job_title": "E1"})
        create_experience(self.profile, {"employer": "ACME Corp", "job_title": "E2"})
        suggestions = get_merge_suggestions(self.profile)
        confirm_merge(self.profile, suggestions[0].suggestion_id)
        with self.assertRaises(ValueError):
            confirm_merge(self.profile, suggestions[0].suggestion_id)

    def test_dismiss_merge_suggestion(self):
        create_experience(self.profile, {"employer": "ACME Corp", "job_title": "E1"})
        create_experience(self.profile, {"employer": "ACME Corp", "job_title": "E2"})
        suggestions = get_merge_suggestions(self.profile)
        dismiss_merge_suggestion(self.profile, suggestions[0].suggestion_id)

        metadata = dict(self.profile.metadata or {})
        from backend.work_experience.service import _read_merge_suggestions
        raw = _read_merge_suggestions(metadata)
        dismissed = [s for s in raw if s.get("status") == MERGE_SUGGESTION_STATUS_DISMISSED]
        self.assertEqual(len(dismissed), 1)

    def test_dismiss_nonexistent(self):
        with self.assertRaises(KeyError):
            dismiss_merge_suggestion(self.profile, "nonexistent")

    def test_delete_cleans_merge_suggestions(self):
        exp = create_experience(self.profile, {"employer": "ACME Corp", "job_title": "E1"})
        create_experience(self.profile, {"employer": "ACME Corp", "job_title": "E2"})
        get_merge_suggestions(self.profile)

        metadata = dict(self.profile.metadata or {})
        from backend.work_experience.service import _read_merge_suggestions
        before_count = len(_read_merge_suggestions(metadata))
        self.assertGreater(before_count, 0)

        delete_experience(self.profile, exp.experience_id)
        metadata = dict(self.profile.metadata or {})
        after = _read_merge_suggestions(metadata)
        self.assertEqual(len(after), 0)


class HeuristicExtractionTests(unittest.TestCase):
    def test_parse_simple_block(self):
        from backend.work_experience.service import _heuristic_parse_experiences
        text = "Software Engineer at ACME Corp\nJan 2020 - Dec 2023\nRemote\nBuilt microservices.\n"
        results = _heuristic_parse_experiences(text)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["job_title"], "Software Engineer")
        self.assertEqual(results[0]["employer"], "ACME Corp")
        self.assertEqual(results[0]["start_date"], "Jan 2020")
        self.assertEqual(results[0]["end_date"], "Dec 2023")
        self.assertEqual(results[0]["location"], "Remote")

    def test_parse_dash_separator(self):
        from backend.work_experience.service import _heuristic_parse_experiences
        text = "ACME Corp - Product Manager\n2020 - 2023\n"
        results = _heuristic_parse_experiences(text)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["employer"], "ACME Corp")
        self.assertEqual(results[0]["job_title"], "Product Manager")

    def test_parse_multiple_blocks(self):
        from backend.work_experience.service import _heuristic_parse_experiences
        text = "Engineer at ACME Corp\n2020 - 2023\n\nManager at XYZ Ltd\n2023 - Present\n"
        results = _heuristic_parse_experiences(text)
        self.assertGreaterEqual(len(results), 2)


if __name__ == "__main__":
    unittest.main()