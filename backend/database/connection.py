from __future__ import annotations

import importlib
import os
import sqlite3
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DatabaseParameters = Sequence[Any] | Mapping[str, Any]


class DatabaseConfigurationError(RuntimeError):
    """Raised when the selected database backend is not configured correctly."""


class DatabaseRow(Mapping[str, Any]):
    """sqlite3.Row-compatible result supporting indexes, names, and dict(row)."""

    __slots__ = ("_columns", "_index", "_values")

    def __init__(self, columns: Sequence[str], values: Sequence[Any]):
        normalized_columns = tuple(str(column) for column in columns)
        normalized_values = tuple(values)
        if len(normalized_columns) != len(normalized_values):
            raise ValueError("Database row column and value counts differ.")
        self._columns = normalized_columns
        self._values = normalized_values
        self._index = {column: index for index, column in enumerate(normalized_columns)}

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return self._values[self._index[key]]

    def __iter__(self) -> Iterator[str]:
        return iter(self._columns)

    def __len__(self) -> int:
        return len(self._columns)

    def keys(self) -> list[str]:
        return list(self._columns)


def _column_names(description: Any) -> tuple[str, ...]:
    if not description:
        return ()
    return tuple(str(column[0]) for column in description)


def _row_values(row: Any, columns: Sequence[str]) -> tuple[Any, ...]:
    if isinstance(row, DatabaseRow):
        return tuple(row[index] for index in range(len(row)))
    if isinstance(row, Mapping):
        return tuple(row[column] for column in columns)
    return tuple(row)


class DatabaseCursor:
    """Small cursor adapter shared by sqlite3 and the Python libSQL driver."""

    def __init__(
        self,
        cursor: Any,
        *,
        rowcount: int | None = None,
        lastrowid: Any = None,
    ):
        self._cursor = cursor
        self._columns = _column_names(getattr(cursor, "description", None))
        raw_rowcount = getattr(cursor, "rowcount", -1)
        self._rowcount = int(raw_rowcount if rowcount is None else rowcount)
        self._lastrowid = getattr(cursor, "lastrowid", None) if lastrowid is None else lastrowid

    @property
    def description(self) -> Any:
        return getattr(self._cursor, "description", None)

    @property
    def rowcount(self) -> int:
        return self._rowcount

    @property
    def lastrowid(self) -> Any:
        return self._lastrowid

    def _adapt_row(self, row: Any) -> DatabaseRow | None:
        if row is None:
            return None
        return DatabaseRow(self._columns, _row_values(row, self._columns))

    def fetchone(self) -> DatabaseRow | None:
        return self._adapt_row(self._cursor.fetchone())

    def fetchall(self) -> list[DatabaseRow]:
        return [self._adapt_row(row) for row in self._cursor.fetchall()]

    def __iter__(self) -> Iterator[DatabaseRow]:
        while True:
            row = self.fetchone()
            if row is None:
                return
            yield row


def _statement_changes_rows(sql: str) -> bool:
    statement = sql.lstrip().split(None, 1)
    if not statement:
        return False
    return statement[0].upper() in {"DELETE", "INSERT", "REPLACE", "UPDATE"}


class DatabaseConnection:
    """Synchronous sqlite3-compatible facade over sqlite3 or libSQL."""

    def __init__(self, connection: Any, *, backend: str):
        self._connection = connection
        self.backend = backend

    def _changes(self) -> int:
        cursor = self._connection.execute("SELECT changes()")
        row = cursor.fetchone()
        return int(row[0] if row is not None else 0)

    def execute(self, sql: str, parameters: DatabaseParameters = ()) -> DatabaseCursor:
        cursor = self._connection.execute(sql, parameters)
        raw_rowcount = getattr(cursor, "rowcount", -1)
        rowcount = int(raw_rowcount) if raw_rowcount is not None else -1
        lastrowid = getattr(cursor, "lastrowid", None)
        if rowcount < 0 and _statement_changes_rows(sql):
            rowcount = self._changes()
        return DatabaseCursor(cursor, rowcount=rowcount, lastrowid=lastrowid)

    def executemany(
        self,
        sql: str,
        parameter_rows: Iterable[DatabaseParameters],
    ) -> DatabaseCursor:
        cursor = self._connection.executemany(sql, list(parameter_rows))
        raw_rowcount = getattr(cursor, "rowcount", -1)
        rowcount = int(raw_rowcount) if raw_rowcount is not None else -1
        lastrowid = getattr(cursor, "lastrowid", None)
        if rowcount < 0 and _statement_changes_rows(sql):
            rowcount = self._changes()
        return DatabaseCursor(cursor, rowcount=rowcount, lastrowid=lastrowid)

    def executescript(self, script: str) -> DatabaseCursor | None:
        pending = ""
        last_cursor: DatabaseCursor | None = None
        for character in script:
            pending += character
            if character == ";" and sqlite3.complete_statement(pending):
                statement = pending.strip()
                pending = ""
                if statement:
                    last_cursor = self.execute(statement)
        if pending.strip():
            last_cursor = self.execute(pending.strip())
        return last_cursor

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> DatabaseConnection:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()
        return False


def _remote_database_url() -> str:
    return os.getenv("TURSO_DATABASE_URL", "").strip()


def database_target_key(local_path: str | Path) -> str:
    remote_url = _remote_database_url()
    if remote_url:
        return f"libsql:{remote_url}"
    return f"sqlite:{Path(local_path).expanduser().resolve()}"


def connect_database(local_path: str | Path) -> DatabaseConnection:
    """Connect to Turso when configured, otherwise preserve local sqlite3 behavior."""

    remote_url = _remote_database_url()
    if remote_url:
        auth_token = os.getenv("TURSO_AUTH_TOKEN", "").strip()
        if not auth_token:
            raise DatabaseConfigurationError(
                "TURSO_AUTH_TOKEN is required when TURSO_DATABASE_URL is configured."
            )
        try:
            libsql = importlib.import_module("libsql")
        except ImportError as exc:
            raise DatabaseConfigurationError(
                "The 'libsql' package is required when TURSO_DATABASE_URL is configured."
            ) from exc
        raw_connection = libsql.connect(database=remote_url, auth_token=auth_token)
        connection = DatabaseConnection(raw_connection, backend="libsql")
    else:
        path = Path(local_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        raw_connection = sqlite3.connect(path, timeout=30)
        connection = DatabaseConnection(raw_connection, backend="sqlite")

    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def database_session(local_path: str | Path) -> Iterator[DatabaseConnection]:
    connection = connect_database(local_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
