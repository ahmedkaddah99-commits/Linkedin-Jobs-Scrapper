from datetime import datetime, timedelta, timezone
import sqlite3

from tests.test_catalog_storage_retention import catalog, ids
from scripts.prune_catalog_history import prune_batch


def test_single_statement_history_deletion_preserves_all_publication_pins(catalog):
    with sqlite3.connect(catalog) as db:
        for _ in range(30):
            receipt = prune_batch(db, 'publications', batch_size=2, cutoff='unused')
            assert receipt['deleted_memberships'] <= 2
    assert ids(catalog) == {'p1','p2','p5','p6','p7'}


def test_head_change_between_batches_protects_new_head_and_rollback(catalog):
    with sqlite3.connect(catalog) as db:
        prune_batch(db, 'publications', batch_size=2, cutoff='unused')
        db.execute("UPDATE acquisition_publication_head SET publication_id='p0'")
        db.execute("UPDATE acquisition_publications SET previous_publication_id='p3' WHERE publication_id='p0'")
        for _ in range(30):
            prune_batch(db, 'publications', batch_size=2, cutoff='unused')
        assert db.execute("SELECT count(*) FROM acquisition_publication_jobs WHERE publication_id='p0'").fetchone()[0] == 3
    assert {'p0','p3'} <= ids(catalog)


def test_rejection_statement_keeps_recent_and_active_cycle_history(catalog):
    now = datetime(2026,10,8,tzinfo=timezone.utc)
    with sqlite3.connect(catalog) as db:
        for key,age,cycle in [('old',8,'done'),('recent',6,'done'),('active',8,'active')]:
            db.execute('INSERT INTO acquisition_job_rejections(rejection_id,request_id,cycle_id,task_id,target_id,reason_code,observed_at) VALUES(?,?,?,?,?,?,?)', (key,key,cycle,'t','target','bad',(now-timedelta(days=age)).isoformat()))
        result = prune_batch(db, 'rejections', batch_size=2, cutoff=(now-timedelta(days=7)).isoformat())
        assert result['deleted_rejections'] == 1
        assert {row[0] for row in db.execute('SELECT rejection_id FROM acquisition_job_rejections')} == {'recent','active'}
