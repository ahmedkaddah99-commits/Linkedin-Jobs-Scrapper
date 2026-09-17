# Runr Local Automation

Runr Local Automation is a laptop-only controller for turning Runr Linear issues into bounded, recoverable engineering work. Source, tests, scripts, skills, examples, and documentation live in this folder. Mutable state stays together under `%LOCALAPPDATA%\RunrAutomation` and is never committed.

## What it is—and is not

It is a poll-based Linear controller needing no webhook, public port, VPS, or paid orchestrator; a durable SQLite ledger; a strict code-scope boundary; and a recovery layer for provider limits, restarts, and network loss.

It is not a deployment service, secret manager, replacement for Linear workflow states, or guarantee that Codex/OpenCode expose subscription balances. It cannot bypass approvals, grant writes from subsystem ownership, auto-close ambiguous duplicates, remove user dependency relations, or silently spend OpenRouter credits.

## Install

From the repository root:

```powershell
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe -m pip install -e .\runr_automation
.venv\Scripts\runr-auto.exe doctor
```

Python must report `3.12.7`. Set `LINEAR_API_TOKEN` and optionally `RUNR_LINEAR_TEAM_ID`; values are never written to state. Copy `config/runr-automation.example.yaml` to `%LOCALAPPDATA%\RunrAutomation\config.yaml` and edit that copy—never add credentials.

## Exact operation

1. `once` reads Linear changes from a durable overlapping watermark and records events idempotently.
2. Reconciliation compares normalized fingerprints and queues only invalidated stages.
3. Scope routing reads `docs/subsystems.yaml`: one Subsystem label bounds reads; only ticket `Allowed paths` grant writes; co-owners authorize declared cross-subsystem paths.
4. Eligible work uses an issue-specific branch/worktree plus issue/resource leases.
5. Model output is schema-checked. Python owns paths, graphs, state transitions, and Linear writes.
6. Every checkpoint validates changed paths and runs configured focused tests.
7. Release actions wait for a local approval tied to the tested commit and current fingerprints.

Available operator commands:

```powershell
runr-auto doctor
runr-auto status
runr-auto once
runr-auto reconcile
runr-auto pause
runr-auto resume
runr-auto migrate-subsystems --dry-run
runr-auto migrate-subsystems --apply
```

Migration apply snapshots first and is capability-gated. If grouped labels or archival are unavailable, it prints exact manual steps and does not claim success. Review dry-run before apply.

## Configure for speed

Edit the runtime YAML:

- `linear.poll_interval_seconds`: 30–90 seconds is a practical range; lower detects faster but makes more requests.
- `execution.max_concurrent_issues`: start at 2; raise only for compatible current-wave tickets and adequate machine resources.
- `execution.checkpoint_interval_seconds`: lower loses less work but validates/commits more often.
- `max_attempt_minutes`, `max_attempt_tokens`, and `reserve_tokens`: bound attempts and preserve handoff capacity.
- `providers.order`: keep Codex and subscription-backed OpenCode ahead of paid fallback.
- `openrouter.enabled`: remains false unless explicitly enabled with nonzero per-job and daily budgets.

Precise `Required reading`, `Allowed paths`, and `Tests` fields usually improve speed more than a stronger model because they reduce context and validation. Do not use WS-12 as blanket scope, run conflicting tickets concurrently, or disable tests. Environment variables such as `RUNR_AUTOMATION_POLL_INTERVAL_SECONDS` override YAML.

## Safe stoppage near Codex/OpenCode limits

The shared guard uses authoritative remaining-token data when a provider exposes it. Otherwise it uses tokens consumed in the attempt, elapsed time, configured reserves, and rate/capacity errors. Before the threshold it stops new model work, validates scope, runs focused tests where possible, commits only the dedicated issue worktree, and writes a redacted handoff under `%LOCALAPPDATA%\RunrAutomation\checkpoints`. The handoff records commit, test result, resumable session ID, and next action; the job becomes `Waiting for Capacity`.

If scope validation fails, it does not commit and marks `Needs Review`. A scope-valid checkpoint with failing tests is saved as incomplete, never called successful. When a CLI exposes no balance API, the reserve is a conservative estimate—not the account's actual remaining credits.

## Stop, recover, and uninstall

- Stop foreground operation with `Ctrl+C`; durable state remains.
- Use `runr-auto pause`, `runr-auto resume`, and `runr-auto status` for maintenance.
- After sleep/network loss, run `runr-auto once`; overlap plus event keys prevent gaps and duplicates.
- Back up `%LOCALAPPDATA%\RunrAutomation` to preserve state, snapshots, and handoffs.
- Uninstall with `.venv\Scripts\python.exe -m pip uninstall runr-local-automation`.

No credentials, full prompts, or unredacted command errors belong in the repository, SQLite, checkpoints, or logs. Predeployment, deployment, destructive cleanup, and project archival remain explicit approval boundaries.

See `docs/specs/2026-09-17-local-linear-automation-design.md` for the design and `docs/plans/2026-09-17-runr-automation.md` for the remaining phased implementation.
