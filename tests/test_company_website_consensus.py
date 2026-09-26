import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import discover_websites_from_web_search as discovery
import discover_websites_consensus as consensus


def test_local_domain_match_prefers_unique_linkedin_slug_and_rejects_name_conflicts():
    rows = [
        {"website_url": "https://acme.example/", "linkedin_slug": "acme", "linkedin_company_id": "1", "company_name": "Acme"},
        {"website_url": "", "linkedin_slug": "acme", "linkedin_company_id": "1", "company_name": "Acme"},
        {"website_url": "https://same-name-one.example/", "linkedin_slug": "one", "linkedin_company_id": "2", "company_name": "Same Name"},
        {"website_url": "https://same-name-two.example/", "linkedin_slug": "two", "linkedin_company_id": "3", "company_name": "Same Name"},
    ]

    maps = discovery.build_local_domain_maps(rows)

    assert discovery.local_domain_for_row(rows[1], maps) == "acme.example"
    assert discovery.local_domain_for_row(rows[2], maps) == "same-name-one.example"
    assert discovery.local_domain_for_row({"website_url": "", "linkedin_slug": "missing", "linkedin_company_id": "", "company_name": "Same Name"}, maps) is None


def test_consensus_accepts_same_domain_from_two_independent_queries():
    result = discovery.select_consensus_candidate(
        [
            {"query": "q1", "candidates": [{"domain": "acme.example", "score": 14, "evidence": 5, "position": 0, "title": "Acme"}]},
            {"query": "q2", "candidates": [{"domain": "acme.example", "score": 11, "evidence": 4, "position": 1, "title": "Acme company"}]},
        ],
        "Acme",
        "acme",
    )

    assert result["status"] == "found"
    assert result["domain"] == "acme.example"


def test_consensus_rejects_conflicting_domains():
    result = discovery.select_consensus_candidate(
        [
            {"query": "q1", "candidates": [{"domain": "one.example", "score": 14, "evidence": 5, "position": 0, "title": "Acme"}]},
            {"query": "q2", "candidates": [{"domain": "two.example", "score": 14, "evidence": 5, "position": 0, "title": "Acme"}]},
        ],
        "Acme",
        "acme",
    )

    assert result["status"] == "ambiguous"
    assert result["domain"] == ""


def test_consensus_queries_include_independent_name_alias_and_slug_variants():
    queries = consensus.consensus_queries("Boston Consulting Group (BCG)", "boston-consulting-group")

    assert queries[0] == '"Boston Consulting Group (BCG)" official website'
    assert '"Boston Consulting Group (BCG)" company website' in queries
    assert '"BCG" official website' in queries
    assert '"boston consulting group" official website' in queries


def test_local_discovery_records_only_fill_blank_rows_from_exact_maps():
    records = consensus.local_discovery_records(
        [
            {"website_url": "https://example.test/", "linkedin_slug": "known", "linkedin_company_id": "1", "company_name": "Known"},
            {"website_url": "", "linkedin_slug": "known", "linkedin_company_id": "1", "company_name": "Known"},
        ]
    )

    assert records["known"]["status"] == "found"
    assert records["known"]["website_url"] == "https://example.test/"


def test_rows_without_linkedin_slug_use_stable_local_key_and_name_queries():
    row = {
        "website_url": "",
        "linkedin_slug": "",
        "linkedin_company_url": "",
        "canonical_CompanyID": "canonical-example-123",
        "company_name": "Example Holdings",
    }

    assert consensus.row_slug(row) == "missing-canonical:canonical-example-123"
    queries = consensus.consensus_queries(row["company_name"], consensus.row_slug(row))
    assert queries == [
        '"Example Holdings" official website',
        '"Example Holdings" company website',
    ]


def test_apply_discoveries_uses_missing_slug_key_for_csv_rows(tmp_path):
    fields = [
        "company_name",
        "canonical_CompanyID",
        "linkedin_company_url",
        "website_url",
        "companyenrich_free_logo_url",
    ]
    rows = [{
        "company_name": "Example Holdings",
        "canonical_CompanyID": "canonical-example-123",
        "linkedin_company_url": "",
        "website_url": "",
        "companyenrich_free_logo_url": "",
    }]
    db_path = tmp_path / "state.sqlite3"
    import sqlite3

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "create table url_resolution (normalized_url text, result_json text, companyenrich_free_logo_url text)"
        )

    summary = discovery.apply_discoveries(
        tmp_path / "output.csv",
        db_path,
        fields,
        rows,
        {
            "missing-canonical:canonical-example-123": {
                "status": "found",
                "website_url": "https://example.test/",
                "domain": "example.test",
            }
        },
        {"example.test": "https://example.test/logo.png"},
    )

    assert summary["website_urls_added"] == 1
    assert rows[0]["website_url"] == "https://example.test/"


