"""Recheck the current publication against employer producer evidence.

This repairs a stale public head even when the full producer delivery times out.
The previous publication stays intact for rollback. No producer rows are deleted.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.acquisition.job_page_evidence import generic_employer_non_job_reason, is_navigation_title
from backend.database.connection import connect_database
from backend.repositories.sqlite_acquisition import (
    SqliteAcquisitionStore, _assert_publication_size_is_safe,
    _insert_publication_jobs_batched, _json, utc_now_iso,
)


def job_identity(url: object, title: object) -> tuple[str, str, str]:
    parts = urlsplit(str(url or ""))
    host = (parts.hostname or "").casefold().removeprefix("www.")
    return host, unquote(parts.path).rstrip("/").casefold(), " ".join(str(title or "").casefold().split())


def load_producer_evidence(state_db: Path) -> dict[tuple[str, str, str], bool]:
    """A failed source observation keeps a disputed job out of the public head."""
    evidence: dict[tuple[str, str, str], bool] = {}
    with sqlite3.connect(f"file:{state_db.as_posix()}?mode=ro", uri=True) as connection:
        for (raw,) in connection.execute("SELECT payload_json FROM jobs"):
            record = json.loads(raw or "{}")
            key = job_identity(record.get("source_job_url"), record.get("job_title"))
            if not key[0] or not key[2]:
                continue
            rejected = bool(generic_employer_non_job_reason(record)) if (
                str(record.get("source_provider") or "").casefold() == "generic_employer_site"
            ) else False
            evidence[key] = evidence.get(key, False) or rejected
    return evidence


def classify_head(
    snapshot: list[dict[str, object]],
    producer_evidence: Mapping[tuple[str, str, str], bool],
    unmatched_rows: Mapping[str, Mapping[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, int]]:
    retained: list[dict[str, object]] = []
    removed: list[dict[str, object]] = []
    counts = {"producer_rejected": 0, "catalog_rejected": 0, "navigation_rejected": 0}
    for job in snapshot:
        key = job_identity(job.get("canonical_url"), job.get("title"))
        reason = ""
        if is_navigation_title(job):
            reason = "navigation_rejected"
        elif key in producer_evidence:
            if producer_evidence[key]:
                reason = "producer_rejected"
        elif key[0] not in {"linkedin.com", "www.linkedin.com"}:
            row = unmatched_rows.get(str(job.get("canonical_job_id") or ""))
            if row:
                record = {**row, "title": job.get("title"), "canonical_url": job.get("canonical_url")}
                if str(record.get("source_provider") or "").casefold() == "generic_employer_site":
                    if generic_employer_non_job_reason(record):
                        reason = "catalog_rejected"
        if reason:
            removed.append(job)
            counts[reason] += 1
        else:
            retained.append(job)
    return retained, removed, counts


def _unmatched_catalog_rows(connection, snapshot, producer_evidence):
    ids = [str(job.get("canonical_job_id") or "") for job in snapshot
           if job_identity(job.get("canonical_url"), job.get("title")) not in producer_evidence
           and job_identity(job.get("canonical_url"), job.get("title"))[0] != "linkedin.com"]
    result = {}
    for offset in range(0, len(ids), 100):
        batch = ids[offset:offset + 100]
        placeholders = ",".join("?" for _ in batch)
        rows = connection.execute(f"""
            SELECT j.canonical_job_id, j.location, v.description, v.apply_url, v.payload_json
            FROM canonical_jobs j
            LEFT JOIN job_posting_versions v ON v.version_id=j.current_version_id
            WHERE j.canonical_job_id IN ({placeholders})
        """, tuple(batch)).fetchall()
        for row in rows:
            payload = json.loads(row["payload_json"] or "{}")
            if not isinstance(payload, dict):
                payload = {}
            payload.update({"location": row["location"], "description": row["description"],
                            "apply_url": row["apply_url"]})
            result[str(row["canonical_job_id"])] = payload
    return result


def _load_env(path: Path) -> None:
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--employer-state", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path(os.getenv("RUNR_DATA_DIR", "/var/lib/runr/acquisition-data")))
    parser.add_argument("--catalog-env", type=Path, action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-head", default="")
    parser.add_argument("--automatic", action="store_true", help="Use the observed head with a compare-and-swap")
    args = parser.parse_args(argv)
    for path in args.catalog_env:
        _load_env(path)
    evidence = load_producer_evidence(args.employer_state)
    db_path = args.data_dir / "backend.sqlite3"
    with connect_database(db_path) as connection:
        head = connection.execute("SELECT publication_id FROM acquisition_publication_head WHERE head_id=1").fetchone()
        old_id = str(head["publication_id"] if head else "")
        publication = connection.execute(
            "SELECT snapshot_json, policy_version FROM acquisition_publications WHERE publication_id=?", (old_id,)
        ).fetchone()
        if publication is None:
            raise RuntimeError("Current publication is unavailable")
        snapshot = json.loads(publication["snapshot_json"] or "[]")
        if not isinstance(snapshot, list):
            raise RuntimeError("Current publication snapshot is invalid")
        unmatched = _unmatched_catalog_rows(connection, snapshot, evidence)
        policy_version = str(publication["policy_version"] or "publication_policy_v1")
    retained, removed, counts = classify_head(snapshot, evidence, unmatched)
    result = {"status": "preview", "head": old_id, "before": len(snapshot), "after": len(retained),
              "removed": len(removed), "reasons": counts,
              "examples": [(j.get("title"), j.get("canonical_url")) for j in removed[:8]]}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if not args.apply or not removed:
        return
    if not args.automatic and args.expected_head != old_id:
        raise RuntimeError("Expected publication head does not match")
    if len(retained) < int(len(snapshot) * 0.5):
        raise RuntimeError("More than half the publication would be removed")
    store = SqliteAcquisitionStore(db_path, initialize=False)
    new_id = f"acq_quality_repair_{uuid4().hex}"
    cycle_id = f"quality_repair_{uuid4().hex}"
    now = utc_now_iso()

    def publish(connection):
        current = connection.execute("SELECT publication_id FROM acquisition_publication_head WHERE head_id=1").fetchone()
        if not current or str(current["publication_id"]) != old_id:
            raise RuntimeError("Publication head changed during repair")
        _assert_publication_size_is_safe(connection, previous_publication_id=old_id, next_count=len(retained))
        preflight = store._build_publication_preflight(
            connection, previous_publication_id=old_id, next_snapshot=retained, policy_version=policy_version,
        )
        connection.execute("""
            INSERT INTO acquisition_publications
            (publication_id, cycle_id, status, snapshot_json, published_at, valid_until,
             previous_publication_id, origin, created_by, scheduled_run_id, preflight_json, policy_version)
            VALUES (?, ?, 'valid', ?, ?, '', ?, 'system', 'employer_job_quality_repair', '', ?, ?)
        """, (new_id, cycle_id, _json(retained), now, old_id, _json(preflight), policy_version))
        _insert_publication_jobs_batched(
            connection, publication_id=new_id,
            canonical_job_ids=(str(job["canonical_job_id"]) for job in retained),
        )
        changed = connection.execute("""
            UPDATE acquisition_publication_head SET publication_id=?, updated_at=?
            WHERE head_id=1 AND publication_id=?
        """, (new_id, now, old_id)).rowcount
        if changed != 1:
            raise RuntimeError("Publication head changed during repair")
        store._record_publication_audit(
            connection, publication_id=new_id, event_type="publication_created",
            actor_user_id="employer_job_quality_repair", previous_publication_id=old_id,
            payload={"removed": len(removed), "reasons": counts}, created_at=now,
        )

    store._run_transaction(publish)
    print(json.dumps({"status": "published", "head": new_id, "jobs": len(retained)}), flush=True)


if __name__ == "__main__":
    main()
