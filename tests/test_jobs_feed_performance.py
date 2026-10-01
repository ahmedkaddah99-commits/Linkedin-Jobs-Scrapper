import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from backend.bootstrap import create_backend
from tests.test_phase_c_personalized_jobs import _seed_catalog


def _promote_new_publication(app, publication_id: str, job_ids: list[str]) -> None:
    """Insert a new valid publication and move the head pointer to it."""
    from backend.domain.models import utc_now_iso

    now = utc_now_iso()

    def write(connection):
        connection.execute(
            """
            INSERT INTO acquisition_publications (
                publication_id, cycle_id, status, snapshot_json, published_at,
                valid_until, previous_publication_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (publication_id, f"cycle-{publication_id}", "valid", "[]", now, "", ""),
        )
        connection.executemany(
            "INSERT INTO acquisition_publication_jobs VALUES (?, ?)",
            [(publication_id, job_id) for job_id in job_ids],
        )
        connection.execute("UPDATE acquisition_publication_head SET publication_id = ?, updated_at = ? WHERE head_id = 1", (publication_id, now))

    app.repositories.acquisition_store._run_transaction(write)


class JobsFeedPerformanceTests(unittest.TestCase):
    def _backend(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        import os

        os.environ.update({
            "RUNR_TEST_MODE": "1",
            "RUNR_ENV": "test",
            "DATABASE_BACKEND": "sqlite",
            "TURSO_DATABASE_URL": " ",
            "TURSO_AUTH_TOKEN": " ",
        })
        return create_backend(Path(temporary_directory.name), storage_backend="sqlite", test_mode=True)

    def test_feed_response_reports_truthful_server_phase_timings(self):
        app = self._backend()
        _seed_catalog(app)

        for card_view in (False, True):
            result = app.get_personalized_jobs("user-a", limit=25, card_view=card_view)
            timings = result["timings"]
            self.assertEqual(set(timings), {"store_query_ms", "capabilities_ms", "total_ms"})
            for value in timings.values():
                self.assertIsInstance(value, float)
                self.assertGreaterEqual(value, 0.0)
            self.assertGreaterEqual(timings["total_ms"], timings["capabilities_ms"])

    def test_filter_capabilities_are_cached_per_publication_and_stay_bounded(self):
        app = self._backend()
        _seed_catalog(app)
        store = app.repositories.personalized_jobs_store

        first = store.get_published_filter_capabilities()
        second = store.get_published_filter_capabilities()
        self.assertEqual(first, second)
        self.assertEqual(set(store._filter_capabilities_cache), {"publication-c"})

        # A new publication head is a different, immutable catalog: the cache
        # must recompute instead of serving the previous publication's result.
        _promote_new_publication(app, "publication-d", ["job-a"])
        third = store.get_published_filter_capabilities()
        self.assertEqual(len(store._filter_capabilities_cache), 2)
        self.assertEqual(third["posting_recency"], True)

        # The cache stays bounded when many publications are read.
        for index in range(10):
            _promote_new_publication(app, f"publication-cache-{index}", ["job-a", "job-b"])
            store.get_published_filter_capabilities()
        self.assertLessEqual(len(store._filter_capabilities_cache), store._FILTER_CAPABILITIES_CACHE_LIMIT)

    def test_cached_capabilities_match_a_fresh_recomputation(self):
        app = self._backend()
        _seed_catalog(app)
        store = app.repositories.personalized_jobs_store
        cached = store.get_published_filter_capabilities()
        store._filter_capabilities_cache.clear()
        recomputed = store.get_published_filter_capabilities()
        self.assertEqual(cached, recomputed)

    def test_default_feed_pages_ids_before_hydrating_expensive_job_details(self):
        app = self._backend()
        _seed_catalog(app)
        store = app.repositories.personalized_jobs_store
        statements: list[str] = []
        original_connect = store._connect

        @contextmanager
        def traced_connect():
            with original_connect() as connection:
                connection._connection.set_trace_callback(statements.append)
                yield connection

        with patch.object(store, "_connect", side_effect=traced_connect):
            result = store.query_published_jobs("user-a", limit=1, filters={"sort": "newest"})

        self.assertEqual(len(result["rows"]), 2)
        page_sql = next(sql for sql in statements if "feed_page_ids" in sql)
        self.assertIn("SELECT COUNT(*) AS total FROM matches", page_sql)
        self.assertIn("WITH matches AS MATERIALIZED", page_sql)
        self.assertIn("LIMIT 2", page_sql)
        self.assertNotIn("job_applicant_snapshots", page_sql)
        self.assertNotIn("personalized_job_evaluations", page_sql)
        self.assertNotIn("job_posting_versions", page_sql)
        hydration_sql = next(sql for sql in statements if "feed_page_hydration" in sql)
        self.assertIn("j.canonical_job_id IN", hydration_sql)
        self.assertNotIn("ROW_NUMBER() OVER", hydration_sql)

    def test_search_counts_and_pages_from_one_filtered_catalog_scan(self):
        app = self._backend()
        _seed_catalog(app)
        store = app.repositories.personalized_jobs_store
        statements: list[str] = []
        original_connect = store._connect

        @contextmanager
        def traced_connect():
            with original_connect() as connection:
                connection._connection.set_trace_callback(statements.append)
                yield connection

        with patch.object(store, "_connect", side_effect=traced_connect):
            first = store.query_published_jobs("user-a", filters={"search_text": ["analyst"], "sort": "newest"}, limit=1)
            if first["rows"]:
                row = first["rows"][0]
                second = store.query_published_jobs("user-a", filters={"search_text": ["analyst"], "sort": "newest"}, limit=1, cursor={"sort": row["last_verified_at"], "canonical_job_id": row["canonical_job_id"]})
                self.assertEqual(second["total"], first["total"])
                self.assertEqual(len(second["rows"]), 1)

        self.assertEqual(first["total"], 2)
        self.assertEqual(sum("feed_page_ids" in sql for sql in statements), 1 + bool(first["rows"]))
        self.assertFalse(any("SELECT COUNT(*) AS total FROM (" in sql for sql in statements))

    def test_search_finds_company_title_and_posting_skill_from_scalar_query(self):
        app = self._backend()
        _seed_catalog(app)
        for query, expected_id in (
            ("Acme", "job-a"),
            ("Finance", "job-b"),
            ("operations", "job-a"),
        ):
            page = app.get_personalized_jobs("user-a", filters={"q": query}, card_view=True)
            self.assertEqual(page["total"], 1, query)
            self.assertEqual(page["jobs"][0]["posting_id"], expected_id)

        # The index follows edits to the current version and company name.
        store = app.repositories.acquisition_store
        def rename(connection):
            connection.execute("UPDATE canonical_companies SET canonical_name='Renamed Labs' WHERE company_id='company-a'")
        store._run_transaction(rename)
        renamed = app.get_personalized_jobs("user-a", filters={"q": "Renamed"}, card_view=True)
        self.assertEqual(renamed["total"], 1)

    def test_filter_capability_scan_does_not_hydrate_job_history(self):
        app = self._backend()
        _seed_catalog(app)
        store = app.repositories.personalized_jobs_store
        statements: list[str] = []
        original_connect = store._connect

        @contextmanager
        def traced_connect():
            with original_connect() as connection:
                connection._connection.set_trace_callback(statements.append)
                yield connection

        with patch.object(store, "_connect", side_effect=traced_connect):
            store.get_published_filter_capabilities()

        capability_sql = next(sql for sql in statements if "filter_capability_probe" in sql)
        self.assertNotIn("MAX(CASE WHEN", capability_sql)
        self.assertIn("EXISTS", capability_sql)
        self.assertNotIn("job_applicant_snapshots", capability_sql)
        self.assertNotIn("job_source_observations", capability_sql)

    def test_large_catalog_uses_supported_filters_without_scanning_json_payloads(self):
        app = self._backend()
        _seed_catalog(app)
        store = app.repositories.personalized_jobs_store
        store._DYNAMIC_CAPABILITY_SCAN_LIMIT = 1
        statements: list[str] = []
        original_connect = store._connect

        @contextmanager
        def traced_connect():
            with original_connect() as connection:
                connection._connection.set_trace_callback(statements.append)
                yield connection

        with patch.object(store, "_connect", side_effect=traced_connect):
            capabilities = store.get_published_filter_capabilities()

        self.assertTrue(all(capabilities.values()))
        self.assertFalse(any("filter_capability_probe" in sql for sql in statements))


if __name__ == "__main__":
    unittest.main()
