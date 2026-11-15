"""Persist successful employer sources and collect only the verified priority list."""
from __future__ import annotations
import argparse,csv,json,sqlite3,sys,hashlib,time,threading,subprocess,re,shutil
from pathlib import Path
from datetime import datetime,timedelta,timezone
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import workbook_employer_dry_run as m
from scripts.master_linkedin_jobs_catalog import load_webshare_proxies
from backend.acquisition.employer_focus import SCOPE_VERSION,review_title_candidate
from scripts.repair_focus_application_links import recover_link
from backend.acquisition.employer_rounds import next_batch, finish_member, summary

def connect(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path);db.row_factory=sqlite3.Row
    db.execute('''CREATE TABLE IF NOT EXISTS priority_employers(source_key TEXT PRIMARY KEY,
        rank TEXT NOT NULL,company_name TEXT NOT NULL,career_url TEXT NOT NULL,
        successful_method TEXT NOT NULL DEFAULT '',usable_jobs INTEGER NOT NULL DEFAULT 0,
        coverage TEXT NOT NULL DEFAULT 'partial',last_success_at TEXT NOT NULL DEFAULT '',
        last_attempt_at TEXT NOT NULL DEFAULT '',next_due_at TEXT NOT NULL DEFAULT '',
        failures INTEGER NOT NULL DEFAULT 0,enabled INTEGER NOT NULL DEFAULT 1,
        evidence_file TEXT NOT NULL DEFAULT '',coverage_limitations TEXT NOT NULL DEFAULT '')''')
    if 'coverage_limitations' not in {r[1] for r in db.execute('PRAGMA table_info(priority_employers)')}:
        db.execute("ALTER TABLE priority_employers ADD COLUMN coverage_limitations TEXT NOT NULL DEFAULT ''")
    if 'source_json' not in {r[1] for r in db.execute('PRAGMA table_info(priority_employers)')}:
        db.execute("ALTER TABLE priority_employers ADD COLUMN source_json TEXT NOT NULL DEFAULT '{}'")
    db.commit();return db

def record_success(db,row,*,jobs,method,coverage,evidence,at,limitations=''):
    if jobs<1:return
    key=hashlib.sha256((row['rank']+'|'+row['career_url']).encode()).hexdigest()
    due=at
    db.execute('''INSERT INTO priority_employers(source_key,rank,company_name,career_url,
        successful_method,usable_jobs,coverage,last_success_at,last_attempt_at,next_due_at,failures,evidence_file,coverage_limitations,source_json)
        VALUES(?,?,?,?,?,?,?,?,?,?,0,?,?,?) ON CONFLICT(source_key) DO UPDATE SET
        successful_method=excluded.successful_method,usable_jobs=excluded.usable_jobs,
        coverage=excluded.coverage,last_success_at=excluded.last_success_at,
        last_attempt_at=excluded.last_attempt_at,next_due_at=excluded.next_due_at,
        failures=0,evidence_file=excluded.evidence_file,coverage_limitations=excluded.coverage_limitations,source_json=excluded.source_json''',
        (key,row['rank'],row['company_name'],row['career_url'],method,jobs,coverage,at,at,due,evidence,limitations,json.dumps(row)));db.commit()

