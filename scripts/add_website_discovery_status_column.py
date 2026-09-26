"""Append the final website-discovery status column to the master CSV.

This is an offline reconciliation step. It reads the existing CSV and the
already-written website-discovery JSONL logs; it performs no web requests and
does not touch the CompanyEnrich database.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from discover_websites_from_web_search import (
    DEFAULT_CSV,
    atomic_write_csv,
    clean,
    discovery_key_for_row,
    load_csv,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DISCOVERY_DIR = (
    ROOT
    / "Company-Urls"
    / "Master-Company-Url"
    / "cleaned"
    / "linkedin_company_enrichment_state"
    / "website_discovery"
)
BASE_LOG_NAME = "bing_web_search_consensus_results.jsonl"
DEEP_LOG_NAME = "ambiguous_bing_recovery_results.jsonl"
STATUS_COLUMN = "website_discovery_status"


def load_latest_statuses(path: Path) -> dict[str, str]:
    """Load the last valid status for each discovery key from a JSONL log."""
    statuses: dict[str, str] = {}
    if not path.exists():
        return statuses

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                raise ValueError(f"Invalid JSON in {path} line {line_number}") from None
            key = clean(record.get("slug")).casefold()
            status = clean(record.get("status")).casefold()
            if key and status:
                statuses[key] = status
    return statuses


def status_for_row(row: dict[str, str], statuses: dict[str, str]) -> str:
    """Return a visible status for every row, using the final CSV website value."""
    if clean(row.get("website_url")):
        return "found"
    return statuses.get(discovery_key_for_row(row), "not_checked")


def reconcile(csv_path: Path, discovery_dir: Path, write: bool) -> Counter[str]:
    fieldnames, rows = load_csv(csv_path)
    if "website_url" not in fieldnames:
        raise ValueError("CSV is missing required website_url column")

    statuses = load_latest_statuses(discovery_dir / BASE_LOG_NAME)
    statuses.update(load_latest_statuses(discovery_dir / DEEP_LOG_NAME))

    if STATUS_COLUMN not in fieldnames:
        fieldnames.append(STATUS_COLUMN)

    counts: Counter[str] = Counter()
    for row in rows:
        row[STATUS_COLUMN] = status_for_row(row, statuses)
        counts[row[STATUS_COLUMN]] += 1

    if write:
        atomic_write_csv(csv_path, fieldnames, rows)

    expected_width = len(fieldnames)
    if any(len(row) != expected_width for row in rows):
        raise AssertionError("CSV rows do not match the reconciled header width")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--discovery-dir", type=Path, default=DEFAULT_DISCOVERY_DIR)
    parser.add_argument(
        "--write",
        action="store_true",
        help="write the new final column; without this flag only validate and preview",
    )
    args = parser.parse_args()

    counts = reconcile(args.csv, args.discovery_dir, write=args.write)
    action = "Updated" if args.write else "Preview"
    print(f"{action}: {args.csv}")
    print(f"{STATUS_COLUMN}: {dict(sorted(counts.items()))}")
    print(f"rows: {sum(counts.values())}")


if __name__ == "__main__":
    main()
