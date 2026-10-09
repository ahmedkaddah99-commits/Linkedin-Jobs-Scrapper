"""Durable collection counters independent of retained vacancy records.

Only hashes and counters survive classification; no job descriptions are stored.
Callers own transactions so counting and producer deletion commit together.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

CATEGORIES = ('white', 'blue', 'not_a_job', 'insufficient_role_information')
COUNT_COLUMNS = (
    'white_collar_count', 'blue_collar_count', 'not_a_job_count',
    'insufficient_role_information_count', 'employer_site_count', 'linkedin_count',
)
CATEGORY_COLUMNS = dict(zip(CATEGORIES, COUNT_COLUMNS[:4], strict=True))
SOURCE_COLUMNS = {'employer': 'employer_site_count', 'linkedin': 'linkedin_count'}


def digest(*values):
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def install_ledger(connection: sqlite3.Connection):
    columns = ','.join(f'{c} INTEGER NOT NULL DEFAULT 0 CHECK({c}>=0)' for c in COUNT_COLUMNS)
    connection.execute(f'CREATE TABLE IF NOT EXISTS employer_counts(company_id TEXT PRIMARY KEY,company_name TEXT NOT NULL DEFAULT \'\',{columns})')
    connection.execute('CREATE TABLE IF NOT EXISTS employer_count_receipts(receipt_hash TEXT PRIMARY KEY)')
    connection.execute('CREATE TABLE IF NOT EXISTS employer_baseline_jobs(identity_hash TEXT PRIMARY KEY,category TEXT NOT NULL)')
    connection.execute('CREATE TABLE IF NOT EXISTS employer_count_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
    connection.execute('CREATE TABLE IF NOT EXISTS employer_source_cursors(source TEXT PRIMARY KEY,updated_at TEXT NOT NULL,row_key TEXT NOT NULL)')


def count_collection(connection, *, company_id, company_name, receipt, category, sources=()):
    """Exactly once per receipt; a later recollection uses a different receipt."""
    if not company_id:
        raise ValueError('Cannot attribute a collection without a canonical employer ID')
    if category not in CATEGORIES or not set(sources) <= SOURCE_COLUMNS.keys():
        raise ValueError('Unsupported classification or source')
    inserted = connection.execute('INSERT OR IGNORE INTO employer_count_receipts VALUES (?)', (receipt,)).rowcount
    if not inserted:
        return False
    connection.execute('INSERT OR IGNORE INTO employer_counts(company_id,company_name) VALUES (?,?)', (company_id, company_name))
    columns = [CATEGORY_COLUMNS[category], *(SOURCE_COLUMNS[s] for s in set(sources))]
    connection.execute('UPDATE employer_counts SET '+','.join(f'{c}={c}+1' for c in columns)+' WHERE company_id=?', (company_id,))
    return True


def canonical_schema_statements(existing_columns):
    """Used by migration and the bounded HTTP deployment preflight."""
    return [(f'ALTER TABLE canonical_companies ADD COLUMN {c} INTEGER NOT NULL DEFAULT 0 CHECK({c}>=0)', ())
            for c in COUNT_COLUMNS if c not in existing_columns]


def counter_sync_statements(rows, now):
    """One worker owns absolute totals; retries never increment them twice."""
    rows = list(rows)
    encoded = json.dumps([dict(r) for r in rows], ensure_ascii=False)
    assignments = ','.join(f"{c}=json_extract(value,'$.{c}')" for c in COUNT_COLUMNS)
    return [
        ("INSERT OR IGNORE INTO canonical_companies(company_id,canonical_name,entity_kind,created_at,updated_at) SELECT json_extract(value,'$.company_id'),json_extract(value,'$.company_name'),'employer',?,? FROM json_each(?)", (now, now, encoded)),
        (f"UPDATE canonical_companies SET {assignments} FROM json_each(?) WHERE company_id=json_extract(value,'$.company_id')", (encoded,)),
    ]
