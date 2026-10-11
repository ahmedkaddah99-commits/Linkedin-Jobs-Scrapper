# Durable database reduction assessment — 2026-10-08

## Finding

The configured Turso database allocates approximately **40.00 decimal GB**.
Only 0.168 GB is free. Most storage is occupied data rather than already freed
pages. A rebuild/reclamation step must follow logical cleanup.

Prevention commits `b756fb55` and `1e88a9b4` are deployed. Historical Turso
compaction remains unfinished. The earlier 1.458 GB cleanup affected the VPS's
separate LinkedIn producer database, not Turso.

Large historical records, repeated normalization/evidence representations, and
unbounded operational history explain the main opportunities. Removing closed
jobs or obsolete versions alone cannot address this: current counts are 56,181
canonical jobs (60 closed) and 57,451 versions, of which only 1,270 are outside
the canonical jobs' current-version pointers. These 1,270 are not automatically
safe to delete; other references can require them.

## Measurement method and limits

Read-only HTTP SQL queries; project Python 3.12.7 verified. No live writes,
deletions, schema changes, deployments, or paid model calls were performed.

`reduction_measurements.jsonl` contains table counts and 100-row samples from
ten rowid positions. `option_measurements.jsonl` contains 50 observation and
50 version payloads analyzed in memory, plus bounded operational-table samples.
No job contents are written to these measurement artifacts. Samples are
distributed across historical rowid ranges, not only recent compact records.

The option calculations reserialize JSON consistently before comparison. They
measure logical UTF-8 JSON savings and extrapolate using observed row counts.
They are **estimates, not exact physical per-table sizes or guaranteed savings**.
Sampling clustered rows can overrepresent sources and payload sizes. Queries
ran while production ingestion continued, so counts describe slightly different
instants. Exact publication/rejection/membership aggregate queries timed out;
they were not repeatedly retried. Even an aggregate dbstat query restricted to
the publications table exceeded its 25-second limit. Physical table/index
attribution remains unverified.

The maximum rowids for rejections and memberships are upper bounds, not exact
row counts. Bounded samples had no unexpected gaps, supporting approximate
counts, but do not prove whole-table density.

## Measured inventory

| Area | Rows | Estimated text/JSON size | Notes |
|---|---:|---:|---|
| Observation payloads and separate raw inputs | 95,648 | 11.45 GB | Includes substantial duplicate historical envelopes |
| Posting versions, including separate description | 57,451 | 11.36 GB | Almost all versions are current |
| Normalization rule outputs | 66,228 | 2.74 GB | Another full normalization mapping representation |
| Per-field provenance | 1,957,557 exact | Sample estimates vary materially | 262/300 sampled rows have unknown/missing state |
| Rejection history | Approximately 4.44 million; max rowid 4,435,455 | Approximately 2.65 GB text, plus indexes | New rejection identity includes acquisition cycle |
| Publication membership history | Approximately 5.69 million; max rowid 5,693,025 | Approximately 0.53 GB identifier text, plus table/index overhead | Current head has only 35,637 memberships |
| Publications | 244 exact | Approximately 2 GB snapshot JSON | Distributed sampled snapshots range from 1.5 KB to 13.7 MB; total not measured |
| Version quality reports | 57,451 | 0.75 GB | Detailed derived audit reports |
| Description intelligence | 32,243 | 0.64 GB | Contains paid derived output and copied original posting |
| Retired FTS | 400 copied documents, 5,528 data blocks | Approximately 0.11 GB | No live FTS-maintenance triggers; migration removed them |

Text/JSON estimates exclude SQLite record overhead, indexes, page slack and
freelist pages. Do not add these estimates to infer an exact physical total.
Current account usage attribution and other organization databases remain
unverified because no Turso account/admin credential is configured.

## Reduction options, in order

