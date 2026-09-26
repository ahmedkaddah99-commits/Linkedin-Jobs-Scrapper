"""Run the RC-004 company-ID backfill dry run or approved output copy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.application.company_id_backfill import (
    backfill_master_rows,
    read_csv_with_hash,
    write_backfill_outputs,
)


def _read_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def build_report(input_path: str, *, approved_mappings_path: str | None = None) -> tuple[list[dict[str, str]], list[str], dict[str, Any]]:
    rows, fieldnames, input_sha256 = read_csv_with_hash(input_path)
    report = backfill_master_rows(
        rows,
        source_path=str(Path(input_path).resolve()),
        input_sha256=input_sha256,
        approved_mappings=_read_json(approved_mappings_path),
    )
    report["input"] = {
        "path": str(Path(input_path).resolve()),
        "sha256": input_sha256,
        "rows": len(rows),
        "columns": len(fieldnames),
        "header": fieldnames,
    }
    return rows, fieldnames, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Explicit local master CSV path")
    parser.add_argument("--output", required=True, help="JSON dry-run report path")
    parser.add_argument("--approved-mappings", help="Reviewed JSON mapping manifest for output application")
    parser.add_argument("--apply-output", help="Write a new CSV copy; never the input path")
    parser.add_argument("--manifest-output", help="Mapping manifest path for --apply-output")
    args = parser.parse_args()
    rows, fieldnames, report = build_report(args.input, approved_mappings_path=args.approved_mappings)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    written = {}
    if args.apply_output:
        if not args.approved_mappings:
            raise ValueError("--apply-output requires --approved-mappings")
        manifest_path = args.manifest_output or str(output.with_name(f"{output.stem}.mapping-manifest.json"))
        written = write_backfill_outputs(
            rows,
            fieldnames,
            source_path=args.input,
            output_path=args.apply_output,
            manifest_path=manifest_path,
            report=report,
        )
    print(
        json.dumps(
            {
                "report": str(output.resolve()),
                "counts": report["counts"],
                "input": report["input"],
                "written": written,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
