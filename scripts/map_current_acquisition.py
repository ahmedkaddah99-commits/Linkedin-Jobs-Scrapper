"""Read-only, company-first snapshot of live acquisition and publication."""
import json
import sys
import subprocess
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone


def remote():
    import os, sqlite3, csv
    sys.path.insert(0, '/opt/runr')
    for path in ['/opt/runr/.env.acquisition', '/etc/runr/acquisition-catalog.env']:
        for line in Path(path).read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k,v=line.split('=',1);os.environ[k.strip()]=v.strip().strip(chr(34)).strip(chr(39))
    from backend.database.connection import connect_database
    from backend.application.company_identity_canonicalization import resolve_company_id
    conn=connect_database(Path('/nonexistent/audit.sqlite3'))
    def rows(sql,params=()):return [dict(r) for r in conn.execute(sql,params).fetchall()]
    def clean(v):return str(v or '').strip().lower() not in {'','//','unknown','none','null','n/a','-'}
    names=['website','domain','industry','company_size','headquarters','linkedin_company_id','logo']
    expressions=[]
    for name in names:
        for section in ['fields','additional_fields']:
            expressions.append(f"json_extract(p.profile_json,'$.{section}.{name}.value') AS {section}_{name}")
    companies=rows('SELECT c.company_id,c.canonical_name,p.logo_source_url,p.logo_object_key,p.logo_verified_at,'+','.join(expressions)+' FROM canonical_companies c LEFT JOIN canonical_company_profiles p ON p.company_id=c.company_id')
    eligible={'linkedin':set(),'employer_site':set()}
    manifest=json.loads(Path(os.environ.get('RUNR_ACQUISITION_MANIFEST','/srv/runr/shared/inputs/SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json')).read_text())
    crosswalk=json.loads(Path(os.environ.get('RUNR_COMPANY_IDENTITY_CROSSWALK','/srv/runr/state/active/company_identity_crosswalk.json')).read_text()).get('mapping_by_identity',{})
    for task in manifest['tasks']:
        source=task['source'];cid=resolve_company_id({'canonical_company_id':task['canonical_company_id']},crosswalk) or task['canonical_company_id']
        eligible.setdefault(source,set()).add(cid)
    counts=Counter();ready_ids=[];company_queue=[]
    careers={r['company_id'] for r in rows("SELECT DISTINCT company_id FROM canonical_company_urls WHERE url_type IN ('careers','ats_jobs')")}
    for c in companies:
        cid=c['company_id']
        present={n:clean(c.get('fields_'+n)) or clean(c.get('additional_fields_'+n)) for n in names}
        logo=clean(c['logo_source_url']) or clean(c['logo_object_key']) or present['logo']
        core=clean(c['canonical_name']) and logo and all(present[n] for n in ['website','industry','company_size','headquarters'])
        counts['total_companies']+=1;counts['linkedin_id_present']+=present['linkedin_company_id'];counts['career_url_present']+=cid in careers
        counts['core_populated']+=core
        if core:
            ready_ids.append(cid)
            counts['core_with_linkedin_id']+=present['linkedin_company_id'];counts['core_with_career_url']+=cid in careers
            counts['core_in_linkedin_manifest']+=cid in eligible.get('linkedin',set())
            counts['core_linkedin_id_not_in_manifest']+=present['linkedin_company_id'] and cid not in eligible.get('linkedin',set())
            counts['core_in_employer_manifest']+=cid in eligible.get('employer_site',set())
            counts['core_with_verified_logo_timestamp']+=clean(c['logo_verified_at'])
        company_queue.append({'company_id':cid,'core_populated':bool(core),'linkedin_id_present':present['linkedin_company_id'],'in_linkedin_manifest':cid in eligible.get('linkedin',set()),'career_url_present':cid in careers})
    head=rows('SELECT publication_id,updated_at FROM acquisition_publication_head WHERE head_id=1')[0]
    catalog={'head':head,'head_jobs':rows('SELECT COUNT(*) AS n FROM acquisition_publication_jobs WHERE publication_id=?',(head['publication_id'],))[0]['n'],
        'lifecycle':rows('SELECT lifecycle_state,COUNT(*) AS jobs,COUNT(DISTINCT company_id) AS companies FROM canonical_jobs GROUP BY lifecycle_state'),
        'checkpoints':rows('SELECT source,source_rowid,bootstrap_complete,updated_at FROM acquisition_publisher_checkpoints')}
    source={}
    li=sqlite3.connect('file:'+os.environ['RUNR_LINKEDIN_STATE_DB']+'?mode=ro',uri=True)
    latest=li.execute('SELECT run_id,started_at,finished_at,status FROM runs ORDER BY started_at DESC LIMIT 1').fetchone()
    source['linkedin']={'jobs_rows':li.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],
        'company_observation_rows':li.execute('SELECT COUNT(*) FROM job_company_observations').fetchone()[0],
        'distinct_observed_job_ids':li.execute('SELECT COUNT(DISTINCT linkedin_job_id) FROM job_company_observations').fetchone()[0],
        'latest_run':list(latest),
        'latest_detail_errors':[list(r) for r in li.execute('SELECT status,error_class,COUNT(*) FROM detail_attempts WHERE run_id=? GROUP BY status,error_class',(latest[0],))],
        'latest_scan_status':[list(r) for r in li.execute('SELECT status,COUNT(*) FROM company_scans WHERE run_id=? GROUP BY status',(latest[0],))],
        'recent_runs':[list(r) for r in li.execute('SELECT run_id,mode,started_at,finished_at,status FROM runs ORDER BY started_at DESC LIMIT 6')]}
    li.close()
    em=sqlite3.connect('file:'+os.environ['RUNR_EMPLOYER_STATE_DB']+'?mode=ro',uri=True)
    source['employer']={'jobs_rows':em.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],
        'companies_rows':em.execute('SELECT COUNT(*) FROM companies').fetchone()[0],
        'company_status':[list(r) for r in em.execute('SELECT status,COUNT(*) FROM companies GROUP BY status')],
        'coverage':[list(r) for r in em.execute('SELECT classification,COUNT(*) FROM coverage_receipts GROUP BY classification')],
        'stored_jobs_by_provider':[list(r) for r in em.execute("SELECT json_extract(payload_json,'$.source_provider'),COUNT(*) FROM jobs GROUP BY json_extract(payload_json,'$.source_provider')")]}
    em.close()
    res=sqlite3.connect('file:/srv/runr/state/enrichment/linkedin_id_resolution.sqlite3?mode=ro',uri=True)
    source['resolver']={'rows':res.execute('SELECT COUNT(*) FROM url_resolution').fetchone()[0],
        'statuses':[list(r) for r in res.execute('SELECT status,COUNT(*) FROM url_resolution GROUP BY status')],
        'last_result_updated':res.execute('SELECT MAX(updated_at) FROM url_resolution').fetchone()[0],
        'last_request_recorded':res.execute('SELECT MAX(recorded_at) FROM request_log').fetchone()[0]}
    res.close()
    limits={k:os.environ.get(k,'wrapper_default') for k in ['RUNR_LINKEDIN_MAX_REQUESTS','RUNR_LINKEDIN_MAX_COMPANIES','RUNR_EMPLOYER_MAX_REQUESTS','RUNR_EMPLOYER_MAX_COMPANIES','RUNR_PUBLISHER_SOURCE_ROW_BATCH_SIZE','RUNR_SOURCE_RUN_TIMEOUT_SECONDS']}
    receipts={}
    for name in ['linkedin','employer','publisher']:
        p=Path('/srv/runr/exports/receipts/'+name+'-latest-metrics.json')
        try:d=json.loads(p.read_text())
        except ValueError:d={}
        receipts[name]={k:v for k,v in d.items() if not isinstance(v,(dict,list))}
    result={'at':datetime.now(timezone.utc).isoformat(),'company_readiness_definition':['name','website','industry','size','headquarters','logo_reference'],
        'company_counts':dict(counts),'manifest_counts':manifest['counts'],'manifest_sources':{k:len(v) for k,v in eligible.items()},
        'catalog':catalog,'source_stores':source,'limits':limits,'receipts':receipts,'company_queue':company_queue}
    conn.close();print(json.dumps(result))


def main():
    if '--remote' in sys.argv:
        remote();return
    r=subprocess.run(['ssh','runr-vps','sudo /opt/runr/.venv/bin/python - --remote'],input=Path(__file__).read_bytes(),capture_output=True,timeout=240)
    if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace')[-1500:])
    report=json.loads(r.stdout)
    output=Path(__file__).resolve().parents[1]/'data/audit/current_pipeline_2026-09-28'
    output.mkdir(parents=True,exist_ok=True)
    (output/'snapshot.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='company_queue'},indent=2))


if __name__=='__main__':main()
