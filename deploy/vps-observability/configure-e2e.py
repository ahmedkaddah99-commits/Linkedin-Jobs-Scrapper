"""Publish and verify the linear VPS acquisition-to-customer dashboard."""
import argparse
import json
import runpy
import re
import time
import urllib.parse
from pathlib import Path

ROOT=Path(__file__).parent
H=runpy.run_path(str(ROOT/'configure-grafana.py'))
UID='runr-e2e-jobs'


def build(prom,logs):
    panels=[];y=0
    def row(title,note):
        nonlocal y
        panels.append({'id':len(panels)+1,'type':'row','title':title,'collapsed':False,'gridPos':{'x':0,'y':y,'w':24,'h':1}});y+=1
        panels.append({'id':len(panels)+1,'type':'text','title':'How to read this stage','gridPos':{'x':0,'y':y,'w':24,'h':3},'options':{'mode':'markdown','content':note}});y+=3
    def panel(title,expr,legend='',kind='timeseries',unit='short',width=24,x=0,height=7,desc=''):
        nonlocal y
        if ' or ' in expr:
            parts=expr.split(' or ')
            expr=' or '.join('label_replace(('+part+'),"metric","'+re.search(r'(runr_e2e_\w+|runr_acquisition_\w+|node_\w+)',part)[1]+'","__name__",".*")' for part in parts)
            legend=legend.replace('{{__name__}}','{{metric}}')
        p={'id':len(panels)+1,'type':kind,'title':title,'description':desc,'gridPos':{'x':x,'y':y,'w':width,'h':height},
           'datasource':{'type':'prometheus','uid':prom},'targets':[{'refId':'A','expr':expr,'legendFormat':legend,'instant':kind!='timeseries','range':kind=='timeseries'}],
           'fieldConfig':{'defaults':{'unit':unit,'decimals':0,'noValue':'No verified data','thresholds':{'mode':'absolute','steps':[{'color':'green','value':None}]}},'overrides':[]},
           'options':{'legend':{'displayMode':'table','placement':'bottom','calcs':['lastNotNull']},'tooltip':{'mode':'multi'}}}
        if kind=='stat':p['options']={'reduceOptions':{'calcs':['lastNotNull'],'fields':'','values':False},'textMode':'value_and_name','colorMode':'none','graphMode':'area'}
        if kind=='table':p['targets'][0]['format']='table';p['options']={'showHeader':True}
        panels.append(p);y+=height
        return p
    row('Start here: what is happening in the last 30 minutes',
        '**Read downward: eligible companies → collection → stored jobs → deletions → import → publication → enrichment → matching → app visibility.** '
        'Counts are live measurements, not targets. Stage inventories overlap; do not add them. Published membership is separate from the app query. '
        'A flat line plus stale telemetry is unknown, not success. Logs below retain actual batch timings. New telemetry history starts at installation; no history is invented.')
    panel('Published catalog / app query / function-indexed / current matching facts',
          'runr_e2e_published_jobs or runr_e2e_customer_query_jobs or runr_e2e_coverage_jobs','{{__name__}} {{stage}}','stat',height=5)
    panel('Net published and app-query change in selected time range',
          'delta(runr_e2e_published_jobs[$__range]) or delta(runr_e2e_customer_query_jobs[$__range])','{{__name__}}','stat',height=4,
          desc='Net change includes removals. It is not gross newly published jobs. Requires at least two samples.')
    p=panel('Telemetry validity: 1 healthy / 0 failed','runr_e2e_section_up','{{stage}}','stat',height=4)
    p['options']['colorMode']='value';p['fieldConfig']['defaults']['thresholds']['steps']=[{'color':'red','value':None},{'color':'green','value':1}]
    panel('Telemetry age by stage','time()-runr_e2e_section_timestamp_seconds','{{stage}}','stat','s',height=4)
    panel('Current blockers: failed workers, lock wait and enrichment review/source failures',
          'runr_e2e_service_failed == 1 or runr_e2e_backfill_waiting_lock or runr_e2e_enrichment_jobs{state=~"review_required|source_missing|source_incomplete"}',
          '{{component}} {{metric}} {{state}}','table',desc='Service failure is the most recent systemd result and may be historical for a disabled unit. Lock wait is scoped to the one-time backfill process tree. Queue counts are current published versions.')
    row('1. Choose eligible companies','Manifest counts are the reviewed input snapshot, not a count of jobs. Employer exclusions apply during collection and publication.')
    panel('Manifest input, eligible source tasks and blocked entities','runr_e2e_manifest_records','{{measure}}')
    row('2. Find postings and fetch details','Latest completed collector-run gauges repeat between runs. These are outcomes per run, not counters to rate(). Requests and failed details explain low yield.')
    panel('Latest LinkedIn durable run: scan and detail outcomes','runr_e2e_collection_latest','{{source}} {{measure}} {{state}}',desc='Latest-run company scan outcomes and detail attempts within the last 2,000 durable attempt rows. The truncation indicator identifies partial detail coverage. Includes incomplete/running runs; no completed result is invented.')
    panel('Detail-attempt window truncated: 1 means partial coverage','runr_e2e_collection_detail_window_truncated','LinkedIn window truncated','stat',height=4)
    panel('Employer company scan state and coverage across time','runr_e2e_employer_scan_inventory or runr_e2e_employer_coverage_inventory','{{metric}} {{state}}',desc='Cumulative current company checkpoints and coverage receipts, not latest-run newly collected jobs. A historical no_jobs state does not prove a fresh complete scan.')
    panel('Collector failure / partial status','runr_acquisition_last_run_failed or runr_acquisition_last_run_partial','{{source}} {{__name__}}','stat',height=4)
    panel('Effective collector and normal publisher limits','runr_e2e_configured_limit{component!="enrichment"}','{{component}} {{limit}}','table',desc='Explicit effective environment values only; absent settings are not replaced with guessed defaults. One-time backfill uses separate process overrides.')
    row('3. Persist source jobs','Durable producer inventory is not newly collected or publishable inventory. The age breakdown joins the retention index to existing rows; deleted index entries are excluded.')
    panel('Source jobs: stored / recent-date / expired-date / unknown-date','runr_e2e_source_jobs','{{source}} {{stage}}')
    row('4. Delete expired producer payloads','Thirty-day cleanup deletes source payloads and related search/detail rows. Retirement tombstones prevent resurrection. Recent-date counts still include jobs blocked by other policies.')
    panel('Retired source identities by reason','runr_e2e_retired_jobs','{{source}} {{reason}}')
    panel('Latest physical cleanup batch and pass-completion evidence','runr_e2e_cleanup_latest{stage="producer-retention"}','{{source}} {{measure}}','table')
    panel('Age of cleanup receipts','time()-runr_e2e_cleanup_receipt_timestamp_seconds','{{stage}}','stat','s',height=4)
    row('5. Snapshot producer states and read the import window','The one-time backfill waits on shared publisher/source locks, takes consistent SQLite snapshots, then releases source locks. Bootstrap completion is explicit; rowid is not a count of jobs.')
    panel('Importer checkpoints over time','runr_e2e_checkpoint_rowid','{{source}}')
    panel('Bootstrap complete and time since checkpoint advance','runr_e2e_bootstrap_complete','{{source}}','stat',height=4)
    panel('Checkpoint age','time()-runr_e2e_checkpoint_timestamp_seconds','{{source}}','stat','s',height=4)
    panel('Backfill waiting for a lock','runr_e2e_backfill_waiting_lock','Waiting','stat',height=4)
    row('6. Normalize, resolve company ownership and deduplicate','Exact identities and source relationships determine merging. Batch execution timing below covers normalization and persistence; unsupported identities remain blocked, not fabricated.')
    panel('Delivery and large-company chunks per selected interval','increase(runr_e2e_batch_events_total{stage=~"delivery_batch|large_company_chunk"}[$__rate_interval])','{{stage}}')
    panel('Input job rows processed in the selected time range','increase(runr_e2e_batch_input_rows_total{stage=~"delivery_batch|large_company_chunk"}[$__range])','{{stage}}','stat',height=4,desc='Rows in observed delivery events; retries may reprocess identities. This is not unique new published jobs. History begins when this counter was installed.')
    panel('Mean delivery transaction duration','increase(runr_e2e_batch_duration_seconds_total{stage=~"delivery_batch|large_company_chunk"}[$__rate_interval])/increase(runr_e2e_batch_events_total{stage=~"delivery_batch|large_company_chunk"}[$__rate_interval])','{{stage}}','timeseries','s')
    row('7. Save canonical jobs, observations and posting versions','Catalog lifecycle inventory is separate from publication. Unchanged source content reuses posting versions. Source history and user records can remain after a job disappears from discovery.')
    panel('Canonical jobs by lifecycle','runr_e2e_catalog_jobs','{{state}}')
    row('8. Apply the publication gate','Age, employer exclusions, blue-collar decisions, application policy, ownership, duplicates and completeness determine eligibility. Rejection reasons can overlap; totals are not unique rejected jobs.')
    panel('Publication queue by current status','runr_e2e_publication_queue_jobs','{{state}}')
    panel('Current rejected-job reason occurrences','sum by(reason)(runr_e2e_gate_reasons)','{{reason}}','table')
    row('9. Commit the published catalog; expire ineligible membership','A successful commit advances the public head. Lifecycle expiry removes membership and marks canonical jobs expired while preserving identities, versions and customer history. This is not physical disk reclamation.')
    panel('Current publication membership across time','runr_e2e_published_jobs','Published catalog')
    panel('Publication batches per sample interval','increase(runr_e2e_batch_events_total{stage="publication_batch"}[$__rate_interval])','Publication batches',desc='Observed finished publication calls, including no-op/replay calls. Use membership/app net change to measure count movement, not this event count.')
    panel('Mean publication batch duration','increase(runr_e2e_batch_duration_seconds_total{stage="publication_batch"}[$__rate_interval])/increase(runr_e2e_batch_events_total{stage="publication_batch"}[$__rate_interval])','Publication duration','timeseries','s')
    panel('Lifecycle expiry and physical deletion: latest receipt','runr_e2e_cleanup_latest{stage="job-lifecycle"}','{{measure}}','table')
    row('10. Queue enrichment for current published versions','Counts are restricted to current versions in the current head. Historical/superseded queue entries are excluded. pending/running/review states are distinct.')
    panel('Current published-job enrichment queue across time','runr_e2e_enrichment_jobs','{{state}}')
    row('11. Classify white/blue collar and assign job functions','Current-version function memberships drive discovery. Blue jobs are excluded. A recent source posting without a usable function is not automatically discoverable.')
    panel('Current published jobs with indexed functions','runr_e2e_coverage_jobs{stage="function_indexed"}','Indexed functions')
    row('12. Generate grounded English description','Descriptions are supported by original-source quotations. This coverage counts matching current description records, not a guarantee every record passes current UI validation.')
    panel('Current-version description records in publication','runr_e2e_coverage_jobs{stage="description_stored"}','Stored descriptions')
    row('13. Repair invalid output and fill missing fields','Missing source text, invalid classification and unsupported descriptions remain explicit failures/review states. Daily provider budget can stop workers; it is a real resource ceiling.')
    panel('Enrichment failure reasons among current published versions','sum by(reason)(runr_e2e_enrichment_errors)','{{reason}}','table')
    panel('AI calls today by ledger state','runr_e2e_ai_calls_today','{{state}}')
    panel('Recorded AI cost, reserved amounts and configured daily ceiling','runr_e2e_ai_recorded_cost_dollars_today or runr_e2e_ai_reserved_dollars_today or runr_e2e_configured_limit{limit="daily_dollars"}','{{__name__}} {{state}}','timeseries','currencyUSD')
    panel('Installed enrichment limits','runr_e2e_configured_limit{component="enrichment"}','{{limit}}','table')
    row('14. Build version-bound profile-matching facts','Matching-fact records must match the current posting version/hash. This is shared fact coverage; individual user match percentages depend on their profiles.')
    panel('Current published jobs with matching facts','runr_e2e_coverage_jobs{stage="matching_facts"}','Matching facts')
    row('15. Return discoverable jobs to the app','This read-only probe uses the serving repository against the VPS database with an empty synthetic disposition and no user preferences. It is an unfiltered backend baseline, not a signed-in browser acceptance test or your personal filtered count.')
    panel('Published membership versus serving repository query','runr_e2e_published_jobs or runr_e2e_customer_query_jobs','{{__name__}}')
    row('16. Reclaim historical storage and check VPS capacity','Hidden/expired jobs, deleted SQL rows and reclaimed filesystem bytes are different. SQLite free pages are reusable inside the file; they do not automatically shrink it. These panels measure actual database/WAL and filesystem bytes.')
    panel('VPS filesystem: total / used / free','runr_e2e_disk_bytes','{{measure}}','timeseries','bytes')
    panel('Database files, allocated disk, WAL and reusable pages','runr_e2e_database_file_bytes or runr_e2e_database_allocated_bytes or runr_e2e_database_wal_bytes or runr_e2e_database_reusable_bytes','{{store}} {{__name__}}','timeseries','bytes')
    row('Resource constraints: which stage is limited?', 'Per-service memory/CPU/task limits come from effective systemd properties; enrichment limits come from its installed command. CPU usage is measured between snapshots. Missing unlimited values remain absent. Host metrics come from Alloy node_exporter.')
    panel('Worker memory usage / peak / enforced ceiling','runr_e2e_service_memory_bytes or runr_e2e_service_memory_peak_bytes or runr_e2e_service_memory_limit_bytes','{{component}} {{__name__}}','timeseries','bytes')
    panel('Worker memory usage as percentage of its enforced limit','100*runr_e2e_service_memory_bytes/on(component) runr_e2e_service_memory_limit_bytes','{{component}}','timeseries','percent')
    panel('Worker measured CPU cores / configured core ceiling','runr_e2e_service_cpu_used_cores or runr_e2e_service_cpu_limit_cores','{{component}} {{__name__}}')
    panel('Service presence, state, failures and exit codes','runr_e2e_service_present or runr_e2e_service_running or runr_e2e_service_failed or runr_e2e_service_last_exit_code','{{component}} {{__name__}}','table')
    panel('Tasks and enforced task ceilings','runr_e2e_service_tasks or runr_e2e_service_task_limit','{{component}} {{__name__}}')
    panel('Host CPU busy percentage','100*(1-avg by(instance)(rate(node_cpu_seconds_total{mode="idle"}[$__rate_interval])))','{{instance}}','timeseries','percent')
    panel('Host RAM usage percentage','100*(1-node_memory_MemAvailable_bytes/node_memory_MemTotal_bytes)','{{instance}}','timeseries','percent')
    panel('Host load averages','node_load1 or node_load5 or node_load15','{{instance}} {{__name__}}')
    panel('Host disk I/O busy seconds per second','rate(node_disk_io_time_seconds_total{device=~"sd.*|vd.*|nvme.*"}[$__rate_interval])','{{instance}} {{device}}')
    row('Execution evidence: batch timings and stage health','Sanitized logs contain stage names, counts, durations and error classes. No job text, account profiles or credentials are shipped. Use the time picker to inspect a stalled interval.')
    panels.append({'id':len(panels)+1,'type':'logs','title':'Pipeline stage snapshots and publication execution events','gridPos':{'x':0,'y':y,'w':24,'h':12},
        'datasource':{'type':'loki','uid':logs},'targets':[{'refId':'A','expr':'{job="runr/e2e"} | json','queryType':'range'}],
        'options':{'showTime':True,'wrapLogMessage':True,'sortOrder':'Descending'}})
    return {'uid':UID,'title':'Runr — Jobs E2E: acquisition → enrichment → app','schemaVersion':39,'version':1,'timezone':'browser',
            'refresh':'1m','time':{'from':'now-30m','to':'now'},'tags':['runr','e2e','vps'],'panels':panels}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    editor=Path('user_config/grafana-dashboard-editor-token.txt').read_text().strip()
    datasources=H['request'](H['GRAFANA']+'/api/datasources',editor)
    prom=next(d['uid'] for d in datasources if d['type']=='prometheus' and d['name'].endswith('-prom'))
    logs=next(d['uid'] for d in datasources if d['type']=='loki' and d['name'].endswith('-logs'))
    dashboard=build(prom,logs)
    if args.publish:
        r=H['request'](H['GRAFANA']+'/api/dashboards/db',editor,payload={'dashboard':dashboard,'overwrite':True,'message':'Owner-requested linear E2E acquisition/enrichment and VPS resource evidence'})
        print(json.dumps({'status':r.get('status'),'url':H['GRAFANA']+r.get('url',''),'panels':len(dashboard['panels'])}))
        (ROOT/'e2e-dashboard.json').write_text(json.dumps(dashboard,indent=2),encoding='utf-8')
    if args.verify:
        token=Path('user_config/grafana-cloud-observer-read-token.txt').read_text().strip();checks=[]
        for p in dashboard['panels']:
            if p.get('datasource',{}).get('type')!='prometheus':continue
            expr=p['targets'][0]['expr'].replace('$__range','30m').replace('$__rate_interval','5m')
            try:
                r=H['request']('https://prometheus-prod-65-prod-eu-west-2.grafana.net/api/prom/api/v1/query?'+urllib.parse.urlencode({'query':expr}),token,username='3614732')
                checks.append({'panel':p['title'],'status':r.get('status'),'series':len(r.get('data',{}).get('result',[]))})
            except Exception as e:checks.append({'panel':p['title'],'error':type(e).__name__})
        r=H['request']('https://logs-prod-012.grafana.net/loki/api/v1/query_range?'+urllib.parse.urlencode({'query':'{job="runr/e2e"}','limit':'3'}),token,username='1803034')
        print(json.dumps({'panels':checks,'log_streams':len(r.get('data',{}).get('result',[]))},indent=2))
        (ROOT/'e2e-verification.json').write_text(json.dumps({'checked_at':time.time(),'panels':checks,'log_streams':len(r.get('data',{}).get('result',[]))},indent=2))


if __name__=='__main__':main()
