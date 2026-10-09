"""Read current publication progress without emitting credentials or job payloads."""
import json
from pathlib import Path

from catalog import check_catalog


def main():
    crosswalk_path = Path('/srv/runr/state/active/company_identity_crosswalk.json')
    if crosswalk_path.is_file():
        crosswalk = json.loads(crosswalk_path.read_text())
        report = crosswalk.get('report') or {}
        print(json.dumps({'identity_input_counts': {
            'mapping': len(crosswalk.get('mapping_by_identity') or {}),
            'canonical_rows': len(report.get('canonical_rows') or []),
            'merge_receipts': len(report.get('merge_receipts') or []),
        }}))
    catalog = check_catalog(Path('/opt/runr/.env.acquisition'))
    print(json.dumps({'catalog': catalog}))
    if not catalog.get('access_ok'):
        return
    from backend.database.connection import connect_database
    connection = connect_database(Path('/var/lib/runr/acquisition-data/runr.sqlite3'))
    try:
        row = connection.execute(
            'SELECT cycle_id,status,started_at,completed_at,updated_at,'
            'jobs_observed,jobs_new,jobs_rejected,jobs_published,error_code '
            'FROM acquisition_cycles ORDER BY scheduled_at DESC LIMIT 1'
        ).fetchone()
        cycle = dict(row) if row else {}
        tasks = connection.execute(
            'SELECT status,COUNT(*) AS count FROM acquisition_tasks '
            'WHERE cycle_id=? GROUP BY status', (cycle.get('cycle_id', ''),)
        ).fetchall()
        print(json.dumps({'latest_cycle': cycle, 'tasks': [dict(task) for task in tasks]}))
    finally:
        connection.close()


if __name__ == '__main__':
    main()
