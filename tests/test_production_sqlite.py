from pathlib import Path
import sqlite3
from types import SimpleNamespace
import pytest
from backend.database.connection import connect_database, database_target_key, database_target_info, DatabaseConfigurationError
from backend.config.env_schema import validate_environment, EnvironmentValidationError

@pytest.fixture
def production_sqlite(monkeypatch, tmp_path):
    path = tmp_path / 'shared.sqlite3'
    sqlite3.connect(path).close()
    values = {'RUNR_ENV':'production','DATABASE_BACKEND':'sqlite','SQLITE_DATABASE_PATH':str(path), 'TURSO_DATABASE_URL':'','TURSO_AUTH_TOKEN':'', 'OBJECT_STORAGE_BACKEND':'r2', 'S3_ENDPOINT_URL':'https://example.invalid', 'S3_ACCESS_KEY_ID':'test', 'S3_SECRET_ACCESS_KEY':'test', 'S3_BUCKET':'test', 'RUNR_ASSISTED_APPLY_EXTENSION_ORIGINS':'chrome-extension://'+'a'*32}
    for k,v in values.items(): monkeypatch.setenv(k,v)
    return path, values

def test_roles_share_database_and_isolate_uncommitted_writes(production_sqlite, tmp_path):
    path, values = production_sqlite
    validate_environment(values)
    with connect_database(tmp_path/'api.sqlite3') as api:
        api.execute('CREATE TABLE records(value TEXT)')
        api.commit()
        with connect_database(tmp_path/'worker.sqlite3') as worker:
            api.execute("INSERT INTO records VALUES ('shared')")
            assert worker.execute('SELECT count(*) FROM records').fetchone()[0] == 0
            api.commit()
            assert worker.execute('SELECT value FROM records').fetchone()[0] == 'shared'
            assert worker.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
            assert worker.execute('PRAGMA synchronous').fetchone()[0] == 2
            assert worker.execute('PRAGMA foreign_keys').fetchone()[0] == 1
    assert not (tmp_path/'api.sqlite3').exists()
    assert database_target_key(tmp_path/'api.sqlite3') == database_target_key(tmp_path/'worker.sqlite3')
    assert database_target_info(tmp_path/'api.sqlite3')['local_path'] == str(path.resolve())

@pytest.mark.parametrize('value', ['', 'relative.sqlite3'])
def test_production_rejects_missing_or_relative_path(production_sqlite, monkeypatch, value):
    _, values = production_sqlite
    values['SQLITE_DATABASE_PATH'] = value
    monkeypatch.setenv('SQLITE_DATABASE_PATH',value)
    with pytest.raises(EnvironmentValidationError, match='SQLITE_DATABASE_PATH'): validate_environment(values)
    with pytest.raises(DatabaseConfigurationError, match='SQLITE_DATABASE_PATH'): connect_database('fallback.sqlite3')

def test_production_does_not_create_empty_database(production_sqlite, monkeypatch, tmp_path):
    path=tmp_path/'missing.sqlite3'
    monkeypatch.setenv('SQLITE_DATABASE_PATH',str(path))
    with pytest.raises((DatabaseConfigurationError,sqlite3.OperationalError)): connect_database('fallback.sqlite3')
    assert not path.exists()

def test_production_rejects_conflicting_remote_target(production_sqlite, monkeypatch):
    _, values=production_sqlite
    values['TURSO_DATABASE_URL']='libsql://example.invalid'
    monkeypatch.setenv('TURSO_DATABASE_URL',values['TURSO_DATABASE_URL'])
    with pytest.raises(EnvironmentValidationError, match='TURSO_DATABASE_URL'): validate_environment(values)
    with pytest.raises(DatabaseConfigurationError, match='TURSO_DATABASE_URL'): connect_database('fallback.sqlite3')

def test_production_readiness_accepts_verified_sqlite(production_sqlite):
    from backend.api.routes.system import _get_readiness
    path,_=production_sqlite
    class Store:
        db_path=path
        def query_rows(self,sql):
            with connect_database(path) as c: return [dict(r) for r in c.execute(sql).fetchall()]
    payloads=[]
    context=SimpleNamespace(application=SimpleNamespace(repositories=SimpleNamespace(analytics_store=Store()),object_storage=object()),query={},send_json=payloads.append)
    _get_readiness(context)
    assert payloads[0]['status']=='ready'
    assert payloads[0]['database']['target_backend']=='sqlite'

def test_read_session_rejects_conflicting_remote_target(production_sqlite, monkeypatch):
    from backend.database.connection import database_read_session
    monkeypatch.setenv('TURSO_DATABASE_URL','libsql://example.invalid')
    with pytest.raises(DatabaseConfigurationError, match='TURSO_DATABASE_URL'):
        with database_read_session('fallback.sqlite3'):
            pytest.fail('must not open remote reader')
