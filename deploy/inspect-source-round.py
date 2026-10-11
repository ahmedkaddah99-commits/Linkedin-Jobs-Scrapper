"""Read source-round progress without provider configuration or posting contents."""
import json
import sqlite3

db=sqlite3.connect('file:/srv/runr/state/active/linkedin/master_linkedin_jobs_state.db?mode=ro',uri=True,timeout=10)
db.row_factory=sqlite3.Row
run=db.execute('SELECT run_id,started_at,status,finished_at FROM runs ORDER BY started_at DESC LIMIT 1').fetchone()
print(json.dumps({'run':dict(run),'journal_mode':db.execute('PRAGMA journal_mode').fetchone()[0]}),flush=True)
for table in ('company_scans','detail_queue','detail_attempts'):
    print(json.dumps({table:[dict(row) for row in db.execute('SELECT status,COUNT(*) AS n FROM '+table+' WHERE run_id=? GROUP BY status',(run['run_id'],))]}),flush=True)
