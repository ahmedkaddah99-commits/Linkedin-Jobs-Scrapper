> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Personalized jobs and customer application services (WS-4, primary)

Secondary slice: [career-profiles-and-documents.md](career-profiles-and-documents.md) covers profiles, the Master CV, CV upload, tailored documents, Career Memory, evidence and work experience. The browser-extension side of Assisted Apply belongs to WS-9: [assisted-apply.md](assisted-apply.md). This doc covers only the backend services behind it.

All line numbers refer to `58a96674`. "Static" means read from source at that SHA. Nothing here was run, and no live system was contacted. LIVE PRODUCTION = UNKNOWN.

---

## 1. Purpose and user-facing capabilities

`backend/application/` is the Python layer between the HTTP route handlers ([backend-api.md](../01-architecture/backend-api.md), WS-1) and the worker ([backend-workers-and-orchestration.md](../01-architecture/backend-workers-and-orchestration.md), WS-2) on one side, and the repositories/domain model ([domain-model.md](../01-architecture/domain-model.md), WS-5) on the other. The facade `BackendApplication` (`backend/application/services.py:863`) is built once by `backend/bootstrap.py:344`. It composes these sub-services (`services.py:880-930`):

| Customer capability | Service (owned) | Facade methods (`services.py`) |
|---|---|---|
| Personalized Jobs feed over the published catalog: filters, saved search, preferences, save/hide/report, company pages, job intelligence | `personalized_jobs_service.py` `PersonalizedJobsService` (L844), `personalized_jobs_intelligence.py` | `get_personalized_jobs` L1159 … `get_hidden_personalized_jobs` L1357 |
| Monthly plan quotas | `quota.py` | used directly by routes and the stage adapter (§3) |
| Async customer slow tasks: bulk document export, tracker email sync | `customer_tasks.py` | `enqueue_customer_task` L1227, `process_next_customer_task` L1253 |
| Tracker, referral contacts, LinkedIn connection sync, outreach, relevant-people discovery | `tracker_services.py` `TrackerApplicationService` (L37), `backend/capabilities/networking/**`, `backend/capabilities/tracker/**` | L2708-2880 |
| Workspaces, workflow templates, runs, reviews, artifacts, workers | `domain_services.py` `WorkspaceCatalogService` (L35), `run_services.py` `RunLifecycleService` (L76) | L1413-1430, L1998-2622, L3108-3366 |
| Identity, API tokens, secrets, scopes | `domain_services.py` `IdentityAccessService` (L121) | L2624-2636, L2882, L3011-3070 |
| Phase I production rollout gates and the catalog cohort gate | `production_rollout.py` | L1068-1105 (no route caller, §3) |
| Assisted Apply backend: extension connection (PKCE), application packages, document grants, corrections, preparations, telemetry | `assisted_apply_service.py`, `assisted_apply_package_service.py`, `assisted_apply_correction_service.py`, `assisted_apply_preparation_service.py`, `assisted_apply_telemetry_service.py` | L2897-3010, L3371-3545 |
| Per-user ScrapeOps company-site budget and usage, shown in Settings | `services.py` L685-815, L1479-1997 (policy config owned by WS-5) | `get_scrapeops_user_usage_summary` L1672 |
| Capability registries shown in the workspace builder (connectors, generations, renderers, stages) | built in `backend/bootstrap.py:47-253` (WS-2); implementations in `backend/capabilities/**` | `list_connectors` L2004, `list_generations` L2007, `list_renderers` L2010, `get_workspace_builder_catalog` L2013 |

`backend/application/` also contains 13 acquisition and company files owned by WS-3 (see §2). `BackendApplication` exposes them too: `run_due_acquisition` L932, `run_due_company_enrichment` L940 and the acquisition cycle/audit methods L1019-1156, L1360-1395. They are documented in [acquisition-and-collectors.md](acquisition-and-collectors.md) and [company-identity-enrichment-and-logos.md](company-identity-enrichment-and-logos.md).

## 2. Owned paths and governing instructions

| Path | Files | Lines (approx.) | Notes |
|---|---|---|---|
| `backend/application/` (WS-4 subset) | 18 of 31 | ~11,400 | `__init__`, `assisted_apply_{correction,package,preparation,telemetry}_service`, `assisted_apply_service`, `baseline_cv_replacement_service`, `contracts`, `customer_tasks`, `domain_services`, `personalized_jobs_intelligence`, `personalized_jobs_service`, `production_rollout`, `quota`, `rebind_service`, `run_services`, `services` (3,545 lines), `tracker_services` |
| `backend/capabilities/**` | 56 | ~22,000 | packages: `candidate_evidence`, `career_profile_evidence`, `cv_bullet_suggestions`, `evidence_recommendation`, `networking`, `profile_matching`, `reusable_packages`, `source_processing`, `source_text_review`, `tailored_documents` (21 files), `tracker` |
| `backend/career_memory/**`, `backend/evidence/**`, `backend/evidence_library/**`, `backend/master_cv/**`, `backend/profiles/**`, `backend/work_experience/**` | 2 + 4 + 2 + 2 + 11 + 2 | — | see the secondary doc |
| `backend/tools/**` | 6 | ~3,500 | local CLI tools (see the secondary doc) |
| `backend/scripts/**` | 1 | 100 | `migrate_users_to_clerk.py` |
| `backend/repositories/sqlite_personalized_jobs.py` | 1 | 1,680 | `SqlitePersonalizedJobsStore`: preferences, dispositions, intelligence queue, published-catalog queries, customer tasks |
| `backend/repositories/assisted_apply_preparation.py` | 1 | 94 | preparation persistence |
| `backend/repositories/document_payloads.py` | 1 | 187 | splits candidate document text/assets out of user/workspace/run payloads |

