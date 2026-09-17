# Runr Local Automation Preflight

**Phase:** Preflight and specification lock  
**Date:** 2026-09-17  
**Repository:** `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper`  
**Branch:** `docs/phase3-integration`  
**Baseline ref:** `41776666` (`docs(reverse-engineering): record Phase 4 organization-acceptance checklist`)

## Repository path mapping

| Requested concern | Actual repository location | Result |
|---|---|---|
| Project control instructions | `AGENTS.md` | Uses `.venv\Scripts\python.exe`; required Python is 3.12.7 |
| Python/test configuration | `pyproject.toml` | Pytest roots at `tests`; Ruff is configured here |
| JavaScript command wrapper | `scripts/run-python.cjs` | Resolves the project virtualenv before spawning Python |
| Document index | `docs/INDEX.md` | Canonical documentation entry point |
| Subsystem registry | `docs/subsystems.yaml` | Current machine-readable subsystem ownership registry |
| Ticket template and label contract | `docs/tickets/TEMPLATE.md` | Current Linear ticket structure and grouped-label contract |
| Existing automation package | No `tools/` directory or `tools/runr_automation/` package | New package required; no duplicate package found |
| Current Python application entry point | `workspace_runner.py` | Existing product CLI; local controller should use a separate `runr-auto` entry point |
| Existing Runr skills | `.agents/skills/runr-ticket-creation/`, `runr-ticket-start/`, `runr-ticket-merge-predeployment/`, `runr-ticket-batch-merge-predeployment/`, `runr-ticket-merge-deployment/`, `runr-ticket-batch-merge-deployment/`, `runr-discard-issue/` | All seven exist; their current files are already untracked user worktree content and must be preserved while revised |
| Test suite | `tests/` | Existing Python test suite; no `tests/runr_automation/` directory exists |
| Dependency manifests | `requirements.txt`, `requirements-dev.txt`, `package.json` | Python dependencies are installed in the project venv; frontend/extension checks remain separate |
| Local credentials convention | `user_config/.env` documented by `README.md` | Secrets must remain outside repository artifacts and logs |

## Baseline verification

Interpreter verification:

```text
.\.venv\Scripts\python.exe --version
Python 3.12.7
```

Commands run from the repository root:

```text
.\.venv\Scripts\python.exe -m ruff check backend tests workspace_runner.py
All checks passed!

.\.venv\Scripts\python.exe -m pytest -q tests/test_backend_application.py tests/test_sqlite_repositories.py tests/test_worker_service.py tests/test_phase0_contracts.py tests/test_job_dedupe.py tests/test_assisted_apply_connection_service.py tests/test_env_config.py
118 passed, 21 subtests passed in 60.06s

.\.venv\Scripts\python.exe -m pytest -q tests/test_backend_api.py -k "assisted_apply or extension_cors or extension_origin or clerk_only_identity"
5 passed, 114 deselected, 7 subtests passed in 14.30s
```

## Scope and safety notes

- No Linear API calls or mutations were attempted during preflight.
- No production code, skill, configuration, or existing user-authored file was changed by this phase except this preflight record.
- The worktree was already dirty before this phase, including modified documentation, seven untracked Runr skill directories, generated reports, archives, and a modified production-debug helper. Those changes are outside this phase and remain untouched.
- The next phase is the core local package: configuration, SQLite schema migrations, typed models, redaction, CLI shell, process lock, and focused tests.
