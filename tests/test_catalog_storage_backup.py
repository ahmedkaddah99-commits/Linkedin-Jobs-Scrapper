import gzip
import io
import sqlite3

import pytest

from scripts.catalog_storage_backup import write_compressed_dump, restore_compressed_dump


def test_streamed_backup_restores_sqlite_data(tmp_path):
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE original(id INTEGER PRIMARY KEY,body TEXT)')
    db.execute('INSERT INTO original VALUES(1,?)', ('Unique source evidence',))
    body = ('\n'.join(db.iterdump())+'\n').encode()
    destination = tmp_path/'backup.sql.gz'
    receipt = write_compressed_dump(io.BytesIO(body), destination)
    restored = sqlite3.connect(':memory:')
    restored.executescript(gzip.decompress(destination.read_bytes()).decode())
    assert restored.execute('SELECT body FROM original').fetchone()[0] == 'Unique source evidence'
    assert receipt['sql_bytes'] == len(body)
    assert len(receipt['sha256']) == 64


def test_incomplete_backup_does_not_claim_success_or_replace_existing(tmp_path):
    destination = tmp_path/'backup.sql.gz'
    with pytest.raises(ValueError, match='Incomplete'):
        write_compressed_dump(io.BytesIO(b'BEGIN TRANSACTION;\nCREATE TABLE x(id);'), destination)
    assert not destination.exists()
    assert destination.with_suffix('.gz.part').exists()


def test_turso_virtual_table_export_restores_seeded_fts_rows(tmp_path):
    db = sqlite3.connect(':memory:')
    db.execute('CREATE VIRTUAL TABLE search USING fts5(body)')
    db.execute("INSERT INTO search VALUES('retained unique evidence')")
    db.commit()
    sql = ['BEGIN;', 'CREATE VIRTUAL TABLE search USING fts5(body);']
    for name, schema in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name LIKE 'search_%'"):
        sql.append(schema.replace('CREATE TABLE', 'CREATE TABLE IF NOT EXISTS', 1) + ';')
        for row in db.execute('SELECT * FROM ' + name):
            values = ','.join(db.execute('SELECT quote(?)', (value,)).fetchone()[0] for value in row)
            sql.append(f'INSERT INTO "{name}" VALUES ({values});')
    sql.append('COMMIT;')
    source, destination = tmp_path/'fts.sql.gz', tmp_path/'restored.sqlite3'
    body = ('\n'.join(sql)+'\n').encode()
    write_compressed_dump(io.BytesIO(body), source)
    receipt = restore_compressed_dump(source, destination, expected_sql_bytes=len(body))
    with sqlite3.connect(destination) as restored:
        assert restored.execute("SELECT body FROM search WHERE search MATCH 'unique'").fetchall() == [('retained unique evidence',)]
    assert receipt['quick_check'] == 'ok'
    with pytest.raises(FileExistsError):
        restore_compressed_dump(source, destination)
