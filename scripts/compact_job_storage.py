"""Bounded, resumable in-place JSON cleanup; preserves identities and hashes."""
from __future__ import annotations
import argparse
import json
import os
import sys
import sqlite3
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import dotenv_values
from backend.database.connection import connect_database


def compact_expression(column):
    paths = ["'$.content_fingerprint'", "'$.source_raw_payload.observation_contract.normalized_mapping'"]
    paths.append(f"CASE WHEN NOT EXISTS (SELECT 1 FROM json_each({column},'$.source_raw_payload.observation_contract.source_record') original WHERE json_extract({column}, '$.' || original.key) IS NOT original.value) THEN '$.source_raw_payload.observation_contract.source_record' ELSE '$.__absent_compaction_field' END")
    paths.append(f"CASE WHEN json_extract({column},'$.field_provenance')=json_extract({column},'$.unified_mapping.fields') THEN '$.field_provenance' ELSE '$.__absent_compaction_field' END")
    for key in ('description', 'description_text', 'description_html', 'description_raw', 'title', 'location'):
        paths.append(f"CASE WHEN json_extract({column},'$.source_raw_payload.{key}')=json_extract({column},'$.{key}') THEN '$.source_raw_payload.{key}' ELSE '$.__absent_compaction_field' END")
    for key in ('source_page_html', 'page_html', 'source_html', 'raw_html', 'html'):
        # Existing raw source HTML is retained until its destination is extracted.
        paths.append(f"CASE WHEN json_type({column},'$.application_destination')='object' THEN '$.{key}' ELSE '$.__absent_compaction_field' END")
        paths.append(f"CASE WHEN json_type({column},'$.application_destination')='object' THEN '$.source_raw_payload.{key}' ELSE '$.__absent_compaction_field' END")
    return f"json_remove({column},{','.join(paths)})"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env', default='user_config/.env')
    parser.add_argument('--overlay')
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--batch-size', type=int, default=200)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--linkedin-state', help='Compact successful LinkedIn attempt diagnostics in this local producer DB')
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 1000:
        parser.error('batch-size must be between 1 and 1000')
    if args.linkedin_state:
        connection = sqlite3.connect(f'file:{Path(args.linkedin_state).resolve()}?mode=rw', uri=True, timeout=30)
        try:
            count, before = connection.execute("SELECT count(*),COALESCE(sum(length(detail_json)),0) FROM detail_attempts WHERE status='SUCCESS'").fetchone()
            if args.apply:
                backup_path = Path(str(args.linkedin_state) + '.before-storage-cleanup.db')
                if not backup_path.exists():
                    backup = sqlite3.connect(backup_path)
                    try:
                        connection.backup(backup, pages=1024)
                    finally:
                        backup.close()
                cursor = 0
                upper = connection.execute('SELECT COALESCE(max(rowid),0) FROM detail_attempts').fetchone()[0]
                while cursor < upper:
                    ids = connection.execute('SELECT rowid FROM detail_attempts WHERE rowid>? AND rowid<=? ORDER BY rowid LIMIT ?', (cursor,upper,args.batch_size)).fetchall()
                    if not ids:
                        break
                    end = ids[-1][0]
                    connection.execute("UPDATE detail_attempts SET detail_json=json_object('body_hash',json_extract(detail_json,'$.body_hash'),'content_hash',json_extract(detail_json,'$.content_hash')) WHERE rowid>? AND rowid<=? AND status='SUCCESS' AND detail_json LIKE '%description%'", (cursor,end))
                    connection.commit()
                    cursor = end
            after = connection.execute("SELECT COALESCE(sum(length(detail_json)),0) FROM detail_attempts WHERE status='SUCCESS'").fetchone()[0]
            print(json.dumps({'producer':'linkedin','successful_attempts':count,'before_bytes':before,'after_bytes':after,'saved_bytes':before-after,'applied':args.apply}), flush=True)
        finally:
            connection.close()
        return
    env = dict(dotenv_values(args.env))
    if args.overlay:
        env.update(dotenv_values(args.overlay))
    os.environ.update({k: str(v) for k,v in env.items() if v is not None})
    checkpoint = Path(args.checkpoint)
    state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    identity = hashlib.sha256(os.environ.get('TURSO_DATABASE_URL', str(ROOT)).encode()).hexdigest()
    if state.get('_database', identity) != identity:
        raise ValueError('Checkpoint belongs to a different database')
    state['_database'] = identity
    connection = connect_database(ROOT / 'data/audit/job_storage_2026-10-08/probe.sqlite3')
    try:
        for table, columns in [('job_source_observations', ['payload_json', 'raw_payload_json']), ('job_posting_versions', ['payload_json']), ('acquisition_ingest_staging', ['payload_json', 'raw_payload_json'])]:
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if not exists:
                continue
            upper = connection.execute(f'SELECT COALESCE(MAX(rowid),0) FROM {table}').fetchone()[0]
            cursor = state.get(table, {}).get('cursor', 0)
            saved = state.get(table, {}).get('saved_bytes', 0)
            while cursor < upper:
                ids = connection.execute(f'SELECT rowid FROM {table} WHERE rowid>? AND rowid<=? ORDER BY rowid LIMIT ?', (cursor, upper, args.batch_size)).fetchall()
                if not ids:
                    break
                end = ids[-1][0]
                size_sql = '+'.join(f'length(CAST({c} AS BLOB))' for c in columns)
                before = connection.execute(f'SELECT COALESCE(SUM({size_sql}),0) FROM {table} WHERE rowid>? AND rowid<=?', (cursor,end)).fetchone()[0]
                if args.apply:
                    if 'raw_payload_json' in columns:
                        connection.execute(f"UPDATE {table} SET raw_payload_json=json_set(raw_payload_json,'$.application_destination',json_extract(payload_json,'$.application_destination')) WHERE rowid>? AND rowid<=? AND json_type(payload_json,'$.application_destination')='object' AND (json_type(raw_payload_json,'$.source_raw_payload.html')='text' OR json_type(raw_payload_json,'$.source_page_html')='text' OR json_type(raw_payload_json,'$.page_html')='text' OR json_type(raw_payload_json,'$.raw_html')='text')", (cursor,end))
                    assignments = ','.join(f'{c}={compact_expression(c)}' for c in columns)
                    connection.execute(f'UPDATE {table} SET {assignments} WHERE rowid>? AND rowid<=?', (cursor,end))
                    connection.commit()
                projected_size = size_sql if args.apply else '+'.join(f'length(CAST({compact_expression(c)} AS BLOB))' for c in columns)
                after = connection.execute(f'SELECT COALESCE(SUM({projected_size}),0) FROM {table} WHERE rowid>? AND rowid<=?', (cursor,end)).fetchone()[0]
                saved += before-after
                cursor = end
                state[table] = {'cursor':cursor, 'upper':upper, 'saved_bytes':saved, 'applied':args.apply}
                if args.apply:
                    checkpoint.parent.mkdir(parents=True, exist_ok=True)
                    temporary = checkpoint.with_suffix('.tmp')
                    temporary.write_text(json.dumps(state), encoding='utf-8')
                    temporary.replace(checkpoint)
                print(json.dumps({'table':table, **state[table]}), flush=True)
            print(json.dumps({'table':table, 'done':True, 'saved_bytes':saved}), flush=True)
    finally:
        connection.close()


if __name__ == '__main__':
    main()
