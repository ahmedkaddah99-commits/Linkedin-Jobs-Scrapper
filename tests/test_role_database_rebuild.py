import sqlite3,json
from scripts.rebuild_role_filtered_database import rebuild

def test_producer_rebuild_preserves_rowids_and_removes_history(tmp_path):
    source=tmp_path/'source.db'; output=tmp_path/'out.db'
    c=sqlite3.connect(source)
    c.executescript('CREATE TABLE jobs(linkedin_job_id TEXT PRIMARY KEY,job_json TEXT); CREATE TABLE detail_attempts(linkedin_job_id TEXT,detail_json TEXT); CREATE TABLE company_scans(observed_job_ids_json TEXT);')
    c.execute('INSERT INTO jobs(rowid,linkedin_job_id,job_json) VALUES(10,?,?)',('keep',json.dumps({'title':'Business Analyst'})))
    c.execute('INSERT INTO jobs VALUES(?,?)',('remove',json.dumps({'title':'Marketing Manager'})))
    c.execute('INSERT INTO detail_attempts VALUES(?,?)',('remove','sensitive source'))
    c.commit();c.close()
    rebuild(source,output,'linkedin')
    result=sqlite3.connect(output)
    assert result.execute('SELECT rowid,linkedin_job_id FROM jobs').fetchall()==[(10,'keep')]
    assert result.execute('SELECT * FROM detail_attempts').fetchall()==[]
    assert sqlite3.connect(source).execute('SELECT count(*) FROM jobs').fetchone()[0]==2
