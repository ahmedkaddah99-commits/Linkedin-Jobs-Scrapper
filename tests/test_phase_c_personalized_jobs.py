import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from backend.bootstrap import create_backend
from backend.application.acquisition_scheduler import PhaseAAcquisitionScheduler
from backend.domain.models import utc_now_iso


def _seed_catalog(app, *, valid_until: str = "") -> None:
    now = utc_now_iso()
    store = app.repositories.acquisition_store

    def write(connection):
        for company_id, name in (("company-a", "Acme Labs"), ("company-b", "Beta Systems")):
            connection.execute(
                "INSERT INTO canonical_companies VALUES (?, ?, ?, ?, ?, ?)",
                (company_id, name, "employer", f"https://{company_id}.example", now, now),
            )
        jobs = (
            ("job-a", "company-a", "Operations Analyst", "Berlin", "https://boards.greenhouse.io/acme/jobs/a", "operations", "remote"),
            ("job-b", "company-b", "Finance Analyst", "Munich", "https://jobs.lever.co/beta/b", "finance", "onsite"),
        )
        for job_id, company_id, title, location, apply_url, category, arrangement in jobs:
            version_id = f"version-{job_id}"
            payload = {
                "title": title,
                "location": location,
                "description": f"{category} role",
                "category": category,
                "work_arrangement": arrangement,
                "employment_type": "full_time",
                "experience_level": "entry",
                "salary": {"min": 50000, "max": 70000, "currency": "EUR"},
                "languages": ["German"],
            }
            connection.execute(
                """
                INSERT INTO canonical_jobs (
                    canonical_job_id, company_id, identity_key, title, location, canonical_url,
                    lifecycle_state, first_seen_at, last_seen_at, last_verified_at,
                    absence_count, current_version_id, created_at, updated_at, identity_signature
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, company_id, f"url:{job_id}", title, location, apply_url, "active", now, now, now, 0, version_id, now, now, f"signature:{job_id}"),
            )
            connection.execute(
                "INSERT INTO job_posting_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (version_id, job_id, 1, f"hash-{job_id}", title, payload["description"], location, apply_url, f"observation-{job_id}", json.dumps(payload), now),
            )
        connection.execute(
            """
            INSERT INTO acquisition_publications (
                publication_id, cycle_id, status, snapshot_json, published_at,
                valid_until, previous_publication_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("publication-c", "cycle-c", "valid", "[]", now, valid_until, ""),
        )
        connection.executemany(
            "INSERT INTO acquisition_publication_jobs VALUES (?, ?)",
            [("publication-c", "job-a"), ("publication-c", "job-b")],
        )
        connection.execute(
            "INSERT INTO acquisition_publication_head VALUES (?, ?, ?)",
            (1, "publication-c", now),
        )

    store._run_transaction(write)


class PhaseCPersonalizedJobsTests(unittest.TestCase):
    def _backend(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        # The test boundary requires explicit local-only database settings.
        import os

        os.environ.update(
            {
                "RUNR_TEST_MODE": "1",
                "RUNR_ENV": "test",
                "DATABASE_BACKEND": "sqlite",
                "TURSO_DATABASE_URL": " ",
                "TURSO_AUTH_TOKEN": " ",
            }
        )
        return create_backend(Path(temporary_directory.name), storage_backend="sqlite", test_mode=True)

    def test_filters_cursor_and_user_state_are_server_side_and_isolated(self):
        app = self._backend()
        _seed_catalog(app)
        app.save_personalized_preferences(
            "user-a",
            {
                "target_roles": ["operations"],
                "preferred_locations": ["Berlin"],
                "work_arrangements": ["remote"],
            },
        )
        with patch.object(PhaseAAcquisitionScheduler, "run_due_cycle") as acquire:
            page = app.get_personalized_jobs("user-a", limit=1)
            acquire.assert_not_called()
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["jobs"][0]["posting_id"], "job-a")
        self.assertEqual(page["jobs"][0]["apply_url"], "https://boards.greenhouse.io/acme/jobs/a")
        self.assertEqual(page["evaluation"]["state"], "available")

        app.set_personalized_job_state("user-a", "job-a", "hidden")
        self.assertEqual(app.get_personalized_jobs("user-a")["jobs"], [])
        self.assertEqual(len(app.get_personalized_jobs("user-b")["jobs"]), 2)
        self.assertEqual(app.get_hidden_personalized_jobs("user-a")["jobs"][0]["user_state"], "hidden")
        app.set_personalized_job_state("user-a", "job-a", "none")
        self.assertEqual(len(app.get_personalized_jobs("user-a")["jobs"]), 1)

    def test_cursor_and_saved_search_are_stable_and_one_per_user(self):
        app = self._backend()
        _seed_catalog(app)
        saved = app.save_personalized_saved_search("user-a", {"name": "Default", "filters": {"location": ["Berlin"]}})
        updated = app.save_personalized_saved_search("user-a", {"name": "Updated", "filters": {"location": ["Munich"]}})
        self.assertEqual(saved["saved_search_id"], updated["saved_search_id"])
        self.assertEqual(app.get_personalized_saved_search("user-a")["name"], "Updated")

        first = app.get_personalized_jobs("user-a", filters={}, limit=1)
        self.assertEqual(first["total"], 1)  # the default saved search is applied
        self.assertIsNone(first["next_cursor"])
        all_jobs = app.get_personalized_jobs("user-a", filters={"location": ["Berlin", "Munich"]}, limit=1)
        self.assertEqual(all_jobs["total"], 2)
        self.assertIsNotNone(all_jobs["next_cursor"])
        second = app.get_personalized_jobs("user-a", filters={"location": ["Berlin", "Munich"]}, cursor=all_jobs["next_cursor"], limit=1)
        self.assertEqual(second["total"], 2)
        self.assertEqual(len(second["jobs"]), 1)
        with self.assertRaises(ValueError):
            app.get_personalized_jobs("user-a", filters={"location": ["Berlin"]}, cursor=all_jobs["next_cursor"], limit=1)

    def test_missing_catalog_and_expired_publication_are_explicit(self):
        app = self._backend()
        self.assertEqual(app.get_personalized_jobs("user-a")["evaluation"]["state"], "unavailable")
        expired = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        _seed_catalog(app, valid_until=expired)
        result = app.get_personalized_jobs("user-a")
        self.assertEqual(result["evaluation"]["state"], "stale")
        self.assertIn("loading", result["evaluation"]["supported_states"])


if __name__ == "__main__":
    unittest.main()
