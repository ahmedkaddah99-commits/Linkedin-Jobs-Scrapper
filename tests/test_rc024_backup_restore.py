from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

import scripts.master_employer_jobs_catalog as employer_catalog
from scripts.acquisition_state_backup import (
    CheckpointError,
    LeaseFenced,
    OwnershipConflict,
    SingleWriterLease,
    create_checkpoint,
    preserve_checkpoint_off_host,
    prune_local_checkpoints,
    restore_remote_checkpoint,
    restore_checkpoint,
    validate_checkpoint,
)
from scripts.master_employer_jobs_catalog import EmployerCollectionResult, EmployerCompany, EmployerState, run_collection
from scripts.master_linkedin_jobs_catalog import StateStore


ZERO_SHA256 = "0" * 64


def _checkpoint_kwargs(source: Path, root: Path, *, role: str = "employer") -> dict[str, object]:
    return {
        "role": role,
        "source_db": source,
        "checkpoint_root": root,
        "source_version": "fixture-release-rc024",
        "release_commit": "fixture-release-rc024",
        "manifest_id": "fixture-manifest-rc024",
        "manifest_sha256": ZERO_SHA256,
        "cycle_id": "fixture-cycle-001",
        "shard_id": "employer-fixture",
        "high_water_marks": {"company_row": 2, "last_company_key": "canonical-acme"},
        "free_space_reserve_bytes": 0,
    }


def _write_employer_source(path: Path) -> None:
    path.write_text(
        "canonical_CompanyID,company_name,website_url\n"
        "canonical-acme,Acme,https://acme.example\n",
        encoding="utf-8",
    )


def _employer_company() -> EmployerCompany:
    return EmployerCompany(
        canonical_company_id="canonical-acme",
        company_name="Acme",
        website_url="https://acme.example",
        linkedin_company_url="https://www.linkedin.com/company/acme",
        source_row_number=2,
    )


def _employer_result(company: EmployerCompany) -> EmployerCollectionResult:
    return EmployerCollectionResult(
        company=company,
        jobs=[
            {
                "canonical_company_id": company.canonical_company_id,
                "source_type": "employer_site",
                "source_provider": "fixture",
                "source_job_id": "fixture-job",
                "source_job_url": "https://acme.example/jobs/fixture-job",
                "job_title": "Fixture job",
                "extraction_method": "fixture",
            }
        ],
        status="completed",
    )


class _MemoryRemote:
    def __init__(self, *, fail_on_call: int | None = None) -> None:
        self.files: dict[str, bytes] = {}
        self.calls: list[str] = []
        self.fail_on_call = fail_on_call

    def put_file(self, path: Path, key: str, *, metadata: dict[str, str], content_type: str) -> dict[str, object]:
        del content_type
        self.calls.append(key)
        if self.fail_on_call == len(self.calls):
            raise RuntimeError("fixture remote upload interruption")
        body = path.read_bytes()
        existing = self.files.get(key)
        if existing is not None and existing != body:
            raise RuntimeError("fixture remote immutable-object conflict")
        self.files[key] = body
        return {"status": "uploaded" if existing is None else "already_present", "key": key, "bytes": len(body), "sha256": metadata["sha256"]}

    def get_file(self, key: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.files[key])

    def head_file(self, key: str) -> dict[str, object] | None:
        body = self.files.get(key)
        if body is None:
            return None
        return {"ContentLength": len(body), "Metadata": {"sha256": hashlib.sha256(body).hexdigest()}}


def test_online_backup_accepts_the_authoritative_14_table_linkedin_schema(tmp_path: Path) -> None:
    source = tmp_path / "master_linkedin_jobs_state.db"
    state = StateStore(source)
    state.close()
    manifest = create_checkpoint(
        **{
            **_checkpoint_kwargs(source, tmp_path / "backups", role="linkedin"),
            "shard_id": "linkedin-fixture",
        }
    )
    checkpoint_dir = tmp_path / "backups" / "linkedin" / str(manifest["checkpoint_id"])
    assert validate_checkpoint(checkpoint_dir, expected_role="linkedin")["backup"]["schema"]["tables"] == [
        "company_scans",
        "company_slug_aliases",
        "detail_attempts",
        "detail_queue",
        "job_company_observations",
        "jobs",
        "lifecycle_events",
        "ownership_exclusions",
        "proxy_health",
        "query_partitions",
        "runs",
        "search_cards",
        "search_pages",
        "source_company_groups",
    ]


