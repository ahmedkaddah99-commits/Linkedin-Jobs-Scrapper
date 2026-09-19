> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14
> Updated by T44 (RUN-44, 2026-09-19): recorded the recovered 2026-09-19 producer/enrichment/export/code set and its versioned off-host preservation (§5.4).

# Acquisition source state (WS-3 data doc)

Data-slice doc for WS-3; subsystem behavior is in [../05-subsystems/acquisition-and-collectors.md](../05-subsystems/acquisition-and-collectors.md) (producers, wrapper call graph) and [../05-subsystems/publication-and-catalog.md](../05-subsystems/publication-and-catalog.md) (publisher). Scope: the VPS acquisition **root layout**, the committed **input CSVs**, the two **producer state DBs** (schemas and restored volumes), other state snapshots, **exports, receipts, locks, backups**, the **data manifest** contract and the runtime **validator**.

Method: static reading at `58a96674` (`deploy/acquisition-data-manifest.json`, wrapper scripts, producer DDL, validator). No host was contacted; actual VPS contents are UNKNOWN.

---

## 1. Purpose

Everything the acquisition role persists lives outside git except three seed CSVs. This doc records what exists, what is committed vs generated, where each artefact lives (default VPS paths), and how integrity is checked at startup.

## 2. Root layout (defaults from wrappers)

| Root | Default | Set by |
|---|---|---|
| Input root | `/srv/runr/shared/inputs` | `run-acquisition-source.sh:13`, validator `ROOT_MAP` |
| State root | `/srv/runr/state` (+ `versions/`, `active` symlink, `locks/`) | L15; `restore-acquisition-states.sh` |
| Export root | `/srv/runr/exports` (+ `{linkedin,employer,combined,receipts}`) | L16 |
| Receipt root | `$export/receipts` | L17 |
| Lock root | `$state/locks` | L18 |
| Backup root | `/srv/runr/backups` | validator `ROOT_MAP`; export unit env |
| Publisher data dir | `/var/lib/runr/acquisition-data` (`backend.sqlite3`) | `run-acquisition-publisher.sh:11` |

## 3. Committed inputs — `data/**` (7 files, WS-3 owned)

Correction N-3 applies: these are **INPUTS**, not disposable output.

| File | Kind | Contract (from `deploy/acquisition-data-manifest.json` `seed_inputs`, verified) |
|---|---|---|
| `data/acquisition/inputs/company_master.csv` | INPUT | utf-8-sig CSV, 9,129 rows × 82 cols, 17,491,851 B; exact SHA-256 at startup; "required company/LinkedIn columns" |
| `data/acquisition/inputs/company_registry_canonical.csv` | INPUT | 17,601 × 42, 11,986,132 B; `canonical_CompanyID`; default registry for `canonicalize_producer_states.py:38` |
| `data/acquisition/inputs/company_sources_linkedin_ids.csv` | INPUT | 17,601 × 118, 18,807,047 B; "118-column contract and required eligibility columns"; eligibility-manifest source; required seed for validator roles `linkedin`/`employer` (`validate_acquisition_runtime.py` `ROLE_REQUIREMENTS`) |
| `data/audit/report/completeness_audit.json` / `.md` | GENERATED | output of `scripts/audit_job_publication_completeness.py` over a synthetic 300-record sample (`scripts/generate_completeness_sample.py`), 2026-09-10 |
| `data/audit/real/completeness_audit_real.json` / `.md` | GENERATED | output of `scripts/audit_real_job_data.py` (read-only over restored producer state; 188,206 LinkedIn records evaluated), 2026-09-10 |

`Company-Urls/` (554 files) exists only in preserved historical feature work (`0d7f2b5c`), **not at the baseline** (verified by `git ls-tree`). SHA-256 values are in the manifest file itself and are not repeated here.

## 4. Server-only inputs (not in git; `seed_inputs` with `repo_path: null`)

