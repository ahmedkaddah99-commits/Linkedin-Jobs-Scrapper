"""Read-only current publication link projection and publication history."""
import json
import subprocess
import sys
from pathlib import Path


def remote():
    import os
    from collections import Counter
    sys.path.insert(0, '/opt/runr')
    for path in ['/opt/runr/.env.acquisition', '/etc/runr/acquisition-catalog.env']:
        for line in Path(path).read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip().strip(chr(34)).strip(chr(39))
    from backend.database.connection import connect_database
    from backend.application.personalized_jobs_service import _approved_apply_url
    conn = connect_database(Path('/nonexistent/audit.sqlite3'))
    def rows(sql):
        return [dict(row) for row in conn.execute(sql).fetchall()]
    published = rows("""SELECT j.lifecycle_state, c.provenance_url AS company_provenance_url,
        v.apply_url, v.payload_json AS version_payload_json,
        p.logo_object_key, p.logo_source_url,
        (SELECT o.source_ats FROM job_source_observations o
         WHERE o.canonical_job_id=j.canonical_job_id ORDER BY o.observed_at DESC LIMIT 1) AS source_ats,
        (SELECT o.original_url FROM job_source_observations o
         WHERE o.canonical_job_id=j.canonical_job_id ORDER BY o.observed_at DESC LIMIT 1) AS observation_url
        FROM acquisition_publication_jobs a
        JOIN acquisition_publication_head h ON h.publication_id=a.publication_id AND h.head_id=1
        JOIN canonical_jobs j ON j.canonical_job_id=a.canonical_job_id
        JOIN job_posting_versions v ON v.version_id=j.current_version_id
        JOIN canonical_companies c ON c.company_id=j.company_id
        LEFT JOIN canonical_company_profiles p ON p.company_id=j.company_id""")
    counts = Counter()
    for row in published:
        payload = json.loads(row['version_payload_json'] or '{}')
        counts['published'] += 1
        counts['approved_apply_url'] += bool(_approved_apply_url(row))
        counts['raw_apply_url_present'] += bool(row['apply_url'])
        counts['logo_object_key_present'] += bool(row['logo_object_key'])
        counts['logo_source_url_present'] += bool(row['logo_source_url'])
        counts['lifecycle_' + row['lifecycle_state']] += 1
        counts['destination_' + str((payload.get('application_destination') or {}).get('status', 'absent'))] += 1
    history = rows("""SELECT p.published_at,p.status,COUNT(a.canonical_job_id) AS jobs
        FROM acquisition_publications p LEFT JOIN acquisition_publication_jobs a
        ON a.publication_id=p.publication_id GROUP BY p.publication_id
        ORDER BY p.published_at DESC LIMIT 12""")
    conn.close()
    print(json.dumps({'head_link_projection': dict(counts), 'publication_history': history}))


if __name__ == '__main__':
    if '--remote' in sys.argv:
        remote()
    else:
        result = subprocess.run(['ssh', 'runr-vps', 'sudo /opt/runr/.venv/bin/python - --remote'],
            input=Path(__file__).read_bytes(), capture_output=True, timeout=180)
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors='replace')[-1500:])
        report = json.loads(result.stdout)
        target = Path('data/audit/current_pipeline_2026-09-28/publication_links.json')
        target.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
