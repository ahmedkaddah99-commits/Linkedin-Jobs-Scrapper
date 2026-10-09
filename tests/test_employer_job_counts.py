import sqlite3

import pytest

from backend.acquisition.employer_job_counts import (
    COUNT_COLUMNS, canonical_schema_statements, count_collection,
    counter_sync_statements, install_ledger,
)
from scripts.process_employer_job_counts import capture_source, purge_sources


def ledger():
    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    install_ledger(connection)
    return connection


def test_recollection_counts_but_delivery_retry_does_not():
    c = ledger()
    for receipt in ('first-collection', 'first-collection', 'fresh-collection'):
        with c:
            count_collection(c, company_id='employer', company_name='Employer', receipt=receipt, category='blue', sources=['linkedin'])
    row = c.execute('SELECT * FROM employer_counts').fetchone()
    assert row['blue_collar_count'] == row['linkedin_count'] == 2
    assert row['white_collar_count'] == row['employer_site_count'] == 0


def test_count_rolls_back_if_job_deletion_fails():
    c = ledger()
    with pytest.raises(sqlite3.OperationalError), c:
        count_collection(c, company_id='employer', company_name='', receipt='one', category='blue')
        c.execute('DELETE FROM missing_job_table')
    assert c.execute('SELECT COUNT(*) FROM employer_count_receipts').fetchone()[0] == 0


def test_absolute_sync_is_retry_safe_and_retains_employer_identity():
    c = ledger()
    c.execute('CREATE TABLE canonical_companies(company_id TEXT PRIMARY KEY,canonical_name TEXT,entity_kind TEXT,created_at TEXT,updated_at TEXT)')
    for sql, params in canonical_schema_statements(set()):
        c.execute(sql, params)
    for category, source in [('white','employer'), ('blue','linkedin'), ('not_a_job','employer'), ('insufficient_role_information','linkedin')]:
        count_collection(c, company_id='company', company_name='Company', receipt=category, category=category, sources=[source])
    rows = c.execute('SELECT * FROM employer_counts').fetchall()
    for _ in range(2):
        for sql, params in counter_sync_statements(rows, 'now'):
            c.execute(sql, params)
    result = c.execute('SELECT * FROM canonical_companies').fetchone()
    assert [result[col] for col in COUNT_COLUMNS] == [1, 1, 1, 1, 2, 2]
    assert result['canonical_name'] == 'Company'


def test_invalid_category_or_employer_cannot_leave_receipt():
    c = ledger()
    with pytest.raises(ValueError):
        count_collection(c, company_id='', company_name='', receipt='bad', category='blue')
    assert c.execute('SELECT COUNT(*) FROM employer_count_receipts').fetchone()[0] == 0


def test_blue_source_deleted_after_count_and_recollection_increases_total(tmp_path):
    import json
    c = ledger()
    c.execute("INSERT INTO employer_count_meta VALUES ('baseline_cutoff','2026-10-08T13:51:00+00:00')")
    c.execute('CREATE TABLE employer_live_title_decisions(title_hash TEXT PRIMARY KEY,category TEXT)')
    c.execute('CREATE TABLE employer_blue_source_queue(source TEXT,row_key TEXT,updated_at TEXT,company_id TEXT,PRIMARY KEY(source,row_key,updated_at))')
    c.commit()
    policy = tmp_path/'policy.json'
    policy.write_text(json.dumps({'decisions': {'cleaner': 'blue'}, 'rules': {}, 'terms': {}, 'max_words': 0}))
    path = tmp_path/'linkedin.db'
    producer = sqlite3.connect(path)
    producer.execute('CREATE TABLE jobs(linkedin_job_id TEXT PRIMARY KEY,job_json TEXT,updated_at TEXT)')
    payload = json.dumps({'canonical_company_id': 'company', 'job_title': 'Cleaner', 'linkedin_job_url': 'https://linkedin.com/jobs/view/123'})
    for stamp in ('2026-10-09T01:00:00+00:00', '2026-10-09T02:00:00+00:00'):
        with producer:
            producer.execute('INSERT INTO jobs VALUES (?,?,?)', ('123', payload, stamp))
        assert capture_source(c, path, 'linkedin', policy, 20) == 1
        assert capture_source(c, path, 'linkedin', policy, 20) == 0
        assert purge_sources(c, {'linkedin': path}, tmp_path, 20) == 1
        assert producer.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 0
    row = c.execute('SELECT * FROM employer_counts').fetchone()
    assert row['blue_collar_count'] == row['linkedin_count'] == 2
    assert len(list(tmp_path.glob('linkedin-*.jsonl.gz'))) == 2


def test_baseline_job_is_not_counted_again_on_first_source_pass(tmp_path):
    import json
    from backend.acquisition.employer_job_counts import digest
    c = ledger()
    c.execute("INSERT INTO employer_count_meta VALUES ('baseline_cutoff','2026-10-08T13:51:00+00:00')")
    c.execute('CREATE TABLE employer_live_title_decisions(title_hash TEXT PRIMARY KEY,category TEXT)')
    c.execute('CREATE TABLE employer_blue_source_queue(source TEXT,row_key TEXT,updated_at TEXT,company_id TEXT,PRIMARY KEY(source,row_key,updated_at))')
    c.execute('INSERT INTO employer_baseline_jobs VALUES (?,?)', (digest('company', 'https://job', 'cleaner'), 'blue'))
    count_collection(c, company_id='company', company_name='', receipt='baseline', category='blue', sources=['linkedin'])
    c.commit()
    path = tmp_path/'linkedin.db'
    producer = sqlite3.connect(path)
    producer.execute('CREATE TABLE jobs(linkedin_job_id TEXT PRIMARY KEY,job_json TEXT,updated_at TEXT)')
    with producer:
        producer.execute('INSERT INTO jobs VALUES (?,?,?)', ('123', json.dumps({'canonical_company_id': 'company', 'job_title': 'Cleaner', 'linkedin_job_url': 'https://job'}), '2026-10-07T01:00:00+00:00'))
    capture_source(c, path, 'linkedin', tmp_path/'unused-policy', 20)
    assert c.execute('SELECT blue_collar_count FROM employer_counts').fetchone()[0] == 1
