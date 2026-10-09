"""Read-only scope and dependency evidence for requested employer cleanup."""
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.snapshot_title_collar_audit import query

SOURCE = ROOT / 'data/audit/title_collar_2026-10-08/nemo_resolved'
OUT = ROOT / 'data/audit/blue_employer_cleanup_2026-10-09'


def main():
    load_dotenv(ROOT / 'user_config/.env')
    OUT.mkdir(parents=True, exist_ok=True)
    with (SOURCE / 'companies_over_60_percent_blue.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = [r for r in csv.DictReader(stream) if int(r['classified_jobs']) >= 20]
    selected = {r['company_id'] for r in rows}
    placeholders = Counter()
    with (SOURCE / 'jobs.csv').open(encoding='utf-8-sig', newline='') as stream:
        for r in csv.DictReader(stream):
            if r['company_id'] in selected and r['collar'] == 'blue' and r['reason'] == 'owner_policy_placeholder':
                placeholders[r['company_id']] += 1
    for r in rows:
        r['placeholder_titles_currently_blue'] = placeholders[r['company_id']]
        b, w = int(r['blue_jobs']) - placeholders[r['company_id']], int(r['white_jobs'])
        r['corrected_blue_jobs'] = b
        r['corrected_classified_jobs'] = b + w
        r['corrected_blue_percentage'] = round(100*b/(b+w), 4) if b+w else ''
        r['still_above_60_excluding_placeholders'] = bool(b+w and b*5 > (b+w)*3)
    with (OUT / 'requested_employer_scope.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    summary = {'requested_employer_records': len(rows), 'snapshot_white_blue_jobs': sum(int(r['classified_jobs']) for r in rows),
        'employers_with_placeholder_blue': sum(bool(r['placeholder_titles_currently_blue']) for r in rows),
        'placeholder_titles_currently_blue': sum(placeholders.values()),
        'still_above_60_excluding_placeholders': sum(r['still_above_60_excluding_placeholders'] for r in rows),
        'not_above_60_or_no_occupational_evidence_after_correction': sum(not r['still_above_60_excluding_placeholders'] for r in rows),
        'production_changes': False}
    schema = query("SELECT name,sql FROM sqlite_master WHERE type='table'")
    (OUT / 'live_schema.json').write_text(json.dumps(schema, indent=2), encoding='utf-8')
    live = []
    ids = sorted(selected)
    for start in range(0, len(ids), 100):
        batch = ids[start:start+100]
        marks = ','.join('?' for _ in batch)
        live.extend(query(f'SELECT company_id,COUNT(*) AS jobs FROM canonical_jobs WHERE company_id IN ({marks}) GROUP BY company_id', batch))
    (OUT / 'live_catalog_counts.json').write_text(json.dumps(live, indent=2), encoding='utf-8')
    summary['live_catalog_jobs_in_original_scope'] = sum(r['jobs'] for r in live)
    summary['original_scope_employers_with_live_catalog_jobs'] = len(live)
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary), flush=True)
    print(json.dumps([r['name'] for r in schema if any(s in r['name'] for s in ('application','personalized','company','job'))]), flush=True)


if __name__ == '__main__':
    main()
