"""Bounded history pruning with pins checked inside each atomic DELETE statement."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.acquisition.storage_retention import _CANDIDATE, _PINS, _TERMINAL
from scripts.compact_job_storage import HttpMaintenanceConnection

MEMBERS = f"""DELETE FROM acquisition_publication_jobs WHERE rowid IN (
    SELECT rowid FROM acquisition_publication_jobs
    WHERE publication_id=({_CANDIDATE}) ORDER BY rowid LIMIT ?)
    RETURNING rowid, length(CAST(publication_id AS BLOB))+length(CAST(canonical_job_id AS BLOB))"""
HEADERS = f"""DELETE FROM acquisition_publications WHERE publication_id IN (
    SELECT p.publication_id FROM acquisition_publications p
    WHERE p.status='valid' AND p.publication_id NOT IN ({_PINS})
    AND NOT EXISTS(SELECT 1 FROM acquisition_publication_jobs j WHERE j.publication_id=p.publication_id)
    ORDER BY p.published_at,p.publication_id LIMIT 1)
    RETURNING rowid, COALESCE(length(CAST(snapshot_json AS BLOB)),0)"""
REJECTIONS = f"""DELETE FROM acquisition_job_rejections WHERE rowid IN (
    SELECT r.rowid FROM acquisition_job_rejections r WHERE observed_at < ?
    AND NOT EXISTS(SELECT 1 FROM acquisition_cycles c WHERE c.cycle_id=r.cycle_id
        AND c.status NOT IN {_TERMINAL})
    ORDER BY observed_at,r.rowid LIMIT ?)
    RETURNING rowid, COALESCE(length(CAST(detail_json AS BLOB)),0)"""


def prune_batch(db, phase, *, batch_size, cutoff):
    if not 1 <= batch_size <= 10000:
        raise ValueError('Batch size must be 1..10000')
    counts = dict(deleted_memberships=0, deleted_publications=0,
                  deleted_rejections=0, logical_bytes_removed=0)
    if phase == 'publications':
        rows = db.execute(MEMBERS, (batch_size,)).fetchall()
        counts['deleted_memberships'] = len(rows)
        if not rows:
            rows = db.execute(HEADERS).fetchall()
            counts['deleted_publications'] = len(rows)
    elif phase == 'rejections':
        rows = db.execute(REJECTIONS, (cutoff, batch_size)).fetchall()
        counts['deleted_rejections'] = len(rows)
    else:
        raise ValueError('Unsupported history phase')
    counts['logical_bytes_removed'] = sum(row[1] or 0 for row in rows)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--batch-size', type=int, default=10000)
    parser.add_argument('--max-seconds', type=float, default=120)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 10000 or args.max_seconds <= 0:
        parser.error('Invalid bounded maintenance budget')
    identity = hashlib.sha256(os.environ['TURSO_DATABASE_URL'].encode()).hexdigest()
    state = json.loads(args.checkpoint.read_text()) if args.checkpoint.exists() else {}
    if state.get('database_identity', identity) != identity:
        raise ValueError('History checkpoint belongs to another database')
    state['database_identity'] = identity
    db = HttpMaintenanceConnection(timeout=30)
    cutoff = (datetime.now(timezone.utc)-timedelta(days=7)).isoformat()
    result = dict(apply=args.apply, batches=0, deleted_memberships=0,
                  deleted_publications=0, deleted_rejections=0, logical_bytes_removed=0)
    if not args.apply:
        result['publication_candidate_present'] = bool(db.execute(_CANDIDATE).fetchone())
        print(json.dumps(result), flush=True)
        return
    deadline = time.monotonic()+args.max_seconds
    finished = set()
    number = 0
    while time.monotonic() < deadline and len(finished) < 2:
        phase = ('publications','rejections')[number % 2]
        number += 1
        if phase in finished:
            continue
        changed = prune_batch(db, phase, batch_size=args.batch_size, cutoff=cutoff)
        result['batches'] += 1
        for key, count in changed.items():
            result[key] += count
            state[key] = state.get(key, 0)+count
        state['last_success_at'] = datetime.now(timezone.utc).isoformat()
        args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.checkpoint.with_suffix('.tmp')
        temporary.write_text(json.dumps(state), encoding='utf-8')
        temporary.chmod(0o600)
        temporary.replace(args.checkpoint)
        print(json.dumps({'phase':phase, **changed}), flush=True)
        if not any(changed[key] for key in ('deleted_memberships','deleted_publications','deleted_rejections')):
            finished.add(phase)
    result['complete'] = len(finished) == 2
    result['logical_bytes_note'] = 'Excludes indexes and other columns; ambiguous requests can undercount committed removals'
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
