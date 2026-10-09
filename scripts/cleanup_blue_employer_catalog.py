"""Owner-approved corrected employer purge, with targeted backup and user protection."""
import argparse
import csv
import gzip
import json
import sys
import os
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request,urlopen

from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.snapshot_title_collar_audit import query as _query
from backend.database.http_batch import execute_atomic_batch
OUT=ROOT/'data/audit/blue_employer_cleanup_2026-10-09'


def query(sql,args=()):
    return _query(sql,args,compressed=True)


def execute_policy_autocommit(sql,params):
    # Policy setup is idempotent and non-destructive; it can be installed one
    # statement at a time even when explicit write transactions cannot start.
    def arg(value):
        return {'type':'text','value':str(value)} if value is not None else {'type':'null'}
    body={'requests':[{'type':'execute','stmt':{'sql':sql,'args':[arg(v) for v in params],'want_rows':False}},{'type':'close'}]}
    url=os.environ['TURSO_DATABASE_URL'].replace('libsql://','https://').rstrip('/')+'/v2/pipeline'
    request=Request(url,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+os.environ['TURSO_AUTH_TOKEN'],'Content-Type':'application/json'})
    with urlopen(request,timeout=30) as response: result=json.load(response)['results'][0]
    if result['type']!='ok': raise RuntimeError('Policy statement failed: '+result.get('error',{}).get('code','unknown'))


def application_reference_guard(batch, company_id):
    """Abort the same transaction if new user history appeared after preparation."""
    refs = []
    for table in ('reviews','application_packages','run_jobs','generation_provenance'):
        refs.append(f'SELECT job_id AS value FROM {table}')
    for table in ('reviews','application_packages','run_jobs','run_job_sets','run_blobs'):
        refs.append(f'SELECT atom AS value FROM {table}, json_tree(CASE WHEN json_valid({table}.payload_json) THEN {table}.payload_json ELSE \'{{}}\' END) WHERE json_tree.type=\'text\'')
    for table in ('personalized_job_dispositions','personalized_job_events','personalized_job_evaluations','job_intelligence_cache'):
        refs.append(f'SELECT canonical_job_id AS value FROM {table}')
    sql = ('WITH refs AS ('+' UNION '.join(refs)+'), selected AS (SELECT canonical_job_id,canonical_url FROM canonical_jobs WHERE canonical_job_id IN (SELECT value FROM json_each(?))) '
           'UPDATE employer_acquisition_exclusions SET reason=CASE WHEN EXISTS(SELECT 1 FROM selected j WHERE '
           'j.canonical_job_id IN (SELECT value FROM refs) OR (j.canonical_url<>\'\' AND j.canonical_url IN (SELECT value FROM refs)) '
           'OR EXISTS(SELECT 1 FROM canonical_job_external_ids e WHERE e.canonical_job_id=j.canonical_job_id AND e.external_job_id IN (SELECT value FROM refs)) '
           'OR EXISTS(SELECT 1 FROM canonical_job_url_aliases a WHERE a.canonical_job_id=j.canonical_job_id AND a.url IN (SELECT value FROM refs))) THEN NULL ELSE reason END WHERE company_id=?')
    return sql, (batch,company_id)


def conditions(job_ids):
    job='canonical_job_id IN (SELECT value FROM json_each(?))'
    version='version_id IN (SELECT version_id FROM job_posting_versions WHERE '+job+')'
    observation='observation_id IN (SELECT observation_id FROM job_source_observations WHERE '+job+')'
    schema=query("SELECT name,sql FROM sqlite_master WHERE type='table'")
    # Append-only audit events retain historical identifiers; user history is protected.
    skip={'canonical_jobs','acquisition_publication_jobs','personalized_job_dispositions','personalized_job_events','personalized_job_evaluations',
          'admin_job_review_decisions','acquisition_quality_events'}
    result={r['name']:(job,[job_ids]) for r in schema if 'canonical_job_id TEXT' in r['sql'] and r['name'] not in skip}
    result['canonical_job_relationships']=('('+job+' OR related_job_id IN (SELECT value FROM json_each(?)))',[job_ids,job_ids])
    result['job_source_observation_relationships']=('('+observation+' OR related_observation_id IN (SELECT observation_id FROM job_source_observations WHERE '+job+'))',[job_ids,job_ids])
    result['profile_job_fact_queue']=(version,[job_ids])
    result['job_intelligence_queue']=('cache_id IN (SELECT cache_id FROM job_intelligence_cache WHERE '+job+')',[job_ids])
    # Append-only rule/provenance and publication history retain their audit IDs.
    # Delete queues/relationships before the parents needed by their subqueries.
    last=('job_intelligence_cache','job_posting_versions','job_source_observations')
    result={**{k:v for k,v in result.items() if k not in last},**{k:result[k] for k in last}}
    result['canonical_jobs']=(job,[job_ids])
    return result


