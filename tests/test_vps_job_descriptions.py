import json
import pytest
import sqlite3
from pathlib import Path

from backend.application.vps_job_descriptions import build_pilot_description, build_runr_description, build_runr_description_rules, build_runr_descriptions, openrouter_generate
from backend.bootstrap import create_backend
from backend.repositories.sqlite_personalized_jobs import SqlitePersonalizedJobsStore
from scripts.process_published_job_descriptions import next_batch, run, save_batch
from scripts.backfill_published_job_descriptions_rules import run_rules_backfill
from test_phase_c_personalized_jobs import _seed_catalog


def test_pilot_accepts_multiple_sections_per_source_and_hides_invalid_numeric_output():
    row = {"current_version_id": "v2", "description": "Build reports. We would like Excel experience. Minimum one year experience."}
    result = build_pilot_description(row, lambda _: {
        "items": [
            {"section": "responsibilities", "text": "Build reports.", "source_ids": ["p1"]},
            {"section": "preferred_qualifications", "text": "Excel experience.", "source_ids": ["p1"]},
        ],
        "header_candidates": {"experience_years_min": {"value": "1", "source_ids": ["p1"]}},
    })
    assert result["prompt_version"] == "runr_description_nemo_v2"
    assert len(result["summary"]["responsibilities"]) == 1
    assert len(result["summary"]["preferred_qualifications"]) == 1
    assert result["structured_description"]["experience_years_min"] is None
    assert "experience_years_min:invalid_output" in result["structured_description"]["rejected_fields"]


def test_pilot_reanchors_stated_years_and_hides_invented_or_alternative_years():
    source = "Qualifications:\nA degree in engineering.\nAt least 5 years of engineering experience."
    result = build_pilot_description({"description": source}, lambda _: {
        "items": [], "header_candidates": {"experience_years_min": {"value": 5, "source_ids": ["p2"]}},
    })
    assert result["structured_description"]["experience_years_min"]["source_ids"] == ["p3"]

    invented = build_pilot_description({"description": "Qualifications:\nHands-on Salesforce experience."}, lambda _: {
        "items": [], "header_candidates": {"experience_years_min": {"value": 1, "source_ids": ["p2"]}},
    })
    assert invented["structured_description"]["experience_years_min"] is None

    alternative = build_pilot_description({"description": "3-4 years of professional experience or a minimum of 2 years transferable recruiting experience."}, lambda _: {
        "items": [], "header_candidates": {"experience_years_min": {"value": 3, "source_ids": ["p1"]}},
    })
    assert alternative["structured_description"]["experience_years_min"] is None

    bounded = build_pilot_description({"description": "2-5 years of experience selling crop protection, seed or agronomy services."}, lambda _: {
        "items": [], "header_candidates": {"experience_years_min": {"value": 2, "source_ids": ["p1"]}},
    })
    assert bounded["structured_description"]["experience_years_min"]["value"] == 2

    wrapped = build_pilot_description({"description": "Qualifications:\n5+ years\nof experience in IT security."}, lambda _: {
        "items": [], "header_candidates": {"experience_years_min": {"value": 5, "source_ids": ["p2"]}},
    })
    assert wrapped["structured_description"]["experience_years_min"]["source_ids"] == ["p2", "p3"]


def test_pilot_recovers_omitted_explicit_qualification_lists_without_legal_text():
    row = {"description": "Responsibilities\nBuild reports.\nQualifications:\nDegree required.\nPreferred Additional Skills:\nSQL is a plus.\nAcme is an Equal Opportunity Employer."}
    result = build_pilot_description(row, lambda _: {
        "items": [{"section": "responsibilities", "text": "Build reports.", "source_ids": ["p2"]}],
        "header_candidates": {},
    })
    assert [item["text"] for item in result["summary"]["required_qualifications"]] == ["Degree required."]
    assert [item["text"] for item in result["summary"]["preferred_qualifications"]] == ["SQL is a plus."]
    assert result["structured_description"]["supplemented_sections"] == ["required_qualifications", "preferred_qualifications"]