The 13 WS-3 files in `backend/application/` are **not** owned here: `acquisition_scheduler`, `company_enrichment`, `company_enrichment_resolution`, `company_identity_canonicalization`, `company_logo`, `company_logo_adapter`, `company_id_backfill`, `company_reconciliation`, `company_registry_reconciliation`, `company_operations`, `source_eligibility_manifest`, `expansion_wave_manifest`, `duplicate_decisions`.

Governing instructions and specs. Each was opened, and its agreement with code is stated:
- Root `AGENTS.md` (25 lines): covers only the Python environment, with nothing specific to this subsystem.
- `docs/personalized_jobs_contracts.md`: says "P0 definitions only … not yet persisted". It describes `backend/domain/personalized_jobs_contracts.py` (WS-5). Its header is **stale**: migration `034_phase_c_personalized_jobs` and `SqlitePersonalizedJobsStore` now persist preferences, saved searches and dispositions. Keep it for payload shapes only.
- `docs/RC020_CUSTOMER_TASK_QUEUE.md`: **matches code** for the two task types, the `202` + status URL behaviour, customer-role-only claiming and bounded attempts (`customer_tasks.py:10-12`, `services.py:1253-1301`).
- `docs/PERSONALIZED_JOBS_PREVIEW.md`: describes a frontend-only preview behind `VITE_PERSONALIZED_JOBS_EXPERIENCE`, with redirects to "the existing dashboard". This is **historical**: the backend feed now exists (§3), and `/dashboard` is residue (§10).
- `docs/reports/phase_i_production_rollout_acceptance_2026-08-07.md`: "not complete — production approval and live evidence are pending". Offline acceptance only.
- Assisted Apply architecture and ticket docs (`docs/architecture/assisted_apply_*_2026-08-01.md`, `docs/assisted-apply/runr-assisted-apply-ticket-pack.md`) are owned and assessed by WS-9 in [assisted-apply.md](assisted-apply.md).
- Standing never-submit boundary for Assisted Apply (owner decision; see WS-9). On the backend side, `assisted_apply_package_service.py:66-67` accepts only observed outcome evidence (`success_banner`, `confirmation_page`, `url_transition`) and the adapters `greenhouse`/`lever`. The backend never submits anything.

## 3. Entry points and registered routes/commands/units

### 3.1 HTTP routes → services

Routes are registered per module and loaded by `build_route_registry` (`backend/api/server.py:28`; WS-1 owns the registry, `backend/api/routes/registry.py`). The table lists registered route **names** and what they call.

| Route module (WS-1) | Registered route names | WS-4 services called |
|---|---|---|
| `backend/api/routes/acquisition_catalog.py:10-22` | `personalized_jobs.read`, `.preferences.read/write/patch`, `.saved_search.read/write/post`, `.hidden.read`, `.report`, `.company.read_prefix`, `.job.read`, `.job.action`, `.job.delete` | `get_personalized_jobs`, `get_personalized_preferences`, `save_personalized_preferences`, `get/save_personalized_saved_search`, `get_personalized_job_detail`, `get_personalized_company_detail`, `set_personalized_job_state`, `report_personalized_job/filter`, `get_hidden_personalized_jobs`, `improve_personalized_resume`, `enqueue_personalized_job_intelligence`, `get_public_acquisition_catalog` |
| `backend/api/routes/tracker.py:29-42` | `tracker.google.callback` (no auth), `tracker.referrals[.post/.put/.delete]`, `tracker.tracker[.post/.put/.delete]`, `tracker.rejected_jobs[.post]`, `tracker.people_discovery[.post]`, `tracker.outreach.post` | `TrackerApplicationService` via the facade (referrals, LinkedIn sync status, outreach, relevant-people discovery), `customer_tasks` (`CUSTOMER_TASK_EMAIL_SYNC`, L323, L817), `quota.check_and_increment_quota` (L637), `capabilities/tracker` |
| `backend/api/routes/documents.py:77-87` | `documents.cv`, `.cv_upload_status`, `.contracts`, `.documents[.post/.put/.delete]`, `.cv_upload`, `.profile_photo_upload`, `.ats`, `.run_generation` | `customer_tasks` (`CUSTOMER_TASK_BULK_EXPORT`, L502-527; status/download L217-226), `profiles.cv_editor`, `profiles.cv_upload_jobs`, `quota` (L552), `requeue_job_for_generation` (see the secondary doc) |
| `backend/api/routes/workspace.py:23-46` | `workspace.workspaces*`, `.builder*`, `.templates*`, `.connectors`, `.generations`, `.renderers`, `.runs*`, `.review_queue`, `.artifacts`, `.workers*`, `.quick_apply`, `.career_url_discovery` | `WorkspaceCatalogService`, `RunLifecycleService`, `start_quick_apply_run`, `validate_workspace_builder_sources` (uses the ScrapeOps policy), `quota` (L418, L474, L549). `career-url-discovery/run` raises `PermissionError` ("disabled on the production API", L381-382) |
| `backend/api/routes/assisted_apply.py` | `assisted_apply.extension.connection_requests.create`, `.extension.token.exchange`, `.extension.session.verify/delete`, `.extension.preferences.update`, `.web.connection.get`, `.web.connection_requests.action`, `.web.preferences.update`, `.web.sessions.delete` | `AssistedApplyConnectionService` |
| `backend/api/routes/assisted_apply_packages.py:31-103` | `assisted_apply.packages.create/prepare/launch`, `.extension.packages.bind/get/post`, `.extension.document_grants.create/download`, `.extension.corrections.create`, `.extension.standard_answers.create`, `.extension.application_outcomes.create` | `ApplicationPackageService`, `AssistedApplyCorrectionService` |
| `backend/api/routes/assisted_apply_preparations.py:19-23` | `assisted_apply.preparations.create/read/action`, `.extension.preparations.report/action` (no bearer auth; extension session) | `AssistedApplyPreparationService` |
| `backend/api/routes/assisted_apply_telemetry.py:44` | `assisted_apply.telemetry.events.receive` (no auth) | `AdapterHealthTelemetryService` |
| `backend/api/routes/assisted_apply_linkedin.py:10` | `assisted_apply.extension.linkedin_connections.sync` | `sync_linkedin_connections`, `get_user_plan_id` |
| `backend/api/routes/application_bindings.py:20-32` | `application_bindings.list/create/get/delete` | `capabilities/profile_matching/application_binding.py` |
| `backend/api/routes/admin.py:24-33` (customer billing/settings, despite the file name) | `admin.scrapeops` (`GET scrapeops/usage`, L84-100), `admin.settings`/`.settings.put`, `admin.billing*` (incl. `.billing.post`), `admin.auth.me`, `admin.webhooks.clerk`, `admin.webhooks.creem`, `admin.account.delete` | `get_scrapeops_user_usage_summary`, `get_scrapeops_usage_summary`. Billing/webhooks are WS-6: [billing-and-creem.md](billing-and-creem.md) |
| Career/evidence/Master CV route modules | see the secondary doc §3 | — |

