"""Durable full-list collection rounds; source absence never closes vacancies."""
from datetime import datetime, timezone
import json


def now():
    return datetime.now(timezone.utc).isoformat()


def initialize(db):
    db.executescript('''
      CREATE TABLE IF NOT EXISTS employer_collection_rounds(
        round_id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL,
        finished_at TEXT, employers_total INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS employer_collection_round_members(
        round_id INTEGER NOT NULL, source_key TEXT NOT NULL, source_json TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending', started_at TEXT, finished_at TEXT,
        usable_jobs INTEGER NOT NULL DEFAULT 0, focus_jobs INTEGER NOT NULL DEFAULT 0,
        outcome TEXT NOT NULL DEFAULT '', duration_seconds REAL NOT NULL DEFAULT 0,
        PRIMARY KEY(round_id,source_key));
    ''')


def next_batch(db, limit):
    """Caller holds the existing exclusive collector lock across the batch."""
    initialize(db)
    with db:
        active = db.execute('SELECT round_id FROM employer_collection_rounds WHERE finished_at IS NULL ORDER BY round_id LIMIT 1').fetchone()
        if active:
            round_id = active[0]
        else:
            sources = db.execute('SELECT * FROM priority_employers WHERE enabled=1 ORDER BY source_key').fetchall()
            if not sources:
                return None, []
            round_id = db.execute('INSERT INTO employer_collection_rounds(started_at,employers_total) VALUES(?,?)', (now(),len(sources))).lastrowid
            db.executemany('INSERT INTO employer_collection_round_members(round_id,source_key,source_json) VALUES(?,?,?)',
                           [(round_id,s['source_key'],json.dumps(dict(s))) for s in sources])
        members = db.execute("SELECT source_key,source_json FROM employer_collection_round_members WHERE round_id=? AND state IN ('pending','running') ORDER BY source_key LIMIT ?", (round_id,limit)).fetchall()
        db.executemany("UPDATE employer_collection_round_members SET state='running',started_at=? WHERE round_id=? AND source_key=?", [(now(),round_id,m[0]) for m in members])
    return round_id, [json.loads(m[1]) for m in members]


def finish_member(db, round_id, source_key, *, usable=0, focused=0, outcome='', seconds=0, failed=False):
    with db:
        db.execute('''UPDATE employer_collection_round_members SET state=?,finished_at=?,
          usable_jobs=?,focus_jobs=?,outcome=?,duration_seconds=? WHERE round_id=? AND source_key=?''',
          ('failed' if failed else 'completed',now(),usable,focused,outcome,seconds,round_id,source_key))
        pending = db.execute("SELECT count(*) FROM employer_collection_round_members WHERE round_id=? AND state IN ('pending','running')", (round_id,)).fetchone()[0]
        if not pending:
            db.execute('UPDATE employer_collection_rounds SET finished_at=? WHERE round_id=? AND finished_at IS NULL',(now(),round_id))


def summary(db):
    initialize(db)
    row = db.execute('SELECT * FROM employer_collection_rounds ORDER BY round_id DESC LIMIT 1').fetchone()
    if not row:
        return {'rounds_completed':0}
    result = dict(row)
    result['rounds_completed'] = db.execute('SELECT count(*) FROM employer_collection_rounds WHERE finished_at IS NOT NULL').fetchone()[0]
    result['states'] = dict(db.execute('SELECT state,count(*) FROM employer_collection_round_members WHERE round_id=? GROUP BY state',(row['round_id'],)))
    result['usable_jobs'],result['focus_jobs'] = db.execute('SELECT COALESCE(sum(usable_jobs),0),COALESCE(sum(focus_jobs),0) FROM employer_collection_round_members WHERE round_id=?',(row['round_id'],)).fetchone()
    result['duration_seconds'] = (datetime.fromisoformat(row['finished_at'] or now())-datetime.fromisoformat(row['started_at'])).total_seconds()
    return result
