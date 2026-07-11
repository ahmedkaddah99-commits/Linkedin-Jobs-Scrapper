from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, TypeVar

from backend.database import DatabaseConnection, connect_database, database_session, initialize_database


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
        try:
            return connection.transaction(callback)
        finally:
            connection.close()
