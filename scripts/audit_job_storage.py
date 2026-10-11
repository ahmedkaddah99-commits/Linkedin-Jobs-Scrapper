"""Read-only job storage size audit. Prints aggregate sizes, never job content."""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import dotenv_values
from backend.database.connection import connect_database

def main():
    os.environ.update({k: v for k, v in dotenv_values(ROOT / 'user_config/.env').items() if v is not None})
    connection = connect_database(ROOT / 'data/audit/job_storage_2026-10-08/probe.sqlite3')
    for table, columns in [('job_source_observations', ['payload_json', 'raw_payload_json']), ('job_posting_versions', ['payload_json', 'description'])]:
        total = connection.fetch_read_rows(f'SELECT count(*) AS rows FROM {table}')[0][0]
        expressions = ','.join(f'COALESCE(SUM(length(CAST({c} AS BLOB))),0)' for c in columns)
        row = connection.fetch_read_rows(f'SELECT count(*),{expressions} FROM (SELECT * FROM {table} ORDER BY rowid DESC LIMIT 100)')[0]
        print(json.dumps({'table': table, 'total_rows': total, 'sample_rows': row[0], 'bytes': {c: row[i+1] for i,c in enumerate(columns)}}), flush=True)
        if 'payload_json' in columns:
            rows = connection.fetch_read_rows(f"SELECT j.key, SUM(length(CAST(j.value AS BLOB))) bytes FROM (SELECT payload_json FROM {table} ORDER BY rowid DESC LIMIT 100) s, json_each(s.payload_json) j GROUP BY j.key ORDER BY bytes DESC LIMIT 20")
            print(json.dumps({'table': table, 'sample_latest': 100, 'fields': [[r[0],r[1]] for r in rows]}), flush=True)
    connection.close()

if __name__ == '__main__':
    main()

