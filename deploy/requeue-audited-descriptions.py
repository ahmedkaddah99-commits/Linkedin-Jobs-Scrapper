"""Requeue only audited completed versions still current, published and unchanged."""
import argparse,json,sqlite3,os
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--database',required=True)
parser.add_argument('--audit',required=True)
parser.add_argument('--apply',action='store_true')
args=parser.parse_args();os.umask(0o007)
rows=json.loads(Path(args.audit).read_text())['completed_repairs']
c=sqlite3.connect(args.database,timeout=30)
changed=0
for offset in range(0,len(rows),100):
 with c:
  for row in rows[offset:offset+100]:
   if args.apply:
    changed+=c.execute('''UPDATE job_enrichment_queue SET state='pending',error_code='english_description_repair',next_attempt_at=''
     WHERE version_id=? AND content_hash=? AND state='completed'
     AND EXISTS(SELECT 1 FROM canonical_jobs j WHERE j.current_version_id=job_enrichment_queue.version_id)
     AND EXISTS(SELECT 1 FROM acquisition_publication_jobs p WHERE p.publication_id=(SELECT publication_id FROM acquisition_publication_head WHERE head_id=1)
         AND p.canonical_job_id=job_enrichment_queue.canonical_job_id)''',(row['version_id'],row['content_hash'])).rowcount
c.close()
print(json.dumps({'audited_candidates':len(rows),'applied':args.apply,'requeued':changed}))
