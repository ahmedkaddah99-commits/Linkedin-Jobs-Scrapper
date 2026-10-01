"""Prepare source-faithful descriptions for all published jobs without model calls."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.application.vps_job_descriptions import build_runr_description_rules
from backend.repositories.sqlite_personalized_jobs import SqlitePersonalizedJobsStore
from scripts.process_published_job_descriptions import next_batch, save_batch


def _save_cursor(path: Path, after_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"after_id": after_id}), encoding="utf-8")
    os.replace(temporary, path)


def run_rules_backfill(
    store: SqlitePersonalizedJobsStore, *, limit: int, cursor_file: Path, page_size: int = 100,
) -> dict[str, int]:
    cursor = ""
    if cursor_file.exists():
        try:
            cursor = str(json.loads(cursor_file.read_text(encoding="utf-8")).get("after_id") or "")
        except (OSError, ValueError, AttributeError):
            pass
    written = failed = pages = 0
    wrapped = False
    while written + failed < limit:
        rows = next_batch(
            store, cursor, min(page_size, limit - written - failed),
            upgrade_rules=False,
        )
        if not rows:
            if cursor and not wrapped:
                cursor = ""
                wrapped = True
                _save_cursor(cursor_file, cursor)
                continue
            break
        prepared = []
        for row in rows:
            try:
                prepared.append(build_runr_description_rules(row))
            except (TypeError, ValueError):
                failed += 1
        if prepared:
            save_batch(store, prepared, preserve_model=True)
            written += len(prepared)
        cursor = str(rows[-1]["canonical_job_id"])
        _save_cursor(cursor_file, cursor)
        pages += 1
        print(json.dumps({"pages": pages, "written": written, "failed": failed}), flush=True)
    return {"pages": pages, "written": written, "failed": failed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=os.getenv("RUNR_DATA_DIR", "/var/lib/runr/acquisition-data"))
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--cursor-file", default="/srv/runr/state/description-rules-cursor.json")
    args = parser.parse_args()
    if not 1 <= args.limit <= 100000:
        parser.error("limit must be between 1 and 100000")
    if not 1 <= args.page_size <= 500:
        parser.error("page-size must be between 1 and 500")
    store = SqlitePersonalizedJobsStore(Path(args.data_dir) / "backend.sqlite3", initialize=False)
    result = run_rules_backfill(store, limit=args.limit, cursor_file=Path(args.cursor_file), page_size=args.page_size)
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

