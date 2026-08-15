import asyncio
import json
from io import BytesIO
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from backend.application.company_logo import (
    MAX_LOGO_BYTES,
    LogoValidationError,
    assert_public_official_host,
    cache_logo,
    deterministic_monogram,
    validate_logo,
    validate_official_url,
)
from backend.application.company_enrichment import (
    ScrapeOpsCompanyProvider,
    ScrapeOpsLinkedInCompanyProvider,
    configured_company_enrichment_provider,
)
from backend.bootstrap import create_backend
from tests.test_phase_f_company_profiles import _seed_catalog


VALID_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><circle cx="32" cy="32" r="30" fill="#0d628c"/></svg>'


def _png(width=64, height=64):
    stream = BytesIO()
    Image.new("RGBA", (width, height), (13, 98, 140, 255)).save(stream, format="PNG")
    return stream.getvalue()


class CountingStorage:
    def __init__(self):
        self.objects = {}
        self.put_calls = []

    def exists(self, key):
        return key in self.objects

    def put(self, key, data, *, content_type="", metadata=None):
        self.put_calls.append((key, content_type, dict(metadata or {})))
        self.objects[key] = bytes(data)
        return type("Stored", (), {"key": key, "size": len(data), "content_type": content_type, "etag": ""})()

    def signed_download_url(self, key, *, expires_in_seconds=None, download_filename=""):
        return f"https://storage.test/{key}"


class FixtureProvider:
    def __init__(self, *, failure=False, empty=False):
        self.calls = 0
        self.failure = failure
        self.empty = empty

    async def enrich(self, company, *, conditional):
        self.calls += 1
        self.last_conditional = dict(conditional)
        if self.failure:
            raise RuntimeError("fixture_provider_failed")
        if self.empty:
            return {
                "fields": {},
                "source": "official_company_website",
                "provenance_url": "https://acme.example/about",
                "request_count": 1,
                "cost_units": 0.25,
            }
        return {
            "source": "official_company_website",
            "provenance_url": "https://acme.example/about",
            "observed_at": "2026-08-06T10:00:00+00:00",
            "verified_at": "2026-08-06T10:00:00+00:00",
            "request_count": 2,
            "cost_units": 1.5,
            "fields": {
                "website": "https://acme.example",
                "industry": "Enterprise Software",
                "company_size": "51-200",
                "headquarters": "Berlin, Germany",
                "founded_year": 2018,
                "company_stage": "Growth",
                "funding_stage": "Series B",
                "total_funding": 12000000,
                "funding_year": 2025,
                "benefits": ["Learning budget"],
                "sponsorship": "unknown",
                "leadership_type": "manager",
            },
            "logo_bytes": VALID_SVG,
            "logo_source_url": "https://acme.example/logo.svg",
            "logo_content_type": "image/svg+xml",
        }


