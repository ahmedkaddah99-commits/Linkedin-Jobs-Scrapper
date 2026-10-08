# Database storage recheck — 2026-10-08

Initial read-only investigation; later implementation and maintenance are recorded in [DEPLOYMENT_PROGRESS.md](DEPLOYMENT_PROGRESS.md). Project Python verified as 3.12.7. No cleanup,
deployment, provider inference calls, or database mutations performed.

## Current deployment

- Render API: live `41f914964a1616faac6750e56094053702d42203`.
- Render worker: live `41f914964a1616faac6750e56094053702d42203`.
- These include storage commits `b756fb55` and `1e88a9b4`.
- VPS LinkedIn, employer and publisher effective systemd commands select
  `1e88a9b4b26544061006c8d90d1e3be829e4f766` in isolated release directories.
- LinkedIn, employer, publisher and backup timers are active.

## Live configured Turso database

Database URL SHA-256 matches the original audit:
`387ee209fb0cf5623d04a2864becf791865b81c52b5dcdbcfb8aefad73eca98a`.

- Page size: 4,096 bytes; page count: 9,765,265.
- Allocated database pages: **39,998,525,440 bytes** (40.00 decimal GB).
- Free pages: 41,106, or **168,370,176 bytes**, approximately **0.42%**.
- This is database page allocation, not an organization billing measurement.
  A physical rebuild alone can reclaim only a small part of current allocation.
- Catalog publication head is valid. Both historical immutability triggers exist;
  temporary `runr_storage_compaction_guard` table is absent.
- No additional Turso account/admin environment keys are configured. Organization
  database breakdown and query usage attribution were not verified.

| Table | Rows | Latest 100 payload bytes | Latest fingerprint/provenance copies | Historical rowids 40000–40099 copies |
|---|---:|---:|---:|---:|
| job_source_observations | 95,605 | 6,001,031 | 0 / 0 | 100 / 100 |
| job_posting_versions | 57,425 | 6,215,641 | 0 / 0 | 100 / 100 |

Historical sampled version payloads total 13,447,745 bytes across 100 rows.
The latest payload field inventories omit the removed duplicate fields.
These samples demonstrate that compact new writes are active and older redundant
payloads remain; they are not estimates of total recoverable storage.

## Reconciliation with prior work

The original REPORT.md records 1,458,235,279 bytes removed from successful
LinkedIn detail payloads on the VPS. This is a separate local producer database,
not Turso storage. Its rollback backup remained and the producer database had
not been vacuumed at that point.

The historical Turso cleanup checkpoint is still rowid 300 with zero recorded
savings. REPORT.md records timeouts even for one existing observation and safe
restoration of historical update guards. Current historical samples confirm
that the backlog remains. Prevention is deployed; bulk history cleanup and
physical Turso storage reduction are incomplete.

The supplied screenshot reports 14.43 billion reads and 28.25 million writes.
Those are separate usage dimensions. Their dominant queries cannot be inferred
from database size or payload samples; account query analytics remain necessary
to attribute them.
