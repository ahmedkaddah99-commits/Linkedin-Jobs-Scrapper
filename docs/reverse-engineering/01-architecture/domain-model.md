> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Domain model, repositories, storage and configuration (WS-5)

LIVE PRODUCTION = UNKNOWN. Everything here comes from reading source at `58a96674`. Production facts are quoted from documents and labelled as documentary. No database, bucket or host was contacted.

Secondary docs for this subsystem:
- [Schema and migrations](../03-data/schema-and-migrations.md)
- [Turso and libSQL](../03-data/turso-and-libsql.md)
- [Object storage (local / S3 / R2)](../03-data/object-storage-r2.md)

---

## 1. Purpose and user-facing capabilities

WS-5 owns the persistence layer and the shared vocabulary of the backend. It is used by every other backend subsystem but has no user interface of its own.

| Layer | What it gives the product |
|---|---|
| Domain (`backend/domain/`) | Dataclasses, status constants and normalizers for runs, workspaces, jobs, reviews, users/tokens, secrets, workers, career profiles, evidence, Assisted Apply packages/preparations/corrections, personalized-jobs contracts, company and job identity, the Phase-0 contract catalog |
| Repositories (WS-5 slice of `backend/repositories/`) | Protocol contracts (`BackendRepositories`), SQLite/libSQL-backed stores, legacy JSON file-backed stores, the migration registry (60 migrations), profile/CV versioning helpers, an optional MySQL sink for career-URL discovery |
| Database (`backend/database/`) | A sqlite3/libSQL connection facade with transient-error retry, a checksum-guarded migration engine, base schema DDL, and the `python -m backend.database.migrate` CLI |
| Storage (`backend/storage/`) | An `ObjectStorage` protocol with local-filesystem and S3-compatible (R2) backends, private key layout, download policy, materialization cache and readiness probe |
| Config (`backend/config/`) | `ENV_SCHEMA` (48 keys) and production validation, dotenv layering, job-seeker/reusable-package JSON config loaders, plan/quota catalog, ScrapeOps policy defaults, the checked-in company career-site inventory |

## 2. Owned paths and governing instructions

| Glob | Files | Lines (approx.) |
|---|---|---|
| `backend/database/**` | 7 | 1,137 |
| `backend/repositories/` WS-5 slice: `__init__.py`, `contracts.py`, `file_backed.py`, `mysql_career_discovery.py`, `sqlite_backed.py`, `sqlite_core.py`, `sqlite_migrations.py`, `versioning_repository.py` | 8 | 9,387 |
| `backend/storage/**` | 9 | 924 |
| `backend/config/**` (7 `.py`/`.json` + 2 `.jsonl` under `company_site_inventory/`) | 9 | 4,172 |
| `backend/domain/**` | 22 | 11,276 |

Total: 55 files, matching the audit's WS-5 count (phase-1 delta audit, row 20).

The other `backend/repositories/` files are not WS-5's:
- WS-3: `backend/repositories/sqlite_acquisition.py`, `backend/repositories/sqlite_acquisition_audit.py`
- WS-4: `backend/repositories/sqlite_personalized_jobs.py`, `backend/repositories/assisted_apply_preparation.py`, `backend/repositories/document_payloads.py`

WS-5's `__init__.py` still re-exports their classes, and `sqlite_migrations.py` imports `document_payloads` (`sqlite_migrations.py:7-11`).

Governing instructions:
- `AGENTS.md`: all Python must run through `.venv\Scripts\python.exe`, version 3.12.7.
- `docs/architecture/backend_service_repository_boundaries.md` (2026-05-31). Checked against code: its protocol list and SQLite split still hold, but it predates the evidence, career-profile, acquisition and personalized-jobs stores.
- `docs/deployment/render.md` L21-25 and L172-192 cover migration ownership and rollback. WS-7 owns deployment; this doc only cites it.
- `docs/RC021_PORTABLE_ARTIFACT_STORAGE.md`: storage contract. Checked against `backend/storage/policy.py` and `backend/storage/materialization.py`; defaults match.
- `docs/RC020_CUSTOMER_TASK_QUEUE.md`: the table from migration 058. Not re-verified here; WS-4 owns the service.

Append-only migration rule: `backend/database/migrations.py:170-182` raises `MigrationChecksumError` when an applied migration's code changes.

## 3. Entry points

WS-5 has no HTTP routes. Its entry points are commands and factories:

| Entry point | Location | Invoked by |
|---|---|---|
| `python -m backend.database.migrate [--status] [--database PATH]` | `backend/database/migrate.py:28-45`; `backend/database/__main__.py` | `deploy/start.sh:76-78` (`migrate` role); `render.yaml:52` `preDeployCommand: ./deploy/start.sh migrate`. WS-7 owns both. |
| `initialize_database(path, force=False)` | `backend/database/initialization.py:29` | `backend/bootstrap.py:286`; `backend/repositories/sqlite_core.py:19` (every `_SqliteStore` constructor); `backend/acquisition/reprocessing.py:152` |
| `connect_database()` / `database_session()` | `backend/database/connection.py:525`, `:564` | `sqlite_core.py`; `backend/acquisition/reprocessing.py` |
| `database_target_info()` | `connection.py:507` | `backend/api/routes/system.py:45` (readiness); `bootstrap.py:364` (test boundary) |
| `create_object_storage(environ)` | `backend/storage/factory.py:12` | `bootstrap.py:330`; `backend/adapters/stage_adapters.py:350` |
| `probe_object_storage()` | `backend/storage/readiness.py:21` | `backend/api/routes/system.py:87` |
| Signed local object download | `LocalObjectStorage.verify_signed_download` (`local.py:150`) | Route `storage.objects` GET prefix `("storage","objects")`, registered at `backend/api/routes/storage.py:23` (WS-1) |
| `validate_environment()` | `backend/config/env_schema.py:438` | `migrate.py:31`; `backend/api/server.py:85` import; `storage/factory.py:18` |
| `load_project_dotenv()` | `backend/config/job_seeker.py:260` | API server, migrate, capabilities, `scripts/master_*_catalog.py` |
| `MySqlCareerDiscoveryStore` | `backend/repositories/mysql_career_discovery.py:71` | Only `backend/tools/discover_company_careers.py:20-22,897` (an opt-in CLI tool) |

