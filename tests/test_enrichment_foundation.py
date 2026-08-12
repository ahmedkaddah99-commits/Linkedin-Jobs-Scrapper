from __future__ import annotations

import inspect
import os
import socket
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.acquisition.unified_mapping import map_job_fields
from backend.database.connection import database_session
from backend.database.initialization import initialize_database
from backend.database.migrations import run_migrations
from backend.database.schema import BASE_SCHEMA_SQL
from backend.enrichment.activation import (
    foundation_projection_enabled,
    foundation_publication_enabled,
)
from backend.enrichment.boundaries import (
    build_company_request,
    build_occupation_request,
    build_place_requests,
    company_identity_can_auto_link,
    extract_language_evidence,
    language_state,
)
from backend.enrichment.cache import cache_key, expires_at, input_fingerprint, sanitize_result_payload
from backend.enrichment.contracts import (
    EnrichmentRequest,
    EvidenceEnvelope,
    LicenceMetadata,
    ProviderBudget,
    ProviderExecutionContext,
    ProviderMetadata,
    ProviderResult,
    ProviderResultState,
    RetentionPolicy,
)
from backend.enrichment.fixture import load_evaluation_fixture, validate_fixture_privacy
from backend.enrichment.persistence import (
    activate_version,
    append_evidence,
    get_cache_entry,
    list_versions,
    put_cache_entry,
    register_version,
)
from backend.enrichment.providers import (
    FixtureCompanyProvider,
    FixtureOccupationProvider,
    FixturePlaceProvider,
    NullProvider,
)
from backend.repositories.sqlite_migrations import MIGRATIONS


class EnrichmentContractTests(unittest.TestCase):
    def test_every_provider_result_state_is_supported(self):
        for state in ProviderResultState:
            result = ProviderResult(state=state)
            self.assertEqual(result.state, state)

    def test_default_external_budget_is_zero(self):
        budget = ProviderBudget()
        self.assertEqual(budget.max_requests, 0)
        self.assertEqual(budget.max_cost_units, 0.0)
        self.assertFalse(budget.consume())

    def test_null_provider_is_fail_closed(self):
        request = EnrichmentRequest("place", "job-1", "job_location", {"display": "Paris"})
        result = NullProvider().resolve(request, ProviderExecutionContext())
        self.assertEqual(result.state, ProviderResultState.BLOCKED_BY_POLICY)
        self.assertEqual(result.request_count, 0)

    def test_fixture_providers_have_no_storage_or_network_boundary(self):
        request = EnrichmentRequest("place", "job-1", "place", {"display": "Paris", "country_code": "FR"})
        providers = [FixturePlaceProvider(), FixtureCompanyProvider(), FixtureOccupationProvider(), NullProvider()]
        with patch.object(socket, "socket", side_effect=AssertionError("network is forbidden")):
            result = providers[0].resolve(request, ProviderExecutionContext())
        self.assertEqual(result.state, ProviderResultState.MATCHED)
        for provider in providers:
            signature = inspect.signature(provider.resolve)
            self.assertNotIn("connection", signature.parameters)
            self.assertNotIn("storage", signature.parameters)
            self.assertNotIn("http_client", signature.parameters)

    def test_fixture_provider_result_states_and_replacement(self):
        matched_request = EnrichmentRequest("place", "job-1", "place", {"display": "Paris", "country_code": "FR"})
        ambiguous_request = EnrichmentRequest("place", "job-2", "place", {"display": "Paris"})
        unsupported_request = EnrichmentRequest("company", "company-1", "website", {"name": "Example"})
        provider = FixturePlaceProvider()
        context = ProviderExecutionContext()
        self.assertEqual(provider.resolve(matched_request, context).state, ProviderResultState.MATCHED)
        self.assertEqual(provider.resolve(ambiguous_request, context).state, ProviderResultState.AMBIGUOUS)
        self.assertEqual(provider.resolve(unsupported_request, context).state, ProviderResultState.UNSUPPORTED)
        self.assertEqual(
            FixturePlaceProvider({}).resolve(matched_request, context).state,
            ProviderResultState.NO_MATCH,
        )
        replacement = FixturePlaceProvider(
            {
                "paris|fr|": {
                    "candidate_id": "replacement:paris",
                    "normalized_value": {"city": "Paris", "country_code": "FR"},
                }
            }
        )
        self.assertEqual(replacement.resolve(matched_request, context).candidates[0].candidate_id, "replacement:paris")

    def test_fixture_evidence_is_never_auto_selected(self):
        request = EnrichmentRequest("place", "job-1", "place", {"display": "Paris", "country_code": "FR"})
        result = FixturePlaceProvider().resolve(request, ProviderExecutionContext())
        self.assertTrue(result.evidence)
        self.assertFalse(any(evidence.selected for evidence in result.evidence))


