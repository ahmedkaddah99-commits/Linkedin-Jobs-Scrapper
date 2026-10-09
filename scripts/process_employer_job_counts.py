"""Bounded automatic counting; delete blue source rows only after remote sync.

Run under the same publisher/source locks as acquisition. The durable ledger
must not live in an ephemeral release or publisher snapshot directory.
"""
import argparse
import gzip
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.acquisition.employer_job_counts import (
    CATEGORIES, COUNT_COLUMNS, canonical_schema_statements, count_collection,
    counter_sync_statements, digest, install_ledger,
)
from backend.acquisition.title_collar import classify_title, normalize
from backend.database.http_batch import execute_atomic_batch
from scripts.snapshot_title_collar_audit import query


def utc():
    return datetime.now(timezone.utc).isoformat()


def resolve_category(ledger, record, policy):
    company = record['company_id']
    identity = digest(company, record['url'], normalize(record['title']))
    baseline = ledger.execute('SELECT category FROM employer_baseline_jobs WHERE identity_hash=?', (identity,)).fetchone()
    if baseline:
        return baseline[0], True
    result = classify_title(record['title'], policy_path=policy)
    if result:
        return result, False
    cached = ledger.execute('SELECT category FROM employer_live_title_decisions WHERE title_hash=?', (digest(record['title']),)).fetchone()
    if cached:
        return cached[0], False
    key = os.environ.get('OPENROUTER_API_KEY')
    if not key:
        raise RuntimeError('New unresolved title needs Nemo classification; OPENROUTER_API_KEY is missing. Record retained and cursor not advanced.')
    from scripts.classify_unresolved_title_nemo import MODEL, PROMPT
    body = {'model': MODEL, 'messages': [{'role': 'user', 'content': PROMPT + json.dumps([{'id': 0, 'title': record['title']}])}],
            'temperature': 0, 'max_tokens': 500, 'response_format': {'type': 'json_object'}, 'provider': {'require_parameters': True}}
    request = Request('https://openrouter.ai/api/v1/chat/completions', data=json.dumps(body).encode(), headers={
        'Authorization': 'Bearer '+key, 'Content-Type': 'application/json'})
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get('model') != MODEL:
        raise RuntimeError('Unexpected classification model; record retained')
    results = json.loads(payload['choices'][0]['message']['content'])['results']
    if len(results) != 1 or results[0]['id'] != 0 or results[0]['category'] not in CATEGORIES:
        raise RuntimeError('Invalid Nemo classification; record retained')
    result = results[0]['category']
    ledger.execute('INSERT OR IGNORE INTO employer_live_title_decisions VALUES (?,?)', (digest(record['title']), result))
    return result, False


def capture_source(ledger, path, source, policy, limit):
    field, key = ('job_json', 'linkedin_job_id') if source == 'linkedin' else ('payload_json', 'source_key')
    connection = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    cursor = ledger.execute('SELECT updated_at,row_key FROM employer_source_cursors WHERE source=?', (source,)).fetchone()
    stamp, last_key = tuple(cursor) if cursor else ('', '')
    cutoff = ledger.execute("SELECT value FROM employer_count_meta WHERE key='baseline_cutoff'").fetchone()[0]
    records = connection.execute(f"SELECT {key} AS row_key,updated_at,json_extract({field},'$.canonical_company_id') AS company_id,json_extract({field},'$.canonical_CompanyID') AS legacy_company_id,COALESCE(json_extract({field},'$.job_title'),json_extract({field},'$.title'),'') AS title,COALESCE(json_extract({field},'$.source_job_url'),json_extract({field},'$.linkedin_job_url'),'') AS url FROM jobs WHERE updated_at>? OR (updated_at=? AND {key}>?) ORDER BY updated_at,{key} LIMIT ?", (stamp, stamp, last_key, limit)).fetchall()
    completed = 0
    for raw in records:
        record = dict(raw)
        record['company_id'] = record['company_id'] or record.pop('legacy_company_id')
        if not record['company_id']:
            # Unknown ownership must not be guessed or attributed to another employer.
            raise RuntimeError(f'{source}: source row has no canonical employer ID; row retained')
        with ledger:
            category, baseline = resolve_category(ledger, record, policy)
            receipt = digest(source, record['company_id'], record['row_key'], record['updated_at'])
            old_baseline = baseline and datetime.fromisoformat(record['updated_at'].replace('Z', '+00:00')) <= datetime.fromisoformat(cutoff)
            if old_baseline:
                ledger.execute('INSERT OR IGNORE INTO employer_count_receipts VALUES (?)', (receipt,))
            else:
                count_collection(ledger, company_id=record['company_id'], company_name='', receipt=receipt, category=category, sources=[source])
            if category == 'blue':
                ledger.execute('INSERT OR IGNORE INTO employer_blue_source_queue VALUES (?,?,?,?)',
                    (source, record['row_key'], record['updated_at'], record['company_id']))
            ledger.execute('INSERT OR REPLACE INTO employer_source_cursors VALUES (?,?,?)', (source, record['updated_at'], record['row_key']))
        completed += 1
    connection.close()
    return completed


