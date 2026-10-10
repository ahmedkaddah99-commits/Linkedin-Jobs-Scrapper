from __future__ import annotations

import importlib
import json
import logging
import os
import random
import re
import sqlite3
import time
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, TypeVar
from urllib.error import HTTPError
from urllib.request import Request, urlopen

DatabaseParameters = Sequence[Any] | Mapping[str, Any]
ResultT = TypeVar("ResultT")

_LOGGER = logging.getLogger("backend.database.connection")
_LIBSQL_RETRY_ATTEMPTS = 4
_LIBSQL_RETRY_BASE_DELAY_SECONDS = 0.25
_LIBSQL_RETRY_MAX_DELAY_SECONDS = 2.0
_LIBSQL_RETRY_JITTER_SECONDS = 0.1

_NON_RETRYABLE_ERROR_MARKERS = (
    "authentication",
    "authorization",
    "unauthorized",
    "forbidden",
    "invalid token",
    "invalid auth",
    "http 400",
    "http 401",
    "http 403",
    "status 400",
    "status 401",
    "status 403",
    "constraint",
    "syntax error",
    "invalid sql",
    "no such table",
    "no such column",
    "datatype mismatch",
    "incorrect number of bindings",
    "sqlite_auth",
    "sqlite_constraint",
    "sqlite_error",
    "sqlite_mismatch",
    "sqlite_misuse",
    "sqlite_range",
    "sqlite_readonly",
    "sqlite_schema",
)

_TRANSIENT_ERROR_MARKERS = (
    ("stream already in use", "stale_stream"),
    ("upstream forward", "upstream_forward"),
    ("http 502", "http_502"),
    ("status 502", "http_502"),
    ("status code 502", "http_502"),
    ("502 bad gateway", "http_502"),
    ("http 503", "http_503"),
    ("status 503", "http_503"),
    ("status code 503", "http_503"),
    ("service unavailable", "temporary_unavailable"),
    ("temporarily unavailable", "temporary_unavailable"),
    ("temporary failure", "temporary_unavailable"),
    ("timed out", "timeout"),
    ("timeout", "timeout"),
    ("connection reset", "network"),
    ("connection refused", "network"),
    ("connection aborted", "network"),
    ("connection closed before message completed", "network"),
    ("broken pipe", "network"),
    ("network", "network"),
    ("transport", "network"),
    ("server disconnected", "network"),
    ("stream not found", "stale_stream"),
)

_DATABASE_DRIVER_PANIC_CLASS_NAMES = {"PanicException"}
_DATABASE_DRIVER_PANIC_MODULE_PREFIXES = ("pyo3_runtime", "libsql")


class DatabaseConfigurationError(RuntimeError):
    """Raised when the selected database backend is not configured correctly."""


_RELEASE_PLACEHOLDER_VALUES = frozenset({"", "unknown", "unset", "none"})


def _known_release_value(value: object) -> str:
    normalized = str(value or "").strip()
    if normalized.casefold() in _RELEASE_PLACEHOLDER_VALUES:
        return ""
    return normalized


def _release_value(value: str | None, environment_name: str) -> str:
    if value is not None:
        return _known_release_value(value)
    return _known_release_value(os.getenv(environment_name, ""))


def _require_matching_release_values(
    label: str,
    left_name: str,
    left_value: str,
    right_name: str,
    right_value: str,
) -> None:
    if left_value and right_value and left_value != right_value:
        raise DatabaseConfigurationError(
            f"Release {label} mismatch: {left_name}={left_value!r}, "
            f"{right_name}={right_value!r}."
        )


def validate_release_provenance(
    *,
    release_branch: str | None = None,
    runtime_branch: str | None = None,
    release_commit: str | None = None,
    runtime_commit: str | None = None,
    configured_migration_head: str | None = None,
) -> str:
    """Fail closed when known release metadata disagrees with the code registry."""

    from backend.repositories.sqlite_migrations import current_migration_head

    expected_migration_head = current_migration_head()
    configured_head = _release_value(configured_migration_head, "RUNR_MIGRATION_HEAD")
    if configured_head and configured_head != expected_migration_head:
        raise DatabaseConfigurationError(
            "Configured migration head does not match the code registry: "
            f"configured={configured_head!r}, expected={expected_migration_head!r}."
        )

    _require_matching_release_values(
        "branch",
        "RUNR_RELEASE_BRANCH",
        _release_value(release_branch, "RUNR_RELEASE_BRANCH"),
        "RENDER_GIT_BRANCH",
        _release_value(runtime_branch, "RENDER_GIT_BRANCH"),
    )
    _require_matching_release_values(
        "commit",
        "RUNR_RELEASE_COMMIT",
        _release_value(release_commit, "RUNR_RELEASE_COMMIT"),
        "RENDER_GIT_COMMIT",
        _release_value(runtime_commit, "RENDER_GIT_COMMIT"),
    )
    return expected_migration_head


