"""Read-only reconciliation of classification snapshot scopes."""
import collections
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/audit/blue_employer_cleanup_2026-10-09'
SNAP = ROOT / 'data/audit/title_collar_2026-10-08/nemo_resolved'

def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        yield from csv.DictReader(stream)

companies = list(rows(SNAP / 'companies_over_90_percent_blue.csv'))
quoted = {r['company_id'] for r in companies if int(r['classified_jobs']) >= 20}
approved = {r['company_id'] for r in rows(OUT / 'corrected_employer_scope.csv')}
groups = collections.Counter()
for r in rows(SNAP / 'jobs.csv'):
    for name, ids in [('quoted_90', quoted), ('approved', approved)]:
        if r['company_id'] in ids:
            groups[(name, r['source'], r['collar'], r['published'])] += 1
result = {
    'quoted_employers': len(quoted),
    'quoted_classified': sum(int(r['classified_jobs']) for r in companies if r['company_id'] in quoted),
    'quoted_approved_intersection': len(quoted & approved),
    'breakdown': [{'scope': k[0], 'source': k[1], 'collar': k[2], 'published': k[3], 'jobs': v} for k, v in sorted(groups.items())],
}
(OUT / 'count_reconciliation.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
