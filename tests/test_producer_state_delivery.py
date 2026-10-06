from backend.application.source_eligibility_manifest import (
    build_source_eligibility_manifest,
    read_master_snapshot,
    write_manifest_bundle,
)
from backend.repositories.sqlite_acquisition import SqliteAcquisitionStore, _BulkTraceConnection
from scripts.master_employer_jobs_catalog import EmployerCollectionResult, EmployerCompany, EmployerState
from scripts.master_linkedin_jobs_catalog import CATALOG_FIELDS, StateStore
from scripts.publish_producer_states import (
    BackfillControls,
    RUNTIME_PUBLICATION_POLICY_VERSION,
    SOURCE_EMPLOYER,
    SOURCE_LINKEDIN,
    _crosswalk_already_applied,
    _current_employer_jobs,
    _latest_employer_statuses,
    _source_group_from_rows,
    _delivery_transaction_batches,
    _enrich_source_groups,
    _publisher_transaction_limits,
    _publisher_cycle_key,
    _split_large_bulk_snapshot,
    _verified_company_registry,
    _target,
    run_delivery,
)

import json
import sqlite3
import pytest
from datetime import datetime, timezone


def test_complete_employer_generation_excludes_retained_jobs_but_partial_keeps_them():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE companies(company_key TEXT, payload_json TEXT, status TEXT)")
    connection.execute("CREATE TABLE coverage_receipts(company_key TEXT, receipt_json TEXT)")
    connection.executemany(
        "INSERT INTO companies VALUES(?, ?, ?)",
        [
            ("complete", json.dumps({"generation_id": "new", "coverage": {"outcome": "confirmed_complete"}}), "completed"),
            ("partial", json.dumps({"generation_id": "new", "coverage": {"outcome": "partial"}}), "partial"),
        ],
    )
    connection.executemany(
        "INSERT INTO coverage_receipts VALUES(?, ?)",
        [
            ("complete", json.dumps({"generation_id": "new", "terminal_classification": "confirmed_complete"})),
            ("partial", json.dumps({"generation_id": "old", "terminal_classification": "confirmed_complete"})),
        ],
    )
    groups = {
        "complete": [{"source_job_id": "old", "last_seen_generation_id": "old"}, {"source_job_id": "new", "last_seen_generation_id": "new"}],
        "partial": [{"source_job_id": "old", "last_seen_generation_id": "old"}],
    }

    filtered = _current_employer_jobs(connection, groups)

    assert [row["source_job_id"] for row in filtered["complete"]] == ["new"]
    assert [row["source_job_id"] for row in filtered["partial"]] == ["old"]
    statuses = _latest_employer_statuses(connection)
    assert statuses["complete"][1] == "confirmed_complete"
    assert statuses["partial"][1] == "partial"


def test_inactive_linkedin_observation_is_not_sent_as_an_active_job():
    rows = [
        {"linkedin_company_id": "123", "linkedin_job_id": "old", "row_json": json.dumps({"canonical_company_id": "company", "lifecycle_status": "inactive"})},
        {"linkedin_company_id": "123", "linkedin_job_id": "live", "row_json": json.dumps({"canonical_company_id": "company", "lifecycle_status": "active"})},
    ]
    groups, _ = _source_group_from_rows(
        rows,
        source=SOURCE_LINKEDIN,
        canonical_by_source_company={"123": "company"},
        selected_ids={"company"},
    )

    assert [row["linkedin_job_id"] for row in groups["company"]] == ["live"]


def test_bulk_trace_reports_database_error_without_swallowing_it(capsys):
    class FailingConnection:
        def execute(self, _sql, _parameters):
            raise ValueError("request exceeds protocol limit")

    connection = _BulkTraceConnection(FailingConnection(), "batch-test")

    with pytest.raises(ValueError, match="protocol limit"):
        connection.execute("INSERT INTO example VALUES (?)", ("private-value",))

    output = capsys.readouterr().out
    assert '"event":"bulk_statement_error"' in output
    assert '"error_type":"ValueError"' in output
    assert "request exceeds protocol limit" in output
    assert "private-value" not in output


def test_bulk_ingest_deduplicates_external_id_when_source_urls_differ(tmp_path):
    store = SqliteAcquisitionStore(tmp_path / "duplicate-external-id.sqlite3")
    target = _target(
        {"canonical_company_id": "duplicate-company", "canonical_company_name": "Duplicate Company"},
        SOURCE_EMPLOYER,
    )
    store.ensure_targets([target])

    result = store.ingest_snapshots_bulk([{
        "cycle_id": "duplicate-cycle",
        "task_id": "duplicate-task",
        "target_id": target["target_id"],
        "observed_at": "2026-09-30T01:00:00+00:00",
        "jobs": [
            {"job_id": "same-id", "title": "Engineer", "url": "https://company.example/jobs/first"},
            {"job_id": "same-id", "title": "Engineer", "url": "https://company.example/jobs/second"},
        ],
        "complete_snapshot": True,
        "valid_snapshot": True,
        "closure_safe": True,
    }])

    target_result = result["targets"][target["target_id"]]
    assert target_result["observed"] == 1
    assert target_result["duplicates"] == 1


