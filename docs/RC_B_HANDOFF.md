# Chat B runtime handoff

Status: RC-023 offline preparation ready for C review; not a deployed or fully
verified VPS acceptance. RC-024, RC-026, and conditional RC-031 remain gated.

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
| RC-023 | Offline preparation complete; full acceptance pending | Systemd runtime contract, acquisition isolation, setup pinning, resource/log controls, and focused tests. Requires authorized clean-host setup/restart/port/synthetic-task evidence. |
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

Evidence/tests:

- `tests/test_rc023_vps_runtime.py`
- `docs/RC023_VPS_RUNTIME.md`
- `docs/RC_B_HANDOFF.md`

No secrets, mutable state databases, browser profiles, historical exports,
provider logs, or large datasets are included.

## Contract details

The chosen primary mechanism is systemd. All service units run as `runr`, use
protected host settings and bounded CPU/memory/tasks. The acquisition role
uses `/opt/runr/.env.acquisition` and cannot inherit the customer/API
`/opt/runr/.env`; the frontend reads no environment file. The acquisition
worker has explicit input/state/export/backup roots and a stable
`vps_acquisition_worker` identity. The VPS API binds loopback via
`RUNR_API_HOST=127.0.0.1`; no public scraper API is required.

Python is pinned at setup/deploy boundaries to exactly `Python 3.12.7` and
the venv is invoked as `/opt/runr/.venv/bin/python -m pip`. The shared local
verification interpreter is:

```text
C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe
Python 3.12.7
```

Provider machine identity, region, price/VAT/add-ons, quotas, actual RAM/disk
headroom, Docker availability, and deployed revision are still unknown.

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
# Result: 42 passed, 4 subtests passed in 40.08s
```

Additional offline checks to run before committing this handoff:

```powershell
bash -n deploy/setup.sh deploy/deploy.sh deploy/start.sh
# Result: passed
git diff --check
# Result: passed
git status --short --branch
```

The VPS setup, service restart, port check, and synthetic worker command are
deliberately not listed as passing results: they require an authorized clean
host and isolated staging state and must be coordinated with C first.

## Handoff to C

1. Review the narrow systemd/runtime patch and integrate it as a scoped patch
   into C's release worktree; do not copy the persistent target's dirty files.
2. Reconcile `deploy/start.sh` and the runtime/release contract with C's
   accepted integration tip before any host verification.
3. On an authorized clean host, record the provider image/region/price/limits,
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

Runtime/evidence commit SHA: `b4f8147fbd4e374af434043d5f78eb74910babfa`.
Final handoff commit SHA: record with `git rev-parse HEAD` after this
documentation-only update.
