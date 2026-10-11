"""Exercise producer evidence through publication, enrichment, facts and customer detail."""
from unittest.mock import patch
from backend.bootstrap import create_backend
from backend.domain.models import UserRecord
from scripts.publish_producer_states import run_delivery
from scripts import process_catalog_enrichment as enrichment
from scripts import process_profile_job_facts as facts
from tests.test_producer_state_delivery import _manifest, _seed_producer_states


def test_fresh_collection_publication_enrichment_facts_and_customer_detail(tmp_path,monkeypatch):
    monkeypatch.setenv('RUNR_ENV','test')
    monkeypatch.setenv('RUNR_TEST_MODE','1')
    monkeypatch.setenv('DATABASE_BACKEND','sqlite')
    monkeypatch.delenv('TURSO_DATABASE_URL',raising=False)
    monkeypatch.delenv('TURSO_AUTH_TOKEN',raising=False)
    manifest=_manifest(tmp_path)
    linkedin,employer=_seed_producer_states(tmp_path)
    data=tmp_path/'backend'
    receipt=run_delivery(manifest_path=manifest,linkedin_state=linkedin,employer_state=employer,
                         data_dir=data,source_version='e2e-fixture')
    assert receipt['publication_id']
    monkeypatch.setenv('SQLITE_DATABASE_PATH',str(data/'backend.sqlite3'))
    app=create_backend(data,storage_backend='sqlite',test_mode=True)
    app.repositories.auth_repository.upsert_user(UserRecord(user_id='e2e-user',email='e2e@example.com'))
    token,rows=enrichment.claim(10)
    assert len(rows)==3  # Current v1 policy retains the audited LinkedIn posting fallback.
    for row in rows:
        def generate(prompt):
            return {'jobs':[{'id':row['canonical_job_id'],'collar':'white','roles':['Backend Engineer'],
                              'evidence':row['title']}],
                    'items':[{'section':'responsibilities','text':row['description'],
                              'source_quote':row['description'],'source_ids':['p1']}],
                    'header_candidates':{}}
        assert enrichment.process(row,token,generate)=='completed'
    with patch('sys.argv',['facts','--max-jobs','10']):
        facts.main()
    for row in rows:
        detail=app.get_personalized_job_detail('e2e-user',row['canonical_job_id'])
        assert detail['runr_summary']['responsibilities']
        assert detail['original_posting']
    current=enrichment.execute('SELECT COUNT(*) AS n FROM profile_job_facts')
    assert current[0]['n']==3
    assert enrichment.execute('SELECT COUNT(*) AS n FROM profile_job_fact_queue')[0]['n']==0
    assert not enrichment.claim(10)[1]
