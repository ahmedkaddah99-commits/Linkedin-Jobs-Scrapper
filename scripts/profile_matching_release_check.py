"""Operator checks for profile matching. Never prints credentials or profiles."""
from __future__ import annotations
import argparse
import json
import os
import statistics
import time
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import dotenv_values
from backend.application.profile_job_matching import FEATURE_VERSION, evaluate_profile_match, profile_snapshot
from backend.domain.models import UserRecord

SERVICES = {'api': 'srv-d8q47dh194ac73df0acg', 'frontend': 'srv-d8q47dh194ac73df0a8g', 'worker': 'srv-d8s24fkm0tmc739t4h10'}


def render(path, *, payload=None):
    key = dotenv_values('user_config/.env').get('RENDER_API_KEY')
    request = Request('https://api.render.com/v1/' + path,
                      data=json.dumps(payload).encode() if payload is not None else None,
                      headers={'Authorization': 'Bearer '+str(key), 'Content-Type': 'application/json'})
    with urlopen(request, timeout=30) as response:
        raw = response.read()
        return json.loads(raw) if raw else {"http_status": response.status}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['status', 'deploy', 'benchmark'])
    parser.add_argument('--commit')
    args = parser.parse_args()
    if args.action == 'benchmark':
        profile = profile_snapshot(UserRecord(user_id='synthetic', email='synthetic@example.test', metadata={'profile': {
            'competencies': ['SQL', 'Python', 'Requirements analysis'], 'industry': 'Insurance',
            'recent_experience': [{'title': 'Data Analyst', 'start_date': '2022-01', 'end_date': '2025-01', 'description': 'SQL and Python reporting'}]}}))
        facts = {'version': FEATURE_VERSION, 'title': 'Data Analyst', 'levels': ['entry'], 'years_min': 2, 'industries': ['Insurance'],
                 'skills': [{'name': skill, 'requiredness': 'required', 'job_evidence': skill} for skill in ['SQL','Python','Excel','Power BI','Tableau','Data analysis','AWS','Azure','Scrum','Agile']]}
        timings = []
        for _ in range(100):
            started = time.perf_counter()
            for _ in range(25):
                evaluate_profile_match(facts, profile, today=date(2026,10,7))
            timings.append((time.perf_counter()-started)*1000)
        ordered = sorted(timings)
        print(json.dumps({'page_size': 25, 'samples': 100, 'p50_ms': round(statistics.median(timings),2), 'p95_ms': round(ordered[94],2), 'provider_calls': 0}))
        return
    result = {}
    for name, sid in SERVICES.items():
        if args.action == 'deploy':
            if not args.commit:
                raise ValueError('--commit required')
            deploy = render(f'services/{sid}/deploys', payload={'commitId': args.commit})
            result[name] = {k: deploy.get(k) for k in ('id','status','createdAt')}
        else:
            records = render(f'services/{sid}/deploys?limit=3')
            result[name] = [{'id': r['deploy']['id'], 'status': r['deploy']['status'], 'commit': r['deploy'].get('commit',{}).get('id')} for r in records]
    print(json.dumps(result))


if __name__ == '__main__':
    main()
