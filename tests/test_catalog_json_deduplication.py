import json
import sqlite3

import pytest

from scripts.deduplicate_catalog_json import deduplicate, install_guard, restore_guards, expression
from scripts.reduce_catalog_storage import native_transaction_script


def test_schema_formatting_comparison_preserves_literals_and_tokens():
    from scripts.deduplicate_catalog_json import same_sql
    assert same_sql("SELECT json_remove(x,'$.a', '$.b');", "select json_remove (x, '$.a', '$.b')")
    assert not same_sql("SELECT 'space matters'", "SELECT 'spacematters'")
    assert not same_sql('SELECT x IS NOT NULL', 'SELECT x ISNOT NULL')


class Database:
    def __init__(self):
        self.connection = sqlite3.connect(':memory:')

    def execute(self, sql, values=()):
        return self.connection.execute(sql, values)

    def atomic(self, statements):
        try:
            self.connection.executescript(native_transaction_script(statements))
        except BaseException:
            self.connection.rollback()
            raise

    def stmt(self, sql, values=(), **kwargs):
        return sql, values

    def request(self, request):
        sql, values = request['stmt']
        cursor = self.connection.execute(sql, values)
        self.connection.commit()
        return {'affected_row_count': cursor.rowcount}


def fixture():
    db = Database()
    for table, extra in [('job_source_observations', ', raw_payload_json TEXT'), ('job_posting_versions', '')]:
        db.connection.executescript(f"CREATE TABLE {table}(identity TEXT, content_hash TEXT, payload_json TEXT{extra}); CREATE TRIGGER trg_{table}_immutable_update BEFORE UPDATE ON {table} BEGIN SELECT RAISE (ABORT, '{table} are immutable'); END;")
    mapping = {'title': {'normalized_value': 'Engineer', 'evidence': ['retained']}}
    raw = {'title': 'Engineer', 'description_text': 'Build'}
    payload = {'title': 'Engineer', 'description_text': 'Build', 'description': 'Build',
               'description_html': '<b>distinct</b>', 'field_provenance': mapping,
               'unified_mapping': {'fields': mapping},
               'source_raw_payload': {'producer_record': raw, 'observation_contract': {'source_record': raw}, 'conflicting_salary': 123}}
    body = json.dumps(payload)
    db.execute('INSERT INTO job_source_observations VALUES(?,?,?,?)', ('id', 'hash', body, json.dumps(raw)))
    db.execute('INSERT INTO job_posting_versions VALUES(?,?,?)', ('version', 'hash', body))
    db.connection.commit()
    return db


def test_full_cleanup_preserves_values_and_restores_immutability(tmp_path):
    db = fixture()
    original_guards = db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name").fetchall()
    result = deduplicate(db, checkpoint=tmp_path/'progress.json', database_identity='test', apply=True)
    assert all(item['updated'] == 1 and item['saved_bytes'] > 0 for item in result.values())
    identity, content_hash, text = db.execute('SELECT identity,content_hash,payload_json FROM job_source_observations').fetchone()
    payload = json.loads(text)
    assert (identity, content_hash) == ('id', 'hash')
    assert payload['description_text'] == 'Build' and payload['description_html'] == '<b>distinct</b>'
    assert 'description' not in payload and 'field_provenance' not in payload
    assert payload['unified_mapping']['fields']['title']['evidence'] == ['retained']
    assert payload['source_raw_payload']['conflicting_salary'] == 123
    assert 'source_record' not in payload['source_raw_payload']['observation_contract']
    assert db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name").fetchall() == original_guards
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE job_source_observations SET payload_json='{}'")


def test_temporary_guard_rejects_identity_changes_and_arbitrary_payloads(tmp_path):
    db = fixture()
    progress, state = {}, {}
    install_guard(db, 'job_source_observations', ('payload_json','raw_payload_json'), progress, tmp_path/'guard.json', state)
    for sql in ("UPDATE job_source_observations SET identity='different'", "UPDATE job_source_observations SET rowid=99", "UPDATE job_source_observations SET payload_json='{}'", "UPDATE job_source_observations SET content_hash='forged'"):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(sql)
        db.connection.rollback()
    db.execute('UPDATE job_source_observations SET payload_json=' + expression('payload_json'))
    db.connection.commit()
    restore_guards(db, progress)


def test_json_type_conflicts_are_preserved(tmp_path):
    db = fixture()
    db.connection.executescript('DROP TRIGGER trg_job_source_observations_immutable_update; DROP TRIGGER trg_job_posting_versions_immutable_update;')
    db.execute('UPDATE job_source_observations SET payload_json=?', (json.dumps({'description_text':1,'description':True}),))
    db.connection.commit()
    result = deduplicate(db, checkpoint=tmp_path/'progress.json', database_identity='test', apply=True)
    assert result['job_source_observations']['updated'] == 0
    assert json.loads(db.execute('SELECT payload_json FROM job_source_observations').fetchone()[0])['description'] is True


def test_completed_checkpoint_processes_new_insertions(tmp_path):
    db = fixture()
    checkpoint = tmp_path/'progress.json'
    deduplicate(db, checkpoint=checkpoint, database_identity='test', apply=True)
    body = json.dumps({'description_text':'new content', 'description':'new content'})
    db.execute('INSERT INTO job_source_observations VALUES(?,?,?,?)', ('new-id','new-hash',body,'{}'))
    db.connection.commit()
    result = deduplicate(db, checkpoint=checkpoint, database_identity='test', apply=True)
    assert result['job_source_observations']['cursor'] == 2
    assert result['job_source_observations']['updated'] == 2
    assert json.loads(db.execute("SELECT payload_json FROM job_source_observations WHERE identity='new-id'").fetchone()[0]) == {'description_text':'new content'}


def test_committed_write_with_lost_response_is_verified_and_counted_once(tmp_path):
    db = fixture()
    request = db.atomic
    def lost_response(value):
        request(value)
        if any(sql.startswith('UPDATE ') for sql, _ in value):
            raise TimeoutError('response lost after commit')
    db.atomic = lost_response
    checkpoint = tmp_path/'progress.json'
    first = deduplicate(db, checkpoint=checkpoint, database_identity='test', apply=True)
    assert all(item['updated'] == 1 and item['saved_bytes'] > 0 for item in first.values())
    second = deduplicate(db, checkpoint=checkpoint, database_identity='test', apply=True)
    assert first == second
