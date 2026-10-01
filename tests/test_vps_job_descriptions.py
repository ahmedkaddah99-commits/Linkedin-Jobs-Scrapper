import json
import pytest
import sqlite3
from pathlib import Path

from backend.application.vps_job_descriptions import build_runr_description, build_runr_descriptions, openrouter_generate
from backend.bootstrap import create_backend
from backend.repositories.sqlite_personalized_jobs import SqlitePersonalizedJobsStore
from scripts.process_published_job_descriptions import next_batch, run, save_batch
from tests.test_phase_c_personalized_jobs import _seed_catalog


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
            CREATE TABLE job_description_intelligence (version_id TEXT, content_hash TEXT, prompt_version TEXT);
            INSERT INTO acquisition_publication_head VALUES (1, 'publication');
            INSERT INTO acquisition_publication_jobs VALUES ('publication', 'job-a'), ('publication', 'job-b'), ('publication', 'job-c');
            INSERT INTO canonical_jobs VALUES ('job-a', 'v-a', 'A', ''), ('job-b', 'v-b', 'B', ''), ('job-c', 'v-c', 'C', '');
            INSERT INTO job_posting_versions VALUES ('v-a', 1, 'hash-a', 'Description A', '{}', '', '', '2026-09-30');
            INSERT INTO job_posting_versions VALUES ('v-b', 1, 'hash-b', 'Description B', '{}', '', '', '2026-10-01');
            INSERT INTO job_posting_versions VALUES ('v-c', 1, 'hash-c', '', '{}', '', '', '2026-10-02');
            INSERT INTO job_description_intelligence VALUES ('v-a', 'hash-a', 'runr_description_v1');
        """)
    store = SqlitePersonalizedJobsStore(db, initialize=False)
    assert [row["canonical_job_id"] for row in next_batch(store, "", 10)] == ["job-b"]
    assert [row["canonical_job_id"] for row in next_batch(store, "job-z", 10, newest=True)] == ["job-b"]
    assert next_batch(store, "job-b", 10) == []


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
