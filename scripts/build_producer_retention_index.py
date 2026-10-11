"""Stream producer payloads into a small retention metadata table."""
import argparse, json, sqlite3, time
from pathlib import Path

def build(path: Path, source: str, *, seconds: int = 30, batch_size: int = 100):
    key, field = ('linkedin_job_id','job_json') if source == 'linkedin' else ('source_key','payload_json')
    db = sqlite3.connect(f'file:{path.resolve()}?mode=rw', uri=True, timeout=30)
    db.execute('PRAGMA cache_size=-4096'); db.execute('PRAGMA temp_store=FILE'); db.execute('PRAGMA mmap_size=0')
    db.execute('CREATE TABLE IF NOT EXISTS runr_retention_index (source TEXT NOT NULL, job_key TEXT NOT NULL, retention_date TEXT, title TEXT, cursor INTEGER NOT NULL, PRIMARY KEY(source,job_key))')
    cursor = db.execute('SELECT COALESCE(MAX(cursor),0) FROM runr_retention_index WHERE source=?',(source,)).fetchone()[0]
    deadline = time.monotonic() + seconds; scanned = 0
    while time.monotonic() < deadline:
        rows = db.execute(f'SELECT rowid,{key},{field} FROM jobs WHERE rowid>? ORDER BY rowid LIMIT ?', (cursor,batch_size)).fetchall()
        if not rows: return {'source':source,'scanned':scanned,'complete':True,'cursor':cursor}
        values=[]
        for rowid, identity, raw in rows:
            try: d=json.loads(raw)
            except (TypeError,ValueError): d={}
            date=d.get('posted_at_estimated') if source=='linkedin' else d.get('date_posted')
            date=date or d.get('first_seen_at')
            values.append((source,identity,date,d.get('job_title') or d.get('title'),rowid))
        with db:
            db.executemany('INSERT OR REPLACE INTO runr_retention_index VALUES(?,?,?,?,?)', values)
        cursor=rows[-1][0]; scanned += len(rows)
    return {'source':source,'scanned':scanned,'complete':False,'cursor':cursor}

def main():
    p=argparse.ArgumentParser(); p.add_argument('--state-root',type=Path,default=Path('/srv/runr/state/active')); p.add_argument('--seconds',type=int,default=30); p.add_argument('--batch-size',type=int,default=10)
    a=p.parse_args(); out=[]
    for source in ('linkedin','employer'):
        out.append(build(a.state_root/source/('master_'+source+'_jobs_state.db'),source,seconds=a.seconds,batch_size=a.batch_size))
    print(json.dumps(out))
if __name__=='__main__': main()
