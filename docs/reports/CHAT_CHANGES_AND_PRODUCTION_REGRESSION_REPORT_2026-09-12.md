# Runr chat changes and production regression report

Recorded: 2026-09-12

## Executive finding

The current production UI was not changed from cursor pagination to a single all-jobs request. Both the source and the live frontend bundle still request 25 jobs initially and follow `next_cursor` for subsequent pages.

There is, however, an automatic prefetch regression risk: commit `530c7942` added an `IntersectionObserver` with a 720px root margin. If the sentinel remains visible, the browser can rapidly request successive 25-job partitions. That can look like “load everything” and can create unnecessary API load. The fallback “Load more jobs” button remains present.

The Render deployment failure is a separate runtime-contract mismatch. `deploy/start.sh` defaults to `/app/.venv/bin/python`, but `Dockerfile.api` and `Dockerfile.worker` install requirements with the system `python` and never create `/app/.venv`. Render logs showed:

```text
Missing required project interpreter: /app/.venv/bin/python
```

The latest API deployment attempts are therefore `pre_deploy_failed`. The worker service is currently live on release `107114620765b52a0c3f41abaf51d4cda67edfab`; this package does not stop or restart it.

## What was changed in the prior workstream

Relative to the source inventory baseline `c25d394ab9355e4d08a058589d9e125df9ee7444`, the production source history includes:

- restoration of the canonical publication chain and display-first recovery;
- bounded acquisition wrappers and VPS timer/runtime wiring;
- LinkedIn apply-destination and Easy Apply evidence handling;
- company/job canonicalization and publication projection changes;
- logo/source/application fields in the job projection and card path;
- publisher and audit tooling, tests, and operational handoff documentation.

Those changes were not intended to remove pagination. The pagination implementation is present in `frontend/src/components/personalized/JobsWorkspace.jsx`, `backend/application/personalized_jobs_service.py`, and `backend/repositories/sqlite_personalized_jobs.py`.

## What was not done

No new production code was changed during this packaging/diagnostic turn. In particular, the automatic prefetch behavior and the Render interpreter mismatch were identified but not silently redesigned or deployed. This preserves the requested design-review checkpoint.

The previous workstream did deviate from the original “display-only Render, acquisition on VPS” goal by retaining a substantial API/worker runtime contract and by adding display-first publication recovery around the existing acquisition state. That is visible in the release history and is included in the source snapshot in the package; it was not a deliberate removal of partitioning.

## Evidence inspected

### Pagination

- Initial frontend request: `limit: 25` and `view: "cards"`.
- Follow-up request: `cursor: feed.next_cursor` and `limit: 25`.
- Results are appended page-by-page in the browser.
- Backend clamps the request limit and queries `limit + 1` rows to determine whether another cursor exists.
- SQL-backed publication queries use `LIMIT ?` with the bounded page size.
- The live `JobsWorkspace` bundle contains `next_cursor`, `IntersectionObserver`, and the “Load more jobs” fallback.

### Render deployment

- `render.yaml` points `runr-api` at `Dockerfile.api` and `./deploy/start.sh api`.
- `render.yaml` points `runr-worker` at `Dockerfile.worker` and `./deploy/start.sh worker`.
- Both Dockerfiles run `python -m pip install ...` but do not run `python -m venv /app/.venv`.
- `deploy/start.sh` checks for an executable `${RUNR_PYTHON_BIN:-/app/.venv/bin/python}` before starting either API or worker roles.
- Read-only Render inspection showed the API’s latest deploy attempts in `pre_deploy_failed` state with the missing-interpreter error.

### Data/provider safety

- The VPS was left running.
- No acquisition cycle, publisher replay, Turso write, or R2 write was run for this package.
- A Turso read probe was blocked by the current plan (`SQL read operations are forbidden`), so no new live Turso counts are asserted here.
- No secrets, `.env` files, state databases, or preserved large catalog outputs are included in the zip.

## Controlled next actions requiring approval

1. Fix the container runtime contract by either creating `/app/.venv` in both images or changing the launcher to the interpreter actually built into the image, then verify the API pre-deploy and worker startup.
2. Keep backend cursor pagination and change the frontend observer to an explicitly bounded/guarded prefetch or explicit user-triggered loading, depending on the approved UX.
3. Redeploy only the affected Render service(s), verify `/health/live` and `/health/ready`, and inspect request/page counts before touching Turso or the VPS acquisition timers.

## Package scope

The accompanying zip contains the tracked producer/deployment source changed after the source-inventory baseline, the relevant pagination/deployment files, and the operations/reports created in this workstream. It excludes credentials, environment files, databases, generated caches, and the large preserved catalog snapshots.
