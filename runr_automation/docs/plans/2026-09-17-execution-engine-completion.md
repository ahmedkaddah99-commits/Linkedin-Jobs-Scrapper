# Runr Execution Engine Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the existing Linear poller, durable queue, provider adapters, worktree controls, validation, safe-stop, and approval records into one runnable local execution cycle.

**Architecture:** Add a deterministic `ExecutionEngine` that claims durable jobs and advances them through explicit stage handlers. Provider discovery produces verified command templates, while an implementation runner owns isolated worktrees, bounded prompts, scope/test validation, checkpoint commits, attempts, circuits, and approval creation. `once` and `daemon` call the same cycle so restart behavior remains idempotent.

**Tech Stack:** Python 3.12.7, sqlite3, subprocess, pathlib, PyYAML, pytest, Git worktrees, Codex CLI, OpenCode CLI.

**Spec:** `runr_automation/docs/specs/2026-09-17-local-linear-automation-design.md`

## Global Constraints

- Use `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe` exclusively for Python commands.
- Write and run one failing behavioral test before each production behavior.
- Keep all versioned controller changes under `runr_automation/`.
- Keep mutable state, generated prompts, worktrees, logs, and checkpoints under `%LOCALAPPDATA%\RunrAutomation`.
- Never persist credentials or unredacted provider output.
- Never invoke OpenRouter unless it is explicitly enabled with positive per-job and daily budgets.
- Stop at local predeployment approval; do not deploy, migrate Linear, or delete worktrees.

---

### Task 1: Verified provider discovery and configuration

**Files:**
- Create: `runr_automation/src/runr_automation/providers/discovery.py`
- Modify: `runr_automation/src/runr_automation/config.py`
- Modify: `runr_automation/src/runr_automation/providers/base.py`
- Modify: `runr_automation/src/runr_automation/providers/codex_cli.py`
- Modify: `runr_automation/src/runr_automation/providers/opencode_cli.py`
- Modify: `runr_automation/src/runr_automation/cli.py`
- Test: `runr_automation/tests/test_provider_discovery.py`
- Test: `runr_automation/tests/test_config.py`
- Test: `runr_automation/tests/test_cli.py`

**Interfaces:**
- Produces: `ProviderCommand(name, argv, model, source, version)` and `discover_providers(config, environment) -> dict[str, ProviderCommand]`.
- Produces: configured command/model fields on `AutomationConfig`.
- Consumes: explicit YAML commands first, then capability-probed local candidates.

- [ ] Write tests proving explicit configuration wins, incompatible PATH Codex is skipped for the newer VS Code binary, OpenCode Desktop can use its matching `npx opencode-ai@<version> run` command, and `doctor` reports selected sources without secrets.
- [ ] Run the focused tests and confirm failures because discovery/config fields do not exist.
- [ ] Implement bounded `--version`/`exec --help`/`run --help` probes and command-template construction without invoking a model.
- [ ] Run focused provider/config/CLI tests and the complete controller suite.
- [ ] Commit the provider-discovery phase.

### Task 2: Durable job lifecycle and provider attempts

**Files:**
- Modify: `runr_automation/src/runr_automation/queue.py`
- Modify: `runr_automation/src/runr_automation/state.py`
- Create: `runr_automation/src/runr_automation/attempts.py`
- Test: `runr_automation/tests/test_queue.py`
- Test: `runr_automation/tests/test_attempts.py`

**Interfaces:**
- Produces: `JobQueue.complete`, `JobQueue.wait`, `JobQueue.fail`, `JobQueue.release`, and stage enqueueing.
- Produces: `AttemptRecorder.start(...)`, `AttemptRecorder.finish(...)`, and checkpoint persistence.
- Consumes: existing reclaimable lease records and provider error classification.

- [ ] Write tests for legal transitions, lease-owner enforcement, restart reclaim, redacted attempt errors, checkpoint/session persistence, and deterministic downstream-stage enqueueing.
- [ ] Run focused tests and confirm failures on missing transition/attempt APIs.
- [ ] Add the minimum schema migration and repositories needed for lifecycle updates.
- [ ] Run queue/attempt/state tests and the complete controller suite.
- [ ] Commit the durable-lifecycle phase.

### Task 3: Scoped implementation runner

