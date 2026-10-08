# Catalog storage reduction — live progress

Status recorded 2026-10-08 17:26 UTC. This is an incomplete maintenance operation, not a completion report.

Implementation and producer prevention are committed and synced through `698698115da44b98dcaae9382ba330ff702abf55`. VPS source and publisher units point to that exact release. The API still serves its preceding release; new API deployment is postponed until the controlled migration finishes. Render reports the worker's `69869811` deploy as live, but runtime logs show it is rejecting the old release-commit environment snapshot. It is not healthy and must be redeployed with the corrected settings. The frontend is live at `5d34149b`, which includes the concurrent frontend changes and the same frontend code used by this storage release.

## Recoverability

The pre-maintenance SQL export is `/srv/runr/backups/catalog-storage-20261008/before.sql.gz`. Its receipt records 35,789,423,816 SQL bytes and 4,046,598,196 compressed bytes. SHA-256: `29d32d776e7e60ee78745c00f63f16efb334b1c402caae0b412931dce19a0864`. Compression integrity verification completed successfully. A private R2 copy under `private/catalog/backups/<database_identity>/<sha256>/before.sql.gz` passed full 4.04 GB readback and SHA-256 verification; the durable receipt is `offhost-verified.json` beside the VPS export. An isolated full restore is in progress and has processed 29 GB successfully. Its first attempt hit the 512 MB process memory cap; the retry disables prepared-statement caching and is bounded to 1 GB. A successful full restore and integrity check are not yet claimed.

Original evidence is uploaded to private, compressed, content-addressed R2 objects and read back before SQL copies are removed. Historical updates preserve identifiers, dates, semantic hashes, and exact immutability trigger definitions. Checkpoint advancement follows verification; ambiguous HTTP timeouts are retried rather than assumed to have rolled back.

## Incomplete live work

- Migration 075 has verified the publication, rejection, version-reference, provenance-reference, rule-output-reference, and relationship indexes. It is building the source-history index. Its migration record must be verified after all statements finish. Long index requests have required controlled retries; fresh SQL write probes and runtime checks distinguish progress from stale client waits.
- Historical backfill has verified the first 120 source-observation rows. Bulk observations, versions, normalization outputs, quality reports, and optional paid-intelligence alias compaction remain.
- Retention has not yet cleared the large historical publication, membership, rejection, and empty-provenance backlogs.
- Source-history pruning is conservatively blocked by two August replay runs still marked failed/incomplete. Their cancellation requires an actual response to the pending recovery decision.
- Physical storage reclamation has not been performed. Logical JSON reduction and free pages must not be reported as a reduction of allocated or billed storage.
- A platform-level Turso token is unavailable for a compact replacement database if in-place reclamation is unsupported. The existing database token does not provide account administration.
- Expiration of unreferenced cold objects remains unimplemented; blanket expiration of the evidence prefix would destroy referenced evidence.

Collector and backup timers remain enabled. The publisher is temporarily excluded by a bounded maintenance lock while indexes are built; the current window expires at 17:39 UTC and publication health must be rechecked afterward.

## Local validation

The full suite before the final liveness change completed with 2,417 passed, 26 failed, and one skipped. Two inline-evidence assertions have since been updated to verify restoration from the archive. All 53 focused storage, backup, migration, retention, writer, and observation-contract tests pass, including unchanged last-seen refreshes and genuine description changes. Five failures in role-feed, intelligence recovery, producer apply type, and browser traversal reproduce at the preceding deployment `b28362af`; seven retention-timer/benchmark failures also reproduce there. The full-suite benchmark CPU assertion differs under the isolated baseline run, so the entire remaining failure set is not classified as pre-existing.

No final database-size reduction is claimed by this progress record.
