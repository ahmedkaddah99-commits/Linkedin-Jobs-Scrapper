from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import unittest

from PIL import Image

from backend.application.company_logo_adapter import (
    CompanyLogoAdapter,
    LogoCandidate,
    candidate_from_provider_result,
)
from backend.application.company_operations import (
    CompanyOperations,
    build_company_url_view,
    normalize_company_url,
)


def _png(width: int = 64, height: int = 64) -> bytes:
    stream = BytesIO()
    Image.new("RGBA", (width, height), (13, 98, 140, 255)).save(stream, format="PNG")
    return stream.getvalue()


class _Storage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_calls = 0

    def exists(self, key: str) -> bool:
        return key in self.objects

    def put(self, key: str, data: bytes, *, content_type: str, metadata=None):
        self.put_calls += 1
        self.objects[key] = bytes(data)
        return {"key": key, "content_type": content_type, "metadata": dict(metadata or {})}


class CompanyUrlViewTests(unittest.TestCase):
    def test_normalization_is_structural_and_drops_fragment_without_network_io(self):
        result = normalize_company_url("HTTPS://WWW.Acme.example:443/careers#openings")

        self.assertEqual(result.canonical_url, "https://www.acme.example/careers")
        self.assertEqual(result.validation_status, "not_validated")
        self.assertEqual(result.validation_reason, "network_validation_not_run")
        self.assertEqual(normalize_company_url("https://user:secret@acme.example").validation_reason, "embedded_credentials")

    def test_aggregates_all_url_types_deduplicates_and_selects_primary_with_provenance(self):
        view = build_company_url_view(
            {
                "company_id": "company-a",
                "canonical_name": "Acme Labs",
                "website": "https://acme.example/#company-record",
                "careers_page": "https://acme.example/careers",
                "social_urls": {"linkedin": "https://www.linkedin.com/company/acme"},
            },
            [
                {
                    "url_type": "homepage",
                    "url": "https://ACME.example",
                    "source": "official_company_website",
                    "source_observation_id": "obs-1",
                    "validation_status": "validated",
                    "first_seen_at": "2026-08-01T00:00:00+00:00",
                    "last_seen_at": "2026-08-03T00:00:00+00:00",
                    "provenance": {"field": "Organization.url"},
                },
                {
                    "url_type": "ats_board",
                    "url": "https://boards.greenhouse.io/acme",
                    "source": "ats_connector",
                    "source_observation_id": "obs-2",
                },
                {
                    "url_type": "application_host",
                    "url": "https://jobs.acme.example/apply",
                    "source": "source_observation",
                    "source_observation_id": "obs-3",
                },
                {
                    "url_type": "source",
                    "url": "javascript:void(0)",
                    "source": "source_observation",
                    "source_observation_id": "obs-4",
                },
            ],
        )

        self.assertEqual(view["company_id"], "company-a")
        self.assertEqual(len(view["urls"]), 6)
        homepage = view["primary_urls"]["homepage"]
        self.assertEqual(homepage["canonical_url"], "https://acme.example/")
        self.assertEqual(homepage["validation_status"], "valid")
        self.assertEqual(homepage["first_seen_at"], "2026-08-01T00:00:00+00:00")
        self.assertEqual(homepage["last_seen_at"], "2026-08-03T00:00:00+00:00")
        self.assertEqual(homepage["provenance"]["observations"], ["obs-1"])
        self.assertEqual(view["primary_urls"]["ats_board"]["primary_state"], "primary")
        invalid = next(item for item in view["urls"] if item["url_type"] == "source")
        self.assertEqual(invalid["validation_status"], "invalid")
        self.assertTrue(any(item.startswith("url_not_canonical:") for item in view["warnings"]))


