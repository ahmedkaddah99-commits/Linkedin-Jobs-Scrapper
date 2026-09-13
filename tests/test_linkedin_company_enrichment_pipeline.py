from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace

from scripts.linkedin_company_enrichment_pipeline import (
    CachedWebshareFetcher,
    EnrichmentPipeline,
    FetchResponse,
    HybridLinkedInFetcher,
    PipelineMetrics,
    StateStore,
    app_relevance,
    classify_page_status,
    compare_job_cards,
    classify_transport_response,
    company_state_key,
    detect_staffing,
    enrich_row,
    extract_f_c_ids,
    germany_signals,
    identity_validation_score,
    normalize_employee_bounds,
    normalize_domain,
    normalize_company_name,
    normalize_linkedin_url,
    parse_integer,
    parse_linkedin_page,
    root_domain,
)


class MappingFetcher:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def fetch(self, url, *, kind="html"):
        self.calls.append(url)
        body = self.pages.get(url, "")
        return FetchResponse(url, url, 200 if body else 404, "text/html", body.encode(), 1)


class ScriptedFetcher:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def fetch(self, url, *, kind="html"):
        self.calls.append((url, kind))
        response = self.responses.pop(0)
        return response


class LinkedInCompanyPipelineTests(unittest.TestCase):
    def test_normalizes_company_urls_without_changing_identity(self):
        self.assertEqual(
            normalize_linkedin_url("http://linkedin.com/company/Siemens/?trk=foo#jobs"),
            "https://www.linkedin.com/company/siemens/",
        )

    def test_extracts_one_numeric_company_id_from_job_filter_links(self):
        html = '<a href="https://www.linkedin.com/jobs/search/?f_C=1043">See all jobs</a>'
        self.assertEqual(extract_f_c_ids(html), {"1043"})

    def test_extracts_ids_from_encoded_urls_and_company_urns(self):
        html = "https://www.linkedin.com/jobs/search/?f%5FC=1043 urn:li:fsd_company:2048"
        self.assertEqual(extract_f_c_ids(html), {"1043", "2048"})

    def test_normalizes_domains_and_company_names(self):
        self.assertEqual(normalize_domain("https://www.Example.co.uk/path"), "example.co.uk")
        self.assertEqual(root_domain("jobs.example.co.uk"), "example.co.uk")
        self.assertEqual(normalize_company_name("Acme GmbH & Co. KG"), "acme and")

    def test_parses_kilogram_style_counts_and_employee_buckets(self):
        self.assertEqual(parse_integer("2.3K followers"), 2300)
        self.assertEqual(normalize_employee_bounds("1-10 employees"), (1, 10, "1-10"))
        self.assertEqual(normalize_employee_bounds("51-200 employees"), (51, 200, "51-200"))
        self.assertEqual(normalize_employee_bounds("over 10,000 employees"), (10000, None, "10001+"))

    def test_parses_json_ld_page_and_exact_see_all_id(self):
        html = """
        <html><head>
          <title>Acme GmbH | LinkedIn</title>
          <meta property="og:description" content="Industrial automation company">
          <script type="application/ld+json">
          {"@type":"Organization","name":"Acme GmbH","url":"https://acme.example.com",
           "industry":"Industrial Automation","foundingDate":"1999",
           "numberOfEmployees":{"minValue":51,"maxValue":200},
           "address":{"addressLocality":"Berlin","addressCountry":"Germany"},
           "logo":"https://media.licdn.com/logo.png"}
          </script>
        </head><body>
          2.3K followers
          <a href="https://www.linkedin.com/jobs/search/?f_C=1043">See all jobs</a>
        </body></html>
        """
        facts = parse_linkedin_page(html, "https://www.linkedin.com/company/acme/")
        self.assertTrue(facts["page_valid"])
        self.assertEqual(facts["display_name"], "Acme GmbH")
        self.assertEqual(facts["raw_company_ids"], ["1043"])
        self.assertEqual(facts["follower_count"], 2300)
        self.assertEqual(facts["headquarters"]["country_code"], "DE")

    def test_identity_scoring_and_page_status_require_evidence(self):
        score, status, confidence = identity_validation_score(
            {"exact_page_see_all_id": True, "slug_match": True, "name_match": True}
        )
        self.assertEqual((score, status), (85, "VALIDATED"))
        self.assertGreater(confidence, 0.8)
        self.assertEqual(classify_page_status(page_valid=True, ids=[], score=100), "NO_ID_EXPOSED")
        self.assertEqual(classify_page_status(page_valid=False, ids=["1043"], score=100), "PAGE_NOT_FOUND")

    def test_job_cards_and_app_signals_are_conservative(self):
        comparison = compare_job_cards(
            [{"company_id": "1043", "text": "Acme automation engineer"}],
            "1043",
            "Acme",
            "acme",
        )
        self.assertEqual(comparison["match_rate"], 1.0)
        staffing, confidence, reasons = detect_staffing(
            {"company_name": "Example Staffing"},
            {"industry": "Staffing and Recruiting"},
        )
        self.assertTrue(staffing)
        self.assertEqual(confidence, "HIGH")
        self.assertIn("staffing", reasons)
        germany, count, headquartered = germany_signals(
            {}, {"headquarters": {"country_code": "DE"}, "locations": []}
        )
        self.assertTrue(germany)
        self.assertEqual((count, headquartered), (0, True))
        relevance = app_relevance(
            {"company_name": "Acme", "website_url": "https://acme.example.com"},
            {"page_type": "company", "page_valid": True, "display_name": "Acme"},
            "VALIDATED",
        )
        self.assertTrue(relevance["has_validated_linkedin_company_id"])

    def test_enrichment_preserves_existing_values_and_records_conflicts(self):
        row = enrich_row(
            {
                "company_name": "Acme",
                "website_url": "https://existing.example.com",
                "linkedin_company_id": "999",
            },
            {
                "page_type": "company",
                "page_valid": True,
                "display_name": "Acme",
                "raw_company_ids": [],
                "id_status": "NO_ID_EXPOSED",
                "website_url": "https://other.example.com",
            },
        )
        self.assertEqual(row["website_url"], "https://existing.example.com")
        self.assertEqual(row["linkedin_company_id"], "999")
        self.assertTrue(row["enrichment_conflicts_json"])

    def test_state_store_round_trips_state_and_cached_response(self):
        with tempfile.TemporaryDirectory() as directory:
            state = StateStore(Path(directory))
            state.put_state("acme", "COMPLETE", {"value": 1})
            self.assertEqual(state.get_state("acme")["result"]["value"], 1)
            response = FetchResponse(
                "https://example.test", "https://example.test/", 200, "text/html", b"ok", 1,
                transport_used="scrapeops", transport_level="default", status_classification="valid_html",
                fallback_reason="webshare_blocked", scrapeops_attempts=1, scrapeops_credit_cost=1,
            )
            state.put_fetch(response)
            cached = state.get_fetch(response.url)
            self.assertEqual(cached["body"], b"ok")
            self.assertEqual(cached["transport_used"], "scrapeops")
            self.assertEqual(cached["scrapeops_credit_cost"], 1)
            state.close()

    def test_webshare_fetcher_does_not_require_network_for_cache_hits(self):
        with tempfile.TemporaryDirectory() as directory:
            state = StateStore(Path(directory))
            response = FetchResponse("https://example.test", "https://example.test/", 200, "text/html", b"ok", 1)
            state.put_fetch(response)
            metrics = PipelineMetrics()
            fetcher = CachedWebshareFetcher.__new__(CachedWebshareFetcher)
            fetcher.state = state
            fetcher.metrics = metrics
            result = fetcher.fetch(response.url)
            self.assertTrue(result.from_cache)
            self.assertEqual(metrics.cache_hits, 1)
            state.close()

    def test_pipeline_fetches_jobs_page_for_exact_id_even_when_company_page_has_no_jobs_link(self):
        company_url = "https://www.linkedin.com/company/acme/"
        jobs_url = "https://www.linkedin.com/company/acme/jobs/"
        company_html = "<html><head><title>Acme | LinkedIn</title></head><body></body></html>"
        jobs_html = '<html><body><a href="https://www.linkedin.com/jobs/search/?f_C=1043">See all jobs</a></body></html>'
        with tempfile.TemporaryDirectory() as directory:
            state = StateStore(Path(directory))
            fetcher = MappingFetcher({company_url: company_html, jobs_url: jobs_html})
            pipeline = EnrichmentPipeline(fetcher=fetcher, state=state)
            result = pipeline._resolve_row({"canonical_CompanyID": "1", "company_name": "Acme", "linkedin_company_url": company_url}, job_validation=False)
            state.close()
        self.assertEqual(result["linkedin_company_id"], "1043")
        self.assertEqual(result["linkedin_company_id_source"], "company_jobs_see_all")
        self.assertIn(jobs_url, fetcher.calls)

    def test_output_validation_rejects_duplicate_canonical_ids(self):
        from scripts.linkedin_company_enrichment_pipeline import validate_output, write_csv

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "output.csv"
            write_csv(path, ["canonical_CompanyID", "company_name"], [{"canonical_CompanyID": "1"}, {"canonical_CompanyID": "1"}])
            with self.assertRaises(ValueError):
                validate_output(path, 2)

    def test_placeholder_canonical_ids_get_stable_distinct_state_keys(self):
        self.assertNotEqual(
            company_state_key({"canonical_CompanyID": "//", "company_name": "Acme"}, 1),
            company_state_key({"canonical_CompanyID": "//", "company_name": "Acme"}, 2),
        )

    def test_hybrid_falls_back_to_scrapeops_after_unusable_webshare_response(self):
        url = "https://www.linkedin.com/company/acme/"
        webshare = ScriptedFetcher([
            FetchResponse(url, url, 999, "text/html", b"challenge", 1, transport_used="webshare", status_classification="blocked")
        ])
        scrapeops = ScriptedFetcher([
            FetchResponse(url, url, 200, "text/html", b"<html><title>Acme</title></html>", 1, transport_used="scrapeops", transport_level="basic", scrapeops_credit_cost=1)
        ])
        hybrid = HybridLinkedInFetcher(
            webshare=webshare,
            scrapeops=scrapeops,
            scrapeops_modes=("basic",),
            fallback_enabled=True,
        )
        result = hybrid.fetch(url, kind="company_page")
        self.assertEqual(result.transport_used, "scrapeops")
        self.assertEqual(result.fallback_reason, "webshare_blocked")
        self.assertEqual(len(webshare.calls), 1)
        self.assertEqual(len(scrapeops.calls), 1)
        self.assertEqual([item["transport_level"] for item in result.transport_trace], ["webshare", "basic"])

    def test_hybrid_uses_usable_webshare_without_scrapeops(self):
        url = "https://www.linkedin.com/company/acme/"
        webshare = ScriptedFetcher([FetchResponse(url, url, 200, "text/html", b"<html><title>Acme</title></html>", 1)])
        scrapeops = ScriptedFetcher([])
        hybrid = HybridLinkedInFetcher(webshare=webshare, scrapeops=scrapeops, fallback_enabled=True)
        result = hybrid.fetch(url, kind="company_page")
        self.assertEqual(result.transport_used, "webshare")
        self.assertEqual(len(scrapeops.calls), 0)

    def test_hybrid_does_not_fallback_for_legitimate_not_found(self):
        url = "https://www.linkedin.com/company/missing/"
        webshare = ScriptedFetcher([FetchResponse(url, url, 404, "text/html", b"<html>Page not found</html>", 1)])
        scrapeops = ScriptedFetcher([])
        hybrid = HybridLinkedInFetcher(webshare=webshare, scrapeops=scrapeops, fallback_enabled=True)
        result = hybrid.fetch(url, kind="company_page")
        self.assertEqual(classify_transport_response(result), "legitimate_not_found")
        self.assertEqual(len(scrapeops.calls), 0)

    def test_hybrid_enforces_per_company_paid_attempt_limit(self):
        url = "https://www.linkedin.com/company/acme/"
        webshare = ScriptedFetcher([FetchResponse(url, url, 999, "text/html", b"challenge", 1)])
        scrapeops = ScriptedFetcher([
            FetchResponse(url, url, 999, "text/html", b"challenge", 1, transport_used="scrapeops", transport_level="default", status_classification="blocked")
        ])
        metrics = PipelineMetrics()
        hybrid = HybridLinkedInFetcher(
            webshare=webshare,
            scrapeops=scrapeops,
            scrapeops_modes=("basic", "residential"),
            fallback_enabled=True,
            metrics=metrics,
            max_scrapeops_attempts_per_company=1,
        )
        hybrid.begin_company("acme")
        result = hybrid.fetch(url, kind="company_page")
        self.assertEqual(len(scrapeops.calls), 1)
        self.assertEqual(metrics.scrapeops_company_budget_exhausted, 1)
        self.assertEqual(result.status_classification, "budget_exhausted")

    def test_hybrid_does_not_fallback_for_valid_page_without_company_id(self):
        url = "https://www.linkedin.com/company/acme/"
        webshare = ScriptedFetcher([FetchResponse(url, url, 200, "text/html", b"<html><title>Acme</title><p>Public profile</p></html>", 1)])
        scrapeops = ScriptedFetcher([])
        hybrid = HybridLinkedInFetcher(webshare=webshare, scrapeops=scrapeops, fallback_enabled=True)
        result = hybrid.fetch(url, kind="company_page")
        self.assertEqual(result.transport_used, "webshare")
        self.assertEqual(len(scrapeops.calls), 0)

    def test_hybrid_keeps_guest_job_validation_on_webshare_by_default(self):
        url = "https://www.linkedin.com/jobs/search/?f_C=1043"
        webshare = ScriptedFetcher([FetchResponse(url, url, 999, "text/html", b"challenge", 1)])
        scrapeops = ScriptedFetcher([])
        hybrid = HybridLinkedInFetcher(webshare=webshare, scrapeops=scrapeops, fallback_enabled=True)
        result = hybrid.fetch(url, kind="job_validation")
        self.assertEqual(result.transport_used, "webshare")
        self.assertEqual(len(scrapeops.calls), 0)

    def test_scrapeops_success_is_cached_with_cost_and_transport_provenance(self):
        from scripts.linkedin_company_enrichment_pipeline import ScrapeOpsFetcher

        url = "https://www.linkedin.com/company/acme/"
        with tempfile.TemporaryDirectory() as directory:
            state = StateStore(Path(directory))
            metrics = PipelineMetrics()
            fetcher = ScrapeOpsFetcher.__new__(ScrapeOpsFetcher)
            fetcher.state = state
            fetcher.metrics = metrics
            fetcher.max_credit_cost = 0.0
            fetcher.credit_budget = 5.0
            fetcher.timeout = 30
            fetcher.retries = 0
            fetcher.default_mode = "basic"
            fetcher.api_key = "redacted-test-key"
            fetcher._estimate_mode_native_credits = lambda mode: 1
            fetcher._billed_status_code = lambda status: status in {200, 404}
            fetcher._build_proxy_params = lambda **kwargs: {"api_key": "redacted-test-key"}
            fetcher._endpoint = "https://proxy.scrapeops.io/v1/"
            fetcher._request_with_retry = lambda *args, **kwargs: SimpleNamespace(
                response=SimpleNamespace(status_code=200, headers={"content-type": "text/html"}),
                attempts=1,
            )
            fetcher._parse_proxy_response_envelope = lambda response: SimpleNamespace(
                target_status_code=200,
                body="<html><title>Acme</title><p>Company</p></html>",
                payload={"content_type": "text/html"},
                billed_credits_actual=1,
            )
            first = fetcher.fetch(url, kind="company_page")
            second = fetcher.fetch(url, kind="company_page")
            cached = state.get_fetch(url)
            state.close()
        self.assertEqual(first.transport_used, "scrapeops")
        self.assertEqual(first.scrapeops_credit_cost, 1)
        self.assertEqual(first.scrapeops_credit_cost_basis, "actual")
        self.assertTrue(second.from_cache)
        self.assertEqual(metrics.scrapeops_requests, 1)
        self.assertEqual(cached["transport_used"], "scrapeops")

    def test_scrapeops_global_credit_budget_blocks_request_before_network_call(self):
        from scripts.linkedin_company_enrichment_pipeline import ScrapeOpsFetcher

        url = "https://www.linkedin.com/company/acme/"
        with tempfile.TemporaryDirectory() as directory:
            state = StateStore(Path(directory))
            metrics = PipelineMetrics()
            fetcher = ScrapeOpsFetcher.__new__(ScrapeOpsFetcher)
            fetcher.state = state
            fetcher.metrics = metrics
            fetcher.max_credit_cost = 0.0
            fetcher.credit_budget = 0.5
            fetcher.timeout = 30
            fetcher.retries = 0
            fetcher.default_mode = "basic"
            fetcher.api_key = "redacted-test-key"
            fetcher._estimate_mode_native_credits = lambda mode: 1

            network_calls = []
            fetcher._request_with_retry = lambda *args, **kwargs: network_calls.append(True)
            result = fetcher.fetch(url, kind="company_page")
            state.close()

        self.assertEqual(result.status_classification, "budget_exhausted")
        self.assertEqual(network_calls, [])
        self.assertTrue(metrics.scrapeops_budget_exhausted)
        self.assertEqual(metrics.scrapeops_requests, 0)


if __name__ == "__main__":
    unittest.main()
