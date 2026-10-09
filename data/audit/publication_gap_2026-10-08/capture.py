"""Read-only, bounded publication-gap snapshot. Writes local evidence only."""
import gzip
import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
from urllib.error import URLError
from urllib.request import Request, urlopen

def query(sql, args=(), *, compressed=False):
    if not sql.lstrip().upper().startswith(('SELECT ', 'PRAGMA ')):
        raise ValueError('Only read-only audit queries are permitted')
    def parameter(value):
        if value is None: return {'type': 'null'}
        if isinstance(value, int): return {'type': 'integer', 'value': str(value)}
        return {'type': 'text', 'value': str(value)}
    payload = {'requests': [{'type': 'execute', 'stmt': {'sql': sql,
        'args': [parameter(v) for v in args], 'want_rows': True}}, {'type': 'close'}]}
    target = os.environ['TURSO_DATABASE_URL'].replace('libsql://', 'https://').rstrip('/') + '/v2/pipeline'
    headers = {'Authorization': 'Bearer ' + os.environ['TURSO_AUTH_TOKEN'], 'Content-Type': 'application/json'}
    if compressed: headers['Accept-Encoding'] = 'gzip'
    request = Request(target, data=json.dumps(payload).encode(), headers=headers)
    for attempt in range(3):
        try:
            with urlopen(request, timeout=45) as response:
                content = gzip.GzipFile(fileobj=response) if response.headers.get('Content-Encoding') == 'gzip' else response
                data = json.load(content)
            break
        except (TimeoutError, URLError):
            if attempt == 2: raise RuntimeError('Read-only Turso snapshot request failed') from None
            time.sleep(1)
    result = data['results'][0]
    if result['type'] != 'ok':
        raise RuntimeError('Read-only Turso statement failed: ' + result.get('error', {}).get('code', 'unknown'))
    result = result['response']['result']
    names = [col['name'] for col in result['cols']]
    def decoded(cell):
        if cell['type'] == 'null': return None
        if cell['type'] == 'integer': return int(cell['value'])
        if cell['type'] == 'float': return float(cell['value'])
        return cell['value']
    return [dict(zip(names, map(decoded, row))) for row in result['rows']]


base_query = query
from dotenv import load_dotenv


def stamp():
    return datetime.now(timezone.utc).isoformat()

def query(sql, args=()):
    for attempt in range(6):
        try:
            return base_query(sql, args)
        except Exception:
            if attempt == 5:
                raise
            print(json.dumps({'retry': attempt+1}), flush=True)
            time.sleep(1)


