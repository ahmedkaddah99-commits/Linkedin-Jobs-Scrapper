# Unified Backend Architecture

## Goal
This repo now has a first-pass unified backend that treats job automation as a composition of:

- job sources
- screening modules
- prioritization/classification modules
- profile generation strategies
- document/package output modules

Workspaces are created from those building blocks instead of being hardcoded product modes.

The backend is organized around reusable capabilities and a stage engine. The active runtime surface now lives in `backend/` plus `workspace_runner.py`.

Shared config, CV loading, pipeline job schema, and dedupe helpers now also live inside `backend/`:

- [backend/config/job_seeker.py](./backend/config/job_seeker.py)
- [backend/profiles/cv_text.py](./backend/profiles/cv_text.py)
- [backend/domain/pipeline_jobs.py](./backend/domain/pipeline_jobs.py)
- [backend/domain/job_identity.py](./backend/domain/job_identity.py)

The old root wrappers were removed after the generic backend surface became authoritative.

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
- starter workflow templates and workspace-builder helpers

Plain language: a run is now executed by one central engine that reads a workflow definition and calls the required stages in order. New databases start with starter templates only; end users are expected to create their own workspaces from scratch.

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

### Stage adapters
Located under [backend/adapters/stage_adapters.py](./backend/adapters/stage_adapters.py).

Tailored-document stages are now consumed through generic backend capability packages:

- [backend/capabilities/tailored_documents/acquisition.py](./backend/capabilities/tailored_documents/acquisition.py)
- [backend/capabilities/tailored_documents/documents.py](./backend/capabilities/tailored_documents/documents.py)

Tailored-document helper capabilities are split into focused modules:

- [backend/capabilities/tailored_documents/common.py](./backend/capabilities/tailored_documents/common.py)
- [backend/capabilities/tailored_documents/snapshotting.py](./backend/capabilities/tailored_documents/snapshotting.py)
- [backend/capabilities/tailored_documents/title_filter.py](./backend/capabilities/tailored_documents/title_filter.py)
- [backend/capabilities/tailored_documents/linkedin_connector.py](./backend/capabilities/tailored_documents/linkedin_connector.py)
- [backend/capabilities/tailored_documents/generation.py](./backend/capabilities/tailored_documents/generation.py)
- [backend/capabilities/tailored_documents/cv_structuring.py](./backend/capabilities/tailored_documents/cv_structuring.py)
- [backend/capabilities/tailored_documents/rendering.py](./backend/capabilities/tailored_documents/rendering.py)
- [backend/capabilities/tailored_documents/tracker_export.py](./backend/capabilities/tailored_documents/tracker_export.py)

`documents.py` is now a thin Stage 4 orchestrator over those modules rather than the place where prompt building, CV structuring, rendering, and export logic live.

Reusable-package stages are now consumed through generic backend capability packages:

- [backend/capabilities/reusable_packages/acquisition.py](./backend/capabilities/reusable_packages/acquisition.py)
- [backend/capabilities/reusable_packages/filtering.py](./backend/capabilities/reusable_packages/filtering.py)
- [backend/capabilities/reusable_packages/classification.py](./backend/capabilities/reusable_packages/classification.py)
- [backend/capabilities/reusable_packages/reusable_profiles.py](./backend/capabilities/reusable_packages/reusable_profiles.py)
- [backend/capabilities/reusable_packages/packaging.py](./backend/capabilities/reusable_packages/packaging.py)

Job-board source collection now lives in generic backend connector packages:

- [backend/connectors/job_boards/strategies.py](./backend/connectors/job_boards/strategies.py)
- [backend/connectors/job_boards/collector.py](./backend/connectors/job_boards/collector.py)

Plain language: the active backend import surface is now generic (`tailored_documents`, `reusable_packages`, `job_boards`), and the older silo module paths and wrapper scripts have been removed.

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
- `GET /workspace-builder/catalog`
- `POST /workspace-builder/workspaces`
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

## Starter Templates And Scratch Workspaces

The backend now seeds starter workflow templates, not default customer workspaces. The starter templates are:

- `search_apply_v1`
- `curated_apply_v1`
- `blended_sources_apply_v1`
- `board_package_v1`

End-user workspaces are created through the scratch builder in:

- [backend/orchestration/workspace_builder.py](./backend/orchestration/workspace_builder.py)
- `GET /workspace-builder/catalog`
- `POST /workspace-builder/workspaces`

These definitions live in [backend/orchestration/seeded_workspaces.py](./backend/orchestration/seeded_workspaces.py) and [backend/orchestration/workspace_builder.py](./backend/orchestration/workspace_builder.py).

## Current Execution Model

### Tailored Document Flow
Typical workflow:

1. acquire listings or ingest curated URLs
2. optionally merge and deduplicate sources
3. run screening
4. optionally prioritize surviving jobs
5. generate tailored application documents

### Reusable Package Flow
Typical workflow:

1. collect jobs from job boards
2. run screening
3. classify jobs into reusable role groups
4. generate reusable role/profile outputs
5. package application exports

The product-facing backend packages, stage types, connectors, templates, and workspace builder now use generic terminology.

## Commands

List workspaces:

```powershell
.venv\Scripts\python.exe workspace_runner.py list-workspaces
```

Dry-run a workspace plan:

```powershell
.venv\Scripts\python.exe workspace_runner.py run --workspace my_custom_workspace --dry-run
```

List backend connectors:

```powershell
.venv\Scripts\python.exe workspace_runner.py list-connectors
```

Run a reusable-package workspace through the unified backend:

```powershell
.venv\Scripts\python.exe workspace_runner.py run --workspace my_custom_workspace
```

Start the API:

```powershell
.venv\Scripts\python.exe workspace_runner.py serve-api
```

Queue a run:

```powershell
.venv\Scripts\python.exe workspace_runner.py run --workspace my_custom_workspace --queue
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

The obsolete top-level launcher scripts were removed. `workspace_runner.py` is now the single supported operator entrypoint.

## Migration Direction

This is the intended next sequence:

1. add session/login flows and externalize auth beyond bootstrap bearer-token issuance
2. move from local persisted secrets to an external secret manager in production deployments
3. add richer audit history, rate limits, and operational dashboards on top of the worker/API surfaces
4. keep expanding capabilities through generic stages, strategies, and workspace data rather than reintroducing product silos

## Important Constraint
The backend should continue to gain capabilities without adding new top-level product silos. New customer experiences should be new workspace/workflow data, new strategies, or new stage adapters, not new parallel code universes.