def test_delivery_transaction_batches_pack_small_companies_and_isolate_large_ones():
    rows = {"small-1": 3, "small-2": 4, "large": 21, "empty": 0, "small-3": 5}
    items = [("employer", company_id) for company_id in rows]

    batches = list(
        _delivery_transaction_batches(
            items,
            source_rows=lambda _source, company_id: rows[company_id],
            max_companies=2,
            max_rows=20,
        )
    )

    assert batches == [
        [("employer", "small-1"), ("employer", "small-2")],
        [("employer", "empty"), ("employer", "small-3")],
        [("employer", "large")],
    ]


def test_publisher_transaction_limits_default_to_bounded_set_based_batch(monkeypatch):
    monkeypatch.delenv("RUNR_PUBLISHER_TRANSACTION_COMPANIES", raising=False)
    monkeypatch.delenv("RUNR_PUBLISHER_TRANSACTION_ROWS", raising=False)
    assert _publisher_transaction_limits() == (50, 100)
    monkeypatch.setenv("RUNR_PUBLISHER_TRANSACTION_COMPANIES", "999")
    monkeypatch.setenv("RUNR_PUBLISHER_TRANSACTION_ROWS", "999")
    assert _publisher_transaction_limits() == (50, 100)


def test_publisher_cycle_key_allows_only_explicit_bounded_producer_override(monkeypatch):
    monkeypatch.delenv("RUNR_PUBLISHER_RESUME_CYCLE_KEY", raising=False)
    assert _publisher_cycle_key("producer:calculated") == "producer:calculated"

    monkeypatch.setenv("RUNR_PUBLISHER_RESUME_CYCLE_KEY", "producer:durable-cycle")
    assert _publisher_cycle_key("producer:calculated") == "producer:durable-cycle"

    monkeypatch.setenv("RUNR_PUBLISHER_RESUME_CYCLE_KEY", "unrelated:cycle")
    with pytest.raises(ValueError, match="producer cycle key"):
        _publisher_cycle_key("producer:calculated")


def test_large_bulk_snapshot_only_authorizes_closure_on_final_chunk():
    jobs = [
        {"job_id": f"job-{index}", "title": f"Engineer {index}", "url": f"https://company.example/jobs/{index}"}
        for index in range(205)
    ]
    snapshot = {
        "cycle_id": "large-cycle",
        "task_id": "large-task",
        "target_id": "large-target",
        "jobs": jobs,
        "complete_snapshot": True,
        "valid_snapshot": True,
        "closure_safe": True,
        "snapshot_external_ids": [job["job_id"] for job in jobs],
    }

    chunks = _split_large_bulk_snapshot(snapshot, max_rows=100)

    assert [len(chunk["jobs"]) for chunk in chunks] == [100, 100, 5]
    assert [chunk["complete_snapshot"] for chunk in chunks] == [False, False, True]
    assert [chunk["closure_safe"] for chunk in chunks] == [False, False, True]
    assert chunks[0]["snapshot_external_ids"] == [f"job-{index}" for index in range(100)]
    assert chunks[-1]["snapshot_external_ids"] == snapshot["snapshot_external_ids"]

def test_bulk_staging_normalizes_and_resolves_duplicate_identity_setwise(tmp_path):
    store = SqliteAcquisitionStore(tmp_path / "catalog.sqlite3")
    targets = [
        _target(
            {"canonical_company_id": "company-1", "canonical_company_name": "Company"},
            source,
        )
        for source in (SOURCE_LINKEDIN, SOURCE_EMPLOYER)
    ]
    store.ensure_targets(targets)
    shared_job = {
        "job_id": "job-1",
        "title": "Platform Engineer",
        "location": "Berlin",
        "url": "https://company.example/jobs/1",
        "application_url": "https://company.example/jobs/1/apply",
        "description": "Build reliable platform services.",
    }
    snapshots = [
        {
            "cycle_id": "cycle-bulk-1",
            "task_id": f"task-{index}",
            "target_id": target["target_id"],
            "jobs": [shared_job],
            "complete_snapshot": True,
            "valid_snapshot": True,
            "closure_safe": True,
        }
        for index, target in enumerate(targets)
    ]

    result = store._run_transaction(
        lambda connection: store._stage_producer_ingest_batch(
            connection,
            snapshots,
            batch_id="bulk-1",
        )
    )

    with store._connect() as connection:
        rows = connection.execute(
            "SELECT target_id, resolved_canonical_job_id, projection_action "
            "FROM acquisition_ingest_staging WHERE batch_id='bulk-1' ORDER BY target_id"
        ).fetchall()
        target_count = connection.execute(
            "SELECT COUNT(*) FROM acquisition_ingest_targets WHERE batch_id='bulk-1'"
        ).fetchone()[0]
        snapshot_count = connection.execute(
            "SELECT COUNT(*) FROM acquisition_ingest_snapshot_ids WHERE batch_id='bulk-1'"
        ).fetchone()[0]

    assert result == {
        "batch_id": "bulk-1",
        "companies": 2,
        "jobs": 2,
        "actions": {"new": 2},
    }
    assert target_count == 2
    assert snapshot_count == 2
    assert len({row["resolved_canonical_job_id"] for row in rows}) == 1
    assert {row["projection_action"] for row in rows} == {"new"}