def _exception_chain(exc: BaseException) -> Iterator[BaseException]:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def transient_database_error_category(exc: BaseException) -> str | None:
    """Return a safe category for retryable Turso/libSQL transport failures."""

    chain = tuple(_exception_chain(exc))
    if any(isinstance(error, (KeyboardInterrupt, SystemExit)) for error in chain):
        return None
    if any(_is_database_driver_panic(error) for error in chain):
        return "driver_panic"
    if any(not isinstance(error, Exception) for error in chain):
        return None
    if any(
        isinstance(
            error,
            (
                DatabaseConfigurationError,
                sqlite3.DataError,
                sqlite3.IntegrityError,
                sqlite3.NotSupportedError,
                sqlite3.ProgrammingError,
            ),
        )
        for error in chain
    ):
        return None

    messages = " ".join(str(error).lower() for error in chain)
    if any(marker in messages for marker in _NON_RETRYABLE_ERROR_MARKERS):
        return None
    if any(isinstance(error, TimeoutError) for error in chain):
        return "timeout"
    if any(isinstance(error, ConnectionError) for error in chain):
        return "network"
    if any(isinstance(error, OSError) for error in chain):
        return "network"
    for marker, category in _TRANSIENT_ERROR_MARKERS:
        if marker in messages:
            return category
    return None


def _is_database_driver_panic(exc: BaseException) -> bool:
    exc_type = type(exc)
    type_name = exc_type.__name__
    module_name = exc_type.__module__.lower()
    if type_name not in _DATABASE_DRIVER_PANIC_CLASS_NAMES:
        return False
    return any(
        module_name == prefix or module_name.startswith(f"{prefix}.")
        for prefix in _DATABASE_DRIVER_PANIC_MODULE_PREFIXES
    )


def is_transient_database_error(exc: BaseException) -> bool:
    return transient_database_error_category(exc) is not None


def _retry_libsql_operation(
    operation: str,
    callback: Callable[[], ResultT],
    *,
    before_retry: Callable[[str], None] | None = None,
) -> ResultT:
    for attempt in range(1, _LIBSQL_RETRY_ATTEMPTS + 1):
        try:
            return callback()
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as exc:
            category = transient_database_error_category(exc)
            if category is None or attempt >= _LIBSQL_RETRY_ATTEMPTS:
                raise
            backoff = min(
                _LIBSQL_RETRY_MAX_DELAY_SECONDS,
                _LIBSQL_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)),
            )
            delay = backoff + random.uniform(0.0, _LIBSQL_RETRY_JITTER_SECONDS)
            if before_retry is not None:
                before_retry(category)
            _LOGGER.warning(
                "database_operation_retry",
                extra={
                    "operation": operation,
                    "attempt": attempt,
                    "delay_seconds": round(delay, 3),
                    "error_category": category,
                },
            )
            time.sleep(delay)
    raise AssertionError("libSQL retry loop exited unexpectedly")


def _log_cleanup_failure(operation: str, exc: BaseException) -> None:
    _LOGGER.warning(
        "database_cleanup_failed",
        extra={
            "operation": operation,
            "error_category": transient_database_error_category(exc) or "non_retryable",
        },
    )


