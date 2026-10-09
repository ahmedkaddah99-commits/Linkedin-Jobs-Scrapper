import json

import pytest

from backend.repositories.sqlite_acquisition import SqliteAcquisitionStore
from backend.database.connection import is_transient_database_error


def ingest(store, cycle='failed-old-cycle', jobs=None):
    store.ensure_targets([{
        'target_id':'producer-fixture','target_kind':'employer_career_site',
        'display_name':'Employer','canonical_target_url':'https://employer.example',
        'provenance_url':'https://employer.example','request_url':'https://employer.example/jobs',
        'connector':'fixture','enabled':True,'publication_enabled':True,'config':{},
    }])
    return store.ingest_snapshots_bulk([{
        'cycle_id':cycle,'task_id':'task-'+cycle,'target_id':'producer-fixture',
        'observed_at':'2026-10-08T12:00:00Z','complete_snapshot':True,
        'valid_snapshot':True,'closure_safe':False,
        'jobs':jobs or [{'job_id':'job','title':'Engineer','company':'Employer',
                        'location':'Berlin','url':'https://employer.example/jobs/1',
                        'description':'Responsibilities and qualifications for this engineering position. '*3}],
    }])


def test_recovers_jobs_from_old_failed_cycles_without_source_replay(tmp_path):
    store=SqliteAcquisitionStore(tmp_path/'catalog.db')
    ingest(store)
    result=store.publish_pending_catalog_jobs(batch_size=10)
    assert result['published']==1
    with store._connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM acquisition_publication_jobs').fetchone()[0]==1
        assert conn.execute("SELECT status FROM acquisition_publication_queue").fetchone()[0]=='published'
    assert store.publish_pending_catalog_jobs(batch_size=10)['published']==0


def test_recovery_survives_commit_failure_and_preserves_existing_feed(tmp_path,monkeypatch):
    store=SqliteAcquisitionStore(tmp_path/'catalog.db')
    ingest(store)
    first=store.publish_pending_catalog_jobs(batch_size=1)
    ingest(store,cycle='second',jobs=[{'job_id':'job-2','title':'Another Engineer','company':'Employer',
            'url':'https://employer.example/jobs/2','location':'Berlin','description':'A detailed engineering role. '*8}])
    original=store._record_publication_audit
    def fail(*args,**kwargs):raise RuntimeError('interrupted')
    monkeypatch.setattr(store,'_record_publication_audit',fail)
    with pytest.raises(RuntimeError,match='interrupted'):
        store.publish_pending_catalog_jobs(batch_size=1)
    with store._connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM acquisition_publication_jobs').fetchone()[0]==1
        assert conn.execute("SELECT COUNT(*) FROM acquisition_publication_queue WHERE status='pending'").fetchone()[0]==1
    monkeypatch.setattr(store,'_record_publication_audit',original)
    assert store.publish_pending_catalog_jobs(batch_size=1)['published']==1
    with store._connect() as conn:
        head=conn.execute('SELECT publication_id FROM acquisition_publication_head WHERE head_id=1').fetchone()[0]
        assert head==first['publication_id']
        assert conn.execute('SELECT COUNT(*) FROM acquisition_publication_jobs WHERE publication_id=?',(head,)).fetchone()[0]==2
        snapshot=json.loads(conn.execute('SELECT snapshot_json FROM acquisition_publications WHERE publication_id=?',(head,)).fetchone()[0])
        assert len(snapshot)==2


def test_navigation_page_is_explicitly_rejected_even_under_v1(tmp_path):
    store=SqliteAcquisitionStore(tmp_path/'catalog.db')
    ingest(store,jobs=[{'job_id':'navigation','title':'Privacy policy','company':'Employer',
                       'url':'https://employer.example/privacy','source_ats':'generic_employer_site'}])
    result=store.publish_pending_catalog_jobs(batch_size=10)
    assert result['published']==0
    assert result['rejected']==1
    with store._connect() as conn:
        row=conn.execute('SELECT status,reason_codes_json FROM acquisition_publication_queue').fetchone()
        assert row['status']=='rejected'
        assert 'generic_navigation_title' in json.loads(row['reason_codes_json'])


def test_hrana_connection_close_is_retryable():
    assert is_transient_database_error(ValueError('Hrana: `http error: `connection closed before message completed``'))


def test_empty_task_completion_uses_bounded_set_updates(tmp_path,monkeypatch):
    from scripts.publish_producer_states import _bulk_complete_empty_tasks
    store=SqliteAcquisitionStore(tmp_path/'catalog.db')
    with store._connect() as conn:
        conn.execute("INSERT INTO acquisition_tasks(task_id,cycle_id,target_id,status,created_at,updated_at) VALUES('empty','cycle','target','pending','before','before')")
    original=store._run_transaction
    class NoPerRow:
        def __init__(self,conn):self.conn=conn
        def execute(self,*args):return self.conn.execute(*args)
        def executemany(self,*args):raise AssertionError('One remote statement per task')
    monkeypatch.setattr(store,'_run_transaction',lambda fn:original(lambda conn:fn(NoPerRow(conn))))
    _bulk_complete_empty_tasks(store,[('empty',True,False,'partial')])
    with store._connect() as conn:
        row=conn.execute("SELECT status,valid_snapshot FROM acquisition_tasks WHERE task_id='empty'").fetchone()
        assert row['status']=='partial' and row['valid_snapshot']==1