Unregistered handler bodies (N-1, residue only, WS-1 owns them): `admin.py:102` (`["dashboard"]` → `server.py:7358 _dashboard_payload` → `server.py:7143 _dashboard_analytics_payload`) and `admin.py:239` (`["analytics","events"]`). Neither has a `registry.exact/prefix` entry in `admin.py:24-33`.

### 3.2 Worker task families → services

Roles and families are defined in `backend/worker/roles.py:5-26`: role `customer` → family `customer`; role `acquisition` → family `acquisition`. `backend/worker/service.py` (WS-2) calls:

| Family | Call (worker/service.py) | WS-4 target |
|---|---|---|
| customer | L261 `process_next_personalized_intelligence` | `PersonalizedJobsService.process_next_intelligence` (L1060) → `SqlitePersonalizedJobsStore.claim_next_intelligence` (L672) / `complete_intelligence` (L722) |
| customer | L277 `process_next_customer_task` | `services.py:1253` → `customer_tasks.execute_customer_task` (L64) |
| customer | L298 `claim_next_queued_run` → `execute_claimed_run` | `RunLifecycleService.claim_next_queued_run` (L713) / `execute_claimed_run` (L769); CV upload runs branch at `run_services.py:771` → `profiles/cv_upload_jobs.process_cv_upload_run` |
| acquisition | L437 `maybe_run_scheduled_scrapeops_maintenance` (every 60 s) | `services.py:1978` → `run_scrapeops_reconciliation_cycle` L1878 |
| acquisition | L476 `run_due_acquisition`, L502 `run_due_company_enrichment` | WS-3 services |

Stage adapters (`backend/adapters/stage_adapters.py:11-60`, WS-2) import `capabilities/reusable_packages/*`, `capabilities/tailored_documents/*`, `capabilities/source_processing/extraction` and `profiles/cv_text`. They charge runner credits via `quota.check_and_increment_quota_amount` (L654, L720). Stages are registered at `stage_adapters.py:1206`.

### 3.3 CLI

`workspace_runner.py` (WS-1) calls the facade for users, tokens, secrets, runs and registries, and imports `backend/tools/discover_company_careers.py` (L15). `backend/scripts/migrate_users_to_clerk.py:84 main()` is a one-off script that calls `backend.bootstrap.create_backend` and `backend.integrations.clerk`. No deploy unit references WS-4 paths directly.

## 4. Inputs, outputs, storage and dependencies

| Store / table | Owner of schema | Written by (WS-4) |
|---|---|---|
| `personalized_search_preferences`, `personalized_saved_searches`, `personalized_job_dispositions`, `personalized_job_events`, `personalized_job_evaluations` (`sqlite_migrations.py:1640-1685`, migration `034_phase_c_personalized_jobs`) plus the intelligence cache/queue (`035_phase_e_job_intelligence`, `038_phase_e_async_intelligence`) | WS-5 [schema-and-migrations.md](../03-data/schema-and-migrations.md) | `sqlite_personalized_jobs.py:80-790` |
| Published catalog (read-only): `query_published_jobs` L1172, `get_current_publication` L1062, `get_published_company_page` L1259 | WS-3 [publication-and-catalog.md](publication-and-catalog.md) | reads only |
| Company profiles/enrichment targets (`sqlite_personalized_jobs.py:793-1044`) | WS-5 / WS-3 | written by the WS-3 `CompanyEnrichmentService` through `profile_writer=upsert_company_profile` (`services.py:925-929`) |
| `customer_tasks` (`sqlite_migrations.py:1891`, migration `058_customer_task_queue`) | WS-5 | `sqlite_personalized_jobs.py:1468-1640` |
| `quota_usage` (`sqlite_migrations.py:165`) | WS-5 | via `auth_repository.increment_quota_usage` (`quota.py:38-45`, L99+) |
| `assisted_apply_connections`, `application_packages`, `assisted_apply_corrections`, `assisted_apply_correction_audit`, `assisted_apply_document_grants`, `assisted_apply_submission_events`, `assisted_apply_tracker_records`, `assisted_apply_preparations`, `assisted_apply_preparation_reports` (`sqlite_migrations.py:823-1035`, migrations 016-020, 027, 028) | WS-5 | the `assisted_apply_*` services and `repositories/assisted_apply_preparation.py` |
| `app_config` key `scrapeops.admin_policy` (read-only here) | WS-5 `backend/config/scrapeops_admin_policy.py:11` | none; read by `services.py:689` |
| Rollout config keys `acquisition.phase_i.*` | WS-5 config store | `ProductionRolloutService.configure/advance` (unreachable from routes, §3) |
| `analytics_events` | WS-5 | `BackendApplication.emit_event` L1431 (ScrapeOps reconciliation/alert events). Worker-side analytics is WS-2 |
| Object storage: company logos (signed URL, `personalized_jobs_service.py:872-880`), document grants and packages | WS-5 [object-storage-r2.md](../03-data/object-storage-r2.md) | — |

