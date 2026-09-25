> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Schema and migrations

This is the primary doc of the 03-data doc group (schema, Turso/libSQL connection, object storage). The WS-5 subsystem primary is [domain-model.md](../01-architecture/domain-model.md), which owns the repository/config/domain slices. LIVE PRODUCTION = UNKNOWN: no database was queried, and nothing here says which migrations are applied anywhere.

## 1. Purpose and capabilities

There is one relational schema, and it is shared by local SQLite and remote Turso/libSQL. It is built in two layers:
1. Base DDL, `BASE_SCHEMA_SQL` in `backend/database/schema.py` (all `CREATE … IF NOT EXISTS`).
2. An ordered, checksum-guarded Python migration registry, `MIGRATIONS` at `backend/repositories/sqlite_migrations.py:3235-3570`. It holds 61 entries, `001`–`061`, contiguous. Despite the module name, the same registry serves libSQL.

There is no ORM and no Alembic. See [turso-and-libsql.md](turso-and-libsql.md) for how the connection is chosen and [object-storage-r2.md](object-storage-r2.md) for binary objects, which live outside this schema.

## 2. Owned paths and governing instructions

Schema-slice paths (WS-5):
- `backend/database/schema.py` (209 lines)
- `backend/database/migrations.py` (204)
- `backend/database/initialization.py` (50)
- `backend/database/migrate.py` (49)
- `backend/database/__main__.py` (3)
- `backend/repositories/sqlite_migrations.py` (3,547)

Governing rules:
- Append-only (a checksum mismatch aborts startup).
- The API pre-deploy owns migrations, per `docs/deployment/render.md` L24-25: "Migrations are owned only by the `runr-api` pre-deploy hook; the worker must not run migrations". This was checked against `render.yaml:52`: only the api service has `preDeployCommand`.
- `AGENTS.md` (repo root): all Python via `.venv\Scripts\python.exe`, 3.12.7.

## 3. Entry points

| Path | Code | Notes |
|---|---|---|
| Render pre-deploy | `render.yaml:52` `./deploy/start.sh migrate` → `deploy/start.sh:76-78` (emits release metadata, then `python -m backend.database.migrate`) | WS-7 owns deploy. See [render.md](../02-deployment/render.md). |
| CLI | `backend/database/migrate.py:28-45`: `load_project_dotenv` → `validate_environment` → `initialize_database(force=True)` → print status. `--status` prints only. `--database` default `.backend_data/backend.sqlite3` (untracked local path). | Target is Turso when `TURSO_DATABASE_URL`/`DATABASE_BACKEND=turso`/production is set. |
| Every process start | `backend/bootstrap.py:286` and each `_SqliteStore.__init__` (`backend/repositories/sqlite_core.py:19`) call `initialize_database`, memoized per process | So an API/worker/VPS process **also applies pending migrations** at startup, whatever the "pre-deploy only" doc rule says (WS5-S1). |
| Acquisition reprocessing | `backend/acquisition/reprocessing.py:152` | WS-3 |

Engine (`backend/database/migrations.py`):
- `schema_migrations(migration_id PK, applied_at, checksum)` (L94-107).
- Checksum = SHA-256 of id, description, apply-callable source and declared `dependencies` sources (L34-56).
- `run_migrations` (L165-204) first validates every applied checksum (raises on mismatch, L170-182), back-fills empty legacy checksums (L184-192), then applies pending ones in order inside the caller's `BEGIN IMMEDIATE` transaction (`backend/database/initialization.py:46-48`).
- `get_migration_status` states: `pending`, `applied`, `applied_unverified`, `checksum_mismatch`.

## 4. Inputs, outputs, storage: base schema and the registry

### 4.1 Base schema (`backend/database/schema.py`)

17 tables: `schema_migrations`, `workflow_templates`, `workspaces`, `runs`, `run_job_sets`, `run_blobs`, `artifacts`, `reviews`, `application_status_history`, `users`, `candidate_assets`, `candidate_documents`, `workspace_document_bindings`, `run_document_bindings`, `api_tokens`, `assisted_apply_connections`, `secrets`. There are also 24 indexes (L177-208).

