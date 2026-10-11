import json

from scripts.apply_linkedin_company_gap_results import load_unambiguous_offers


def test_load_unambiguous_offers_deduplicates_and_rejects_conflicts(tmp_path):
    path = tmp_path / "results.jsonl"
    rows = [
        {"company_id": "c1", "provider_status": "matched", "collectible_offers": {"website": "https://a.example", "industry": "Tech"}},
        {"company_id": "c1", "provider_status": "matched", "collectible_offers": {"website": "https://a.example", "industry": "Finance"}},
        {"company_id": "c2", "provider_status": "not_found", "collectible_offers": {"website": "https://b.example"}},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    offers, stats = load_unambiguous_offers(path)

    assert offers == {"c1": {"website": "https://a.example"}}
    assert stats["conflicting_industry"] == 1
    assert stats["nonmatched_rows"] == 1
