"""Offline publication-completeness audit over master-job data.

Read-only.  Evaluates each canonical job record with the source-independent
validator and writes a JSON + Markdown report.  Never writes to the input,
any live database, or any scraper state.

The audit deliberately separates *record completeness* from *source-scan
completeness*.  A collector that exited successfully is irrelevant here; only
the record's own fields determine its outcome.

Usage (project venv only):

    .venv\\Scripts\\python.exe scripts\\audit_job_publication_completeness.py `
        --input data/audit/master_jobs_sample.jsonl `
        --company-registry data/acquisition/inputs/company_registry_canonical.csv `
        --output data/audit/completeness_report `
        --format both
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.acquisition.job_publication_completeness import (
    STATUSES,
    CompletenessResult,
    validate_job_for_publication,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_records(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.casefold()
    if suffix == ".jsonl":
        records: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if isinstance(payload, list):
                records.extend(item for item in payload if isinstance(item, dict))
            elif isinstance(payload, dict):
                records.append(payload)
        return records
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict) and isinstance(payload.get("records"), list):
            return [item for item in payload["records"] if isinstance(item, dict)]
        raise ValueError(f"Unsupported JSON shape in {path}")
    if suffix == ".csv":
        return list(csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()))
    raise ValueError(f"Unsupported input type: {suffix}")


def load_company_registry(path: Path | None) -> set[str] | None:
    if path is None or not path.exists():
        return None
    rows = csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines())
    return {str(row.get("canonical_CompanyID") or "").strip() for row in rows if str(row.get("canonical_CompanyID") or "").strip()}


def _canonical_job_id(record: Mapping[str, Any]) -> str:
    return str(record.get("canonical_job_id") or record.get("job_id") or "").strip()


def _source(record: Mapping[str, Any]) -> str:
    return str(record.get("source") or record.get("source_ats") or "").strip() or "unknown"


def _company_id(record: Mapping[str, Any]) -> str:
    return str(record.get("canonical_company_id") or record.get("company_id") or "").strip()


def _is_published(record: Mapping[str, Any]) -> bool:
    if record.get("is_live") is True:
        return True
    state = str(record.get("publication_state") or record.get("publication") or "").strip().casefold()
    return state in {"published", "live", "public"}


def _pct(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 2) if denominator else 0.0


def run_audit(
    records: list[dict[str, Any]],
    *,
    company_registry: set[str] | None,
    now: datetime,
    min_description_chars: int = 80,
    stale_after_days: int = 90,
) -> dict[str, Any]:
    total = len(records)

    # Deduplicate by canonical job id, preserving first occurrence order.
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicate_identity_records = 0
    for record in records:
        key = _canonical_job_id(record)
        if key and key in seen:
            duplicate_identity_records += 1
            continue
        if key:
            seen.add(key)
        unique.append(record)

    results: list[CompletenessResult] = []
    for record in unique:
        results.append(
            validate_job_for_publication(
                record,
                now=now,
                company_registry=company_registry,
                min_description_chars=min_description_chars,
                stale_after_days=stale_after_days,
            )
        )

    outcome_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    source_outcome: dict[str, Counter[str]] = defaultdict(Counter)

    for record, result in zip(unique, results):
        outcome_counts[result.status] += 1
        src = _source(record)
        source_counts[src] += 1
        source_outcome[src][result.status] += 1
        for reason in result.reasons:
            reason_counts[reason.code] += 1

    publishable = [r for r in results if r.publishable]
    publishable_records = [rec for rec, r in zip(unique, results) if r.publishable]

    publishable_company_ids = {_company_id(rec) for rec in publishable_records}
    publishable_company_ids.discard("")
    company_coverage = {
        "publishable_jobs": len(publishable_records),
        "distinct_publishable_companies": len(publishable_company_ids),
    }

    def records_with(predicate) -> int:
        return sum(1 for rec in unique if predicate(rec))

    missing_company_identity = records_with(lambda rec: not _company_id(rec))
    invalid_application_url = [
        rec for rec, r in zip(unique, results)
        if any(
            reason.code in {
                "missing_application_url", "invalid_application_url",
                "tracking_only_application_url", "listing_fallback_application_url",
            }
            for reason in r.reasons
        )
    ]
    missing_or_placeholder_description = records_with(
        lambda rec: not str(rec.get("description_text") or rec.get("description") or "").strip()
    )
    placeholder_description = records_with(
        lambda rec: bool(str(rec.get("description_text") or rec.get("description") or "").strip())
        and _looks_placeholder(str(rec.get("description_text") or rec.get("description") or ""))
    )
    published_but_would_fail = [
        rec for rec, r in zip(unique, results)
        if _is_published(rec) and not r.publishable
    ]
    outcome_summary = {
        status: {
            "count": outcome_counts.get(status, 0),
            "percent": _pct(outcome_counts.get(status, 0), len(unique)),
        }
        for status in STATUSES
    }

    top_reasons = [
        {"code": code, "count": count, "status": "see status mapping"}
        for code, count in reason_counts.most_common(20)
    ]

    outcome_total = sum(outcome_counts.values())
    reconciliation = {
        "input_records": total,
        "unique_canonical_jobs": len(unique),
        "duplicate_identity_records_skipped": duplicate_identity_records,
        "unique_plus_duplicates_equals_input": (len(unique) + duplicate_identity_records) == total,
        "outcome_total_equals_unique": outcome_total == len(unique),
        "outcome_total": outcome_total,
    }

    return {
        "contract_version": "job_publication_completeness_v1",
        "generated_at": now.isoformat(),
        "input_records": total,
        "unique_canonical_jobs": len(unique),
        "duplicate_identity_records_skipped": duplicate_identity_records,
        "reconciliation": reconciliation,
        "outcome_counts": dict(outcome_counts),
        "outcome_summary": outcome_summary,
        "counts_by_source": dict(source_counts),
        "outcome_by_source": {src: dict(c) for src, c in sorted(source_outcome.items())},
        "top_blocking_reasons": top_reasons,
        "company_coverage": company_coverage,
        "missing_canonical_company_identity": missing_company_identity,
        "invalid_or_missing_application_url_count": len(invalid_application_url),
        "missing_description_count": missing_or_placeholder_description,
        "placeholder_description_count": placeholder_description,
        "published_that_would_fail": {
            "count": len(published_but_would_fail),
            "canonical_job_ids": [_canonical_job_id(rec) for rec in published_but_would_fail][:20],
        },
    }


def _looks_placeholder(value: str) -> bool:
    lowered = value.casefold().strip()
    return lowered in {
        "", "n/a", "na", "none", "null", "placeholder", "lorem ipsum",
    } or "<" in value or "{{" in value


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Job Publication Completeness Audit")
    lines.append("")
    lines.append(f"- Contract: `{report['contract_version']}`")
    lines.append(f"- Generated: `{report['generated_at']}`")
    lines.append(f"- Input records: {report['input_records']}")
    lines.append(f"- Unique canonical jobs: {report['unique_canonical_jobs']}")
    lines.append(f"- Duplicate-identity records skipped: {report['duplicate_identity_records_skipped']}")
    lines.append("")
    lines.append("## Outcomes")
    lines.append("")
    lines.append("| Status | Count | Percent |")
    lines.append("|---|---|---|")
    for status in STATUSES:
        entry = report["outcome_summary"][status]
        lines.append(f"| `{status}` | {entry['count']} | {entry['percent']}% |")
    lines.append("")
    lines.append("## Counts by source")
    lines.append("")
    lines.append("| Source | Count |")
    lines.append("|---|---|")
    for src, count in sorted(report["counts_by_source"].items()):
        lines.append(f"| `{src}` | {count} |")
    lines.append("")
    lines.append("## Top blocking reasons")
    lines.append("")
    lines.append("| Reason code | Count |")
    lines.append("|---|---|")
    for reason in report["top_blocking_reasons"]:
        lines.append(f"| `{reason['code']}` | {reason['count']} |")
    lines.append("")
    lines.append("## Coverage")
    lines.append("")
    coverage = report["company_coverage"]
    lines.append(f"- Publishable jobs: {coverage['publishable_jobs']}")
    lines.append(f"- Distinct publishable companies: {coverage['distinct_publishable_companies']}")
    lines.append(f"- Records lacking canonical company identity: {report['missing_canonical_company_identity']}")
    lines.append(f"- Invalid or missing application URLs: {report['invalid_or_missing_application_url_count']}")
    lines.append(f"- Missing descriptions: {report['missing_description_count']}")
    lines.append(f"- Placeholder descriptions: {report['placeholder_description_count']}")
    lines.append(f"- Published that would fail the contract: {report['published_that_would_fail']['count']}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit job publication completeness offline.")
    parser.add_argument("--input", type=Path, required=True, help="JSONL/JSON/CSV of canonical job records.")
    parser.add_argument("--company-registry", type=Path, default=None, help="company_registry_canonical.csv path.")
    parser.add_argument("--output", type=Path, required=True, help="Output directory for reports.")
    parser.add_argument("--format", choices=["json", "markdown", "both"], default="both")
    parser.add_argument("--now", default="", help="Override 'now' as ISO-8601 (deterministic audits).")
    parser.add_argument("--min-description-chars", type=int, default=80)
    parser.add_argument("--stale-after-days", type=int, default=90)
    args = parser.parse_args(argv)

    records = load_records(args.input)
    company_registry = load_company_registry(args.company_registry)
    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)

    report = run_audit(
        records,
        company_registry=company_registry,
        now=now,
        min_description_chars=args.min_description_chars,
        stale_after_days=args.stale_after_days,
    )

    args.output.mkdir(parents=True, exist_ok=True)
    if args.format in {"json", "both"}:
        (args.output / "completeness_audit.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    if args.format in {"markdown", "both"}:
        (args.output / "completeness_audit.md").write_text(
            render_markdown(report), encoding="utf-8"
        )

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