def sync_counts(ledger):
    columns = {r['name'] for r in query('PRAGMA table_info(canonical_companies)')}
    statements = canonical_schema_statements(columns)
    if statements:
        execute_atomic_batch(statements, timeout=20)
    if not query("SELECT name FROM sqlite_master WHERE type='table' AND name='employer_count_purge_guard'"):
        execute_atomic_batch([('CREATE TABLE IF NOT EXISTS employer_count_purge_guard(guard_id TEXT PRIMARY KEY,safe INTEGER NOT NULL)', ()),
                              ("INSERT OR IGNORE INTO employer_count_purge_guard VALUES ('blue_cleanup',1)", ())], timeout=20)
    cursor = ledger.execute('SELECT c.* FROM employer_counts c LEFT JOIN employer_synced_counts s ON s.company_id=c.company_id WHERE s.signature IS NULL OR s.signature!=('+"||':'||".join('c.'+col for col in COUNT_COLUMNS)+') ORDER BY c.company_id')
    total = 0
    while rows := cursor.fetchmany(100):
        execute_atomic_batch(counter_sync_statements(rows, utc()), timeout=20)
        # Verify actual shared values before authorizing deletion, including lost-response cases.
        expected = {r['company_id']: [r[c] for c in COUNT_COLUMNS] for r in rows}
        actual = query('SELECT company_id,'+','.join(COUNT_COLUMNS)+' FROM canonical_companies WHERE company_id IN (SELECT value FROM json_each(?))', [json.dumps(list(expected))])
        if {r['company_id']: [r[c] for c in COUNT_COLUMNS] for r in actual} != expected:
            raise RuntimeError('Employer counter read-back mismatch; deletion is blocked')
        with ledger:
            ledger.executemany('INSERT OR REPLACE INTO employer_synced_counts VALUES (?,?)',
                [(r['company_id'], ':'.join(str(r[c]) for c in COUNT_COLUMNS)) for r in rows])
        total += len(rows)
    return total


def catalog_reference_cte():
    references = []
    for table in ('reviews', 'application_packages', 'run_jobs', 'generation_provenance'):
        references.append(f'SELECT job_id AS value FROM {table}')
    for table in ('reviews', 'application_packages', 'run_jobs', 'run_job_sets', 'run_blobs'):
        references.append(f"SELECT atom AS value FROM {table},json_tree(CASE WHEN json_valid({table}.payload_json) THEN {table}.payload_json ELSE '{{}}' END) WHERE json_tree.type='text'")
    for table in ('personalized_job_dispositions', 'personalized_job_events', 'personalized_job_evaluations', 'job_intelligence_cache'):
        references.append(f'SELECT canonical_job_id AS value FROM {table}')
    return 'WITH refs AS ('+' UNION '.join(references)+') '