| Artefact (`server_path`) | Validation at startup |
|---|---|
| `/srv/runr/shared/inputs/SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json` | schema `runr_source_eligibility_manifest_v1`, manifest hash, sidecar hash, unresolved-ownership gate |
| `/srv/runr/shared/inputs/SOURCE_ELIGIBILITY_RAW_RC005_RECONCILED.jsonl` | sidecar schema `runr_source_eligibility_raw_sidecar_v1`, exact SHA-256 (17,601 rows) |
| `/srv/runr/shared/inputs/linkedin/linkedin_endpoint_pagination_validation.json` | exact SHA-256, endpoint match, numeric page step, bounded max start |
| `/srv/runr/shared/inputs/linkedin/linkedin_guest_endpoint_filter_validation.json` | exact SHA-256, endpoint match, only explicitly SUPPORTED filters enabled |

## 5. Producer state DBs

Authoritative schemas are the DDL in the producers; restored volumes below are the **manifest's documentary record** of the 2026-09-08 snapshot (not live).

### 5.1 LinkedIn — `/srv/runr/state/linkedin/master_linkedin_jobs_state.db`
- 15 tables created by `StateStore` (`scripts/master_linkedin_jobs_catalog.py:1887–2029`): `runs`, `source_company_groups`, `company_slug_aliases`, `company_scans`, `query_partitions`, `search_pages`, `search_cards`, `jobs`, `job_company_observations`, `detail_queue`, `detail_attempts`, `ownership_exclusions`, `lifecycle_events`, `proxy_health`, `collection_cursor`, `company_scan_schedule` (the manifest lists 4 supported schema variants, the newest adding `collection_cursor` + `company_scan_schedule`).
- Manifest record: 3,479,191,552 B; row counts include `jobs` 188,206, `job_company_observations` 188,206, `search_cards` 198,491, `ownership_exclusions` 8,689; integrity_check "ok"; `required_on_first_acquisition_start: true`; backup method "SQLite online backup or filesystem copy only while no writer is active".
- Publisher reads `job_company_observations` (bootstrap window + latest-run rows) and `company_scans` statuses; never writes it (`scripts/publish_producer_states.py:54–60` read-only connection).

### 5.2 Employer — `/srv/runr/state/employer/master_employer_jobs_state.db`
- 5 tables (`scripts/master_employer_jobs_catalog.py:1277–1293`): `companies`, `jobs`, `coverage_receipts`, `collection_cursor`, `company_scan_schedule` (manifest lists 4 supported variants).
- Manifest record: 83,841,024 B; `companies` 428, `jobs` 2,612; integrity_check "ok"; `required_on_first_acquisition_start: true`.
- Publisher reads `jobs.payload_json` / `companies` (coverage `outcome` drives closure safety).

### 5.3 Other state snapshots (manifest `state_snapshots`, none required on first start)
| Snapshot | Server path | Purpose |
|---|---|---|
| `linkedin_id_resolution_state` (~414 MB) | `/srv/runr/state/enrichment/linkedin_id_resolution.sqlite3` | RC-006 resolver checkpoints; "RC-006b remains pending" |
| `linkedin_legacy_archive` (~2.0 GB) | `/srv/runr/backups/linkedin/linkedin_germany_discovery_state_pre_v2.db` | forensic comparison only |
| `linkedin_legacy_v2_state` (~116 MB) | `/srv/runr/backups/linkedin/linkedin_germany_discovery_state_v2.db` | historical; "do not use as the 14-table producer state" |

### 5.4 Recovered 2026-09-19 acquisition set and off-host preservation (T44)

The historical producer state was recovered non-destructively on 2026-09-19 after the former local snapshots root disappeared; the full evidence and per-file SHA-256 values are in `data/audit/runr_source_state/2026-09-19/recovery_manifest.md`. The recovered set is 13 files / 4,915,180,506 bytes: the LinkedIn producer DB (14-table schema; `jobs` 188,206; `job_company_observations` 188,206; integrity ok), the employer producer DB (`companies` 428, `jobs` 2,612), the company identity/enrichment SQLite (`url_resolution` 15,454), three company-source CSVs (the `company_sources_linkedin_ids.csv` input holds 12,059 resolved LinkedIn company IDs), the LinkedIn/employer exports, the RC-024 employer checkpoint record (`not_uploaded`), the complete-history Git bundle (verified refs: `deployment/render-turso-r2` `30c8d5f1`, `temp/runr-linkedin-final` `e8469711`, `temp/runr-employer-final` `6ea7f460`, `temp/runr-production-final` `58a96674`) and the recovery manifest itself.

