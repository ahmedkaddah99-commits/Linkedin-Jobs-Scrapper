"""Local Webshare-only additional-job sample audit; no production writes."""
import argparse
import csv
import gzip
import json
import re
import sys
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.master_linkedin_jobs_catalog import load_webshare_proxies, build_search_url, parse_search_page, canonical_company_url
from scripts.master_employer_jobs_catalog import EmployerCompany, CollectorLimits, collect_company
from backend.connectors.company_career_discovery import FetchResult
from backend.connectors.ats_router import detect_ats
from scripts.audit_title_collars import classify_titles
import scripts.classify_unresolved_title_nemo as nemo

BASE = ROOT / 'data/audit/title_collar_2026-10-08'
OUT = ROOT / 'data/audit/blue_employer_recheck_2026-10-09'


def key(url):
    if url.startswith('linkedin:'):
        return url
    match = re.search(r'/jobs/view/(?:[^/?]*-)?(\d+)', url)
    if match:
        return 'linkedin:' + match[1]
    p = urlsplit(url)
    query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
        if not k.lower().startswith('utm_') and k.lower() not in {'trackingid', 'refid', 'gh_src', 'lever-source', 'origin', 'source'}])
    return urlunsplit(('', p.netloc.lower(), p.path.rstrip('/'), query, ''))


def recorded_source_seed(row):
    roots = set()
    for value in row['existing_url_keys']:
        if value.startswith('linkedin:'):
            continue
        p = urlsplit('https:' + value)
        host = p.hostname or ''
        if not host or host.endswith('linkedin.com'):
            continue
        parts = [s for s in p.path.split('/') if s]
        root = 'https://' + p.netloc
        if host in ('boards.greenhouse.io', 'job-boards.greenhouse.io', 'jobs.lever.co', 'jobs.smartrecruiters.com', 'apply.workable.com'):
            if not parts:
                continue
            root += '/' + parts[0]
        roots.add(root)
    if len(roots) == 1:
        return roots.pop()
    # Multiple recorded sources are not merged or guessed from a company name.
    return ''


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    cohort = {r['company_id']: r for r in csv.DictReader((BASE / 'nemo_resolved/companies_over_60_percent_blue.csv').open(encoding='utf-8-sig')) if int(r['classified_jobs']) < 20}
    mappings = {}
    with gzip.open(BASE / 'catalog.jsonl.gz', 'rt', encoding='utf-8') as f:
        for line in f:
            r = json.loads(line)
            if r['kind'] == 'identity':
                mappings[r['source_identity_key']] = r['winner_company_id']

    def resolved(cid):
        return mappings.get('old-company:' + cid, mappings.get('canonical:' + cid, mappings.get(cid, cid)))

    seeds = defaultdict(list)
    with (ROOT / 'data/acquisition/inputs/company_sources_linkedin_ids.csv').open(encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            cid = resolved(r['canonical_CompanyID'])
            if cid in cohort:
                seeds[cid].append(r)
    linkedin = defaultdict(set)
    with gzip.open(BASE / 'producers.jsonl.gz', 'rt', encoding='utf-8') as f:
        for line in f:
            r = json.loads(line)
            if r['kind'] == 'job' and r.get('linkedin_company_id') and resolved(r['company_id']) in cohort:
                linkedin[resolved(r['company_id'])].add(str(r['linkedin_company_id']))
    old_urls = defaultdict(set)
    with (BASE / 'nemo_resolved/jobs.csv').open(encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            if r['company_id'] in cohort and r['url']:
                old_urls[r['company_id']].add(key(r['url']))
    result = []
    for cid, original in cohort.items():
        candidates = seeds[cid]
        numeric = {r.get('linkedin_company_id', '').strip() for r in candidates if r.get('linkedin_company_id', '').strip().isdigit()} | linkedin[cid]
        websites = sorted({r.get('website_url', '').strip() for r in candidates if r.get('website_url', '').startswith('http')})
        company_urls = sorted({canonical_company_url(r.get('linkedin_company_url', '')) for r in candidates if r.get('linkedin_company_url')})
        result.append({**original, 'linkedin_company_id': next(iter(numeric)) if len(numeric) == 1 else '',
                       'linkedin_company_urls': company_urls, 'website_url': websites[0] if len(websites) == 1 else '',
                       'existing_url_keys': sorted(old_urls[cid]), 'identity_ambiguous': len(numeric) > 1 or len(websites) > 1})
    for row in result:
        if not row['website_url']:
            row['website_url'] = recorded_source_seed(row)
            row['website_seed_provenance'] = 'same_employer_recorded_job_urls' if row['website_url'] else 'unavailable_or_multiple_hosts'
    (OUT / 'cohort.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'cohort': len(result), 'linkedin_ids': sum(bool(r['linkedin_company_id']) for r in result),
                      'websites': sum(bool(r['website_url']) for r in result)}), flush=True)
    return result


