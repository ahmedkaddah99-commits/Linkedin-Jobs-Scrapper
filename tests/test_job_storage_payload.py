from backend.acquisition.storage_payload import compact_job_payload
from backend.acquisition.quality import normalize_job_for_ingestion


def test_successful_linkedin_attempt_does_not_store_another_full_description(tmp_path):
    import json
    from scripts.master_linkedin_jobs_catalog import StateStore
    store = StateStore(tmp_path / "state.db")
    store.record_detail_attempt("run", "123", status="SUCCESS", detail={"description_text": "x" * 10000, "body_hash": "abc"})
    detail = json.loads(store.connection.execute("SELECT detail_json FROM detail_attempts").fetchone()[0])
    assert "description_text" not in detail
    assert detail["body_hash"] == "abc"
    store.connection.close()


def test_page_html_removed_only_after_destination_extracted_and_reprocessing_survives():
    job = {"title": "Engineer", "description": "Build systems", "url": "https://careers.acme.example/jobs/123",
           "source_raw_payload": {"format": "json-ld", "html": '<a href="https://boards.greenhouse.io/acme/jobs/123/apply">Apply</a>', "salaryCustom": 100}}
    target = {"connector": "career_site", "display_name": "Acme", "official_employer_hosts": ["careers.acme.example"]}
    normalized = normalize_job_for_ingestion(job, target)
    compact = compact_job_payload(job, normalized=normalized)
    assert "html" not in compact["source_raw_payload"]
    assert compact["source_raw_payload"]["salaryCustom"] == 100
    reprocessed = normalize_job_for_ingestion(compact, target)
    assert reprocessed["application_url"] == normalized["application_url"]
    assert reprocessed["application_destination"]["candidate_urls"][0]["source_field"] == normalized["application_destination"]["candidate_urls"][0]["source_field"]
    assert compact_job_payload(compact, normalized=normalized) == compact
    assert "html" in compact_job_payload(job)["source_raw_payload"]


def test_unique_source_evidence_and_description_representations_survive():
    fields = {"title": {"raw_value": "Engineer"}}
    job = {"title": "Engineer", "description_html": "<p>Build</p>", "description_text": "Build",
           "unified_mapping": {"fields": fields}, "field_provenance": fields,
           "content_fingerprint": {"description": "Build"},
           "source_raw_payload": {"title": "Engineer", "producer_record": {"title": "Engineer", "company": "Foreign label"},
                                  "observation_contract": {"schema_version": "v1", "source_record": {"title": "Engineer"}, "normalized_mapping": fields}}}
    compact = compact_job_payload(job)
    assert "field_provenance" not in compact and "content_fingerprint" not in compact
    assert compact["source_raw_payload"]["producer_record"] == {"company": "Foreign label"}
    assert compact["source_raw_payload"]["observation_contract"] == {"schema_version": "v1"}
    assert compact["description_html"] == "<p>Build</p>"
    assert "source_record" in job["source_raw_payload"]["observation_contract"]


def test_historical_cleanup_sql_preserves_hashes_descriptions_and_conflicting_evidence():
    import json
    import sqlite3
    from scripts.compact_job_storage import compact_expression
    connection = sqlite3.connect(':memory:')
    payload = {"description_text":"Build", "content_hash":"stable", "content_fingerprint":{"description":"Build"},
               "unified_mapping":{"fields":{"title":"Engineer"}}, "field_provenance":{"title":"Engineer"},
               "source_raw_payload":{"description_text":"Build", "title":"Foreign title", "observation_contract":{"source":"linkedin", "source_record":{"description_text":"Build"}, "normalized_mapping":{}}}}
    connection.execute('CREATE TABLE jobs(payload_json TEXT)')
    connection.execute('INSERT INTO jobs VALUES(?)', (json.dumps(payload),))
    result = json.loads(connection.execute(f'SELECT {compact_expression("payload_json")} FROM jobs').fetchone()[0])
    assert result['content_hash']=='stable' and result['description_text']=='Build'
    assert 'content_fingerprint' not in result and 'field_provenance' not in result
    assert result['source_raw_payload']['title']=='Foreign title'
    assert result['source_raw_payload']['observation_contract']=={'source':'linkedin'}
    connection.close()


def test_original_source_record_survives_when_projection_overwrote_values():
    import json
    import sqlite3
    from scripts.compact_job_storage import compact_expression
    job = {'title':'Projected', 'source_raw_payload':{'observation_contract':{'source_record':{'title':'Original'}, 'normalized_mapping':{'fields':{}}}}}
    assert compact_job_payload(job)['source_raw_payload']['observation_contract']['source_record']=={'title':'Original'}
    connection = sqlite3.connect(':memory:')
    connection.execute('CREATE TABLE jobs(payload_json TEXT)')
    connection.execute('INSERT INTO jobs VALUES(?)', (json.dumps(job),))
    compact = json.loads(connection.execute(f'SELECT {compact_expression("payload_json")} FROM jobs').fetchone()[0])
    assert compact['source_raw_payload']['observation_contract']['source_record']=={'title':'Original'}
    connection.close()