def _handle_cleanup_failure(
    operation: str,
    cleanup_error: BaseException,
    *,
    primary_error: BaseException | None,
) -> None:
    """Preserve a primary failure without swallowing a new fatal cleanup signal."""

    if primary_error is None:
        raise cleanup_error
    cleanup_category = transient_database_error_category(cleanup_error)
    primary_is_fatal = not isinstance(primary_error, Exception)
    cleanup_is_fatal = not isinstance(cleanup_error, Exception)
    if cleanup_is_fatal and cleanup_category is None and not primary_is_fatal:
        raise cleanup_error
    if (
        isinstance(cleanup_error, (KeyboardInterrupt, SystemExit))
        and not isinstance(primary_error, (KeyboardInterrupt, SystemExit))
    ):
        raise cleanup_error
    _log_cleanup_failure(operation, cleanup_error)


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

    def __init__(
        self,
        connection: Any,
        *,
        backend: str,
        reconnect: Callable[[], Any] | None = None,
    ):
        self._connection = connection
        self.backend = backend
        self._reconnect = reconnect
        self._transaction_depth = 0

    def _refresh_connection_for_retry(self, category: str) -> None:
        if self.backend != "libsql" or category not in {"stale_stream", "driver_panic"} or self._reconnect is None:
            return
        try:
            self._connection.close()
        except BaseException as exc:
            if not isinstance(exc, Exception) and transient_database_error_category(exc) is None:
                raise
            _log_cleanup_failure("stale_stream_close", exc)
        self._connection = self._reconnect()

    def _run(self, operation: str, callback: Callable[[], ResultT]) -> ResultT:
        if self.backend == "libsql" and self._transaction_depth == 0:
            return _retry_libsql_operation(
                operation,
                callback,
                before_retry=self._refresh_connection_for_retry,
            )
        return callback()

    def transaction(self, callback: Callable[[DatabaseConnection], ResultT]) -> ResultT:
        """Run and, for libSQL, replay a complete transaction after a transient driver failure."""

        if self._transaction_depth:
            return callback(self)

        def attempt() -> ResultT:
            self._transaction_depth += 1
            try:
                result = callback(self)
                self._connection.commit()
                return result
            except BaseException:
                try:
                    self._connection.rollback()
                except BaseException as cleanup_error:
                    if (
                        not isinstance(cleanup_error, Exception)
                        and transient_database_error_category(cleanup_error) is None
                    ):
                        raise
                    _log_cleanup_failure("transaction_rollback", cleanup_error)
                raise
            finally:
                self._transaction_depth -= 1

        if self.backend == "libsql":
            return _retry_libsql_operation(
                "transaction",
                attempt,
                before_retry=self._refresh_connection_for_retry,
            )
        return attempt()

    def _changes(self) -> int:
        cursor = self._run("changes", lambda: self._connection.execute("SELECT changes()"))
        row = cursor.fetchone()
        return int(row[0] if row is not None else 0)

    def execute(self, sql: str, parameters: DatabaseParameters = ()) -> DatabaseCursor:
        cursor = self._run("execute", lambda: self._connection.execute(sql, parameters))
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
        rows = list(parameter_rows)
        cursor = self._run("executemany", lambda: self._connection.executemany(sql, rows))
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

    def fetch_read_rows(
        self, sql: str, parameters: Sequence[Any] = (), *, deadline: float | None = None,
    ) -> list[DatabaseRow]:
        """Fetch a bounded SELECT in one response instead of streaming driver rows."""
        statement = sql.lstrip()
        while statement.startswith("/*"):
            statement = statement.split("*/", 1)[-1].lstrip()
        tokens = re.sub(r"'(?:''|[^'])*'|/\*.*?\*/|--[^\n]*", " ", statement, flags=re.DOTALL)
        if not statement.upper().startswith(("SELECT ", "WITH ")) or re.search(
            r"\b(INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|ATTACH|DETACH|PRAGMA)\b|\bREPLACE\s+INTO\b",
            tokens, re.IGNORECASE,
        ):
            raise ValueError("Page reads require a SELECT statement.")
        if self.backend != "libsql" or self._transaction_depth:
            return self.execute(sql, parameters).fetchall()
        target = _remote_database_url().replace("libsql://", "https://").rstrip("/")
        token = os.getenv("TURSO_AUTH_TOKEN", "").strip()
        if not target or not token:
            raise DatabaseConfigurationError("Turso page reads require database URL and auth token.")

        def parameter(value):
            if value is None:
                return {"type": "null"}
            if isinstance(value, int):
                return {"type": "integer", "value": str(value)}
            if isinstance(value, float):
                return {"type": "float", "value": value}
            return {"type": "text", "value": str(value)}

        body = {"requests": [
            {"type": "execute", "stmt": {"sql": sql, "args": [parameter(value) for value in parameters], "want_rows": True}},
            {"type": "close"},
        ]}
        request = Request(target + "/v2/pipeline", data=json.dumps(body).encode(), headers={
            "Authorization": "Bearer " + token, "Content-Type": "application/json",
        })

        def fetch():
            timeout = 15.0
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Turso read deadline exceeded")
                timeout = min(8.0, remaining)
            try:
                with urlopen(request, timeout=timeout) as response:
                    payload = json.load(response)
            except HTTPError as exc:
                raise RuntimeError(f"Turso page read HTTP {exc.code}") from None
            result = payload["results"][0]
            if result["type"] != "ok":
                code = str(result.get("error", {}).get("code", "unknown"))
                raise RuntimeError(f"Turso page read statement error: {code}")
            result = result["response"]["result"]
            columns = [column["name"] for column in result["cols"]]

            def decode(cell):
                if cell["type"] == "null":
                    return None
                if cell["type"] == "integer":
                    return int(cell["value"])
                return cell["value"]

            return [DatabaseRow(columns, [decode(cell) for cell in row]) for row in result["rows"]]

        def check_deadline(_category):
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("Turso read deadline exceeded")

        return _retry_libsql_operation("page_read", fetch, before_retry=check_deadline)

    def commit(self) -> None:
        try:
            self._connection.commit()
        except BaseException as exc:
            category = transient_database_error_category(exc)
            if category is not None:
                self._refresh_connection_for_retry(category)
            raise

    def rollback(self) -> None:
        self._run("rollback", lambda: self._connection.rollback())

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> DatabaseConnection:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        if exc_type is not None:
            primary_error = exc if isinstance(exc, BaseException) else None
            try:
                self.rollback()
            except BaseException as cleanup_error:
                _handle_cleanup_failure(
                    "rollback",
                    cleanup_error,
                    primary_error=primary_error,
                )
            try:
                self.close()
            except BaseException as cleanup_error:
                _handle_cleanup_failure(
                    "close",
                    cleanup_error,
                    primary_error=primary_error,
                )
            return False

        commit_error: BaseException | None = None
        try:
            self.commit()
        except BaseException as error:
            commit_error = error
            raise
        finally:
            try:
                self.close()
            except BaseException as cleanup_error:
                _handle_cleanup_failure(
                    "close",
                    cleanup_error,
                    primary_error=commit_error,
                )
        return False


