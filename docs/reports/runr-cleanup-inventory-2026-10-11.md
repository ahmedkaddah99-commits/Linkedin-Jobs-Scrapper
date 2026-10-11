# Runr cleanup inventory — 11 October 2026

## Owner-authorized cleanup execution

Historical VPS cleanup is complete. Archives are preserved at
`C:\Users\ahmed\Runr-Historical-Archives\2026-10-11`, outside the repository.
The verified data archive is 5,688,671,964 bytes; the verified archive of 36
unreferenced releases is 947,118,748 bytes. Full local hash verification,
archive readability and source comparison passed before deletion. Google Drive is not connected;
the owner authorized local storage as the fallback. New historical archives were
not uploaded to R2. Operational disaster-recovery backups remain on their existing
bounded policy until an automatic, verified replacement destination is available.

Deployed `/opt/runr-ops/run-storage-budget.sh` and the hourly
`runr-storage-budget.timer`: fixed-size receipt/metrics, 48 GiB minimum headroom,
6 GiB export budget and 6 GiB release budget. These limits flag excess history;
they do not automatically delete unarchived files. Existing acquisition backups
retain two local and seven remote generations, LinkedIn exports retain two
generations, and journald is capped at 1 GiB. The historical architecture note
was replaced by a recovery pointer; stale subsystem baseline claims received
current corrections. Product services were not replaced by the cleanup deployment.

The release warning budget was increased from 4 to 6 GiB after the separate
external-jobs deployment added a referenced release, bringing preserved release
storage to 4.27 GiB. This allows current component references and rollback copies;
it does not authorize additional unverified deletion.

### Verified release cleanup

At 02:56 Europe/Berlin, 36 selected historical releases were removed after full
local SHA-256 verification, archive readability, source comparison and renewed
reference/open-file checks. The archive is
`C:\Users\ahmed\Runr-Historical-Archives\2026-10-11\releases.tar.gz`
(947,118,748 bytes), SHA-256
`5d1e0b103259c92c2e2e6e151e93b4ae114dbc60200cfbc505b470dda6e7832e`.
Exact paths and members are preserved beside it in `releases.paths.txt` and
`releases.members.txt`; `releases.completed.txt` contains the VPS deletion
receipt. Available space after this batch was 67,418,390,528 bytes (62.79 GiB).
At 03:33 Europe/Berlin the data archive also passed full local SHA-256
verification and source comparison. Its SHA-256 is
`fbef3a29c7656fa3334ecfc16e88996424e56a5f6961e30964b306f32e58c3f3`.
The five source directories in `history.paths.txt` were removed, including the
retired catalog compaction backup and four historical t42 export attempts.
`history.completed.txt`, `final-source-verification.txt` and `COMPLETE.txt`
record completion. The latter check confirmed all 41 selected directories absent,
all serving services active and the original active-state symlink preserved.

The two archives total 6,635,790,712 bytes (6.18 GiB). Temporary download routes,
password files, HTTP server and SSH tunnel were removed/stopped. An empty nginx
include remains so another deployment's rollback snapshot stays valid without
recreating download routes. Obsolete local fragments were removed after renewed
full archive hash checks, reclaiming 9,064,440,344 bytes (8.44 GiB).

The completed archive receipt recorded 52,485,947,392 bytes available (48.88 GiB).
A concurrent customer backup then held a 33,902,206,976-byte temporary SQLite
snapshot and a 4,312,397,000-byte gzip copy, bringing an interim reading to
48,159,100,928 bytes (44.85 GiB). The backup deletes both after its verified
off-host readback; do not mistake temporary backup usage for retained history.
The backup subsequently completed and removed its temporary files. The resulting
measurement was **86,352,568,320 bytes available (80.42 GiB / 86.35 GB)**, with
59% filesystem usage. The API remained ready throughout the cleanup checks.

The exact historical catalog blob `before.sql.gz` was extracted from the local
archive and verified independently (4,046,598,196 bytes; SHA-256
`29d32d776e7e60ee78745c00f63f16efb334b1c402caae0b412931dce19a0864`).
The VPS re-read and hashed the matching R2 object, deleted only that exact key,
then confirmed absence. Receipts are `historical-r2-retirement.json` and
`catalog-payload-from-history.verified.json` beside the local archives. The
standalone payload is also available under the device backup folder using its
original object-key path.

The resumable completion controller is `deploy/complete-vps-history.ps1`. It
checks full local SHA-256 and archive readability, then requests source comparison
and removal on the VPS. Deletion cannot proceed on an incomplete download.
Receipts and final status are written beside the local archives; `COMPLETE.txt`
is created only after both cleanup batches and final readiness checks succeed.
The temporary password-protected HTTPS transfer routes were torn down and their
expiry timer stopped. Further historical R2 migration continues through the device
task below; operational recovery backups remain under their bounded policy.

### Device backup migration