def test_bulk_projection_materializes_shared_job_and_cleans_staging(tmp_path):
    store = SqliteAcquisitionStore(tmp_path / "catalog.sqlite3")
    targets = [
        _target(
            {"canonical_company_id": "company-1", "canonical_company_name": "Company"},
            source,
        )
        for source in (SOURCE_LINKEDIN, SOURCE_EMPLOYER)
    ]
    store.ensure_targets(targets)
    snapshots = [
        {
            "cycle_id": "cycle-bulk-project",
            "task_id": f"task-{index}",
            "target_id": target["target_id"],
            "observed_at": "2026-09-30T01:00:00+00:00",
            "jobs": [
                {
                    "job_id": f"source-job-{index}",
                    "title": "Platform Engineer",
                    "location": "Berlin",
                    "url": "https://company.example/jobs/1",
                    "application_url": "https://company.example/jobs/1/apply",
                    "description": "Build reliable platform services.",
                }
            ],
            "complete_snapshot": True,
            "valid_snapshot": True,
            "closure_safe": True,
        }
        for index, target in enumerate(targets)
    ]

    result = store.ingest_snapshots_bulk(snapshots, batch_id="bulk-project-1")

    with store._connect() as connection:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "canonical_companies",
                "canonical_jobs",
                "job_source_observations",
                "job_posting_versions",
                "job_source_states",
                "acquisition_ingest_batches",
                "acquisition_ingest_staging",
                "acquisition_ingest_targets",
                "acquisition_ingest_snapshot_ids",
            )
        }
        job = connection.execute(
            "SELECT canonical_job_id, company_id, lifecycle_state, current_version_id FROM canonical_jobs"
        ).fetchone()
        rule_outputs = connection.execute("SELECT COUNT(*) FROM acquisition_rule_outputs").fetchone()[0]
        provenance = connection.execute("SELECT COUNT(*) FROM acquisition_field_provenance").fetchone()[0]
        completeness = connection.execute(
            "SELECT entity_kind, entity_id, rule_version, state, report_json "
            "FROM acquisition_completeness_reports"
        ).fetchall()

    assert result["companies"] == 2
    assert result["jobs"] == 2
    assert set(result["targets"]) == {target["target_id"] for target in targets}
    assert counts == {
        "canonical_companies": 1,
        "canonical_jobs": 1,
        "job_source_observations": 2,
        "job_posting_versions": 1,
        "job_source_states": 2,
        "acquisition_ingest_batches": 0,
        "acquisition_ingest_staging": 0,
        "acquisition_ingest_targets": 0,
        "acquisition_ingest_snapshot_ids": 0,
    }
    assert job["company_id"] == "company-1"
    assert job["lifecycle_state"] == "active"
    assert job["current_version_id"]
    assert rule_outputs == 2
    assert provenance > 0
    assert len(completeness) == 1
    assert completeness[0]["entity_kind"] == "job"
    assert completeness[0]["entity_id"] == job["canonical_job_id"]
    assert completeness[0]["rule_version"]
    assert completeness[0]["state"] in {"complete", "warning"}
    assert '"report_only":true' in completeness[0]["report_json"]


def test_bulk_projection_completes_task_evidence_in_same_transaction(tmp_path):
    store = SqliteAcquisitionStore(tmp_path / "catalog.sqlite3")
    target = _target(
        {"canonical_company_id": "company-1", "canonical_company_name": "Company"},
        SOURCE_EMPLOYER,
    )
    store.ensure_targets([target])
    cycle = store.claim_due_cycle(
        window_key="bulk-task-evidence",
        lease_owner="test",
        scheduled_at="2026-09-30T01:00:00+00:00",
        scope_key="bulk-task-evidence",
    )
    assert cycle is not None
    store.ensure_cycle_tasks(cycle["cycle_id"], [target])
    task_id = store.list_cycle_task_ids(cycle["cycle_id"])[target["target_id"]]

    store.ingest_snapshots_bulk(
        [{
            "cycle_id": cycle["cycle_id"],
            "task_id": task_id,
            "target_id": target["target_id"],
            "source": SOURCE_EMPLOYER,
            "observed_at": "2026-09-30T01:00:00+00:00",
            "jobs": [{"job_id": "job-1", "title": "Engineer", "url": "https://company.example/jobs/1"}],
            "complete_snapshot": True,
            "valid_snapshot": True,
            "closure_safe": True,
            "unresolved_observations": 2,
        }]
    )

    with store._connect() as connection:
        task = connection.execute(
            "SELECT status, jobs_observed, jobs_new, credible_evidence, collection_metadata_json "
            "FROM acquisition_tasks WHERE task_id=?",
            (task_id,),
        ).fetchone()
    assert task["status"] == "completed"
    assert task["jobs_observed"] == 1
    assert task["jobs_new"] == 1
    assert task["credible_evidence"] == 1
    assert '"unresolved_observations":2' in task["collection_metadata_json"]


