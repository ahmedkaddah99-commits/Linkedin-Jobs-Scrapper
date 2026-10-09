from copy import deepcopy

from backend.acquisition.storage_payload import compact_catalog_payload, hydrate_description_aliases
from backend.acquisition.public_contract import normalize_typed_contract
from backend.acquisition.unified_mapping import map_job_fields


def test_catalog_compaction_preserves_projection_and_unique_descriptions():
    job = {"title": "Engineer", "description_text": "Build", "description": "Build",
           "description_raw": "Build", "description_html": "<p>Build</p>",
           "company_urls": [{"url": "https://example.com", "url_type": "official"}],
           "source_raw_payload": {"custom": "unique"}, "source": "greenhouse"}
    job["unified_mapping"] = map_job_fields(job, source="greenhouse", observed_at="2026-10-08")
    original = deepcopy(job)
    compact = compact_catalog_payload(job)
    assert normalize_typed_contract(compact) == normalize_typed_contract(job)
    assert job == original
    assert compact_catalog_payload(compact) == compact
    assert "description" not in compact and "description_raw" not in compact
    assert compact["description_html"] == "<p>Build</p>"
    assert compact["source_raw_payload"]["custom"] == "unique"
    assert "raw_value" not in compact["unified_mapping"]["fields"]["description"]
    assert "clean_text" not in compact["unified_mapping"]["fields"]["description"]["normalized_value"]
    assert hydrate_description_aliases(compact)["description"] == "Build"


def test_archive_reference_is_explicit_and_conflicting_aliases_survive():
    job = {"description_text": "Build", "description": "Original", "source_raw_payload": {"custom": "unique"}}
    compact = compact_catalog_payload(job, storage_evidence_key="archive/jobs/verified.json.gz")
    assert "source_raw_payload" not in compact
    assert compact["storage_evidence_key"] == "archive/jobs/verified.json.gz"
    assert compact["description"] == "Original"
    assert hydrate_description_aliases(compact)["description"] == "Original"


def test_missing_and_inferred_states_remain_distinct():
    job = {"unified_mapping": {"rule_version": "v1", "fields": {
        "employment_type": {"normalized_value": None, "state": "missing", "raw_value": None},
        "workplace_arrangement": {"normalized_value": "Remote", "state": "inferred", "confidence": .8},
    }}}
    compact = compact_catalog_payload(job)
    typed = normalize_typed_contract(compact)
    assert typed["field_states"]["employment_type"] == "missing"
    assert typed["field_states"]["workplace_arrangement"] == "inferred"
    assert compact["unified_mapping"]["fields"]["workplace_arrangement"]["confidence"] == .8


def test_unique_mapping_description_survives():
    job = {"description_text": "Build", "unified_mapping": {"fields": {
        "description": {"raw_value": "Original source text", "normalized_value": {"clean_text": "Build"}},
        "employment_type": {"raw_value": "Contract", "state": "present"},
    }}}
    compact = compact_catalog_payload(job)
    assert compact["unified_mapping"]["fields"]["description"]["normalized_value"]["source_description"] == "Original source text"
    assert normalize_typed_contract(compact) == normalize_typed_contract(job)
    assert compact_catalog_payload(compact) == compact
