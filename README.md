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

## Main Entry Points

Use these first:

- `workspace_runner.py`
- `backend/api/server.py`
- `frontend/`

## Setup (Windows + venv)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

For local verification and cleanup work, install the dev tools too:

```powershell
pip install -r requirements-dev.txt
```

Frontend:

```powershell
cd frontend
npm install
```

Create `frontend/.env.local` for the Vite client:

```env
VITE_API_BASE_URL=/v1
VITE_CLERK_PUBLISHABLE_KEY=your_clerk_publishable_key
```

## Secrets

Create `user_config/.env` for local external-service credentials:

```env
SCRAPEOPS_API_KEY=your_scrapeops_key
DEEPSEEK_API_KEY=your_deepseek_key
GEMINI_API_KEY=your_gemini_key
# Optional: disable billing quota enforcement during local development.
RUNR_DISABLE_QUOTAS=true
```

For the unified backend, prefer persisted backend secrets instead of raw config values.

## Run The Product

All successful local start commands currently available in this repo are below.

Start API + worker + frontend from one terminal at the repo root:

```powershell
npm run dev
```

Start only the API from the repo root:

```powershell
npm run dev:api
```

Start only the worker from the repo root:

```powershell
npm run dev:worker
```

Start only the frontend from the repo root:

```powershell
npm run dev:ui
```

Start only the frontend from inside `frontend/`:

```powershell
cd frontend
npm run dev
```

If you start services individually, the equivalent direct Python commands are:

```powershell
.\.venv\Scripts\python.exe workspace_runner.py serve-api
.\.venv\Scripts\python.exe workspace_runner.py run-worker --worker-id local_worker
```

Local URLs:

```text
Frontend: http://127.0.0.1:4173
API health: http://127.0.0.1:8000/health
```

## Production

Do not use `npm run dev` for production. Production expects:

- a ready Python virtualenv at `.venv`
- frontend dependencies installed
- required backend environment variables configured from `.env.example`
- a process manager such as PM2

Build and start the production stack with:

```powershell
npm run pm2:prod
```

Useful production process commands:

```powershell
npm run pm2:status
npm run pm2:logs
npm run pm2:stop
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

## Architecture

Start with [docs/architecture/current_system.md](./docs/architecture/current_system.md) for current agent context, then use [ARCHITECTURE.md](./ARCHITECTURE.md) for the longer historical architecture narrative.

## Verification

Fast checks from the repo root:

```powershell
npm run check
npm run check:backend
npm run check:frontend
```

`check:backend` runs Ruff plus a documented fast pytest subset. Use `npm run check:backend:api` for the slower API sweep and `npm run check:backend:full` before larger merges. `check:frontend` currently uses the Vite production build as the frontend check.
