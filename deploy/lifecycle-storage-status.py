"""Read-only aggregate object and producer-state inventory; no customer content."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import boto3

pid = subprocess.check_output(['systemctl','show','runr-api-candidate','-p','MainPID','--value'], text=True).strip()
env = dict(item.split('=',1) for item in Path('/proc/'+pid+'/environ').read_text().split('\0') if '=' in item)
client = boto3.client('s3', endpoint_url=env['S3_ENDPOINT_URL'], aws_access_key_id=env['S3_ACCESS_KEY_ID'], aws_secret_access_key=env['S3_SECRET_ACCESS_KEY'], region_name=env.get('S3_REGION','auto'))
totals = {}
for page in client.get_paginator('list_objects_v2').paginate(Bucket=env['S3_BUCKET']):
    for obj in page.get('Contents',[]):
        key = obj['Key']
        kind = 'backups' if any(s in key for s in ('backup','checkpoint','recovery/')) else 'application_objects'
        entry = totals.setdefault(kind, {'objects':0,'bytes':0})
        entry['objects'] += 1
        entry['bytes'] += obj['Size']
print(json.dumps({'r2':totals}), flush=True)
for source in ('linkedin','employer'):
    path = Path('/srv/runr/state') / source / ('master_'+source+'_jobs_state.db')
    db = sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    print(json.dumps({'producer':source,'bytes':path.stat().st_size,'tables':tables,
        'job_columns':[r[1] for r in db.execute('PRAGMA table_info(jobs)')],
        'jobs':db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]}), flush=True)
