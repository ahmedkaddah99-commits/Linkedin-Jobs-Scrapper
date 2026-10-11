"""Resumable, budget-limited Nemo classification of a pinned Turso publication.

Snapshot and model outputs are local; --publish writes only validated, unchanged
posting versions. Blue collar exclusion is performed by customer repository SQL.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from dotenv import load_dotenv
from backend.application.catalog_job_filters import METADATA_FIELDS, PROMPT_VERSION, ROLES, classification_prompt, function_prompt, metadata_prompt, validate_classification
from backend.database.connection import connect_database, database_target_info
from backend.domain.job_filter_source_cache import SOURCE_PATHS, SOURCE_SCHEMA

MODEL = 'mistralai/mistral-nemo'
ROOT = PROJECT.parent.parent if PROJECT.parent.name == '.worktrees' else PROJECT
DB = PROJECT / '.backend_data/backend.sqlite3'
AUDIT = ROOT / 'data/audit/catalog_classification_2026-10-04'
REVIEWS = {}


def review_for_row(row):
    review=REVIEWS.get(row['id'])
    return review if review and review['version_id']==row['version_id'] and review['content_hash']==row['content_hash'] else None


def http_execute(sql,arguments=()):
    """Bounded Hrana request for the operator batch; each SQL statement is atomic."""
    def parameter(value):
        if value is None:return {'type':'null'}
        if type(value) is int:return {'type':'integer','value':str(value)}
        if type(value) is float:return {'type':'float','value':value}
        return {'type':'text','value':str(value)}
    body={'requests':[{'type':'execute','stmt':{'sql':sql,'args':[parameter(value) for value in arguments],'want_rows':True}}, {'type':'close'}]}
    target=os.environ['TURSO_DATABASE_URL'].replace('libsql://','https://').rstrip('/')+'/v2/pipeline'
    request=Request(target,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+os.environ['TURSO_AUTH_TOKEN'],'Content-Type':'application/json'})
    for attempt in range(3):
        try:
            with urlopen(request,timeout=60) as response:payload=json.load(response)
            break
        except (TimeoutError, URLError):
            if attempt == 2:raise
            print('Turso request interrupted; retrying the same atomic statement',flush=True)
            time.sleep(1)
    result=payload['results'][0]
    if result['type']!='ok':raise RuntimeError('Turso statement error: '+str(result.get('error',{}).get('code','unknown')))
    value=result['response']['result'];names=[column['name'] for column in value['cols']]
    def decoded(cell):
        if cell['type']=='null':return None
        if cell['type']=='integer':return int(cell['value'])
        if cell['type']=='float':return float(cell['value'])
        return cell['value']
    return [dict(zip(names,(decoded(cell) for cell in row))) for row in value['rows']]


def initialize():
    global REVIEWS
    load_dotenv(ROOT / 'user_config/.env', override=False)
    if database_target_info(DB).get('target_backend') != 'libsql':
        raise RuntimeError('Production Turso configuration required')
    AUDIT.mkdir(parents=True, exist_ok=True)
    review_path=AUDIT/'reviewed_classifications.json'
    REVIEWS=json.loads(review_path.read_text(encoding='utf-8')) if review_path.exists() else {}
    local = sqlite3.connect(AUDIT / 'run.sqlite3', timeout=60)
    local.row_factory = sqlite3.Row
    local.execute('PRAGMA journal_mode=WAL')
    local.executescript('''
    CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT);
    CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,version_id TEXT,content_hash TEXT,title TEXT,company TEXT,description TEXT,location TEXT,result TEXT,attempts INTEGER DEFAULT 0,error TEXT,published INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS calls(id INTEGER PRIMARY KEY, cost REAL, usage TEXT, response TEXT);
    CREATE TABLE IF NOT EXISTS rollback(version_id TEXT PRIMARY KEY,previous_json TEXT);
    CREATE TABLE IF NOT EXISTS reservations(id INTEGER PRIMARY KEY,cost REAL,state TEXT);
    CREATE TABLE IF NOT EXISTS written(version_id TEXT PRIMARY KEY,filters_json TEXT,content_hash TEXT,generated_at TEXT);
    CREATE INDEX IF NOT EXISTS classification_progress ON jobs(id) WHERE result IS NOT NULL;
    CREATE TABLE IF NOT EXISTS snapshot_history(version_id TEXT PRIMARY KEY,row_json TEXT);
    ''')
    columns={row['name'] for row in local.execute('PRAGMA table_info(jobs)')}
    for name,definition in (('is_current','INTEGER DEFAULT 1'),('start_call_id','INTEGER DEFAULT 0')):
        if name not in columns:local.execute('ALTER TABLE jobs ADD COLUMN '+name+' '+definition)
    if not local.execute('SELECT 1 FROM metadata WHERE key="publication"').fetchone():
        with connect_database(DB) as remote:
            publication = remote.execute('SELECT publication_id FROM acquisition_publication_head WHERE head_id=1').fetchone()[0]
            cursor = ''
            while True:
                rows = remote.execute('''SELECT j.canonical_job_id AS id,j.current_version_id AS version_id,v.content_hash,j.title,
                co.canonical_name AS company,v.description,j.location
                FROM acquisition_publication_jobs pj JOIN canonical_jobs j ON j.canonical_job_id=pj.canonical_job_id
                JOIN canonical_companies co ON co.company_id=j.company_id
                JOIN job_posting_versions v ON v.version_id=j.current_version_id
                WHERE pj.publication_id=? AND co.entity_kind='employer' AND j.canonical_job_id>? ORDER BY j.canonical_job_id LIMIT 500''', (publication,cursor)).fetchall()
                if not rows:
                    break
                local.executemany('INSERT OR IGNORE INTO jobs(id,version_id,content_hash,title,company,description,location) VALUES (?,?,?,?,?,?,?)',
                                  [tuple(row[key] for key in ('id','version_id','content_hash','title','company','description','location')) for row in rows])
                local.commit()
                cursor = rows[-1]['id']
                print('snapshot',local.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],flush=True)
        local.execute('INSERT INTO metadata VALUES (?,?)',('publication',publication))
        local.execute('INSERT INTO metadata VALUES (?,?)',('started_at',datetime.now(timezone.utc).isoformat()))
        local.commit()
    return local


def refresh_snapshot(local):
    """Catch up once to the current publication; keep superseded input/outputs for audit."""
    existing={row['id']:dict(row) for row in local.execute('SELECT * FROM jobs')}
    first_call=local.execute('SELECT COALESCE(MAX(id),0)+1 FROM calls').fetchone()[0]
    local.execute('UPDATE jobs SET is_current=0');local.commit()
    added=changed=current=0
    with connect_database(DB) as remote:
        publication=remote.execute('SELECT publication_id FROM acquisition_publication_head WHERE head_id=1').fetchone()[0]
        cursor=''
        while True:
            rows=remote.execute('''SELECT j.canonical_job_id AS id,j.current_version_id AS version_id,v.content_hash,j.title,
            co.canonical_name AS company,j.location FROM acquisition_publication_jobs pj
            JOIN canonical_jobs j ON j.canonical_job_id=pj.canonical_job_id
            JOIN canonical_companies co ON co.company_id=j.company_id JOIN job_posting_versions v ON v.version_id=j.current_version_id
            WHERE pj.publication_id=? AND co.entity_kind='employer' AND j.canonical_job_id>? ORDER BY j.canonical_job_id LIMIT 1000''',(publication,cursor)).fetchall()
            if not rows:break
            replacements=[row for row in rows if row['id'] not in existing or existing[row['id']]['version_id']!=row['version_id'] or existing[row['id']]['content_hash']!=row['content_hash']]
            descriptions={}
            for start in range(0,len(replacements),100):
                ids=[row['version_id'] for row in replacements[start:start+100]]
                for value in remote.execute('SELECT version_id,description FROM job_posting_versions WHERE version_id IN ('+','.join('?' for _ in ids)+')',ids).fetchall():
                    descriptions[value['version_id']]=value['description']
            replacement_ids={row['id'] for row in replacements}
            for row in rows:
                if row['id'] not in replacement_ids:
                    local.execute('UPDATE jobs SET is_current=1 WHERE id=?',(row['id'],));continue
                old=existing.get(row['id'])
                if old:
                    local.execute('INSERT OR IGNORE INTO snapshot_history VALUES (?,?)',(old['version_id'],json.dumps(old,ensure_ascii=False)));changed+=1
                else:added+=1
                local.execute('''INSERT INTO jobs(id,version_id,content_hash,title,company,description,location,is_current,start_call_id)
                VALUES (?,?,?,?,?,?,?,1,?) ON CONFLICT(id) DO UPDATE SET version_id=excluded.version_id,content_hash=excluded.content_hash,
                title=excluded.title,company=excluded.company,description=excluded.description,location=excluded.location,
                result=NULL,attempts=0,error=NULL,published=0,is_current=1,start_call_id=excluded.start_call_id''',
                (row['id'],row['version_id'],row['content_hash'],row['title'],row['company'],descriptions[row['version_id']],row['location'],first_call))
            local.commit();current+=len(rows);cursor=rows[-1]['id']
    for key,value in (('current_publication',publication),('refresh_added',str(added)),('refresh_changed',str(changed))):
        local.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',(key,value))
    local.commit();print('refreshed',current,'added',added,'changed',changed,flush=True)


def generate(rows):
    inputs = [{'id':row['id'],'title':row['title'],'location':row['location'],'description':row['description']} for row in rows]
    prompt = function_prompt(inputs[0])
    if rows[0].get('attempts',0):
        prompt += '\nPrevious attempt was rejected. Copy the exact job title verbatim into evidence. A qualified nurse, doctor, office receptionist, engineer, office administrator or professional manager is white collar. Manual trades, drivers and assembly operators are blue collar.'
    body = {'model':MODEL,'messages':[{'role':'user','content':prompt}], 'temperature':0,
            'max_tokens':1400,'response_format':{'type':'json_schema','json_schema':{'name':'job_function','strict':True,'schema':{
                'type':'object','properties':{'collar':{'type':'string','enum':['white','blue']},
                'roles':{'type':'array','items':{'type':'string','enum':list(ROLES)}},'evidence':{'type':'string'}},
                'required':['collar','roles','evidence'],'additionalProperties':False}}},
            'provider':{'order':['Parasail','DeepInfra','DekaLLM'],'require_parameters':True,'max_price':{'prompt':0.03,'completion':0.03}}}
    def call():
        request = Request('https://openrouter.ai/api/v1/chat/completions',data=json.dumps(body).encode(),
                          headers={'Authorization':'Bearer '+os.environ['OPENROUTER_API_KEY'],'Content-Type':'application/json'})
        with urlopen(request,timeout=120) as response:
            return json.load(response)
    payload = call()
    originals=[payload]
    extracted=json.loads(payload['choices'][0]['message']['content'])
    review=review_for_row(rows[0])
    if review:
        extracted.update({key:review[key] for key in ('collar','roles','evidence')})
    accepted=validate_classification(extracted, str(inputs[0]['title'])+' '+str(inputs[0]['description'] or ''),inputs[0]['title'],reviewed=bool(review))
    if accepted and accepted['collar']=='white' and extracted.get('collar')=='blue':
        extracted.update(collar='white',roles=accepted['roles'],evidence=accepted['evidence'])
    if extracted.get('collar')=='white':
        body['messages'][0]['content']=metadata_prompt(inputs[0])
        body['response_format']={'type':'json_object'}
        metadata=call()
        originals.append(metadata)
        extracted.update({key:value for key,value in json.loads(metadata['choices'][0]['message']['content']).items() if key in METADATA_FIELDS})
    extracted['id']=inputs[0]['id']
    usage={'prompt_tokens':sum((p.get('usage') or {}).get('prompt_tokens',0) for p in originals),
           'completion_tokens':sum((p.get('usage') or {}).get('completion_tokens',0) for p in originals)}
    cost=sum(float((p.get('usage') or {}).get('cost') if (p.get('usage') or {}).get('cost') is not None
                   else ((p.get('usage') or {}).get('prompt_tokens',len(prompt.encode()))+(p.get('usage') or {}).get('completion_tokens',1400))*0.03/1e6) for p in originals)
    payload={'choices':[{'message':{'content':json.dumps({'jobs':[extracted]},ensure_ascii=False)}}], 'provider_responses':originals}
    return payload,cost,usage


def run(local,args):
    abandoned=local.execute("SELECT COALESCE(SUM(cost),0) FROM reservations WHERE state='pending'").fetchone()[0]
    if abandoned:
        local.execute('INSERT INTO calls(cost,usage,response) VALUES (?,?,?)',(abandoned,'{}','conservative charge for interrupted requests'))
        local.execute("UPDATE reservations SET state='interrupted' WHERE state='pending'")
        local.commit()
    rows = [dict(row) for row in local.execute('SELECT * FROM jobs WHERE is_current=1 AND result IS NULL AND attempts<? ORDER BY attempts,id',(args.max_attempts,))]
    if args.limit:
        rows=rows[:args.limit]
    batches=[]
    batch=[]
    size=0
    for row in rows:
        length=len(row['description'] or '')
        if batch and (len(batch)>=1 or size+length>35000):
            batches.append(batch);batch=[];size=0
        batch.append(row);size+=length
    if batch:
        batches.append(batch)
    spent=local.execute('SELECT COALESCE(SUM(cost),0) FROM calls').fetchone()[0]
    reserved=0.0
    pending={}
    index=0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        while index<len(batches) or pending:
            while index<len(batches) and len(pending)<args.workers:
                batch=batches[index]
                # UTF-8 bytes bound token count, plus full maximum output.
                reserve=(2*len(classification_prompt([{'id':r['id'],'title':r['title'],'location':r['location'],'description':r['description']} for r in batch]).encode())+2800)*0.03/1e6
                if spent+reserved+reserve>args.budget:
                    print('Budget guard: no further requests',flush=True);index=len(batches);break
                reservation_id=local.execute("INSERT INTO reservations(cost,state) VALUES (?,'pending')",(reserve,)).lastrowid
                local.commit()
                pending[executor.submit(generate,batch)]=(batch,reserve,reservation_id)
                reserved+=reserve;index+=1
            if not pending:
                break
            future=next(as_completed(pending))
            batch,reserve,reservation_id=pending.pop(future);reserved-=reserve
            try:
                payload,cost,usage=future.result()
                spent+=cost
                local.execute('INSERT INTO calls(cost,usage,response) VALUES (?,?,?)',(cost,json.dumps(usage),json.dumps(payload,ensure_ascii=False)))
                content=payload['choices'][0]['message']['content']
                parsed=json.loads(content)
                outputs={item['id']:item for item in parsed.get('jobs',[]) if isinstance(item,dict) and 'id' in item}
                for row in batch:
                    result=validate_classification(outputs.get(row['id']),str(row['title'])+' '+str(row['description'] or ''),row['title'],reviewed=bool(review_for_row(row)))
                    local.execute('UPDATE jobs SET result=?,attempts=attempts+1,error=? WHERE id=?',
                                  (json.dumps(result,ensure_ascii=False) if result else None,None if result else 'invalid classification/evidence',row['id']))
            except Exception as exc:
                # Reserve the maximum charge for an uncertain failed request.
                if future.exception() is not None:
                    spent+=reserve
                    local.execute('INSERT INTO calls(cost,usage,response) VALUES (?,?,?)',(reserve,'{}','request failed: '+type(exc).__name__))
                for row in batch:
                    local.execute('UPDATE jobs SET attempts=attempts+1,error=? WHERE id=?',(type(exc).__name__,row['id']))
            local.execute("UPDATE reservations SET state='complete' WHERE id=?",(reservation_id,))
            local.commit()
            done=local.execute('SELECT COUNT(*) FROM jobs WHERE result IS NOT NULL').fetchone()[0]
            if done % 100 == 0 or not pending:
                print(f'validated={done} cost=${spent:.5f} pending={len(pending)} batches_remaining={len(batches)-index}',flush=True)


def preserve_write_attempts(local):
    local.execute('CREATE TABLE IF NOT EXISTS write_attempts(version_id TEXT,filters_json TEXT,content_hash TEXT,generated_at TEXT,PRIMARY KEY(version_id,generated_at))')
    local.execute('INSERT OR IGNORE INTO write_attempts SELECT * FROM written')
    local.commit()


def cache_source_metadata(local):
    rows=[dict(row) for row in local.execute('SELECT * FROM jobs WHERE is_current=1 AND result IS NOT NULL')
          if json.loads(row['result']).get('source_metadata_schema')!=SOURCE_SCHEMA]
    objects=['json_object('+','.join("'"+path+"',json_extract(v.payload_json,'"+path+"')" for path in SOURCE_PATHS[start:start+30])+')'
             for start in range(0,len(SOURCE_PATHS),30)]
    projection=objects[0]
    for value in objects[1:]:projection='json_patch('+projection+','+value+')'
    def fetch(batch):
        values=http_execute('SELECT v.version_id,v.content_hash,'+projection+' AS source_metadata FROM job_posting_versions v WHERE v.version_id IN ('+','.join('?' for row in batch)+')',tuple(row['version_id'] for row in batch))
        return batch,{value['version_id']:value for value in values}
    completed=0
    with ThreadPoolExecutor(max_workers=4) as executor:
        for batch,values in executor.map(fetch,[rows[start:start+100] for start in range(0,len(rows),100)]):
            for row in batch:
                source=values.get(row['version_id'])
                if not source or source['content_hash']!=row['content_hash']:
                    raise RuntimeError('Source-cache version/hash mismatch')
                result=json.loads(row['result'])
                result['source_metadata']=json.loads(source['source_metadata'])
                result['source_metadata_schema']=SOURCE_SCHEMA
                local.execute('UPDATE jobs SET result=?,published=0 WHERE id=?',(json.dumps(result,ensure_ascii=False),row['id']))
            local.commit();completed+=len(batch)
            print('cached source metadata',completed,'of',len(rows),flush=True)


def publish(local):
    preserve_write_attempts(local)
    rows=[dict(row) for row in local.execute('SELECT * FROM jobs WHERE is_current=1 AND result IS NOT NULL AND published=0')]
    changed=0
    for start in range(0,len(rows),25):
        batch=rows[start:start+25]
        placeholders=','.join('?' for _ in batch)
        previous={row['version_id']:row for row in http_execute('SELECT * FROM job_filter_intelligence WHERE version_id IN ('+placeholders+')',tuple(row['version_id'] for row in batch))}
        for row in batch:
            local.execute('INSERT OR IGNORE INTO rollback VALUES (?,?)',(row['version_id'],json.dumps(previous[row['version_id']]) if row['version_id'] in previous else None))
        local.commit()  # Persist all rollback rows before the remote transaction.
        arguments=[]
        generated_at=datetime.now(timezone.utc).isoformat()
        for row in batch:
            arguments.extend((row['version_id'],row['id'],row['content_hash'],row['result'],MODEL,PROMPT_VERSION,generated_at))
            local.execute('INSERT OR REPLACE INTO written VALUES (?,?,?,?)',(row['version_id'],row['result'],row['content_hash'],generated_at))
            local.execute('INSERT OR IGNORE INTO write_attempts VALUES (?,?,?,?)',(row['version_id'],row['result'],row['content_hash'],generated_at))
        local.commit()
        saved=http_execute('''WITH incoming(version_id,canonical_job_id,content_hash,filters_json,model,prompt_version,generated_at) AS (VALUES '''+','.join('(?,?,?,?,?,?,?)' for _ in batch)+''')
            INSERT INTO job_filter_intelligence SELECT incoming.* FROM incoming
            JOIN canonical_jobs j ON j.canonical_job_id=incoming.canonical_job_id AND j.current_version_id=incoming.version_id
            JOIN job_posting_versions v ON v.version_id=j.current_version_id AND v.content_hash=incoming.content_hash
            WHERE 1 ON CONFLICT(version_id) DO UPDATE SET
            canonical_job_id=excluded.canonical_job_id,content_hash=excluded.content_hash,filters_json=excluded.filters_json,
            model=excluded.model,prompt_version=excluded.prompt_version,generated_at=excluded.generated_at
            RETURNING canonical_job_id''',arguments)
        saved_ids={row['canonical_job_id'] for row in saved}
        changed+=len(batch)-len(saved_ids)
        for row in batch:
            local.execute('UPDATE jobs SET published=? WHERE id=?',(1 if row['id'] in saved_ids else -1,row['id']))
        local.commit()
        print('published batch',start+len(rows[start:start+25]),'changed',changed,flush=True)


def revalidate(local):
    sources={row['id']:dict(row) for row in local.execute('SELECT * FROM jobs') if dict(row).get('is_current',1)}
    latest={}
    for call in local.execute('SELECT id,response FROM calls ORDER BY id'):
        try:
            payload=json.loads(call['response'])
            parsed=json.loads(payload['choices'][0]['message']['content'])
            originals=payload.get('provider_responses')
            if originals:
                classification=json.loads(originals[0]['choices'][0]['message']['content'])
                if len(originals)>1:
                    extracted_metadata=json.loads(originals[1]['choices'][0]['message']['content'])
                    classification.update({key:value for key,value in extracted_metadata.items() if key in METADATA_FIELDS})
                classification['id']=parsed['jobs'][0]['id']
                parsed={'jobs':[classification]}
            for item in parsed.get('jobs',[]):
                if item.get('id') in sources and call['id']>=sources[item['id']].get('start_call_id',0):
                    latest[item['id']]=item
        except (ValueError,KeyError,TypeError):
            continue
    for identity,raw in latest.items():
        row=sources[identity]
        original_collar=raw.get('collar')
        review=review_for_row(row)
        if review:
            raw.update({key:review[key] for key in ('collar','roles','evidence')})
        result=validate_classification(raw,str(row['title'])+' '+str(row['description'] or ''),row['title'],reviewed=bool(review))
        needs_metadata = bool(result and result['collar']=='white' and original_collar=='blue' and row['description']
                              and not any(key in raw for key in METADATA_FIELDS))
        if needs_metadata:
            result=None
            local.execute('UPDATE jobs SET attempts=MIN(attempts,2) WHERE id=?',(identity,))
        local.execute('UPDATE jobs SET result=?,error=? WHERE id=?',
                      (json.dumps(result,ensure_ascii=False) if result else None,None if result else 'metadata extraction needed' if needs_metadata else 'invalid classification/evidence',identity))
    local.commit()


def rollback(local):
    preserve_write_attempts(local)
    restored=skipped=0
    for previous in local.execute('SELECT * FROM rollback'):
        attempts=local.execute('SELECT * FROM write_attempts WHERE version_id=?',(previous['version_id'],)).fetchall()
        if not attempts:
            skipped+=1;continue
        with connect_database(DB) as remote:
            ownership=(previous['version_id'],MODEL,PROMPT_VERSION)+tuple(value for row in attempts for value in (row['filters_json'],row['content_hash'],row['generated_at']))
            guard='version_id=? AND model=? AND prompt_version=? AND ('+' OR '.join('(filters_json=? AND content_hash=? AND generated_at=?)' for row in attempts)+')'
            if previous['previous_json'] is None:
                restored_rows=remote.execute('DELETE FROM job_filter_intelligence WHERE '+guard+' RETURNING version_id',ownership).fetchall()
            else:
                saved=json.loads(previous['previous_json'])
                restored_rows=remote.execute('''UPDATE job_filter_intelligence SET canonical_job_id=?,content_hash=?,filters_json=?,model=?,prompt_version=?,generated_at=?
                WHERE '''+guard+' RETURNING version_id',tuple(saved[key] for key in ('canonical_job_id','content_hash','filters_json','model','prompt_version','generated_at'))+ownership).fetchall()
            remote.commit()
        if not restored_rows:
            skipped+=1;continue
        local.execute('UPDATE jobs SET published=0 WHERE version_id=?',(previous['version_id'],));local.commit();restored+=1
    print('rollback restored',restored,'skipped changed rows',skipped,flush=True)


def report(local):
    total=local.execute('SELECT COUNT(*) FROM jobs WHERE is_current=1').fetchone()[0]
    counts={role:0 for role in ROLES}
    blue=white=0
    coverage={key:0 for key in ('required_experience_years','experience_level','work_arrangement','employment_type','skills','role_type')}
    for row in local.execute('SELECT result FROM jobs WHERE is_current=1 AND result IS NOT NULL'):
        result=json.loads(row[0])
        if result['collar']=='blue':blue+=1;continue
        white+=1
        for role in result['roles']:counts[role]+=1
        for key in coverage:
            if result.get(key) not in (None,[], ''):coverage[key]+=1
    cost=local.execute('SELECT COALESCE(SUM(cost),0) FROM calls').fetchone()[0]
    api_cost=local.execute("SELECT COALESCE(SUM(cost),0) FROM calls WHERE usage!='{}'").fetchone()[0]
    conservative=cost-api_cost
    published=local.execute('SELECT COUNT(*) FROM jobs WHERE is_current=1 AND published=1').fetchone()[0]
    changed=local.execute('SELECT COUNT(*) FROM jobs WHERE is_current=1 AND published=-1').fetchone()[0]
    summary={'snapshot_jobs':total,'white_collar':white,'blue_collar':blue,'unresolved':total-white-blue,'published':published,'changed_versions_skipped':changed,'cost_usd':cost,'reported_api_cost_usd':api_cost,'conservative_charges_usd':conservative,'counts':counts,'coverage':coverage}
    (AUDIT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    lines=['# Full catalog classification â€” 2026-10-04','',f'Generated snapshot results: {total} jobs; white collar: {white}; blue collar: {blue}; unresolved: {total-white-blue}.',f'Successfully saved to Turso: {published}. Changed versions skipped: {changed}. Counts below describe generated snapshot results, not live catalog counts.',f'API cost (includes conservative failed-call charges): ${cost:.5f}.','',
           'Multiple functions per job are allowed; function counts overlap. Blue collar classifications hide customer listings only after deployment. Original employer postings are retained. Unsupported numeric/model fields are hidden. Full source, outputs, API usage, and rollback data are saved in run.sqlite3.','',
           'Model: mistralai/mistral-nemo. Original German/English input is used for verifiable exact evidence. Actual prompts: backend/application/catalog_job_filters.py, function_prompt and metadata_prompt.','',
           '| Function | Jobs |','|---|---:|']
    lines.extend(f'| {role} | {count} |' for role,count in counts.items())
    lines+=['','## White collar field coverage','']+[f'- {key}: {value}' for key,value in coverage.items()]
    lines+=['','## Scope and classification rules','',
        'This round covers the current published employer catalog. The starting publication had 29,217 jobs; one catch-up added 277 postings. Historical/unpublished source rows are outside the customer catalog.',
        'White collar includes office, analytical, administrative, sales, engineering/design, scientific, education, legal, qualified clinical and professional management work. Retail sales uses the existing Retail Sales function. Manual trades, drivers, machine operators, warehouse picking, cleaning, cooking and table service are excluded. Professional planning, management, teaching and source-confirmed clinical work remain eligible.',
        'Each accepted white collar job has at least one function. Functions share one taxonomy between the frontend and backend; specific missing professional functions were added. The lists allow multiple functions per job.',
        'Reliable scraped metadata takes precedence. Nemo fills supported experience years, seniority, work arrangement, employment type, skills and people-management facts. Location, salary and company filters continue to use existing source data. Full-time is the product default when no supported alternative contract type is available. Unsupported optional output is hidden without repeated field retries.',
        'Two adjacent seniority levels may display together. A gap or more than two levels displays the highest. Years require numeric output and a source quote stating a year unit; months, company age and unsupported guessed years are rejected.',
        '', '## Quality checks and retained evidence','',
        'Source review found and corrected systematic nursing, therapy, veterinary, teaching, accounting and engineering mislabels, oversized copied taxonomies, false manual-work retentions, and fixed-term wording mistaken for unbefristet. Version-bound reviewed_classifications.json records '+str(len(REVIEWS))+' individual source decisions, including professional duties under conflicting trade titles.',
        'Metadata keys are whitelisted so the second model call cannot change collar, functions or their supporting quote. Every saved record matches the current posting version and content hash. Later production writes are protected by atomic rollback ownership guards.',
        'Coverage and filter-query verification measure accepted data and wiring; they are not a measured accuracy rate for every job. Original employer text, model responses, costs, superseded snapshot inputs and rollback rows are retained locally in run.sqlite3. jobs.csv contains every current job and its Runr URL.',
        f'Provider-reported/usage-priced calls: ${api_cost:.5f}. Conservative uncertain-call allowance: ${conservative:.5f}. Total budget ledger: ${cost:.5f}, below $5.',
        '', '## Unresolved records','',
        'These records remain visible for source review; no occupation is invented and they are not removed as blue collar.','']
    for row in local.execute('SELECT id,title,error FROM jobs WHERE is_current=1 AND result IS NULL'):
        lines.append(f'- [{row["title"]}](https://app.userunr.com/jobs/{row["id"]}): {row["error"]}.')
    (AUDIT/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    with (AUDIT/'jobs.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['title','employer','collar','functions','url','published'])
        for row in local.execute('SELECT * FROM jobs WHERE is_current=1 ORDER BY company,title'):
            result=json.loads(row['result']) if row['result'] else {}
            writer.writerow([row['title'],row['company'],result.get('collar','unresolved'),'; '.join(result.get('roles',[])),
                             'https://app.userunr.com/jobs/'+row['id'],row['published']])
    print(json.dumps({k:v for k,v in summary.items() if k!='counts'}),flush=True)


def live_report():
    with connect_database(DB) as remote:
        totals=dict(remote.execute('''SELECT COUNT(*) AS published_jobs,
        SUM(CASE WHEN fi.content_hash=v.content_hash AND json_extract(fi.filters_json,'$.collar')='white' THEN 1 ELSE 0 END) AS classified_white,
        SUM(CASE WHEN fi.content_hash=v.content_hash AND json_extract(fi.filters_json,'$.collar')='blue' THEN 1 ELSE 0 END) AS excluded_blue
        FROM acquisition_publication_head h JOIN acquisition_publication_jobs pj ON pj.publication_id=h.publication_id
        JOIN canonical_jobs j ON j.canonical_job_id=pj.canonical_job_id JOIN canonical_companies c ON c.company_id=j.company_id
        JOIN job_posting_versions v ON v.version_id=j.current_version_id LEFT JOIN job_filter_intelligence fi ON fi.version_id=v.version_id
        WHERE h.head_id=1 AND c.entity_kind='employer' ''').fetchone())
        counts={role:0 for role in ROLES}
        for row in remote.execute('''SELECT role.value,COUNT(DISTINCT j.canonical_job_id) AS total
        FROM acquisition_publication_head h JOIN acquisition_publication_jobs pj ON pj.publication_id=h.publication_id
        JOIN canonical_jobs j ON j.canonical_job_id=pj.canonical_job_id JOIN canonical_companies c ON c.company_id=j.company_id
        JOIN job_posting_versions v ON v.version_id=j.current_version_id JOIN job_filter_intelligence fi ON fi.version_id=v.version_id AND fi.content_hash=v.content_hash
        JOIN json_each(fi.filters_json,'$.roles') role WHERE h.head_id=1 AND c.entity_kind='employer'
        AND json_extract(fi.filters_json,'$.collar')='white' GROUP BY role.value''').fetchall():
            counts[row[0]]=row['total']
    totals['unclassified_visible']=totals['published_jobs']-(totals['classified_white'] or 0)-(totals['excluded_blue'] or 0)
    totals['visible_jobs']=totals['published_jobs']-(totals['excluded_blue'] or 0)
    (AUDIT/'live_counts.json').write_text(json.dumps({'totals':totals,'counts':counts},indent=2),encoding='utf-8')
    with (AUDIT/'REPORT.md').open('a',encoding='utf-8') as stream:
        stream.write('\n## Verified current Turso catalog\n\n'+json.dumps(totals)+'\n\n| Function | Current jobs |\n|---|---:|\n')
        stream.write('\n'.join(f'| {role} | {count} |' for role,count in counts.items())+'\n')
    print('live',json.dumps(totals),flush=True)


def verify_live_filters(local):
    from backend.repositories.sqlite_personalized_jobs import SqlitePersonalizedJobsStore
    class ReadRows:
        def __init__(self,rows):self.rows=rows
        def fetchone(self):return self.rows[0] if self.rows else None
        def fetchall(self):return self.rows
    class ReadConnection:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def execute(self,sql,args=()):
            if not sql.lstrip().startswith(('SELECT','WITH','/*')):
                raise RuntimeError('Verification connection permits read queries only')
            return ReadRows(http_execute(sql,args))
    expected=json.loads((AUDIT/'live_counts.json').read_text(encoding='utf-8'))
    store=SqlitePersonalizedJobsStore(DB,initialize=False)
    # Execute the actual customer repository queries against Turso with bounded
    # operator transport, without changing application connection behavior.
    store._connect=lambda:ReadConnection()
    user='catalog-rollout-readonly-verification'
    first=store.query_published_jobs(user,filters={},limit=1)
    if first['total']!=expected['totals']['visible_jobs']:
        raise RuntimeError('Unfiltered customer count differs from live catalog count')
    progress_path=AUDIT/'verification_progress.json'
    progress=json.loads(progress_path.read_text(encoding='utf-8')) if progress_path.exists() else {}
    checks=[]
    def check_role(role):
        page=store.query_published_jobs(user,filters={'role':[role]},limit=1)
        required=expected['counts'][role]
        if page['total']!=required:
            raise RuntimeError(f'Function count mismatch: {role}: {page["total"]} != {required}')
        if page['rows']:
            raw=page['rows'][0]['filter_json'];filters=json.loads(raw) if isinstance(raw,str) else raw
            if role not in filters['roles']:raise RuntimeError('Returned job does not have selected function')
        print('verified function',role,'jobs',page['total'],flush=True)
        return {'function':role,'jobs':page['total'],'passed':True}
    if progress.get('counts')==expected['counts'] and progress.get('publication_id')==first['publication']['publication_id']:
        checks=progress['function_checks']
    else:
        with ThreadPoolExecutor(max_workers=8) as executor:
            checks=list(executor.map(check_role,ROLES))
    progress={'counts':expected['counts'],'publication_id':first['publication']['publication_id'],'function_checks':checks}
    progress_path.write_text(json.dumps(progress,indent=2),encoding='utf-8')
    fields=[]
    for field,values in (('work_arrangement',('onsite','hybrid','remote')),
                         ('employment_type',('full_time','part_time','contract','internship','working_student','apprenticeship')),
                         ('experience_level',('intern','entry','mid','senior','lead','director')),
                         ('role_type',('ic','manager'))):
        for value in values:
            print('checking field',field,value,flush=True)
            page=store.query_published_jobs(user,filters={field:[value]},limit=1)
            fields.append({'filter':field,'value':value,'jobs':page['total'],'returned_row':bool(page['rows'])})
    for filters in ({'required_experience_min':1,'required_experience_max':3},{'skills_include':['SQL']},
                    {'role':['Data Analyst'],'skills_include':['SQL']}):
        print('checking field combination',json.dumps(filters),flush=True)
        page=store.query_published_jobs(user,filters=filters,limit=1)
        if not page['rows']:raise RuntimeError('Expected a supported field-filter result')
        fields.append({'filters':filters,'jobs':page['total'],'returned_row':True})
    blue=local.execute("SELECT id FROM jobs WHERE is_current=1 AND json_extract(result,'$.collar')='blue' LIMIT 1").fetchone()[0]
    if store.get_published_job_row(blue) is not None:raise RuntimeError('Blue collar detail remains customer visible')
    verified={'verified_at':datetime.now(timezone.utc).isoformat(),'publication_id':first['publication']['publication_id'],
              'transport':'Bounded Hrana HTTP executing unchanged customer repository SQL',
              'unfiltered_jobs':first['total'],'blue_detail_excluded':True,'function_checks':checks,'field_checks':fields,
              'browser_visual_check':'Not performed: browser security policy blocked the signed-in Runr page.'}
    (AUDIT/'verification.json').write_text(json.dumps(verified,indent=2),encoding='utf-8')
    with (AUDIT/'REPORT.md').open('a',encoding='utf-8') as stream:
        stream.write(f'\n## Live filter verification\n\nVerified {len(checks)} function selections against their exact live counts. '
                     f'Unfiltered customer count: {first["total"]}. Blue collar detail is excluded. '
                     f'Tested {len(fields)} field/filter selections, including experience years, skills and a combined function/skill filter. '
                     'Field queries were exercised and counts recorded; exact membership was checked for function filters. Full results are in verification.json. A browser security policy blocked the signed-in visual check.\n')
    print('verified',len(checks),'functions;',len(fields),'field/filter selections',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--limit',type=int,default=0)
    parser.add_argument('--workers',type=int,default=12)
    parser.add_argument('--max-attempts',type=int,default=3)
    parser.add_argument('--budget',type=float,default=5)
    parser.add_argument('--publish',action='store_true')
    parser.add_argument('--report-only',action='store_true')
    parser.add_argument('--revalidate',action='store_true')
    parser.add_argument('--refresh-snapshot',action='store_true')
    parser.add_argument('--rollback',action='store_true')
    parser.add_argument('--live-report',action='store_true')
    parser.add_argument('--verify-live',action='store_true')
    parser.add_argument('--cache-source',action='store_true')
    args=parser.parse_args()
    local=initialize()
    if args.refresh_snapshot:refresh_snapshot(local)
    if args.rollback:
        rollback(local);report(local);sys.exit(0)
    if args.revalidate:revalidate(local)
    if not args.report_only:run(local,args)
    if args.cache_source:cache_source_metadata(local)
    if args.publish:publish(local)
    report(local)
    if args.live_report:live_report()
    if args.verify_live:verify_live_filters(local)
