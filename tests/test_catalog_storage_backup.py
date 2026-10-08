import gzip
import io
import sqlite3

import pytest

from scripts.catalog_storage_backup import write_compressed_dump


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
