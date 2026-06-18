import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.connectors.company_career_discovery import (
    FetchResult,
    detect_ats_type,
    discover_career_url,
    domain_from_url,
)
from backend.connectors.company_career_sites import (
    PageFetchResult,
    plan_company_site_scope,
    load_discovered_company_site_entries,
    parse_company_site_entries,
    scrape_company_career_sites,
)
from backend.tools.discover_company_careers import (
    default_output_paths,
    load_targets_from_csv,
    source_path_for_preset,
    source_presets_for_run,
)


class FakeFetcher:
    def __init__(self, responses):
        self.responses = responses

    def __call__(self, url):
        normalized = url.rstrip("/")
        response = self.responses.get(normalized)
        if response is None:
            return FetchResult(url, url, 404, text="")
        return FetchResult(
            requested_url=url,
            final_url=response.get("final_url", url),
            status_code=response.get("status_code", 200),
            content_type=response.get("content_type", "text/html"),
            text=response.get("text", ""),
        )


class CompanyCareerDiscoveryTests(unittest.TestCase):
    def test_detects_external_ats_from_homepage_link(self):
        fetch = FakeFetcher(
            {
                "https://example.com": {
                    "text": '<a href="https://jobs.lever.co/example">Jobs</a>',
                }
            }
        )

        result = discover_career_url(homepage_url="https://example.com", fetch=fetch)

        self.assertEqual(result.crawl_status, "found")
        self.assertEqual(result.primary_career_url, "https://jobs.lever.co/example")
        self.assertEqual(result.ats_type, "lever")
        self.assertGreaterEqual(result.confidence_score, 0.55)

    def test_common_path_guess_can_win(self):
        fetch = FakeFetcher(
            {
                "https://example.com": {"text": "<html></html>"},
                "https://example.com/karriere": {
                    "text": "<title>Karriere</title>",
                },
            }
        )

        result = discover_career_url(homepage_url="example.com", fetch=fetch)

        self.assertEqual(result.primary_career_url, "https://example.com/karriere")
        self.assertEqual(result.crawl_status, "found")

    def test_domain_normalization_removes_www(self):
        self.assertEqual(domain_from_url("https://www.example.com/careers"), "example.com")

    def test_csv_loader_supports_bisscareer_columns(self):
        temp_dir = Path("tests") / "_tmp_company_career_discovery"
        temp_dir.mkdir(parents=True, exist_ok=True)
        csv_path = temp_dir / "companies.csv"
        try:
            csv_path.write_text(
                textwrap.dedent(
                    """
                    company,estimated_revenue_eur_million,city,sectors_active,website
                    2G ENERGY,238,Heek,Industrial,http://www.2-g.de
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            targets = load_targets_from_csv(csv_path)
        finally:
            if csv_path.exists():
                csv_path.unlink()
            if temp_dir.exists():
                temp_dir.rmdir()

        self.assertEqual(targets, [{"company_name": "2G ENERGY", "homepage_url": "http://www.2-g.de"}])

    def test_source_presets_point_to_canonical_inputs(self):
        self.assertEqual(
            source_path_for_preset("regular"),
            str(Path("Jobs-Urls") / "Master-Jobs-Url" / "Master-Jobs-Url.csv"),
        )
        self.assertEqual(
            source_path_for_preset("phd"),
            str(Path("Jobs-Urls") / "List-of-All-European-Universities" / "ETER-DB-Euro-Uni-Export.csv"),
        )

    def test_source_preset_all_expands_to_both_inputs(self):
        self.assertEqual(source_presets_for_run("all"), ["regular", "phd"])
        self.assertEqual(
            default_output_paths("all"),
            (
                str(Path(".backend_data") / "career_discovery" / "all_results.json"),
                str(Path("user_config") / "discovered_company_career_sites.txt"),
            ),
        )

    def test_company_site_parser_accepts_discovery_results(self):
        entries = parse_company_site_entries(
            [
                {
                    "company_name": "Acme",
                    "primary_career_url": "https://careers.acme.example/jobs",
                }
            ]
        )

        self.assertEqual(
            entries,
            [
                {
                    "company_name": "Acme",
                    "url": "https://careers.acme.example/jobs",
                }
            ],
        )

    def test_discovered_company_site_loader_feeds_workspace_company_source(self):
        temp_dir = Path("tests") / "_tmp_company_career_discovery"
        temp_dir.mkdir(parents=True, exist_ok=True)
        discovered_path = temp_dir / "discovered_sites.txt"
        try:
            discovered_path.write_text(
                "Acme | https://careers.acme.example/jobs\n"
                "Beta | https://jobs.beta.example\n",
                encoding="utf-8",
            )

            entries = load_discovered_company_site_entries([discovered_path])
        finally:
            if discovered_path.exists():
                discovered_path.unlink()
            if temp_dir.exists():
                temp_dir.rmdir()

        self.assertEqual(
            entries,
            [
                {"company_name": "Acme", "url": "https://careers.acme.example/jobs"},
                {"company_name": "Beta", "url": "https://jobs.beta.example/"},
            ],
        )

    def test_discovered_company_site_loader_reads_live_file_variant(self):
        temp_dir = Path("tests") / "_tmp_company_career_discovery"
        temp_dir.mkdir(parents=True, exist_ok=True)
        canonical_path = temp_dir / "discovered_regular_company_career_sites.txt"
        live_path = temp_dir / "discovered_regular_company_career_sites.live.txt"
        try:
            live_path.write_text(
                "Acme | https://careers.acme.example/jobs\n",
                encoding="utf-8",
            )

            entries = load_discovered_company_site_entries([canonical_path])
        finally:
            if canonical_path.exists():
                canonical_path.unlink()
            if live_path.exists():
                live_path.unlink()
            if temp_dir.exists():
                temp_dir.rmdir()

        self.assertEqual(
            entries,
            [
                {"company_name": "Acme", "url": "https://careers.acme.example/jobs"},
            ],
        )

    def test_discovered_company_site_loader_does_not_hardcap_backend_entries(self):
        temp_dir = Path("tests") / "_tmp_company_career_discovery"
        temp_dir.mkdir(parents=True, exist_ok=True)
        discovered_path = temp_dir / "discovered_sites.txt"
        try:
            discovered_path.write_text(
                "\n".join(
                    f"Company {index} | https://careers{index}.example/jobs"
                    for index in range(60)
                ),
                encoding="utf-8",
            )

            entries = load_discovered_company_site_entries([discovered_path])
        finally:
            if discovered_path.exists():
                discovered_path.unlink()
            if temp_dir.exists():
                temp_dir.rmdir()

        self.assertEqual(len(entries), 60)
        self.assertEqual(entries[0]["url"], "https://careers0.example/jobs")
        self.assertEqual(entries[-1]["url"], "https://careers59.example/jobs")

    def test_company_site_scraper_follows_external_ats_listing_page(self):
        root_url = "https://example.com/careers"
        ats_listing_url = "https://acme.wd1.myworkdayjobs.com/en-US/careers"
        job_url = "https://acme.wd1.myworkdayjobs.com/en-US/careers/job/Berlin/Product-Owner_R12345"

        def fake_fetch(url, **_kwargs):
            if url == root_url:
                return PageFetchResult(
                    requested_url=url,
                    final_url=url,
                    status_code=200,
                    text=f'<a href="{ats_listing_url}">Stellenanzeigen</a>',
                )
            if url == ats_listing_url:
                return PageFetchResult(
                    requested_url=url,
                    final_url=url,
                    status_code=200,
                    text=f'<a href="{job_url}">Product Owner</a>',
                )
            raise AssertionError(f"Unexpected fetch URL: {url}")

        with (
            patch("backend.connectors.company_career_sites._fetch_page_content", side_effect=fake_fetch),
            patch(
                "backend.connectors.company_career_sites.fetch_and_normalize_manual_job",
                return_value={
                    "job_id": "job_123",
                    "title": "Product Owner",
                    "company": "Acme",
                    "full_description": "Product Owner role for platform delivery.",
                    "apply_link": job_url,
                    "source_url": job_url,
                    "link": job_url,
                },
            ),
        ):
            jobs, failures = scrape_company_career_sites(
                company_sites=[{"company_name": "Acme", "url": root_url}],
                keywords=["product owner"],
                request_timeout_seconds=15,
                max_jobs_per_site=5,
            )

        self.assertEqual(failures, [])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Product Owner")
        self.assertEqual(jobs[0]["apply_link"], job_url)
        self.assertEqual(jobs[0]["career_site_url"], root_url)

    def test_company_site_scraper_reuses_cached_job_urls_without_hiding_them(self):
        root_url = "https://example.com/careers"
        cached_url = "https://example.com/job/old-product-owner"
        new_url = "https://example.com/job/new-product-owner"
        history_records = []

        with (
            patch(
                "backend.connectors.company_career_sites._fetch_page_content",
                return_value=PageFetchResult(
                    requested_url=root_url,
                    final_url=root_url,
                    status_code=200,
                    text=(
                        f'<a href="{cached_url}">Old Product Owner</a>'
                        f'<a href="{new_url}">New Product Owner</a>'
                    ),
                ),
            ),
            patch(
                "backend.connectors.company_career_sites.fetch_and_normalize_manual_job",
                return_value={
                    "job_id": "job_new",
                    "title": "New Product Owner",
                    "company": "Example",
                    "full_description": "Product owner role.",
                    "apply_link": new_url,
                    "source_url": new_url,
                    "link": new_url,
                },
            ) as mock_normalize,
        ):
            jobs, failures = scrape_company_career_sites(
                company_sites=[{"company_name": "Example", "url": root_url}],
                keywords=["product owner"],
                cached_job_lookup=lambda _site_url, _urls: {
                    cached_url: {
                        "job_id": "job_cached",
                        "title": "Old Product Owner",
                        "company": "Example",
                        "full_description": "Product owner role from public job index.",
                        "apply_link": cached_url,
                        "source_url": cached_url,
                        "link": cached_url,
                    }
                },
                job_url_history_callback=lambda _site_url, attempts: history_records.extend(attempts),
            )

        self.assertEqual(failures, [])
        self.assertEqual([job["apply_link"] for job in jobs], [cached_url, new_url])
        self.assertEqual(mock_normalize.call_count, 1)
        self.assertEqual(mock_normalize.call_args.args[0], new_url)
        self.assertTrue(
            any(item["job_url"] == cached_url and item["status"] == "cache_reused" for item in history_records)
        )
        self.assertTrue(any(item["job_url"] == new_url and item["status"] == "accepted" for item in history_records))

    def test_company_site_scope_prefers_local_market_and_skips_foreign_sites(self):
        scope = plan_company_site_scope(
            company_sites=[
                {"company_name": "Local", "url": "https://company.example/de/karriere"},
                {"company_name": "Global", "url": "https://company.example/careers/global"},
                {"company_name": "Foreign", "url": "https://company.example/us/careers"},
            ],
            target_country_codes=["DE"],
            locality_mode="local_preferred",
            max_sites_per_run=2,
        )

        self.assertEqual([item["company_name"] for item in scope.selected_sites], ["Local", "Global"])
        self.assertEqual(scope.stats["selected_site_count"], 2)
        self.assertEqual(scope.stats["foreign_site_skipped_count"], 1)

    def test_company_site_scraper_no_longer_defaults_to_ten_followed_jobs(self):
        root_url = "https://example.com/careers"
        listing_url = "https://jobs.example.com/de/jobs"
        job_urls = [f"https://jobs.example.com/de/jobs/{index}" for index in range(12)]

        def fake_fetch(url, **_kwargs):
            if url == root_url:
                return PageFetchResult(
                    requested_url=url,
                    final_url=url,
                    status_code=200,
                    text=f'<a href="{listing_url}">Alle Jobs</a>',
                )
            if url == listing_url:
                links = "".join(f'<a href="{job_url}">Role {index}</a>' for index, job_url in enumerate(job_urls, start=1))
                return PageFetchResult(
                    requested_url=url,
                    final_url=url,
                    status_code=200,
                    text=links,
                )
            raise AssertionError(f"Unexpected fetch URL: {url}")

        with (
            patch("backend.connectors.company_career_sites._fetch_page_content", side_effect=fake_fetch),
            patch(
                "backend.connectors.company_career_sites.fetch_and_normalize_manual_job",
                side_effect=[
                    {
                        "job_id": f"job_{index}",
                        "title": f"Role {index}",
                        "company": "Acme",
                        "full_description": "Product role in Germany.",
                        "apply_link": job_url,
                        "source_url": job_url,
                        "link": job_url,
                    }
                    for index, job_url in enumerate(job_urls, start=1)
                ],
            ),
        ):
            jobs, failures = scrape_company_career_sites(
                company_sites=[{"company_name": "Acme", "url": root_url}],
                keywords=["role"],
                request_timeout_seconds=15,
                max_jobs_per_site=0,
                max_job_links_per_site=20,
                target_country_codes=["DE"],
            )

        self.assertEqual(len(jobs), 12)
        self.assertFalse(any(item["error"] == "explicit_jobs_per_site_cap" for item in failures))

    def test_company_site_scraper_reports_capped_sites_when_link_cap_is_reached(self):
        root_url = "https://example.com/careers"
        job_urls = [f"https://example.com/job/role-{index}" for index in range(3)]
        progress = []

        with (
            patch(
                "backend.connectors.company_career_sites._fetch_page_content",
                return_value=PageFetchResult(
                    requested_url=root_url,
                    final_url=root_url,
                    status_code=200,
                    text="".join(f'<a href="{url}">Role</a>' for url in job_urls),
                ),
            ),
            patch(
                "backend.connectors.company_career_sites.fetch_and_normalize_manual_job",
                side_effect=[
                    {
                        "job_id": f"job_{index}",
                        "title": f"Role {index}",
                        "company": "Acme",
                        "full_description": "Role in Germany.",
                        "apply_link": url,
                        "source_url": url,
                        "link": url,
                    }
                    for index, url in enumerate(job_urls)
                ],
            ),
            self.assertLogs("backend.connectors.company_career_sites", level="INFO") as logs,
        ):
            jobs, failures = scrape_company_career_sites(
                company_sites=[{"company_name": "Acme", "url": root_url}],
                max_job_links_per_site=2,
                progress_callback=progress.append,
            )

        self.assertEqual(len(jobs), 2)
        self.assertTrue(any(item["error"] == "company_site_max_job_links_per_site" for item in failures))
        self.assertIn("Job link cap reached for https://example.com/careers", "\n".join(logs.output))
        self.assertEqual(
            progress[-1]["counters"]["capped_sites"],
            [{"url": root_url, "links_fetched": 2, "cap_value": 2}],
        )

    def test_company_site_scraper_filters_navigation_before_normalizing_jobs(self):
        root_url = "https://careers.abb/dach/de"
        listing_url = "https://careers.abb/dach/de/jobs"
        job_url = "https://careers.abb/dach/de/job/berlin/product-owner-r123"
        fetch_calls = []

        def fake_fetch(url, **_kwargs):
            fetch_calls.append(url)
            if url == root_url:
                return PageFetchResult(
                    requested_url=url,
                    final_url=url,
                    status_code=200,
                    text=(
                        '<a href="https://careers.abb/dach/de/life-at-abb">Life at ABB</a>'
                        '<a href="https://careers.abb/dach/de/how-to-apply">How to apply</a>'
                        '<a href="https://careers.abb/dach/de/locations">Locations</a>'
                        f'<a href="{listing_url}">Search jobs</a>'
                    ),
                )
            if url == listing_url:
                return PageFetchResult(
                    requested_url=url,
                    final_url=url,
                    status_code=200,
                    text=f'<a href="{job_url}">Product Owner Berlin</a>',
                )
            raise AssertionError(f"Unexpected fetch URL: {url}")

        with (
            patch("backend.connectors.company_career_sites._fetch_page_content", side_effect=fake_fetch),
            patch(
                "backend.connectors.company_career_sites.fetch_and_normalize_manual_job",
                return_value={
                    "job_id": "job_123",
                    "title": "Product Owner",
                    "company": "ABB",
                    "full_description": "Product Owner role in Berlin.",
                    "apply_link": job_url,
                    "source_url": job_url,
                    "link": job_url,
                },
            ) as mock_normalize,
        ):
            jobs, failures = scrape_company_career_sites(
                company_sites=[{"company_name": "ABB", "url": root_url}],
                keywords=["product owner"],
                request_timeout_seconds=15,
                target_country_codes=["DE"],
            )

        self.assertEqual(failures, [])
        self.assertEqual(fetch_calls, [root_url, listing_url])
        self.assertEqual(mock_normalize.call_count, 1)
        self.assertEqual(jobs[0]["apply_link"], job_url)

    def test_company_site_posted_window_filters_known_old_jobs_and_keeps_unknown_dates(self):
        root_url = "https://careers.example.com/jobs"
        recent_url = "https://careers.example.com/job/recent-product-role"
        old_url = "https://careers.example.com/job/old-product-role"
        unknown_url = "https://careers.example.com/job/unknown-product-role"

        def normalize_candidate(url, **_kwargs):
            posted_age_by_url = {
                recent_url: 48,
                old_url: 240,
                unknown_url: None,
            }
            return {
                "job_id": url.split("/")[-1],
                "title": url.split("/")[-1].replace("-", " ").title(),
                "company": "Example",
                "full_description": "Product role.",
                "posted_age_hours": posted_age_by_url[url],
                "apply_link": url,
                "source_url": url,
                "link": url,
            }

        with (
            patch(
                "backend.connectors.company_career_sites._fetch_page_content",
                return_value=PageFetchResult(
                    requested_url=root_url,
                    final_url=root_url,
                    status_code=200,
                    text=(
                        f'<a href="{recent_url}">Recent Product Role</a>'
                        f'<a href="{old_url}">Old Product Role</a>'
                        f'<a href="{unknown_url}">Unknown Product Role</a>'
                    ),
                ),
            ),
            patch(
                "backend.connectors.company_career_sites.fetch_and_normalize_manual_job",
                side_effect=normalize_candidate,
            ),
        ):
            jobs, failures = scrape_company_career_sites(
                company_sites=[{"company_name": "Example", "url": root_url}],
                keywords=["product"],
                request_timeout_seconds=15,
                posted_within_days=7,
            )

        self.assertEqual(
            {job["job_id"] for job in jobs},
            {"recent-product-role", "unknown-product-role"},
        )
        self.assertEqual(failures, [])

    def test_company_site_scraper_does_not_treat_tankstellenmuseum_as_stellen_job(self):
        root_url = "https://avia-regenstauf.de/karriere"
        museum_url = "https://avia-regenstauf.de/ueber-bauer/tankstellenmuseum"
        job_url = "https://avia-regenstauf.de/karriere/job/product-owner-r123"

        def fake_fetch(url, **_kwargs):
            if url == root_url:
                return PageFetchResult(
                    requested_url=url,
                    final_url=url,
                    status_code=200,
                    text=(
                        f'<a href="{museum_url}">Tankstellenmuseum</a>'
                        f'<a href="{job_url}">Product Owner</a>'
                    ),
                )
            raise AssertionError(f"Unexpected fetch URL: {url}")

        with (
            patch("backend.connectors.company_career_sites._fetch_page_content", side_effect=fake_fetch),
            patch(
                "backend.connectors.company_career_sites.fetch_and_normalize_manual_job",
                return_value={
                    "job_id": "job_123",
                    "title": "Product Owner",
                    "company": "Avia",
                    "full_description": "Product Owner role.",
                    "apply_link": job_url,
                    "source_url": job_url,
                    "link": job_url,
                },
            ) as mock_normalize,
        ):
            jobs, failures = scrape_company_career_sites(
                company_sites=[{"company_name": "Avia", "url": root_url}],
                keywords=["product owner"],
                request_timeout_seconds=15,
            )

        self.assertEqual(failures, [])
        self.assertEqual(mock_normalize.call_count, 1)
        self.assertEqual(mock_normalize.call_args.args[0], job_url)
        self.assertEqual(jobs[0]["apply_link"], job_url)

    def test_company_site_scraper_applies_domain_policy_modes_and_country(self):
        root_url = "https://acme.myworkdayjobs.com/de-DE/careers"
        job_url = "https://acme.myworkdayjobs.com/de-DE/careers/job/Berlin/Product-Owner_R12345"
        fetch_modes = []

        def fake_fetch(url, **kwargs):
            fetch_modes.append(kwargs.get("request_mode"))
            self.assertEqual(kwargs.get("country_code"), "de")
            return PageFetchResult(
                requested_url=url,
                final_url=url,
                status_code=200,
                text=f'<a href="{job_url}">Product Owner Berlin</a>',
            )

        with (
            patch("backend.connectors.company_career_sites._fetch_page_content", side_effect=fake_fetch),
            patch(
                "backend.connectors.company_career_sites.fetch_and_normalize_manual_job",
                return_value={
                    "job_id": "job_123",
                    "title": "Product Owner",
                    "company": "Acme",
                    "full_description": "Product Owner role in Berlin.",
                    "apply_link": job_url,
                    "source_url": job_url,
                    "link": job_url,
                },
            ) as mock_normalize,
        ):
            jobs, failures = scrape_company_career_sites(
                company_sites=[{"company_name": "Acme", "url": root_url}],
                keywords=["product owner"],
                request_timeout_seconds=15,
                target_country_codes=["US"],
                domain_policies=[
                    {
                        "policy_id": "workday_de",
                        "domain_pattern": "*.myworkdayjobs.com",
                        "site_request_modes": ["render_js_cheap"],
                        "job_detail_request_modes": ["basic"],
                        "locality_mode": "strict_local_only",
                        "country_code": "DE",
                        "priority": 1,
                        "is_active": True,
                    }
                ],
            )

        self.assertEqual(failures, [])
        self.assertEqual(fetch_modes, ["render_js_cheap"])
        self.assertEqual(mock_normalize.call_args.kwargs["scrapeops_mode"], "basic")
        self.assertEqual(mock_normalize.call_args.kwargs["scrapeops_country_code"], "de")
        self.assertEqual(jobs[0]["company_site_domain_policy_id"], "workday_de")
        self.assertEqual(jobs[0]["company_site_locality_mode"], "strict_local_only")


if __name__ == "__main__":
    unittest.main()
