"""Resume a bounded backfill of the published-job FTS index.

Run after migration 065. The search endpoint uses its legacy predicate until
the final batch marks this index ready, so partial results are never served.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.database.connection import connect_database
from backend.domain.models import utc_now_iso


def load_env(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def backfill(db_path: Path, *, batch_size: int = 200) -> tuple[int, int]:
    connection = connect_database(db_path)
    try:
        state = connection.execute(
            "SELECT last_rowid, target_rowid, ready FROM published_job_search_backfill WHERE id = 1"
        ).fetchone()
        if state is None:
            raise RuntimeError("Search index migration 065 has not completed")
        last_rowid = int(state["last_rowid"])
        target_rowid = int(state["target_rowid"])
        if not target_rowid:
            target_rowid = int(connection.execute("SELECT COALESCE(MAX(rowid), 0) AS n FROM canonical_jobs").fetchone()["n"])
            connection.execute(
                "UPDATE published_job_search_backfill SET target_rowid = ?, ready = 0, updated_at = ? WHERE id = 1",
                (target_rowid, utc_now_iso()),
            )
            connection.commit()
        if int(state["ready"]):
            return last_rowid, target_rowid
        while last_rowid < target_rowid:
            next_rowid = min(last_rowid + batch_size, target_rowid)
            # Current rows may already have been indexed by a trigger. Replace
            # that range from the canonical tables in the same transaction.
            connection.execute("DELETE FROM published_job_search WHERE rowid BETWEEN ? AND ?", (last_rowid + 1, next_rowid))
            connection.execute(
                """
                INSERT INTO published_job_search(rowid, title, company, description, payload_json)
                SELECT j.rowid, j.title, c.canonical_name,
                       COALESCE(v.description, ''), COALESCE(v.payload_json, '')
                FROM canonical_jobs j
                JOIN canonical_companies c ON c.company_id = j.company_id
                LEFT JOIN job_posting_versions v ON v.version_id = j.current_version_id
                WHERE j.rowid BETWEEN ? AND ?
                """,
                (last_rowid + 1, next_rowid),
            )
            connection.execute(
                "UPDATE published_job_search_backfill SET last_rowid = ?, updated_at = ? WHERE id = 1",
                (next_rowid, utc_now_iso()),
            )
            connection.commit()
            last_rowid = next_rowid
            print(f"indexed through job row {last_rowid} of {target_rowid}", flush=True)
        connection.execute(
            "UPDATE published_job_search_backfill SET ready = 1, updated_at = ? WHERE id = 1",
            (utc_now_iso(),),
        )
        connection.commit()
        return last_rowid, target_rowid
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path)
    parser.add_argument("--db", type=Path, default=Path("user_data/runr.sqlite3"))
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()
    if args.batch_size < 1 or args.batch_size > 500:
        parser.error("--batch-size must be between 1 and 500")
    if args.env:
        load_env(args.env)
    last_rowid, target_rowid = backfill(args.db, batch_size=args.batch_size)
    print(f"search index ready: {last_rowid}/{target_rowid}")


if __name__ == "__main__":
    main()
