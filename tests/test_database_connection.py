import os
import shutil
import sqlite3
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend.database.connection import (
    DatabaseConfigurationError,
    connect_database,
    database_session,
)


class DatabaseConnectionTests(unittest.TestCase):
    def _db_path(self, name: str) -> Path:
        path = Path.cwd() / ".backend_test_tmp" / name / "backend.sqlite3"
        if path.parent.exists():
            shutil.rmtree(path.parent, ignore_errors=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(path.parent, ignore_errors=True))
        return path

    def test_local_connection_supports_rows_scripts_batches_and_rowcount(self):
        db_path = self._db_path("database_connection_local")
        with patch.dict(
            os.environ,
            {"TURSO_DATABASE_URL": "", "TURSO_AUTH_TOKEN": ""},
        ):
            with database_session(db_path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE records (
                        record_id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL
                    );
                    INSERT INTO records (record_id, name) VALUES (1, 'first');
                    INSERT INTO records (record_id, name) VALUES (4, 'no-semicolon')
                    """
                )
                inserted = connection.executemany(
                    "INSERT INTO records (record_id, name) VALUES (?, ?)",
                    [(2, "second"), (3, "third")],
                )
                updated = connection.execute(
                    "UPDATE records SET name = ? WHERE record_id = ?",
                    ("updated", 2),
                )
                row = connection.execute(
                    "SELECT record_id, name FROM records WHERE record_id = ?",
                    (2,),
                ).fetchone()

        self.assertEqual(inserted.rowcount, 2)
        self.assertEqual(updated.rowcount, 1)
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 2)
        self.assertEqual(row["name"], "updated")
        self.assertEqual(dict(row), {"record_id": 2, "name": "updated"})
        self.assertEqual(row.keys(), ["record_id", "name"])

    def test_database_session_rolls_back_failed_transaction(self):
        db_path = self._db_path("database_connection_rollback")
        with patch.dict(
            os.environ,
            {"TURSO_DATABASE_URL": "", "TURSO_AUTH_TOKEN": ""},
        ):
            with database_session(db_path) as connection:
                connection.execute("CREATE TABLE records (record_id INTEGER PRIMARY KEY)")

            with self.assertRaisesRegex(RuntimeError, "stop"):
                with database_session(db_path) as connection:
                    connection.execute("INSERT INTO records (record_id) VALUES (1)")
                    raise RuntimeError("stop")

            with database_session(db_path) as connection:
                count = connection.execute("SELECT COUNT(*) FROM records").fetchone()[0]

        self.assertEqual(count, 0)

    def test_remote_turso_connection_uses_libsql_environment_contract(self):
        db_path = self._db_path("database_connection_remote")
        raw_connection = sqlite3.connect(":memory:")
        connect = Mock(return_value=raw_connection)
        fake_libsql = types.ModuleType("libsql")
        fake_libsql.connect = connect

        with (
            patch.dict(sys.modules, {"libsql": fake_libsql}),
            patch.dict(
                os.environ,
                {
                    "TURSO_DATABASE_URL": "libsql://example-database.turso.io",
                    "TURSO_AUTH_TOKEN": "test-token",
                },
            ),
        ):
            connection = connect_database(db_path)
            try:
                self.assertEqual(connection.backend, "libsql")
                connection.execute("CREATE TABLE records (record_id INTEGER PRIMARY KEY)")
                connection.execute("INSERT INTO records (record_id) VALUES (?)", (1,))
                connection.commit()
                self.assertEqual(
                    connection.execute("SELECT record_id FROM records").fetchone()[0],
                    1,
                )
            finally:
                connection.close()

        connect.assert_called_once_with(
            database="libsql://example-database.turso.io",
            auth_token="test-token",
        )
        self.assertFalse(db_path.exists())

    def test_remote_turso_connection_requires_auth_token(self):
        with patch.dict(
            os.environ,
            {
                "TURSO_DATABASE_URL": "libsql://example-database.turso.io",
                "TURSO_AUTH_TOKEN": "",
            },
        ):
            with self.assertRaisesRegex(
                DatabaseConfigurationError,
                "TURSO_AUTH_TOKEN",
            ):
                connect_database(Path("unused.sqlite3"))

    def test_installed_libsql_driver_supports_the_connection_adapter(self):
        with patch.dict(
            os.environ,
            {
                "TURSO_DATABASE_URL": ":memory:",
                "TURSO_AUTH_TOKEN": "test-token",
            },
        ):
            connection = connect_database(Path("unused.sqlite3"))
            try:
                connection.executescript(
                    """
                    CREATE TABLE records (
                        record_id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL
                    );
                    INSERT INTO records (name) VALUES ('actual-driver');
                    """
                )
                connection.commit()
                row = connection.execute(
                    "SELECT record_id, name FROM records"
                ).fetchone()
            finally:
                connection.close()

        self.assertEqual(connection.backend, "libsql")
        self.assertEqual(dict(row), {"record_id": 1, "name": "actual-driver"})


if __name__ == "__main__":
    unittest.main()
