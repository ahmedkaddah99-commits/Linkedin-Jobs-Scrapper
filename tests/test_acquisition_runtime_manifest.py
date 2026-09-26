from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest

from backend.application.source_eligibility_manifest import (
    RAW_SIDECAR_SCHEMA_VERSION,
    SCHEMA_VERSION,
    _manifest_hash,
    load_manifest,
)
from deploy.validate_acquisition_runtime import capture_evidence, validate_manifest


SYSTEMD = Path(__file__).resolve().parents[1] / "deploy" / "systemd"
DEPLOY = Path(__file__).resolve().parents[1] / "deploy"


LINKEDIN_TABLES = (
    "runs",
    "source_company_groups",
    "company_slug_aliases",
    "company_scans",
    "query_partitions",
    "search_pages",
    "search_cards",
    "jobs",
    "job_company_observations",
    "detail_queue",
    "detail_attempts",
    "ownership_exclusions",
    "lifecycle_events",
    "proxy_health",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(
    tmp_path: Path,
    *,
    corrupt_seed_hash: bool = False,
    table_counts: dict[str, int] | None = None,
) -> tuple[Path, Path, Path]:
    input_root = tmp_path / "inputs"
    state_root = tmp_path / "state"
    input_root.mkdir()
    state_root.mkdir()
    seed = input_root / "company_sources_linkedin_ids.csv"
    seed.write_bytes(b"canonical_CompanyID,linkedin_company_id\ncompany-1,123\n")
    state = state_root / "master_linkedin_jobs_state.db"
    with sqlite3.connect(state) as connection:
        for table in LINKEDIN_TABLES:
            connection.execute(f"CREATE TABLE {table} (id INTEGER)")
        for _ in range(2):
            connection.execute("INSERT INTO jobs (id) VALUES (NULL)")
    payload = {
        "schema_version": "runr.acquisition.data-manifest.v1",
        "seed_inputs": [
            {
                "logical_name": "company_sources_linkedin_ids",
                "repo_path": None,
                "server_path": "/srv/runr/shared/inputs/company_sources_linkedin_ids.csv",
                "bytes": seed.stat().st_size,
                "sha256": "0" * 64 if corrupt_seed_hash else _sha256(seed),
            }
        ],
        "state_snapshots": [
            {
                "logical_name": "linkedin_authoritative_state",
                "server_path": "/srv/runr/state/master_linkedin_jobs_state.db",
                "bytes": state.stat().st_size,
                "sha256": _sha256(state),
                "schema": {"tables": dict(table_counts) if table_counts is not None else {table: 0 for table in LINKEDIN_TABLES}},
            }
        ],
    }
    manifest = tmp_path / "acquisition-data-manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    return manifest, input_root, state_root


def test_runtime_manifest_validates_seed_and_fourteen_table_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest, input_root, state_root = _write_manifest(tmp_path)
    monkeypatch.setenv("RUNR_ACQUISITION_INPUT_ROOT", str(input_root))
    monkeypatch.setenv("RUNR_ACQUISITION_STATE_ROOT", str(state_root))

    result = validate_manifest(manifest, "linkedin")

    assert result["role"] == "linkedin"
    assert result["seeds"][0]["logical_name"] == "company_sources_linkedin_ids"
    assert result["states"][0]["logical_name"] == "linkedin_authoritative_state"


def test_runtime_manifest_rejects_seed_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest, input_root, state_root = _write_manifest(tmp_path, corrupt_seed_hash=True)
    monkeypatch.setenv("RUNR_ACQUISITION_INPUT_ROOT", str(input_root))
    monkeypatch.setenv("RUNR_ACQUISITION_STATE_ROOT", str(state_root))

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        validate_manifest(manifest, "linkedin")


def test_historical_absolute_sidecar_path_can_be_restored_next_to_manifest(tmp_path: Path) -> None:
    sidecar = tmp_path / "SOURCE_ELIGIBILITY_RAW.jsonl"
    sidecar.write_text(
        json.dumps({"schema_version": RAW_SIDECAR_SCHEMA_VERSION, "row_fingerprint": "row-1", "raw_columns": {}})
        + "\n",
        encoding="utf-8",
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "raw_sidecar": {
            "path": r"C:\Users\old-host\runr\SOURCE_ELIGIBILITY_RAW.jsonl",
            "sha256": _sha256(sidecar),
        },
    }
    payload["manifest_hash"] = _manifest_hash(payload)
    manifest = tmp_path / "SOURCE_ELIGIBILITY_MANIFEST.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_manifest(manifest)

    assert loaded["raw_sidecar"]["resolved_path"] == str(sidecar.resolve())


def test_schedule_manifest_is_machine_readable_and_has_no_duplicate_owner() -> None:
    target = (SYSTEMD / "runr.target").read_text(encoding="utf-8")
    start = "# RUNR_ACQUISITION_SCHEDULE_MANIFEST_BEGIN\n# "
    end = "\n# RUNR_ACQUISITION_SCHEDULE_MANIFEST_END"
    assert start in target and end in target
    payload = target.split(start, 1)[1].split(end, 1)[0]
    manifest = json.loads(payload)

    schedules = manifest["schedules"]
    assert set(schedules) == {"linkedin", "employer", "publisher"}
    assert len({item["owner_timer"] for item in schedules.values()}) == len(schedules)
    assert len({item["owner_service"] for item in schedules.values()}) == len(schedules)
    assert set(manifest["disabled_units"]) >= {
        "runr-acquisition-cycle.timer",
        "runr-acquisition-export.timer",
        "runr-acquisition-worker.service",
    }


def test_runtime_manifest_enforces_row_count_contract_before_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = {table: 0 for table in LINKEDIN_TABLES}
    expected["jobs"] = 2
    manifest, input_root, state_root = _write_manifest(tmp_path, table_counts=expected)
    monkeypatch.setenv("RUNR_ACQUISITION_INPUT_ROOT", str(input_root))
    monkeypatch.setenv("RUNR_ACQUISITION_STATE_ROOT", str(state_root))

    result = validate_manifest(manifest, "linkedin", require_table_counts=True)

    assert result["require_table_counts"] is True
    assert result["states"][0]["table_counts"]["jobs"] == 2

    expected["jobs"] = 999_999
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["state_snapshots"][0]["schema"]["tables"] = expected
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="row-count contract"):
        validate_manifest(manifest, "linkedin", require_table_counts=True)


