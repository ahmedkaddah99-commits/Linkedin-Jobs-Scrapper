"""Bounded producer job expiry under existing collector/publisher locks."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.acquisition.job_lifecycle import exclusion_reason
from backend.application.catalog_job_filters import profession_override


def maintain(path, source, *, apply=False, batch_size=500, max_seconds=60, now=None):
    if source not in ('linkedin','employer') or not 1 <= batch_size <= 1000 or max_seconds <= 0:
        raise ValueError('invalid producer maintenance bounds')
    key, field = ('linkedin_job_id','job_json') if source == 'linkedin' else ('source_key','payload_json')
    current = now or datetime.now(timezone.utc)
    result = dict(source=source,apply=apply,scanned=0,removed=0,candidates=0,pass_complete=False)
    db = sqlite3.connect('file:'+str(Path(path).resolve())+'?mode=rw', uri=True, timeout=30)
    db.execute('PRAGMA foreign_keys=ON')
    # Producer payloads are large. Keep SQLite's page cache and temporary JSON
    # work off the process heap so this maintenance job stays small on the VPS.
    db.execute('PRAGMA cache_size=-4096')
    db.execute('PRAGMA temp_store=FILE')
    db.execute('PRAGMA mmap_size=0')
    has_index = 'runr_retention_index' in {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if apply:
        with db:
            db.execute('CREATE TABLE IF NOT EXISTS runr_retired_jobs(job_key TEXT PRIMARY KEY,reason TEXT NOT NULL,retired_at TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS runr_job_retention_progress(id INTEGER PRIMARY KEY,cursor INTEGER NOT NULL)')
            db.execute(f"CREATE TRIGGER IF NOT EXISTS runr_no_retired_job_reinsert BEFORE INSERT ON jobs WHEN EXISTS(SELECT 1 FROM runr_retired_jobs WHERE job_key=NEW.{key}) BEGIN SELECT RAISE(IGNORE); END")
    has_progress = apply or 'runr_job_retention_progress' in tables
    prior = db.execute('SELECT cursor FROM runr_job_retention_progress WHERE id=1').fetchone() if has_progress else None
    cursor = int(prior[0]) if prior else 0
    related = []
    if source == 'linkedin':
        for table in ('search_cards','detail_queue','detail_attempts','job_company_observations'):
            if table in tables and key in {r[1] for r in db.execute('PRAGMA table_info('+table+')')}:
                related.append(table)
    deadline = time.monotonic()+max_seconds
    try:
        while time.monotonic() < deadline:
            cutoff = (current.date().toordinal() - 30)
            if has_index:
                rows = db.execute("SELECT j.rowid,j."+key+",j."+field+" FROM jobs j JOIN runr_retention_index i ON i.source=? AND i.job_key=j."+key+" WHERE i.cursor>? AND i.retention_date IS NOT NULL AND date(i.retention_date)<date(?) ORDER BY i.cursor LIMIT ?", (source,cursor,current.date().isoformat(),batch_size)).fetchall()
            else:
                rows = db.execute(f"SELECT rowid,{key},{field} FROM jobs WHERE rowid>? ORDER BY rowid LIMIT ?", (cursor,batch_size)).fetchall()
            if not rows:
                result['pass_complete'] = True
                if apply:
                    with db: db.execute('INSERT OR REPLACE INTO runr_job_retention_progress VALUES(1,0)')
                break
            selected = []
            for rowid, identity, raw in rows:
                payload = json.loads(raw)
                reason = exclusion_reason(payload,now=current)
                if not reason and profession_override(payload.get('job_title') or payload.get('title'), '') == ('blue',[]):
                    reason = 'blue_collar_rules'
                if reason: selected.append((identity,reason,current.isoformat()))
            result['scanned'] += len(rows)
            result['candidates'] += len(selected)
            cursor = rows[-1][0]
            if apply:
                with db:
                    db.executemany('INSERT OR IGNORE INTO runr_retired_jobs VALUES(?,?,?)',selected)
                    ids = json.dumps([r[0] for r in selected])
                    for table in related:
                        db.execute(f'DELETE FROM {table} WHERE {key} IN (SELECT value FROM json_each(?))',(ids,))
                    db.execute(f'DELETE FROM jobs WHERE {key} IN (SELECT value FROM json_each(?))',(ids,))
                    db.execute('INSERT OR REPLACE INTO runr_job_retention_progress VALUES(1,?)',(cursor,))
                result['removed'] += len(selected)
        result['remaining_jobs'] = db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
        result['reusable_bytes'] = db.execute('PRAGMA freelist_count').fetchone()[0] * db.execute('PRAGMA page_size').fetchone()[0]
        return result
    finally:
        db.close()


def main():
    import fcntl
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root',type=Path,default=Path('/srv/runr/state/active'))
    parser.add_argument('--lock-root',type=Path,default=Path('/srv/runr/state/locks'))
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--batch-size',type=int,default=10)
    parser.add_argument('--max-seconds',type=int,default=30)
    parser.add_argument('--receipt',type=Path)
    args = parser.parse_args()
    streams = []
    for name in ('publisher','linkedin','employer'):
        stream = (args.lock_root / (name+'.lock')).open('a')
        try: fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return 75
        streams.append(stream)
    result = [maintain(args.state_root/source/('master_'+source+'_jobs_state.db'),source,
                      apply=args.apply,batch_size=args.batch_size,max_seconds=args.max_seconds) for source in ('linkedin','employer')]
    rendered = json.dumps(result)
    if args.receipt:
        temporary = args.receipt.with_suffix('.tmp')
        temporary.write_text(rendered+'\n')
        temporary.replace(args.receipt)
    print(rendered)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())




