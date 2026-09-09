# Chat B runtime handoff

Status: RC-023 offline preparation and producer state/export correction are
complete on B. RC-024 offline implementation and fixture rehearsal are
complete on B. RC-026 offline benchmark implementation and comparable local
state evidence are complete on B. The authorized host phase was attempted
against INT-1's accepted candidate but is access-blocked before mutation;
deployed/full VPS, off-host backup/restore acceptance, and the authorized
staging benchmark remain pending. Conditional RC-031 remains gated.

## Identity and worktree

| Item | Value |
| --- | --- |
| Persistent target | `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview` |
| Target branch | `deployment/render-turso-r2` |
| B worktree | `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview-rc-b-vps-runtime` |
| B branch | `temp/rc-b-vps-runtime` |
| S0/common launch SHA | `b0f47788c1a5d385ae4c3c770d5cd990f586a626` |
| B working-tree policy | clean target/A/C worktrees preserved; edits only here |

The target currently has unrelated dirty work and a different HEAD. It was not
edited. No reset, clean, pull, merge, push, deploy, production migration,
host command, provider request, or live request was performed.

## Ticket status

| Ticket | Status | Evidence/next gate |
| --- | --- | --- |
| RC-023 | Offline preparation plus producer state/export correction complete; full acceptance pending | Runtime contract, acquisition isolation, setup pinning, resource/log controls, separate producer state/export paths, and focused tests. Requires C's accepted integrated SHA plus authorized clean-host setup/restart/port/synthetic-task evidence. |
| RC-024 | Offline implementation and fixture rehearsal complete; full acceptance pending | `scripts/acquisition_state_backup.py` uses SQLite Online Backup, manifest-last S3/R2 preservation, isolated restore, measured local budget and epoch-fenced single-writer leases. Fixture proof passes; historical source, approved bucket/lifecycle, replacement-host restore/reboot and service-account evidence remain required. |
| RC-025 | A-owned and accepted in C's integrated history; not changed | C records A's `6ab6f31bec0977b6db2435920942a7d885ead66d` integration and the later candidate; B did not modify A's files. |
| RC-026 | Offline benchmark/evidence complete; full acceptance pending | `docs/RC026_BENCHMARK.md`, `scripts/benchmark_acquisition_full_state.py`, and `tests/test_rc026_benchmark.py`. Both RC-024 historical checkpoint copies, bounded employer matrix, customer warm path, resource metrics, request accounting, and unknown-cost model were measured offline. Production/VPS/Turso/provider capacity remains unverified. |
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

The VPS setup, service restart, port check, and synthetic worker command are
deliberately not listed as passing results: they require an authorized clean
host and isolated staging state and must be coordinated with C first.

## Host verification attempt

The existing preflight connection was used on 2026-09-09 without repeating
completed firewall/SSH-hardening work:

| Item | Observation |
| --- | --- |
| Candidate requested | INT-1 accepted integrated candidate `3943be1a146600f67c09431f5fdddccdb56e049e` (runtime code-bearing tip `9d837e2d56930715db1de22f191644531c2c00b8`) |
| Host connection | SSH reached `runradmin@144.91.99.90` using the existing approved key; host `vmd205749` |
| Host OS | Ubuntu 24.04.4 LTS, kernel `6.8.0-139-generic` |
| Account | `runradmin`, member of `sudo`; non-interactive `sudo -n -v` failed because a password is required |
| Root SSH fallback | Existing key rejected for `root@144.91.99.90` (`Permission denied (publickey,password)`) |
| Installed runtime | `/opt/runr` absent; all checked `/srv/runr/*` mounts, `/var/lib/runr/acquisition-data`, env files, and `/opt/runr/.venv/bin/python` absent |
| Host revision | None installed; no accepted SHA was deployed |
| Mutation result | No setup, package install, service change, reboot, mount change, or data transfer performed |

The host is therefore blocked on an approved elevation method: either restore
the established `runradmin` sudo access/passwordless elevation or authorize a
working root SSH/admin path. Once supplied, resume the RC-023 host checklist
at the accepted candidate above; do not redo the offline producer/runtime work
or completed preflight.

## Handoff to C

1. Integrate producer state/export correction tip `d14332db57c06d2021e4e41c240d8727e5f212da` and this
   handoff sequentially into C's release worktree. Resolve the shared
   `deploy/acquisition-data-manifest.json` edit by retaining all four explicit
   state roots and restore guards; do not copy the persistent target's dirty
   files.
2. The host attempt reached `144.91.99.90` but is blocked by missing sudo/root
   elevation. Continue only after that access detail is supplied.
3. On an authorized clean host at INT-1's accepted candidate, record the provider image/region/price/limits,
   create both environment boundaries from secret storage, run setup/deploy,
   verify services and closed ports, and execute one isolated synthetic worker
   task. Record deployed commit separately from this branch.
4. C must integrate the scoped RC-024 tip and rerun the combined suites. Only
   after RC-015/016/023 are integrated and the actual backup/restore drill is
   accepted may RC-024 be marked fully verified.
5. Integrate the scoped RC-026 benchmark/evidence commits and rerun the
   combined matrix before staging execution. RC-026 remains fully pending
   until the authorized staging benchmark measures the real provider/browser
   workload, customer overlap, Turso billing/contention, and cost scenarios.
   RC-031 stays conditional and must not be started from this offline result.

## RC-024 rollback and next action

The scoped implementation/evidence commit is
`6e315b9324e4ba2fb1b2ffbb42592fe55d01c610`. C may integrate that immutable
tip together with `docs/RC024_BACKUP_RESTORE.md`, this handoff, and
`tests/test_rc024_backup_restore.py`; B will not amend or rebase it. No
historical source or generated checkpoint is part of the commit.

If the correction is rejected before deployment, C should revert the scoped
commit in the integration branch and leave all source/checkpoint directories
untouched. If a runtime trial has started, first stop or disable the backup or
acquisition schedule and prevent new shard claims, then retain the newest
verified checkpoint and its off-host receipt. Restart only the prior compatible
release after checking its state path and ownership epoch. Do not delete source
databases, overwrite newer state with an older restore, or remove the external
snapshot quarantine. Any host unit rollback remains the RC-023 procedure:
restore the prior unit files, reload systemd and restart the prior compatible
release while leaving `.env*`, `/srv/runr`, `/var/lib/runr`, backups and
journald data intact.

This handoff is frozen after the final scoped documentation commit below; B
will not edit the worktree again until C supplies an accepted integration tip.

## Rollback

Rollback only the B commit(s) after checking the target status: stop new
acquisition claims, disable/remove the B acquisition unit from the host,
restore the prior unit files and restart the previous compatible release.
Leave `.env*`, `/var/lib/runr`, `/srv/runr`, backups, and journald data intact.
Do not use `git reset`, `git clean`, whole-file rollback, or database restore
over newer customer writes.

Prior runtime/evidence commit SHA: `e7c70a9b52c1d839ee3df24c63efced106d7d18a`.
Producer state/export correction SHA: `d14332db57c06d2021e4e41c240d8727e5f212da`.
RC-024 implementation/evidence SHA: `6e315b9324e4ba2fb1b2ffbb42592fe55d01c610`.
RC-026 implementation/evidence SHA: `61d204cea7ef8ddfd9451c40d7dcc158db8d2f7a`.
Final B handoff tip: this documentation commit; verify its immutable SHA with
`git rev-parse HEAD` and report it with the implementation SHA.
