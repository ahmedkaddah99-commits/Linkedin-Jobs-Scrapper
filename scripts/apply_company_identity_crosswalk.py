"""Apply a previously reviewed company crosswalk to the durable acquisition store."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.repositories.sqlite_acquisition import SqliteAcquisitionStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, required=True, help="company_identity_crosswalk.json produced by canonicalize_producer_states.py")
    parser.add_argument("--database", type=Path, required=True, help="Local SQLite path, or the repository path used with Turso environment settings.")
    parser.add_argument("--actor", default="company_identity_crosswalk", help="Provenance label recorded with the migration.")
    return parser


def run(args: argparse.Namespace) -> dict:
    document = json.loads(args.mapping.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("crosswalk document must be an object")
    report = document.get("report") if isinstance(document.get("report"), dict) else {}
    result = SqliteAcquisitionStore(args.database).apply_company_identity_crosswalk(
        mapping_by_identity=document.get("mapping_by_identity") or {},
        merge_receipts=report.get("merge_receipts") or [],
        canonical_rows=report.get("canonical_rows") or [],
        provenance={
            "actor": args.actor,
            "mapping": str(args.mapping.resolve()),
            "schema_version": document.get("schema_version", ""),
            "registry_sha256": document.get("registry_sha256", ""),
        },
    )
    return {"mapping": str(args.mapping.resolve()), "database": str(args.database.resolve()), **result}


if __name__ == "__main__":
    print(json.dumps(run(build_parser().parse_args()), ensure_ascii=False, indent=2))