def collect(row, proxies, locks):
    path = OUT / 'employers' / (row['company_id'] + '.json')
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    import hashlib
    index = int(hashlib.sha256(row['company_id'].encode()).hexdigest()[:8], 16) % len(proxies)
    session = requests.Session()
    session.trust_env = False
    session.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36'
    attempts, jobs, seen = [], [], {key(u) for u in row['existing_url_keys']}

    def request(url, **kwargs):
        if len(attempts) >= 18:
            raise requests.RequestException('local_company_request_budget_exhausted')
        proxy_index = (index + len(attempts)) % len(proxies)
        kwargs['timeout'] = 12
        kwargs['proxies'] = {'http': proxies[proxy_index].url, 'https': proxies[proxy_index].url}
        method = 'POST' if kwargs.get('json') is not None else 'GET'
        record = {'url': url, 'transport': 'webshare'}
        attempts.append(record)
        try:
            with locks[proxy_index]:
                response = session.request(method, url, **kwargs)
            record['status'] = response.status_code
            response.transport_used = 'webshare'
            return response
        except requests.RequestException as error:
            record['error'] = type(error).__name__
            record['error_detail'] = str(error).replace(proxies[proxy_index].url, '[proxy]')[:400] if isinstance(error, requests.exceptions.SSLError) else ''
            raise
    request.last_transport = 'webshare'

    def add(title, url, location='', source=''):
        identity = key(url)
        if title and identity and identity not in seen and len(jobs) < 10:
            seen.add(identity)
            jobs.append({'title': title, 'url': url, 'location': location, 'source': source, 'identity_key': identity})

    errors = []
    try:
        if row['linkedin_company_id']:
            for start in (0, 25, 50):
                try:
                    response = request(build_search_url(row['linkedin_company_id'], start=start))
                    parsed = parse_search_page(response.text) if response.status_code == 200 else None
                    if not parsed or not parsed.is_usable:
                        errors.append('linkedin_http_' + str(response.status_code) if not parsed else 'linkedin_' + parsed.body_class)
                        if start == 0:
                            continue
                        break
                    for card in parsed.cards:
                        if row['linkedin_company_urls'] and canonical_company_url(card.company_url) not in row['linkedin_company_urls']:
                            continue
                        add(card.title, card.linkedin_job_url, card.location, 'linkedin_search_card')
                    if len(jobs) >= 10 or parsed.is_no_results:
                        break
                except requests.RequestException as error:
                    errors.append(type(error).__name__)
        if len(jobs) < 10 and row['website_url']:
            def fetch(url, **kwargs):
                try:
                    response = request(url, **kwargs)
                    return FetchResult(url, response.url, response.status_code, response.headers.get('content-type', ''), response.text[:1500000], transport='webshare')
                except requests.RequestException as error:
                    return FetchResult(url, url, 0, error=type(error).__name__, transport='webshare')
            fetch.requester = request
            result = collect_company(EmployerCompany(row['company_id'], row['company'], row['website_url'],
                verified_ats_url=row['website_url'] if detect_ats(row['website_url']) else ''), fetch,
                CollectorLimits(max_targets=2, max_job_links=20, max_pages=2, allow_browser_fallback=False, timeout_seconds=12))
            errors.append('employer_' + result.resolved_outcome())
            for job in result.jobs:
                add(job.get('job_title', ''), job.get('source_job_url', ''), job.get('location', ''), 'employer_site')
    except Exception as error:
        errors.append(type(error).__name__)
    finally:
        session.close()
    if not row['linkedin_company_id'] and not row['website_url']:
        errors.append('no_unambiguous_recorded_source')
    record = {'company_id': row['company_id'], 'company': row['company'], 'collected_at': datetime.now(timezone.utc).isoformat(),
              'additional_jobs': jobs, 'attempts': attempts, 'outcomes': errors,
              'sample_status': 'enough_additional_jobs' if len(jobs) >= 3 else 'insufficient_additional_jobs'}
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record


