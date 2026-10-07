import json
import tempfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from backend.application.profile_job_matching import (
    FEATURE_VERSION, build_job_facts, evaluate_profile_match, profile_snapshot, union_years,
)
from backend.bootstrap import create_backend
from backend.domain.models import UserRecord, utc_now_iso
from tests.test_phase_c_personalized_jobs import _seed_catalog


def snapshot(**profile):
    return profile_snapshot(SimpleNamespace(metadata={"profile": profile}))


def facts(**extra):
    return {"version": FEATURE_VERSION, "skills": [
        {"name": "SQL", "requiredness": "required", "job_evidence": "SQL required"},
        {"name": "Python", "requiredness": "preferred", "job_evidence": "Python preferred"}],
        "title": "Data Analyst", "roles": ["Data Analyst"], "levels": ["entry"],
        "years_min": 2, "industries": ["Insurance"], "posting_version": "version-job-a", **extra}


def test_profile_hash_ignores_cv_preferences_and_identity():
    a = SimpleNamespace(metadata={"profile": {"competencies": ["SQL"], "cv_hash": "a", "email": "one"}, "documents": {"cv": "a"}})
    b = SimpleNamespace(metadata={"profile": {"competencies": ["SQL"], "cv_hash": "b", "email": "two"}, "documents": {"cv": "b"}, "preferences": {"target_roles": ["Python"]}})
    assert profile_snapshot(a) == profile_snapshot(b)
    b.metadata['profile']['competencies'] = ['Python']
    assert profile_snapshot(a) != profile_snapshot(b)


def test_required_preferred_aliases_and_no_substring_false_positive():
    result = evaluate_profile_match(facts(), snapshot(competencies=['SQL'], industry='Versicherung'))
    assert result['dimensions']['skill']['score'] == 67
    assert result['dimensions']['industry_experience']['score'] == 100
    assert result['dimensions']['experience_level']['score'] is None
    assert result['state'] == 'partial'
    assert evaluate_profile_match(facts(), snapshot(competencies=['MySQL']))['dimensions']['skill']['score'] == 0
    assert evaluate_profile_match(facts(), snapshot(competencies=['No SQL experience']))['dimensions']['skill']['score'] == 0


def test_dates_overlap_and_relevant_experience():
    profile = snapshot(competencies=['SQL', 'Python'], industry='Insurance', recent_experience=[
        {'title': 'Data Analyst', 'start_date': '2022-01', 'end_date': '2024-01', 'description': 'SQL and Python'},
        {'title': 'Data Analyst', 'start_date': '2023-01', 'end_date': '2025-01', 'description': 'SQL'},
        {'title': 'Chef', 'start_date': '2010-01', 'end_date': '2020-01'}])
    result = evaluate_profile_match(facts(), profile, today=date(2026, 10, 7))
    assert result['dimensions']['experience_level']['relevant_years'] == 3
    assert result['score'] == 100
    assert union_years([(1, 25), (13, 37)]) == 3


def test_unknown_dates_do_not_make_up_years_or_zero_scores():
    result = evaluate_profile_match(facts(), snapshot(recent_experience=[{'title': 'Data Analyst'}]))
    assert result['dimensions']['experience_level']['score'] is None
    assert result['dimensions']['industry_experience']['score'] is None
    assert evaluate_profile_match(None, snapshot(skills=['SQL']))['state'] == 'pending'
    assert evaluate_profile_match(facts(), snapshot())['state'] == 'needs_profile'


def test_source_supported_facts_and_alternative_levels():
    row = {'version_id': 'v', 'content_hash': 'h', 'title': 'Analyst', 'description': 'SQL required. Python preferred.',
           'summary_json': json.dumps({'required_qualifications': [{'text': 'SQL required'}], 'preferred_qualifications': [{'text': 'Python preferred'}]}),
           'filters_json': json.dumps({'skills': ['SQL', 'Python', 'Invented'], 'required_experience_years': 2, 'experience_level': ['entry', 'mid']})}
    result = build_job_facts(row)
    assert result['years_min'] == 2
    assert result['levels'] == ['entry', 'mid']
    assert [(s['name'], s['requiredness']) for s in result['skills']] == [('Python', 'preferred'), ('SQL', 'required')]