| Change | Estimated reduction | Work required to keep it reduced |
|---|---:|---|
| 1. Finish historical cleanup using the deployed compaction helper | **11.9 GB logical**: 3.93 GB observation payloads + 2.46 GB raw inputs + 5.49 GB version payloads | Keep compaction at every durable write boundary; enforce it for bulk ingestion, reprocessing and repairs as well as ordinary ingestion |
| 2. Remove byte-equal description aliases, after option 1 | **1.34 GB additional logical** | Persist one canonical description; synthesize compatibility aliases when reading. Preserve distinct HTML/text source representations when needed |
| 3. Replace embedded full mappings with one canonical mapping and compact field projection, after options 1–2 | **Up to 5.25 GB additional logical** before replacement projections and any missing canonical mappings | Store field values/states needed by feeds and publication directly; reference reusable evidence instead of embedding it in every observation and version |
| 4. Bound historical publications and memberships | **Roughly 2–3 GB logical snapshot/identifier data**, plus unmeasured table/index savings | Retain current head, rollback publication and a small number of successful snapshots; pin active/checkpoint/recovery references. Clean up both JSON and membership rows |
| 5. Replace repeated historical rejection rows with current rejection state and bounded events | **Up to approximately 2.6 GB logical text**, plus indexes; retained diagnostics reduce this saving | Deduplicate current state across cycles by job/reason/policy, retain short event history and daily aggregate counters; never append the same full rejection solely because a new cycle started |
| 6. Stop writing separate empty per-field evidence records | **Approximately 0.57 GB logical** for sampled missing/unknown records, plus indexes | Encode complete current missing/unknown states compactly; retain real evidence and prevent older present values resurfacing when a field becomes missing |
| 7. Move necessary cold raw/normalization/audit evidence to compressed content-addressed objects | Several more GB; current rule-output and quality-report candidates alone total about **3.5 GB logical** | SQL retains typed current fields, hashes and object references. Write each unique object once; fetch it only for explicit reprocessing/audit. Expire unreferenced historical objects |
| 8. Remove retired FTS and other confirmed unused structures | About **0.1 GB** for FTS | Forward migration removes the virtual table correctly and prevents its recreation; do not delete its shadow tables individually |
| 9. Physically reclaim storage after cleanup | Initially only **0.168 GB** available; much more after preceding changes | Verify the deployed libSQL/Turso-supported reclamation path, or migrate into a compact replacement database; confirm page counts and billed storage afterward |

Options 1–3 identify **18.46 GB of candidate logical removal** in the sampled
observation/version representations. This includes an upper bound for full
mapping removal, so the actual subtotal is lower if replacement projections
or missing canonical mappings must be added. Do not add option 7's raw-input
savings to option 1's raw savings without measuring the remaining raw input.
Options 4–8 affect other representations but retention and reference pins reduce
their achievable savings. Compression is an alternative for a particular
representation, not another saving to add after deleting that representation.

A reasonable full-project engineering target is **roughly 8–12 GB**, with a
goal of getting below the owner's 9 GB plan allowance. This is not a verified
forecast or a promised final size. Establish the actual target using a compact
candidate database before cutover. A lighter first phase can remove around
10–13 GB of historical logical duplication without the broader storage redesign.

## Required reader and reference changes

Deleting mappings in place would be unsafe. `public_contract._mapping_and_fields`
uses embedded mapping records and field states, while feed SQL currently strips
the full mapping only during projection. Publication completeness, source
reprocessing and normalization need the semantic fields currently represented
there. Preserve those fields in a compact projection and change consumers before
removing the redundant evidence bodies.

There are fewer rule-output rows than observations; do not assume every
observation already has a usable canonical mapping. Backfill missing canonical
records and verify references before removing embedded copies. Content-address
deduplication must exclude volatile observation timestamps/IDs from semantic
identity while retaining those timestamps/IDs separately as event evidence.

Raw input remains necessary for current reprocessing. Preserve a verified current
source record for each required content hash. Large redundant copies and obsolete
debug history do not require indefinite SQL retention.

Keep current version/source relationships, original first-seen/posting anchors,
job/company identities and aliases, application destinations, publication head,
publisher checkpoints, running task leases, user saved/applied jobs and document
references. Preserve paid description/profile outputs needed by current records;
deleting them would cause avoidable provider spending.

