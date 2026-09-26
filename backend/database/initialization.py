from __future__ import annotations

import os
import threading
from pathlib import Path

from backend.database.connection import database_session, database_target_key
from backend.database.migrations import run_migrations
from backend.database.schema import BASE_SCHEMA_SQL

_INITIALIZATION_LOCK = threading.RLock()
_INITIALIZED_TARGETS: dict[str, str] = {}


def _local_database_identity(path: Path) -> str:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return ""
    return f"{stat.st_dev}:{stat.st_ino}"


def _target_identity(local_path: Path) -> str:
    if os.getenv("TURSO_DATABASE_URL", "").strip():
        return "remote"
    return _local_database_identity(local_path)


def initialize_database(local_path: str | Path, *, force: bool = False) -> None:
    """Create the base schema and apply registered migrations once per database."""

    from backend.repositories.sqlite_migrations import MIGRATIONS

    path = Path(local_path)
    target_key = database_target_key(path)
    with _INITIALIZATION_LOCK:
        current_identity = _target_identity(path)
        if (
            not force
            and current_identity
            and _INITIALIZED_TARGETS.get(target_key) == current_identity
        ):
            return

        with database_session(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.executescript(BASE_SCHEMA_SQL)
            run_migrations(connection, MIGRATIONS)

        _INITIALIZED_TARGETS[target_key] = _target_identity(path)
