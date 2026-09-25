import os
import json
import shutil
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from backend.database import connection
from backend.database.connection import (
    DatabaseConfigurationError,
    database_session,
)
from backend.database.initialization import initialize_database
from backend.database.migrations import (
    Migration,
    MigrationChecksumError,
    get_migration_status,
    run_migrations,
)
from backend.database.schema import BASE_SCHEMA_SQL
from backend.repositories.sqlite_migrations import MIGRATIONS, current_migration_head


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

    def _migration_index(self, migration_id: str) -> int:
        for index, migration in enumerate(MIGRATIONS):
            if migration.migration_id == migration_id:
                return index
        raise AssertionError(f"Unknown migration id: {migration_id}")

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

    def test_committed_registry_preserves_migration_ids_001_through_020(self):
        self.assertEqual(
            [migration.migration_id for migration in MIGRATIONS[:20]],
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
                "013_candidate_document_normalization",
                "014_workspace_ownership",
                "015_email_sync_start_date",
                "016_assisted_apply_connections",
                "017_application_packages",
                "018_assisted_apply_corrections",
                "019_assisted_apply_document_grants",
                "020_assisted_apply_tracker_confirmation",
            ],
        )
        self.assertTrue(all(len(migration.checksum) == 64 for migration in MIGRATIONS))

    def test_registry_head_is_append_only_and_checksum_backed(self):
        migration_ids = [migration.migration_id for migration in MIGRATIONS]
        self.assertEqual(migration_ids, sorted(migration_ids))
        self.assertEqual(len(migration_ids), len(set(migration_ids)))
        self.assertEqual(current_migration_head(), "061_acquisition_publisher_checkpoints")
        self.assertTrue(all(len(migration.checksum) == 64 for migration in MIGRATIONS))

    def test_database_boundary_rejects_a_configured_head_older_than_the_registry(self):
        with patch.dict(os.environ, {"RUNR_MIGRATION_HEAD": "058_customer_task_queue"}, clear=True):
            with self.assertRaisesRegex(DatabaseConfigurationError, "migration head"):
                connection.connect_database(self._db_path("incompatible_migration_head"))

    def test_workspace_ownership_migration_backfills_from_the_single_run_owner(self):
        db_path = self._db_path("workspace_ownership_backfill")
        user_id = "user_existing_owner"
        workspace_id = "workspace_existing_owner"

        with closing(sqlite3.connect(db_path)) as connection:
            connection.executescript(BASE_SCHEMA_SQL)
            connection.executemany(
                "INSERT INTO schema_migrations (migration_id, applied_at, checksum) VALUES (?, ?, ?)",
                [
                    (migration.migration_id, "2026-01-01T00:00:00+00:00", migration.checksum)
                    for migration in MIGRATIONS[: self._migration_index("014_workspace_ownership")]
                ],
            )
            connection.execute(
                "INSERT INTO workflow_templates (id, name, description, payload_json, updated_at) "
                "VALUES (?, ?, '', ?, ?)",
                (
                    "workflow_existing_owner",
                    "Existing workflow",
                    json.dumps(
                        {
                            "id": "workflow_existing_owner",
                            "name": "Existing workflow",
                            "stages": [],
                        }
                    ),
                    "2026-01-01T00:00:00+00:00",
                ),
            )
            connection.execute(
                "INSERT INTO users (user_id, email, role, is_active, updated_at, payload_json) "
                "VALUES (?, ?, 'viewer', 1, ?, ?)",
                (
                    user_id,
                    "existing-owner@example.com",
                    "2026-01-01T00:00:00+00:00",
                    json.dumps(
                        {
                            "user_id": user_id,
                            "email": "existing-owner@example.com",
                            "role": "viewer",
                            "is_active": True,
                        }
                    ),
                ),
            )
            connection.execute(
                "INSERT INTO workspaces "
                "(id, name, workflow_template_id, workspace_type, payload_json, updated_at) "
                "VALUES (?, ?, ?, 'custom', ?, ?)",
                (
                    workspace_id,
                    "Existing workspace",
                    "workflow_existing_owner",
                    json.dumps(
                        {
                            "id": workspace_id,
                            "name": "Existing workspace",
                            "workflow_template_id": "workflow_existing_owner",
                            "workspace_type": "custom",
                        }
                    ),
                    "2026-01-01T00:00:00+00:00",
                ),
            )
            connection.execute(
                "INSERT INTO runs "
                "(id, workspace_id, workflow_template_id, status, requested_by, user_id, "
                "created_at, updated_at, payload_json) "
                "VALUES (?, ?, ?, 'completed', ?, ?, ?, ?, ?)",
                (
                    "run_existing_owner",
                    workspace_id,
                    "workflow_existing_owner",
                    f"api:{user_id}",
                    user_id,
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                    json.dumps(
                        {
                            "id": "run_existing_owner",
                            "workspace_id": workspace_id,
                            "workflow_template_id": "workflow_existing_owner",
                            "status": "completed",
                            "requested_by": f"api:{user_id}",
                            "user_id": user_id,
                        }
                    ),
                ),
            )
            connection.commit()

        with patch.dict(
            os.environ,
            {
                "TURSO_DATABASE_URL": "",
                "TURSO_AUTH_TOKEN": "",
                "DATABASE_BACKEND": "sqlite",
                "RUNR_ENV": "development",
            },
        ):
            initialize_database(db_path, force=True)

        with closing(sqlite3.connect(db_path)) as connection:
            workspace_row = connection.execute(
                "SELECT owner_user_id, payload_json FROM workspaces WHERE id = ?",
                (workspace_id,),
            ).fetchone()

        self.assertEqual(workspace_row[0], user_id)
        self.assertEqual(json.loads(workspace_row[1])["owner_user_id"], user_id)

    def test_candidate_document_migration_extracts_legacy_aggregate_text(self):
        db_path = self._db_path("candidate_document_legacy_migration")
        private_cv = "Legacy Private CV\nlegacy@example.com"
        user_payload = {
            "user_id": "user_legacy_cv",
            "email": "legacy@example.com",
            "role": "viewer",
            "is_active": True,
            "metadata": {
                "cv_text": private_cv,
                "candidate_assets": [
                    {
                        "asset_id": "asset_legacy_cv",
                        "asset_kind": "workspace_cv",
                        "display_name": "Legacy CV.pdf",
                        "file": {"object_key": "users/user_legacy_cv/workspace_cv/asset_legacy_cv/cv.pdf"},
                        "metadata": {"source_text": private_cv},
                    }
                ],
            },
        }
        workspace_payload = {
            "id": "workspace_legacy_cv",
            "name": "Legacy CV workspace",
            "workflow_template_id": "workflow_legacy_cv",
            "settings": {
                "workspace_cv_asset_id": "asset_legacy_cv",
                "workspace_cv_text": private_cv,
            },
        }

        with closing(sqlite3.connect(db_path)) as connection:
            connection.executescript(BASE_SCHEMA_SQL)
            connection.executemany(
                "INSERT INTO schema_migrations (migration_id, applied_at, checksum) VALUES (?, ?, ?)",
                [
                    (migration.migration_id, "2026-01-01T00:00:00+00:00", migration.checksum)
                    for migration in MIGRATIONS[: self._migration_index("013_candidate_document_normalization")]
                ],
            )
            connection.execute(
                "INSERT INTO users (user_id, email, role, is_active, updated_at, payload_json) "
                "VALUES (?, ?, 'viewer', 1, ?, ?)",
                (
                    "user_legacy_cv",
                    "legacy@example.com",
                    "2026-01-01T00:00:00+00:00",
                    json.dumps(user_payload),
                ),
            )
            connection.execute(
                "INSERT INTO workspaces "
                "(id, name, workflow_template_id, workspace_type, payload_json, updated_at) "
                "VALUES (?, ?, ?, '', ?, ?)",
                (
                    "workspace_legacy_cv",
                    "Legacy CV workspace",
                    "workflow_legacy_cv",
                    json.dumps(workspace_payload),
                    "2026-01-01T00:00:00+00:00",
                ),
            )
            connection.commit()

        with patch.dict(
            os.environ,
            {
                "TURSO_DATABASE_URL": " ",
                "TURSO_AUTH_TOKEN": " ",
                "DATABASE_BACKEND": "sqlite",
                "RUNR_ENV": "development",
            },
        ):
            initialize_database(db_path, force=True)

        with closing(sqlite3.connect(db_path)) as connection:
            raw_user = connection.execute(
                "SELECT payload_json FROM users WHERE user_id = 'user_legacy_cv'"
            ).fetchone()[0]
            raw_workspace = connection.execute(
                "SELECT payload_json FROM workspaces WHERE id = 'workspace_legacy_cv'"
            ).fetchone()[0]
            document = connection.execute(
                "SELECT source_text FROM candidate_documents WHERE asset_id = 'asset_legacy_cv'"
            ).fetchone()
            asset = connection.execute(
                "SELECT object_key FROM candidate_assets WHERE asset_id = 'asset_legacy_cv'"
            ).fetchone()

        self.assertNotIn(private_cv, raw_user)
        self.assertNotIn(private_cv, raw_workspace)
        self.assertEqual(document, (private_cv,))
        self.assertEqual(asset, ("users/user_legacy_cv/workspace_cv/asset_legacy_cv/cv.pdf",))


    def test_publisher_checkpoint_table_exists_after_fresh_initialization(self):
        db_path = self._db_path("publisher_checkpoint_fresh")

        with self._local_environment():
            initialize_database(db_path, force=True)

        with closing(sqlite3.connect(db_path)) as connection:
            columns = {
                row[1]: row
                for row in connection.execute(
                    "PRAGMA table_info(acquisition_publisher_checkpoints)"
                ).fetchall()
            }
            applied = connection.execute(
                "SELECT checksum FROM schema_migrations WHERE migration_id = '061_acquisition_publisher_checkpoints'"
            ).fetchone()

        self.assertEqual(
            set(columns),
            {
                "source",
                "source_rowid",
                "source_watermark",
                "bootstrap_complete",
                "last_cycle_id",
                "last_publication_id",
                "updated_at",
            },
        )
        self.assertEqual(columns["source"][5], 1, "source must be the primary key")
        self.assertIsNotNone(applied)
        self.assertEqual(len(str(applied[0])), 64)

    def test_publisher_checkpoint_upgrade_path_creates_missing_table(self):
        db_path = self._db_path("publisher_checkpoint_upgrade_missing")
        with closing(sqlite3.connect(db_path)) as connection:
            connection.executescript(BASE_SCHEMA_SQL)
            connection.executemany(
                "INSERT INTO schema_migrations (migration_id, applied_at, checksum) VALUES (?, ?, ?)",
                [
                    (migration.migration_id, "2026-01-01T00:00:00+00:00", migration.checksum)
                    for migration in MIGRATIONS[: self._migration_index("061_acquisition_publisher_checkpoints")]
                ],
            )
            connection.commit()

        with self._local_environment():
            initialize_database(db_path, force=True)

        with closing(sqlite3.connect(db_path)) as connection:
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='acquisition_publisher_checkpoints'"
            ).fetchone()
            applied_ids = [
                row[0]
                for row in connection.execute(
                    "SELECT migration_id FROM schema_migrations ORDER BY migration_id"
                ).fetchall()
            ]

        self.assertIsNotNone(table)
        self.assertEqual(applied_ids, [migration.migration_id for migration in MIGRATIONS])

    def test_publisher_checkpoint_migration_preserves_preexisting_ad_hoc_table(self):
        db_path = self._db_path("publisher_checkpoint_upgrade_existing")
        with closing(sqlite3.connect(db_path)) as connection:
            connection.executescript(BASE_SCHEMA_SQL)
            connection.executemany(
                "INSERT INTO schema_migrations (migration_id, applied_at, checksum) VALUES (?, ?, ?)",
                [
                    (migration.migration_id, "2026-01-01T00:00:00+00:00", migration.checksum)
                    for migration in MIGRATIONS[: self._migration_index("061_acquisition_publisher_checkpoints")]
                ],
            )
            connection.execute(
                """
                CREATE TABLE acquisition_publisher_checkpoints (
                    source TEXT PRIMARY KEY,
                    source_rowid INTEGER NOT NULL DEFAULT 0,
                    source_watermark TEXT NOT NULL DEFAULT '',
                    bootstrap_complete INTEGER NOT NULL DEFAULT 0,
                    last_cycle_id TEXT NOT NULL DEFAULT '',
                    last_publication_id TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "INSERT INTO acquisition_publisher_checkpoints "
                "(source, source_rowid, source_watermark, bootstrap_complete, last_cycle_id, last_publication_id, updated_at) "
                "VALUES ('linkedin', 42, '2026-09-10T00:00:00Z', 1, 'cycle-1', 'publication-1', '2026-09-10T00:00:00Z')"
            )
            connection.commit()

        with self._local_environment():
            initialize_database(db_path, force=True)

        with closing(sqlite3.connect(db_path)) as connection:
            rows = connection.execute(
                "SELECT source, source_rowid, bootstrap_complete, last_cycle_id "
                "FROM acquisition_publisher_checkpoints WHERE source='linkedin'"
            ).fetchall()

        self.assertEqual(rows, [("linkedin", 42, 1, "cycle-1")])


if __name__ == "__main__":
    unittest.main()
