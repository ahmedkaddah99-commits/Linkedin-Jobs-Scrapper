"""Audit every current published German posting without provider calls."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.application.description_translation import source_language
from backend.application.vps_job_descriptions import SECTIONS, _quoted_passage_ids, pilot_passages

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--database',required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args()
c=sqlite3.connect('file:'+args.database+'?mode=ro',uri=True,timeout=30);c.row_factory=sqlite3.Row
head=c.execute('SELECT publication_id FROM acquisition_publication_head WHERE head_id=1').fetchone()[0]
rows=c.execute('''SELECT j.canonical_job_id,v.version_id,v.content_hash,v.description,d.summary_json,d.original_json,d.structured_json,d.prompt_version,q.state
 FROM acquisition_publication_jobs p JOIN canonical_jobs j ON j.canonical_job_id=p.canonical_job_id
 JOIN job_posting_versions v ON v.version_id=j.current_version_id
 LEFT JOIN job_description_intelligence d ON d.version_id=v.version_id AND d.content_hash=v.content_hash
 LEFT JOIN job_enrichment_queue q ON q.version_id=v.version_id WHERE p.publication_id=?''',(head,)).fetchall()
c.close()
counts=Counter();errors=[];started=time.monotonic()
for i,row in enumerate(rows):
 source=row['description'] or ''
 if len(source)<80:counts['source_missing_or_short']+=1;continue
 if source_language(source[:12000])!='de':continue
 counts['german_postings']+=1
 counts['german_queue_'+str(row['state'])]+=1
 summary=json.loads(row['summary_json'] or '{}')
 facts=[f for section in SECTIONS for f in summary.get(section,[]) if isinstance(f,dict) and isinstance(f.get('text'),str)]
 text=' '.join(f['text'] for f in facts)
 reason=[]
 if not facts:counts['german_without_description_facts']+=1;reason.append('missing_facts')
 elif source_language(text)!='en':counts['german_non_english_description']+=1;reason.append('non_english')
 else:counts['german_english_description']+=1
 if row['prompt_version']=='runr_description_nemo_v3':
  passages=json.loads(row['structured_json'] or '{}').get('source_passages') or pilot_passages(source)
  lookup={p['id']:p.get('original_text') or p['text'] for p in passages}
  invalid=sum(not _quoted_passage_ids(f.get('source_quote'),lookup) for f in facts)
  counts['grounded_facts_checked']+=len(facts);counts['invalid_fact_quotes']+=invalid
  if invalid:reason.append('invalid_source_quote')
 if reason and row['state']=='completed':
  counts['completed_german_needing_repair']+=1
  errors.append({'version_id':row['version_id'],'content_hash':row['content_hash'],'canonical_job_id':row['canonical_job_id'],'reasons':reason})
 if i%1000==0:print(json.dumps({'checked':i,'german':counts['german_postings']}),flush=True)
receipt={'publication_id':head,'published':len(rows),'counts':dict(counts),'completed_repairs':errors,'seconds':round(time.monotonic()-started,2)}
Path(args.output).write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in receipt.items() if k!='completed_repairs'}),flush=True)
