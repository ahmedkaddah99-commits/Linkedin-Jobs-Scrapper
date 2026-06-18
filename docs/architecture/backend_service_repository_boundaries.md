# Backend Service And Repository Boundaries

Status: active agent context

Date: 2026-05-31

Wave 4 introduced explicit backend boundaries without changing public behavior.

## Application Facade

`backend/application/services.py` still exposes `BackendApplication` as the compatibility facade for API routes, workers, CLI entrypoints, and tests.

`BackendApplication` now has typed constructor boundaries:

- `repositories: BackendRepositories`
- `registries: BackendRegistriesProtocol`
- `stage_engine: StageEngineProtocol`

New application service modules should be added behind the facade so callers can keep using `BackendApplication`.

## Extracted Domain Services

Extracted application services currently include:

- `WorkspaceCatalogService`: workspace CRUD, workflow template CRUD, registry listing, and workspace builder catalog payloads.
- `IdentityAccessService`: users, API tokens, workspace access checks, secrets, and runtime secret resolution.
- `RunLifecycleService`: run, job-set, artifact, review, worker, queue, retry, and execution behavior.
- `TrackerApplicationService`: referrals, job workspaces, relevant-people discovery, and user-level tracker duplicate detection.

The facade delegates to these services. Keep new service extraction small and cohesive; avoid rewriting API, worker, and CLI callers at the same time.

## Repository Contracts

`backend/repositories/contracts.py` owns repository protocols and the typed `BackendRepositories` dataclass.

Repository implementations should satisfy these protocols:

- workspace repository
- run repository
- job store
- artifact store
- review store
- auth repository
- secret store
- worker store
- analytics store
- config store
- optional source-policy store

Public imports through `backend.repositories` remain compatible.

## SQLite Split

SQLite ownership is now separated:

- `backend/repositories/sqlite_backed.py`: concrete SQLite store classes.
- `backend/repositories/sqlite_core.py`: shared SQLite connection handling and base schema bootstrap.
- `backend/repositories/sqlite_migrations.py`: runtime migrations and application-status-history row helpers.

Keep schema changes in `sqlite_migrations.py` or `sqlite_core.py` depending on whether they are migration logic or base schema creation. Store behavior should stay in `sqlite_backed.py` unless a follow-up splits stores into domain modules.
