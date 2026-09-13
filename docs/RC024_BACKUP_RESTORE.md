# RC-024 acquisition checkpoint and restore runbook

Status: the implementation and fixture rehearsal are integrated, and a bounded
off-host checkpoint/restore was executed for the RC-027 LinkedIn pilot state.
Replacement-host service resume, outage/reboot acceptance, and restoration of
the preserved historical state remain required before RC-024 is fully verified.
RC-026 and the benchmark/pilot gates must not use this document as historical
state acceptance.

## Verified bounded off-host checkpoint - 2026-09-09

The host source was opened through the repository backup helper as the
`runr-acquisition` role; the live SQLite file was not copied with its WAL/SHM
sidecars:

| Item | Verified value |
| --- | --- |
| Host | `runr-vps` / `vmd205749` |
| Source | `/srv/runr/state/rc027-linkedin-6e9a1e9301ffca644aca916aad6fc8827e4a792d/master_linkedin_jobs_state.db` |
| Source bytes / SHA-256 | `770048` / `ed94c1cd30095c3544adccabb028072b327885ccaf2e48630d3d4945213a59d5` |
| Source integrity/schema | SQLite `ok`; exact current 14-table LinkedIn schema |
| Checkpoint | `linkedin-20260909T201035631862Z-e6d35734a371` |
| Backup bytes / SHA-256 | `770048` / `d445e6c1a2dfb45d189c3ced3351406f867f49f3264f5375b07f078f26659356` |
| Local persistent checkpoint | `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc027-20260909\offhost-linkedin\offhost-linkedin-20260909\` |
| Local restore | `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc027-20260909\restored-linkedin` |
| R2 bucket / keys | `runr-prod-artifacts`; `rc027/checkpoints/linkedin/linkedin-20260909T201035631862Z-e6d35734a371/master_linkedin_jobs_state.db` and `.../checkpoint.json` |
| R2 restore | `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc027-20260909\restored-from-r2-linkedin`; hash/schema/integrity matched |

The R2 objects were uploaded in database-then-manifest order by
`preserve_checkpoint_off_host`; the manifest is the remote commit record. The
receipt records the database and manifest hashes and an upload timestamp of
`2026-09-09T20:12:12.124516Z`. This is a verified checkpoint of the bounded
RC-027 host overlay state, not the preserved approximately 3.48 GB historical
LinkedIn state and not proof of a replacement-host service restart.

## Contract

The canonical producer databases remain local SQLite state:

| Role | Persistent source/state path | Checkpoint role | Required schema |
| --- | --- | --- | --- |
| LinkedIn | `/srv/runr/state/linkedin/master_linkedin_jobs_state.db` | `linkedin` | exact current 14-table `StateStore` schema |
| Employer | `/srv/runr/state/employer/master_employer_jobs_state.db` | `employer` | `companies`, `jobs` |

The source is opened read-only. `scripts/acquisition_state_backup.py` uses the
SQLite Online Backup API, checks the exact role schema and full integrity, and
writes one immutable checkpoint under the controlled backup root. It never
copies a live main file with its WAL/SHM sidecars and never changes the source.

Each checkpoint records the release/source version, input manifest ID and
hash, cycle, logical shard, high-water markers, role schema, backup size/hash,
backup method, and compact terminal receipt/identity/absence evidence IDs.
Credentials, request payloads and browser profiles are not accepted as
checkpoint metadata.

`/srv/runr/state/ownership` is the shared durable lease root for the logical
state shard. `SingleWriterLease` gives each claim a token and monotonically
increasing epoch. Collection and publication code must call
`lease.assert_current()` immediately before checkpoint/publication completion;
an expired or replaced owner is fenced. A per-host local lease directory is
only a fixture and cannot coordinate machines.

## Local checkpoint and restore

Use the accepted integrated release SHA and the reconciled source manifest at
runtime. The command below is an example only; it does not run against the
historical laptop databases during this offline pass:

```bash
/opt/runr/.venv/bin/python scripts/acquisition_state_backup.py backup \
  --role linkedin \
  --source-db /srv/runr/state/linkedin/master_linkedin_jobs_state.db \
  --checkpoint-root /srv/runr/backups/acquisition-checkpoints \
  --source-version "$RUNR_RELEASE_COMMIT" \
  --manifest-id "$RUNR_INPUT_MANIFEST_ID" \
  --manifest-sha256 "$RUNR_INPUT_MANIFEST_SHA256" \
  --cycle-id "$RUNR_CYCLE_ID" \
  --shard-id linkedin-catalog \
  --high-water company_scan_id="$RUNR_COMPANY_SCAN_HIGH_WATER" \
  --local-budget-bytes "$RUNR_BACKUP_LOCAL_BUDGET_BYTES" \
  --free-space-reserve-bytes "$RUNR_BACKUP_TEMP_RESERVE_BYTES" \
  --upload
```

`--upload` uses the existing private S3/R2-compatible configuration from
`S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET` and
`S3_REGION`. No new storage service or credential is introduced. The local
database object is uploaded first; the manifest object is uploaded last and is
the remote commit record. A failed upload leaves the local checkpoint for
retry and does not produce a preservation receipt.

The upload key is immutable and includes role and checkpoint ID. Retrying the
same checkpoint is idempotent when the remote size/hash match and refuses a
different object at the same key. The remote lifecycle policy must retain only
the approved bounded number of generations (the checkpoint metadata default
is seven); that policy and its actual result still require host/infrastructure
verification.

Validate and restore only into a new, isolated directory:

```bash
/opt/runr/.venv/bin/python scripts/acquisition_state_backup.py validate \
  --checkpoint-dir /srv/runr/backups/acquisition-checkpoints/linkedin/ID