def test_saved_profile_dates_and_industry_survive_settings_merge():
    from backend.api.server import _merge_profile_metadata
    user = UserRecord(user_id='u', email='u@example.test')
    raw = {'recent_experience': [{'title': 'Analyst', 'start_date': '2022-01', 'end_date': 'Present', 'description': 'SQL reporting', 'industry': 'Insurance'}]}
    saved = _merge_profile_metadata({}, raw, user)
    reloaded = _merge_profile_metadata(saved, {}, user)
    for key in ('start_date', 'end_date', 'description', 'industry'):
        assert reloaded['recent_experience'][0][key] == raw['recent_experience'][0][key]


def test_feed_detail_user_isolation_profile_edits_and_stale_features():
    with tempfile.TemporaryDirectory() as directory:
        app = create_backend(Path(directory), storage_backend='sqlite', test_mode=True)
        _seed_catalog(app)
        store = app.repositories.personalized_jobs_store
        for uid, skills in [('one', ['SQL']), ('two', ['Python'])]:
            app.repositories.auth_repository.upsert_user(UserRecord(user_id=uid, email=uid+'@example.test', metadata={'profile': {'competencies': skills}}))
        def write(connection):
            connection.execute('INSERT INTO profile_job_facts VALUES (?,?,?,?,?,?,?)',
                               ('version-job-a', 'job-a', 'hash-job-a', FEATURE_VERSION, '||', json.dumps(facts()), utc_now_iso()))
        store._run_transaction(write)
        service = app._personalized_jobs_service
        one = next(j for j in service.feed('one', card_view=True)['jobs'] if j['posting_id'] == 'job-a')['match_intelligence']
        two = service.detail('two', 'job-a')['match_intelligence']
        assert one['score'] == 67
        assert two['dimensions']['skill']['score'] == 33
        assert service.detail('one', 'job-a')['match_intelligence']['score'] == one['score']
        user = app.repositories.auth_repository.get_user('one')
        user.metadata['profile']['competencies'] = ['SQL', 'Python']
        app.repositories.auth_repository.upsert_user(user)
        assert service.detail('one', 'job-a')['match_intelligence']['dimensions']['skill']['score'] == 100
        store._run_transaction(lambda c: c.execute("UPDATE profile_job_facts SET content_hash='stale'"))
        assert service.detail('one', 'job-a')['match_intelligence']['state'] == 'pending'


def test_acquisition_queue_races_cannot_publish_or_acknowledge_old_facts(monkeypatch):
    import io
    from scripts import process_profile_job_facts as worker
    with tempfile.TemporaryDirectory() as directory:
        app = create_backend(Path(directory), storage_backend='sqlite', test_mode=True)
        _seed_catalog(app)
        store = app.repositories.personalized_jobs_store
        row = {'canonical_job_id': 'job-a', 'version_id': 'version-job-a', 'content_hash': 'hash-job-a',
               'title': 'Operations Analyst', 'description': 'SQL required', 'input_signature': '||', 'queued_revision': 1}
        monkeypatch.setattr(worker, 'os', SimpleNamespace(environ={
            'TURSO_DATABASE_URL': 'libsql://fixture.invalid', 'TURSO_AUTH_TOKEN': 'fixture-only'}))
        def transport(request, timeout):
            results = []
            def execute_requests(connection):
                for item in json.loads(request.data)['requests']:
                    if item['type'] == 'close':
                        results.append({'type': 'ok', 'response': {}})
                        continue
                    args = [a['value'] for a in item['stmt']['args']]
                    cursor = connection.execute(item['stmt']['sql'], args)
                    results.append({'type': 'ok', 'response': {'result': {'affected_row_count': cursor.rowcount}}})
            store._run_transaction(execute_requests)
            return io.BytesIO(json.dumps({'results': results}).encode())
        monkeypatch.setattr(worker, 'urlopen', transport)
        store._run_transaction(lambda c: c.execute("UPDATE profile_job_fact_queue SET revision=2 WHERE version_id='version-job-a'"))
        assert worker.write_batch([row]) == 0
        assert store.list_profile_job_facts(['version-job-a']) == {}
        row['queued_revision'] = 2
        assert worker.write_batch([row]) == 1
        assert 'version-job-a' in store.list_profile_job_facts(['version-job-a'])
        def add_filters(c):
            c.execute('INSERT INTO job_filter_intelligence VALUES(?,?,?,?,?,?,?)',
                      ('version-job-a', 'job-a', 'hash-job-a', '{}', 'fixture', 'fixture', 'changed'))
        store._run_transaction(add_filters)
        assert store.list_profile_job_facts(['version-job-a']) == {}
        with store._connect() as connection:
            assert connection.execute("SELECT revision FROM profile_job_fact_queue WHERE version_id='version-job-a'").fetchone() is not None
