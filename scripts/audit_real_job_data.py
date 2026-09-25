"""Read-only publication-completeness audit over REAL producer state.

Reads the authoritative LinkedIn and employer producer state databases
(SQLite) in read-only mode, maps each raw producer row onto the validator's
record shape with an explicit, documented field mapping, and reports outcomes
by source.  No database, state file, or origin data is written or mutated.

Dataset authority (see ``docs/ACQUISITION_RUNTIME_DATA_INVENTORY.md``):

- Historical (authoritative, 2026-09-08): ``rc023-20260908/state/...``
- Pilot (2026-09-09): ``rc027-20260909/...`` (reported separately if provided)

The producer state contains no ``canonical_job_id`` (that is assigned at
ingestion); the audit derives a stable identity from the source job id and
labels it ``source_derived``.  ``canonical_company_id`` is taken from the
producer field verbatim -- the LinkedIn producer writes ``//`` for an
unresolved identity, which the validator treats as missing.

Usage (project venv only):

    .venv\\Scripts\\python.exe scripts\\audit_real_job_data.py \
        --linkedin-state <path> --employer-state <path> \
        --company-registry data/acquisition/inputs/company_registry_canonical.csv \
        --output data/audit/real --format both
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
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
    is_missing_identity,
    validate_job_for_publication,
)

DEFAULT_LINKEDIN_STATE = (
    r"C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots"
    r"\rc023-20260908\state\linkedin\master_linkedin_jobs_state.db"
)
DEFAULT_EMPLOYER_STATE = (
    r"C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots"
    r"\rc023-20260908\state\employer\master_employer_jobs_state.db"
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def load_company_registry(path: Path | None) -> set[str] | None:
    if path is None or not path.exists():
        return None
    rows = csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines())
    return {str(r.get("canonical_CompanyID") or "").strip() for r in rows if str(r.get("canonical_CompanyID") or "").strip()}


def _connect_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _linkedin_record(job_id: str, row_json: str) -> dict[str, Any]:
    p = json.loads(row_json)
    if not isinstance(p, dict):
        p = {}
    return {
        "canonical_job_id": f"linkedin:{job_id}",
        "identity_mode": "source_derived",
        "canonical_company_id": _text(p.get("canonical_company_id")),
        "company_name": _text(p.get("source_company_name") or p.get("observed_company_name")),
        "title": _text(p.get("job_title")),
        "description_text": _text(p.get("description")),
        "location_raw": _text(p.get("location")),
        "workplace_arrangement": _text(p.get("workplace_type")),
        "seniority": _text(p.get("seniority") or p.get("experience_level")),
        "employment_type": _text(p.get("employment_type") or p.get("job_type")),
        "company_logo": _text(p.get("company_logo") or p.get("logo_url") or p.get("logo")),
        "company_enrichment": _text(p.get("company_enrichment") or p.get("enrichment") or p.get("company_metadata")),
        "apply_url": _text(p.get("apply_url_canonical") or p.get("apply_url_raw")),
        "apply_url_canonical": _text(p.get("apply_url_canonical")),
        "apply_url_raw": _text(p.get("apply_url_raw")),
        "easy_apply_status": _text(p.get("easy_apply_status")),
        "source": "linkedin",
        "source_ats": "linkedin",
        "source_job_id": _text(job_id),
        "observed_at": _text(p.get("last_seen_at") or p.get("detail_last_refreshed_at")),
        "lifecycle_state": _text(p.get("lifecycle_status")),
        "posted_at": _text(p.get("posted_at_estimated")),
        "ownership_status": _text(p.get("ownership_status")),
        "company_match_status": _text(p.get("company_match_status")),
        "location_classification": _text(p.get("location_classification")),
    }


def _employer_record(source_key: str, payload_json: str) -> dict[str, Any]:
    p = json.loads(payload_json)
    if not isinstance(p, dict):
        p = {}
    return {
        "canonical_job_id": f"employer:{source_key}",
        "identity_mode": "source_derived",
        "canonical_company_id": _text(p.get("canonical_company_id")),
        "company_name": _text(p.get("source_company_name")),
        "title": _text(p.get("job_title") or p.get("title_raw")),
        "description_text": _text(p.get("description_text") or p.get("description")),
        "location_raw": _text(p.get("location") or p.get("location_raw")),
        "workplace_arrangement": _text(p.get("workplace_type")),
        "seniority": _text(p.get("seniority") or p.get("experience_level")),
        "employment_type": _text(p.get("employment_type") or p.get("job_type")),
        "company_logo": _text(p.get("company_logo") or p.get("logo_url") or p.get("logo")),
        "company_enrichment": _text(p.get("company_enrichment") or p.get("enrichment") or p.get("company_metadata")),
        "apply_url": _text(p.get("apply_url_canonical") or p.get("apply_url_raw") or p.get("source_job_url")),
        "apply_url_canonical": _text(p.get("apply_url_canonical")),
        "apply_url_raw": _text(p.get("apply_url_raw")),
        "source_job_url": _text(p.get("source_job_url")),
        "source": "employer_site",
        "source_ats": _text(p.get("source_provider") or "employer_site"),
        "source_job_id": _text(p.get("source_job_id") or source_key),
        "observed_at": _text(p.get("last_seen_at") or p.get("first_seen_at")),
        "lifecycle_state": "active" if _text(p.get("collection_status") or "accepted") in {"accepted", "active"} else _text(p.get("collection_status")),
        "posted_at": _text(p.get("date_posted")),
        "germany_classification": _text(p.get("germany_classification")),
    }


def _evaluate_records(
    records: list[dict[str, Any]],
    *,
    company_registry: set[str] | None,
    now: datetime,
    min_description_chars: int,
    stale_after_days: int,
) -> dict[str, Any]:
    total = len(records)
    outcomes: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    distinct_source_job_ids: set[str] = set()
    duplicate_source_job_ids = 0
    seen_job_ids: set[str] = set()

    for record in records:
        sjid = record.get("source_job_id") or ""
        if sjid:
            distinct_source_job_ids.add(sjid)
            if sjid in seen_job_ids:
                duplicate_source_job_ids += 1
            seen_job_ids.add(sjid)

    publishable = 0
    publishable_company_ids: set[str] = set()
    for record in records:
        result = validate_job_for_publication(
            record,
            now=now,
            company_registry=company_registry,
            min_description_chars=min_description_chars,
            stale_after_days=stale_after_days,
        )
        outcomes[result.status] += 1
        for r in result.reasons:
            reasons[r.code] += 1
        if result.publishable:
            publishable += 1
            ccid = _text(record.get("canonical_company_id"))
            if ccid:
                publishable_company_ids.add(ccid)

    return {
        "total": total,
        "distinct_source_job_ids": len(distinct_source_job_ids),
        "duplicate_source_job_ids": duplicate_source_job_ids,
        "publishable": publishable,
        "distinct_publishable_companies": len(publishable_company_ids),
        "outcomes": dict(outcomes),
        "top_reasons": [{"code": c, "count": n} for c, n in reasons.most_common(30)],
    }


def _source_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    missing_company_id = sum(1 for r in records if is_missing_identity(r.get("canonical_company_id")))
    missing_description = sum(1 for r in records if not _text(r.get("description_text")))
    missing_application_url = sum(1 for r in records if not _text(r.get("apply_url")))
    missing_location = sum(1 for r in records if not _text(r.get("location_raw")))
    return {
        "missing_canonical_company_id": missing_company_id,
        "missing_description": missing_description,
        "missing_application_url": missing_application_url,
        "missing_location": missing_location,
    }


def _employer_apply_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    missing_explicit = sum(
        1 for r in records
        if not _text(r.get("apply_url_raw")) and not _text(r.get("apply_url_canonical"))
    )
    has_job_detail_url = sum(1 for r in records if _text(r.get("source_job_url")))
    return {
        "missing_explicit_apply_url": missing_explicit,
        "has_job_detail_url_fallback": has_job_detail_url,
    }


def _linkedin_apply_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    easy_apply_true = sum(
        1 for r in records if str(r.get("easy_apply_status") or "").casefold() == "true"
    )
    view_url = sum(
        1 for r in records if "linkedin.com/jobs/view" in _text(r.get("apply_url"))
    )
    return {"easy_apply_true": easy_apply_true, "apply_url_is_linkedin_view": view_url}


def run_real_audit(
    *,
    linkedin_state: Path,
    employer_state: Path,
    company_registry: set[str] | None,
    now: datetime,
    min_description_chars: int = 80,
    stale_after_days: int = 90,
) -> dict[str, Any]:
    linkedin_records: list[dict[str, Any]] = []
    employer_records: list[dict[str, Any]] = []

    if linkedin_state.exists():
        conn = _connect_ro(linkedin_state)
        try:
            for job_id, row_json in conn.execute(
                "SELECT linkedin_job_id, row_json FROM job_company_observations"
            ):
                linkedin_records.append(_linkedin_record(job_id, row_json))
        finally:
            conn.close()

    if employer_state.exists():
        conn = _connect_ro(employer_state)
        try:
            for source_key, payload_json in conn.execute(
                "SELECT source_key, payload_json FROM jobs"
            ):
                employer_records.append(_employer_record(source_key, payload_json))
        finally:
            conn.close()

    linkedin = _evaluate_records(
        linkedin_records,
        company_registry=company_registry,
        now=now,
        min_description_chars=min_description_chars,
        stale_after_days=stale_after_days,
    )
    employer = _evaluate_records(
        employer_records,
        company_registry=company_registry,
        now=now,
        min_description_chars=min_description_chars,
        stale_after_days=stale_after_days,
    )

    return {
        "contract_version": "job_publication_completeness_v1",
        "generated_at": now.isoformat(),
        "linkedin": {
            **linkedin,
            "source_metrics": _source_metrics(linkedin_records),
            "apply_metrics": _linkedin_apply_metrics(linkedin_records),
        },
        "employer": {
            **employer,
            "source_metrics": _source_metrics(employer_records),
            "apply_metrics": _employer_apply_metrics(employer_records),
        },
        "reconciliation": {
            "linkedin_outcome_total_equals_records": sum(linkedin["outcomes"].values()) == linkedin["total"],
            "employer_outcome_total_equals_records": sum(employer["outcomes"].values()) == employer["total"],
        },
        "combined": {
            "total": linkedin["total"] + employer["total"],
            "publishable": linkedin["publishable"] + employer["publishable"],
            "distinct_source_job_ids": linkedin["distinct_source_job_ids"] + employer["distinct_source_job_ids"],
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Real-data Job Publication Completeness Audit")
    lines.append("")
    lines.append(f"- Contract: `{report['contract_version']}`")
    lines.append(f"- Generated: `{report['generated_at']}`")
    lines.append("")
    for name in ("linkedin", "employer"):
        src = report[name]
        lines.append(f"## {name}")
        lines.append("")
        lines.append(f"- Records evaluated: {src['total']}")
        lines.append(f"- Distinct source job identities: {src['distinct_source_job_ids']}")
        lines.append(f"- Duplicate source job identities: {src['duplicate_source_job_ids']}")
        lines.append(f"- Publishable: {src['publishable']}")
        lines.append(f"- Distinct publishable companies: {src['distinct_publishable_companies']}")
        lines.append("")
        lines.append("### Outcomes")
        lines.append("")
        lines.append("| Status | Count |")
        lines.append("|---|---|")
        for status in STATUSES:
            lines.append(f"| `{status}` | {src['outcomes'].get(status, 0)} |")
        lines.append("")
        lines.append("### Source field gaps")
        lines.append("")
        m = src["source_metrics"]
        lines.append(f"- Missing canonical company id: {m['missing_canonical_company_id']}")
        lines.append(f"- Missing description: {m['missing_description']}")
        lines.append(f"- Missing application URL: {m['missing_application_url']}")
        lines.append(f"- Missing location: {m['missing_location']}")
        am = src.get("apply_metrics", {})
        if am:
            lines.append(f"- Apply metrics: {json.dumps(am, sort_keys=True)}")
        lines.append("")
        lines.append("### Top blocking reasons")
        lines.append("")
        lines.append("| Reason | Count |")
        lines.append("|---|---|")
        for r in src["top_reasons"]:
            lines.append(f"| `{r['code']}` | {r['count']} |")
        lines.append("")
    lines.append("## Combined")
    lines.append("")
    c = report["combined"]
    lines.append(f"- Total records: {c['total']}")
    lines.append(f"- Publishable: {c['publishable']}")
    lines.append("")
    lines.append("## Reconciliation")
    lines.append("")
    for key, value in report.get("reconciliation", {}).items():
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Real-data job publication completeness audit.")
    parser.add_argument("--linkedin-state", type=Path, default=Path(DEFAULT_LINKEDIN_STATE))
    parser.add_argument("--employer-state", type=Path, default=Path(DEFAULT_EMPLOYER_STATE))
    parser.add_argument("--company-registry", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "audit" / "real")
    parser.add_argument("--format", choices=["json", "markdown", "both"], default="both")
    parser.add_argument("--now", default="")
    parser.add_argument("--min-description-chars", type=int, default=80)
    parser.add_argument("--stale-after-days", type=int, default=90)
    args = parser.parse_args(argv)

    company_registry = load_company_registry(args.company_registry)
    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)

    report = run_real_audit(
        linkedin_state=args.linkedin_state,
        employer_state=args.employer_state,
        company_registry=company_registry,
        now=now,
        min_description_chars=args.min_description_chars,
        stale_after_days=args.stale_after_days,
    )

    args.output.mkdir(parents=True, exist_ok=True)
    if args.format in {"json", "both"}:
        (args.output / "completeness_audit_real.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    if args.format in {"markdown", "both"}:
        (args.output / "completeness_audit_real.md").write_text(render_markdown(report), encoding="utf-8")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