def test_bulk_projection_remote_call_count_is_constant_per_batch(tmp_path, monkeypatch):
    from backend.database.connection import DatabaseConnection

    def prepared_store(name):
        store = SqliteAcquisitionStore(tmp_path / name / "catalog.sqlite3")
        target = _target(
            {"canonical_company_id": f"company-{name}", "canonical_company_name": f"Company {name}"},
            SOURCE_EMPLOYER,
        )
        store.ensure_targets([target])
        return store, target

    small_store, small_target = prepared_store("small")
    large_store, large_target = prepared_store("large")
    original_execute = DatabaseConnection.execute
    original_executemany = DatabaseConnection.executemany
    calls = {"execute": 0, "executemany": 0}

    def counted_execute(self, *args, **kwargs):
        calls["execute"] += 1
        return original_execute(self, *args, **kwargs)

    def counted_executemany(self, *args, **kwargs):
        calls["executemany"] += 1
        return original_executemany(self, *args, **kwargs)

    monkeypatch.setattr(DatabaseConnection, "execute", counted_execute)
    monkeypatch.setattr(DatabaseConnection, "executemany", counted_executemany)

    def ingest(store, target, count, cycle):
        calls.update(execute=0, executemany=0)
        store.ingest_snapshots_bulk(
            [{
                "cycle_id": cycle,
                "task_id": f"task-{cycle}",
                "target_id": target["target_id"],
                "observed_at": "2026-09-30T01:00:00+00:00",
                "jobs": [
                    {
                        "job_id": f"job-{index}",
                        "title": f"Engineer {index}",
                        "url": f"https://company.example/jobs/{cycle}/{index}",
                    }
                    for index in range(count)
                ],
                "complete_snapshot": True,
                "valid_snapshot": True,
                "closure_safe": True,
            }]
        )
        return dict(calls)

    one_job = ingest(small_store, small_target, 1, "one")
    twenty_jobs = ingest(large_store, large_target, 20, "twenty")

    assert twenty_jobs == one_job
    assert twenty_jobs["executemany"] == 5
    assert twenty_jobs["execute"] < 40


def test_bulk_projection_failure_rolls_back_staging_and_projection(tmp_path, monkeypatch):
    store = SqliteAcquisitionStore(tmp_path / "catalog.sqlite3")
    target = _target(
        {"canonical_company_id": "company-rollback", "canonical_company_name": "Rollback Company"},
        SOURCE_EMPLOYER,
    )
    store.ensure_targets([target])

    def fail_projection(_connection, *, batch_id):
        raise RuntimeError(f"projection failed for {batch_id}")

    monkeypatch.setattr(store, "_project_producer_ingest_batch", fail_projection)
    with pytest.raises(RuntimeError, match="projection failed"):
        store.ingest_snapshots_bulk(
            [{
                "cycle_id": "cycle-rollback",
                "task_id": "task-rollback",
                "target_id": target["target_id"],
                "jobs": [{"job_id": "job-1", "title": "Engineer", "url": "https://company.example/jobs/1"}],
                "complete_snapshot": True,
                "valid_snapshot": True,
                "closure_safe": True,
            }],
            batch_id="rollback-batch",
        )

    with store._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM acquisition_ingest_batches").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM acquisition_ingest_staging").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM canonical_jobs").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM job_source_observations").fetchone()[0] == 0


