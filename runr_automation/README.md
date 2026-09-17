# Runr Local Automation

Runr Local Automation is a laptop-only controller that turns structured Linear issues into isolated, tested Git commits and then stops for local approval. All versioned source, tests, scripts, skills, examples, and documentation live in this `runr_automation/` folder. All mutable state lives together under `%LOCALAPPDATA%\RunrAutomation`.

## What it is

- A poll-based Linear controller with no webhook, public port, VPS, or hosted orchestrator.
- A durable SQLite queue with idempotent events, leases, attempts, checkpoints, provider circuits, and approvals.
- A strict execution boundary: one issue-specific Git branch/worktree and only ticket-declared write paths.
- A local provider router that discovers the newest compatible Codex CLI and OpenCode CLI/Desktop shared-auth package.
- A recovery layer that preserves safe partial work when a provider reports capacity, loses its connection, or reaches the local timeout.

## What it is not

- It is not a deployment service. Successful work stops at an unapproved `predeployment` record.
- It does not auto-merge, push, deploy, archive projects, delete worktrees, or discard changes.
- It does not infer write permission from broad subsystem ownership. The ticket's `Allowed paths` are the write allowlist.
- It cannot read a hidden Codex/OpenCode subscription balance when the CLI does not expose one. In that case it uses bounded time, observed errors, and configured token estimates; it never claims an exact remaining balance.
- OpenRouter is not implemented as an execution adapter and is never silently used. Keep it disabled.

## Install and first check

Run from the product repository root using the required project environment:

```powershell
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe -m pip install -e .\runr_automation
.venv\Scripts\runr-auto.exe --repo-root . doctor
```

Python must report `3.12.7`. Copy `config/runr-automation.example.yaml` to `%LOCALAPPDATA%\RunrAutomation\config.yaml`. Do not put credentials in YAML. Export `LINEAR_API_TOKEN` and `RUNR_LINEAR_TEAM_ID` only in the process environment.

`doctor` reports the selected executable, source, version, and model without invoking a model. Explicit command arrays in YAML override discovery. Commands are argument lists, not shell strings; `{cwd}` and `{prompt_file}` are expanded safely.

## Required Linear ticket shape

The controller accepts structured fields or these Markdown sections in the issue description:

```markdown
## Primary subsystem
- api

## Allowed paths
- backend/example.py

## Minimal required reading
- docs/INDEX.md

## Acceptance criteria
- The bounded behavior works.

## Safe local verification commands
- python -m pytest tests/test_example.py -q
```

Exactly one grouped `Subsystem` label can supply the subsystem when the section is absent. Allowed paths must belong to that subsystem or a declared co-owner. Safe verification commands are shell-free and limited to local Python, Node, npm, or npx executables. The configured project-venv interpreter replaces ticket references to Python.

## How one cycle works

1. `once` polls Linear from an overlapping durable watermark and records changes idempotently.
2. Reconciliation queues deterministic `normalize`, `deduplicate`, `research`, `parallelize`, and `implement` stages.
3. Scope routing reads `docs/subsystems.yaml` and builds exact read/write/test boundaries.
4. The implementation stage creates or resumes `runr-auto/<issue>` in `%LOCALAPPDATA%\RunrAutomation\worktrees`.
5. Codex runs first by default; capacity/transient failure opens a durable circuit and safely hands off to OpenCode.
6. Changed paths are validated, required tests run with Python 3.12.7, and valid work is checkpoint-committed.
7. A fingerprint-bound predeployment approval is created. Nothing is deployed.

Prompts are outside Git under the runtime root. Stored provider errors and checkpoint summaries are redacted. Worktrees are deliberately preserved for inspection and recovery.

## Commands

```powershell
runr-auto --repo-root . doctor
runr-auto --repo-root . status
runr-auto --repo-root . once
runr-auto --repo-root . daemon
runr-auto --repo-root . reconcile
runr-auto --repo-root . pause
runr-auto --repo-root . resume
runr-auto --repo-root . retry <job-id>
runr-auto --repo-root . approve <approval-id>
runr-auto --repo-root . reject <approval-id> --reason "reason"
runr-auto --repo-root . migrate-subsystems --dry-run
runr-auto --repo-root . migrate-subsystems --apply
```

Use `Ctrl+C` for a safe foreground stop. Durable state is retained. `pause` prevents new daemon cycles; `resume` allows them again.

To verify either installed provider through a real isolated controller ticket, without Linear or the product repository:

```powershell
runr-auto --repo-root . verify-provider codex --run-id codex-check-1
runr-auto --repo-root . verify-provider opencode_subscription --run-id opencode-check-1
```

Each command creates a tiny fixture repository under `%LOCALAPPDATA%\RunrAutomation\verification`, runs all five stages, executes a Python 3.12.7 acceptance test, commits the scoped edit, and stops at approval. Repeating the same run ID proves restart idempotency and does not call the provider again.

## Configure for speed and safety

- `linear.poll_interval_seconds`: 30-90 seconds is a practical range. Lower is faster but polls more often.
- `execution.max_concurrent_issues`: reserved for the scheduler; execution is intentionally serial until conflict-aware scheduling is enabled.
- `execution.max_attempt_minutes`: hard provider-process deadline. A timeout becomes a recoverable handoff.
- `execution.max_attempt_tokens` and `reserve_tokens`: conservative policy values. Current Codex/OpenCode adapters do not expose authoritative live balances, so these are estimates rather than active streaming cutoffs.
- `providers.order`: reorder `codex` and `opencode_subscription` to change failover preference.
- Provider `model`: select the subscription-backed model passed to that CLI.
- Provider `command`: pin an executable and argument list when discovery is not desired.

The biggest speed improvement is precise tickets: minimal reading, narrow allowed paths, one focused test, and a clear acceptance criterion. Broad scope makes both models slower and increases review risk.

## Capacity, timeout, and recovery behavior

On a `429`, quota/capacity response, connection timeout, or local process deadline, the runner:

1. records the redacted provider attempt and session ID when available;
2. validates all changed paths;
3. refuses to commit and marks review-needed if scope escaped;
4. otherwise runs focused tests, checkpoint-commits even when incomplete, and records the test result;
5. opens a 15-minute provider circuit and tries the next configured provider;
6. leaves the job waiting when no provider remains.

Authentication, malformed output, and permanent tool errors fail visibly instead of being mislabeled as capacity. Use `status`, inspect the runtime checkpoint, fix the cause, then `retry <job-id>`. No cleanup is automatic.

## Startup and removal

Install the current-user startup task without administrator access:

```powershell
.\runr_automation\scripts\install-runr-automation-task.ps1
```

Remove only that task while preserving runtime data:

```powershell
.\runr_automation\scripts\uninstall-runr-automation-task.ps1
```

Back up `%LOCALAPPDATA%\RunrAutomation` to preserve state, worktrees, migration snapshots, and handoffs. Uninstall the package with `.venv\Scripts\python.exe -m pip uninstall runr-local-automation`; remove runtime data only after manually reviewing it.

See `docs/specs/2026-09-17-local-linear-automation-design.md` for design constraints and `docs/VERIFICATION.md` for current evidence.
