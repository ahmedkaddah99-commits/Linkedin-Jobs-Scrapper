import json
import pytest

from backend.application.employer_acquisition_policy import excluded_company_ids
from backend.application.source_eligibility_manifest import validate_manifest_for_source, SCHEMA_VERSION


def test_exclusion_survives_new_manifests_and_applies_to_both_sources(tmp_path, monkeypatch):
    policy = tmp_path / 'policy.json'
    policy.write_text(json.dumps({'schema_version': 1, 'company_ids': ['blocked']}))
    monkeypatch.setenv('RUNR_EMPLOYER_EXCLUSION_POLICY', str(policy))
    for source in ('linkedin', 'employer_site'):
        tasks = [{'task_key': name, 'canonical_company_id': name, 'source': source,
                  'row_fingerprints': ['evidence'], 'pilot_eligible': True,
                  'organization_associations': [{'linkedin_org_id': '123'}]} for name in ('blocked','allowed')]
        for generation in range(2):
            manifest = {'schema_version': SCHEMA_VERSION, 'generation': generation,
                        'integrity': {'eligible_tasks_have_one_canonical_id': True},
                        'rows': [{'row_fingerprint': 'evidence'}], 'tasks': tasks}
            assert [t['canonical_company_id'] for t in validate_manifest_for_source(manifest, source)] == ['allowed']


def test_explicit_missing_or_invalid_policy_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / 'policy.json'
    monkeypatch.setenv('RUNR_EMPLOYER_EXCLUSION_POLICY', str(path))
    with pytest.raises(FileNotFoundError): excluded_company_ids()
    path.write_text(json.dumps({'schema_version': 1, 'company_ids': 'bad'}))
    with pytest.raises(ValueError): excluded_company_ids()


def test_publisher_blocks_identity_resolved_after_manifest_validation(tmp_path, monkeypatch):
    from scripts.publish_producer_states import _manifest_companies
    path=tmp_path/'policy.json'
    path.write_text(json.dumps({'schema_version':1,'company_ids':['blocked']}))
    monkeypatch.setenv('RUNR_EMPLOYER_EXCLUSION_POLICY',str(path))
    task={'task_key':'alias','canonical_company_id':'alias','source':'employer_site',
          'row_fingerprints':['row'],'pilot_eligible':True}
    manifest={'schema_version':SCHEMA_VERSION,'integrity':{'eligible_tasks_have_one_canonical_id':True},
              'rows':[{'row_fingerprint':'row','canonical_company_id':'alias'}],'tasks':[task]}
    assert _manifest_companies(manifest,'employer_site',pilot_only=False,crosswalk={'old-company:alias':'blocked'})=={}


def test_publication_gate_rejects_excluded_employer_even_with_completeness_disabled(tmp_path, monkeypatch):
    from backend.repositories.sqlite_acquisition import SqliteAcquisitionStore
    from backend.acquisition.publication import get_publication_policy
    path=tmp_path/'policy.json'
    path.write_text(json.dumps({'schema_version':1,'company_ids':['blocked']}))
    monkeypatch.setenv('RUNR_EMPLOYER_EXCLUSION_POLICY',str(path))
    snapshot,rejected=SqliteAcquisitionStore._publication_rows_with_completeness(
        [{'canonical_job_id':'job','company_id':'blocked','title':'Engineer'}],
        policy=get_publication_policy('publication_policy_v1'),validate_completeness=False)
    assert snapshot==[]
    assert rejected[0]['reasons'][0]['code']=='owner_excluded_employer'
