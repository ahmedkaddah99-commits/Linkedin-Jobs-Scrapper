"""Reconcile captured live evidence; no remote calls or production writes."""
import csv
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from backend.acquisition.job_page_evidence import employer_page_needs_verification, generic_employer_non_job_reason, is_navigation_title


def records(name):
    with gzip.open(OUT / (name+'.jsonl.gz'), 'rt', encoding='utf-8') as stream:
        return [json.loads(line) for line in stream]


head = {r['canonical_job_id'] for r in json.loads((OUT/'head_membership.json').read_text())}
jobs = {r['canonical_job_id']:r for r in records('canonical_jobs')}
unpublished = {k:v for k,v in jobs.items() if v['lifecycle_state']=='active' and k not in head}
tasks = {r['target_id']:r for r in json.loads((OUT/'acquisition_tasks.json').read_text())}
cycles = {r['cycle_id']:r for r in json.loads((OUT/'acquisition_cycles.json').read_text())}
metadata = json.loads((OUT/'metadata.json').read_text())
cycle_id = metadata['head_start']['cycle_id']
latest = {}
for row in records('observation_index'):
    key = row['canonical_job_id']
    if key in unpublished and (key not in latest or (row['observed_at'],row['observation_id'])>(latest[key]['observed_at'],latest[key]['observation_id'])):
        latest[key] = row
observations = {r['canonical_job_id']:r for r in records('unpublished_latest_observations')}
companies = {r['company_id'] for r in json.loads((OUT/'company_ids.json').read_text())}
assert len(unpublished)==20483
assert set(unpublished)==set(latest)==set(observations)
assert all(j['current_version_id'] and j['company_id'] in companies for j in unpublished.values())

hard_gate = {}
for row in json.loads((OUT/'partial_task_job_records.json').read_text()):
    key = row['canonical_job_id']
    record = {**row, 'title':unpublished[key]['title'], 'canonical_url':unpublished[key]['canonical_url'], 'description_text':row['description'], 'location_raw':row['location'], 'application_url':row['apply_url']}
    if row['raw_format']:
        record['source_raw_payload'] = {'format':row['raw_format']}
    hard_gate[key] = generic_employer_non_job_reason(record) if employer_page_needs_verification(record) or is_navigation_title(record) else ''
assert len(hard_gate)==216 and not any(hard_gate.values())

rows = []
for key, job in unpublished.items():
    obs = observations[key]
    target = latest[key]['target_id']
    task = tasks.get(target,{})
    historical = cycles[obs['cycle_id']]
    if obs['cycle_id']==cycle_id:
        cause = 'current_cycle_delivery_not_in_publication'
        assert task['status']=='partial' and task['valid_snapshot']==1 and key in hard_gate
    elif not task:
        cause = 'historical_job_target_outside_current_cycle'
    elif task['status']=='pending':
        cause = 'historical_job_current_target_delivery_pending'
    else:
        cause = 'historical_job_not_redelivered_by_partial_target'
        assert task['status']=='partial'
    rows.append({'canonical_job_id':key,'title':job['title'],'company_id':job['company_id'],'cause':cause,'source_target_id':target,'latest_observation_id':obs['observation_id'],'latest_observation_cycle':obs['cycle_id'],'latest_observation_cycle_status':historical['status'],'latest_observation_cycle_error':historical['error_code'],'current_task_id':task.get('task_id',''),'current_task_status':task.get('status','outside_cycle'),'current_task_valid_snapshot':task.get('valid_snapshot',''),'current_task_jobs_published':task.get('jobs_published',''),'first_seen_at':job['first_seen_at'],'last_seen_at':job['last_seen_at'],'hard_gate_checked':key in hard_gate,'hard_gate_reason':hard_gate.get(key,'')})
with (OUT/'unpublished_jobs.csv').open('w',newline='',encoding='utf-8-sig') as stream:
    writer = csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
summary = {'publication':metadata['head_start'],'catalog_jobs':len(jobs),'published_jobs':len(head),'active_unpublished':len(rows),'causes':dict(Counter(r['cause'] for r in rows)),'latest_observation_cycle_status':dict(Counter(r['latest_observation_cycle_status'] for r in rows)),'latest_observation_cycle_error':dict(Counter(r['latest_observation_cycle_error'] for r in rows)),'missing_company_or_version_or_observation':0,'partial_target_hard_gate_checked':len(hard_gate),'partial_target_hard_gate_blocked':sum(bool(v) for v in hard_gate.values()),'verification':'All 20,483 IDs reconciled exactly once. Current head remained unchanged on read-back. Metadata captured through bounded reads; no cross-table transaction.'}
assert sum(summary['causes'].values())==20483
(OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))