## 4. Inputs, outputs, storage and dependencies

### 4.1 Repository layer and backend selection

`backend/bootstrap.py:263-308` (`_build_repositories`) picks the store family from `storage_backend`. That value comes from `workspace_runner.py:71` `--storage {sqlite,file}`, which `deploy/start.sh` fills from `RUNR_STORAGE_BACKEND` (default `sqlite`). `render.yaml` L94-95 and L211-212 set `sqlite`.

| `storage_backend` | Stores built | Notes |
|---|---|---|
| `sqlite` (default and production) | `SqliteWorkspaceRepository`, `SqliteRunRepository`, `SqliteJobStore`, `SqliteArtifactStore`, `SqliteReviewStore`, `SqliteAuthRepository`, `SqliteSecretStore`, `SqliteWorkerStore`, `SqliteAnalyticsStore`, `SqliteConfigStore`, `SqliteSourcePolicyStore`, `SqliteCareerProfileStore`, `SqliteEvidenceStore`, plus WS-3/WS-4 `SqliteAcquisitionStore`, `SqliteAcquisitionAuditStore`, `SqlitePersonalizedJobsStore` | Path is `<data_dir>/backend.sqlite3` unless the path already ends in `.db`/`.sqlite`/`.sqlite3` (`bootstrap.py:257-260`). Whether this is a local file or remote libSQL is decided later by `connect_database` (section 5.1), not by `storage_backend`. |
| `file` (legacy) | `File*` stores in `file_backed.py` (11 classes, L76-1153) | Source-policy, evidence, acquisition, audit and personalized-jobs stores are `None`. JSON files live under the base dir (`workspaces.json`, `runs/<id>.json`, `users.json`, `analytics_events.json`, ...). Only test user found: `tests/test_backend_application.py:913`. |

Contracts are in `backend/repositories/contracts.py`: 16 `Protocol` classes (L25-387) plus the `BackendRepositories` dataclass (L442-459). `sqlite_backed.py` classes all subclass `_SqliteStore` (`sqlite_core.py:14`):

| Class | Line | Main tables (see [schema doc](../03-data/schema-and-migrations.md)) |
|---|---|---|
| `SqliteWorkspaceRepository` | 227 | `workflow_templates`, `workspaces`, `workspace_document_bindings` |
| `SqliteRunRepository` | 402 | `runs`, `run_jobs`, `run_stage_results`, `run_blobs`, `run_document_bindings` |
| `SqliteJobStore` | 755 | `run_job_sets`, `site_job_url_history` |
| `SqliteArtifactStore` | 1037 | `artifacts` |
| `SqliteReviewStore` | 1142 | `reviews`, `application_status_history` |
| `SqliteAuthRepository` | 1316 | `users`, `api_tokens`, `assisted_apply_connections`, billing tables, `candidate_assets`/`candidate_documents` |
| `SqliteSecretStore` | 2081 | `secrets` |
| `SqliteWorkerStore` | 2130 | `workers` |
| `SqliteAnalyticsStore` | 2278 | `analytics_events` (`emit_event` L2334, insert L2353), `scrapeops_usage_ledger` (`record_scrapeops_usage` L2279), `query_rows` L2374 |
| `SqliteSourcePolicyStore` | 2477 | `site_source_policy` |
| `SqliteConfigStore` | 2792 | `app_config` |
| `SqliteCareerProfileStore` | 2847 | `career_profiles` |
| `SqliteEvidenceStore` | 2937 | `evidence`, `evidence_state_history` |

The table column is taken from each class's responsibility and the migration that creates each table. The SQL inside every method was not traced exhaustively.

`backend/repositories/versioning_repository.py` holds module-level functions (not a store class) over `profile_versions`, `cv_asset_versions` and `generation_provenance` (migration 026). Its only runtime caller is a lazy import at `backend/adapters/stage_adapters.py:1250`.

`backend/repositories/mysql_career_discovery.py` is an optional external MySQL sink (`pymysql`, imported lazily at L79). Config env names: `CAREER_DISCOVERY_MYSQL_{HOST,PORT,USER,PASSWORD,DATABASE,TABLE}`, falling back to `MYSQL_{HOST,PORT,USER,PASSWORD,DATABASE}` (L46-53). None of them are in `ENV_SCHEMA`. Render and the API/worker bootstrap do not use it.

### 4.2 Domain modules (`backend/domain/`, 22 files)

These are plain dataclasses and constants with no ORM. Rows are serialized to TEXT/JSON columns by the repositories. The importer counts below are `git grep` over `backend`+`scripts` and are approximate.