Environment keys read inside WS-4 services. Only names are listed, never values. "Schema" means declared in `backend/config/env_schema.py`; "render" means a `key:` in `render.yaml`.

| Key | Read at | Schema / render.yaml |
|---|---|---|
| `PERSONALIZED_JOBS_SUMMARY_PROVIDER` (must equal `gemini` to enable AI summaries), `PERSONALIZED_JOBS_SUMMARY_MODEL` (default `gemini-2.5-flash-lite`), `GEMINI_API_KEY` / `GOOGLE_API_KEY` | `personalized_jobs_intelligence.py:367-397` (`google.genai`, L373) | only `GEMINI_API_KEY` is in the schema; none are in render.yaml. With the provider unset, summaries are deterministic (`build_description_intelligence` L411) |
| `RUNR_CUSTOMER_TASKS_ASYNC`, `RUNR_ENV` | `customer_tasks.py:18-23` (default async only when `RUNR_ENV` is prod/production) | render.yaml L78, L195; not in the schema |
| `RUNR_DISABLE_QUOTAS` | `quota.py:35`; also `server.py:7417` | schema L267 |
| `RUNR_PRIVATE_TEST_DEPLOYMENT` | `production_rollout.py:68-72` (forces rollout flags off, L142-156) | render.yaml L80, L197 |
| `CREEM_API_KEY`, `CREEM_WEBHOOK_SECRET`, `CREEM_RUNR_PRO_PRODUCT_ID` (presence check only) | `production_rollout.py:356-357` | WS-6 |
| `RUNR_ENABLE_ASSISTED_APPLY_PREPARATION` | `assisted_apply_preparation_service.py:34,54` | schema; render.yaml L103 |
| `SCRAPEOPS_API_KEY` | `services.py:817` (account state), L1709 (domain stats); `capabilities/networking/discovery.py:550,718`; `capabilities/tailored_documents/linkedin_connector.py:171` | render.yaml L150, L239 |
| `DEEPSEEK_API_KEY` (+ model keys `DEEPSEEK_NETWORKING_DISCOVERY_MODEL`, `DEEPSEEK_STAGE4_MODEL`) | `capabilities/networking/discovery.py:562-567` (`https://api.deepseek.com/chat/completions` L582); document generation in the secondary doc | render.yaml L152, L241 |
| `RUNR_ENABLE_LIVE_NETWORKING_DISCOVERY`, `RUNR_NETWORKING_DISCOVERY_SEARCH_MODE/COUNTRY` | `capabilities/networking/discovery.py:534,722-723` | schema; render.yaml L86, L203 |
| `TRACKER_GOOGLE_OAUTH_CLIENT_ID/_SECRET/_REDIRECT_URI/_SCOPES` | `capabilities/tracker/google_oauth.py:27-34` | render.yaml L154 (client id) |
| `RUNR_COMPANY_ENRICHMENT_ENABLED`, `RUNR_COMPANY_ENRICHMENT_IMPORT_INVENTORY` | `services.py:952-960` (WS-3 feature, facade-owned read) | schema; render.yaml L90, L207 |

Document rendering dependency: the server-side CV PDF renderer shells out to `node frontend/scripts/render-cv-pdf.mjs` (`capabilities/tailored_documents/rendering.py:1350-1380`). For that reason the Render `runr-api` and `runr-worker` `buildFilter` lists include `frontend/package.json`, `frontend/package-lock.json`, `frontend/scripts/render-cv-pdf.mjs`, `frontend/src/lib/cvStudio.js` and `frontend/src/lib/cvSocialLinks.js` (`render.yaml:60-64`, `176-180`). `Dockerfile.api:56-58` and `Dockerfile.worker:55-57` copy them, and `backend/deployment/release_contract.py:18-25` mirrors them as `FRONTEND_RUNTIME_PATHS`. WS-7 owns these files: [render.md](../02-deployment/render.md).

Other dependencies: plan limits come from `backend/config/plans.py` (WS-5). Auth context (`plan_id`, `quota_overrides`) comes from WS-6 [security-and-auth.md](../01-architecture/security-and-auth.md). The ScrapeOps client lives in `backend/integrations/scrapeops.py` (WS-6).

## 5. Important call/data flows