class CompanyLogoAdapterTests(unittest.TestCase):
    def test_valid_candidate_is_validated_without_cache_write_by_default(self):
        storage = _Storage()
        adapter = CompanyLogoAdapter(storage=storage, refresh_after_days=7)
        result = adapter.resolve_one(
            {"company_id": "company-a", "canonical_name": "Acme Labs"},
            candidates=[
                LogoCandidate(
                    provider="official_company_website",
                    data=_png(),
                    content_type="image/png",
                    source_url="https://acme.example/logo.png",
                    observed_at="2026-08-10T10:00:00+00:00",
                    provenance={"field": "Organization.logo"},
                )
            ],
            now="2026-08-10T10:00:00+00:00",
        )

        self.assertEqual(result["state"], "validated")
        self.assertEqual(result["validation_status"], "valid")
        self.assertEqual(result["cache_status"], "not_requested")
        self.assertEqual(result["refresh_state"], "fresh")
        self.assertEqual(result["provenance"]["field"], "Organization.logo")
        self.assertEqual(result["monogram"], "AL")
        self.assertEqual(storage.put_calls, 0)

    def test_explicit_cache_is_content_addressed_and_bad_candidates_do_not_abort(self):
        storage = _Storage()
        adapter = CompanyLogoAdapter(storage=storage)
        result = adapter.resolve_one(
            {"company_id": "company-a", "name": "Acme"},
            candidates=[
                {"provider": "bad", "data": b"not-an-image", "content_type": "image/png", "source_url": "https://bad.example/logo.png"},
                {"provider": "good", "data": _png(), "content_type": "image/png", "source_url": "https://acme.example/logo.png"},
            ],
            persist=True,
            now=datetime(2026, 8, 10, tzinfo=timezone.utc),
        )

        self.assertEqual(result["state"], "cached")
        self.assertEqual(result["cache_status"], "cached")
        self.assertEqual(len(result["candidate_failures"]), 1)
        self.assertIn("logo_candidate_failures", result["warnings"])
        self.assertEqual(storage.put_calls, 1)
        self.assertTrue(result["object_key"].startswith("catalog/company-logos/company-a/"))

    def test_malformed_candidate_is_isolated_without_aborting_the_company(self):
        result = CompanyLogoAdapter().resolve_one(
            {"company_id": "company-a", "name": "Acme"},
            candidates=[
                {"provider": "malformed", "data": "not-bytes", "content_type": "image/png"},
                {"provider": "good", "data": _png(), "content_type": "image/png", "source_url": "https://acme.example/logo.png"},
            ],
        )

        self.assertEqual(result["state"], "validated")
        self.assertEqual(len(result["candidate_failures"]), 1)

    def test_failed_refresh_keeps_cached_logo_and_marks_it_due(self):
        adapter = CompanyLogoAdapter()
        result = adapter.resolve_one(
            {"company_id": "company-a", "name": "Acme"},
            candidates=[{"provider": "official", "data": b"bad", "content_type": "image/png"}],
            cached={
                "provider": "official",
                "object_key": "catalog/company-logos/company-a/hash.png",
                "content_hash": "hash",
                "content_type": "image/png",
                "last_success_at": "2026-07-01T00:00:00+00:00",
                "next_refresh_at": "2026-08-01T00:00:00+00:00",
                "status": "cached",
            },
            now="2026-08-10T00:00:00+00:00",
        )

        self.assertEqual(result["state"], "cached")
        self.assertEqual(result["refresh_state"], "due")
        self.assertIn("logo_refresh_failed", result["warnings"])
        self.assertEqual(result["monogram"], "AC")

    def test_missing_logo_uses_deterministic_monogram_and_many_is_bounded(self):
        adapter = CompanyLogoAdapter()
        result = adapter.resolve_many(
            [
                {"company_id": "company-a", "name": "Acme Labs"},
                {"company_id": "company-b", "name": "Beta"},
                {"name": "Invalid"},
            ],
            limit=2,
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["requested"], 2)
        self.assertEqual(result["results"][0]["state"], "fallback")
        self.assertEqual(result["results"][0]["monogram"], "AL")
        self.assertEqual(result["results"][1]["monogram"], "BE")

    def test_provider_result_adapter_supports_existing_enrichment_shape(self):
        candidate = candidate_from_provider_result(
            {
                "source": "official_company_website",
                "logo_bytes": _png(),
                "logo_content_type": "image/png",
                "logo_source_url": "https://acme.example/logo.png",
            }
        )

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.provider, "official_company_website")
        self.assertEqual(candidate.source_url, "https://acme.example/logo.png")


class CompanyOperationsTests(unittest.TestCase):
    def test_bounded_one_and_many_contracts_are_provider_free_and_isolated(self):
        operations = CompanyOperations(logo_adapter=CompanyLogoAdapter())
        one = operations.one({"company_id": "company-a", "name": "Acme", "website": "https://acme.example"})
        many = operations.many(
            [
                {"company_id": "company-a", "name": "Acme"},
                {"name": "missing-id"},
            ],
            limit=2,
        )

        self.assertEqual(one["status"], "completed")
        self.assertEqual(one["logo"]["state"], "fallback")
        self.assertEqual(many["status"], "degraded")
        self.assertEqual(many["succeeded"], 1)
        self.assertEqual(many["failed"], 1)
        self.assertEqual(many["failures"][0]["error_code"], "ValueError")


if __name__ == "__main__":
    unittest.main()
