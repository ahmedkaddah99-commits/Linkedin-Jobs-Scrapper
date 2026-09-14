> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Backend workers, orchestration and adapters (WS-2)

Primary doc for subsystem **WS-2**. It covers the lease-aware worker process, its two roles, how it claims each queue, the stage engine, the stage adapters, and what `create_backend` constructs.
Acquisition collectors, the publisher and enrichment internals are covered by WS-3 ([../05-subsystems/acquisition-and-collectors.md](../05-subsystems/acquisition-and-collectors.md), [../05-subsystems/company-identity-enrichment-and-logos.md](../05-subsystems/company-identity-enrichment-and-logos.md)). The CLI flag definitions and HTTP routes are covered by WS-1 ([backend-api.md](backend-api.md)). Deploy units and Render services are covered by WS-7 ([../02-deployment/render.md](../02-deployment/render.md), [../02-deployment/vps-runtime-and-acquisition-timers.md](../02-deployment/vps-runtime-and-acquisition-timers.md)).

All file:line references are to `58a96674`. "Static" means the code was read, not run.

---

## 1. Purpose and user-facing capabilities

| Capability | What the customer or operator sees | Where |
|---|---|---|
| Queued workspace runs | A customer starts a run (search → screen → rank → documents). The API enqueues it and a `customer` worker claims it, executes the stages and publishes artifacts | `backend/worker/service.py` `WorkerService.process_next` → `backend/orchestration/engine.py` `StageEngine.execute` |
| Personalized job intelligence | GET requests only enqueue. The worker computes the intelligence out of band | `service.py:254-273` |
| Customer slow tasks (RC-020) | `POST /tracker/email-integration/sync` and `POST /documents/bulk-export` return `202` with a task, and the worker executes them | `service.py:275-295`, migration `058_customer_task_queue` |
| Crash recovery | A run whose worker died is requeued (or finalized or cancelled) after its lease expires | `backend/application/run_services.py:507` `recover_stale_workers` |
| Retry | Failed or transient-DB-failed runs requeue until `max_attempts` | `run_services.py:911-938` |
| Acquisition-role maintenance | The VPS-only role runs the ScrapeOps reconciliation poll, the Phase A scheduler poll and bounded company enrichment | `service.py:431-523` |
| Run and usage analytics | Run lifecycle events and ScrapeOps usage are written to `analytics_events` | `engine.py:444`, `backend/adapters/stage_adapters.py:141-177` |
| Workspace builder / templates | The builder catalog and seeded workflow templates that define stage graphs | `backend/orchestration/workspace_builder.py`, `seeded_workspaces.py` |

No UI is owned here. The admin dashboard and admin job import are **RETIRED**; see §8 and [../06-history-and-provenance/retired-features.md](../06-history-and-provenance/retired-features.md).

## 2. Owned paths and governing instructions

| Path | Files | Lines | Role |
|---|---:|---:|---|
| `backend/worker/__init__.py` | 1 | 11 | Re-exports `WorkerService`, `configure_worker_logging`, role constants |
| `backend/worker/roles.py` | 1 | 26 | Role and task-family contract |
| `backend/worker/service.py` | 1 | 580 | `WorkerService` (claim, heartbeat, loop) |
| `backend/worker/logging_config.py` | 1 | 130 | JSON rotating worker logs with redaction |
| `backend/orchestration/__init__.py` | 1 | 26 | Public exports |
| `backend/orchestration/engine.py` | 1 | 547 | `BaseStage`, `StageOutcome`, `StageEngine` |
| `backend/orchestration/registries.py` | 1 | 48 | `Registry`, `ComponentDescriptor`, `BackendRegistries` |
| `backend/orchestration/seeded_workspaces.py` | 1 | 187 | 4 `DEFAULT_WORKFLOW_TEMPLATES`, empty `DEFAULT_WORKSPACES` |
| `backend/orchestration/workspace_builder.py` | 1 | 2424 | Builder catalog, validation, stage-graph construction |
| `backend/adapters/__init__.py` | 1 | 3 | Exports `register_stage_adapters` |
| `backend/adapters/stage_adapters.py` | 1 | 1391 | Stage implementations and registration |
| `backend/bootstrap.py` | 1 | 387 | `create_backend` composition root |
| `backend/__init__.py` | 1 | 11 | Lazy `create_backend` export |

Totals: worker 4, orchestration 5, adapters 2, plus 2 root files, which is 13 files (matches audit row 20). `backend/orchestration/**` has an empty diff over `848408f3..58a96674` (verified with `git diff --stat`). Only `backend/worker/service.py` changed in that range: −18 lines in `dd47acf9`.

Governing instructions and specs (read at the baseline):
- Root `AGENTS.md` (repo-wide agent rules).
- `docs/RC018_WORKER_ROLES.md`: role contract. **Partly stale.** It still lists "admin imports" as acquisition-role work, which `dd47acf9` removed (see WS2-G2). The role, version and capacity metadata it describes match the code.
- `docs/RC020_CUSTOMER_TASK_QUEUE.md`: the customer task queue contract. Checked against `sqlite_personalized_jobs.py:1521-1680` and `services.py:1253`; it matches.
- `docs/RC023_VPS_RUNTIME.md`: VPS units (WS-7). L50 says `runr.target` "includes the separate acquisition worker", which is **false at the baseline** (see WS2-G1).
- `ARCHITECTURE.md` §"Queue + Worker Execution" (~L212-246): a correct high-level description of leases, heartbeats, stale recovery and resume. It has no roles, customer tasks or intelligence queue.

## 3. Entry points and registered commands/units

### 3.1 Process entry points

