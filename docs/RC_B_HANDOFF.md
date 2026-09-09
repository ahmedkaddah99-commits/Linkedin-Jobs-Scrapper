# Chat B runtime handoff

Status: B completed the authorized VPS-local RC-024 backup/restore rehearsal
and RC-026 bounded benchmark against the deployed candidate. The host-local
historical copies, isolated restores, exact-schema validation, single-writer
fencing, fixture replay, customer replay, disk/RAM/RSS/CPU sampling, and local
SQLite contention measurements passed. Full RC-024/026 acceptance remains
pending because the VPS has no approved off-host S3/R2 resources or Turso
staging access, and the acquisition unit exposed a bootstrap permission defect
on the current candidate. B fixed that defect in the final tip below; C must
integrate and deploy it before repeating the acquisition-unit start/restart
gate. No live provider/browser acquisition was run. Conditional RC-031
remains gated.

## Identity and worktree

| Item | Value |
| --- | --- |
| Persistent target | `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview` |
| Target branch | `deployment/render-turso-r2` |
| B worktree | `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview-rc-b-vps-runtime` |
| B branch | `temp/rc-b-vps-runtime` |
| S0/common launch SHA | `b0f47788c1a5d385ae4c3c770d5cd990f586a626` |
| B working-tree policy | clean target/A/C worktrees preserved; edits only here |
| B final immutable tip | `8a87df8f7abb02a46fe0249b391ffe75aa415174` |
| Host candidate measured | `6e9a1e9301ffca644aca916aad6fc8827e4a792d` on `deployment/render-turso-r2` |
| Latest observed target/C tip | `f9417f2286c4d423bbf16ab15e2c90fe36d3f625`; target and C worktrees clean; B's work began from the earlier accepted `c69535f7...` descendant |

The target currently has unrelated dirty work and a different HEAD. It was not
edited. No reset, clean, pull, merge, push, deploy, production migration,
host command, provider request, or live request was performed.

## Ticket status

| Ticket | Status | Evidence/next gate |
| --- | --- | --- |
| RC-023 | Code correction complete on B; host gate found a candidate bootstrap defect; full acceptance pending | `RUNR_SKIP_PROJECT_DOTENV=1` now protects the acquisition boundary and unreadable dotenv files are skipped. Local tests pass. The deployed `6e9a...` candidate still needs C's integrated tip and a clean acquisition-unit start/restart verification. |
| RC-024 | VPS-local historical checkpoint/restore rehearsal complete; full acceptance pending | Host re-checkpoints and isolated restores passed for both roles under `runr-acquisition`; single-writer epoch fencing passed. Off-host upload/download, approved lifecycle policy, replacement-host restore, and reboot recovery remain unverified. |
| RC-025 | A-owned and accepted in C's integrated history; not changed | C records A's `6ab6f31bec0977b6db2435920942a7d885ead66d` integration and the later candidate; B did not modify A's files. |
| RC-026 | VPS bounded offline benchmark complete; staging/provider acceptance pending | Host report at `/srv/runr/rc024-evidence/rc026-vps-benchmark-20260909/report.json`, sampled report at `/srv/runr/rc024-evidence/rc026-vps-benchmark-sampled2-20260909/report.json`, and local SQLite contention evidence at `/srv/runr/rc024-evidence/rc026-sqlite-contention-20260909`. Provider requests, Turso contention/billing, and acquisition/customer overlap remain unverified. |
| RC-031 | Conditional, not started | Requires trigger evidence after RC-024/026/028. |

## Changed files

Runtime code/config:

- `deploy/vps-runtime-contract.json`
- `deploy/acquisition.env.example`
- `deploy/systemd/runr-acquisition-worker.service`
- `deploy/systemd/runr-api.service`
- `deploy/systemd/runr-worker.service`
- `deploy/systemd/runr-frontend.service`
- `deploy/systemd/runr.target`
- `deploy/systemd/runr-journald.conf`
- `deploy/setup.sh`
- `deploy/deploy.sh`
- `deploy/start.sh`
- `scripts/master_linkedin_jobs_catalog.py`
- `scripts/master_employer_jobs_catalog.py`
- `scripts/run_manifested_linkedin.py`
- `scripts/run_manifested_employer.py`
- `deploy/acquisition-data-manifest.json`
- `scripts/acquisition_state_backup.py`
- `scripts/benchmark_acquisition_full_state.py`
- `scripts/benchmark_personalized_jobs.py`

