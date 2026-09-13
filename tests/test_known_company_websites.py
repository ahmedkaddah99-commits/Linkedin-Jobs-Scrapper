import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from apply_known_company_websites import match_known_rows


def test_known_company_names_match_suffixes_and_prefer_valid_duplicate_identity():
    known = [
        {"company_name_as_listed": "Inverto \\", "official_website": "https://www.inverto.com/"},
        {"company_name_as_listed": "Durr Group", "official_website": "https://www.durr.com/"},
    ]
    master = [
        {
            "company_name": "Inverto | A BCG Company",
            "canonical_CompanyID": "//",
            "linkedin_company_id": "55589",
        },
        {
            "company_name": "Durr Group",
            "canonical_CompanyID": "canonical-valid",
            "linkedin_company_id": "67873",
        },
        {
            "company_name": "Durr Group",
            "canonical_CompanyID": "//",
            "linkedin_company_id": "18120956",
        },
    ]

    result = match_known_rows(known, master)

    assert result["matches"] == {0: 0, 1: 1}
    assert result["unmatched"] == []
    assert result["ambiguous"] == {}
