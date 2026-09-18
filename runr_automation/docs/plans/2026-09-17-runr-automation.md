# Runr Local Linear Automation Implementation Plan

> Required execution skill: `superpowers:executing-plans`. Apply `superpowers:test-driven-development` to each behavioral change and `superpowers:verification-before-completion` before completion claims.

## Goal

Deliver a single-folder, installable, configurable local controller implementing the approved Linear-driven Runr workflow, including durable safe stoppage near provider capacity limits.

## Architecture

Use `runr_automation/` as the sole versioned product root and `%LOCALAPPDATA%/RunrAutomation/` as the sole mutable runtime root. Keep deterministic control in Python, integrations behind typed adapters, SQLite as durable coordination state, and agent work inside issue-specific worktrees bounded by scope manifests.

## Tech stack

Python 3.12.7, `sqlite3`, PyYAML, stdlib subprocess/logging/path libraries, pytest, Ruff, Typer-free argparse CLI, Linear GraphQL, PowerShell Task Scheduler scripts.

## Specification

`runr_automation/docs/specs/2026-09-17-local-linear-automation-design.md` and the original implementation request are authoritative.

## Global constraints

- Use `.venv\Scripts\python.exe` exclusively and verify version before Python work.
- Write a failing behavioral test before implementation.
- Do not touch unrelated dirty changes.
- Never persist secrets or full prompts.
- Do not execute live migration apply, release, paid fallback, or destructive cleanup.
- End every phase with focused tests, relevant broader tests, diff stat, scoped checkpoint commit, and external ledger checkpoint.

## Task 1: Consolidate and package the existing controller

1. Add a test that invokes the package CLI from its intended installed layout and fails before packaging.
2. Move `tools/runr_automation` to `runr_automation/src/runr_automation` and `tests/runr_automation` to `runr_automation/tests`.
3. Add package `pyproject.toml`, `runr-auto` entry point, example configuration, scripts/docs/skills directories, and root test discovery integration.
4. Move the preflight document under the product docs and remove the controller dependency added to root requirements.
5. Install editable with the project interpreter; run package tests, Ruff, documented backend regression tests; commit and checkpoint.

## Task 2: Complete safe subsystem migration

1. Add failing tests for partial failure/no archive, rerun idempotency, exact-project isolation, and RUN-1..RUN-4 protection.
2. Complete migration orchestration, snapshots/repair reports, grouped-label capability reporting, and deterministic idempotency.
3. Wire dry-run/apply CLI with explicit confirmation semantics; implement the production adapter without invoking apply.
4. Run fake tests and a read-only live dry-run only if credentials/capabilities are available; commit and checkpoint.

## Task 3: Durable jobs, invalidation, and leases

1. Add tests for stage-specific invalidation, cosmetic edits, crashed lease reclaim, idempotent writes, and analysis metadata.
2. Add queue/job/attempt/checkpoint/lease schema and typed repositories.
3. Implement fingerprint-aware invalidation and retry scheduling.
4. Verify focused and broader tests; commit and checkpoint.

## Task 4: Deduplication

1. Record pressure scenarios and a failing baseline test.
2. Add strict result schema, deterministic candidate filtering, bounded model adjudication, and review-safe Linear projection.
3. Create canonical `runr-ticket-deduplication` skill plus discovery shim.
4. Prove ambiguous/invalid output cannot close or mutate destructively; commit and checkpoint.

## Task 5: Research

1. Add pressure/freshness/scope tests.
2. Implement internal scoped inspection and opt-in evidence-based external research artifact generation.
3. Create canonical `runr-ticket-research` skill and shim.
4. Verify citations/fingerprints and no time-only staleness; commit and checkpoint.

## Task 6: Dependency graph and waves

1. Add tests for evidence-backed edges, preserved user edges, cycles, conflicts, connected-component locality, and compatible waves.
2. Implement DAG/conflict planning and deterministic Linear label projection.
3. Create canonical `runr-parallelization-plan` skill and shim.
4. Verify pressure scenarios; commit and checkpoint.

## Task 7: Providers, budgets, circuits, and safe stoppage

1. Add tests for detected CLI commands, routing order, disabled/over-budget OpenRouter, error classification, circuit recovery, threshold stop, commit/checkpoint handoff, and resume.
2. Implement typed Codex/OpenCode adapters and provider discovery without embedding unverified CLI syntax.
3. Implement local and authoritative usage budgets plus the safe-stop coordinator.
4. Ensure commits occur only in dedicated validated issue worktrees; persist incomplete checkpoints without false success.
5. Verify redaction across output/errors/logs/state; commit and checkpoint.

## Task 8: Scheduler and bounded implementation

1. Add tests for eligibility, wave concurrency, locks, worktree isolation, diff validation, checkpoint resume, sleep/offline catch-up, and serialized integration.
2. Implement scheduler, worktree manager, implementation/validation jobs, and handoff artifacts.
3. Wire `daemon`, `once`, `status`, `pause`, `resume`, `reconcile`, and `retry`.
4. Verify restart simulations; commit and checkpoint.

## Task 9: Approval-gated actions and existing skills

1. Add tests for missing/expired/stale approvals across predeployment, deployment, discard, and migration archive.
2. Implement approval records and CLI approve/reject commands.
3. Copy the seven skills into canonical product storage, revise them to the new subsystem/scope/plan/approval contracts, and replace originals with thin discovery shims.
4. Update ticket template and skill index without creating a second subsystem registry.
5. Validate every skill and lifecycle test; commit and checkpoint.

## Task 10: Local installation and operating guide

1. Add tests/validation for configuration precedence and generated Task Scheduler commands.
2. Implement per-user install/uninstall PowerShell scripts, rotating structured logs, doctor diagnostics, and foreground operation.
3. Write `runr_automation/README.md` and detailed guide covering what it is/is not, exact flow, configuration/performance, capacity safe-stop limits, install/start/stop/pause/resume/recovery/migration/approval/cost/uninstall.
4. Verify no credentials or machine-specific values are tracked; commit and checkpoint.

## Task 11: End-to-end verification

1. Add fake end-to-end issue-change-to-approval-wait and offline/provider-capacity recovery tests.
2. Run all package tests, Ruff, repository lint/type/build commands, affected broader test suites, skill validation, CLI doctor, and read-only migration dry-run where available.
3. Inspect tracked files for secrets and confirm no prohibited live action occurred.
4. Write final resumable progress/verification report, commit, and external checkpoint.
