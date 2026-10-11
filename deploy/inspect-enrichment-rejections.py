"""Read bounded cached provider results; never call a provider or expose config."""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.application.catalog_job_filters import validate_classification, ROLES, normalized

catalog = sqlite3.connect('file:/var/lib/runr/customer-candidate-db/backend.sqlite3?mode=ro', uri=True, timeout=10)
catalog.row_factory = sqlite3.Row
ledger = sqlite3.connect('file:/srv/runr/state/nemo-enrichment-usage.sqlite3?mode=ro', uri=True, timeout=10)
for code in ('filter_validation_failed', 'description_output_not_english', 'description_has_no_supported_facts'):
    rows = catalog.execute('''SELECT q.version_id,q.content_hash,j.title,v.description FROM job_enrichment_queue q
        JOIN canonical_jobs j USING(canonical_job_id) JOIN job_posting_versions v USING(version_id)
        WHERE q.error_code=? ORDER BY q.updated_at DESC LIMIT 4''', (code,)).fetchall()
    for row in rows:
        saved = ledger.execute('SELECT response_json FROM version_requests WHERE version_id=? AND content_hash=?', (row['version_id'], row['content_hash'])).fetchone()
        if not saved or not saved[0]:
            continue
        response = json.loads(saved[0])
        job = (response.get('jobs') or [{}])[0]
        print(json.dumps(dict(code=code,title=row['title'],keys=list(response),classification=job,
            role_count=len(job.get('roles') or []),unknown_roles=[r for r in job.get('roles',[]) if r not in ROLES],
            evidence_in_source=normalized(job.get('evidence')) in normalized(row['title']+' '+row['description']),
            items=(response.get('items') or [])[:2]), ensure_ascii=True))