def finish(cohort):
    OUT.mkdir(exist_ok=True)
    decisions = {r['title']: r for r in csv.DictReader((BASE / 'nemo_resolved/title_decisions.csv').open(encoding='utf-8-sig'))}
    prior_jobs = OUT / 'additional_jobs.csv'
    if prior_jobs.exists():
        with prior_jobs.open(encoding='utf-8-sig', newline='') as stream:
            for r in csv.DictReader(stream):
                if r['category'] != 'unresolved':
                    decisions[r['title']] = {'category': r['category'], 'reason': r['reason']}
    pending = set()
    aliases = defaultdict(set)
    with gzip.open(BASE / 'catalog.jsonl.gz', 'rt', encoding='utf-8') as stream:
        for line in stream:
            item = json.loads(line)
            if item['kind'] == 'url_alias':
                aliases[item['canonical_job_id']].add(key(item['url']))
    known = {r['company_id']: {key(u) for u in r['existing_url_keys']} for r in cohort}
    placeholder_counts = Counter()
    with (BASE / 'nemo_resolved/jobs.csv').open(encoding='utf-8-sig', newline='') as stream:
        for item in csv.DictReader(stream):
            if item['company_id'] in known:
                known[item['company_id']].update(aliases.get(item['canonical_job_id'], ()))
                if item['collar'] == 'blue' and item['reason'] == 'owner_policy_placeholder':
                    placeholder_counts[item['company_id']] += 1
    records = []
    for row in cohort:
        path = OUT / 'employers' / (row['company_id'] + '.json')
        if path.exists():
            record = json.loads(path.read_text(encoding='utf-8'))
            record['additional_jobs'] = [j for j in record['additional_jobs'] if key(j['url']) not in known[row['company_id']]]
            records.append((row, record))
            for job in record['additional_jobs']:
                if job['title'] not in decisions:
                    pending.add(job['title'])
    titles = sorted(pending)
    nemo.OUT = OUT / 'nemo'
    (nemo.OUT / 'calls').mkdir(parents=True, exist_ok=True)
    batches = [[{'id': i, 'title': titles[i]} for i in range(start, min(start+15, len(titles)))] for start in range(0, len(titles), 15)]
    failures = []
    with ThreadPoolExecutor(max_workers=24) as pool:
        futures = {pool.submit(nemo.classify_retry, b): b for b in batches}
        for i, future in enumerate(as_completed(futures), 1):
            try:
                for d in future.result():
                    decisions[titles[d['id']]] = d
            except Exception as error:
                failures.append({'ids': [r['id'] for r in futures[future]], 'error': type(error).__name__})
            if i % 10 == 0:
                print(json.dumps({'classified_batches': i, 'total': len(batches)}), flush=True)
    result_rows, job_rows = [], []
    for row, record in records:
        counts = Counter()
        for job in record['additional_jobs']:
            title = job['title']
            d = decisions.get(title, {'category': 'unresolved', 'reason': 'nemo_processing_failure'})
            counts[d['category']] += 1
            job_rows.append({'company_id': row['company_id'], 'company': row['company'], **job, 'category': d['category'], 'reason': d['reason']})
        blue, white = int(row['blue_jobs']), int(row['white_jobs'])
        after_b, after_w = blue + counts['blue'], white + counts['white']
        enough = len(record['additional_jobs']) >= 3 and counts['blue']+counts['white'] >= 3 and not counts['unresolved']
        status = ('still_above_60_percent' if after_b*5 > (after_b+after_w)*3 else 'no_longer_above_60_percent') if enough else 'inconclusive'
        placeholders = placeholder_counts[row['company_id']]
        clean_b = after_b - placeholders
        clean_total = clean_b + after_w
        clean_status = ('still_above_60_percent' if clean_b*5 > clean_total*3 else 'no_longer_above_60_percent') if enough and clean_total else 'inconclusive'
        result_rows.append({'company': row['company'], 'company_id': row['company_id'], 'before_blue': blue, 'before_white': white,
            'before_blue_percentage': row['blue_percentage'], 'additional_jobs': len(record['additional_jobs']), 'additional_blue': counts['blue'],
            'additional_white': counts['white'], 'additional_not_a_job': counts['not_a_job'], 'additional_insufficient_role_information': counts['insufficient_role_information'],
            'additional_unresolved': counts['unresolved'], 'after_blue': after_b, 'after_white': after_w,
            'after_blue_percentage': round(after_b/(after_b+after_w)*100,4), 'conclusion': status,
            'baseline_placeholder_blue': placeholders,
            'after_blue_percentage_excluding_placeholders': round(clean_b/clean_total*100,4) if clean_total else '',
            'conclusion_excluding_placeholders': clean_status,
            'sample_status': 'enough_additional_jobs' if len(record['additional_jobs']) >= 3 else 'insufficient_additional_jobs', 'outcomes': ' | '.join(record['outcomes'])})
    for filename, rows in [('employer_ratio_recheck.csv', result_rows), ('additional_jobs.csv', job_rows)]:
        if rows:
            with (OUT / filename).open('w', encoding='utf-8-sig', newline='') as f:
                w=csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    summary = {'target_employers': len(cohort), 'attempted_employers': len(records), 'additional_jobs': len(job_rows),
               'conclusions': dict(Counter(r['conclusion'] for r in result_rows)), 'model_failures': failures,
               'conclusions_excluding_placeholders': dict(Counter(r['conclusion_excluding_placeholders'] for r in result_rows)),
               'production_changes': False, 'ratio': 'blue / (blue + white), strictly >60%',
               'minimum_for_conclusion': '3 additional white/blue jobs; fewer is inconclusive',
               'limitations': 'Small convenience sample; prior placeholder-blue counts remain in baseline. Current search cards are not detail-page availability verification.'}
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--finish-only', action='store_true')
    parser.add_argument('--retry-transport-failures', action='store_true')
    args = parser.parse_args()
    load_dotenv(ROOT / 'user_config/.env')
    cohort_path = OUT / 'cohort.json'
    cohort = json.loads(cohort_path.read_text(encoding='utf-8')) if cohort_path.exists() else prepare()
    for row in cohort:
        if not row['website_url']:
            row['website_url'] = recorded_source_seed(row)
            row['website_seed_provenance'] = 'same_employer_recorded_job_urls' if row['website_url'] else 'unavailable_or_multiple_hosts'
    cohort_path.write_text(json.dumps(cohort, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.limit:
        cohort = cohort[:args.limit]
    if args.retry_transport_failures:
        retry_rows = []
        preserved = OUT / 'transport_failed_records'
        preserved.mkdir(exist_ok=True)
        for row in cohort:
            path = OUT / 'employers' / (row['company_id'] + '.json')
            if not path.exists():
                continue
            record = json.loads(path.read_text(encoding='utf-8'))
            if record['attempts'] and all(a.get('error') for a in record['attempts']):
                retry_rows.append(row)
                path.replace(preserved / path.name)
        print(json.dumps({'transport_retry_employers': len(retry_rows)}), flush=True)
        collection_cohort = retry_rows
    else:
        collection_cohort = cohort
    if not args.finish_only:
        proxies = load_webshare_proxies()
        print(json.dumps({'proxy_count': len(proxies), 'targets': len(cohort)}), flush=True)
        locks = [threading.Semaphore(1) for _ in proxies]
        (OUT / 'employers').mkdir(exist_ok=True)
        with ThreadPoolExecutor(max_workers=32) as pool:
            futures = [pool.submit(collect, row, proxies, locks) for row in collection_cohort]
            counts = Counter()
            for i, future in enumerate(as_completed(futures), 1):
                r = future.result()
                counts[r['sample_status']] += 1
                if i % 25 == 0:
                    print(json.dumps({'employers_done': i, 'total': len(cohort), 'samples': dict(counts)}), flush=True)
    finish(cohort)


if __name__ == '__main__':
    main()