1. **Jobs feed** (`GET /personalized-jobs`): `acquisition_catalog.py` → `services.py:1159 get_personalized_jobs` → `personalized_jobs_service.py:1290 feed`. The flow:
   - `_assert_catalog_access` (L853) → `production_rollout.catalog_user_access` (L159). This returns true unless `user_cohort_gate_enabled`; otherwise only internal or selected cohort users get through.
   - Filters merge in order: preferences, then the saved search (applied only when no explicit filters), then explicit filters.
   - Non-Pro plans are downgraded from `priority`/`best` sort to `newest` (L1315-1317).
   - A cursor fingerprint mismatch raises `cursor_filter_mismatch`.
   - `store.query_published_jobs` (L1172) runs against the current publication.
   - Cached intelligence is attached. GETs never enqueue intelligence (`services.py:1303-1305` docstring).
2. **Job intelligence**: `enqueue_personalized_job_intelligence` → `enqueue_intelligence_for_job` (L930) → `store.enqueue_intelligence` (L551). The customer worker then runs `process_next_intelligence` (L1060): `recover_stale_intelligence` (L614), `claim_next_intelligence`, `build_description_intelligence` (optional Gemini summary), `build_match_intelligence` (L784), and `complete_intelligence`. `improve_resume` (L1211) builds a tailored document payload (`build_tailored_document` L811).
3. **Customer tasks**:
   - Route side (`documents.py:502-527`, `tracker.py:817`): if `customer_tasks_async_enabled()`, the route calls `enqueue_customer_task` with `customer_task_idempotency_key` (sha256 of user/type/payload, `customer_tasks.py:26`) and returns `202` with the status URL (`customer_task_status_url` L37). Otherwise it runs synchronously.
   - Worker side (`services.py:1253`): non-customer roles return immediately (L1261). The worker calls `recover_stale_customer_tasks`, then `claim_next_customer_task`, then `execute_customer_task`, and finally `complete_customer_task` with the lease token (fenced).
   - Task bodies import `backend.api.server` helpers lazily: `_create_bulk_export_bundle` (`customer_tasks.py:73-88`) and the tracker email helpers (L91-186). This is a layering inversion (WS4-G3).
   - `public_customer_task` (L45) strips `user_id`, lease fields and the local bundle `path`.
4. **Quota**: `check_and_increment_quota` (`quota.py:99`) resolves the limit (override, else `plans.get_quota`) and short-circuits with `limit=-1` if quotas are disabled. It raises `QuotaExceededError` (L10) when `used >= limit` and emits an event. The period key is UTC `YYYY-MM`.
5. **Assisted Apply packages**: `create_application_package` (`services.py:3371`) → `ApplicationPackageService.create_package` (L252). Then `launch_package` (L321) → the extension calls `bind_package` (L361) and `get_or_bind_package_for_extension` (L439). Next come `create_document_grant` (L526; 60 s TTL, `aadoc_` prefix, ≤10 MiB, L43-48) and `consume_document_grant` (L628). `respond_to_application_outcome` (L703) records a submission event and a tracker record idempotently (L766-797). Corrections go through `AssistedApplyCorrectionService` (365-day TTL, sensitive exact-question filter, `assisted_apply_correction_service.py:30-38`). Connection (`assisted_apply_service.py`): a chrome-extension origin with a 32-char `[a-p]` id, PKCE S256, request TTL 10 min, auth code 2 min, session 8 h (L26-38). Preparations are gated by `RUNR_ENABLE_ASSISTED_APPLY_PREPARATION`, and report idempotency uses a fingerprint (`repositories/assisted_apply_preparation.py:66-86`).
6. **ScrapeOps company-site policy** (decision for the brief question): `services.py:29-32` imports `SCRAPEOPS_ADMIN_POLICY_CONFIG_KEY`, `default_scrapeops_admin_policy`, `normalize_scrapeops_admin_policy` and `plan_policy_limits` from WS-5's `backend/config/scrapeops_admin_policy.py`.
   - `_load_scrapeops_admin_policy` (L685-690) reads `app_config` key `scrapeops.admin_policy`, defaulting to plan-derived limits (`scrapeops_admin_policy.py:59-80`).
   - `_effective_scrapeops_policy_limits` (L693-715) and `_plan_limit_for_user` (L718-734) feed `_current_company_site_policy_snapshot` (L761-813).
   - That snapshot is served by the **registered customer route** `admin.scrapeops` → `GET scrapeops/usage` (`admin.py:27,84-100`) and by the subscription payload `server.py:7973`, which the frontend reads (`frontend/src/pages/SettingsPage.jsx:740`).
   - It also feeds `validate_workspace_builder_sources` (L2053-2077: `domain_policies`, runtime quota overrides) and the worker's `maybe_run_scheduled_scrapeops_maintenance` (L1978, `alert_policy.enabled`, `worker/service.py:437`).
   - **Decision: live customer/runtime ScrapeOps budget policy, not admin-dashboard residue.** Only the *name* ("admin") and the missing write path are residue. No route or code at baseline writes `scrapeops.admin_policy` (`git grep` finds only the reads in `services.py`). The admin editor was removed with the admin surfaces (`dd47acf9`), so the defaults apply unless the value was persisted earlier (UNKNOWN, WS4-G1).
7. **Production rollout**: `ProductionRolloutService` (`production_rollout.py:236`) has `status` L365, `configure` L427, `evidence_report` L466 and `advance` L538, exposed by the facade at `services.py:1068-1102`. `git grep` finds **no route, worker or script caller** outside `services.py`. Only the module functions `catalog_user_access`, `phase_i_config` (imported by `admin.py:4`) and `private_test_deployment_enabled` (used by WS-3 `acquisition_scheduler.py:34,159,181`) are live in code.

## 6. Invariants, failure handling and recovery

