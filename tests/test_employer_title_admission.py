"""Source wording must not bypass the validated function/publication decision."""
import json

import pytest

from backend.acquisition.employer_focus import (
    SCOPE_VERSION, review_title_candidate, scope_reason, publication_reason,
)


@pytest.mark.parametrize('title', [
    'Junior Product Line Manager Kids Footwear',
    'Customer Service Representative', 'Planner E-Commerce Europe',
    'Manager Mobility Fleet', 'Referent Unternehmenssteuerung',
    'Commercial Enablement Associate', 'Business Process Owner',
    'HR Business Partner', 'Marketing Manager', 'Software Engineer',
    'Unfamiliar Function With No Known Keywords',
])
def test_unknown_titles_reach_classification(title):
    assert review_title_candidate(title)
    payload = {'country': 'DE', 'employer_focus': {'scope_version': SCOPE_VERSION}}
    assert scope_reason({'title': title, 'version_payload_json': json.dumps(payload)}) == ''


@pytest.mark.parametrize('title', [
    '', '  ', 'Intern Product Line Management', 'Working Student Business Analyst',
    'Pflichtpraktikum Global Operations', 'Ausbildung Kaufmann',
])
def test_explicit_student_contracts_and_empty_titles_stay_excluded(title):
    assert not review_title_candidate(title)


def test_admission_does_not_expand_validated_business_or_experience_scope():
    args = dict(filters_hash='h', description_hash='h', content_hash='h', description_ready=True)
    for role in ['Product Manager', 'Customer Service Representative', 'Operations Analyst']:
        filters = {'collar': 'white', 'roles': [role], 'required_experience_years': 1}
        assert publication_reason(filters, **args) == ''
        assert publication_reason({**filters, 'required_experience_years': 3}, **args) == 'employer_focus_required_experience_over_two'
    for role in ['Software Engineer', 'HR Business Partner', 'Brand Manager']:
        assert publication_reason({'collar': 'white', 'roles': [role]}, **args) == 'employer_focus_business_classification_unconfirmed'
    assert publication_reason({'collar': 'blue', 'roles': []}, **args) == 'employer_focus_business_classification_unconfirmed'


def test_recurring_collector_fetches_unfamiliar_titles_before_function_review(tmp_path):
    from scripts.workbook_employer_dry_run import collect
    from tests.test_workbook_employer_dry_run import company, response, puma_detail_html
    titles = ['Junior Product Line Manager Kids Footwear', 'Customer Service Representative',
              'Planner E-Commerce Europe', 'Unfamiliar Commercial Function']
    detail_requests = []

    class Transport:
        def request(self, url, **kw):
            if url.endswith('/dd_job_search'):
                return response(url, {'hits': {'total': {'value': len(titles), 'relation': 'eq'}, 'hits': [
                    {'_source': {'title': title, 'url': f'/en/jobs/role-r{i}', 'is_retail': 0,
                                 'location_tids': ['298']}} for i, title in enumerate(titles)]}})
            if '/en/jobs/' in url:
                i = int(url.rsplit('r', 1)[1]); detail_requests.append(i)
                return response(url, puma_detail_html(i).replace(f'Product Manager {i}', titles[i]))
            return response(url, '<div id="dd-job-search"></div>')

    row = {**company(), 'career_url': 'https://about.puma.com/en/careers/job-openings?area=corporate&location=298',
           'api_endpoint': 'https://about.puma.com/dd_job_search', '_business_candidates_only': True}
    result, jobs = collect(row, Transport(), tmp_path)
    assert result['status'] == 'complete'
    assert sorted(detail_requests) == list(range(len(titles)))
    assert {j['title'] for j in jobs} == set(titles)
