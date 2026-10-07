import json
import sqlite3
from pathlib import Path
from unittest.mock import patch
import unittest
from tests import test_jobs_role_scoped_feed as fixtures
from scripts import process_catalog_enrichment as worker

class NemoWorkerPersistenceTests(unittest.TestCase):
 def test_claim_uses_selected_version_lookups_and_can_skip_maintenance(self):
  app=self.classified();store=app.repositories.personalized_jobs_store
  with store._connect() as c:
   queries=[]
   def sql(query,args=()):
    queries.append(query)
    if "SET state='processing',attempts=" in query:
     plan=[dict(r) for r in c.execute('EXPLAIN QUERY PLAN '+query,args).fetchall()]
     outer=[r['detail'] for r in plan if 'SEARCH job_enrichment_queue ' in r['detail']]
     self.assertTrue(any('version_id=?' in detail for detail in outer),plan)
    return [dict(r) for r in c.execute(query,args).fetchall()]
   with patch.object(worker,'execute',sql):
    self.assertEqual(len(worker.claim(1,maintain=False)[1]),1)
   self.assertEqual(len(queries),2)

 def test_claim_timeout_recovers_without_terminating_worker(self):
  import tempfile
  from unittest.mock import Mock
  client=Mock();client.remaining.return_value=10
  with tempfile.TemporaryDirectory() as directory:
   with patch.object(worker,'load_project_dotenv'),patch.object(worker,'validate_release_provenance'),patch.object(worker,'NemoClient',return_value=client),patch.object(worker,'claim',side_effect=[TimeoutError('private detail'),('lease',[])] ) as claim,patch.object(worker.time,'sleep'),patch.object(worker.time,'monotonic',side_effect=range(0,1000,10)),patch.dict(worker.os.environ,{'OPENROUTER_API_KEY':'test','TURSO_DATABASE_URL':'test','TURSO_AUTH_TOKEN':'test'}),patch('sys.argv',['worker','--ledger',str(Path(directory)/'ledger.sqlite3')]),patch('builtins.print') as log:
    self.assertEqual(worker.main(),0)
    self.assertEqual(claim.call_count,2)
    messages=[json.loads(call.args[0]) for call in log.call_args_list]
    self.assertEqual(messages[-1]['claim_failed'],1)
    self.assertNotIn('private detail',str(messages))

 def test_provider_routes_for_speed_with_existing_spend_limits(self):
  import tempfile
  from unittest.mock import MagicMock
  response=MagicMock()
  response.__enter__.return_value.read.return_value=json.dumps({'model':'mistralai/mistral-nemo','usage':{'cost':0.0001},'choices':[{'message':{'content':'{}'}}]}).encode()
  with tempfile.TemporaryDirectory() as directory:
   client=worker.NemoClient(Path(directory)/'ledger.sqlite3',10)
   try:
    with patch.dict(worker.os.environ,{'OPENROUTER_API_KEY':'test'}),patch.object(worker,'urlopen',return_value=response) as send:
     client('test prompt')
     body=json.loads(send.call_args.args[0].data)
     self.assertEqual(body['provider']['sort'],'throughput')
     self.assertNotIn('order',body['provider'])
     self.assertEqual(body['provider']['max_price'],{'prompt':0.03,'completion':0.03})
   finally:
    client.db.close()

 def test_failure_to_record_a_job_error_does_not_stop_other_jobs(self):
  row={'current_version_id':'test-version'}
  with patch.object(worker,'process',side_effect=[TimeoutError('private connection detail'),'completed']),patch('builtins.print') as log:
   self.assertEqual(worker.process_isolated(row,'lease',None),'persistence_TimeoutError')
   self.assertEqual(worker.process_isolated(row,'lease',None),'completed')
   message=json.loads(log.call_args.args[0])
   self.assertEqual(message['error_code'],'TimeoutError')
   self.assertNotIn('private connection detail',log.call_args.args[0])
 _backend=fixtures.RoleScopedFeedTests._backend
 def classified(self):
  original=fixtures._seed_catalog
  description='Analyze operations. Build accurate monthly reports and coordinate requirements with business stakeholders.'
  def seed(app):original(app,payload_overrides={job:{'description':description} for job in ('job-a','job-b')})
  with patch.object(fixtures,'_seed_catalog',seed):
   return fixtures.RoleScopedFeedTests.classified(self)
 def test_claim_save_and_reuse_after_description_failure(self):
  app=self.classified();store=app.repositories.personalized_jobs_store
  with store._connect() as c:
   c.execute("DELETE FROM job_filter_intelligence")
   def sql(query,args=()):return [dict(r) for r in c.execute(query,args).fetchall()]
   with patch.object(worker,'execute',sql):
    token,rows=worker.claim(2);self.assertEqual(len(rows),2)
    def generate(_):return {'items':[{'section':'responsibilities','text':'Analyze operations.','source_ids':['p1'],'source_quote':'Analyze operations.'}],'header_candidates':{},'_runr_model':'mistralai/mistral-nemo'}
    # Seeded filters are not Nemo, so exercise the filter stage too.
    def both(prompt):
     if 'Classify each' in prompt:
      posting=json.loads(prompt.rsplit('Postings: ',1)[1])[0]
      identity=posting['id'];title=posting['title']
      return {'jobs':[{'id':identity,'collar':'white','roles':['Business Analyst'],'evidence':title}]}
     return generate(prompt)
    self.assertEqual(worker.process(rows[0],token,both),'completed')
    ready=c.execute('SELECT state FROM job_enrichment_queue WHERE version_id=?',(rows[0]['current_version_id'],)).fetchone()
    self.assertEqual(ready['state'],'completed')
    self.assertEqual(worker.process(rows[1],token,both),'completed')
    self.assertEqual(worker.claim(2)[1],[])

 def test_save_cannot_overwrite_a_superseded_version(self):
  app=self.classified();store=app.repositories.personalized_jobs_store
  with store._connect() as c:
   def sql(query,args=()):return [dict(r) for r in c.execute(query,args).fetchall()]
   with patch.object(worker,'execute',sql):
    token,rows=worker.claim(1);row=rows[0]
    c.execute('UPDATE canonical_jobs SET current_version_id=? WHERE canonical_job_id=?',('other',row['canonical_job_id']))
    worker.save_stage(row,token,{'filters':{'collar':'white','roles':['Finance Analyst']}})
    actual=c.execute('SELECT model FROM job_filter_intelligence WHERE version_id=?',(row['current_version_id'],)).fetchone()
    self.assertEqual(actual['model'],'test')

 def test_description_failure_preserves_filters_and_retry_only_generates_description(self):
  app=self.classified();store=app.repositories.personalized_jobs_store
  with store._connect() as c:
   c.execute("DELETE FROM job_filter_intelligence")
   def sql(query,args=()):return [dict(r) for r in c.execute(query,args).fetchall()]
   with patch.object(worker,'execute',sql):
    token,rows=worker.claim(1);row=rows[0]
    def fail_description(prompt):
     if 'Classify each' in prompt:
      posting=json.loads(prompt.rsplit('Postings: ',1)[1])[0]
      return {'jobs':[{'id':posting['id'],'collar':'white','roles':['Business Analyst'],'evidence':posting['title']}]}
     raise RuntimeError('temporary_provider_failure')
    self.assertEqual(worker.process(row,token,fail_description),'RuntimeError')
    cached=c.execute('SELECT model FROM job_filter_intelligence WHERE version_id=?',(row['current_version_id'],)).fetchone()
    self.assertEqual(cached['model'],'mistralai/mistral-nemo')
    c.execute("UPDATE job_enrichment_queue SET next_attempt_at='' WHERE version_id=?",(row['current_version_id'],))
    # Only this version is due for the retry.
    c.execute("UPDATE job_enrichment_queue SET next_attempt_at='9999' WHERE version_id!=?",(row['current_version_id'],))
    token,rows=worker.claim(1);self.assertTrue(rows[0]['filters_ready'])
    prompts=[]
    def description(prompt):
     prompts.append(prompt)
     return {'items':[{'section':'responsibilities','text':'Analyze operations.','source_ids':['p1'],'source_quote':'Analyze operations.'}],'header_candidates':{},'_runr_model':'mistralai/mistral-nemo'}
    self.assertEqual(worker.process(rows[0],token,description),'completed')
    self.assertEqual(len(prompts),2)
    self.assertNotIn('Classify each',prompts[0])

 def test_acceptable_existing_output_is_reused_without_model_calls(self):
  from backend.application.vps_job_descriptions import build_pilot_description
  app=self.classified();store=app.repositories.personalized_jobs_store
  with store._connect() as c:
   def sql(query,args=()):return [dict(r) for r in c.execute(query,args).fetchall()]
   with patch.object(worker,'execute',sql):
    token,rows=worker.claim(1);row=rows[0]
    c.execute("UPDATE job_filter_intelligence SET model='older_provider',prompt_version='older_acceptable_prompt' WHERE version_id=?",(row['current_version_id'],))
    old=build_pilot_description(row,lambda _: {'items':[{'section':'responsibilities','text':'Analyze operations.','source_ids':['p1']}],'header_candidates':{}})
    old.update(model='runr_rules',provider='rules',prompt_version='runr_description_v1')
    worker.save_stage(row,token,{'description':old})
    c.execute("UPDATE job_description_intelligence SET model='runr_rules',provider='rules' WHERE version_id=?",(row['current_version_id'],))
    c.execute("UPDATE job_enrichment_queue SET state='pending',lease_token='' WHERE version_id=?",(row['current_version_id'],))
    c.execute("UPDATE job_enrichment_queue SET next_attempt_at='9999' WHERE version_id!=?",(row['current_version_id'],))
    token,rows=worker.claim(1)
    self.assertTrue(rows[0]['filters_ready']);self.assertTrue(rows[0]['description_ready'])
    extra=[]
    def forbidden(prompt):
     extra.append(prompt)
     return {'filters':{'jobs':[]},'description':{'items':[],'header_candidates':{}}}
    self.assertEqual(worker.process(rows[0],token,forbidden),'completed')
    cached=c.execute('SELECT prompt_version FROM job_description_intelligence WHERE version_id=?',(row['current_version_id'],)).fetchone()
    self.assertEqual(cached['prompt_version'],'runr_description_v1')
    audit=c.execute('SELECT gap_pass_attempted,missing_fields_json FROM job_enrichment_queue WHERE version_id=?',(row['current_version_id'],)).fetchone()
    self.assertEqual(audit['gap_pass_attempted'],1)
    self.assertIn('structured.salary',json.loads(audit['missing_fields_json']))
    c.commit()
    public=json.dumps(app.get_personalized_job_detail('user-a',row['canonical_job_id']))
    self.assertNotIn('missing_fields_json',public)
    self.assertNotIn('gap_pass_attempted',public)
    self.assertEqual(len(extra),1)
    self.assertIn('supplemental',extra[0])
    self.assertEqual(worker.claim(1)[1],[])
