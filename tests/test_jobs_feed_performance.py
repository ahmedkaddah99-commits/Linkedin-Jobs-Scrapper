import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from backend.bootstrap import create_backend
from tests.test_phase_c_personalized_jobs import _seed_catalog


def _append_test_payload(connection, payload_json):
    connection.execute(
        """INSERT INTO job_posting_versions (
            version_id, canonical_job_id, version_number, content_hash, title,
            description, location, apply_url, source_observation_id, payload_json, created_at
        ) SELECT 'version-performance', canonical_job_id, version_number+1,
                 content_hash, title, description, location, apply_url,
                 source_observation_id, ?, created_at
          FROM job_posting_versions WHERE version_id=(
              SELECT current_version_id FROM canonical_jobs WHERE canonical_job_id='job-a')""",
        (payload_json,),
    )
    connection.execute("UPDATE canonical_jobs SET current_version_id='version-performance' WHERE canonical_job_id='job-a'")


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
    def test_default_count_reads_posting_hash_only_for_blue_candidates(self):
        import sqlite3
        from backend.repositories.sqlite_personalized_jobs import SqlitePersonalizedJobsStore

        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        hash_reads = []
        connection.create_function("read_posting_hash", 1, lambda value: (hash_reads.append(value), value)[1])
        connection.executescript("""
            CREATE TABLE acquisition_publication_jobs(publication_id TEXT, canonical_job_id TEXT);
            CREATE TABLE canonical_jobs(canonical_job_id TEXT PRIMARY KEY, company_id TEXT,
                current_version_id TEXT, first_seen_at TEXT, last_verified_at TEXT);
            CREATE TABLE canonical_companies(company_id TEXT PRIMARY KEY, entity_kind TEXT);
            CREATE TABLE version_data(version_id TEXT PRIMARY KEY, content_hash TEXT);
            CREATE VIEW job_posting_versions AS SELECT version_id,
                read_posting_hash(content_hash) AS content_hash FROM version_data;
            CREATE TABLE job_filter_intelligence(version_id TEXT PRIMARY KEY, content_hash TEXT, filters_json TEXT);
            CREATE TABLE personalized_job_dispositions(user_id TEXT, canonical_job_id TEXT, state TEXT);
            CREATE INDEX idx_canonical_jobs_feed_metadata ON canonical_jobs(
                canonical_job_id, company_id, current_version_id, last_verified_at, first_seen_at);
            CREATE INDEX idx_job_filter_feed_metadata ON job_filter_intelligence(
                version_id, content_hash, json_extract(filters_json, '$.collar'));
            INSERT INTO canonical_companies VALUES ('company','employer');
        """)
        for index in range(100):
            job, version = f"job-{index}", f"version-{index}"
            connection.execute("INSERT INTO canonical_jobs VALUES (?,'company',?,'','')", (job, version))
            connection.execute("INSERT INTO acquisition_publication_jobs VALUES ('publication',?)", (job,))
            connection.execute("INSERT INTO version_data VALUES (?,'current')", (version,))
            connection.execute("INSERT INTO job_filter_intelligence VALUES (?,?,?)", (
                version, "stale" if index == 9 else "current",
                '{"collar":"blue"}' if index < 10 else '{"collar":"white"}',
            ))
        total = connection.execute("SELECT COUNT(*) FROM (" + SqlitePersonalizedJobsStore._feed_index_sql() + ")",
                                   ("user", "publication")).fetchone()[0]
        self.assertEqual(total, 91)  # Nine current blue records are excluded; the stale one is visible.
        self.assertLessEqual(len(hash_reads), 10)

    def test_page_hydration_reads_uncommitted_rows_from_ambient_connection(self):
        from unittest.mock import Mock

        app = self._backend()
        store = app.repositories.personalized_jobs_store
        connection = Mock()
        connection.execute.return_value.fetchall.return_value = [{"canonical_job_id": "job", "value": "uncommitted"}]
        connection.fetch_read_rows.return_value = [{"canonical_job_id": "job", "value": "committed"}]
        store._active_transaction_connection = connection
        rows = store._hydrate_feed_page(connection, publication_id="publication", user_id="user", canonical_job_ids=["job"])
        self.assertEqual(rows[0]["value"], "uncommitted")
        connection.fetch_read_rows.assert_not_called()

    def test_feed_omits_acquisition_audit_payloads_but_preserves_public_fields(self):
        import json

        app = self._backend()
        _seed_catalog(app)
        store = app.repositories.personalized_jobs_store
        full_payload = {"employment_type": "full-time", "salary": {"min": 60000},
                        "job": {"skills": ["Python"]}, "description": "Public description"}
        internal_fields = ("source_raw_payload", "unified_mapping", "field_provenance",
                           "normalized_source_metadata", "content_fingerprint")
        full_payload.update({key: {"audit": "x" * 10000} for key in internal_fields})
        app.repositories.acquisition_store._run_transaction(lambda connection: _append_test_payload(connection, json.dumps(full_payload)))
        page = store.query_published_jobs("user-a", limit=25)
        row = next(row for row in page["rows"] if row["canonical_job_id"] == "job-a")
        compact = json.loads(row["version_payload_json"])
        self.assertEqual(compact, {key: value for key, value in full_payload.items() if key not in internal_fields})
        detail = store.get_published_job_row("job-a")
        self.assertEqual(json.loads(detail["version_payload_json"]), full_payload)

    def test_capabilities_refresh_when_same_publication_is_updated(self):
        app = self._backend()
        _seed_catalog(app)
        store = app.repositories.personalized_jobs_store
        before = store.get_published_filter_capabilities()
        app.repositories.acquisition_store._run_transaction(lambda connection: (
            _append_test_payload(connection, '{"lifting_requirement":"20 kg"}'),
            connection.execute("UPDATE acquisition_publication_head SET updated_at='later' WHERE head_id=1"),
        ))
        self.assertFalse(before["lifting_requirement"])
        self.assertTrue(store.get_published_filter_capabilities()["lifting_requirement"])

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
        self.assertEqual({key.split(":", 1)[0] for key in store._filter_capabilities_cache}, {"publication-c"})

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
        # Current-version classification must exclude reviewed blue collar jobs.
        self.assertIn("job_posting_versions", page_sql)
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

    def test_search_finds_company_and_title_but_not_description_only_text(self):
        app = self._backend()
        _seed_catalog(app)
        for query, expected_id in (
            ("Acme", "job-a"),
            ("Finance", "job-b"),
        ):
            page = app.get_personalized_jobs("user-a", filters={"q": query}, card_view=True)
            self.assertEqual(page["total"], 1, query)
            self.assertEqual(page["jobs"][0]["posting_id"], expected_id)

        description_only = app.get_personalized_jobs("user-a", filters={"q": "role"}, card_view=True)
        self.assertEqual(description_only["total"], 0)
        self.assertEqual(description_only["jobs"], [])

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
