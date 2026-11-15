"""AUDIT/NET-OPS: recover observed apply links for unpublished focus jobs.

No URL is invented and no application is submitted. Default is audit only.
--apply reimports through the existing validation/archive path. Already-approved
jobs and versions currently being enriched are left untouched.
"""
from __future__ import annotations
import argparse,json,sqlite3,hashlib,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.acquisition.employer_focus import scope_reason
from backend.acquisition.quality import extract_application_candidates_from_html,canonicalize_url
from backend.acquisition.job_page_evidence import _application_targets_detail


def recover_link(row,cache):
    check=row.get('employer_focus',{}).get('live_check') or {}
    url=check.get('source_url')
    if not url or canonicalize_url(url).rstrip('/')!=canonicalize_url(row['job_detail_url']).rstrip('/'):return None
    path=cache/(hashlib.sha256(('GET'+url+'null').encode()).hexdigest()+'.json')
    if not path.exists():return None
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('status')!=200:return None
    # Candidate URLs use the same canonical host (including removal of www).
    # Normalize the observed trust context too; do not broaden host matching.
    target={'canonical_target_url':canonicalize_url(row['career_url']),
        'request_url':canonicalize_url(url),'provenance_url':canonicalize_url(row['company_website'])}
    candidates=extract_application_candidates_from_html(data.get('body',''),url,target=target,source_ats=row.get('source_ats',''))
    return next((c for c in candidates if c.get('verified') and _application_targets_detail(
        row['job_detail_url'],c['url'],row['title'].casefold())),None)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--cache',type=Path,required=True);p.add_argument('--db',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
    db=sqlite3.connect(a.db.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    fixes=[]
    for line in a.input.read_text(encoding='utf-8').splitlines():
        if not line:continue
        row=json.loads(line)
        if scope_reason(row):continue
        current=db.execute('''SELECT j.title,v.description,v.location,q.state,q.error_code,
            publication.status AS publication_status,publication.reason_codes_json,
            CASE WHEN pj.canonical_job_id IS NULL THEN 0 ELSE 1 END AS published,
            v.payload_json,v.apply_url FROM canonical_jobs j
            JOIN job_posting_versions v ON v.version_id=j.current_version_id
            LEFT JOIN job_enrichment_queue q ON q.version_id=v.version_id
            LEFT JOIN acquisition_publication_queue publication ON publication.canonical_job_id=j.canonical_job_id
            LEFT JOIN acquisition_publication_jobs pj ON pj.canonical_job_id=j.canonical_job_id
                AND pj.publication_id=(SELECT publication_id FROM acquisition_publication_head WHERE head_id=1)
            WHERE j.canonical_url IN (?,?) LIMIT 1''',(row['job_detail_url'],canonicalize_url(row['job_detail_url']))).fetchone()
        if (not current or current['published'] or current['state'] not in {'completed','review_required'}
                or current['error_code']=='blue_collar_excluded' or current['apply_url']):continue
        if current['publication_status']=='rejected' and 'unverified_generic_page' not in (current['reason_codes_json'] or ''):continue
        # Do not overwrite fresher source changes with historical preparation.
        if any(str(current[k] or '')!=str(row.get(k) or '') for k in ('title','description','location')):continue
        candidate=recover_link(row,a.cache)
        if candidate:
            fixes.append({**row,'application_url':candidate['url'],'apply_url':candidate['url'],
                'application_link_repair':{'source_url':row['employer_focus']['live_check']['source_url'],
                    'candidate':candidate,'verified_at':datetime.now(timezone.utc).isoformat()}})
    report={'recoverable_unpublished_application_links':len(fixes),'apply':a.apply,'already_published_changed':False}
    if a.apply and fixes:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in fixes),encoding='utf-8')
        subprocess.run([sys.executable,str(ROOT/'scripts/import_employer_focus.py'),'--input',str(a.output),'--db',str(a.db)],check=True)
    print(json.dumps(report))

if __name__=='__main__':main()
