from types import SimpleNamespace

from backend.api.server import _merge_profile_metadata
from backend.profiles.cv_profile_extraction import normalize_profile_payload


def test_profile_editor_fields_survive_settings_roundtrip():
    profile = {
        "name": "Test User", "phone": "+49 123", "competencies": ["SQL", "Product Design"],
        "education": [{"institution": "Example University", "degree_title": "MSc", "field": "Computer Science",
                       "gpa": "1.5", "start_date": "2020-10", "end_date": "2022-06", "period": "2020–2022", "current": False}],
        "recent_experience": [{"title": "Designer", "company": "Example", "job_type": "Full-time",
                               "location": "Berlin", "start_date": "2022-06", "end_date": "", "current": True,
                               "description": "Design team", "bullets": ["Built a product", "Led research"]}],
    }
    user = SimpleNamespace(email="user@example.com", display_name="Test User", metadata={})
    saved = _merge_profile_metadata({}, profile, user)
    reread = _merge_profile_metadata(saved, {}, user)
    assert reread["phone"] == "+49 123"
    assert reread["education"][0]["degree_title"] == "MSc"
    for key in ("field", "gpa", "start_date", "end_date", "current"):
        assert reread["education"][0][key] == profile["education"][0][key]
    for key in ("job_type", "location", "current", "bullets"):
        assert reread["recent_experience"][0][key] == profile["recent_experience"][0][key]
    assert reread["competencies"] == ["SQL", "Product Design"]


def test_clear_profile_values_does_not_restore_old_text_or_skills():
    user = SimpleNamespace(email="user@example.com", display_name="Test User", metadata={})
    saved = _merge_profile_metadata({"website": "https://example.com", "summary": "Old", "competencies": ["SQL"]},
                                    {"website": "", "summary": "", "competencies": []}, user)
    assert saved["website"] == ""
    assert saved["summary"] == ""
    assert saved["competencies"] == []


def test_legacy_cv_education_is_retained_when_new_fields_are_absent():
    old = {"education": [{"degree_title": "BSc", "institution": "Example", "period": "2010–2014", "details": ["Research"]}]}
    normalized = normalize_profile_payload(old)
    assert normalized["education"][0]["period"] == "2010–2014"
    assert normalized["education"][0]["details"] == ["Research"]


def test_application_answers_are_explicit_and_whitelisted():
    user = SimpleNamespace(email="user@example.com", display_name="Test User", metadata={})
    saved = _merge_profile_metadata({}, {"application_details": {"gender": "Decline to state", "requires_sponsorship": "No", "unexpected": "value"}}, user)
    assert saved["application_details"] == {"gender": "Decline to state", "requires_sponsorship": "No"}
    assert _merge_profile_metadata(saved, {}, user)["application_details"] == saved["application_details"]


def test_skill_tags_keep_commas_inside_a_single_skill_and_all_bullets():
    profile = normalize_profile_payload({"competencies": ["GenAI tools (OpenAI, Hugging Face)", "SQL"], "recent_experience": [{"title": "Analyst", "bullets": [f"Outcome {i}" for i in range(12)]}]})
    assert profile["competencies"] == ["GenAI tools (OpenAI, Hugging Face)", "SQL"]
    assert len(profile["recent_experience"][0]["bullets"]) == 12
