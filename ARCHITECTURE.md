# Unified Backend Architecture

## Goal
This repo now has a first-pass unified backend that treats:

- white-collar LinkedIn
- white-collar manual URLs
- blue-collar

as **workspace/workflow configurations**, not separate backend code silos.

The backend is organized around reusable capabilities and a stage engine. The existing scripts remain in place as migration adapters.

## What Was Added

### Shared domain model
Located under [backend/domain](./backend/domain):

- `WorkspaceDefinition`
- `WorkflowTemplate`
- `RunRecord`
- `RunPlan`
- `StageDefinition`
- `StageResult`
- `JobRecord`
- `ArtifactRecord`
- `UserRecord`
- `ApiTokenRecord`
- `SecretRecord`
- `ProfileRef`
- `PromptSetRef`
- `JobSource`

Plain language: the system now has one shared vocabulary for workspaces, runs, jobs, stages, artifacts, users, API tokens, secrets, profiles, and prompt families.

### Stage engine
Located under [backend/orchestration](./backend/orchestration):

- `StageEngine`
- `BaseStage`
- `StageOutcome`
- stage/component registries
- seeded workflow templates and seeded workspaces

Plain language: a run is now executed by one central engine that reads a workflow definition and calls the required stages in order.

### Repository layer
Located under [backend/repositories](./backend/repositories):

- `SqliteWorkspaceRepository`
- `SqliteRunRepository`
- `SqliteJobStore`
- `SqliteArtifactStore`
- `SqliteReviewStore`
- `SqliteAuthRepository`
- `SqliteSecretStore`
- `SqliteWorkerStore`
- `FileWorkspaceRepository`
- `FileRunRepository`
- `FileJobStore`
- `FileArtifactStore`
- `FileReviewStore`
- `FileAuthRepository`
- `FileSecretStore`
- `FileWorkerStore`

SQLite now applies internal schema migrations through `schema_migrations` and persists normalized runtime tables for:

- `run_stage_results`
- `run_jobs`
- `workers`

Plain language: the backend now has a real SQLite-backed system of record by default for workspaces, runs, normalized run state, artifacts, reviews, users, API tokens, secrets, and worker leases, while the older file-backed repositories remain available as an explicit fallback.

### Auth + Secrets
Located under [backend/security](./backend/security):

- [backend/security/auth.py](./backend/security/auth.py)
- [backend/security/secrets.py](./backend/security/secrets.py)

The API now uses bearer-token authentication backed by persisted users and API tokens. Authorization is scope-based with workspace-level access checks.

Secrets are stored separately from workspace definitions and can be referenced in runtime settings with:

- `${secret:secret_id}`
- `${env:ENV_VAR_NAME}`

Plain language: the frontend or operator can point workspace/run settings at a secret reference, and the backend resolves it only at execution time instead of baking the raw value into workspace config or run responses.

### Legacy stage adapters
Located under [backend/adapters/legacy_stages.py](./backend/adapters/legacy_stages.py).

White-collar stages are now called in-process through dedicated backend capability modules:

- [backend/capabilities/white_collar/acquisition.py](./backend/capabilities/white_collar/acquisition.py)
- [backend/capabilities/white_collar/documents.py](./backend/capabilities/white_collar/documents.py)

White-collar helper capabilities are now split further into focused modules:

- [backend/capabilities/white_collar/common.py](./backend/capabilities/white_collar/common.py)
- [backend/capabilities/white_collar/snapshotting.py](./backend/capabilities/white_collar/snapshotting.py)
- [backend/capabilities/white_collar/title_filter.py](./backend/capabilities/white_collar/title_filter.py)
- [backend/capabilities/white_collar/linkedin_connector.py](./backend/capabilities/white_collar/linkedin_connector.py)
- [backend/capabilities/white_collar/generation.py](./backend/capabilities/white_collar/generation.py)
- [backend/capabilities/white_collar/cv_structuring.py](./backend/capabilities/white_collar/cv_structuring.py)
- [backend/capabilities/white_collar/rendering.py](./backend/capabilities/white_collar/rendering.py)
- [backend/capabilities/white_collar/tracker_export.py](./backend/capabilities/white_collar/tracker_export.py)

