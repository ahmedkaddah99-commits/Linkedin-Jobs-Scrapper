# Frozen producer catch-up

The dedicated runner takes one consistent pair of producer snapshots under the
collector locks, then releases those locks. It reuses the snapshots across
bounded delivery batches. Checkpoints cannot advance beyond capture time, so
later observations remain available to normal incremental delivery. Snapshot
hashes and frozen manifest/crosswalk inputs are retained.

`scripts/run_producer_catchup.py` uses the existing publisher lock for the frozen
delivery window. Other publication writers defer during this bounded operation;
collectors and enrichment continue. Narrowing this lock to the final transaction
requires a separate ingestion/concurrency audit. Resume fails closed if another
publisher changed checkpoints. Interrupted captures require inspection and a new
operation directory. No source or catalog data is deleted.

Operation evidence: `snapshot.json`, `expected-checkpoints.json`, `rounds.jsonl`,
`round-latest.log`, and atomic `status.json`. Source delivery completes when both
bootstrap flags and watermarks reach capture time. Empty final scans now persist
their checkpoint, including exact multiples of the batch limit.

`scripts/audit_producer_catchup.py` maintains a SQLite ledger keyed by source and
original rowid, retaining target/external identity and outcome. Indexed identity
joins use compact projections. Unknown identities/eligibility remain review
states. Current-head membership is `published_requires_app_check`, never verified
customer readiness. Rerun the audit to refresh outcomes; source rows are not
unique jobs.

Provider budgets and memory caps stay unchanged pending measured evidence.
Producer change-event transport, publication critical-section redesign and
evidence-based enrichment repairs are not implemented by this release.

Verification covers producer delivery, publication recovery, persistence,
snapshot checkpoint fencing, exact-size bootstrap completion and outcome audit.
Live release evidence will be appended after the canary.