### 4.2 Migration registry 001–061

How the table was built:
- Purpose is the registry description string.
- "Tables" were extracted by static regex over each apply function and the helpers it calls: `CREATE TABLE`, `ALTER TABLE`/`_ensure_*_column`, and index targets. **C** = created, **A** = altered or data-migrated, **I** = index only. This is heuristic and the SQL was not executed.
- "Fn line" is the apply function line in `sqlite_migrations.py`.

| ID | Fn line | Purpose (registry description) | Tables touched |
|---|---|---|---|
| 001_runtime_normalization | 44 | Normalize run runtime fields and create runtime tables | C `run_jobs`, `run_stage_results`, `workers`; A `runs` |
| 002_analytics_events | 199 | Create analytics event storage and indexes | C `analytics_events` |
| 003_application_status_history | 430 | Create application status history storage and indexes | C `application_status_history` |
| 004_runs_user_id | 116 | Add and backfill normalized run user ID | A `runs` |
| 005_billing | 134 | Billing, subscription, quota storage | C `subscriptions`, `subscription_events`, `quota_usage`; A `users` |
| 006_app_config | 226 | Application configuration storage | C `app_config` |
| 007_scrapeops_usage_ledger | 240 | ScrapeOps usage ledger | C `scrapeops_usage_ledger` |
| 008_site_source_policy | 271 | Site source policy storage | C `site_source_policy` |
| 009_site_job_url_history | 290 | Public job URL history | C `site_job_url_history` |
| 010_site_job_url_history_workspace_scope | 320 | Preserve URL history lookup indexes | I `site_job_url_history` |
| 011_site_job_url_history_public_index | 331 | Normalize URL history to a public URL index | C/A `site_job_url_history` (rebuild; drops legacy temp table) |
| 012_creem_billing | 183 | Creem provider identifiers | A `subscriptions`, `subscription_events` |
| 013_candidate_document_normalization | 582 | Move candidate assets/private document text out of aggregate JSON | C `candidate_assets`, `candidate_documents`, `workspace_document_bindings`, `run_document_bindings`; A `users`, `workspaces`, `runs` |
| 014_workspace_ownership | 737 | Workspace ownership + legacy backfill | A `workspaces` |
| 015_email_sync_start_date | 784 | Email sync start date/status/scheduling; remove scan_depth | A `users` |
| 016_assisted_apply_connections | 820 | One-time AA connection + extension sessions | C `assisted_apply_connections` |
| 017_application_packages | 861 | Immutable application packages | C `application_packages` |
| 018_assisted_apply_corrections | 892 | Scoped auditable AA corrections | C `assisted_apply_corrections`, `assisted_apply_correction_audit` |
| 019_assisted_apply_document_grants | 927 | One-time session-bound document grants | C `assisted_apply_document_grants` |
| 020_assisted_apply_tracker_confirmation | 961 | AA outcome events + idempotent tracker records | C `assisted_apply_submission_events`, `assisted_apply_tracker_records` |
| 021_career_profiles | 1048 | Career profile lifecycle | C `career_profiles` |
| 022_career_profiles_workspace_binding | 1069 | Workspace binding column | A `career_profiles` |
| 023_career_profiles_baseline_cv | 1078 | Baseline CV fields | A `career_profiles` |
| 024_evidence_state_tracking | 1214 | Evidence + state history (CP-028) | C `evidence`, `evidence_state_history` |
| 025_work_experiences | 1093 | Work experience + merge suggestions | C `work_experiences`, `work_experience_merge_suggestions` |
| 026_profile_versioning | 1139 | Profile/CV versions + generation provenance (CP-025) | C `profile_versions`, `cv_asset_versions`, `generation_provenance` |
| 027_assisted_apply_preparations | 1005 | Disabled-by-default durable AA preparation + report idempotency | C `assisted_apply_preparations`, `assisted_apply_preparation_reports` |
| 028_assisted_apply_document_grant_intents | 999 | Bind grants to upload field intents | A `assisted_apply_document_grants` |
| 029_phase_a_acquisition | 1254 | System-owned Phase A acquisition, canonical catalog, publication | C `acquisition_cycles`, `acquisition_targets`, `acquisition_tasks`, `acquisition_requests`, `acquisition_target_attempts`, `acquisition_budget_reservations`, `acquisition_publications`, `acquisition_publication_jobs`, `canonical_companies`, `canonical_jobs`, `canonical_job_url_aliases`, `canonical_job_relationships`, `job_posting_versions`, `job_source_observations` |
| 030_phase_a_publication_head | 1515 | Singleton valid-publication head | C `acquisition_publication_head` |
| 031_phase_a_published_jobs | 1528 | Per-target published-job counts | A `acquisition_tasks` |
| 032_phase_a_request_state | 1533 | Write-ahead dispatch / uncertain outcome metadata | A `acquisition_requests` |
| 033_phase_b_catalog | 1546 | Normalization rejection evidence | C `acquisition_job_rejections` |
| 034_phase_c_personalized_jobs | 1636 | User-scoped personalized jobs state | C `personalized_search_preferences`, `personalized_saved_searches`, `personalized_job_evaluations`, `personalized_job_dispositions`, `personalized_job_events` |
| 035_phase_e_job_intelligence | 1706 | Version-keyed job summaries | C `job_description_intelligence` |
| 036_phase_f_company_profiles | 1730 | Company enrichment + logo metadata | C `canonical_company_profiles` |
| 037_phase_g_applicant_competition | 1796 | Applicant competition snapshots | C `job_applicant_snapshots` |
| 038_phase_e_async_intelligence | 1828 | Intelligence cache keys + async precompute | C `job_intelligence_cache`, `job_intelligence_queue` |
| 039_phase_b_catalog_correctness | 1570 | Source-scoped identity, lifecycle, replay, immutable versions | C `canonical_job_external_ids`, `job_source_states`, `job_source_observation_relationships`; A `canonical_jobs`; I `acquisition_job_rejections` |
| 040_phase_f_company_enrichment | 1751 | Idempotent company-target enrichment attempts | C `company_enrichment_targets`, `company_enrichment_attempts` |
| 041_phase_g_applicant_boundary | 1921 | Official-apply/internal-provenance fields | A `job_applicant_snapshots` |
| 042_admin_job_import_dashboard | 1932 | Admin job import, review, publication, audit state | C `admin_job_imports`, `admin_job_review_decisions`, `admin_job_audit_events`; A `acquisition_publications` |
| 043_acquisition_quality_contract | 1987 | Quality, provenance, reconciliation annotations | C `acquisition_quality_events`, `acquisition_version_quality`, `canonical_company_aliases` |
| 044_unified_acquisition_mapping | 2055 | Connector-independent mapping, provenance, duplicates, reprocessing | C `acquisition_stage_results`, `acquisition_rule_outputs`, `acquisition_field_provenance`, `acquisition_completeness_reports`, `acquisition_duplicate_clusters`, `acquisition_duplicate_members`, `acquisition_reprocessing_runs`, `canonical_company_urls`, `company_logo_enrichments` |
| 045_acquisition_reprocessing_leases | 2245 | CAS leases for reprocessing | A `acquisition_reprocessing_runs` |
| 046_acquisition_source_quarantine | 2263 | Fixture/test source quarantine | A `acquisition_targets` |
| 047_product_completion_wave | 2293 | Duplicate decision history + connector capability snapshots | C `acquisition_duplicate_decisions`, `acquisition_connector_capability_snapshots` |
| 048_posting_identity_anchor | 2329 | URL identity + first-observed age anchors | A `canonical_jobs` |
| 049_enrichment_foundation | 2392 | Inactive provider-neutral enrichment evidence/version/cache | C `enrichment_evidence`, `enrichment_version_registry`, `enrichment_cache_entries` |
| 050_collection_controls | 2504 | Retrieval mode, limits, completeness, stop reason | A `acquisition_tasks` |
| 051_enrichment_operations | 2515 | Report-only enrichment plans/runs/proposals/budgets/audit | C `enrichment_operation_plans`, `enrichment_operation_runs`, `enrichment_operation_run_items`, `enrichment_field_proposals`, `enrichment_proposal_actions`, `enrichment_provider_budgets`, `enrichment_operation_audit_events` |
| 052_publication_policy_history | 2712 | Publication origins, versioned preflight, restore audit | C `publication_audit_events`; A `acquisition_publications` |
| 053_acquisition_audit_permissions | 2754 | Granular acquisition permissions + unified audit stream | C `acquisition_audit_events` |
| 054_company_identity_reconciliation | 2883 | Entity kinds, profile status, URL lifecycle, reconciliation state | C `company_identity_keys`, `company_identity_evidence`, `company_link_candidates`, `canonical_company_url_occurrences`; rebuilds `canonical_companies`; A `canonical_company_profiles`, `canonical_company_urls` |
| **055_acquisition_analytics_indexes** | 3104 | Timestamp indexes for read-only acquisition analytics aggregates | I on 19 acquisition/catalog/enrichment tables (e.g. `acquisition_cycles`, `canonical_jobs`, `job_source_observations`, `publication_audit_events`) |
| 056_phase_a_scheduler_fencing | 3151 | Manifest/scope identities, lease tokens, retry checkpoints | A `acquisition_cycles`, `acquisition_tasks` |
| 057_phase_e_intelligence_recovery | 1871 | Bounded leases, claim fencing, stale-work recovery | A `job_intelligence_queue` |
| 058_customer_task_queue | 1886 | User-scoped durable queue for slow customer operations | C `customer_tasks` |
| 059_company_identity_crosswalk | 3183 | Deterministic company identity crosswalks + merge receipts | C `company_identity_crosswalk`, `company_merge_receipts` |
| 060_publication_latest_observation_index | 3172 | Accelerate latest-observation joins for publication gates | I `job_source_observations` |
| 061_acquisition_publisher_checkpoints | 3183 | Own the durable producer-state publisher checkpoint schema (WS-3/WS-5; closes WS3-G9 ad hoc creation) | C `acquisition_publisher_checkpoints` |

