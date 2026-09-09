# Chat B runtime handoff

Status: RC-023 offline preparation and producer state/export correction are
complete on B. The authorized host phase was attempted against INT-1's
accepted candidate but is access-blocked before mutation; deployed/full VPS
acceptance remains pending. RC-024, RC-026, and conditional RC-031 remain
gated.

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
| RC-024 | Not started / gated | Requires RC-015, RC-016, and accepted RC-023; historical state is not copied into this worktree. |
| RC-025 | A-owned, not changed | Required before RC-026. |
| RC-026 | Not started / gated | Requires RC-012/014/015/021/024/025 and comparable measured state; no capacity/cost claim made. |
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

Evidence/tests:

- `tests/test_rc023_vps_runtime.py`
- `tests/test_rc023_producer_state_paths.py`
- `docs/RC023_VPS_RUNTIME.md`
- `docs/RC_B_HANDOFF.md`

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
4. Only after RC-015/016/023 are integrated may B resume RC-024. RC-026 waits
   for A's RC-025 and all plan dependencies. RC-031 stays conditional.

This handoff is frozen after the final scoped commit below; B will not edit
the worktree again until C supplies an accepted integration tip.

## Rollback

Rollback only the B commit(s) after checking the target status: stop new
acquisition claims, disable/remove the B acquisition unit from the host,
restore the prior unit files and restart the previous compatible release.
Leave `.env*`, `/var/lib/runr`, `/srv/runr`, backups, and journald data intact.
Do not use `git reset`, `git clean`, whole-file rollback, or database restore
over newer customer writes.

Prior runtime/evidence commit SHA: `e7c70a9b52c1d839ee3df24c63efced106d7d18a`.
Producer state/export correction SHA: `d14332db57c06d2021e4e41c240d8727e5f212da`.
Final handoff tip: this documentation commit; verify its immutable SHA with
`git rev-parse HEAD` (reported in the final handoff message).
