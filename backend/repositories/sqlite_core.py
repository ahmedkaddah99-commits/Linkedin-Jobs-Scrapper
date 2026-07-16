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
        initialize_database(self.db_path)

    @contextmanager
    def _connect(self) -> Iterator[DatabaseConnection]:
        with database_session(self.db_path) as connection:
            yield connection

    def _run_transaction(
        self,
        callback: Callable[[DatabaseConnection], TransactionResultT],
    ) -> TransactionResultT:
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
