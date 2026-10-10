# VPS shared SQLite deployment

Production supports Turso or one existing local SQLite database. For the VPS set
`RUNR_ENV=production`, `DATABASE_BACKEND=sqlite`, and an absolute
`SQLITE_DATABASE_PATH` shared by API, customer worker, and any future publisher.
Remove `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` from these services. R2 remains
required. Role-specific RUNR_DATA_DIR values remain separate for caches and logs.

The database file must exist: connections use mode=rw and never create an empty
production database. Connections enable WAL, synchronous=FULL, foreign keys,
a 30-second busy timeout, 1,000-page auto-checkpoint, and 64 MiB retained journal
limit. That limit does not bound an active WAL; long readers and bulk writes can
still grow it. Monitor free disk and WAL bytes, and bound acquisition batches.

Use a SQLite runtime with the upstream WAL-reset fix (3.51.3 or later, or a
verified backport). The Oct 10 VPS candidate pins SQLite 3.54.0 through a
service-only LD_LIBRARY_PATH; system Python/SQLite and acquisition are unchanged.
Python remains 3.12.7. Official source/archive SHA3 hashes were verified and FTS5
was exercised before use. Source: https://sqlite.org/wal.html and
https://sqlite.org/releaselog/3_54_0.html.

This deployment retains the existing SQLite schema and query semantics.
PostgreSQL would require a separate compatibility migration. The libSQL server
rehearsal was rejected because restoring this 33.9 GB file generated a full-size
replication log, undermining the VPS storage requirement.

Keep all writers frozen for final reconciliation. Apply migrations once before
starting services. Do not copy a live database file: use SQLite's backup API or
a consistent SQL export, upload off-host, and verify a restore/checksum before
retiring the previous backup. Keep one bounded local recovery generation, with
historical backups in object storage. The candidate is not the live authority
until Render writers stop, final data is reconciled, and traffic switches.

Tests cover shared paths, transaction isolation, WAL durability settings,
missing-file protection, invalid configuration, and production readiness.
