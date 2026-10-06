import json
import unittest
from unittest.mock import patch
from tests import test_jobs_feed_performance as performance
from tests.test_phase_c_personalized_jobs import _seed_catalog


class RoleScopedFeedTests(unittest.TestCase):
    _backend = performance.JobsFeedPerformanceTests._backend

    def classified(self):
        app = self._backend()
        _seed_catalog(app)

        def seed(c):
            for job, roles in [("job-a", ["Data Analyst", "Business Analyst"]), ("job-b", ["Finance Analyst"])]:
                c.execute(
                    "INSERT INTO job_filter_intelligence VALUES (?,?,?,?,?,?,?)",
                    (
                        "version-" + job,
                        job,
                        "hash-" + job,
                        json.dumps({"collar": "white", "roles": roles}),
                        "test",
                        "test",
                        "now",
                    ),
                )

        app.repositories.acquisition_store._run_transaction(seed)
        return app

    def test_empty_selection_does_not_query_catalog(self):
        app = self.classified()
        store = app.repositories.personalized_jobs_store
        with patch.object(store, "query_published_jobs", side_effect=AssertionError("catalog read without selection")):
            page = app.get_personalized_jobs("user-a", require_role_selection=True, card_view=True)
        self.assertTrue(page["selection_required"])
        self.assertEqual(page["jobs"], [])

    def test_indexed_roles_filters_pagination_and_no_count(self):
        app = self.classified()
        store = app.repositories.personalized_jobs_store
        trace = []
        original = store._connect
        from contextlib import contextmanager

        @contextmanager
        def traced():
            with original() as c:
                c._connection.set_trace_callback(trace.append)
                yield c

        with patch.object(store, "_connect", traced):
            result = store.query_published_jobs(
                "user-a",
                filters={"role": ["Data Analyst", "Business Analyst"], "location": ["Berlin"]},
                role_scoped=True,
                include_total=False,
                limit=1,
            )
        self.assertEqual([r["canonical_job_id"] for r in result["rows"]], ["job-a"])
        self.assertIsNone(result["total"])
        self.assertFalse(any("COUNT(" in s.upper() for s in trace if "feed_page_ids" in s))
        result = store.query_published_jobs(
            "user-a", filters={"role": ["Data Analyst"], "location": ["Munich"]}, role_scoped=True, include_total=False
        )
        self.assertEqual(result["rows"], [])

    def test_role_lookup_tracks_classification_and_ignores_metadata_only_updates(self):
        app = self.classified()
        store = app.repositories.acquisition_store

        def check(c):
            before = c._connection.total_changes
            c.execute("UPDATE job_filter_intelligence SET generated_at='later' WHERE canonical_job_id='job-a'")
            self.assertEqual(c._connection.total_changes - before, 1)
            c.execute(
                "UPDATE job_filter_intelligence SET filters_json=? WHERE canonical_job_id='job-a'",
                (json.dumps({"collar": "white", "roles": ["Software Engineer"]}),),
            )
            roles = c.execute("SELECT role FROM job_filter_roles WHERE canonical_job_id='job-a'").fetchall()
            self.assertEqual([r["role"] for r in roles], ["software engineer"])
            c.execute("DELETE FROM job_filter_intelligence WHERE canonical_job_id='job-a'")
            self.assertEqual(
                c.execute("SELECT role FROM job_filter_roles WHERE canonical_job_id='job-a'").fetchall(), []
            )

        store._run_transaction(check)

    def test_stale_classification_and_unpublished_jobs_are_excluded(self):
        app = self.classified()
        store = app.repositories.personalized_jobs_store
        app.repositories.acquisition_store._run_transaction(
            lambda c: c.execute(
                "UPDATE job_filter_intelligence SET content_hash='stale' WHERE canonical_job_id='job-a'"
            )
        )
        page = store.query_published_jobs(
            "user-a", filters={"role": ["Data Analyst"]}, role_scoped=True, include_total=False
        )
        self.assertEqual(page["rows"], [])
        app.repositories.acquisition_store._run_transaction(
            lambda c: c.execute("DELETE FROM acquisition_publication_jobs WHERE canonical_job_id='job-b'")
        )
        self.assertEqual(
            store.query_published_jobs(
                "user-a", filters={"role": ["Finance Analyst"]}, role_scoped=True, include_total=False
            )["rows"],
            [],
        )

    def test_customer_feed_paginates_without_total_or_capability_scan(self):
        app = self.classified()
        store = app.repositories.personalized_jobs_store
        filters = {"role": ["Data Analyst", "Business Analyst", "Finance Analyst"]}
        with patch.object(store, "get_published_filter_capabilities", return_value={}) as capabilities:
            first = app.get_personalized_jobs(
                "user-a", filters=filters, limit=1, require_role_selection=True, card_view=True
            )
            second = app.get_personalized_jobs(
                "user-a",
                filters=filters,
                limit=1,
                cursor=first["next_cursor"],
                require_role_selection=True,
                card_view=True,
            )
        self.assertIsNone(first["total"])
        self.assertIsNone(second["total"])
        self.assertEqual(len({first["jobs"][0]["canonical_job_id"], second["jobs"][0]["canonical_job_id"]}), 2)
        self.assertIsNone(second["next_cursor"])
        capabilities.assert_called_with(query_support_only=True)

    def test_role_query_plan_starts_from_indexed_lookup(self):
        app = self.classified()
        store = app.repositories.personalized_jobs_store
        with store._connect() as c:
            plan = c.execute(
                "EXPLAIN QUERY PLAN " + store._feed_candidate_sql(["data analyst"]),
                ("data analyst", "user-a", "publication-c"),
            ).fetchall()
        details = " ".join(r["detail"] for r in plan)
        self.assertIn("SEARCH job_filter_roles USING COVERING INDEX idx_job_filter_roles_role (role=?)", details)
        self.assertNotIn("SCAN pj", details)
        self.assertNotIn("SCAN j", details)

    def test_role_scope_applies_to_every_sort_and_search(self):
        app = self.classified()
        store = app.repositories.personalized_jobs_store
        for sort in ["newest", "priority", "best", "least_competitive"]:
            page = store.query_published_jobs(
                "user-a",
                filters={"role": ["Data Analyst"], "sort": sort, "search_text": ["Operations"]},
                role_scoped=True,
                include_total=False,
            )
            self.assertEqual([r["canonical_job_id"] for r in page["rows"]], ["job-a"])
            self.assertIsNone(page["total"])
