"""Read-only job counts in audit and default producer paths; run on VPS."""
import json
import sqlite3
from pathlib import Path

ids = json.loads(Path('/etc/runr/employer-exclusions.json').read_text())['company_ids']
results = []
for source, field in [('linkedin', 'job_json'), ('employer', 'payload_json')]:
    for base in ['/srv/runr/state', '/srv/runr/state/active']:
        path = Path(base) / source / f'master_{source}_jobs_state.db'
        connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
        connection.execute('PRAGMA query_only=ON')
        count = connection.execute(
            f"SELECT COUNT(*) FROM jobs WHERE COALESCE(json_extract({field},'$.canonical_company_id'),json_extract({field},'$.canonical_CompanyID'),'') IN (SELECT value FROM json_each(?))",
            [json.dumps(ids)],
        ).fetchone()[0]
        results.append({'source': source, 'path': str(path), 'resolved': str(path.resolve()), 'selected_jobs': count})
        connection.close()
print(json.dumps(results, indent=2))