def prepare_source(source,inventory):
    row={**inventory.get(source['rank'],{}),**json.loads(source.get('source_json') or '{}'),
         'rank':source['rank'],'company_name':source['company_name'],'career_url':source['career_url']}
    # Some verified boards need more than 100 requests for listing pagination
    # plus eligible job details. Keep overrides bounded and preserve title gating.
    row['_max_pages']=max(1,min(200,int(row.get('_max_pages',100))))
    row['_business_candidates_only']=True
    return row

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=['seed','observe','run','status'])
    p.add_argument('--registry',type=Path,required=True);p.add_argument('--seed',type=Path)
    p.add_argument('--inventory',type=Path);p.add_argument('--receipt',type=Path)
    p.add_argument('--output',type=Path);p.add_argument('--db',type=Path)
    p.add_argument('--export',type=Path,help='Export the current verified employer registry as CSV')
    p.add_argument('--retain-response-cache',action='store_true',help='Retain transient response bodies for a diagnostic round')
    p.add_argument('--limit',type=int,default=5);a=p.parse_args()
    db=connect(a.registry)
    if a.stage=='seed':
        rows=list(csv.DictReader(a.seed.open(encoding='utf-8-sig')))
        for row in rows:
            count=int(row.get('source_jobs_reported') or 0)
            if count<1:count=int(row.get('current_export_rows_attributed') or 0)
            if not count:continue
            key=hashlib.sha256((row['rank']+'|'+row['career_url']).encode()).hexdigest()
            db.execute('''INSERT OR IGNORE INTO priority_employers(source_key,rank,company_name,career_url,
                usable_jobs,successful_method,coverage,evidence_file,coverage_limitations) VALUES(?,?,?,?,?,?,?,?,?)''',
                (key,row['rank'],row['company_name'],row['career_url'],count,row.get('retry_methods') or row.get('source_platform',''),row.get('status','partial'),str(a.seed),row.get('limitation','')))
        db.commit()
    elif a.stage=='observe':
        receipt=json.loads(a.receipt.read_text(encoding='utf-8'));row=receipt['source']
        valid=[j for j in receipt.get('jobs',[]) if m.canonical(j.get('job_detail_url')) and len(m.plain(j.get('description','')))>=80]
        record_success(db,row,jobs=len(valid),method=receipt['method'],coverage=receipt.get('coverage','partial'),evidence=str(a.receipt),at=m.now(),limitations=receipt.get('coverage_limitations',''))
    elif a.stage=='run':
        if not a.inventory or not a.output or not a.db:p.error('run needs inventory, output and db')
        from uuid import uuid4
        a.output = a.output / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8])
        a.output.mkdir(parents=True,exist_ok=True)
        round_id,chosen=next_batch(db,a.limit)
        print(json.dumps({'event':'round_batch_started','round_id':round_id,'employers':len(chosen)}),flush=True)
        inventory={r['rank']:r for r in csv.DictReader(a.inventory.open(encoding='utf-8-sig'))}
        pool=load_webshare_proxies();budget=[0];lock=threading.Lock();deadline=time.monotonic()+600
        class Transport(m.Transport):
            def request(self,url,**kw):
                with lock:
                    budget[0]+=1
                    if budget[0]>500 or time.monotonic()>deadline:raise ValueError('priority_round_budget_exhausted')
                proxy=pool[int(hashlib.sha256(url.encode()).hexdigest()[:8],16)%len(pool)].url
                return super().request(url,proxies={'http':proxy,'https':proxy},**kw)
        t=Transport(a.output)
        # Fetch independent employers concurrently; catalog imports remain serial.
        executor=ThreadPoolExecutor(max_workers=3)
        prepared={source['source_key']:prepare_source(source,inventory) for source in chosen}
        futures={key:executor.submit(m.collect,row,t,a.output,probe=False,browser=False,exclude_blue_collar=True)
                 for key,row in prepared.items()}
        for source in chosen:
            source_start=time.monotonic()
            row=prepared[source['source_key']]
            try:
                result,jobs=futures[source['source_key']].result()
            except Exception as exc:
                finish_member(db,round_id,source['source_key'],outcome=type(exc).__name__,seconds=time.monotonic()-source_start,failed=True)
                continue
            usable=[j for j in jobs if m.canonical(j.get('job_detail_url')) and len(m.plain(j.get('description','')))>=80]
            at=m.now()
            if usable:
                record_success(db,row,jobs=len(usable),method=result.get('method',''),coverage=result['status'],evidence=str(a.output/'companies'/(row['rank']+'.json')),at=at,
                    limitations='Business-title details only; Germany enrichment only; max 100 pages and 500 round requests; absence closure disabled.')
            else:
                due=m.now()
                db.execute('UPDATE priority_employers SET last_attempt_at=?,next_due_at=?,failures=failures+1 WHERE source_key=?',(at,due,source['source_key']));db.commit()
            focused=[]
            for job in usable:
                country=str(job.get('country') or '').strip().casefold();loc=str(job.get('location') or '')
                germany=country in {'de','deu','germany','deutschland'} or (not country and re.search(r'\b(?:Germany|Deutschland)\b|(?:^|[,; ])DE(?:$|[,; ])',loc))
                if not germany or not review_title_candidate(job['title']):continue
                for page in dict.fromkeys((job.get('source_page'),job['job_detail_url'],job['job_detail_url'].rstrip('/')+'/')):
                    candidate=recover_link({**job,'employer_focus':{'live_check':{'source_url':page}}},t.cache)
                    if candidate:
                        job={**job,'application_url':candidate['url'],'apply_url':candidate['url'],
                             'application_link_repair':{'source_url':page,'candidate':candidate}}
                        break
                raw_path=a.output/job['raw_record_file'];raw=json.loads(raw_path.read_text(encoding='utf-8'))
                focused.append({**job,'country':'DE','url':job['job_detail_url'],'source_ats':job.get('source_platform') or 'career_site',
                    'source_raw_payload':raw,'source_company_name':job.get('legal_employer') or job['company_name'],
                    'employer_focus':{'scope_version':SCOPE_VERSION,'registry_rank':job['rank'],'raw_record_sha256':hashlib.sha256(raw_path.read_bytes()).hexdigest(),'experience_decision':'deferred_to_validated_enrichment'}})
            if focused:
                batch=a.output/(row['rank']+'-focus.jsonl')
                batch.write_text(''.join(json.dumps(j,ensure_ascii=False)+'\n' for j in focused),encoding='utf-8')
                try:
                    subprocess.run([sys.executable,str(ROOT/'scripts/import_employer_focus.py'),'--input',str(batch),'--db',str(a.db)],check=True)
                except subprocess.CalledProcessError:
                    due=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()
                    db.execute('UPDATE priority_employers SET next_due_at=?,failures=failures+1 WHERE source_key=?',(due,source['source_key']));db.commit()
                    finish_member(db,round_id,source['source_key'],usable=len(usable),focused=len(focused),outcome='focus_import_failed',seconds=time.monotonic()-source_start,failed=True)
                    print(json.dumps({'rank':row['rank'],'status':'focus_import_failed','retry_after':due}),flush=True)
                    continue
            finish_member(db,round_id,source['source_key'],usable=len(usable),focused=len(focused),outcome=result['status'],seconds=time.monotonic()-source_start,failed=result['status'] not in ('confirmed_complete','complete','partial','success','no_jobs','complete_zero_confirmed') and not usable)
            print(json.dumps({'round_id':round_id,'rank':row['rank'],'usable_source_jobs':len(usable),'focus_candidates':len(focused),'status':result['status']}),flush=True)
        executor.shutdown(wait=True)
        m.write_csv(a.output/'requests.csv',t.logs)
        # First-round proof stays intact. Later rounds retain job records and
        # durable imported originals, without accumulating every HTTP body.
        if round_id and round_id>1 and not a.retain_response_cache:
            cache=t.cache.resolve()
            assert cache.is_relative_to(a.output.resolve()) and cache.name=='cache'
            try:shutil.rmtree(cache)
            except OSError as exc:print(json.dumps({'event':'response_cache_cleanup_failed','error':type(exc).__name__}),flush=True)
        print(json.dumps({'event':'round_progress',**summary(db)}),flush=True)
    if a.export:
        columns=('rank','company_name','career_url','successful_method','last_success_at','usable_jobs','coverage','coverage_limitations')
        m.write_csv(a.export,[{k:r[k] for k in columns} for r in db.execute('SELECT * FROM priority_employers WHERE enabled=1 ORDER BY CAST(rank AS INTEGER)')])
    print(json.dumps({'priority_employers':db.execute('SELECT count(*) FROM priority_employers WHERE enabled=1').fetchone()[0],**summary(db)}),flush=True)

if __name__=='__main__':main()
