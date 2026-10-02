from __future__ import annotations

import sqlite3

from scripts.snapshot_producer_states import snapshot_database


def test_snapshot_database_is_stable_after_source_changes(tmp_path):
    source = tmp_path / "source.db"
    destination = tmp_path / "snapshot.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY, title TEXT)")
        connection.execute("INSERT INTO jobs (title) VALUES ('first')")

    receipt = snapshot_database(source, destination)
    with sqlite3.connect(source) as connection:
        connection.execute("INSERT INTO jobs (title) VALUES ('second')")

    with sqlite3.connect(destination) as connection:
        titles = [row[0] for row in connection.execute("SELECT title FROM jobs ORDER BY id")]
        integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
    assert titles == ["first"]
    assert integrity == "ok"
    assert receipt["source_bytes"] > 0
    assert receipt["snapshot_bytes"] > 0
