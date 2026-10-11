"""Remove equal JSON copies in place, retaining canonical values and identities.

The temporary immutable-update exception permits only this exact deterministic
transformation. It never permits identity edits, arbitrary payloads or deletes.
Original trigger SQL is saved before installation and restored on completion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import dotenv_values
from scripts.reduce_catalog_storage import NativeMaintenanceConnection, _save

TABLES = {
    'job_source_observations': ('payload_json', 'raw_payload_json'),
    'job_posting_versions': ('payload_json',),
}
NOOP = '$.__runr_duplicate_noop_20261009_a52fd62f'
ALIASES = ('description', 'description_raw', 'description_html', 'full_description')


def same_sql(left, right):
    """Turso formats schema SQL; compare tokens, retaining quoted literals."""
    if left is None or right is None:
        return left == right
    pattern = r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|[^\s]"
    def tokens(value):
        values = re.findall(pattern, value)
        while values and values[-1] == ';':
            values.pop()
        return [token if token.startswith(("'", '"')) else token.lower() for token in values]
    return tokens(left) == tokens(right)


def quote_identifier(value):
    return '"' + value.replace('"', '""') + '"'


def duplicate_pairs():
    pairs = [('$.field_provenance', '$.unified_mapping.fields'),
             ('$.source_raw_payload.observation_contract.source_record', '$.source_raw_payload.producer_record')]
    pairs.extend(('$.source_raw_payload.' + key, '$.' + key)
                 for key in ('title', 'location', 'company', 'company_name', 'source', 'description_text', *ALIASES))
    pairs.extend(('$.source_raw_payload.producer_record.' + key, '$.' + key)
                 for key in ('title', 'location', 'company', 'company_name', 'source', 'description_text', *ALIASES))
    pairs.extend(('$.' + key, '$.description_text') for key in ALIASES)
    return pairs


def equality(column, copy, canonical):
    return (f"json_type({column},'{copy}') IS NOT NULL AND "
            f"json_type({column},'{copy}')=json_type({column},'{canonical}') AND "
            f"json_extract({column},'{copy}')=json_extract({column},'{canonical}')")


def expression(column):
    paths = [f"CASE WHEN {equality(column, copy, canonical)} THEN '{copy}' ELSE '{NOOP}' END"
             for copy, canonical in duplicate_pairs()]
    return f"json_remove({column},{','.join(paths)})"


def predicate(column):
    return (f"json_valid({column}) AND json_type({column},'{NOOP}') IS NULL AND (" +
            ' OR '.join('(' + equality(column, copy, canonical) + ')' for copy, canonical in duplicate_pairs()) + ')')


def guarded_trigger(table, name, all_columns, payload_columns):
    checks = ['NEW.rowid IS OLD.rowid']
    for column in all_columns:
        key = quote_identifier(column)
        if column in payload_columns:
            checks.append(f'(NEW.{key} IS OLD.{key} OR (json_valid(OLD.{key}) AND '
                          f"json_type(OLD.{key},'{NOOP}') IS NULL AND NEW.{key} IS {expression('OLD.' + key)}))")
        else:
            checks.append(f'NEW.{key} IS OLD.{key}')
    return (f'CREATE TRIGGER {quote_identifier(name)} BEFORE UPDATE ON {quote_identifier(table)} '
            'WHEN NOT (' + ' AND '.join(checks) + ") BEGIN SELECT RAISE(ABORT,'immutable catalog values'); END")


def install_guard(db, table, columns, progress, checkpoint, state):
    triggers = db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name=? ORDER BY name", (table,)).fetchall()
    if 'guards' not in progress:
        progress['guards'] = []
        all_columns = [row[1] for row in db.execute(f'PRAGMA table_info({table})').fetchall()]
        for name, sql in triggers:
            # Only known unconditional immutable-update guards are replaced.
            normalized = ' '.join(sql.split()).lower()
            if 'before update on' not in normalized:
                continue
            expected = f"create trigger {name} before update on {table} begin select raise (abort, '{table} are immutable'); end".lower()
            if normalized.rstrip(';') != expected:
                raise RuntimeError('Unrecognized immutable update trigger; leaving it unchanged')
            progress['guards'].append({'name': name, 'original': sql,
                                       'temporary': guarded_trigger(table, name, all_columns, columns)})
        _save(checkpoint, state)
    actual = dict(triggers)
    statements = []
    for guard in progress['guards']:
        existing = actual.get(guard['name'])
        if same_sql(existing, guard['temporary']):
            continue
        if not same_sql(existing, guard['original']):
            raise RuntimeError('Immutable trigger differs from saved definitions')
        statements.extend([(f"DROP TRIGGER {quote_identifier(guard['name'])}", ()), (guard['temporary'], ())])
    if statements:
        db.atomic(statements)


def restore_guards(db, progress):
    statements = []
    for guard in progress.get('guards', []):
        row = db.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (guard['name'],)).fetchone()
        if row and same_sql(row[0], guard['original']):
            continue
        if not row or not same_sql(row[0], guard['temporary']):
            raise RuntimeError('Cannot restore an unexpected immutable trigger')
        statements.extend([(f"DROP TRIGGER {quote_identifier(guard['name'])}", ()), (guard['original'], ())])
    if statements:
        db.atomic(statements)


def deduplicate(db, *, checkpoint, database_identity, max_seconds=300, batch_size=100, apply=False, keep_compaction_guards=False):
    checkpoint = Path(checkpoint)
    state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    identity = hashlib.sha256(database_identity.encode()).hexdigest()
    if state.get('database_identity', identity) != identity:
        raise ValueError('Checkpoint belongs to another database')
    state['database_identity'] = identity
    deadline = time.monotonic() + max_seconds
    for table, columns in TABLES.items():
        if time.monotonic() >= deadline:
            break
        progress = state.setdefault(table, {'cursor': 0, 'saved_bytes': 0, 'updated': 0})
        if 'upper' not in progress:
            progress['upper'] = db.execute(f'SELECT COALESCE(max(rowid),0) FROM {table}').fetchone()[0]
        if progress['cursor'] >= progress['upper']:
            progress['upper'] = db.execute(f'SELECT COALESCE(max(rowid),0) FROM {table}').fetchone()[0]
            if progress['cursor'] >= progress['upper']:
                continue
        try:
            if apply:
                install_guard(db, table, columns, progress, checkpoint, state)
            while progress['cursor'] < progress['upper'] and time.monotonic() < deadline:
                rows = db.execute(f'SELECT rowid FROM {table} WHERE rowid>? AND rowid<=? ORDER BY rowid LIMIT ?',
                                  (progress['cursor'], progress['upper'], batch_size)).fetchall()
                if not rows:
                    progress['cursor'] = progress['upper']
                    break
                start, end = progress['cursor'], rows[-1][0]
                size = '+'.join(f'COALESCE(length(CAST({column} AS BLOB)),0)' for column in columns)
                before = db.execute(f'SELECT COALESCE(sum({size}),0) FROM {table} WHERE rowid>? AND rowid<=?', (start, end)).fetchone()[0]
                if apply:
                    assignments = ','.join(f'{column}={expression(column)}' for column in columns)
                    eligible = ' OR '.join('(' + predicate(column) + ')' for column in columns)
                    pending = progress.get('pending')
                    if pending:
                        start, end, before = pending['start'], pending['end'], pending['before_bytes']
                    else:
                        candidates = db.execute(f'SELECT count(*) FROM {table} WHERE rowid>? AND rowid<=? AND ({eligible})', (start, end)).fetchone()[0]
                        pending = {'start': start, 'end': end, 'before_bytes': before,
                                   'candidates': candidates, 'row_count': len(rows)}
                        progress['pending'] = pending
                        _save(checkpoint, state)
                    remaining = db.execute(f'SELECT count(*) FROM {table} WHERE rowid>? AND rowid<=? AND ({eligible})', (start, end)).fetchone()[0]
                    write_error = None
                    if remaining:
                        try:
                            db.atomic([(
                                f'UPDATE {table} SET {assignments} WHERE rowid>? AND rowid<=? AND ({eligible})', (start, end))])
                        except (TimeoutError, OSError) as error:
                            # A commit can precede a lost/blocked close response.
                            # Recover using saved before sizes and live values.
                            write_error = error
                    remaining = db.execute(f'SELECT count(*) FROM {table} WHERE rowid>? AND rowid<=? AND ({eligible})', (start, end)).fetchone()[0]
                    count = db.execute(f'SELECT count(*) FROM {table} WHERE rowid>? AND rowid<=?', (start, end)).fetchone()[0]
                    if remaining or count != pending['row_count']:
                        if write_error:
                            raise write_error
                        raise RuntimeError('Guarded compaction did not verify; checkpoint retained')
                    after = db.execute(f'SELECT COALESCE(sum({size}),0) FROM {table} WHERE rowid>? AND rowid<=?', (start, end)).fetchone()[0]
                    # Negative/ambiguous observations do not advance a receipt.
                    if after > before:
                        raise RuntimeError('Catalog size increased during guarded cleanup')
                    progress['saved_bytes'] += before - after
                    progress['updated'] += pending['candidates']
                    progress.pop('pending', None)
                progress['cursor'] = end
                if apply:
                    _save(checkpoint, state)
                print(json.dumps({'table': table, 'applied': apply, **{key: progress[key] for key in ('cursor','upper','updated','saved_bytes')}}), flush=True)
        finally:
            if apply and (not keep_compaction_guards or progress['cursor'] >= progress['upper']):
                restore_guards(db, progress)
    if apply:
        _save(checkpoint, state)
    return {table: {key: value[key] for key in ('cursor', 'upper', 'updated', 'saved_bytes')} for table, value in state.items() if isinstance(value, dict)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env', action='append', default=[])
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--batch-size', type=int, default=100)
    parser.add_argument('--max-seconds', type=float, default=300)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--keep-compaction-guards', action='store_true',
                        help='Keep the strictly lossless guard between resumable rounds; restore when a table finishes')
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 1000 or args.max_seconds <= 0:
        parser.error('Positive time budget and batch size 1..1000 required')
    for path in args.env:
        os.environ.update({k:v for k,v in dotenv_values(path).items() if v is not None})
    db = NativeMaintenanceConnection(timeout=30)
    try:
        print(json.dumps(deduplicate(db, checkpoint=args.checkpoint, database_identity=os.environ['TURSO_DATABASE_URL'],
                                    max_seconds=args.max_seconds, batch_size=args.batch_size, apply=args.apply,
                                    keep_compaction_guards=args.keep_compaction_guards)), flush=True)
    finally:
        db.close()


if __name__ == '__main__':
    main()
