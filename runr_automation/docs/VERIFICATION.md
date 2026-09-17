# Runr Local Automation Verification

Date: 2026-09-17

## Delivered boundary

The versioned controller is contained in `runr_automation/`. Runtime configuration, SQLite state, prompts, locks, worktrees, migration snapshots, provider verification fixtures, and checkpoints are contained under `%LOCALAPPDATA%\RunrAutomation`.

The runnable path now includes provider discovery, real Linear polling, canonical Markdown ticket parsing, durable stage execution, stale-job suppression, isolated Git worktrees, exact write-scope validation, shell-free focused tests, checkpoint commits, provider failover circuits, restart-safe approvals, and daemon/operator commands.

## Automated evidence

The final quality gate is recorded from the project Python 3.12.7 virtual environment and includes:

- the complete `runr_automation/tests` suite;
- a subprocess-level fake-provider cycle and idempotent restart;
- Ruff static checks;
- package build/install metadata and entry-point checks;
- `doctor` and `status` using the packaged command;
- diff whitespace, secret-pattern, and folder-boundary checks.

See the final implementation commit and handoff checkpoint for exact current counts and command output.

## Real provider evidence

Two isolated tickets were run through the complete controller, not directly through provider adapters.

### Codex in VS Code

- Discovered source: `vscode-extension`
- CLI version: `codex-cli 0.154.0-alpha.6.2`
- Model: `gpt-5.6-luna`
- Run ID: `codex-live-20260917`
- Result: `awaiting_approval`
- Durable stages processed: 5
- Attempt outcome: `implemented`
- Python 3.12.7 acceptance test: passed
- Worktree after checkpoint commit: clean
- Commit: `f101f33d54557beb4195e5d3dba8d879ee9beae4`
- Approval: `007183c35cc3f7a46c949f98` (left undecided)
- Restart with the same run ID: 0 jobs processed; provider was not called again

### OpenCode Desktop shared auth

- Discovered source: `desktop-shared-auth`
- CLI/package version: `1.18.30`
- Model: `opencode-go/gpt-5.6-luna`
- Run ID: `opencode-live-20260917-final`
- Result: `awaiting_approval`
- Durable stages processed: 5
- Attempt outcome: `implemented`
- Python 3.12.7 acceptance test: passed
- Worktree after checkpoint commit: clean
- Commit: `3e9724321db4b2e95635d21f884c7e377f6dba52`
- Approval: `c77366e51783f34c950cc8d8` (left undecided)

The OpenCode live test also identified and fixed a real 1.18.30 argument-order issue: because `--file` is multi-valued, the message must precede options and the file pair must be last.

## Safety boundaries retained

No production deployment, push, merge, live Linear mutation, OpenRouter request, worktree deletion, or destructive discard was performed. Provider verification used dedicated repositories under the runtime root. The failed pre-fix OpenCode fixtures are retained for audit and can be manually removed later.

Current Codex/OpenCode CLIs do not expose an authoritative remaining subscription-credit balance to this controller. Capacity responses and local timeout are actionable safe-stop signals; token reserve configuration remains a conservative estimate until a provider supplies streaming usage or balance data.

## Reproduction

```powershell
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe -m pytest -p no:cacheprovider runr_automation\tests -q
.venv\Scripts\python.exe -m ruff check runr_automation
.venv\Scripts\runr-auto.exe --repo-root . doctor
.venv\Scripts\runr-auto.exe --repo-root . verify-provider codex --run-id codex-check-1
.venv\Scripts\runr-auto.exe --repo-root . verify-provider opencode_subscription --run-id opencode-check-1
```

Live Linear execution additionally requires `LINEAR_API_TOKEN` and `RUNR_LINEAR_TEAM_ID`. `migrate-subsystems --apply` remains a separate explicit human action.
