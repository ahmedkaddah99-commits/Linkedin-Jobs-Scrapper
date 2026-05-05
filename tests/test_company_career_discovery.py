import textwrap
import unittest
from pathlib import Path

from backend.connectors.company_career_discovery import (
    FetchResult,
    detect_ats_type,
    discover_career_url,
    domain_from_url,
)
from backend.connectors.company_career_sites import (
    load_discovered_company_site_entries,
    parse_company_site_entries,
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


if __name__ == "__main__":
    unittest.main()
