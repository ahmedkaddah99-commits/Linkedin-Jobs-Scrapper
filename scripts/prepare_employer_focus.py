"""Rebuild the intact employer export and produce an auditable enrichment scope."""
from __future__ import annotations
import argparse,csv,json,hashlib,sys,collections,re
from pathlib import Path
from functools import lru_cache
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.acquisition.employer_focus import SCOPE_VERSION,review_title_candidate
from backend.acquisition.job_lifecycle import exclusion_reason

def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    # Reuse the geography matcher that produced the owner's previous counts.
    sys.path.insert(0,str(ROOT.parent/'employer-scraper-local'))
    import region
    region.EUROPE={'DE'}
    classify=lru_cache(maxsize=None)(region.classify)
    sources=[ROOT/'outputs/company-jobs-repaired-20261109/jobs_repaired_final.csv',ROOT/'outputs/zero-job-retry-20261109/added_jobs.csv']
    hashes={str(path):digest(path) for path in sources}
    rows=[];seen=set();identities=set();candidates=[];dispositions=[];counts=collections.Counter()
    for path in sources:
        with path.open(encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                row={k:v for k,v in row.items() if k}
                url=row.get('job_detail_url') or '';title=row.get('title') or ''
                assert urlsplit(url).scheme in ('https','http') and urlsplit(url).hostname
                assert title.strip() and not title.strip().isdigit()
                assert url not in seen;seen.add(url)
                key=(row.get('source_platform'),row.get('source_tenant'),row.get('job_id'))
                if row.get('job_id'):assert key not in identities;identities.add(key)
                rows.append(row)
                country=row.get('country') or ''
                location=' | '.join(row.get(k) or '' for k in ('location','city','region'))
                scope=classify(country if country.strip() else location)
                de=scope[0]=='europe' and 'DE' in scope[1].split(',')
                if not de or not review_title_candidate(title):continue
                counts['germany_business_function_candidates']+=1
                rawfile=Path(row.get('raw_record_file') or '')
                if not rawfile.is_absolute():rawfile=ROOT/'outputs/verified-company-dry-run-20261108'/rawfile
                reason=''
                if not rawfile.is_file():reason='raw_evidence_missing'
                if not row.get('description','').strip() or len(row['description'].strip())<80:reason='source_description_incomplete'
                age_reason=exclusion_reason({'date_posted':row.get('date_posted'),'first_seen_at':row.get('date_collected')})
                if age_reason:reason=age_reason
                if reason:
                    dispositions.append({'rank':row['rank'],'company_name':row['company_name'],'title':title,'job_detail_url':url,'reason':reason})
                    counts[reason]+=1
                    if reason!='source_description_incomplete':continue
                record={**row,'country':'DE','location':row.get('location') or ', '.join(filter(None,(row.get('city'),'Germany'))),
                    'url':url,'job_detail_url':url,'description':row.get('description',''),
                    'job_id':row.get('job_id') or hashlib.sha256(url.encode()).hexdigest(),
                    'source_ats':row.get('source_platform') or 'career_site',
                    'source_provider':row.get('source_platform') or 'career_site',
                    'source_job_url':url,'source_company_name':row.get('legal_employer') or row['company_name'],
                    'source_company_url':row.get('company_website'),
                    'first_seen_at':row.get('date_collected'),
                    'employer_focus':{'scope_version':SCOPE_VERSION,'registry_rank':row['rank'],
                        'workbook_company_name':row['company_name'],'legal_employer':row.get('legal_employer'),
                        'geography_evidence':{'source_country':country,'source_location':location,'country_codes':scope[1]},
                        'raw_record_sha256':digest(rawfile),'raw_record_file':str(rawfile.resolve()),
                        'experience_decision':'deferred_to_validated_enrichment'}}
                raw=json.loads(rawfile.read_text(encoding='utf-8'))
                record['source_raw_payload']=raw
                for field in ('application_url','apply_url','applyUrl','applicationUrl','apply_link'):
                    value=raw.get(field)
                    if isinstance(value,str) and value.startswith(('http://','https://')):record[field]=value
                candidates.append(record)
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with (a.output/'jobs_clean.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    with (a.output/'candidates.jsonl').open('w',encoding='utf-8') as f:
        for row in candidates:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    with (a.output/'dispositions.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['rank','company_name','title','job_detail_url','reason']);w.writeheader();w.writerows(dispositions)
    assert all(digest(path)==hashes[str(path)] for path in sources)
    report={'sources':hashes,'clean_rows':len(rows),'candidates_for_live_check':len(candidates),'candidate_counts':dict(counts),'scope_version':SCOPE_VERSION}
    (a.output/'preparation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)

if __name__=='__main__':main()