## Persistent operating policy to implement

These are proposed defaults, not settings already deployed:

1. **Write compact data by default.** Persist an explicit storage projection
   rather than a copy of the entire in-memory job. Separate current normalized
   values from raw evidence. Guard all writers, including SQL bulk projection,
   rule replay, repair and import paths. Compare semantic hashes before adding
   another large source/mapping record for an unchanged job.
2. **Bound history by count as well as age.** Keep head + rollback + at most
   three successful publication snapshots, plus temporarily pinned snapshots.
   Seven days alone is inadequate: 180 of the current 244 publications fall
   within the last seven days. Preserve metadata/count summaries for older cycles
   without their full catalog membership copies.
3. **Keep current rejection state and seven days of bounded diagnostic events.**
   Cap verbose event samples per job/reason and retain daily aggregate counts.
   Seven days of every repeated full rejection could still be too large.
4. **Retain current and required previous job content plus pinned user/run
   references.** Keep detailed observation/debug events for 14 days, and expire
   unreferenced cold history after 30 days. Keep required current source content
   as long as the referenced job/version needs it. Retention must not remove
   lifecycle closure evidence before the configured grace process completes.
5. **Run resumable maintenance daily**, with a per-run row/time budget, locking,
   checkpoint, reference pin set, batch transactions and sanitized receipt.
   Restart/redeploy must resume it. Failed maintenance must alert; a script that
   exists but never succeeds is not a working retention policy.
6. **Monitor allocated bytes, live payload bytes, table counts, retention
   backlog, unique content count and growth rate.** Use cheap bounded metrics,
   not repeated full JSON scans. Set warning/critical thresholds relative to
   the verified post-migration budget and alert before 9 GB; the current 40 GB
   database cannot immediately meet that budget.
7. **Prove persistence:** same-source replay must not add another full blob;
   repeated unchanged collection must not multiply provenance or rejection
   bodies; history remains bounded across many cycles; pinned jobs still open;
   maintenance survives interruption; no routine GET downloads cold evidence
   or performs cleanup writes.

## Delivery sequence

This is the approved reduction proposal, not a completion report. Actual implementation, verified backups, and unfinished live operations are tracked in [DEPLOYMENT_PROGRESS.md](DEPLOYMENT_PROGRESS.md).

1. Capture a recoverable consistent baseline and reference-pin inventory.
2. Deploy and verify permanent writer/reader changes and the retention job.
3. Build a compact candidate database or execute a bounded historical backfill.
   Existing in-place updates repeatedly stalled, including single-row attempts;
   do not simply rerun that failed operator path with bigger batches/timeouts.
   Investigate account/platform write visibility first. A streamed rebuild into
   a new database is the fallback, with writers serialized and final changes
   replayed so user data cannot be lost.
4. Validate table counts, hashes, current-job/publication/user references,
   paid derived outputs, feed/detail/document behavior and resumable queues.
   Check all immutability guards after maintenance.
5. Reclaim physical pages or cut over to the measured compact candidate.
   Switch Render API, worker and VPS catalog bindings together, with verified
   database identity and rollback. Old database storage remains billable until
   its bounded rollback window ends and it is deliberately retired.
6. Observe multiple real acquisition/publication cycles. Compare growth and
   retention receipts to the new budget, not just deployment success.

Turso's organization query analytics are needed to attribute the 14.43 billion
reads shown in the screenshot. Storage reduction alone does not fix repeated
unscoped scans. Treat rows read/written as separate acceptance metrics.

## Separate VPS disk work

The producer cleanup already freed 1.458 GB logically. The SQLite file was not
vacuumed and its rollback backup remained at the prior audit. Schedule producer
reclamation within a serialized acquisition maintenance window and retire
temporary backups after verified off-host recovery and a bounded rollback window.
Keep the existing three-local/seven-off-host checkpoint policy. These changes
reduce VPS/backup storage, not the configured Turso database's 40 GB allocation.
