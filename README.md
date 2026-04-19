# Job Automation Platform

This repo now runs as one workspace-driven application.

The product surface is:
- scratch-built workspaces
- workflow templates
- queued or synchronous runs
- background workers
- generated artifacts
- review queue
- React frontend + JSON API

The old stage scripts still exist, but they are compatibility wrappers only.

## Main Entry Points

Use these first:

- `workspace_runner.py`
- `backend/api/server.py`
- `frontend/`

Legacy compatibility entrypoints:

- `main.py`
- `orchestrator.py`
- `stage1_scrape_enrich.py`
- `stage2_filter_local.py`
- `stage3_filter_ai.py`
- `stage4_docs_export.py`

## Setup (Windows + venv)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Frontend:

```powershell
cd frontend
npm install
```

## Secrets

Create `user_config/.env` when running local legacy-compatible flows:

```env
SCRAPEOPS_API_KEY=your_scrapeops_key
DEEPSEEK_API_KEY=your_deepseek_key
GEMINI_API_KEY=your_gemini_key
```

For the unified backend, prefer persisted backend secrets instead of raw config values.

## Run The Product

Backend API:

```powershell
.\.venv\Scripts\python.exe workspace_runner.py serve-api
```

Worker:

```powershell
.\.venv\Scripts\python.exe workspace_runner.py run-worker --worker-id local_worker
```

Frontend:

```powershell
cd frontend
npm run dev
```

Open:

```text
http://127.0.0.1:4173
```

## Create And Run Workspaces

The intended path is:

1. create a workspace from the frontend or `POST /workspace-builder/workspaces`
2. inspect/edit its settings
3. run it synchronously from the app or queue it for a worker
4. review jobs and download artifacts

CLI example:

```powershell
.\.venv\Scripts\python.exe workspace_runner.py list-templates
.\.venv\Scripts\python.exe workspace_runner.py list-workspaces
.\.venv\Scripts\python.exe workspace_runner.py run --workspace my_custom_workspace
```

Queue instead of executing immediately:

```powershell
.\.venv\Scripts\python.exe workspace_runner.py run --workspace my_custom_workspace --queue
```

## Scheduled Execution

The daily scripts now run a workspace through the unified backend instead of calling old orchestrators.

Example:

```powershell
.\run_daily.ps1 -WorkspaceId my_custom_workspace
```

## Legacy Compatibility

These still work, but they are no longer the product model:

- `main.py`
- `orchestrator.py`
- `bc_automation/orchestrator_blue_collar.py`

They exist only so older script-based usage does not break immediately.

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md).
