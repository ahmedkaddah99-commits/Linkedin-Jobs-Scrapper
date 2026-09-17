# Runr Local Automation Verification

Date: 2026-09-17

## Delivered boundary

The versioned controller is contained in `runr_automation/`; only root pytest discovery and `.agents/skills/runr-*` discovery shims live outside it. Mutable state, logs, migration backups, checkpoints, locks, and worktrees share `%LOCALAPPDATA%\RunrAutomation`.

Implemented capabilities include durable overlap polling, idempotent events/jobs, SQLite migrations and leases, subsystem scope manifests, guarded subsystem migration, deterministic deduplication/research/dependency waves, provider routing and paid-fallback budgets, capacity safe-stop checkpoints, worktree path validation, bounded scheduling, fingerprint-bound approvals, local daemon/pause/resume/retry/status/doctor commands, rotating redacted logs, Windows login-task scripts, canonical skills, and a fake end-to-end pipeline ending at predeployment approval.

## Fresh local evidence

- Python: 3.12.7 from `.venv\Scripts\python.exe`.
- Automation: `58 passed`; Ruff passed.
- Backend focused regression: `118 passed, 21 subtests passed`.
- Backend API subset: `5 passed, 114 deselected, 7 subtests passed`.
- Frontend: `157 passed`; ESLint passed; Vite production build passed.
- Browser extension: type preparation passed; serial Vitest rerun `26 files, 198 tests passed`; WXT production build passed; guarded MV3 manifest verification passed.
- Fake end-to-end: issue -> dedup -> scope -> research -> dependency wave -> bounded implementation -> validation -> local approval wait passed.
- Doctor: project interpreter and runtime paths correct; Codex available; OpenCode unavailable; OpenRouter disabled.

The default parallel extension test run first produced three worker-start timeouts after all 168 scheduled assertions passed. Re-running with `--maxWorkers=1` completed all 198 tests. This was local process-capacity pressure, not an assertion failure.

## External verification boundary

`LINEAR_API_TOKEN` was not set, so the live read-only `migrate-subsystems --dry-run` could not be executed. The fake adapter verifies the exact 12-project mapping, zero dry-run mutations, add/verify-before-clear ordering, no archive after partial failure, idempotent rerun, unrelated-project isolation, and RUN-1 through RUN-4 protection.

No live Linear mutation, subsystem project archival, predeployment, production deployment, OpenRouter request, branch/worktree deletion, or destructive discard occurred.

## Commands

```powershell
.venv\Scripts\python.exe -m pytest runr_automation\tests -q
.venv\Scripts\python.exe -m ruff check runr_automation
npm run check:backend
npm --prefix frontend run check
npm --prefix apps/browser-extension run test:unit -- --maxWorkers=1
npm --prefix apps/browser-extension run build
npm --prefix apps/browser-extension run verify:manifest
.venv\Scripts\runr-auto.exe --repo-root . doctor
```

When a Linear token is available, the remaining read-only command is:

```powershell
.venv\Scripts\runr-auto.exe --repo-root . migrate-subsystems --dry-run
```

Applying the migration remains an explicit human boundary:

```powershell
.venv\Scripts\runr-auto.exe --repo-root . migrate-subsystems --apply
```
