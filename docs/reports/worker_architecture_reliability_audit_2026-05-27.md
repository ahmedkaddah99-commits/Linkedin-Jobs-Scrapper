# Worker Architecture & Reliability Audit - 2026-05-27

Date: 2026-05-27  
Scope: Runr backend worker architecture, queue behavior, SQLite persistence, reliability risks, and worker logging implementation.

## 1. Worker Overview

The Runr worker is a Python backend service implemented in `backend/worker/service.py`. It is not a separate product or framework; it is Runr's local queue consumer. In standard architecture language, this is a worker process: a long-running process that polls a queue, claims work, executes it, sends heartbeats, and marks itself stopped when it exits.

In local development, the worker is a separate OS process from the API. `package.json` runs three processes with `npm run dev`: the API (`workspace_runner.py serve-api`), the worker (`workspace_runner.py run-worker --worker-id local_worker`), and the frontend. The backend API can also trigger one unit of worker processing through `POST /workers/process-next`, but that is a manual/API execution path, not the normal long-running worker loop.

The queue is the `runs` table. A run enters the queue when the API or CLI creates it with `execution_mode=queued` or `enqueue=True`. The worker loop then:

1. Starts and writes a heartbeat row to the `workers` table.
2. Periodically runs scheduled ScrapeOps maintenance.
3. Recovers expired workers whose lease has elapsed.
4. Enqueues due scheduled workspace runs.
5. Claims the oldest queued run using a SQLite `BEGIN IMMEDIATE` transaction.
6. Marks the run `running` and increments `attempt_count`.
7. Starts a heartbeat thread while the run executes.
8. Calls `BackendApplication.execute_claimed_run(...)`.
9. Logs task completion, failure, cancellation, and summary.
10. Releases its worker lease and returns to polling.

Triggers found:

- HTTP run creation endpoints with `execution_mode=queued`.
- CLI `workspace_runner.py run --queue`.
- Recurring workspace schedules via `enqueue_due_scheduled_runs()`.
- Manual worker execution through `workspace_runner.py process-next`.
- Manual/API worker execution through `POST /workers/process-next`.
- Long-running polling through `workspace_runner.py run-worker`.

## 2. Failure Analysis

The old failure mode was that a queued run could remain queued when the long-running worker process was not alive or was not actually using the lease-aware worker path. That was corrected earlier by routing both CLI/API one-off processing through `WorkerService.process_next()`.

If the worker process crashes while it has a valid `current_run_id`, stale-worker recovery can requeue that run after the lease expires. This is a useful safety net, but it is not a complete production queue. If the process is killed at an unlucky point or the worker row is inconsistent, a run can still require explicit recovery. The architecture should add a direct orphaned-running-run sweeper before scale: any `running` run without a live worker lease should be moved back to `queued` or `failed` with a clear error.

What is lost on a crash:

- In-memory stage state is lost.
- The active run may need stale-worker recovery.
- Partial external side effects may already have happened, depending on the stage.
- Database-persisted run, stage, job, artifact, review, and worker records remain.

Main crash/stuck triggers:

- Worker process not started while API accepts queued runs.
- Multiple local dev stacks running at the same time with the same `local_worker` ID.
- Worker killed during a long scraping or document generation run.
- External API timeouts or exceptions inside a stage.
- SQLite write contention when multiple worker/API operations write at the same time.
- Missing operational logging, which previously made failures look like silent UI issues.

Local finding on 2026-05-27: multiple API, worker, and frontend dev processes were running simultaneously. That creates confusing behavior because several processes can heartbeat or process work using the same `local_worker` identity. The duplicate local processes were stopped and one clean `npm run dev` stack was started.

## 3. Scale Assessment

Current capacity is intentionally small. One `local_worker` processes exactly one run at a time. With 10 simultaneous users, runs queue and execute serially unless more workers are started. With 50 users, backlog and API/SQLite contention become likely. With 500 users, this architecture is not suitable.

Current controls:

- Queue claim is atomic at the SQLite level with `BEGIN IMMEDIATE`.
- Worker leases and heartbeats exist.
- Stale worker recovery exists.
- Per-run attempts exist through `attempt_count` and `max_attempts`.

Missing controls:

- No external durable job broker.
- No queue visibility timeout beyond the custom worker lease.
- No per-source scraping rate limiter.
- No global concurrency budget for ScrapeOps, LinkedIn, LLM calls, or document generation.
- No production-grade worker supervisor in the Python code itself.
- No admin UI for run logs yet.

Realistic capacity:

- Local/dev: 1 worker, 1 active run.
- Small internal use: 1-3 workers may work if runs are not heavy and SQLite write contention stays low.
- Beyond that: expect SQLite write locks, scraping provider limits, and queue backlog to break user expectations before CPU is the main bottleneck.

To support many concurrent users, Runr should move the queue to a standard worker system such as Celery/RQ with Redis, or an equivalent managed queue. The database should move to PostgreSQL, and workers should run as horizontally scalable processes with explicit concurrency limits by task type and source type.

## 4. Database Assessment