/opt/runr/.venv/bin/python scripts/acquisition_state_backup.py restore \
  --checkpoint-dir /srv/runr/backups/acquisition-checkpoints/linkedin/ID \
  --target-dir /srv/runr/restore-drills/linkedIn-OWNER-ID

/opt/runr/.venv/bin/python deploy/validate_acquisition_runtime.py \
  --manifest deploy/acquisition-data-manifest.json --role linkedin --deep

/opt/runr/.venv/bin/python scripts/run_manifested_linkedin.py \
  --manifest /srv/runr/shared/inputs/SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json \
  --output-dir /srv/runr/exports/linkedin-restore-drill \
  --state-dir /srv/runr/restore-drills/linkedin-OWNER-ID \
  --require-existing-state
```

The restore command refuses to overwrite an existing target and validates the
checkpoint hash/schema/integrity before atomically promoting the new state
directory. It does not restore over a newer state database. The producer's
existing generation/pointer and final-export behavior remains responsible for
replay-safe publication; restore acceptance must show that behavior on the
accepted integrated release.

## Off-host and outage procedure

The approved runtime sequence is:

1. Claim the role/shard lease under the shared ownership root.
2. Persist producer checkpoints and compact terminal evidence.
3. Create and locally validate a consistent SQLite checkpoint.
4. Upload the database, then the manifest, and persist the off-host receipt.
5. On a replacement host, download the committed manifest first, verify its
   remote metadata hash, download and validate the database, then restore to a
   new state directory.
6. Validate the restored runtime and resume with the explicit state path.
7. Release the old lease only after confirming the new owner has the current
   epoch; the old owner must not publish after fencing.

The local free-space reserve includes temporary backup peak space. A measured
`--local-budget-bytes` refuses additional buffered checkpoints before an
object-storage outage can consume the disk. An outage leaves the last local
checkpoint available for retry; the service must pause/backpressure collection
when that budget is reached. `prune` removes only generated checkpoints that
already have a verified off-host receipt; it never touches source databases,
unpreserved checkpoints, or the external historical snapshots.

## Evidence boundary

`tests/test_rc024_backup_restore.py` is fixture proof only. It uses synthetic
EmployerState and an empty current 14-table StateStore, an in-memory remote,
and a patched employer collector. It proves algorithmic consistency,
integrity, resume, interruption, disk-budget, manifest-last, restore-isolation
and lease fencing behavior without provider or host requests.

It does not prove that the verified external snapshots were preserved in the
approved off-host store, that the S3/R2 credentials/bucket/lifecycle policy
work, that service-account
permissions are correct, or that a replacement VPS/reboot resumes the
historical catalog. Those are required RC-024 acceptance observations and
must be recorded separately with the deployed release SHA and source hashes.

The verified external source inventory remains preserved outside this
worktree at
`C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\feature-worktree-recovery\jobs-urls-preserved\Jobs-Urls\`.
In particular, the authoritative LinkedIn state is the recorded
3,479,191,552-byte SHA-256
`26b81012177f40949b6b3ede3187860129db9fdaf3392d2195d78ac050244317`, and the
employer state is the recorded 83,841,024-byte SHA-256
`b1eee3b449afd075d9b860f12a5880da6769fcc666473bbfe8f08e7e4cb36737`. This
implementation does not move, delete, or commit either source. A historical
source drill must pass the recorded size/hash before creating a generated
checkpoint in a separate temporary or approved backup root.

## 2026-09-09 historical-source rehearsal

Using the verified external snapshot directory above and the shared Python
3.12.7 interpreter, B performed one local, read-only Online Backup measurement
for each authoritative state. Generated checkpoint and restore directories
are outside Git under `C:\Users\ahmed\AppData\Local\Temp\`; no upload was
attempted.

| Role | Source bytes/hash verified | Backup checkpoint | Backup bytes/hash | Online Backup + validation |
| --- | ---: | --- | ---: | --- |
| Employer | 83,841,024 / `b1eee3b449afd075d9b860f12a5880da6769fcc666473bbfe8f08e7e4cb36737` | `employer-20260909T085018133133Z-53589d4a53bb` | 83,841,024 / `4f779500c9cd5fb66342cb36bd2fd236cefb9b9eebb3caf13876fca8b1265aaf` | 2.17s; tables `companies`, `jobs`; integrity `ok` |
| LinkedIn | 3,479,191,552 / `26b81012177f40949b6b3ede3187860129db9fdaf3392d2195d78ac050244317` | `linkedin-20260909T085116426477Z-4b604df8392a` | 3,479,191,552 / `adc5c1ab7ac5b7bdca67cdabd7687fdd29913afae188fab2aba4377a41327525` | 183.67s; exact 14 tables; integrity `ok` |

The generated checkpoint root was
`C:\Users\ahmed\AppData\Local\Temp\runr-rc024-historical-20260909`.
Both checkpoints were restored into the separate
`C:\Users\ahmed\AppData\Local\Temp\runr-rc024-historical-restore-20260909`
root. The combined isolated restore took 117.36s; Employer and LinkedIn
restored hashes matched their checkpoint hashes and both integrity checks were
`ok`. An export-only read of the restored Employer state produced 2,612 jobs
and `final_export_completed=true` in 8.69s under
`C:\Users\ahmed\AppData\Local\Temp\runr-rc024-historical-export-20260909`.

This measures one local source/backup/restore path; it does not select a
production cadence, prove peak-disk headroom, verify remote lifecycle policy,
or substitute for a replacement-host restore. The LinkedIn result especially
requires measured compression/transfer and outage retention decisions before a
six-hour or any other cadence is approved.