def _remote_database_url() -> str:
    return os.getenv("TURSO_DATABASE_URL", "").strip()


def _database_backend() -> str:
    return os.getenv("DATABASE_BACKEND", "sqlite").strip().lower() or "sqlite"


def _runtime_environment() -> str:
    return os.getenv("RUNR_ENV", "development").strip().lower() or "development"


def _remote_database_required() -> bool:
    return _database_backend() == "turso"


def _local_database_path(local_path: str | Path) -> Path:
    configured = os.getenv("SQLITE_DATABASE_PATH", "").strip()
    production = _runtime_environment() in {"prod", "production"}
    if production and _database_backend() == "sqlite":
        if not configured or not Path(configured).is_absolute():
            raise DatabaseConfigurationError("Production SQLite requires an absolute SQLITE_DATABASE_PATH.")
        if _remote_database_url():
            raise DatabaseConfigurationError("Remove TURSO_DATABASE_URL when using production SQLite.")
    if configured and not Path(configured).is_absolute():
        raise DatabaseConfigurationError("SQLITE_DATABASE_PATH must be absolute.")
    return Path(configured or local_path).expanduser().resolve()


def database_target_key(local_path: str | Path) -> str:
    path = _local_database_path(local_path)
    remote_url = _remote_database_url()
    if remote_url or _remote_database_required():
        return f"libsql:{remote_url}"
    return f"sqlite:{path}"