- **Versioned preservation manifest:** `data/audit/runr_source_state/2026-09-19/offhost_preservation_manifest.json` (schema `runr.acquisition.recovery-manifest.v1`; per asset: bytes, SHA-256, logical role, retention class, source revisions for the bundle, SQLite integrity/row-count expectations).
- **Off-host storage:** S3/R2 under the checkpoint prefix `runr/acquisition/checkpoints/recovery/2026-09-19/<relative-path>`; every object carries a `sha256` metadata record and is HEAD/download verified against the manifest.
- **Verification/restore drill:** `scripts/acquisition_state_backup.py preserve-recovery-set` (upload) and `verify-recovery-set --download-dir <isolated dir>` (HEAD + isolated download + SHA-256 + SQLite integrity/schema/row counts + `git bundle verify`; never touches active state). Runbook: `data/audit/runr_source_state/2026-09-19/offhost_preservation_runbook.md`.
- The RC-024 scheduled checkpoint pipeline (timer `runr-acquisition-backup.timer`) owns recurring off-host preservation from the live producer state; see `../02-deployment/vps-runtime-and-acquisition-timers.md`.

Versioning/restore: `deploy/restore-acquisition-states.sh` validates (`--role all --allow-state-drift`), canonicalizes via `scripts/canonicalize_producer_states.py` into `/srv/runr/state/versions/<release>`, then atomically switches the `active` symlink (L53–69). Checkpoints/backups: `scripts/acquisition_state_backup.py` (SQLite Online-Backup; optional S3/R2 upload; tests `tests/test_rc024_backup_restore.py`).

## 6. Exports, receipts, locks

| Artefact | Path (default) | Writer |
|---|---|---|
| Source CSV/JSONL/metrics | `/srv/runr/exports/{linkedin,employer}/` (+ `.manifest_inputs/` staged manifest CSV, regenerated per run) | runners |
| Combined CSV | `/srv/runr/exports/combined/master_jobs.csv` | `scripts/build_master_jobs_catalog.py` (export unit / cycle wrapper; both source CSVs must be non-empty) |
| Receipts | `$receipt_root/<source>-latest.json`, `-latest-metrics.json`, `-validation.json`, `<source>-receipt-write.json` | wrappers + `scripts/write_acquisition_receipt.py` (fields: source, status, exit_code, started/finished, duration, metrics SHA-256, release commit, cgroup `memory.peak`/`cpu.stat` counters when under systemd) |
| Locks | `$state/locks/{linkedin,employer,publisher}.lock` | `flock -n`; busy source → exit 75; publisher also takes both source locks non-blocking |

Large exports are explicitly excluded from git (manifest `excluded_from_git.large_exports`: `master_linkedin_jobs.csv/.jsonl`, `master_jobs.csv`, `master_employer_jobs.csv/.jsonl`).

## 7. Validator and integrity contract

`deploy/validate_acquisition_runtime.py` (read-only, no providers): validates immutable seed hashes, required paths per role (`linkedin`/`employer`/`enrichment`/`all`), SQLite table contracts, and with `--deep` full integrity + state hashes. Wrappers run it before every source/publisher run with `--allow-state-drift` (mutable state drift expected after a prior run). Failure copies the validation JSON into the receipt metrics (`run-acquisition-source.sh:109–112`).

The store-side catalog DB (`$RUNR_DATA_DIR/backend.sqlite3` / Turso) is WS-5's: [schema-and-migrations.md](schema-and-migrations.md).

## 8. Safe verification commands (not executed in Phase 2)

```bash
git show 58a96674:deploy/acquisition-data-manifest.json   # read the contract
node scripts/run-python.cjs deploy/validate_acquisition_runtime.py --help
node scripts/run-python.cjs scripts/acquisition_state_backup.py --help
node scripts/run-python.cjs -m pytest -q tests/test_rc024_backup_restore.py tests/test_acquisition_runtime_manifest.py
git grep -n "required_on_first_acquisition_start" 58a96674 -- deploy
```

Do not open restored state DBs outside an authorized host; do not run the restore script.

