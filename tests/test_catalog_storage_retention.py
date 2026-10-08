from datetime import datetime, timedelta, timezone
import sqlite3

import pytest
from backend.repositories.sqlite_acquisition import SqliteAcquisitionStore
from backend.acquisition.storage_retention import maintain_catalog_storage


@pytest.fixture
def catalog(tmp_path):
    path = tmp_path / 'backend.sqlite3'
    SqliteAcquisitionStore(path)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS runr_catalog_storage_maintenance (name TEXT PRIMARY KEY,last_rowid INTEGER NOT NULL DEFAULT 0,last_run_at TEXT NOT NULL DEFAULT \'\',last_error TEXT NOT NULL DEFAULT \'\')')
        for n in range(8):
            db.execute("INSERT INTO acquisition_publications(publication_id,cycle_id,status,snapshot_json,published_at,previous_publication_id) VALUES(?,?, 'valid',?, ?, ?)", (f'p{n}',f'c{n}','[]',f'2026-10-0{n+1}T00:00:00+00:00',f'p{n-1}' if n else ''))
            db.executemany('INSERT INTO acquisition_publication_jobs VALUES(?,?)', [(f'p{n}', f'j{k}') for k in range(5)])
        db.execute("INSERT INTO acquisition_publication_head VALUES(1,'p7','now')")
        db.execute("INSERT INTO acquisition_publisher_checkpoints(source,last_publication_id,updated_at) VALUES('linkedin','p1','now')")
        db.execute("INSERT INTO acquisition_cycles(cycle_id,window_key,status,scheduled_at,created_at,updated_at,publication_id) VALUES('active','active','recovery_required','now','now','now','p2')")
    return path


def ids(path):
    with sqlite3.connect(path) as db:
        return {r[0] for r in db.execute('SELECT publication_id FROM acquisition_publications')}


def test_dry_run_and_pins(catalog):
    before = ids(catalog)
    receipt = maintain_catalog_storage(catalog, batch_size=2, max_seconds=2)
    assert ids(catalog) == before
    assert receipt['apply'] is False
    maintain_catalog_storage(catalog, apply=True, batch_size=2, max_seconds=5)
    assert ids(catalog) == {'p1','p2','p5','p6','p7'}


def test_bounded_progress_and_restart(catalog):
    result = maintain_catalog_storage(catalog, apply=True, batch_size=2, max_seconds=5, max_batches=1)
    assert result['deleted_memberships'] <= 2
    assert 'p0' in ids(catalog)
    with sqlite3.connect(catalog) as db:
        assert db.execute('SELECT count(*) FROM runr_catalog_storage_maintenance').fetchone()[0] > 0
    maintain_catalog_storage(catalog, apply=True, batch_size=2, max_seconds=5)
    assert ids(catalog) == {'p1','p2','p5','p6','p7'}


def test_immediate_rollback_pin(catalog):
    with sqlite3.connect(catalog) as db:
        db.execute("UPDATE acquisition_publications SET previous_publication_id='p0' WHERE publication_id='p7'")
    maintain_catalog_storage(catalog, apply=True, batch_size=2, max_seconds=5)
    assert 'p0' in ids(catalog)


def test_rejections_age_and_active_cycle(catalog):
    now = datetime(2026,10,8,tzinfo=timezone.utc)
    with sqlite3.connect(catalog) as db:
        for key, age, cycle in [('old',8,'done'),('young',6,'done'),('active',8,'active')]:
            db.execute('INSERT INTO acquisition_job_rejections(rejection_id,request_id,cycle_id,task_id,target_id,reason_code,observed_at) VALUES(?,?,?,?,?,?,?)',(key,key,cycle,'t','target','bad',(now-timedelta(days=age)).isoformat()))
    maintain_catalog_storage(catalog, apply=True, batch_size=2, max_seconds=5, now=now)
    with sqlite3.connect(catalog) as db:
        assert {r[0] for r in db.execute('SELECT rejection_id FROM acquisition_job_rejections')} == {'young','active'}