def database_target_info(local_path: str | Path) -> dict[str, str | bool]:
    path = _local_database_path(local_path)
    remote_url = _remote_database_url()
    required_remote = _remote_database_required()
    target_backend = "libsql" if remote_url or required_remote else "sqlite"
    payload: dict[str, str | bool] = {
        "database_backend": _database_backend(),
        "runtime_environment": _runtime_environment(),
        "target_backend": target_backend,
        "remote_required": required_remote,
        "remote_configured": bool(remote_url),
    }
    if target_backend == "sqlite":
        payload["local_path"] = str(path)
    elif remote_url:
        payload["remote_url_prefix"] = remote_url.split("://", 1)[0] if "://" in remote_url else "libsql"
    return payload


def connect_database(local_path: str | Path) -> DatabaseConnection:
    """Connect to Turso when configured, otherwise preserve local sqlite3 behavior."""

    validate_release_provenance()
    path = _local_database_path(local_path)
    remote_url = _remote_database_url()
    if remote_url or _remote_database_required():
        if not remote_url:
            raise DatabaseConfigurationError(
                "TURSO_DATABASE_URL is required when DATABASE_BACKEND=turso."
            )
        auth_token = os.getenv("TURSO_AUTH_TOKEN", "").strip()
        if not auth_token:
            raise DatabaseConfigurationError(
                "TURSO_AUTH_TOKEN is required when DATABASE_BACKEND=turso or TURSO_DATABASE_URL is configured."
            )
        try:
            libsql = importlib.import_module("libsql")
        except ImportError as exc:
            raise DatabaseConfigurationError(
                "The 'libsql' package is required when TURSO_DATABASE_URL is configured."
            ) from exc
        def reconnect():
            return _retry_libsql_operation(
                "connect",
                lambda: libsql.connect(database=remote_url, auth_token=auth_token),
            )

        raw_connection = reconnect()
        connection = DatabaseConnection(raw_connection, backend="libsql", reconnect=reconnect)
    else:
        if _runtime_environment() in {"prod", "production"}:
            # Fail closed: a typo must never create an empty production database.
            raw_connection = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=30)
            try:
                mode = raw_connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
                if mode != "wal":
                    raise DatabaseConfigurationError("Production SQLite requires WAL mode.")
                raw_connection.execute("PRAGMA synchronous=FULL")
                raw_connection.execute("PRAGMA wal_autocheckpoint=1000")
                raw_connection.execute("PRAGMA journal_size_limit=67108864")
            except BaseException:
                raw_connection.close()
                raise
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            raw_connection = sqlite3.connect(path, timeout=30)
        connection = DatabaseConnection(raw_connection, backend="sqlite")

    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def database_session(local_path: str | Path) -> Iterator[DatabaseConnection]:
    connection = connect_database(local_path)
    original_error: BaseException | None = None
    try:
        yield connection
        connection.commit()
    except BaseException as error:
        original_error = error
        try:
            connection.rollback()
        except BaseException as cleanup_error:
            _handle_cleanup_failure(
                "rollback",
                cleanup_error,
                primary_error=original_error,
            )
        raise
    finally:
        try:
            connection.close()
        except BaseException as cleanup_error:
            _handle_cleanup_failure(
                "close",
                cleanup_error,
                primary_error=original_error,
            )


class _BufferedReadCursor:
    def __init__(self, rows: list[DatabaseRow]):
        self._rows = iter(rows)

    def fetchone(self) -> DatabaseRow | None:
        return next(self._rows, None)

    def fetchall(self) -> list[DatabaseRow]:
        return list(self._rows)


class _HttpReadSession:
    """Independent SELECT requests; each request closes its server stream."""

    def __init__(self, deadline: float):
        self._reader = DatabaseConnection(None, backend="libsql")
        self._deadline = deadline

    def fetch_read_rows(self, sql: str, parameters: Sequence[Any] = ()) -> list[DatabaseRow]:
        return self._reader.fetch_read_rows(sql, parameters, deadline=self._deadline)

    def execute(self, sql: str, parameters: Sequence[Any] = ()) -> _BufferedReadCursor:
        return _BufferedReadCursor(self.fetch_read_rows(sql, parameters))


@contextmanager
def database_read_session(
    local_path: str | Path, *, deadline: float | None = None,
) -> Iterator[DatabaseConnection | _HttpReadSession]:
    validate_release_provenance()
    _local_database_path(local_path)
    if _remote_database_url() or _remote_database_required():
        yield _HttpReadSession(deadline if deadline is not None else time.monotonic() + 15.0)
    else:
        with database_session(local_path) as connection:
            yield connection
