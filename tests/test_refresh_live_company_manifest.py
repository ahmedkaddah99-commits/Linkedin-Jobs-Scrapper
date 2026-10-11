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


def test_merge_promotes_verified_website_for_existing_company_without_replacing_identity():
    rows, added = merge_rows(
        [{"canonical_CompanyID": "c1", "company_name": "Existing", "website_url": "", "website_discovery_status": "missing"}],
        ["canonical_CompanyID", "company_name", "website_url", "website_discovery_status", "last_enriched_at"],
        [{"canonical_CompanyID": "c1", "company_name": "Different", "website_url": "https://existing.example", "website_discovery_status": "verified", "last_enriched_at": "2026-09-30T00:00:00Z"}],
    )
    assert added == 0
    assert rows[0]["company_name"] == "Existing"
    assert rows[0]["website_url"] == "https://existing.example"
    assert rows[0]["website_discovery_status"] == "verified"


def test_merge_does_not_promote_unverified_or_conflicting_website():
    rows, _ = merge_rows(
        [{"canonical_CompanyID": "c1", "website_url": "https://original.example", "website_discovery_status": "missing"}],
        ["canonical_CompanyID", "website_url", "website_discovery_status"],
        [{"canonical_CompanyID": "c1", "website_url": "https://different.example", "website_discovery_status": "verified"}],
    )
    assert rows[0]["website_url"] == "https://original.example"
    assert rows[0]["website_discovery_status"] == "missing"
