"""Deliver durable LinkedIn/employer producer state into the Runr catalog.

Collectors own their source SQLite databases. This command is the only bridge
from those databases to the shared acquisition repository: it reads producer
state, adapts rows to the source-observation contract, ingests each canonical
company as an independent target, and creates one explicit v2 publication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.acquisition.producer_adapters import (
    SOURCE_EMPLOYER,
    SOURCE_LINKEDIN,
    UNKNOWN,
    adapt_employer_job,
    adapt_linkedin_job,
    empty_observation_batch,
    iter_observation_batches,
    SqliteAcquisitionTransport,
)
from backend.application.source_eligibility_manifest import (
    load_manifest,
    validate_manifest_for_source,
)
from backend.repositories.sqlite_acquisition import SqliteAcquisitionStore


COMPLETE_LINKEDIN_SCAN_STATUSES = frozenset({"COMPLETE", "COMPLETE_ZERO_CONFIRMED", "SATURATED_RECOVERED"})
FAILED_EMPLOYER_STATUSES = frozenset({"discovery_failed", "source_failed", "failed", "error"})


def _text(value: object) -> str:
    return str(value or "").strip()


def _read_only_connection(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _decode(value: object, default: object) -> object:
    try:
        decoded = json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default
    return decoded


def _host(value: object) -> str:
    try:
        return (_text(urlsplit(_text(value)).hostname) or "").casefold().removeprefix("www.")
    except ValueError:
        return ""


def _resolve_company_id(value: object, crosswalk: Mapping[str, str] | None = None) -> str:
    company_id = _text(value)
    if not company_id:
        return ""
    mapping = crosswalk or {}
    return _text(mapping.get(f"old-company:{company_id}")) or company_id


def _manifest_companies(
    manifest: Mapping[str, object],
    source: str,
    *,
    pilot_only: bool,
    crosswalk: Mapping[str, str] | None = None,
) -> dict[str, dict[str, object]]:
    tasks = validate_manifest_for_source(manifest, source, pilot_only=pilot_only)
    rows = [item for item in (manifest.get("rows") or []) if isinstance(item, Mapping)]
    by_id: dict[str, dict[str, object]] = {}
    for task in tasks:
        company_id = _resolve_company_id(task.get("canonical_company_id"), crosswalk)
        if not company_id:
            continue
        representative = next(
            (item for item in rows if _resolve_company_id(item.get("canonical_company_id"), crosswalk) == company_id),
            {},
        )
        website = ((representative.get("website") or {}).get("url") or {}).get("canonical", "") if isinstance(representative.get("website"), Mapping) else ""
        linkedin = ((representative.get("linkedin") or {}).get("url") or {}).get("canonical", "") if isinstance(representative.get("linkedin"), Mapping) else ""
        by_id[company_id] = {
            "canonical_company_id": company_id,
            "canonical_company_name": _text(representative.get("company_name")) or company_id,
            "company_name": _text(representative.get("company_name")) or company_id,
            "website_url": _text(website),
            "linkedin_company_url": _text(linkedin),
            "official_employer_hosts": sorted({host for host in (_host(website),) if host}),
        }
    return by_id


def _latest_linkedin_statuses(connection: sqlite3.Connection) -> dict[str, str]:
    rows = connection.execute(
        """
        SELECT linkedin_company_id, status
        FROM company_scans latest
        WHERE started_at = (
            SELECT MAX(previous.started_at)
            FROM company_scans previous
            WHERE previous.linkedin_company_id = latest.linkedin_company_id
        )
        """
    ).fetchall()
    return {_text(row["linkedin_company_id"]): _text(row["status"]) for row in rows}


def _latest_employer_statuses(connection: sqlite3.Connection) -> dict[str, tuple[str, str]]:
    rows = connection.execute("SELECT company_key, status, payload_json FROM companies").fetchall()
    result: dict[str, tuple[str, str]] = {}
    for row in rows:
        payload = _decode(row["payload_json"], {})
        payload = payload if isinstance(payload, Mapping) else {}
        coverage = payload.get("coverage") if isinstance(payload.get("coverage"), Mapping) else {}
        classification = _text(coverage.get("outcome") or payload.get("terminal_classification"))
        result[_text(row["company_key"])] = (_text(row["status"]), classification)
    return result


def _linkedin_run_marker(connection: sqlite3.Connection) -> str:
    row = connection.execute("SELECT run_id FROM runs ORDER BY started_at DESC, run_id DESC LIMIT 1").fetchone()
    return _text(row["run_id"]) if row is not None else ""


def _employer_run_marker(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        "SELECT payload_json FROM companies ORDER BY updated_at DESC, company_key DESC LIMIT 1"
    ).fetchone()
    payload = _decode(row["payload_json"], {}) if row is not None else {}
    return _text(payload.get("generation_id") if isinstance(payload, Mapping) else "")


def _iter_linkedin_groups(
    connection: sqlite3.Connection,
    *,
    canonical_by_source_company: Mapping[str, str],
    selected_ids: set[str],
    crosswalk: Mapping[str, str] | None = None,
) -> Iterator[tuple[str, list[dict[str, object]]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    cursor = connection.execute(
        """
        SELECT linkedin_company_id, linkedin_job_id, run_id, company_scan_id, row_json
        FROM job_company_observations
        ORDER BY json_extract(row_json, '$.canonical_company_id'), linkedin_company_id, linkedin_job_id
        """
    )
    for row in cursor:
        payload = _decode(row["row_json"], {})
        if not isinstance(payload, Mapping):
            continue
        source_company_id = _text(row["linkedin_company_id"])
        canonical_id = _resolve_company_id(payload.get("canonical_company_id"), crosswalk) or _resolve_company_id(canonical_by_source_company.get(source_company_id), crosswalk)
        if canonical_id not in selected_ids:
            continue
        item = dict(payload)
        item.setdefault("linkedin_company_id", source_company_id)
        item.setdefault("linkedin_job_id", _text(row["linkedin_job_id"]))
        item.setdefault("run_id", _text(row["run_id"]))
        item.setdefault("company_scan_id", _text(row["company_scan_id"]))
        grouped.setdefault(canonical_id, []).append(item)
    yield from grouped.items()


def _iter_employer_groups(
    connection: sqlite3.Connection,
    *,
    selected_ids: set[str],
    crosswalk: Mapping[str, str] | None = None,
) -> Iterator[tuple[str, list[dict[str, object]]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    cursor = connection.execute(
        """
        SELECT payload_json
        FROM jobs
        ORDER BY json_extract(payload_json, '$.canonical_company_id'), source_key
        """
    )
    for row in cursor:
        payload = _decode(row["payload_json"], {})
        if not isinstance(payload, Mapping):
            continue
        canonical_id = _resolve_company_id(payload.get("canonical_company_id"), crosswalk)
        if canonical_id not in selected_ids:
            continue
        grouped.setdefault(canonical_id, []).append(dict(payload))
    yield from grouped.items()


def _target(company: Mapping[str, object], source: str) -> dict[str, object]:
    company_id = _text(company.get("canonical_company_id"))
    company_name = _text(company.get("canonical_company_name") or company.get("company_name")) or company_id
    source_label = "linkedin" if source == SOURCE_LINKEDIN else "employer"
    company_url = _text(company.get("linkedin_company_url") if source == SOURCE_LINKEDIN else company.get("website_url"))
    return {
        "target_id": f"producer_{source_label}_{company_id}",
        "target_kind": f"producer_{source_label}",
        "display_name": f"{company_name} ({source_label})",
        "canonical_target_url": company_url,
        "provenance_url": company_url,
        "request_url": company_url,
        # This is a job-source producer, not the separate Phase G applicant
        # intelligence source. Keep the connector distinct so the applicant
        # audit gate cannot block ordinary source-state delivery.
        "connector": f"producer_{source_label}",
        "provider": source_label,
        "source_token": company_id,
        "policy_version": "publication_policy_v2",
        "maturity_state": "proven",
        "enabled": True,
        "publication_enabled": True,
        "max_direct_requests": 1,
        "request_mode": "producer_state",
        "canonical_company_id": company_id,
        "canonical_company_name": company_name,
        "official_employer_hosts": list(company.get("official_employer_hosts") or []),
        "config": {
            "entity_kind": "employer",
            "canonical_company_id": company_id,
            "canonical_company_name": company_name,
            "source": source,
            "absence_grace_attempts": 3,
        },
    }


def _deliver_group(
    store: SqliteAcquisitionStore,
    *,
    cycle_id: str,
    task_id: str,
    target_id: str,
    observations: Iterable[object],
    closure_safe: bool,
    valid_snapshot: bool,
) -> dict[str, int | bool]:
    items = list(observations)
    batches = list(iter_observation_batches(items, max_batch_size=100))
    transport = SqliteAcquisitionTransport(store, cycle_id=cycle_id, task_id=task_id, target_id=target_id)
    if not batches:
        receipt = transport.send_final(
            empty_observation_batch(),
            snapshot_external_ids=(),
            valid_snapshot=valid_snapshot,
            closure_safe=closure_safe,
        )
        return dict(receipt.store_result)
    for batch in batches[:-1]:
        transport.send(batch)
    receipt = transport.send_final(
        batches[-1],
        snapshot_external_ids=(
            item.source_job_id for item in items if item.source_job_id not in {"", UNKNOWN}
        ),
        valid_snapshot=valid_snapshot,
        closure_safe=closure_safe,
    )
    return dict(receipt.store_result)


def run_delivery(
    *,
    manifest_path: Path,
    linkedin_state: Path,
    employer_state: Path,
    data_dir: Path,
    source_version: str,
    pilot_only: bool = False,
    company_ids: Iterable[str] | None = None,
    identity_crosswalk: Mapping[str, str] | None = None,
    identity_crosswalk_document: Mapping[str, object] | None = None,
) -> dict[str, object]:
    manifest = load_manifest(manifest_path)
    crosswalk = dict(identity_crosswalk or {})
    linkedin_companies = _manifest_companies(manifest, SOURCE_LINKEDIN, pilot_only=pilot_only, crosswalk=crosswalk)
    employer_companies = _manifest_companies(manifest, SOURCE_EMPLOYER, pilot_only=pilot_only, crosswalk=crosswalk)
    requested = {value.strip() for value in (company_ids or ()) if value.strip()}
    if requested:
        linkedin_companies = {key: value for key, value in linkedin_companies.items() if key in requested}
        employer_companies = {key: value for key, value in employer_companies.items() if key in requested}

    li_connection = _read_only_connection(linkedin_state)
    employer_connection = _read_only_connection(employer_state)
    try:
        linkedin_marker = _linkedin_run_marker(li_connection)
        employer_marker = _employer_run_marker(employer_connection)
        li_statuses = _latest_linkedin_statuses(li_connection)
        employer_statuses = _latest_employer_statuses(employer_connection)
        linkedin_org_to_canonical = {
            _text(association.get("linkedin_org_id")): _resolve_company_id(task.get("canonical_company_id"), crosswalk)
            for task in validate_manifest_for_source(manifest, SOURCE_LINKEDIN, pilot_only=pilot_only)
            for association in (task.get("organization_associations") or [])
            if isinstance(association, Mapping) and _text(association.get("linkedin_org_id"))
        }
        linkedin_statuses_by_canonical: dict[str, set[str]] = {}
        for source_company_id, status in li_statuses.items():
            canonical_id = _text(linkedin_org_to_canonical.get(source_company_id))
            if canonical_id:
                linkedin_statuses_by_canonical.setdefault(canonical_id, set()).add(status)
        linkedin_groups = dict(
            _iter_linkedin_groups(
                li_connection,
                canonical_by_source_company=linkedin_org_to_canonical,
                selected_ids=set(linkedin_companies),
                crosswalk=crosswalk,
            )
        )
        employer_groups = dict(
            _iter_employer_groups(employer_connection, selected_ids=set(employer_companies), crosswalk=crosswalk)
        )
    finally:
        li_connection.close()
        employer_connection.close()

    store = SqliteAcquisitionStore(data_dir / "backend.sqlite3")
    crosswalk_result: dict[str, object] = {}
    if identity_crosswalk_document:
        crosswalk_report = identity_crosswalk_document.get("report")
        crosswalk_report = crosswalk_report if isinstance(crosswalk_report, Mapping) else {}
        crosswalk_result = store.apply_company_identity_crosswalk(
            mapping_by_identity=crosswalk,
            merge_receipts=crosswalk_report.get("merge_receipts") or [],
            canonical_rows=crosswalk_report.get("canonical_rows") or [],
            provenance={
                "actor": "producer_state_publisher",
                "schema_version": _text(identity_crosswalk_document.get("schema_version")),
                "registry_sha256": _text(identity_crosswalk_document.get("registry_sha256")),
            },
        )
    source_specs = (
        (SOURCE_LINKEDIN, linkedin_companies, linkedin_groups, linkedin_marker),
        (SOURCE_EMPLOYER, employer_companies, employer_groups, employer_marker),
    )
    targets = [_target(company, source) for source, companies, _groups, _marker in source_specs for company in companies.values()]
    if not targets:
        return {
            "status": "no_eligible_companies",
            "manifest_id": _text(manifest.get("manifest_id")),
            "manifest_hash": _text(manifest.get("manifest_hash")),
            "source_version": source_version,
        }
    existing_target_ids = store.list_target_ids()
    store.ensure_targets(
        target for target in targets if _text(target.get("target_id")) not in existing_target_ids
    )
    marker = "|".join([_text(manifest.get("manifest_hash")), linkedin_marker, employer_marker, source_version])
    cycle_key = "producer:" + hashlib.sha256(marker.encode("utf-8")).hexdigest()[:24]
    cycle = store.claim_due_cycle(
        window_key=cycle_key,
        lease_owner=f"producer_bridge:{os.getpid()}",
        scheduled_at=datetime.now(timezone.utc).isoformat(),
        force=True,
        manifest_version=_text(manifest.get("manifest_hash")),
        scope_key="producer_state",
    )
    if cycle is None:
        return {"status": "already_running", "cycle_key": cycle_key}
    cycle_id = _text(cycle.get("cycle_id"))
    store.ensure_cycle_tasks(cycle_id, targets)
    cycle_targets = {
        target_id: {"task": {"task_id": task_id}}
        for target_id, task_id in store.list_cycle_task_ids(cycle_id).items()
    }
    all_target_ids: list[str] = []
    partial = False
    metrics: dict[str, object] = {
        "status": "running",
        "cycle_id": cycle_id,
        "cycle_key": cycle_key,
        "manifest_id": _text(manifest.get("manifest_id")),
        "manifest_hash": _text(manifest.get("manifest_hash")),
        "source_version": source_version,
        "sources": {},
        "unresolved_observations": 0,
        "identity_crosswalk": crosswalk_result,
    }

    def deliver_company(
        source: str,
        company_id: str,
        company: Mapping[str, object],
    ) -> dict[str, object]:
        target_id = _text(_target(company, source)["target_id"])
        task = (cycle_targets.get(target_id) or {}).get("task") or {}
        task_id = _text(task.get("task_id")) or f"producer_task:{target_id}"
        raw_rows = groups.get(company_id, [])
        failed = False
        if source == SOURCE_LINKEDIN:
            observations = [
                adapt_linkedin_job(row, cycle_id=cycle_id, scan_id=_text(row.get("company_scan_id")))
                for row in raw_rows
            ]
            status_values = {
                _text(li_statuses.get(_text(row.get("linkedin_company_id"))))
                for row in raw_rows
                if _text(row.get("linkedin_company_id"))
            }
            status_values.update(linkedin_statuses_by_canonical.get(company_id, set()))
            closure_safe = bool(status_values) and status_values.issubset(COMPLETE_LINKEDIN_SCAN_STATUSES)
            valid_snapshot = True
        else:
            observations = [
                adapt_employer_job(row, cycle_id=cycle_id)
                for row in raw_rows
            ]
            status, classification = employer_statuses.get(company_id, ("", ""))
            closure_safe = classification == "confirmed_complete"
            failed = status.casefold() in FAILED_EMPLOYER_STATUSES
            valid_snapshot = not failed
        deliverable = [item for item in observations if item.canonical_company_id not in {"", UNKNOWN, "//"}]
        result = _deliver_group(
            store,
            cycle_id=cycle_id,
            task_id=task_id,
            target_id=target_id,
            observations=deliverable,
            closure_safe=closure_safe,
            valid_snapshot=valid_snapshot,
        )
        store.complete_task(
            task_id,
            status="completed" if closure_safe else "partial",
            result={
                **result,
                "complete_snapshot": True,
                "valid_snapshot": valid_snapshot,
                "closure_safe": closure_safe,
                "credible_evidence": closure_safe,
                "collection_metadata": {
                    "producer_bridge": True,
                    "source": source,
                    "source_marker": marker_value,
                    "unresolved_observations": len(observations) - len(deliverable),
                },
            },
        )
        return {
            "target_id": target_id,
            "closure_safe": closure_safe,
            "failed": failed,
            "jobs_delivered": len(deliverable),
            "unresolved_observations": len(observations) - len(deliverable),
        }

    try:
        for source, companies, groups, marker_value in source_specs:
            source_metrics = {"companies": len(companies), "groups_with_jobs": len(groups), "jobs_delivered": 0, "partial_companies": 0, "failed_companies": 0, "source_marker": marker_value}
            company_items = [
                (company_id, company)
                for company_id, company in companies.items()
                if (
                    company_id in groups
                    or (
                        source == SOURCE_LINKEDIN
                        and company_id in linkedin_statuses_by_canonical
                    )
                    or (
                        source == SOURCE_EMPLOYER
                        and company_id in employer_statuses
                    )
                )
            ]
            source_metrics["companies_pending_source_state"] = len(companies) - len(company_items)
            for offset in range(0, len(company_items), 100):
                with store.transaction_scope():
                    for company_id, company in company_items[offset : offset + 100]:
                        delivered = deliver_company(source, company_id, company)
                        source_metrics["unresolved_observations"] = int(source_metrics.get("unresolved_observations") or 0) + int(delivered["unresolved_observations"])
                        source_metrics["jobs_delivered"] = int(source_metrics["jobs_delivered"]) + int(delivered["jobs_delivered"])
                        if bool(delivered["failed"]):
                            source_metrics["failed_companies"] = int(source_metrics["failed_companies"]) + 1
                        if not bool(delivered["closure_safe"]):
                            partial = True
                            source_metrics["partial_companies"] = int(source_metrics["partial_companies"]) + 1
                        all_target_ids.append(str(delivered["target_id"]))
            metrics["sources"][source] = source_metrics
        publication_id = store.publish_valid_snapshot(
            cycle_id=cycle_id,
            valid_target_ids=all_target_ids,
            origin="scheduled",
            created_by="producer_bridge",
            scheduled_run_id=cycle_id,
            policy_version="publication_policy_v2",
        )
        store.complete_cycle(
            cycle_id,
            status="degraded" if partial else "completed",
            publication_id=publication_id,
            error_code="partial_source_coverage" if partial else "",
            error_message="One or more source companies lacked closure-safe completeness evidence." if partial else "",
        )
        report = store.get_cycle_report(cycle_id)
        metrics.update({
            "status": "degraded" if partial else "completed",
            "publication_id": publication_id,
            "report": report,
        })
        return metrics
    except BaseException as exc:
        store.complete_cycle(cycle_id, status="recovery_required", error_code=type(exc).__name__.casefold(), error_message=str(exc)[:500])
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--linkedin-state", type=Path, required=True)
    parser.add_argument("--employer-state", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--source-version", default=os.getenv("RUNR_SOURCE_VERSION", ""))
    parser.add_argument("--company-ids", nargs="*")
    parser.add_argument("--pilot-only", action="store_true")
    parser.add_argument("--identity-crosswalk", type=Path, help="optional reviewed company_identity_crosswalk.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    identity_crosswalk = {}
    identity_crosswalk_document: Mapping[str, object] | None = None
    if args.identity_crosswalk:
        document = json.loads(args.identity_crosswalk.resolve().read_text(encoding="utf-8"))
        if not isinstance(document, Mapping):
            raise ValueError("identity crosswalk must be a JSON object")
        identity_crosswalk_document = document
        identity_crosswalk = {
            _text(key): _text(value)
            for key, value in (document.get("mapping_by_identity") or {}).items()
            if _text(key) and _text(value)
        }
    result = run_delivery(
        manifest_path=args.manifest.resolve(),
        linkedin_state=args.linkedin_state.resolve(),
        employer_state=args.employer_state.resolve(),
        data_dir=args.data_dir.resolve(),
        source_version=_text(args.source_version) or "unknown",
        pilot_only=bool(args.pilot_only),
        company_ids=args.company_ids,
        identity_crosswalk=identity_crosswalk,
        identity_crosswalk_document=identity_crosswalk_document,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
