import json
import sqlite3
import pytest
from backend.storage.local import LocalObjectStorage
from scripts.reduce_catalog_storage import reduce_catalog_storage, apply_rows


def fixture_database(tmp_path):
    connection = sqlite3.connect(tmp_path / 'catalog.db')
    connection.executescript('''CREATE TABLE job_source_observations(observation_id TEXT, content_hash TEXT, payload_json TEXT, raw_payload_json TEXT, current_id TEXT); CREATE TABLE job_posting_versions(version_id TEXT, content_hash TEXT, payload_json TEXT, description_text TEXT); CREATE TRIGGER frozen BEFORE UPDATE ON job_source_observations BEGIN SELECT RAISE(ABORT,'immutable'); END; CREATE TRIGGER versions_frozen BEFORE UPDATE ON job_posting_versions BEGIN SELECT RAISE(ABORT,'immutable'); END;''')
    payload = {'description_text': 'canonical', 'description': 'canonical', 'description_html': '<b>conflicting</b>', 'source_raw_payload': {'html': 'page ' * 1000}, 'unified_mapping': {'fields': {'title': {'normalized_value': 'engineer', 'raw_value': 'original'}}}}
    for index in range(3):
        connection.execute('INSERT INTO job_source_observations VALUES(?,?,?,?,?)', (str(index), 'hash', json.dumps(payload), json.dumps(payload['source_raw_payload']), 'head'))
        connection.execute('INSERT INTO job_posting_versions VALUES(?,?,?,?)', (str(index), 'hash', json.dumps(payload), 'canonical'))
    connection.commit()
    return connection


def test_dry_run_preservation_and_resumable_backfill(tmp_path):
    connection = fixture_database(tmp_path)
    checkpoint = tmp_path / 'checkpoint.json'
    storage = LocalObjectStorage(tmp_path / 'objects')
    before = connection.execute('SELECT rowid,* FROM job_source_observations').fetchall()
    original_triggers = connection.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name").fetchall()
    result = reduce_catalog_storage(connection, database_identity='local', checkpoint=checkpoint, storage=storage)
    assert result['scanned'] == 6 and not checkpoint.exists()
    assert connection.execute('SELECT rowid,* FROM job_source_observations').fetchall() == before
    result = reduce_catalog_storage(connection, database_identity='local', checkpoint=checkpoint, storage=storage, apply=True, batch_size=1)
    assert result['updated'] == 6
    assert connection.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name").fetchall() == original_triggers
    after = connection.execute('SELECT rowid,* FROM job_source_observations').fetchall()
    for previous, current in zip(before, after):
        assert previous[:3] == current[:3] and previous[-1] == current[-1]
        payload = json.loads(current[3])
        assert payload['description_html'] == '<b>conflicting</b>'
        assert json.loads(current[4])['storage_evidence_key'] == payload['storage_evidence_key']
    assert connection.execute('SELECT description_text FROM job_posting_versions').fetchall() == [('canonical',)] * 3
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE job_source_observations SET content_hash='changed'")
    assert reduce_catalog_storage(connection, database_identity='local', checkpoint=checkpoint, storage=storage, apply=True)['scanned'] == 0
    with pytest.raises(ValueError):
        reduce_catalog_storage(connection, database_identity='other', checkpoint=checkpoint)


def test_one_update_statement_preserves_each_rows_optimistic_guard(tmp_path, monkeypatch):
    import scripts.reduce_catalog_storage as module
    connection = fixture_database(tmp_path)
    rows = connection.execute('SELECT rowid,payload_json,raw_payload_json FROM job_source_observations ORDER BY rowid').fetchall()
    values = [(json.dumps({'row': row[0]}), json.dumps({'raw': row[0]})) for row in rows]
    original = module._atomic
    statements = []
    def tracked(db, batch):
        statements.extend(batch)
        original(db, batch)
    monkeypatch.setattr(module, '_atomic', tracked)
    apply_rows(connection, 'job_source_observations', rows, ('payload_json','raw_payload_json'), values)
    assert len([sql for sql, _ in statements if sql.startswith('UPDATE ')]) == 1
    after = connection.execute('SELECT rowid,payload_json,raw_payload_json FROM job_source_observations ORDER BY rowid').fetchall()
    assert [tuple(row[1:]) for row in after] == values
    with pytest.raises(RuntimeError, match='optimistic'):
        apply_rows(connection, 'job_source_observations', rows, ('payload_json','raw_payload_json'), [('{"stale":true}','{}')] * 3)
    assert connection.execute('SELECT rowid,payload_json,raw_payload_json FROM job_source_observations ORDER BY rowid').fetchall() == after