def test_pilot_recovers_alternative_employer_headings_when_model_stops_after_duties():
    row = {"description": "Main responsibilities:\nBuild reports.\nWhat we are looking for\nAt least 5 years of experience.\nKnowledge of Valmet DNA is preferred.\nAdditional requirements\nWillingness to travel.\nWhy join Valmet?\nCompany marketing.\nWe offer:\nTechnical training.\nWhat will help you succeed\nCompany values."}
    result = build_pilot_description(row, lambda _: {
        "items": [{"section": "responsibilities", "text": "Build reports.", "source_ids": ["p2"]}],
        "header_candidates": {},
    })
    assert [item["text"] for item in result["summary"]["required_qualifications"]] == ["At least 5 years of experience.", "Willingness to travel."]
    assert [item["text"] for item in result["summary"]["preferred_qualifications"]] == ["Knowledge of Valmet DNA is preferred."]
    assert [item["text"] for item in result["summary"]["benefits"]] == ["Technical training."]


def test_pilot_recovers_required_preferred_and_named_benefits():
    row = {"description": "Person Specification:\nRequired:\n3+ years of pricing experience.\nPreferred:\nGLM experience.\nWhat Hiscox USA Offers:\nHealth insurance.\nAbout Hiscox USA:\nCompany marketing."}
    result = build_pilot_description(row, lambda _: {"items": [], "header_candidates": {}})
    assert [item["text"] for item in result["summary"]["required_qualifications"]] == ["3+ years of pricing experience."]
    assert [item["text"] for item in result["summary"]["preferred_qualifications"]] == ["GLM experience."]
    assert [item["text"] for item in result["summary"]["benefits"]] == ["Health insurance."]


def test_pilot_recovers_candidate_and_job_qualification_headings():
    row = {"description": "As a Senior GIS Specialist you will:\nMake maps.\nThe successful candidate will:\nHave a GIS degree.\nBenefits:\nPaid leave.\nJob Responsibilities:**\nLead a shift.\nJob Qualifications:**\n3+ years in production."}
    result = build_pilot_description(row, lambda _: {"items": [], "header_candidates": {}})
    assert [item["text"] for item in result["summary"]["responsibilities"]] == ["Make maps.", "Lead a shift."]
    assert [item["text"] for item in result["summary"]["required_qualifications"]] == ["Have a GIS degree.", "3+ years in production."]


def test_pilot_recovers_benefits_after_different_employer_headings():
    row = {"description": "WHAT YOU BRING ALONG\nMust-have skills:\nApex experience.\nNice-to-have skills:\nJira experience.\nWHAT WE HAVE TO OFFER\nProfessional & Personal Growth:\nFree training.\nWHAT WE VALUE\nCompany values."}
    result = build_pilot_description(row, lambda _: {"items": [], "header_candidates": {}})
    assert [item["text"] for item in result["summary"]["required_qualifications"]] == ["Apex experience."]
    assert [item["text"] for item in result["summary"]["preferred_qualifications"]] == ["Jira experience."]
    assert [item["text"] for item in result["summary"]["benefits"]] == ["Free training."]


def test_pilot_fallback_splits_mixed_preferences_and_joins_wrapped_lines():
    row = {"description": "Job Qualifications:**\nHands-on DCS experience; knowledge of DNAe is preferred.\n3+ years of pricing experience, preferably in commercial lines.\nHave practical GIS experience and ideally within the energy sector\nHave a full UK driving licence\nand willingness to travel to project\nlocations"}
    result = build_pilot_description(row, lambda _: {"items": [], "header_candidates": {}})
    required = [item["text"] for item in result["summary"]["required_qualifications"]]
    preferred = [item["text"] for item in result["summary"]["preferred_qualifications"]]
    assert "Hands-on DCS experience" in required
    assert "3+ years of pricing experience" in required
    assert "Have practical GIS experience" in required
    assert "Have a full UK driving licence and willingness to travel to project locations" in required
    assert "knowledge of DNAe is preferred." in preferred
    assert "Experience in commercial lines is preferred." in preferred
    assert "Experience within the energy sector is preferred." in preferred


