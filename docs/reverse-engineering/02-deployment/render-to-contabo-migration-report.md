# Runr VPS migration: current operating state

Updated 10 October 2026. This page is the current record; superseded migration
plans and progress notes remain available in Git history.

## Production

- `https://app.userunr.com` serves the VPS at `144.91.99.90`.
- Nginx serves the frontend and proxies `/v1` to the API on loopback port 18000.
- HTTPS certificate expires 8 January 2027; simulated renewal passed.
- Owner confirmed Render API and worker suspended. Keep them suspended to avoid
  two independent database authorities.
- API and customer worker use release `/srv/runr/releases/customer-ebaa4147`.
  Returning browsers retire the stored former Render API address.
- Python 3.12.7 uses private SQLite 3.54.0. The production database is
  `/var/lib/runr/customer-candidate-db/backend.sqlite3`, at migration 077.
- API and worker share WAL access through group `runr-database`, with mode 0660
  on the database and sidecars. Worker historical automatic retries are disabled.
- R2 remains the object store. Service credentials live in protected VPS env
  files and must never be copied into Git or printed.

## Verified

- Complete export restored in isolation: full integrity check passed, no foreign
  key violations. Migration from 076 to 077 rehearsed and applied successfully.
- 68 customer/billing tables matched the frozen Turso export in every column.
  VPS differences were the expected migration entry and worker heartbeats.
- Major catalog counts match frozen Turso: canonical jobs 56,817; posting
  versions 58,099; source observations 96,778; publications 32; publication jobs
  6,442,383. Counts do not establish equality of every catalog payload.
- Publication head and all 20,547 queue rows matched. Queue has 5,535 published,
  15,012 rejected and no pending rows.
- Publisher SQLite permissions, write-lock preflight and bounded empty-queue
  drain passed under the publisher account. Existing 555 employer exclusions
  remain configured.
- Public homepage and private readiness passed after release activation.
- Real Chromium PDF generation passed under the application service account.
- Frontend API regression tests: 24 passed. Signed-in customer journeys still
  require acceptance verification. Browser access is currently blocked because the
  administrator policy could not be verified.

## Backups and storage

- Original complete export is on R2 and passed a full checksum readback.
- Historical `rc024-evidence` was compressed, archived on R2, checksum verified
  by full readback, and removed locally after reference/open-handle checks.
  This reclaimed approximately 16 GiB; durable receipt remains on the VPS.
- `runr-customer-backup.timer` runs daily at 03:30 UTC (05:30 Berlin on this date),
  with up to five minutes of jitter. It pins a consistent SQLite read snapshot,
  checks integrity and foreign keys, verifies compressed restore hash, uploads
  to R2, and verifies a full download before removing temporary local files.
- R2 keeps seven verified customer backup generations. Local snapshot/archive
  files are temporary. A failed attempt preserves its temporary files for
  inspection and cannot overwrite them silently.
- First customer backup completed successfully: full integrity check passed,
  foreign key violations zero, compressed restore hash verified and full R2
  readback verified. The durable latest.json receipt now exists.
- Temporary first snapshot uses about 32 GiB. Additional historical cleanup must
  wait for its verification/removal to preserve operating headroom.

## Observability

[Customer dashboard](https://pluckyhovercraft81.grafana.net/d/runr-vps-customer/runr-vps-customer-services)
shows public HTTP rates/errors/latency/logs, API readiness, service memory/CPU,
customer queue age, real database query health, SQLite/WAL sizes and backup age.

Five customer alerts cover API unavailability, database query failure, stale
monitoring, missing/stale backup and free disk below 12 GiB. Existing alert
contact point is retained; no test email was sent. Acquisition catalog monitoring
now reads the VPS SQLite database, rather than the former Turso database.

## Remaining acceptance work

1. Finish the separate isolated restore drill. Verify backup metrics reach Grafana.
2. Check signed-in customer workflows, uploads, billing callbacks and exports.
3. Missing-object classification verified against the live VPS and current
   frontend/repository hydration: two missing objects have current Career Assets
   entries (one real uploaded CV and one test resume). Seven only have retained
   document records; one also has a workspace text binding. Preserve all retained
   text. Missing originals are not frontend code assets or company logos.
   Do not classify all nine as current downloadable files or fabricate originals.
4. Continue verified off-host historical storage cleanup and bounded retention.
   Preserve active producer state, manifests, exclusions and rollback evidence.
5. Complete any broader catalog payload reconciliation needed beyond the count,
   customer-table, publication-head and queue checks above.
6. Rehearse a bounded producer-to-publication cycle, then resume the dedicated
   collectors with resource limits. Owner pause remains active during this work.

## Queued autonomous work

- Completed: `runr-customer-backup.service`, with verified receipt.
- Completed: `runr-offload-historical-acquisition-v2-20261010.service` archived
  four historical/rehearsal directories, verifies full R2 readback and only then
  removed their local copies.
- Running: `runr-customer-restore-drill-v2-20261010.service` restores the newly
  verified backup from R2 into isolation, verifies the exact database hash,
  schema, structural checks and customer counts, then removes the temporary copy.
- The isolated restore drill is not complete yet. Historical archive receipt
  verifies full R2 readback and archive listing. Acquisition local backup retention
  is now two generations;
  remote policy remains seven. Heavy pipeline snapshots resume after the first
  verified customer-backup receipt exists.

## Evidence locations

- Initial restore: `/srv/runr/migration-20261010/verification.json`.
- Customer reconciliation and archive receipts:
  `/srv/runr/ops/alloy-repair-20261010/`.
- Publisher smoke receipt:
  `/var/lib/runr/acquisition-data/publisher-sqlite-smoke.json`.
- Verified recurring backup receipt:
  `/var/lib/runr/customer-backups/latest.json` (exists only after success).
- Implementation branch: `migration/vps-sqlite-20261010`, pushed to GitHub.

Use [VPS acquisition operating policy](vps-acquisition-operating-policy.md) for
owner pause and collector policy, and [runtime/timers](vps-runtime-and-acquisition-timers.md)
for acquisition operation. Historical deployment plans must not override this page.