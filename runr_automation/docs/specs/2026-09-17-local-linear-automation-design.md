# Runr Local Linear Automation Design

## Goal

Provide one installable, local-only controller that turns Runr Linear issues into bounded, resumable engineering jobs while preserving human approval for release and destructive actions.

## Product boundary

The controller is a local engineering orchestrator. It polls Linear, validates tickets, creates scope manifests, runs analysis and implementation jobs in isolated worktrees, records durable checkpoints, and projects state back to Linear.

It is not a hosted service, webhook receiver, autonomous production deployer, secret store, replacement for Linear workflow states, or guarantee of unlimited Codex/OpenCode capacity. It never spends OpenRouter credits unless the adapter is explicitly enabled, keyed, ordered, and bounded by positive budgets.

## Folder boundary

All versioned controller-owned material lives under one repository folder:

```text
runr_automation/
  pyproject.toml
  README.md
  config/
  docs/
  scripts/
  skills/
  src/runr_automation/
  tests/
```

Only two repository integration points may remain outside it:

- root test discovery/configuration;
- `.agents/skills/runr-*` discovery shims that point to canonical skills in `runr_automation/skills`.

Mutable state and credentials must not be tracked. One OS-local runtime root contains everything the running controller controls:

```text
%LOCALAPPDATA%/RunrAutomation/
  config.yaml
  state.db
  logs/
  backups/
  checkpoints/
  locks/
  worktrees/
```

## Control flow

One process acquires the repository/team lock, reads durable state, polls Linear from an overlapping `updatedAt` watermark, records pages before advancing the watermark, and schedules only invalidated stages. Each issue passes through normalize, deduplicate, scope, research, dependency planning, implementation, validation, and an approval wait. Work uses one branch/worktree per issue. External writes use deterministic idempotency keys.

The subsystem registry remains authoritative in `docs/subsystems.yaml`; the controller reads it but does not duplicate it. Exactly one grouped Subsystem label selects the primary read boundary. Only ticket `Allowed paths` grant writes. Co-owner subsystem IDs authorize declared cross-subsystem paths. Every agent receives a hashed scope manifest, and every checkpoint validates the diff against that manifest.

## Provider and safe-stop design

Routing order is configured by `providers.order`; the recommended deployment order is OpenCode subscription, explicitly enabled and budgeted OpenRouter, then Codex CLI. Deterministic work stays in Python. Provider commands are discovered by `doctor`, not assumed.

Providers do not consistently expose subscription credits. Therefore the controller distinguishes:

1. authoritative remaining-usage metadata, when a provider exposes it;
2. configurable local attempt budgets (tokens, elapsed minutes, estimated cost, and request count);
3. capacity/rate-limit signals and conservative retry times.

Before any known remaining amount crosses its reserve, or before a local attempt budget is exhausted, the safe-stop coordinator stops launching new model work. It validates the current diff, runs the configured focused checkpoint tests when time permits, commits only ticket-allowed changes in the dedicated issue worktree, records the commit/session/handoff/checkpoint, marks the job `Waiting for Capacity`, releases renewable leases safely, and exits or tries the next permitted provider. If validation fails, it records an incomplete checkpoint and requires review; it never labels incomplete work successful. On providers with no credit telemetry, the guide must clearly say the threshold is a conservative estimate, not the account balance.

## Approval boundary

Normalization, analysis, evidence-backed relation creation, planning, scoped implementation, tests, and non-release status updates are automatic. Predeployment, deployment, destructive discard/cleanup, and subsystem project archival require an unexpired approval or the explicit migration apply command. Approvals bind action, targets, issue/scope fingerprints, tested commit, test result, and expiry; any material change invalidates them.

## Configuration

Configuration loads defaults, then the user-owned runtime `config.yaml`, then environment overrides. It covers Linear team and poll timing; paths; concurrency; provider order, models, circuits, attempt budgets and reserves; OpenRouter opt-in and daily/job caps; analysis freshness; retry/backoff; approvals; logging/redaction; test commands; and Windows startup behavior. Example configuration contains names and safe defaults but no credentials.

## Failure and recovery

SQLite uses WAL, foreign keys, schema migrations, leases, and idempotent records. A restart reclaims expired jobs, verifies worktrees/checkpoints, resumes provider sessions when safe, and replays overlapping Linear updates exactly once. Offline errors preserve the watermark and retry with bounded backoff. Invalid model output, dependency cycles, ambiguous duplicates, scope escapes, and conflicting Linear state become review-required without destructive mutation.

## Verification

Unit and integration tests use fake Linear/provider adapters. End-to-end verification covers issue update through approval wait, restart/offline overlap, rate-limit failover, safe stop and resume, approval invalidation, migration idempotency, and single-daemon locking. Live smoke tests are read-only; migration apply, deployment, paid OpenRouter calls, and destructive cleanup are excluded.