| Module | Lines | Key content | Main consumers (approx. importers) |
|---|---|---|---|
| `backend/domain/models.py` | 2218 | Run/stage/worker status constants (L11-68), role/token scopes including 11 `TOKEN_SCOPE_ACQUISITION_*` (L50-60), `utc_now_iso` (L71); dataclasses `JobRecord` L80, `ArtifactRecord` L197, `ReviewRecord` L217, `UserRecord` L430, `ApiTokenRecord` L484, `SecretRecord` L561, `WorkerRecord` L633, `StageDefinition` L688, `WorkflowTemplate` L718, `WorkspaceDefinition` L746, `RunRecord` L856, `CareerProfile` L990, `StageContext` L1076, `WorkExperienceRecord` L1509, `EvidenceRecord` L1723, `JobApplicationBinding` L1926, `EvidenceItem` L2053 and others | ~68 (everything) |
| `backend/domain/__init__.py` | 204 | Re-exports ~85 names, mostly from `models.py` | — |
| `backend/domain/phase0_contracts.py` | 1610 | `PHASE0_CONTRACT_VERSION`, schema ids (workspace config v2, candidate asset, rejected job, mail connection, referral, tracker, Gmail detection, application document, ATS gate), normalizers | ~14 |
| `backend/domain/personalized_jobs_contracts.py` | 1680 | Personalized Jobs `StrEnum`s, `CandidateSearchPreferences`, `JobPosting`, `EligibilityEvaluation`, `MatchEvaluation`, `JobDisposition`, `derive_posting_id`, `canonical_plan_id` | ~3 (WS-4) |
| `backend/domain/application_package.py` | 820 | Immutable Assisted Apply `ApplicationPackage` and sub-records, TTL/status constants, `resolve_approved_value` | ~4 |
| `backend/domain/application_policy.py` | 404 | AA-06 `ProfileValue`, `FieldDecision`, `decide_field_action` | 1 |
| `backend/domain/application_correction.py` | 75 | Correction scopes and precedence, `ApplicationCorrection` | 2 |
| `backend/domain/assisted_apply.py` | 222 | Connection statuses, `AssistedApplyPreferences`, `AssistedApplyConnectionRecord` | ~7 |
| `backend/domain/assisted_apply_preparation.py` | 164 | Preparation state machine (`transition_for_report`/`transition_for_action`), `PreparationFeatureDisabledError` | ~4 |
| `backend/domain/ats_export_gate.py` | 65 | `evaluate_ats_export_gate` | ~4 |
| `backend/domain/candidate_evidence.py` | 450 | CP-009 `CandidateEvidence`, evidence types/statuses, `classify_evidence_type` | ~13 |
| `backend/domain/career_profile_evidence.py` | 228 | CP-010 `CareerProfileEvidence` | 2 |
| `backend/domain/evidence.py` | 269 | CP-028 evidence state machine (`EVIDENCE_TRANSITIONS`), `EvidenceRecord`, `EvidenceStateHistory` | ~4 |
| `backend/domain/evidence_recommendation.py` | 194 | CP-018 `EvidenceRecommendation` | 2 |
| `backend/domain/cv_bullet_suggestion.py` | 344 | CP-036R `CVBulletSuggestion` transitions | 3 |
| `backend/domain/source_processing.py` | 229 | Source/batch processing statuses, extraction methods, `SourceTextRecord` | 3 |
| `backend/domain/source_text_review.py` | 189 | CP-008 `SourceTextReview` | 3 |
| `backend/domain/company_identity.py` | 217 | Provider-independent company entity kinds, URL types/lifecycles, `classify_company_link` | ~7 (WS-3) |
| `backend/domain/job_identity.py` | 188 | `canonicalize_url`, `posting_url_identity_key`, `dedupe_job_records` | ~15 |
| `backend/domain/pipeline_jobs.py` | 102 | `PipelineJob`, `normalize_job_record` | ~6 |
| `backend/domain/run_eta.py` | 148 | `build_run_eta` | 2 |
| `backend/domain/tracker.py` | 54 | Tracker placement metadata helpers | ~5 |

### 4.3 Configuration and environment schema

`backend/config/env_schema.py` defines `ENV_SCHEMA`. An AST parse at `58a96674` finds **48 keys**. That supersedes the "52" in the evidence package (audit N-6). Six keys are `required: True`. Scopes: 45 `backend`, 1 `shared`, 2 `frontend`.

