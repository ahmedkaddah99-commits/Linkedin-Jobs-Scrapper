"""Bounded read-only VPS pipeline snapshots and sanitized execution events."""
import json
import math
import os
import sqlite3
import subprocess
import time
from functools import lru_cache
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path('/var/lib/runr/observability')
DB = Path('/var/lib/runr/customer-candidate-db/backend.sqlite3')
COMPONENTS = {
    'linkedin': 'runr-acquisition-linkedin', 'employer': 'runr-acquisition-employer',
    'publisher': 'runr-acquisition-publisher', 'backfill': 'runr-publish-recent-once-20261012',
    'publication': 'runr-catalog-publication', 'retention': 'runr-producer-retention',
    'lifecycle': 'runr-job-lifecycle', 'enrichment': 'runr-job-descriptions',
    'matching': 'runr-profile-job-facts', 'api': 'runr-api-candidate', 'worker': 'runr-worker-candidate',
    'observer': 'runr-e2e-observer',
    'storage_maintenance': 'runr-catalog-storage-maintenance',
}


def point(name, value, **labels):
    return {'name': 'runr_e2e_' + name, 'value': value, 'labels': labels}


@lru_cache(maxsize=256)
def reason_label(value):
    import ast
    if isinstance(value,str) and value.startswith('{'):
        try:value=json.loads(value).get('code','other')
        except ValueError:return 'other'
    tree=ast.parse(Path('/srv/runr/releases/acquisition-repair-be18a0c7/backend/acquisition/job_publication_completeness.py').read_text())
    allowed={n.value.value for n in tree.body if isinstance(n,ast.Assign) and isinstance(n.value,ast.Constant)
             and isinstance(n.value.value,str) and any(isinstance(t,ast.Name) and t.id.startswith('REASON_') for t in n.targets)}
    allowed.update(('owner_blue_collar_job','posted_over_30_days','first_seen_over_30_days','blue_collar_rules'))
    return value if value in allowed else 'other'


def connect(path):
    db = sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True, timeout=2)
    db.execute('PRAGMA cache_size=-2048')
    deadline = time.monotonic() + 20
    db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
    return db


def sources():
    result = []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
    for source, key in [('linkedin', 'linkedin_job_id'), ('employer', 'source_key')]:
        with connect(Path('/srv/runr/state/active') / source / ('master_' + source + '_jobs_state.db')) as db:
            counts = db.execute(f'''SELECT count(*),sum(date(i.retention_date)>=date(?)),
                sum(date(i.retention_date)<date(?)),sum(i.retention_date IS NULL)
                FROM jobs j LEFT JOIN runr_retention_index i ON i.source=? AND i.job_key=j.{key}''',
                (cutoff, cutoff, source)).fetchone()
            for stage, value in zip(('stored', 'recent_date', 'expired_date', 'unknown_date'), counts):
                result.append(point('source_jobs', value or 0, source=source, stage=stage))
            for reason, count in db.execute('SELECT reason,count(*) FROM runr_retired_jobs GROUP BY reason'):
                safe = reason if reason in ('retention_30_days', 'blue_collar_rules', 'posted_over_30_days', 'first_seen_over_30_days') else 'other'
                result.append(point('retired_jobs', count, source=source, reason=safe))
    return result


def eligibility():
    import ijson
    path=Path('/srv/runr/shared/inputs/manifest-generations/active/SOURCE_ELIGIBILITY_MANIFEST.json')
    with path.open('rb') as stream:counts=next(ijson.items(stream,'counts'))
    return [point('manifest_records',int(v),measure=k) for k,v in counts.items() if isinstance(v,(int,float))]


def catalog():
    result = []
    with connect(DB) as db:
        for state, count in db.execute('SELECT lifecycle_state,count(*) FROM canonical_jobs GROUP BY lifecycle_state'):
            result.append(point('catalog_jobs', count, state=state))
        head = db.execute('SELECT publication_id,updated_at FROM acquisition_publication_head WHERE head_id=1').fetchone()
        if head:
            result.append(point('published_jobs', db.execute('SELECT count(*) FROM acquisition_publication_jobs WHERE publication_id=?', (head[0],)).fetchone()[0]))
            result.append(point('head_timestamp_seconds', datetime.fromisoformat(head[1]).timestamp()))
        for source, rowid, complete, stamp in db.execute('SELECT source,source_rowid,bootstrap_complete,updated_at FROM acquisition_publisher_checkpoints'):
            source = 'employer' if source == 'employer_site' else source
            result.extend([point('checkpoint_rowid', rowid, source=source), point('bootstrap_complete', complete, source=source),
                           point('checkpoint_timestamp_seconds', datetime.fromisoformat(stamp).timestamp(), source=source)])
        for state, count in db.execute('SELECT status,count(*) FROM acquisition_publication_queue GROUP BY status'):
            result.append(point('publication_queue_jobs', count, state=state))
    return result


