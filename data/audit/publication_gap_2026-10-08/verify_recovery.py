"""Read-only verification of actual head membership and durable queue outcomes."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from dotenv import load_dotenv
from capture import base_query as query
load_dotenv(ROOT/'user_config/.env')
result={'checked_at':datetime.now(timezone.utc).isoformat()}
result['head']=query('''SELECT h.publication_id,h.updated_at,p.policy_version,
 (SELECT COUNT(*) FROM acquisition_publication_jobs a WHERE a.publication_id=h.publication_id) AS membership,
 json_array_length(p.snapshot_json) AS snapshot_rows
 FROM acquisition_publication_head h JOIN acquisition_publications p USING(publication_id) WHERE h.head_id=1''')
result['queue']=query('SELECT status,COUNT(*) AS jobs,MAX(evaluated_at) AS last_evaluated_at FROM acquisition_publication_queue GROUP BY status')
result['unpublished']=query('''SELECT COALESCE(q.status,'missing_queue') AS outcome,
 COALESCE(q.reason_codes_json,'[]') AS reasons,COUNT(*) AS jobs FROM canonical_jobs j
 LEFT JOIN acquisition_publication_queue q USING(canonical_job_id)
 WHERE j.lifecycle_state='active' AND NOT EXISTS(SELECT 1 FROM acquisition_publication_jobs a
 JOIN acquisition_publication_head h USING(publication_id) WHERE h.head_id=1 AND a.canonical_job_id=j.canonical_job_id)
 GROUP BY outcome,reasons''')
result['checkpoints']=query('SELECT source,source_rowid,source_watermark,bootstrap_complete,updated_at FROM acquisition_publisher_checkpoints ORDER BY source')
result['latest_cycles']=query('SELECT cycle_id,status,error_code,jobs_observed,jobs_published,started_at,updated_at FROM acquisition_cycles ORDER BY started_at DESC LIMIT 3')
result['head_end']=query('SELECT publication_id,updated_at FROM acquisition_publication_head WHERE head_id=1')
result['head_stable_during_check']=all(result['head'][0][key]==result['head_end'][0][key] for key in ('publication_id','updated_at'))
dest=Path(__file__).with_name('recovery_verification_latest.json')
dest.write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
