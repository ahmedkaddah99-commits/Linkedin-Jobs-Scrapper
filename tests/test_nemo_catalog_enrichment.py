import json
import unittest
from tests import test_jobs_role_scoped_feed as fixtures
from tests.test_phase_c_personalized_jobs import _seed_catalog

class NemoQueueTests(unittest.TestCase):
 _backend = fixtures.RoleScopedFeedTests._backend
 def test_published_versions_enqueue_once_and_new_versions_enqueue(self):
  app=self._backend();_seed_catalog(app);s=app.repositories.acquisition_store
  def check(c):
   rows=c.execute('SELECT version_id FROM job_enrichment_queue').fetchall();self.assertEqual(len(rows),2)
   c.execute("INSERT OR IGNORE INTO acquisition_publication_jobs VALUES ('publication-c','job-a')")
   self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM job_enrichment_queue').fetchone()['n'],2)
   c.execute("INSERT INTO job_posting_versions SELECT 'changed',canonical_job_id,2,'changed',title,description,location,apply_url,source_observation_id,payload_json,created_at FROM job_posting_versions WHERE version_id='version-job-a'")
   c.execute("UPDATE canonical_jobs SET current_version_id='changed' WHERE canonical_job_id='job-a'")
   self.assertEqual(c.execute("SELECT canonical_job_id FROM job_enrichment_queue WHERE version_id='changed'").fetchone()['canonical_job_id'],'job-a')
  s._run_transaction(check)

