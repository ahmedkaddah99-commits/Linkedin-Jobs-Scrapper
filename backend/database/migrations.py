from __future__ import annotations

import hashlib
import inspect
import textwrap
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from backend.database.connection import DatabaseConnection
from backend.domain.models import utc_now_iso

MigrationCallable = Callable[[DatabaseConnection], None]


class MigrationChecksumError(RuntimeError):
    """Raised when committed migration code differs from an applied migration."""


def _callable_source(function: Callable[..., object]) -> str:
    try:
        return textwrap.dedent(inspect.getsource(function)).strip()
    except (OSError, TypeError):
        return f"{function.__module__}.{function.__qualname__}"


@dataclass(frozen=True)
class Migration:
    migration_id: str
    description: str
    apply: MigrationCallable
    checksum: str

    @classmethod
    def from_callable(
        cls,
        migration_id: str,
        description: str,
        apply: MigrationCallable,
        *,
        dependencies: Sequence[Callable[..., object]] = (),
    ) -> Migration:
        material = "\n\n".join(
            [
                migration_id,
                description,
                _callable_source(apply),
                *(_callable_source(dependency) for dependency in dependencies),
            ]
        )
        checksum = hashlib.sha256(material.encode("utf-8")).hexdigest()
        return cls(
            migration_id=migration_id,
            description=description,
            apply=apply,
            checksum=checksum,
        )


@dataclass(frozen=True)
class MigrationStatus:
    migration_id: str
    description: str
    state: str
    expected_checksum: str
    applied_checksum: str = ""
    applied_at: str = ""


def _validate_registry(migrations: Sequence[Migration]) -> None:
    migration_ids = [migration.migration_id for migration in migrations]
    if len(migration_ids) != len(set(migration_ids)):
        raise ValueError("Migration IDs must be unique.")
    if migration_ids != sorted(migration_ids):
        raise ValueError("Migrations must be registered in migration ID order.")
    if any(not migration.checksum for migration in migrations):
        raise ValueError("Every migration must have a checksum.")


def _table_exists(connection: DatabaseConnection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _migration_table_columns(connection: DatabaseConnection) -> set[str]:
    if not _table_exists(connection, "schema_migrations"):
        return set()
    rows = connection.execute("PRAGMA table_info(schema_migrations)").fetchall()
    return {str(row["name"]) for row in rows}


def ensure_migration_table(connection: DatabaseConnection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL,
            checksum TEXT NOT NULL DEFAULT ''
        )
        """
    )
    if "checksum" not in _migration_table_columns(connection):
        connection.execute(
            "ALTER TABLE schema_migrations ADD COLUMN checksum TEXT NOT NULL DEFAULT ''"
        )


def _applied_migrations(connection: DatabaseConnection) -> dict[str, tuple[str, str]]:
    columns = _migration_table_columns(connection)
    if not columns:
        return {}
    if "checksum" in columns:
        rows = connection.execute(
            "SELECT migration_id, applied_at, checksum FROM schema_migrations"
        ).fetchall()
        return {
            str(row["migration_id"]): (
                str(row["applied_at"] or ""),
                str(row["checksum"] or ""),
            )
            for row in rows
        }
    rows = connection.execute(
        "SELECT migration_id, applied_at FROM schema_migrations"
    ).fetchall()
    return {
        str(row["migration_id"]): (str(row["applied_at"] or ""), "")
        for row in rows
    }


def get_migration_status(
    connection: DatabaseConnection,
    migrations: Iterable[Migration],
) -> list[MigrationStatus]:
    registry = tuple(migrations)
    _validate_registry(registry)
    applied = _applied_migrations(connection)
    statuses: list[MigrationStatus] = []
    for migration in registry:
        applied_at, applied_checksum = applied.get(migration.migration_id, ("", ""))
        if not applied_at:
            state = "pending"
        elif not applied_checksum:
            state = "applied_unverified"
        elif applied_checksum == migration.checksum:
            state = "applied"
        else:
            state = "checksum_mismatch"
        statuses.append(
            MigrationStatus(
                migration_id=migration.migration_id,
                description=migration.description,
                state=state,
                expected_checksum=migration.checksum,
                applied_checksum=applied_checksum,
                applied_at=applied_at,
            )
        )
    return statuses


def run_migrations(
    connection: DatabaseConnection,
    migrations: Iterable[Migration],
) -> list[str]:
    registry = tuple(migrations)
    _validate_registry(registry)
    ensure_migration_table(connection)
    applied = _applied_migrations(connection)

    for migration in registry:
        if migration.migration_id not in applied:
            continue
        _, applied_checksum = applied[migration.migration_id]
        if applied_checksum and applied_checksum != migration.checksum:
            raise MigrationChecksumError(
                f"Migration '{migration.migration_id}' checksum mismatch: "
                f"database={applied_checksum}, code={migration.checksum}."
            )

    applied_now: list[str] = []
    for migration in registry:
        if migration.migration_id in applied:
            _, applied_checksum = applied[migration.migration_id]
            if not applied_checksum:
                connection.execute(
                    "UPDATE schema_migrations SET checksum = ? WHERE migration_id = ?",
                    (migration.checksum, migration.migration_id),
                )
            continue

        migration.apply(connection)
        connection.execute(
            (
                "INSERT INTO schema_migrations "
                "(migration_id, applied_at, checksum) VALUES (?, ?, ?)"
            ),
            (migration.migration_id, utc_now_iso(), migration.checksum),
        )
        applied_now.append(migration.migration_id)
    return applied_now
