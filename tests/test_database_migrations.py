import os
import shutil
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from backend.database.connection import database_session
from backend.database.initialization import initialize_database
from backend.database.migrations import (
    Migration,
    MigrationChecksumError,
    get_migration_status,
    run_migrations,
)
from backend.repositories.sqlite_migrations import MIGRATIONS


class DatabaseMigrationTests(unittest.TestCase):
    def _db_path(self, name: str) -> Path:
        path = Path.cwd() / ".backend_test_tmp" / name / "backend.sqlite3"
        if path.parent.exists():
            shutil.rmtree(path.parent, ignore_errors=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(path.parent, ignore_errors=True))
        return path

    def _local_environment(self):
        return patch.dict(
            os.environ,
            {"TURSO_DATABASE_URL": "", "TURSO_AUTH_TOKEN": ""},
        )

    def test_runner_applies_migrations_once_and_reports_checksums(self):
        db_path = self._db_path("database_migrations_repeatable")
        calls: list[str] = []

        def apply_first(connection):
            calls.append("first")
            connection.execute("CREATE TABLE first_table (id INTEGER PRIMARY KEY)")

        def apply_second(connection):
            calls.append("second")
            connection.execute("CREATE TABLE second_table (id INTEGER PRIMARY KEY)")

        migrations = (
            Migration.from_callable("001_first", "Create first table.", apply_first),
            Migration.from_callable("002_second", "Create second table.", apply_second),
        )

        with self._local_environment():
            with database_session(db_path) as connection:
                first_run = run_migrations(connection, migrations)
            with database_session(db_path) as connection:
                second_run = run_migrations(connection, migrations)
                statuses = get_migration_status(connection, migrations)
                rows = connection.execute(
                    "SELECT migration_id, checksum FROM schema_migrations ORDER BY migration_id"
                ).fetchall()

        self.assertEqual(first_run, ["001_first", "002_second"])
        self.assertEqual(second_run, [])
        self.assertEqual(calls, ["first", "second"])
        self.assertEqual([status.state for status in statuses], ["applied", "applied"])
        self.assertEqual([row["migration_id"] for row in rows], ["001_first", "002_second"])
        self.assertTrue(all(len(str(row["checksum"])) == 64 for row in rows))

    def test_runner_rejects_changed_applied_migration(self):
        db_path = self._db_path("database_migrations_checksum_mismatch")

        def apply_migration(connection):
            connection.execute("CREATE TABLE records (id INTEGER PRIMARY KEY)")

        migration = Migration.from_callable(
            "001_records",
            "Create records.",
            apply_migration,
        )
        changed_migration = Migration(
            migration_id=migration.migration_id,
            description=migration.description,
            apply=migration.apply,
            checksum="0" * 64,
        )

        with self._local_environment():
            with database_session(db_path) as connection:
                run_migrations(connection, (migration,))
            with database_session(db_path) as connection:
                with self.assertRaisesRegex(
                    MigrationChecksumError,
                    "001_records",
                ):
                    run_migrations(connection, (changed_migration,))

    def test_existing_two_column_migration_table_is_upgraded_without_rerunning_rows(self):
        db_path = self._db_path("database_migrations_legacy_table")
        with closing(sqlite3.connect(db_path)) as connection:
            connection.executescript(
                """
                CREATE TABLE schema_migrations (
                    migration_id TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                INSERT INTO schema_migrations (migration_id, applied_at) VALUES
                    ('001_runtime_normalization', '2026-01-01T00:00:00+00:00'),
                    ('002_analytics_events', '2026-01-01T00:00:00+00:00'),
                    ('003_application_status_history', '2026-01-01T00:00:00+00:00');
                """
            )
            connection.commit()

        with self._local_environment():
            initialize_database(db_path, force=True)

        with closing(sqlite3.connect(db_path)) as connection:
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(schema_migrations)").fetchall()
            }
            rows = connection.execute(
                "SELECT migration_id, checksum FROM schema_migrations ORDER BY migration_id"
            ).fetchall()

        self.assertIn("checksum", columns)
        self.assertEqual([row[0] for row in rows], [migration.migration_id for migration in MIGRATIONS])
        self.assertTrue(all(len(str(row[1])) == 64 for row in rows))

    def test_committed_registry_preserves_migration_ids_001_through_012(self):
        self.assertEqual(
            [migration.migration_id for migration in MIGRATIONS],
            [
                "001_runtime_normalization",
                "002_analytics_events",
                "003_application_status_history",
                "004_runs_user_id",
                "005_billing",
                "006_app_config",
                "007_scrapeops_usage_ledger",
                "008_site_source_policy",
                "009_site_job_url_history",
                "010_site_job_url_history_workspace_scope",
                "011_site_job_url_history_public_index",
                "012_creem_billing",
            ],
        )
        self.assertTrue(all(len(migration.checksum) == 64 for migration in MIGRATIONS))


if __name__ == "__main__":
    unittest.main()
