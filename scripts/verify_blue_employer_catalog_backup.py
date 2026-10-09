"""Verify a completed catalog backup before any destructive maintenance."""
import gzip
import hashlib
import json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
OUT=Path(__file__).resolve().parents[1]/'data/audit/blue_employer_cleanup_2026-10-09'
path=OUT/'catalog-deleted-rows-v5.jsonl.gz'
plan=json.loads((OUT/'deletion_plan.json').read_text())
expected=json.loads((OUT/'catalog-backup-counts.json').read_text())
scope=set(plan['delete_job_ids']); counts=Counter(); ids={name:set() for name in ('canonical_jobs','job_posting_versions','job_source_observations')}
keys={'canonical_jobs':'canonical_job_id','job_posting_versions':'version_id','job_source_observations':'observation_id'}
with gzip.open(path,'rt',encoding='utf-8') as f:
    for line in f:
        record=json.loads(line); table=record['table']; row=record['row']; counts[table]+=1
        if table in ids:
            assert row['canonical_job_id'] in scope
            assert row[keys[table]] not in ids[table]
            ids[table].add(row[keys[table]])
for table,count in expected.items():
    if table not in ('acquisition_publication_head','acquisition_publications'):
        assert counts[table]==count,(table,counts[table],count)
assert ids['canonical_jobs']==scope
assert counts['canonical_jobs']==6154
assert counts['job_posting_versions']==6155
assert counts['job_source_observations']==9205
with path.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
result={'verified_at_utc':datetime.now(timezone.utc).isoformat(),'backup':path.name,'gzip_integrity':True,
        'valid_json_rows':sum(counts.values()),'canonical_scope_verified':True,'counts':dict(counts),'sha256':digest,'bytes':path.stat().st_size,
        'scope_sha256':hashlib.sha256(json.dumps(sorted(plan['delete_job_ids'])).encode()).hexdigest()}
(OUT/'catalog-backup-verification.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='counts'}))
