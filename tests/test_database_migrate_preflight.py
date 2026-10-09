from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from backend.database import migrate
from backend.database.migrations import MigrationChecksumError
from backend.repositories.sqlite_migrations import MIGRATIONS


def rows():
    return [{"migration_id": m.migration_id, "checksum": m.checksum, "applied_at": "2026-10-06"} for m in MIGRATIONS]


@pytest.mark.parametrize(
    "change,expected", [("complete", True), ("pending", False), ("unverified", False), ("missing_table", False)]
)
def test_remote_preflight_requires_every_checksum(change, expected):
    c = MagicMock()
    values = rows()
    if change == "pending":
        values.pop()
    if change == "unverified":
        values[-1]["checksum"] = ""
    c.execute.return_value.fetchone.return_value = None if change == "missing_table" else {"name": "schema_migrations"}
    c.execute.return_value.fetchall.return_value = values
    with patch.object(migrate, "database_read_session") as session:
        session.return_value.__enter__.return_value = c
        assert migrate._remote_migrations_verified(Path("unused.sqlite3")) is expected


def test_remote_preflight_rejects_checksum_mismatch():
    c = MagicMock()
    values = rows()
    values[-1]["checksum"] = "incorrect"
    c.execute.return_value.fetchone.return_value = {"name": "schema_migrations"}
    c.execute.return_value.fetchall.return_value = values
    with patch.object(migrate, "database_read_session") as session:
        session.return_value.__enter__.return_value = c
        with pytest.raises(MigrationChecksumError):
            migrate._remote_migrations_verified(Path("unused.sqlite3"))
