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

def test_catalog_rebuild_retains_only_current_eligible_membership(tmp_path):
    source=tmp_path/'source.db'; output=tmp_path/'out.db'
    c=sqlite3.connect(source)
    c.executescript('''
    CREATE TABLE canonical_jobs(canonical_job_id TEXT PRIMARY KEY,title TEXT,current_version_id TEXT);
    CREATE TABLE job_posting_versions(version_id TEXT PRIMARY KEY,canonical_job_id TEXT,description TEXT);
    CREATE TABLE job_source_observations(observation_id TEXT PRIMARY KEY,canonical_job_id TEXT);
    CREATE TABLE job_intelligence_cache(cache_id TEXT PRIMARY KEY,canonical_job_id TEXT);
    CREATE TABLE acquisition_publication_head(head_id INTEGER PRIMARY KEY,publication_id TEXT);
    CREATE TABLE acquisition_publications(publication_id TEXT PRIMARY KEY,snapshot_json TEXT,previous_publication_id TEXT);
    CREATE TABLE acquisition_publication_jobs(publication_id TEXT,canonical_job_id TEXT,PRIMARY KEY(publication_id,canonical_job_id));
    ''')
    c.executemany('INSERT INTO canonical_jobs VALUES(?,?,?)',[('keep','Business Analyst','v1'),('bad','Financial Analyst','v2'),('experienced','Product Manager','v3')])
    c.executemany('INSERT INTO job_posting_versions VALUES(?,?,?)',[('v1','keep','Entry level'),('v2','bad','Entry level'),('v3','experienced','5 years experience required')])
    c.execute('INSERT INTO acquisition_publication_head VALUES(1,?)',('current',))
    snapshot=json.dumps([{'canonical_job_id':x} for x in ['keep','bad','experienced']])
    c.executemany('INSERT INTO acquisition_publications VALUES(?,?,?)',[('current',snapshot,'old'),('old',snapshot,'')])
    c.executemany('INSERT INTO acquisition_publication_jobs VALUES(?,?)',[(p,j) for p in ['current','old'] for j in ['keep','bad','experienced']])
    c.commit();c.close();rebuild(source,output,'catalog')
    c=sqlite3.connect(output)
    assert c.execute('SELECT canonical_job_id FROM canonical_jobs').fetchall()==[('keep',)]
    assert c.execute('SELECT * FROM acquisition_publication_jobs').fetchall()==[('current','keep')]
    assert json.loads(c.execute('SELECT snapshot_json FROM acquisition_publications').fetchone()[0])==[{'canonical_job_id':'keep'}]
