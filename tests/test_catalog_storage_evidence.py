from unittest.mock import Mock
import pytest
from backend.storage.local import LocalObjectStorage
from backend.acquisition.storage_evidence import (archive_catalog_evidence, restore_catalog_evidence, CatalogEvidenceMissingError, CatalogEvidenceCorruptError)


def test_roundtrip_deterministic_and_deduplicated(tmp_path):
    storage = LocalObjectStorage(tmp_path)
    storage.put = Mock(wraps=storage.put)
    job = {'title': 'Über engineer', 'source_raw_payload': {'html': '<p>' + 'source ' * 500 + '</p>'}, 'unified_mapping': {'rule': 'v1'}}
    reference = archive_catalog_evidence(job, storage=storage)
    second = archive_catalog_evidence(dict(reversed(list(job.items()))), storage=storage)
    assert reference == second
    assert storage.put.call_count == 1
    assert reference['storage_evidence_bytes'] < reference['storage_evidence_uncompressed_bytes']
    assert restore_catalog_evidence(reference, storage=storage) == {'schema_version': 1, 'payload': job, 'raw_payload': job['source_raw_payload']}
    other = LocalObjectStorage(tmp_path / 'other')
    assert archive_catalog_evidence(job, storage=other) == reference
    assert storage.get(reference['storage_evidence_key']) == other.get(reference['storage_evidence_key'])


def test_missing_corrupt_and_existing_corrupt_fail(tmp_path):
    storage = LocalObjectStorage(tmp_path)
    reference = archive_catalog_evidence({'title': 'job'}, {'id': 42}, storage)
    storage.delete(reference['storage_evidence_key'])
    with pytest.raises(CatalogEvidenceMissingError):
        restore_catalog_evidence(reference, storage)
    storage.put(reference['storage_evidence_key'], b'broken')
    with pytest.raises(CatalogEvidenceCorruptError):
        restore_catalog_evidence(reference, storage)
    with pytest.raises(CatalogEvidenceCorruptError):
        archive_catalog_evidence({'title': 'job'}, {'id': 42}, storage)


def test_reference_validation_and_bounded_decompression(tmp_path, monkeypatch):
    import backend.acquisition.storage_evidence as module
    storage = LocalObjectStorage(tmp_path)
    reference = archive_catalog_evidence({'html': 'x' * 1000}, storage=storage)
    monkeypatch.setattr(module, 'MAX_EVIDENCE_BYTES', 100)
    with pytest.raises(CatalogEvidenceCorruptError):
        restore_catalog_evidence(reference, storage)
    with pytest.raises(CatalogEvidenceCorruptError):
        restore_catalog_evidence({**reference, 'storage_evidence_key': 'private/elsewhere.json.gz'}, storage)

@pytest.mark.parametrize('column', ['raw_payload_json', 'payload_json'])
def test_replay_hydrates_original_source_only(tmp_path, monkeypatch, column):
    import json
    import backend.acquisition.reprocessing as replay
    storage = LocalObjectStorage(tmp_path)
    raw = {'title': 'original', 'html': '<p>source</p>'}
    reference = archive_catalog_evidence({'title': 'normalized', 'apply_url': 'https://apply.example'}, raw, storage)
    monkeypatch.setattr(replay, 'restore_catalog_evidence', lambda ref: restore_catalog_evidence(ref, storage))
    row = {column: json.dumps(reference)}
    assert replay._reprocessing_source_payload(row) == (raw, False)
    assert replay._reprocessing_source_payload({'raw_payload_json': json.dumps(raw)}) == (raw, False)


def test_collection_metadata_does_not_duplicate_source_evidence(tmp_path):
    storage = LocalObjectStorage(tmp_path)
    raw = {'updated_at': '2026-01-01', 'observed_at': 'source-owned-value'}
    first = {'title': 'job', 'observed_at': 'today', 'source_observation_id': 'one', 'unified_mapping': {'records': [{'observed_at': 'today', 'published_at': 'yesterday'}]}, 'source_raw_payload': raw}
    second = {**first, 'observed_at': 'tomorrow', 'source_observation_id': 'two', 'unified_mapping': {'records': [{'observed_at': 'tomorrow', 'published_at': 'yesterday'}]}}
    reference = archive_catalog_evidence(first, storage=storage)
    assert archive_catalog_evidence(second, storage=storage) == reference
    envelope = restore_catalog_evidence(reference, storage)
    assert envelope['raw_payload'] == raw
    assert envelope['payload']['source_raw_payload'] == raw
    assert envelope['payload']['unified_mapping']['records'][0]['published_at'] == 'yesterday'
def test_remote_catalog_refuses_writer_local_evidence(monkeypatch, tmp_path):
    from backend.acquisition.storage_evidence import archive_catalog_evidence, CatalogEvidenceError
    monkeypatch.setenv('TURSO_DATABASE_URL', 'libsql://test.invalid')
    monkeypatch.setenv('OBJECT_STORAGE_BACKEND', 'local')
    monkeypatch.setenv('OBJECT_STORAGE_LOCAL_ROOT', str(tmp_path / 'objects'))
    with pytest.raises(CatalogEvidenceError, match='shared object storage'):
        archive_catalog_evidence({'title': 'Engineer'})



def test_normalized_same_source_two_collection_times_deduplicates(tmp_path):
    from backend.acquisition.quality import normalize_job_for_ingestion
    storage = LocalObjectStorage(tmp_path)
    raw = {'id': '123', 'title': 'Engineer', 'description': 'Build software', 'location': 'Berlin', 'url': 'https://example.com/jobs/123'}
    target = {'connector': 'greenhouse', 'display_name': 'Example', 'target_id': 'target', 'source_token': 'example', 'canonical_target_url': 'https://example.com/careers'}
    first = normalize_job_for_ingestion(raw, target, observed_at='2026-01-01T00:00:00Z')
    second = normalize_job_for_ingestion(raw, target, observed_at='2026-01-02T00:00:00Z')
    assert archive_catalog_evidence(first, raw, storage) == archive_catalog_evidence(second, raw, storage)
