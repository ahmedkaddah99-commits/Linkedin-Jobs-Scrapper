"""Validate acquisition inputs and restored state without contacting providers.

This is intentionally read-only.  It validates immutable seed hashes, required
paths, SQLite table contracts, per-table row-count contracts (``--require-table-counts``),
and (with ``--deep``) full SQLite integrity and state hashes.  ``--evidence-report``
captures read-only pre-mutation restore evidence.  It does not create a
database, run migrations, or start a collector.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path(__file__).with_name("acquisition-data-manifest.json")
CONTRACT_PATH = Path(__file__).with_name("vps-runtime-contract.json")
UNIT_DIR = Path(__file__).with_name("systemd")
EVIDENCE_SCHEMA_VERSION = "runr.acquisition.pre-mutation-evidence.v1"
STATE_OVERRIDE_ENV_NAMES = (
    "RUNR_ACQUISITION_MANIFEST",
    "RUNR_ACQUISITION_DATA_MANIFEST",
    "RUNR_ACQUISITION_INPUT_ROOT",
    "RUNR_ACQUISITION_STATE_ROOT",
    "RUNR_ACQUISITION_STATE_ROOT_PHYSICAL",
    "RUNR_ACQUISITION_RAW_STATE_ROOT",
    "RUNR_ACQUISITION_EXPORT_ROOT",
    "RUNR_ACQUISITION_RECEIPT_ROOT",
    "RUNR_ACQUISITION_LOCK_ROOT",
    "RUNR_ACQUISITION_INCLUDE_SINGLE_SOURCE",
    "RUNR_LINKEDIN_STATE_DIR",
    "RUNR_LINKEDIN_STATE_DB",
    "RUNR_EMPLOYER_STATE_DIR",
    "RUNR_EMPLOYER_STATE_DB",
    "RUNR_COMPANY_IDENTITY_CROSSWALK",
)
ROOT_MAP = {
    "/srv/runr/shared/inputs": "RUNR_ACQUISITION_INPUT_ROOT",
    "/srv/runr/state": "RUNR_ACQUISITION_STATE_ROOT",
    "/srv/runr/exports": "RUNR_ACQUISITION_EXPORT_ROOT",
    "/srv/runr/backups": "RUNR_ACQUISITION_BACKUP_ROOT",
}
ROLE_REQUIREMENTS = {
    "linkedin": {"seed_inputs": {"company_sources_linkedin_ids"}, "states": {"linkedin_authoritative_state"}},
    "employer": {"seed_inputs": {"company_sources_linkedin_ids"}, "states": {"employer_state"}},
    "enrichment": {"seed_inputs": {"company_registry_canonical"}, "states": {"linkedin_id_resolution_state"}},
}


def _sha256(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_path(server_path: str, roots: dict[str, Path]) -> Path:
    normalized = server_path.replace("\\", "/")
    for server_root, env_name in ROOT_MAP.items():
        if normalized == server_root or normalized.startswith(server_root + "/"):
            suffix = normalized[len(server_root) :].lstrip("/")
            return roots[env_name] / Path(suffix)
    return Path(server_path)


def _resolve_roots() -> dict[str, Path]:
    return {
        env_name: Path(os.environ[env_name]).expanduser().resolve()
        for env_name in ROOT_MAP.values()
        if os.environ.get(env_name)
    }


def _resolve_seed_path(item: dict[str, Any], manifest_path: Path, roots: dict[str, Path]) -> Path:
    repo_path = item.get("repo_path")
    if repo_path and not roots.get("RUNR_ACQUISITION_INPUT_ROOT"):
        return (manifest_path.parent.parent / repo_path).resolve()
    return _runtime_path(str(item["server_path"]), roots).resolve()


def _validate_seed(item: dict[str, Any], manifest_path: Path, roots: dict[str, Path]) -> dict[str, Any]:
    path = _resolve_seed_path(item, manifest_path, roots)
    if not path.is_file():
        raise FileNotFoundError(f"required seed input is missing: {path}")
    actual_size = path.stat().st_size
    if actual_size != int(item["bytes"]):
        raise ValueError(f"seed input size mismatch for {path}: expected {item['bytes']}, got {actual_size}")
    actual_hash = _sha256(path)
    if actual_hash != item["sha256"]:
        raise ValueError(f"seed input SHA-256 mismatch for {path}: expected {item['sha256']}, got {actual_hash}")
    return {"logical_name": item["logical_name"], "path": str(path), "bytes": actual_size, "sha256": actual_hash}


def _validate_state(
    item: dict[str, Any],
    roots: dict[str, Path],
    *,
    deep: bool,
    allow_state_drift: bool = False,
    require_table_counts: bool = False,
) -> dict[str, Any]:
    path = _runtime_path(str(item["server_path"]), roots).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"required state database is missing: {path}")
    actual_size = path.stat().st_size
    if not allow_state_drift and actual_size != int(item["bytes"]):
        raise ValueError(f"state database size mismatch for {path}: expected {item['bytes']}, got {actual_size}")
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5)
    table_counts: dict[str, int] = {}
    try:
        actual_tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        schema = item.get("schema") or {}
        expected_tables = set(schema.get("tables", {}))
        supported_table_sets = schema.get("supported_tables") or []
        supported = [set(table_set) for table_set in supported_table_sets if isinstance(table_set, list)]
        if expected_tables and actual_tables not in (supported or [expected_tables]):
            raise ValueError(
                f"state database table mismatch for {path}: expected one of "
                f"{[sorted(table_set) for table_set in (supported or [expected_tables])]}, got {sorted(actual_tables)}"
            )
        if require_table_counts:
            for table_name, expected_count in (schema.get("tables") or {}).items():
                actual_count = int(connection.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0])
                if actual_count != int(expected_count):
                    raise ValueError(
                        f"state database row-count contract failed for {path}: "
                        f"table {table_name} expected {expected_count}, got {actual_count}"
                    )
                table_counts[str(table_name)] = actual_count
        if deep:
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            if integrity != "ok":
                raise ValueError(f"SQLite integrity check failed for {path}: {integrity}")
    finally:
        connection.close()
    result = {"logical_name": item["logical_name"], "path": str(path), "bytes": actual_size}
    if table_counts:
        result["table_counts"] = table_counts
    if deep:
        actual_hash = _sha256(path)
        if not allow_state_drift and actual_hash != item["sha256"]:
            raise ValueError(f"state database SHA-256 mismatch for {path}: expected {item['sha256']}, got {actual_hash}")
        result["sha256"] = actual_hash
    return result


def validate_manifest(
    manifest_path: Path,
    role: str,
    *,
    deep: bool = False,
    allow_state_drift: bool = False,
    require_table_counts: bool = False,
) -> dict[str, Any]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "runr.acquisition.data-manifest.v1":
        raise ValueError(f"unsupported acquisition data manifest schema: {payload.get('schema_version')}")
    roots = _resolve_roots()
    if role == "all":
        requirements = {
            "seed_inputs": {
                "company_registry_canonical",
                "company_sources_linkedin_ids",
            },
            "states": {"linkedin_authoritative_state", "employer_state"},
        }
    else:
        requirements = ROLE_REQUIREMENTS[role]
    seeds = {item["logical_name"]: item for item in payload.get("seed_inputs", [])}
    states = {item["logical_name"]: item for item in payload.get("state_snapshots", [])}
    # Older test/recovery manifests predate the explicit LinkedIn evidence
    # entries.  The production manifest contains both and therefore makes
    # them mandatory without breaking validation of historical fixtures.
    if role in {"linkedin", "all"} and {"linkedin_pagination_report", "linkedin_filters_report"}.issubset(seeds):
        requirements["seed_inputs"].update({"linkedin_pagination_report", "linkedin_filters_report"})
    checked_seeds = [_validate_seed(seeds[name], manifest_path, roots) for name in sorted(requirements["seed_inputs"])]
    checked_states = [
        _validate_state(
            states[name],
            roots,
            deep=deep,
            allow_state_drift=allow_state_drift,
            require_table_counts=require_table_counts,
        )
        for name in sorted(requirements["states"])
    ]
    return {
        "manifest": str(manifest_path.resolve()),
        "role": role,
        "deep": deep,
        "allow_state_drift": allow_state_drift,
        "require_table_counts": require_table_counts,
        "seeds": checked_seeds,
        "states": checked_states,
    }


def _unit_document(unit_name: str) -> dict[str, Any]:
    """Read a repo systemd unit and record command plus environment path names."""

    path = UNIT_DIR / f"{unit_name}.service"
    if not path.is_file():
        return {"unit": unit_name, "present": False}
    exec_start: list[str] = []
    environment_names: list[str] = []
    environment_files: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("ExecStart="):
            exec_start.append(stripped)
        elif stripped.startswith("EnvironmentFile="):
            environment_files.append(stripped.split("=", 1)[1].lstrip("-"))
        elif stripped.startswith("Environment="):
            assignment = stripped.split("=", 1)[1]
            # Environment path names only: values are intentionally dropped.
            environment_names.append(assignment.split("=", 1)[0])
    return {
        "unit": unit_name,
        "present": True,
        "exec_start": exec_start,
        "environment_names": environment_names,
        "environment_files": environment_files,
    }


def _evidence_state(item: dict[str, Any], roots: dict[str, Path]) -> dict[str, Any]:
    path = _runtime_path(str(item["server_path"]), roots).resolve()
    record: dict[str, Any] = {
        "logical_name": item["logical_name"],
        "declared_server_path": str(item["server_path"]),
        "path": str(path),
        "present": path.is_file(),
    }
    if not record["present"]:
        return record
    record["bytes"] = path.stat().st_size
    record["sha256"] = _sha256(path)
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5)
    try:
        record["integrity_check"] = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        record["tables"] = {
            str(row[0]): int(connection.execute(f'SELECT COUNT(*) FROM "{row[0]}"').fetchone()[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        }
    finally:
        connection.close()
    return record


def capture_evidence(manifest_path: Path, role: str) -> dict[str, Any]:
    """Read-only pre-mutation restore evidence: release, units, states, rollback target."""

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    roots = _resolve_roots()
    state_root = roots.get("RUNR_ACQUISITION_STATE_ROOT")
    if state_root is None:
        state_root = Path(payload["server_roots"]["state_root"])

    active_link = state_root / "active"
    active_target: str | None = None
    if active_link.is_symlink():
        active_target = str(Path(os.readlink(active_link)).resolve())

    rollback_target: str | None = None
    versions_root = state_root / "versions"
    if versions_root.is_dir():
        candidates: list[Path] = []
        for entry in versions_root.iterdir():
            if not entry.is_dir():
                continue
            if active_target is not None and str(entry.resolve()) == active_target:
                continue
            candidates.append(entry)
        if candidates:
            rollback_target = str(max(candidates, key=lambda item: item.stat().st_mtime).resolve())

    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8")) if CONTRACT_PATH.is_file() else {}
    acquisition = contract.get("roles", {}).get("acquisition", {})
    units = [
        _unit_document("runr-acquisition-linkedin"),
        _unit_document("runr-acquisition-employer"),
        _unit_document("runr-acquisition-publisher"),
        _unit_document("runr-acquisition-backup"),
    ]

    seeds = {item["logical_name"]: item for item in payload.get("seed_inputs", [])}
    states = {item["logical_name"]: item for item in payload.get("state_snapshots", [])}
    if role == "all":
        required_seeds = sorted(seeds)
        required_states = sorted(states)
    else:
        requirements = ROLE_REQUIREMENTS[role]
        required_seeds = sorted(set(requirements["seed_inputs"]))
        required_states = sorted(set(requirements["states"]))

    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "release": {
            "declared_branch": payload.get("branch"),
            "declared_commit": payload.get("release_commit"),
            "source_version_override": os.environ.get("RUNR_SOURCE_VERSION"),
            "release_commit_override": os.environ.get("RUNR_RELEASE_COMMIT"),
        },
        "units": units,
        "contract_entrypoints": {
            "collector_entrypoints": acquisition.get("collector_entrypoints", []),
            "state_restore_entrypoint": acquisition.get("state_restore_entrypoint"),
            "backup_entrypoint": acquisition.get("backup_entrypoint"),
            "backup_unit": acquisition.get("backup_unit"),
            "backup_timer": acquisition.get("backup_timer"),
            "active_state_root": acquisition.get("active_state_root"),
        },
        "state_overrides": {
            "present": sorted(name for name in STATE_OVERRIDE_ENV_NAMES if os.environ.get(name)),
            "values_recorded": False,
        },
        "active_state": {"path": str(active_link), "target": active_target},
        "rollback_target": rollback_target,
        "seeds": [_evidence_seed(seeds[name], manifest_path, roots) for name in required_seeds],
        "states": [_evidence_state(states[name], roots) for name in required_states],
    }


def _evidence_seed(item: dict[str, Any], manifest_path: Path, roots: dict[str, Path]) -> dict[str, Any]:
    path = _resolve_seed_path(item, manifest_path, roots)
    record: dict[str, Any] = {
        "logical_name": item["logical_name"],
        "declared_server_path": str(item["server_path"]),
        "path": str(path),
        "present": path.is_file(),
    }
    if record["present"]:
        record["bytes"] = path.stat().st_size
        record["sha256"] = _sha256(path)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--role", choices=("linkedin", "employer", "enrichment", "all"), required=True)
    parser.add_argument("--deep", action="store_true", help="also run SQLite integrity and state hash checks")
    parser.add_argument("--allow-state-drift", action="store_true", help="allow mutable producer state size/hash changes while retaining schema validation")
    parser.add_argument(
        "--require-table-counts",
        action="store_true",
        help="enforce the per-table row-count contract from the manifest before state activation",
    )
    parser.add_argument(
        "--evidence-report",
        type=Path,
        default=None,
        help="write a read-only pre-mutation evidence report (release, units, state overrides, counts, rollback target) to this path",
    )
    args = parser.parse_args()
    try:
        if args.evidence_report is not None:
            result = capture_evidence(args.manifest.resolve(), args.role)
            args.evidence_report.write_text(
                json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            result = validate_manifest(
                args.manifest.resolve(),
                args.role,
                deep=args.deep,
                allow_state_drift=args.allow_state_drift,
                require_table_counts=args.require_table_counts,
            )
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