`documents.py` is now a thin Stage 4 orchestrator over those modules rather than the place where prompt building, CV structuring, rendering, and export logic live.

Blue-collar stages are now called in-process through dedicated backend capability modules:

- [backend/capabilities/blue_collar/acquisition.py](./backend/capabilities/blue_collar/acquisition.py)
- [backend/capabilities/blue_collar/filtering.py](./backend/capabilities/blue_collar/filtering.py)
- [backend/capabilities/blue_collar/classification.py](./backend/capabilities/blue_collar/classification.py)
- [backend/capabilities/blue_collar/role_cvs.py](./backend/capabilities/blue_collar/role_cvs.py)
- [backend/capabilities/blue_collar/packaging.py](./backend/capabilities/blue_collar/packaging.py)

Blue-collar source collection now lives in backend connector modules rather than the legacy `bc_automation` folder:

- [backend/connectors/blue_collar/strategies.py](./backend/connectors/blue_collar/strategies.py)
- [backend/connectors/blue_collar/collector.py](./backend/connectors/blue_collar/collector.py)

The root and `bc_automation` stage scripts are now thin CLI wrappers only:

- `stage1_scrape_enrich.py`
- `stage4_docs_export.py`

- `stage1_scrape_blue_collar.py`
- `stage2_filter_blue_collar.py`
- `stage3_classify_blue_collar.py`
- `stage4_build_role_cvs.py`
- `stage5_generate_blue_collar_docs.py`

Plain language: the real business logic now lives in backend service modules, and the old script files are just entrypoints for manual/legacy CLI use.

### API
Located under [backend/api/server.py](./backend/api/server.py).

Authentication:

- `Authorization: Bearer <token>`

Routing:

- both `/...` and `/v1/...` are supported

Hardening:

- JSON-object request validation
- structured error responses
- `limit` + `offset` pagination on list endpoints

Endpoints:

- `GET /health`
- `GET /auth/me`
- `GET /users`
- `GET /users/{id}`
- `POST /users`
- `PUT /users/{id}`
- `DELETE /users/{id}`
- `GET /users/{id}/tokens`
- `POST /users/{id}/tokens`
- `DELETE /users/{id}/tokens/{token_id}`
- `GET /secrets`
- `GET /secrets/{id}`
- `POST /secrets`
- `PUT /secrets/{id}`
- `DELETE /secrets/{id}`
- `GET /workflow-templates`
- `GET /workflow-templates/{id}`
- `POST /workflow-templates`
- `PUT /workflow-templates/{id}`
- `DELETE /workflow-templates/{id}`
- `GET /workspaces`
- `GET /workspaces/{id}`
- `POST /workspaces`
- `PUT /workspaces/{id}`
- `DELETE /workspaces/{id}`
- `GET /connectors`
- `GET /generations`
- `GET /renderers`
- `GET /runs`
- `GET /runs/{id}`
- `POST /runs`
- `POST /runs/{id}/cancel`
- `POST /runs/{id}/retry`
- `POST /runs/{id}/resume`
- `GET /runs/{id}/jobs`
- `GET /runs/{id}/jobs/{set_key}`
- `PUT /runs/{id}/jobs/{set_key}`
- `DELETE /runs/{id}/jobs/{set_key}`
- `GET /runs/{id}/artifacts`
- `GET /runs/{id}/artifacts/{artifact_id}`
- `PUT /runs/{id}/artifacts/{artifact_id}`
- `DELETE /runs/{id}/artifacts/{artifact_id}`
- `GET /runs/{id}/reviews`
- `GET /runs/{id}/reviews/{review_id}`
- `POST /runs/{id}/reviews`
- `PUT /runs/{id}/reviews/{review_id}`
- `DELETE /runs/{id}/reviews/{review_id}`
- `GET /workers`
- `GET /workers/{id}`
- `POST /workers/process-next`
- `POST /workers/recover-stale`

Plain language: the API now covers workspace/template CRUD, paginated run control, worker visibility/recovery, and run-scoped job/artifact/review resources through a versionable HTTP surface.

### Queue + Worker Execution
Runs can now be created in three modes:

- `planned`
- `queued`
- `sync`