def test_pilot_splits_required_and_preferred_wording_in_one_model_item():
    result = build_pilot_description({"description": "Languages: English and German required, additional European language is a plus."}, lambda _: {
        "items": [{"section": "required_qualifications", "text": "English and German required, additional European language is a plus.", "source_ids": ["p1"]}],
        "header_candidates": {},
    })
    assert result["summary"]["required_qualifications"][0]["text"] == "English and German required."
    assert result["summary"]["preferred_qualifications"][0]["text"] == "additional European language is a plus."


def test_pilot_separates_ideal_platform_and_preferred_degree_field():
    result = build_pilot_description({"description": "Qualifications: Core banking experience, ideally with Oracle. Bachelor's degree required (Finance preferred)."}, lambda _: {
        "items": [
            {"section": "required_qualifications", "text": "Core banking experience, ideally with Oracle.", "source_ids": ["p1"]},
            {"section": "required_qualifications", "text": "Bachelor's degree required (Finance preferred).", "source_ids": ["p1"]},
        ],
        "header_candidates": {},
    })
    required = [item["text"] for item in result["summary"]["required_qualifications"]]
    preferred = [item["text"] for item in result["summary"]["preferred_qualifications"]]
    assert "Core banking experience." in required
    assert "Bachelor's degree required." in required
    assert "Ideally, experience with Oracle." in preferred
    assert "Degree in Finance preferred." in preferred


def test_pilot_recovers_salary_only_with_explicit_currency_and_period():
    result = build_pilot_description({"description": "Responsibilities\nBuild reports.\nPay ranges from $24.00 to $43.00 per hour."}, lambda _: {
        "items": [{"section": "responsibilities", "text": "Build reports.", "source_ids": ["p2"]}],
        "header_candidates": {"salary": {"min": 24, "max": 43, "currency": "USD", "period": "hour"}},
    })
    assert result["structured_description"]["salary"]["value"] == {"min": 24.0, "max": 43.0, "currency": "USD", "period": "hour"}
    assert result["structured_description"]["salary"]["source_ids"] == ["p3"]


def test_builds_shared_english_description_from_german_posting():
    row = {
        "current_version_id": "version-1",
        "canonical_job_id": "job-1",
        "content_hash": "hash-1",
        "description": "Aufgaben: Betreuung der Kundschaft. Voraussetzung: Deutsch C1.",
    }
    captured = []

    def generate(prompt):
        captured.append(prompt)
        return {
            "source_language": "de",
            "overview": "Support customers in German.",
            "responsibilities": [{"text": "Support customers", "source_excerpt": "Betreuung der Kundschaft"}],
            "required_qualifications": [{"text": "German C1", "source_excerpt": "Deutsch C1"}],
            "preferred_qualifications": [],
            "benefits": [],
            "application_details": [],
        }

    result = build_runr_description(row, generate)

    assert row["description"] in captured[0]
    assert result["summary"]["source_language"] == "de"
    assert result["summary"]["required_qualifications"][0]["source_excerpt"] == "Deutsch C1"
    assert result["original_posting"]["description_text"] == row["description"]
    assert result["version_id"] == "version-1"


