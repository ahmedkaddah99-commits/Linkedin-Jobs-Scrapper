"""Authenticated VPS smoke test; removes its users, tokens, postings and HTML."""
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from backend.bootstrap import create_backend
from backend.database.connection import database_session
from backend.domain.models import UserRecord, utc_plus_seconds


def main():
    app = create_backend(Path(os.environ['RUNR_DATA_DIR']), storage_backend='sqlite')
    suffix = uuid4().hex[:12]
    user_ids = [f'external_probe_{suffix}', f'external_probe_other_{suffix}']
    probe = Path('frontend/dist') / f'external-import-probe-{suffix}.html'
    url = f'https://app.userunr.com/{probe.name}'
    description = ('Responsibilities\nBuild Python software and maintain reliable customer services.\n'
                   'Improve testing and collaborate with the engineering team on production systems.\n'
                   'Requirements\nThree years of software engineering experience and Python skills are required.\n'
                   'This is a full-time mid-level position working on-site in Berlin.\n'
                   'Benefits\nPaid leave and a professional development budget.\n'
                   'Application details\nSubmit your CV using the employer application link.')
    results = {}
    def request(token, method, path, body=None):
        payload = json.dumps(body).encode() if body is not None else None
        req = Request('https://app.userunr.com/v1' + path, data=payload, method=method,
                      headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        try:
            with urlopen(req, timeout=115) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)
    try:
        tokens = []
        for user_id in user_ids:
            app.upsert_user(UserRecord(user_id=user_id, email=user_id + '@example.invalid', role='admin'))
            _, token = app.issue_api_token(user_id=user_id, name='temporary external import verification', expires_at=utc_plus_seconds(600))
            tokens.append(token)
        posting = {'@context': 'https://schema.org', '@type': 'JobPosting', 'title': 'Software Engineer',
                   'hiringOrganization': {'@type': 'Organization', 'name': 'Runr Deployment Verification'},
                   'description': description, 'employmentType': 'FULL_TIME',
                   'jobLocation': {'@type': 'Place', 'address': {'addressLocality': 'Berlin', 'addressCountry': 'DE'}}}
        probe.write_text('<html><head><meta name="robots" content="noindex,nofollow">'
                         '<script type="application/ld+json">' + json.dumps(posting) + '</script></head>'
                         '<body><h1>Software Engineer</h1><p>Temporary deployment verification posting.</p></body></html>')
        status, imported = request(tokens[0], 'POST', '/personalized-jobs/import', {'url': url})
        assert status == 200 and imported.get('job'), ('import', status, imported)
        job = imported['job']
        assert job['enrichment_state'] == 'available', ('enrichment', job.get('enrichment_state'))
        assert job['description_intelligence']['model'] == 'mistralai/mistral-nemo', job['description_intelligence']
        assert job['employment_type'] == 'full_time', job['employment_type']
        assert job['experience_level'] == 'mid', job['experience_level']
        assert job['work_arrangement'] == 'onsite', job['work_arrangement']
        job_id = job['canonical_job_id']
        status, detail = request(tokens[0], 'GET', '/personalized-jobs/' + job_id)
        assert status == 200 and detail['original_posting']['description_text'] == description
        status, _ = request(tokens[1], 'GET', '/personalized-jobs/' + job_id)
        assert status == 404, ('ownership', status)
        status, saved = request(tokens[0], 'POST', '/personalized-jobs/' + job_id + '/save', {})
        assert status == 200 and saved['state'] == 'saved', ('save', status)
        status, listing = request(tokens[0], 'GET', '/personalized-jobs/external')
        assert status == 200 and listing['jobs'][0]['canonical_job_id'] == job_id
        for flags in ({'preview': True}, {'manual': True}):
            status, duplicate = request(tokens[0], 'POST', '/personalized-jobs/import', {'url': url, **flags})
            assert status == 200 and duplicate['reason'] == 'already_added', ('private duplicate', status, duplicate)
        store = app.repositories.personalized_jobs_store
        with store._connect() as connection:
            published = connection.execute(store._published_jobs_sql() + " AND j.canonical_url<>'' LIMIT 1",
                                           (store._head_publication_id(connection),)).fetchone()
        assert published is not None, 'A published job is required for the duplicate smoke check'
        for flags in ({'preview': True}, {'manual': True}):
            status, duplicate = request(tokens[0], 'POST', '/personalized-jobs/import', {'url': published['canonical_url'], **flags})
            assert status == 200 and duplicate['reason'] == 'already_published', ('published duplicate', status, duplicate)
        status, fallback = request(tokens[0], 'POST', '/personalized-jobs/import', {'url': 'https://example.com/'})
        assert status == 200 and fallback['state'] == 'manual_required', ('non-job', status, fallback)
        status, manual = request(tokens[0], 'POST', '/personalized-jobs/import', {
            'url': 'https://example.com/manual-' + suffix, 'manual': True, 'title': 'Software Engineer',
            'company': 'Runr Deployment Verification', 'location': 'Berlin', 'description': description})
        assert status == 200 and manual.get('job'), ('manual', status)
        status, _ = request(tokens[0], 'POST', '/quick-apply/runs', {})
        assert status == 404, ('retired endpoint', status)
        siemens_url = 'https://jobs.siemens.com/en_US/externaljobs/JobDetail/524459'
        status, preview = request(tokens[0], 'POST', '/personalized-jobs/import', {'url': siemens_url, 'preview': True})
        assert status == 200 and preview['state'] == 'review_required', ('preview', status)
        fields = preview['fields']
        assert fields['title'].startswith('Advanced Digital Engineer'), ('title', fields['title'])
        assert fields['company'] == 'Siemens AG', ('company', fields['company'])
        assert 'Erlangen' in fields['location'], ('location', fields['location'])
        assert fields['employment_type'] == 'full_time', ('type', fields['employment_type'])
        assert fields['experience_level'] == 'mid', ('level', fields['experience_level'])
        assert fields['work_arrangement'] == 'onsite', ('work', fields['work_arrangement'])
        assert preview['message'] == '', ('unexpected warning', preview['message'])
        status, confirmed = request(tokens[0], 'POST', '/personalized-jobs/import', {**fields, 'manual': True})
        assert status == 200 and confirmed.get('job'), ('confirmation', status)
        assert confirmed['job']['description_intelligence']['model'] == 'mistralai/mistral-nemo'
        results = {'state': 'passed', 'scrape': 'passed', 'nemo_enrichment': 'passed',
                   'duplicate_private_and_published_urls': 'passed',
                   'siemens_ai_preview_and_confirmation': 'passed',
                   'shared_reader_api': 'passed', 'owner_isolation': 'passed', 'save': 'passed',
                   'external_list': 'passed', 'non_job_fallback': 'passed', 'manual_completion': 'passed',
                   'quick_apply_retired': 'passed', 'release': os.getenv('RUNR_RELEASE_COMMIT')}
    finally:
        probe.unlink(missing_ok=True)
        with database_session(Path(os.environ['RUNR_DATA_DIR']) / 'backend.sqlite3') as connection:
            def cleanup(c):
                for table in ('external_jobs', 'external_job_import_attempts', 'personalized_job_dispositions',
                              'personalized_job_events', 'api_tokens', 'users'):
                    c.execute(f'DELETE FROM {table} WHERE user_id IN (?,?)', tuple(user_ids))
            connection.transaction(cleanup)
        results['temporary_data_removed'] = True
    print(json.dumps(results, sort_keys=True))


if __name__ == '__main__':
    main()
