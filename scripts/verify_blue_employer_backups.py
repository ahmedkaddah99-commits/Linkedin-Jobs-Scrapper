"""Verify producer backup scope and row totals against successful cleanup receipts."""
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path
OUT=Path(__file__).resolve().parents[1]/'data/audit/blue_employer_cleanup_2026-10-09'
ids=set(json.loads((OUT/'employer-exclusions.json').read_text())['company_ids'])
receipt=json.loads((OUT/'producer-cleanup.json').read_text())
results={}
for source,field in (('linkedin','job_json'),('employer','payload_json')):
    path=OUT/f'{source}-deleted-jobs.jsonl.gz'; counts=Counter()
    with gzip.open(path,'rt',encoding='utf-8') as stream:
        for line in stream:
            record=json.loads(line); counts[record['table']]+=1
            if record['table']=='jobs':
                payload=json.loads(record['row'][field])
                assert (payload.get('canonical_company_id') or payload.get('canonical_CompanyID')) in ids
    assert counts['jobs']==receipt[source]['jobs']
    for table,count in receipt[source]['additional_rows'].items(): assert counts[table]==count
    results[source]={'counts':dict(counts),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'verified':True}
(OUT/'producer-backup-verification.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results))
