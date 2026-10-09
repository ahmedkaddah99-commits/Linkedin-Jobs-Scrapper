"""Read-only VPS producer title snapshot, written as gzipped JSONL to stdout.

Execute via SSH stdin with the verified project interpreter. No files, locks,
credentials, scraper requests, database writes or AI requests are created here.
"""
import gzip
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.version_info[:3] != (3, 12, 7):
    raise RuntimeError('Python 3.12.7 required')


def now():
    return datetime.now(timezone.utc).isoformat()


def emit(kind, **record):
    output.write((json.dumps({'kind': kind, **record}, ensure_ascii=False) + '\n').encode())


def opened(path):
    resolved = Path(path).resolve(strict=True)
    connection = sqlite3.connect(resolved.as_uri() + '?mode=ro', uri=True, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA query_only=ON')
    connection.execute('BEGIN')
    connection.execute('SELECT name FROM sqlite_master LIMIT 1').fetchone()
    return connection, str(resolved)


def titles(payload):
    names = ('title', 'title_raw', 'job_title', 'title_en', 'title_de', 'english_title',
             'german_title', 'job_title_en', 'job_title_de')
    return list(dict.fromkeys(payload[key] for key in names
                             if isinstance(payload.get(key), str) and payload[key].strip()))


def job(payload, source, identity, updated, **extra):
    recorded_titles = titles(payload)
    emit('job', source=source, id=str(identity),
         company_id=payload.get('canonical_company_id') or payload.get('canonical_CompanyID') or '',
         company=payload.get('source_company_name') or payload.get('observed_company_name') or payload.get('company_name') or '',
         title=payload.get('job_title') or payload.get('title') or payload.get('title_raw') or '',
         other_titles=recorded_titles,
         url=payload.get('source_job_url') or payload.get('linkedin_job_url') or '',
         location=payload.get('location') or '',
         lifecycle=payload.get('lifecycle_status') or 'unknown',
         linkedin_job_id=payload.get('linkedin_job_id') or '',
         linkedin_company_id=payload.get('linkedin_company_id') or '',
         ownership=payload.get('ownership_status') or '',
         content_hash=payload.get('content_hash') or payload.get('raw_content_hash') or '',
         updated_at=updated, published=False, **extra)


with gzip.GzipFile(fileobj=sys.stdout.buffer, mode='wb', mtime=0) as output:
    manifest_path = Path('/srv/runr/shared/inputs/manifest-generations/active/SOURCE_ELIGIBILITY_MANIFEST.json').resolve(strict=True)
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    rows_by_fingerprint = {r['row_fingerprint']: r for r in manifest['rows']}
    tasks = []
    for task in manifest['tasks']:
        if task['source'] == 'employer_site':
            row = rows_by_fingerprint[task['representative_row_fingerprint']]
            tasks.append({'company_id': task['canonical_company_id'], 'company': row['company_name'],
                          'website': row['website']['url'].get('canonical', '')})
    emit('manifest', path=str(manifest_path), sha256=hashlib.sha256(manifest_bytes).hexdigest(),
         manifest_id=manifest['manifest_id'], manifest_hash=manifest['manifest_hash'],
         counts=manifest['counts'], employer_tasks=tasks)
    for row in manifest['rows']:
        if row.get('canonical_company_id'):
            emit('company', company_id=row['canonical_company_id'], company=row['company_name'])
    employer, employer_path = opened('/srv/runr/state/active/employer/master_employer_jobs_state.db')
    started = now()
    count = 0
    for row in employer.execute('SELECT source_key,payload_json,updated_at FROM jobs ORDER BY source_key'):
        payload = json.loads(row['payload_json'])
        job(payload, 'employer', row['source_key'], row['updated_at'])
        count += 1
    receipts = {r['company_key']: dict(r) for r in employer.execute('SELECT company_key,classification,receipt_json,updated_at FROM coverage_receipts')}
    for row in employer.execute('SELECT company_key,payload_json,status,updated_at FROM companies ORDER BY company_key'):
        payload = json.loads(row['payload_json'])
        evidence = payload.get('coverage') or {}
        receipt = receipts.get(row['company_key'], {})
        attempts = evidence.get('method_attempts') or []
        company = payload.get('company') or {}
        emit('coverage', company_id=row['company_key'], company=company.get('company_name', ''),
             classification=receipt.get('classification') or 'unknown',
             outcome=evidence.get('outcome') or payload.get('outcome') or row['status'],
             status=row['status'], updated_at=row['updated_at'],
             browser_deferred=any(a.get('method', '').startswith('browser_rendered') and a.get('status') == 'deferred' for a in attempts),
             method_attempts=attempts)
    emit('snapshot', source='employer', path=employer_path, started_at=started, finished_at=now(), jobs=count,
         companies=employer.execute('SELECT COUNT(*) FROM companies').fetchone()[0],
         missing_title_fields=employer.execute("SELECT COUNT(*) FROM jobs WHERE COALESCE(json_extract(payload_json,'$.job_title'),json_extract(payload_json,'$.title'),'')='' ").fetchone()[0])
    employer.rollback()
    employer.close()
    linkedin, linkedin_path = opened('/srv/runr/state/active/linkedin/master_linkedin_jobs_state.db')
    started = now()
    count = 0
    for row in linkedin.execute('SELECT linkedin_job_id,job_json,updated_at FROM jobs ORDER BY linkedin_job_id'):
        payload = json.loads(row['job_json'])
        job(payload, 'linkedin', row['linkedin_job_id'], row['updated_at'])
        count += 1
    emit('snapshot', source='linkedin', path=linkedin_path, started_at=started, finished_at=now(), jobs=count)
    # Search-only titles are in the acquisition lifecycle before detail extraction.
    # Collapse repeated search cards by stable LinkedIn job ID, preserving latest
    # observed card and its organization; details above are authoritative when present.
    search_count = 0
    query = '''SELECT s.linkedin_job_id,s.linkedin_company_id,s.card_json,s.run_id
        FROM search_cards s JOIN (
            SELECT linkedin_job_id,MAX(rowid) AS latest FROM search_cards
            WHERE NOT EXISTS (SELECT 1 FROM jobs j WHERE j.linkedin_job_id=search_cards.linkedin_job_id)
            GROUP BY linkedin_job_id
        ) latest ON latest.latest=s.rowid'''
    group_ids = {r['linkedin_company_id']: r['primary_canonical_company_id']
                 for r in linkedin.execute('SELECT linkedin_company_id,primary_canonical_company_id FROM source_company_groups')}
    for row in linkedin.execute(query):
        payload = json.loads(row['card_json'])
        payload['linkedin_company_id'] = row['linkedin_company_id']
        payload['canonical_company_id'] = group_ids.get(row['linkedin_company_id'], '')
        job(payload, 'linkedin_search', row['linkedin_job_id'], row['run_id'])
        search_count += 1
    emit('snapshot', source='linkedin_search', path=linkedin_path, started_at=started, finished_at=now(), jobs=search_count,
         scope='latest unique search-only card per LinkedIn job ID, excluding IDs with persisted details')
    emit('linkedin_coverage', distinct_organizations_scanned=linkedin.execute('SELECT COUNT(DISTINCT linkedin_company_id) FROM company_scans').fetchone()[0])
    linkedin.rollback()
    linkedin.close()
