from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from scripts import process_catalog_enrichment as worker


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / 'catalog.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE work(id INTEGER PRIMARY KEY, state TEXT, token TEXT)')
        db.executemany("INSERT INTO work VALUES(?,'pending','')", [(i,) for i in range(20)])
    monkeypatch.setenv('DATABASE_BACKEND', 'sqlite')
    monkeypatch.setenv('SQLITE_DATABASE_PATH', str(path))
    monkeypatch.setenv('RUNR_ENV', 'production')
    monkeypatch.delenv('TURSO_DATABASE_URL', raising=False)
    monkeypatch.delenv('TURSO_AUTH_TOKEN', raising=False)
    monkeypatch.delenv('RUNR_MIGRATION_HEAD', raising=False)
    return path


def test_worker_uses_configured_sqlite_without_turso(database):
    result = worker.execute("UPDATE work SET state='done' WHERE id=0 RETURNING id,state")
    assert result == [{'id': 0, 'state': 'done'}]
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT state FROM work WHERE id=0').fetchone()[0] == 'done'


def test_concurrent_claims_are_disjoint_and_durable(database):
    def claim(token):
        return worker.execute("UPDATE work SET state='processing',token=? WHERE id IN "
                              "(SELECT id FROM work WHERE state='pending' LIMIT 3) "
                              "AND state='pending' RETURNING id", (str(token),))
    with ThreadPoolExecutor(max_workers=8) as pool:
        groups = list(pool.map(claim, range(8)))
    ids = [r['id'] for group in groups for r in group]
    assert len(ids) == len(set(ids)) == 20
    assert worker.execute("SELECT COUNT(*) AS n FROM work WHERE state='pending'") == [{'n': 0}]


def test_worker_rejects_missing_production_database(database, monkeypatch):
    monkeypatch.setenv('SQLITE_DATABASE_PATH', str(database.parent / 'missing.sqlite3'))
    with pytest.raises(sqlite3.OperationalError):
        worker.execute('SELECT 1')
    assert not (database.parent / 'missing.sqlite3').exists()


def test_provider_result_survives_restart_without_second_call(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(worker.NemoClient, '__call__', lambda self, prompt: calls.append(prompt) or {'jobs': []})
    path = tmp_path / 'ledger.sqlite3'
    client = worker.NemoClient(path, 1)
    assert client.for_version('version', 'hash', 'prompt') == {'jobs': []}
    client.db.close()
    client = worker.NemoClient(path, 1)
    assert client.for_version('version', 'hash', 'prompt') == {'jobs': []}
    assert calls == ['prompt']
    client.db.close()


def test_uncertain_provider_request_is_not_automatically_replayed(tmp_path, monkeypatch):
    calls = []
    def fail(self, prompt):
        calls.append(prompt)
        raise TimeoutError('provider timed out')
    monkeypatch.setattr(worker.NemoClient, '__call__', fail)
    client = worker.NemoClient(tmp_path / 'ledger.sqlite3', 1)
    with pytest.raises(TimeoutError):
        client.for_version('version', 'hash', 'prompt')
    with pytest.raises(ValueError, match='provider_request_already_attempted'):
        client.for_version('version', 'hash', 'prompt')
    assert len(calls) == 1
    client.db.close()


def test_fact_write_and_acknowledgement_rollback_together(tmp_path, monkeypatch):
    from backend.bootstrap import create_backend
    from tests.test_phase_c_personalized_jobs import _seed_catalog
    from scripts import process_profile_job_facts as facts_worker
    app = create_backend(tmp_path, storage_backend='sqlite', test_mode=True)
    _seed_catalog(app)
    store = app.repositories.personalized_jobs_store
    monkeypatch.setenv('DATABASE_BACKEND', 'sqlite')
    monkeypatch.setenv('SQLITE_DATABASE_PATH', str(store.db_path.resolve()))
    monkeypatch.delenv('TURSO_DATABASE_URL', raising=False)
    row = {'canonical_job_id': 'job-a', 'version_id': 'version-job-a', 'content_hash': 'hash-job-a',
           'title': 'Operations Analyst', 'description': 'SQL required', 'input_signature': '||', 'queued_revision': 1}
    with sqlite3.connect(store.db_path) as db:
        db.execute("CREATE TRIGGER fail_ack BEFORE DELETE ON profile_job_fact_queue BEGIN SELECT RAISE(ABORT,'ack failed'); END")
    with pytest.raises(sqlite3.IntegrityError, match='ack failed'):
        facts_worker.write_batch([row])
    with sqlite3.connect(store.db_path) as db:
        assert db.execute('SELECT COUNT(*) FROM profile_job_facts').fetchone()[0] == 0
        assert db.execute("SELECT revision FROM profile_job_fact_queue WHERE version_id='version-job-a'").fetchone()[0] == 1
        db.execute('DROP TRIGGER fail_ack')
    assert facts_worker.write_batch([row]) == 1
