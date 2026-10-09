"""Read-only live dependency inventory and approved corrected employer list."""
import csv
import json
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.snapshot_title_collar_audit import query

OUT = ROOT / 'data/audit/blue_employer_cleanup_2026-10-09'

def main():
    load_dotenv(ROOT / 'user_config/.env')
    rows = list(csv.DictReader((OUT / 'requested_employer_scope.csv').open(encoding='utf-8-sig')))
    selected = [r for r in rows if r['still_above_60_excluding_placeholders'] == 'True']
    with (OUT / 'corrected_employer_scope.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(selected)
    ids = {r['company_id'] for r in selected}
    crosswalk = query('SELECT source_identity_key,winner_company_id FROM company_identity_crosswalk')
    aliases = {r['source_identity_key'].removeprefix('old-company:').removeprefix('canonical:') for r in crosswalk
               if r['winner_company_id'] in ids and r['source_identity_key'].startswith(('old-company:', 'canonical:'))}
    policy = {'schema_version': 1, 'approved_by': 'Ahmed', 'approved_at': '2026-10-09',
              'reason': 'Owner-approved exclusion: corrected blue/(blue+white)>60% within original 625 employers; placeholders excluded.',
              'selected_company_ids': sorted(ids), 'company_ids': sorted(ids | aliases)}
    (OUT / 'employer-exclusions.json').write_text(json.dumps(policy, indent=2), encoding='utf-8')
    tables = query("SELECT name,sql FROM sqlite_master WHERE type='table'")
    relevant = {r['name']: r['sql'] for r in tables if any(w in (r['sql'] or '') for w in ('canonical_job_id','version_id','observation_id'))}
    evidence = {'policy_ids': len(policy['company_ids']), 'selected_employers': len(ids), 'tables': relevant,
                'triggers': query("SELECT name,sql FROM sqlite_master WHERE type='trigger'"), 'counts': {}}
    for table in ('reviews','application_packages','run_jobs','run_job_sets','personalized_job_dispositions','personalized_job_events','personalized_job_evaluations'):
        evidence['counts'][table] = query(f'SELECT COUNT(*) AS n FROM {table}')[0]['n']
    (OUT / 'dependency_inventory.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print(json.dumps({'selected':len(ids),'policy_ids':len(policy['company_ids']),'user_reference_counts':evidence['counts']}))

if __name__ == '__main__': main()
