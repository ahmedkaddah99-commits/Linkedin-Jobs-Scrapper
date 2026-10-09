"""Read-only producer schemas for maintenance planning."""
import json
import sqlite3
for source in ('linkedin','employer'):
    c=sqlite3.connect(f'file:/srv/runr/state/{source}/master_{source}_jobs_state.db?mode=ro',uri=True)
    print(json.dumps({'source':source,'schema':c.execute("SELECT name,sql FROM sqlite_master WHERE type='table'").fetchall()}))
