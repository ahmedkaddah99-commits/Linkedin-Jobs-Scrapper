"""Drain durable unpublished catalog jobs in bounded, restart-safe batches."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.acquisition.publication import StalePublicationHeadError
from backend.repositories.sqlite_acquisition import SqliteAcquisitionStore
from scripts.publish_producer_states import resolve_runtime_publication_policy


def drain(store, *, batch_size=200, max_seconds=120, max_batches=100):
    started=time.monotonic()
    total={'processed':0,'published':0,'rejected':0}
    policy=resolve_runtime_publication_policy()
    for _ in range(max_batches):
        if time.monotonic()-started>=max_seconds:
            break
        batch_started=time.monotonic()
        try:
            result=store.publish_pending_catalog_jobs(batch_size=batch_size,policy_version=policy)
        except StalePublicationHeadError:
            print(json.dumps({'event':'publication_recovery_input_changed','retry_next_batch':True}),flush=True)
            continue
        for key in total:
            total[key]+=result[key]
        print(json.dumps({'event':'publication_recovery_batch','seconds':round(time.monotonic()-batch_started,3),**result}),flush=True)
        if not result['processed']:
            break
    with store._connect() as conn:
        states=store._fetch_read_rows(conn,'SELECT status,COUNT(*) AS jobs FROM acquisition_publication_queue GROUP BY status')
    remaining={r['status']:r['jobs'] for r in states}
    receipt={'status':'completed' if not remaining.get('pending',0) else 'partial',**total,
             'queue':remaining,'elapsed_seconds':round(time.monotonic()-started,3)}
    print(json.dumps(receipt),flush=True)
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=Path('/var/lib/runr/acquisition-data'))
    parser.add_argument('--batch-size',type=int,default=200)
    parser.add_argument('--max-seconds',type=int,default=120)
    parser.add_argument('--max-batches',type=int,default=100)
    args=parser.parse_args()
    if not 1<=args.batch_size<=500 or args.max_seconds<1 or args.max_batches<1:
        parser.error('Batch size must be 1..500 and time/batch limits positive.')
    return drain(SqliteAcquisitionStore(args.data_dir/'backend.sqlite3',initialize=False),
                 batch_size=args.batch_size,max_seconds=args.max_seconds,max_batches=args.max_batches)


if __name__=='__main__':
    main()
