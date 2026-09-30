from scripts.refresh_live_company_manifest import catalog_row, merge_rows


def test_catalog_row_does_not_promote_unverified_urls():
    row = catalog_row(
        {"company_id": "c2", "canonical_name": "New Co", "updated_at": "2026-09-28T00:00:00Z"},
        {"fields": {"website": {"value": "https://new.example", "status": "known"}}},
        None,
    )
    assert row["website_url"] == "https://new.example"
    assert row["website_discovery_status"] == "missing"


def test_catalog_row_promotes_only_verified_profile_identity():
    profile = {"additional_fields": {
        "website": {"value": "https://new.example", "verified_at": "2026-09-28T00:00:00Z"},
        "linkedin_company_url": {"value": "https://linkedin.com/company/new", "confidence": "provider_verified"},
        "linkedin_company_id": {"value": "123", "verified_at": "2026-09-28T00:00:00Z", "provenance": {"source": "provider"}},
    }}
    row = catalog_row({"company_id": "c2", "canonical_name": "New Co"}, profile, None)
    assert row["website_discovery_status"] == "verified"
    assert row["linkedin_company_id_status"] == "verified"
    assert row["linkedin_company_id_url_used"] == row["linkedin_company_url"]


def test_merge_adds_each_missing_live_company_once():
    rows, added = merge_rows(
        [{"canonical_CompanyID": "c1", "company_name": "Old"}],
        ["canonical_CompanyID", "company_name"],
        [{"canonical_CompanyID": "c1", "company_name": "Duplicate"}, {"canonical_CompanyID": "c2", "company_name": "New"}],
    )
    assert added == 1
    assert [row["canonical_CompanyID"] for row in rows] == ["c1", "c2"]
