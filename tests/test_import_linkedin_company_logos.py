from __future__ import annotations

import csv
import io
import json

from scripts.import_linkedin_company_logos import (
    build_company_indexes,
    load_linkedin_logo_candidates,
    merge_logo_into_profile,
    normalise_linkedin_slug,
)


def test_loads_linkedin_logo_column_but_rejects_companyenrich_logo(tmp_path):
    path = tmp_path / "companies.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "canonical_CompanyID",
                "company_name",
                "linkedin_company_url",
                "logo_url",
                "logo_source",
                "companyenrich_logo_url",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "canonical_CompanyID": "canonical-acme",
                "company_name": "Acme",
                "linkedin_company_url": "https://www.linkedin.com/company/acme/",
                "logo_url": "https://media.licdn.com/acme.png",
                "logo_source": "LinkedIn",
                "companyenrich_logo_url": "https://api.companyenrich.com/acme.png",
            }
        )
        writer.writerow(
            {
                "canonical_CompanyID": "canonical-other",
                "company_name": "Other",
                "linkedin_company_url": "https://www.linkedin.com/company/other/",
                "logo_url": "https://api.companyenrich.com/other.png",
                "logo_source": "companyenrich_autocomplete",
                "companyenrich_logo_url": "https://api.companyenrich.com/other.png",
            }
        )

    candidates = load_linkedin_logo_candidates(path)

    assert len(candidates) == 1
    assert candidates[0]["canonical_company_id"] == "canonical-acme"
    assert candidates[0]["logo_source"] == "LinkedIn"
    assert normalise_linkedin_slug(candidates[0]["linkedin_company_url"]) == "acme"


def test_company_index_resolves_linkedin_url_before_ambiguous_name():
    indexes = build_company_indexes(
        [
            {"company_id": "canonical-one", "canonical_name": "Acme", "provenance_url": "https://www.linkedin.com/company/acme-one"},
            {"company_id": "canonical-two", "canonical_name": "Acme", "provenance_url": "https://www.linkedin.com/company/acme-two"},
        ]
    )

    resolved = indexes.resolve({"canonical_company_id": "", "company_name": "Acme", "linkedin_company_url": "https://www.linkedin.com/company/acme-two"})

    assert resolved == ("canonical-two", "linkedin_url")


def test_merge_logo_into_existing_profile_preserves_other_fields():
    profile = {
        "schema_version": "phase_f_v3",
        "fields": {"description": {"value": "Existing", "state": "known"}},
    }

    merged = merge_logo_into_profile(
        profile,
        logo_url="https://media.licdn.com/acme.png",
        linkedin_company_url="https://www.linkedin.com/company/acme",
        verified_at="2026-09-13T10:00:00Z",
    )

    assert merged["schema_version"] == "phase_f_v3"
    assert merged["fields"]["description"]["value"] == "Existing"
    assert merged["fields"]["logo"] == {
        "value": "https://media.licdn.com/acme.png",
        "state": "known",
        "provenance": {
            "source": "linkedin_company_master",
            "url": "https://www.linkedin.com/company/acme",
        },
        "verified_at": "2026-09-13T10:00:00Z",
    }
