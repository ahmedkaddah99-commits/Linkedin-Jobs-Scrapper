import sqlite3
from pathlib import Path

import pytest

from backend.repositories.sqlite_acquisition import SqliteAcquisitionStore


def store_with_counter(monkeypatch):
    connection = sqlite3.connect(':memory:')
    connection.executescript('''
        CREATE TABLE company_identity_crosswalk (
          crosswalk_id TEXT, source_identity_key TEXT UNIQUE, winner_company_id TEXT,
          identity_type TEXT, provenance_json TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE canonical_companies (
          company_id TEXT PRIMARY KEY, canonical_name TEXT CHECK(canonical_name != 'bad'),
          entity_kind TEXT, provenance_url TEXT, created_at TEXT, updated_at TEXT);
    ''')
    calls = []

    class CountedConnection:
        def execute(self, sql, parameters=()):
            calls.append(sql)
            return connection.execute(sql, parameters)

    store = SqliteAcquisitionStore(Path('unused.sqlite3'), initialize=False)

    def transaction(callback):
        with connection:
            return callback(CountedConnection())

    monkeypatch.setattr(store, '_run_transaction', transaction)
    return store, connection, calls


def test_registry_reconciliation_uses_bounded_round_trips_and_preserves_existing(monkeypatch):
    store, connection, calls = store_with_counter(monkeypatch)
    connection.execute("INSERT INTO canonical_companies VALUES ('c0','Existing','employer','old','before','before')")
    connection.commit()
    rows = [{'canonical_CompanyID': f'c{i}', 'company_name': f'New {i}'} for i in range(225)]
    mapping = {f'linkedin:{i}': f'c{i}' for i in range(225)}
    result = store.apply_company_identity_crosswalk(mapping_by_identity=mapping, canonical_rows=rows)
    assert result['crosswalk_rows'] == 225
    assert connection.execute('SELECT COUNT(*) FROM canonical_companies').fetchone()[0] == 225
    assert connection.execute('SELECT canonical_name,provenance_url FROM canonical_companies WHERE company_id=?', ('c0',)).fetchone() == ('Existing', 'old')
    assert len(calls) <= 12, 'A full registry must not issue one remote query per identity/company'
    assert all(sql.count('?') <= 900 for sql in calls)
    connection.close()


def test_reconciliation_failure_rolls_back_all_batches(monkeypatch):
    store, connection, _ = store_with_counter(monkeypatch)
    rows = [{'canonical_CompanyID': f'c{i}', 'company_name': 'bad' if i == 150 else 'Good'} for i in range(225)]
    with pytest.raises(sqlite3.IntegrityError):
        store.apply_company_identity_crosswalk(mapping_by_identity={'linkedin:1': 'c1'}, canonical_rows=rows)
    assert connection.execute('SELECT COUNT(*) FROM company_identity_crosswalk').fetchone()[0] == 0
    assert connection.execute('SELECT COUNT(*) FROM canonical_companies').fetchone()[0] == 0
    connection.close()


def test_field_provenance_batches_preserve_first_evidence_and_parameter_limit():
    connection = sqlite3.connect(':memory:')
    connection.execute('''CREATE TABLE acquisition_field_provenance (
      provenance_id TEXT, entity_kind TEXT, entity_id TEXT, field_name TEXT,
      source_observation_id TEXT, raw_value_json TEXT, normalized_value_json TEXT,
      state TEXT, source TEXT, source_field TEXT, extraction_method TEXT,
      evidence_json TEXT, confidence REAL, observed_at TEXT, rule_version TEXT,
      selected INTEGER, selection_reason TEXT, created_at TEXT,
      UNIQUE(entity_kind,entity_id,field_name,source_observation_id,rule_version))''')
    calls = []

    class RemoteLikeConnection:
        def execute(self, sql, params=()):
            if 'INSERT OR IGNORE INTO acquisition_field_provenance' in sql:
                calls.append((sql, params))
                return connection.execute(sql, params)
        def executemany(self, sql, rows):
            # The live driver's executemany waits on each statement separately.
            for row in rows:
                self.execute(sql, row)

    mapping = {'fields': {f'field{i}': {'raw_value': i, 'normalized_value': i, 'state': 'present'} for i in range(225)}}
    def persist():
        SqliteAcquisitionStore._persist_unified_mapping(RemoteLikeConnection(),
            canonical_job_id='j1', company_id='c1', source_observation_id='o1',
            execution_id='e1', mapping=mapping, job={'company': 'Company'}, observed_at='2026-09-26T16:00:00Z')
    persist()
    assert len(calls) <= 6, 'Field evidence must use bounded remote writes, not one request per field'
    assert all(len(params) <= 900 for _, params in calls)
    assert connection.execute("SELECT COUNT(*) FROM acquisition_field_provenance WHERE entity_kind='job'").fetchone()[0] == 225
    mapping['fields']['field1']['raw_value'] = 'later'
    persist()
    assert connection.execute("SELECT raw_value_json FROM acquisition_field_provenance WHERE entity_kind='job' AND field_name='field1'").fetchone()[0] == '1'
    connection.close()