def catalog_protection_predicate():
    return "(j.canonical_job_id IN (SELECT value FROM refs) OR (j.canonical_url<>'' AND j.canonical_url IN (SELECT value FROM refs)) OR EXISTS(SELECT 1 FROM canonical_job_external_ids e WHERE e.canonical_job_id=j.canonical_job_id AND e.external_job_id IN (SELECT value FROM refs)) OR EXISTS(SELECT 1 FROM canonical_job_url_aliases a WHERE a.canonical_job_id=j.canonical_job_id AND a.url IN (SELECT value FROM refs)))"


def capture_catalog(ledger, policy, limit):
    cursor = ledger.execute("SELECT value FROM employer_count_meta WHERE key='catalog_cursor'").fetchone()
    rows = query("SELECT canonical_job_id,current_version_id,company_id,title,canonical_url AS url FROM canonical_jobs WHERE canonical_job_id>? ORDER BY canonical_job_id LIMIT ?", [cursor[0] if cursor else '', limit])
    for row in rows:
        with ledger:
            baseline = ledger.execute('SELECT category FROM employer_baseline_catalog WHERE job_id=? AND version_id=?', (row['canonical_job_id'], row['current_version_id'])).fetchone()
            category = baseline[0] if baseline else resolve_category(ledger, row, policy)[0]
            if category == 'blue':
                ledger.execute('INSERT OR REPLACE INTO employer_blue_catalog_queue VALUES (?,?,?)', (row['canonical_job_id'], row['current_version_id'], row['company_id']))
            ledger.execute("INSERT OR REPLACE INTO employer_count_meta VALUES ('catalog_cursor',?)", (row['canonical_job_id'],))
    if not rows:
        with ledger:
            ledger.execute("INSERT OR REPLACE INTO employer_count_meta VALUES ('catalog_cursor','')")
    return len(rows)