- **Catalog cohort gate**: `PermissionError("jobs_catalog_rollout_not_available")` (`personalized_jobs_service.py:855`). `RUNR_PRIVATE_TEST_DEPLOYMENT` forces the cohort gate off, i.e. open access (`production_rollout.py:142-156`).
- **Read-only GETs**: Jobs/Company GETs never enqueue intelligence (`services.py:1304`). The feed limit is clamped to 1–100 (`personalized_jobs_service.py:1303`). Without a store or publication the feed returns an "unavailable" empty feed (`personalized_jobs_service.py:1325`, `1336`).
- **Public payload scrubbing**: `_PUBLIC_INTERNAL_KEYS` (`personalized_jobs_service.py:38`) and `_public_clean`. Company provenance `source` is replaced with "verified source" (L864-869).
- **Customer tasks**: unique `(user_id, idempotency_key)`, bounded attempts (default 3), stale-lease requeue then terminal failure, and lease-fenced completion (`sqlite_personalized_jobs.py:1521-1640`; `docs/RC020_CUSTOMER_TASK_QUEUE.md`). Execution exceptions are stored as `failed` with `retryable=True` (`services.py:1280-1291`).
- **Intelligence queue**: `recover_stale_intelligence` before each claim, and a cache key over user/job version/profile/cv/evidence/evaluator versions plus input hash (`personalized_jobs_service.py:901-906`).
- **Quota**: fails closed if the repository lacks `increment_quota_usage` (`quota.py:109`, `180`). `-1` means unlimited.
- **Assisted Apply**: short TTLs, token prefixes with lookup-prefix hashing, origin allow-pattern, document size and MIME limits, adapter version semver (`assisted_apply_package_service.py:43-68`). The backend accepts outcome evidence only and never submits (see WS-9).
- **ScrapeOps maintenance**: exceptions are caught and emitted as the alert event `reconciliation_cycle_failed` (`services.py:1985-1996`). The worker also logs `worker_scheduled_maintenance_failed` (`worker/service.py:441-444`).
- **Runs**: orphaned running runs are recovered after 600 s (`run_services.py:52`), `WorkerLeaseLostError` (L56), `recover_stale_workers` (L507).

## 7. Relevant tests and safe verification commands

Tests are owned by WS-10 ([test-suite-map.md](../04-testing/test-suite-map.md)). Test files that exist at baseline:

- Application/facade: `tests/test_backend_application.py`
- Personalized jobs: `tests/test_phase_c_personalized_jobs.py`, `tests/test_phase_c_feed_performance_security.py`, `tests/test_phase_d_jobs_cutover.py`, `tests/test_phase_e_personalized_jobs_intelligence.py`, `tests/test_phase_e_job_intelligence_async.py`, `tests/test_personalized_jobs_contracts.py` (WS-5 contract)
- Rollout: `tests/test_phase_i_production_rollout.py`
- Assisted Apply backend: `tests/test_assisted_apply_connection_service.py`, `tests/test_assisted_apply_corrections.py`, `tests/test_assisted_apply_document_grants.py`, `tests/test_assisted_apply_launch_prepare.py`, `tests/test_assisted_apply_package_routes.py`, `tests/test_assisted_apply_telemetry.py`, `tests/test_assisted_apply_tracker_confirmation.py`
- Tracker/networking/capabilities: `tests/test_tracker_gmail_integration.py`, `tests/test_networking_referrals.py`, `tests/test_application_binding.py`, `tests/test_reusable_package_services.py`, `tests/test_scrapeops_integration.py`, `tests/test_title_filter.py`, `tests/test_company_career_discovery.py` (tools)
- Career/documents: see the secondary doc §7

No dedicated test file for `quota.py`, `customer_tasks.py` or `scrapeops_admin_policy` was found by file name (`git ls-tree` over `tests/`). Their coverage, if any, is inside the broader files above (UNKNOWN, WS4-G5).

Safe verification commands (not executed in Phase 2):
```
python -m pytest tests/test_backend_application.py tests/test_phase_c_personalized_jobs.py tests/test_phase_c_feed_performance_security.py tests/test_phase_d_jobs_cutover.py tests/test_phase_e_personalized_jobs_intelligence.py tests/test_phase_e_job_intelligence_async.py tests/test_phase_i_production_rollout.py -q
python -m pytest tests/test_assisted_apply_*.py tests/test_tracker_gmail_integration.py tests/test_networking_referrals.py -q
git grep -n "scrapeops.admin_policy\|SCRAPEOPS_ADMIN_POLICY_CONFIG_KEY" 58a96674 -- backend frontend/src
git grep -n "get_production_rollout_status\|advance_production_rollout" 58a96674 -- backend scripts workspace_runner.py
```

## 8. Historical decisions and supporting commits

From `git log --oneline 58a96674 -- <WS-4 application files, sqlite_personalized_jobs.py>`, selected:

| SHA | Subject | Relevance |
|---|---|---|
| `d44d3c0f` | production: restore canonical publication chain | feed reads the canonical publication |
| `dd47acf9` | Complete acquisition delivery and remove admin surfaces | admin routes removed; `/dashboard` and `analytics/events` bodies left unregistered (N-1) |
| `bdd58615` | feat: add product outcome analytics and wave planning | analytics hooks in services |
| `5b900167` | perf: avoid hydrating run payloads for document lists | equivalent of unmerged `61c3a686` (U5) |
| `530c7942` | Speed up personalized jobs loading | feed performance |
| `42d4603d` | feat: complete Phase D Jobs production cutover | `/jobs` over the published catalog |
| `5a91380e` | reconstruct Phase I offline rollout evidence and disable career discovery API | `production_rollout.py`; `career-url-discovery` disabled |
| `027c976a` / `247c3a4b` | feat: complete phase e job intelligence / add async job intelligence and evidence review | intelligence queue |
| `6d938f1c` | fix: bound personalized jobs feed and public intelligence | clamps and scrubbing |
| `c7bf109b` | feat: deploy jobs catalog and portal rollout | cohort gate |
| `5e674e1e` | fix: migrate Creem billing to Runr Pro | Pro plan id used by rollout checks |
| `92760a3a`, `cc9cf2b8` | LinkedIn connection sync from browser tab; unlimited sync for paid plans | tracker services |
| `664f0810`, `04fa1ba4` | assisted apply package launch lifecycle / complete package filling | package service |
| `ec49b716` | ScrapeOps use AM control mechanisms and endpoint | origin of `scrapeops_admin_policy` |
| `7251ae29` | feat(acquisition): reconcile producers inputs and runtime data | last touch of `customer_tasks.py` |

## 9. Current implementation status

| Capability | Classification |
|---|---|
| Personalized Jobs feed/detail/company/preferences/saved-search/dispositions | VERIFIED (scope: static — 13 routes registered `acquisition_catalog.py:10-22`, handlers call facade → `PersonalizedJobsService` → `SqlitePersonalizedJobsStore.query_published_jobs`; not run, U10 payloads unverified) |
| Catalog cohort gate | VERIFIED (scope: static — `catalog_user_access` called at `personalized_jobs_service.py:854`; effective config values UNKNOWN) |
| Async job intelligence (deterministic) | VERIFIED (scope: static — customer worker `worker/service.py:261` → `process_next_intelligence`) |
| Gemini AI job summaries | IMPLEMENTED-UNVERIFIED (code at `personalized_jobs_intelligence.py:367-397`; provider key not in render.yaml, so enablement is UNKNOWN) |
| Customer task queue (bulk export, email sync) | VERIFIED (scope: static — enqueue in `documents.py:502-527`/`tracker.py:817`, claim in `worker/service.py:277`; async flag in render.yaml L78/L195, value not inspected) |
| Plan quotas | VERIFIED (scope: static — callers in `documents.py:552`, `tracker.py:637`, `workspace.py:418/474/549`, `stage_adapters.py:720`) |
| Tracker/referrals/outreach/LinkedIn sync | VERIFIED (scope: static — `tracker.*` and `assisted_apply.extension.linkedin_connections.sync` routes registered, facade → `TrackerApplicationService`) |
| Live relevant-people discovery (DeepSeek + ScrapeOps) | IMPLEMENTED-UNVERIFIED (gated by `RUNR_ENABLE_LIVE_NETWORKING_DISCOVERY`, `discovery.py:534`) |
| Workspaces/runs/workers/quick-apply | VERIFIED (scope: static — `workspace.*` routes registered, facade → `RunLifecycleService`/`WorkspaceCatalogService`) |
| Career URL discovery API | RETIRED/HISTORICAL (handler raises `PermissionError`, `workspace.py:381-382`; CLI tool remains) |
| ScrapeOps per-user company-site budget and usage | VERIFIED (scope: static — `admin.scrapeops` registered `admin.py:27`, calls `get_scrapeops_user_usage_summary`; policy read `services.py:685-690`) |
| ScrapeOps policy editing | RETIRED/HISTORICAL (no writer of `scrapeops.admin_policy` at baseline; admin surfaces removed `dd47acf9`) |
| ScrapeOps reconciliation/alert maintenance | IMPLEMENTED-UNVERIFIED (acquisition worker `worker/service.py:437`; which host runs an acquisition-role worker is WS-7, C6) |
| Assisted Apply connection/packages/grants/corrections/outcomes (backend) | VERIFIED (scope: static — `assisted_apply.*` routes registered in 5 route modules, handlers call the facade services) |
| Assisted Apply preparations | IMPLEMENTED-UNVERIFIED (routes registered `assisted_apply_preparations.py:19-23`; gated by `RUNR_ENABLE_ASSISTED_APPLY_PREPARATION`, render.yaml L103 value not inspected) |
| Phase I production rollout status/configure/advance | PARTIAL (service exists `production_rollout.py:236-600`; no caller outside `services.py`, so unreachable at runtime; acceptance report says not complete) |
| Customer `/dashboard` analytics payload, `POST /analytics/events` | RETIRED/HISTORICAL (unregistered bodies `admin.py:102`, `admin.py:239`; N-1, WS-1) |
| Unmerged CV editor/perf commits on the feature branch | see §10 (U5); patch-equivalent content already in baseline |

### Deployment evidence (documentary only)

- `docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md` records Render at `5dfdd106`. The baseline is 44 commits later (U1). None of the above is claimed live.
- `docs/reports/phase_i_production_rollout_acceptance_2026-08-07.md`: offline acceptance, "production approval and live evidence are pending".
- `render.yaml` declares `RUNR_CUSTOMER_TASKS_ASYNC`, `RUNR_PRIVATE_TEST_DEPLOYMENT`, `RUNR_ENABLE_ASSISTED_APPLY_PREPARATION`, `RUNR_ENABLE_LIVE_NETWORKING_DISCOVERY` for api/worker. What is actually set on the service is UNKNOWN (U3).

## 10. Confirmed gaps and unresolved questions