def test_rule_pass_organizes_german_posting_without_rewriting_its_conditions():
    row = {
        "current_version_id": "version-de", "canonical_job_id": "job-de", "content_hash": "hash-de",
        "description": "Unterstützung im Betrieb.\nAufgaben:\n- Produktionssysteme überwachen\nAnforderungen:\n- Deutsch C1\nVon Vorteil:\n- Grafana\nWas wir bieten:\n- Homeoffice",
    }
    result = build_runr_description_rules(row)
    summary = result["summary"]
    assert result["provider"] == "runr_rules"
    assert summary["output_language"] == "de"
    assert summary["overview"] == "Unterstützung im Betrieb."
    assert summary["responsibilities"] == [{"text": "Produktionssysteme überwachen", "source_excerpt": "Produktionssysteme überwachen"}]
    assert summary["required_qualifications"][0]["text"] == "Deutsch C1"
    assert summary["preferred_qualifications"][0]["text"] == "Grafana"
    assert summary["benefits"][0]["text"] == "Homeoffice"
    assert result["original_posting"]["description_text"] == row["description"]


def test_rejects_incomplete_model_response_without_writing_fallback():
    with pytest.raises(ValueError, match="missing field"):
        build_runr_description({"description": "A full job posting"}, lambda _: {"overview": "A job"})