## 9. Status, gaps and provenance notes

| Item | Classification |
|---|---|
| Committed input CSVs (3) + contracts | VERIFIED (scope: static — manifest `seed_inputs` matches `git ls-tree` output; `startup_validation` strings cross-checked with validator code) |
| Generated audit outputs (4) | VERIFIED (scope: static — file list matches; provenance inferred from generating scripts' usage lines) |
| Producer state schemas | VERIFIED (scope: static DDL read; 15/5 tables enumerated) |
| Restored volumes / row counts | UNKNOWN on the actual host — manifest values are a 2026-09-08 documentary snapshot; mutable state drift is expected and allowed |
| Recovered 2026-09-19 set (§5.4) | VERIFIED locally (bytes, SHA-256, SQLite integrity/row counts re-run 2026-09-19); off-host preservation verified per runbook receipt |
| `Company-Urls/` | RETIRED/HISTORICAL (only on `0d7f2b5c`) |
| `scripts/audit_runr_data_readiness.py` (T11) | PLANNED-NOT-IMPLEMENTED — untracked, feature checkout only; `DEFAULT_RUNR_ROOT` points at a stale worktree (readiness-audit bug, ticket T11) |

### Deployment evidence (documentary only — not live verification)
- `deploy/acquisition-data-manifest.json` (baseline, generated 2026-09-08 at release `9ba1d551`): all volumes/hashes above; policy `no_live_acquisition`, `mutable_state_is_not_committed`, `secrets_are_environment_only`.
- Untracked `docs/reports/RUNR_PRODUCTION_COMPLETION_REPORT_2026-09-12.md` (feature checkout; T06): post-`4a1b1df5` run records — LinkedIn state "188,238 jobs", employer "2,612 durable jobs / 5,135 manifest tasks" — recorded, not verified; contradiction with the 2026-09-08 snapshot counts is expected drift.

| ID | Gap |
|---|---|
| **WS3-G15** | The data manifest is generated at `9ba1d551` but the baseline is `58a96674`; input CSVs may have drifted since (hashes not re-verified against the working tree in Phase 2 — no dataset reads). |
| **WS3-G16** | `data/audit/**` outputs are committed although generated; no `.gitignore`/regeneration marker records their provenance (audit N-3 partially addressed; decide commit-or-generate). |
| T11 | Readiness audit script untracked with stale default root. |

## Agent context and remaining work

**(a) Agent context packet — acquisition source state**
- Required reading: this doc; `deploy/acquisition-data-manifest.json`; `deploy/validate_acquisition_runtime.py`; `deploy/restore-acquisition-states.sh` (WS-7 owns deploy; read to trace state flow); primary §4.
- Allowed paths: `data/**`, the backup/audit/receipt scripts; `deploy/acquisition-data-manifest.json` is read-only for WS-3 (WS-7 owns `deploy/**`).
- Tests to run: `node scripts/run-python.cjs -m pytest -q tests/test_rc024_backup_restore.py tests/test_acquisition_runtime_manifest.py`.
- Prohibited: committing state DBs, exports or receipts; running restore/backup against live roots; copying hashes of secrets-bearing artefacts into docs.

**(b) Registry proposal**

| subsystem id | name | owned globs | primary doc | test globs | owner |
|---|---|---|---|---|---|
| `acquisition-source-state` | Acquisition source state (inputs, producer DBs, exports, receipts) | `data/**`, `scripts/{acquisition_state_backup,audit_real_job_data,audit_job_publication_completeness,generate_completeness_sample,write_acquisition_receipt}.py` (file `deploy/acquisition-data-manifest.json` is WS-7's; this doc owns its content description) | this doc (secondary to `05-subsystems/acquisition-and-collectors.md`) | `tests/test_{rc024_backup_restore,acquisition_runtime_manifest,real_job_data_audit,job_completeness_audit}.py` | WS-3 |

**(c) Gap/ticket candidates**
1. WS3-G15: regenerate the data manifest (or a delta) at the current release head as part of the next data release.
2. WS3-G16: decide commit-vs-generate for `data/audit/**` and record it.
3. T11: land `audit_runr_data_readiness.py` with a correct default root.