def test_empty_provenance_requires_current_state_projection(catalog):
    with sqlite3.connect(catalog) as db:
        db.execute("INSERT INTO canonical_jobs(canonical_job_id,company_id,identity_key,title,first_seen_at,last_seen_at,current_version_id,created_at,updated_at) VALUES('job','co','key','title','now','now','version','now','now')")
        db.execute('INSERT INTO job_posting_versions(version_id,canonical_job_id,version_number,content_hash,title,source_observation_id,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?)', ('version','job',1,'hash','title','obs','{"unified_mapping":{"fields":{"empty":{"state":"missing"},"evidence":{"state":"missing"}}}}','now'))
        for field, evidence in [('empty','null'),('evidence','{"reason":"known"}'),('unmapped','null')]:
            db.execute('INSERT INTO acquisition_field_provenance(provenance_id,entity_kind,entity_id,field_name,state,evidence_json,rule_version,created_at) VALUES(?,?,?,?,?,?,?,?)',(field,'job','job',field,'missing',evidence,'v1','now'))
    receipt = maintain_catalog_storage(catalog, apply=True, batch_size=1, max_seconds=5)
    assert receipt['deleted_empty_provenance'] == 1
    with sqlite3.connect(catalog) as db:
        assert {r[0] for r in db.execute('SELECT provenance_id FROM acquisition_field_provenance')} == {'evidence','unmapped'}

def test_failed_batch_rolls_back_memberships_and_records_error(catalog):
    with sqlite3.connect(catalog) as db:
        db.execute("CREATE TRIGGER fail_membership_delete BEFORE DELETE ON acquisition_publication_jobs BEGIN SELECT RAISE(ABORT,'test failure'); END")
    with pytest.raises(Exception, match='test failure'):
        maintain_catalog_storage(catalog, apply=True, batch_size=2, max_seconds=5)
    with sqlite3.connect(catalog) as db:
        assert db.execute("SELECT count(*) FROM acquisition_publication_jobs WHERE publication_id='p0'").fetchone()[0] == 5
        assert db.execute("SELECT last_error FROM runr_catalog_storage_maintenance WHERE name='publications'").fetchone()[0] == 'IntegrityError'

def source_fixture(catalog, tmp_path):
    import json
    from backend.storage.local import LocalObjectStorage
    from backend.acquisition.storage_evidence import archive_catalog_evidence
    storage = LocalObjectStorage(tmp_path / 'evidence')
    reference = archive_catalog_evidence({'title':'original'}, storage=storage)
    payload = json.dumps({**reference,'catalog_storage_version':1})
    with sqlite3.connect(catalog) as db:
        for key,cycle,age in [('eligible','old',30),('latest','old',20),('version','old',30),('related','old',30),('active_obs','active',30),('young_obs','old',5),('unarchived','old',30)]:
            # Every protected observation except eligible has its own source pair
            # and a later witness, so other safety conditions are exercised.
            pair = 'pair' if key in ('eligible','latest') else key
            db.execute('INSERT INTO job_source_observations(observation_id,canonical_job_id,target_id,cycle_id,task_id,external_job_id,payload_json,observed_at) VALUES(?,?,?,?,?,?,?,?)',(key,'job',pair,cycle,key,key,payload if key!='unarchived' else '{}',(datetime(2026,10,8,tzinfo=timezone.utc)-timedelta(days=age)).isoformat()))
            if key not in ('eligible','latest'):
                db.execute('INSERT INTO job_source_observations(observation_id,canonical_job_id,target_id,cycle_id,task_id,external_job_id,payload_json,observed_at) VALUES(?,?,?,?,?,?,?,?)',(key+'_new','job',pair,'new',key,key+'_new',payload,'2026-10-07T00:00:00+00:00'))
        db.execute("INSERT INTO job_posting_versions(version_id,canonical_job_id,version_number,content_hash,title,source_observation_id,created_at) VALUES('heldversion','job',1,'hash','title','version','now')")
        db.execute("INSERT INTO job_source_observation_relationships VALUES('rel','related','latest','same','now')")
    return storage


