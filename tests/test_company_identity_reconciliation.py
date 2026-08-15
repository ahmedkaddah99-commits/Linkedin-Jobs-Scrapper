from __future__ import annotations

from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import Mock

from backend.application.company_reconciliation import build_url_reconciliation_report
from backend.api.routes import build_route_registry
from backend.api.routes.registry import ApiRouteContext
from backend.bootstrap import create_backend
from backend.domain.company_identity import (
    CANONICAL_ENTITY_KINDS,
    CANONICAL_URL_TYPES,
    PROFILE_STATUSES,
    URL_LIFECYCLES,
    canonical_entity_kind,
    canonical_profile_status,
    canonical_url_lifecycle,
    canonical_url_type,
    classify_company_link,
)
from backend.domain.models import utc_now_iso


class _AdminRouteHandler:
    def __init__(self, body=None):
        self.body = body or {}
        self.payload = None
        self.admin_calls = 0

    def _require_admin(self):
        self.admin_calls += 1
        return {"id": "admin-fixture"}, object()

    def _read_json_body(self):
        return self.body

    def _send_json(self, payload, status=200, *, headers=None):
        self.payload = (status, payload)


class CompanyIdentityContractTests(unittest.TestCase):
    def test_explicit_vocabularies_are_closed(self):
        self.assertEqual(CANONICAL_ENTITY_KINDS, ("employer", "source", "fixture", "quarantined", "unknown"))
        self.assertEqual(PROFILE_STATUSES, ("present", "absent", "incomplete", "conflicted"))
        self.assertEqual(
            URL_LIFECYCLES,
            (
                "discovered",
                "configured_official",
                "validated",
                "invalid",
                "rejected",
                "duplicate",
                "unlinked",
                "ignored",
            ),
        )
        self.assertEqual(CANONICAL_URL_TYPES, ("homepage", "careers", "ats_jobs", "job_detail", "source", "other"))
        self.assertEqual(canonical_entity_kind("fixture", quarantined=True), "fixture")
        self.assertEqual(canonical_entity_kind("employer", quarantined=True), "quarantined")
        self.assertEqual(canonical_profile_status("conflicted"), "conflicted")
        self.assertEqual(canonical_url_lifecycle("valid"), "validated")
        self.assertEqual(canonical_url_type("jobs_url"), "careers")

    def test_name_collision_never_auto_merges_and_requires_review(self):
        decision = classify_company_link(
            "Acme",
            [
                {"company_id": "company-de", "canonical_name": "Acme"},
                {"company_id": "company-us", "canonical_name": "Acme"},
            ],
        )
        self.assertEqual(decision.decision, "needs_review")
        self.assertTrue(decision.review_required)
        self.assertEqual(decision.reason, "company_name_collision")

    def test_single_name_match_still_requires_review(self):
        decision = classify_company_link("Acme", [{"company_id": "company-a", "canonical_name": "Acme"}])
        self.assertEqual(decision.decision, "needs_review")
        self.assertTrue(decision.review_required)

    def test_stable_target_identity_can_be_accepted_with_evidence(self):
        decision = classify_company_link(
            "Acme",
            [{"company_id": "company-a", "canonical_name": "Other", "target_id": "target-a"}],
            target_id="target-a",
            evidence=[{"source": "configured_target"}],
        )
        self.assertEqual(decision.decision, "accepted")
        self.assertFalse(decision.review_required)


class UrlReconciliationTests(unittest.TestCase):
    def test_shared_careers_ats_urls_and_duplicate_occurrences_are_reported(self):
        report = build_url_reconciliation_report(
            checked_in_urls=[
                {"company_id": "company-a", "url_type": "careers", "url": "https://jobs.example/careers"},
                {"company_id": "company-a", "url_type": "ats_jobs", "url": "https://boards.greenhouse.io/acme"},
                {"company_id": "company-b", "url_type": "careers", "url": "https://jobs.example/careers"},
            ],
            imported_urls=[
                {"company_id": "company-a", "url_type": "careers", "url": "https://jobs.example/careers"},
                {"company_id": "company-a", "url_type": "careers", "url": "https://JOBS.example/careers#openings"},
                {"company_id": "company-a", "url_type": "ats_jobs", "url": "https://boards.greenhouse.io/acme"},
                {"company_id": "company-c", "url_type": "careers", "url": "https://unlinked.example/careers"},
            ],
            persisted_urls=[
                {"company_id": "company-a", "url_type": "careers", "url": "https://jobs.example/careers"},
                {"company_id": "company-a", "url_type": "ats_jobs", "url": "https://boards.greenhouse.io/acme"},
            ],
        )
        self.assertEqual(report["counts"]["persisted"], 2)
        self.assertEqual(report["counts"]["deduplicated"], 1)
        self.assertEqual(report["counts"]["unlinked"], 1)
        self.assertEqual(report["counts"]["never_imported"], 1)
        self.assertEqual(report["never_imported"][0]["company_id"], "company-b")

    def test_invalid_and_intentionally_ignored_urls_remain_visible(self):
        report = build_url_reconciliation_report(
            imported_urls=[
                {"company_id": "company-a", "url_type": "other", "url": "javascript:void(0)"},
                {
                    "company_id": "company-a",
                    "url_type": "source",
                    "url": "https://source.example",
                    "url_lifecycle": "ignored",
                    "ignored_reason": "fixture source",
                },
            ]
        )
        self.assertEqual(report["counts"]["invalid"], 1)
        self.assertEqual(report["counts"]["intentionally_ignored"], 1)