def enrichment():
    result = []
    with connect(DB) as db:
        head = db.execute('SELECT publication_id FROM acquisition_publication_head WHERE head_id=1').fetchone()[0]
        for state, count in db.execute('''SELECT q.state,count(*) FROM job_enrichment_queue q
            JOIN canonical_jobs j ON j.current_version_id=q.version_id
            JOIN acquisition_publication_jobs a ON a.canonical_job_id=j.canonical_job_id
            WHERE a.publication_id=? GROUP BY q.state''', (head,)):
            result.append(point('enrichment_jobs', count, state=state))
        for error, count in db.execute('''SELECT q.error_code,count(*) FROM job_enrichment_queue q
            JOIN canonical_jobs j ON j.current_version_id=q.version_id
            JOIN acquisition_publication_jobs a ON a.canonical_job_id=j.canonical_job_id
            WHERE a.publication_id=? AND q.error_code<>'' GROUP BY q.error_code''', (head,)):
            safe = error if error in ('source_missing', 'source_incomplete', 'filter_validation_failed', 'description_has_no_supported_facts', 'description_output_not_english', 'daily_budget_exceeded', 'blue_collar_excluded') else 'other'
            result.append(point('enrichment_errors', count, reason=safe))
        for stage, count in db.execute('''SELECT 'function_indexed',count(DISTINCT j.canonical_job_id)
            FROM canonical_jobs j JOIN job_filter_roles r ON r.version_id=j.current_version_id
            JOIN job_posting_versions v ON v.version_id=j.current_version_id AND v.content_hash=r.content_hash
            JOIN acquisition_publication_jobs a ON a.canonical_job_id=j.canonical_job_id
            WHERE a.publication_id=?''', (head,)):
            result.append(point('coverage_jobs', count, stage=stage))
        for stage, table in [('description_stored', 'job_description_intelligence'), ('matching_facts', 'profile_job_facts')]:
            count = db.execute(f'''SELECT count(*) FROM canonical_jobs j JOIN {table} f ON f.version_id=j.current_version_id
                JOIN job_posting_versions v ON v.version_id=j.current_version_id AND v.content_hash=f.content_hash
                JOIN acquisition_publication_jobs a ON a.canonical_job_id=j.canonical_job_id
                WHERE a.publication_id=?''', (head,)).fetchone()[0]
            result.append(point('coverage_jobs', count, stage=stage))
    return result


def gate():
    with connect(DB) as db:
        # Count current queue reasons; history rows and reasons are not unique jobs.
        return [point('gate_reasons', count, reason=reason_label(reason))
            for reason, count in db.execute('''SELECT r.value,count(*) FROM acquisition_publication_queue q,
                json_each(q.reason_codes_json) r WHERE q.status='rejected' GROUP BY r.value''')]


def visibility():
    import sys
    release=subprocess.check_output(['systemctl','show',COMPONENTS['api']+'.service','-p','WorkingDirectory','--value'],text=True,timeout=5).strip()
    if not release or not Path(release).is_dir():raise RuntimeError('serving_release_unavailable')
    sys.path.insert(0, release)
    os.environ.update(DATABASE_BACKEND='sqlite', SQLITE_DATABASE_PATH=str(DB), RUNR_SKIP_PROJECT_DOTENV='1')
    from backend.repositories.sqlite_personalized_jobs import SqlitePersonalizedJobsStore
    result = SqlitePersonalizedJobsStore(DB, initialize=False).query_published_jobs('e2e-observer', limit=1)
    return [point('customer_query_jobs', result['total'])]