| Group | Keys (names only) | Default / rule |
|---|---|---|
| Runtime / DB (4) | `RUNR_ENV`, `DATABASE_BACKEND`, `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN` | `development`; `sqlite`. Turso URL+token are required when `DATABASE_BACKEND=turso` or production. |
| Object storage (14) | `OBJECT_STORAGE_BACKEND`, `OBJECT_STORAGE_LOCAL_ROOT`, `OBJECT_STORAGE_CACHE_ROOT`, `OBJECT_STORAGE_CACHE_MAX_BYTES`, `OBJECT_STORAGE_CACHE_MAX_AGE_SECONDS`, `OBJECT_STORAGE_MAX_DOWNLOAD_BYTES`, `LOCAL_OBJECT_STORAGE_BASE_URL`, `LOCAL_OBJECT_STORAGE_SIGNING_SECRET`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET`, `S3_REGION`, `S3_SIGNED_URL_TTL_SECONDS` | `local`, `.backend_storage/objects`, `.backend_storage/cache`, 512 MiB, 86400 s, 100 MiB, loopback URL, (none), 4 × none, `auto`, 900 |
| Clerk (3, all required) | `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY` (shared), `CLERK_WEBHOOK_SECRET` | WS-6 |
| Creem (10) | `CREEM_API_KEY` (req), `CREEM_WEBHOOK_SECRET` (req), `CREEM_API_BASE_URL`, `CREEM_RUNR_PRO_PRODUCT_ID`, `CREEM_RUNR_PRO_{WEEKLY,MONTHLY,QUARTERLY}_PRODUCT_ID`, `CREEM_{LAUNCH,MOMENTUM,SCALE}_PRODUCT_ID` | 7 product-id keys; WS-6 |
| Origins / Assisted Apply (4) | `APP_FRONTEND_ORIGIN`, `RENDER_FRONTEND_EXTERNAL_HOSTNAME`, `RUNR_ASSISTED_APPLY_EXTENSION_ORIGINS`, `RUNR_ENABLE_ASSISTED_APPLY_PREPARATION` | preparation default `0` |
| Frontend (2) | `VITE_CLERK_PUBLISHABLE_KEY` (req), `VITE_API_EXTERNAL_HOSTNAME` | — |
| Company enrichment (8) | `RUNR_COMPANY_ENRICHMENT_{PROVIDER,LINKEDIN_SCRAPEOPS_MODE,LINKEDIN_PREFER_DIRECT,ENABLED,IMPORT_INVENTORY,MAX_COMPANIES,CONCURRENCY,REQUEST_BUDGET}` | `official_website`, `render_js_cheap`, `0`, `0`, `0`, 25, 5, 25 |
| Misc (3) | `RUNR_ENABLE_LIVE_NETWORKING_DISCOVERY`, `RUNR_DISABLE_QUOTAS`, `GEMINI_API_KEY` | — |

Validation rules in `get_environment_validation_errors` (`env_schema.py:375-435`):
- `RUNR_ENV` must be one of dev/development/test/staging/prod/production.
- `DATABASE_BACKEND` must be `sqlite` or `turso`.
- `OBJECT_STORAGE_BACKEND` must be `local`, `s3` or `r2`.
- The signed-URL TTL must be greater than 0.
- Turso requires both URL and token.
- `s3`/`r2`, or production, requires the four S3 values.
- Production additionally requires `DATABASE_BACKEND=turso`, an `s3`/`r2` storage backend, no `*` in `BACKEND_ALLOWED_ORIGINS`, and at least one exact `chrome-extension://[a-p]{32}` origin.

Env names read at runtime but **not** in `ENV_SCHEMA` include:
- `BACKEND_ALLOWED_ORIGINS` (validated only)
- `S3_CONNECT_TIMEOUT_SECONDS`, `S3_READ_TIMEOUT_SECONDS`, `S3_MAX_ATTEMPTS` (`storage/s3.py:28-39`)
- `RUNR_MIGRATION_HEAD`, `RUNR_STORAGE_BACKEND`, `RUNR_DATA_DIR` (deploy/release)
- `JOB_SEEKER_CONFIG_PATH`, `REUSABLE_PACKAGES_CONFIG_PATH`/`BLUE_COLLAR_CONFIG_PATH`, `RUNR_SKIP_PROJECT_DOTENV`
- `RUNR_INTERNAL_OBJECT_STORAGE_LOCAL_ROOT` (`bootstrap.py:324`)
- the MySQL names in section 4.1
- `SCRAPEOPS_API_KEY`, `DEEPSEEK_API_KEY` (render.yaml)

The schema is therefore descriptive, not exhaustive (WS5-G4).

Other config modules:

| File | Role | Users |
|---|---|---|
| `backend/config/__init__.py` | Re-exports job_seeker, env_schema and reusable_packages helpers | many |
| `backend/config/job_seeker.py` | `DEFAULT_JOB_SEEKER_CONFIG` including an `outputs` block (L202-206: stage4 JSON/XLSX, `generated_docs`). `load_project_dotenv` (L260) layers `.env` → `dev.env` → `user_config/.env` without overriding injected env; disabled by `RUNR_SKIP_PROJECT_DOTENV`. | capabilities, tools, scripts, `server.py:85`, `migrate.py:6` |
| `backend/config/reusable_packages.py` + `backend/config/reusable_packages.json` | Legacy "blue-collar" reusable-package config. The JSON holds a candidate block with personal contact fields (not reproduced here; privacy note WS5-G6). | `backend/capabilities/reusable_packages/support.py:6`, `backend/profiles/reusable_packages.py:3` |
| `backend/config/plans.py` | `free`/`runr_pro` plan catalog, quotas/limits, Creem product-id mapping from env | `quota.py`, `services.py:28`, `clerk.py:21`, `server.py:87`, routes, `stage_adapters.py:45` |
| `backend/config/scrapeops_admin_policy.py` | ScrapeOps policy defaults and normalizers; see section 6.4 | `backend/application/services.py:29-32` |
| `backend/config/company_site_inventory/discovered_regular_company_career_sites.jsonl` (1,414 lines), `.../discovered_phd_university_career_sites.jsonl` (1,092 lines) | Checked-in employer career-site inventory | `backend/connectors/company_career_sites.py:105-111`; imported into the catalog by `sqlite_acquisition.py:4935` when `acquisition.phase_f.company_site_inventory_enabled` is set (`services.py:964-971`) (WS-3) |

### 4.4 Local runtime data locations (T08)

These are local runtime data locations only. Their contents were not opened.