Evidence/tests:

- `tests/test_rc023_vps_runtime.py`
- `tests/test_rc023_producer_state_paths.py`
- `docs/RC023_VPS_RUNTIME.md`
- `docs/RC_B_HANDOFF.md`
- `tests/test_rc024_backup_restore.py`
- `docs/RC024_BACKUP_RESTORE.md`
- `tests/test_rc026_benchmark.py`
- `docs/RC026_BENCHMARK.md`

No secrets, mutable state databases, browser profiles, historical exports,
provider logs, or large datasets are included.

## Contract details

The chosen primary mechanism is systemd. API/customer services run as
`runr`; the acquisition service runs as the separate non-root
`runr-acquisition` account. All units use protected host settings and bounded
CPU/memory/tasks. The acquisition role uses
`/opt/runr/.env.acquisition` and cannot inherit the customer/API
`/opt/runr/.env`; the frontend reads no environment file. The acquisition
worker has explicit input/state/export/backup roots and a stable
`vps_acquisition_worker` identity. The VPS API binds loopback via
`RUNR_API_HOST=127.0.0.1`; no public scraper API is required. Actual
provider/database permission granularity remains a host-side verification
item; shared full-scope credentials are a residual risk until verified.

Python is pinned at setup/deploy boundaries to exactly `Python 3.12.7` and
the venv is invoked as `/opt/runr/.venv/bin/python -m pip`. The shared local
verification interpreter is:

```text
C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe
Python 3.12.7
```

Provider machine identity, region, price/VAT/add-ons, quotas, actual RAM/disk
headroom, Docker availability, and deployed revision are still unknown.

## Producer state/export correction

The four producer entrypoints now accept an optional `--state-dir` (and the
low-level APIs accept `state_dir=`) while preserving the historical default of
placing state beside `--output-dir`. `--require-existing-state` is an explicit
restore guard: it fails before SQLite creation when the required database is
missing. Employer `--export-only` opens the selected state through the existing
schema validation and never falls back to an empty database.

With an explicit state root, SQLite databases and any SQLite sidecars remain
under `/srv/runr/state/{linkedin,employer}`. LinkedIn generations, its
generation-local JSONL journal, pointer, metrics, and compatibility aliases
remain under `/srv/runr/exports/linkedin`; employer materializations remain
under `/srv/runr/exports/employer`. Checkpoint transactions, resume IDs,
immutable generation publication, and single-final-export behavior were not
changed. Existing callers that omit `state_dir` retain their prior paths.

The shared `deploy/acquisition-data-manifest.json` runtime commands now carry
the separate POSIX state and export roots plus `--require-existing-state`.
This is the exact manifest patch C must integrate with the release candidate;
the release commit field was not changed by B.

## RC-024 checkpoint implementation and rehearsal

The new `scripts/acquisition_state_backup.py` is deliberately independent of
the producer modules. It validates the exact 14-table LinkedIn state or the
two-table employer state, opens the source read-only, performs SQLite Online
Backup into a temporary file, removes any temporary WAL/SHM sidecars, hashes
the immutable database and atomically publishes `checkpoint.json`. It records
release/source version, input manifest ID/hash, cycle/shard/high-water marks,
schema, backup method/hash/bytes, bounded retention settings and compact
receipt/identity/absence evidence IDs. Sensitive metadata and browser-profile
keys are rejected.

Off-host preservation uses the existing S3/R2-compatible environment contract
(`S3_ENDPOINT_URL`, `S3_*`, `S3_BUCKET`) and streams the database with
`upload_file`; it is opt-in via `--upload`. The database object is uploaded
before the manifest object, and the manifest is the remote commit record.
Retries accept only an identical immutable object. Remote restore verifies the
manifest object metadata hash, validates the checkpoint database, and restores
only to a new directory. `SingleWriterLease` uses a shared durable ownership
ledger, tokens and epochs so an expired/replaced owner fails immediately before
publication. Local budget and free-space checks pause before unbounded outage
buffering; pruning is limited to generated checkpoints with an off-host
receipt.

