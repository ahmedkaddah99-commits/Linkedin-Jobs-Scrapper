"""Build a local, read-only RC-003 company registry reconciliation report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.application.company_registry_reconciliation import (
    read_master_csv,
    reconcile_master_rows,
    summarise_registry_report,
)


def _read_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def build_report(input_path: str, *, application_registry_path: str | None = None, dispositions_path: str | None = None) -> dict[str, Any]:
    rows, header, source_sha256 = read_master_csv(input_path)
    report = reconcile_master_rows(
        rows,
        application_registry=_read_json(application_registry_path),
        shared_organization_dispositions=_read_json(dispositions_path),
    )
    report["input"] = {
        "path": str(Path(input_path).resolve()),
        "sha256": source_sha256,
        "rows": len(rows),
        "columns": len(header),
        "header": header,
    }
    report["application_registry_supplied"] = bool(application_registry_path)
    report["shared_organization_review_supplied"] = bool(dispositions_path)
    return summarise_registry_report(report)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Explicit local UTF-8 master CSV path")
    parser.add_argument("--output", required=True, help="JSON evidence output path")
    parser.add_argument("--application-registry", help="Optional local JSON export of application companies/identity keys")
    parser.add_argument("--dispositions", help="Optional local JSON reviewed shared-organization dispositions")
    args = parser.parse_args()
    report = build_report(
        args.input,
        application_registry_path=args.application_registry,
        dispositions_path=args.dispositions,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output.resolve()), "counts": report["counts"], "input": report["input"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
