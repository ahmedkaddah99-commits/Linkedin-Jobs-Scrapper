from backend.database.connection import connect_database
from backend.repositories.sqlite_acquisition import SqliteAcquisitionStore
from backend.repositories.sqlite_migrations import current_migration_head


def test_retention_migration_owns_checkpoint_and_removes_retired_fts(tmp_path):
    path = tmp_path / 'catalog.db'
    SqliteAcquisitionStore(path)
    with connect_database(path) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name='runr_catalog_storage_maintenance'").fetchone()
        assert not db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'published_job_search_%' AND name!='published_job_search_backfill'").fetchall()
        indexes = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert 'idx_acquisition_job_rejections_observed_at' in indexes
    assert current_migration_head() == '075_catalog_storage_retention'