| ID | Gap / question | Evidence |
|---|---|---|
| WS4-G1 | `scrapeops.admin_policy` has no writer at baseline. The effective policy is plan defaults unless a value persisted before `dd47acf9`. The "admin" naming is misleading for a live customer policy. Owner: rename/move, or add a non-admin config path? | `services.py:685-690`; `git grep` shows only reads |
| WS4-G2 | `ProductionRolloutService` status/configure/advance/evidence have no reachable caller. Its Phase I stages are driven only by config defaults and `RUNR_PRIVATE_TEST_DEPLOYMENT`. Delete, or re-expose via CLI? | `services.py:1068-1102`; grep in §7 |
| WS4-G3 | `customer_tasks.py` imports private helpers from `backend.api.server` (`_create_bulk_export_bundle`, tracker email helpers), so the worker depends on the API module. | `customer_tasks.py:77, 94, 179` |
| WS4-G4 | `docs/personalized_jobs_contracts.md` header ("not yet persisted") and `docs/PERSONALIZED_JOBS_PREVIEW.md` (dashboard redirect, frontend-only) contradict baseline code. | §2 |
| WS4-G5 | No test file by name for `quota.py`, `customer_tasks.py` or the ScrapeOps policy loader. | `git ls-tree tests/` |
| WS4-G6 | AI summary env keys (`PERSONALIZED_JOBS_SUMMARY_PROVIDER/MODEL`, `GOOGLE_API_KEY`) and `RUNR_CUSTOMER_TASKS_ASYNC` are read in code but absent from `env_schema.py` (48 keys). | §4 table |
| N-1 (link) | Customer `/dashboard` → the frontend redirects to `/jobs`. The backend `_dashboard_payload`/`_dashboard_analytics_payload` (`server.py:7358`, `7143`) are reachable only from the unregistered `admin.py:102` branch. Residue, owned by WS-1/WS-11. | [backend-api.md](../01-architecture/backend-api.md), [retired-features.md](../06-history-and-provenance/retired-features.md) |
| U5 (label only) | `UNMERGED (feature/admin-analytics-final-production @ ce3718b0)`: CV editor/perf commits `1bffdc21`, `85d4ddb2`, `77a19ba9`, `646ef39e`, `5574f396`, `09c24293`, `61c3a686`, `92b575e4`, `06ace3ba` all show as patch-equivalent (`-`) in `git cherry -v 58a96674 ce3718b0`. A two-dot diff of WS-4 paths shows no `cv_editor.py` difference. The remaining owned-path differences are the branch being older (no `customer_tasks.py`) plus `backend/application/admin_job_import.py`, a retired admin feature absent from baseline. Nothing to restore. | `git cherry`, `git diff --stat 58a96674 ce3718b0` |
| U7 / U10 / U11 | Owner decision on dead telemetry; authenticated `/jobs` payloads not visually verified; full backend suite not run. | contradictions-and-unknowns |
| T03 (link) | Unmerged assisted-apply panel / generic ATS planner work in `0d7f2b5c`, reviewed under WS-9. | linear-ticket-candidates |

## Agent context and remaining work

**(a) Agent context packet**
- Required reading: this doc; [career-profiles-and-documents.md](career-profiles-and-documents.md); [backend-api.md](../01-architecture/backend-api.md); [backend-workers-and-orchestration.md](../01-architecture/backend-workers-and-orchestration.md); [schema-and-migrations.md](../03-data/schema-and-migrations.md); [assisted-apply.md](assisted-apply.md); `docs/RC020_CUSTOMER_TASK_QUEUE.md`; `backend/application/services.py:863-930` (composition).
- Allowed paths: the WS-4 owned set in §2. Never the 13 WS-3 application files, `backend/api/**`, `backend/config/**` or `tests/**` without the owner.
- Tests to run: the §7 commands, plus `tests/test_backend_api.py` and `tests/test_customer_route_surface.py` when facade signatures change.
- Prohibited: re-registering `/dashboard` or `analytics/events`; restoring admin surfaces or `admin_job_import.py`; any Assisted Apply submit path; live provider calls (Gemini, DeepSeek, ScrapeOps) in tests; changing `RUNR_MIGRATION_HEAD` (C3, WS-5/WS-7).

**(b) Registry proposal**

| subsystem id | name | owned globs | primary doc | test globs | owner WS |
|---|---|---|---|---|---|
| `app-services` | Personalized jobs and customer application services | `backend/application/{__init__,assisted_apply_*,baseline_cv_replacement_service,contracts,customer_tasks,domain_services,personalized_jobs_*,production_rollout,quota,rebind_service,run_services,services,tracker_services}.py`, `backend/capabilities/**`, `backend/career_memory/**`, `backend/evidence/**`, `backend/evidence_library/**`, `backend/master_cv/**`, `backend/profiles/**`, `backend/work_experience/**`, `backend/tools/**`, `backend/scripts/**`, `backend/repositories/{sqlite_personalized_jobs,assisted_apply_preparation,document_payloads}.py` | `docs/reverse-engineering/05-subsystems/personalized-jobs-and-customer-app-services.md` | `tests/test_backend_application.py`, `tests/test_phase_{c,d,e,i}_*.py`, `tests/test_assisted_apply_*.py`, `tests/test_career_*.py`, `tests/test_evidence*.py`, `tests/test_master_cv.py`, `tests/test_tailored_document_generation.py` | WS-4 |

**(c) Gap/ticket candidates**: WS4-G1 (ScrapeOps policy naming and writer), WS4-G2 (dead rollout service), WS4-G3 (worker→API import inversion), WS4-G4 (stale specs), WS4-G5 (quota/customer-task tests), WS4-G6 (env_schema coverage). No new Linear tickets created.
