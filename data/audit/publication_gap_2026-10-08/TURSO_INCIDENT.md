# Provider incident: intermittent database storage divergence

Prepared for review; not sent.

The shared Runr catalog intermittently rejects or stalls writes, preventing a publication backlog from draining. On 2026-10-09 around 00:30 UTC, both a native libSQL read-only query-plan probe and an atomic HTTP write batch returned `SQLITE_IOERR`. The native response was:

`SQLite error: request interrupted because local diskless state diverged from S3`

Ordinary bounded HTTP reads generally complete in approximately 0.15 seconds; a 200-job publication candidate query takes 2–4 seconds. An idempotent no-op UPDATE timed out after 15 seconds. Publication writes alternate between successful batches and prolonged waits or timeout. The issue reproduces through both native libSQL and the Hrana HTTP pipeline.

The atomic HTTP batch acquires `BEGIN IMMEDIATE`, verifies prepared head/job revisions, writes publication membership, snapshot, queue outcomes and audit, and commits; failed steps conditionally roll back. Successful batches have matching snapshot and membership counts. No catalog recreation, restore, or destructive database operation was performed.

Please investigate the diskless primary/replica storage state and S3 divergence for the affected database, restore healthy write service without losing committed rows, and identify the underlying cause. Database identity and account details should be supplied through the authenticated provider account, not a public issue.

Local evidence: `RECOVERY.md`, `recovery_verification_latest.json`, and `gate_projection_verification.json`. VPS evidence: systemd journal for `runr-catalog-publication.service`, `/srv/runr/exports/receipts/publisher-timings.jsonl`, and the deployed release path recorded in `RECOVERY.md`.