| Entry | Code path | Notes |
|---|---|---|
| `workspace_runner.py run-worker` | `workspace_runner.py:166-176` (flags), `:375-393` → `WorkerService.run_loop` | Flags: `--worker-id`, `--max-runs` (0 = unlimited), `--sleep-seconds` (5.0 → `poll_interval_seconds`), `--lease-seconds` (60), `--no-auto-retry`, `--worker-role {customer,acquisition}` (default `$RUNR_WORKER_ROLE` or `customer`). Global flags are `--data-dir`, `--storage`, `--log-level` (`:70-72`). Flag ownership is WS-1's: [backend-api.md](backend-api.md) |
| `workspace_runner.py process-next` | `:156-164`, `:354-373` → one `WorkerService.process_next` | Same role, id and lease flags. It does **not** call `run_loop`, so it never runs acquisition maintenance, the scheduler or enrichment |
| Worker id | `workspace_runner.py:41` `_runtime_worker_id` | An empty id gives `cli_worker_<8hex>`. When `RUNR_ENV` is prod or production, it appends `_<host>_<pid>` |
| HTTP `POST /workers/process-next` | `backend/api/routes/workspace.py:665-683` (WS-1) | Requires scope `TOKEN_SCOPE_WORKER_EXECUTE`. Builds a one-shot `WorkerService` (`worker_role` from the body, default `customer`) |
| HTTP `POST /workers/recover-stale`, `GET /workers[/{id}]` | `workspace.py:685-689`, `:341-355` | Calls `recover_stale_workers` and lists `workers` rows |
| Library | `backend/__init__.py:6-11` → `backend/bootstrap.py:311` `create_backend` | Used by the CLI (`workspace_runner.py:193`), the API server and 27 test files |

### 3.2 Roles (`backend/worker/roles.py`)

| Constant | Value | Line |
|---|---|---|
| `WORKER_ROLES` | exactly `("customer", "acquisition")` | 5-7 |
| `WORKER_VERSION_DEFAULT` | `rc018-v1` | 8 |
| `TASK_FAMILY_CUSTOMER` / `TASK_FAMILY_ACQUISITION` | `customer` / `acquisition` | 10-11 |
| `normalize_worker_role` | casefold, default `customer`, `ValueError` otherwise | 14-19 |
| `allowed_task_families` | `acquisition` → `[acquisition]`, otherwise `[customer]` | 22-26 |

### 3.3 Deploy wiring (cited only; WS-7 owns)

| Launcher | Command | Role/id |
|---|---|---|
| `deploy/start.sh worker` (L41-51) | `run-worker --worker-id ${WORKER_ID:-render_worker} --worker-role ${WORKER_ROLE:-customer}` | Calls `release_contract --service worker --worker-role …` first (L21-27, L42) |
| `deploy/start.sh acquisition` (L52-64) | `run-worker --worker-id ${WORKER_ID:-vps_acquisition_worker} --worker-role acquisition` | The role is hard-pinned; `WORKER_ROLE` is ignored |
| `deploy/start.sh process-next` (L65-75) | `process-next --worker-id ${WORKER_ID:-render_cron} --worker-role ${WORKER_ROLE:-customer}` | No unit or cron in `render.yaml` uses it (it only defines `dockerCommand: ./deploy/start.sh worker`) |
| `Dockerfile.worker:69` | `CMD ["./deploy/start.sh", "worker"]` | — |
| `render.yaml:161-221` `runr-worker` | `dockerCommand: ./deploy/start.sh worker`, `maxShutdownDelaySeconds: 300` (L185) | Env: `WORKER_ID=render_customer_worker` (L215), `WORKER_ROLE=customer` (L217), `RUNR_WORKER_VERSION=rc018-v1` (L219), `RUNR_WORKER_CAPACITY_SLOTS="1"` (L221), `RUNR_CUSTOMER_TASKS_ASYNC=true`, `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED=false` (L201), `RUNR_COMPANY_ENRICHMENT_ENABLED=0` (L207), `RUNR_MIGRATION_HEAD=058_customer_task_queue` (L193-194; C3) |
| `deploy/systemd/runr-worker.service` | `start.sh worker`, `WORKER_ROLE=customer`, `WORKER_ID=vps_customer_worker`, `RUNR_WORKER_LOG_DIR=/var/log/runr/customer` | VPS customer worker |
| `deploy/systemd/runr-acquisition-worker.service` | `start.sh acquisition` (L29), user `runr-acquisition`, `EnvironmentFile=/opt/runr/.env.acquisition`, `WORKER_ROLE=acquisition` (L21), `RUNR_ACQUISITION_SCHEDULER_DISABLED=true` (L28) | Named in `deploy/vps-runtime-contract.json:52-53` `roles.acquisition.unit`. **Not** in `deploy/systemd/runr.target` Wants (L3). See §6.3 and C6 |

## 4. Inputs, outputs, storage and dependencies

**Environment read directly by owned code**

| Variable | Read at | Effect |
|---|---|---|
| `RUNR_WORKER_VERSION` | `service.py:77-80` | Heartbeat and log metadata only |
| `RUNR_WORKER_CAPACITY_SLOTS` | `service.py:81` (`_positive_int_env`, default 1, min 1 at L87) | **Metadata only.** It is written into heartbeat metadata (`:93`) and logs (`:112`). No code at the baseline changes concurrency: each process runs one task at a time, and nothing else in `backend/`, `scripts/` or `deploy/` reads the variable (git grep) |
| `RUNR_COMPANY_ENRICHMENT_MAX_COMPANIES` / `_CONCURRENCY` / `_REQUEST_BUDGET` | `service.py:503-505` (defaults 25/5/25) | Arguments passed to `run_due_company_enrichment` (acquisition role only) |
| `RUNR_WORKER_LOG_DIR` | `logging_config.py:103` (default `logs/worker.log`, 10 MiB × 5) | JSON log file plus stdout, both with `RedactingFilter` |
| `OBJECT_STORAGE_BACKEND`, `OBJECT_STORAGE_LOCAL_ROOT`, `RUNR_INTERNAL_OBJECT_STORAGE_LOCAL_ROOT` | `bootstrap.py:321-330` | Local object root defaults to `<data_dir>/objects`. **Mutates `os.environ`** |
| `RUNR_TEST_MODE`, `RUNR_ENV`, `PYTEST_CURRENT_TEST`, `DATABASE_BACKEND`, `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED` | `bootstrap.py:354-387` | Test-database boundary guard |