def collection():
    from collections import Counter
    result=[]
    with connect(Path('/srv/runr/state/active/linkedin/master_linkedin_jobs_state.db')) as db:
        run=db.execute('SELECT run_id,started_at,status FROM runs ORDER BY started_at DESC LIMIT 1').fetchone()
        attempts=db.execute('SELECT run_id,status FROM detail_attempts ORDER BY rowid DESC LIMIT 2000').fetchall()
        for state,count in Counter(status for runid,status in attempts if runid==run[0]).items():
            result.append(point('collection_latest',count,source='linkedin',measure='detail_attempts',state=state))
        result.append(point('collection_detail_window_truncated',int(bool(attempts) and len(attempts)==2000 and attempts[-1][0]==run[0]),source='linkedin'))
        for state,count in db.execute('SELECT status,count(*) FROM company_scans WHERE run_id=? GROUP BY status',(run[0],)):
            result.append(point('collection_latest',count,source='linkedin',measure='company_scans',state=state))
        result.append(point('collection_latest_timestamp_seconds',datetime.fromisoformat(run[1].replace('Z','+00:00')).timestamp(),source='linkedin'))
    with connect(Path('/srv/runr/state/active/employer/master_employer_jobs_state.db')) as db:
        for state,count in db.execute('SELECT status,count(*) FROM companies GROUP BY status'):
            result.append(point('employer_scan_inventory',count,state=state))
        for state,count in db.execute('SELECT classification,count(*) FROM coverage_receipts GROUP BY classification'):
            result.append(point('employer_coverage_inventory',count,state=state))
    return result


def storage():
    import shutil
    disk=shutil.disk_usage('/srv/runr')
    result=[point('disk_bytes',value,measure=label) for label,value in
            [('total',disk.total),('used',disk.used),('free',disk.free)]]
    for store,path in [('catalog',DB),*[(s,Path('/srv/runr/state/active')/s/('master_'+s+'_jobs_state.db')) for s in ('linkedin','employer')]]:
        result.append(point('database_file_bytes',path.stat().st_size,store=store))
        result.append(point('database_allocated_bytes',path.stat().st_blocks*512,store=store))
        wal=Path(str(path)+'-wal')
        result.append(point('database_wal_bytes',wal.stat().st_size if wal.exists() else 0,store=store))
        with connect(path) as db:
            free=db.execute('PRAGMA freelist_count').fetchone()[0]*db.execute('PRAGMA page_size').fetchone()[0]
            result.append(point('database_reusable_bytes',free,store=store))
    for role in ('producer-retention','job-lifecycle'):
        p=Path('/srv/runr/exports/receipts')/(role+'-latest.json')
        if not p.exists():continue
        receipt=json.loads(p.read_text())
        result.append(point('cleanup_receipt_timestamp_seconds',p.stat().st_mtime,stage=role))
        for item in receipt if isinstance(receipt,list) else [receipt]:
            for field in ('scanned','removed','remaining_jobs','expired_jobs','physical_rows_deleted','pass_complete'):
                if field in item:result.append(point('cleanup_latest',int(item[field]),stage=role,source=item.get('source','catalog'),measure=field))
    return result


def budget():
    day = datetime.now(timezone.utc).date().isoformat()
    with connect(Path('/srv/runr/state/nemo-enrichment-usage.sqlite3')) as db:
        rows = db.execute('SELECT state,count(*),sum(reserved),sum(cost) FROM calls WHERE day=? GROUP BY state', (day,)).fetchall()
    result = []
    for state, count, reserved, cost in rows:
        result.extend([point('ai_calls_today', count, state=state), point('ai_reserved_dollars_today', reserved or 0, state=state),
                       point('ai_recorded_cost_dollars_today', cost or 0, state=state)])
    # The limit is read from the installed service, not assumed from old docs.
    command = subprocess.check_output(['systemctl', 'show', 'runr-job-descriptions.service', '-p', 'ExecStart', '--value'], text=True)
    import re
    for flag, name in [('daily-budget', 'daily_dollars'), ('workers', 'workers'), ('max-jobs', 'jobs_per_run'), ('runtime-seconds', 'runtime_seconds')]:
        match = re.search(r'--' + flag + r'\s+(\d+(?:\.\d+)?)', command)
        if match:
            result.append(point('configured_limit', float(match[1]), component='enrichment', limit=name))
    return result


