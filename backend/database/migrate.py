from __future__ import annotations

import argparse
from pathlib import Path

from backend.config import load_project_dotenv, validate_environment
from backend.database.connection import database_session
from backend.database.initialization import initialize_database
from backend.database.migrations import get_migration_status
from backend.repositories.sqlite_migrations import MIGRATIONS


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
