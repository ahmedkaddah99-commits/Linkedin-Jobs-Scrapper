# Employer counting and acquisition checkpoint — 2026-10-09

This branch preserves unfinished local work for review. It is not a production
release, a deployment approval, or evidence that the job cleanup completed.
Do not enable the new counter timer or run destructive cleanup scripts merely
because they are committed here.

## Preserved changes

- Existing publication recovery, HTTP transaction support, monitoring, and
  associated tests and deployment definitions.
- Title classification scripts and the occupation dictionary.
- Employer-wide exclusion hooks previously copied to isolated VPS releases.
- Draft cumulative employer counters, migration 077, a counting/cleanup worker,
  and timer definitions. This feature remains undeployed and incomplete.
- Operator verification/cleanup tools and incident/architecture documentation.

## Known incomplete work

The earlier producer cleanup operated on default producer paths, whereas the
live source and publisher services use `/srv/runr/state/active`. The old cleanup
scripts and receipts are historical operation tools, not proof that the active
stores are clean. Their fixed scopes and paths require review before reuse.

Shared catalog write attempts timed out. No additional live job deletion or
counter deployment was performed during checkpoint preparation. The new worker
requires an existing classification baseline and policy bundle that are kept
locally, and successful shared counter persistence before deletion.

The draft worker needs further review of complete source-state cleanup,
protected user history, collection identities/timestamps, unmatched ownership,
job reclassification/version races, bounded throughput, and baseline lifecycle.
The title-only publication gate is opt-in through `RUNR_TITLE_COLLAR_POLICY`.
The employer-wide exclusion policy still needs reconciliation with the owner's
new requirement to continue collecting and count every employer's output.

## Local-only artifacts

The four classification, recheck, cleanup, and counter audit folders remain on
disk, excluded through `.git/info/exclude`. This local exclusion is intentionally
not shared through GitHub. Large snapshots, model-response caches, backups, and
the SQLite counter baseline are not included in this checkpoint.

Reference PNGs, publication investigation Python scripts, and temporary backup
progress/compression/write-probe/recovery tools are also retained locally and
excluded from Source Control. Final publication incident reports are retained
in the repository as historical evidence; their referenced raw evidence remains
local or on the VPS.

Git synchronization does not synchronize Turso data, VPS SQLite databases, or
the deployed VPS overlays. Those remain separate from this checkpoint branch.
