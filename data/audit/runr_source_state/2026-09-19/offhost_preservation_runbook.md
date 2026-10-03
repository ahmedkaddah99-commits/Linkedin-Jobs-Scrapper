# Off-host acquisition preservation runbook — 2026-09-19 (T44)

Scope: one-time off-host preservation of the recovered 2026-09-19 acquisition set, plus the recurring RC-024 checkpoint schedule. This runbook never restores into active VPS state and never records credentials.

## Preservation set

- Recovery source: `C:\Users\ahmed\Projects_Local\runr-acquisition-recovery\2026-09-19` (13 files, 4,915,180,506 bytes).
- Versioned manifest: `data/audit/runr_source_state/2026-09-19/offhost_preservation_manifest.json` (bytes, SHA-256, logical role, retention class, source revisions, SQLite integrity/row-count expectations per asset).
- Counts preserved and re-verified: 188,206 LinkedIn jobs; 2,612 employer jobs; 428 employer companies; 15,454 LinkedIn URL resolutions; 12,059 resolved LinkedIn company IDs (17,601-row company-source CSV).

## Object key layout and immutability

- Prefix: `runr/acquisition/checkpoints` (RC-024 default; also in `deploy/vps-runtime-contract.json` `retention.backup_object_prefix`).
- Recovered-set objects: `runr/acquisition/checkpoints/recovery/2026-09-19/<relative-path>`; each object metadata carries `sha256`, `recovery-id`, `logical-role`. Uploads refuse to overwrite a different object with the same key (`S3CompatibleRemoteStore.put_file`).
- Scheduled checkpoint objects: `runr/acquisition/checkpoints/<role>/<checkpoint-id>/…`, database uploaded first, `checkpoint.json` manifest last; the manifest is the commit record and a checkpoint without its manifest must not be restored.
- Encryption/access: S3/R2 bucket credentials come only from the environment (`S3_*` in `/opt/runr/.env.acquisition` on the VPS; never in manifests, logs or tickets). Bucket access must be least-privilege (read/write on the acquisition prefix only) and, when the provider supports it, object-lock/versioning retention on the `recovery/` and checkpoint prefixes; the vault scope of T08 stays separate.
- Retention: recurring checkpoints keep `RUNR_ACQUISITION_BACKUP_REMOTE_KEEP=7` remote and `RUNR_ACQUISITION_BACKUP_LOCAL_KEEP=3` local generations (minimum two verified generations in both tiers); `prune_local_checkpoints` removes a local generation only when its `off-host-receipt.json` exists. No pruning before two independently verified copies exist.

## Recovery point / recovery time objectives

- RPO: 24 hours for live producer state (daily 05:00 UTC scheduled backup, after the 04:00 publisher); 0 for the 2026-09-19 recovered set once this runbook's upload completes (immutable historical snapshot).
- RTO: restore is a download plus SQLite validation, not a repair: isolated `verify-recovery-set`/`restore` drill first, then the authorized host restore path (`deploy/restore-acquisition-states.sh`); budget 2–4 hours including transfer of the 3.5 GB LinkedIn state on a normal link.

## One-time preserved-set operations

```bash
cd /opt/runr   # or the repository checkout; use .venv python on Windows

# 1. Validate the manifest against the local recovery root (no network):
.venv/Scripts/python.exe scripts/acquisition_state_backup.py preserve-recovery-set \
  --manifest data/audit/runr_source_state/2026-09-19/offhost_preservation_manifest.json \
  --recovery-root "C:/Users/ahmed/Projects_Local/runr-acquisition-recovery/2026-09-19"

# 2. Upload every asset (idempotent; fails closed on local drift):
.venv/Scripts/python.exe scripts/acquisition_state_backup.py preserve-recovery-set \
  --manifest data/audit/runr_source_state/2026-09-19/offhost_preservation_manifest.json \
  --recovery-root "C:/Users/ahmed/Projects_Local/runr-acquisition-recovery/2026-09-19" --upload

# 3. Verify off-host and run the isolated restore drill (fresh download dir; refuses overwrite):
.venv/Scripts/python.exe scripts/acquisition_state_backup.py verify-recovery-set \
  --manifest data/audit/runr_source_state/2026-09-19/offhost_preservation_manifest.json \
  --download-dir "C:/Users/ahmed/AppData/Local/Temp/runr-restore-drill-t44"
```

The drill verifies, without touching active state: remote HEAD byte counts and SHA-256 metadata; isolated downloads re-hashed; SQLite `PRAGMA integrity_check`, schema tables and row counts (`jobs` 188,206; `companies` 428; `url_resolution` 15,454; …); `git bundle verify` on the code bundle.

## Recurring scheduled backups (VPS)

- Unit: `deploy/systemd/runr-acquisition-backup.service` (oneshot, `runr-acquisition`, hardened); timer `runr-acquisition-backup.timer` at `*-*-* 05:00:00` + `RandomizedDelaySec=300`, `Persistent=true`; installed and enabled by `deploy/setup.sh` (`systemctl enable --now runr-acquisition-backup.timer`).
- The unit runs `scheduled-backup` for the LinkedIn then the employer state: SQLite-consistent Online Backup checkpoint, upload (database before manifest), then receipt-gated prune.
- Monitoring/failure: non-zero exit fails the unit; check `systemctl status runr-acquisition-backup.service` and `journalctl -u runr-acquisition-backup.service`. A failed upload leaves the local checkpoint without a receipt; re-running the unit retries it.

## Prohibitions (standing)

- No pruning before two independently verified copies exist (enforced by the receipt gate).
- No restore into active VPS state from this ticket or this runbook; the authorized restore is RUN-45/T45 scope via `deploy/restore-acquisition-states.sh`.
- No secrets in manifests, receipts, logs or tickets; credentials only via the environment contract.
