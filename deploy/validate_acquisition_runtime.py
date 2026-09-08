"""Validate acquisition inputs and restored state without contacting providers.

This is intentionally read-only.  It validates immutable seed hashes, required
paths, SQLite table contracts, and (with ``--deep``) full SQLite integrity and
state hashes.  It does not create a database, run migrations, or start a
collector.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path(__file__).with_name("acquisition-data-manifest.json")
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


def _validate_state(item: dict[str, Any], roots: dict[str, Path], *, deep: bool) -> dict[str, Any]:
    path = _runtime_path(str(item["server_path"]), roots).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"required state database is missing: {path}")
    actual_size = path.stat().st_size
    if actual_size != int(item["bytes"]):
        raise ValueError(f"state database size mismatch for {path}: expected {item['bytes']}, got {actual_size}")
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5)
    try:
        actual_tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        expected_tables = set((item.get("schema") or {}).get("tables", {}))
        if expected_tables and actual_tables != expected_tables:
            raise ValueError(
                f"state database table mismatch for {path}: expected {sorted(expected_tables)}, got {sorted(actual_tables)}"
            )
        if deep:
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            if integrity != "ok":
                raise ValueError(f"SQLite integrity check failed for {path}: {integrity}")
    finally:
        connection.close()
    result = {"logical_name": item["logical_name"], "path": str(path), "bytes": actual_size}
    if deep:
        actual_hash = _sha256(path)
        if actual_hash != item["sha256"]:
            raise ValueError(f"state database SHA-256 mismatch for {path}: expected {item['sha256']}, got {actual_hash}")
        result["sha256"] = actual_hash
    return result


def validate_manifest(manifest_path: Path, role: str, *, deep: bool = False) -> dict[str, Any]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "runr.acquisition.data-manifest.v1":
        raise ValueError(f"unsupported acquisition data manifest schema: {payload.get('schema_version')}")
    roots = _resolve_roots()
    if role == "all":
        requirements = {
            "seed_inputs": {"company_registry_canonical", "company_sources_linkedin_ids"},
            "states": {"linkedin_authoritative_state", "employer_state"},
        }
    else:
        requirements = ROLE_REQUIREMENTS[role]
    seeds = {item["logical_name"]: item for item in payload.get("seed_inputs", [])}
    states = {item["logical_name"]: item for item in payload.get("state_snapshots", [])}
    checked_seeds = [_validate_seed(seeds[name], manifest_path, roots) for name in sorted(requirements["seed_inputs"])]
    checked_states = [_validate_state(states[name], roots, deep=deep) for name in sorted(requirements["states"])]
    return {"manifest": str(manifest_path.resolve()), "role": role, "deep": deep, "seeds": checked_seeds, "states": checked_states}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--role", choices=("linkedin", "employer", "enrichment", "all"), required=True)
    parser.add_argument("--deep", action="store_true", help="also run SQLite integrity and state hash checks")
    args = parser.parse_args()
    try:
        result = validate_manifest(args.manifest.resolve(), args.role, deep=args.deep)
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