The owner selected this device instead of Google Drive. A Windows scheduled task,
`Runr device backup mirror`, runs daily at 03:30, catches up when available, and
stores copies under `C:\Users\ahmed\Runr-Historical-Archives\backups`.
`deploy/sync-device-backups.ps1` obtains short-lived signed URLs through the VPS;
R2 credentials stay on the VPS. Downloads resume using bounded ranges and verify
full SHA-256 before promoting each file. A process lock prevents overlapping
copies. The local generation policy follows the seven verified remote generations
per producer; prior verified files are retired only after seven replacements
are completely copied. Historical catalog archives are preserved indefinitely.

The initial inventory contains 69 objects totaling 89.55 GiB across acquisition,
customer-database and historical catalog backup prefixes. The initial copy is
still running; there is no verified full-set migration receipt yet. After a
fresh complete copy, the task retires only individually verified historical
objects under `runr/acquisition/checkpoints/recovery/` and
`private/catalog/backups/`. It compares remote size and SHA metadata again and
checks absence after deletion. Live checkpoint generations, customer database
backups and user documents are excluded. This task does **not** disable
production backup uploads. Completion
is recorded in `backups/latest-verified.json`; unattended task output is in
`backups/latest-run.log`. The device must be available for off-host copies to
advance. Full retirement of operational R2 backups requires a verified replacement
for future backup creation. Historical retirement is recorded locally in
`backups/historical-r2-retirement.json` and on the VPS in
`/srv/runr/ops/device-history-retirement/latest.json`.

## Original inventory snapshot

Read-only inventory requested by the owner. No VPS files, services, timers,
retention settings or repository artifacts were deleted or changed during this
inspection. This report and its evidence files are the only additions.

## Findings

The host reported 69,288,701,952 bytes available (64.53 GiB), at approximately
01:18 Europe/Berlin on 11 October. Directory allocated sizes are measured with
`du -x -B1`; file logical sizes in the export listing use `find`. These differ,
and parent/child rows must not be added together. Shared hard links can also
make separately measured directory totals differ from a combined measurement.

| Area | Exact root | Allocated GiB | Proposed action |
|---|---|---:|---|
| Acquisition backups | `/srv/runr/backups` | 22.46 | Preserve two local generations per producer; examine remaining historical copies individually. |
| Acquisition exports | `/srv/runr/exports` | 9.94 | Review historical t42/rc027 outputs; retain current output/receipt contracts until consumers are traced. |
| Release copies | `/srv/runr/releases` | 6.02 | Prune only after effective service, process, symlink and rollback checks. |
| Active restored scraper state | `/srv/runr/state/versions/t42-restored-20260923` | 21.56 | Keep: `/srv/runr/state/active` resolves here. Historical naming does not make it obsolete. |
| Shared runtime | `/opt/runr` | 3.16 | Keep: shared virtual environment and live service dependencies. |
| Production database directory | `/var/lib/runr/customer-candidate-db` | 31.57 | Keep: authoritative customer/catalog database. |

## Completed backup cleanup, confirmed from current evidence

The previously pending oldest-backup verification has completed. The following
local directories are absent from the current directory inventory:

- `/srv/runr/backups/linkedin/linkedin-20261008T050232738579Z-239b2625fbeb`
- `/srv/runr/backups/employer/employer-20261008T055910027049Z-1ce8c78e7303`

Their cleanup receipts record full readback verification of both database and
manifest, SHA-256 values, remote object keys and the two retained generations.
The database payloads total 7,786,139,648 bytes (7.25 GiB); this is payload size,
not a newly measured disk-space delta. This inspection read existing receipts;
it did not repeat the remote downloads. Evidence is in
[receipts-and-exports.txt](cleanup-inventory-2026-10-11/receipts-and-exports.txt).

Retain these four exact local generations:

- `/srv/runr/backups/linkedin/linkedin-20261009T050223741176Z-43b5b1646746`
- `/srv/runr/backups/linkedin/linkedin-20261010T050611407150Z-361bd2ebba86`
- `/srv/runr/backups/employer/employer-20261009T055745881710Z-465c5c02efcd`
- `/srv/runr/backups/employer/employer-20261010T055933898950Z-302b1e923f2b`

## Concrete next candidates

| Exact path | Allocated GiB | Evidence | Proposed action and remaining gate |
|---|---:|---|---|
| `/srv/runr/backups/catalog-storage-20261008` | 7.81 | Contains `before.sql.gz` (4,046,598,196 logical bytes), `restored-before.sqlite3` (4,339,732,480 logical bytes), verification receipts and an empty trial database. A retired compaction unit references it. | Historical recovery candidate. Read its verification receipts, confirm remote objects and rollback requirements, and establish that no process uses the restored DB before removal. |
| `/srv/runr/exports/t42-d21a3901` | 1.47 | Historical t42 directory. | Archive candidate; inventory nested contents, trace readers, verify recovery. |
| `/srv/runr/exports/t42-attempt05-20260924` | 1.54 | Historical attempt directory. | Same gate. |
| `/srv/runr/exports/t42-attempt08-20260925` | 1.54 | Historical attempt directory. | Same gate. |
| `/srv/runr/exports/t42-attempt09-20260925` | 1.54 | Historical attempt directory. | Same gate. |
| `/srv/runr/exports/linkedin` | 3.14 | Current CSV, generation metadata, metrics and lock; directory size includes nested content beyond the captured file listing. | Keep pending consumer and nested-history review. |
| `/srv/runr/exports/employer` | 0.53 | Current CSV/JSONL and company-method audit. | Keep pending consumer and nested-history review. |
| `/srv/runr/exports/receipts` | 0.001 | Monitoring reads source latest receipts and metrics (`deploy/vps-observability/pipeline.py`, `observe.py`). | Preserve current receipts; apply separate historical receipt retention after classification. |
| `/srv/runr/staging` | 0.41 | Four exact staging paths listed in CSV; some virtual environments link into `/opt/runr`. | Review each staging tree and its rollback links before archive/removal. |

