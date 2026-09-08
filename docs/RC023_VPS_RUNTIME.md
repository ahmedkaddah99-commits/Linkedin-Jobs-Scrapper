# RC-023 VPS runtime preparation

Status: offline preparation complete on the B worktree; VPS acceptance is
pending an authorized host and C's accepted runtime/release integration tip.
This document does not claim a purchased machine, a deployed service, a port
check, or a synthetic task executed on a VPS.

## Release and operating boundary

The B worktree was created from the exact common launch commit
`b0f47788c1a5d385ae4c3c770d5cd990f586a626` on branch
`temp/rc-b-vps-runtime`. The target integration branch remains
`deployment/render-turso-r2`; C owns integration and push.

The primary VPS mechanism is systemd. Docker remains the existing Render
release mechanism and was not changed in this ticket. Runtime data stays
outside `/opt/runr` and outside disposable Git worktrees.

The machine profile is intentionally a guarded proposal, not a capacity
claim. RC-002 measured only a small offline fixture on Windows. Before
purchase, operations must record the provider image identifier, region close
to Turso, vCPU/RAM/disk, VAT/add-ons, monthly price, bandwidth/storage limits,
and provider/account quotas. The runtime contract leaves price and limits
`null` until those values are supplied. Every deployment must retain at least
25% RAM headroom and calculate disk as:

```text
state + exports + one verified backup + temporary peak space + outage buffer
```

The `MemoryHigh=9G`, `MemoryMax=12G`, `CPUQuota=300%`, and `TasksMax=512`
values on the worker units are safety ceilings for a proposed 16 GiB-class
host, not measured capacity. They must be reconciled with the approved
benchmark before production use.

## Implemented files and symbols

- `deploy/vps-runtime-contract.json` — versioned systemd, release, resource,
  path, role, and retention contract.
- `deploy/acquisition.env.example` — non-secret acquisition-only environment
  template; customer document/email/OAuth/billing/Clerk values are excluded.
- `deploy/systemd/runr-acquisition-worker.service` — non-root acquisition
  worker, unique ID, explicit acquisition roots, resource ceilings, and
  protected writable paths.
- `deploy/systemd/runr-api.service` and `runr-worker.service` — non-root
  customer/API services with explicit Python venv, data roots, limits, and
  hardened systemd settings.
- `deploy/systemd/runr-frontend.service` — non-root static server with no
  customer environment file.
- `deploy/systemd/runr.target` — includes the separate acquisition worker.
- `deploy/systemd/runr-journald.conf` — bounded system/runtime journal usage
  and 14-day retention.
- `deploy/setup.sh` — requires Python 3.12.7, creates the `runr` user and
  runtime directories, protects both environment files, installs all units,
  and configures chrony/journald.
- `deploy/deploy.sh` — refuses a missing or wrong-version project venv and
  installs with `python -m pip` before restarting the selected target.
- `deploy/start.sh` — accepts `RUNR_API_HOST`, allowing the VPS API to bind
  loopback while Render remains the public API boundary.
- `tests/test_rc023_vps_runtime.py` — offline contract tests for role
  separation, non-root services, bounds, setup pinning, and journal policy.

The application worker role itself remains in the shared files owned by C;
this ticket only supplies its systemd runtime boundary. Source producer
scheduling and live provider authorization remain separate gates.

## Environment and security contract

`runr-api.service` and `runr-worker.service` read `/opt/runr/.env`, while
`runr-acquisition-worker.service` reads only `/opt/runr/.env.acquisition`.
The acquisition unit is explicitly assigned `WORKER_ROLE=acquisition` and
`WORKER_ID=vps_acquisition_worker`; the customer unit uses
`WORKER_ROLE=customer` and `WORKER_ID=vps_customer_worker`.

All services run as `runr:runr`, use mode `0077`, disallow privilege
escalation, protect the host filesystem/home, and expose no public scraper
API. The VPS API unit binds to `127.0.0.1`; firewall policy must still deny
inbound ports. Inputs are not included in the acquisition unit's writable
paths. Credentials are referenced by environment variable name only and must
be supplied by the host secret mechanism.

## Offline verification

Required interpreter, verified before tests:

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' --version
# Python 3.12.7
```

Pre-change focused suite: `9 passed` for the runtime manifest and RC-022
contract tests. The post-change RC-023/runtime/worker suite passed `42 tests,
4 subtests` with the same interpreter. Ruff passed for the focused Python
files and `bash -n` passed for all edited deployment scripts. No network,
Docker daemon, provider, VPS, or historical database was used.

The following are acceptance commands for an authorized replacement host;
they were not run in this offline pass:

```bash
sudo env RUNR_PYTHON_BIN=/usr/local/bin/python3.12 /opt/runr/deploy/setup.sh
sudo /opt/runr/deploy/deploy.sh
systemctl is-active runr-api.service runr-worker.service runr-acquisition-worker.service
ss -lntp
curl --fail http://127.0.0.1:8000/health/live
```

The clean-host and port/service checks need a host-capable session. A
synthetic worker task also needs an isolated staging database/queue and an
approved fixture; the existing offline worker tests do not substitute for
that VPS demonstration.

## Pending dependencies and rollback

RC-023 is not fully verified until an authorized host demonstrates clean setup,
restart, closed inbound ports, and one synthetic worker task. RC-024 remains
blocked from completion until RC-015/016 and this runtime contract are
integrated, and the missing historical state is restored through a consistent
backup workflow. RC-025 is owned by A. RC-026 remains gated on RC-024 and
RC-025 plus comparable measured state. RC-031 is trigger-based and must not
start without RC-024/026/028 evidence.

Rollback is scoped: stop new claims, disable the B-added acquisition unit,
restore the prior unit files and restart the previous compatible target. In
Git, C should revert the B integration commit(s) after verifying the target
status; do not reset or clean the persistent target. Environment files,
runtime state, backups, and journals remain outside Git and are not deleted by
this rollback.
