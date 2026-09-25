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
from backend.acquisition.publication import RestorePublicationConfirmation
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
    parser.add_argument("--policy-version", default="publication_policy_v1")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rollback-publication")
    parser.add_argument("--expected-head-publication", default="")
    parser.add_argument("--actor-user-id", default=os.getenv("RUNR_ACTOR_USER_ID", "catalog_recovery"))
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
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
    if args.rollback_publication:
        if not args.expected_head_publication:
            raise ValueError("--expected-head-publication is required for rollback")
        restored_publication_id = store.restore_publication(
            RestorePublicationConfirmation.from_values(
                target_publication_id=args.rollback_publication,
                expected_head_publication_id=args.expected_head_publication,
                actor_user_id=args.actor_user_id,
                confirmation="restore_publication",
            )
        )
        print(
            json.dumps(
                {
                    "status": "restored",
                    "publication_id": restored_publication_id,
                    "target_publication_id": args.rollback_publication,
                    "expected_head_publication_id": args.expected_head_publication,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return
    if args.dry_run:
        preview = store.publish_existing_catalog_snapshot(
            created_by=args.created_by,
            origin=args.origin,
            policy_version=args.policy_version,
            batch_size=args.batch_size,
            dry_run=True,
        )
        assert isinstance(preview, dict)
        preview["limits"] = {"batch_size": int(preview["batch_size"])}
        print(json.dumps(preview, ensure_ascii=False, sort_keys=True))
        return
    publication_id = store.publish_existing_catalog_snapshot(
        created_by=args.created_by,
        origin=args.origin,
        policy_version=args.policy_version,
        batch_size=args.batch_size,
    )
    assert isinstance(publication_id, str)
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