def test_transaction_failure_restores_guards_and_payload(tmp_path):
    connection = fixture_database(tmp_path)
    rows = connection.execute('SELECT rowid,payload_json,raw_payload_json FROM job_source_observations LIMIT 1').fetchall()
    # A post-trigger restoration failure rolls the entire DDL/update transaction back.
    class FailingConnection:
        def execute(self, sql, args=()):
            if sql.startswith('CREATE TRIGGER frozen'):
                raise RuntimeError('injected')
            return connection.execute(sql, args)
        def commit(self): connection.commit()
        def rollback(self): connection.rollback()
    with pytest.raises(RuntimeError):
        apply_rows(FailingConnection(), 'job_source_observations', rows, ('payload_json','raw_payload_json'), [('{}','{}')])
    assert connection.execute('SELECT rowid,payload_json,raw_payload_json FROM job_source_observations LIMIT 1').fetchall() == rows
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE job_source_observations SET content_hash='changed'")


def test_ambiguous_committed_batch_retries_without_blind_cursor_advance(tmp_path, monkeypatch):
    import scripts.reduce_catalog_storage as module
    connection = fixture_database(tmp_path)
    storage = LocalObjectStorage(tmp_path / 'objects')
    checkpoint = tmp_path / 'resume.json'
    original = module._atomic
    def committed_timeout(connection, statements):
        original(connection, statements)
        raise TimeoutError('ambiguous response')
    monkeypatch.setattr(module, '_atomic', committed_timeout)
    with pytest.raises(TimeoutError):
        module.reduce_catalog_storage(connection, database_identity='local', checkpoint=checkpoint, storage=storage, apply=True, batch_size=1)
    assert json.loads(checkpoint.read_text())['job_source_observations']['cursor'] == 0
    assert json.loads(connection.execute('SELECT payload_json FROM job_source_observations WHERE rowid=1').fetchone()[0])['catalog_storage_version'] == 1
    monkeypatch.setattr(module, '_atomic', original)
    result = module.reduce_catalog_storage(connection, database_identity='local', checkpoint=checkpoint, storage=storage, apply=True, batch_size=1)
    assert result['scanned'] == 6 and result['updated'] == 5
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE job_source_observations SET content_hash='changed'")


def test_derived_audit_archives_exact_body_preserves_metadata_and_paid_fields(tmp_path, capsys):
    from backend.acquisition.storage_evidence import restore_catalog_evidence
    connection = fixture_database(tmp_path)
    connection.executescript('''CREATE TABLE acquisition_rule_outputs(output_id TEXT, rule_version TEXT, stage_name TEXT, semantic_hash TEXT, output_json TEXT, created_at TEXT); CREATE TABLE acquisition_version_quality(version_id TEXT, stable_content_hash TEXT, redundant INTEGER, report_json TEXT, calculated_at TEXT); CREATE TABLE job_description_intelligence(version_id TEXT, original_json TEXT, summary_json TEXT, structured_json TEXT, paid_cost REAL);''')
    mapping = {'rule_version': 'v1', 'observed_at': 'today', 'fields': {'title': {'normalized_value': 'engineer', 'raw_value': 'raw-secret-body', 'evidence': {'html': 'page ' * 1000}}}}
    quality = {'warnings': ['unknown'], 'application': {'resolved_url': 'https://apply.example'}, 'normalized_metadata': {'large': 'raw-secret-body' * 1000}, 'completeness': {'schema_version': 'v1', 'overall': {'present': 1, 'total': 2}, 'categories': {'job': {'present': 1, 'total': 2, 'rules': ['detail'] * 1000}}, 'all_rules': ['detail'] * 1000}}
    connection.execute('INSERT INTO acquisition_rule_outputs VALUES(?,?,?,?,?,?)', ('out', 'v1', 'normalization', 'semantic-hash', json.dumps(mapping), 'date'))
    connection.execute('INSERT INTO acquisition_version_quality VALUES(?,?,?,?,?)', ('version', 'semantic-hash', 0, json.dumps(quality), 'date'))
    connection.execute('INSERT INTO job_description_intelligence VALUES(?,?,?,?,?)', ('version', json.dumps({'original': 'posting'}), '{"summary":"paid"}', '{"structured":"paid"}', 4.2))
    connection.commit()
    paid_before = connection.execute('SELECT rowid,* FROM job_description_intelligence').fetchall()
    storage = LocalObjectStorage(tmp_path / 'objects')
    checkpoint = tmp_path / 'state.json'
    result = reduce_catalog_storage(connection, database_identity='local', checkpoint=checkpoint, storage=storage, apply=True)
    output = connection.execute('SELECT rowid,* FROM acquisition_rule_outputs').fetchone()
    assert output[:5] == (1, 'out', 'v1', 'normalization', 'semantic-hash') and output[-1] == 'date'
    compact = json.loads(output[5])
    assert compact['fields']['title']['normalized_value'] == 'engineer'
    assert 'raw_value' not in compact['fields']['title']
    assert restore_catalog_evidence(compact, storage)['raw_payload'] == mapping
    report_row = connection.execute('SELECT rowid,* FROM acquisition_version_quality').fetchone()
    assert report_row[:4] == (1, 'version', 'semantic-hash', 0) and report_row[-1] == 'date'
    report = json.loads(report_row[4])
    assert report['warnings'] == quality['warnings'] and report['application'] == quality['application']
    assert report['completeness']['overall'] == quality['completeness']['overall']
    assert 'normalized_metadata' not in report
    assert restore_catalog_evidence(report, storage)['raw_payload'] == quality
    assert paid_before == connection.execute('SELECT rowid,* FROM job_description_intelligence').fetchall()
    assert result['job_description_intelligence']['status'] == 'optional_equal_description_aliases_only'
    state = json.loads(checkpoint.read_text())
    assert state['acquisition_version_quality']['updated'] == 1
    assert state['acquisition_version_quality']['saved_bytes'] > 0
    assert 'raw-secret-body' not in capsys.readouterr().out