def resources(previous):
    result, states = [], {}
    props = ['LoadState','ActiveState','Result','MemoryCurrent','MemoryPeak','MemoryMax','MemoryHigh','CPUUsageNSec','CPUQuotaPerSecUSec','TasksCurrent','TasksMax','ExecMainStatus']
    for component, unit in COMPONENTS.items():
        output = subprocess.check_output(['systemctl','show',unit+'.service',*[x for p in props for x in ('-p',p)]], text=True, timeout=5)
        values = dict(line.split('=',1) for line in output.splitlines() if '=' in line)
        result.append(point('service_present',int(values.get('LoadState')=='loaded'),component=component))
        if values.get('LoadState')!='loaded':continue
        result.append(point('service_running', int(values.get('ActiveState') in ('active','activating')), component=component))
        result.append(point('service_failed', int(values.get('Result') not in (None,'','success') or values.get('ActiveState')=='failed'), component=component))
        for key, metric in [('MemoryCurrent','memory_bytes'),('MemoryPeak','memory_peak_bytes'),('MemoryMax','memory_limit_bytes'),('MemoryHigh','memory_high_bytes'),('TasksCurrent','tasks'),('TasksMax','task_limit'),('ExecMainStatus','last_exit_code')]:
            if values.get(key,'').isdigit():result.append(point('service_'+metric,int(values[key]),component=component))
        cpu = int(values.get('CPUUsageNSec','0')) / 1e9
        quota = values.get('CPUQuotaPerSecUSec','')
        if quota.endswith('s') and quota[:-1].replace('.','',1).isdigit():
            result.append(point('service_cpu_limit_cores',float(quota[:-1]),component=component))
        elif quota.endswith('ms') and quota[:-2].replace('.','',1).isdigit():
            result.append(point('service_cpu_limit_cores',float(quota[:-2])/1000,component=component))
        prior = previous.get(component,{})
        if prior and cpu>=prior['cpu']:
            result.append(point('service_cpu_used_cores',(cpu-prior['cpu'])/max(1,time.time()-prior['time']),component=component))
        states[component]={'cpu':cpu,'time':time.time()}
    mainpid=subprocess.check_output(['systemctl','show',COMPONENTS['backfill']+'.service','-p','MainPID','--value'],text=True,timeout=5).strip()
    processes=subprocess.check_output(['ps','-eo','pid=,ppid=,args='],text=True,timeout=5)
    rows=[line.split(None,2) for line in processes.splitlines() if len(line.split(None,2))==3]
    descendants={mainpid} if mainpid!='0' else set()
    while True:
        children={pid for pid,parent,cmd in rows if parent in descendants}
        if children<=descendants:break
        descendants.update(children)
    result.append(point('backfill_waiting_lock',int(any(pid in descendants and cmd.startswith('flock -w ') for pid,parent,cmd in rows))))
    return result, states


def collector_limits():
    import re
    import shlex
    from dotenv import dotenv_values
    result=[]
    for component in ('linkedin','employer','publisher'):
        unit=COMPONENTS[component]+'.service'
        raw=subprocess.check_output(['systemctl','show',unit,'-p','Environment','--value'],text=True,timeout=5)
        values=dict(part.split('=',1) for part in shlex.split(raw) if '=' in part)
        paths=subprocess.check_output(['systemctl','show',unit,'-p','EnvironmentFiles','--value'],text=True,timeout=5)
        for path in re.findall(r'(/[^\s]+)\s+\(ignore_errors=',paths):
            if Path(path).exists():values.update({k:v for k,v in dotenv_values(path).items() if v is not None})
        selected={'linkedin':{'requests':'RUNR_LINKEDIN_MAX_REQUESTS','companies':'RUNR_LINKEDIN_MAX_COMPANIES'},
                  'employer':{'requests':'RUNR_EMPLOYER_MAX_REQUESTS','companies':'RUNR_EMPLOYER_MAX_COMPANIES'},
                  'publisher':{'source_rows':'RUNR_PUBLISHER_SOURCE_ROW_BATCH_SIZE','companies':'RUNR_PUBLISHER_MAX_COMPANIES'}}[component]
        for name,key in selected.items():
            if str(values.get(key,'')).isdigit():result.append(point('configured_limit',int(values[key]),component=component,limit=name))
    return result