Fixture evidence is separate from historical/host evidence. The ten tests
in `tests/test_rc024_backup_restore.py` use synthetic EmployerState,
synthetic/empty current 14-table StateStore, an in-memory remote and a patched
employer collector. They passed with the shared interpreter:

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' --version
# Python 3.12.7
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest -q tests\test_rc024_backup_restore.py
# 10 passed
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m ruff check scripts\acquisition_state_backup.py tests\test_rc024_backup_restore.py
# All checks passed!
```

The adjacent combined regression command passed 122 tests with the known
timing-sensitive limiter test deselected. The same limiter test passed alone
(1 passed in 0.80s); when embedded in the mixed process it once observed a
peak of 1 instead of 2 and failed, so that transient mixed-process result is
retained as a limitation rather than attributed to RC-024.

The test suite also proves an actual employer producer resume from a restored
checkpoint and the no-overwrite/missing-remote/failed-upload boundaries. It
does not prove a real S3/R2 upload, replacement-VPS restore, reboot recovery,
host permissions, lifecycle policy, or provider availability. The verified
external snapshots remain preserved at their recorded source paths and hashes;
none was moved, deleted, modified, or added to Git during this pass. Generated
historical checkpoint copies were written only under the disposable temp root
recorded below.

As a separate historical-source rehearsal, the verified external Employer
snapshot was backed up read-only to
`C:\Users\ahmed\AppData\Local\Temp\runr-rc024-historical-20260909` in
2.17s: 83,841,024 bytes, source SHA-256
`b1eee3b449afd075d9b860f12a5880da6769fcc666473bbfe8f08e7e4cb36737`, backup
SHA-256 `4f779500c9cd5fb66342cb36bd2fd236cefb9b9eebb3caf13876fca8b1265aaf`,
tables `companies`/`jobs`, integrity `ok`. The verified external LinkedIn
snapshot completed the same operation in 183.67s: 3,479,191,552 bytes,
source SHA-256
`26b81012177f40949b6b3ede3187860129db9fdaf3392d2195d78ac050244317`, backup
SHA-256 `adc5c1ab7ac5b7bdca67cdabd7687fdd29913afae188fab2aba4377a41327525`,
exact 14 tables, integrity `ok`. Both generated checkpoints were restored to
the separate `C:\Users\ahmed\AppData\Local\Temp\runr-rc024-historical-restore-20260909`
root in 117.36s; restored hashes matched. Employer export-only then read 2,612
jobs and completed the final export in 8.69s. These are local
historical-source/algorithm results only: no source was moved or deleted, no
S3/R2 upload was attempted, and no VPS/replacement-host/reboot/service-account
acceptance is claimed.

## RC-026 benchmark and cost evidence

The complete offline benchmark is recorded in
`docs/RC026_BENCHMARK.md`. It measured both verified RC-024 state copies, the
bounded employer worker matrix at 1/2/4 company workers, the existing 1,000-job
customer warm path, checkpoint/export wall time, peak RSS/workspace bytes, and
request/cost accounting. The final run used the disposable
`C:\Users\ahmed\AppData\Local\Temp\runr-rc026-benchmark-20260909-v3` root.

Results: LinkedIn 3,479,191,552 B copied in 5.2050s and streamed to a
775,613,386 B CSV in 137.6890s; Employer 83,841,024 B copied in 0.1157s and
exported 2,612 jobs in 4.9885s to 78,134,553 B of CSV/JSONL/metrics. The
fixture matrix preserved 5/5 companies/jobs at every tested concurrency and
observed zero network attempts. Customer replay p50/p95 were 287.28/751.50ms
for Jobs and 63.32/210.37ms for Company detail. External prices, Turso
contention/billing, host headroom, active-acquisition customer overlap, and
provider retry behavior remain unknown by design; no uncapped provider
benchmark or capacity claim was made.

The large LinkedIn export used a read-only row-at-a-time equivalent of
`StateStore.export_catalog_csv` because reopening the full historical copy
entered an unbounded legacy repair scan. The source remained unchanged and no
final artifact was promoted by that stopped attempt. This reopen-path issue is
explicitly retained as an integrated/staging follow-up.

## Commands and results

Executed from the B worktree:

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' --version
# Python 3.12.7

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest -q tests/test_acquisition_runtime_manifest.py tests/test_rc022_build_release_contract.py
# Pre-change baseline: 9 passed in 14.07s

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest -q tests/test_rc023_vps_runtime.py tests/test_acquisition_runtime_manifest.py tests/test_rc022_build_release_contract.py
# Result: 14 passed in 4.56s

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest -q tests/test_rc023_vps_runtime.py tests/test_acquisition_runtime_manifest.py tests/test_rc022_build_release_contract.py tests/test_worker_service.py
# Result: 42 passed, 4 subtests passed in 25.23s

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest -q tests/test_rc023_producer_state_paths.py
# Result: 9 passed in 4.19s

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest -q tests/test_master_linkedin_jobs_catalog.py tests/test_master_employer_jobs_catalog.py tests/test_source_eligibility_manifest.py tests/test_employer_site_fallbacks.py tests/test_rc011_employer_outcomes.py tests/test_rc012_employer_concurrency.py --deselect tests/test_master_linkedin_jobs_catalog.py::test_shared_limiter_gates_actual_account_and_provider_in_flight_work
# Result: 120 passed, 1 deselected in 19.49s

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest -q tests/test_master_linkedin_jobs_catalog.py::test_shared_limiter_gates_actual_account_and_provider_in_flight_work
# Result: 1 passed in 0.97s; timing-sensitive in the larger mixed producer process.

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m ruff check scripts/master_linkedin_jobs_catalog.py scripts/master_employer_jobs_catalog.py scripts/run_manifested_linkedin.py scripts/run_manifested_employer.py tests/test_rc023_producer_state_paths.py
# Result: All checks passed!

& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m py_compile scripts/master_linkedin_jobs_catalog.py scripts/master_employer_jobs_catalog.py scripts/run_manifested_linkedin.py scripts/run_manifested_employer.py tests/test_rc023_producer_state_paths.py
# Result: passed
```

