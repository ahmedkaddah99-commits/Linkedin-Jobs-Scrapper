"""Check compact gate inputs against complete stored payloads without printing them."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from dotenv import load_dotenv
load_dotenv(ROOT/'user_config/.env')
from capture import base_query as query
from backend.repositories.sqlite_acquisition import SqliteAcquisitionStore,_publication_payload_sql
from backend.acquisition.publication import get_publication_policy
sql='''SELECT j.*,c.canonical_name AS company,v.description AS version_description,
 v.location AS version_location,v.apply_url,v.payload_json AS full_payload,
 COMPACT AS version_payload_json,o.external_job_id AS source_job_id,o.source_ats,
 o.observed_at AS observation_observed_at,o.target_id AS source_target_id,o.task_id AS source_task_id
 FROM acquisition_publication_queue q JOIN canonical_jobs j USING(canonical_job_id)
 JOIN canonical_companies c USING(company_id) JOIN job_posting_versions v ON v.version_id=j.current_version_id
 LEFT JOIN job_source_observations o ON o.observation_id=(SELECT observation_id FROM job_source_observations
 WHERE canonical_job_id=j.canonical_job_id ORDER BY observed_at DESC,observation_id DESC LIMIT 1)
 WHERE q.status=? ORDER BY q.canonical_job_id LIMIT 100'''.replace('COMPACT',_publication_payload_sql())
rows=query(sql,['rejected'])+query(sql,['published'])
full=[{**r,'version_payload_json':r['full_payload']} for r in rows]
def evaluate(values):
    accepted,rejected=SqliteAcquisitionStore._publication_rows_with_completeness(values,policy=get_publication_policy())
    return {r['canonical_job_id'] for r in accepted},{r['canonical_job_id']:r['reasons'] for r in rejected}
same=evaluate(rows)==evaluate(full)
result={'sample_rows':len(rows),'compact_equals_complete_gate_outcomes':same}
Path(__file__).with_name('gate_projection_verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
if not same:raise SystemExit('Compact gate projection differs from complete stored evidence.')
