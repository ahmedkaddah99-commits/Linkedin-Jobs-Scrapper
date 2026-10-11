"""Summarize employer coverage audit JSON without exposing company or job rows."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def _percentage(count: int, total: int) -> float:
    return round((count / total * 100.0), 2) if total else 0.0


def summarize(payload: dict[str, Any]) -> dict[str, Any]:
    rows = [
        row
        for classification_rows in payload.get("by_classification", {}).values()
        for row in classification_rows
    ]
    company_counts = Counter(str(row.get("terminal_classification") or "unknown") for row in rows)
    methods: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        seen_methods: set[str] = set()
        for attempt in row.get("attempts") or []:
            method = str(attempt.get("connector_family") or attempt.get("transport") or "unknown")
            method_counts = methods[method]
            method_counts["attempts"] += 1
            accepted = int(attempt.get("accepted_count") or 0)
            method_counts["jobs_accepted"] += accepted
            if attempt.get("pages_attempted") is not None:
                method_counts["attempts_with_page_measurement"] += 1
                method_counts["listing_pages_fetched"] += int(attempt["pages_attempted"] or 0)
            method_counts["detail_failures"] += int(attempt.get("pending_detail_count") or 0)
            if accepted > 0:
                method_counts["successful_attempts"] += 1
            elif bool(attempt.get("complete")):
                method_counts["successful_zero_job_attempts"] += 1
            else:
                method_counts["unsuccessful_attempts"] += 1
            if method not in seen_methods:
                method_counts["companies_attempted"] += 1
                seen_methods.add(method)

    total_companies = len(rows)
    return {
        "companies": {
            "total": total_companies,
            "outcomes": {
                outcome: {"count": count, "percentage": _percentage(count, total_companies)}
                for outcome, count in sorted(company_counts.items())
            },
        },
        "jobs": {"persisted": sum(int(row.get("persisted_job_count") or 0) for row in rows)},
        "methods": {
            method: {
                **dict(counts),
                "success_with_jobs_percentage": _percentage(
                    counts["successful_attempts"], counts["attempts"]
                ),
                "successful_zero_job_percentage": _percentage(
                    counts["successful_zero_job_attempts"], counts["attempts"]
                ),
                "unsuccessful_percentage": _percentage(
                    counts["unsuccessful_attempts"], counts["attempts"]
                ),
            }
            for method, counts in sorted(methods.items())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_json", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.audit_json.read_text(encoding="utf-8"))
    print(json.dumps(summarize(payload), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
