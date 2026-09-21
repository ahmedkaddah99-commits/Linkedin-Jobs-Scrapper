> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14
> Updated by T44 (RUN-44, 2026-09-19): added the scheduled off-host backup service and timer; WS7-G11 closed in §10.

# VPS runtime and acquisition timers

This is a secondary WS-7 doc. Release records, evidence classes and C1–C3 are in [release-process-and-production-records.md](release-process-and-production-records.md).

The collector and publisher **scripts** under `scripts/` are WS-3's and are documented in `../05-subsystems/acquisition-and-collectors.md` and `../05-subsystems/publication-and-catalog.md`. Producer state and exports are in `../03-data/acquisition-source-state.md`.

No host was contacted for this doc. Everything below describes the files at `58a96674`. Which units are installed or enabled on the VPS is **UNKNOWN** (U2).

## 1. Purpose

The VPS is the acquisition plane. It runs:
- bounded LinkedIn and employer-site collectors
- a producer-state publisher that writes the shared Turso catalog
- a CSV export

It can also host the API, the customer worker and the static frontend, but the recorded production API is on Render. The primary mechanism is systemd (`deploy/vps-runtime-contract.json:3`). PM2 (`ecosystem.config.cjs`) is an unrelated developer mechanism (U9).

## 2. Owned paths

`deploy/` has 29 files:

| Group | Files |
|---|---|
| systemd units | `deploy/systemd/` has 18 files: 10 services, 6 timers, `runr.target`, `runr-journald.conf` |
| Wrappers | `deploy/run-acquisition-source.sh` (128 lines), `deploy/run-acquisition-publisher.sh` (75), `deploy/run-acquisition-cycle.sh` (53) |
| Operator scripts | `deploy/setup.sh` (117), `deploy/deploy.sh` (47), `deploy/restore-acquisition-states.sh` (74), `deploy/start.sh` (85; shared with Render) |
| Contracts and templates | `deploy/vps-runtime-contract.json` (88), `deploy/acquisition-data-manifest.json` (340), `deploy/acquisition.env.example` (59) |
| Validator | `deploy/validate_acquisition_runtime.py` (170) |

`backend/static_server.py` (55) is also WS-7's.

## 3. Units and timers

All paths are under `deploy/systemd/`. Every service sets `UMask=0077`, `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=strict`, `ProtectHome=true`, `ProtectKernelTunables/Modules/ControlGroups=true`, `RestrictSUIDSGID=true`, `LockPersonality=true` and `RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6`.