def test_online_backup_preserves_wal_consistency_schema_and_source(tmp_path: Path) -> None:
    source = tmp_path / "state" / "master_employer_jobs_state.db"
    source.parent.mkdir()
    state = EmployerState(source)
    state.connection.execute(
        "INSERT INTO companies(company_key, payload_json, status, error, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("canonical-acme", json.dumps({"name": "Acme"}), "completed", "", "fixture"),
    )
    state.connection.execute(
        "INSERT INTO jobs(source_key, payload_json, updated_at) VALUES (?, ?, ?)",
        ("fixture-job", json.dumps({"title": "Fixture job"}), "fixture"),
    )
    state.connection.commit()
    state.close()
    with sqlite3.connect(source) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.commit()

    original_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = create_checkpoint(**_checkpoint_kwargs(source, tmp_path / "backups"))
    checkpoint_dir = tmp_path / "backups" / "employer" / str(manifest["checkpoint_id"])
    assert validate_checkpoint(checkpoint_dir)["backup"]["method"] == "sqlite_online_backup"
    assert manifest["backup"]["wal_consistent"] is True
    assert manifest["cycle"]["high_water_marks"]["company_row"] == 2
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_digest
    assert not list(checkpoint_dir.glob("*.db-wal"))
    assert not list(checkpoint_dir.glob("*.db-shm"))
    assert manifest["state"]["schema"]["tables"] == ["companies", "jobs"]


def test_off_host_upload_commits_manifest_last_and_remote_restore_is_isolated(tmp_path: Path) -> None:
    source = tmp_path / "master_employer_jobs_state.db"
    state = EmployerState(source)
    state.connection.execute(
        "INSERT INTO jobs(source_key, payload_json, updated_at) VALUES (?, ?, ?)",
        ("fixture-job", json.dumps({"title": "Fixture job"}), "fixture"),
    )
    state.connection.commit()
    state.close()
    manifest = create_checkpoint(**_checkpoint_kwargs(source, tmp_path / "backups"))
    checkpoint_dir = tmp_path / "backups" / "employer" / str(manifest["checkpoint_id"])
    remote = _MemoryRemote()

    receipt = preserve_checkpoint_off_host(checkpoint_dir, remote)
    assert [key.rsplit("/", 1)[-1] for key in remote.calls] == [
        "master_employer_jobs_state.db",
        "checkpoint.json",
    ]
    assert receipt["manifest_is_commit_record"] is True
    assert (checkpoint_dir / "off-host-receipt.json").is_file()

    target = tmp_path / "restored" / "employer"
    restored = restore_remote_checkpoint(
        remote,
        manifest_key=str(manifest["off_host"]["manifest_object_key"]),
        target_dir=target,
        expected_role="employer",
    )
    assert restored["checkpoint_id"] == manifest["checkpoint_id"]
    assert (target / "master_employer_jobs_state.db").is_file()
    restored_state = EmployerState.open_existing(target / "master_employer_jobs_state.db")
    try:
        assert restored_state.job_count() == 1
    finally:
        restored_state.close()


def test_interrupted_backup_has_no_published_checkpoint_and_source_remains_usable(tmp_path: Path) -> None:
    source = tmp_path / "master_employer_jobs_state.db"
    state = EmployerState(source)
    state.close()

    def interrupt(_status: int, _remaining: int, _total: int) -> None:
        raise KeyboardInterrupt("fixture kill during backup")

    with pytest.raises(KeyboardInterrupt):
        create_checkpoint(**_checkpoint_kwargs(source, tmp_path / "backups"), backup_pages=1, progress=interrupt)
    assert not list((tmp_path / "backups" / "employer").glob("*/checkpoint.json"))
    assert source.is_file()
    validate_checkpoint  # keep the acceptance surface explicit in this drill


def test_manifest_upload_failure_leaves_local_checkpoint_for_retry_without_ack(tmp_path: Path) -> None:
    source = tmp_path / "master_employer_jobs_state.db"
    EmployerState(source).close()
    manifest = create_checkpoint(**_checkpoint_kwargs(source, tmp_path / "backups"))
    checkpoint_dir = tmp_path / "backups" / "employer" / str(manifest["checkpoint_id"])
    remote = _MemoryRemote(fail_on_call=2)

    with pytest.raises(RuntimeError, match="upload interruption"):
        preserve_checkpoint_off_host(checkpoint_dir, remote)
    assert (checkpoint_dir / "checkpoint.json").is_file()
    assert not (checkpoint_dir / "off-host-receipt.json").exists()
    assert len(remote.files) == 1


