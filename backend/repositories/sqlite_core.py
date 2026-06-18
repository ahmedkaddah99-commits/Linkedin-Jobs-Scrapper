from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from backend.database import DatabaseConnection, database_session, initialize_database


class _SqliteStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        initialize_database(self.db_path)

    @contextmanager
    def _connect(self) -> Iterator[DatabaseConnection]:
        with database_session(self.db_path) as connection:
            yield connection