def test_collector_round_changes_do_not_abandon_capped_delivery_cycle(tmp_path,monkeypatch):
    from tests.test_producer_state_delivery import _manifest,_seed_producer_states
    import scripts.publish_producer_states as publisher
    manifest=_manifest(tmp_path)
    linkedin,employer=_seed_producer_states(tmp_path)
    args=dict(manifest_path=manifest,linkedin_state=linkedin,employer_state=employer,
              data_dir=tmp_path/'backend',source_version='same-release')
    first=publisher.run_delivery(**args,controls=publisher.BackfillControls(batch_size=250,max_companies=1))
    assert first['status']=='stopped'
    monkeypatch.setattr(publisher,'_linkedin_run_marker',lambda _: 'new-collector-round')
    monkeypatch.setattr(publisher,'_employer_run_marker',lambda _: 'another-new-round')
    second=publisher.run_delivery(**args,controls=publisher.BackfillControls(batch_size=250,max_companies=50))
    assert second['cycle_id']==first['cycle_id']
    assert second['status'] in ('completed','degraded')


def test_recovery_fences_a_version_changed_after_gate_evaluation(tmp_path,monkeypatch):
    from backend.acquisition.publication import StalePublicationHeadError
    store=SqliteAcquisitionStore(tmp_path/'catalog.db');ingest(store)
    original=store._publication_rows_with_completeness
    def concurrent_change(*args,**kwargs):
        result=original(*args,**kwargs)
        with store._connect() as conn:
            conn.execute("UPDATE canonical_jobs SET current_version_id='new-version'")
        return result
    monkeypatch.setattr(store,'_publication_rows_with_completeness',concurrent_change)
    with pytest.raises(StalePublicationHeadError,match='Job changed'):
        store.publish_pending_catalog_jobs(batch_size=10)
    with store._connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM acquisition_publication_jobs').fetchone()[0]==0
        assert conn.execute('SELECT status FROM acquisition_publication_queue').fetchone()[0]=='pending'


def test_rejected_job_requeues_after_content_changes(tmp_path):
    store=SqliteAcquisitionStore(tmp_path/'catalog.db')
    ingest(store,jobs=[{'job_id':'job','title':'Privacy policy','company':'Employer','url':'https://employer.example/privacy'}])
    assert store.publish_pending_catalog_jobs(batch_size=10)['rejected']==1
    with store._connect() as conn:
        conn.execute("UPDATE canonical_jobs SET title='Engineer',last_seen_at='2026-10-09T12:00:00Z'")
        assert conn.execute('SELECT status FROM acquisition_publication_queue').fetchone()[0]=='pending'


def test_recovery_policy_cannot_silently_downgrade_published_policy(tmp_path):
    store=SqliteAcquisitionStore(tmp_path/'catalog.db');ingest(store)
    store.publish_pending_catalog_jobs(batch_size=10)
    with pytest.raises(ValueError,match='policy'):
        store.publish_pending_catalog_jobs(batch_size=10,policy_version='publication_policy_v2')


def test_active_job_removed_by_head_change_is_requeued(tmp_path):
    store=SqliteAcquisitionStore(tmp_path/'catalog.db');ingest(store)
    first=store.publish_pending_catalog_jobs(batch_size=10)
    with store._connect() as conn:
        conn.execute("""INSERT INTO acquisition_publications(publication_id,cycle_id,status,snapshot_json,published_at,
            valid_until,previous_publication_id,origin,created_by,scheduled_run_id,preflight_json,policy_version)
            VALUES('replacement','replacement','valid','[]','now','','','system','test','','{}','publication_policy_v1')""")
        conn.execute("UPDATE acquisition_publication_head SET publication_id='replacement',updated_at='later' WHERE head_id=1")
        assert conn.execute('SELECT status FROM acquisition_publication_queue').fetchone()[0]=='pending'
    assert store.publish_pending_catalog_jobs(batch_size=10)['published']==1


def test_recovery_transaction_does_not_stream_candidate_rows(tmp_path,monkeypatch):
    store=SqliteAcquisitionStore(tmp_path/'catalog.db')
    ingest(store,jobs=[{'job_id':str(i),'title':'Engineer','company':'Employer',
        'url':f'https://employer.example/jobs/{i}','description':'Engineering responsibilities. '*8}
        for i in range(3)])
    original=store._run_transaction
    class BoundedRead:
        def __init__(self,conn):self.conn=conn
        def execute(self,sql,*args):
            cursor=self.conn.execute(sql,*args)
            if sql.lstrip().upper().startswith(('SELECT','WITH')) and cursor.description:
                rows=cursor.fetchall()
                assert len(rows)<=1,'A recovery transaction must not stream candidates over remote cursors'
                class Row:
                    def fetchone(self):return rows[0] if rows else None
                    def fetchall(self):return rows
                return Row()
            return cursor
    monkeypatch.setattr(store,'_run_transaction',lambda fn:original(lambda conn:fn(BoundedRead(conn))))
    assert store.publish_pending_catalog_jobs(batch_size=3)['published']==3


def test_recovery_fences_run_under_a_write_transaction(tmp_path,monkeypatch):
    store=SqliteAcquisitionStore(tmp_path/'catalog.db');ingest(store)
    original=store._run_transaction
    class AtomicFence:
        def __init__(self,conn):self.conn=conn
        def execute(self,sql,*args):
            if sql.lstrip().upper().startswith('SELECT'):
                assert self.conn._connection.in_transaction,'Fences must run after acquiring the write transaction'
            return self.conn.execute(sql,*args)
    monkeypatch.setattr(store,'_run_transaction',lambda fn:original(lambda conn:fn(AtomicFence(conn))))
    assert store.publish_pending_catalog_jobs(batch_size=1)['published']==1