**Files:**
- Create: `runr_automation/src/runr_automation/execution.py`
- Modify: `runr_automation/src/runr_automation/worktrees.py`
- Modify: `runr_automation/src/runr_automation/safe_stop.py`
- Modify: `runr_automation/src/runr_automation/providers/base.py`
- Test: `runr_automation/tests/test_execution.py`
- Test: `runr_automation/tests/test_worktrees.py`
- Test: `runr_automation/tests/test_safe_stop.py`

**Interfaces:**
- Produces: `TicketExecutionRequest`, `TicketExecutionResult`, `ImplementationRunner.run(request, provider)`.
- Consumes: a `ScopeManifest`, verified provider command, repository root, runtime root, issue payload, and required tests.
- Guarantees: prompt file outside Git, issue-specific worktree, exact changed-path validation, repository-venv tests, scoped commit, resumable checkpoint, and no cleanup.

- [ ] Write tests for prompt construction with explicit skill/ticket/scope constraints, provider invocation, scope escape rejection, test failure checkpointing, successful commit, capacity failover handoff, and secret redaction.
- [ ] Run focused tests and confirm failures because the runner does not exist.
- [ ] Implement the runner and concrete Git checkpoint adapter with argument-list subprocess calls and bounded timeouts.
- [ ] Run execution/worktree/safe-stop tests and the complete controller suite.
- [ ] Commit the implementation-runner phase.

### Task 4: Real controller cycle and recovery

**Files:**
- Create: `runr_automation/src/runr_automation/engine.py`
- Modify: `runr_automation/src/runr_automation/cli.py`
- Modify: `runr_automation/src/runr_automation/reconciler.py`
- Modify: `runr_automation/src/runr_automation/pipeline.py`
- Test: `runr_automation/tests/test_engine.py`
- Test: `runr_automation/tests/test_end_to_end.py`
- Test: `runr_automation/tests/test_cli.py`

**Interfaces:**
- Produces: `ControllerCycle.run(poll: bool) -> CycleResult` and `ExecutionEngine.run_available() -> EngineResult`.
- Consumes: durable issue payloads, jobs, provider routing, scope registry, analysis jobs, implementation runner, and approval manager.
- Guarantees: `once` polls, reconciles, executes available work, and exits; `daemon` repeats the same cycle; provider capacity opens a circuit and tries the next allowed provider; success stops at `Awaiting Approval`.

- [ ] Write an integration test that records a structured issue, runs the cycle through implementation, verifies the scoped commit/checkpoint/attempt, and ends at an unapproved predeployment record.
- [ ] Write recovery tests for expired leases, interrupted provider attempts, all-provider capacity, stale fingerprints, and idempotent reruns.
- [ ] Run focused tests and confirm failures because no execution engine is wired.
- [ ] Implement deterministic stage handlers and wire `once`, `daemon`, `status`, `retry`, and reconciliation to them.
- [ ] Run engine/CLI/end-to-end tests and the complete controller suite.
- [ ] Commit the controller-cycle phase.

### Task 5: Operations guide and live provider end-to-end verification

**Files:**
- Modify: `runr_automation/config/runr-automation.example.yaml`
- Modify: `runr_automation/README.md`
- Modify: `runr_automation/docs/VERIFICATION.md`
- Modify: `runr_automation/docs/runr-local-automation-preflight.md`
- Test: `runr_automation/tests/test_end_to_end.py`
- Test: `runr_automation/tests/test_packaging.py`

**Interfaces:**
- Produces: documented configuration for explicit/discovered Codex and OpenCode commands, attempt limits, tests, recovery, and live smoke invocation.
- Consumes: the completed `runr-auto` commands and isolated local smoke tickets.

- [ ] Add a subprocess-level end-to-end test that runs `runr-auto once` with fake Linear/provider boundaries and verifies restart-safe approval waiting.
- [ ] Run the test and confirm it fails before final CLI fixture wiring.
- [ ] Complete example configuration and operator documentation, including what is automatic, what still requires approval, and how unknown subscription balances are estimated.
- [ ] Run all controller tests, Ruff, package installation/entry-point checks, CLI doctor/status, secret scan, and tracked-file boundary checks.
- [ ] Run two live isolated tickets through the controller: Codex first and OpenCode second; independently verify Python 3.12.7 tests, scope, commits, attempts, checkpoints, clean worktrees, and approval records.
- [ ] Commit the verification/documentation phase and write a redacted external checkpoint under `%LOCALAPPDATA%\RunrAutomation\checkpoints`.
