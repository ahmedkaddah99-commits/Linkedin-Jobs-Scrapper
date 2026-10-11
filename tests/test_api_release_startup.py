from pathlib import Path
from unittest.mock import patch

from backend.bootstrap import _build_repositories


def test_release_startup_can_reuse_schema_applied_by_predeploy(tmp_path: Path) -> None:
    db_path = tmp_path / "backend.sqlite3"
    with (
        patch("backend.bootstrap.initialize_database") as bootstrap_initialize,
        patch("backend.repositories.sqlite_core.initialize_database") as store_initialize,
        patch.object(
            __import__("backend.repositories.sqlite_backed", fromlist=["SqliteWorkspaceRepository"]).SqliteWorkspaceRepository,
            "_ensure_seed_data",
        ),
    ):
        repositories = _build_repositories(
            tmp_path,
            storage_backend="sqlite",
            initialize_schema=False,
        )

    bootstrap_initialize.assert_not_called()
    store_initialize.assert_not_called()
    assert repositories.personalized_jobs_store.db_path == db_path