| Location | Gitignore at `58a96674` | Written by |
|---|---|---|
| `.backend_data/` (untracked) | `.gitignore:30` `.backend_*`, `:32` `.backend_data/`; also `*.sqlite`/`*.sqlite3`/`*.db` at `:40-42` | Default `--data-dir` (`workspace_runner.py:70`), migrate default DB path `.backend_data/backend.sqlite3` (`migrate.py:17`), file-backed stores, local objects fallback `<data_dir>/objects` (`bootstrap.py:325-327`) |
| `.backend_storage/` (untracked) | `.gitignore:30`, `:37` | `OBJECT_STORAGE_LOCAL_ROOT`/`OBJECT_STORAGE_CACHE_ROOT` defaults |
| `backend/config/outputs/` (untracked) | `.gitignore:47` ("Generated product outputs") | Legacy pipeline/document outputs; no code path at baseline builds this exact path from `job_seeker.py` (its `outputs` block uses relative filenames). The writer was not traced (WS5-G7). |

`git ls-tree` confirms none of the three is tracked. Ticket T08 (`clean-slate-2026-09-13/linear-ticket-candidates.md` L177-208) lists them as sensitive local data that needs an encrypted vault and off-machine copy. It is an owner action and changes no code.

### 4.5 Dependencies on other workstreams

- **WS-1** routes: [backend-api](backend-api.md).
- **WS-2** bootstrap/worker: [workers](backend-workers-and-orchestration.md).
- **WS-3** acquisition stores and the inventory: [acquisition source state](../03-data/acquisition-source-state.md).
- **WS-4** services that consume the stores.
- **WS-6** Clerk/Creem env: [security](security-and-auth.md).
- **WS-7** render.yaml, `deploy/start.sh`, release contract: [render](../02-deployment/render.md).

## 5. Important call and data flows

### 5.1 Connection selection
`connect_database(local_path)` (`connection.py:525-560`):
1. If `TURSO_DATABASE_URL` is set, or `_remote_database_required()` is true (`DATABASE_BACKEND=turso` or `RUNR_ENV` in prod/production, L496), use the remote path.
2. The remote path needs a token, otherwise `DatabaseConfigurationError`. It imports `libsql`, otherwise `DatabaseConfigurationError`. It then calls `libsql.connect(database=url, auth_token=token)` inside `_retry_libsql_operation` and wraps the result in `DatabaseConnection(backend="libsql", reconnect=...)`.
3. Otherwise it runs `mkdir` on the parent and `sqlite3.connect(path, timeout=30)`.
4. Always `PRAGMA foreign_keys = ON`.

Details: [turso-and-libsql.md](../03-data/turso-and-libsql.md).

### 5.2 Initialization and migration
`bootstrap.create_backend` → `_build_repositories` → `initialize_database(db_path)` (`initialization.py:29-50`). It is memoized per target key and identity: `"remote"` for Turso, otherwise the file's `st_dev:st_ino`. It takes `BEGIN IMMEDIATE`, runs `executescript(BASE_SCHEMA_SQL)`, then `run_migrations(connection, MIGRATIONS)`.

Each `_SqliteStore(db_path)` also calls `initialize_database` (`sqlite_core.py:19`). After the first call this is a memoized no-op.

At deploy, the `migrate` CLI calls `initialize_database(force=True)` and prints `migration_id\tstate\tdescription`. Details: [schema-and-migrations.md](../03-data/schema-and-migrations.md).

### 5.3 Store transactions
- Ordinary methods use `_SqliteStore._connect()`: one `database_session` per call, commit on exit (`sqlite_core.py:22-28`).
- `transaction_scope()` (L29-68) shares one connection across a bounded batch (used for producer delivery over Turso).
- `_run_transaction(callback)` (L70-91) delegates to `DatabaseConnection.transaction`. On libSQL that replays the whole callback after a transient failure (`connection.py:351-383`).

### 5.4 Artifact publication and object reads
`StageEngine` → `artifact_publisher` → `publish_file_artifacts(storage, run_id, artifacts)` (`materialization.py:148-193`):
1. Validate the download policy.
2. Build key `private/runs/<run_id>/<artifact_type>/<artifact_id>-<sha16>/<filename>`.
3. `storage.put`.
4. Record `object_key`, `object_size`, `object_etag` in the artifact metadata.

Reads go through `materialize_object` into the bounded cache. Details: [object-storage-r2.md](../03-data/object-storage-r2.md).

### 5.5 Worker-side analytics (still live in code)
`backend/adapters/stage_adapters.py:141-165` (also L744) `_build_scrapeops_usage_callback`:
- `analytics_store.record_scrapeops_usage` writes `scrapeops_usage_ledger`.
- `analytics_store.emit_event(event_name="scrapeops_request")` writes `analytics_events` (`sqlite_backed.py:2334-2372`).

The HTTP ingestion path `POST /analytics/events` has no registered route at baseline (audit N-1). The frontend still posts to it (`frontend/src/lib/analytics.js:125`, `frontend/src/lib/api.js:267`) and swallows the errors. See section 10, U7.

### 5.6 ScrapeOps policy resolution
`services._load_scrapeops_admin_policy` (`services.py:685-690`):
1. Read `config_store.get_value("scrapeops.admin_policy", defaults)` from `app_config`.
2. Normalize it with `normalize_scrapeops_admin_policy`.