Additional offline checks:

```powershell
bash -n deploy/setup.sh deploy/deploy.sh deploy/start.sh
# Result: passed
git diff --check
# Result: passed
git status --short --branch
# Result before the handoff commit: expected scoped changes only; clean after commit.
```

The pre-change offline checks above did not claim VPS setup, service restart,
port, or synthetic-worker acceptance. The authorized host observations and
the current candidate's acquisition bootstrap failure are recorded below;
post-integration repetition remains required.

## VPS verification and deployed-versus-local distinction

The existing approved SSH setup was reused on 2026-09-09. No firewall,
SSH-hardening, or customer-service setup was repeated. Host observations:

| Item | Observation |
| --- | --- |
| Host | `runr-vps` / `vmd205749`, Ubuntu 24.04.4; `sudo -n whoami` returned `root` |
| Host release | `/opt/runr/.env`: `RUNR_RELEASE_COMMIT=6e9a1e9301ffca644aca916aad6fc8827e4a792d`, branch `deployment/render-turso-r2` |
| Host Python | `/opt/runr/.venv/bin/python` and `/opt/python/3.12.7/bin/python3.12` both report Python 3.12.7 |
| Acquisition account | `runr-acquisition`, non-root; service and benchmark commands ran under that account |
| Role paths | `/srv/runr/shared/inputs` `root:runr-acquisition` 0750; `/srv/runr/state`, `/srv/runr/exports`, `/srv/runr/backups`, and `/var/log/runr/acquisition` `runr-acquisition:runr-acquisition` 0750 |
| Live gate | `/opt/runr/.env.acquisition`: `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED=false`, `RUNR_ACQUISITION_MAX_REQUESTS=0` |
| Service state after rehearsal | acquisition `inactive/dead`, `disabled`; API, frontend, and customer worker `active` |
| Current host limits | `CPUQuota=300%`, `MemoryHigh=9G`, `MemoryMax=12G`, `TasksMax=512` |

The host candidate predates B's final correction. A bounded acquisition-unit
start exposed `PermissionError: [Errno 13] Permission denied: '.env'` while
the worker was auto-restarting (`ExecMainStatus=1`); B stopped it and confirmed
the unit remained disabled and customer services remained active. The final B
tip adds `RUNR_SKIP_PROJECT_DOTENV=1` to the acquisition unit and makes the
dotenv loader skip an unreadable file. That tip is local-only until C
integrates/deploys it; the host was not modified with unaccepted code.

## RC-024 VPS-local backup, restore, and ownership evidence

The verified workstation snapshots were copied to the VPS without moving or
modifying their originals. Destination checkpoint roots are local VPS backup
storage, not off-host preservation:

| Role | Persistent historical checkpoint | Host validation |
| --- | --- | --- |
| Employer | `/srv/runr/backups/rc024-historical-20260909-employer/employer-20260909T085018133133Z-53589d4a53bb` | source SHA `b1eee3b449afd075d9b860f12a5880da6769fcc666473bbfe8f08e7e4cb36737`, checkpoint SHA `4f779500c9cd5fb66342cb36bd2fd236cefb9b9eebb3caf13876fca8b1265aaf`, 2 tables, integrity `ok` |
| LinkedIn | `/srv/runr/backups/rc024-historical-20260909-linkedin/linkedin-20260909T085116426477Z-4b604df8392a` | source SHA `26b81012177f40949b6b3ede3187860129db9fdaf3392d2195d78ac050244317`, checkpoint SHA `adc5c1ab7ac5b7bdca67cdabd7687fdd29913afae188fab2aba4377a41327525`, exact 14 tables, integrity `ok` |

Host-side SQLite Online Backup re-checkpoints were then created and validated
as `runr-acquisition`:

- Employer: checkpoint `employer-20260909T144811797243Z-caa39b4cccba` at
  `/srv/runr/backups/rc024-vps-rehearsal-employer-20260909/employer/...`,
  83,841,024 bytes, SHA
  `12fefe3bd5d8a1a47215b6c203bb065f925b8f372f502667110748a2931a4465`,
  tables `companies/jobs`, `wal_consistent=true`.
- LinkedIn: checkpoint `linkedin-20260909T150049679427Z-8cba2aca442e` at
  `/srv/runr/backups/rc024-vps-rehearsal-linkedin-20260909/linkedin/...`,
  3,479,191,552 bytes, SHA
  `f2032a13637804492cc8e2faa7770bf974bf6298bf10b60d34aaba7ad8eca4f0`,
  exact 14 tables, `wal_consistent=true`.

Isolated restores succeeded to the new, acquisition-owned paths
`/srv/runr/rc024-evidence/restore-employer-20260909` and
`/srv/runr/rc024-evidence/restore-linkedin-20260909`; restored hashes matched
their validated checkpoint hashes and both receipts reported
`require_existing_state=true`. An initial restore to an unwritable sibling of
`/srv/runr` failed closed; no persistent path was loosened.

The epoch-fenced lease rehearsal at
`/srv/runr/rc024-evidence/lease-employer-fencing-20260909` observed active-owner
conflict, renewal, expiry fencing, and epoch advancement 1 to 2. The VPS
rehearsal did not upload to S3/R2: all required S3/R2 environment names were
absent, so no external write/download or off-host acceptance is claimed. A
real reboot was not run because acquisition is intentionally disabled and
customer services are in place; systemd start/restart recovery remains a
pending post-integration gate.

## RC-026 VPS benchmark evidence

The bounded command was run from `/tmp` as the acquisition account so the
current host candidate's unreadable customer dotenv did not interfere with
the isolated benchmark:

```text
sudo -n -u runr-acquisition /opt/runr/.venv/bin/python \
  /opt/runr/scripts/benchmark_acquisition_full_state.py \
  --output-root /srv/runr/rc024-evidence/rc026-vps-benchmark-20260909 \
  --linkedin-checkpoint-dir /srv/runr/backups/rc024-vps-rehearsal-linkedin-20260909/linkedin/linkedin-20260909T150049679427Z-8cba2aca442e \
  --employer-checkpoint-dir /srv/runr/backups/rc024-vps-rehearsal-employer-20260909/employer/employer-20260909T144811797243Z-caa39b4cccba \
  --customer-jobs 1000 --customer-iterations 30 --company-concurrency 1 2 4
```

Report: `/srv/runr/rc024-evidence/rc026-vps-benchmark-20260909/report.json`.
It copied the LinkedIn checkpoint in 8.7278s and streamed 188,206
observations to a 775,613,386-byte CSV in 71.4389s. Employer copied in
0.1569s and exported 2,612 jobs to 78,131,906 bytes in 2.2284s with the final
export completed. Every fixture concurrency value 1/2/4 preserved 5/5 jobs,
with zero network/request attempts. Customer replay (1,000 jobs, 30
iterations) recorded Jobs p50/p95 177.67/223.31ms and Company p50/p95
43.39/53.47ms, with zero network requests.