The backend now supports:

- retry attempts via `max_attempts`
- cooperative cancellation through `cancel_requested`
- resumability by preserving completed stage outputs and continuing from the next unfinished stage
- authenticated API access through bearer tokens
- runtime secret resolution without persisting resolved secret values into run records
- worker leases with heartbeats and stale-worker recovery

There is now a real worker service under [backend/worker/service.py](./backend/worker/service.py). It refreshes its lease while a run is executing and marks itself stopped when the loop exits.

Plain language: the backend can hold work for later, process it through a lease-aware worker, recover abandoned runs after stale heartbeats, retry transient failures, stop cleanly between stages, and resume a partially successful run without restarting from zero by default.

### Workspace runner
Located at [workspace_runner.py](./workspace_runner.py).

This is the generic entrypoint for:

- listing workspaces
- listing workflow templates
- listing connectors / generators / renderers
- creating users and issuing API tokens
- creating and rotating backend secrets
- listing worker leases
- listing runs
- executing, queueing, or planning any workspace
- cancelling, retrying, and resuming runs
- processing one queued run or running a lease-aware worker loop
- serving the API

## Seeded Workspaces

The backend seeds these default workspaces:

- `white_collar_linkedin`
- `white_collar_manual_urls`
- `white_collar_combined`
- `blue_collar_default`

These definitions live in [backend/orchestration/seeded_workspaces.py](./backend/orchestration/seeded_workspaces.py).

## Current Execution Model

### White-collar LinkedIn
Workflow:

1. LinkedIn acquisition and enrichment
2. local filter
3. ranking/final filter
4. CV generation + document export

### White-collar Manual URLs
Workflow:

1. manual URL ingestion
2. dedupe
3. CV generation + document export

### White-collar Combined
Workflow:

1. LinkedIn acquisition
2. local filter
3. ranking/final filter
4. manual URL ingestion
5. merge + dedupe
6. CV generation + document export

### Blue-collar
Workflow:

1. portal scrape
2. local filter
3. role classification
4. reusable role CV generation
5. package/export

## Commands

List workspaces:

```powershell
.venv\Scripts\python.exe workspace_runner.py list-workspaces
```

Dry-run a workspace plan:

```powershell
.venv\Scripts\python.exe workspace_runner.py run --workspace white_collar_combined --dry-run
```

List backend connectors:

```powershell
.venv\Scripts\python.exe workspace_runner.py list-connectors
```

Run blue-collar through the unified backend:

```powershell
.venv\Scripts\python.exe workspace_runner.py run --workspace blue_collar_default
```

Start the API:

```powershell
.venv\Scripts\python.exe workspace_runner.py serve-api
```

Queue a run:

```powershell
.venv\Scripts\python.exe workspace_runner.py run --workspace white_collar_manual_urls --queue
```

Process the next queued run:

```powershell
.venv\Scripts\python.exe workspace_runner.py process-next
```

Run a polling worker:

```powershell
.venv\Scripts\python.exe workspace_runner.py run-worker --worker-id worker_a --sleep-seconds 5 --lease-seconds 60
```

Bootstrap an admin user and token:

```powershell
.venv\Scripts\python.exe workspace_runner.py create-user --email admin@example.com --display-name Admin --role admin
.venv\Scripts\python.exe workspace_runner.py create-token --user-id <user_id> --name bootstrap
```

Create a stored secret:

```powershell
.venv\Scripts\python.exe workspace_runner.py set-secret --name openai_api_key --provider stored --value "<secret>"
```

Use the legacy file-backed repositories explicitly:

```powershell
.venv\Scripts\python.exe workspace_runner.py --storage file list-workspaces
```

## Migration Direction

This is the intended next sequence:

1. add session/login flows and externalize auth beyond bootstrap bearer-token issuance
2. move from local persisted secrets to an external secret manager in production deployments
3. add richer audit history, rate limits, and operational dashboards on top of the worker/API surfaces
4. retire direct script orchestration once all legacy stages have service equivalents

## Important Constraint
The backend should continue to gain capabilities without adding new top-level product silos. New customer experiences should be new workspace/workflow data, new strategies, or new stage adapters, not new parallel code universes.