def test_bulk_company_profile_preserves_known_fields_and_improves_missing_fields(tmp_path):
    import json

    store = SqliteAcquisitionStore(tmp_path / "catalog.sqlite3")
    target = _target(
        {"canonical_company_id": "company-profile", "canonical_company_name": "Profile Company"},
        SOURCE_EMPLOYER,
    )
    target["config"]["company_profile"] = {"industry": "Technology"}
    store.ensure_targets([target])
    base_job = {"job_id": "job-1", "title": "Engineer", "url": "https://profile.example/jobs/1"}
    store.ingest_snapshots_bulk(
        [{
            "cycle_id": "profile-cycle-1",
            "task_id": "profile-task-1",
            "target_id": target["target_id"],
            "observed_at": "2026-09-30T01:00:00+00:00",
            "jobs": [base_job],
            "complete_snapshot": True,
            "valid_snapshot": True,
            "closure_safe": True,
        }]
    )

    target["config"]["company_profile"] = {"description": "A verified employer profile."}
    store.ensure_targets([target])
    store.ingest_snapshots_bulk(
        [{
            "cycle_id": "profile-cycle-2",
            "task_id": "profile-task-2",
            "target_id": target["target_id"],
            "observed_at": "2026-09-30T02:00:00+00:00",
            "jobs": [{**base_job, "description": "Updated role"}],
            "complete_snapshot": True,
            "valid_snapshot": True,
            "closure_safe": True,
        }]
    )

    with store._connect() as connection:
        company_count = connection.execute(
            "SELECT COUNT(*) FROM canonical_companies WHERE company_id='company-profile'"
        ).fetchone()[0]
        profile_row = connection.execute(
            "SELECT profile_json FROM canonical_company_profiles WHERE company_id='company-profile'"
        ).fetchone()
    fields = json.loads(profile_row["profile_json"])["fields"]
    assert company_count == 1
    assert fields["industry"]["value"] == "Technology"
    assert fields["description"]["value"] == "A verified employer profile."


def test_bulk_company_identity_records_target_evidence_without_stealing_aliases(tmp_path):
    store = SqliteAcquisitionStore(tmp_path / "catalog.sqlite3")
    target = _target(
        {"canonical_company_id": "company-evidence", "canonical_company_name": "Evidence Company"},
        SOURCE_EMPLOYER,
    )
    store.ensure_targets([target])
    now = "2026-09-30T01:00:00+00:00"
    with store._connect() as connection:
        connection.execute(
            "INSERT INTO canonical_companies "
            "(company_id, canonical_name, entity_kind, provenance_url, created_at, updated_at) "
            "VALUES ('other-company', 'Other Company', 'employer', '', ?, ?)",
            (now, now),
        )
        connection.execute(
            "INSERT INTO canonical_company_aliases "
            "(alias_id, company_id, alias_key, alias_display, source, confidence, created_at, updated_at) "
            "VALUES ('alias-existing', 'other-company', 'evidence company employer', 'Evidence Company (employer)', "
            "'fixture', 'verified', ?, ?)",
            (now, now),
        )

    store.ingest_snapshots_bulk(
        [{
            "cycle_id": "identity-cycle",
            "task_id": "identity-task",
            "target_id": target["target_id"],
            "observed_at": now,
            "jobs": [{"job_id": "job-1", "title": "Engineer", "url": "https://evidence.example/jobs/1"}],
            "complete_snapshot": True,
            "valid_snapshot": True,
            "closure_safe": True,
        }]
    )

    with store._connect() as connection:
        evidence = connection.execute(
            "SELECT company_id, identity_key, target_id, link_state, review_required "
            "FROM company_identity_evidence WHERE evidence_type='acquisition_target'"
        ).fetchall()
        aliases = {
            row["alias_key"]: row["company_id"]
            for row in connection.execute(
                "SELECT alias_key, company_id FROM canonical_company_aliases"
            ).fetchall()
        }

    assert len(evidence) == 1
    assert evidence[0]["company_id"] == "company-evidence"
    assert evidence[0]["identity_key"] == f"target:{target['target_id']}"
    assert evidence[0]["target_id"] == target["target_id"]
    assert evidence[0]["link_state"] == "linked"
    assert evidence[0]["review_required"] == 0
    assert aliases["evidence company employer"] == "other-company"
    assert aliases["company evidence"] == "company-evidence"


def test_bulk_company_profile_persists_configured_official_urls_and_occurrences(tmp_path):
    store = SqliteAcquisitionStore(tmp_path / "catalog.sqlite3")
    target = _target(
        {"canonical_company_id": "company-urls", "canonical_company_name": "URL Company"},
        SOURCE_EMPLOYER,
    )
    target["config"]["company_profile"] = {
        "website": "https://url-company.example/",
        "careers_page": "https://url-company.example/careers/",
    }
    store.ensure_targets([target])

    store.ingest_snapshots_bulk(
        [{
            "cycle_id": "url-cycle",
            "task_id": "url-task",
            "target_id": target["target_id"],
            "observed_at": "2026-09-30T01:00:00+00:00",
            "jobs": [{"job_id": "job-1", "title": "Engineer", "url": "https://url-company.example/jobs/1"}],
            "complete_snapshot": True,
            "valid_snapshot": True,
            "closure_safe": True,
        }]
    )

    with store._connect() as connection:
        urls = connection.execute(
            "SELECT url_type, canonical_url, url_lifecycle, occurrence_count "
            "FROM canonical_company_urls WHERE company_id='company-urls' ORDER BY url_type"
        ).fetchall()
        occurrences = connection.execute(
            "SELECT url_type, canonical_url, url_lifecycle, source, target_id "
            "FROM canonical_company_url_occurrences WHERE company_id='company-urls' ORDER BY url_type"
        ).fetchall()

    assert [dict(row) for row in urls] == [
        {
            "url_type": "careers",
            "canonical_url": "https://url-company.example/careers/",
            "url_lifecycle": "configured_official",
            "occurrence_count": 1,
        },
        {
            "url_type": "homepage",
            "canonical_url": "https://url-company.example/",
            "url_lifecycle": "configured_official",
            "occurrence_count": 1,
        },
    ]
    assert [dict(row) for row in occurrences] == [
        {
            "url_type": "careers",
            "canonical_url": "https://url-company.example/careers/",
            "url_lifecycle": "configured_official",
            "source": "official_employer_source",
            "target_id": target["target_id"],
        },
        {
            "url_type": "homepage",
            "canonical_url": "https://url-company.example/",
            "url_lifecycle": "configured_official",
            "source": "official_employer_source",
            "target_id": target["target_id"],
        },
    ]