def purge_catalog(ledger, backup_root, limit):
    """Keep referenced jobs; close/unpublish all blue jobs; back up before purge."""
    from scripts.cleanup_blue_employer_catalog import conditions
    from uuid import uuid4
    pending = ledger.execute('SELECT * FROM employer_blue_catalog_queue LIMIT ?', [min(limit, 50)]).fetchall()
    if not pending:
        return {'deleted': 0, 'protected': 0}
    selected = json.dumps([r['job_id'] for r in pending])
    # Version comparison avoids removing a job whose title changed since capture.
    versions = json.dumps([dict(r) for r in pending])
    current = query("SELECT j.canonical_job_id FROM canonical_jobs j JOIN json_each(?) p ON j.canonical_job_id=json_extract(p.value,'$.job_id') AND j.current_version_id=json_extract(p.value,'$.version_id')", [versions])
    ids = [r['canonical_job_id'] for r in current]
    selected = json.dumps(ids)
    protected = {r['canonical_job_id'] for r in query(catalog_reference_cte()+"SELECT j.canonical_job_id FROM canonical_jobs j WHERE j.canonical_job_id IN (SELECT value FROM json_each(?)) AND "+catalog_protection_predicate(), [selected])}
    deleting = json.dumps([job for job in ids if job not in protected])
    predicates = conditions(deleting)
    # Keep historical publication snapshots and append-only audit identifiers.
    backup = backup_root/f'catalog-{time.time_ns()}.jsonl.gz'
    with gzip.open(backup, 'wt', encoding='utf-8') as stream:
        for table, (condition, params) in predicates.items():
            keys = query(f'SELECT rowid AS rid FROM {table} WHERE {condition}', params)
            for start in range(0, len(keys), 25):
                for row in query(f'SELECT * FROM {table} WHERE rowid IN (SELECT value FROM json_each(?))', [json.dumps([r['rid'] for r in keys[start:start+25]])]):
                    stream.write(json.dumps({'table': table, 'row': row}, ensure_ascii=False)+'\n')
    with gzip.open(backup, 'rt', encoding='utf-8') as stream:
        for line in stream:
            json.loads(line)
    head = query('SELECT publication_id FROM acquisition_publication_head WHERE head_id=1')[0]['publication_id']
    new = 'blue_job_cleanup_'+uuid4().hex
    now = utc()
    statements = [
        ("UPDATE acquisition_publication_head SET publication_id=CASE WHEN publication_id=? THEN publication_id ELSE NULL END WHERE head_id=1", (head,)),
        ("UPDATE employer_count_purge_guard SET safe=CASE WHEN EXISTS(SELECT 1 FROM canonical_jobs j JOIN json_each(?) p ON j.canonical_job_id=json_extract(p.value,'$.job_id') WHERE j.current_version_id<>json_extract(p.value,'$.version_id')) THEN NULL ELSE 1 END WHERE guard_id='blue_cleanup'", (versions,)),
        (catalog_reference_cte()+"UPDATE employer_count_purge_guard SET safe=CASE WHEN EXISTS(SELECT 1 FROM canonical_jobs j WHERE j.canonical_job_id IN (SELECT value FROM json_each(?)) AND "+catalog_protection_predicate()+") THEN NULL ELSE 1 END WHERE guard_id='blue_cleanup'", (deleting,)),
        ("INSERT INTO acquisition_publications(publication_id,cycle_id,status,snapshot_json,published_at,valid_until,previous_publication_id,origin,created_by,policy_version) SELECT ?,?,'valid',COALESCE((SELECT json_group_array(json(value)) FROM json_each(p.snapshot_json) WHERE json_extract(value,'$.canonical_job_id') NOT IN (SELECT value FROM json_each(?))),'[]'),?,'',publication_id,'system','blue_job_cleanup',policy_version FROM acquisition_publications p WHERE publication_id=?", (new, new, selected, now, head)),
        ("INSERT INTO acquisition_publication_jobs SELECT ?,canonical_job_id FROM acquisition_publication_jobs WHERE publication_id=? AND canonical_job_id NOT IN (SELECT value FROM json_each(?))", (new, head, selected)),
        ("UPDATE acquisition_publication_head SET publication_id=?,updated_at=? WHERE head_id=1", (new, now)),
        ("UPDATE canonical_jobs SET lifecycle_state='closed' WHERE canonical_job_id IN (SELECT value FROM json_each(?))", (json.dumps(sorted(protected)),)),
    ]
    guards = {r['name']: r['sql'] for r in query("SELECT name,sql FROM sqlite_master WHERE type='trigger'")}
    for table, (condition, params) in predicates.items():
        guard = f'trg_{table}_immutable_delete'
        if guard in guards:
            statements.append((f'DROP TRIGGER {guard}', ()))
        statements.append((f'DELETE FROM {table} WHERE {condition}', params))
        if guard in guards:
            statements.append((guards[guard], ()))
    execute_atomic_batch(statements, timeout=60)
    remaining = query('SELECT canonical_job_id FROM canonical_jobs WHERE canonical_job_id IN (SELECT value FROM json_each(?))', [selected])
    if {r['canonical_job_id'] for r in remaining} != protected:
        raise RuntimeError('Catalog purge verification failed')
    with ledger:
        ledger.executemany('DELETE FROM employer_blue_catalog_queue WHERE job_id=?', [(r['job_id'],) for r in pending])
    return {'deleted': len(ids)-len(protected), 'protected': len(protected)}