def snapshot():
    load_dotenv(ROOT / 'user_config/.env', override=False)
    meta = {'started_at': stamp(), 'database_identity': hashlib.sha256(os.environ['TURSO_DATABASE_URL'].encode()).hexdigest(), 'tables': {}}
    meta['head_start'] = query('SELECT h.*,p.cycle_id,p.policy_version,p.status,p.published_at,p.origin,p.created_by FROM acquisition_publication_head h JOIN acquisition_publications p USING(publication_id) WHERE head_id=1')[0]
    meta['schema'] = query("SELECT name,sql FROM sqlite_master WHERE type IN ('table','index') AND (name LIKE '%publication%' OR name IN ('acquisition_tasks','acquisition_cycles','job_source_observations','canonical_jobs','job_source_states'))")
    (OUT / 'metadata.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    specs = {
        'canonical_jobs': 'canonical_job_id,company_id,title,location,canonical_url,lifecycle_state,first_seen_at,last_seen_at,last_verified_at,current_version_id,created_at,updated_at,published_at',
        'job_source_observations': 'observation_id,canonical_job_id,target_id,cycle_id,task_id,external_job_id,source_ats,observed_at,active',
        'job_posting_versions': 'version_id,canonical_job_id,source_observation_id,created_at',
        'canonical_companies': 'company_id,canonical_name',
        'acquisition_cycles': 'cycle_id,status,started_at,completed_at,updated_at,publication_id,error_code,error_message,jobs_observed,jobs_published',
        'acquisition_tasks': 'task_id,cycle_id,target_id,status,started_at,completed_at,updated_at,valid_snapshot,complete_snapshot,jobs_observed,jobs_published,error_code,error_message',
        'acquisition_publications': 'publication_id,cycle_id,status,published_at,previous_publication_id,origin,created_by,policy_version',
        'acquisition_publication_target_scope': 'scope_id,target_id',
        'acquisition_publisher_checkpoints': '*',
        'job_source_states': '*',
    }
    for table, columns in specs.items():
        dest = OUT / (table + '.jsonl.gz')
        if dest.exists():
            print(json.dumps({'table': table, 'cached': True}), flush=True)
            continue
        bounds = query(f'SELECT COALESCE(MAX(rowid),0) AS upper FROM {table}')[0]
        if table == 'job_source_observations':
            def page(start):
                return query(f'SELECT rowid AS audit_rowid,{columns} FROM {table} WHERE rowid>? AND rowid<=?', (start, min(start+1000,bounds['upper'])))
            total = 0
            with gzip.open(dest, 'wt', encoding='utf-8') as stream, ThreadPoolExecutor(max_workers=6) as pool:
                for batch in pool.map(page, range(0,bounds['upper'],1000)):
                    for row in batch:
                        stream.write(json.dumps(row, ensure_ascii=False)+'\n')
                    total += len(batch)
                    print(json.dumps({'table': table, 'captured': total}), flush=True)
            meta['tables'][table] = {**bounds, 'captured': total, 'finished_at': stamp()}
            continue
        cursor = 0
        total = 0
        begun = time.monotonic()
        temp = dest.with_suffix('.partial')
        if temp.exists():
            with gzip.open(temp, 'rt', encoding='utf-8') as existing:
                for line in existing:
                    cursor = json.loads(line)['audit_rowid']
                    total += 1
        with gzip.open(temp, 'at', encoding='utf-8') as stream:
            while cursor < bounds['upper']:
                batch = query(f'SELECT rowid AS audit_rowid,{columns} FROM {table} WHERE rowid>? AND rowid<=? ORDER BY rowid LIMIT 1000', (cursor, bounds['upper']))
                if not batch:
                    break
                for row in batch:
                    stream.write(json.dumps(row, ensure_ascii=False) + '\n')
                cursor = batch[-1]['audit_rowid']
                total += len(batch)
                print(json.dumps({'table': table, 'captured': total, 'upper_rowid': bounds['upper'], 'seconds': round(time.monotonic()-begun, 1)}), flush=True)
        temp.replace(dest)
        meta['tables'][table] = {**bounds, 'captured': total, 'finished_at': stamp()}
        (OUT / 'metadata.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    dest = OUT / 'head_membership.jsonl.gz'
    if not dest.exists():
        cursor = ''
        total = 0
        with gzip.open(dest, 'wt', encoding='utf-8') as stream:
            while True:
                batch = query('SELECT canonical_job_id FROM acquisition_publication_jobs WHERE publication_id=? AND canonical_job_id>? ORDER BY canonical_job_id LIMIT 4000', (meta['head_start']['publication_id'], cursor))
                if not batch:
                    break
                for row in batch:
                    stream.write(json.dumps(row) + '\n')
                total += len(batch)
                cursor = batch[-1]['canonical_job_id']
                print(json.dumps({'table': 'head_membership', 'captured': total}), flush=True)
        meta['head_membership_rows'] = total
    meta['head_end'] = query('SELECT * FROM acquisition_publication_head WHERE head_id=1')[0]
    meta['finished_at'] = stamp()
    (OUT / 'metadata.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    print(json.dumps({'complete': True, 'head_stable': meta['head_start']['publication_id']==meta['head_end']['publication_id'] and meta['head_start']['updated_at']==meta['head_end']['updated_at']}), flush=True)


if __name__ == '__main__':
    if sys.version_info[:3] != (3,12,7):
        raise RuntimeError('Project Python 3.12.7 required')
    snapshot()
