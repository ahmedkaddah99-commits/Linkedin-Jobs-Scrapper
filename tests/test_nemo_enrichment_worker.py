import json
import sqlite3
from pathlib import Path
from unittest.mock import patch
import unittest
from tests import test_jobs_role_scoped_feed as fixtures
from scripts import process_catalog_enrichment as worker

class NemoWorkerPersistenceTests(unittest.TestCase):
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
    self.assertEqual(len(prompts),1)
    self.assertNotIn('Classify each',prompts[0])

 def test_acceptable_older_nemo_output_is_reused_without_model_calls(self):
  from backend.application.vps_job_descriptions import build_pilot_description
  app=self.classified();store=app.repositories.personalized_jobs_store
  with store._connect() as c:
   def sql(query,args=()):return [dict(r) for r in c.execute(query,args).fetchall()]
   with patch.object(worker,'execute',sql):
    token,rows=worker.claim(1);row=rows[0]
    c.execute("UPDATE job_filter_intelligence SET model='mistralai/mistral-nemo',prompt_version='older_acceptable_prompt' WHERE version_id=?",(row['current_version_id'],))
    old=build_pilot_description(row,lambda _: {'items':[{'section':'responsibilities','text':'Analyze operations.','source_ids':['p1']}],'header_candidates':{}})
    worker.save_stage(row,token,{'description':old})
    c.execute("UPDATE job_enrichment_queue SET state='pending',lease_token='' WHERE version_id=?",(row['current_version_id'],))
    c.execute("UPDATE job_enrichment_queue SET next_attempt_at='9999' WHERE version_id!=?",(row['current_version_id'],))
    token,rows=worker.claim(1)
    self.assertTrue(rows[0]['filters_ready']);self.assertTrue(rows[0]['description_ready'])
    def forbidden(_):raise AssertionError('acceptable output must not be regenerated')
    self.assertEqual(worker.process(rows[0],token,forbidden),'completed')
    cached=c.execute('SELECT prompt_version FROM job_description_intelligence WHERE version_id=?',(row['current_version_id'],)).fetchone()
    self.assertEqual(cached['prompt_version'],'runr_description_nemo_v2')
