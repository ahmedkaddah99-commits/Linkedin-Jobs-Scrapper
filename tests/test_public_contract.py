from __future__ import annotations

import unittest

from backend.acquisition.public_contract import (
    build_field_lineage,
    build_typed_filter_predicate,
    build_version_diff,
    matches_typed_filters,
    normalize_typed_contract,
    serialize_public_contract,
)


class PublicContractTests(unittest.TestCase):
    @staticmethod
    def _payload() -> dict[str, object]:
        return {
            "title": "Finance Operations Engineer",
            "company": {"name": "Acme GmbH"},
            "location_collection": [
                {"city": "Berlin", "country_code": "DE"},
                {"label": "Remote - Germany"},
            ],
            "description": "This role mentions remote collaboration, but is office based.",
            "source_raw_payload": {"secret": "do-not-expose"},
            "unified_mapping": {
                "schema_version": "unified_mapping_v1",
                "rule_version": "unified_mapping_v1",
                "fields": {
                    "runr_function": {
                        "normalized_value": "Finance",
                        "state": "present",
                        "source": "greenhouse",
                        "source_field": "department",
                        "extraction_method": "versioned_department_mapping",
                        "confidence": 0.9,
                        "evidence": "Finance",
                        "raw_value": "Finance",
                    },
                    "source_department": {
                        "normalized_value": "Finance",
                        "state": "present",
                        "source": "greenhouse",
                        "source_field": "department",
                        "confidence": 0.95,
                        "evidence": "Finance",
                    },
                    "source_team": {"normalized_value": "Operations", "state": "present"},
                    "source_category": {"normalized_value": "Accounting", "state": "present"},
                    "employment_type": {"normalized_value": "full_time", "state": "present"},
                    "workplace_arrangement": {"normalized_value": "onsite", "state": "present"},
                    "remote_geographic_restrictions": {"normalized_value": ["Germany"], "state": "present"},
                    "languages": {
                        "normalized_value": [{"language": "German", "status": "required", "proficiency": "C1"}],
                        "state": "present",
                    },
                    "experience": {
                        "normalized_value": {
                            "minimum_years": 3,
                            "maximum_years": 6,
                            "seniority": "mid",
                            "requirement_status": "required",
                        },
                        "state": "present",
                    },
                    "salary": {
                        "normalized_value": {"min": 70000, "max": 90000, "currency": "EUR", "period": "year"},
                        "state": "present",
                    },
                    "application_destination": {
                        "normalized_value": {
                            "classification": "careers_index",
                            "destination_type": "listing_fallback",
                            "user_facing_url": "https://acme.example/careers",
                            "status": "unresolved",
                            "application_method": "listing_fallback",
                        },
                        "state": "present",
                    },
                    "completeness": {
                        "normalized_value": {"overall": {"status": "warning", "present": 8, "total": 10}},
                        "state": "present",
                    },
                    "warnings": {"normalized_value": ["missing_direct_application_url"], "state": "present"},
                    "freshness": {"normalized_value": {"state": "fresh", "age_days": 1}, "state": "present"},
                    "duplicate": {"normalized_value": {"state": "candidate", "cluster_id": "cluster-1"}, "state": "present"},
                    "logo": {"normalized_value": {"state": "known", "url": "https://acme.example/logo.png"}, "state": "present"},
                    "enrichment": {"normalized_value": {"state": "available", "provider": "approved"}, "state": "present"},
                    "publication_state": {"normalized_value": "published", "state": "present"},
                },
            },
        }

    def test_serializer_adds_typed_namespace_without_overwriting_legacy_fields(self):
        payload = {
            "title": "Backend Engineer",
            "languages": ["German"],
            "salary": {"min": 70000, "currency": "EUR"},
            "unified_mapping": {
                "schema_version": "unified_mapping_v1",
                "rule_version": "unified_mapping_v1",
                "fields": {
                    "runr_function": {
                        "normalized_value": "Engineering",
                        "state": "present",
                        "source": "greenhouse",
                        "source_field": "department",
                        "confidence": 0.9,
                    },
                },
            },
        }

        result = serialize_public_contract(payload)

        self.assertEqual(result["languages"], ["German"])
        self.assertEqual(result["salary"], {"min": 70000, "currency": "EUR"})
        self.assertEqual(result["typed"]["runr_function"], "Engineering")
        self.assertEqual(result["typed"]["schema_version"], "public_typed_contract_v1")

    def test_normalizer_returns_canonical_typed_shapes_and_truthful_application_state(self):
        typed = normalize_typed_contract(self._payload())

        self.assertEqual(typed["runr_function"], "Finance")
        self.assertEqual(typed["source_team"], "Operations")
        self.assertEqual(typed["employment_type"], "Full-time")
        self.assertEqual(typed["workplace_arrangement"], "On-site")
        self.assertEqual(typed["locations"][0]["city"], "Berlin")
        self.assertEqual(typed["languages"], [{"language": "German", "requirement": "required", "proficiency": "C1"}])
        self.assertEqual(typed["experience"]["minimum_years"], 3)
        self.assertEqual(typed["salary"]["maximum"], 90000)
        self.assertEqual(typed["application_status"], "unresolved")
        self.assertIsNone(typed["application_destination"]["resolved_url"])
        self.assertEqual(typed["completeness"]["score"], 0.8)

    def test_public_serializer_excludes_admin_evidence_but_admin_lineage_is_bounded(self):
        public = serialize_public_contract(self._payload())
        admin = serialize_public_contract(self._payload(), audience="admin")

        self.assertNotIn("source_raw_payload", public)
        self.assertNotIn("unified_mapping", public)
        self.assertNotIn("evidence", public["typed"])
        self.assertNotIn("raw_value", public["typed"])
        lineage = next(item for item in admin["typed_lineage"] if item["field"] == "runr_function")
        self.assertEqual(lineage["provenance"]["source_field"], "department")
        self.assertEqual(lineage["evidence_summary"], "Finance")

    def test_typed_filters_do_not_match_words_in_untyped_description(self):
        payload = self._payload()

        self.assertFalse(matches_typed_filters(payload, {"workplace_arrangement": "Remote"}))
        self.assertTrue(matches_typed_filters(payload, {"work_arrangement": "On-site", "runr_function": "Finance"}))
        self.assertFalse(matches_typed_filters(payload, {"runr_function": "Engineering"}))
        self.assertTrue(matches_typed_filters(payload, {"location": "Berlin", "language": "German", "salary_min": 80000}))
        self.assertFalse(matches_typed_filters(payload, {"salary_max": 60000}))

    def test_filter_predicate_is_reusable_for_canonical_records(self):
        predicate = build_typed_filter_predicate({"source_team": "Operations", "experience_min": 2})

        self.assertTrue(predicate(self._payload()))
        changed = self._payload()
        changed["unified_mapping"]["fields"]["source_team"]["normalized_value"] = "Treasury"  # type: ignore[index]
        self.assertFalse(predicate(changed))

    def test_lineage_and_version_diff_only_present_typed_values(self):
        before = self._payload()
        after = self._payload()
        after["unified_mapping"]["fields"]["workplace_arrangement"]["normalized_value"] = "hybrid"  # type: ignore[index]
        after["unified_mapping"]["fields"]["salary"]["normalized_value"] = {"min": 80000, "max": 100000, "currency": "EUR"}  # type: ignore[index]

        diff = build_version_diff(before, after)
        self.assertEqual(diff["changed_fields"], ["workplace_arrangement", "salary"])
        self.assertNotIn("source_raw_payload", str(diff))
        public_lineage = build_field_lineage(before, audience="public", fields=["runr_function"])
        self.assertNotIn("provenance", public_lineage[0])


if __name__ == "__main__":
    unittest.main()