History at other SHAs (audit row 13; not re-run): `3c5e609a` = 054, `93099afc`/`ce3718b0` = 055, `848408f3` = 058. The last two entries were added by `d44d3c0f` (059, 2026-09-11) and `c964b208` (060, 2026-09-12).

## 5. Call and data flows

### 5.1 Deploy-time migration (intended owner)
`render.yaml:52` (`preDeployCommand: ./deploy/start.sh migrate`, api service only) → `deploy/start.sh:76-78` emits release metadata then runs `python -m backend.database.migrate` → `migrate.py:28-45`: `load_project_dotenv()` (`backend/config/job_seeker.py:260`) → `validate_environment()` (`backend/config/env_schema.py:438`) → `initialize_database(path, force=True)` → prints `migration_id\tstate\tdescription`. `force=True` bypasses the memo so the pre-deploy run always checks the registry. WS-7 owns both invoking files.

### 5.2 Startup migration (what actually happens)
Process start → `backend/bootstrap.py:286` (or any `_SqliteStore.__init__`, `backend/repositories/sqlite_core.py:19`) → `initialize_database` (`backend/database/initialization.py:29-50`):
1. Memo check per target identity — `"remote"` for Turso, otherwise the file's `st_dev:st_ino` (L22-26).
2. `database_session` opens `BEGIN IMMEDIATE` (`initialization.py:46-48`).
3. `executescript(BASE_SCHEMA_SQL)` creates the 17 base tables if absent.
4. `run_migrations(connection, MIGRATIONS)` (`migrations.py:165-204`): validate applied checksums (raise on mismatch) → back-fill empty legacy checksums → apply pending in registry order, each recording id + checksum into `schema_migrations`.
5. Commit; any failure rolls back the whole batch (`connection.py:564-589`, see [turso-and-libsql.md](turso-and-libsql.md)).

