"""Rollback must not overwrite later production intelligence writes."""
import json
import sqlite3

from scripts import classify_published_catalog as rollout


def test_rollback_restores_own_write_and_preserves_newer_same_json(tmp_path, monkeypatch):
    local=sqlite3.connect(':memory:')
    local.row_factory=sqlite3.Row
    local.executescript('''CREATE TABLE jobs(version_id TEXT,published INTEGER,result TEXT);
    CREATE TABLE written(version_id TEXT,filters_json TEXT,content_hash TEXT,generated_at TEXT);
    CREATE TABLE rollback(version_id TEXT,previous_json TEXT);''')
    remote_path=tmp_path/'remote.sqlite3'
    def connect(_):
        connection=sqlite3.connect(remote_path)
        connection.row_factory=sqlite3.Row
        return connection
    monkeypatch.setattr(rollout,'connect_database',connect)
    previous={'version_id':'v1','canonical_job_id':'j1','content_hash':'h1','filters_json':'{"role":"old"}',
              'model':'previous','prompt_version':'old','generated_at':'before'}
    with connect(None) as remote:
        remote.execute('CREATE TABLE job_filter_intelligence(version_id TEXT PRIMARY KEY,canonical_job_id TEXT,content_hash TEXT,filters_json TEXT,model TEXT,prompt_version TEXT,generated_at TEXT)')
        remote.executemany('INSERT INTO job_filter_intelligence VALUES (?,?,?,?,?,?,?)',[
            ('v1','j1','h1','{}',rollout.MODEL,rollout.PROMPT_VERSION,'own-write'),
            ('v2','j2','h2','{}',rollout.MODEL,rollout.PROMPT_VERSION,'later-write')])
    local.executemany('INSERT INTO jobs VALUES (?,1,?)',[('v1','{"revalidated":true}'),('v2','{}')])
    local.executemany('INSERT INTO written VALUES (?,?,?,?)',[('v1','{}','h1','own-write'),('v2','{}','h2','own-write')])
    local.executemany('INSERT INTO rollback VALUES (?,?)',[('v1',json.dumps(previous)),('v2',None)])
    local.commit()
    rollout.rollback(local)
    with connect(None) as remote:
        assert dict(remote.execute("SELECT * FROM job_filter_intelligence WHERE version_id='v1'").fetchone()) == previous
        assert remote.execute("SELECT generated_at FROM job_filter_intelligence WHERE version_id='v2'").fetchone()[0] == 'later-write'
    assert local.execute("SELECT published FROM jobs WHERE version_id='v1'").fetchone()[0] == 0
    assert local.execute("SELECT published FROM jobs WHERE version_id='v2'").fetchone()[0] == 1


def test_revalidation_keeps_function_decision_when_metadata_tries_to_overwrite_it(monkeypatch):
    local=sqlite3.connect(':memory:');local.row_factory=sqlite3.Row
    local.executescript('''CREATE TABLE jobs(id TEXT,title TEXT,description TEXT,version_id TEXT,content_hash TEXT,result TEXT,error TEXT,attempts INTEGER);
    CREATE TABLE calls(id INTEGER PRIMARY KEY,response TEXT);''')
    local.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)',('j1','Data Analyst','Analyze data with SQL.','v1','h1',None,None,1))
    function={'collar':'white','roles':['Data Analyst'],'evidence':'Data Analyst'}
    metadata={'roles':['Nursing Professional'],'collar':'blue','evidence':'incorrect', 'skills':['SQL']}
    envelope=lambda value: {'choices':[{'message':{'content':json.dumps(value)}}]}
    combined=envelope({'jobs':[dict(metadata,id='j1')]})
    combined['provider_responses']=[envelope(function),envelope(metadata)]
    local.execute('INSERT INTO calls(response) VALUES (?)',(json.dumps(combined),))
    monkeypatch.setattr(rollout,'REVIEWS',{})
    rollout.revalidate(local)
    result=json.loads(local.execute('SELECT result FROM jobs').fetchone()[0])
    assert result['collar']=='white'
    assert result['roles']==['Data Analyst']
    assert result['skills']==['SQL']


def test_old_calls_cannot_classify_a_refreshed_posting_version(monkeypatch):
    local=sqlite3.connect(':memory:');local.row_factory=sqlite3.Row
    local.executescript('''CREATE TABLE jobs(id TEXT,title TEXT,description TEXT,result TEXT,error TEXT,attempts INTEGER,start_call_id INTEGER,is_current INTEGER);
    CREATE TABLE calls(id INTEGER PRIMARY KEY,response TEXT);''')
    local.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)',('j1','Data Analyst','Current source',None,None,0,2,1))
    old={'choices':[{'message':{'content':json.dumps({'jobs':[{'id':'j1','collar':'white','roles':['Data Analyst'],'evidence':'Data Analyst'}]})}}]}
    local.execute('INSERT INTO calls VALUES (?,?)',(1,json.dumps(old)))
    monkeypatch.setattr(rollout,'REVIEWS',{})
    rollout.revalidate(local)
    assert local.execute('SELECT result FROM jobs').fetchone()[0] is None