The default database is SQLite at `.backend_data/backend.sqlite3`, created by `create_backend(..., storage_backend="sqlite")`. There is also a file-backed storage option, but the active local backend uses SQLite. "Lightweight" here means a single local file database with minimal operational setup.

SQLite is appropriate for local development and small single-user/internal workflows. It is not the right long-term database for a multi-user scraping and document-generation platform.

Observed SQLite configuration:

- Each repository call opens a new SQLite connection.
- `PRAGMA foreign_keys = ON` is enabled.
- No WAL mode configuration was found.
- No `busy_timeout` configuration was found.
- Queue claim uses `BEGIN IMMEDIATE`, which takes a write lock.

Concurrency implications:

- SQLite allows many readers but only one writer at a time.
- Long write transactions or frequent writes can block other write operations.
- Worker heartbeats, run updates, stage results, job storage, API writes, and analytics ledger inserts all compete for the same writer lock.

Recommended upgrade path:

1. Short term: enable WAL mode and a busy timeout for SQLite to reduce local lock errors.
2. Near term: add orphaned-run recovery and clearer queue/admin diagnostics.
3. Production: move operational data to PostgreSQL.
4. Production queue: move run execution to Celery/RQ plus Redis, or a managed queue.
5. Split high-volume telemetry if needed, but keep run state transactional in PostgreSQL first.

## 5. Logging Implementation

Structured worker logging was implemented on 2026-05-27.

Files changed:

- `backend/worker/logging_config.py`
- `backend/worker/service.py`
- `backend/worker/__init__.py`
- `workspace_runner.py`
- `backend/api/server.py`
- `tests/test_worker_service.py`
- `logs/.gitignore`

Worker logs now write JSON lines to both stdout and `logs/worker.log`. The file handler uses rotation with max size 10 MB and keeps the last 5 files.

Logged fields include:

- `timestamp`
- `level`
- `logger`
- `message`
- `worker_id`
- `worker_process_id`
- `host_name`
- `run_id`
- `workspace_id`
- `task_name`
- `duration_ms`
- `status`
- `attempt_count`
- `max_attempts`
- `stage_count`
- `job_set_count`
- `artifact_count`
- `error_message`
- `stack_trace` when an exception is present

Worker event coverage:

- INFO: loop start, task start, task complete, run summary, loop stop.
- WARNING: retries, stale worker recovery, cancellation, unexpected run status, slow operations.
- ERROR: claim failures, heartbeat failures, task exceptions, failed runs, release failures, stop failures, DB/application exceptions surfaced through worker calls.

Where to look now:

- Live worker file log: `logs/worker.log`
- API/dev stdout and stderr logs if using the current local scripts: `.runr_dev_stdout.log` and `.runr_dev_stderr.log`
- Older manual logs may still exist as `.backend_worker_stdout.log`, `.backend_worker_stderr.log`, `.backend_api_stdout.log`, `.backend_api_stderr.log`
- Database run state: `.backend_data/backend.sqlite3`, table `runs`
- Worker heartbeats: `.backend_data/backend.sqlite3`, table `workers`

## 6. Recommendations

Critical:

1. Add an orphaned-running-run recovery sweep, not only stale-worker recovery. A `running` run with no valid worker lease should not stay running forever.
2. Make worker liveness visible in the UI: show active workers, last heartbeat, current run ID, and lease expiry.
3. Add a run detail log endpoint that reads structured worker logs or stores run-scoped log events in the database.
4. Add queue age alerts: warn when a run has been queued longer than a configured threshold.

High priority:

1. Enable SQLite WAL and `busy_timeout` while SQLite remains in use.
2. Add per-source scraping concurrency limits and global credit budgets.
3. Add retry policy by error category, not only by run attempt count.
4. Add a startup health check that refuses to accept queued runs if no worker has heartbeated recently, or clearly labels the queue as waiting for a worker.

Scale path:

1. Move primary data to PostgreSQL.
2. Move run execution to Celery/RQ with Redis or a managed queue.
3. Split workers by workload class: scraping, document generation, scheduled maintenance, and lightweight admin jobs.
4. Add distributed locks/rate limits for expensive external providers such as ScrapeOps, LinkedIn, and LLM APIs.

Nice to have:

1. Add a log viewer in the run review screen.
2. Add a worker dashboard showing throughput, failures, retries, and average run duration.
3. Add structured event names to all stages, not only the worker lifecycle.

## Verification

Verification was run after implementation:

- `.venv\Scripts\python.exe -m compileall backend/worker backend/api/server.py workspace_runner.py`
- `.venv\Scripts\python.exe -m pytest tests/test_worker_service.py tests/test_backend_api.py::BackendApiTests::test_job_workspace_people_discovery_endpoints_persist_selected_people tests/test_stage_adapters.py -q`
- API health check returned `{"status": "ok"}` from `http://127.0.0.1:8000/health`.
- Frontend returned HTTP 200 from `http://127.0.0.1:4173/`.
- Worker heartbeat shows one active `local_worker` process in the worker table.

The focused worker logging test asserts that `worker_task_start`, `worker_task_complete`, `worker_run_summary`, and `worker_loop_stop` are emitted as JSON with run ID, workspace ID, worker ID, timestamp, status, and duration.
