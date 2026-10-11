from __future__ import annotations

import argparse
from pathlib import Path

from backend.config import load_project_dotenv, validate_environment
from backend.database.connection import database_read_session, database_session, database_target_info
from backend.database.initialization import initialize_database
from backend.database.migrations import MigrationChecksumError, get_migration_status
from backend.repositories.sqlite_migrations import MIGRATIONS


def _remote_migrations_verified(database_path: Path) -> bool:
    """Avoid opening a write transaction when the remote registry is complete."""
    with database_read_session(database_path) as connection:
        exists = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
        if exists is None:
            return False
        rows = connection.execute("SELECT * FROM schema_migrations").fetchall()
    applied = {row["migration_id"]: dict(row) for row in rows}
    verified = True
    for migration in MIGRATIONS:
        row = applied.get(migration.migration_id, {})
        checksum = row.get("checksum", "")
        if checksum and checksum != migration.checksum:
            raise MigrationChecksumError(f"Migration '{migration.migration_id}' checksum mismatch.")
        if not row.get("applied_at") or not checksum:
            verified = False
    return verified


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply or inspect database migrations.")
    parser.add_argument(
        "--database",
        default=".backend_data/backend.sqlite3",
        help="Local SQLite path used when TURSO_DATABASE_URL is not configured.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print migration status without applying migrations.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    load_project_dotenv()
    args = _parser().parse_args(argv)
    validate_environment()
    database_path = Path(args.database)
    if (
        not args.status
        and database_target_info(database_path).get("target_backend") == "libsql"
        and _remote_migrations_verified(database_path)
    ):
        print(f"{MIGRATIONS[-1].migration_id}\tapplied\tAll registered migration checksums verified.")
        return 0
    if args.status:
        with database_session(database_path) as connection:
            statuses = get_migration_status(connection, MIGRATIONS)
        for status in statuses:
            print(f"{status.migration_id}\t{status.state}\t{status.description}")
        return 0

    initialize_database(database_path, force=True)
    with database_session(database_path) as connection:
        statuses = get_migration_status(connection, MIGRATIONS)
    for status in statuses:
        print(f"{status.migration_id}\t{status.state}\t{status.description}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