def test_deep_query_plan_uses_context_and_independent_search_engines():
    plan = consensus.deep_query_plan({
        "company_name": "Example Holdings",
        "slug": "example-holdings",
        "headquarters_city": "Berlin",
        "headquarters_country": "Germany",
        "industry": "Financial Services",
        "prior_candidates": [{"domain": "example.test", "score": 12, "evidence": 5}],
    })

    assert {item["engine"] for item in plan} == {"bing"}
    assert any("Berlin" in item["query"] for item in plan)
    assert any("site:example.test" in item["query"] for item in plan)


def test_duckduckgo_parser_extracts_result_domains():
    page = """
    <div class="result">
      <a rel="nofollow" class="result__a" href="https://example.test/about">Example Holdings</a>
      <a class="result__url" href="https://example.test/about">example.test/about</a>
      <a class="result__snippet">Example Holdings official company site.</a>
    </div>
    """

    candidates = consensus.parse_duckduckgo_candidates(page, "Example Holdings", "example-holdings")

    assert candidates[0]["domain"] == "example.test"
    assert candidates[0]["title"] == "Example Holdings"


def test_deep_selection_requires_cross_engine_corroboration():
    accepted = consensus.select_deep_candidate(
        [
            {"engine": "bing", "query_family": "name", "query": "q1", "candidates": [{"domain": "example.test", "score": 12, "evidence": 5, "position": 0, "title": "Example Holdings"}]},
            {"engine": "duckduckgo", "query_family": "context", "query": "q2", "candidates": [{"domain": "example.test", "score": 11, "evidence": 4, "position": 1, "title": "Example Holdings"}]},
        ],
        "Example Holdings",
        "example-holdings",
    )
    rejected = consensus.select_deep_candidate(
        [
            {"engine": "bing", "query_family": "name", "query": "q1", "candidates": [{"domain": "one.test", "score": 14, "evidence": 5, "position": 0, "title": "Example Holdings"}]},
            {"engine": "bing", "query_family": "context", "query": "q2", "candidates": [{"domain": "two.test", "score": 14, "evidence": 5, "position": 0, "title": "Example Holdings"}]},
        ],
        "Example Holdings",
        "example-holdings",
    )

    assert accepted["status"] == "found"
    assert accepted["domain"] == "example.test"
    assert rejected["status"] == "ambiguous"


def test_ambiguous_tasks_excludes_filled_and_non_ambiguous_rows():
    rows = [
        {"website_url": "", "linkedin_slug": "ambiguous", "company_name": "Ambiguous Co"},
        {"website_url": "https://known.test/", "linkedin_slug": "known", "company_name": "Known Co"},
        {"website_url": "", "linkedin_slug": "missing", "company_name": "Missing Co"},
    ]
    discoveries = {
        "ambiguous": {"status": "ambiguous"},
        "known": {"status": "found"},
        "missing": {"status": "not_found"},
    }

    tasks = consensus.build_ambiguous_tasks(rows, discoveries)

    assert tasks == [{"slug": "ambiguous", "company_name": "Ambiguous Co", "prior_candidates": []}]


def test_bing_recovery_requires_distinct_query_families_and_rejects_ties():
    accepted = consensus.select_bing_recovery_candidate(
        [
            {"engine": "bing", "query_family": "name", "query": "q1", "candidates": [{"domain": "example.test", "score": 12, "evidence": 5, "position": 0, "title": "Example Holdings"}]},
            {"engine": "bing", "query_family": "context", "query": "q2", "candidates": [{"domain": "example.test", "score": 10, "evidence": 4, "position": 1, "title": "Example Holdings Berlin"}]},
        ],
        "Example Holdings",
        "example-holdings",
    )
    rejected = consensus.select_bing_recovery_candidate(
        [
            {"engine": "bing", "query_family": "name", "query": "q1", "candidates": [{"domain": "one.test", "score": 12, "evidence": 5, "position": 0, "title": "Example Holdings"}]},
            {"engine": "bing", "query_family": "context", "query": "q2", "candidates": [{"domain": "two.test", "score": 12, "evidence": 5, "position": 0, "title": "Example Holdings"}]},
        ],
        "Example Holdings",
        "example-holdings",
    )

    assert accepted["status"] == "found"
    assert accepted["domain"] == "example.test"
    assert rejected["status"] == "ambiguous"