class PhaseFCompanyEnrichmentTests(unittest.TestCase):
    def backend(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        values = {
            "RUNR_TEST_MODE": "1",
            "RUNR_ENV": "test",
            "DATABASE_BACKEND": "sqlite",
            "TURSO_DATABASE_URL": " ",
            "TURSO_AUTH_TOKEN": " ",
            "OBJECT_STORAGE_BACKEND": "local",
        }
        original = {name: os.environ.get(name) for name in values}

        def restore_environment():
            for name, value in original.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

        self.addCleanup(restore_environment)
        os.environ.update(values)
        app = create_backend(Path(temporary_directory.name), storage_backend="sqlite", test_mode=True)
        _seed_catalog(app)
        storage = CountingStorage()
        app._company_enrichment_service.object_storage = storage
        app._personalized_jobs_service.object_storage = storage
        return app, storage

    def test_company_enrichment_is_worker_only_and_customer_reads_do_not_fetch(self):
        app, storage = self.backend()
        provider = FixtureProvider()
        app._company_enrichment_service.provider = provider

        disabled = app.run_due_company_enrichment(provider=provider, cycle_key="worker-gate")
        app.get_personalized_jobs("user-a", filters={})
        app.get_personalized_company_detail("user-a", "company-a")

        self.assertEqual(disabled["status"], "disabled")
        self.assertEqual(provider.calls, 0)
        self.assertEqual(storage.put_calls, [])

    def test_explicit_environment_enable_overrides_durable_disabled_config(self):
        app, _ = self.backend()
        provider = FixtureProvider()
        app.repositories.config_store.set_value("acquisition.phase_f.company_enrichment_enabled", False)
        previous = os.environ.get("RUNR_COMPANY_ENRICHMENT_ENABLED")
        os.environ["RUNR_COMPANY_ENRICHMENT_ENABLED"] = "1"
        self.addCleanup(
            lambda: os.environ.__setitem__("RUNR_COMPANY_ENRICHMENT_ENABLED", previous)
            if previous is not None
            else os.environ.pop("RUNR_COMPANY_ENRICHMENT_ENABLED", None)
        )

        result = app.run_due_company_enrichment(provider=provider, cycle_key="environment-enable")

        self.assertEqual(result["companies_processed"], 1)
        self.assertEqual(provider.calls, 1)

    def test_bounded_idempotent_company_target_process_records_yield_and_reuses_logo(self):
        app, storage = self.backend()
        provider = FixtureProvider()

        first = app.run_due_company_enrichment(provider=provider, max_companies=25, concurrency=3, request_budget=3, cycle_key="2026-08-06", force=True)
        second = app.run_due_company_enrichment(provider=provider, max_companies=25, concurrency=3, request_budget=3, cycle_key="2026-08-06", force=True)

        self.assertEqual(first["companies_processed"], 1)
        self.assertEqual(first["requests"], 2)
        self.assertEqual(first["cost_units"], 1.5)
        self.assertEqual(first["fields_written"], 11)
        self.assertEqual(first["logos_cached"], 1)
        self.assertEqual(second["companies_processed"], 0)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(len(storage.put_calls), 1)
        self.assertEqual(storage.put_calls[0][2]["width"], "64")
        self.assertEqual(storage.put_calls[0][2]["height"], "64")
        attempt = app.list_company_enrichment_attempts(company_id="company-a")[0]
        self.assertEqual(attempt["status"], "succeeded")
        self.assertEqual(attempt["fields_available"], 11)
        self.assertEqual(attempt["request_count"], 2)
        self.assertIn("company-a", attempt["idempotency_key"])
        profile = app.repositories.personalized_jobs_store.get_company_profile("company-a")["profile"]
        self.assertEqual(profile["fields"]["company_stage"]["value"], "Growth")
        self.assertEqual(profile["fields"]["industry"]["provenance"]["source"], "official_company_website")
        self.assertEqual(profile["fields"]["industry"]["observed_at"], "2026-08-06T10:00:00+00:00")
        self.assertEqual(profile["fields"]["sponsorship"]["state"], "unknown")

    def test_customer_company_page_uses_signed_private_storage_asset(self):
        app, storage = self.backend()
        app.run_due_company_enrichment(provider=FixtureProvider(), cycle_key="signed-logo", force=True)

        detail = app.get_personalized_company_detail("user-a", "company-a")
        public_profile = detail["profile"]
        self.assertTrue(public_profile["logo_cached"])
        self.assertTrue(public_profile["logo_url"].startswith("https://storage.test/catalog/company-logos/company-a/"))
        self.assertEqual(public_profile["fields"]["logo"]["value"], public_profile["logo_url"])
        self.assertNotIn("logo_source_url", public_profile)
        self.assertEqual(len(storage.put_calls), 1)

    def test_failure_is_durable_and_does_not_retry_same_cycle(self):
        app, _ = self.backend()
        provider = FixtureProvider(failure=True)

        result = app.run_due_company_enrichment(provider=provider, cycle_key="2026-08-06-failure", force=True)
        repeated = app.run_due_company_enrichment(provider=provider, cycle_key="2026-08-06-failure", force=True)

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["failures"], 1)
        self.assertEqual(repeated["companies_processed"], 0)
        self.assertEqual(provider.calls, 1)
        attempt = app.list_company_enrichment_attempts(company_id="company-a")[0]
        self.assertEqual(attempt["status"], "failed")
        self.assertEqual(attempt["error_code"], "RuntimeError")

    def test_request_budget_is_bounded_before_provider_call(self):
        app, _ = self.backend()
        provider = FixtureProvider()

        result = app.run_due_company_enrichment(provider=provider, request_budget=0, cycle_key="budget", force=True)

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["failures"], 1)
        self.assertEqual(provider.calls, 0)

    def test_partial_refresh_preserves_verified_value_and_records_unknowns(self):
        app, _ = self.backend()
        app.run_due_company_enrichment(provider=FixtureProvider(), cycle_key="2026-08-06-known", force=True)
        app.run_due_company_enrichment(provider=FixtureProvider(empty=True), cycle_key="2026-08-07-empty", force=True)

        profile = app.repositories.personalized_jobs_store.get_company_profile("company-a")["profile"]["fields"]
        self.assertEqual(profile["industry"]["value"], "Enterprise Software")
        self.assertEqual(profile["industry"]["state"], "known")
        self.assertEqual(profile["leadership_type"]["value"], "manager")
        self.assertEqual(profile["sponsorship"]["state"], "unknown")
        self.assertEqual(profile["sponsorship"]["unknown_reason"], "not_verified_from_authoritative_company_source")

    def test_scrapeops_provider_parses_typed_extra_fields_and_logo(self):
        html = """
        <html><head>
          <meta property="og:image" content="https://acme.example/brand.svg">
          <script type="application/ld+json">
          {"@type":"Organization","url":"https://acme.example","legalName":"Acme GmbH",
           "description":"A software company.","sameAs":["https://www.linkedin.com/company/acme"],
           "numberOfEmployees":{"value":125},"email":"hello@acme.example",
           "address":{"addressLocality":"Berlin","addressCountry":"DE"},
           "logo":"https://acme.example/brand.svg"}
          </script></head><body><a href="/careers">Careers</a></body></html>
        """
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="#0d628c"/></svg>'
        page_response = type("Response", (), {"status_code": 200, "headers": {"content-type": "application/json"}, "text": json.dumps({"status_code": 200, "content_type": "text/html", "body": html, "sops_api_credits": 1})})()
        logo_response = type("Response", (), {"status_code": 200, "headers": {"content-type": "image/svg+xml"}, "content": svg, "text": ""})()
        responses = iter([SimpleNamespace(response=page_response, attempts=1), SimpleNamespace(response=logo_response, attempts=1)])
        provider = ScrapeOpsCompanyProvider(api_key="test-key", mode="basic")
        with patch("backend.application.company_enrichment.scrapeops_request_with_retry", side_effect=lambda *args, **kwargs: next(responses)), patch("backend.application.company_enrichment.assert_public_official_host", return_value=None):
            result = asyncio.run(provider.enrich({"provenance_url": "https://acme.example"}, conditional={}))
        self.assertEqual(result["fields"]["website"], "https://acme.example")
        self.assertEqual(result["fields"]["careers_page"], "https://acme.example/careers")
        self.assertEqual(result["extra_fields"]["employee_count"], 125)
        self.assertEqual(result["extra_fields"]["legal_name"], "Acme GmbH")
        self.assertEqual(result["request_count"], 2)
        self.assertEqual(result["cost_units"], 2.0)
        self.assertEqual(result["logo_bytes"], svg)

    def test_linkedin_provider_discovers_matches_and_extracts_company_data_and_logo(self):
        discovery_html = """
        <html><body>
          <a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.linkedin.com%2Fcompany%2Facme">Acme GmbH | LinkedIn</a>
        </body></html>
        """
        linkedin_html = """
        <html><head>
          <meta property="og:title" content="Acme GmbH | LinkedIn">
          <meta property="og:description" content="A software company.">
          <meta property="og:image" content="https://media.licdn.com/logo.svg">
          <script type="application/ld+json">
          {"@type":"Organization","url":"https://acme.example","industry":"Software",
           "numberOfEmployees":{"value":125},"address":{"addressLocality":"Berlin","addressCountry":"DE"},
           "foundingDate":"2018-01-01","description":"A software company."}
          </script>
        </head></html>
        """
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="#0d628c"/></svg>'
        search_response = type("Response", (), {"status_code": 200, "headers": {"content-type": "application/json"}, "text": json.dumps({"status_code": 200, "content_type": "text/html", "body": discovery_html, "sops_api_credits": 1})})()
        page_response = type("Response", (), {"status_code": 200, "headers": {"content-type": "application/json"}, "text": json.dumps({"status_code": 200, "content_type": "text/html", "body": linkedin_html, "sops_api_credits": 1})})()
        logo_response = type("Response", (), {"status_code": 200, "headers": {"content-type": "image/svg+xml"}, "content": svg, "text": ""})()
        responses = iter([
            SimpleNamespace(response=search_response, attempts=1),
            SimpleNamespace(response=page_response, attempts=1),
            SimpleNamespace(response=logo_response, attempts=1),
        ])
        provider = ScrapeOpsLinkedInCompanyProvider(api_key="test-key", mode="basic")
        company = {"canonical_name": "Acme GmbH", "provenance_url": "https://acme.example"}
        with patch("backend.application.company_enrichment.scrapeops_request_with_retry", side_effect=lambda *args, **kwargs: next(responses)), patch("backend.application.company_enrichment.assert_public_official_host", return_value=None):
            result = asyncio.run(provider.enrich(company, conditional={}))

        self.assertEqual(result["source"], "scrapeops_linkedin_company_page")
        self.assertEqual(result["provenance_url"], "https://www.linkedin.com/company/acme")
        self.assertEqual(result["fields"]["website"], "https://acme.example")
        self.assertEqual(result["fields"]["industry"], "Software")
        self.assertEqual(result["fields"]["company_size"], 125)
        self.assertEqual(result["fields"]["headquarters"], "Berlin, DE")
        self.assertEqual(result["fields"]["founded_year"], 2018)
        self.assertEqual(result["extra_fields"]["linkedin_company_url"], "https://www.linkedin.com/company/acme")
        self.assertEqual(result["extra_fields"]["linkedin_description"], "A software company.")
        self.assertEqual(result["extra_fields"]["linkedin_lookup_status"], "matched")
        self.assertEqual(result["extra_fields"]["linkedin_jsonld"]["@type"], "Organization")
        self.assertEqual(result["logo_bytes"], svg)
        self.assertEqual(result["request_count"], 3)
        self.assertEqual(result["cost_units"], 3.0)

    def test_linkedin_provider_uses_bounded_direct_fallback_when_scrapeops_times_out(self):
        discovery_html = '<html><body><a href="https://www.linkedin.com/company/acme">Acme GmbH | LinkedIn</a></body></html>'
        linkedin_html = """
        <html><head><meta property="og:title" content="Acme GmbH | LinkedIn">
        <script type="application/ld+json">{"@type":"Organization","industry":"Software","url":"https://acme.example"}</script>
        </head></html>
        """
        direct_responses = iter([
            (discovery_html.encode(), "text/html", "https://html.duckduckgo.com/html/", 1, 0.0),
            (linkedin_html.encode(), "text/html", "https://www.linkedin.com/company/acme", 1, 0.0),
        ])
        provider = ScrapeOpsLinkedInCompanyProvider(api_key="test-key", mode="basic")
        with patch.object(provider, "_proxy_fetch", side_effect=RuntimeError("proxy_timeout")), patch.object(provider, "_direct_fetch", side_effect=lambda *args, **kwargs: next(direct_responses)):
            result = asyncio.run(provider.enrich({"canonical_name": "Acme GmbH"}, conditional={}))
        self.assertEqual(result["source"], "linkedin_company_page_direct_fallback")
        self.assertEqual(result["fields"]["industry"], "Software")
        self.assertEqual(result["extra_fields"]["linkedin_fetch_transport"], "direct_fallback")
        self.assertEqual(result["cost_units"], 0.0)

    def test_linkedin_scrapeops_provider_is_selected_by_worker_configuration(self):
        original = os.environ.get("RUNR_COMPANY_ENRICHMENT_PROVIDER")
        os.environ["RUNR_COMPANY_ENRICHMENT_PROVIDER"] = "scrapeops_linkedin"
        try:
            provider = configured_company_enrichment_provider()
        finally:
            if original is None:
                os.environ.pop("RUNR_COMPANY_ENRICHMENT_PROVIDER", None)
            else:
                os.environ["RUNR_COMPANY_ENRICHMENT_PROVIDER"] = original
        self.assertIsInstance(provider, ScrapeOpsLinkedInCompanyProvider)

    def test_scrapeops_provider_is_selected_by_worker_configuration(self):
        original = os.environ.get("RUNR_COMPANY_ENRICHMENT_PROVIDER")
        os.environ["RUNR_COMPANY_ENRICHMENT_PROVIDER"] = "scrapeops"
        try:
            provider = configured_company_enrichment_provider()
        finally:
            if original is None:
                os.environ.pop("RUNR_COMPANY_ENRICHMENT_PROVIDER", None)
            else:
                os.environ["RUNR_COMPANY_ENRICHMENT_PROVIDER"] = original
        self.assertIsInstance(provider, ScrapeOpsCompanyProvider)

    def test_scrapeops_additional_fields_are_retained_by_profile_writer(self):
        app, _ = self.backend()
        app._personalized_jobs_service.upsert_company_profile(
            "company-a",
            {
                "schema_version": "phase_f_v3",
                "fields": {},
                "additional_fields": {
                    "legal_name": {"value": "Acme Example GmbH", "state": "known"},
                    "employee_count": {"value": 42, "state": "known"},
                },
            },
        )
        profile = app.repositories.personalized_jobs_store.get_company_profile("company-a")["profile"]
        self.assertEqual(profile["additional_fields"]["legal_name"]["value"], "Acme Example GmbH")
        self.assertEqual(profile["additional_fields"]["employee_count"]["value"], 42)