def test_bulk_retry_appends_observation_without_duplicate_version_for_unchanged_content(tmp_path):
    store = SqliteAcquisitionStore(tmp_path / "catalog.sqlite3")
    target = _target(
        {"canonical_company_id": "company-version", "canonical_company_name": "Version Company"},
        SOURCE_EMPLOYER,
    )
    store.ensure_targets([target])
    job = {
        "job_id": "job-1",
        "title": "Engineer",
        "url": "https://version.example/jobs/1",
        "description": "Stable content",
    }
    base = {
        "target_id": target["target_id"],
        "jobs": [job],
        "complete_snapshot": True,
        "valid_snapshot": True,
        "closure_safe": True,
    }
    store.ingest_snapshots_bulk(
        [{**base, "cycle_id": "version-cycle-1", "task_id": "version-task-1", "observed_at": "2026-09-30T01:00:00+00:00"}]
    )
    second = store.ingest_snapshots_bulk(
        [{**base, "cycle_id": "version-cycle-2", "task_id": "version-task-2", "observed_at": "2026-09-30T02:00:00+00:00"}]
    )

    with store._connect() as connection:
        observation_count = connection.execute("SELECT COUNT(*) FROM job_source_observations").fetchone()[0]
        version_count = connection.execute("SELECT COUNT(*) FROM job_posting_versions").fetchone()[0]

    target_result = second["targets"][target["target_id"]]
    assert target_result["observed"] == 1
    assert target_result["updated"] == 0
    assert target_result["unchanged"] == 1
    assert observation_count == 2
    assert version_count == 1


def test_bulk_intermediate_same_cycle_replay_skips_projection(tmp_path, monkeypatch):
    store = SqliteAcquisitionStore(tmp_path / "catalog.sqlite3")
    target = _target(
        {"canonical_company_id": "company-replay", "canonical_company_name": "Replay Company"},
        SOURCE_EMPLOYER,
    )
    store.ensure_targets([target])
    snapshot = {
        "cycle_id": "replay-cycle",
        "task_id": "replay-task",
        "target_id": target["target_id"],
        "observed_at": "2026-09-30T01:00:00+00:00",
        "jobs": [{"job_id": "job-1", "title": "Engineer", "url": "https://replay.example/jobs/1"}],
        "complete_snapshot": False,
        "valid_snapshot": True,
        "closure_safe": False,
    }
    store.ingest_snapshots_bulk([snapshot])

    def unexpected_projection(*_args, **_kwargs):
        raise AssertionError("an already committed intermediate chunk must not re-run projection")

    monkeypatch.setattr(store, "_project_producer_ingest_batch", unexpected_projection)
    replay = store.ingest_snapshots_bulk([snapshot])

    assert replay["actions"] == {"replay": 1}
    assert replay["targets"][target["target_id"]]["unchanged"] == 1
    with store._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM job_source_observations").fetchone()[0] == 1