def main():
    p=argparse.ArgumentParser(); p.add_argument('phase',choices=('local-check','guard','guard-autocommit','backup','apply','verify')); args=p.parse_args()
    load_dotenv(ROOT/'user_config/.env')
    policy=json.loads((OUT/'employer-exclusions.json').read_text())
    ids=policy['company_ids']; assert len(policy['selected_company_ids'])==555
    now=datetime.now(timezone.utc).isoformat()
    plan=json.loads((OUT/'deletion_plan.json').read_text())
    job_ids=json.dumps(plan['delete_job_ids']); all_ids=json.dumps([r['canonical_job_id'] for r in plan['jobs']])
    if args.phase in ('guard','guard-autocommit','local-check'):
        before=OUT/'guard-before.json'
        if args.phase!='local-check' and not before.exists():
            before.write_text(json.dumps({'targets':query("SELECT * FROM acquisition_targets WHERE source_token IN (SELECT value FROM json_each(?)) OR json_extract(config_json,'$.canonical_company_id') IN (SELECT value FROM json_each(?))",[json.dumps(ids),json.dumps(ids)]),
                'companies':query('SELECT * FROM canonical_companies WHERE company_id IN (SELECT value FROM json_each(?))',[json.dumps(ids)])},indent=2),encoding='utf-8')
        statements=[('CREATE TABLE IF NOT EXISTS employer_acquisition_exclusions (company_id TEXT PRIMARY KEY, reason TEXT NOT NULL, approved_by TEXT NOT NULL, created_at TEXT NOT NULL)',())]
        statements.append(('INSERT OR IGNORE INTO employer_acquisition_exclusions SELECT value,?,?,? FROM json_each(?)',(policy['reason'],'Ahmed',now,json.dumps(ids))))
        companies=list(csv.DictReader((OUT/'corrected_employer_scope.csv').open(encoding='utf-8-sig')))
        statements.append(("INSERT OR IGNORE INTO canonical_companies(company_id,canonical_name,entity_kind,created_at,updated_at) SELECT json_extract(value,'$.company_id'),json_extract(value,'$.company'),'employer',?,? FROM json_each(?)",(now,now,json.dumps(companies))))
        statements += [
            ("CREATE TRIGGER IF NOT EXISTS owner_excluded_employer_job_insert BEFORE INSERT ON canonical_jobs WHEN EXISTS(SELECT 1 FROM employer_acquisition_exclusions WHERE company_id=NEW.company_id) BEGIN SELECT RAISE(ABORT,'employer excluded by owner policy'); END",()),
            ("CREATE TRIGGER IF NOT EXISTS owner_excluded_employer_publication_insert BEFORE INSERT ON acquisition_publication_jobs WHEN EXISTS(SELECT 1 FROM canonical_jobs j JOIN employer_acquisition_exclusions e ON e.company_id=j.company_id WHERE j.canonical_job_id=NEW.canonical_job_id) BEGIN SELECT RAISE(ABORT,'employer excluded by owner policy'); END",()),
            ("UPDATE acquisition_targets SET enabled=0,publication_enabled=0,quarantined=1,quarantine_reason='owner_blue_collar_employer_exclusion',quarantined_at=? WHERE source_token IN (SELECT company_id FROM employer_acquisition_exclusions) OR json_extract(config_json,'$.canonical_company_id') IN (SELECT company_id FROM employer_acquisition_exclusions)",(now,))]
        if args.phase=='local-check':
            import sqlite3
            c=sqlite3.connect(':memory:')
            for table in json.loads((OUT/'live_schema.json').read_text()):
                if table['name'] in ('canonical_companies','canonical_jobs','acquisition_targets','acquisition_publication_jobs'):
                    c.execute(table['sql'])
            cols=[r[1] for r in c.execute('PRAGMA table_info(canonical_jobs)') if (r[3] or r[5]) and r[4] is None]
            values=[ids[0] if col=='company_id' else 'existing' if col=='canonical_job_id' else 'fixture' for col in cols]
            c.execute('INSERT INTO canonical_jobs('+','.join(cols)+') VALUES ('+','.join('?' for _ in cols)+')',values)
            for sql,params in statements: c.execute(sql,params)
            assert c.execute('SELECT COUNT(*) FROM employer_acquisition_exclusions').fetchone()[0]==555
            assert c.execute('SELECT COUNT(*) FROM canonical_companies').fetchone()[0]==555
            try: c.execute("INSERT INTO acquisition_publication_jobs VALUES ('test','existing')")
            except sqlite3.IntegrityError as exc: assert 'employer excluded' in str(exc)
            else: raise AssertionError('publication guard failed')
            try: c.execute('INSERT INTO canonical_jobs('+','.join(cols)+') VALUES ('+','.join('?' for _ in cols)+')',values)
            except sqlite3.IntegrityError as exc: assert 'employer excluded' in str(exc)
            else: raise AssertionError('job guard failed')
            print(json.dumps({'guard_sql_valid_against_live_schema':True,'exclusion_rows':555})); return
        if args.phase=='guard-autocommit':
            for i in (0,1,3,4,2,5):
                execute_policy_autocommit(*statements[i])
                print(json.dumps({'policy_statement_completed':i}),flush=True)
        else:
            execute_atomic_batch(statements,timeout=180)
        print(json.dumps({'policy_rows':query('SELECT COUNT(*) AS n FROM employer_acquisition_exclusions')[0]['n']})); return
    predicates=conditions(job_ids)
    if args.phase=='backup':
        backup=OUT/'catalog-deleted-rows-v5.jsonl.gz'
        verification=OUT/'catalog-backup-verification.json'
        if verification.exists(): verification.unlink()
        counts={}; cursors={}
        if backup.exists():
            with gzip.open(backup,'rt',encoding='utf-8') as f:
                for line in f:
                    r=json.loads(line); table=r['table']
                    counts[table]=counts.get(table,0)+1
                    cursors[table]=max(cursors.get(table,0),r['row'].get('__backup_rowid',0))
        with gzip.open(backup,'at',encoding='utf-8',compresslevel=1) as f:
            for table,(condition,params) in predicates.items():
                last=cursors.get(table,0); count=counts.get(table,0)
                has_payload=any(c['name'] in ('payload_json','raw_payload_json','description','snapshot_json') for c in query(f'PRAGMA table_info({table})'))
                limit=150 if has_payload else 10000
                print(json.dumps({'starting_backup':table,'page_size':limit}),flush=True)
                while True:
                    if has_payload:
                        keys=query(f'SELECT rowid AS rid FROM {table} WHERE ({condition}) AND rowid>? ORDER BY rowid LIMIT {limit}',[*params,last])
                        rows=query(f'SELECT rowid AS __backup_rowid,* FROM {table} WHERE rowid IN (SELECT value FROM json_each(?)) ORDER BY rowid',[json.dumps([r['rid'] for r in keys])]) if keys else []
                    else:
                        rows=query(f'SELECT rowid AS __backup_rowid,* FROM {table} WHERE ({condition}) AND rowid>? ORDER BY rowid LIMIT {limit}',[*params,last])
                    if not rows: break
                    for r in rows: f.write(json.dumps({'table':table,'row':r},ensure_ascii=False)+'\n')
                    last=rows[-1]['__backup_rowid']; count+=len(rows)
                counts[table]=count
                (OUT/'catalog-backup-counts.json').write_text(json.dumps(counts,indent=2))
                print(json.dumps({'backed_up':table,'rows':count}),flush=True)
            for table in ('acquisition_publication_head',):
                for row in query(f'SELECT * FROM {table}'):
                    f.write(json.dumps({'table':table,'row':row},ensure_ascii=False)+'\n')
            for row in query('SELECT * FROM acquisition_publications WHERE publication_id=(SELECT publication_id FROM acquisition_publication_head WHERE head_id=1)'):
                f.write(json.dumps({'table':'acquisition_publications','row':row},ensure_ascii=False)+'\n')
        (OUT/'catalog-backup-counts.json').write_text(json.dumps(counts,indent=2)); return
    if args.phase=='apply':
        installed=query('SELECT COUNT(*) AS n FROM employer_acquisition_exclusions WHERE company_id IN (SELECT value FROM json_each(?))',[json.dumps(ids)])[0]['n']
        guards_installed=query("SELECT COUNT(*) AS n FROM sqlite_master WHERE type='trigger' AND name IN ('owner_excluded_employer_job_insert','owner_excluded_employer_publication_insert')")[0]['n']
        assert installed==len(ids) and guards_installed==2, 'Catalog exclusion must be installed and verified before deletion'
        verification=json.loads((OUT/'catalog-backup-verification.json').read_text())
        scope_hash=hashlib.sha256(json.dumps(sorted(plan['delete_job_ids'])).encode()).hexdigest()
        assert verification['canonical_scope_verified'] and verification['scope_sha256']==scope_hash
        with (OUT/verification['backup']).open('rb') as stream:
            assert hashlib.file_digest(stream,'sha256').hexdigest()==verification['sha256'], 'Backup changed after verification'
        counts=json.loads((OUT/'catalog-backup-counts.json').read_text())
        assert counts['canonical_jobs']==len(plan['delete_job_ids'])
        head=query('SELECT publication_id FROM acquisition_publication_head WHERE head_id=1')[0]['publication_id']
        new='acq_owner_blue_exclusion_20261009'
        if head!=new and query('SELECT publication_id FROM acquisition_publications WHERE publication_id=?',[new]):
            from uuid import uuid4
            new+='_'+uuid4().hex[:8]
        # CAS guard before creating a replacement head, using the same connection/transaction.
        statements=[("UPDATE acquisition_publication_head SET publication_id=CASE WHEN publication_id=? THEN publication_id ELSE NULL END WHERE head_id=1",(head,)),
            ("INSERT INTO acquisition_publications(publication_id,cycle_id,status,snapshot_json,published_at,valid_until,previous_publication_id,origin,created_by,policy_version) SELECT ?,?,'valid',COALESCE((SELECT json_group_array(json(value)) FROM json_each(p.snapshot_json) WHERE json_extract(value,'$.canonical_job_id') NOT IN (SELECT value FROM json_each(?))), '[]'),?,'',publication_id,'system','owner_blue_employer_cleanup',policy_version FROM acquisition_publications p WHERE publication_id=?",(new,new,all_ids,now,head)),
            ("INSERT INTO acquisition_publication_jobs(publication_id,canonical_job_id) SELECT ?,canonical_job_id FROM acquisition_publication_jobs WHERE publication_id=? AND canonical_job_id NOT IN (SELECT value FROM json_each(?))",(new,head,all_ids)),
            ("UPDATE acquisition_publication_head SET publication_id=?,updated_at=? WHERE head_id=1 AND publication_id=?",(new,now,head)),
            ("DELETE FROM acquisition_publication_queue WHERE canonical_job_id IN (SELECT value FROM json_each(?))",(all_ids,)),
            ]
        statements.append(("UPDATE canonical_jobs SET lifecycle_state='closed',closed_at=?,updated_at=? WHERE canonical_job_id IN (SELECT value FROM json_each(?))",(now,now,json.dumps(plan['protected_job_ids']))))
        if head!=new:
            execute_atomic_batch(statements,timeout=90)
        # Restore each immutable DELETE guard in the same atomic transaction as its purge.
        guards={r['name']:r['sql'] for r in query("SELECT name,sql FROM sqlite_master WHERE type='trigger'")}
        for start in range(0,len(plan['delete_job_ids']),200):
            batch=json.dumps(plan['delete_job_ids'][start:start+200]); statements=[application_reference_guard(batch,ids[0])]
            subset=conditions(batch)
            for table,(condition,params) in subset.items():
                guard=f'trg_{table}_immutable_delete'
                if guard in guards: statements.append((f'DROP TRIGGER {guard}',()))
                statements.append((f'DELETE FROM {table} WHERE {condition}',params))
                if guard in guards: statements.append((guards[guard],()))
            execute_atomic_batch(statements,timeout=60)
            print(json.dumps({'deleted_batch':start,'size':len(plan['delete_job_ids'][start:start+200])}),flush=True)
        (OUT/'catalog-cleanup-applied.json').write_text(json.dumps({'head_before':head,'head_after':new,'deleted_jobs':len(plan['delete_job_ids']),'protected_jobs':len(plan['protected_job_ids'])},indent=2))
    remaining=query('SELECT canonical_job_id FROM canonical_jobs WHERE company_id IN (SELECT value FROM json_each(?))',[json.dumps(ids)])
    published=query('SELECT COUNT(*) AS n FROM acquisition_publication_jobs p JOIN canonical_jobs j ON j.canonical_job_id=p.canonical_job_id WHERE p.publication_id=(SELECT publication_id FROM acquisition_publication_head WHERE head_id=1) AND j.company_id IN (SELECT value FROM json_each(?))',[json.dumps(ids)])[0]['n']
    result={'remaining_jobs':len(remaining),'protected_jobs':len(plan['protected_job_ids']),'published_jobs_for_selected_employers':published,
            'retained_employers':query('SELECT COUNT(*) AS n FROM canonical_companies WHERE company_id IN (SELECT value FROM json_each(?))',[json.dumps(ids)])[0]['n']}
    assert {r['canonical_job_id'] for r in remaining}==set(plan['protected_job_ids'])
    assert published==0
    assert result['retained_employers']==555
    (OUT/'catalog-verification.json').write_text(json.dumps(result,indent=2)); print(json.dumps(result))

if __name__=='__main__': main()
