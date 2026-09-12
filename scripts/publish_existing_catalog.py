"""Recheck and publish the active canonical catalog without source replay."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import connect_database
from backend.repositories.sqlite_acquisition import SqliteAcquisitionStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.getenv("RUNR_DATA_DIR", "/var/lib/runr/acquisition-data")),
    )
    parser.add_argument("--created-by", default="catalog_recovery")
    parser.add_argument("--origin", default="system")
    parser.add_argument("--policy-version", default="publication_policy_v2")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    database_path = args.data_dir / "backend.sqlite3"
    connection = connect_database(database_path)
    try:
        required_tables = {
            "acquisition_publication_head",
            "acquisition_publications",
            "acquisition_publication_jobs",
            "canonical_jobs",
            "canonical_companies",
            "job_posting_versions",
            "job_source_observations",
        }
        present_tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        connection.close()
    missing_tables = sorted(required_tables - present_tables)
    if missing_tables:
        raise RuntimeError(
            "catalog recovery schema preflight failed; missing tables: "
            + ", ".join(missing_tables)
        )
    # The production schema is preflighted above. Avoid replaying every
    # migration over Turso for this one-shot recovery command.
    store = SqliteAcquisitionStore(database_path, initialize=False)
    publication_id = store.publish_existing_catalog_snapshot(
        created_by=args.created_by,
        origin=args.origin,
        policy_version=args.policy_version,
    )
    with store._connect() as connection:
        head = connection.execute(
            """
            SELECT h.publication_id, COUNT(pj.canonical_job_id) AS jobs
            FROM acquisition_publication_head h
            LEFT JOIN acquisition_publication_jobs pj ON pj.publication_id=h.publication_id
            WHERE h.head_id=1
            GROUP BY h.publication_id
            """
        ).fetchone()
        publication = connection.execute(
            "SELECT snapshot_json FROM acquisition_publications WHERE publication_id=?",
            (publication_id,),
        ).fetchone()
        snapshot = json.loads(str(publication["snapshot_json"] or "[]")) if publication else []
        rejected = connection.execute(
            "SELECT COUNT(*) AS count FROM acquisition_job_rejections WHERE cycle_id LIKE 'republish_%'"
        ).fetchone()
    print(
        json.dumps(
            {
                "status": "succeeded",
                "publication_id": publication_id,
                "head_publication_id": str(head["publication_id"] if head else ""),
                "published_jobs": int(head["jobs"] or 0) if head else 0,
                "snapshot_jobs": len(snapshot) if isinstance(snapshot, list) else 0,
                "republish_rejection_rows": int(rejected["count"] or 0) if rejected else 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
