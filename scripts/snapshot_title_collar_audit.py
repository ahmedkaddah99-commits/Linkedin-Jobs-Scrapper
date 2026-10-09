"""Capture title-only audit inputs through read-only Turso SQL and SSH.

Writes local gzipped snapshots only. No model imports, requests or production
mutations. Producer helper executes from stdin without installation on the VPS.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def now():
    return datetime.now(timezone.utc).isoformat()


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


def capture_catalog(output):
    started = now()
    head = query('SELECT publication_id,updated_at FROM acquisition_publication_head WHERE head_id=1')[0]
    count = 0
    with gzip.open(output / 'catalog.jsonl.gz', 'wt', encoding='utf-8') as stream:
        def emit(kind, **row):
            stream.write(json.dumps({'kind': kind, **row}, ensure_ascii=False) + '\n')
        for row in query('SELECT company_id,canonical_name AS company FROM canonical_companies'):
            emit('company', **row)
        for row in query('SELECT source_identity_key,winner_company_id FROM company_identity_crosswalk'):
            emit('identity', **row)
        for row in query('SELECT canonical_job_id,url FROM canonical_job_url_aliases'):
            emit('url_alias', **row)
        for row in query('SELECT canonical_job_id,source_id,external_job_id FROM canonical_job_external_ids'):
            emit('external_id', **row)
        cursor = ''
        while True:
            rows = query('''SELECT j.canonical_job_id AS id,j.canonical_job_id,j.company_id,
                co.canonical_name AS company,j.title,j.canonical_url AS url,j.location,
                j.lifecycle_state AS lifecycle,j.current_version_id AS version_id,v.content_hash,
                v.title AS version_title, j.last_seen_at AS updated_at,
                CASE WHEN pj.canonical_job_id IS NULL THEN 0 ELSE 1 END AS published,
                CASE WHEN fi.content_hash=v.content_hash THEN json_extract(fi.filters_json,'$.collar') END AS existing_collar
                FROM canonical_jobs j JOIN canonical_companies co ON co.company_id=j.company_id
                LEFT JOIN job_posting_versions v ON v.version_id=j.current_version_id
                LEFT JOIN job_filter_intelligence fi ON fi.version_id=j.current_version_id
                LEFT JOIN acquisition_publication_jobs pj ON pj.canonical_job_id=j.canonical_job_id AND pj.publication_id=?
                WHERE j.canonical_job_id>? ORDER BY j.canonical_job_id LIMIT 1000''', (head['publication_id'], cursor))
            if not rows: break
            for row in rows:
                row['source'] = 'catalog'
                row['other_titles'] = [row.pop('version_title') or '']
                emit('job', **row)
            count += len(rows)
            cursor = rows[-1]['id']
            print(json.dumps({'source': 'catalog', 'jobs_captured': count}), flush=True)
        # Ingest staging is an additional unpublished lifecycle boundary.
        columns = [r['name'] for r in query('PRAGMA table_info(acquisition_ingest_staging)')]
        staging_count = 0
        if columns:
            rows = query('''SELECT batch_id,row_number,company_id,company_name AS company,
                canonical_job_id,resolved_canonical_job_id,title,original_url AS url,location,
                version_id,content_hash,observed_at AS updated_at
                FROM acquisition_ingest_staging ORDER BY batch_id,row_number''')
            for row in rows:
                row['id'] = row.pop('batch_id') + ':' + str(row.pop('row_number'))
                row['canonical_job_id'] = row.pop('resolved_canonical_job_id') or row['canonical_job_id']
                emit('job', source='ingest_staging', published=False, lifecycle='unknown', **row)
                staging_count += 1
        emit('snapshot', source='catalog', started_at=started, finished_at=now(), jobs=count,
             staging_jobs=staging_count, publication_start=head,
             publication_end=query('SELECT publication_id,updated_at FROM acquisition_publication_head WHERE head_id=1')[0],
             capture='bounded read-only pages; immutable version IDs/hashes recorded; no cross-page transaction')
    print(json.dumps({'source': 'catalog', 'complete': True, 'jobs': count, 'staging_jobs': staging_count}), flush=True)


def capture_producers(output):
    version = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'runr-vps',
                              '/opt/runr/.venv/bin/python --version'], capture_output=True, check=True)
    if version.stdout.strip() != b'Python 3.12.7':
        raise RuntimeError('VPS project interpreter must be Python 3.12.7')
    with (output / 'producers.jsonl.gz').open('wb') as stream:
        result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'runr-vps',
            'sudo /opt/runr/.venv/bin/python -'], input=(ROOT / 'scripts/export_title_audit_producers.py').read_bytes(),
            stdout=stream, stderr=subprocess.PIPE, timeout=600)
    if result.returncode:
        raise RuntimeError('Read-only producer snapshot failed: ' + result.stderr.decode(errors='replace')[:600])
    print(json.dumps({'source': 'producers', 'complete': True,
                      'bytes': (output / 'producers.jsonl.gz').stat().st_size}), flush=True)


if __name__ == '__main__':
    if sys.version_info[:3] != (3, 12, 7):
        raise RuntimeError('Project Python 3.12.7 required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--source', choices=('catalog','producers'), required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.source == 'catalog':
        load_dotenv(ROOT / 'user_config/.env', override=False)
        capture_catalog(args.output)
    else:
        capture_producers(args.output)