So the first process of any role to reach a stale database migrates it, including the shared remote Turso database (WS5-S1).

### 5.3 Store reads/writes after migration
Repository method → `_SqliteStore._connect()` → one `database_session` per call, commit on exit (`sqlite_core.py:22-28`); bounded batches share one connection via `transaction_scope` (L29-68). The store-to-table mapping is in [domain-model.md §4.1](../01-architecture/domain-model.md#41-repository-layer-and-backend-selection).

### 5.4 Acquisition reprocessing
`backend/acquisition/reprocessing.py:152` → `initialize_database` (WS-3 path; the same engine and registry).

### 5.5 Release metadata (no gate)
`backend/deployment/release_contract.py:135-137` reads `RUNR_MIGRATION_HEAD` (default `DEFAULT_MIGRATION_HEAD = "058_customer_task_queue"`, L14) into release metadata only. Nothing compares it with `MIGRATIONS[-1]` (C3).

### 5.6 Analytics writes into migration-002 storage
Worker `backend/adapters/stage_adapters.py:141-165`/`:744` → `SqliteAnalyticsStore.emit_event` (`backend/repositories/sqlite_backed.py:2334`, insert L2353) → `analytics_events`. Readers: `backend/application/services.py:1513`, `:1748`; `backend/profiles/cv_upload_jobs.py:285`. HTTP ingestion is unregistered (U7).

## 6. Invariants, failure handling and recovery

- **055 is retained, append-only residue.** It was added by `12f342fb` ("feat: add read-only acquisition analytics dashboard", 2026-08-12). The admin analytics consumers were removed in `dd47acf9`, merged by `550ee00a` (RETIRED feature; see [retired-features.md](../06-history-and-provenance/retired-features.md), WS-11). The migration must stay in the registry: deleting or editing it changes nothing in migrated databases and breaks registry continuity. Removing its indexes would need a new `061_*` migration and an owner decision. Its indexes cost write amplification on high-volume acquisition tables; the size of that cost is UNKNOWN.
- **042 `admin_job_*` tables** are admin-import state from the same era. They are still in the schema and must not be removed; whether the WS-3 code still uses them was not traced here.
- **`analytics_events` (002) is still written.** Writers and readers as in section 5.6. The HTTP ingestion endpoint is unregistered (audit N-1; U7).
- **C3: release head 058 vs registry head 061.**
  - `render.yaml:76-77` (api) and `:193-194` (worker) set `RUNR_MIGRATION_HEAD=058_customer_task_queue`.
  - `backend/deployment/release_contract.py:14` defaults `DEFAULT_MIGRATION_HEAD = "058_customer_task_queue"` and reads it only into release metadata (`:135-137`).
  - `git grep "MIGRATION_HEAD\|migration_head"` over `backend tests deploy scripts .github` finds no comparison with `MIGRATIONS[-1]` or with applied rows. **There is no gate.** The metadata under-reports the schema by three migrations (059 `company_identity_crosswalk`, 060 `publication_latest_observation_index`, 061 `acquisition_publisher_checkpoints`).
  - The 058 value came from `39d15b8f` ("RC-022 separate release and runtime contracts", 2026-09-08) and was not bumped by `d44d3c0f`/`c964b208`.
  - T30 (RUN-29) recorded the owner decision: direct release metadata must derive its default migration head from `current_migration_head()` instead of the stale 058 fallback. Note: at the T31 base revision `539c6e2a` that derivation fix is not yet present on `predeployment/render-turso-r2` (the tested T30 commit `2db8997b` is not an ancestor of the recorded integration revision `5d68ae93`); the registry tail at that revision is 061.
  - 061 (`acquisition_publisher_checkpoints`) was appended by T31 as an add-only `CREATE TABLE IF NOT EXISTS`, so both fresh databases and databases that already carry the publisher's former ad hoc table stay checksum-safe.
- **Checksum hazard.** Declared dependencies (for example `_table_columns`, `_ensure_table_column`, and `prepare_user_payload` from WS-4's `backend/repositories/document_payloads.py`, used by 013) are part of the checksum. Refactoring those helpers breaks startup on every migrated database. Past fixes: `81140897`, `6fd91cb2`.
- **Startup migration vs pre-deploy ownership (WS5-S1).** Any process that constructs repositories applies pending migrations. The doc rule "worker must not run migrations" is therefore not enforced in code. A worker that deploys before the API migrates would itself migrate Turso under `BEGIN IMMEDIATE`.
- **Registry integrity checks** (`migrations.py:69-76`): ids unique and sorted; every migration needs a checksum. Recovery: checksum mismatch aborts startup (no auto-repair); legacy rows without checksums are back-filled to `applied_unverified` rather than failing.

## 7. Tests and safe verification (not executed in Phase 2)

- `tests/test_database_migrations.py`: 9 tests (6 pre-T31 plus publisher-checkpoint fresh-database, upgrade-path, and pre-existing-ad-hoc-table coverage added by T31). Ids frozen for 001–020 only (L138); gap WS5-G1.
- `tests/test_sqlite_repositories.py:565`: run user-id backfill.
- `tests/test_database_connection.py`: transaction/rollback semantics.

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_database_migrations.py tests/test_sqlite_repositories.py
$env:RUNR_ENV='test'; .venv\Scripts\python.exe -m backend.database.migrate --status --database <scratch>\backend.sqlite3
```
Safe verification commands, not executed in Phase 2. The migrate command must never run against production credentials. Static check that was run: `git show 58a96674:backend/repositories/sqlite_migrations.py | grep -oE '"[0-9]{3}_[a-z0-9_]+"' | sort -u | wc -l` → 60.

## 8. Historical decisions and supporting commits

`git log --oneline 58a96674 -- backend/database/` (full list, 9 commits) and the registry-relevant slice of `backend/repositories/sqlite_migrations.py`:

| Commit | Date | Subject | Decision |
|---|---|---|---|
| `bbb958b8` | 2026-04-18 | (initial large import) | first `sqlite_backed.py` stores |
| `c7bf7cbd` | 2026-06-18 | deoployment prep initial setup | `backend/database/` package: migration engine, `migrate` CLI, base schema |
| `386ea700` | 2026-07-02 | Turso fix | libSQL migration compatibility hardening |
| `81140897` | — | preserve production migration checksum | checksum covers dependencies (invariant fix) |
| `6fd91cb2` | — | preserve applied enrichment migration checksum | same invariant after 049/051 |
| `12f342fb` | 2026-08-12 | feat: add read-only acquisition analytics dashboard | added migration 055 |
| `dd47acf9` (merged `550ee00a`) | 2026-09 | admin retirement | removed 055's consumers; migration kept append-only (C7(c)) |
| `39d15b8f` | 2026-09-08 | RC-022 separate release and runtime contracts | `RUNR_MIGRATION_HEAD=058` frozen in `render.yaml` (C3) |
| `7251ae29` | 2026-09-08 | feat(acquisition): reconcile producers inputs and runtime data | 058 registry wording |
| `d44d3c0f` | 2026-09-11 | production: restore canonical publication chain | migration 059 |
| `c964b208` | 2026-09-12 | speed up publication latest observation reads | migration 060 (registry head; head metadata not bumped) |

## 9. Current implementation status

| Capability | Classification |
|---|---|
| Base schema + registry 001–061 | VERIFIED (scope: static AST enumeration of `MIGRATIONS`; ids contiguous and sorted; tail `061_acquisition_publisher_checkpoints` read at `sqlite_migrations.py:3565-3569`, appended by T31) |
| Checksum guard | VERIFIED (scope: static read of `migrations.py:165-204`) |
| Pre-deploy migration on Render api | IMPLEMENTED-UNVERIFIED (config `render.yaml:52`; no deploy observed) |
| Migration-head release gate | UNKNOWN (absent in code; no plan cited) |
| 055 analytics indexes | RETIRED/HISTORICAL consumer; migration retained |
| Startup auto-migration from any role | VERIFIED (scope: static — `sqlite_core.py:19` and `bootstrap.py:286` call `initialize_database`; runs migrations) |

### Deployment evidence (documentary only)

`docs/deployment/render.md` L172-192 describe backup-then-migrate and `./deploy/start.sh migrate --status`. Which migrations are applied in the shared Turso database is UNKNOWN; no deploy, migration or database query was performed in Phase 2.

## 10. Confirmed gaps and unresolved questions

| ID | Item |
|---|---|
| C3 | `RUNR_MIGRATION_HEAD`/`DEFAULT_MIGRATION_HEAD` = 058 vs registry head 060; metadata only, no gate (section 6). Owner decision with WS-7. |
| C7(c) | Fate of `055_acquisition_analytics_indexes` and its 19 timestamp indexes under the owner decision; removal needs a new `061_*` migration (append-only rule). |
| U7 | Fate of `analytics_events` (002) under the owner decision: HTTP ingestion dead, worker writes live, three readers remain (section 5.6). |
| WS5-G1 | `tests/test_database_migrations.py:138` freezes ids 001–020 only; 021–060 unprotected. |
| WS5-S1 | Startup auto-migration contradicts "api pre-deploy only" rule (`docs/deployment/render.md` L24-25); unenforced in code. |
| WS5-G5 | No test runs the engine against a real Turso instance (offline by design); libSQL DDL compatibility asserted via fakes. |

## Agent context and remaining work

**(a) Agent context packet**
- Required reading: this doc; [domain-model.md](../01-architecture/domain-model.md) (subsystem primary); `backend/database/migrations.py`; the `MIGRATIONS` tuple at `backend/repositories/sqlite_migrations.py:3217`; `backend/database/initialization.py`; `backend/database/migrate.py`; `docs/deployment/render.md` L21-25, L172-192; `AGENTS.md`.
- Allowed paths: `backend/database/**` (7 files), `backend/repositories/sqlite_migrations.py`; new migrations append here.
- Tests to run: `.venv\Scripts\python.exe -m pytest -q tests/test_database_migrations.py tests/test_database_connection.py tests/test_sqlite_repositories.py` (safe verification commands, not executed in Phase 2).
- Prohibited: editing or reordering any existing migration or its declared dependency functions (checksum break — new schema only as a new `061_*` entry appended); deleting migration 055; running `migrate` against production credentials or any shared database; running migrations during documentation work; copying env values or secrets.

**(b) Registry proposal** (slice row; the WS-5 subsystem row is in [domain-model.md §Agent context](../01-architecture/domain-model.md#agent-context-and-remaining-work))

| id | name | owned globs | primary doc | test globs | owner |
|---|---|---|---|---|---|
| `data-schema-migrations` | Relational schema and migrations | `backend/database/**`, `backend/repositories/sqlite_migrations.py` | `docs/reverse-engineering/03-data/schema-and-migrations.md` | `tests/test_database_migrations.py`, `tests/test_database_connection.py` | WS-5 |

**(c) Gap and ticket candidates**
1. Bump or derive `RUNR_MIGRATION_HEAD` from `MIGRATIONS[-1]` and add a head check to the release contract or CI (C3; with WS-7).
2. Extend the frozen-id migration test to 001–060 (WS5-G1).
3. Owner decision on U7/C7(c): remove the dead ingestion handler and frontend emitter, and decide whether 055's indexes should be dropped via a new `061_*` migration.
4. Decide whether non-api roles should call `initialize_database` with migrations disabled (WS5-S1).
