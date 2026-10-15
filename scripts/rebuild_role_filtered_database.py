"""Offline filtered SQLite rebuild; source stays unchanged until verified replacement."""
import argparse,json,sqlite3,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.acquisition.job_role_policy import accepts_record, title_matches, exceeds_experience_limit

def quote(value): return '"'+value.replace('"','""')+'"'
def rebuild(source, output, kind):
    if output.exists(): raise RuntimeError('Output exists; inspect previous receipt before retry')
    src=sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)
    dst=sqlite3.connect(output,uri=True)
    dst.execute('PRAGMA journal_mode=DELETE'); dst.execute('PRAGMA cache_size=-32768')
    dst.execute('ATTACH DATABASE ? AS original',(source.resolve().as_uri()+'?mode=ro',))
    schema=list(src.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY rowid"))
    receipt={'source':str(source),'output':str(output),'kind':kind,'started':time.time(),'tables':{}}
    def log(message): print(json.dumps(message),flush=True)
    def idset(name, values):
        dst.execute('CREATE TEMP TABLE '+name+'(id TEXT PRIMARY KEY)')
        dst.executemany('INSERT OR IGNORE INTO '+name+' VALUES(?)',((v,) for v in values))
        dst.commit()
    if kind=='catalog':
        jobs=list(src.execute('SELECT j.canonical_job_id,j.title,v.description FROM canonical_jobs j LEFT JOIN job_posting_versions v ON v.version_id=j.current_version_id'))
        keep=[id for id,title,desc in jobs if title_matches(title) and not exceeds_experience_limit(desc)]
        allowed=set(keep); idset('keep_jobs',keep); idset('drop_jobs',(id for id,_,_ in jobs if id not in allowed))
        idset('drop_versions',(r[0] for r in dst.execute('SELECT version_id FROM original.job_posting_versions WHERE canonical_job_id IN (SELECT id FROM drop_jobs)')))
        idset('drop_observations',(r[0] for r in dst.execute('SELECT observation_id FROM original.job_source_observations WHERE canonical_job_id IN (SELECT id FROM drop_jobs)')))
        idset('drop_caches',(r[0] for r in dst.execute('SELECT cache_id FROM original.job_intelligence_cache WHERE canonical_job_id IN (SELECT id FROM drop_jobs)')))
        head=src.execute('SELECT publication_id FROM acquisition_publication_head WHERE head_id=1').fetchone()[0]
        receipt.update(before_jobs=len(jobs),after_jobs=len(keep),removed_jobs=len(jobs)-len(keep),head=head)
        log(receipt)
    else:
        payload='job_json' if kind=='linkedin' else 'payload_json'; key='linkedin_job_id' if kind=='linkedin' else 'source_key'
        keep=[]; total=0
        for id,raw in src.execute('SELECT '+key+','+payload+' FROM jobs'):
            total+=1
            if accepts_record(json.loads(raw)): keep.append(id)
        idset('keep_jobs',keep)
        receipt.update(before_jobs=total,after_jobs=len(keep),removed_jobs=total-len(keep)); log(receipt)
    for typ,name,_,sql in schema:
        if typ!='table' or name.startswith('sqlite_'): continue
        dst.execute(sql)
        cols=[r[1] for r in src.execute('PRAGMA table_xinfo('+quote(name)+')') if r[6]==0]
        where=[]; params=[]
        if kind=='catalog':
            for col,tab in [('canonical_job_id','drop_jobs'),('related_job_id','drop_jobs'),('version_id','drop_versions'),('job_version_id','drop_versions'),('observation_id','drop_observations'),('related_observation_id','drop_observations'),('cache_id','drop_caches')]:
                if col in cols: where.append(quote(col)+' NOT IN (SELECT id FROM '+tab+')')
            if 'entity_id' in cols:
                where.append('entity_id NOT IN (SELECT id FROM drop_jobs UNION SELECT id FROM drop_versions UNION SELECT id FROM drop_observations)')
            if name=='acquisition_publication_jobs': where=['publication_id=?','canonical_job_id IN (SELECT id FROM keep_jobs)']; params=[head]
            if name=='acquisition_publications': where=['publication_id=?']; params=[head]
            if name in ('acquisition_ingest_staging','acquisition_ingest_snapshot_ids','acquisition_ingest_targets','acquisition_ingest_batches','acquisition_job_rejections','admin_job_audit_events','publication_audit_events','acquisition_duplicate_decisions','acquisition_reprocessing_runs'):
                where=['0']
            if 'source_observation_id' in cols and not name.startswith(('canonical_company','company_')):
                where.append("(source_observation_id='' OR source_observation_id NOT IN (SELECT id FROM drop_observations))")
        else:
            if name=='jobs': where=[quote(key)+' IN (SELECT id FROM keep_jobs)']
            elif 'linkedin_job_id' in cols: where=['linkedin_job_id IN (SELECT id FROM keep_jobs)']
            elif name=='runr_retention_index': where=['job_key IN (SELECT id FROM keep_jobs)']
            elif name in ('search_pages','query_partitions','runr_job_retention_progress'): where=['0']
        fields=','.join(map(quote,cols))
        # Preserve rowids: producer publisher and retention checkpoints use them.
        rowid= 'rowid,' if 'WITHOUT ROWID' not in sql.upper() else ''
        query='INSERT INTO '+quote(name)+'('+rowid+fields+') SELECT '+rowid+fields+' FROM original.'+quote(name)
        if where: query+=' WHERE '+' AND '.join('('+x+')' for x in where)
        started=time.time(); log({'copying':name})
        count=dst.execute(query,params).rowcount
        dst.commit(); receipt['tables'][name]=count
        log({'copied':name,'rows':count,'seconds':round(time.time()-started,2)})
    if kind=='catalog':
        # Historical snapshot JSON is redundant; current members are authoritative.
        raw=dst.execute('SELECT snapshot_json FROM acquisition_publications WHERE publication_id=?',(head,)).fetchone()[0]
        items=json.loads(raw); allowed=set(keep)
        if not isinstance(items,list): raise RuntimeError('Unexpected snapshot format')
        dst.execute("UPDATE acquisition_publications SET snapshot_json=?,previous_publication_id='' WHERE publication_id=?",(json.dumps([x for x in items if x.get('canonical_job_id') in allowed]),head))
        receipt['published_jobs']=dst.execute('SELECT count(*) FROM acquisition_publication_jobs').fetchone()[0]
    else:
        if kind=='linkedin': dst.execute("UPDATE company_scans SET observed_job_ids_json='[]'")
        elif kind=='employer':
            for key,raw in list(dst.execute('SELECT company_key,payload_json FROM companies')):
                payload=json.loads(raw)
                if isinstance(payload.get('jobs'),list):
                    payload['jobs']=[job for job in payload['jobs'] if accepts_record(job)]
                    dst.execute('UPDATE companies SET payload_json=? WHERE company_key=?',(json.dumps(payload),key))
    dst.commit()
    for typ,name,_,sql in schema:
        if typ in ('index','trigger','view'):
            log({'creating':name}); dst.execute(sql)
    dst.commit()
    result=dst.execute('PRAGMA integrity_check').fetchall()
    if result!=[('ok',)]: raise RuntimeError(str(result[:10]))
    violations=dst.execute('PRAGMA foreign_key_check').fetchall()
    if violations: raise RuntimeError(str(violations[:10]))
    receipt.update(integrity='ok',foreign_key_violations=0,finished=time.time(),bytes=output.stat().st_size)
    output.with_suffix(output.suffix+'.receipt.json').write_text(json.dumps(receipt,indent=2))
    log(receipt); dst.close(); src.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);p.add_argument('--kind',choices=['catalog','linkedin','employer'],required=True)
    a=p.parse_args();rebuild(a.source,a.output,a.kind)

