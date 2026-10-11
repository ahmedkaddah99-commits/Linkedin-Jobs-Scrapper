"""Read-only, credential-free deployment evidence for acquisition recovery."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess

pid = subprocess.check_output(['systemctl','show','runr-api-candidate','-p','MainPID','--value'], text=True).strip()
env = dict(item.split('=',1) for item in Path('/proc/'+pid+'/environ').read_text().split('\0') if '=' in item)
print(json.dumps({'api_release': env.get('RUNR_RELEASE_COMMIT'), 'database': env.get('SQLITE_DATABASE_PATH'),
                  'storage': env.get('OBJECT_STORAGE_BACKEND')}))
db = sqlite3.connect('file:'+env['SQLITE_DATABASE_PATH']+'?mode=ro', uri=True, timeout=10)
db.row_factory = sqlite3.Row
for name, sql in {
    'migration_tables': "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%migration%'",
    'migration_head': 'SELECT * FROM schema_migrations ORDER BY rowid DESC LIMIT 2',
    'enrichment': 'SELECT state,COUNT(*) AS n FROM job_enrichment_queue GROUP BY state',
    'facts_queue': 'SELECT COUNT(*) AS n FROM profile_job_fact_queue',
    'head': 'SELECT h.*,p.status FROM acquisition_publication_head h JOIN acquisition_publications p USING(publication_id)',
    'published': 'SELECT COUNT(*) AS n FROM acquisition_publication_jobs WHERE publication_id=(SELECT publication_id FROM acquisition_publication_head WHERE head_id=1)',
    'schema_maintenance': "SELECT COUNT(*) AS n FROM sqlite_master WHERE name='runr_catalog_storage_maintenance'",
    'schema_guards': "SELECT name,tbl_name FROM sqlite_master WHERE type='trigger' AND name LIKE '%immutable%'",
}.items():
    print(json.dumps({name:[dict(r) for r in db.execute(sql)]}))
for path in ['/etc/runr/acquisition-catalog.env','/etc/runr/publisher-sqlite.env','/etc/runr/nemo-enrichment.env','/etc/runr/description.env']:
    values = {}
    for line in Path(path).read_text().splitlines():
        if '=' not in line or line.lstrip().startswith('#'): continue
        key,value = line.split('=',1)
        if key in ('DATABASE_BACKEND','SQLITE_DATABASE_PATH','RUNR_MIGRATION_HEAD','RUNR_PROJECT_DIR','RUNR_ENV','OBJECT_STORAGE_BACKEND'):
            values[key] = value
        elif any(x in key for x in ('KEY','TOKEN','SECRET')):
            values[key] = 'present' if value.strip() else 'absent'
    print(json.dumps({'config':path,'values':values}))
