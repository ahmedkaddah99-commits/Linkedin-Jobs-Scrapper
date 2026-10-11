# Existing catalog JSON deduplication

`scripts/deduplicate_catalog_json.py` removes exact redundant descriptions,
mapping copies and source envelope fields in the existing Turso database.
Canonical values, differing source values, row identities and hashes remain.
This operation does not create a replacement database or archive another copy.

The narrowly scoped maintenance trigger permits only the deterministic JSON
transformation, checks every other SQL column and rowid, and retains immutable
DELETE guards. Original trigger definitions are saved before installation.
Turso schema formatting is compared by SQL tokens, preserving quoted literals.
`--keep-compaction-guards` retains this restriction between resumable rounds;
the original update guard is restored when its table finishes.

The private checkpoint is bound to the database URL hash. Each batch saves its
before-size before writing. A lost response does not imply failure or success:
the remaining duplicate predicates, row count and after-size must verify before
the checkpoint advances. Confirmed savings are logical UTF-8 bytes, not a claim
of physical file or billing reduction. New rowids are included after the first
pass finishes.

The optional native transport in `reduce_catalog_storage.py` uses explicit
libSQL transactions. Remote `executescript` is deliberately avoided. This older
archive-backed reducer and exact JSON cleanup share the backfill lock and must
not execute concurrently. Existing writer compaction remains responsible for
avoiding new duplicate representations.

The service and persistent five-minute timer are in `deploy/systemd/`.
Install with an explicit committed release WorkingDirectory and Python 3.12.7.
Do not silently disable acquisition timers. Run bounded rounds and inspect
checkpoint progress and unit failures; an enabled timer alone is not evidence
of successful cleanup.

Verification: `tests/test_catalog_json_deduplication.py` covers canonical and
conflicting values, identity/hash protection, trigger restoration, schema
formatting, new insertions and lost responses after commit.