The worker reaches environment it does not own through the application layer: `RUNR_ACQUISITION_SCHEDULER_DISABLED` (`backend/application/acquisition_scheduler.py:152-158`), `RUNR_COMPANY_ENRICHMENT_ENABLED` (`backend/application/services.py:950-959`), `RUNR_CUSTOMER_TASKS_ASYNC` (`backend/application/customer_tasks.py:15`, API-side enqueue) and `SCRAPEOPS_API_KEY` (`services.py:816`).

**Storage touched by the worker loop** (schema is WS-5's: [../03-data/schema-and-migrations.md](../03-data/schema-and-migrations.md))

| Table | Operation | Via |
|---|---|---|
| `workers` | upsert heartbeat; CAS lease renewal; mark stale | `run_services.py:372/407/447/507/791`, `backend/repositories/sqlite_backed.py:2143/2193/2233` |
| `runs` (+ `run_stage_results`, `run_job_sets`, `run_blobs`, `artifacts`) | claim (`BEGIN IMMEDIATE`), stage saves, recovery transitions | `sqlite_backed.py:702`, `:502`, `engine.py` |
| `customer_tasks` (migration 058) | recover, claim, fenced complete | `backend/repositories/sqlite_personalized_jobs.py:1521/1577/1619` |
| Personalized intelligence cache/queue | recover, claim, complete | `sqlite_personalized_jobs.py:672`, `backend/application/personalized_jobs_service.py:1060` |
| `analytics_events` | insert | `sqlite_backed.py:2334` (`SqliteAnalyticsStore.emit_event`) |
| Object storage (local/R2) | artifact publish | `bootstrap.py:338-342` → `backend/storage` `publish_file_artifacts` (WS-5: [../03-data/object-storage-r2.md](../03-data/object-storage-r2.md)) |
| Acquisition store (acquisition role) | `recover_dispatching_requests`, cycles, enrichment | WS-3 |

**What `bootstrap.create_backend` constructs** (`bootstrap.py:311-351`)
1. Test guard (`:318-319`) when `test_mode` or a test context is detected. It rejects remote/Turso/production DB configuration, live acquisition network authorization and the default `.backend_data` path.
2. `_build_repositories` (`:263-308`). `sqlite` (default): `initialize_database(db_path)` (runs migrations; WS-5), then 16 SQLite stores: workspace, run, job, artifact, review, auth, secret, worker, analytics, config, source_policy, career_profile, evidence, acquisition, acquisition_audit, personalized_jobs. `file`: 11 file stores, with evidence, acquisition, acquisition_audit and personalized_jobs set to `None`, which silently disables the customer-task and intelligence queues (§6).
3. Object storage from env (`:321-330`).
4. `_build_registries` (`:47-254`): 12 connector descriptors (incl. legacy aliases), 4 generation, 4 renderer, and a stage registry filled by `register_stage_adapters` (`:248`).
5. `StageEngine(stage_registry, run_repository, job_store, artifact_store, artifact_publisher=publish_file_artifacts…)` (`:332-343`).
6. `BackendApplication(repositories, registries, stage_engine, object_storage)` (`:344-349`, WS-4), then `stage_engine.event_emitter = application.emit_event` (`:350`).

**Stage registry** (`stage_adapters.py:1206-1232`)

| Stage type | Adapter class |
|---|---|
| `jobs.sources.process_text` | `SourceProcessingStage` |
| `jobs.acquire.search_listings` / `legacy.linkedin.acquire` | `LinkedInAcquireStage` |
| `jobs.ingest.curated_urls` / `legacy.manual_url.ingest` | `ManualUrlIngestionStage` |
| `jobs.acquire.company_sites` | `CompanyCareerSiteAcquisitionStage` |
| `jobs.screen.filter` | `GenericScreeningStage` |
| `legacy.white_collar.local_filter` | `TailoredScreeningStage` |
| `jobs.prioritize.rank` / `legacy.white_collar.rank` | `TailoredPrioritizationStage` |
| `jobs.merge.dedupe` / `legacy.jobs.merge` | `MergeJobSetsStage` |
| `applications.generate.documents` / `legacy.white_collar.docs` | `TailoredDocumentExportStage` |
| `jobs.acquire.job_boards` / `legacy.blue_collar.stage1` | `JobBoardAcquisitionStage` |
| `legacy.blue_collar.stage2` | `ReusablePackageFilteringStage` |
| `jobs.classify.roles` / `legacy.blue_collar.stage3` | `RoleClassificationStage` |
| `profiles.generate.reusable` / `legacy.blue_collar.stage4` | `ReusableProfileGenerationStage` |
| `applications.package.export` / `legacy.blue_collar.stage5` | `ApplicationPackageExportStage` |

These adapters wrap `backend/capabilities/**` pipelines (tailored documents, reusable packages, source processing; WS-4: [../05-subsystems/career-profiles-and-documents.md](../05-subsystems/career-profiles-and-documents.md)). The in-run acquisition stages (LinkedIn search, company sites, job boards) are **customer-run** stages. They are not the VPS acquisition producers; for those see [../05-subsystems/acquisition-and-collectors.md](../05-subsystems/acquisition-and-collectors.md).

Seeded templates (`seeded_workspaces.py`): `search_apply_v1` (L8), `curated_apply_v1` (L49), `blended_sources_apply_v1` (L83), `board_package_v1` (L139). `DEFAULT_WORKSPACES = []` (L187). Consumed by `sqlite_backed.py:45` and `file_backed.py:41`. `workspace_builder.py` builds stage graphs from the builder's source and module selections (`_build_source_stages` L2034, `_build_tailored_stages` L2124; stage types L2043-2265).

**Depends on:** WS-4 `backend/application` (all queue and run semantics), WS-5 `backend/repositories`/`backend/database`/`backend/storage`/`backend/domain` ([domain-model.md](domain-model.md)), WS-3 acquisition scheduler and enrichment, WS-6 secrets (resolved via `resolve_runtime_value`).

## 5. Important call/data flows

### 5.1 `WorkerService.run_loop` (one iteration; `service.py:393-580`)

```
initial heartbeat(idle)                                   :407-426  (transient DB error → warn, continue)
while not stopped:
  [acquisition] every 60s: heartbeat(running,acq) → application.maybe_run_scheduled_scrapeops_maintenance(source="worker")   :431-454
  max_runs reached? → break                                :455-464
  every scheduled_run_check_interval_seconds (60s; not a CLI flag):
     [acquisition] heartbeat → application.run_due_acquisition() → _log_acquisition_result   :465-487
  [acquisition] every company_enrichment_check_interval_seconds (300s):
     application.run_due_company_enrichment(max/concurrency/budget from env)                 :488-523
  process_next(enqueue_scheduled_runs = due AND role==customer)                              :524-530
     transient DB error → warn, sleep poll interval, continue                                 :531-546
     None → sleep poll_interval_seconds (default 5s)                                          :547-549
finally: application.stop_worker(worker_id) (status=stopped, lease expires now)              :554-579
```

### 5.2 `WorkerService.process_next` (`service.py:226-391`). Claim order for the customer role

1. `application.recover_stale_workers()` (`:232-249`). This runs for **both** roles, so an acquisition worker also recovers stale customer runs.
2. `role == acquisition` → `return None` (`:251-252`). Nothing else is claimed.
3. **Intelligence queue**: heartbeat(running, customer) → `process_next_personalized_intelligence(worker_role, worker_id, lease_seconds)` (`services.py:1207` → `personalized_jobs_service.py:1060`: role gate, `recover_stale_intelligence`, `claim_next_intelligence`, fenced `complete_intelligence`) → heartbeat(idle). A non-None result is returned (`:258-273`).
4. **Customer task queue** (migration 058): heartbeat → `process_next_customer_task` (`services.py:1253-1300`):
   `recover_stale_customer_tasks` → `claim_next_customer_task` → `customer_tasks.execute_customer_task` (types `CUSTOMER_TASK_EMAIL_SYNC`, `CUSTOMER_TASK_BULK_EXPORT`, `customer_tasks.py:12/64`) → `complete_customer_task(state=completed|failed, lease_owner, lease_token, attempt_count, retryable=True on exception)`. The result is returned (`:275-295`).
   Steps 3-4 run only when `isinstance(self.application, BackendApplication)` (`:258`), so test doubles skip them.
5. **Run queue**: `claim_next_queued_run(recover_stale_workers=False, enqueue_scheduled_runs, worker_role, worker_metadata)` (`run_services.py:713-767`). A non-customer role only gets an idle heartbeat and None (`:724-735`). Otherwise it optionally calls `enqueue_due_scheduled_runs`, then `run_repository.claim_next_queued()`. SQLite does this under `BEGIN IMMEDIATE`: oldest `queued` by `queued_at`/`updated_at`, then `created_at`; sets `running`, `started_at`, and `attempt_count += 1` (`sqlite_backed.py:702-740`). Then heartbeat(running, `current_run_id`, metadata `run_attempt_count`).
6. A daemon heartbeat thread renews the lease every `max(1, lease_seconds/3)` s (`service.py:319-345`) via `renew_run_lease` → `run_services.py:407-445`. That checks that the observed worker is `running` on this run and attempt, then calls `renew_worker_lease_if_owned`, a single-row CAS UPDATE that matches the prior `last_heartbeat_at`/`lease_expires_at` **and** `EXISTS runs(id, status IN running/cancel_requested, attempt_count)` (`sqlite_backed.py:2193-2231`). On `WorkerLeaseLostError` the thread logs `worker_lease_lost` and stops renewing. The run keeps executing (§6).
7. `execute_claimed_run(run_id, auto_retry_failed)` (`run_services.py:769-789`): CV-upload runs go to `process_cv_upload_run`. Otherwise it validates a workspace snapshot (preflight fail → `fail_run_preflight`), then `execute_run` → `StageEngine.execute(context)` (`:884-944`).
8. `finally`: stop the heartbeat thread, then `release_worker` (status idle, lease expires now) (`service.py:378-391`).

### 5.3 `StageEngine.execute` (`engine.py:103-339`)

For each `workflow.stages` entry, in order:
- Skip stages already `completed`/`skipped` (resume).
- Check for a cancel request (`_cancel_requested` re-reads the run, `:395`).
- Save `current_stage_id` and progress.
- Disabled stage → `skipped`.
- `stage_registry.get(stage_type)`; `can_run` false → `skipped`.
- `execute`. Then persist `job_sets` (`job_store.save_job_set`), `data` blobs, and artifacts (through `artifact_publisher` to object storage, then `artifact_store.save_artifacts`). Document-generation stage types are validated (`:467`) and emit `cv_generation_completed`.
- On exception: stage `failed`, run `failed`, emit `automation_step_failed` and `run_failed`, **re-raise**. A transient DB error during persistence is re-raised without marking the stage failed (`:267-268`).
- End: run `completed`, emit `run_completed`.
- Test runs (`run_mode == "test"`) cap generation inputs and outputs at 1 job (`:57-65`, `:341-373`).

### 5.4 Worker-side analytics. Separate from the retired HTTP endpoint (brief correction 2, verified)

| Writer | Event names | `source` | Path |
|---|---|---|---|
| Stage engine → app | `run_completed`, `run_failed`, `automation_step_failed`, `cv_generation_completed` | `runtime` | `engine.py:444-446` `_emit_event` → `event_emitter` = `application.emit_event` (`bootstrap.py:350`) → `services.py:1431-1470` (adds `analytics_environment` from `RUNR_ENV`) → `analytics_store.emit_event` → `INSERT INTO analytics_events` (`sqlite_backed.py:2334-2370`) |
| ScrapeOps usage callback | `scrapeops_request`, plus `record_scrapeops_usage` ledger row when `method == "scrapeops_proxy"` | `worker` | `stage_adapters.py:141-177` `_build_scrapeops_usage_callback`: calls `context.repositories.analytics_store.emit_event` **directly** (`:163-176`) and `record_scrapeops_usage` (`:153-162`). Wired into `LinkedInAcquireStage` (`:595`), `ManualUrlIngestionStage` (`:623`) and `JobBoardAcquisitionStage` (`:1039`) |
| Acquisition-role maintenance | ScrapeOps reconciliation snapshot and alert events | `worker` | `services.py:1978` → `:1878` `run_scrapeops_reconciliation_cycle` → `emit_event` |

None of these depends on `POST /analytics/events`. Per audit N-1, that endpoint is unregistered (404) at the baseline (WS-1 scope; WS-2 did not re-verify the route table).

### 5.5 Customer task lifecycle (migration `058_customer_task_queue`, `sqlite_migrations.py:1886-1918`, registry `:3533`)

```
API route (RUNR_CUSTOMER_TASKS_ASYNC=true) → application.enqueue_customer_task (services.py:1227)
   → store.enqueue_customer_task: unique (user_id, idempotency_key) → 202 + status URL
customer worker → recover_stale_customer_tasks: running & lease_expires_at<=now →
      attempt_count >= min(max_attempts, 5) ? failed(lease_expired) : queued(lease_expired)
   → claim_next_customer_task: role must be "customer"; oldest queued with attempt_count < min(max_attempts,5);
      state=running, attempt_count+1, new lease_token (uuid4), lease_expires_at = now+lease_seconds
   → execute_customer_task → complete_customer_task with predicates task_id, state='running',
      lease_owner, lease_token, attempt_count (fencing); failed+retryable+attempts left → queued
```

Worker lease for tasks = `max(1, lease_seconds)` (60 s from the CLI). Unlike runs, customer tasks and intelligence items get **no heartbeat renewal thread** while they execute; see §6.

## 6. Invariants, failure handling and recovery

### 6.1 Invariants (static)

| # | Invariant | Enforced at |
|---|---|---|
| I1 | Only `customer` claims runs, customer tasks or intelligence | `service.py:251`; `run_services.py:724`; `services.py:1261`; `sqlite_personalized_jobs.py:1585`; `personalized_jobs_service.py:1071` (defence in depth) |
| I2 | Only `acquisition` runs the ScrapeOps maintenance, `run_due_acquisition` and `run_due_company_enrichment` from the loop | `service.py:431, 472, 495` |
| I3 | A run claim is atomic and increments `attempt_count` | `sqlite_backed.py:704-740` |
| I4 | A lease renewal cannot resurrect a recovered or reclaimed run (CAS on the heartbeat snapshot + run status + attempt) | `sqlite_backed.py:2193-2231`, `run_services.py:407-445` |
| I5 | Stale recovery skips runs owned by live workers and uses CAS transitions | `run_services.py:507-548` `_live_owned_run_ids`, `save_recovery_transition_if_stale` (`sqlite_backed.py:502`) |
| I6 | Customer-task completion is fenced by owner, token and attempt | `sqlite_personalized_jobs.py:1619-1675` |
| I7 | Unknown roles fail fast | `roles.py:14-19`; argparse `choices=WORKER_ROLES` |
| I8 | Tests cannot bootstrap against remote/Turso/prod or with live acquisition network enabled | `bootstrap.py:354-379` |
| I9 | Only `Exception` or a classified transient DB error is "handled". Other `BaseException`s (e.g. `KeyboardInterrupt`) propagate without failure logging | `service.py:34-53` |

### 6.2 Failure handling

| Failure | Behaviour |
|---|---|
| Stage exception (non-transient) | Stage/run `failed` and events emitted by the engine. Then `execute_run` requeues via `trim_to_resumable_prefix` + `queue_run` if `auto_retry_failed` and `attempt_count < max_attempts` (`run_services.py:935-938`). `max_attempts` defaults to 1 on `start_run`/`enqueue_run` (`:646`, `:701`), so there is no automatic retry unless the caller sets it higher |
| Transient DB error during a run | Already completed per stage results → finalize. Otherwise requeue if retries remain, else `failed` with `last_error_category` (`run_services.py:911-933`) |
| Transient DB error in the loop | `worker_transient_database_failure` warning, sleep, continue. Non-transient errors re-raise and end the loop (`service.py:531-546`) |
| Acquisition poll or enrichment exception | Logged (`worker_acquisition_cycle_failed`, `worker_company_enrichment_failed`); the loop continues (`:479-485`, `:509-515`) |
| Lease lost mid-run | The heartbeat thread stops renewing; **the run continues to completion in-process**. Another worker may have requeued it after expiry (lease 60 s, renew every 20 s). The CAS write guards (I4/I5) keep recovery from being overwritten by a stale heartbeat. They do **not** stop the original process's stage writes |
| Worker crash | `workers.lease_expires_at` passes → next `recover_stale_workers` (any role, any process, or `POST /workers/recover-stale`) marks it `stale` and requeues (resumable prefix kept), finalizes or cancels its run. Runs orphaned without a worker record are recovered after `ORPHANED_RUNNING_RUN_RECOVERY_SECONDS = 600` (`run_services.py:52`, `:572-615`) |
| `release_worker` / `stop_worker` fail | Logged. Re-raised only when no primary error is in flight (`service.py:381-391`, `:556-570`) |
| Long intelligence or customer task | No renewal thread. A task running longer than `lease_seconds` (60 s from the CLI) can be requeued by the next worker's `recover_stale_customer_tasks`; fencing (I6) makes the late completion a no-op. See WS2-G4 |

### 6.3 Acquisition role with `RUNR_ACQUISITION_SCHEDULER_DISABLED=true` (C6). Traced

Unit `deploy/systemd/runr-acquisition-worker.service` → `start.sh acquisition` → `run-worker --worker-role acquisition`, with `WorkerService.run_loop` on the defaults (lease 60 s, poll 5 s, scheduled check 60 s, enrichment check 300 s). Per iteration:

| Step | Gate | Result with the env set |
|---|---|---|
| 1. ScrapeOps maintenance (every 60 s) | `maybe_run_scheduled_scrapeops_maintenance` → alert policy `enabled` (default True) → `run_scrapeops_reconciliation_cycle`, bucketed by `cadence_hours` (default 6); skipped if a reconciliation event already exists in the bucket (`services.py:1878-1900`) | **Not gated by the scheduler flag.** When `SCRAPEOPS_API_KEY` is set, `_scrapeops_account_state` calls `fetch_account_usage` (network, 6 s timeout, `services.py:816-827`) about once per bucket and writes events. Whether the key is present in `.env.acquisition` is UNKNOWN |
| 2. Scheduler poll (every 60 s) | `run_due_acquisition` → `PhaseAAcquisitionScheduler.run_due_cycle` (`acquisition_scheduler.py:262`) | (a) `acquisition_store.recover_dispatching_requests()` **runs first and can mutate state** even when disabled; if it recovered anything → `recovery_required` (logged warning). (b) `kill_switch` config true → `{"status":"kill_switch"}`. (c) The env forces `scheduler_enabled`, `global_enabled` and `publication_enabled` to False (`:152-158`) → `{"status":"scheduler_disabled"}` → log `worker_acquisition_scheduler_disabled` (`service.py:182-183`). No cycle is created (`tests/test_phase_a_safety_defaults.py:13-21`) |
| 3. Company enrichment (every 300 s) | `run_due_company_enrichment` (`services.py:940`): `RUNR_COMPANY_ENRICHMENT_ENABLED` env, else config `acquisition.phase_f.company_enrichment_enabled` | **Not gated by the scheduler flag or by `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED`** (no such check in `backend/application/company_enrichment.py`). `deploy/acquisition.env.example:55-59` sets `RUNR_COMPANY_ENRICHMENT_ENABLED=1` (provider `webshare_linkedin`, 25/3/25). With that env file the unit would run bounded enrichment every 5 minutes, in parallel with the oneshot timers. Internals: WS-3 |
| 4. `process_next` | — | `recover_stale_workers()` (can requeue customer runs in the shared DB), then `return None`. No claims |

The unit comment (L25-27) says the worker is kept "for leases/maintenance without letting it run the legacy source scheduler". The code matches for step 2 only. The handoff (documentary) says the unit is disabled and inactive (C6), so whether steps 1 and 3 run in production is UNKNOWN.

### 6.4 Removed admin job-import branch (`dd47acf9`). Confirmed there is no dependent task family

- `git show dd47acf9 -- <WS-2 paths>` touches only `backend/worker/service.py` (−18). It removed the `role == acquisition` block that called `application.process_next_admin_job_import(...)` and logged `worker_admin_job_import_complete`, leaving `return None` (`service.py:251-252`).
- `git grep process_next_admin_job_import 58a96674 -- backend scripts` returns nothing, so there is no dangling call.
- `TASK_FAMILY_ACQUISITION` is used only as heartbeat metadata (`active_task_family`) in `service.py:435, 474, 500` and `roles.py:25`. **No queue claims by task family.** The only claims are role-gated `customer` queues. Removing the branch left no acquisition task family without a consumer.
- Residue outside WS-2 (reported, not owned): table `admin_job_imports` (migration `042_admin_job_import_dashboard`, `sqlite_migrations.py:1932/3442`), its store methods (`sqlite_acquisition.py:3501-3860`, incl. a `status='queued'` claim at ~`:3564`), and `PhaseAAcquisitionScheduler.run_controlled_import` (`acquisition_scheduler.py:588`), which has **no caller** in `backend/` or `scripts/`. Any `queued` rows would now never be processed. Owners: WS-3 / WS-5 / WS-11 (C7).

## 7. Relevant tests and safe verification commands

| Test file | Covers |
|---|---|
| `tests/test_worker_service.py` (993 lines, 29 tests) | Loop start/stop; transient DB survival; release/stop failures not masking primary errors; heartbeat after driver panic; scheduled-run scan throttling; acquisition kill-switch/no-op log semantics; stale recovery (requeue, CAS vs renewed lease, cancel-requested, orphaned, completed-stage finalize, reclaimed run); attempt-scoped renewal; structured logs; role-specific log dir |
| `tests/test_stage_adapters.py` (578 lines, 14 tests) | Workspace CV materialization, company-site limits, LinkedIn stage exclusions, tailored document artifacts, stage2/stage3 arg translation, academic site selection, proxy fallback flag |
| `tests/test_phase_a_rc018.py` | Role isolation: customer skips acquisition claims (L20); acquisition skips customer work (L38); stores reject the wrong role (L48); heartbeat metadata (L91); customer loop skips scheduler and enrichment (L109) |
| `tests/test_phase_a_rc020.py` | Customer task idempotency and role gate (L41); expired lease requeue → fenced failure (L79); worker executes a task (L125); email and bulk task reuse (L155, L189) |
| `tests/test_phase_a_safety_defaults.py` | `scheduler_disabled` / `kill_switch` poll results; worker defaults cannot contact sources |
| `tests/test_log_privacy.py` | `WorkerJsonFormatter` redaction |
| `tests/test_rc023_vps_runtime.py` (WS-7/WS-10) | Unit files. **L92-99 asserts `runr-acquisition-worker.service` is in `runr.target`, which does not hold at the baseline** (static; WS2-G1) |
| `tests/test_backend_application.py`, `tests/test_backend_api.py`, `tests/test_company_career_discovery.py` | Reference `backend.orchestration` / `backend.adapters` |
| 27 files importing `backend.bootstrap` (e.g. `tests/test_phase_a_scheduler.py`, `tests/test_phase_f_company_enrichment.py`) | Use `create_backend` as a fixture; see [../04-testing/test-suite-map.md](../04-testing/test-suite-map.md) |

Safe verification commands (**not executed in Phase 2**; need a venv; offline, temp SQLite):
```
RUNR_TEST_MODE=1 python -m pytest tests/test_worker_service.py tests/test_stage_adapters.py -q
RUNR_TEST_MODE=1 python -m pytest tests/test_phase_a_rc018.py tests/test_phase_a_rc020.py tests/test_phase_a_safety_defaults.py tests/test_log_privacy.py -q
RUNR_TEST_MODE=1 python -m pytest tests/test_rc023_vps_runtime.py -q   # expected to expose WS2-G1
git grep -n "RUNR_WORKER_CAPACITY_SLOTS\|capacity_slots" 58a96674 -- backend scripts deploy
```

## 8. Historical decisions and supporting commits

`git log --oneline 58a96674 -- backend/worker backend/orchestration backend/adapters backend/bootstrap.py backend/__init__.py` returns 41 commits. Selected:

| SHA | Date | Subject | Relevance |
|---|---|---|---|
| `dd47acf9` | 2026-09-10 | Complete acquisition delivery and remove admin surfaces | Removed the acquisition-role admin job-import branch (§6.4); merged by `550ee00a` |
| `6e9a1e93` | 2026-09-09 | fix: bind worker logs to writable role paths | `RUNR_WORKER_LOG_DIR` per role unit |
| `39d15b8f` | 2026-09-08 | RC-022 separate release and runtime contracts | Added `roles.py` and the role/version/capacity metadata in `service.py` (+159/−26) |
| `703d6881` | 2026-08-15 | Scale scheduled company enrichment cycles | Env-driven enrichment bounds in the loop |
| `b270d2cb` | 2026-08-12 | recover acquisition audit permissions | Acquisition audit store wiring |
| `fa5e4d3a` | 2026-08-07 | feat: add admin job import dashboard | Added the (now retired) import branch |
| `247c3a4b` | 2026-08-06 | feat: add async job intelligence and evidence review | Intelligence queue before run claims |
| `e71fb447` | 2026-08-06 | fix: clarify phase a scheduler poll semantics | `_log_acquisition_result` kill_switch/disabled/no-op distinctions |
| `c7bf109b` | 2026-08-06 | feat: deploy jobs catalog and portal rollout | Catalog-era bootstrap stores |
| `676ecd1a` | 2026-04-19 | Complete refactor of the codebase | Stage engine / registry architecture |

Decision records: `docs/RC018_WORKER_ROLES.md` (the role boundary, "role checks happen before a queue claim") and `docs/RC020_CUSTOMER_TASK_QUEUE.md` (the 058 queue, fencing, rollback by flag). Dirty-state record `R00017` (`backend/worker/service.py` in the retired checkout `runr-opencode-a-remove-admin`) is classified DUPLICATE-SUPERSEDED by `58a96674`.

## 9. Current implementation status

| Capability | Classification |
|---|---|
| Roles exactly `customer`/`acquisition`, normalized and validated | VERIFIED (scope: static, `roles.py:5-26`; argparse `choices=WORKER_ROLES` at `workspace_runner.py:162,174`) |
| CLI `run-worker` / `process-next` → `WorkerService` | VERIFIED (scope: static, `workspace_runner.py:354-393` constructs the service and calls `process_next`/`run_loop`) |
| `create_backend` composition (repositories, registries, engine, event emitter) | VERIFIED (scope: static, `bootstrap.py:311-351`) |
| Stage registry: 12 canonical + 11 legacy stage types | VERIFIED (scope: static, `stage_adapters.py:1206-1232` called from `bootstrap.py:248`) |
| Atomic run claim with attempt increment | VERIFIED (scope: static, `sqlite_backed.py:702-740` `BEGIN IMMEDIATE`) |
| Lease heartbeat thread with CAS renewal and lease-lost detection | VERIFIED (scope: static, `service.py:319-345` → `run_services.py:407-445` → `sqlite_backed.py:2193-2231`) |
| Stale worker and orphaned run recovery | VERIFIED (scope: static call path `service.py:233` → `run_services.py:507-615`); runtime behaviour IMPLEMENTED-UNVERIFIED (tests not run) |
| Retry via `max_attempts` | IMPLEMENTED-UNVERIFIED (`run_services.py:911-938`; default `max_attempts=1`, so retry is effectively opt-in) |
| Customer task queue (058) claimed only by the customer role, fenced | VERIFIED (scope: static, `service.py:275-295` → `services.py:1253` → `sqlite_personalized_jobs.py:1521-1675`) |
| Personalized intelligence queue in the worker | VERIFIED (scope: static call path `service.py:261` → `personalized_jobs_service.py:1060`) |
| `RUNR_WORKER_CAPACITY_SLOTS` as parallelism | PARTIAL (read and reported as metadata only; no concurrency implementation) |
| Worker-side analytics to `analytics_events` (run events + ScrapeOps usage) | VERIFIED (scope: static, `stage_adapters.py:163-176` and `engine.py:444` → `services.py:1431` → `sqlite_backed.py:2334` INSERT; independent of the HTTP endpoint) |
| Acquisition role: scheduler poll returns `scheduler_disabled` under the env flag | VERIFIED (scope: static, `acquisition_scheduler.py:152-158, 282-284`; kill switch and dispatch recovery run earlier) |
| Acquisition role: ScrapeOps maintenance and enrichment unaffected by the scheduler flag | VERIFIED (scope: static, `service.py:431-454, 488-523`; no flag check in `services.py:940-959, 1978`) |
| Acquisition-role admin job import | RETIRED/HISTORICAL (`dd47acf9`) |
| Workspace builder catalog and seeded templates | IMPLEMENTED-UNVERIFIED (unchanged since `848408f3`; not traced beyond stage-type mapping) |
| Worker log JSON + rotation + redaction | IMPLEMENTED-UNVERIFIED (`logging_config.py:71-119`) |
| `start.sh process-next` cron role in use | UNKNOWN (no Render cron or systemd unit references it) |

### Deployment evidence (documentary only; LIVE PRODUCTION = UNKNOWN)

- `render.yaml:161-221` declares `runr-worker` as the customer role (`render_customer_worker`, `rc018-v1`, 1 slot). The last recorded Render deploy is `5dfdd106` (`docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md`); U1 remains open.
- `docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md:29` records "`runr-acquisition-worker.service`: disabled and inactive". `deploy/vps-runtime-contract.json:52-53` still names it as the acquisition role unit (C6). The last recorded VPS release per the untracked 2026-09-12 report is `4a1b1df5` (C2, U2).
- `docs/RC023_VPS_RUNTIME.md:107` lists the acquisition worker in its `systemctl is-active` check. That record predates the target change.

## 10. Confirmed gaps and unresolved questions

| ID | Gap / question | Evidence | Refs |
|---|---|---|---|
| WS2-G1 | `tests/test_rc023_vps_runtime.py:99` asserts `runr-acquisition-worker.service` is in `runr.target`, but `deploy/systemd/runr.target:3` omits it. The test would fail at the baseline (static inference, not run). `docs/RC023_VPS_RUNTIME.md:50` has the same stale statement | file reads | C6, U11; WS-7/WS-10 |
| WS2-G2 | `docs/RC018_WORKER_ROLES.md` still lists "admin imports" as acquisition-role work, and its rollout example uses `start.sh worker` for acquisition (superseded by `start.sh acquisition`) | doc vs `service.py:251-252` | C7; WS-11 |
| WS2-G3 | The acquisition worker, if enabled, still runs the ScrapeOps reconciliation (provider account API when the key is present) and company enrichment (enabled in `deploy/acquisition.env.example:55`) regardless of `RUNR_ACQUISITION_SCHEDULER_DISABLED`. It also runs `recover_dispatching_requests` before the disabled check. The unit comment implies a narrower scope | §6.3 | C4, C5, C6; WS-3/WS-7 |
| WS2-G4 | No lease renewal during intelligence or customer-task execution. Tasks longer than `lease_seconds` (60 s from the CLI/`start.sh`) can be requeued and re-executed concurrently; completion is fenced, but side effects (email sync, bundle writes) may repeat | `service.py:258-295`; `sqlite_personalized_jobs.py:1521-1575` | WS-4 |
| WS2-G5 | Lease loss does not abort the in-flight run, so two workers can execute stages of the same run after a > 60 s stall | `service.py:326-331` | — |
| WS2-G6 | `RUNR_WORKER_CAPACITY_SLOTS` is advertised but not enforced or used | §4 | RC-018/RC-020 "later worker-capacity ticket" (`docs/RC020_CUSTOMER_TASK_QUEUE.md` Limitations) |
| WS2-G7 | The ScrapeOps usage callback writes `analytics_events` directly and bypasses `application.emit_event`, so those rows lack `analytics_environment` (production/staging tagging) | `stage_adapters.py:163-176` vs `services.py:1455-1457` | U7 (post N-1) |
| WS2-G8 | `admin_job_imports` queue residue plus uncalled `run_controlled_import`: queued rows are orphaned | §6.4 | C7; WS-3/WS-5/WS-11 |
| WS2-G9 | `bootstrap.create_backend` mutates `os.environ` (`OBJECT_STORAGE_*`) as a side effect; the `file` storage backend silently disables the customer-task and intelligence queues (`personalized_jobs_store=None`) | `bootstrap.py:277-280, 321-330` | WS-5 |
| WS2-Q1 | Is `start.sh process-next` (`render_cron`) used anywhere? | no referencing unit/cron | U1, U2 |
| WS2-Q2 | Is `SCRAPEOPS_API_KEY` or `RUNR_COMPANY_ENRICHMENT_ENABLED` set on the VPS `.env.acquisition`, and is the acquisition worker enabled? | host inspection | U2, C6 |

## Agent context and remaining work

**(a) Proposed agent context packet: WS-2 workers/orchestration**
- Required reading: this doc; `backend/worker/service.py`; `backend/worker/roles.py`; `backend/bootstrap.py`; `backend/orchestration/engine.py`; `backend/adapters/stage_adapters.py` L1-180 and L1206-1232; `backend/application/run_services.py` L372-548, L713-944; `docs/RC018_WORKER_ROLES.md`; `docs/RC020_CUSTOMER_TASK_QUEUE.md`; [backend-api.md](backend-api.md) for CLI flags.
- Allowed paths: `backend/worker/**`, `backend/orchestration/**`, `backend/adapters/**`, `backend/bootstrap.py`, `backend/__init__.py`, plus their tests.
- Tests to run: `tests/test_worker_service.py`, `tests/test_stage_adapters.py`, `tests/test_phase_a_rc018.py`, `tests/test_phase_a_rc020.py`, `tests/test_phase_a_safety_defaults.py`, `tests/test_log_privacy.py`, `tests/test_backend_application.py` (always with `RUNR_TEST_MODE=1`, temp SQLite, no live network).
- Prohibited: letting the `acquisition` role claim customer queues or the `customer` role run acquisition/enrichment; weakening the CAS or fencing predicates; changing `bootstrap._assert_test_database_boundary`; editing migrations (append-only, WS-5); changing `deploy/**`/`render.yaml` (WS-7); restoring the admin job import or the admin dashboard; enabling live acquisition network or provider spending.

**(b) Registry proposal**

| subsystem id | name | owned globs | primary doc | test globs | owner WS |
|---|---|---|---|---|---|
| `backend-workers-orchestration` | Workers, orchestration and stage adapters | `backend/worker/**`, `backend/orchestration/**`, `backend/adapters/**`, `backend/bootstrap.py`, `backend/__init__.py` | `docs/reverse-engineering/01-architecture/backend-workers-and-orchestration.md` | `tests/test_worker_service.py`, `tests/test_stage_adapters.py`, `tests/test_phase_a_rc018.py`, `tests/test_phase_a_rc020.py`, `tests/test_phase_a_safety_defaults.py` | WS-2 |

**(c) Gap / ticket candidates** (candidates only; no tickets created)
1. Reconcile `runr.target` vs `tests/test_rc023_vps_runtime.py:99` and `docs/RC023_VPS_RUNTIME.md:50` (WS2-G1; WS-7 decision on C6).
2. Gate acquisition-worker ScrapeOps maintenance and enrichment explicitly (or document them as intended) when the unit is enabled (WS2-G3).
3. Add lease renewal (or a longer lease) for customer tasks and intelligence; decide on abort-on-lease-loss for runs (WS2-G4, WS2-G5).
4. Implement or remove `RUNR_WORKER_CAPACITY_SLOTS` (WS2-G6).
5. Route the ScrapeOps usage callback through `application.emit_event`, or add `analytics_environment` (WS2-G7).
6. Update `docs/RC018_WORKER_ROLES.md` for the admin-import removal; decide the fate of `admin_job_imports` and `run_controlled_import` residue (WS2-G2, WS2-G8; with WS-11 retired-features).