class EnrichmentBoundaryTests(unittest.TestCase):
    def test_places_preserve_multiple_locations_and_keep_remote_as_context(self):
        requests = build_place_requests(
            target_id="job-1",
            raw_location=["Paris, France", "Lyon, France"],
            workplace_arrangement="Hybrid",
            remote_scope="France",
        )
        self.assertEqual([request.input["display"] for request in requests], ["Paris, France", "Lyon, France"])
        self.assertEqual(requests[0].context["workplace_arrangement"], "Hybrid")
        self.assertEqual(requests[0].context["remote_scope"], "France")

        remote = build_place_requests(
            target_id="job-2",
            raw_location="Remote EU",
            workplace_arrangement="Remote",
            remote_scope="EU",
        )
        self.assertEqual(remote, ())

    def test_company_name_alone_cannot_auto_link(self):
        self.assertFalse(company_identity_can_auto_link(name="Lowell"))
        self.assertTrue(company_identity_can_auto_link(name="Lowell", domain="lowell.com"))
        request = build_company_request(target_id="company-1", name="Lowell")
        self.assertFalse(request.context["name_only_auto_link_allowed"])

    def test_occupation_request_keeps_title_department_and_employment_context_separate(self):
        request = build_occupation_request(
            target_id="job-1",
            title="Werkstudent Data Analyst",
            department="Engineering",
            description_excerpt="Analyze product metrics.",
        )
        self.assertEqual(request.input["title"], "Werkstudent Data Analyst")
        self.assertEqual(request.input["department"], "Engineering")
        self.assertNotIn("employment_type", request.input)
        self.assertEqual(request.context["description_excerpt"], "Analyze product metrics.")

    def test_posting_language_alone_never_creates_requirement(self):
        evidence = extract_language_evidence(
            posting_language="French",
            description="Nous construisons des produits utiles pour nos clients.",
        )
        self.assertEqual(evidence, ())
        self.assertEqual(language_state(evidence), "not_established")

    def test_language_evidence_requires_structured_or_explicit_text(self):
        required = extract_language_evidence(description="German C1 required for this role.")
        preferred = extract_language_evidence(description="Preferred languages: French and English")
        mentioned = extract_language_evidence(description="Languages: German and English")
        boilerplate = extract_language_evidence(description="You will work with our German and English teams.")
        self.assertEqual(language_state(required), "required")
        self.assertEqual(required[0].proficiency, "C1")
        self.assertEqual(language_state(preferred), "preferred")
        self.assertEqual(language_state(mentioned), "mentioned")
        self.assertEqual(language_state(boilerplate), "not_established")