class SqliteCompanyIdentityTests(unittest.TestCase):
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

    def test_same_name_entities_can_coexist_and_fixture_is_filterable(self):
        app = self._backend()
        store = app.repositories.acquisition_store
        now = utc_now_iso()

        def write(connection):
            connection.execute(
                "INSERT INTO canonical_companies VALUES (?, ?, ?, ?, ?, ?)",
                ("employer-a", "Acme", "employer", "", now, now),
            )
            connection.execute(
                "INSERT INTO canonical_companies VALUES (?, ?, ?, ?, ?, ?)",
                ("source-a", "Acme", "source", "", now, now),
            )
            connection.execute(
                "INSERT INTO canonical_companies VALUES (?, ?, ?, ?, ?, ?)",
                ("fixture-a", "Acme", "fixture", "", now, now),
            )
            connection.execute(
                "INSERT INTO canonical_companies VALUES (?, ?, ?, ?, ?, ?)",
                ("quarantined-a", "Acme", "quarantined", "", now, now),
            )

        store._run_transaction(write)
        rows = store.list_admin_companies(entity_kind="fixture")
        self.assertEqual([row["company_id"] for row in rows], ["fixture-a"])
        self.assertEqual(
            [row["company_id"] for row in store.list_admin_companies(entity_kind="quarantined")], ["quarantined-a"]
        )
        self.assertEqual(len(store.list_admin_companies(search="acme")), 4)

    def test_company_creation_requires_stable_identity_and_does_not_merge_by_name(self):
        app = self._backend()
        store = app.repositories.acquisition_store
        now = utc_now_iso()

        def write(connection):
            first = store._ensure_company(
                connection,
                "Acme",
                "employer",
                now,
                identity_key="target:de",
                identity_type="acquisition_target",
            )
            second = store._ensure_company(
                connection,
                "Acme",
                "employer",
                now,
                identity_key="target:us",
                identity_type="acquisition_target",
            )
            self.assertNotEqual(first, second)

        store._run_transaction(write)
        self.assertEqual(len(store.list_admin_companies(search="acme")), 2)

    def test_link_candidate_preserves_evidence_and_review(self):
        app = self._backend()
        store = app.repositories.acquisition_store
        now = utc_now_iso()

        def write(connection):
            connection.execute(
                "INSERT INTO canonical_companies VALUES (?, ?, ?, ?, ?, ?)",
                ("company-a", "Acme", "employer", "", now, now),
            )

        store._run_transaction(write)
        result = store.record_admin_company_link_candidate(
            observed_name="Acme",
            candidate_company_ids=["company-a"],
            target_id="target-a",
            evidence=[{"source": "job_observation", "url": "https://source.example/job"}],
        )
        self.assertEqual(result["decision"]["decision"], "needs_review")
        detail = store.get_admin_company_detail("company-a")
        self.assertEqual(detail["identity_evidence"][0]["evidence"]["evidence"][0]["source"], "job_observation")
        self.assertTrue(detail["link_candidates"][0]["review_required"])

    def test_shared_careers_and_ats_urls_are_scoped_to_each_company(self):
        app = self._backend()
        store = app.repositories.acquisition_store
        now = utc_now_iso()

        def write(connection):
            for company_id in ("company-a", "company-b"):
                connection.execute(
                    "INSERT INTO canonical_companies VALUES (?, ?, ?, ?, ?, ?)",
                    (company_id, company_id, "employer", "", now, now),
                )
            for company_id in ("company-a", "company-b"):
                store._record_company_url_occurrence(
                    connection,
                    company_id=company_id,
                    url_type="careers",
                    url="https://shared.example/careers",
                    url_lifecycle="configured_official",
                    source="official_employer_source",
                    now=now,
                    persist=True,
                )
                store._record_company_url_occurrence(
                    connection,
                    company_id=company_id,
                    url_type="ats_jobs",
                    url="https://boards.greenhouse.io/shared",
                    url_lifecycle="validated",
                    source="ats_connector",
                    now=now,
                    persist=True,
                )

        store._run_transaction(write)
        with store._connect() as connection:
            persisted = connection.execute(
                "SELECT company_id, url_type, canonical_url FROM canonical_company_urls ORDER BY company_id, url_type"
            ).fetchall()
            occurrences = connection.execute(
                "SELECT COUNT(*) AS count FROM canonical_company_url_occurrences"
            ).fetchone()
        self.assertEqual(len(persisted), 4)
        self.assertEqual({str(row["company_id"]) for row in persisted}, {"company-a", "company-b"})
        self.assertEqual(int(occurrences["count"]), 4)

    def test_company_site_inventory_is_idempotent_and_domain_scoped(self):
        app = self._backend()
        store = app.repositories.acquisition_store

        first = store.sync_company_site_inventory(
            [
                {"company_name": "Acme Example", "url": "https://acme.example/careers"},
                {"company_name": "Acme Example", "url": "https://acme.example/careers"},
                {"company_name": "Other Example", "url": "https://other.example/jobs"},
            ],
            checked_in_path="inventory.jsonl",
            import_id="inventory-test",
        )
        second = store.sync_company_site_inventory(
            [
                {"company_name": "Acme Example", "url": "https://acme.example/careers"},
                {"company_name": "Other Example", "url": "https://other.example/jobs"},
            ],
            checked_in_path="inventory.jsonl",
            import_id="inventory-test",
        )

        self.assertEqual(first["companies_created"], 2)
        self.assertEqual(first["urls_persisted"], 2)
        self.assertEqual(first["duplicates_skipped"], 1)
        self.assertEqual(second["companies_created"], 0)
        self.assertEqual(second["urls_persisted"], 0)
        self.assertEqual(second["duplicates_skipped"], 2)
        self.assertEqual(len(store.list_admin_companies(entity_kind="employer", limit=20)), 2)