def test_bulk_ingestion_matches_single_company_semantic_projection(tmp_path):
    def ingest(store, *, bulk):
        target = _target(
            {"canonical_company_id": "company-parity", "canonical_company_name": "Parity Company"},
            SOURCE_EMPLOYER,
        )
        target["config"]["company_profile"] = {"industry": "Software"}
        store.ensure_targets([target])
        snapshot = {
            "cycle_id": "parity-cycle",
            "task_id": "parity-task",
            "target_id": target["target_id"],
            "observed_at": "2026-09-30T01:00:00+00:00",
            "jobs": [{
                "job_id": "parity-job",
                "title": "Platform Engineer",
                "location": "Berlin",
                "url": "https://parity.example/jobs/1",
                "application_url": "https://parity.example/jobs/1/apply",
                "description": "Build reliable services.",
            }],
            "complete_snapshot": True,
            "valid_snapshot": True,
            "closure_safe": True,
        }
        if bulk:
            store.ingest_snapshots_bulk([snapshot])
        else:
            store.ingest_snapshot(**snapshot)

    legacy = SqliteAcquisitionStore(tmp_path / "legacy.sqlite3")
    bulk = SqliteAcquisitionStore(tmp_path / "bulk.sqlite3")
    ingest(legacy, bulk=False)
    ingest(bulk, bulk=True)

    def projection(store):
        with store._connect() as connection:
            job = connection.execute(
                "SELECT title, location, canonical_url, lifecycle_state, absence_count "
                "FROM canonical_jobs"
            ).fetchone()
            version = connection.execute(
                "SELECT version_number, content_hash, title, location, apply_url FROM job_posting_versions"
            ).fetchone()
            observation = connection.execute(
                "SELECT target_id, cycle_id, task_id, external_job_id, original_url, application_url, active "
                "FROM job_source_observations"
            ).fetchone()
            state = connection.execute(
                "SELECT target_id, external_job_id, lifecycle_state, absence_count, grace_attempts "
                "FROM job_source_states"
            ).fetchone()
            return {
                "company_count": connection.execute("SELECT COUNT(*) FROM canonical_companies").fetchone()[0],
                "job": dict(job),
                "version": dict(version),
                "observation": dict(observation),
                "source_state": dict(state),
                "versions": connection.execute("SELECT COUNT(*) FROM job_posting_versions").fetchone()[0],
                "observations": connection.execute("SELECT COUNT(*) FROM job_source_observations").fetchone()[0],
                "completeness": connection.execute("SELECT COUNT(*) FROM acquisition_completeness_reports").fetchone()[0],
            }

    assert projection(bulk) == projection(legacy)


def test_bulk_content_change_advances_current_version_without_mutating_history(tmp_path):
    store = SqliteAcquisitionStore(tmp_path / "catalog.sqlite3")
    target = _target(
        {"canonical_company_id": "company-current-version", "canonical_company_name": "Versioned Company"},
        SOURCE_EMPLOYER,
    )
    store.ensure_targets([target])
    base = {
        "target_id": target["target_id"],
        "complete_snapshot": True,
        "valid_snapshot": True,
        "closure_safe": True,
    }
    store.ingest_snapshots_bulk([{
        **base,
        "cycle_id": "current-version-cycle-1",
        "task_id": "current-version-task-1",
        "observed_at": "2026-09-30T01:00:00+00:00",
        "jobs": [{"job_id": "job-1", "title": "Engineer", "url": "https://versions.example/jobs/1", "description": "First"}],
    }])
    store.ingest_snapshots_bulk([{
        **base,
        "cycle_id": "current-version-cycle-2",
        "task_id": "current-version-task-2",
        "observed_at": "2026-09-30T02:00:00+00:00",
        "jobs": [{"job_id": "job-1", "title": "Senior Engineer", "url": "https://versions.example/jobs/1", "description": "Second"}],
    }])

    with store._connect() as connection:
        job = connection.execute(
            "SELECT title, current_version_id FROM canonical_jobs"
        ).fetchone()
        versions = connection.execute(
            "SELECT version_id, version_number, title, description FROM job_posting_versions ORDER BY version_number"
        ).fetchall()

    assert job["title"] == "Senior Engineer"
    assert [(row["version_number"], row["title"], row["description"]) for row in versions] == [
        (1, "Engineer", "First"),
        (2, "Senior Engineer", "Second"),
    ]
    assert job["current_version_id"] == versions[1]["version_id"]


def test_bulk_projection_closes_only_after_closure_safe_complete_absences(tmp_path):
    store = SqliteAcquisitionStore(tmp_path / "catalog.sqlite3")
    target = _target(
        {"canonical_company_id": "company-1", "canonical_company_name": "Company"},
        SOURCE_EMPLOYER,
    )
    store.ensure_targets([target])
    base = {
        "task_id": "task-present",
        "target_id": target["target_id"],
        "observed_at": "2026-09-30T01:00:00+00:00",
        "jobs": [{"job_id": "job-1", "title": "Engineer", "url": "https://company.example/jobs/1"}],
        "complete_snapshot": True,
        "valid_snapshot": True,
        "closure_safe": True,
    }
    store.ingest_snapshots_bulk([{**base, "cycle_id": "cycle-present"}])

    unknown = store.ingest_snapshots_bulk(
        [{
            **base,
            "cycle_id": "cycle-incomplete",
            "task_id": "task-incomplete",
            "observed_at": "2026-09-30T02:00:00+00:00",
            "jobs": [],
            "valid_snapshot": False,
            "closure_safe": False,
        }]
    )
    with store._connect() as connection:
        state_after_incomplete = connection.execute(
            "SELECT lifecycle_state, absence_count FROM job_source_states"
        ).fetchone()
    assert unknown["targets"][target["target_id"]]["closed"] == 0
    assert (state_after_incomplete["lifecycle_state"], state_after_incomplete["absence_count"]) == ("unknown", 0)

    closed_counts = []
    for index, hour in enumerate((3, 4, 5), start=1):
        result = store.ingest_snapshots_bulk(
            [{
                **base,
                "cycle_id": f"cycle-absence-{index}",
                "task_id": f"task-absence-{index}",
                "observed_at": f"2026-09-30T0{hour}:00:00+00:00",
                "jobs": [],
            }]
        )
        closed_counts.append(result["targets"][target["target_id"]]["closed"])

    with store._connect() as connection:
        source_state = connection.execute(
            "SELECT lifecycle_state, absence_count FROM job_source_states"
        ).fetchone()
        canonical_state = connection.execute(
            "SELECT lifecycle_state FROM canonical_jobs"
        ).fetchone()[0]
    assert closed_counts == [0, 0, 1]
    assert (source_state["lifecycle_state"], source_state["absence_count"]) == ("closed", 3)
    assert canonical_state == "closed"


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
        # The listing-only row is reported for audit, but v1 keeps it visible.
        assert rejection_count == 1
        first_publication = store.get_public_catalog(limit=20, offset=0)
        assert first_publication["total"] == 3
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


