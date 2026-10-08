import json

import pytest

from backend.repositories.sqlite_acquisition import SqliteAcquisitionStore
from backend.storage.local import LocalObjectStorage
from backend.acquisition.storage_evidence import restore_catalog_evidence


def _store(tmp_path, monkeypatch):
    monkeypatch.setenv('OBJECT_STORAGE_LOCAL_ROOT', str(tmp_path / 'objects'))
    store = SqliteAcquisitionStore(tmp_path / 'catalog.db')
    store.ensure_targets([{
        'target_id': 'target', 'display_name': 'Acme',
        'canonical_target_url': 'https://acme.example/careers',
        'request_url': 'https://acme.example/careers',
        'connector': 'producer_employer', 'publication_enabled': True,
    }])
    return store


def _snapshot(cycle='cycle'):
    return {
        'target_id': 'target', 'cycle_id': cycle, 'task_id': 'task-' + cycle,
        'observed_at': '2026-10-08T12:00:00+00:00',
        'complete_snapshot': True, 'valid_snapshot': True, 'closure_safe': False,
        'jobs': [{'job_id': 'job', 'title': 'Software Engineer',
                  'url': 'https://acme.example/jobs/1',
                  'description': 'Build Python systems',
                  'source_raw_payload': {'unique_salary_evidence': 12345}}],
    }


def test_bulk_writer_archives_original_and_persists_compact_projection(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    store.ingest_snapshots_bulk([_snapshot()])
    with store._connect() as connection:
        row = connection.execute('SELECT payload_json,raw_payload_json FROM job_source_observations').fetchone()
        version = connection.execute('SELECT payload_json FROM job_posting_versions').fetchone()
    payload, raw = json.loads(row[0]), json.loads(row[1])
    assert payload.get('storage_evidence_key'), 'original evidence must be archived before inline copies disappear'
    assert raw.get('storage_evidence_key') == payload['storage_evidence_key']
    assert 'source_raw_payload' not in payload
    assert 'description' not in payload and 'description_raw' not in payload
    assert payload['description_text'] == 'Build Python systems'
    assert json.loads(version[0])['storage_evidence_key'] == payload['storage_evidence_key']
    storage = LocalObjectStorage(tmp_path / 'objects')
    evidence = restore_catalog_evidence(raw, storage)
    assert evidence['raw_payload']['source_raw_payload']['unique_salary_evidence'] == 12345
    with store._connect() as connection:
        mapping = json.loads(connection.execute('SELECT output_json FROM acquisition_rule_outputs').fetchone()[0])
    assert restore_catalog_evidence(mapping, storage)['raw_payload'] == evidence['raw_payload']


def test_unchanged_recollection_does_not_create_a_repair_version(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    store.ingest_snapshots_bulk([_snapshot('first')])
    second = _snapshot('second')
    second['observed_at'] = '2026-10-08T13:00:00+00:00'
    store.ingest_snapshots_bulk([second])
    with store._connect() as connection:
        assert connection.execute('SELECT count(*) FROM job_posting_versions').fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM acquisition_field_provenance WHERE state IN ('unknown','missing') AND raw_value_json IN ('null','[]','{}','\"\"') AND normalized_value_json IN ('null','[]','{}','\"\"') AND evidence_json IN ('null','[]','{}','\"\"')").fetchone()[0] == 0
        outputs = connection.execute('SELECT output_json FROM acquisition_rule_outputs').fetchall()
    assert len(outputs) == 1, 'unchanged collection must reuse normalization evidence'
    for row in outputs:
        mapping = json.loads(row[0])
        assert 'taxonomies' not in mapping
        assert all('evidence' not in field and 'raw_value' not in field for field in mapping['fields'].values())


def test_repeated_publication_rejection_updates_one_current_state(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    rejection = {'canonical_job_id': 'job', 'external_job_id': 'source-job', 'title': 'Engineer',
                 'target_id': 'target', 'task_id': 'task', 'status': 'rejected',
                 'reasons': [{'code': 'missing_application_destination', 'fields': ['application_url']}]}
    with store._connect() as connection:
        store._persist_publication_rejections(connection, cycle_id='first', rejected_rows=[rejection])
        store._persist_publication_rejections(connection, cycle_id='second', rejected_rows=[rejection])
        assert connection.execute('SELECT count(*) FROM acquisition_job_rejections').fetchone()[0] == 1
        assert connection.execute('SELECT cycle_id FROM acquisition_job_rejections').fetchone()[0] == 'second'


def test_failed_archive_prevents_catalog_projection(tmp_path, monkeypatch):
    from backend.acquisition.storage_evidence import CatalogEvidenceError
    import backend.repositories.sqlite_acquisition as module
    store = _store(tmp_path, monkeypatch)
    def fail(*args, **kwargs):
        raise CatalogEvidenceError('archive verification failed')
    monkeypatch.setattr(module, 'archive_catalog_evidence', fail, raising=False)
    with pytest.raises(CatalogEvidenceError, match='verification'):
        store.ingest_snapshots_bulk([_snapshot()])
    with store._connect() as connection:
        assert connection.execute('SELECT count(*) FROM job_source_observations').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM canonical_jobs').fetchone()[0] == 0


def test_bulk_archives_use_bounded_parallel_work(tmp_path, monkeypatch):
    from threading import Barrier, Lock
    import backend.repositories.sqlite_acquisition as module
    store = _store(tmp_path, monkeypatch)
    snapshot = _snapshot()
    template = snapshot['jobs'][0]
    snapshot['jobs'] = [{**template, 'job_id': str(index), 'url': f'https://acme.example/jobs/{index}'} for index in range(8)]
    barrier, lock = Barrier(4), Lock()
    original = module._catalog_storage_payloads
    active = peak = 0
    def tracked(*args):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            barrier.wait(timeout=10)
            return original(*args)
        finally:
            with lock:
                active -= 1
    monkeypatch.setattr(module, '_catalog_storage_payloads', tracked)
    store.ingest_snapshots_bulk([snapshot])
    assert peak == 4
    with store._connect() as connection:
        assert connection.execute('SELECT count(*) FROM job_source_observations').fetchone()[0] == 8


def test_same_title_rejections_without_source_ids_do_not_collide(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    rows = [{'canonical_job_id': job, 'external_job_id': '', 'title': 'Engineer',
             'target_id': 'target', 'reasons': [{'code': 'missing_application_destination'}]}
            for job in ('first-job', 'second-job')]
    with store._connect() as connection:
        store._persist_publication_rejections(connection, cycle_id='first', rejected_rows=rows)
        rows[0]['external_job_id'] = 'new-source-id'
        store._persist_publication_rejections(connection, cycle_id='second', rejected_rows=rows)
        assert connection.execute('SELECT count(*) FROM acquisition_job_rejections').fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM acquisition_job_rejections WHERE external_job_id='new-source-id'").fetchone()[0] == 1
