from scripts.apply_company_reuse_and_validate_boards import missing_updates, check_board


def test_missing_only_and_no_false_verification():
    original = {"fields": {"domain": {"value": "kept.example"}}, "additional_fields": {}}
    updated, changed = missing_updates(original, {"domain": ["new.example"], "description": ["Restored description"], "linkedin_company_id": ["1234"]}, "now")
    assert updated["fields"]["domain"]["value"] == "kept.example"
    assert set(changed) == {"description", "linkedin_company_id"}
    assert updated["additional_fields"]["description"]["verified_at"] is None
    assert "description" not in original["additional_fields"]


def test_ambiguous_or_invalid_values_not_applied():
    updated, changed = missing_updates({}, {"description": ["one", "two"], "linkedin_company_id": ["not-numeric"]}, "now")
    assert changed == []
    assert updated == {}


def test_populated_additional_field_is_preserved():
    updated, changed = missing_updates({"additional_fields": {"domain": {"value": "kept.example"}}}, {"domain": ["new.example"]}, "now")
    assert changed == []
    assert updated["additional_fields"]["domain"]["value"] == "kept.example"


def test_success_status_alone_does_not_validate_board(monkeypatch):
    monkeypatch.setattr("scripts.apply_company_reuse_and_validate_boards.public_get", lambda url: (url, 200, "<html>Hello world</html>"))
    company = {"company_id": "c", "name": "Some Company", "selected": ["https://example.com"], "homepages": [], "website": "https://example.com"}
    result = check_board(company, "https://example.com/careers")
    assert result["status"] == "career_content_not_confirmed"


def test_unrelated_external_board_not_promoted(monkeypatch):
    monkeypatch.setattr("scripts.apply_company_reuse_and_validate_boards.public_get", lambda url: (url, 200, "<html>Careers at Other Company. Open positions.</html>"))
    company = {"company_id": "c", "name": "Some Company", "selected": [], "homepages": [], "website": ""}
    assert check_board(company, "https://jobs.lever.co/other")["status"] == "company_identity_not_confirmed"
