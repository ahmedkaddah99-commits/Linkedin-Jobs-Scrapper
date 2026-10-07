"""VPS acquisition companion: bounded, provider-free matching-fact projection.

Polls the shared published catalog and enrichment changes. Only the changed
versions are written, in batches; no customer/profile data reaches this worker.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.application.profile_job_matching import FEATURE_VERSION, build_job_facts
from backend.config import load_project_dotenv
from scripts.process_catalog_enrichment import execute, now

SIGNATURE = "COALESCE(d.updated_at,'') || '|' || COALESCE(f.generated_at,'') || '|' || COALESCE(json_extract(p.profile_json,'$.fields.industry'),'')"
JOINS = """FROM canonical_jobs j
    JOIN job_posting_versions v ON v.version_id=j.current_version_id
    LEFT JOIN job_description_intelligence d ON d.version_id=v.version_id AND d.content_hash=v.content_hash
    LEFT JOIN job_filter_intelligence f ON f.version_id=v.version_id AND f.content_hash=v.content_hash
    LEFT JOIN canonical_company_profiles p ON p.company_id=j.company_id"""
PUBLISHED = "EXISTS (SELECT 1 FROM acquisition_publication_jobs pj JOIN acquisition_publication_head h ON h.publication_id=pj.publication_id JOIN acquisition_publications pub ON pub.publication_id=h.publication_id WHERE h.head_id=1 AND pj.canonical_job_id=j.canonical_job_id AND pub.status='valid')"
QUEUED_JOINS = JOINS.replace("FROM canonical_jobs j\n    JOIN job_posting_versions v ON v.version_id=j.current_version_id",
    "FROM profile_job_fact_queue q CROSS JOIN job_posting_versions v ON v.version_id=q.version_id CROSS JOIN canonical_jobs j ON j.canonical_job_id=v.canonical_job_id AND j.current_version_id=v.version_id")


def write_batch(rows):
    inputs = [{**{key: row[key] for key in ('version_id', 'canonical_job_id', 'content_hash', 'input_signature', 'queued_revision')},
               'facts_json': json.dumps(build_job_facts(row), ensure_ascii=False)} for row in rows]
    payload = json.dumps(inputs, ensure_ascii=False)
    receipts = json.dumps([{key: item[key] for key in ("version_id", "queued_revision", "input_signature")} for item in inputs])
    joins = JOINS.replace('FROM canonical_jobs j',
        "FROM json_each(?) i CROSS JOIN canonical_jobs j ON j.canonical_job_id=json_extract(i.value,'$.canonical_job_id')")
    insert = f"""INSERT INTO profile_job_facts
        (version_id,canonical_job_id,content_hash,feature_version,input_signature,facts_json,updated_at)
        SELECT v.version_id,j.canonical_job_id,v.content_hash,?,json_extract(i.value,'$.input_signature'),
            json_extract(i.value,'$.facts_json'),? {joins}
        WHERE v.version_id=json_extract(i.value,'$.version_id') AND v.content_hash=json_extract(i.value,'$.content_hash')
        AND ({SIGNATURE})=json_extract(i.value,'$.input_signature')
        AND EXISTS(SELECT 1 FROM profile_job_fact_queue q WHERE q.version_id=v.version_id
                   AND q.revision=json_extract(i.value,'$.queued_revision'))
        ON CONFLICT(version_id) DO UPDATE SET content_hash=excluded.content_hash,
        feature_version=excluded.feature_version,input_signature=excluded.input_signature,
        facts_json=excluded.facts_json,updated_at=excluded.updated_at"""
    acknowledge = """DELETE FROM profile_job_fact_queue
        WHERE version_id IN (SELECT json_extract(value,'$.version_id') FROM json_each(?))
        AND EXISTS(SELECT 1 FROM json_each(?) i JOIN profile_job_facts m ON m.version_id=profile_job_fact_queue.version_id
            WHERE json_extract(i.value,'$.version_id')=profile_job_fact_queue.version_id
            AND json_extract(i.value,'$.queued_revision')=profile_job_fact_queue.revision
            AND m.input_signature=json_extract(i.value,'$.input_signature'))"""
    def statement(sql, args=()):
        return {'type': 'execute', 'stmt': {'sql': sql, 'args': [{'type': 'text', 'value': str(v)} for v in args], 'want_rows': False}}
    requests = [statement(insert, [FEATURE_VERSION, now(), payload]),
                statement(acknowledge, [receipts, receipts]), {'type': 'close'}]
    url = os.environ['TURSO_DATABASE_URL'].replace('libsql://', 'https://').rstrip('/') + '/v2/pipeline'
    request = Request(url, data=json.dumps({'requests': requests}).encode(), headers={
        'Authorization': 'Bearer ' + os.environ['TURSO_AUTH_TOKEN'], 'Content-Type': 'application/json'})
    with urlopen(request, timeout=30) as response:
        results = json.load(response)['results']
    if any(r.get('type') != 'ok' for r in results):
        raise RuntimeError('profile_facts_batch_failed')
    return int(results[0].get('response', {}).get('result', {}).get('affected_row_count', 0))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-jobs', type=int, default=4096)
    parser.add_argument('--runtime-seconds', type=int, default=180)
    parser.add_argument('--batch-size', type=int, default=100)
    parser.add_argument('--status', action='store_true')
    args = parser.parse_args()
    load_project_dotenv()
    if args.status:
        rows = execute(f"""SELECT COUNT(*) AS published,
            SUM(CASE WHEN m.feature_version=? AND m.content_hash=v.content_hash AND m.input_signature=({SIGNATURE}) THEN 1 ELSE 0 END) AS current_facts
            {JOINS} LEFT JOIN profile_job_facts m ON m.version_id=v.version_id WHERE {PUBLISHED}""", [FEATURE_VERSION])
        print(json.dumps(rows))
        return
    started, processed, written = time.monotonic(), 0, 0
    # Superseded or unpublished versions cannot block current queue work.
    execute(f"""DELETE FROM profile_job_fact_queue WHERE version_id IN (
        SELECT q.version_id FROM (SELECT version_id FROM profile_job_fact_queue ORDER BY version_id LIMIT 100) q
        LEFT JOIN job_posting_versions v ON v.version_id=q.version_id
        LEFT JOIN canonical_jobs j ON j.canonical_job_id=v.canonical_job_id
        WHERE j.canonical_job_id IS NULL OR j.current_version_id!=q.version_id OR NOT ({PUBLISHED}) LIMIT 100)""")
    while processed < args.max_jobs and time.monotonic() - started < args.runtime_seconds:
        rows = execute(f"""SELECT j.canonical_job_id,j.title,v.version_id,v.content_hash,v.description,
            json_object('industry',COALESCE(json_extract(v.payload_json,'$.industry'),json_extract(v.payload_json,'$.company_industry'))) AS payload_json,
            d.summary_json,f.filters_json,json_object('fields',json_object('industry',json_extract(p.profile_json,'$.fields.industry'))) AS company_profile_json,
            q.revision AS queued_revision, ({SIGNATURE}) AS input_signature {QUEUED_JOINS}
            WHERE {PUBLISHED} ORDER BY q.version_id LIMIT ?""", [min(max(1, args.batch_size), 100, args.max_jobs - processed)])
        if not rows:
            break
        written += write_batch(rows)
        processed += len(rows)
    print(json.dumps({'feature_version': FEATURE_VERSION, 'processed': processed, 'written': written,
                      'seconds': round(time.monotonic() - started, 3), 'provider_calls': 0}))


if __name__ == '__main__':
    main()
