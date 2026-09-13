"""Audit real (historical) employer state read-only and report per-company coverage.

This script opens the authoritative employer state database in SQLite read-only
mode.  It never initializes, migrates, or writes the original file, so it is
safe to run against the preserved historical state without a state helper.

Historical rows predate the coverage-receipt work, so none can be proven
``confirmed_complete``.  Each row is classified conservatively:
  * positive collection -> partial (unproven completeness)
  * genuine empty page -> partial (suspicious empty, not a confirmed zero)
  * timeout / incomplete / discovery failure -> failed
  * challenge / block -> blocked
  * no usable evidence -> unknown
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.acquisition.employer_coverage import COVERAGE_CLASSIFICATIONS, classify_legacy_result


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_only_uri(path: Path) -> str:
    return "file:" + str(path.resolve()).replace("\\", "/") + "?mode=ro"


def _load_rows(path: Path) -> list[dict[str, Any]]:
    db = sqlite3.connect(_read_only_uri(path), uri=True)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute("SELECT company_key, status, payload_json FROM companies ORDER BY company_key").fetchall()
    finally:
        db.close()
    result: list[dict[str, Any]] = []
    for row in rows:
        key = str(row["company_key"])
        status = str(row["status"] or "unknown")
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        jobs = payload.get("jobs") or []
        result.append(
            {
                "company_key": key,
                "status": status,
                "jobs": jobs,
                "targets": payload.get("targets") or [],
                "failures": payload.get("failures") or [],
                "persisted_job_count": len(jobs) if isinstance(jobs, list) else 0,
            }
        )
    return result


def build_real_report(path: Path) -> dict[str, Any]:
    rows = _load_rows(path)
    classification_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    failure_categories: Counter[str] = Counter()
    by_classification: dict[str, list[dict[str, Any]]] = {cls: [] for cls in COVERAGE_CLASSIFICATIONS}

    for row in rows:
        classification = classify_legacy_result(row)
        classification_counts[classification] += 1
        status_counts[row["status"]] += 1
        for failure in row["failures"]:
            if isinstance(failure, dict):
                stage = str(failure.get("stage") or "unknown")
                error = str(failure.get("error") or "unknown")
                failure_categories[f"{stage}:{error}"] += 1
        by_classification[classification].append(
            {
                "company_id": row["company_key"],
                "status": row["status"],
                "persisted_job_count": row["persisted_job_count"],
                "target_count": len(row["targets"]),
                "failures": row["failures"][:5],
            }
        )

    return {
        "mode": "read_only_real_employer_coverage_audit",
        "state_db": str(path),
        "generated_at": _utc_now(),
        "company_count": len(rows),
        "classification_counts": {cls: classification_counts.get(cls, 0) for cls in COVERAGE_CLASSIFICATIONS},
        "status_counts": dict(status_counts),
        "top_failure_categories": [
            {"category": category, "count": count}
            for category, count in failure_categories.most_common(20)
        ],
        "by_classification": by_classification,
        "disposition": {
            "confirmed_complete": {
                "count": classification_counts.get("confirmed_complete", 0),
                "note": "Historical rows predate coverage receipts; zero are provably complete offline.",
            },
            "partial": {
                "count": classification_counts.get("partial", 0),
                "note": "Jobs collected but pagination/partition completeness unproven.",
            },
            "blocked": {
                "count": classification_counts.get("blocked", 0),
                "note": "Active challenge/block.",
            },
            "failed": {
                "count": classification_counts.get("failed", 0),
                "note": "Timeout, incomplete, or discovery failure.",
            },
            "unknown": {
                "count": classification_counts.get("unknown", 0),
                "note": "No usable evidence.",
            },
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-db", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not args.state_db.is_file():
        raise SystemExit(f"state database not found: {args.state_db}")
    report = build_real_report(args.state_db)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