class PhaseFLogoValidationTests(unittest.TestCase):
    def test_logo_requires_mime_signature_safe_decode_and_dimensions(self):
        logo = validate_logo(_png(), "image/png; charset=utf-8")
        self.assertEqual((logo.width, logo.height), (64, 64))
        with self.assertRaises(LogoValidationError):
            validate_logo(VALID_SVG, "image/png")
        with self.assertRaises(LogoValidationError):
            validate_logo(b"not-an-image", "image/png")
        with self.assertRaises(LogoValidationError):
            validate_logo(b"x" * (MAX_LOGO_BYTES + 1), "image/png")
        with self.assertRaises(LogoValidationError):
            validate_logo(b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"></svg>', "image/svg+xml")

    def test_logo_cache_is_content_addressed_and_records_dimensions(self):
        storage = CountingStorage()
        logo = validate_logo(VALID_SVG, "image/svg+xml; charset=utf-8")
        first_key, first_write = cache_logo(storage, "company-a", logo)
        second_key, second_write = cache_logo(storage, "company-a", logo)

        self.assertEqual(first_key, second_key)
        self.assertTrue(first_write)
        self.assertFalse(second_write)
        self.assertEqual(len(storage.put_calls), 1)
        self.assertEqual(storage.put_calls[0][2]["content_sha256"], logo.content_hash)
        self.assertEqual(storage.put_calls[0][2]["width"], "64")

    def test_official_urls_require_https_approved_hosts_and_public_targets(self):
        with self.assertRaises(LogoValidationError):
            validate_official_url("http://acme.example/logo.svg")
        with self.assertRaises(LogoValidationError):
            validate_official_url("https://10.0.0.1/logo.svg")
        with self.assertRaises(LogoValidationError):
            validate_official_url("https://metadata.google.internal/logo.svg")
        with self.assertRaises(LogoValidationError):
            validate_official_url("https://cdn.other.example/logo.svg", approved_host="acme.example")
        self.assertEqual(
            validate_official_url("https://assets.acme.example/logo.svg#fragment", approved_host="acme.example"),
            "https://assets.acme.example/logo.svg",
        )
        with self.assertRaises(LogoValidationError):
            assert_public_official_host("127.0.0.1")

    def test_monogram_is_deterministic_and_name_based(self):
        self.assertEqual(deterministic_monogram("Acme Labs"), "AL")
        self.assertEqual(deterministic_monogram("Acme Labs"), deterministic_monogram("Acme Labs"))
        self.assertEqual(deterministic_monogram("Acme"), "AC")


if __name__ == "__main__":
    unittest.main()