class EnrichmentCacheAndPersistenceTests(unittest.TestCase):
    def _db_path(self, name: str) -> Path:
        root = Path(tempfile.mkdtemp(prefix=f"runr-enrichment-{name}-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        return root / "backend.sqlite3"

    def _evidence(self, *, raw: bool = False) -> EvidenceEnvelope:
        return EvidenceEnvelope(
            target_type="place",
            target_id="job-1",
            field_path="job_location",
            input_fingerprint="input-fingerprint",
            normalized_candidate_value={"city": "Paris", "country_code": "FR"},
            candidate_id="fixture:paris-fr",
            provider_id="fixture_place",
            adapter_version="fixture_adapter_v1",
            dataset_version="runr_fixture_v1",
            snapshot_version="offline_fixture_2026_08",
            source_uri="offline://runr-fixture",
            source_record_id="fixture-paris",
            source_field="location",
            extraction_method="offline_fixture",
            observed_at="2026-08-12T00:00:00+00:00",
            retrieved_at="2026-08-12T00:00:00+00:00",
            licence=LicenceMetadata(raw_storage_permitted=False),
            terms_url="",
            privacy_class="offline_fixture",
            retention_class="fixture",
            rule_version="place_normalization_v1",
            result_state=ProviderResultState.MATCHED,
            raw_value={"source": "not persisted"} if raw else None,
            raw_evidence_excerpt="minimal excerpt" if raw else "",
            raw_storage_permitted=raw,
        )

    def test_migration_adds_only_new_foundation_tables_and_evidence_is_append_only(self):
        db_path = self._db_path("migration")
        initialize_database(db_path, force=True)
        with database_session(db_path) as connection:
            tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'enrichment_%'"
                ).fetchall()
            }
            self.assertEqual(
                tables,
                {"enrichment_evidence", "enrichment_version_registry", "enrichment_cache_entries"},
            )
            evidence = self._evidence(raw=True)
            append_evidence(connection, evidence)
            stored = connection.execute(
                "SELECT raw_value_json, raw_evidence_excerpt, raw_storage_permitted FROM enrichment_evidence WHERE evidence_id=?",
                (evidence.evidence_id,),
            ).fetchone()
            self.assertEqual(stored["raw_value_json"], "null")
            self.assertEqual(stored["raw_evidence_excerpt"], "")
            self.assertEqual(stored["raw_storage_permitted"], 0)
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE enrichment_evidence SET selected=1 WHERE evidence_id=?",
                    (evidence.evidence_id,),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM enrichment_evidence WHERE evidence_id=?",
                    (evidence.evidence_id,),
                )

    def test_migration_upgrades_previous_level_and_is_idempotent(self):
        db_path = self._db_path("migration_previous_level")
        with patch.dict(
            os.environ,
            {
                "DATABASE_BACKEND": "sqlite",
                "RUNR_ENV": "test",
                "TURSO_DATABASE_URL": "",
                "TURSO_AUTH_TOKEN": "",
            },
        ):
            with database_session(db_path) as connection:
                connection.executescript(BASE_SCHEMA_SQL)
                applied_before_foundation = run_migrations(connection, MIGRATIONS[:-1])
                self.assertEqual(applied_before_foundation, [migration.migration_id for migration in MIGRATIONS[:-1]])
                self.assertIsNone(
                    connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='enrichment_evidence'"
                    ).fetchone()
                )
                applied_foundation = run_migrations(connection, MIGRATIONS)
                rerun = run_migrations(connection, MIGRATIONS)

                self.assertEqual(applied_foundation, ["049_enrichment_foundation"])
                self.assertEqual(rerun, [])
                self.assertIsNotNone(
                    connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='enrichment_evidence'"
                    ).fetchone()
                )
                triggers = {
                    row["name"]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'trg_enrichment_evidence_%'"
                    ).fetchall()
                }
                self.assertEqual(
                    triggers,
                    {
                        "trg_enrichment_evidence_immutable_delete",
                        "trg_enrichment_evidence_immutable_update",
                    },
                )

    def test_versions_are_inactive_until_explicit_activation(self):
        db_path = self._db_path("versions")
        initialize_database(db_path, force=True)
        with database_session(db_path) as connection:
            version_id = register_version(
                connection,
                version_kind="rule",
                version_key="place_normalization",
                version_value="v1",
            )
            row = connection.execute(
                "SELECT is_active FROM enrichment_version_registry WHERE version_id=?",
                (version_id,),
            ).fetchone()
            self.assertEqual(row["is_active"], 0)
            activate_version(connection, version_id)
            self.assertEqual(
                connection.execute(
                    "SELECT is_active FROM enrichment_version_registry WHERE version_id=?",
                    (version_id,),
                ).fetchone()["is_active"],
                1,
            )
            self.assertEqual(len(list_versions(connection, version_kind="rule")), 1)

    def test_cache_identity_contains_all_replacement_dimensions(self):
        request = EnrichmentRequest("place", "job-1", "place", {"display": "Paris", "country_code": "FR"})
        metadata = ProviderMetadata(
            provider_id="fixture_place", adapter_version="v1", dataset_version="d1", snapshot_version="s1"
        )
        original_fingerprint = input_fingerprint(request)
        original_key = cache_key(request, metadata, fingerprint=original_fingerprint)
        changed_rule = EnrichmentRequest(
            request.target_type,
            request.target_id,
            request.field_path,
            request.input,
            request.context,
            request.policy_version,
            "place_normalization_v2",
        )
        self.assertNotEqual(original_key, cache_key(changed_rule, metadata, fingerprint=original_fingerprint))

    def test_cache_sanitizes_raw_payload_and_separates_negative_ttl(self):
        db_path = self._db_path("cache")
        initialize_database(db_path, force=True)
        request = EnrichmentRequest("place", "job-1", "place", {"display": "Paris"})
        metadata = ProviderMetadata(provider_id="fixture_place", adapter_version="v1")
        matched = ProviderResult(state=ProviderResultState.MATCHED, raw_storage_permitted=True)
        no_match = ProviderResult(state=ProviderResultState.NO_MATCH, raw_storage_permitted=True)
        self.assertNotIn("raw_response", sanitize_result_payload(matched, raw_storage_permitted=False))
        with database_session(db_path) as connection:
            put_cache_entry(
                connection,
                cache_key=cache_key(request, metadata),
                input_fingerprint=input_fingerprint(request),
                provider_id=metadata.provider_id,
                adapter_version=metadata.adapter_version,
                dataset_version=metadata.dataset_version,
                rule_version=request.rule_version,
                policy_version=request.policy_version,
                result=matched,
                retrieved_at="2026-08-12T00:00:00+00:00",
                policy=RetentionPolicy(),
            )
            entry = get_cache_entry(connection, cache_key(request, metadata))
            self.assertIsNotNone(entry)
            self.assertFalse(entry["raw_storage_permitted"])
            self.assertEqual(entry["result"]["raw_storage_permitted"], False)
            self.assertEqual(
                expires_at(matched, retrieved_at="2026-08-12T00:00:00+00:00", policy=RetentionPolicy()),
                "2026-09-11T00:00:00+00:00",
            )
            self.assertNotEqual(
                expires_at(no_match, retrieved_at="2026-08-12T00:00:00+00:00", policy=RetentionPolicy()),
                "2026-09-11T00:00:00+00:00",
            )


