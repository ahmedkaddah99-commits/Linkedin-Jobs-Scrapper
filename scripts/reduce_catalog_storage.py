"""Bounded operator backfill; no network work occurs on import or dry-run."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import dotenv_values
from backend.acquisition.storage_evidence import archive_catalog_evidence, restore_catalog_evidence
from backend.acquisition.storage_payload import compact_catalog_payload
from scripts.compact_job_storage import HttpMaintenanceConnection

TABLES = {'job_source_observations': ('payload_json', 'raw_payload_json'), 'job_posting_versions': ('payload_json',),
          'acquisition_rule_outputs': ('output_json',), 'acquisition_version_quality': ('report_json',)}
MARKER = 'catalog_storage_version'
MAX_BATCH_WIRE_BYTES = 8 * 1024 * 1024
MAX_BATCH_BODY_BYTES = 3 * 1024 * 1024


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _decode(value):
    result = json.loads(value or '{}')
    if not isinstance(result, dict):
        raise ValueError('Catalog payload must be a JSON object')
    return result


def _save(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(_json(state), encoding='utf-8')
    temporary.replace(path)


def prepare_row(row, columns, storage=None, *, table=None, version_description=None):
    original = tuple(row[1:])
    payload = _decode(original[0])
    if payload.get(MARKER) == 1 and payload.get('storage_evidence_key'):
        restore_catalog_evidence(payload, storage)
        if len(columns) == 2:
            pointer = _decode(original[1])
            if pointer.get('storage_evidence_key') != payload['storage_evidence_key']:
                raise ValueError('Observation evidence references disagree')
            restore_catalog_evidence(pointer, storage)
        return original
    if table == 'job_description_intelligence':
        aliases = [key for key in ('description', 'description_raw', 'description_html', 'description_text')
                   if isinstance(version_description, str) and key in payload and payload[key] == version_description]
        if not aliases:
            return original
        reference = archive_catalog_evidence(payload, payload, storage)
        compact = {key: value for key, value in payload.items() if key not in aliases}
        compact.update(reference)
        compact[MARKER] = 1
        compact['original_description_aliases'] = aliases
        return (_json(compact),)
    if table in ('acquisition_rule_outputs', 'acquisition_version_quality'):
        # Verbatim old JSON body is the raw envelope, including source timestamps.
        reference = archive_catalog_evidence(payload, payload, storage)
        if table == 'acquisition_rule_outputs':
            if isinstance(payload.get('fields'), dict):
                compact = compact_catalog_payload({'unified_mapping': payload})['unified_mapping']
            else:
                compact = dict(payload)
        else:
            compact = dict(payload)
            compact.pop('normalized_metadata', None)
            completeness = compact.get('completeness')
            if isinstance(completeness, dict):
                compact['completeness'] = {key: value for key, value in completeness.items()
                    if key in ('schema_version', 'report_only', 'overall', 'state', 'status', 'score', 'score_ratio', 'required_count', 'present_count', 'missing_count', 'warning_count', 'counts', 'rule_version')}
                categories = completeness.get('categories')
                if isinstance(categories, dict):
                    compact['completeness']['categories'] = {key: {name: value for name, value in category.items() if name != 'rules'}
                        for key, category in categories.items() if isinstance(category, dict)}
        compact.update(reference)
        compact[MARKER] = 1
        return (_json(compact),)
    raw = _decode(original[1]) if len(columns) == 2 else None
    if raw and raw.get('storage_evidence_key'):
        raw = restore_catalog_evidence(raw, storage)['raw_payload']
    if payload.get('storage_evidence_key'):
        restore_catalog_evidence(payload, storage)
        # Historical partial compaction must retain the archived full envelope.
        reference = {key: value for key, value in payload.items() if key.startswith('storage_evidence_')}
    else:
        reference = archive_catalog_evidence(payload, raw or None, storage)
    compact = compact_catalog_payload(payload, storage_evidence_key=reference['storage_evidence_key'])
    compact.update(reference)
    compact[MARKER] = 1
    values = [_json(compact)]
    if len(columns) == 2:
        values.append(_json({**reference, MARKER: 1}))
    return tuple(values)


def _atomic(connection, statements):
    if isinstance(connection, HttpMaintenanceConnection):
        connection.atomic(statements)
        return
    connection.execute('BEGIN IMMEDIATE')
    try:
        for sql, values in statements:
            connection.execute(sql, values)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def apply_rows(connection, table, rows, columns, prepared):
    # Restore all exact trigger definitions before the transaction commits.
    triggers = connection.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name=? ORDER BY name", (table,)).fetchall()
    if any('runr_storage_compaction_guard' in (sql or '') for _, sql in triggers):
        raise RuntimeError('Restore preexisting maintenance guards before catalog backfill')
    statements = [(f'DROP TRIGGER "{name.replace(chr(34), chr(34)*2)}"', ()) for name, _ in triggers]
    assignments = ','.join(column + '=?' for column in columns)
    guard = ' AND '.join(column + ' IS ?' for column in columns)
    for row, values in zip(rows, prepared):
        if tuple(row[1:]) != values:
            statements.append((f'UPDATE {table} SET {assignments} WHERE rowid=? AND {guard}', (*values, row[0], *row[1:])))
    statements += [(sql, ()) for _, sql in triggers]
    if isinstance(connection, HttpMaintenanceConnection):
        # Includes JSON escaping, original-value guards and compact replacements.
        encoded = json.dumps([connection.stmt(sql, values, want_rows=False) for sql, values in statements]).encode('utf-8')
        if len(encoded) > MAX_BATCH_WIRE_BYTES - 65536:
            raise RuntimeError('Catalog batch exceeds safe request limit; use a smaller batch')
    _atomic(connection, statements)
    # A stale writer or ambiguous response never authorizes advancing the cursor.
    ids = [row[0] for row in rows]
    placeholders = ','.join('?' for _ in ids)
    verified = connection.execute(f'SELECT rowid,{",".join(columns)} FROM {table} WHERE rowid IN ({placeholders}) ORDER BY rowid', ids).fetchall()
    actual_by_id = {row[0]: tuple(row[1:]) for row in verified}
    for row, values in zip(rows, prepared):
        if actual_by_id.get(row[0]) != values:
            raise RuntimeError('Catalog backfill optimistic update verification failed')


def reduce_catalog_storage(connection, *, database_identity, checkpoint, apply=False, batch_size=10, max_seconds=60, storage=None, archive_workers=4, compact_intelligence=False):
    if not 1 <= batch_size <= 100 or max_seconds <= 0 or not 1 <= archive_workers <= 8:
        raise ValueError('Batch size must be 1..100 and time budget positive')
    checkpoint = Path(checkpoint)
    state = json.loads(checkpoint.read_text(encoding='utf-8')) if checkpoint.exists() else {}
    identity = hashlib.sha256(database_identity.encode()).hexdigest()
    if state.get('database_identity', identity) != identity:
        raise ValueError('Checkpoint belongs to another database')
    state['database_identity'] = identity
    deadline = time.monotonic() + max_seconds
    totals = {'scanned': 0, 'updated': 0, 'saved_bytes': 0, 'applied': apply, 'tables': {}}
    tables = dict(TABLES)
    if compact_intelligence:
        tables['job_description_intelligence'] = ('original_json',)
    for table, columns in tables.items():
        if time.monotonic() >= deadline:
            break
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            continue
        progress = state.setdefault(table, {})
        for counter in ('scanned', 'updated', 'before_bytes', 'after_bytes', 'saved_bytes'):
            progress.setdefault(counter, 0)
        guards = connection.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name=? ORDER BY name", (table,)).fetchall()
        guards = [list(row) for row in guards]
        if any('runr_storage_compaction_guard' in (sql or '') for _, sql in guards):
            raise RuntimeError('Restore preexisting maintenance guards before catalog backfill')
        if 'original_guards' in progress and progress['original_guards'] != guards:
            raise RuntimeError('Catalog immutability guards changed since checkpoint')
        progress['original_guards'] = guards
        if 'upper' not in progress:
            progress.update(upper=connection.execute(f'SELECT COALESCE(MAX(rowid),0) FROM {table}').fetchone()[0], cursor=0)
        if apply:
            _save(checkpoint, state)
        while progress['cursor'] < progress['upper'] and time.monotonic() < deadline:
            # Account for JSON escaping in the HTTP response, not only SQL text bytes.
            sizes = '+'.join(f'COALESCE(length(CAST(json_quote({column}) AS BLOB)),0)' for column in columns)
            candidates = connection.execute(f'SELECT rowid,{sizes} FROM {table} WHERE rowid>? AND rowid<=? ORDER BY rowid LIMIT ?', (progress['cursor'], progress['upper'], batch_size)).fetchall()
            selected = []
            body_bytes = 0
            for rowid, size in candidates:
                if body_bytes + size > MAX_BATCH_BODY_BYTES:
                    if not selected:
                        raise RuntimeError('Catalog row exceeds bounded read limit; requires a separate large-object maintenance path')
                    break
                selected.append(rowid)
                body_bytes += size
            if selected:
                placeholders = ','.join('?' for _ in selected)
                rows = connection.execute(f'SELECT rowid,{",".join(columns)} FROM {table} WHERE rowid IN ({placeholders}) ORDER BY rowid', selected).fetchall()
                if [row[0] for row in rows] != selected:
                    raise RuntimeError('Catalog rows changed during bounded read')
            else:
                rows = []
            if not rows:
                progress['cursor'] = progress['upper']
                if apply:
                    _save(checkpoint, state)
                break
            totals['scanned'] += len(rows)
            before_bytes = sum(len((value or '').encode('utf-8')) for row in rows for value in row[1:])
            updated = 0
            after_bytes = before_bytes
            if apply:
                # Object writes and validation finish before the database transaction.
                descriptions = {}
                if table == 'job_description_intelligence':
                    descriptions = dict(connection.execute(f'SELECT i.rowid,v.description FROM job_description_intelligence i LEFT JOIN job_posting_versions v ON v.version_id=i.version_id WHERE i.rowid IN ({placeholders})', selected).fetchall())
                with ThreadPoolExecutor(max_workers=archive_workers) as executor:
                    prepared = list(executor.map(lambda row: prepare_row(row, columns, storage, table=table, version_description=descriptions.get(row[0])), rows))
                updated = sum(tuple(row[1:]) != values for row, values in zip(rows, prepared))
                apply_rows(connection, table, rows, columns, prepared)
                after_bytes = sum(len(value.encode('utf-8')) for values in prepared for value in values)
            else:
                for row in rows:
                    _decode(row[1])
            progress['cursor'] = rows[-1][0]
            progress['scanned'] += len(rows)
            progress['updated'] += updated
            progress['before_bytes'] += before_bytes
            progress['after_bytes'] += after_bytes
            progress['saved_bytes'] += before_bytes - after_bytes
            totals['updated'] += updated
            totals['saved_bytes'] += before_bytes - after_bytes
            if apply:
                _save(checkpoint, state)
            print(_json({'table': table, 'cursor': progress['cursor'], 'upper': progress['upper'],
                         'scanned': progress['scanned'], 'updated': progress['updated'],
                         'saved_bytes': progress['saved_bytes'], 'applied': apply}), flush=True)
        totals['tables'][table] = {key: progress[key] for key in ('cursor', 'upper', 'scanned', 'updated', 'before_bytes', 'after_bytes', 'saved_bytes')}
    # Original intelligence postings remain inline until app readers support hydration.
    if not compact_intelligence and connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='job_description_intelligence'").fetchone():
        totals['job_description_intelligence'] = {'status': 'optional_equal_description_aliases_only'}
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env', default='user_config/.env')
    parser.add_argument('--overlay')
    parser.add_argument('--storage-env', help='Shared evidence storage environment overrides')
    parser.add_argument('--sqlite', help='Explicit existing local SQLite database')
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--batch-size', type=int, default=10)
    parser.add_argument('--max-seconds', type=float, default=60)
    parser.add_argument('--archive-workers', type=int, default=4)
    parser.add_argument('--compact-intelligence', action='store_true', help='Remove only original aliases byte-equal to their linked version description; requires updated app readers')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    env = dict(dotenv_values(args.env))
    if args.overlay:
        env.update(dotenv_values(args.overlay))
    if args.storage_env:
        env.update(dotenv_values(args.storage_env))
    os.environ.update({key: str(value) for key, value in env.items() if value is not None})
    if args.sqlite:
        path = Path(args.sqlite).resolve()
        identity = 'sqlite:' + str(path)
        connection = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True)
    else:
        if not os.environ.get('TURSO_DATABASE_URL'):
            parser.error('Remote URL or explicit --sqlite is required')
        identity = os.environ['TURSO_DATABASE_URL']
        connection = HttpMaintenanceConnection()
    try:
        result = reduce_catalog_storage(connection, database_identity=identity, checkpoint=args.checkpoint, apply=args.apply, batch_size=args.batch_size, max_seconds=args.max_seconds, archive_workers=args.archive_workers, compact_intelligence=args.compact_intelligence)
        print(_json(result))
    finally:
        connection.close()


if __name__ == '__main__':
    main()
