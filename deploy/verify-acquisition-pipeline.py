"""Read current pipeline coverage and exercise the serving API's customer projection.

Run as root on the VPS. Prints public job IDs and aggregate checks, never
configuration values or customer data. This does not replace browser acceptance.
"""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--since',required=True)
args=parser.parse_args()
pid=subprocess.check_output(['systemctl','show','runr-api-candidate.service','-p','MainPID','--value'],text=True).strip()
env=dict(item.split('=',1) for item in Path('/proc/'+pid+'/environ').read_text().split('\0') if '=' in item)
os.environ.update(env)
os.environ['RUNR_SKIP_PROJECT_DOTENV']='1'
serving=Path('/proc/'+pid+'/cwd').resolve()
sys.path.insert(0,str(serving))
db=sqlite3.connect('file:'+env['SQLITE_DATABASE_PATH']+'?mode=ro',uri=True,timeout=10)
db.row_factory=sqlite3.Row
head="(SELECT publication_id FROM acquisition_publication_head WHERE head_id=1)"
published="EXISTS(SELECT 1 FROM acquisition_publication_jobs pj WHERE pj.publication_id="+head+" AND pj.canonical_job_id=j.canonical_job_id)"
for name,sql in {
    'head': 'SELECT h.publication_id,p.status FROM acquisition_publication_head h JOIN acquisition_publications p USING(publication_id)',
    'enrichment_queue': 'SELECT state,error_code,COUNT(*) AS jobs FROM job_enrichment_queue GROUP BY state,error_code',
    'profile_fact_queue': 'SELECT COUNT(*) AS jobs FROM profile_job_fact_queue',
    'fresh_published': "SELECT COUNT(*) AS jobs FROM canonical_jobs j JOIN job_posting_versions v ON v.version_id=j.current_version_id WHERE j.last_seen_at>=? AND "+published,
}.items():
    params=(args.since,) if '?' in sql else ()
    print(json.dumps({name:[dict(row) for row in db.execute(sql,params)]}),flush=True)
rows=db.execute('''SELECT j.canonical_job_id,j.company_id,v.version_id,v.content_hash,f.filters_json,
    d.summary_json,d.original_json,j.last_seen_at,
    CASE WHEN m.input_signature=(COALESCE(d.updated_at,'') || '|' || COALESCE(f.generated_at,'') || '|' || COALESCE(json_extract(p.profile_json,'$.fields.industry'),'')) THEN m.version_id END AS facts_version
    FROM canonical_jobs j JOIN job_posting_versions v ON v.version_id=j.current_version_id
    JOIN job_filter_intelligence f ON f.version_id=v.version_id AND f.content_hash=v.content_hash
    JOIN job_description_intelligence d ON d.version_id=v.version_id AND d.content_hash=v.content_hash
    LEFT JOIN profile_job_facts m ON m.version_id=v.version_id AND m.content_hash=v.content_hash
    LEFT JOIN canonical_company_profiles p ON p.company_id=j.company_id
    WHERE j.lifecycle_state<>'expired' AND (d.generated_at>=? OR j.last_seen_at>=?) AND '''+published+'''
    ORDER BY j.last_seen_at DESC,d.generated_at DESC LIMIT 8''',(args.since,args.since)).fetchall()
from backend.bootstrap import create_backend
from backend.application.description_translation import source_language
app=create_backend(Path(env.get('RUNR_DATA_DIR','/var/lib/runr/customer-candidate-api')),storage_backend='sqlite',initialize_schema=False)
users=app.repositories.auth_repository.list_users()
if not users:
    raise RuntimeError('No real user exists for customer projection verification')
checked=0
for row in rows:
    filters=json.loads(row['filters_json'])
    if filters.get('collar')=='blue' or not filters.get('roles'):
        continue
    detail=app.get_personalized_job_detail(users[0].user_id,row['canonical_job_id'])
    if detail is None:
        continue
    summary=detail.get('runr_summary') or {}
    text=' '.join([str(summary.get('overview') or '')]+[item['text'] for value in summary.values() if isinstance(value,list)
                  for item in value if isinstance(item,dict) and isinstance(item.get('text'),str)])
    source=(detail.get('original_posting') or {}).get('description_text')
    assert text and source, 'Customer summary or original evidence missing'
    assert len(text)<80 or source_language(text)=='en', 'Customer description is not English'
    feed=app._personalized_jobs_service.feed(users[0].user_id,filters={
        'role':filters['roles'][0],'company_id':row['company_id']},limit=20)
    assert feed.get('jobs'), 'Combined function/company filter returned no jobs'
    print(json.dumps({'customer_projection':{'job_id':row['canonical_job_id'],
        'english':True,'source_evidence':True,'facts_current':bool(row['facts_version']),
        'freshly_observed':row['last_seen_at']>=args.since,
        'combined_filter_jobs':len(feed['jobs'])}}),flush=True)
    checked+=1
print(json.dumps({'serving_release':env.get('RUNR_RELEASE_COMMIT'),'customer_projections_checked':checked,
                  'browser_acceptance':False}),flush=True)
if not checked:
    raise SystemExit(2)
