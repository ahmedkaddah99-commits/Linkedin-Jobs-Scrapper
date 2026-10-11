"""Enable WAL once during a serialized release, with long-lived readers paused."""
import json
from pathlib import Path
import sqlite3

for source in ('linkedin','employer'):
    path=Path('/srv/runr/state/active')/source/('master_'+source+'_jobs_state.db')
    db=sqlite3.connect('file:'+str(path.resolve())+'?mode=rw',uri=True,timeout=30)
    try:
        mode=db.execute('PRAGMA journal_mode=WAL').fetchone()[0]
        if mode != 'wal':
            raise RuntimeError('producer WAL mode was not activated')
        db.execute('PRAGMA journal_size_limit=67108864')
        if source=='linkedin':
            db.execute('CREATE INDEX IF NOT EXISTS idx_job_company_observations_run ON job_company_observations(run_id)')
        print(json.dumps({'producer':source,'journal_mode':mode}),flush=True)
    finally:
        db.close()
