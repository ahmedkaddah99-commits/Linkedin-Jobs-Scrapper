from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from backend.application.source_eligibility_manifest import (
    RAW_SIDECAR_SCHEMA_VERSION,
    SCHEMA_VERSION,
    _manifest_hash,
    load_manifest,
)
from deploy.validate_acquisition_runtime import validate_manifest


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


def _write_manifest(tmp_path: Path, *, corrupt_seed_hash: bool = False) -> tuple[Path, Path, Path]:
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
                "schema": {"tables": {table: 0 for table in LINKEDIN_TABLES}},
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
