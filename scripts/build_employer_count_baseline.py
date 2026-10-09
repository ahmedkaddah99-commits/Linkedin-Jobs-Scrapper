"""Freeze the owner's existing classification decisions into a count baseline."""
import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.acquisition.employer_job_counts import count_collection, digest, install_ledger
from scripts.audit_title_collars import normalize_title, COMPILED, OCCUPATION_TERMS, MAX_OCCUPATION_WORDS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    db = args.output / 'employer-counts.sqlite3'
    connection = sqlite3.connect(db)
    install_ledger(connection)
    connection.execute('CREATE TABLE IF NOT EXISTS employer_baseline_catalog(job_id TEXT,version_id TEXT,category TEXT NOT NULL,PRIMARY KEY(job_id,version_id))')
    title_categories = defaultdict(set)
    total = 0
    unattributed = Counter()
    source = ROOT / 'data/audit/title_collar_2026-10-08/nemo_resolved/jobs.csv'
    with connection, source.open(encoding='utf-8-sig', newline='') as stream:
        for index, row in enumerate(csv.DictReader(stream)):
            category = row['collar']
            if not row['company_id']:
                unattributed[category] += 1
                continue
            titles = json.loads(row['titles'])
            for title in titles:
                title_categories[normalize_title(title)].add(category)
            sources = set(json.loads(row['sources']))
            counted_sources = sorted({'linkedin' if s.startswith('linkedin') else 'employer' for s in sources if s.startswith('linkedin') or s == 'employer'})
            total += count_collection(connection, company_id=row['company_id'], company_name=row['company'],
                receipt=digest('audit-baseline-2026-10-08', index), category=category, sources=counted_sources)
            connection.execute('INSERT OR IGNORE INTO employer_baseline_jobs VALUES (?,?)',
                (digest(row['company_id'], row['url'], normalize_title(row['title'])), category))
            if row['canonical_job_id']:
                connection.execute('INSERT OR IGNORE INTO employer_baseline_catalog VALUES (?,?,?)',
                    (row['canonical_job_id'], row['version_id'], category))
        connection.execute("INSERT OR REPLACE INTO employer_count_meta VALUES ('baseline_cutoff','2026-10-08T13:51:00+00:00')")
    # Conflicting standalone title decisions must not overwrite one another.
    cache = {title: next(iter(categories)) for title, categories in title_categories.items() if len(categories) == 1}
    bundle = {'decisions': cache, 'rules': {c: {name: rule.pattern for name, rule in rules} for c, rules in COMPILED.items()},
              'terms': OCCUPATION_TERMS, 'max_words': MAX_OCCUPATION_WORDS}
    (args.output / 'title-decisions.json').write_text(json.dumps(bundle, ensure_ascii=False), encoding='utf-8')
    report = {'new_baseline_receipts': total, 'classified_records_attributed': connection.execute('SELECT SUM(white_collar_count+blue_collar_count+not_a_job_count+insufficient_role_information_count) FROM employer_counts').fetchone()[0],
              'unattributed_records_by_category': dict(unattributed), 'employers': connection.execute('SELECT COUNT(*) FROM employer_counts').fetchone()[0],
              'counts': dict(zip([c[0] for c in connection.execute('SELECT * FROM employer_counts').description][2:],
                  connection.execute('SELECT SUM(white_collar_count),SUM(blue_collar_count),SUM(not_a_job_count),SUM(insufficient_role_information_count),SUM(employer_site_count),SUM(linkedin_count) FROM employer_counts').fetchone(), strict=True)),
              'title_cache_entries': len(cache), 'scope': 'All employers; existing categories unchanged; placeholders remain in their assigned category.'}
    (args.output / 'baseline-summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    connection.close()


if __name__ == '__main__':
    main()
