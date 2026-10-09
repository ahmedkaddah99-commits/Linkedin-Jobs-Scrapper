"""Bounded producer maintenance under collector/publisher locks; backups first."""
import argparse
import fcntl
import gzip
import json
import sqlite3
import signal
from pathlib import Path

ROOT = Path('/srv/runr/ops/blue-employer-cleanup-2026-10-09')
POLICY = Path('/etc/runr/employer-exclusions.json')


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--apply',action='store_true'); args=parser.parse_args()
    ids = json.loads(POLICY.read_text())['company_ids']
    signal.alarm(1800)
    locks=[]
    for name in ('publisher','employer','linkedin'):
        stream=open(f'/srv/runr/state/locks/{name}.lock','a'); fcntl.flock(stream,fcntl.LOCK_EX); locks.append(stream)
        print(json.dumps({'cleanup_lock_acquired':name}),flush=True)
    receipt={}
    for source,field,key in [('linkedin','job_json','linkedin_job_id'),('employer','payload_json','source_key')]:
        path=Path(f'/srv/runr/state/{source}/master_{source}_jobs_state.db').resolve(strict=True)
        c=sqlite3.connect(path); c.row_factory=sqlite3.Row
        schemas=[dict(r) for r in c.execute("SELECT name,sql FROM sqlite_master WHERE type='table'")]
        matches=[]
        for row in c.execute(f'SELECT * FROM jobs'):
            payload=json.loads(row[field]); company=payload.get('canonical_company_id') or payload.get('canonical_CompanyID')
            if company in ids: matches.append(dict(row))
        receipt[source]={'path':str(path),'jobs':len(matches),'tables':schemas}
        extras={}
        orgs=[]
        if source=='linkedin':
            orgs=[r['linkedin_company_id'] for r in c.execute('SELECT * FROM source_company_groups') if r['primary_canonical_company_id'] in ids]
            encoded=json.dumps(orgs)
            for table in ('search_cards','detail_queue','job_company_observations'):
                extras[table]=[dict(r) for r in c.execute(f'SELECT * FROM {table} WHERE linkedin_company_id IN (SELECT value FROM json_each(?))',(encoded,))]
            job_ids=json.dumps([r[key] for r in matches])
            extras['detail_attempts']=[dict(r) for r in c.execute('SELECT * FROM detail_attempts WHERE linkedin_job_id IN (SELECT value FROM json_each(?))',(job_ids,))]
        receipt[source]['additional_rows']={t:len(rows) for t,rows in extras.items()}
        if args.apply:
            backup=ROOT/f'{source}-deleted-jobs.jsonl.gz'
            if backup.exists(): raise RuntimeError('Existing producer backup: refuse overwrite')
            with gzip.open(backup,'wt',encoding='utf-8') as f:
                for row in matches: f.write(json.dumps({'table':'jobs','row':row},ensure_ascii=False)+'\n')
                for table,rows in extras.items():
                    for row in rows: f.write(json.dumps({'table':table,'row':row},ensure_ascii=False)+'\n')
            # Only job rows are removed; employer/company and coverage records stay.
            with c:
                c.execute('CREATE TABLE IF NOT EXISTS employer_acquisition_exclusions(company_id TEXT PRIMARY KEY, reason TEXT NOT NULL)')
                c.executemany('INSERT OR IGNORE INTO employer_acquisition_exclusions VALUES (?,?)',[(i,'owner_blue_collar_employer_exclusion') for i in ids])
                if source=='linkedin':
                    for table in ('search_cards','detail_queue','job_company_observations'):
                        c.execute(f'DELETE FROM {table} WHERE linkedin_company_id IN (SELECT value FROM json_each(?))',(encoded,))
                    c.execute('DELETE FROM detail_attempts WHERE linkedin_job_id IN (SELECT value FROM json_each(?))',(job_ids,))
                c.executemany(f'DELETE FROM jobs WHERE {key}=?',[(r[key],) for r in matches])
            receipt[source]['remaining_selected_jobs']=sum(1 for r in c.execute(f'SELECT {field} FROM jobs')
                if (json.loads(r[0]).get('canonical_company_id') or json.loads(r[0]).get('canonical_CompanyID')) in ids)
            assert receipt[source]['remaining_selected_jobs']==0
        c.close()
    ROOT.mkdir(parents=True,exist_ok=True)
    (ROOT/('producer-cleanup.json' if args.apply else 'producer-plan.json')).write_text(json.dumps(receipt,indent=2))
    print(json.dumps({k:{f:v for f,v in r.items() if f!='tables'} for k,r in receipt.items()}))

if __name__=='__main__': main()
