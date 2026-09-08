import csv
import json

from scripts.clean_master_company_url import (
    consolidate_group,
    dedupe_json,
    normalize_domain,
    normalize_linkedin_url,
    normalize_url,
    prepare_row,
    run_cleaning,
)


def test_url_normalization_removes_tracking_and_normalizes_host():
    assert normalize_url("HTTP://WWW.Example.COM/path/?utm_source=x&keep=yes#fragment") == "https://www.example.com/path?keep=yes"
    assert normalize_domain("https://sub.example.co.uk/path") == "example.co.uk"
    assert normalize_linkedin_url("https://de.linkedin.com/company/Acme/?trk=foo#top") == "https://www.linkedin.com/company/Acme"


def test_json_arrays_are_deduplicated_without_losing_order():
    assert dedupe_json(["a", "a", {"x": 1}, {"x": 1}, "b"]) == ["a", {"x": 1}, "b"]


def test_company_name_precedence_and_website_selection():
    row = {
        "No": "1",
        "company": "Original Name",
        "company_name": "LinkedIn Display Name",
        "companyenrich_name": "Enrichment Name",
        "website": "HTTP://WWW.Example.COM/?utm_campaign=ignored",
        "companyenrich_website": "https://other.example/",
        "Company-LinkedIn-url": "https://www.linkedin.com/company/acme/?trk=ignored",
    }
    prepared = [prepare_row(row, 0)]
    canonical, _, _ = consolidate_group(prepared)
    assert canonical["company_name"] == "LinkedIn Display Name"
    assert canonical["website_url"] == "https://www.example.com"
    assert canonical["domain"] == "example.com"
    assert canonical["linkedin_company_url"] == "https://www.linkedin.com/company/acme"
    assert canonical["linkedin_page_type"] == "company"


def test_run_cleaning_merges_strong_identities_and_reviews_shared_domains(tmp_path):
    input_path = tmp_path / "input.csv"
    output_dir = tmp_path / "out"
    fieldnames = [
        "No",
        "company",
        "company_name",
        "website",
        "Company-LinkedIn-url",
        "companyenrich_id",
        "companyenrich_profile_json",
        "page_valid",
        "scraped_at",
    ]
    rows = [
        {
            "No": "1",
            "company": "Alpha GmbH",
            "company_name": "Alpha GmbH",
            "website": "https://example.com/",
            "Company-LinkedIn-url": "https://www.linkedin.com/company/alpha/?trk=one",
            "companyenrich_id": "ce-1",
            "companyenrich_profile_json": '{"source": "one"}',
            "page_valid": "TRUE",
            "scraped_at": "2026-08-01T00:00:00Z",
        },
        {
            "No": "2",
            "company": "Alpha",
            "company_name": "Alpha",
            "website": "https://other.example.com",
            "Company-LinkedIn-url": "https://www.linkedin.com/company/alpha/",
            "companyenrich_id": "ce-1",
            "companyenrich_profile_json": '{"source": "two"}',
            "page_valid": "TRUE",
            "scraped_at": "2026-08-02T00:00:00Z",
        },
        {
            "No": "3",
            "company": "Example Subsidiary",
            "company_name": "Example Subsidiary",
            "website": "https://example.com/subsidiary",
            "Company-LinkedIn-url": "https://www.linkedin.com/company/example-subsidiary",
            "companyenrich_id": "ce-2",
            "companyenrich_profile_json": '{"source": "three"}',
            "page_valid": "TRUE",
            "scraped_at": "2026-08-03T00:00:00Z",
        },
        {
            "No": "4",
            "company": "Example University",
            "company_name": "Example University",
            "website": "https://example.com/education",
            "Company-LinkedIn-url": "https://www.linkedin.com/school/example-university",
            "companyenrich_id": "ce-3",
            "companyenrich_profile_json": '{"source": "four"}',
            "page_valid": "TRUE",
            "scraped_at": "2026-08-04T00:00:00Z",
        },
    ]
    with input_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    summary = run_cleaning(input_path, output_dir)

    assert summary["original_rows"] == 4
    assert summary["canonical_rows"] == 3
    assert summary["merged_rows"] == 1
    assert summary["possible_duplicates"] >= 1
    assert input_path.exists()

    with (output_dir / "Master-Company-Url-canonical.csv").open(encoding="utf-8-sig", newline="") as handle:
        canonical_rows = list(csv.DictReader(handle))
    assert len(canonical_rows) == 3
    assert any(row["source_row_numbers"] == '["1", "2"]' for row in canonical_rows)
    assert all(row["linkedin_page_type"] in {"company", "school"} for row in canonical_rows)

    with (output_dir / "company_enrichment_audit.csv").open(encoding="utf-8-sig", newline="") as handle:
        audit_rows = list(csv.DictReader(handle))
    assert len(audit_rows) == 4
    assert json.loads(audit_rows[0]["companyenrich_profile_json"])["source"] == "one"

    with (output_dir / "company_possible_duplicates.csv").open(encoding="utf-8-sig", newline="") as handle:
        possible_rows = list(csv.DictReader(handle))
    assert any(row["reason"] == "shared_domain" for row in possible_rows)

    with (output_dir / "company_merge_conflicts.csv").open(encoding="utf-8-sig", newline="") as handle:
        conflict_rows = list(csv.DictReader(handle))
    assert any(row["conflicting_field"] == "website_url" for row in conflict_rows)
