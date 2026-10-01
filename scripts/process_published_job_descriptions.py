"""Build shared Runr descriptions for current published posting versions on the VPS."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import sleep

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.application.vps_job_descriptions import (
    PROMPT_VERSION,
    RateLimitError,
    build_runr_descriptions,
    openrouter_generate,
)
from backend.repositories.sqlite_personalized_jobs import SqlitePersonalizedJobsStore
from backend.repositories.sqlite_migrations import current_migration_head


def next_batch(
    store: SqlitePersonalizedJobsStore, after_id: str, limit: int, *,
    newest: bool = False, excluded_ids: frozenset[str] = frozenset(),
    upgrade_rules: bool = True,
) -> list[dict]:
    cursor_clause = "" if newest else "AND j.canonical_job_id > ?"
    excluded_clause = f"AND j.canonical_job_id NOT IN ({','.join('?' for _ in excluded_ids)})" if excluded_ids else ""
    order_clause = "v.created_at DESC, j.canonical_job_id" if newest else "j.canonical_job_id"
    rule_clause = "OR d.provider = 'runr_rules'" if upgrade_rules else ""
    parameters = (() if newest else (after_id,)) + tuple(sorted(excluded_ids)) + (PROMPT_VERSION, limit)
    with store._connect() as connection:
        rows = connection.execute(
            f"""
            SELECT j.canonical_job_id, j.current_version_id, j.title, j.canonical_url,
                   v.version_number, v.content_hash, v.description,
                   v.payload_json AS version_payload_json, v.location AS version_location,
                   v.apply_url
            FROM acquisition_publication_head h
            JOIN acquisition_publication_jobs pj ON pj.publication_id = h.publication_id
            JOIN canonical_jobs j ON j.canonical_job_id = pj.canonical_job_id
            JOIN job_posting_versions v ON v.version_id = j.current_version_id
            LEFT JOIN job_description_intelligence d ON d.version_id = v.version_id
            WHERE h.head_id = 1 {cursor_clause} {excluded_clause}
              AND TRIM(COALESCE(v.description, '')) != ''
              AND (d.version_id IS NULL OR COALESCE(d.content_hash, '') != v.content_hash
                   OR COALESCE(d.prompt_version, '') != ? {rule_clause})
            ORDER BY {order_clause} LIMIT ?
            """,
            parameters,
        ).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]


def save_batch(store: SqlitePersonalizedJobsStore, results: list[dict], *, preserve_model: bool = False) -> None:
    """Commit a model response in one remote transaction instead of one per job."""
    now = datetime.now(timezone.utc).isoformat()
    parameters = [(
        result["version_id"], result["canonical_job_id"], result["content_hash"],
        json.dumps(result["summary"], ensure_ascii=False),
        json.dumps(result["structured_description"], ensure_ascii=False),
        json.dumps(result["original_posting"], ensure_ascii=False),
        result["provider"], result["model"], result["prompt_version"], now, now, now,
    ) for result in results]
    conflict_guard = "WHERE job_description_intelligence.provider != 'openrouter'" if preserve_model else ""
    with store.transaction_scope() as connection:
        connection.executemany(
            f"""
            INSERT INTO job_description_intelligence (
                version_id, canonical_job_id, content_hash, summary_json,
                structured_json, original_json, provider, model,
                prompt_version, generated_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(version_id) DO UPDATE SET
                canonical_job_id=excluded.canonical_job_id,
                content_hash=excluded.content_hash,
                summary_json=excluded.summary_json,
                structured_json=excluded.structured_json,
                original_json=excluded.original_json,
                provider=excluded.provider,
                model=excluded.model,
                prompt_version=excluded.prompt_version,
                generated_at=excluded.generated_at,
                updated_at=excluded.updated_at
                {conflict_guard}
            """,
            parameters,
        )


def run(store: SqlitePersonalizedJobsStore, *, limit: int, cursor_file: Path) -> dict:
    cursor = ""
    if cursor_file.exists():
        try:
            cursor = str(json.loads(cursor_file.read_text(encoding="utf-8")).get("after_id") or "")
        except (OSError, ValueError, AttributeError):
            cursor = ""
    counts = {"requests": 0, "attempted": 0, "completed": 0, "failed": 0}
    errors: list[str] = []
    rate_limited = False
    excluded_ids: set[str] = set()
    batch_size = 5
    recent_requests = min(2, max(0, limit - 1))
    while counts["requests"] < limit and not rate_limited:
        newest = counts["requests"] < recent_requests
        candidates = next_batch(store, cursor, batch_size, newest=newest, excluded_ids=frozenset(excluded_ids))
        if not candidates and newest:
            recent_requests = counts["requests"]
            continue
        # Keep full postings intact while bounding a multi-job request's size.
        batch = []
        source_chars = 0
        for row in candidates:
            length = len(str(row.get("description") or ""))
            if batch and source_chars + length > 20000:
                break
            batch.append(row)
            source_chars += length
        if not batch:
            cursor = ""
            break
        results = None
        model_error = None
        for attempt in range(3):
            if counts["requests"] >= limit:
                break
            counts["requests"] += 1
            try:
                results = build_runr_descriptions(batch, openrouter_generate)
                break
            except RateLimitError:
                rate_limited = True
                break
            except Exception as exc:
                model_error = exc
                if attempt < 2 and counts["requests"] < limit:
                    sleep(5 * (attempt + 1))
        if rate_limited:
            break
        if results is None:
            errors.append(type(model_error).__name__ if model_error is not None else "request_limit")
            if len(batch) > 1:
                if counts["requests"] >= limit:
                    counts["attempted"] += len(batch)
                    counts["failed"] += len(batch)
                    break
                batch_size = max(1, len(batch) // 2)
                continue
            counts["attempted"] += 1
            counts["failed"] += 1
            excluded_ids.update(str(row["canonical_job_id"]) for row in batch)
            if not newest:
                cursor = str(batch[-1]["canonical_job_id"])
            batch_size = 5
            continue
        counts["attempted"] += len(batch)
        try:
            save_batch(store, results)
        except Exception as exc:
            counts["failed"] += len(batch)
            errors.append(type(exc).__name__)
            break
        counts["completed"] += len(batch)
        print(json.dumps({"requests": counts["requests"], "completed": counts["completed"], "failed": counts["failed"]}), flush=True)
        batch_size = 5
        if not newest:
            cursor = str(batch[-1]["canonical_job_id"])
    cursor_file.parent.mkdir(parents=True, exist_ok=True)
    temp = cursor_file.with_suffix(".tmp")
    temp.write_text(json.dumps({"after_id": cursor}), encoding="utf-8")
    os.replace(temp, cursor_file)
    return {**counts, "cursor_present": bool(cursor), "rate_limited": rate_limited, "error_types": sorted(set(errors))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=os.getenv("RUNR_DATA_DIR", "/var/lib/runr/acquisition-data"))
    parser.add_argument("--limit", type=int, default=45, help="maximum free-tier model requests")
    parser.add_argument("--cursor-file", default="/srv/runr/state/description-cursor.json")
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 1000:
        parser.error("limit must be between 1 and 1000")
    if not os.getenv("OPENROUTER_API_KEY"):
        parser.error("OPENROUTER_API_KEY is required")
    os.environ["RUNR_MIGRATION_HEAD"] = current_migration_head()
    store = SqlitePersonalizedJobsStore(Path(args.data_dir) / "backend.sqlite3", initialize=False)
    result = run(store, limit=args.limit, cursor_file=Path(args.cursor_file))
    print(json.dumps(result, sort_keys=True))
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