def test_batch_verifies_all_rows_once_and_rejects_stale_original(tmp_path):
    connection = fixture_database(tmp_path)
    rows = connection.execute('SELECT rowid,payload_json,raw_payload_json FROM job_source_observations ORDER BY rowid').fetchall()
    statements = []
    connection.set_trace_callback(statements.append)
    prepared = [('{}', '{}')] * 3
    apply_rows(connection, 'job_source_observations', rows, ('payload_json', 'raw_payload_json'), prepared)
    reads = [sql for sql in statements if sql.startswith('SELECT rowid,payload_json,raw_payload_json FROM job_source_observations WHERE rowid IN')]
    assert len(reads) == 1 and '(1,2,3)' in reads[0]
    with pytest.raises(RuntimeError, match='optimistic'):
        apply_rows(connection, 'job_source_observations', rows, ('payload_json', 'raw_payload_json'), [('{"new":1}', '{}')] * 3)
    assert connection.execute('SELECT payload_json FROM job_source_observations').fetchall() == [('{}',)] * 3


def test_bounded_payload_pages(tmp_path, monkeypatch):
    import scripts.reduce_catalog_storage as module
    connection = fixture_database(tmp_path)
    storage = LocalObjectStorage(tmp_path / 'objects')
    monkeypatch.setattr(module, 'MAX_BATCH_BODY_BYTES', 12000)
    result = module.reduce_catalog_storage(connection, database_identity='local', checkpoint=tmp_path/'bounded.json', storage=storage, apply=True, archive_workers=8)
    assert result['updated'] == 6


def test_original_alias_compaction_reads_identical_posting_without_cold_downloads(tmp_path, monkeypatch):
    from backend.repositories.sqlite_personalized_jobs import SqlitePersonalizedJobsStore
    import backend.acquisition.storage_evidence as evidence
    connection = sqlite3.connect(tmp_path / 'intelligence.db')
    connection.row_factory = sqlite3.Row
    connection.executescript('''CREATE TABLE job_posting_versions(version_id TEXT, description TEXT); CREATE TABLE job_description_intelligence(version_id TEXT, canonical_job_id TEXT, content_hash TEXT, summary_json TEXT, structured_json TEXT, original_json TEXT, provider TEXT, model TEXT, prompt_version TEXT, generated_at TEXT, created_at TEXT, updated_at TEXT);''')
    description = 'Employer original language ' * 1000
    original = {'description': description, 'description_text': description, 'description_raw': '<b>distinct raw language</b>', 'description_html': '<p>distinct markup</p>', 'description_decoding': {'repaired': True}, 'preserved': True}
    connection.execute('INSERT INTO job_posting_versions VALUES(?,?)', ('version', description))
    connection.execute('INSERT INTO job_description_intelligence VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', ('version','job','hash','{"summary":"paid English translation"}','{"sections":"paid"}',json.dumps(original),'provider','model','prompt','generated','created','updated'))
    connection.commit()
    # Only the optional intelligence path; the synthetic version table has no payload column.
    import scripts.reduce_catalog_storage as module
    monkeypatch.setattr(module, 'TABLES', {})
    storage = LocalObjectStorage(tmp_path / 'objects')
    before = tuple(connection.execute('SELECT * FROM job_description_intelligence').fetchone())
    result = module.reduce_catalog_storage(connection, database_identity='local', checkpoint=tmp_path/'intel.json', storage=storage, apply=True, compact_intelligence=True)
    assert result['updated'] == 1 and result['saved_bytes'] > 0
    after = tuple(connection.execute('SELECT * FROM job_description_intelligence').fetchone())
    assert before[:5] == after[:5] and before[6:] == after[6:]
    compact = json.loads(after[5])
    assert evidence.restore_catalog_evidence(compact, storage)['raw_payload'] == original
    monkeypatch.setattr(evidence, 'restore_catalog_evidence', lambda *args, **kwargs: pytest.fail('normal reader must not hydrate cold evidence'))
    store = SqlitePersonalizedJobsStore.__new__(SqlitePersonalizedJobsStore)
    monkeypatch.setattr(store, '_connect', lambda: connection)
    single = store.get_description_intelligence('version', content_hash='hash')
    batch = store.list_cached_descriptions(['version'])['version']
    assert single['original_posting'] == original == batch['original_posting']
    assert single['summary'] == {'summary': 'paid English translation'}
