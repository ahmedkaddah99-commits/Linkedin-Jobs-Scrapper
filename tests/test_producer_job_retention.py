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