def events(state):
    path = Path('/srv/runr/exports/receipts/publisher-timings.jsonl')
    old = state.get('publisher_events', {})
    counts, durations = old.get('counts', {}), old.get('durations', {})
    jobs=old.get('jobs',{})
    inode = path.stat().st_ino
    offset = old.get('offset', 0) if old.get('inode') == inode else 0
    if offset > path.stat().st_size:offset=0
    event_logs = []
    with path.open('rb') as stream:
        stream.seek(offset)
        end = offset + 4*1024*1024
        while stream.tell()<end:
            line=stream.readline()
            if not line or not line.endswith(b'\n'):break
            offset=stream.tell()
            try:item=json.loads(line)
            except ValueError:continue
            action=item.get('action','')
            if action not in ('delivery_batch','publication_batch','large_company_chunk'):continue
            counts[action]=counts.get(action,0)+1
            durations[action]=durations.get(action,0)+float(item.get('duration_seconds') or 0)
            jobs[action]=jobs.get(action,0)+int(item.get('counts',{}).get('jobs',0))
            event_logs.append({'event':'pipeline_batch','timestamp':item.get('timestamp'),'stage':action,
                'seconds':item.get('duration_seconds'),'counts':item.get('counts',{})})
    state['publisher_events']={'inode':inode,'offset':offset,'counts':counts,'durations':durations,'jobs':jobs}
    result=[]
    for stage,count in counts.items():
        result.extend([point('batch_events_total',count,stage=stage),point('batch_duration_seconds_total',durations[stage],stage=stage),point('batch_input_rows_total',jobs.get(stage,0),stage=stage)])
    return result,event_logs


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    state_path=OUT/'e2e.json'
    try:state=json.loads(state_path.read_text())
    except (OSError,ValueError):state={}
    sections=state.get('sections',{})
    now=time.time()
    logs=[]
    for name,fn in [('eligibility',eligibility),('collection',collection),('collector_limits',collector_limits),('sources',sources),('catalog',catalog),('gate',gate),('enrichment',enrichment),('visibility',visibility),('budget',budget),('storage',storage)]:
        start=time.monotonic()
        try:
            metrics=fn();sections[name]={'up':1,'timestamp':time.time(),'metrics':metrics}
            error=''
        except Exception as e:
            sections.setdefault(name,{'timestamp':0,'metrics':[]})['up']=0;error=type(e).__name__
        logs.append({'event':'pipeline_snapshot','timestamp':datetime.now(timezone.utc).isoformat(),
            'stage':name,'up':sections[name]['up'],'error_class':error,'seconds':round(time.monotonic()-start,3),
            'metrics':sections[name].get('metrics',[]) if not error else []})
    try:
        metrics, state['resources']=resources(state.get('resources',{}))
        sections['resources']={'up':1,'timestamp':time.time(),'metrics':metrics}
    except Exception as e:
        sections.setdefault('resources',{'timestamp':0,'metrics':[]})['up']=0
        logs.append({'event':'pipeline_snapshot','stage':'resources','up':0,'error_class':type(e).__name__})
    try:
        metrics, event_logs=events(state);logs.extend(event_logs)
        sections['events']={'up':1,'timestamp':time.time(),'metrics':metrics}
    except Exception as e:
        sections.setdefault('events',{'timestamp':0,'metrics':[]})['up']=0
    state['sections']=sections
    lines=[f'runr_e2e_observer_timestamp_seconds {now}']
    for name,section in sections.items():
        merged={}
        for item in [point('section_up',section['up'],stage=name),point('section_timestamp_seconds',section['timestamp'],stage=name),*section['metrics']]:
            if not isinstance(item['value'],(int,float)) or not math.isfinite(item['value']):continue
            key=(item['name'],tuple(sorted(item['labels'].items())))
            if key in merged:merged[key]['value']+=item['value']
            else:merged[key]=dict(item)
        for item in merged.values():
            labels=','.join(f'{k}={json.dumps(str(v))}' for k,v in sorted(item['labels'].items()))
            lines.append(item['name']+('{'+labels+'}' if labels else '')+' '+str(item['value']))
    for path,content in [(OUT/'e2e.prom','\n'.join(lines)+'\n'),(state_path,json.dumps(state))]:
        temp=path.with_suffix('.tmp');temp.write_text(content);temp.chmod(0o644);temp.replace(path)
    logpath=OUT/'e2e-events.jsonl'
    if logpath.exists() and logpath.stat().st_size>16*1024*1024:logpath.replace(OUT/'e2e-events.previous.jsonl')
    with logpath.open('a') as stream:
        for entry in logs:stream.write(json.dumps(entry)+'\n')
    logpath.chmod(0o644)
    print(json.dumps({'event':'e2e_observer_complete','sections':{k:v['up'] for k,v in sections.items()},'seconds':round(time.time()-now,3)}))


if __name__=='__main__':main()