The four large historical export directories total approximately **6.09 GiB**.
They are candidates, not a verified deletion allowance. Together with the
historical catalog recovery directory they represent about **13.90 GiB** to
investigate first.

## Release evidence and deletion criteria

The [path inventory](cleanup-inventory-2026-10-11/path-inventory.csv) gives an
individual row for captured release, staging, backup and export paths, with
allocated bytes, proposed action and verification gate. Referenced releases
are conservatively preserved: references in old configuration may be overridden,
but require review before deletion.

Current API and customer worker configuration points at
`/srv/runr/releases/customer-ebaa4147`. The description-worker current pointer
resolves to `/srv/runr/releases/description-60097a9838c4e3d52f119127b6cb23025e52d0da`;
profile-matching current resolves to
`/opt/runr-profile-matching/releases/0f0a81b29c580633c05df0f2c4843aee90821da8`.
Paused services still require their configured code when resumed.

Before deleting any release: check effective systemd settings (including unloaded
installed units), all service/timer/script references, process cwd/executable/open
files, current symlinks and shared package paths; select and document a usable
rollback release; prove Git/release-artifact recovery including dependencies and
build outputs. A missing reference in this snapshot alone does not prove safety.

## Retention proposal

- Acquisition backups: retain the documented two local and seven remote
  generations per role; prune only after successful verification and protect
  incomplete/in-use generations. The local snapshot currently contains two per
  role; sustained automatic enforcement and remote generation counts remain to
  be checked.
- Customer database backups: preserve the documented seven verified remote
  generations. The latest receipt records integrity `ok`, zero FK violations,
  compressed restore-hash verification and complete off-host readback. Enumerate
  remote generations to verify ongoing retention.
- Releases: retain every referenced release plus an explicitly selected rollback
  release per component. Prune other recovered historical copies after dependency
  review. A universal count of two would be unsafe with the current mixed releases.
- Exports: preserve current output and receipt contracts; retire verified
  historical attempt directories. Set rolling limits after identifying generation
  rates and required readers. No unsupported age limit is assumed here.
- Audit/checkpoint files: preserve active cursors and recovery receipts; define
  separate limits for append-only historical output after schema/reader review.

## Repository and documentation inventory

[repository-candidates.csv](cleanup-inventory-2026-10-11/repository-candidates.csv)
lists exact tracked historical report/audit paths and current file sizes.
These are review candidates, not files approved for deletion.

The existing `de093182` commit already removed five historical readiness CSVs
and an embedded code snapshot: seven files changed, 25 insertions and 58,825
deletions. Do not repeat this completed subset.

`ARCHITECTURE.md` is explicitly historical in `docs/INDEX.md`: preserve unique
decisions, then shorten to a history pointer or relocate with link updates.
Review `docs/RC*` and root report/handoff candidates for unique contracts before
consolidation. Update stale Render/Turso assumptions in subsystem docs against
the current operating record rather than deleting the whole documentation corpus.

The older repository-artifacts document claims hundreds of tracked generated CV
samples. Current `git ls-files` found no tracked files under `test CV/` or
`test-CV/`; those paths are already ignored. They still exist in VPS release
trees, so repository untracking and deployed-artifact cleanup are different tasks.
Intentional `.agents`/`.cline`/`.codex` skill copies and frontend-imported legal
documents need to remain unless their consumers are changed.

## Evidence and limits

- [Disk paths and allocated bytes](cleanup-inventory-2026-10-11/disk-paths.tsv).
- [Service settings and symlinks](cleanup-inventory-2026-10-11/runtime-references.txt).
- [Nested inventory and installed configuration references](cleanup-inventory-2026-10-11/detail-evidence.txt).
- [Existing verification receipts, current pointers and export file sizes](cleanup-inventory-2026-10-11/receipts-and-exports.txt).

Inspection used SSH and shell read operations; no Python, tests or paid provider
calls ran. No credential file contents were read. Shell quoting/CRLF errors
affected portions of the collection: the process cwd loop did not complete and
the first receipt glob could not expand as the unprivileged user. Receipt reading
was subsequently collected as root. Process/open-file checks, remote object
verification, full export-consumer tracing and complete repository inbound-link
review remain explicit deletion gates. This inventory establishes priorities and
protected paths; it does not certify all candidates as disposable.