def test_rejects_paid_model_before_sending_request(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("RUNR_DESCRIPTION_MODEL", "nvidia/nemotron-3-super-120b-a12b")
    with pytest.raises(ValueError, match="free-tier"):
        openrouter_generate("test prompt")


def test_batch_keeps_each_result_with_its_posting_version():
    rows = [
        {"canonical_job_id": "a", "current_version_id": "v-a", "description": "Build reports"},
        {"canonical_job_id": "b", "current_version_id": "v-b", "description": "Kunden betreuen"},
    ]
    def generate(prompt):
        assert "Build reports" in prompt and "Kunden betreuen" in prompt
        return {"jobs": [
            {"id": "v-a", "source_language": "en", "overview": "Build reports", "responsibilities": [], "required_qualifications": [], "preferred_qualifications": [], "benefits": [], "application_details": []},
            {"id": "v-b", "source_language": "de", "overview": "Support customers", "responsibilities": [], "required_qualifications": [], "preferred_qualifications": [], "benefits": [], "application_details": []},
        ]}

    result = build_runr_descriptions(rows, generate)
    assert [item["version_id"] for item in result] == ["v-a", "v-b"]
    assert result[1]["summary"]["source_language"] == "de"


def test_backfill_selects_only_current_unprocessed_published_versions(tmp_path: Path):
    db = tmp_path / "catalog.db"
    with sqlite3.connect(db) as connection:
        connection.executescript("""
            CREATE TABLE acquisition_publication_head (head_id INTEGER, publication_id TEXT);
            CREATE TABLE acquisition_publication_jobs (publication_id TEXT, canonical_job_id TEXT);
            CREATE TABLE canonical_jobs (canonical_job_id TEXT, current_version_id TEXT, title TEXT, canonical_url TEXT);
            CREATE TABLE job_posting_versions (version_id TEXT, version_number INTEGER, content_hash TEXT,
                description TEXT, payload_json TEXT, location TEXT, apply_url TEXT, created_at TEXT);
            CREATE TABLE job_description_intelligence (version_id TEXT, content_hash TEXT, prompt_version TEXT, provider TEXT);
            INSERT INTO acquisition_publication_head VALUES (1, 'publication');
            INSERT INTO acquisition_publication_jobs VALUES ('publication', 'job-a'), ('publication', 'job-b'), ('publication', 'job-c');
            INSERT INTO canonical_jobs VALUES ('job-a', 'v-a', 'A', ''), ('job-b', 'v-b', 'B', ''), ('job-c', 'v-c', 'C', '');
            INSERT INTO job_posting_versions VALUES ('v-a', 1, 'hash-a', 'Description A', '{}', '', '', '2026-09-30');
            INSERT INTO job_posting_versions VALUES ('v-b', 1, 'hash-b', 'Description B', '{}', '', '', '2026-10-01');
            INSERT INTO job_posting_versions VALUES ('v-c', 1, 'hash-c', '', '{}', '', '', '2026-10-02');
            INSERT INTO job_description_intelligence VALUES ('v-a', 'hash-a', 'runr_description_v1', 'openrouter');
        """)
    store = SqlitePersonalizedJobsStore(db, initialize=False)
    assert [row["canonical_job_id"] for row in next_batch(store, "", 10)] == ["job-b"]
    assert [row["canonical_job_id"] for row in next_batch(store, "job-z", 10, newest=True)] == ["job-b"]
    assert next_batch(store, "job-b", 10) == []
    with sqlite3.connect(db) as connection:
        connection.execute("INSERT INTO job_description_intelligence VALUES ('v-b', 'hash-b', 'runr_description_nemo_v2', 'openrouter')")
    assert next_batch(store, "", 10) == []


def test_shared_description_is_returned_to_multiple_users(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RUNR_TEST_MODE", "1")
    monkeypatch.setenv("RUNR_ENV", "test")
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    app = create_backend(tmp_path, storage_backend="sqlite", test_mode=True)
    _seed_catalog(app)
    store = app.repositories.personalized_jobs_store
    row = store.get_published_job_row("job-a")
    generated = build_runr_description(row, lambda _: {
        "source_language": "en", "overview": "Readable overview",
        "responsibilities": [{"text": "Build reports", "source_excerpt": "Build reports"}],
        "required_qualifications": [], "preferred_qualifications": [],
        "benefits": [], "application_details": [],
    })
    store.save_description_intelligence(**generated)

    for user_id in ("user-a", "user-b"):
        detail = app.get_personalized_job_detail(user_id, "job-a")
        assert detail["runr_summary"]["overview"] == "Readable overview"
        assert detail["original_posting"]["description_text"]
        assert detail["description_intelligence"]["prompt_version"] == "runr_description_v1"


def test_pilot_description_is_served_to_customer_from_shared_version(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RUNR_TEST_MODE", "1")
    monkeypatch.setenv("RUNR_ENV", "test")
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    app = create_backend(tmp_path, storage_backend="sqlite", test_mode=True)
    _seed_catalog(app)
    store = app.repositories.personalized_jobs_store
    row = store.get_published_job_row("job-a")
    result = build_pilot_description(row, lambda _: {
        "items": [{"section": "responsibilities", "text": "Build reports.", "source_ids": ["p1"]}],
        "header_candidates": {"experience_years_min": {"value": 1, "source_ids": ["p1"]}},
    })
    store.save_description_intelligence(**result)
    detail = app.get_personalized_job_detail("user-a", "job-a")
    assert detail["description_intelligence"]["prompt_version"] == "runr_description_nemo_v2"
    assert detail["runr_summary"]["responsibilities"][0]["text"] == "Build reports."
    assert detail["structured_description"]["experience_years_min"] is None


def test_grounded_nemo_description_is_served_to_customer_from_shared_version(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RUNR_TEST_MODE", "1")
    monkeypatch.setenv("RUNR_ENV", "test")
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    app = create_backend(tmp_path, storage_backend="sqlite", test_mode=True)
    _seed_catalog(app, payload_overrides={"job-a": {"description": "Build reports."}})
    store = app.repositories.personalized_jobs_store
    row = store.get_published_job_row("job-a")
    result = build_pilot_description(row, lambda _: {
        "items": [{"section": "responsibilities", "text": "Build reports.", "source_ids": ["p1"], "source_quote": "Build reports."}],
        "header_candidates": {"experience_years_min": {"value": 1, "source_ids": ["p1"], "source_quote": "Build reports."}},
    }, require_source_quotes=True)
    store.save_description_intelligence(**result)
    detail = app.get_personalized_job_detail("user-a", "job-a")
    assert detail["description_intelligence"]["prompt_version"] == "runr_description_nemo_v3"
    assert detail["runr_summary"]["responsibilities"][0]["text"] == "Build reports."
    assert detail["structured_description"]["experience_years_min"] is None


def test_rule_backfill_prepares_all_jobs_and_model_can_upgrade_them(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RUNR_TEST_MODE", "1")
    monkeypatch.setenv("RUNR_ENV", "test")
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    app = create_backend(tmp_path, storage_backend="sqlite", test_mode=True)
    _seed_catalog(app)
    store = app.repositories.personalized_jobs_store
    cursor_file = tmp_path / "rules-cursor.json"
    result = run_rules_backfill(store, limit=2, cursor_file=cursor_file, page_size=1)
    assert result == {"pages": 2, "written": 2, "failed": 0}
    detail = app.get_personalized_job_detail("user-a", "job-a")
    assert detail["description_intelligence"]["provider"] == "runr_rules"
    assert detail["runr_summary"]["overview"]
    assert [row["canonical_job_id"] for row in next_batch(store, "", 5)] == ["job-a", "job-b"]
    assert next_batch(store, "", 5, upgrade_rules=False) == []

    model_result = build_runr_description(store.get_published_job_row("job-a"), lambda _: {
        "source_language": "en", "overview": "Model improved description",
        "responsibilities": [], "required_qualifications": [],
        "preferred_qualifications": [], "benefits": [], "application_details": [],
    })
    save_batch(store, [model_result])
    save_batch(store, [build_runr_description_rules(store.get_published_job_row("job-a"))], preserve_model=True)
    second = run_rules_backfill(store, limit=2, cursor_file=cursor_file, page_size=1)
    assert second["written"] == 0
    assert app.get_personalized_job_detail("user-b", "job-a")["runr_summary"]["overview"] == "Model improved description"


def test_backfill_writes_shared_description_and_resumes(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RUNR_TEST_MODE", "1")
    monkeypatch.setenv("RUNR_ENV", "test")
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    app = create_backend(tmp_path, storage_backend="sqlite", test_mode=True)
    _seed_catalog(app)
    monkeypatch.setattr("scripts.process_published_job_descriptions.openrouter_generate", lambda _: {"jobs": [{
        "id": version_id,
        "source_language": "en", "overview": "Prepared job",
        "responsibilities": [], "required_qualifications": [],
        "preferred_qualifications": [], "benefits": [], "application_details": [],
    } for version_id in ("version-job-a", "version-job-b")]})
    cursor_file = tmp_path / "cursor.json"
    result = run(app.repositories.personalized_jobs_store, limit=1, cursor_file=cursor_file)
    assert result["requests"] == 1
    assert result["completed"] == 2
    assert cursor_file.exists()
    assert app.get_personalized_job_detail("user-a", "job-a")["runr_summary"]["overview"] == "Prepared job"


def test_failed_write_is_retried_before_cursor_advances(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RUNR_TEST_MODE", "1")
    monkeypatch.setenv("RUNR_ENV", "test")
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    app = create_backend(tmp_path, storage_backend="sqlite", test_mode=True)
    _seed_catalog(app)
    store = app.repositories.personalized_jobs_store
    def generate(prompt):
        postings = json.loads(prompt.split("Postings:\n", 1)[1])
        return {"jobs": [{
            "id": posting["id"], "source_language": "en", "overview": "Prepared job",
            "responsibilities": [], "required_qualifications": [],
            "preferred_qualifications": [], "benefits": [], "application_details": [],
        } for posting in postings]}

    monkeypatch.setattr("scripts.process_published_job_descriptions.openrouter_generate", generate)
    original_save = save_batch
    failed_once = False

    def fail_first(store, results):
        nonlocal failed_once
        if not failed_once:
            failed_once = True
            raise ValueError("temporary write failure")
        return original_save(store, results)

    monkeypatch.setattr("scripts.process_published_job_descriptions.save_batch", fail_first)
    cursor_file = tmp_path / "cursor.json"
    first = run(store, limit=1, cursor_file=cursor_file)
    assert first["completed"] == 0 and first["failed"] == 2
    assert json.loads(cursor_file.read_text())["after_id"] == ""
    second = run(store, limit=1, cursor_file=cursor_file)
    assert second["completed"] == 2 and second["failed"] == 0


def test_transient_model_failure_retries_without_advancing_cursor(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RUNR_TEST_MODE", "1")
    monkeypatch.setenv("RUNR_ENV", "test")
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    app = create_backend(tmp_path, storage_backend="sqlite", test_mode=True)
    _seed_catalog(app)
    calls = 0

    def generate(prompt):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("temporary model timeout")
        postings = json.loads(prompt.split("Postings:\n", 1)[1])
        return {"jobs": [{
            "id": posting["id"], "source_language": "en", "overview": "Prepared job",
            "responsibilities": [], "required_qualifications": [],
            "preferred_qualifications": [], "benefits": [], "application_details": [],
        } for posting in postings]}

    monkeypatch.setattr("scripts.process_published_job_descriptions.openrouter_generate", generate)
    monkeypatch.setattr("scripts.process_published_job_descriptions.sleep", lambda _: None)
    cursor_file = tmp_path / "cursor.json"
    result = run(app.repositories.personalized_jobs_store, limit=2, cursor_file=cursor_file)
    assert calls == 2
    assert result["requests"] == 2
    assert result["completed"] == 2
    assert result["failed"] == 0


def test_persistent_batch_failure_is_split_into_individual_jobs(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RUNR_TEST_MODE", "1")
    monkeypatch.setenv("RUNR_ENV", "test")
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    app = create_backend(tmp_path, storage_backend="sqlite", test_mode=True)
    _seed_catalog(app)
    calls = 0

    def generate(prompt):
        nonlocal calls
        calls += 1
        postings = json.loads(prompt.split("Postings:\n", 1)[1])
        if len(postings) > 1:
            raise ValueError("batch response was incomplete")
        return {"jobs": [{
            "id": postings[0]["id"], "source_language": "en", "overview": "Prepared job",
            "responsibilities": [], "required_qualifications": [],
            "preferred_qualifications": [], "benefits": [], "application_details": [],
        }]}

    monkeypatch.setattr("scripts.process_published_job_descriptions.openrouter_generate", generate)
    monkeypatch.setattr("scripts.process_published_job_descriptions.sleep", lambda _: None)
    result = run(app.repositories.personalized_jobs_store, limit=5, cursor_file=tmp_path / "cursor.json")
    assert calls == 5
    assert result["completed"] == 2
    assert result["failed"] == 0


def test_unprocessable_single_posting_does_not_block_other_jobs(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RUNR_TEST_MODE", "1")
    monkeypatch.setenv("RUNR_ENV", "test")
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    app = create_backend(tmp_path, storage_backend="sqlite", test_mode=True)
    _seed_catalog(app)

    def generate(prompt):
        postings = json.loads(prompt.split("Postings:\n", 1)[1])
        if len(postings) > 1 or postings[0]["id"] == "version-job-a":
            raise ValueError("unprocessable posting")
        return {"jobs": [{
            "id": postings[0]["id"], "source_language": "en", "overview": "Prepared job",
            "responsibilities": [], "required_qualifications": [],
            "preferred_qualifications": [], "benefits": [], "application_details": [],
        }]}

    monkeypatch.setattr("scripts.process_published_job_descriptions.openrouter_generate", generate)
    monkeypatch.setattr("scripts.process_published_job_descriptions.sleep", lambda _: None)
    result = run(app.repositories.personalized_jobs_store, limit=7, cursor_file=tmp_path / "cursor.json")
    assert result["completed"] == 1
    assert result["failed"] == 1
    assert app.get_personalized_job_detail("user-a", "job-b")["runr_summary"]["overview"] == "Prepared job"
