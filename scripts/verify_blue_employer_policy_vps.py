"""Read-only installed policy verification; no requests to employer sites."""
import json
import subprocess
import sys
import sqlite3
import hashlib
from pathlib import Path

policy=json.loads(Path('/etc/runr/employer-exclusions.json').read_text())
ids=set(policy['company_ids'])
manifest=json.loads(Path('/srv/runr/shared/inputs/manifest-generations/active/SOURCE_ELIGIBILITY_MANIFEST.json').read_text())
raw_counts={s:sum(t.get('canonical_company_id') in ids and t.get('source')==s for t in manifest['tasks']) for s in ('linkedin','employer_site')}
services={}
for source in ('linkedin','employer','publisher','catalog-publication'):
    unit=f'runr-acquisition-{source}.service' if source!='catalog-publication' else 'runr-catalog-publication.service'
    release=Path(subprocess.check_output(['systemctl','show',unit,'-p','WorkingDirectory','--value'],text=True).strip())
    assert (release/'backend/application/employer_acquisition_policy.py').exists()
    assert 'excluded_company_ids' in (release/'backend/application/source_eligibility_manifest.py').read_text()
    assert 'excluded_company_ids' in (release/'scripts/publish_producer_states.py').read_text()
    assert 'owner_excluded_employer' in (release/'backend/repositories/sqlite_acquisition.py').read_text()
    timer=f'runr-acquisition-{source}.timer' if source!='catalog-publication' else 'runr-catalog-publication.timer'
    services[source]={'release':str(release),'timer_active':subprocess.check_output(['systemctl','is-active',timer],text=True).strip(),
                     'timer_enabled':subprocess.check_output(['systemctl','is-enabled',timer],text=True).strip()}
    services[source]['file_sha256']={name:hashlib.sha256((release/name).read_bytes()).hexdigest() for name in (
        'backend/application/employer_acquisition_policy.py','backend/application/source_eligibility_manifest.py',
        'backend/repositories/sqlite_acquisition.py','scripts/publish_producer_states.py')}
result={'policy_employers':len(ids),'blocked_manifest_tasks':raw_counts,'services':services}
result['remaining_selected_producer_jobs']={}
for source,field in (('linkedin','job_json'),('employer','payload_json')):
    connection=sqlite3.connect(f'file:/srv/runr/state/{source}/master_{source}_jobs_state.db?mode=ro',uri=True)
    result['remaining_selected_producer_jobs'][source]=connection.execute(
        f"SELECT COUNT(*) FROM jobs WHERE COALESCE(json_extract({field},'$.canonical_company_id'),json_extract({field},'$.canonical_CompanyID'),'') IN (SELECT value FROM json_each(?))",(json.dumps(sorted(ids)),)).fetchone()[0]
    connection.close()
Path('/srv/runr/ops/blue-employer-cleanup-2026-10-09/policy-verification.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'policy_employers':len(ids),'blocked_manifest_tasks':raw_counts,'remaining_selected_producer_jobs':result['remaining_selected_producer_jobs'],
                  'effective_service_paths_verified':list(services)}))
