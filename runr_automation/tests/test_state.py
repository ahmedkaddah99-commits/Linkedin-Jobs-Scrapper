from pathlib import Path

from runr_automation.state import StateStore


def test_state_store_initializes_durable_schema(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")

    with store.connect() as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        migration = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
        ).fetchone()
        assert migration[0] == 2

        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "issues",
            "events",
            "jobs",
            "attempts",
            "checkpoints",
            "dependency_edges",
            "waves",
            "approvals",
            "provider_circuits",
            "locks",
            "migrations",
            "controller_state",
        } <= tables