def test_runtime_publisher_does_not_rerun_database_initialization(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNR_ENV", "test")
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("RUNR_PUBLISHER_INITIALIZE_DATABASE", "0")
    manifest = _manifest(tmp_path)
    linkedin_path, employer_path = _seed_producer_states(tmp_path)
    database_path = tmp_path / "backend" / "backend.sqlite3"
    SqliteAcquisitionStore(database_path)
    initialize_flags = []
    original_init = SqliteAcquisitionStore.__init__

    def recorded_init(self, db_path, *, initialize=True):
        initialize_flags.append(initialize)
        original_init(self, db_path, initialize=initialize)

    monkeypatch.setattr(SqliteAcquisitionStore, "__init__", recorded_init)
    result = run_delivery(
        manifest_path=manifest,
        linkedin_state=linkedin_path,
        employer_state=employer_path,
        data_dir=tmp_path / "backend",
        source_version="fixture-release-no-init",
    )

    assert result["publication_id"]
    assert initialize_flags
    assert all(flag is False for flag in initialize_flags)


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

    original_bulk_ingest = SqliteAcquisitionStore.ingest_snapshots_bulk

    def fail_once(*args, **kwargs):
        raise RuntimeError("transient canary failure")

    monkeypatch.setattr(SqliteAcquisitionStore, "ingest_snapshots_bulk", fail_once)
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

    monkeypatch.setattr(SqliteAcquisitionStore, "ingest_snapshots_bulk", original_bulk_ingest)
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


def test_bounded_incremental_run_publishes_before_resuming_remaining_targets(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNR_ENV", "test")
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("RUNR_PUBLISHER_INCREMENTAL_PUBLICATION", "1")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    manifest = _manifest(tmp_path)
    linkedin_path, employer_path = _seed_producer_states(tmp_path)
    data_dir = tmp_path / "backend"

    first = run_delivery(
        manifest_path=manifest,
        linkedin_state=linkedin_path,
        employer_state=employer_path,
        data_dir=data_dir,
        source_version="fixture-incremental",
        controls=BackfillControls(batch_size=1, max_companies=1),
    )
    assert first["status"] == "stopped"
    store = SqliteAcquisitionStore(data_dir / "backend.sqlite3")
    try:
        first_catalog = store.get_public_catalog()
        first_publication_id = first_catalog["publication"]["publication_id"]
        first_job_count = first_catalog["total"]
        assert first_job_count > 0
        assert store.publisher_checkpoint(SOURCE_LINKEDIN)["source_rowid"] == 0
    finally:
        if hasattr(store, "close"):
            store.close()

    last = first
    for _ in range(10):
        last = run_delivery(
            manifest_path=manifest,
            linkedin_state=linkedin_path,
            employer_state=employer_path,
            data_dir=data_dir,
            source_version="fixture-incremental",
            controls=BackfillControls(batch_size=1, max_companies=1),
        )
        if last["status"] in {"completed", "degraded"}:
            break
    assert last["status"] in {"completed", "degraded"}
    assert last["publication_id"]
    store = SqliteAcquisitionStore(data_dir / "backend.sqlite3")
    try:
        with store._connect() as connection:
            publications = connection.execute(
                "SELECT publication_id FROM acquisition_publications"
            ).fetchall()
            memberships = connection.execute(
                "SELECT canonical_job_id FROM acquisition_publication_jobs WHERE publication_id=?",
                (last["publication_id"],),
            ).fetchall()
        assert len(publications) == 1, "resuming one cycle must not copy the full catalog again"
        assert publications[0]["publication_id"] == last["publication_id"] == first_publication_id
        assert len(memberships) > first_job_count, "later batches must add their new jobs"
        assert len(memberships) == store.get_public_catalog()["total"]
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
        assert published == 3
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