It is consumed by `_plan_limit_for_user` (L718-726), `_current_company_site_policy_snapshot` (L761-768), `build_scrapeops_quota_overrides` (L1728-1735), `run_scrapeops_reconciliation_cycle` (L1878), `maybe_run_scheduled_scrapeops_maintenance` (L1978; called only by acquisition-role workers, `backend/worker/service.py:431-437`) and a company-site policy snapshot (L2053).

## 6. Invariants, failure handling and recovery

### 6.1 Database
- **Migration registry integrity** (`migrations.py:69-76`): IDs must be unique and sorted, and every migration needs a checksum. The checksum is the SHA-256 of id + description + source of the apply callable and its declared dependencies (`Migration.from_callable`, L34-57). Any edit to an applied migration's function, **or to a declared dependency such as `_ensure_table_column` or `prepare_user_payload`**, trips `MigrationChecksumError` on the next startup. Commits `81140897` and `6fd91cb2` ("preserve … migration checksum") were fixes for exactly this.
- **Legacy checksum upgrade**: a `schema_migrations` table without a checksum column gets the column added, and empty checksums are back-filled rather than failing (L94-107, L184-192). Status `applied_unverified` reports this case.
- **Atomicity**: base schema and pending migrations run in a single `BEGIN IMMEDIATE` session (`initialization.py:46-48`). A failure rolls back the whole batch (`database_session`, `connection.py:564-589`).
- **libSQL retries**: 4 attempts, backoff 0.25 → 2.0 s plus jitter. Only errors classified transient are retried (502/503, timeouts, network, stale stream, `PanicException` from `pyo3_runtime`/`libsql`). Auth, constraint and syntax errors are never retried (`connection.py:18-80`, `151-183`). Stale-stream and driver-panic errors force a reconnect (L331-340). Inside an explicit transaction, per-statement retry is off and the whole transaction is replayed instead (L342-383).
- **Cleanup never masks the primary error** (`_handle_cleanup_failure`, L196).
- **Test boundary**: `bootstrap._assert_test_database_boundary` (L354-380) refuses remote DB config, `DATABASE_BACKEND=turso`, production env, live acquisition network, or the default `.backend_data` path in test context.

### 6.2 Storage
- Keys must be relative, non-empty, free of `.`/`..` segments and NUL (`keys.py:15-30`). Private keys sanitize each segment and add a digest suffix when altered (L32-61).
- `LocalObjectStorage` confines paths to the root. The object path is `root/<h[0:2]>/<h[2:4]>/<h[4:32]>` from `sha256(key)` (`local.py:42-50`), and the legacy full-digest and plain layouts are still readable (L52-69).
- Downloads are rejected beyond `OBJECT_STORAGE_MAX_DOWNLOAD_BYTES` or for unapproved MIME types/suffixes, before any bytes or signed URL are issued (`policy.py:72-107`).
- The readiness probe is a bounded put/get/delete on a thread with a caller timeout capped at 30 s (`readiness.py:21-72`).

### 6.3 Config
`validate_environment` raises `EnvironmentValidationError` listing every error. `migrate` and `create_object_storage` both call it, so a misconfigured production environment fails migration pre-deploy before the API starts (by code path; not observed).

### 6.4 `backend/config/scrapeops_admin_policy.py`: live dependency, misleading name
- **Status: IMPLEMENTED-UNVERIFIED, live in code.** It is not dead residue. It supplies the defaults and normalization that `BackendApplication` uses for customer plan limits and ScrapeOps quota overrides (section 5.6) and for acquisition-role maintenance.
- **Residue aspect:** no writer of config key `scrapeops.admin_policy` exists in `backend/`, `frontend/src` or `scripts/` at baseline. `git grep admin_policy` outside this module and `services.py` returns nothing. The admin editing surface went away with the admin retirement (`dd47acf9`), so the effective policy is whatever row already exists in `app_config` or else the coded defaults. Whether the registered `admin.settings.put` route can write arbitrary `app_config` keys was not traced (WS5-G3, WS-1).
- The file's last change was `b0359e4d` (2026-06-19). The "admin" in its name is historical.

## 7. Relevant tests and safe verification commands

| Test file | Tests | Covers |
|---|---|---|
| `tests/test_database_migrations.py` | 6 | Apply-once and checksums, changed-migration rejection, two-column table upgrade, **ids 001–020 frozen only** (L138-163), workspace ownership and candidate-document backfills |
| `tests/test_database_connection.py` | 19 | Local rows/scripts, rollback, cleanup masking, libSQL env contract, transient retry/reconnect/panic replay, non-retryable errors, token requirement, installed `libsql` driver adapter (L445) |
| `tests/test_sqlite_repositories.py` | 9 | Workspace seeding, summary reads, run/job/artifact/review persistence, ScrapeOps ledger, source policy, URL history, run user-id backfill |
| `tests/test_object_storage.py` | 13 | Keys, local lifecycle/signing, factory, materialization, bounded probe, S3/R2 with an injected fake client (no network; L313 "real R2" test uses `_FakeS3Client`) |
| `tests/test_env_config.py` | 12 | Dotenv layering, local defaults, production Turso/R2/origin/extension rules |
| `tests/test_phase0_contracts.py` | 15 | Phase-0 normalizers |
| `tests/test_personalized_jobs_contracts.py` | 11 | Personalized-jobs contracts |
| `tests/test_backend_application.py` (L913) | — | file backend smoke |
| `tests/test_rc022_build_release_contract.py` | — | release contract (WS-7); does not compare the head against the registry |

`package.json` L5 `check:backend` includes `test_sqlite_repositories`, `test_phase0_contracts` and `test_env_config`. CI `backend` job L39 runs `python -m pytest -q`, the full suite.