def test_runtime_manifest_count_contract_defaults_to_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, input_root, state_root = _write_manifest(tmp_path)
    monkeypatch.setenv("RUNR_ACQUISITION_INPUT_ROOT", str(input_root))
    monkeypatch.setenv("RUNR_ACQUISITION_STATE_ROOT", str(state_root))

    result = validate_manifest(manifest, "linkedin")

    assert "table_counts" not in result["states"][0]
    assert result["require_table_counts"] is False


def test_evidence_report_records_release_units_counts_and_rollback_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, input_root, state_root = _write_manifest(tmp_path)
    monkeypatch.setenv("RUNR_ACQUISITION_INPUT_ROOT", str(input_root))
    monkeypatch.setenv("RUNR_ACQUISITION_STATE_ROOT", str(state_root))
    monkeypatch.setenv("RUNR_SOURCE_VERSION", "abc123release")
    monkeypatch.setenv("RUNR_EMPLOYER_STATE_DIR", "/srv/runr/state/employer")
    monkeypatch.delenv("RUNR_COMPANY_IDENTITY_CROSSWALK", raising=False)

    (state_root / "versions" / "gen-1").mkdir(parents=True)
    release_two = state_root / "versions" / "gen-2"
    release_two.mkdir()
    try:
        os.symlink(release_two, state_root / "active", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this host")

    report = capture_evidence(manifest, "linkedin")

    assert report["schema_version"] == "runr.acquisition.pre-mutation-evidence.v1"
    assert report["release"]["declared_commit"] is None
    assert report["release"]["source_version_override"] == "abc123release"

    by_unit = {unit["unit"]: unit for unit in report["units"]}
    assert by_unit["runr-acquisition-linkedin"]["exec_start"] == [
        "ExecStart=/opt/runr/deploy/run-acquisition-source.sh linkedin"
    ]
    assert by_unit["runr-acquisition-employer"]["exec_start"] == [
        "ExecStart=/opt/runr/deploy/run-acquisition-source.sh employer"
    ]
    assert by_unit["runr-acquisition-publisher"]["exec_start"] == [
        "ExecStart=/opt/runr/deploy/run-acquisition-publisher.sh"
    ]
    for unit in report["units"]:
        for assignment in unit["environment_names"]:
            assert "=" not in assignment

    assert report["state_overrides"]["values_recorded"] is False
    assert "RUNR_EMPLOYER_STATE_DIR" in report["state_overrides"]["present"]
    assert "RUNR_COMPANY_IDENTITY_CROSSWALK" not in report["state_overrides"]["present"]

    assert report["active_state"]["target"] == str(release_two.resolve())
    assert report["rollback_target"] == str((state_root / "versions" / "gen-1").resolve())

    state_record = report["states"][0]
    assert state_record["present"] is True
    assert state_record["tables"]["jobs"] == 2
    assert len(state_record["sha256"]) == 64

    report_path = tmp_path / "evidence.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    assert json.loads(report_path.read_text(encoding="utf-8"))["schema_version"] == report["schema_version"]


def test_enrichment_role_maps_identity_inputs_to_runtime_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_root = tmp_path / "inputs"
    state_root = tmp_path / "state"
    input_root.mkdir()
    (state_root / "enrichment").mkdir(parents=True)
    registry = input_root / "company_registry_canonical.csv"
    registry.write_bytes(b"canonical_CompanyID,company_name\ncompany-1,Alpha\n")
    resolution = state_root / "enrichment" / "linkedin_id_resolution.sqlite3"
    with sqlite3.connect(resolution) as connection:
        connection.execute("CREATE TABLE url_resolution (id INTEGER)")
        connection.execute("CREATE TABLE request_log (id INTEGER)")
        connection.execute("CREATE TABLE run_meta (id INTEGER)")

    payload = {
        "schema_version": "runr.acquisition.data-manifest.v1",
        "seed_inputs": [
            {
                "logical_name": "company_registry_canonical",
                "repo_path": None,
                "server_path": "/srv/runr/shared/inputs/company_registry_canonical.csv",
                "bytes": registry.stat().st_size,
                "sha256": _sha256(registry),
            }
        ],
        "state_snapshots": [
            {
                "logical_name": "linkedin_id_resolution_state",
                "server_path": "/srv/runr/state/enrichment/linkedin_id_resolution.sqlite3",
                "bytes": resolution.stat().st_size,
                "sha256": _sha256(resolution),
                "schema": {},
            }
        ],
    }
    manifest = tmp_path / "acquisition-data-manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("RUNR_ACQUISITION_INPUT_ROOT", str(input_root))
    monkeypatch.setenv("RUNR_ACQUISITION_STATE_ROOT", str(state_root))

    result = validate_manifest(manifest, "enrichment")

    assert result["seeds"][0]["logical_name"] == "company_registry_canonical"
    assert Path(result["states"][0]["path"]) == (state_root / "enrichment" / "linkedin_id_resolution.sqlite3").resolve()


def test_units_route_wrappers_to_producer_entrypoints() -> None:
    linkedin_unit = (SYSTEMD / "runr-acquisition-linkedin.service").read_text(encoding="utf-8")
    employer_unit = (SYSTEMD / "runr-acquisition-employer.service").read_text(encoding="utf-8")
    publisher_unit = (SYSTEMD / "runr-acquisition-publisher.service").read_text(encoding="utf-8")
    assert "ExecStart=/opt/runr/deploy/run-acquisition-source.sh linkedin" in linkedin_unit
    assert "ExecStart=/opt/runr/deploy/run-acquisition-source.sh employer" in employer_unit
    assert "ExecStart=/opt/runr/deploy/run-acquisition-publisher.sh" in publisher_unit

    source_wrapper = (DEPLOY / "run-acquisition-source.sh").read_text(encoding="utf-8")
    publisher_wrapper = (DEPLOY / "run-acquisition-publisher.sh").read_text(encoding="utf-8")
    assert "scripts/run_manifested_linkedin.py" in source_wrapper
    assert "--require-existing-state" in source_wrapper
    assert "scripts/master_linkedin_jobs_catalog.py" not in source_wrapper
    assert "scripts/run_manifested_employer.py" in source_wrapper
    assert "scripts/publish_producer_states.py" in publisher_wrapper
    assert "--linkedin-state" in publisher_wrapper and "--employer-state" in publisher_wrapper

    catalog = (DEPLOY / "acquisition-data-manifest.json").read_text(encoding="utf-8")
    assert "run_manifested_linkedin.py" in catalog
    assert "--require-existing-state" in catalog

    contract = json.loads((DEPLOY / "vps-runtime-contract.json").read_text(encoding="utf-8"))
    acquisition = contract["roles"]["acquisition"]
    assert acquisition["collector_entrypoints"] == [
        "/opt/runr/deploy/run-acquisition-source.sh linkedin",
        "/opt/runr/deploy/run-acquisition-source.sh employer",
        "/opt/runr/deploy/run-acquisition-publisher.sh",
    ]
    assert acquisition["state_restore_entrypoint"] == "/opt/runr/deploy/restore-acquisition-states.sh"
