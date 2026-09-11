from __future__ import annotations

from backend.application.company_identity_canonicalization import (
    build_company_crosswalk,
    canonicalize_registry_rows,
    canonical_company_id_for_row,
)


def test_exact_linkedin_url_converges_existing_ids_and_keeps_richer_survivor() -> None:
    rows = [
        {
            "canonical_CompanyID": "company-a",
            "company_name": "Acme",
            "linkedin_company_url": "https://www.linkedin.com/company/acme/",
            "linkedin_company_id": "100",
            "website_url": "https://acme.example",
        },
        {
            "canonical_CompanyID": "company-b",
            "company_name": "Acme Holdings",
            "linkedin_company_url": "https://de.linkedin.com/company/acme?trk=jobs",
            "linkedin_company_id": "100",
            "website_url": "https://acme.example",
            "description": "A verified company profile with a current official website and logo.",
            "logo_url": "https://cdn.example/acme.png",
            "enrichment_status": "complete",
        },
        {
            "canonical_CompanyID": "//",
            "company_name": "Acme old observation",
            "linkedin_company_url": "https://www.linkedin.com/company/acme",
            "linkedin_company_id": "100",
        },
    ]

    result = build_company_crosswalk(rows)

    assert result.mapping_by_row[0] == "company-b"
    assert result.mapping_by_row[1] == "company-b"
    assert result.mapping_by_row[2] == "company-b"
    assert result.report["duplicate_merges"] == 1
    assert result.report["sentinel_rows_after"] == 0
    assert result.report["merge_receipts"][0]["winner_company_id"] == "company-b"


def test_missing_id_uses_normalized_linkedin_org_url_and_is_order_independent() -> None:
    rows = [
        {
            "canonical_CompanyID": "//",
            "company_name": "Beta",
            "linkedin_company_url": "https://www.linkedin.com/company/beta/",
            "linkedin_company_id": "200",
        },
        {
            "canonical_CompanyID": "",
            "company_name": "Gamma",
            "linkedin_company_url": "https://www.linkedin.com/company/gamma/",
            "linkedin_company_id": "201",
        },
    ]

    forward = build_company_crosswalk(rows)
    reverse = build_company_crosswalk(reversed(rows))

    assert forward.mapping_by_row[0].startswith("canonical_company_")
    assert forward.mapping_by_row[1].startswith("canonical_company_")
    forward_by_url = {
        row["linkedin_company_url"]: forward.mapping_by_row[index]
        for index, row in enumerate(rows)
    }
    reverse_rows = list(reversed(rows))
    reverse_by_url = {
        row["linkedin_company_url"]: reverse.mapping_by_row[index]
        for index, row in enumerate(reverse_rows)
    }
    assert forward_by_url == reverse_by_url
    assert forward.report["url_seed_allocations"] == 2


def test_numeric_and_companyenrich_evidence_corrobates_url_without_becoming_domain_only_merge() -> None:
    rows = [
        {
            "canonical_CompanyID": "company-a",
            "company_name": "Shared Domain A",
            "linkedin_company_url": "https://www.linkedin.com/company/a",
            "linkedin_company_id": "300",
            "website_url": "https://shared.example",
        },
        {
            "canonical_CompanyID": "company-b",
            "company_name": "Shared Domain B",
            "linkedin_company_url": "https://www.linkedin.com/company/b",
            "linkedin_company_id": "301",
            "website_url": "https://shared.example",
        },
        {
            "canonical_CompanyID": "//",
            "company_name": "Shared Domain C",
            "linkedin_company_url": "https://www.linkedin.com/company/c",
            "linkedin_company_id": "302",
            "website_url": "https://shared.example",
        },
    ]

    result = build_company_crosswalk(rows)

    assert len(set(result.mapping_by_row.values())) == 3
    assert result.report["domain_only_non_merges"] >= 1


def test_domain_only_rows_get_distinct_seeds_and_do_not_merge() -> None:
    result = build_company_crosswalk([
        {"canonical_CompanyID": "//", "company_name": "One", "website_url": "https://shared.example"},
        {"canonical_CompanyID": "//", "company_name": "Two", "website_url": "https://shared.example"},
    ])

    assert len(set(result.mapping_by_row.values())) == 2


def test_canonicalized_registry_preserves_alias_evidence_and_no_sentinels() -> None:
    rows = [
        {
            "canonical_CompanyID": "//",
            "company_name": "Delta Old Name",
            "linkedin_company_url": "https://www.linkedin.com/company/delta",
            "linkedin_company_id": "400",
        }
    ]

    result = canonicalize_registry_rows(rows)
    row = result.rows[0]

    assert row["canonical_CompanyID"] == canonical_company_id_for_row(rows[0])
    assert row["canonical_company_id"] == row["canonical_CompanyID"]
    assert row["identity_resolution_status"] == "allocated_url_seed"
    assert "Delta Old Name" in row["identity_aliases"]
    assert "linkedin_url:https://www.linkedin.com/company/delta" in row["identity_aliases"]
    assert result.report["canonical_ids_after"] == 1