def test_source_pruning_pins_and_restores_guard(catalog,tmp_path):
    storage = source_fixture(catalog,tmp_path)
    receipt = maintain_catalog_storage(catalog, apply=True,batch_size=2,max_seconds=5,now=datetime(2026,10,8,tzinfo=timezone.utc), evidence_storage=storage)
    assert receipt['deleted_source_observations'] == 1
    with sqlite3.connect(catalog) as db:
        remaining = {r[0] for r in db.execute('SELECT observation_id FROM job_source_observations')}
        assert 'eligible' not in remaining
        assert {'latest','version','related','active_obs','young_obs','unarchived'} <= remaining
        assert db.execute("SELECT sql FROM sqlite_master WHERE name='trg_job_source_observations_immutable_delete'").fetchone()
        with pytest.raises(sqlite3.IntegrityError,match='immutable'):
            db.execute("DELETE FROM job_source_observations WHERE observation_id='latest'")


def test_source_pruning_skips_active_replay_and_missing_evidence(catalog,tmp_path):
    storage = source_fixture(catalog,tmp_path)
    with sqlite3.connect(catalog) as db:
        db.execute("INSERT INTO acquisition_reprocessing_runs(reprocessing_id,idempotency_key,status,rule_version,created_at,updated_at) VALUES('replay','key','running','v1','now','now')")
    receipt = maintain_catalog_storage(catalog,apply=True,batch_size=2,max_seconds=5,evidence_storage=storage)
    assert receipt['deleted_source_observations'] == 0

def test_source_pruning_missing_evidence_is_retained(catalog,tmp_path):
    storage = source_fixture(catalog,tmp_path)
    import json
    with sqlite3.connect(catalog) as db:
        reference = json.loads(db.execute("SELECT payload_json FROM job_source_observations WHERE observation_id='eligible'").fetchone()[0])
    storage.delete(reference['storage_evidence_key'])
    receipt = maintain_catalog_storage(catalog,apply=True,batch_size=2,max_seconds=5,now=datetime(2026,10,8,tzinfo=timezone.utc),evidence_storage=storage)
    assert receipt['deleted_source_observations'] == 0
    assert receipt['source_verification_failures'] == 1
    with sqlite3.connect(catalog) as db:
        assert db.execute("SELECT 1 FROM job_source_observations WHERE observation_id='eligible'").fetchone()


def test_source_delete_failure_restores_guard_and_row(catalog,tmp_path):
    storage = source_fixture(catalog,tmp_path)
    with sqlite3.connect(catalog) as db:
        original = db.execute("SELECT sql FROM sqlite_master WHERE name='trg_job_source_observations_immutable_delete'").fetchone()[0]
        db.execute("CREATE TRIGGER another_source_guard BEFORE DELETE ON job_source_observations BEGIN SELECT RAISE(ABORT,'operator failure'); END")
    with pytest.raises(Exception,match='operator failure'):
        maintain_catalog_storage(catalog,apply=True,batch_size=2,max_seconds=5,now=datetime(2026,10,8,tzinfo=timezone.utc),evidence_storage=storage)
    with sqlite3.connect(catalog) as db:
        assert db.execute("SELECT sql FROM sqlite_master WHERE name='trg_job_source_observations_immutable_delete'").fetchone()[0] == original
        assert db.execute("SELECT 1 FROM job_source_observations WHERE observation_id='eligible'").fetchone()

