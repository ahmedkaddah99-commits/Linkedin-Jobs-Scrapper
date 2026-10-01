"""Deliver durable LinkedIn/employer producer state into the Runr catalog.

Collectors own their source SQLite databases. This command is the only bridge
from those databases to the shared acquisition repository: it reads producer
state, adapts rows to the source-observation contract, ingests each canonical
company as an independent target, and creates one explicit publication.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock, local
from time import monotonic, sleep
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.acquisition.producer_adapters import (
    SOURCE_EMPLOYER,
    SOURCE_LINKEDIN,
    UNKNOWN,
    _observation_to_ingest_job,
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
from backend.application.company_identity_canonicalization import (
    resolve_company_id as resolve_company_identity,
)
from backend.acquisition.job_publication_completeness import validate_job_for_publication
from backend.acquisition.publication import DEFAULT_PUBLICATION_POLICY_VERSION
from backend.repositories.sqlite_acquisition import SqliteAcquisitionStore


COMPLETE_LINKEDIN_SCAN_STATUSES = frozenset({"COMPLETE", "COMPLETE_ZERO_CONFIRMED", "SATURATED_RECOVERED"})
FAILED_EMPLOYER_STATUSES = frozenset({"discovery_failed", "source_failed", "failed", "error"})
RUNTIME_PUBLICATION_POLICY_VERSION = DEFAULT_PUBLICATION_POLICY_VERSION
REGISTERED_PUBLICATION_POLICY_VERSIONS = frozenset({"publication_policy_v1", "publication_policy_v2"})
PUBLICATION_POLICY_VERSION_ENV = "RUNR_PUBLICATION_POLICY_VERSION"
APPROVED_PUBLICATION_POLICIES_ENV = "RUNR_APPROVED_PUBLICATION_POLICIES"

TELEMETRY_SCHEMA_VERSION = "runr.producer.telemetry.v1"
TELEMETRY_SOURCE_KEYS = frozenset(
    {
        "checkpoint_age_seconds",
        "stale_checkpoint",
        "publish_lag_seconds",
        "last_cycle_id",
        "last_publication_id",
    }
)
DEFAULT_STALE_CHECKPOINT_SECONDS = 86400
_SENIORITY_IN_TITLE = re.compile(
    r"\b(senior|sr\.?|lead|principal|staff|junior|jr\.?|entry.level|intern|trainee|"
    r"berufseinsteiger|werkstudent|praktikant|teamleit[eu]ng)\b",
    re.IGNORECASE,
)
_EXPLICIT_WORKPLACE = re.compile(r"\b(remote|hybrid|on[- ]site|onsite|vor\s+ort)\b", re.IGNORECASE)


@dataclass(frozen=True)
class BackfillControls:
    """Operator limits for one bounded producer-state backfill attempt."""

    batch_size: int = 250
    max_companies: int | None = None
    rate_per_second: float = 0.0
    timeout_seconds: float | None = None
    max_failures: int = 0
    dry_run: bool = False

    def __post_init__(self) -> None:
        if not 1 <= int(self.batch_size) <= 1000:
            raise ValueError("batch_size must be between 1 and 1000")
        if self.max_companies is not None and int(self.max_companies) < 1:
            raise ValueError("max_companies must be positive")
        if float(self.rate_per_second) < 0:
            raise ValueError("rate_per_second must be non-negative")
        if self.timeout_seconds is not None and float(self.timeout_seconds) <= 0:
            raise ValueError("timeout_seconds must be positive")
        if int(self.max_failures) < 0:
            raise ValueError("max_failures must be non-negative")

    @property
    def limits(self) -> dict[str, int | float | None]:
        return {
            "batch_size": int(self.batch_size),
            "max_companies": int(self.max_companies) if self.max_companies is not None else None,
            "rate_per_second": float(self.rate_per_second),
            "timeout_seconds": float(self.timeout_seconds) if self.timeout_seconds is not None else None,
            "max_failures": int(self.max_failures),
        }


def _default_backfill_controls(*, dry_run: bool = False) -> BackfillControls:
    def env_int(name: str, default: int) -> int:
        raw = os.getenv(name, str(default)).strip()
        try:
            return int(raw)
        except ValueError:
            return default

    def env_float(name: str, default: float | None) -> float | None:
        raw = os.getenv(name, "").strip()
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    return BackfillControls(
        batch_size=env_int("RUNR_PUBLISHER_SOURCE_ROW_BATCH_SIZE", 250),
        rate_per_second=env_float("RUNR_PUBLISHER_RATE_PER_SECOND", 0.0) or 0.0,
        timeout_seconds=env_float("RUNR_PUBLISHER_TIMEOUT_SECONDS", None),
        max_failures=env_int("RUNR_PUBLISHER_MAX_FAILURES", 0),
        dry_run=dry_run,
    )


def _receipt(
    controls: BackfillControls,
    *,
    started_at: str,
    started_monotonic: float,
    status: str,
    failures: int = 0,
    stop_reason: str = "",
    eligibility: Mapping[str, int] | None = None,
) -> dict[str, object]:
    finished_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    result: dict[str, object] = {
        "schema_version": "runr.producer.backfill-receipt.v1",
        "dry_run": bool(controls.dry_run),
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_seconds": round(max(0.0, monotonic() - started_monotonic), 3),
        "limits": controls.limits,
        "failures": int(failures),
        "stop_reason": stop_reason,
        "resume": True,
    }
    if eligibility is not None:
        result["eligibility"] = {
            "eligible": int(eligibility.get("eligible") or 0),
            "ineligible": int(eligibility.get("ineligible") or 0),
        }
    return result


def _with_receipt(
    result: dict[str, object],
    controls: BackfillControls,
    *,
    started_at: str,
    started_monotonic: float,
    failures: int = 0,
    stop_reason: str = "",
    eligibility: Mapping[str, int] | None = None,
) -> dict[str, object]:
    result["limits"] = controls.limits
    result["failures"] = int(failures)
    if stop_reason:
        result["stop_reason"] = stop_reason
    result["receipt"] = _receipt(
        controls,
        started_at=started_at,
        started_monotonic=started_monotonic,
        status=str(result.get("status") or "unknown"),
        failures=failures,
        stop_reason=stop_reason,
        eligibility=eligibility,
    )
    return result


def _preview_eligibility(
    source_specs: Iterable[tuple[str, Mapping[str, Mapping[str, object]], Mapping[str, list[Mapping[str, object]]]]],
    *,
    cycle_id: str,
    max_companies: int | None = None,
) -> dict[str, int]:
    """Classify source rows without opening or mutating the acquisition store."""

    company_ids = {
        company_id
        for _source, companies, _groups in source_specs
        for company_id in companies
    }
    eligible = 0
    ineligible = 0
    companies_seen = 0
    for source, companies, groups in source_specs:
        for company_id in companies:
            if max_companies is not None and companies_seen >= max_companies:
                return {"eligible": eligible, "ineligible": ineligible}
            companies_seen += 1
            for row in groups.get(company_id, []):
                observation = (
                    adapt_linkedin_job(row, cycle_id=cycle_id, scan_id=_text(row.get("company_scan_id")))
                    if source == SOURCE_LINKEDIN
                    else adapt_employer_job(row, cycle_id=cycle_id)
                )
                candidate = dict(observation.normalized_mapping)
                candidate.update(_observation_to_ingest_job(observation))
                result = validate_job_for_publication(
                    candidate,
                    company_registry=company_ids,
                    require_application_destination=True,
                )
                if result.publishable:
                    eligible += 1
                else:
                    ineligible += 1
    return {"eligible": eligible, "ineligible": ineligible}
def resolve_runtime_publication_policy(
    requested_version: str | None = None,
    *,
    approved_versions: Iterable[str] = (),
    rollback_to: str | None = None,
) -> str:
    """Resolve an explicit policy flag without implicitly relaxing publication."""

    if requested_version and rollback_to:
        raise ValueError("Choose a policy version or rollback target, not both.")
    approved = {
        item.strip()
        for item in os.getenv(APPROVED_PUBLICATION_POLICIES_ENV, "").split(",")
        if item.strip()
    }
    approved.update(str(item).strip() for item in approved_versions if str(item).strip())
    requested = str(
        rollback_to
        or requested_version
        or os.getenv(PUBLICATION_POLICY_VERSION_ENV, "")
        or RUNTIME_PUBLICATION_POLICY_VERSION
    ).strip()
    if requested not in REGISTERED_PUBLICATION_POLICY_VERSIONS:
        raise ValueError(f"Unknown publication policy: {requested}")
    if requested != RUNTIME_PUBLICATION_POLICY_VERSION and requested not in approved and not rollback_to:
        raise ValueError(
            f"Publication policy {requested} requires owner approval or an explicit rollback target."
        )
    return requested


def _resource_peaks() -> dict[str, float | int | None]:
    peaks: dict[str, float | int | None] = {"max_rss_bytes": None, "cpu_seconds": None}
    try:
        import resource
    except ImportError:
        return peaks
    usage = resource.getrusage(resource.RUSAGE_SELF)
    if usage.ru_maxrss:
        peaks["max_rss_bytes"] = int(usage.ru_maxrss) * 1024
    peaks["cpu_seconds"] = round(float(usage.ru_utime) + float(usage.ru_stime), 3)
    return peaks


def _stale_checkpoint_seconds() -> int:
    raw = os.getenv("RUNR_TELEMETRY_STALE_CHECKPOINT_SECONDS", "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            return DEFAULT_STALE_CHECKPOINT_SECONDS
        if value > 0:
            return value
    return DEFAULT_STALE_CHECKPOINT_SECONDS


def _checkpoint_age_seconds(checkpoint: Mapping[str, object], now: str) -> float | None:
    stamp = _text(checkpoint.get("updated_at"))
    if not stamp:
        return None
    try:
        updated = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        reference = datetime.fromisoformat(now.replace("Z", "+00:00"))
    except ValueError:
        return None
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return max(0.0, (reference - updated).total_seconds())


def _publisher_telemetry(
    checkpoints: Mapping[str, Mapping[str, object]], now: str
) -> dict[str, object]:
    threshold = _stale_checkpoint_seconds()
    sources: dict[str, object] = {}
    for source, checkpoint in sorted(checkpoints.items()):
        age = _checkpoint_age_seconds(checkpoint, now)
        sources[source] = {
            "checkpoint_age_seconds": round(age, 3) if age is not None else None,
            "stale_checkpoint": age is None or age > threshold,
            "publish_lag_seconds": (
                round(age, 3)
                if age is not None and bool(checkpoint.get("bootstrap_complete"))
                else None
            ),
            "last_cycle_id": _text(checkpoint.get("last_cycle_id")),
            "last_publication_id": _text(checkpoint.get("last_publication_id")),
        }
    return {
        "schema_version": TELEMETRY_SCHEMA_VERSION,
        "stale_checkpoint_seconds": threshold,
        "sources": sources,
        "resource_peaks": _resource_peaks(),
    }


_PROGRESS_LOCK = Lock()


def _progress(phase: str, **counts: int) -> None:
    """Optional bounded status file; does not change the final metrics format."""
    destination = os.getenv("RUNR_PUBLISHER_PROGRESS_FILE", "").strip()
    if not destination:
        return
    path = Path(destination)
    payload = {"phase": phase, "timestamp": datetime.now(timezone.utc).isoformat(),
               "pid": os.getpid(), "counts": counts}
    with _PROGRESS_LOCK:
        try:
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            temporary.replace(path)
        except OSError as error:
            print(f"publisher_progress_write_failed:{type(error).__name__}", file=sys.stderr, flush=True)


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


def read_incremental_rows(
    connection: sqlite3.Connection,
    *,
    source: str,
    rowid: int,
    limit: int,
) -> tuple[list[sqlite3.Row], int, bool]:
    """Read a bounded source rowid window and return its durable high-water mark."""

    table = "job_company_observations" if source == SOURCE_LINKEDIN else "jobs"
    rows = connection.execute(
        f"SELECT rowid, * FROM {table} WHERE rowid > ? ORDER BY rowid LIMIT ?",
        (max(0, int(rowid)), max(1, int(limit))),
    ).fetchall()
    high_watermark = int(rows[-1]["rowid"] if isinstance(rows[-1], sqlite3.Row) else rows[-1][0]) if rows else max(0, int(rowid))
    return rows, high_watermark, len(rows) < max(1, int(limit))


def _ensure_publisher_checkpoint_table(store: SqliteAcquisitionStore) -> None:
    """Explicit preflight: the checkpoint schema is owned by migration
    ``061_acquisition_publisher_checkpoints`` in the WS-5 registry, so this
    fails fast instead of creating the table ad hoc."""

    store.require_publisher_checkpoint_table()


def _crosswalk_already_applied(
    store: SqliteAcquisitionStore,
    *,
    mapping: Mapping[str, str],
    document: Mapping[str, object],
) -> bool:
    """Check the stored registry before repeating its expensive merge."""

    registry_sha = _text(document.get("registry_sha256"))
    if not registry_sha or not mapping:
        return False
    report = document.get("report")
    report = report if isinstance(report, Mapping) else {}
    canonical_ids = {
        _text(row.get("canonical_CompanyID") or row.get("canonical_company_id"))
        for row in (report.get("canonical_rows") or [])
        if isinstance(row, Mapping)
    }
    canonical_ids.discard("")

    def check(connection: sqlite3.Connection) -> bool:
        stored = {
            _text(row[0]): _text(row[1])
            for row in connection.execute(
                "SELECT source_identity_key, winner_company_id, provenance_json FROM company_identity_crosswalk"
            )
            if _decode(row[2], {}).get("registry_sha256") == registry_sha
        }
        if any(stored.get(key) != value for key, value in mapping.items()):
            return False
        if canonical_ids:
            present = {
                _text(row[0])
                for row in connection.execute("SELECT company_id FROM canonical_companies")
            }
            if not canonical_ids.issubset(present):
                return False
        return True

    return bool(store._run_transaction(check))


def _verified_company_registry(manifest_path: Path) -> tuple[dict[str, dict[str, str]], str]:
    """Load recently verified company facts beside the reviewed source manifest."""

    path = Path(os.getenv("RUNR_PUBLISHER_COMPANY_REGISTRY") or manifest_path.with_name("company_registry_canonical.csv"))
    if not path.is_file():
        return {}, ""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    current_time = datetime.now(timezone.utc)
    cutoff = current_time - timedelta(days=90)
    verified: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            company_id = _text(row.get("canonical_CompanyID"))
            logo = _text(row.get("logo_url"))
            try:
                logo_url = urlsplit(logo)
            except ValueError:
                continue
            if (
                not company_id
                or _text(row.get("enrichment_status")) != "succeeded"
                or logo_url.scheme != "https"
                or not logo_url.hostname
            ):
                continue
            try:
                enriched_at = datetime.fromisoformat(_text(row.get("last_enriched_at")).replace("Z", "+00:00"))
            except ValueError:
                continue
            if enriched_at.tzinfo is None or not cutoff <= enriched_at <= current_time:
                continue
            facts = {
                key: _text(row.get(key))
                for key in ("industry", "description", "employee_count", "headquarters_display", "website_url")
                if _text(row.get(key))
            }
            if facts:
                verified[company_id] = {"logo_url": logo, "last_enriched_at": enriched_at.isoformat(), **facts}
    return verified, digest


def _explicit_workplace(value: str) -> str:
    match = _EXPLICIT_WORKPLACE.search(value)
    if match is None:
        return ""
    nearby = value[max(0, match.start() - 25):match.start()].casefold()
    if re.search(r"\b(no|not|kein(?:e|en)?|nicht|without)\s+(?:\w+\s+){0,2}$", nearby):
        return ""
    return match.group(0)


def _enrich_source_groups(
    groups: Mapping[str, list[dict[str, object]]],
    *,
    verified_companies: Mapping[str, Mapping[str, str]],
    registry_sha256: str,
) -> dict[str, list[dict[str, object]]]:
    enriched: dict[str, list[dict[str, object]]] = {}
    for company_id, rows in groups.items():
        company = verified_companies.get(company_id)
        enriched_rows: list[dict[str, object]] = []
        for original in rows:
            row = dict(original)
            evidence: dict[str, object] = {}
            if company:
                if not _text(row.get("company_logo") or row.get("logo_url")):
                    row["company_logo"] = company["logo_url"]
                if not row.get("company_enrichment"):
                    row["company_enrichment"] = {
                        "source": "verified_company_registry",
                        "registry_sha256": registry_sha256,
                        "verified_at": company["last_enriched_at"],
                        "fields": {key: value for key, value in company.items() if key not in {"logo_url", "last_enriched_at"}},
                    }
                evidence["company_registry_sha256"] = registry_sha256
            if not _text(row.get("seniority") or row.get("experience_level")):
                match = _SENIORITY_IN_TITLE.search(_text(row.get("job_title") or row.get("title")))
                if match:
                    row["seniority"] = match.group(0)
                    evidence["seniority_source"] = "explicit_job_title"
            if not _text(row.get("workplace_type") or row.get("workplace_arrangement")):
                for field in ("job_title", "title", "location", "location_raw", "description_text", "description"):
                    value = _explicit_workplace(_text(row.get(field)))
                    if value:
                        row["workplace_type"] = value
                        evidence["workplace_source"] = f"explicit_{field}"
                        break
            if evidence:
                row["publication_enrichment_evidence"] = evidence
            enriched_rows.append(row)
        enriched[company_id] = enriched_rows
    return enriched


def _row_value(row: Mapping[str, object], key: str) -> object:
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return ""


def _row_payload(row: Mapping[str, object]) -> dict[str, object]:
    payload = _decode(_row_value(row, "row_json") or _row_value(row, "payload_json"), {})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _source_group_from_rows(
    rows: Iterable[Mapping[str, object]],
    *,
    source: str,
    canonical_by_source_company: Mapping[str, str],
    selected_ids: set[str],
    crosswalk: Mapping[str, str] | None = None,
) -> tuple[dict[str, list[dict[str, object]]], set[str]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    source_company_ids: set[str] = set()
    for row in rows:
        payload = _row_payload(row)
        source_company_id = _text(_row_value(row, "linkedin_company_id")) if source == SOURCE_LINKEDIN else ""
        identity_payload = dict(payload)
        if source_company_id:
            identity_payload.setdefault("linkedin_company_id", source_company_id)
            identity_payload.setdefault(
                "linkedin_company_url",
                _text(payload.get("source_company_url") or payload.get("linkedin_company_url")),
            )
        resolved_identity = resolve_company_identity(identity_payload, crosswalk or {})
        canonical_id = _resolve_company_id(
            resolved_identity
            or payload.get("canonical_company_id")
            or canonical_by_source_company.get(source_company_id)
            or (_row_value(row, "company_key") if source == SOURCE_EMPLOYER else ""),
            crosswalk,
        )
        if not canonical_id or canonical_id not in selected_ids:
            continue
        if source_company_id:
            source_company_ids.add(source_company_id)
        item = dict(payload)
        if source == SOURCE_LINKEDIN:
            # Inactive postings remain in producer state for history, but must
            # not be presented as observations in an active snapshot.
            if _text(item.get("lifecycle_status")) == "inactive":
                continue
            item.setdefault("linkedin_company_id", source_company_id)
            item.setdefault("linkedin_job_id", _text(_row_value(row, "linkedin_job_id")))
            item.setdefault("run_id", _text(_row_value(row, "run_id")))
            item.setdefault("company_scan_id", _text(_row_value(row, "company_scan_id")))
        grouped.setdefault(canonical_id, []).append(item)
    return grouped, source_company_ids


def _current_employer_jobs(
    connection: sqlite3.Connection,
    groups: dict[str, list[dict[str, object]]],
    crosswalk: Mapping[str, str] | None = None,
) -> dict[str, list[dict[str, object]]]:
    """Exclude retained jobs absent from a verified complete employer scan.

    Partial scans preserve older jobs. Legacy jobs without a generation marker
    are retired only after the company has a new complete generation.
    """
    if not groups:
        return groups
    result = dict(groups)
    keys = set(groups)
    keys.update(
        old for old, winner in (crosswalk or {}).items()
        if _resolve_company_id(winner, crosswalk) in groups
    )
    ordered_keys = sorted(keys)
    for start in range(0, len(ordered_keys), 400):
        batch = ordered_keys[start:start + 400]
        placeholders = ",".join("?" for _ in batch)
        rows = connection.execute(
            f"""SELECT companies.company_key, companies.payload_json,
                       coverage_receipts.receipt_json
                FROM companies LEFT JOIN coverage_receipts
                  ON coverage_receipts.company_key=companies.company_key
                WHERE companies.company_key IN ({placeholders})""",
            tuple(batch),
        ).fetchall()
        for row in rows:
            payload = _decode(row["payload_json"], {})
            if not isinstance(payload, Mapping):
                continue
            receipt = _decode(row["receipt_json"], {})
            generation = _text(payload.get("generation_id"))
            verified = (
                isinstance(receipt, Mapping)
                and _text(receipt.get("generation_id")) == generation
                and _text(receipt.get("terminal_classification")) == "confirmed_complete"
            )
            company_id = _resolve_company_id(
                payload.get("canonical_company_id") or row["company_key"], crosswalk
            )
            if company_id in groups and verified and generation:
                result[company_id] = [
                    job for job in groups[company_id]
                    if _text(job.get("last_seen_generation_id")) == generation
                ]
    return result


def _load_incremental_source(
    connection: sqlite3.Connection,
    *,
    source: str,
    checkpoint: Mapping[str, object],
    canonical_by_source_company: Mapping[str, str],
    selected_ids: set[str],
    crosswalk: Mapping[str, str] | None,
    batch_size: int,
    now: str,
) -> tuple[dict[str, list[dict[str, object]]], set[str], dict[str, object], bool]:
    """Load only a bootstrap chunk or rows belonging to changed companies."""

    next_checkpoint = dict(checkpoint)
    if not bool(checkpoint.get("bootstrap_complete")):
        rows, high_watermark, complete = read_incremental_rows(
            connection,
            source=source,
            rowid=int(checkpoint.get("source_rowid") or 0),
            limit=batch_size,
        )
        live_source_ids: set[str] = set()
        if source == SOURCE_LINKEDIN:
            latest_run = connection.execute(
                "SELECT run_id FROM company_scans WHERE run_id <> '' ORDER BY finished_at DESC, rowid DESC LIMIT 1"
            ).fetchone()
            latest_run_id = _text(latest_run[0]) if latest_run is not None else ""
            if latest_run_id:
                live_source_ids = {
                    _text(row[0])
                    for row in connection.execute(
                        "SELECT DISTINCT linkedin_company_id FROM company_scans WHERE run_id=?",
                        (latest_run_id,),
                    ).fetchall()
                    if _text(row[0])
                }
                live_rows = connection.execute(
                    "SELECT rowid,linkedin_company_id,linkedin_job_id,run_id,company_scan_id,row_json FROM job_company_observations WHERE run_id=? ORDER BY rowid DESC LIMIT ?",
                    (latest_run_id, max(1, int(batch_size))),
                ).fetchall()
                rows = [*rows, *live_rows]
        grouped, _source_company_ids = _source_group_from_rows(
            rows,
            source=source,
            canonical_by_source_company=canonical_by_source_company,
            selected_ids=selected_ids,
            crosswalk=crosswalk,
        )
        if source == SOURCE_EMPLOYER:
            grouped = _current_employer_jobs(connection, grouped, crosswalk)
        next_checkpoint.update(
            {
                "source": source,
                "source_rowid": high_watermark,
                "bootstrap_complete": complete,
                "source_watermark": now if complete else _text(checkpoint.get("source_watermark")),
            }
        )
        live_changed_ids = {
            _resolve_company_id(canonical_by_source_company.get(source_id), crosswalk)
            for source_id in live_source_ids
            if canonical_by_source_company.get(source_id)
        }
        changed_ids = {value for value in (*grouped.keys(), *live_changed_ids) if value in selected_ids}
        return grouped, changed_ids, next_checkpoint, bool(rows)

    watermark = _text(checkpoint.get("source_watermark"))
    linkedin_source_ids: set[str] = set()
    if source == SOURCE_LINKEDIN:
        changed_rows = connection.execute(
            """SELECT DISTINCT linkedin_company_id FROM company_scans WHERE finished_at > ?
               UNION SELECT DISTINCT linkedin_company_id FROM job_company_observations WHERE last_seen_at > ?""",
            (watermark, watermark),
        ).fetchall()
        linkedin_source_ids = {_text(row[0]) for row in changed_rows if _text(row[0])}
        if linkedin_source_ids:
            placeholders = ",".join("?" for _ in linkedin_source_ids)
            rows = connection.execute(
                f"SELECT linkedin_company_id,linkedin_job_id,run_id,company_scan_id,row_json FROM job_company_observations WHERE linkedin_company_id IN ({placeholders}) ORDER BY linkedin_company_id,linkedin_job_id",
                tuple(sorted(linkedin_source_ids)),
            ).fetchall()
        else:
            rows = []
    else:
        changed_companies = {
            _text(row[0])
            for row in connection.execute("SELECT company_key FROM companies WHERE updated_at > ?", (watermark,)).fetchall()
            if _text(row[0])
        }
        changed_jobs = connection.execute("SELECT payload_json FROM jobs WHERE updated_at > ?", (watermark,)).fetchall()
        for row in changed_jobs:
            payload = _row_payload(row)
            company_id = _resolve_company_id(payload.get("canonical_company_id"), crosswalk)
            if company_id:
                changed_companies.add(company_id)
        if changed_companies:
            rows = connection.execute("SELECT source_key,payload_json FROM jobs ORDER BY source_key").fetchall()
            rows = [row for row in rows if _resolve_company_id(_row_payload(row).get("canonical_company_id"), crosswalk) in changed_companies]
        else:
            rows = []
    grouped, _source_company_ids = _source_group_from_rows(
        rows,
        source=source,
        canonical_by_source_company=canonical_by_source_company,
        selected_ids=selected_ids,
        crosswalk=crosswalk,
    )
    if source == SOURCE_EMPLOYER:
        grouped = _current_employer_jobs(connection, grouped, crosswalk)
    changed_ids = set(grouped)
    if source == SOURCE_EMPLOYER:
        changed_ids.update(changed_companies)
    if source == SOURCE_LINKEDIN:
        changed_ids.update(
            _resolve_company_id(canonical_by_source_company.get(source_id), crosswalk)
            for source_id in linkedin_source_ids
            if canonical_by_source_company.get(source_id)
        )
    next_checkpoint.update({"source": source, "source_watermark": now})
    return grouped, {value for value in changed_ids if value in selected_ids}, next_checkpoint, bool(changed_ids)


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
    representatives: dict[str, Mapping[str, object]] = {}
    for item in rows:
        company_id = _text(item.get("canonical_company_id"))
        if company_id and company_id not in representatives:
            representatives[company_id] = item
    by_id: dict[str, dict[str, object]] = {}
    for task in tasks:
        original_company_id = _text(task.get("canonical_company_id"))
        if not original_company_id:
            continue
        representative = representatives.get(original_company_id, {})
        website = ((representative.get("website") or {}).get("url") or {}).get("canonical", "") if isinstance(representative.get("website"), Mapping) else ""
        linkedin = ((representative.get("linkedin") or {}).get("url") or {}).get("canonical", "") if isinstance(representative.get("linkedin"), Mapping) else ""
        identity_payload = {
            **dict(representative),
            "canonical_company_id": original_company_id,
            "website_url": _text(website),
            "linkedin_company_url": _text(linkedin),
        }
        linkedin_company_ids = tuple(
            _text(association.get("linkedin_org_id"))
            for association in (task.get("organization_associations") or [])
            if isinstance(association, Mapping) and _text(association.get("linkedin_org_id"))
        )
        if source == SOURCE_LINKEDIN and linkedin_company_ids:
            identity_payload["linkedin_company_id"] = linkedin_company_ids[0]
        company_id = _text(resolve_company_identity(identity_payload, crosswalk or {})) or original_company_id
        by_id[company_id] = {
            "canonical_company_id": company_id,
            "canonical_company_name": _text(representative.get("company_name")) or company_id,
            "company_name": _text(representative.get("company_name")) or company_id,
            "website_url": _text(website),
            "linkedin_company_url": _text(linkedin),
            "linkedin_company_ids": linkedin_company_ids,
            "official_employer_hosts": sorted({host for host in (_host(website),) if host}),
        }
    return by_id


def _latest_linkedin_statuses(
    connection: sqlite3.Connection, source_company_ids: Iterable[str] | None = None
) -> dict[str, str]:
    ids = sorted({str(value) for value in (source_company_ids or ()) if str(value).strip()})
    filter_sql = ""
    params: tuple[object, ...] = ()
    if ids:
        placeholders = ",".join("?" for _ in ids)
        filter_sql = f" AND latest.linkedin_company_id IN ({placeholders})"
        params = tuple(ids)
    rows = connection.execute(
        f"""
        SELECT linkedin_company_id, status
        FROM company_scans latest
        WHERE started_at = (
            SELECT MAX(previous.started_at)
            FROM company_scans previous
            WHERE previous.linkedin_company_id = latest.linkedin_company_id
        ){filter_sql}
        """,
        params,
    ).fetchall()
    return {_text(row["linkedin_company_id"]): _text(row["status"]) for row in rows}


def _latest_employer_statuses(
    connection: sqlite3.Connection, company_ids: Iterable[str] | None = None
) -> dict[str, tuple[str, str]]:
    ids = sorted({str(value) for value in (company_ids or ()) if str(value).strip()})
    if ids:
        placeholders = ",".join("?" for _ in ids)
        rows = connection.execute(
            f"""SELECT companies.company_key, companies.status, companies.payload_json,
                       coverage_receipts.receipt_json
                FROM companies LEFT JOIN coverage_receipts
                  ON coverage_receipts.company_key=companies.company_key
                WHERE companies.company_key IN ({placeholders})""",
            tuple(ids),
        ).fetchall()
    else:
        rows = connection.execute(
            """SELECT companies.company_key, companies.status, companies.payload_json,
                      coverage_receipts.receipt_json
               FROM companies LEFT JOIN coverage_receipts
                 ON coverage_receipts.company_key=companies.company_key"""
        ).fetchall()
    result: dict[str, tuple[str, str]] = {}
    for row in rows:
        payload = _decode(row["payload_json"], {})
        payload = payload if isinstance(payload, Mapping) else {}
        receipt = _decode(row["receipt_json"], {})
        classification = (
            "confirmed_complete"
            if isinstance(receipt, Mapping)
            and _text(receipt.get("generation_id"))
            and _text(receipt.get("generation_id")) == _text(payload.get("generation_id"))
            and _text(receipt.get("terminal_classification")) == "confirmed_complete"
            else "partial"
        )
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


def _target(
    company: Mapping[str, object],
    source: str,
    *,
    policy_version: str = "publication_policy_v1",
) -> dict[str, object]:
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
        "policy_version": policy_version,
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
    batches = list(iter_observation_batches(items, max_batch_size=20))
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


def _terminal_cycle_task_statuses(
    store: SqliteAcquisitionStore,
    cycle_id: str,
) -> dict[str, str]:
    """Return targets already durably delivered by an earlier cycle attempt."""

    with store._connect() as connection:
        rows = connection.execute(
            """
            SELECT target_id, status
            FROM acquisition_tasks
            WHERE cycle_id = ? AND status IN ('completed', 'partial')
            """,
            (cycle_id,),
        ).fetchall()
    return {
        _text(row["target_id"]): _text(row["status"])
        for row in rows
        if _text(row["target_id"])
    }


def _source_state_target_ids(store: SqliteAcquisitionStore) -> set[str]:
    with store._connect() as connection:
        rows = connection.execute("SELECT DISTINCT target_id FROM job_source_states").fetchall()
    return {_text(row["target_id"]) for row in rows if _text(row["target_id"])}


def _bulk_complete_empty_tasks(
    store: SqliteAcquisitionStore,
    tasks: Iterable[tuple[str, bool, bool, str]],
) -> None:
    """Complete safe no-op tasks with one bounded remote batch."""

    now = datetime.now(timezone.utc).isoformat()
    parameters = [
        (
            status,
            now,
            int(valid_snapshot),
            int(credible_evidence),
            json.dumps({"complete_snapshot": True, "closure_safe": credible_evidence}, separators=(",", ":")),
            now,
            task_id,
        )
        for task_id, valid_snapshot, credible_evidence, status in tasks
        if task_id
    ]
    if not parameters:
        return

    def write(connection) -> None:
        connection.executemany(
            """
            UPDATE acquisition_tasks
            SET status=?, completed_at=?, complete_snapshot=1,
                valid_snapshot=?, credible_evidence=?,
                requests_avoided=0, credits_avoided=0,
                jobs_observed=0, jobs_new=0, jobs_updated=0,
                jobs_unchanged=0, jobs_closed=0, jobs_rejected=0,
                jobs_duplicates=0, reconciliation_json='{}',
                quality_warnings_json='[]', collection_metadata_json=?,
                error_code='', error_message='', last_error_code='',
                last_error_message='', lease_owner='', lease_token='',
                lease_expires_at='', updated_at=?
            WHERE task_id=?
            """,
            parameters,
        )

    store._run_transaction(write)


def _delivery_transaction_batches(
    items: Iterable[tuple[str, str]],
    *,
    source_rows: Callable[[str, str], int],
    max_companies: int,
    max_rows: int,
) -> Iterable[list[tuple[str, str]]]:
    """Pack small companies into bounded shared database transactions.

    A company larger than ``max_rows`` remains a one-company batch. Its
    observation chunks are deliberately committed independently by
    ``_deliver_group`` so a large source snapshot cannot create an oversized
    libSQL transaction.
    """

    batch: list[tuple[str, str]] = []
    batch_rows = 0
    oversized: list[tuple[str, str]] = []
    for item in items:
        row_count = max(0, source_rows(*item))
        if row_count > max_rows:
            oversized.append(item)
            continue
        if batch and (
            len(batch) >= max_companies
            or batch_rows + row_count > max_rows
        ):
            yield batch
            batch = []
            batch_rows = 0
        batch.append(item)
        batch_rows += row_count
    if batch:
        yield batch
    for item in oversized:
        yield [item]


def _publisher_transaction_limits() -> tuple[int, int]:
    """Return bounds for one set-based projection transaction."""

    try:
        companies = int(os.getenv("RUNR_PUBLISHER_TRANSACTION_COMPANIES", "50"))
    except ValueError:
        companies = 50
    try:
        rows = int(os.getenv("RUNR_PUBLISHER_TRANSACTION_ROWS", "100"))
    except ValueError:
        rows = 100
    return max(1, min(50, companies)), max(1, min(100, rows))


def _publisher_initializes_database() -> bool:
    return os.getenv("RUNR_PUBLISHER_INITIALIZE_DATABASE", "1").strip().casefold() not in {
        "0", "false", "no", "off",
    }


def _publisher_cycle_key(calculated_key: str) -> str:
    """Allow an operator to finish one explicitly identified durable cycle."""

    override = os.getenv("RUNR_PUBLISHER_RESUME_CYCLE_KEY", "").strip()
    if not override:
        return calculated_key
    if not override.startswith("producer:") or len(override) > 128:
        raise ValueError("RUNR_PUBLISHER_RESUME_CYCLE_KEY must be a bounded producer cycle key")
    return override


def _split_large_bulk_snapshot(
    snapshot: Mapping[str, object],
    *,
    max_rows: int,
) -> list[dict[str, object]]:
    """Split a large source snapshot without granting early closure authority."""

    jobs = [dict(job) for job in snapshot.get("jobs") or ()]
    if not jobs:
        return [dict(snapshot)]
    external_ids = [str(value) for value in snapshot.get("snapshot_external_ids") or ()]
    chunks: list[dict[str, object]] = []
    for offset in range(0, len(jobs), max(1, max_rows)):
        chunk_jobs = jobs[offset : offset + max(1, max_rows)]
        final = offset + len(chunk_jobs) >= len(jobs)
        chunk_ids = [
            str(job.get("job_id") or job.get("external_job_id") or job.get("url") or "")
            for job in chunk_jobs
        ]
        chunks.append(
            {
                **dict(snapshot),
                "jobs": chunk_jobs,
                "complete_snapshot": bool(snapshot.get("complete_snapshot")) if final else False,
                "closure_safe": bool(snapshot.get("closure_safe")) if final else False,
                "snapshot_external_ids": external_ids if final else [value for value in chunk_ids if value],
            }
        )
    return chunks


def _run_delivery_legacy(
    *,
    manifest_path: Path,
    linkedin_state: Path,
    employer_state: Path,
    data_dir: Path,
    source_version: str,
    pilot_only: bool = False,
    company_ids: Iterable[str] | None = None,
    skip_status_only: bool = False,
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

    store = SqliteAcquisitionStore(
        data_dir / "backend.sqlite3",
        initialize=_publisher_initializes_database(),
    )
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
    cycle_key = _publisher_cycle_key(
        "producer:" + hashlib.sha256(marker.encode("utf-8")).hexdigest()[:24]
    )
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
                        not skip_status_only
                        and (
                            (
                                source == SOURCE_LINKEDIN
                                and company_id in linkedin_statuses_by_canonical
                            )
                            or (
                                source == SOURCE_EMPLOYER
                                and company_id in employer_statuses
                            )
                        )
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


def run_delivery(
    *,
    manifest_path: Path,
    linkedin_state: Path,
    employer_state: Path,
    data_dir: Path,
    source_version: str,
    pilot_only: bool = False,
    company_ids: Iterable[str] | None = None,
    skip_status_only: bool = False,
    identity_crosswalk: Mapping[str, str] | None = None,
    identity_crosswalk_document: Mapping[str, object] | None = None,
    controls: BackfillControls | None = None,
    publication_policy: str | None = None,
    rollback_policy: str | None = None,
) -> dict[str, object]:
    """Incrementally publish source changes without replaying whole catalogs."""

    controls = controls or _default_backfill_controls()
    started_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    started_monotonic = monotonic()
    policy_version = resolve_runtime_publication_policy(
        publication_policy,
        rollback_to=rollback_policy,
    )
    manifest = load_manifest(manifest_path)
    crosswalk = dict(identity_crosswalk or {})
    verified_companies, company_registry_sha256 = _verified_company_registry(manifest_path)
    linkedin_companies = _manifest_companies(manifest, SOURCE_LINKEDIN, pilot_only=pilot_only, crosswalk=crosswalk)
    employer_companies = _manifest_companies(manifest, SOURCE_EMPLOYER, pilot_only=pilot_only, crosswalk=crosswalk)
    requested = {value.strip() for value in (company_ids or ()) if value.strip()}
    if requested:
        linkedin_companies = {key: value for key, value in linkedin_companies.items() if key in requested}
        employer_companies = {key: value for key, value in employer_companies.items() if key in requested}

    _progress("initializing_database")
    store: SqliteAcquisitionStore | None = None
    if not controls.dry_run:
        store = SqliteAcquisitionStore(
            data_dir / "backend.sqlite3",
            initialize=_publisher_initializes_database(),
        )
        _ensure_publisher_checkpoint_table(store)
    crosswalk_result: dict[str, object] = {}
    if identity_crosswalk_document and store is not None:
        crosswalk_report = identity_crosswalk_document.get("report")
        crosswalk_report = crosswalk_report if isinstance(crosswalk_report, Mapping) else {}
        _progress("identity_reconciliation", identities=len(crosswalk),
                  companies=len(crosswalk_report.get("canonical_rows") or []))
        if _crosswalk_already_applied(store, mapping=crosswalk, document=identity_crosswalk_document):
            crosswalk_result = {"status": "already_applied", "registry_sha256": _text(identity_crosswalk_document.get("registry_sha256"))}
        else:
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

    _progress("source_loading")
    linkedin_org_to_canonical = {
        _text(source_company_id): company_id
        for company_id, company in linkedin_companies.items()
        for source_company_id in (company.get("linkedin_company_ids") or ())
        if _text(source_company_id)
    }
    empty_checkpoint = {
        "source_rowid": 0,
        "source_watermark": "",
        "bootstrap_complete": False,
        "last_cycle_id": "",
        "last_publication_id": "",
    }
    linkedin_checkpoint = store.publisher_checkpoint(SOURCE_LINKEDIN) if store is not None else dict(empty_checkpoint)
    employer_checkpoint = store.publisher_checkpoint(SOURCE_EMPLOYER) if store is not None else dict(empty_checkpoint)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    batch_size = controls.batch_size
    telemetry = _publisher_telemetry(
        {SOURCE_LINKEDIN: linkedin_checkpoint, SOURCE_EMPLOYER: employer_checkpoint}, now
    )
    li_connection = _read_only_connection(linkedin_state)
    employer_connection = _read_only_connection(employer_state)
    try:
        linkedin_groups, linkedin_changed_ids, next_linkedin_checkpoint, linkedin_changed = _load_incremental_source(
            li_connection,
            source=SOURCE_LINKEDIN,
            checkpoint=linkedin_checkpoint,
            canonical_by_source_company=linkedin_org_to_canonical,
            selected_ids=set(linkedin_companies),
            crosswalk=crosswalk,
            batch_size=batch_size,
            now=now,
        )
        employer_groups, employer_changed_ids, next_employer_checkpoint, employer_changed = _load_incremental_source(
            employer_connection,
            source=SOURCE_EMPLOYER,
            checkpoint=employer_checkpoint,
            canonical_by_source_company={},
            selected_ids=set(employer_companies),
            crosswalk=crosswalk,
            batch_size=batch_size,
            now=now,
        )
        linkedin_groups = _enrich_source_groups(
            linkedin_groups,
            verified_companies=verified_companies,
            registry_sha256=company_registry_sha256,
        )
        employer_groups = _enrich_source_groups(
            employer_groups,
            verified_companies=verified_companies,
            registry_sha256=company_registry_sha256,
        )
        li_source_ids = {
            _text(item.get("linkedin_company_id"))
            for rows in linkedin_groups.values()
            for item in rows
            if _text(item.get("linkedin_company_id"))
        }
        li_source_ids.update(
            source_id for source_id, canonical_id in linkedin_org_to_canonical.items()
            if canonical_id in linkedin_changed_ids
        )
        li_statuses = _latest_linkedin_statuses(li_connection, li_source_ids)
        employer_statuses = _latest_employer_statuses(employer_connection, employer_changed_ids)
        linkedin_marker = _linkedin_run_marker(li_connection)
        employer_marker = _employer_run_marker(employer_connection)
    finally:
        li_connection.close()
        employer_connection.close()

    source_metrics: dict[str, dict[str, object]] = {
        SOURCE_LINKEDIN: {
            "companies_changed": len(linkedin_changed_ids),
            "groups_with_jobs": len(linkedin_groups),
            "source_marker": linkedin_marker,
            "bootstrap_complete": bool(next_linkedin_checkpoint.get("bootstrap_complete")),
            "verified_company_registry_sha256": company_registry_sha256,
        },
        SOURCE_EMPLOYER: {
            "companies_changed": len(employer_changed_ids),
            "groups_with_jobs": len(employer_groups),
            "source_marker": employer_marker,
            "bootstrap_complete": bool(next_employer_checkpoint.get("bootstrap_complete")),
            "verified_company_registry_sha256": company_registry_sha256,
        },
    }
    source_specs = (
        (SOURCE_LINKEDIN, linkedin_companies, linkedin_groups),
        (SOURCE_EMPLOYER, employer_companies, employer_groups),
    )
    if controls.dry_run:
        eligibility = _preview_eligibility(
            source_specs,
            cycle_id="dry-run",
            max_companies=controls.max_companies,
        )
        return _with_receipt(
            {
                "status": "dry_run",
                "dry_run": True,
                "manifest_id": _text(manifest.get("manifest_id")),
                "manifest_hash": _text(manifest.get("manifest_hash")),
                "source_version": source_version,
                "sources": source_metrics,
                "identity_crosswalk": {},
                "telemetry": telemetry,
                "eligibility": eligibility,
            },
            controls,
            started_at=started_at,
            started_monotonic=started_monotonic,
            eligibility=eligibility,
        )
    if not linkedin_changed and not employer_changed:
        return _with_receipt(
            {
                "status": "no_changes",
                "cycle_id": _text(linkedin_checkpoint.get("last_cycle_id") or employer_checkpoint.get("last_cycle_id")),
                "publication_id": _text(linkedin_checkpoint.get("last_publication_id") or employer_checkpoint.get("last_publication_id")),
                "manifest_id": _text(manifest.get("manifest_id")),
                "manifest_hash": _text(manifest.get("manifest_hash")),
                "source_version": source_version,
                "policy_version": policy_version,
                "sources": source_metrics,
                "identity_crosswalk": crosswalk_result,
                "telemetry": telemetry,
            },
            controls,
            started_at=started_at,
            started_monotonic=started_monotonic,
        )

    changed_by_source = {
        SOURCE_LINKEDIN: linkedin_changed_ids,
        SOURCE_EMPLOYER: employer_changed_ids,
    }
    deferred_companies = False
    if controls.max_companies is not None:
        remaining = controls.max_companies
        bounded_changed_by_source: dict[str, set[str]] = {}
        for source, company_ids_for_source in changed_by_source.items():
            selected = set(sorted(company_ids_for_source)[:remaining])
            bounded_changed_by_source[source] = selected
            deferred_companies = deferred_companies or len(selected) < len(company_ids_for_source)
            remaining -= len(selected)
        changed_by_source = bounded_changed_by_source
    companies_by_source = {
        SOURCE_LINKEDIN: linkedin_companies,
        SOURCE_EMPLOYER: employer_companies,
    }
    targets = [
        _target(
            companies_by_source[source][company_id],
            source,
            policy_version=policy_version,
        )
        for source, company_ids_for_source in changed_by_source.items()
        for company_id in company_ids_for_source
        if company_id in companies_by_source[source]
    ]
    if not targets:
        # A bounded bootstrap chunk can contain only companies outside the
        # selected cohort. Advance its durable cursors without creating an
        # empty cycle or replacing the public publication head.
        assert store is not None
        previous_cycle_id = _text(linkedin_checkpoint.get("last_cycle_id") or employer_checkpoint.get("last_cycle_id"))
        previous_publication_id = _text(linkedin_checkpoint.get("last_publication_id") or employer_checkpoint.get("last_publication_id"))
        store.save_publisher_checkpoint(next_linkedin_checkpoint, cycle_id=previous_cycle_id, publication_id=previous_publication_id)
        store.save_publisher_checkpoint(next_employer_checkpoint, cycle_id=previous_cycle_id, publication_id=previous_publication_id)
        return _with_receipt(
            {
                "status": "no_changes",
                "checkpoint_advanced": True,
                "manifest_id": _text(manifest.get("manifest_id")),
                "manifest_hash": _text(manifest.get("manifest_hash")),
                "source_version": source_version,
                "policy_version": policy_version,
                "sources": source_metrics,
                "identity_crosswalk": crosswalk_result,
                "telemetry": telemetry,
            },
            controls,
            started_at=started_at,
            started_monotonic=started_monotonic,
        )
    assert store is not None
    _progress("targets_registration", targets=len(targets))
    existing_target_ids = store.list_target_ids()
    store.ensure_targets(
        target for target in targets if _text(target.get("target_id")) not in existing_target_ids
    )
    marker = "|".join(
        [
            _text(manifest.get("manifest_hash")),
            linkedin_marker,
            employer_marker,
            str(linkedin_checkpoint.get("source_rowid") or 0),
            str(employer_checkpoint.get("source_rowid") or 0),
            _text(linkedin_checkpoint.get("source_watermark")),
            _text(employer_checkpoint.get("source_watermark")),
            source_version,
            policy_version,
        ]
    )
    cycle_key = _publisher_cycle_key(
        "producer:" + hashlib.sha256(marker.encode("utf-8")).hexdigest()[:24]
    )
    _progress("cycle_claim")
    cycle = store.claim_due_cycle(
        window_key=cycle_key,
        lease_owner=f"producer_bridge:{os.getpid()}",
        scheduled_at=now,
        force=True,
        manifest_version=_text(manifest.get("manifest_hash")),
        scope_key="producer_state",
    )
    if cycle is None:
        return _with_receipt(
            {"status": "already_running", "cycle_key": cycle_key, "telemetry": telemetry},
            controls,
            started_at=started_at,
            started_monotonic=started_monotonic,
        )
    cycle_id = _text(cycle.get("cycle_id"))
    _progress("task_registration", targets=len(targets))
    store.ensure_cycle_tasks(cycle_id, targets)
    cycle_task_ids = store.list_cycle_task_ids(cycle_id)
    metrics: dict[str, object] = {
        "status": "running",
        "cycle_id": cycle_id,
        "cycle_key": cycle_key,
        "manifest_id": _text(manifest.get("manifest_id")),
        "manifest_hash": _text(manifest.get("manifest_hash")),
        "source_version": source_version,
        "policy_version": policy_version,
        "sources": source_metrics,
        "unresolved_observations": 0,
        "identity_crosswalk": crosswalk_result,
        "source_row_batch_size": batch_size,
        "telemetry": telemetry,
    }
    terminal_task_statuses = _terminal_cycle_task_statuses(store, cycle_id)
    current_target_ids = {_text(target.get("target_id")) for target in targets}
    resumed_target_ids = current_target_ids.intersection(terminal_task_statuses)
    partial = any(terminal_task_statuses[target_id] == "partial" for target_id in resumed_target_ids)
    valid_target_ids: list[str] = sorted(resumed_target_ids)
    failures = 0
    companies_attempted = 0
    stop_reason = ""
    stop_requested = False
    next_allowed_delivery = 0.0

    def deliver_company(
        source: str,
        company_id: str,
        delivery_store: SqliteAcquisitionStore = store,
    ) -> dict[str, object]:
        company = companies_by_source[source][company_id]
        target_id = _text(_target(company, source, policy_version=policy_version)["target_id"])
        task_id = _text(cycle_task_ids.get(target_id)) or f"producer_task:{target_id}"
        raw_rows = (linkedin_groups if source == SOURCE_LINKEDIN else employer_groups).get(company_id, [])
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
            status_values.update(
                _text(li_statuses.get(source_id))
                for source_id, canonical_id in linkedin_org_to_canonical.items()
                if canonical_id == company_id and li_statuses.get(source_id)
            )
            closure_safe = bool(next_linkedin_checkpoint.get("bootstrap_complete")) and bool(status_values) and status_values.issubset(COMPLETE_LINKEDIN_SCAN_STATUSES)
            valid_snapshot = True
        else:
            observations = [adapt_employer_job(row, cycle_id=cycle_id) for row in raw_rows]
            status, classification = employer_statuses.get(company_id, ("", ""))
            closure_safe = classification == "confirmed_complete"
            valid_snapshot = status.casefold() not in FAILED_EMPLOYER_STATUSES
        deliverable = [item for item in observations if item.canonical_company_id not in {"", UNKNOWN, "//"}]
        if not deliverable and not closure_safe and valid_snapshot:
            # An incomplete empty snapshot cannot add observations or authorize
            # absence. Persist the task evidence without a no-op ingest round trip.
            result = {
                "observed": 0,
                "new": 0,
                "updated": 0,
                "unchanged": 0,
                "closed": 0,
                "rejected": 0,
                "duplicates": 0,
            }
        else:
            result = _deliver_group(
                delivery_store,
                cycle_id=cycle_id,
                task_id=task_id,
                target_id=target_id,
                observations=deliverable,
                closure_safe=closure_safe,
                valid_snapshot=valid_snapshot,
            )
        delivery_store.complete_task(
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
                    "source_marker": _text(source_metrics[source].get("source_marker")),
                    "unresolved_observations": len(observations) - len(deliverable),
                },
            },
        )
        return {
            "source": source,
            "target_id": target_id,
            "jobs_delivered": len(deliverable),
            "unresolved_observations": len(observations) - len(deliverable),
            "closure_safe": closure_safe,
            "failed": not valid_snapshot,
        }

    def prepare_bulk_snapshot(source: str, company_id: str) -> tuple[dict[str, object], dict[str, object]]:
        """Adapt one ordinary company without touching the remote catalog."""

        company = companies_by_source[source][company_id]
        target_id = _text(_target(company, source, policy_version=policy_version)["target_id"])
        task_id = _text(cycle_task_ids.get(target_id)) or f"producer_task:{target_id}"
        raw_rows = (linkedin_groups if source == SOURCE_LINKEDIN else employer_groups).get(company_id, [])
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
            status_values.update(
                _text(li_statuses.get(source_id))
                for source_id, canonical_id in linkedin_org_to_canonical.items()
                if canonical_id == company_id and li_statuses.get(source_id)
            )
            closure_safe = bool(next_linkedin_checkpoint.get("bootstrap_complete")) and bool(status_values) and status_values.issubset(COMPLETE_LINKEDIN_SCAN_STATUSES)
            valid_snapshot = True
        else:
            observations = [adapt_employer_job(row, cycle_id=cycle_id) for row in raw_rows]
            status, classification = employer_statuses.get(company_id, ("", ""))
            closure_safe = classification == "confirmed_complete"
            valid_snapshot = status.casefold() not in FAILED_EMPLOYER_STATUSES
        deliverable = [item for item in observations if item.canonical_company_id not in {"", UNKNOWN, "//"}]
        observed_at = next(
            (item.observed_at for item in deliverable if item.observed_at != UNKNOWN),
            "",
        )
        snapshot = {
            "cycle_id": cycle_id,
            "task_id": task_id,
            "target_id": target_id,
            "source": source,
            "jobs": [_observation_to_ingest_job(item) for item in deliverable],
            "complete_snapshot": True,
            "valid_snapshot": valid_snapshot,
            "closure_safe": closure_safe,
            "observed_at": observed_at,
            "snapshot_external_ids": [
                item.source_job_id for item in deliverable if item.source_job_id not in {"", UNKNOWN}
            ],
            "unresolved_observations": len(observations) - len(deliverable),
        }
        delivered = {
            "source": source,
            "target_id": target_id,
            "jobs_delivered": len(deliverable),
            "unresolved_observations": len(observations) - len(deliverable),
            "closure_safe": closure_safe,
            "failed": not valid_snapshot,
        }
        return snapshot, delivered

    def deliver_large_company_bulk(source: str, company_id: str, *, max_rows: int) -> dict[str, object]:
        """Commit one large company as closure-safe bounded set-based chunks."""

        snapshot, delivered = prepare_bulk_snapshot(source, company_id)
        totals = {
            key: 0
            for key in (
                "observed", "new", "updated", "unchanged", "stale_ignored",
                "closed", "rejected", "duplicates", "applicant_snapshots_blocked",
            )
        }
        final_result: dict[str, object] = {}
        for chunk in _split_large_bulk_snapshot(snapshot, max_rows=max_rows):
            projected = store.ingest_snapshots_bulk([chunk])
            final_result = dict(projected["targets"][_text(delivered["target_id"])])
            for key in totals:
                totals[key] += int(final_result.get(key) or 0)
        task_id = _text(snapshot.get("task_id"))
        store.complete_task(
            task_id,
            status="completed" if bool(delivered["closure_safe"]) else "partial",
            result={
                **final_result,
                **totals,
                "complete_snapshot": True,
                "valid_snapshot": not bool(delivered["failed"]),
                "closure_safe": bool(delivered["closure_safe"]),
                "credible_evidence": bool(delivered["closure_safe"]),
                "collection_metadata": {
                    "producer_bridge": True,
                    "source": source,
                    "source_marker": _text(source_metrics[source].get("source_marker")),
                    "unresolved_observations": int(delivered["unresolved_observations"]),
                    "large_company_bulk_chunks": len(
                        _split_large_bulk_snapshot(snapshot, max_rows=max_rows)
                    ),
                },
            },
        )
        return {**delivered, "result": {**final_result, **totals}}

    try:
        delivered_companies = len(resumed_target_ids)
        _progress("delivery", companies_completed=delivered_companies, targets=len(targets))
        delivery_items: list[tuple[str, str]] = []
        bulk_empty_items: list[tuple[str, str, str, bool, bool, str]] = []
        source_state_target_ids = _source_state_target_ids(store)
        for source, changed_ids in changed_by_source.items():
            source_metrics[source]["companies_pending_source_state"] = 0
            source_metrics[source]["jobs_delivered"] = 0
            source_metrics[source]["partial_companies"] = 0
            source_metrics[source]["failed_companies"] = 0
            for company_id in sorted(changed_ids):
                if skip_status_only and not (linkedin_groups if source == SOURCE_LINKEDIN else employer_groups).get(company_id):
                    continue
                target_id = _text(_target(companies_by_source[source][company_id], source, policy_version=policy_version)["target_id"])
                if target_id in resumed_target_ids:
                    continue
                raw_rows = (linkedin_groups if source == SOURCE_LINKEDIN else employer_groups).get(company_id, [])
                if not raw_rows:
                    if source == SOURCE_LINKEDIN:
                        status_values = {
                            _text(li_statuses.get(source_id))
                            for source_id, canonical_id in linkedin_org_to_canonical.items()
                            if canonical_id == company_id and li_statuses.get(source_id)
                        }
                        closure_safe = bool(next_linkedin_checkpoint.get("bootstrap_complete")) and bool(status_values) and status_values.issubset(COMPLETE_LINKEDIN_SCAN_STATUSES)
                        valid_snapshot = True
                    else:
                        status, classification = employer_statuses.get(company_id, ("", ""))
                        closure_safe = classification == "confirmed_complete"
                        valid_snapshot = status.casefold() not in FAILED_EMPLOYER_STATUSES
                    if (not closure_safe and valid_snapshot) or target_id not in source_state_target_ids:
                        task_id = _text(cycle_task_ids.get(target_id)) or f"producer_task:{target_id}"
                        bulk_empty_items.append((
                            source,
                            target_id,
                            task_id,
                            valid_snapshot,
                            closure_safe,
                            "completed" if closure_safe else "partial",
                        ))
                        continue
                delivery_items.append((source, company_id))
        if controls.max_companies is not None and len(delivery_items) > controls.max_companies:
            delivery_items = delivery_items[: controls.max_companies]
            stop_reason = "max_companies"
            stop_requested = True

        try:
            delivery_batch_size = int(os.getenv("RUNR_PUBLISHER_DELIVERY_BATCH_SIZE", "1000"))
        except ValueError:
            delivery_batch_size = 1000
        try:
            delivery_workers = int(os.getenv("RUNR_PUBLISHER_DELIVERY_WORKERS", "1"))
        except ValueError:
            delivery_workers = 1
        delivery_batch_size = max(1, min(1000, delivery_batch_size))
        delivery_workers = max(1, min(8, delivery_workers))
        transaction_companies, transaction_rows = _publisher_transaction_limits()
        worker_state = local()

        def source_row_count(source: str, company_id: str) -> int:
            return len((linkedin_groups if source == SOURCE_LINKEDIN else employer_groups).get(company_id, []))

        def deliver_with_worker_store(source: str, company_id: str) -> dict[str, object]:
            worker_store = getattr(worker_state, "store", None)
            if worker_store is None:
                worker_store = SqliteAcquisitionStore(data_dir / "backend.sqlite3", initialize=False)
                worker_state.store = worker_store
            raw_rows = (linkedin_groups if source == SOURCE_LINKEDIN else employer_groups).get(company_id, [])
            _progress(
                "delivery_company",
                companies_completed=delivered_companies,
                targets=len(targets),
                source=source,
                company_id=company_id,
                source_rows=len(raw_rows),
            )
            return deliver_company(source, company_id, worker_store)

        def record_delivery(source: str, delivered: Mapping[str, object]) -> None:
            nonlocal delivered_companies, partial
            delivered_companies += 1
            valid_target_ids.append(_text(delivered.get("target_id")))
            partial = partial or not bool(delivered["closure_safe"])
            source_metrics[source]["jobs_delivered"] = int(source_metrics[source]["jobs_delivered"]) + int(delivered["jobs_delivered"])
            source_metrics[source]["unresolved_observations"] = int(source_metrics[source].get("unresolved_observations") or 0) + int(delivered["unresolved_observations"])
            if bool(delivered["failed"]):
                source_metrics[source]["failed_companies"] = int(source_metrics[source]["failed_companies"]) + 1
            if not bool(delivered["closure_safe"]):
                source_metrics[source]["partial_companies"] = int(source_metrics[source]["partial_companies"]) + 1

        for bulk_start in range(0, len(bulk_empty_items), 250):
            bulk = bulk_empty_items[bulk_start : bulk_start + 250]
            _bulk_complete_empty_tasks(
                store,
                ((task_id, valid_snapshot, closure_safe, status) for _source, _target_id, task_id, valid_snapshot, closure_safe, status in bulk),
            )
            delivered_companies += len(bulk)
            companies_attempted += len(bulk)
            for source, target_id, _task_id, valid_snapshot, closure_safe, _status in bulk:
                valid_target_ids.append(target_id)
                if not closure_safe:
                    partial = True
                    source_metrics[source]["partial_companies"] = int(source_metrics[source]["partial_companies"]) + 1
                if not valid_snapshot:
                    source_metrics[source]["failed_companies"] = int(source_metrics[source]["failed_companies"]) + 1
            _progress("delivery", companies_completed=delivered_companies, targets=len(targets))

        if delivery_workers == 1 and not controls.rate_per_second:
            transaction_batches = _delivery_transaction_batches(
                delivery_items,
                source_rows=source_row_count,
                max_companies=transaction_companies,
                max_rows=transaction_rows,
            )
            for transaction_batch in transaction_batches:
                if controls.timeout_seconds is not None and monotonic() - started_monotonic >= controls.timeout_seconds:
                    stop_reason = "timeout"
                    stop_requested = True
                    break
                companies_attempted += len(transaction_batch)
                committed: list[tuple[str, Mapping[str, object]]] = []
                try:
                    # Large companies retain the existing <=20-observation
                    # commits. Small companies share one bounded transaction,
                    # eliminating one remote commit per company.
                    use_shared_transaction = not (
                        len(transaction_batch) == 1
                        and source_row_count(*transaction_batch[0]) > transaction_rows
                    )
                    if use_shared_transaction:
                        prepared = [
                            (source, *prepare_bulk_snapshot(source, company_id))
                            for source, company_id in transaction_batch
                        ]
                        bulk_result = store.ingest_snapshots_bulk(
                            [snapshot for _source, snapshot, _delivered in prepared]
                        )
                        for source, _snapshot, delivered in prepared:
                            target_result = bulk_result["targets"][_text(delivered["target_id"])]
                            delivered = {**delivered, "result": target_result}
                            committed.append((source, delivered))
                    else:
                        source, company_id = transaction_batch[0]
                        committed.append((source, deliver_large_company_bulk(
                            source,
                            company_id,
                            max_rows=min(20, transaction_rows),
                        )))
                    for source, delivered in committed:
                        record_delivery(source, delivered)
                    _progress("delivery", companies_completed=delivered_companies, targets=len(targets))
                except Exception as exc:
                    failures += 1
                    partial = True
                    for source, _company_id in transaction_batch:
                        source_metrics[source]["failed_companies"] = int(source_metrics[source]["failed_companies"]) + 1
                        source_metrics[source]["last_error"] = type(exc).__name__.casefold()
                    stop_reason = "max_failures"
                    stop_requested = True
                    break

        for batch_start in range(0, len(delivery_items), delivery_batch_size):
            if delivery_workers == 1 and not controls.rate_per_second:
                break
            if controls.timeout_seconds is not None and monotonic() - started_monotonic >= controls.timeout_seconds:
                stop_reason = "timeout"
                stop_requested = True
                break
            batch = delivery_items[batch_start : batch_start + delivery_batch_size]
            companies_attempted += len(batch)
            effective_workers = 1 if controls.rate_per_second else delivery_workers
            with ThreadPoolExecutor(max_workers=min(effective_workers, len(batch))) as executor:
                future_sources = {
                    executor.submit(deliver_with_worker_store, source, company_id): source
                    for source, company_id in batch
                }
                for future in as_completed(future_sources):
                    source = future_sources[future]
                    try:
                        record_delivery(source, future.result())
                        _progress("delivery", companies_completed=delivered_companies, targets=len(targets))
                    except Exception as exc:
                        failures += 1
                        partial = True
                        source_metrics[source]["failed_companies"] = int(source_metrics[source]["failed_companies"]) + 1
                        source_metrics[source]["last_error"] = type(exc).__name__.casefold()
                        stop_reason = "max_failures"
                        stop_requested = True
                        if controls.max_failures == 0 or failures >= controls.max_failures:
                            break
            if stop_requested:
                break
            if failures and (controls.max_failures == 0 or failures >= controls.max_failures):
                stop_reason = "max_failures"
                stop_requested = True
                break
        if not stop_requested and deferred_companies:
            stop_reason = "max_companies"
            stop_requested = True
        if not stop_requested and failures:
            stop_reason = "failures_observed"
            stop_requested = True
        if stop_requested:
            store.complete_cycle(
                cycle_id,
                status="recovery_required",
                error_code=stop_reason,
                error_message="Backfill stopped before checkpoint advancement; resume is safe after operator review.",
            )
            metrics.update(
                {
                    "status": "stopped",
                    "failures": failures,
                    "stop_reason": stop_reason,
                    "companies_attempted": companies_attempted,
                }
            )
            return _with_receipt(
                metrics,
                controls,
                started_at=started_at,
                started_monotonic=started_monotonic,
                failures=failures,
                stop_reason=stop_reason,
            )
        _progress("publication", companies_completed=delivered_companies)
        publication_id = store.publish_valid_snapshot(
            cycle_id=cycle_id,
            valid_target_ids=valid_target_ids,
            origin="scheduled",
            created_by="producer_bridge",
            scheduled_run_id=cycle_id,
            policy_version=policy_version,
        )
        store.complete_cycle(
            cycle_id,
            status="degraded" if partial else "completed",
            publication_id=publication_id,
            error_code="partial_source_coverage" if partial else "",
            error_message="One or more source companies lacked closure-safe completeness evidence." if partial else "",
        )
        _progress("checkpoints")
        store.save_publisher_checkpoint(next_linkedin_checkpoint, cycle_id=cycle_id, publication_id=publication_id)
        store.save_publisher_checkpoint(next_employer_checkpoint, cycle_id=cycle_id, publication_id=publication_id)
        metrics.update(
            {
                "status": "degraded" if partial else "completed",
                "publication_id": publication_id,
                "report": store.get_cycle_report(cycle_id),
            }
        )
        _progress("completed", companies_completed=delivered_companies)
        return _with_receipt(
            metrics,
            controls,
            started_at=started_at,
            started_monotonic=started_monotonic,
            failures=failures,
        )
    except BaseException as exc:
        _progress("failed")
        store.complete_cycle(
            cycle_id,
            status="recovery_required",
            error_code=type(exc).__name__.casefold(),
            error_message=str(exc)[:500],
        )
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--linkedin-state", type=Path, required=True)
    parser.add_argument("--employer-state", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--source-version", default=os.getenv("RUNR_SOURCE_VERSION", ""))
    parser.add_argument("--company-ids", nargs="*")
    parser.add_argument(
        "--skip-status-only",
        action="store_true",
        help="Recovery mode: deliver only companies with producer job groups; preserve normal empty-snapshot closure by default.",
    )
    parser.add_argument("--pilot-only", action="store_true")
    parser.add_argument("--identity-crosswalk", type=Path, help="optional reviewed company_identity_crosswalk.json")
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--max-companies", type=int)
    parser.add_argument("--rate-per-second", type=float)
    parser.add_argument("--timeout-seconds", type=float)
    parser.add_argument("--max-failures", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--publication-policy-version",
        dest="publication_policy_version",
        help="owner-approved policy version; defaults to the blocking runtime policy",
    )
    parser.add_argument(
        "--rollback-policy-version",
        dest="rollback_policy_version",
        help="explicitly restore a registered prior policy without deleting data",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    defaults = _default_backfill_controls(dry_run=bool(args.dry_run))
    controls = BackfillControls(
        batch_size=args.batch_size if args.batch_size is not None else defaults.batch_size,
        max_companies=args.max_companies,
        rate_per_second=args.rate_per_second if args.rate_per_second is not None else defaults.rate_per_second,
        timeout_seconds=args.timeout_seconds if args.timeout_seconds is not None else defaults.timeout_seconds,
        max_failures=args.max_failures if args.max_failures is not None else defaults.max_failures,
        dry_run=bool(args.dry_run),
    )
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
        skip_status_only=bool(args.skip_status_only),
        identity_crosswalk=identity_crosswalk,
        identity_crosswalk_document=identity_crosswalk_document,
        controls=controls,
        publication_policy=args.publication_policy_version,
        rollback_policy=args.rollback_policy_version,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