class EnrichmentFixtureAndRegressionTests(unittest.TestCase):
    def test_fixture_is_sanitized_and_blind_labels_are_not_exposed(self):
        validate_fixture_privacy()
        cases = load_evaluation_fixture()
        blind = load_evaluation_fixture(include_blind_holdout=True)[len(cases) :]
        self.assertTrue(cases)
        self.assertTrue(blind)
        self.assertTrue(all("expected" in case for case in cases))
        self.assertTrue(all("expected" not in case for case in blind))
        self.assertTrue(all(case["synthetic"] is True for case in cases + blind))

    def test_fixture_covers_required_adversarial_categories(self):
        cases = load_evaluation_fixture(include_blind_holdout=True)
        ids = {case["fixture_id"] for case in cases}
        for required in (
            "dev_paris_france",
            "dev_paris_texas",
            "dev_paris_ontario",
            "cal_unqualified_paris",
            "dev_lowell_employer_leeds",
            "dev_lowell_massachusetts",
            "dev_multiple_locations",
            "dev_hybrid_role",
            "dev_remote_germany",
            "dev_remote_eu",
            "cal_remote_without_scope",
            "dev_explicit_required_language",
            "dev_preferred_language",
            "cal_language_merely_mentioned",
            "dev_posting_written_in_language_only",
        ):
            self.assertIn(required, ids)

    def test_new_foundation_does_not_change_published_unified_mapping_shape(self):
        mapping = map_job_fields(
            {
                "title": "Senior Backend Engineer",
                "department": "Engineering",
                "employment_type": "Full-time",
                "workplace_arrangement": "Hybrid",
                "languages": [{"language": "German", "status": "required"}],
                "description_text": "Required languages: German",
                "company": {"name": "Example GmbH", "website": "https://example.com/"},
            },
            observed_at="2026-08-12T00:00:00+00:00",
        )
        self.assertEqual(mapping["schema_version"], "unified_mapping_v1")
        self.assertEqual(mapping["rule_version"], "unified_mapping_v1")
        self.assertEqual(mapping["fields"]["runr_function"]["normalized_value"], "Engineering")
        self.assertEqual(mapping["fields"]["workplace_arrangement"]["normalized_value"], "Hybrid")
        self.assertEqual(mapping["languages"][0]["status"], "required")

    def test_new_projection_and_publication_gates_are_inactive_by_default(self):
        self.assertFalse(foundation_projection_enabled())
        self.assertFalse(foundation_publication_enabled())


if __name__ == "__main__":
    unittest.main()
