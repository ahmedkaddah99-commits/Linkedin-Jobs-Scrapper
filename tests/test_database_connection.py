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
    DatabaseConnection,
    connect_database,
    database_session,
    database_target_info,
    transient_database_error_category,
)


class PanicException(BaseException):
    pass


PanicException.__module__ = "pyo3_runtime"


class UnrelatedBaseException(BaseException):
    pass


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
            {"RUNR_ENV": "development", "DATABASE_BACKEND": "sqlite", "TURSO_DATABASE_URL": "", "TURSO_AUTH_TOKEN": ""},
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
            {"RUNR_ENV": "development", "DATABASE_BACKEND": "sqlite", "TURSO_DATABASE_URL": "", "TURSO_AUTH_TOKEN": ""},
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

    def test_database_session_cleanup_does_not_mask_original_error(self):
        raw_connection = Mock()
        raw_connection.rollback.side_effect = RuntimeError("HTTP 503 during rollback")
        raw_connection.close.side_effect = RuntimeError("HTTP 503 during close")
        connection = DatabaseConnection(raw_connection, backend="libsql")

        with (
            patch("backend.database.connection.connect_database", return_value=connection),
            patch("backend.database.connection.time.sleep"),
            patch("backend.database.connection.random.uniform", return_value=0.0),
            self.assertRaisesRegex(RuntimeError, "primary failure"),
        ):
            with database_session(Path("unused.sqlite3")):
                raise RuntimeError("primary failure")

    def test_database_session_cleanup_panic_does_not_mask_fatal_primary_error(self):
        for fatal_error in (KeyboardInterrupt("stop"), SystemExit(2)):
            with self.subTest(error=type(fatal_error).__name__):
                raw_connection = Mock()
                raw_connection.rollback.side_effect = PanicException("rollback panic")
                raw_connection.close.side_effect = PanicException("close panic")
                connection = DatabaseConnection(raw_connection, backend="sqlite")

                with (
                    patch("backend.database.connection.connect_database", return_value=connection),
                    self.assertRaises(type(fatal_error)) as raised,
                ):
                    with database_session(Path("unused.sqlite3")):
                        raise fatal_error

                self.assertIs(raised.exception, fatal_error)
                raw_connection.rollback.assert_called_once()
                raw_connection.close.assert_called_once()

    def test_connection_context_cleanup_panic_does_not_mask_fatal_primary_error(self):
        for fatal_error in (KeyboardInterrupt("stop"), SystemExit(2)):
            with self.subTest(error=type(fatal_error).__name__):
                raw_connection = Mock()
                raw_connection.rollback.side_effect = PanicException("rollback panic")
                raw_connection.close.side_effect = PanicException("close panic")
                connection = DatabaseConnection(raw_connection, backend="sqlite")

                with self.assertRaises(type(fatal_error)) as raised:
                    with connection:
                        raise fatal_error

                self.assertIs(raised.exception, fatal_error)
                raw_connection.rollback.assert_called_once()
                raw_connection.close.assert_called_once()

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
                    "DATABASE_BACKEND": "turso",
                    "RUNR_ENV": "development",
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

    def test_remote_turso_connection_recovers_from_transient_upstream_failure(self):
        db_path = self._db_path("database_connection_retry_recovery")
        raw_connection = sqlite3.connect(":memory:")
        connect = Mock(
            side_effect=[
                RuntimeError(
                    "Hrana returned HTTP 502: upstream forward failed "
                    "for libsql://private.example with token-secret"
                ),
                raw_connection,
            ]
        )
        fake_libsql = types.ModuleType("libsql")
        fake_libsql.connect = connect

        with (
            patch.dict(sys.modules, {"libsql": fake_libsql}),
            patch.dict(
                os.environ,
                {
                    "DATABASE_BACKEND": "turso",
                    "RUNR_ENV": "development",
                    "TURSO_DATABASE_URL": "libsql://example-database.turso.io",
                    "TURSO_AUTH_TOKEN": "test-token",
                },
            ),
            patch("backend.database.connection.time.sleep") as sleep,
            patch("backend.database.connection.random.uniform", return_value=0.0),
            self.assertLogs("backend.database.connection", level="WARNING") as captured_logs,
        ):
            connection = connect_database(db_path)
            connection.close()

        self.assertEqual(connect.call_count, 2)
        sleep.assert_called_once()
        retry_record = captured_logs.records[0]
        self.assertEqual(retry_record.operation, "connect")
        self.assertEqual(retry_record.attempt, 1)
        self.assertEqual(retry_record.delay_seconds, 0.25)
        self.assertEqual(retry_record.error_category, "upstream_forward")
        self.assertNotIn("token-secret", retry_record.getMessage())
        self.assertNotIn("private.example", retry_record.getMessage())

    def test_libsql_operation_stops_after_bounded_transient_retries(self):
        raw_connection = Mock()
        raw_connection.execute.side_effect = RuntimeError("HTTP 503 service unavailable")
        connection = DatabaseConnection(raw_connection, backend="libsql")

        with (
            patch("backend.database.connection.time.sleep") as sleep,
            patch("backend.database.connection.random.uniform", return_value=0.0),
            self.assertRaisesRegex(RuntimeError, "503"),
        ):
            connection.execute("SELECT 1")

        self.assertEqual(raw_connection.execute.call_count, 4)
        self.assertEqual(sleep.call_count, 3)

    def test_libsql_operation_recovers_from_timeout_and_network_errors(self):
        for error in (
            TimeoutError("request timed out"),
            OSError("temporary network failure"),
            RuntimeError('Hrana: `api error: `status=404 Not Found, body={"error":"stream not found: abc:def"}``'),
        ):
            with self.subTest(error=type(error).__name__):
                raw_cursor = Mock(rowcount=-1, lastrowid=None, description=None)
                raw_connection = Mock()
                raw_connection.execute.side_effect = [error, raw_cursor]
                connection = DatabaseConnection(raw_connection, backend="libsql")

                with (
                    patch("backend.database.connection.time.sleep") as sleep,
                    patch("backend.database.connection.random.uniform", return_value=0.0),
                ):
                    connection.execute("SELECT 1")

                self.assertEqual(raw_connection.execute.call_count, 2)
                sleep.assert_called_once()

    def test_libsql_operation_reconnects_before_retrying_stale_stream(self):
        stale_connection = Mock()
        fresh_cursor = Mock(rowcount=-1, lastrowid=None, description=None)
        fresh_connection = Mock()
        stale_connection.execute.side_effect = RuntimeError(
            'Hrana: `api error: `status=404 Not Found, body={"error":"stream not found: abc:def"}``'
        )
        fresh_connection.execute.return_value = fresh_cursor
        reconnect = Mock(return_value=fresh_connection)
        connection = DatabaseConnection(stale_connection, backend="libsql", reconnect=reconnect)

        with (
            patch("backend.database.connection.time.sleep") as sleep,
            patch("backend.database.connection.random.uniform", return_value=0.0),
        ):
            connection.execute("SELECT 1")

        stale_connection.close.assert_called_once()
        reconnect.assert_called_once()
        fresh_connection.execute.assert_called_once_with("SELECT 1", ())
        sleep.assert_called_once()

    def test_libsql_operation_reconnects_before_retrying_driver_panic(self):
        stale_connection = Mock()
        fresh_cursor = Mock(rowcount=-1, lastrowid=None, description=None)
        fresh_connection = Mock()
        stale_connection.execute.side_effect = PanicException(
            "called `Option::unwrap()` on a `None` value"
        )
        fresh_connection.execute.return_value = fresh_cursor
        reconnect = Mock(return_value=fresh_connection)
        connection = DatabaseConnection(stale_connection, backend="libsql", reconnect=reconnect)

        with (
            patch("backend.database.connection.time.sleep") as sleep,
            patch("backend.database.connection.random.uniform", return_value=0.0),
        ):
            connection.execute("SELECT 1")

        self.assertEqual(transient_database_error_category(PanicException("panic")), "driver_panic")
        stale_connection.close.assert_called_once()
        reconnect.assert_called_once()
        fresh_connection.execute.assert_called_once_with("SELECT 1", ())
        sleep.assert_called_once()

    def test_libsql_rollback_retries_on_refreshed_connection(self):
        stale_connection = Mock()
        stale_connection.rollback.side_effect = PanicException("rollback panic")
        fresh_connection = Mock()
        reconnect = Mock(return_value=fresh_connection)
        connection = DatabaseConnection(stale_connection, backend="libsql", reconnect=reconnect)

        with (
            patch("backend.database.connection.time.sleep") as sleep,
            patch("backend.database.connection.random.uniform", return_value=0.0),
        ):
            connection.rollback()

        stale_connection.rollback.assert_called_once()
        stale_connection.close.assert_called_once()
        reconnect.assert_called_once()
        fresh_connection.rollback.assert_called_once()
        sleep.assert_called_once()

    def test_driver_panic_classification_requires_matching_class_and_module(self):
        libsql_panic_type = type(
            "PanicException",
            (BaseException,),
            {"__module__": "libsql._internal"},
        )
        lookalike_panic_type = type(
            "PanicException",
            (BaseException,),
            {"__module__": "runr.pyo3_adapter"},
        )

        self.assertEqual(transient_database_error_category(PanicException("panic")), "driver_panic")
        self.assertEqual(
            transient_database_error_category(libsql_panic_type("panic")),
            "driver_panic",
        )
        self.assertIsNone(transient_database_error_category(lookalike_panic_type("network timeout")))
        self.assertIsNone(transient_database_error_category(UnrelatedBaseException("HTTP 503 timeout")))

    def test_libsql_transaction_replays_statements_after_commit_driver_panic(self):
        stale_cursor = Mock(rowcount=1, lastrowid=None, description=None)
        stale_connection = Mock()
        stale_connection.execute.return_value = stale_cursor
        stale_connection.commit.side_effect = PanicException(
            "called `Option::unwrap()` on a `None` value"
        )
        fresh_cursor = Mock(rowcount=1, lastrowid=None, description=None)
        fresh_connection = Mock()
        fresh_connection.execute.return_value = fresh_cursor
        reconnect = Mock(return_value=fresh_connection)
        connection = DatabaseConnection(stale_connection, backend="libsql", reconnect=reconnect)
        attempts = []

        def operation(active_connection):
            attempts.append(active_connection)
            active_connection.execute("UPDATE site_source_policy SET site_state = ?", ("selected",))
            return "selected"

        with (
            patch("backend.database.connection.time.sleep") as sleep,
            patch("backend.database.connection.random.uniform", return_value=0.0),
        ):
            result = connection.transaction(operation)

        self.assertEqual(result, "selected")
        self.assertEqual(attempts, [connection, connection])
        stale_connection.execute.assert_called_once()
        stale_connection.commit.assert_called_once()
        stale_connection.rollback.assert_called_once()
        stale_connection.close.assert_called_once()
        reconnect.assert_called_once()
        fresh_connection.execute.assert_called_once()
        fresh_connection.commit.assert_called_once()
        sleep.assert_called_once()

    def test_libsql_transaction_does_not_swallow_unrelated_base_exception(self):
        for fatal_error in (
            KeyboardInterrupt("network timeout"),
            SystemExit("HTTP 503 service unavailable"),
            UnrelatedBaseException("HTTP 502 upstream forward timeout"),
        ):
            with self.subTest(error=type(fatal_error).__name__):
                raw_connection = Mock()
                reconnect = Mock()
                connection = DatabaseConnection(raw_connection, backend="libsql", reconnect=reconnect)

                def raise_fatal(_connection):
                    raise fatal_error

                with (
                    patch("backend.database.connection.time.sleep") as sleep,
                    self.assertRaises(type(fatal_error)),
                ):
                    connection.transaction(raise_fatal)

                raw_connection.rollback.assert_called_once()
                raw_connection.commit.assert_not_called()
                reconnect.assert_not_called()
                sleep.assert_not_called()
                self.assertIsNone(transient_database_error_category(fatal_error))

    def test_libsql_operation_does_not_retry_non_retryable_errors(self):
        for error in (
            RuntimeError("HTTP 401 unauthorized"),
            sqlite3.ProgrammingError("syntax error in SQL statement"),
            sqlite3.IntegrityError("unique constraint failed"),
        ):
            with self.subTest(error=type(error).__name__):
                raw_connection = Mock()
                raw_connection.execute.side_effect = error
                connection = DatabaseConnection(raw_connection, backend="libsql")

                with (
                    patch("backend.database.connection.time.sleep") as sleep,
                    self.assertRaises(type(error)),
                ):
                    connection.execute("SELECT 1")

                raw_connection.execute.assert_called_once()
                sleep.assert_not_called()

    def test_remote_turso_connection_requires_auth_token(self):
        with patch.dict(
            os.environ,
            {
                "TURSO_DATABASE_URL": "libsql://example-database.turso.io",
                "RUNR_ENV": "development",
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
                "RUNR_ENV": "development",
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

    def test_database_backend_turso_requires_remote_url(self):
        with patch.dict(
            os.environ,
            {
                "DATABASE_BACKEND": "turso",
                "RUNR_ENV": "development",
                "TURSO_DATABASE_URL": "",
                "TURSO_AUTH_TOKEN": "test-token",
            },
        ):
            self.assertEqual(
                database_target_info(Path("unused.sqlite3"))["target_backend"],
                "libsql",
            )
            with self.assertRaisesRegex(
                DatabaseConfigurationError,
                "TURSO_DATABASE_URL",
            ):
                connect_database(Path("unused.sqlite3"))


if __name__ == "__main__":
    unittest.main()
