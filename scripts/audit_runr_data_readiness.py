"""Read-only live Runr company/job publication-readiness audit.

The audit connects to the configured Runr database, evaluates every canonical
job and every canonical company, and writes redacted counts plus full
identifier-level remediation queues. It never mutates the database.

The Runr source checkout is separate from this collector checkout; use
``--runr-root`` to point at the migrated Runr code so the audit uses the same
completeness validator as production.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNR_ROOT = PROJECT_ROOT.parent / "runr-admin-linkedin-preview"
DEFAULT_ENV = PROJECT_ROOT / "user_config" / ".env"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "audit" / "runr_readiness"


def load_env(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def add_import_root(path: Path) -> None:
    resolved = str(path.resolve())
    if resolved not in sys.path:
        sys.path.insert(0, resolved)


def row_values(row: Any) -> list[Any]:
    return [row[index] for index in range(len(row))]


def row_dict(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def parse_json(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def grouped(rows: list[Any]) -> list[dict[str, Any]]:
    return [row_dict(row) for row in rows]


def count(conn: Any, sql: str, params: tuple[Any, ...] | None = None) -> int:
    cursor = conn.execute(sql) if params is None else conn.execute(sql, params)
    return int(cursor.fetchone()[0])


def missing(value: Any) -> bool:
    return text(value).casefold() in {"", "//", "-", "--", "/", "n/a", "na", "null", "none", "unknown"}


def field_gap_counts(conn: Any, table: str, fields: list[str]) -> dict[str, int]:
    gaps = {}
    for field in fields:
        gaps[field] = count(
            conn,
            f'''SELECT COUNT(*) FROM "{table}"
                WHERE "{field}" IS NULL
                   OR TRIM(CAST("{field}" AS TEXT)) IN ('', '//', '-', '--', '/', 'n/a', 'na', 'null', 'none', 'unknown')''',
        )
    return gaps


def build_job_record(row: dict[str, Any]) -> dict[str, Any]:
    version = parse_json(row.get("version_payload"))
    observation = parse_json(row.get("observation_payload"))
    original_url = text(row.get("original_url"))
    application_url = (
        text(row.get("application_url"))
        or text(row.get("observation_apply_url"))
        or text(row.get("version_apply_url"))
        or original_url
    )
    classification = text(row.get("application_classification"))
    if not classification and original_url:
        classification = "job_detail_only"
    return {
        "canonical_job_id": text(row.get("canonical_job_id")),
        "canonical_company_id": text(row.get("company_id")),
        "company_name": text(row.get("canonical_name")),
        "title": text(row.get("version_title")) or text(row.get("job_title")),
        "description": (
            text(row.get("version_description"))
            or text(version.get("description_text"))
            or text(version.get("description"))
            or text(observation.get("description_text"))
            or text(observation.get("description"))
        ),
        "location": (
            text(row.get("version_location"))
            or text(row.get("job_location"))
            or text(observation.get("location"))
            or text(observation.get("location_raw"))
        ),
        "source": text(row.get("source_connector")) or text(row.get("source_ats")),
        "source_job_id": text(row.get("external_job_id")),
        "observed_at": text(row.get("observed_at")) or text(row.get("last_verified_at")),
        "lifecycle_state": text(row.get("lifecycle_state")),
        "posted_at": (
            text(observation.get("posted_at"))
            or text(observation.get("posted_at_estimated"))
            or text(version.get("posted_at"))
        ),
        "closed_at": text(row.get("closed_at")) or text(observation.get("closed_at")),
        "application_destination": {
            "resolved_url": application_url,
            "destination_type": classification,
        },
    }


def job_row(conn: Any, head_id: str) -> list[dict[str, Any]]:
    sql = """
        SELECT
            j.canonical_job_id, j.company_id, c.canonical_name,
            j.title AS job_title, j.location AS job_location,
            j.canonical_url, j.lifecycle_state, j.last_verified_at,
            j.source_updated_at, j.closed_at, j.published_at,
            j.current_version_id,
            v.title AS version_title, v.description AS version_description,
            v.location AS version_location, v.apply_url AS version_apply_url,
            v.payload_json AS version_payload,
            o.external_job_id, o.original_url,
            o.apply_url AS observation_apply_url, o.source_ats,
            o.observed_at, o.application_url, o.application_classification,
            o.payload_json AS observation_payload, o.source_connector,
            CASE WHEN pj.publication_id IS NULL THEN 0 ELSE 1 END AS in_head
        FROM canonical_jobs j
        LEFT JOIN canonical_companies c ON c.company_id = j.company_id
        LEFT JOIN job_posting_versions v ON v.version_id = j.current_version_id
        LEFT JOIN job_source_observations o ON o.observation_id = v.source_observation_id
        LEFT JOIN acquisition_publication_jobs pj
          ON pj.canonical_job_id = j.canonical_job_id
         AND pj.publication_id = ?
        ORDER BY j.canonical_job_id
    """
    rows = []
    for raw in conn.execute(sql, (head_id,)).fetchall():
        row = row_dict(raw)
        record = build_job_record(row)
        row["record"] = record
        rows.append(row)
    return rows


def company_rows(conn: Any, head_id: str) -> list[dict[str, Any]]:
    job_counts = {
        text(row["company_id"]): int(row["job_count"])
        for row in conn.execute(
            "SELECT company_id, COUNT(*) AS job_count FROM canonical_jobs GROUP BY company_id"
        ).fetchall()
    }
    head_counts = {
        text(row["company_id"]): int(row["job_count"])
        for row in conn.execute(
            """
            SELECT j.company_id, COUNT(*) AS job_count
            FROM acquisition_publication_jobs pj
            JOIN canonical_jobs j ON j.canonical_job_id = pj.canonical_job_id
            WHERE pj.publication_id = ?
            GROUP BY j.company_id
            """,
            (head_id,),
        ).fetchall()
    }
    profiles = {
        text(row["company_id"]): row_dict(row)
        for row in conn.execute("SELECT * FROM canonical_company_profiles").fetchall()
    }
    urls: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in conn.execute("SELECT * FROM canonical_company_urls").fetchall():
        data = row_dict(row)
        urls[text(data.get("company_id"))].append(data)
    identity_keys = Counter(
        text(row["company_id"])
        for row in conn.execute("SELECT company_id FROM company_identity_keys").fetchall()
    )
    evidence = Counter(
        text(row["company_id"])
        for row in conn.execute("SELECT company_id FROM company_identity_evidence").fetchall()
    )
    review_evidence = Counter(
        text(row["company_id"])
        for row in conn.execute(
            "SELECT company_id FROM company_identity_evidence WHERE review_required = 1"
        ).fetchall()
    )
    output = []
    for raw in conn.execute("SELECT * FROM canonical_companies ORDER BY company_id").fetchall():
        row = row_dict(raw)
        company_id = text(row.get("company_id"))
        profile = profiles.get(company_id, {})
        company_urls = urls.get(company_id, [])
        primary_urls = [url for url in company_urls if int(url.get("selected_primary") or 0) == 1]
        blockers: list[str] = []
        if missing(company_id):
            blockers.append("missing_canonical_company_id")
        if missing(row.get("canonical_name")):
            blockers.append("missing_company_name")
        if not primary_urls:
            blockers.append("missing_selected_primary_url")
        if not profile:
            blockers.append("missing_company_profile")
        elif missing(profile.get("profile_json")) or text(profile.get("profile_json")) in {"{}", "null"}:
            blockers.append("empty_company_profile")
        if profile and missing(profile.get("logo_verified_at")):
            blockers.append("missing_verified_logo")
        canonical_ready = not any(
            blocker in {"missing_canonical_company_id", "missing_company_name"} for blocker in blockers
        )
        presentation_ready = canonical_ready and bool(primary_urls)
        enrichment_complete = presentation_ready and bool(profile) and not any(
            blocker in {"empty_company_profile", "missing_verified_logo"} for blocker in blockers
        )
        row.update(
            {
                "primary_url": text(primary_urls[0].get("url")) if primary_urls else "",
                "primary_url_count": len(primary_urls),
                "url_count": len(company_urls),
                "profile_present": bool(profile),
                "profile_status": text(profile.get("profile_status")),
                "profile_json_present": bool(profile and not missing(profile.get("profile_json"))),
                "logo_object_key_present": bool(profile and not missing(profile.get("logo_object_key"))),
                "logo_verified_at": text(profile.get("logo_verified_at")),
                "identity_key_count": identity_keys[company_id],
                "identity_evidence_count": evidence[company_id],
                "review_evidence_count": review_evidence[company_id],
                "job_count_all": job_counts.get(company_id, 0),
                "job_count_head": head_counts.get(company_id, 0),
                "canonical_ready": canonical_ready,
                "presentation_ready": presentation_ready,
                "enrichment_complete": enrichment_complete,
                "blockers": blockers,
            }
        )
        output.append(row)
    return output


def evaluate_jobs(job_rows: list[dict[str, Any]], company_ids: set[str], validator: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    evaluated = []
    status_counts = Counter()
    reason_counts = Counter()
    field_counts = Counter()
    for row in job_rows:
        record = row["record"]
        result = validator(record, now=datetime.now(timezone.utc), company_registry=company_ids)
        status_counts[result.status] += 1
        for reason in result.reason_codes:
            reason_counts[reason] += 1
        for field, state in result.field_states.items():
            if state in {"missing", "invalid", "placeholder", "stale", "closed"}:
                field_counts[field] += 1
        evaluated.append(
            {
                "scope": "current_head" if int(row.get("in_head") or 0) else "all_canonical_jobs",
                "canonical_job_id": record["canonical_job_id"],
                "canonical_company_id": record["canonical_company_id"],
                "company_name": record["company_name"],
                "title": record["title"],
                "canonical_url": text(row.get("canonical_url")),
                "source": record["source"],
                "source_job_id": record["source_job_id"],
                "observed_at": record["observed_at"],
                "lifecycle_state": record["lifecycle_state"],
                "application_url": record["application_destination"]["resolved_url"],
                "application_classification": record["application_destination"]["destination_type"],
                "description_length": len(record["description"]),
                "location": record["location"],
                "in_current_head": bool(int(row.get("in_head") or 0)),
                "status": result.status,
                "publishable": result.publishable,
                "reason_codes": ";".join(result.reason_codes),
            }
        )
    return evaluated, {
        "total": len(evaluated),
        "publishable": sum(1 for row in evaluated if row["publishable"]),
        "status_counts": dict(status_counts),
        "reason_counts": dict(reason_counts),
        "field_problem_counts": dict(field_counts),
    }


def render_report(summary: dict[str, Any], paths: dict[str, str]) -> str:
    head = summary["head"]
    cycle = summary["latest_cycle"]
    head_quality = summary["job_completeness"]["current_head"]
    all_quality = summary["job_completeness"]["all_canonical_jobs"]
    company = summary["company_readiness"]
    lines = [
        "# Runr data completion and publication-readiness audit",
        "",
        f"Generated: `{summary['generated_at']}`",
        f"Decision: **{summary['decision']}**",
        "",
        "## Scope",
        "",
        f"- Live database backend: `{summary['database_backend']}`",
        f"- Current publication head: `{head['publication_id']}`",
        f"- Current publication status: `{head['status']}`",
        f"- Current publication jobs: `{head['job_count']}`",
        f"- Latest acquisition cycle: `{cycle.get('cycle_id', '')}` (`{cycle.get('status', '')}`)",
        f"- Latest cycle observed/new/published: `{cycle.get('jobs_observed', 0)}/{cycle.get('jobs_new', 0)}/{cycle.get('jobs_published', 0)}`",
        f"- All canonical jobs stored: `{summary['counts']['canonical_jobs']}`",
        f"- All canonical companies stored: `{summary['counts']['canonical_companies']}`",
        f"- Validator contract: `{summary['validator_contract']}`",
        "",
        "The audit evaluates the live canonical tables and the current publication head. It does not infer completeness from collector success, source-scan completion, or a previous migration report.",
        "",
        "## Executive result",
        "",
        f"- Current head: `{head_quality['publishable']}/{head_quality['total']}` jobs pass the production completeness validator.",
        f"- All stored canonical jobs: `{all_quality['publishable']}/{all_quality['total']}` pass the same validator.",
        f"- Canonical company identity-ready: `{company['canonical_ready']}/{company['total']}`.",
        f"- Company presentation-ready with selected primary URL: `{company['presentation_ready']}/{company['total']}`.",
        f"- Company enrichment-complete under the audit’s non-blocking enrichment definition: `{company['enrichment_complete']}/{company['total']}`.",
        f"- Companies referenced by the current head: `{company['head_total']}`; head-referenced companies with a selected primary URL: `{company['head_presentation_ready']}`.",
        "",
        "## Current-head blockers",
        "",
        "### Reason counts",
        "",
        "| Reason | Jobs |",
        "|---|---:|",
    ]
    for reason, amount in sorted(head_quality["reason_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| `{reason}` | {amount} |")
    lines += ["", "### Status counts", "", "| Status | Jobs |", "|---|---:|"]
    for status, amount in sorted(head_quality["status_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| `{status}` | {amount} |")
    lines += [
        "",
        "A job is publishable only when its canonical identity, company identity, title, direct application destination, description, location/remote classification, source identity, freshness, and lifecycle checks pass. Recommended fields such as salary, benefits, seniority, and logos are not publication blockers in the contract.",
        "",
        "## Raw field gaps across stored tables",
        "",
        "These counts are row-level storage gaps, including non-head and historical rows. They are separate from the validator outcome counts above.",
        "",
    ]
    for table, fields in summary["raw_field_gaps"].items():
        lines += [f"### `{table}`", "", "| Field | Missing/sentinel rows |", "|---|---:|"]
        for field, amount in fields.items():
            lines.append(f"| `{field}` | {amount} |")
        lines.append("")
    lines += [
        "## All stored-job gaps",
        "",
        "| Status | Jobs |",
        "|---|---:|",
    ]
    for status, amount in sorted(all_quality["status_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| `{status}` | {amount} |")
    lines += ["", "| Reason | Jobs |", "|---|---:|"]
    for reason, amount in sorted(all_quality["reason_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| `{reason}` | {amount} |")
    lines += [
        "",
        "## Company readiness",
        "",
        "| Gate | Ready | Total |", "|---|---:|---:|",
        f"| Canonical identity (ID + name) | {company['canonical_ready']} | {company['total']} |",
        f"| Presentation (identity + selected primary URL) | {company['presentation_ready']} | {company['total']} |",
        f"| Enrichment (presentation + profile + verified logo) | {company['enrichment_complete']} | {company['total']} |",
        "",
        "| Company blocker | Companies |", "|---|---:|",
    ]
    for reason, amount in sorted(company["blocker_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| `{reason}` | {amount} |")
    lines += [
        "",
        "## Interpretation and implementation queue",
        "",
        "1. Fix or quarantine every current-head job listed in `jobs_readiness.csv` with a non-publishable status. The CSV is the fill/delete decision queue, keyed by canonical job ID.",
        "2. Do not treat missing company profiles, logos, or selected company URLs as interchangeable with missing canonical identity. The report separates those gates so deletion is not used for optional enrichment gaps.",
        "3. Re-run this audit after remediation and require the current head to be 100% `publishable_complete` before calling the catalog complete.",
        "4. Keep the separate operational frontend/API-proxy failure in the deployment checklist; it is not a data-field count but can prevent customers from seeing an otherwise valid publication.",
        "",
        "## Evidence and absolute paths",
        "",
    ]
    for label, path in paths.items():
        lines.append(f"- {label}: `{path}`")
    lines += ["", "## Audit caveat", "", "The company readiness gates are an audit classification for remediation. The Runr job publication contract is authoritative for job publication; company logo/profile enrichment is explicitly optional/non-blocking there.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runr-root", type=Path, default=DEFAULT_RUNR_ROOT)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    load_env(args.env_file)
    add_import_root(args.runr_root)
    from backend.acquisition.job_publication_completeness import CONTRACT_VERSION, validate_job_for_publication
    from backend.database.connection import connect_database

    args.output_dir.mkdir(parents=True, exist_ok=True)
    conn = connect_database(args.output_dir / "readonly_probe.sqlite3")
    try:
        head_raw = conn.execute(
            "SELECT head_id, publication_id, updated_at FROM acquisition_publication_head WHERE head_id = 1"
        ).fetchone()
        if head_raw is None:
            raise RuntimeError("No acquisition publication head exists.")
        head = row_dict(head_raw)
        publication = row_dict(
            conn.execute(
                "SELECT * FROM acquisition_publications WHERE publication_id = ?",
                (head["publication_id"],),
            ).fetchone()
        )
        head["job_count"] = count(
            conn,
            "SELECT COUNT(*) FROM acquisition_publication_jobs WHERE publication_id = ?",
            (head["publication_id"],),
        )
        head.update({key: publication.get(key) for key in ("status", "cycle_id", "published_at", "valid_until", "policy_version", "rule_version", "origin")})

        job_rows = job_row(conn, text(head["publication_id"]))
        companies = company_rows(conn, text(head["publication_id"]))
        company_ids = {text(row["company_id"]) for row in companies if not missing(row.get("company_id"))}
        evaluated_jobs, all_job_quality = evaluate_jobs(job_rows, company_ids, validate_job_for_publication)
        current_head = [row for row in evaluated_jobs if row["in_current_head"]]
        current_head_quality = {
            "total": len(current_head),
            "publishable": sum(1 for row in current_head if row["publishable"]),
            "status_counts": dict(Counter(row["status"] for row in current_head)),
            "reason_counts": dict(
                Counter(reason for row in current_head for reason in row["reason_codes"].split(";") if reason)
            ),
        }
        blocker_counts = Counter(blocker for row in companies for blocker in row["blockers"])
        company_summary = {
            "total": len(companies),
            "canonical_ready": sum(1 for row in companies if row["canonical_ready"]),
            "presentation_ready": sum(1 for row in companies if row["presentation_ready"]),
            "enrichment_complete": sum(1 for row in companies if row["enrichment_complete"]),
            "head_total": sum(1 for row in companies if int(row.get("job_count_head") or 0) > 0),
            "head_presentation_ready": sum(1 for row in companies if int(row.get("job_count_head") or 0) > 0 and row["presentation_ready"]),
            "blocker_counts": dict(blocker_counts),
        }

        counts = {}
        for table in (
            "canonical_companies", "canonical_jobs", "canonical_company_profiles", "canonical_company_urls",
            "job_source_observations", "job_posting_versions", "acquisition_targets", "acquisition_tasks",
            "acquisition_publications", "acquisition_publication_jobs", "acquisition_job_rejections",
        ):
            counts[table] = count(conn, f"SELECT COUNT(*) FROM {table}")

        raw_field_gaps = {
            "canonical_jobs": field_gap_counts(
                conn,
                "canonical_jobs",
                ["canonical_job_id", "company_id", "identity_key", "title", "location", "canonical_url", "lifecycle_state", "last_verified_at", "current_version_id", "identity_signature", "source_updated_at"],
            ),
            "canonical_companies": field_gap_counts(
                conn,
                "canonical_companies",
                ["company_id", "canonical_name", "entity_kind", "provenance_url"],
            ),
            "canonical_company_profiles": field_gap_counts(
                conn,
                "canonical_company_profiles",
                ["company_id", "profile_json", "logo_object_key", "logo_source_url", "logo_verified_at", "profile_status"],
            ),
            "canonical_company_urls": field_gap_counts(
                conn,
                "canonical_company_urls",
                ["company_id", "url_type", "url", "canonical_url", "validation_status", "selected_primary"],
            ),
            "job_posting_versions": field_gap_counts(
                conn,
                "job_posting_versions",
                ["version_id", "canonical_job_id", "version_number", "content_hash", "title", "description", "location", "apply_url", "source_observation_id", "payload_json"],
            ),
            "job_source_observations": field_gap_counts(
                conn,
                "job_source_observations",
                ["observation_id", "canonical_job_id", "target_id", "cycle_id", "task_id", "external_job_id", "original_url", "apply_url", "source_ats", "content_hash", "payload_json", "observed_at", "source_display_name", "source_connector", "application_url", "application_classification"],
            ),
        }
        latest_cycle_raw = conn.execute(
            "SELECT * FROM acquisition_cycles ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        latest_cycle = row_dict(latest_cycle_raw) if latest_cycle_raw else {}

        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "database_backend": getattr(conn, "backend", "unknown"),
            "validator_contract": CONTRACT_VERSION,
            "decision": (
                "CURRENT_HEAD_PUBLISHABLE_BUT_CATALOG_INCOMPLETE"
                if current_head_quality["total"] and current_head_quality["publishable"] == current_head_quality["total"] and all_job_quality["publishable"] < all_job_quality["total"]
                else "PUBLISHABLE"
                if current_head_quality["total"] and current_head_quality["publishable"] == current_head_quality["total"]
                else "NOT_PUBLISHABLE_AS_COMPLETE"
            ),
            "head": head,
            "latest_cycle": latest_cycle,
            "counts": counts,
            "raw_field_gaps": raw_field_gaps,
            "job_completeness": {"current_head": current_head_quality, "all_canonical_jobs": all_job_quality},
            "company_readiness": company_summary,
            "target_states": grouped(conn.execute("SELECT maturity_state, enabled, publication_enabled, quarantined, COUNT(*) AS count FROM acquisition_targets GROUP BY maturity_state, enabled, publication_enabled, quarantined ORDER BY count DESC").fetchall()),
            "task_states": grouped(conn.execute("SELECT status, COUNT(*) AS count FROM acquisition_tasks GROUP BY status ORDER BY count DESC").fetchall()),
            "observation_application_classifications": grouped(conn.execute("SELECT COALESCE(application_classification, '') AS classification, COUNT(*) AS count FROM job_source_observations GROUP BY application_classification ORDER BY count DESC").fetchall()),
            "observation_connectors": grouped(conn.execute("SELECT COALESCE(source_connector, '') AS connector, COUNT(*) AS count FROM job_source_observations GROUP BY source_connector ORDER BY count DESC").fetchall()),
        }
        jobs_csv = args.output_dir / "jobs_readiness.csv"
        companies_csv = args.output_dir / "companies_readiness.csv"
        write_csv(jobs_csv, evaluated_jobs, list(evaluated_jobs[0].keys()) if evaluated_jobs else [])
        write_csv(companies_csv, companies, list(companies[0].keys()) if companies else [])
        paths = {
            "collector_root": str(PROJECT_ROOT.resolve()),
            "runr_root": str(args.runr_root.resolve()),
            "env_file_used_redacted": str(args.env_file.resolve()),
            "migration_transcript": str((Path.home() / ".codex" / "attachments" / "0383ee05-fb65-451e-9a36-ed608b63fda5" / "pasted-text.txt").resolve()),
            "runr_completeness_contract": str((args.runr_root / "docs" / "JOB_PUBLICATION_COMPLETENESS_CONTRACT.md").resolve()),
            "runr_completeness_validator": str((args.runr_root / "backend" / "acquisition" / "job_publication_completeness.py").resolve()),
            "audit_script": str(Path(__file__).resolve()),
            "json_report": str((args.output_dir / "audit_summary.json").resolve()),
            "markdown_report": str((args.output_dir / "audit_report.md").resolve()),
            "jobs_queue": str(jobs_csv.resolve()),
            "companies_queue": str(companies_csv.resolve()),
        }
        summary["paths"] = paths
        (args.output_dir / "audit_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        (args.output_dir / "audit_report.md").write_text(render_report(summary, paths), encoding="utf-8")
        print(json.dumps({"decision": summary["decision"], "head": head, "job_completeness": summary["job_completeness"], "company_readiness": company_summary, "output_dir": str(args.output_dir.resolve())}, indent=2, ensure_ascii=False, default=str))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
