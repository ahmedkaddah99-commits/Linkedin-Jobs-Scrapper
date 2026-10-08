"""Bounded, resumable in-place JSON cleanup; preserves identities and hashes."""
from __future__ import annotations
import argparse
import json
import os
import sys
import sqlite3
import hashlib
from urllib.request import Request, urlopen
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import dotenv_values
from backend.database.connection import connect_database


class HttpMaintenanceConnection:
    """Bounded aggregate reads and one atomic HTTP round trip per batch."""
    def __init__(self, timeout=180):
        self.timeout = timeout
        self.url = os.environ['TURSO_DATABASE_URL'].replace('libsql://','https://').rstrip('/') + '/v2/pipeline'
        self.token = os.environ['TURSO_AUTH_TOKEN']

    def request(self, request):
        body = {'requests':[request, {'type':'close'}]}
        req = Request(self.url,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        with urlopen(req,timeout=self.timeout) as response:
            result = json.load(response)['results'][0]
        if result['type'] != 'ok':
            raise RuntimeError('Turso maintenance request failed: '+str(result.get('error',{}).get('code','unknown')))
        return result['response']['result']

    @staticmethod
    def stmt(sql, parameters=(), *, want_rows=True):
        args = [{'type':'integer','value':str(v)} if isinstance(v,int) else {'type':'text','value':str(v)} for v in parameters]
        return {'sql':sql,'args':args,'want_rows':want_rows}

    def execute(self, sql, parameters=()):
        result = self.request({'type':'execute','stmt':self.stmt(sql,parameters)})
        def decode(cell):
            if cell['type']=='null':
                return None
            if cell['type']=='integer':
                return int(cell['value'])
            return cell['value']
        rows = [[decode(c) for c in row] for row in result['rows']]
        class Rows:
            def fetchone(self):
                return rows[0] if rows else None
            def fetchall(self):
                return rows
        return Rows()

    def atomic(self, statements):
        steps = [{'stmt':self.stmt('BEGIN IMMEDIATE',want_rows=False)}]
        for sql, parameters in statements + [('COMMIT',())]:
            steps.append({'condition':{'type':'ok','step':len(steps)-1},'stmt':self.stmt(sql,parameters,want_rows=False)})
        commit_step = len(steps)-1
        steps.append({'condition':{'type':'not','cond':{'type':'ok','step':commit_step}},'stmt':self.stmt('ROLLBACK',want_rows=False)})
        result = self.request({'type':'batch','batch':{'steps':steps}})
        if result['step_results'][commit_step] is None:
            codes = [error.get('code','unknown') for error in result['step_errors'] if error]
            raise RuntimeError('Turso maintenance transaction rolled back: '+','.join(codes))

    def close(self):
        pass


def provision_compaction_guard(connection, table, original_sql):
    columns = connection.execute(f'PRAGMA table_info({table})').fetchall()
    protected = ['NEW.rowid IS NOT OLD.rowid']
    protected += [f'NEW."{row[1]}" IS NOT OLD."{row[1]}"' for row in columns if row[1] not in ('payload_json','raw_payload_json')]
    trigger = 'trg_' + table + '_immutable_update'
    guard = f"CREATE TRIGGER {trigger} BEFORE UPDATE ON {table} WHEN NOT EXISTS (SELECT 1 FROM runr_storage_compaction_guard WHERE table_name='{table}' AND OLD.rowid>first_rowid AND OLD.rowid<=last_rowid) OR {' OR '.join(protected)} BEGIN SELECT RAISE(ABORT,'{table} are immutable'); END"
    connection.atomic([
        ('CREATE TABLE IF NOT EXISTS runr_storage_compaction_guard(table_name TEXT PRIMARY KEY,first_rowid INTEGER NOT NULL,last_rowid INTEGER NOT NULL)',()),
        (f'DROP TRIGGER {trigger}',()), (guard,())])
    if connection.execute('SELECT count(*) FROM runr_storage_compaction_guard').fetchone()[0]:
        raise RuntimeError('Unexpected persistent compaction flag; refuse further writes')


def compact_expression(column):
    paths = ["'$.content_fingerprint'", "'$.source_raw_payload.observation_contract.normalized_mapping'"]
    paths.append(f"CASE WHEN json_extract({column},'$.source_raw_payload.observation_contract.source_record')=json_extract({column},'$.source_raw_payload.producer_record') THEN '$.source_raw_payload.observation_contract.source_record' ELSE '$.__absent_compaction_field' END")
    paths.append(f"CASE WHEN json_extract({column},'$.field_provenance')=json_extract({column},'$.unified_mapping.fields') THEN '$.field_provenance' ELSE '$.__absent_compaction_field' END")
    for key in ('description', 'description_text', 'description_html', 'description_raw', 'title', 'location'):
        paths.append(f"CASE WHEN json_extract({column},'$.source_raw_payload.{key}')=json_extract({column},'$.{key}') THEN '$.source_raw_payload.{key}' ELSE '$.__absent_compaction_field' END")
    base = f"json_remove({column},{','.join(paths)})"
    prefixes = ('$', '$.source_raw_payload', '$.source_raw_payload.producer_record', '$.source_raw_payload.producer_record.source_raw_payload', '$.source_raw_payload.observation_contract.source_record', '$.source_raw_payload.observation_contract.source_record.source_raw_payload')
    html_paths = ','.join(f"'{prefix}.{key}'" for prefix in prefixes for key in ('source_page_html','page_html','source_html','raw_html','html'))
    return f"CASE WHEN json_type({column},'$.application_destination')='object' THEN json_remove({base},{html_paths}) ELSE {base} END"


def candidate_predicate(columns):
    keys = ('content_fingerprint','field_provenance','normalized_mapping','source_page_html','page_html','source_html','raw_html','html')
    return ' OR '.join(f"{column} LIKE '%\"{key}\":%'" for column in columns for key in keys)


def apply_batch(connection, table, columns, cursor, end):
    """Restore immutable-history guards before committing storage-only writes."""
    trigger_name = 'trg_' + table + '_immutable_update'
    row = connection.execute('SELECT sql FROM sqlite_master WHERE type=\'trigger\' AND name=?', (trigger_name,)).fetchone()
    trigger_sql = row[0] if row else None
    flag_guard = trigger_sql and 'runr_storage_compaction_guard' in trigger_sql
    statements = []
    if flag_guard:
        statements.append(('INSERT INTO runr_storage_compaction_guard VALUES(?,?,?)',(table,cursor,end)))
    elif trigger_sql:
        statements.append((f'DROP TRIGGER {trigger_name}', ()))
    if 'raw_payload_json' in columns:
        html_paths = [f'$.{key}' for key in ('source_page_html','page_html','source_html','raw_html','html')]
        html_paths += [f'$.source_raw_payload.{key}' for key in ('source_page_html','page_html','source_html','raw_html','html')]
        predicate = ' OR '.join(f"json_type(raw_payload_json,'{path}')='text'" for path in html_paths)
        statements.append((f"UPDATE {table} SET raw_payload_json=json_set(raw_payload_json,'$.application_destination',json_extract(payload_json,'$.application_destination')) WHERE rowid>? AND rowid<=? AND json_type(payload_json,'$.application_destination')='object' AND ({predicate})", (cursor,end)))
    assignments = ','.join(f'{c}={compact_expression(c)}' for c in columns)
    statements.append((f'UPDATE {table} SET {assignments} WHERE rowid>? AND rowid<=? AND ({candidate_predicate(columns)})', (cursor,end)))
    if flag_guard:
        statements.append(('DELETE FROM runr_storage_compaction_guard WHERE table_name=?',(table,)))
    elif trigger_sql:
        statements.append((trigger_sql, ()))
    if isinstance(connection,HttpMaintenanceConnection):
        connection.atomic(statements)
        if flag_guard and connection.execute('SELECT count(*) FROM runr_storage_compaction_guard').fetchone()[0]:
            raise RuntimeError('Unexpected persistent compaction flag after batch')
        return
    connection.execute('BEGIN IMMEDIATE')
    try:
        for sql, parameters in statements:
            connection.execute(sql,parameters)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env', default='user_config/.env')
    parser.add_argument('--overlay')
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--batch-size', type=int, default=200)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--linkedin-state', help='Compact successful LinkedIn attempt diagnostics in this local producer DB')
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 5000:
        parser.error('batch-size must be between 1 and 5000')
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
    connection = HttpMaintenanceConnection() if os.environ.get('TURSO_DATABASE_URL') else connect_database(ROOT / 'data/audit/job_storage_2026-10-08/probe.sqlite3')
    original_guards = state.setdefault('_original_guards', {})
    try:
        for table, columns in [('job_source_observations', ['payload_json', 'raw_payload_json']), ('job_posting_versions', ['payload_json']), ('acquisition_ingest_staging', ['payload_json', 'raw_payload_json'])]:
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if not exists:
                continue
            if args.apply and isinstance(connection,HttpMaintenanceConnection):
                guard_row = connection.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", ('trg_'+table+'_immutable_update',)).fetchone()
                if guard_row:
                    current_guard = guard_row[0]
                    if 'runr_storage_compaction_guard' not in current_guard:
                        original_guards[table] = current_guard
                        checkpoint.parent.mkdir(parents=True,exist_ok=True)
                        checkpoint.write_text(json.dumps(state),encoding='utf-8')
                        provision_compaction_guard(connection,table,current_guard)
                    elif table not in original_guards:
                        raise RuntimeError('Missing original guard backup; refuse further writes')
            upper = connection.execute(f'SELECT COALESCE(MAX(rowid),0) FROM {table}').fetchone()[0]
            cursor = state.get(table, {}).get('cursor', 0)
            saved = state.get(table, {}).get('saved_bytes', 0)
            while cursor < upper:
                ids = connection.execute(f'SELECT rowid FROM {table} WHERE rowid>? AND rowid<=? AND ({candidate_predicate(columns)}) ORDER BY rowid LIMIT ?', (cursor, upper, args.batch_size)).fetchall()
                if not ids:
                    state[table] = {'cursor':upper, 'upper':upper, 'saved_bytes':saved, 'applied':args.apply}
                    break
                end = ids[-1][0]
                start = ids[0][0] - 1
                size_sql = '+'.join(f'length(CAST({c} AS BLOB))' for c in columns)
                print(json.dumps({'table':table, 'phase':'batch_start', 'start':start, 'end':end}), flush=True)
                before = connection.execute(f'SELECT COALESCE(SUM({size_sql}),0) FROM {table} WHERE rowid>? AND rowid<=?', (start,end)).fetchone()[0]
                if args.apply:
                    apply_batch(connection,table,columns,start,end)
                projected_size = size_sql if args.apply else '+'.join(f'length(CAST({compact_expression(c)} AS BLOB))' for c in columns)
                after = connection.execute(f'SELECT COALESCE(SUM({projected_size}),0) FROM {table} WHERE rowid>? AND rowid<=?', (start,end)).fetchone()[0]
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
        if args.apply and isinstance(connection,HttpMaintenanceConnection):
            restore = []
            for table, sql in original_guards.items():
                current = connection.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", ('trg_'+table+'_immutable_update',)).fetchone()
                if current and 'runr_storage_compaction_guard' in current[0]:
                    restore += [(f'DROP TRIGGER trg_{table}_immutable_update',()), (sql,())]
            flag_table = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='runr_storage_compaction_guard'").fetchone()
            if flag_table:
                if connection.execute('SELECT count(*) FROM runr_storage_compaction_guard').fetchone()[0]:
                    raise RuntimeError('Unexpected persistent compaction authorization')
                restore.append(('DROP TABLE runr_storage_compaction_guard',()))
            if restore:
                connection.atomic(restore)
                print(json.dumps({'immutability_guards':'restored','maintenance_flags':'removed'}),flush=True)
        connection.close()


if __name__ == '__main__':
    main()