Safe verification commands, **not executed in Phase 2**:
```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_database_migrations.py tests/test_database_connection.py tests/test_sqlite_repositories.py tests/test_object_storage.py tests/test_env_config.py tests/test_phase0_contracts.py tests/test_personalized_jobs_contracts.py
# local-only migration status against a scratch DB (never production credentials):
$env:RUNR_ENV='test'; .venv\Scripts\python.exe -m backend.database.migrate --status --database <scratch>\backend.sqlite3
```
Read-only static checks that were run:
```bash
git show 58a96674:backend/repositories/sqlite_migrations.py | grep -oE '"[0-9]{3}_[a-z0-9_]+"' | sort -u | wc -l   # 60
python -c "import ast;..."   # ENV_SCHEMA keys = 48
```

## 8. Historical decisions and supporting commits

109 commits touch the WS-5 paths (`git log --oneline 58a96674 -- <WS-5 paths> | wc -l`). Key ones:

| Commit | Date | Subject | Relevance |
|---|---|---|---|
| `bbb958b8` | 2026-04-18 | (initial large import) | first `sqlite_backed.py` |
| `fa5f32cb` | 2026-05-03 | URL Crawler, Workspace modularization, E-Tracking | MySQL career discovery |
| `ec49b716` | 2026-05-25 | ScrapeOps use AM control mechanisms and endpoint. | `scrapeops_admin_policy.py` introduced |
| `c7bf7cbd` | 2026-06-18 | deoployment prep initial setup | `backend/database/connection.py`, `migrations.py`, `storage/s3.py` added (Turso/R2 foundation) |
| `10e65b01`, `d6018c3e`, `386ea700` | 2026-06-21…07-02 | Production Tech Stack Correction / render turso r2 fixes / Turso fix | libSQL hardening |
| `dcbd9765` | 2026-07-22 | feat(cp-025): version profiles… | `versioning_repository.py` |
| `93419e48` | 2026-08-04 | fix: recover occupied Turso streams | stale-stream reconnect |
| `ee5b113a` | 2026-08-07 | fix(storage): keep local object paths Windows-safe | 32-hex local layout |
| `81140897`, `6fd91cb2` | — | preserve production / applied enrichment migration checksum | checksum invariant |
| `12f342fb` | 2026-08-12 | feat: add read-only acquisition analytics dashboard | added migration 055 (retired feature; residue) |
| `39d15b8f` | 2026-09-08 | RC-022 separate release and runtime contracts | `RUNR_MIGRATION_HEAD=058` in render.yaml (C3) |
| `7251ae29` | 2026-09-08 | feat(acquisition): reconcile producers inputs and runtime data | storage cache/download limits, env keys, 058 registry wording |
| `d44d3c0f` | 2026-09-11 | production: restore canonical publication chain | migration 059 |
| `c964b208` | 2026-09-12 | speed up publication latest observation reads | migration 060 |

`backend/domain`, `backend/database`, `backend/storage` and `backend/config` have had no content change since `848408f3` (audit row 26). All of the repositories changes since then are in files WS-5 re-read at baseline.

## 9. Current implementation status

| Capability | Classification |
|---|---|
| SQLite/libSQL connection selection and retry | VERIFIED (scope: static — `connection.py:484-560` read; selection rules match `env_schema` validation; covered by 19 tests, not run) |
| Checksum-guarded migration engine | VERIFIED (scope: static — `migrations.py` read in full; invoked from `initialization.py:48` and `migrate.py:40`) |
| Migration registry 001–060 | VERIFIED (scope: static — AST enumeration of `MIGRATIONS`, 60 contiguous ids) |
| Repository backend selection sqlite/file | VERIFIED (scope: static — `bootstrap.py:263-308`, `workspace_runner.py:71`) |
| File-backed stores | PARTIAL (legacy; missing evidence/acquisition/personalized stores; one test user) |
| Object storage local + S3/R2 | VERIFIED (scope: static — factory branches `factory.py:20-41`; used by `bootstrap.py:330`) |
| Download policy / cache bounds (RC-021) | IMPLEMENTED-UNVERIFIED |
| Env schema + production validation | VERIFIED (scope: static — 48 keys by AST; rules in `env_schema.py:375-435`) |
| ScrapeOps policy defaults consumed by services | IMPLEMENTED-UNVERIFIED (admin editor RETIRED; no writer) |
| MySQL career-discovery sink | IMPLEMENTED-UNVERIFIED (tool-only, opt-in) |
| Profile/CV versioning helpers | IMPLEMENTED-UNVERIFIED |
| Domain contracts (22 modules) | IMPLEMENTED-UNVERIFIED (unit-tested contracts for phase0/personalized jobs) |
| Worker-side `analytics_events` writes | IMPLEMENTED-UNVERIFIED |
| HTTP `POST /analytics/events` ingestion | RETIRED/HISTORICAL (unregistered, 404; audit N-1; WS-1 owns) |
| Migration 055 acquisition analytics indexes | RETIRED/HISTORICAL feature; migration retained append-only |
| Release migration-head gate | UNKNOWN (no gate in code and no doc/ticket plans one; only release metadata exists, C3) |

