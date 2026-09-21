import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