def purge_sources(ledger, paths, backup_root, limit):
    deleted = 0
    for source, path in paths.items():
        field, key = ('job_json', 'linkedin_job_id') if source == 'linkedin' else ('payload_json', 'source_key')
        connection = sqlite3.connect(path, timeout=10)
        connection.row_factory = sqlite3.Row
        pending = ledger.execute('SELECT row_key,updated_at,company_id FROM employer_blue_source_queue WHERE source=? LIMIT ?', (source, limit)).fetchall()
        if not pending:
            connection.close()
            continue
        backup = backup_root / f'{source}-{time.time_ns()}.jsonl.gz'
        removed = []
        # Read, back up, close and verify the gzip before issuing DELETE.
        # Source/publisher locks prevent payload changes during this interval.
        with gzip.open(backup, 'wt', encoding='utf-8') as stream:
            for queued in pending:
                row = connection.execute(f'SELECT * FROM jobs WHERE {key}=? AND updated_at=?', tuple(queued)[:2]).fetchone()
                if row:
                    # Record immutable evidence before removal. Every source row
                    # must still match the exact version which was counted.
                    stream.write(json.dumps({'table': 'jobs', 'row': dict(row)}, ensure_ascii=False)+'\n')
                removed.append(tuple(queued)[:2])
        # Verify gzip integrity before acknowledging the queue. A failed delete
        # leaves its queue item for retry; counters never decrement.
        with gzip.open(backup, 'rt', encoding='utf-8') as stream:
            for line in stream:
                json.loads(line)
        with connection:
            for row_key, stamp in removed:
                deleted += connection.execute(f'DELETE FROM jobs WHERE {key}=? AND updated_at=?', (row_key, stamp)).rowcount
        with ledger:
            ledger.executemany('DELETE FROM employer_blue_source_queue WHERE source=? AND row_key=? AND updated_at=?', [(source, *r) for r in removed])
        connection.close()
    return deleted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--linkedin-state', type=Path, required=True)
    parser.add_argument('--employer-state', type=Path, required=True)
    parser.add_argument('--max-rows', type=int, default=500)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.max_rows <= 0:
        parser.error('--max-rows must be positive')
    if sys.version_info[:3] != (3, 12, 7):
        raise RuntimeError('Python 3.12.7 required')
    if not args.ledger.exists():
        raise RuntimeError('Existing classification baseline is required; refusing an empty ledger')
    from dotenv import load_dotenv
    load_dotenv(ROOT/'user_config/.env')
    paths = {'linkedin': args.linkedin_state, 'employer': args.employer_state}
    ledger = sqlite3.connect(args.ledger)
    ledger.row_factory = sqlite3.Row
    install_ledger(ledger)
    ledger.execute('CREATE TABLE IF NOT EXISTS employer_live_title_decisions(title_hash TEXT PRIMARY KEY,category TEXT NOT NULL)')
    ledger.execute('CREATE TABLE IF NOT EXISTS employer_blue_source_queue(source TEXT,row_key TEXT,updated_at TEXT,company_id TEXT,PRIMARY KEY(source,row_key,updated_at))')
    ledger.execute('CREATE TABLE IF NOT EXISTS employer_blue_catalog_queue(job_id TEXT PRIMARY KEY,version_id TEXT,company_id TEXT)')
    ledger.execute('CREATE TABLE IF NOT EXISTS employer_synced_counts(company_id TEXT PRIMARY KEY,signature TEXT NOT NULL)')
    ledger.commit()
    result = {'started_at': utc(), 'status': 'counting', 'paths': {s: str(p.resolve(strict=True)) for s,p in paths.items()}}
    try:
        result['processed'] = {s: capture_source(ledger, p, s, args.policy, args.max_rows) for s,p in paths.items()}
        if args.apply:
            result['synced_employers'] = sync_counts(ledger)
            backups = args.ledger.parent/'deleted-source-backups'
            backups.mkdir(exist_ok=True)
            result['catalog_rows_checked'] = capture_catalog(ledger, args.policy, args.max_rows)
            result['catalog_purge'] = purge_catalog(ledger, backups, args.max_rows)
            result['source_jobs_deleted'] = purge_sources(ledger, paths, backups, args.max_rows)
        result['status'] = 'source_pass_complete' if args.apply else 'counted_locally_no_deletion'
    except Exception as exc:
        result.update(status='blocked_no_further_deletion', error_type=type(exc).__name__)
        # Do not expose provider responses, URLs, job payloads, or credentials.
        print(json.dumps(result), flush=True)
        (args.ledger.parent/'latest-worker-status.json').write_text(json.dumps(result, indent=2))
        raise SystemExit(1) from None
    result['finished_at'] = utc()
    (args.ledger.parent/'latest-worker-status.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
