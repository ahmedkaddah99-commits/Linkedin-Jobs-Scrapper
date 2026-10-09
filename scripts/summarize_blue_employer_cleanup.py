"""Read-only final operation status, including explicit incomplete catalog work."""
import json
import sys
from datetime import datetime,timezone
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from scripts.snapshot_title_collar_audit import query
OUT=ROOT/'data/audit/blue_employer_cleanup_2026-10-09'
load_dotenv(ROOT/'user_config/.env')
policy=json.loads((OUT/'employer-exclusions.json').read_text())
ids=json.dumps(policy['company_ids'])
plan=json.loads((OUT/'deletion_plan.json').read_text())
producers=json.loads((OUT/'producer-cleanup.json').read_text())
live=query('SELECT COUNT(*) AS n FROM canonical_jobs WHERE company_id IN (SELECT value FROM json_each(?))',[ids])[0]['n']
published=query('SELECT COUNT(*) AS n FROM acquisition_publication_jobs p JOIN canonical_jobs j ON j.canonical_job_id=p.canonical_job_id WHERE p.publication_id=(SELECT publication_id FROM acquisition_publication_head WHERE head_id=1) AND j.company_id IN (SELECT value FROM json_each(?))',[ids])[0]['n']
result={'as_of_utc':datetime.now(timezone.utc).isoformat(),'status':'incomplete_active_producer_cleanup_unverified',
    'selected_employers':555,'original_scope_employers_not_excluded':70,
    'producer_job_rows_deleted':sum(r['jobs'] for r in producers.values()),
    'default_path_producer_remaining_selected_jobs':json.loads((OUT/'policy-verification.json').read_text())['remaining_selected_producer_jobs'],
    'active_producer_cleanup_verified':False,
    'producer_path_correction':'Cleanup receipts cover /srv/runr/state/{source}; live services use /srv/runr/state/active/{source}, which resolves to different databases.',
    'live_catalog_jobs_for_selected_employers':live,'currently_published_selected_jobs':published,
    'planned_catalog_deletions':len(plan['delete_job_ids']),'protected_user_referenced_jobs':len(plan['protected_job_ids']),
    'catalog_deletions_applied':False,'catalog_policy_rows':query('SELECT COUNT(*) AS n FROM employer_acquisition_exclusions')[0]['n'],
    'catalog_owner_insert_guards':query("SELECT COUNT(*) AS n FROM sqlite_master WHERE type='trigger' AND name LIKE 'owner_excluded_%'")[0]['n'],
    'catalog_backup_status':'verified_complete' if (OUT/'catalog-backup-verification.json').exists() else 'read_only_backup_in_progress',
    'last_observed_write_blocker':'Shared catalog HTTP and native write transactions stalled/timed out. No catalog purge was attempted. Read-back alone does not retest write availability.'}
(OUT/'execution_summary.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
