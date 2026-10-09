"""Read-only inventory of database contents, sizes, and safe runtime bindings."""
import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def inspect_sqlite(path, tables):
    resolved = path.resolve(strict=True)
    connection = sqlite3.connect(resolved.as_uri()+'?mode=ro', uri=True, timeout=5)
    connection.execute('PRAGMA query_only=ON')
    connection.execute('BEGIN')
    schema = dict(connection.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
    result = {'path': str(path), 'resolved_path': str(resolved), 'main_file_bytes': resolved.stat().st_size,
              'wal_file_bytes': Path(str(resolved)+'-wal').stat().st_size if Path(str(resolved)+'-wal').exists() else 0,
              'table_names': sorted(schema),
              'rows': {table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in tables if table in schema}}
    for pragma in ('page_size', 'page_count', 'freelist_count'):
        result[pragma] = connection.execute('PRAGMA '+pragma).fetchone()[0]
    result['allocated_database_bytes'] = result['page_size']*result['page_count']
    result['free_database_bytes'] = result['page_size']*result['freelist_count']
    if 'employer_counts' in schema:
        cols = [r[1] for r in connection.execute('PRAGMA table_info(employer_counts)')][2:]
        result['counter_totals'] = dict(zip(cols, connection.execute('SELECT '+','.join(f'SUM({col})' for col in cols)+' FROM employer_counts').fetchone(), strict=True))
    connection.rollback()
    connection.close()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('local', 'vps', 'turso'))
    args = parser.parse_args()
    if sys.version_info[:3] != (3, 12, 7):
        raise RuntimeError('Python 3.12.7 required')
    result = {'as_of_utc': datetime.now(timezone.utc).isoformat(), 'mode': args.mode}
    if args.mode == 'local':
        result['database'] = inspect_sqlite(ROOT/'data/audit/employer_job_counts_2026-10-09/employer-counts.sqlite3',
            ['employer_counts', 'employer_count_receipts', 'employer_baseline_jobs', 'employer_baseline_catalog', 'employer_source_cursors'])
    elif args.mode == 'vps':
        from dotenv import dotenv_values
        env = {}
        for path in ('/opt/runr/.env.acquisition', '/opt/runr/.env.acquisition.provider', '/etc/runr/acquisition-catalog.env', '/etc/runr/catalog-storage.env'):
            if Path(path).exists():
                env.update(dotenv_values(path))
        safe = ('DATABASE_BACKEND', 'RUNR_DATA_DIR', 'RUNR_ACQUISITION_STATE_ROOT', 'RUNR_LINKEDIN_STATE_DIR', 'RUNR_EMPLOYER_STATE_DIR', 'RUNR_LINKEDIN_STATE_DB', 'RUNR_EMPLOYER_STATE_DB')
        result['publisher_environment_bindings'] = {k: env[k] for k in safe if k in env}
        result['turso_url_sha256'] = hashlib.sha256((env.get('TURSO_DATABASE_URL') or '').rstrip('/').encode()).hexdigest()
        result['databases'] = []
        for source in ('linkedin', 'employer'):
            for base in ('/srv/runr/state/active', '/srv/runr/state'):
                path = Path(base)/source/f'master_{source}_jobs_state.db'
                tables = ['jobs', 'companies', 'coverage_receipts', 'source_company_groups', 'search_cards', 'detail_queue', 'detail_attempts', 'job_company_observations']
                result['databases'].append(inspect_sqlite(path, tables))
        result['effective_units'] = subprocess.check_output(['systemctl','show','runr-acquisition-publisher.service','runr-acquisition-linkedin.service','runr-acquisition-employer.service','-p','WorkingDirectory','-p','EnvironmentFiles'], text=True)
    else:
        from dotenv import load_dotenv
        import os
        from scripts.snapshot_title_collar_audit import query
        load_dotenv(ROOT/'user_config/.env')
        result['turso_url_sha256'] = hashlib.sha256(os.environ['TURSO_DATABASE_URL'].rstrip('/').encode()).hexdigest()
        result['schema'] = query("SELECT name,sql FROM sqlite_master WHERE type='table'")
        tables = {r['name'] for r in result['schema']}
        result['table_count'] = len(tables)
        result['rows'] = {}
        for table in ('canonical_companies', 'canonical_jobs', 'job_posting_versions', 'job_source_observations', 'acquisition_targets', 'acquisition_publications', 'users', 'runs', 'reviews', 'application_packages', 'profile_job_facts', 'job_filter_intelligence'):
            if table in tables:
                result['rows'][table] = query(f'SELECT COUNT(*) AS n FROM {table}')[0]['n']
        result['current_published_memberships'] = query('SELECT COUNT(*) AS n FROM acquisition_publication_jobs WHERE publication_id=(SELECT publication_id FROM acquisition_publication_head WHERE head_id=1)')[0]['n']
        for pragma in ('page_size', 'page_count', 'freelist_count'):
            try:
                result[pragma] = query('PRAGMA '+pragma)[0][pragma]
            except Exception as exc:
                result[pragma] = {'unavailable': type(exc).__name__}
        if all(isinstance(result.get(k), int) for k in ('page_size','page_count','freelist_count')):
            result['allocated_database_bytes'] = result['page_size']*result['page_count']
            result['free_database_bytes'] = result['page_size']*result['freelist_count']
        result['schema_groups'] = {group: [t for t in sorted(tables) if any(term in t for term in terms)] for group, terms in {
            'catalog_and_acquisition': ['canonical', 'acquisition', 'job_posting', 'job_source'],
            'users_and_applications': ['user', 'workspace', 'run', 'review', 'application', 'candidate'],
            'intelligence_and_enrichment': ['intelligence', 'enrichment', 'profile_job', 'company_profile'],
            'billing': ['billing', 'payment', 'subscription', 'creem'],
        }.items()}
    result['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