def test_local_checkpoint_budget_pauses_before_unbounded_outage_buffer(tmp_path: Path) -> None:
    source = tmp_path / "master_employer_jobs_state.db"
    EmployerState(source).close()
    kwargs = _checkpoint_kwargs(source, tmp_path / "backups")
    first = create_checkpoint(**kwargs)
    current_bytes = int(first["backup"]["bytes"])
    kwargs["local_budget_bytes"] = current_bytes
    with pytest.raises(CheckpointError, match="local checkpoint budget exhausted"):
        create_checkpoint(**kwargs)


def test_prune_keeps_unpreserved_generations_and_bounds_preserved_generations(tmp_path: Path) -> None:
    source = tmp_path / "master_employer_jobs_state.db"
    EmployerState(source).close()
    checkpoint_root = tmp_path / "backups"
    first = create_checkpoint(**_checkpoint_kwargs(source, checkpoint_root))
    second = create_checkpoint(**_checkpoint_kwargs(source, checkpoint_root))
    first_dir = checkpoint_root / "employer" / str(first["checkpoint_id"])
    second_dir = checkpoint_root / "employer" / str(second["checkpoint_id"])
    remote = _MemoryRemote()
    preserve_checkpoint_off_host(second_dir, remote)
    assert prune_local_checkpoints(checkpoint_root, role="employer", keep=1) == []
    preserve_checkpoint_off_host(first_dir, remote)
    removable = prune_local_checkpoints(checkpoint_root, role="employer", keep=1)
    assert removable == [str(first_dir)]
    prune_local_checkpoints(checkpoint_root, role="employer", keep=1, apply=True)
    assert not first_dir.exists()
    assert second_dir.exists()


def test_lost_disk_preflight_does_not_create_partial_checkpoint(tmp_path: Path) -> None:
    source = tmp_path / "master_employer_jobs_state.db"
    EmployerState(source).close()
    kwargs = _checkpoint_kwargs(source, tmp_path / "backups")
    kwargs["free_space_reserve_bytes"] = 10**18
    with pytest.raises(CheckpointError, match="insufficient free space"):
        create_checkpoint(**kwargs)
    assert not (tmp_path / "backups" / "employer").exists()


def test_competing_owner_and_expired_owner_are_epoch_fenced(tmp_path: Path) -> None:
    current = [100.0]
    lease_store = SingleWriterLease(tmp_path / "ownership", clock=lambda: current[0])
    first = lease_store.claim(role="employer", shard_id="employer-fixture", owner_id="host-a", ttl_seconds=10)
    with pytest.raises(OwnershipConflict):
        lease_store.claim(role="employer", shard_id="employer-fixture", owner_id="host-b", ttl_seconds=10)
    current[0] = 111.0
    second = lease_store.claim(role="employer", shard_id="employer-fixture", owner_id="host-b", ttl_seconds=10)
    with pytest.raises(LeaseFenced):
        first.assert_current()
    first.release()  # stale cleanup cannot release the new owner's lease
    second.assert_current()


def test_restored_checkpoint_resumes_actual_employer_producer_without_collection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_csv = tmp_path / "companies.csv"
    _write_employer_source(source_csv)
    source_state = tmp_path / "state" / "master_employer_jobs_state.db"
    source_output = tmp_path / "first-export"
    monkeypatch.setattr(employer_catalog, "collect_company", lambda company, *_args, **_kwargs: _employer_result(company))
    run_collection(
        input_csv=source_csv,
        output_dir=source_output,
        state_dir=source_state.parent,
        limit=1,
        resume=False,
        company_concurrency=1,
    )
    manifest = create_checkpoint(**_checkpoint_kwargs(source_state, tmp_path / "backups"))
    checkpoint_dir = tmp_path / "backups" / "employer" / str(manifest["checkpoint_id"])
    restored_state_dir = tmp_path / "restored-state"
    restore_checkpoint(checkpoint_dir, restored_state_dir, expected_role="employer")

    def must_not_collect(*_args: object, **_kwargs: object) -> EmployerCollectionResult:
        raise AssertionError("resumed completed company was collected again")

    monkeypatch.setattr(employer_catalog, "collect_company", must_not_collect)
    resumed = run_collection(
        input_csv=source_csv,
        output_dir=tmp_path / "resumed-export",
        state_dir=restored_state_dir,
        limit=1,
        resume=True,
        require_existing_state=True,
        company_concurrency=1,
    )
    assert resumed["companies_skipped_resume"] == 1
    assert resumed["final_export_completed"] is True
    with (tmp_path / "resumed-export" / "master_employer_jobs.csv").open(encoding="utf-8-sig", newline="") as handle:
        assert [row["source_job_id"] for row in csv.DictReader(handle)] == ["fixture-job"]
