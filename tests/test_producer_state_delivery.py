from backend.application.source_eligibility_manifest import (
    build_source_eligibility_manifest,
    read_master_snapshot,
    write_manifest_bundle,
)
from backend.repositories.sqlite_acquisition import SqliteAcquisitionStore
from scripts.master_employer_jobs_catalog import EmployerCollectionResult, EmployerCompany, EmployerState
from scripts.master_linkedin_jobs_catalog import CATALOG_FIELDS, StateStore
from scripts.publish_producer_states import run_delivery


def _manifest(tmp_path):
    rows, columns, digest = read_master_snapshot("tests/fixtures/rc005_source_eligibility.csv")
    report = build_source_eligibility_manifest(
        rows[:1],
        columns,
        source_path="tests/fixtures/rc005_source_eligibility.csv",
        input_sha256=digest,
        cycle_id="bridge-fixture",
        as_of="2026-09-10T00:00:00Z",
        max_evidence_age_days=30,
        raw_sidecar_path="bridge.raw.jsonl",
    )
    path = tmp_path / "manifest.json"
    write_manifest_bundle(path, report, raw_sidecar_path=tmp_path / "bridge.raw.jsonl")
    return path


def test_durable_producer_states_reach_shared_publication_and_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNR_ENV", "test")
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    manifest = _manifest(tmp_path)

    linkedin_path = tmp_path / "linkedin" / "master_linkedin_jobs_state.db"
    linkedin = StateStore(linkedin_path)
    linkedin.start_run("li-run-1", mode="daily", input_sha256="fixture")
    linkedin_row = {field: "" for field in CATALOG_FIELDS}
    linkedin_row.update(
        {
            "canonical_company_id": "master-alpha",
            "linkedin_company_id": "101",
            "source_company_name": "Alpha GmbH",
            "source_company_url": "https://www.linkedin.com/company/alpha",
            "linkedin_job_id": "li-job-1",
            "linkedin_job_url": "https://www.linkedin.com/jobs/view/li-job-1",
            "apply_url_canonical": "https://alpha.example/jobs/li-job-1/apply",
            "job_title": "LinkedIn Backend Engineer",
            "description": "Build resilient backend services with a collaborative engineering team and clear ownership across the product.",
            "location": "Berlin, Germany",
            "last_seen_at": "2026-09-10T00:00:00Z",
            "lifecycle_status": "active",
            "source": "linkedin",
            "run_id": "li-run-1",
            "company_scan_id": "li-scan-1",
        }
    )
    linkedin.upsert_catalog_row(linkedin_row)
    linkedin.upsert_catalog_row(
        {
            **linkedin_row,
            "linkedin_job_id": "li-job-listing-only",
            "linkedin_job_url": "https://www.linkedin.com/jobs/view/li-job-listing-only",
            "apply_url_canonical": "",
            "job_title": "LinkedIn Listing Only",
        }
    )
    linkedin.close()

    employer_path = tmp_path / "employer" / "master_employer_jobs_state.db"
    employer = EmployerState(employer_path)
    company = EmployerCompany(
        canonical_company_id="master-alpha",
        company_name="Alpha GmbH",
        website_url="https://alpha.example",
    )
    employer.save(
        EmployerCollectionResult(
            company=company,
            jobs=[
                {
                    "canonical_company_id": "master-alpha",
                    "source_provider": "greenhouse",
                    "source_job_id": "em-job-1",
                    "source_job_url": "https://alpha.example/jobs/em-job-1",
                    "application_url": "https://alpha.example/jobs/em-job-1/apply",
                    "job_title": "Employer Platform Engineer",
                    "description_text": "Build resilient platform services with a collaborative engineering team and clear ownership across the product.",
                    "location_raw": "Berlin, Germany",
                    "last_seen_at": "2026-09-10T00:00:00Z",
                }
            ],
            status="completed",
        ),
        generation_id="em-run-1",
        source_version="fixture",
    )
    employer.close()

    result = run_delivery(
        manifest_path=manifest,
        linkedin_state=linkedin_path,
        employer_state=employer_path,
        data_dir=tmp_path / "backend",
        source_version="fixture-release",
    )
    assert result["status"] == "degraded"
    assert result["publication_id"]

    store = SqliteAcquisitionStore(tmp_path / "backend" / "backend.sqlite3")
    try:
        first_cycle = result["cycle_id"]
        with store._connect() as connection:
            companies = {
                row["company_id"]
                for row in connection.execute("SELECT company_id FROM canonical_companies")
            }
            sources = {
                row["source_ats"]
                for row in connection.execute("SELECT DISTINCT source_ats FROM job_source_observations")
            }
            rejection_count = connection.execute(
                "SELECT COUNT(*) FROM acquisition_job_rejections WHERE cycle_id=?",
                (first_cycle,),
            ).fetchone()[0]
        assert "master-alpha" in companies
        assert {"linkedin", "greenhouse"}.issubset(sources)
        assert rejection_count == 1
        first_publication = store.get_public_catalog(limit=20, offset=0)
        assert first_publication["total"] == 2
    finally:
        store.close() if hasattr(store, "close") else None

    replay = run_delivery(
        manifest_path=manifest,
        linkedin_state=linkedin_path,
        employer_state=employer_path,
        data_dir=tmp_path / "backend",
        source_version="fixture-release",
    )
    assert replay["cycle_id"] == first_cycle
    assert replay["publication_id"] == result["publication_id"]
