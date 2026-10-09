"""Read-only job scope, application-history protection, and dependency backup."""
import gzip
import json
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.snapshot_title_collar_audit import query
OUT = ROOT / 'data/audit/blue_employer_cleanup_2026-10-09'


def strings(value):
    if isinstance(value, str):
        yield value
        if value.startswith(('{','[')):
            try: yield from strings(json.loads(value))
            except ValueError: pass
    elif isinstance(value, dict):
        for item in value.values(): yield from strings(item)
    elif isinstance(value, list):
        for item in value: yield from strings(item)


def main():
    load_dotenv(ROOT / 'user_config/.env')
    ids = json.loads((OUT / 'employer-exclusions.json').read_text())['company_ids']
    refs = set()
    for table in ('reviews','application_packages','run_jobs','run_job_sets','run_blobs','generation_provenance',
                  'personalized_job_dispositions','personalized_job_events','personalized_job_evaluations','job_intelligence_cache'):
        for row in query(f'SELECT * FROM {table}'):
            refs.update(strings(row))
    jobs = []
    for start in range(0,len(ids),50):
        batch = ids[start:start+50]
        jobs.extend(query('SELECT * FROM canonical_jobs WHERE company_id IN ('+','.join('?' for _ in batch)+')',batch))
    protected = set()
    for start in range(0,len(jobs),100):
        batch = [j['canonical_job_id'] for j in jobs[start:start+100]]
        marks = ','.join('?' for _ in batch)
        for table, field in [('canonical_job_external_ids','external_job_id'),('canonical_job_url_aliases','url')]:
            for row in query(f'SELECT canonical_job_id,{field} FROM {table} WHERE canonical_job_id IN ({marks})',batch):
                if row[field] in refs: protected.add(row['canonical_job_id'])
    for job in jobs:
        if job['canonical_job_id'] in refs or job['canonical_url'] and job['canonical_url'] in refs:
            protected.add(job['canonical_job_id'])
    plan = {'selected_employers':len(ids),'live_jobs':len(jobs),'protected_job_ids':sorted(protected),
            'delete_job_ids': sorted(j['canonical_job_id'] for j in jobs if j['canonical_job_id'] not in protected),
            'jobs':jobs, 'production_changes':False}
    (OUT/'deletion_plan.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
    print(json.dumps({'live_jobs':len(jobs),'protected':len(protected),'to_delete':len(plan['delete_job_ids'])}))

if __name__ == '__main__': main()
