from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, TypeVar

from backend.database import DatabaseConnection, connect_database, database_session, initialize_database
from backend.database.connection import _handle_cleanup_failure


TransactionResultT = TypeVar("TransactionResultT")


class _SqliteStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._active_transaction_connection: DatabaseConnection | None = None
        initialize_database(self.db_path)

    @contextmanager
    def _connect(self) -> Iterator[DatabaseConnection]:
        if self._active_transaction_connection is not None:
            yield self._active_transaction_connection
            return
        with database_session(self.db_path) as connection:
            yield connection

    @contextmanager
    def transaction_scope(self) -> Iterator[DatabaseConnection]:
        """Share one transaction across a bounded group of store operations.

        The normal repository methods intentionally open and commit their own
        transactions. Long-running producer delivery over Turso needs a small
        bounded scope so one target does not require multiple network round
        trips while preserving rollback and lease behavior at the batch level.
        """

        if self._active_transaction_connection is not None:
            yield self._active_transaction_connection
            return
        connection = connect_database(self.db_path)
        self._active_transaction_connection = connection
        primary_error: BaseException | None = None
        try:
            yield connection
            connection.commit()
        except BaseException as error:
            primary_error = error
            try:
                connection.rollback()
            except BaseException as cleanup_error:
                _handle_cleanup_failure(
                    "transaction_scope_rollback",
                    cleanup_error,
                    primary_error=primary_error,
                )
            raise
        finally:
            self._active_transaction_connection = None
            try:
                connection.close()
            except BaseException as cleanup_error:
                _handle_cleanup_failure(
                    "transaction_scope_close",
                    cleanup_error,
                    primary_error=primary_error,
                )

    def _run_transaction(
        self,
        callback: Callable[[DatabaseConnection], TransactionResultT],
    ) -> TransactionResultT:
        if self._active_transaction_connection is not None:
            return callback(self._active_transaction_connection)
        connection = connect_database(self.db_path)
        primary_error: BaseException | None = None
        try:
            return connection.transaction(callback)
        except BaseException as error:
            primary_error = error
            raise
        finally:
            try:
                connection.close()
            except BaseException as cleanup_error:
                _handle_cleanup_failure(
                    "transaction_close",
                    cleanup_error,
                    primary_error=primary_error,
                )
