"""Read-only full published-catalog match audit using the serving evaluator.

Run as root on the VPS. Reports aggregates only; no identities/profile contents.
No AI requests, service stops, or score writes. Percentages are personal to each
saved profile and remain calculated from that profile on customer requests.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from collections import Counter

pid=subprocess.check_output(['systemctl','show','runr-api-candidate.service','-p','MainPID','--value'],text=True).strip()
env=dict(item.split('=',1) for item in Path('/proc/'+pid+'/environ').read_text().split('\0') if '=' in item)
os.environ.update(env)
os.environ['RUNR_SKIP_PROJECT_DOTENV']='1'
serving=Path('/proc/'+pid+'/cwd').resolve()
sys.path.insert(0,str(serving))
from backend.bootstrap import create_backend
from backend.application.profile_job_matching import evaluate_profile_match
app=create_backend(Path(env.get('RUNR_DATA_DIR','/var/lib/runr/customer-candidate-api')),storage_backend='sqlite',initialize_schema=False)
store=app.repositories.personalized_jobs_store
with store._connect() as c:
    head=c.execute('SELECT publication_id FROM acquisition_publication_head WHERE head_id=1').fetchone()[0]
    versions=[r[0] for r in c.execute('''SELECT j.current_version_id FROM acquisition_publication_jobs p
        JOIN canonical_jobs j ON j.canonical_job_id=p.canonical_job_id WHERE p.publication_id=?''',(head,))]
profiles=[app._personalized_jobs_service._saved_matching_profile(u.user_id)
          for u in app.repositories.auth_repository.list_users()]
profiles=[p for p in profiles if p.get('data')]
counts=[Counter() for p in profiles]
started=time.monotonic()
current=0
for offset in range(0,len(versions),250):
    batch=versions[offset:offset+250]
    facts=store.list_profile_job_facts(batch)
    current+=len(facts)
    for index,profile in enumerate(profiles):
        for version in batch:
            result=evaluate_profile_match(facts.get(version),profile)
            score=result.get('score')
            assert score is None or 0<=score<=100
            counts[index][result['state']]+=1
            if score is not None:counts[index]['numeric_percentage']+=1
    if offset%2500==0:print(json.dumps({'checked':min(offset+250,len(versions))}),flush=True)
print(json.dumps({'publication_id':head,'published':len(versions),'current_facts':current,
    'fact_coverage_percent':round(100*current/len(versions),2) if versions else 100,
    'saved_profiles_checked':len(profiles),'profile_outcomes':[dict(c) for c in counts],
    'seconds':round(time.monotonic()-started,2),'provider_calls':0}),flush=True)