| Unit | Type | User | ExecStart | Env files / key env | Timeout (start) | CPU / MemHigh / MemMax / Tasks | ReadWritePaths | `[Install]` | `PartOf=runr.target` |
|---|---|---|---|---|---|---|---|---|---|
| `runr-api.service` | simple, `Restart=always` | `runr` | `deploy/start.sh api` (L17) | `/opt/runr/.env`; `RUNR_API_HOST=127.0.0.1` (L16); data `/var/lib/runr/api-data` | default | 200% / 3G / 4G / 256 | `/var/lib/runr` | none | yes |
| `runr-worker.service` | simple, always | `runr` | `deploy/start.sh worker` (L19) | `.env`; `WORKER_ROLE=customer`, `WORKER_ID=vps_customer_worker` (L17–18); `After=runr-api.service` | default | 300% / 9G / 12G / 512 | `/var/lib/runr`, `/var/log/runr/customer` | none | yes |
| `runr-frontend.service` | simple, always | `runr` | `.venv/bin/python backend/static_server.py` (L13) | none | default | 100% / 384M / 512M / 128 | none | none | yes |
| `runr-acquisition-worker.service` | simple, always | `runr-acquisition` | `deploy/start.sh acquisition` (L29) | `.env.acquisition`; `WORKER_ROLE=acquisition`; `RUNR_ACQUISITION_SCHEDULER_DISABLED=true` (L28) | default | 300% / 6G / 9G / 512 | `/var/lib/runr`, `/srv/runr/{state,exports,backups}`, `/var/log/runr/acquisition` | `WantedBy=multi-user.target` | yes |
| `runr-acquisition-linkedin.service` | oneshot | `runr-acquisition` | `run-acquisition-source.sh linkedin` (L19) | `.env.acquisition` + optional `-.env.acquisition.provider`; **`RUNR_ACQUISITION_LIVE_NETWORK_ENABLED=true` (L17)** | **2h** (L26) | 250% / 6G / 9G / 384 | `/var/lib/runr`, `/srv/runr/{state,exports,backups}` | multi-user | yes |
| `runr-acquisition-employer.service` | oneshot | `runr-acquisition` | `run-acquisition-source.sh employer` (L19) | same; **live network true (L17)** | **2h** (L26) | 250% / 6G / 9G / 384 | same | multi-user | yes |
| `runr-acquisition-publisher.service` | oneshot | `runr-acquisition` | `run-acquisition-publisher.sh` (L16) | `.env.acquisition` only (no provider file) | **12h** (L23) | 200% / 4G / 6G / 256 | same | multi-user | yes |
| `runr-acquisition-cycle.service` | oneshot | `runr-acquisition` | `run-acquisition-cycle.sh` (L25) | `.env.acquisition` + provider; roots set explicitly (L17–24); **no** live-network override | **infinity** (L32) | 300% / 6G / 9G / 512 | same | multi-user | yes |
| `runr-acquisition-export.service` | oneshot | `runr-acquisition` | `.venv/bin/python scripts/build_master_jobs_catalog.py --linkedin-csv … --employer-csv … --output …/combined/master_jobs.csv` (L19–22) | `.env.acquisition`; **`After=` + `Wants=runr-acquisition-cycle.service` (L3–4)** | default (disabled for oneshot) | 100% / 2G / 3G / 64 | `/srv/runr/exports` | **none** | **no** |
| `runr-acquisition-backup.service` (T44) | oneshot | `runr-acquisition` | `.venv/bin/python scripts/acquisition_state_backup.py scheduled-backup --role linkedin …` then `--role employer …` with `--upload` (two `ExecStart=` lines, fail-fast) | `.env.acquisition`; `${RUNR_LINKEDIN_STATE_DB}`, `${RUNR_EMPLOYER_STATE_DB}`, `${RUNR_ACQUISITION_BACKUP_ROOT}`, `${RUNR_ACQUISITION_DATA_MANIFEST}` | **4h** | 200% / 4G / 6G / 256 | `/srv/runr/state`, `/srv/runr/backups` | multi-user | yes |

| Timer | `OnCalendar` (host clock; "UTC" per `da565e94`) | `RandomizedDelaySec` | `Persistent` | Unit |
|---|---|---|---|---|
| `runr-acquisition-linkedin.timer` | `*-*-* 02:00:00` | 300 | true | linkedin.service |
| `runr-acquisition-cycle.timer` | `*-*-* 02:00:00` | 300 | true | cycle.service |
| `runr-acquisition-employer.timer` | `*-*-* 02:30:00` | 300 | true | employer.service |
| `runr-acquisition-publisher.timer` | `*-*-* 04:00:00` | 300 | true | publisher.service |
| `runr-acquisition-export.timer` | `*-*-* 06:00:00` | 300 | true | (implicit) export.service |
| `runr-acquisition-backup.timer` (T44) | `*-*-* 05:00:00` | 300 | true | backup.service |

The backup timer sits between the publisher (04:00) and the export timer (06:00). `setup.sh` enables it directly (`systemctl enable --now runr-acquisition-backup.timer`); it is **not** a member of `runr.target`'s `Wants=` so a failed backup unit never silently drops out of `systemctl list-timers`.

**`runr.target`** (L3–4) `Wants=` and `After=`:
- `runr-api.service`
- `runr-worker.service`
- the linkedin, employer and publisher timers
- `runr-frontend.service`

It **excludes** `runr-acquisition-worker.service` (removed by `b12c69dd`), the cycle timer and the export timer.

**`runr-journald.conf`:** `SystemMaxUse=1G`, `RuntimeMaxUse=256M`, `MaxRetentionSec=14day`, `ForwardToSyslog=no`. `setup.sh:99` installs it as `/etc/systemd/journald.conf.d/runr.conf`.

## 4. Inputs, outputs, dependencies

**Host layout** (`vps-runtime-contract.json:33–40`, `setup.sh:45–57`):

| Path | Owner |
|---|---|
| app `/opt/runr` | — |
| `/var/lib/runr/{api-data,customer-data}` | `runr` |
| `/var/lib/runr/acquisition-data` | `runr-acquisition` |
| `/srv/runr/{state,state/locks,exports,exports/receipts,backups}` | `runr-acquisition` |
| inputs `/srv/runr/shared/inputs` | `root:runr-acquisition` 0750 |
| logs | journald plus `/var/log/runr/{customer,acquisition}` |