The process-sampled repeat is at
`/srv/runr/rc024-evidence/rc026-vps-benchmark-sampled2-20260909/report.json`.
Host baseline was 6 vCPUs, 12,541,493,248 bytes RAM, 11,752,128,512 bytes
available, and no swap. Over 97.002s the child used 97.82 CPU seconds
(100.84% of one core; 16.81% of host total), peak RSS/HWM was 87,609,344
bytes, minimum available memory was 11,634,204,672 bytes, and the isolated
tree consumed 4,420,440,064 disk bytes. These are measured VPS observations,
not a production capacity or cost claim.

The direct local-SQLite contention probe at
`/srv/runr/rc024-evidence/rc026-sqlite-contention-20260909` committed all
20/40/80 transactions for 1/2/4 writers, had zero lock errors, and kept one
concurrent write section. `BEGIN IMMEDIATE` p95/max wait was 0.065/0.088ms
for one writer, 0.076/180.143ms for two, and 0.083/630.492ms for four.
This is host-local SQLite only; it is not Turso contention. The evidence
supports keeping the existing bounded fixture maximum of four and not raising
production concurrency without provider/Turso/customer-overlap evidence.

## Producer and scraper verification

After C's accepted integration tip and B's correction, the focused suite ran
with the shared repository interpreter:

```text
Python 3.12.7
160 passed, 4 subtests passed in 47.25s
```

Covered files include both master producers, both manifested wrappers,
RC-009/010/011/012, RC-016/017 immutable-generation behavior, producer state
paths, RC-024 checkpoint/restore, RC-026 benchmark, environment loading, and
VPS runtime contract tests. Ruff passed for the changed Python/config tests.
No live LinkedIn/employer requests, browser demonstration, provider retry
sample, Turso request, or customer-facing staging publication was performed.
The producer acceptance that depends on those resources remains open.

## Handoff to C

1. Integrate immutable B tip
   `8a87df8f7abb02a46fe0249b391ffe75aa415174` after the already accepted
   integration history. It changes only the dotenv loader, acquisition unit,
   and focused tests; no company-identity or historical database files are
   included. Keep the shared manifest and existing C edits intact.
2. Deploy that integrated SHA through the established runtime procedure, then
   repeat the acquisition-unit start/restart/stop rehearsal from `/opt/runr`.
   Confirm no `.env` permission error, live networking remains disabled,
   acquisition is returned to `disabled/inactive`, and API/frontend/customer
   worker remain active. Record the deployed SHA separately from B's tip.
3. Supply the approved isolated S3/R2 bucket/prefix and credential boundary,
   plus any isolated Turso staging resource required for RC-027. Execute
   database-first/manifest-last upload, remote receipt verification, download,
   isolated restore, and resume proof. Until then RC-024 is not fully verified.
4. Integrate the VPS benchmark result before staging execution. Any live
   pilot must use C's frozen caps, one coordinated run, and no duplicate paid
   collection; provider/browser and Turso/customer-overlap results remain
   required for RC-026.
5. Keep RC-031 conditional on measured thresholds. RC-033 owns cleanup of the
   VPS evidence roots and any retained source quarantine; do not delete them
   during integration.

## Rollback

No B correction was deployed to the host, so the deployed runtime remains
`6e9a1e9301ffca644aca916aad6fc8827e4a792d`. If C rejects the correction,
revert commit `8a87df8f7abb02a46fe0249b391ffe75aa415174` in the integration
branch with a normal revert; do not reset or amend B history. If a host trial
has begun, stop/disable acquisition and prevent new claims before restoring
the prior accepted unit/release. Leave `.env*`, `/var/lib/runr`, `/srv/runr`,
backups, journals, and all immutable evidence intact.

For state recovery, validate the selected checkpoint, restore only to a new
acquisition-owned directory, verify SHA/schema/receipt, and resume with the
explicit state path. Never overwrite a newer state with an older restore or
delete the verified source snapshot. B is frozen at the final documentation
tip below; C may integrate the immutable commits sequentially.

Prior runtime/evidence commit SHA: `e7c70a9b52c1d839ee3df24c63efced106d7d18a`.
Producer state/export correction SHA: `d14332db57c06d2021e4e41c240d8727e5f212da`.
RC-024 implementation/evidence SHA: `6e315b9324e4ba2fb1b2ffbb42592fe55d01c610`.
RC-026 implementation/evidence SHA: `61d204ce53ab02060514409b6ef7514846d2d133`.
Final B correction SHA: `8a87df8f7abb02a46fe0249b391ffe75aa415174`.
Final B documentation tip: verify with `git rev-parse HEAD` after this commit.