class CompanyIdentityApiTests(unittest.TestCase):
    def test_company_filters_and_url_inspection_are_admin_authorized_and_bounded(self):
        registry = build_route_registry()
        application = Mock()
        application.list_admin_companies.return_value = []
        handler = _AdminRouteHandler()
        context = ApiRouteContext(
            application=application,
            handler=handler,
            method="GET",
            segments=("admin", "acquisition", "companies"),
            query={
                "entity_kind": ["fixture"],
                "profile_status": ["incomplete"],
                "url_type": ["ats_jobs"],
                "url_lifecycle": ["discovered"],
                "limit": ["9999"],
            },
        )
        self.assertTrue(registry.dispatch(context, auth_required=True))
        self.assertEqual(handler.admin_calls, 1)
        application.list_admin_companies.assert_called_once_with(
            limit=500,
            search="",
            entity_kind="fixture",
            profile_status="incomplete",
            url_type="ats_jobs",
            url_lifecycle="discovered",
        )

        application.reset_mock()
        application.list_admin_company_urls.return_value = {"read_only": True, "urls": [], "occurrences": []}
        handler = _AdminRouteHandler()
        context = ApiRouteContext(
            application=application,
            handler=handler,
            method="GET",
            segments=("admin", "acquisition", "companies", "company-a", "urls"),
            query={"persisted_only": ["true"], "limit": ["9999"]},
        )
        self.assertTrue(registry.dispatch(context, auth_required=True))
        application.list_admin_company_urls.assert_called_once_with(
            "company-a", url_type="", url_lifecycle="", include_occurrences=False, limit=1000
        )

    def test_company_routes_are_rejected_without_route_authentication(self):
        registry = build_route_registry()
        application = Mock()
        handler = _AdminRouteHandler()
        context = ApiRouteContext(
            application=application,
            handler=handler,
            method="GET",
            segments=("admin", "acquisition", "companies"),
            query={},
        )
        self.assertFalse(registry.dispatch(context, auth_required=False))
        application.list_admin_companies.assert_not_called()


if __name__ == "__main__":
    unittest.main()
