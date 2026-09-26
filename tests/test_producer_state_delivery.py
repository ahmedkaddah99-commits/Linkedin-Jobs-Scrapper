from backend.application.source_eligibility_manifest import (
    build_source_eligibility_manifest,
    read_master_snapshot,
    write_manifest_bundle,
)
from backend.repositories.sqlite_acquisition import SqliteAcquisitionStore
from scripts.master_employer_jobs_catalog import EmployerCollectionResult, EmployerCompany, EmployerState
from scripts.master_linkedin_jobs_catalog import CATALOG_FIELDS, StateStore
from scripts.publish_producer_states import (
    BackfillControls,
    RUNTIME_PUBLICATION_POLICY_VERSION,
    SOURCE_EMPLOYER,
    SOURCE_LINKEDIN,
    _crosswalk_already_applied,
    _enrich_source_groups,
    _verified_company_registry,
    _target,
    run_delivery,
)

import pytest
from datetime import datetime, timezone


def test_publisher_uses_only_verified_registry_and_explicit_job_evidence(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    registry = tmp_path / "company_registry_canonical.csv"
    registry.write_text(
        "canonical_CompanyID,enrichment_status,logo_url,last_enriched_at,industry,description\n"
        f"company-1,succeeded,https://example.com/logo.png,{datetime.now(timezone.utc).isoformat()},Technology,Verified company\n"
        f"company-2,failed,https://example.com/other.png,{datetime.now(timezone.utc).isoformat()},Technology,Unverified\n",
        encoding="utf-8",
    )
    companies, digest = _verified_company_registry(manifest)
    groups = _enrich_source_groups(
        {
            "company-1": [{"job_title": "Senior Engineer", "description": "Work on-site in Berlin."}],
            "company-2": [{"job_title": "Engineer", "description": "No remote work."}],
        },
        verified_companies=companies,
        registry_sha256=digest,
    )

    assert groups["company-1"][0]["company_logo"] == "https://example.com/logo.png"
    assert groups["company-1"][0]["company_enrichment"]["fields"]["industry"] == "Technology"
    assert groups["company-1"][0]["seniority"] == "Senior"
    assert groups["company-1"][0]["workplace_type"] == "on-site"
    assert "company_logo" not in groups["company-2"][0]
    assert "seniority" not in groups["company-2"][0]
    assert "workplace_type" not in groups["company-2"][0]


def test_publisher_skips_only_an_exact_applied_crosswalk(tmp_path):
    store = SqliteAcquisitionStore(tmp_path / "catalog.sqlite3")
    document = {
        "registry_sha256": "reviewed-registry",
        "report": {"canonical_rows": [{"canonical_CompanyID": "company-1", "company_name": "Company"}]},
    }
    mapping = {"old-company:legacy-1": "company-1"}

    assert not _crosswalk_already_applied(store, mapping=mapping, document=document)
    store.apply_company_identity_crosswalk(
        mapping_by_identity=mapping,
        canonical_rows=document["report"]["canonical_rows"],
        provenance={"registry_sha256": document["registry_sha256"]},
    )
    assert _crosswalk_already_applied(store, mapping=mapping, document=document)
    assert not _crosswalk_already_applied(
        store, mapping={"old-company:legacy-1": "company-2"}, document=document
    )


def test_producer_targets_record_the_selected_policy_version():
    target = _target(
        {"canonical_company_id": "company-1", "canonical_company_name": "Company"},
        SOURCE_EMPLOYER,
        policy_version=RUNTIME_PUBLICATION_POLICY_VERSION,
    )

    assert target["policy_version"] == RUNTIME_PUBLICATION_POLICY_VERSION


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


def _seed_producer_states(tmp_path):
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
            "employment_type": "full_time",
            "workplace_type": "hybrid",
            "seniority": "mid",
            "company_logo": "https://alpha.example/logo.png",
            "company_enrichment": "verified",
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
                    "employment_type": "full_time",
                    "workplace_type": "hybrid",
                    "seniority": "mid",
                    "company_logo": "https://alpha.example/logo.png",
                    "company_enrichment": "{}",
                    "last_seen_at": "2026-09-10T00:00:00Z",
                }
            ],
            status="completed",
        ),
        generation_id="em-run-1",
        source_version="fixture",
    )
    employer.close()
    return linkedin_path, employer_path


