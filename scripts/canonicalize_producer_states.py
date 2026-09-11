"""Create immutable, versioned producer-state copies with canonical company IDs.

The source registry and producer SQLite files are read-only inputs.  This
command writes new copies, carries the original identity as evidence, and
emits a JSON crosswalk/report suitable for a later Turso migration.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.application.company_identity_canonicalization import (
    SCHEMA_VERSION,
    CompanyCrosswalk,
    _strong_identity_keys,
    canonicalize_registry_rows,
    resolve_company_id,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = PROJECT_ROOT / "data" / "acquisition" / "inputs" / "company_registry_canonical.csv"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_registry(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"registry has no header: {path}")
        return [dict(row) for row in reader], list(reader.fieldnames)


def _write_registry(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    extra = sorted({str(key) for row in rows for key in row if str(key) not in fieldnames})
    columns = [*fieldnames, *extra]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            serialized = {
                key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                if isinstance(value, (list, dict)) else value
                for key, value in row.items()
            }
            writer.writerow(serialized)


def _json_load(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        decoded = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        decoded = {}
    return dict(decoded) if isinstance(decoded, dict) else {}


def _canonical_payload(payload: dict[str, Any], crosswalk: CompanyCrosswalk) -> tuple[dict[str, Any], bool]:
    identity_keys = [key for _identity_type, key in _strong_identity_keys(payload)]
    resolved = resolve_company_id(payload, crosswalk)
    old_id = str(payload.get("canonical_CompanyID") or payload.get("canonical_company_id") or "").strip()
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "original_company_id": old_id,
        "identity_keys": identity_keys,
        "resolved_company_id": resolved,
        "resolution_source": "company_identity_crosswalk",
    }
    updated = dict(payload)
    updated["canonical_CompanyID"] = resolved
    updated["canonical_company_id"] = resolved
    updated["source_identity_crosswalk"] = evidence
    if old_id and old_id != resolved:
        updated["canonical_company_id_before"] = old_id
    return updated, updated != payload


def _integrity_and_counts(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(str(path))
    try:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        tables = {
            str(row[0]): int(connection.execute(f"SELECT COUNT(*) FROM \"{row[0]}\"").fetchone()[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        }
        return {"integrity_check": integrity, "tables": tables}
    finally:
        connection.close()


def _backup_state(source: Path, destination: Path, kind: str, crosswalk: CompanyCrosswalk) -> dict[str, Any]:
    source = source.resolve()
    destination = destination.resolve()
    if source == destination:
        raise ValueError(f"refusing to overwrite producer state: {source}")
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    source_before = _integrity_and_counts(source)
    source_connection = sqlite3.connect(str(source))
    destination_connection = sqlite3.connect(str(destination))
    destination_connection.row_factory = sqlite3.Row
    updated_rows = 0
    try:
        source_connection.backup(destination_connection)
        destination_connection.commit()
        if kind == "linkedin":
            targets = [
                ("job_company_observations", "row_json"),
                ("jobs", "job_json"),
                ("source_company_groups", ""),
            ]
        elif kind == "employer":
            targets = [("companies", "payload_json"), ("jobs", "payload_json")]
        else:
            raise ValueError(f"unknown producer state kind: {kind}")

        for table, payload_column in targets:
            columns = {str(row[1]) for row in destination_connection.execute(f"PRAGMA table_info(\"{table}\")")}
            if payload_column not in columns:
                continue
            # These producer tables are ordinary rowid tables.  Using rowid
            # avoids accidentally updating multiple observations that share a
            # component of a composite primary key.
            select_key = "rowid"
            rows = destination_connection.execute(
                f"SELECT {select_key}, \"{payload_column}\" FROM \"{table}\""
            ).fetchall()
            for key, raw_payload in rows:
                updated_payload, changed = _canonical_payload(_json_load(raw_payload), crosswalk)
                if changed:
                    destination_connection.execute(
                        f"UPDATE \"{table}\" SET \"{payload_column}\"=? WHERE \"{select_key}\"=?",
                        (json.dumps(updated_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")), key),
                    )
                    updated_rows += 1

            for direct_column in ("canonical_company_id", "canonical_CompanyID", "primary_canonical_company_id"):
                if direct_column not in columns:
                    continue
                for row in destination_connection.execute(
                    f"SELECT {select_key}, * FROM \"{table}\""
                ).fetchall():
                    row_map = dict(row)
                    if direct_column == "primary_canonical_company_id":
                        source_id = str(row_map.get(direct_column) or "").strip()
                        linkedin_id = str(row_map.get("linkedin_company_id") or "").strip()
                        resolved = (
                            str(crosswalk.mapping_by_identity.get(f"old-company:{source_id}") or "").strip()
                            or str(crosswalk.mapping_by_identity.get(f"linkedin-org:{linkedin_id}") or "").strip()
                            or source_id
                        )
                    else:
                        resolved = resolve_company_id(row_map, crosswalk)
                    destination_connection.execute(
                        f"UPDATE \"{table}\" SET \"{direct_column}\"=? WHERE \"{select_key}\"=?",
                        (resolved, row_map[select_key]),
                    )
        destination_connection.commit()
    finally:
        source_connection.close()
        destination_connection.close()

    after = _integrity_and_counts(destination)
    if after["integrity_check"] != "ok":
        raise RuntimeError(f"canonicalized state failed integrity check: {destination}")
    return {
        "source": str(source),
        "source_sha256": _sha256(source),
        "source_integrity": source_before,
        "destination": str(destination),
        "destination_sha256": _sha256(destination),
        "destination_integrity": after,
        "payload_rows_updated": updated_rows,
    }


def _mapping_document(registry: Path, crosswalk: CompanyCrosswalk) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": _now(),
        "registry": str(registry.resolve()),
        "registry_sha256": _sha256(registry),
        "mapping_by_identity": dict(sorted(crosswalk.mapping_by_identity.items())),
        "mapping_by_row": {str(key): value for key, value in sorted(crosswalk.mapping_by_row.items())},
        "report": crosswalk.report,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    registry = args.registry.resolve()
    linkedin_state = args.linkedin_state.resolve()
    employer_state = args.employer_state.resolve()
    output_dir = args.output_dir.resolve()

    rows, fieldnames = _load_registry(registry)
    crosswalk = canonicalize_registry_rows(rows)
    canonical_registry = output_dir / "company_registry_canonicalized.csv"
    mapping_path = output_dir / "company_identity_crosswalk.json"
    linkedin_destination = output_dir / f"{linkedin_state.stem}.canonicalized.db"
    employer_destination = output_dir / f"{employer_state.stem}.canonicalized.db"
    if args.dry_run:
        return {
            "schema_version": SCHEMA_VERSION,
            "created_at": _now(),
            "dry_run": True,
            "registry": str(registry),
            "registry_sha256": _sha256(registry),
            "would_write": [str(canonical_registry), str(mapping_path), str(linkedin_destination), str(employer_destination)],
            "crosswalk_report": crosswalk.report,
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in (canonical_registry, mapping_path, linkedin_destination, employer_destination):
        if path.exists():
            raise FileExistsError(f"refusing to replace existing canonicalization output: {path}")

    _write_registry(canonical_registry, crosswalk.rows, fieldnames)
    mapping_path.write_text(json.dumps(_mapping_document(registry, crosswalk), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    state_reports = [
        _backup_state(linkedin_state, linkedin_destination, "linkedin", crosswalk),
        _backup_state(employer_state, employer_destination, "employer", crosswalk),
    ]
    report = {
        "schema_version": SCHEMA_VERSION,
        "created_at": _now(),
        "dry_run": bool(args.dry_run),
        "registry": str(registry),
        "registry_sha256": _sha256(registry),
        "canonical_registry": str(canonical_registry),
        "canonical_registry_sha256": _sha256(canonical_registry),
        "mapping": str(mapping_path),
        "states": state_reports,
        "crosswalk_report": crosswalk.report,
    }
    report_path = output_dir / "canonicalization_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--linkedin-state", type=Path, required=True)
    parser.add_argument("--employer-state", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true", help="Record the report field; outputs remain versioned copies.")
    return parser


if __name__ == "__main__":
    parsed = build_parser().parse_args()
    print(json.dumps(run(parsed), ensure_ascii=False, indent=2))
