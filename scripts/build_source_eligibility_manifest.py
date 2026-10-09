"""Build an offline, versioned source-eligibility manifest from one master snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.application.source_eligibility_manifest import (
    build_source_eligibility_manifest,
    read_master_snapshot,
    write_manifest_bundle,
)


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="one master CSV snapshot")
    parser.add_argument("--output", type=Path, required=True, help="immutable manifest JSON output")
    parser.add_argument("--raw-sidecar", type=Path, help="raw-column JSONL sidecar; defaults beside --output")
    parser.add_argument("--cycle-id", default="", help="immutable cycle label; defaults from the input hash")
    parser.add_argument("--as-of", default="", help="UTC evidence cut-off, for example 2026-09-06T00:00:00Z")
    parser.add_argument("--max-evidence-age-days", type=int, default=30)
    parser.add_argument("--registry-report", type=Path, help="RC-003 ownership review/report JSON")
    parser.add_argument("--backfill-report", type=Path, help="RC-004 mapping report; dry-run mappings stay pending")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_path = args.input.resolve()
    output_path = args.output.resolve()
    if output_path == input_path:
        raise SystemExit("Refusing to overwrite the master snapshot with its manifest")
    rows, fieldnames, input_sha256 = read_master_snapshot(input_path)
    raw_sidecar = (args.raw_sidecar or output_path.with_suffix(".raw.jsonl")).resolve()
    report = build_source_eligibility_manifest(
        rows,
        fieldnames,
        source_path=str(input_path),
        input_sha256=input_sha256,
        cycle_id=args.cycle_id,
        as_of=args.as_of or None,
        max_evidence_age_days=args.max_evidence_age_days,
        registry_report=_load_json(args.registry_report),
        backfill_report=_load_json(args.backfill_report),
        raw_sidecar_path=str(raw_sidecar),
    )
    persisted = write_manifest_bundle(output_path, report, raw_sidecar_path=raw_sidecar)
    print(
        json.dumps(
            {
                **persisted,
                "schema_version": report["schema_version"],
                "manifest_id": report["manifest_id"],
                "cycle_id": report["cycle_id"],
                "source_snapshot": report["source_snapshot"],
                "counts": report["counts"],
                "deductions": report["deductions"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