def test_durable_producer_states_reach_shared_publication_and_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNR_ENV", "test")
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    manifest = _manifest(tmp_path)
    linkedin_path, employer_path = _seed_producer_states(tmp_path)

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
        # The listing-only LinkedIn row has no apply URL; runtime policy v2 blocks it.
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


def test_dry_run_reports_eligibility_without_creating_catalog_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNR_ENV", "test")
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    manifest = _manifest(tmp_path)
    linkedin_path, employer_path = _seed_producer_states(tmp_path)

    result = run_delivery(
        manifest_path=manifest,
        linkedin_state=linkedin_path,
        employer_state=employer_path,
        data_dir=tmp_path / "backend",
        source_version="fixture-release",
        controls=BackfillControls(batch_size=1, dry_run=True),
    )

    assert result["status"] == "dry_run"
    assert result["dry_run"] is True
    assert result["limits"] == {
        "batch_size": 1,
        "max_companies": None,
        "rate_per_second": 0.0,
        "timeout_seconds": None,
        "max_failures": 0,
    }
    assert result["eligibility"]["eligible"] + result["eligibility"]["ineligible"] > 0
    assert result["receipt"]["dry_run"] is True
    assert not (tmp_path / "backend" / "backend.sqlite3").exists()


def test_backfill_controls_reject_unbounded_or_negative_limits():
    with pytest.raises(ValueError, match="batch_size"):
        BackfillControls(batch_size=0)
    with pytest.raises(ValueError, match="rate_per_second"):
        BackfillControls(batch_size=1, rate_per_second=-1)
    with pytest.raises(ValueError, match="timeout_seconds"):
        BackfillControls(batch_size=1, timeout_seconds=0)
    with pytest.raises(ValueError, match="max_failures"):
        BackfillControls(batch_size=1, max_failures=-1)