**Environment boundary:**
- `/opt/runr/.env` is `root:runr` 0640 and serves the API and customer roles.
- `/opt/runr/.env.acquisition` is `root:runr-acquisition` 0640 (`setup.sh:59–70`).
- `/opt/runr/.env.acquisition.provider` is optional, holds provider credentials, and is loaded only by the linkedin, employer and cycle units.
- The contract forbids the secret families `CLERK_`, `CREEM_`, `TRACKER_GOOGLE_OAUTH_` and `DEEPSEEK_` in the acquisition role (L69–74).

`deploy/acquisition.env.example` variable names:

| Group | Names |
|---|---|
| Runtime and database | `RUNR_ENV`, `DATABASE_BACKEND`, `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `RUNR_STORAGE_BACKEND`, `RUNR_DATA_DIR` |
| Acquisition paths | `RUNR_ACQUISITION_{MANIFEST,STATE_ROOT,EXPORT_ROOT,RECEIPT_ROOT,LOCK_ROOT}`, `RUNR_{LINKEDIN,EMPLOYER}_STATE_{DIR,DB}`, `RUNR_LINKEDIN_{PAGINATION,FILTERS}_REPORT`, `RUNR_COMPANY_IDENTITY_CROSSWALK`, `RUNR_ACQUISITION_INCLUDE_SINGLE_SOURCE`, `RUNR_SOURCE_VERSION` |
| Object storage | `OBJECT_STORAGE_BACKEND`, `S3_*` |
| Providers | `SCRAPEOPS_API_KEY`, `WEBSHARE_PROXY_{URL,USERNAME,PASSWORD}` |
| Switches and caps | `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED=false` (L39), `RUNR_ENABLE_LIVE_NETWORKING_DISCOVERY=false`, caps `RUNR_ACQUISITION_MAX_REQUESTS=110`, `RUNR_LINKEDIN_MAX_REQUESTS=100`, `RUNR_EMPLOYER_MAX_REQUESTS=10` (L43–46), `RUNR_SOURCE_RUN_TIMEOUT_SECONDS=900` (L44) |
| Concurrency | LinkedIn and employer concurrency knobs (L47–54) |
| Enrichment | **`RUNR_COMPANY_ENRICHMENT_ENABLED=1`**, `RUNR_COMPANY_ENRICHMENT_{PROVIDER=webshare_linkedin,MAX_COMPANIES,CONCURRENCY,REQUEST_BUDGET}` (L55–59) |

**`deploy/vps-runtime-contract.json`** (schema `runr.vps-runtime.v1`):
- release: branch, `commit` `9ba1d551` (L6), `migration_owner: api-pre-deploy-only`, `dependency_lock: requirements-linux.txt`
- host: Python 3.12.7, chrony, `public_scraper_api: false`, `inbound_ports: []` (L21–22)
- roles: api `runr-api.service` bound to 127.0.0.1; customer `runr-worker.service`; acquisition `unit: runr-acquisition-worker.service` (L53) with `collector_units` = the linkedin, employer and publisher timers (L54–58), entrypoints (L59–63), `state_restore_entrypoint` (L64), `active_state_root: /srv/runr/state/active` (L65)
- retention: L81–87
- placeholders: C9 (L12, L29, L30–31)

**`deploy/acquisition-data-manifest.json`** (schema `runr.acquisition.data-manifest.v1`, `release_commit` `9ba1d551` L4):
- policy flags L6–11
- server roots L12–16
- seed inputs: the three `data/acquisition/inputs/*.csv` files (repo paths, sizes, SHA-256), plus LinkedIn evidence reports
- state snapshots
- code-file hashes for `scripts/*` and `deploy/*` (~L203–330)
- The inputs are WS-3's (N-3).

## 5. Call graph (wrappers → scripts; resolves U13)

```
runr-acquisition-{linkedin|employer}.service
 └─ deploy/run-acquisition-source.sh <src>
     ├─ validate caps positive + source_cap+other_cap ≤ total (L46–55)   exit 64 on violation
     ├─ flock -n $lock_root/<src>.lock (L57–63)                           exit 75 if held
     ├─ python deploy/validate_acquisition_runtime.py --manifest deploy/acquisition-data-manifest.json
     │        --role <src> --allow-state-drift  > receipts/<src>-validation.json (L72–77)
     ├─ if valid: timeout --foreground $RUNR_SOURCE_RUN_TIMEOUT_SECONDS(900) python
     │        linkedin: scripts/run_manifested_linkedin.py --manifest --output-dir exports/linkedin --state-dir
     │                  --require-existing-state --pagination-report --filters-report --mode daily
     │                  --workers 10 --detail-workers 5 --per-proxy-concurrency 1 --max-requests 100 --max-companies 25 (L82–95)
     │        employer: scripts/run_manifested_employer.py --manifest --output-dir exports/employer --state-dir
     │                  --require-existing-state --limit 10 --max-requests 10 (L99–106)
     └─ python scripts/write_acquisition_receipt.py --source <src> --status --exit-code … --release-commit $RUNR_SOURCE_VERSION (L117–126)
        exit <collector exit code>

runr-acquisition-publisher.service
 └─ deploy/run-acquisition-publisher.sh
     ├─ flock -n publisher.lock (L16–21), then linkedin.lock (L25–29) and employer.lock (L30–34)  exit 75 if a collector runs
     ├─ python scripts/publish_producer_states.py --manifest --linkedin-state --employer-state --data-dir
     │        --source-version [--identity-crosswalk] [--skip-status-only] (L51–59)
     └─ scripts/write_acquisition_receipt.py --source publisher (L64–73)

runr-acquisition-cycle.service (legacy combined)
 └─ deploy/run-acquisition-cycle.sh
     ├─ caps 110/100/10 check (L6–25)
     ├─ run-acquisition-source.sh linkedin; … employer; run-acquisition-publisher.sh (L27–34; failures collected)
     ├─ if both CSVs non-empty: scripts/build_master_jobs_catalog.py → exports/combined/master_jobs.csv (L39–49)
     └─ exit 1 if any step failed (L51–53)

runr-acquisition-export.service
 └─ scripts/build_master_jobs_catalog.py (direct; no non-empty check, unlike the cycle wrapper)

runr-acquisition-backup.service (T44)
 └─ .venv/bin/python scripts/acquisition_state_backup.py scheduled-backup (twice: linkedin, then employer)
     ├─ create_checkpoint: read-only source, SQLite Online Backup API, no WAL/SHM sidecars
     ├─ input manifest = sha256 of deploy/acquisition-data-manifest.json (validated input contract of the generation)
     ├─ preserve_checkpoint_off_host: database object uploaded first, checkpoint manifest last
     └─ prune_local_checkpoints(apply): removes only generations with a verified off-host receipt;
        keeps at least two verified generations (defaults: local 3, remote 7)

deploy/restore-acquisition-states.sh (operator)
 ├─ refuse non-symlink active path or existing release dir (L21–32); flock canonicalize.lock (L34–39)
 ├─ validate_acquisition_runtime.py --role all --allow-state-drift --require-table-counts (L44–49)
 ├─ scripts/canonicalize_producer_states.py --registry inputs/company_registry_canonical.csv … --output-dir versions/<id> (L52–56)
 ├─ symlink linkedin/employer DBs; atomic `mv -Tf` of state/active (L58–67)
 └─ `rollback` subcommand: atomically re-points `active` at the most recent other
    `versions/<release>` dir (newest by mtime, excluding the current target) under the same
    canonicalize.lock; never deletes any generation; exits 1 when no previous release exists

Pre-mutation evidence: `deploy/validate_acquisition_runtime.py --role all --evidence-report <path>`
writes a read-only report (`runr.acquisition.pre-mutation-evidence.v1`) with the declared release
SHA, exact unit `ExecStart` commands, environment names only (values dropped), state-override
variable names, active symlink target, database size/SHA-256/schema/row counts, and the rollback
target. The T45 activation contract also enforces per-table row counts at restore time via
`--require-table-counts` (e.g. LinkedIn `jobs`/`job_company_observations` = 188,206, employer
`jobs` = 2,612, `companies` = 428 before any activation).

runr-acquisition-worker.service → deploy/start.sh acquisition → workspace_runner.py run-worker --worker-role acquisition
   (legacy source scheduler disabled by env; see ../01-architecture/backend-workers-and-orchestration.md)
```

`deploy/validate_acquisition_runtime.py`:
- Read-only: it checks seed-input size and SHA-256 plus the SQLite table set (`_validate_state` L80–114).
- `--deep` adds `PRAGMA integrity_check` and a state hash.
- It remaps server roots through `RUNR_ACQUISITION_{INPUT,STATE,EXPORT,BACKUP}_ROOT` (L22–27).
- Roles: `linkedin`, `employer`, `enrichment`, `all` (L157).

## 5a. Producer health telemetry (T39)

Bounded telemetry rides on the existing receipt pipeline; no payload capture, no secrets, no unbounded cardinality.

- `runr.producer.telemetry.v1` — `scripts/run_manifested_linkedin.py`, `scripts/run_manifested_employer.py` and `scripts/publish_producer_states.py` emit a `telemetry` object inside their JSON metrics: fixed allowlisted keys only (`schema_version`, `source`, `emitted_at`, `source_version`, `resource_peaks`, `reason_code`; publisher adds per-source `checkpoint_age_seconds`, `stale_checkpoint`, `publish_lag_seconds`, `last_cycle_id`, `last_publication_id`). `resource_peaks` uses `getrusage` (`max_rss_bytes`, `cpu_seconds`) when `resource` is available, else `null`. The wrappers embed the whole metrics object into the receipt, so telemetry reaches `receipts/<name>-latest.json` without touching `write_acquisition_receipt.py`.
- `deploy/run-acquisition-source.sh` and `deploy/run-acquisition-publisher.sh` additionally write `receipts/<name>-latest-telemetry.json` with a classified `reason_code`: `ok`, `lock_overlap` (exit 75), `stall_timeout` (124/137), `validation_failed`, `failed`. Values are sanitized (`tr -d '"\'`); the file is overwritten per run.
- Retention: one latest receipt, metrics and telemetry file per source (`-latest` naming); journald caps remain `SystemMaxUse=1G`, `MaxRetentionSec=14day` (`runr-journald.conf`). Older receipts are not appended.
- Redaction: telemetry carries counts, IDs, timestamps and resource peaks only — no job payloads, no env values, no provider credentials; `release_commit` comes from `RUNR_SOURCE_VERSION`/`RUNR_RELEASE_COMMIT`.
- Staleness threshold: `RUNR_TELEMETRY_STALE_CHECKPOINT_SECONDS` (publisher default `86400`, set in `runr-acquisition-publisher.service`); a missing/never-written checkpoint is always `stale_checkpoint: true`.
- Fixture/VPS dry-run: `scripts/run_manifested_linkedin.py --dry-run` (and the employer variant) emits telemetry without provider credentials; the WSL wrapper tests prove receipts and telemetry survive validation failure and lock overlap.

## 6. Invariants, contradictions and failure handling

**Invariants (SOURCE):**
- Non-root service users.
- Collectors are mutually excluded per source by `flock`, and the publisher waits on both source locks. A busy lock exits 75, which systemd records as a unit failure because no `SuccessExitStatus` is set (WS7-G7).
- Caps fail closed when unset, zero, or when the per-source sum exceeds the total (`ab1a6a32`).
- A per-run watchdog (`timeout 900`, from `5a7f9627`) sits inside the unit's 2h `TimeoutStartSec`.
- The combined CSV is never built from a single source in the cycle wrapper (L36–38 comment).

**C4 (live network).** The handoff (L31) says the flag was reset to `false`, and `acquisition.env.example:39` has `false`. At the baseline, however, the linkedin and employer units hard-set `true`. Unit `Environment=` lines are applied after `EnvironmentFile=`. The cycle unit does **not** override the flag, so a cycle run inherits `.env.acquisition`.

**C5 (timer ownership).** Four sources disagree:

| Source | Claim |
|---|---|
| Handoff (L27–28, 2026-09-11) | owner = `runr-acquisition-cycle.timer`, enabled |
| `setup.sh:103–106` (comment and command) | disables the cycle timer ("legacy combined timer must not compete") |
| Untracked 2026-09-12 report L45–46 | legacy combined timer disabled; independent linkedin, employer and publisher timers enabled |
| Contract | lists only the three independent timers |

The SOURCE and the newest record agree on independent timers. If both were enabled, the cycle and linkedin timers would fire at 02:00 and contend on `linkedin.lock`, and the loser would exit 75. The host state is UNKNOWN (U2).

**C6 (acquisition worker).** The handoff (L29) says disabled, and `b12c69dd` dropped the unit from `runr.target`. But:
- `setup.sh:88` still installs it.
- Its `[Install]` is `WantedBy=multi-user.target`.
- The contract still names it as `roles.acquisition.unit` (L53).
- `tests/test_rc023_vps_runtime.py:99` still asserts that it is in the target (WS7-G1).

**N-5 (export → cycle).**
- `runr-acquisition-export.service` has `Wants=` and `After=runr-acquisition-cycle.service`. Starting the export (for example from the 06:00 export timer) therefore also starts a full combined cycle (collectors, publisher and combined CSV) unless the cycle already ran and is inactive. Because the cycle is a oneshot without `RemainAfterExit`, it would be started again.
- This bypasses the `setup.sh` intent to disable the cycle.
- Mitigation in the tree: `setup.sh` installs neither `runr-acquisition-export.service` nor its timer (unit copies L86–98). The export path is active only if an operator copies the units by hand (WS7-G4).

**Caps: source defaults vs recorded values.**

| Source | Total | LinkedIn | Employer |
|---|---|---|---|
| `acquisition.env.example:43–46` and `run-acquisition-{cycle,source}.sh` defaults | 110 | 100 | 10 |
| Handoff L32 ("effective bounded caps") | 12 | 6 | 6 |
| 2026-09-12 report L97 ("requests: 100") | — | 100 in a LinkedIn run | — |

The handoff numbers are host overrides from the 2026-09-10/11 pilot and are superseded by the later record. The current host values are UNKNOWN.

**Enrichment (WS7-G8).** The handoff (L33) says `RUNR_COMPANY_ENRICHMENT_ENABLED=0`. `acquisition.env.example:55` sets `1` with provider `webshare_linkedin`, and the 2026-09-12 report (L77–78) describes VPS enrichment via Webshare. No systemd unit runs enrichment explicitly; which process does is WS-3's question.

**U8 (reverse proxy).**
- `git grep -il "nginx\|caddy" 58a96674` matches only data CSVs. There is no proxy config in the tree, and `setup.sh:20–21` installs no proxy.
- The API binds `127.0.0.1` and the contract says `inbound_ports: []`.
- `backend/static_server.py:8` hard-codes `HOST = "0.0.0.0"` on port 3000 (L9), so `runr-frontend.service` listens on all interfaces. The contract relies on a host firewall that the repo does not describe (WS7-G9).
- U8 is narrowed to host inspection only.

**U9 (PM2).**
- `ecosystem.config.cjs` defines `runr-api`, `runr-worker` (`--worker-id local_worker`) and `runr-frontend` (static_server, `PORT=3000`), all via `scripts/run-python.cjs`, which looks for `.venv`.
- Only root `package.json` `pm2:*` scripts reference it.
- No systemd unit, deploy script or the contract (`primary_mechanism: systemd`) uses PM2.
- Production use is UNKNOWN; the repo shows none.

**Backups (RC-024, closed by T44).**
- `scripts/acquisition_state_backup.py` (WS-3) provides these CLI subcommands: backup via the SQLite Online Backup API, optional R2 upload with the manifest last, validate, restore, remote-restore, prune with epoch-fenced leases, plus the T44 additions `scheduled-backup` (create + upload + prune in one command), `preserve-recovery-set` and `verify-recovery-set` (versioned off-host preservation of the 2026-09-19 recovered asset set).
- **`runr-acquisition-backup.service` + `.timer` now invoke it** (05:00 daily, after the publisher, before the export timer; installed and enabled by `setup.sh`). Pruning only removes generations with a verified off-host receipt and retains at least two verified generations. A failed upload leaves the local checkpoint without a receipt for retry; the unit reports failure through its exit code and journald (T44; WS7-G11 closed).
- The one-time 2026-09-19 recovered-set preservation (13 files, 4,915,180,506 bytes) is an operator command, not a timer: `preserve-recovery-set --manifest data/audit/runr_source_state/2026-09-19/offhost_preservation_manifest.json --recovery-root <recovery root> --upload`, then `verify-recovery-set --manifest … --download-dir <isolated dir>` for the isolated restore drill. Runbook and receipt: `data/audit/runr_source_state/2026-09-19/`.
- The restore path is `deploy/restore-acquisition-states.sh`.
- The contract forbids browser profiles in backups (L86).

**Deploy and setup.**
- `setup.sh` requires the repo at `/opt/runr` (L11–16), Python 3.12.7 (L22–31) and both env files (L33–36).
- It then creates the users, installs the venv, requirements and Playwright, runs `npm install` in `frontend/` (not `ci`, and no build), copies the units, disables the cycle timer and enables `runr.target`.
- `deploy.sh` reinstalls requirements and Playwright and restarts `runr.target`. That restart touches only the target's members: timers are restarted, but oneshot collectors are not run immediately except through `Persistent=` catch-up.

## 7. Tests and safe verification commands

| Test | Covers |
|---|---|
| `tests/test_rc023_vps_runtime.py` | contract keys (L15–26), acquisition env boundary (L29–43), hardening (L46–69), setup/deploy/start pins (L72–89), journald and target (L92–99, **stale assertion**); T44: backup unit/timer/setup/contract/env assertions |
| `tests/test_acquisition_runtime_manifest.py` | `validate_manifest` seed/state validation and drift rejection |
| `tests/test_rc024_backup_restore.py` | checkpoint, restore, lease and prune (script level); T44: scheduled backup, recovery-set preservation, isolated verify drill |
| `tests/test_production_completion_regressions.py` | reads `deploy/run-acquisition-source.sh` |

Not executed in Phase 2 (offline; no host):
```
.venv\Scripts\python.exe -m pytest -q tests/test_rc023_vps_runtime.py tests/test_acquisition_runtime_manifest.py tests/test_rc024_backup_restore.py
git show 58a96674:deploy/systemd/runr.target
git show 58a96674:deploy/systemd/runr-acquisition-export.service | grep -n "Wants\|After"
git grep -n "runr-acquisition-export" 58a96674 -- deploy/setup.sh      # expect no match
sh -n deploy/run-acquisition-source.sh deploy/run-acquisition-publisher.sh deploy/run-acquisition-cycle.sh
# host-side (owner only, read-only): systemctl list-timers 'runr-*'; systemctl is-enabled runr-acquisition-cycle.timer runr-acquisition-worker.service
```

## 8. History (`git log --oneline 58a96674 -- deploy`, selected)

| Commit | Subject |
|---|---|
| `b4f8147f` / `e7c70a9b` | prepare systemd VPS contract / isolate acquisition service account |
| `6e9a1e93`, `8a87df8f` | worker log paths; acquisition dotenv boundary (`RUNR_SKIP_PROJECT_DOTENV=1`) |
| `6e315b93` | add RC-024 checkpoint restore drills (tests) |
| `da565e94` | move acquisition to VPS role and pin 24h UTC schedule (adds export service and timer) |
| `d9ec8a57`, `ab1a6a32`, `ac79d936` | per-source state paths; fail closed when caps unset; provider credentials for cycle |
| `d44d3c0f` | restore canonical publication chain |
| `a35a5e8c` | pin integrated acquisition contract (`9ba1d551`) |
| `b12c69dd` | keep legacy acquisition worker disabled (target change) |
| `f0002bac`, `41b7179a` | validate data manifest in restore and before source runs |
| `c85f7275` | enable bounded live acquisition services (live network true; timeout 2h) |
| `963c8f21` | separate scraper completion from publisher start (removed `ExecStartPost`) |
| `3514ad92`, `5a7f9627`, `7f75275e` | employer wrapper CLI; finite watchdog; accept scheduled state schemas |

## 9. Status

| Capability | Classification |
|---|---|
| Hardened non-root systemd units with resource limits | VERIFIED (scope: static — all 10 services read; directives listed in §3) |
| Independent daily source and publisher timers in `runr.target` | VERIFIED (scope: static — `runr.target:3`, timer `OnCalendar` lines) |
| Per-source locking, fail-closed caps, watchdog, receipts | VERIFIED (scope: static — wrapper lines cited in §5) |
| Pre-run data-manifest validation | VERIFIED (scope: static — `run-acquisition-source.sh:72–77` → `validate_acquisition_runtime.py:validate_manifest`) |
| Combined cycle timer | RETIRED/HISTORICAL (disabled by `setup.sh:106`; unit kept for compatibility) |
| Export service/timer | PARTIAL (defined, but not installed by `setup.sh`; pulls in the cycle, N-5) |
| Long-lived acquisition worker | PARTIAL (installed but outside the target; scheduler disabled; contract and test still reference it) |
| State restore with atomic switch | IMPLEMENTED-UNVERIFIED |
| Scheduled off-host backups | IMPLEMENTED (T44: `runr-acquisition-backup.service`/`.timer` at 05:00 daily; upload before manifest; receipt-gated pruning keeps ≥2 verified generations; host schedule enablement is U2 scope) |
| VPS-hosted API/customer worker/frontend | IMPLEMENTED-UNVERIFIED (Render is the recorded public API) |
| PM2 process management | UNKNOWN (U9) |

### Deployment evidence (documentary only)

- **Handoff** (DOC-TRACKED, 2026-09-11): VPS marker `5dfdd106` (L12); cycle timer enabled (L28); acquisition worker disabled (L29); live network false (L31); caps 12/6/6 (L32); enrichment 0 (L33). Host name and state-directory hashes not reproduced.
- **2026-09-12 report** (DOC-UNTRACKED): release `4a1b1df5` (L7–8); independent timers enabled and legacy cycle disabled (L45–46); acquisition worker, customer worker, API and frontend "left running" (L47–48); LinkedIn receipt with 100 requests (L94–106).
- **Contract** `release.commit` `9ba1d551`.

## 10. Gaps

| ID | Item |
|---|---|
| C4 | Live network hard-set `true` in the linkedin/employer units vs handoff `false` |
| C5 | Timer ownership: handoff cycle timer vs source and report independent timers; 02:00 collision if both enabled |
| C6 | Acquisition worker disabled/outside target, but still installed, named in the contract and asserted by the test |
| C9 | Contract placeholders (see primary) |
| N-5 | Export `Wants=`/`After=` cycle; caps 110/100/10 (source) vs 12/6/6 (handoff) |
| U2 | Enabled units and release on the host |
| U8 | Reverse proxy / public exposure: none in tree; host-only question |
| U9 | PM2 use |
| U13 | Wrapper call graph: **resolved** here (§5) |
| WS7-G1 | `test_rc023_vps_runtime.py:99` stale target assertion |
| WS7-G4 | `setup.sh` omits the export units; `deploy.sh` never reinstalls units |
| WS7-G7 | Lock-busy exit 75 marks oneshot units failed (no `SuccessExitStatus=75`) |
| WS7-G8 | VPS enrichment enabled in the env example vs handoff "disabled"; no unit owns enrichment explicitly |
| WS7-G9 | `static_server.py` binds `0.0.0.0` vs contract `inbound_ports: []` |
| WS7-G10 | Export service lacks the cycle wrapper's both-CSVs-present guard |
| WS7-G11 | No scheduled backup unit — **closed by T44** (`runr-acquisition-backup.service`/`.timer`, `setup.sh` enables the timer, `scheduled-backup` CLI) |

## Agent context and remaining work

- **Read:** `deploy/systemd/*`, the three wrappers, `deploy/setup.sh`, `deploy/deploy.sh`, `deploy/vps-runtime-contract.json`, `deploy/acquisition.env.example`, `tests/test_rc023_vps_runtime.py`; WS-3 docs for `scripts/`.
- **Allowed:** `deploy/**`, `backend/static_server.py`, `ecosystem.config.cjs`.
- **Tests:** `tests/test_rc023_vps_runtime.py`, `tests/test_acquisition_runtime_manifest.py`, `tests/test_rc024_backup_restore.py`, `tests/test_production_completion_regressions.py`; `sh -n` on the wrappers.
- **Prohibited:**
  - no running wrappers or `setup.sh`/`deploy.sh`
  - no enabling live network, the cycle or export timers, or the acquisition worker without an owner decision
  - no host identifiers or state hashes in the repo
  - no provider calls
- **Registry:** part of `deployment-release-ci` (primary doc).
- **Ticket candidates:**
  1. Decide C5/C6: delete or retire the cycle unit and the acquisition worker, update the contract and `test_rc023`.
  2. Remove export `Wants=`/`After=` on the cycle (or point it at the publisher), install it in `setup.sh` or delete it (N-5, WS7-G4).
  3. `SuccessExitStatus=75` for the collectors and publisher (WS7-G7).
  4. Bind `static_server.py` to a configurable host, defaulting to loopback on the VPS (WS7-G9).
  5. ~~Add a backup timer or record that backups are manual (WS7-G11).~~ Done by T44 (RUN-44).
  6. Reconcile the enrichment switch with WS-3 (WS7-G8).
