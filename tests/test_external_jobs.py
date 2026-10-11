import json
import os
import unittest
from email.message import Message
from unittest.mock import MagicMock, patch

from tests import test_phase_c_personalized_jobs as fixtures
from backend.domain.models import utc_now_iso


DESCRIPTION = ('Responsibilities\nBuild software and maintain reliable services for customers.\n'
               'Requirements\nThree years of software engineering experience. Python skills required.\n'
               'This is a full-time mid-level position working on-site in Berlin.')
URL = 'https://example.com/jobs/software-engineer'


class ExternalJobsTests(unittest.TestCase):
    def test_fetch_accepts_standard_http_header_capitalization(self):
        from backend.application.external_jobs import fetch_job_page
        headers = Message()
        headers['Content-Type'] = 'text/html; charset=utf-8'
        headers['Content-Length'] = '26'
        response = MagicMock()
        response.url = URL
        response.headers = headers
        response.read.return_value = b'<html>Job posting</html>'
        response.__enter__.return_value = response
        with patch('backend.application.company_enrichment.assert_public_official_host'), \
             patch('backend.application.company_enrichment.build_opener') as opener:
            opener.return_value.open.return_value = response
            self.assertEqual(fetch_job_page(URL), '<html>Job posting</html>')

    def _backend(self):
        app = fixtures.PhaseCPersonalizedJobsTests._backend(self)
        return app

    def setUp(self):
        environment = patch.dict(os.environ, {'OPENROUTER_API_KEY': ''})
        environment.start()
        self.addCleanup(environment.stop)
        provider = patch('backend.application.external_jobs.openrouter_generate', side_effect=RuntimeError('provider unavailable'))
        provider.start()
        self.addCleanup(provider.stop)

    def test_manual_import_is_persisted_private_and_uses_jobs_actions(self):
        app = self._backend()
        result = app.import_personalized_job('user-a', {
            'url': URL, 'manual': True, 'title': 'Software Engineer',
            'company': 'Example', 'location': 'Berlin', 'description': DESCRIPTION,
        })
        job_id = result['job']['canonical_job_id']
        detail = app.get_personalized_job_detail('user-a', job_id)
        self.assertEqual(detail['title'], 'Software Engineer')
        self.assertEqual(detail['original_posting']['description_text'], DESCRIPTION)
        self.assertIsNone(app.get_personalized_job_detail('user-b', job_id))
        self.assertEqual(app.set_personalized_job_state('user-a', job_id, 'saved')['state'], 'saved')
        with self.assertRaises(KeyError):
            app.set_personalized_job_state('user-b', job_id, 'saved')
        self.assertEqual(app.list_external_jobs('user-a')['jobs'][0]['canonical_job_id'], job_id)

    def test_manual_import_rejects_non_job_and_oversized_fields(self):
        app = self._backend()
        for fields in ({'description': 'A recipe for chocolate cake. ' * 15},
                       {'title': 'x' * 201}, {'description': 'x' * 50001}):
            with self.subTest(fields=list(fields)):
                with self.assertRaises(ValueError):
                    app.import_personalized_job('user-a', {
                        'url': URL, 'manual': True, 'title': 'Software Engineer',
                        'company': 'Example', 'description': DESCRIPTION, **fields,
                    })

    def test_existing_catalog_url_opens_existing_job(self):
        app = self._backend()
        now = utc_now_iso()
        def seed(connection):
            connection.execute('INSERT INTO canonical_companies (company_id,canonical_name,created_at,updated_at) VALUES (?,?,?,?)',
                               ('company-a', 'Acme Labs', now, now))
            connection.execute('''INSERT INTO canonical_jobs (canonical_job_id,company_id,identity_key,title,canonical_url,
                first_seen_at,last_seen_at,last_verified_at,current_version_id,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''', ('job-a', 'company-a', 'job-a', 'Engineer',
                    'https://boards.greenhouse.io/acme/jobs/a', now, now, now, 'version-a', now, now))
            connection.execute('''INSERT INTO job_posting_versions (version_id,canonical_job_id,version_number,content_hash,title,
                description,source_observation_id,created_at) VALUES (?,?,1,?,?,?,?,?)''',
                ('version-a', 'job-a', 'hash-a', 'Engineer', DESCRIPTION, 'observation-a', now))
            connection.execute('''INSERT INTO acquisition_publications (publication_id,cycle_id,status,snapshot_json,published_at,
                valid_until,previous_publication_id) VALUES ('publication-a','cycle-a','valid','[]',?,'','')''', (now,))
            connection.execute("INSERT INTO acquisition_publication_jobs (publication_id,canonical_job_id) VALUES ('publication-a','job-a')")
            connection.execute("INSERT INTO acquisition_publication_head VALUES (1,'publication-a',?)", (now,))
        app.repositories.acquisition_store._run_transaction(seed)
        result = app.import_personalized_job('user-a', {'url': 'https://boards.greenhouse.io/acme/jobs/a'})
        self.assertEqual(result['job']['title'], 'Engineer')
        job_id = result['job']['canonical_job_id']
        self.assertTrue(job_id.startswith('import_'))
        self.assertEqual(app.list_external_jobs('user-a')['jobs'][0]['canonical_job_id'], job_id)
        app.repositories.acquisition_store._run_transaction(lambda c: c.execute("DELETE FROM acquisition_publication_jobs WHERE canonical_job_id='job-a'"))
        self.assertEqual(app.get_personalized_job_detail('user-a', job_id)['title'], 'Engineer')

    def test_external_jobs_paginate_without_losing_older_imports(self):
        app = self._backend()
        from backend.application.external_jobs import build_row
        store = app.repositories.personalized_jobs_store
        for index in range(27):
            url = f'https://example.com/jobs/{index}'
            row = build_row('user-a', url, {'title': f'Engineer {index}', 'company': 'Example',
                'location': 'Berlin', 'description': DESCRIPTION})
            store.save_external_job_row('user-a', url, row)
        first = app.list_external_jobs('user-a')
        self.assertEqual(first['total'], 27)
        self.assertEqual(len(first['jobs']), 25)
        second = app.list_external_jobs('user-a', cursor=first['next_cursor'])
        self.assertEqual(len(second['jobs']), 2)
        self.assertIsNone(second['next_cursor'])
        self.assertEqual(len({job['canonical_job_id'] for job in first['jobs'] + second['jobs']}), 27)

    def test_blocked_fetch_returns_editable_fields_and_no_job(self):
        app = self._backend()
        with patch('backend.application.external_jobs.fetch_job_page', side_effect=OSError('blocked')):
            result = app.import_personalized_job('user-a', {'url': URL})
        self.assertEqual(result['state'], 'manual_required')
        self.assertEqual(result['fields']['url'], URL)
        self.assertNotIn('job', result)

    def test_jsonld_scrape_and_enrichment_share_catalog_projection(self):
        app = self._backend()
        html = '<script type="application/ld+json">' + json.dumps({
            '@type': 'JobPosting', 'title': 'Software Engineer', 'description': DESCRIPTION,
            'hiringOrganization': {'name': 'Example'}, 'employmentType': 'FULL_TIME',
        }) + '</script>'
        def enriched(row, generate):
            return {'filters': {'employment_type': 'full_time', 'experience_level': ['mid'],
                                'work_arrangement': ['onsite'], 'roles': ['Software Engineer']},
                    'description': {'state': 'available', 'prompt_version': 'runr_description_nemo_v3',
                                    'summary': {'overview': 'Build reliable software.',
                                                'responsibilities': [{'text': 'Build software', 'source_excerpt': 'Build software'}]},
                                    'structured_description': {}, 'provider': 'openrouter'}}
        with patch('backend.application.external_jobs.fetch_job_page', return_value=html), \
             patch('backend.application.external_jobs.enrich_version', side_effect=enriched):
            result = app.import_personalized_job('user-a', {'url': URL})
        detail = app.get_personalized_job_detail('user-a', result['job']['canonical_job_id'])
        self.assertEqual(detail['employment_type'], 'full_time')
        self.assertEqual(detail['experience_level'], 'mid')
        self.assertEqual(detail['work_arrangement'], 'onsite')
        self.assertEqual(detail['runr_summary']['overview'], 'Build reliable software.')
        self.assertEqual(detail['description_intelligence']['state'], 'available')

    def test_url_rejects_local_targets_and_credentials(self):
        app = self._backend()
        for url in ('http://127.0.0.1/job', 'http://169.254.169.254/job',
                    'file:///etc/passwd', 'https://user:secret@example.com/job'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                app.import_personalized_job('user-a', {'url': url})

    def test_real_enrichment_validates_provider_evidence(self):
        app = self._backend()
        def generate(prompt, **kwargs):
            if 'Classify each' in prompt:
                # The input identity is supplied by the real import row, not the provider.
                import re
                job_id = re.search(r'"id":\s*"(import_[^"]+)"', prompt).group(1)
                return {'jobs': [{'id': job_id, 'collar': 'white', 'roles': ['Software Engineer'],
                                  'evidence': 'Software Engineer', 'employment_type': 'full_time',
                                  'employment_evidence': 'full-time', 'experience_level': 'mid',
                                  'level_evidence': 'mid-level', 'work_arrangement': 'onsite',
                                  'work_arrangement_evidence': 'on-site'}]}
            return {'items': [{'section': 'responsibilities', 'text': 'Build software and maintain reliable services for customers.',
                               'source_ids': ['p2'], 'source_quote': 'Build software and maintain reliable services for customers.'}],
                    'header_candidates': {}, '_runr_model': 'mistralai/mistral-nemo'}
        with patch('backend.application.external_jobs.openrouter_generate', side_effect=generate):
            result = app.import_personalized_job('user-a', {'url': URL, 'manual': True,
                'title': 'Software Engineer', 'company': 'Example', 'description': DESCRIPTION})
        self.assertEqual(result['job']['enrichment_state'], 'available')
        self.assertEqual(result['job']['description_intelligence']['model'], 'mistralai/mistral-nemo')
        self.assertEqual(result['job']['employment_type'], 'full_time')

    def test_repeat_import_reuses_owned_job_without_fetching(self):
        app = self._backend()
        first = app.import_personalized_job('user-a', {'url': URL, 'manual': True,
            'title': 'Software Engineer', 'company': 'Example', 'description': DESCRIPTION})
        with patch('backend.application.external_jobs.fetch_job_page', side_effect=AssertionError('duplicate fetch')):
            second = app.import_personalized_job('user-a', {'url': URL})
        self.assertEqual(first['job']['canonical_job_id'], second['job']['canonical_job_id'])
        self.assertEqual(app.list_external_jobs('user-a')['total'], 1)