@pytest.mark.parametrize('reference_table',['acquisition_field_provenance','acquisition_rule_outputs'])
def test_source_pruning_preserves_derived_references(catalog,tmp_path,reference_table):
    storage = source_fixture(catalog,tmp_path)
    with sqlite3.connect(catalog) as db:
        if reference_table == 'acquisition_field_provenance':
            db.execute("INSERT INTO acquisition_field_provenance(provenance_id,entity_kind,entity_id,field_name,source_observation_id,state,rule_version,created_at) VALUES('derived','job','job','field','eligible','known','v1','now')")
        else:
            db.execute("INSERT INTO acquisition_rule_outputs(output_id,entity_kind,entity_id,source_observation_id,stage_name,rule_version,created_at) VALUES('derived','job','job','eligible','normalization','v1','now')")
    receipt = maintain_catalog_storage(catalog,apply=True,batch_size=2,max_seconds=5,now=datetime(2026,10,8,tzinfo=timezone.utc),evidence_storage=storage)
    assert receipt['deleted_source_observations'] == 0

def test_empty_provenance_batches_real_state_queries_by_job(catalog,monkeypatch):
    import json
    from backend.database.connection import DatabaseConnection
    with sqlite3.connect(catalog) as db:
        for n in range(51):
            job,version = f'job{n}',f'version{n}'
            db.execute('INSERT INTO canonical_jobs(canonical_job_id,company_id,identity_key,title,first_seen_at,last_seen_at,current_version_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(job,'co',job,'title','now','now',version,'now','now'))
            mapping = {'fields':{'empty.a':{'state':'missing'},'empty"b':{'state':'unknown'}}}
            payload = {('unified_mapping' if n%2 else 'normalized_mapping'): mapping, 'large_unneeded_description':'x'*10000}
            db.execute('INSERT INTO job_posting_versions(version_id,canonical_job_id,version_number,content_hash,title,source_observation_id,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?)',(version,job,1,'hash','title','obs',json.dumps(payload),'now'))
            for field,state in [('empty.a','missing'),('empty"b','unknown')]:
                db.execute('INSERT INTO acquisition_field_provenance(provenance_id,entity_kind,entity_id,field_name,state,rule_version,created_at) VALUES(?,?,?,?,?,?,?)',(job+field,'job',job,field,state,'v1','now'))
    original = DatabaseConnection.execute
    actual_queries = []
    def traced_execute(db,sql,parameters=()):
        if 'FROM canonical_jobs j JOIN job_posting_versions v' in sql:
            actual_queries.append((sql,parameters))
        return original(db,sql,parameters)
    monkeypatch.setattr(DatabaseConnection,'execute',traced_execute)
    receipt = maintain_catalog_storage(catalog,apply=True,batch_size=1000,max_seconds=30,max_batches=3)
    assert receipt['deleted_empty_provenance'] == 102
    assert len(actual_queries) == 2
    assert all('json_each' in sql and 'json_group_object' in sql and len(params)<=50 for sql,params in actual_queries)

def test_receipt_reports_replay_pin_backlog(catalog,tmp_path):
    storage = source_fixture(catalog,tmp_path)
    with sqlite3.connect(catalog) as db:
        for status in ('failed','incomplete'):
            db.execute('INSERT INTO acquisition_reprocessing_runs(reprocessing_id,idempotency_key,status,rule_version,created_at,updated_at) VALUES(?,?,?,?,?,?)',(status,status,status,'v1','2026-01-01','2026-01-02'))
    receipt = maintain_catalog_storage(catalog,apply=True,batch_size=2,max_seconds=5,evidence_storage=storage)
    source = receipt['phase_backlog']['source_observations']
    assert source['status'] == 'blocked'
    assert {row['status']:row['count'] for row in source['replay_blockers']} == {'failed':1,'incomplete':1}
    assert receipt['complete'] is False
    with sqlite3.connect(catalog) as db:
        assert {r[0] for r in db.execute('SELECT status FROM acquisition_reprocessing_runs')} == {'failed','incomplete'}
