import json
import os
import tempfile
import unittest
from pathlib import Path

from backend.bootstrap import create_backend
from backend.domain.models import utc_now_iso


def _seed_catalog(app):
    now = utc_now_iso()
    store = app.repositories.acquisition_store

    def write(connection):
        connection.execute(
            "INSERT INTO canonical_companies VALUES (?, ?, ?, ?, ?, ?)",
            ("company-a", "Acme Labs", "employer", "https://acme.example", now, now),
        )
        payload = {
            "title": "Operations Analyst",
            "location": "Berlin",
            "description": "Operations role",
            "category": "operations",
            "work_arrangement": "remote",
            "employment_type": "full_time",
            "experience_level": "entry",
            "languages": ["German"],
        }
        connection.execute(
            """
            INSERT INTO canonical_jobs (
                canonical_job_id, company_id, identity_key, title, location,
                canonical_url, lifecycle_state, first_seen_at, last_seen_at,
                last_verified_at, absence_count, current_version_id, created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "job-a",
                "company-a",
                "url:job-a",
                "Operations Analyst",
                "Berlin",
                "https://boards.greenhouse.io/acme/jobs/a",
                "active",
                now,
                now,
                now,
                0,
                "version-job-a",
                now,
                now,
            ),
        )
        connection.execute(
            "INSERT INTO job_posting_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "version-job-a",
                "job-a",
                1,
                "hash-job-a",
                payload["title"],
                payload["description"],
                payload["location"],
                "https://boards.greenhouse.io/acme/jobs/a",
                "observation-job-a",
                json.dumps(payload),
                now,
            ),
        )
        connection.execute(
            "INSERT INTO acquisition_publications VALUES (?, ?, ?, ?, ?, ?)",
            ("publication-f", "cycle-f", "valid", "[]", now, ""),
        )
        connection.execute(
            "INSERT INTO acquisition_publication_jobs VALUES (?, ?)",
            ("publication-f", "job-a"),
        )
        connection.execute(
            "INSERT INTO acquisition_publication_head VALUES (?, ?, ?)",
            (1, "publication-f", now),
        )

    store._run_transaction(write)


class PhaseFCompanyProfileTests(unittest.TestCase):
    def _backend(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        os.environ.update(
            {
                "RUNR_TEST_MODE": "1",
                "RUNR_ENV": "test",
                "DATABASE_BACKEND": "sqlite",
                "TURSO_DATABASE_URL": " ",
                "TURSO_AUTH_TOKEN": " ",
                "OBJECT_STORAGE_BACKEND": "local",
            }
        )
        return create_backend(Path(temporary_directory.name), storage_backend="sqlite", test_mode=True)

    def test_missing_profile_does_not_hide_job_and_disables_unreliable_filters(self):
        app = self._backend()
        _seed_catalog(app)

        result = app.get_personalized_jobs("user-a", filters={})

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["jobs"][0]["posting_id"], "job-a")
        self.assertEqual(result["jobs"][0]["company_detail"]["profile"]["fields"]["industry"]["state"], "unknown")
        self.assertFalse(result["filter_capabilities"]["industry"])
        self.assertFalse(result["filter_capabilities"]["company_size"])

    def test_profile_fields_are_provenance_aware_and_logo_is_cached(self):
        app = self._backend()
        _seed_catalog(app)

        app.upsert_personalized_company_profile(
            "company-a",
            {
                "source": "official_employer_source",
                "provenance_url": "https://acme.example/about",
                "verified_at": "2026-08-05T10:00:00+00:00",
                "description": "Tools for better operations.",
                "website": "https://acme.example",
                "industry": "Enterprise Software",
                "company_size": "51-200",
                "headquarters": "Berlin, Germany",
                "founded_year": 2018,
                "funding_stage": "Series B",
                "total_funding": 12000000,
                "funding_year": 2025,
                "leadership_type": "manager",
                "benefits": ["Learning budget"],
                "sponsorship": "unknown",
            },
            logo_bytes=b"verified-logo",
            logo_source_url="https://acme.example/logo.svg",
            logo_content_type="image/svg+xml",
        )

        result = app.get_personalized_jobs("user-a", filters={"industry": ["Enterprise Software"]})
        job = result["jobs"][0]
        profile = job["company_detail"]["profile"]
        industry = profile["fields"]["industry"]

        self.assertEqual(result["total"], 1)
        self.assertEqual(industry["value"], "Enterprise Software")
        self.assertEqual(industry["verified_at"], "2026-08-05T10:00:00+00:00")
        self.assertEqual(profile["fields"]["sponsorship"]["state"], "unknown")
        self.assertTrue(profile["logo_cached"])
        self.assertIn("/catalog/company-logos/company-a/", profile["logo_url"])
        self.assertTrue(result["filter_capabilities"]["industry"])
        self.assertTrue(result["filter_capabilities"]["funding_range"])

        stored = app.repositories.personalized_jobs_store.get_company_profile("company-a")
        self.assertEqual(
            stored["profile"]["fields"]["industry"]["provenance"]["url"],
            "https://acme.example/about",
        )
        self.assertNotIn("provenance", repr(result).casefold())


if __name__ == "__main__":
    unittest.main()
