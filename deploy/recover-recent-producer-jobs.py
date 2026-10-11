"""Restore only jobs wrongly retired by the indexed cutoff, from a verified backup.

Dry-run by default. Run with collectors and publisher stopped; locks are held
throughout recovery. Existing producer rows and legitimate tombstones survive.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.acquisition.job_lifecycle import exclusion_reason
from backend.application.catalog_job_filters import profession_override


def recover(path, backup, source, *, apply=False, now=None):
    key, field = ('linkedin_job_id','job_json') if source == 'linkedin' else ('source_key','payload_json')
    current = now or datetime.now(timezone.utc)
    db = sqlite3.connect('file:'+str(Path(path).resolve())+'?mode=rw',uri=True,timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA cache_size=-4096')
    db.execute('ATTACH DATABASE ? AS recovery', ('file:'+str(Path(backup).resolve())+'?mode=ro',))
    result = dict(source=source,apply=apply,examined=0,eligible=0,restored=0,not_in_backup=0)
    columns = [r[1] for r in db.execute('PRAGMA table_info(jobs)')]
    if columns != [r[1] for r in db.execute('PRAGMA recovery.table_info(jobs)')]:
        raise ValueError('backup schema mismatch')
    retired = db.execute("SELECT job_key FROM runr_retired_jobs WHERE reason='retention_30_days' AND retired_at>=?", ('2026-10-11',)).fetchall()
    for entry in retired:
        identity = entry[0]
        result['examined'] += 1
        original = db.execute(f'SELECT * FROM recovery.jobs WHERE {key}=?',(identity,)).fetchone()
        if not original:
            result['not_in_backup'] += 1
            continue
        payload = json.loads(original[field])
        if exclusion_reason(payload,now=current) or profession_override(payload.get('job_title') or payload.get('title'),'') == ('blue',[]):
            continue
        result['eligible'] += 1
        if apply:
            db.execute('BEGIN IMMEDIATE')
            with db:
                db.execute("DELETE FROM runr_retired_jobs WHERE job_key=? AND reason='retention_30_days'", (identity,))
                quoted = ','.join('"'+column+'"' for column in columns)
                db.execute(f'INSERT OR IGNORE INTO jobs({quoted}) SELECT {quoted} FROM recovery.jobs WHERE {key}=?',(identity,))
                result['restored'] += db.execute('SELECT changes()').fetchone()[0]
    db.close()
    return result


if __name__ == '__main__':
    import fcntl
    import hashlib
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',choices=('linkedin','employer'),required=True)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--backup',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    receipt=json.loads((args.backup.parent/'off-host-receipt.json').read_text())['database']
    if args.backup.stat().st_size != receipt['bytes']:
        raise ValueError('backup size mismatch')
    with args.backup.open('rb') as stream:
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
    if digest != receipt['sha256']:
        raise ValueError('backup checksum mismatch')
    streams=[]
    for name in ('publisher','linkedin','employer'):
        stream=Path('/srv/runr/state/locks',name+'.lock').open('a')
        try: fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise SystemExit(75)
        streams.append(stream)
    result=recover(args.database,args.backup,args.source,apply=args.apply)
    result['backup_sha256_verified']=True
    print(json.dumps(result),flush=True)
