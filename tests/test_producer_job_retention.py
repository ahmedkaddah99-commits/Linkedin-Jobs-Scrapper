import json
import sqlite3
from datetime import datetime,timezone
from scripts.maintain_producer_jobs import maintain


def test_expiry_removes_payload_and_prevents_resurrection(tmp_path):
    path=tmp_path/'producer.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE jobs(linkedin_job_id TEXT PRIMARY KEY,job_json TEXT,updated_at TEXT)')
        db.execute('CREATE TABLE detail_queue(linkedin_job_id TEXT PRIMARY KEY)')
        for key, posted, title in [('old','2026-08-01','Analyst'),('blue','2026-10-10','Truck Driver'),('fresh','2026-10-10','Data Analyst')]:
            db.execute('INSERT INTO jobs VALUES(?,?,?)',(key,json.dumps({'posted_at_estimated':posted,'job_title':title}),'now'))
            db.execute('INSERT INTO detail_queue VALUES(?)',(key,))
    now=datetime(2026,10,11,tzinfo=timezone.utc)
    assert maintain(path,'linkedin',now=now)['candidates']==2
    result=maintain(path,'linkedin',apply=True,now=now,batch_size=1)
    assert result['removed']==2
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO jobs VALUES('old','{}','now')")
        assert db.execute('SELECT linkedin_job_id FROM jobs').fetchall()==[('fresh',)]
        assert db.execute('SELECT linkedin_job_id FROM detail_queue').fetchall()==[('fresh',)]
        assert db.execute('SELECT COUNT(*) FROM runr_retired_jobs').fetchone()[0]==2


def test_indexed_retention_preserves_recent_rows_and_uses_index_cursor(tmp_path):
    path = tmp_path / 'producer.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE jobs(linkedin_job_id TEXT PRIMARY KEY,job_json TEXT)')
        db.execute('CREATE TABLE runr_retention_index(source TEXT,job_key TEXT,retention_date TEXT,title TEXT,cursor INTEGER,PRIMARY KEY(source,job_key))')
        for key, date, cursor in [('recent','2026-10-10',100), ('old','2026-08-01',200), ('boundary','2026-09-11',300)]:
            db.execute('INSERT INTO jobs VALUES(?,?)', (key,'{}'))
            db.execute('INSERT INTO runr_retention_index VALUES(?,?,?,?,?)', ('linkedin',key,date,'Analyst',cursor))
    result = maintain(path,'linkedin',apply=True,now=datetime(2026,10,11,tzinfo=timezone.utc),batch_size=1)
    assert result['pass_complete']
    assert result['removed'] == 1
    with sqlite3.connect(path) as db:
        assert {r[0] for r in db.execute('SELECT linkedin_job_id FROM jobs')} == {'recent','boundary'}
        assert db.execute('SELECT job_key FROM runr_retired_jobs').fetchall() == [('old',)]


def test_wrongly_retired_recent_job_is_restored_without_old_or_blue_jobs(tmp_path):
    import runpy
    from pathlib import Path
    recover=runpy.run_path(str(Path(__file__).parents[1]/'deploy/recover-recent-producer-jobs.py'))['recover']
    backup=tmp_path/'backup.db'
    active=tmp_path/'active.db'
    for path in (backup,active):
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE jobs(linkedin_job_id TEXT PRIMARY KEY,job_json TEXT)')
    with sqlite3.connect(backup) as db:
        for key,title,date in [('recent','Data Analyst','2026-10-10'),('old','Analyst','2026-08-01'),('blue','Truck Driver','2026-10-10')]:
            db.execute('INSERT INTO jobs VALUES(?,?)',(key,json.dumps({'title':title,'posted_at':date})))
    with sqlite3.connect(active) as db:
        db.execute('CREATE TABLE runr_retired_jobs(job_key TEXT PRIMARY KEY,reason TEXT,retired_at TEXT)')
        db.executemany('INSERT INTO runr_retired_jobs VALUES(?,?,?)',[(key,'retention_30_days','2026-10-11') for key in ('recent','old','blue')])
    now=datetime(2026,10,11,tzinfo=timezone.utc)
    assert recover(active,backup,'linkedin',now=now)['eligible']==1
    assert recover(active,backup,'linkedin',apply=True,now=now)['restored']==1
    with sqlite3.connect(active) as db:
        assert db.execute('SELECT linkedin_job_id FROM jobs').fetchall()==[('recent',)]
        assert {r[0] for r in db.execute('SELECT job_key FROM runr_retired_jobs')}=={'old','blue'}