### Deployment evidence (documentary only)
- `docs/deployment/render.md` L91-99 names the intended production values: `DATABASE_BACKEND=turso`, a libSQL URL, `OBJECT_STORAGE_BACKEND=r2`, and an R2 endpoint. `render.yaml` api/worker set `DATABASE_BACKEND=turso`, `OBJECT_STORAGE_BACKEND=r2`, `S3_REGION=auto`, and `sync: false` for the Turso and S3 credentials.
- `docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md` (2026-09-11) records Render on `5dfdd106` and a bounded R2 write/read/delete probe passing. It is documentary, 44 commits behind baseline.
- The untracked 2026-09-12 report records shared Turso catalog counts. Documentary; current counts are UNKNOWN.

## 10. Confirmed gaps and unresolved questions

| ID | Item |
|---|---|
| C3 (WS-5/WS-7) | `RUNR_MIGRATION_HEAD=058_customer_task_queue` (`render.yaml:76-77`, `:193-194`) and `DEFAULT_MIGRATION_HEAD` (`backend/deployment/release_contract.py:14`, read at `:136`) differ from registry head `060_publication_latest_observation_index`. No code compares them. Metadata only. |
| C7(c) | Migration `055_acquisition_analytics_indexes` is residue from the retired admin analytics feature. It must stay (append-only checksum). Dropping its indexes would need a new migration and an owner decision. |
| C7(d) | `scrapeops_admin_policy.py` is live in code with a residual name and no writer (section 6.4). |
| U7 (reformulated per N-1) | The HTTP ingestion endpoint is dead (unregistered), and the frontend emitter posts to a 404. Owner question: delete the dead `admin.py` handler plus the frontend emitter, or re-register? Worker-side writes to `analytics_events` (`stage_adapters.py`) remain. `services.py:1513`/`1748` and `cv_upload_jobs.py:285` still read the table. |
| T08 | `.backend_data/`, `.backend_storage/`, `backend/config/outputs/` are sensitive, gitignored local data; vault and off-machine copy still open (owner). |
| WS5-G1 | `tests/test_database_migrations.py:138` freezes only ids 001–020; ids 021–060 have no order/name regression test. |
| WS5-G2 | Residue bugs: `backend/repositories/__init__.py:67` and `:93` put class objects (not strings) into `__all__`, so `from backend.repositories import *` would raise `TypeError`. `contracts.py:454-455` declares `career_profile_store` twice. |
| WS5-G3 | Can a registered `admin.settings.put` route write `app_config` key `scrapeops.admin_policy`? Not traced (WS-1). |
| WS5-G4 | `ENV_SCHEMA` is not exhaustive (section 4.3 list). `describe_env_schema` under-reports runtime env. |
| WS5-G5 | `DatabaseConnection` uses `sqlite_master`/`PRAGMA` introspection in migrations. libSQL compatibility is asserted by tests with fakes plus one installed-driver adapter test; there is no test against a real Turso instance (by design, offline). |
| WS5-G6 | `backend/config/reusable_packages.json` is tracked and contains personal candidate contact fields. Privacy review suggested (WS-6/WS-11). |
| WS5-G7 | The writer of `backend/config/outputs/` was not identified at baseline (likely legacy pipeline). |

## Agent context and remaining work

**(a) Agent context packet**
- Required reading: this doc; `backend/database/{connection,migrations,initialization}.py`; the `MIGRATIONS` tuple at `backend/repositories/sqlite_migrations.py:3217`; `backend/repositories/contracts.py`; `backend/bootstrap.py:257-380`; `backend/storage/{factory,local,s3,materialization,policy}.py`; `backend/config/env_schema.py`; `AGENTS.md`.
- Allowed paths: the 55 WS-5 files (section 2).
- Tests to run: the seven key tests in section 7 via `.venv\Scripts\python.exe -m pytest -q …`.
- Prohibited:
  - editing or reordering any existing migration or its declared dependency functions (checksum break); new schema only as a new `061_*` entry appended;
  - running `migrate` against production credentials;
  - copying env values or secrets;
  - touching WS-3/WS-4 repository files;
  - deleting migration 055;
  - removing `ENV_SCHEMA` keys without WS-6/WS-7 review.

**(b) Registry proposal**

| id | name | owned globs | primary doc | test globs | owner |
|---|---|---|---|---|---|
| `data-domain-storage-config` | Data, repositories, storage, config and domain model | `backend/database/**`, `backend/storage/**`, `backend/config/**`, `backend/domain/**`, `backend/repositories/{__init__,contracts,file_backed,mysql_career_discovery,sqlite_backed,sqlite_core,sqlite_migrations,versioning_repository}.py` | `docs/reverse-engineering/01-architecture/domain-model.md` | `tests/test_database_*.py`, `tests/test_sqlite_repositories.py`, `tests/test_object_storage.py`, `tests/test_env_config.py`, `tests/test_phase0_contracts.py`, `tests/test_personalized_jobs_contracts.py` | WS-5 |

**(c) Gap and ticket candidates**
1. Add a startup or CI check that `RUNR_MIGRATION_HEAD` equals `MIGRATIONS[-1].migration_id`, or derive the head from the registry (C3; with WS-7).
2. Extend the frozen-id migration test to 001–060 (WS5-G1).
3. Fix the `__all__` entries and the duplicate dataclass field (WS5-G2).
4. Owner decision on U7: remove the dead ingestion handler and frontend emitter.
5. Rename or document `scrapeops_admin_policy` as a service policy, and decide whether a writer is needed (C7(d), WS5-G3).
6. Complete `ENV_SCHEMA` or mark it partial (WS5-G4).
7. Privacy review of `reusable_packages.json` (WS5-G6).
8. T08 vault (owner; existing ticket).
