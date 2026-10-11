"""Compact a verified local restore, archiving evidence to shared storage first.

This is a candidate only: it never changes the production database configuration.
New production writes since the export must be reconciled before any cutover.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import dotenv_values
from backend.acquisition.storage_evidence import create_catalog_evidence_storage
from scripts import reduce_catalog_storage as reducer


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sqlite',type=Path,required=True)
    parser.add_argument('--restore-receipt',type=Path,required=True)
    parser.add_argument('--checkpoint',type=Path,required=True)
    parser.add_argument('--env',action='append',required=True)
    parser.add_argument('--max-seconds',type=float,default=1800)
    args=parser.parse_args()
    if args.max_seconds <= 0:
        parser.error('Time budget must be positive')
    if not args.sqlite.is_file() or not args.restore_receipt.is_file():
        parser.error('Existing verified restore and receipt required')
    receipt=json.loads(args.restore_receipt.read_text())
    if receipt.get('quick_check') != 'ok' or receipt.get('restored') is not True:
        raise ValueError('Full restore verification did not pass')
    for path in args.env:
        os.environ.update({k:v for k,v in dotenv_values(path).items() if v is not None})
    storage=create_catalog_evidence_storage()
    # The 3 MiB body limit protects HTTP. This local-only candidate uses a
    # bounded 32 MiB read page and never sends these batches to Turso.
    reducer.MAX_BATCH_BODY_BYTES=32*1024*1024
    db=sqlite3.connect(args.sqlite.resolve().as_uri()+'?mode=rw',uri=True,cached_statements=32)
    try:
        expected=receipt.get('counts',{})
        for table in ('canonical_jobs','job_posting_versions','job_source_observations'):
            if table not in expected or db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] != expected[table]:
                raise ValueError('Candidate identity counts disagree with verified restore')
        db.execute('PRAGMA cache_size=-65536')
        result=reducer.reduce_catalog_storage(db,database_identity='sqlite:'+str(args.sqlite.resolve()),checkpoint=args.checkpoint,apply=True,batch_size=100,max_seconds=args.max_seconds,storage=storage,archive_workers=32,compact_intelligence=True)
        page_size=db.execute('PRAGMA page_size').fetchone()[0]
        pages=db.execute('PRAGMA page_count').fetchone()[0]
        free=db.execute('PRAGMA freelist_count').fetchone()[0]
        print(json.dumps({'candidate_only':True,'allocated_bytes':pages*page_size,'free_page_bytes':free*page_size,**result}),flush=True)
    finally:
        db.close()


if __name__=='__main__':
    main()