def test_failure_threshold_stops_without_advancing_checkpoint_and_resume_is_safe(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNR_ENV", "test")
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    manifest = _manifest(tmp_path)
    linkedin_path, employer_path = _seed_producer_states(tmp_path)

    import scripts.publish_producer_states as publisher

    original_deliver_group = publisher._deliver_group

    def fail_once(*args, **kwargs):
        raise RuntimeError("transient canary failure")

    monkeypatch.setattr(publisher, "_deliver_group", fail_once)
    stopped = run_delivery(
        manifest_path=manifest,
        linkedin_state=linkedin_path,
        employer_state=employer_path,
        data_dir=tmp_path / "backend",
        source_version="fixture-release",
        controls=BackfillControls(batch_size=1, max_failures=1),
    )
    assert stopped["status"] == "stopped"
    assert stopped["failures"] == 1
    assert stopped["stop_reason"] == "max_failures"

    monkeypatch.setattr(publisher, "_deliver_group", original_deliver_group)
    resumed = run_delivery(
        manifest_path=manifest,
        linkedin_state=linkedin_path,
        employer_state=employer_path,
        data_dir=tmp_path / "backend",
        source_version="fixture-release",
        controls=BackfillControls(batch_size=1, max_failures=1),
    )
    assert resumed["status"] in {"completed", "degraded"}
    assert resumed["receipt"]["limits"]["batch_size"] == 1

    store = SqliteAcquisitionStore(tmp_path / "backend" / "backend.sqlite3")
    try:
        with store._connect() as connection:
            duplicated_pairs = connection.execute(
                "SELECT target_id, external_job_id, COUNT(*) AS occurrences "
                "FROM job_source_observations GROUP BY target_id, external_job_id "
                "HAVING occurrences > 1"
            ).fetchall()
        assert duplicated_pairs == []
    finally:
        if hasattr(store, "close"):
            store.close()

def test_crash_before_checkpoint_save_reruns_the_same_window_idempotently(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNR_ENV", "test")
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    manifest = _manifest(tmp_path)
    linkedin_path, employer_path = _seed_producer_states(tmp_path)

    store_path = tmp_path / "backend" / "backend.sqlite3"
    store = SqliteAcquisitionStore(store_path)
    try:
        assert store.publisher_checkpoint(SOURCE_LINKEDIN)["bootstrap_complete"] is False
        assert store.publisher_checkpoint(SOURCE_EMPLOYER)["source_rowid"] == 0
    finally:
        if hasattr(store, "close"):
            store.close()

    original_publish = SqliteAcquisitionStore.publish_valid_snapshot

    def crash(self, *args, **kwargs):
        raise RuntimeError("simulated crash after delivery")

    monkeypatch.setattr(SqliteAcquisitionStore, "publish_valid_snapshot", crash)
    with pytest.raises(RuntimeError, match="simulated crash"):
        run_delivery(
            manifest_path=manifest,
            linkedin_state=linkedin_path,
            employer_state=employer_path,
            data_dir=tmp_path / "backend",
            source_version="fixture-release",
        )
    monkeypatch.setattr(SqliteAcquisitionStore, "publish_valid_snapshot", original_publish)

    store = SqliteAcquisitionStore(store_path)
    try:
        with store._connect() as connection:
            cycle = connection.execute(
                "SELECT status, error_code FROM acquisition_cycles"
            ).fetchall()
            checkpoint_rows = connection.execute(
                "SELECT source, source_rowid, bootstrap_complete FROM acquisition_publisher_checkpoints"
            ).fetchall()
        assert any(row["status"] == "recovery_required" for row in cycle)
        assert checkpoint_rows == [], "a crashed run must never advance checkpoints"
    finally:
        if hasattr(store, "close"):
            store.close()

    retry = run_delivery(
        manifest_path=manifest,
        linkedin_state=linkedin_path,
        employer_state=employer_path,
        data_dir=tmp_path / "backend",
        source_version="fixture-release",
    )
    assert retry["status"] in {"completed", "degraded"}
    assert retry["publication_id"]

    store = SqliteAcquisitionStore(store_path)
    try:
        linkedin_checkpoint = store.publisher_checkpoint(SOURCE_LINKEDIN)
        employer_checkpoint = store.publisher_checkpoint(SOURCE_EMPLOYER)
        assert linkedin_checkpoint["bootstrap_complete"] is True
        assert linkedin_checkpoint["last_publication_id"] == retry["publication_id"]
        assert employer_checkpoint["bootstrap_complete"] is True

        with store._connect() as connection:
            published = connection.execute(
                "SELECT COUNT(*) FROM acquisition_publication_jobs WHERE publication_id=?",
                (retry["publication_id"],),
            ).fetchone()[0]
            duplicated_pairs = connection.execute(
                "SELECT target_id, external_job_id, COUNT(*) AS occurrences "
                "FROM job_source_observations GROUP BY target_id, external_job_id HAVING occurrences > 1"
            ).fetchall()
            observation_total = connection.execute(
                "SELECT COUNT(*) FROM job_source_observations"
            ).fetchone()[0]
        assert published == 2
        assert duplicated_pairs == [], "replayed delivery must not duplicate catalog jobs"
        assert observation_total == 3
    finally:
        if hasattr(store, "close"):
            store.close()


def test_publisher_checkpoint_preflight_requires_registry_table(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNR_ENV", "test")
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)

    store = SqliteAcquisitionStore(tmp_path / "backend" / "backend.sqlite3")
    try:
        with store._connect() as connection:
            connection.execute("DROP TABLE acquisition_publisher_checkpoints")
        with pytest.raises(RuntimeError, match="061_acquisition_publisher_checkpoints"):
            store.require_publisher_checkpoint_table()
    finally:
        if hasattr(store, "close"):
            store.close()
