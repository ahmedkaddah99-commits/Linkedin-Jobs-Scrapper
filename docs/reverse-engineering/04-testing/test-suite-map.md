> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Backend test suite map (WS-10)

Primary doc for subsystem **WS-10 Backend test suite**. Frontend and extension tests are out of scope: see §7.5.

## 1. Purpose and user-facing capabilities

The suite is the offline, deterministic pytest regression suite for the Python backend (`backend/**`), the acquisition scripts (`scripts/**`), the deploy/VPS contract files and the CLI (`workspace_runner.py`). It has no end-user capability. What it provides to maintainers:

| Capability | Where |
|---|---|
| Fast curated backend gate (7 files + `-k` subset of the API test) | `.github/workflows/ci.yml` job `backend` L18–51; root `package.json` `check:backend` L5 |
| Full backend suite in two shards (`api`, `non-api`) | `.github/workflows/ci.yml` job `backend-full` L53–88; `package.json` `check:backend:full` L7 |
| Safe-by-default test environment (SQLite, local storage, no live acquisition network, blank provider keys) | `tests/conftest.py` L10–30 |
| Guard against accidental outbound HTTP through `requests` | `tests/conftest.py` L63–75 `_forbid_non_loopback_http` |
| Fail-closed test backend factory | `backend/testing/bootstrap.py` L12–43 `create_test_backend` |
| Regression guard for the retired admin surfaces | `tests/test_customer_route_surface.py` L4–13 (§7.3) |

Nothing here verifies production. A passing test proves code behaviour under fixtures only.

## 2. Owned paths and governing instructions

| Path | Files | Notes |
|---|---|---|
| `tests/test_*.py` (top level) | 147 | the suite; all collected by `testpaths` |
| `tests/conftest.py` | 1 | autouse fixtures and env |
| `tests/fixtures/**` | 33 | 31 top-level data files and one seed script, plus `tests/fixtures/rc002/` (9) and `tests/fixtures/employer_coverage/` (1); both subdirectories are included in the 33 |
| **`tests/**` total** | **181** | `git ls-tree -r --name-only 58a96674 tests \| wc -l` |
| `backend/testing/__init__.py`, `backend/testing/bootstrap.py` | 2 | test-only bootstrap helper |

No `tests/__init__.py` exists. Suite totals: 1,745 static `def test_*` functions (§7 method).

Governing instructions and config. WS-10 only cites these; the owner is shown per row.

| Source | Relevant content | Owner |
|---|---|---|
| `AGENTS.md` L13, L25 | verify the interpreter before running tests; run tests with `.venv\Scripts\python.exe -m pytest` | WS-11 |
| `pyproject.toml` L1–7 | `[tool.pytest.ini_options]` `testpaths=["tests"]`, markers `slow` / `external`, `addopts="-ra"` | WS-7 |
| `pyproject.toml` L9–28 | ruff `target-version=py311`, `select=["E9","F63","F7","F82"]` (syntax/undefined-name class only) | WS-7 |
| `.github/workflows/ci.yml` | CI jobs (§3) | WS-7, [../02-deployment/ci-cd.md](../02-deployment/ci-cd.md) |
| `package.json` L4–10 | `check`, `check:backend`, `check:backend:api`, `check:backend:full`; `scripts/run-python.cjs` interpreter launcher | WS-7 |

## 3. Entry points and registered commands

| Command / job | Exact selection | Source |
|---|---|---|
| CI `backend` → "Lint backend" | `python -m ruff check backend tests workspace_runner.py` | `ci.yml` L34–35 |
| CI `backend` → "Run backend checks" | `pytest -q` on `test_backend_application`, `test_sqlite_repositories`, `test_worker_service`, `test_phase0_contracts`, `test_job_dedupe`, `test_assisted_apply_connection_service`, `test_env_config` | `ci.yml` L37–46 |
| CI `backend` → "Assisted Apply API boundary checks" | `pytest -q tests/test_backend_api.py -k "assisted_apply or extension_cors or extension_origin or clerk_only_identity"` | `ci.yml` L48–51 |
| CI `backend-full` shard `api` | `pytest -q tests/test_backend_api.py` | `ci.yml` L60–61, L84 |
| CI `backend-full` shard `non-api` | `find tests -maxdepth 1 -name 'test_*.py' ! -name 'test_backend_api.py'` → 146 files, `fail-fast: false` | `ci.yml` L57, L62–63, L80–82 |
| CI `backend-full` → "Lint backend shard" | `python -m ruff check backend tests` (runs after the tests) | `ci.yml` L87–88 |
| `npm run check:backend` | same ruff + same 7 files + same `-k` API subset as CI `backend` | `package.json` L5 |
| `npm run check:backend:api` | `pytest -q tests/test_backend_api.py` | `package.json` L6 |
| `npm run check:backend:full` | bare `pytest` → `testpaths` → all 147 files | `package.json` L7 |
| `npm run check` | `check:backend` + `check:frontend` + `check:extension` (does **not** include `check:backend:full`) | `package.json` L4 |

Triggers: every `pull_request`, and pushes to `main` and `deployment/render-turso-r2` (`ci.yml` L3–8). CI runs Python 3.12 with `requirements-linux.txt` + `pytest>=9,<10` + `ruff>=0.8,<1.0` (L24–32). The `docker` job `needs` only `backend`, `frontend`, `assisted-apply-extension` and `assisted-apply-extension-edge` (L181–185), **not** `backend-full`. The shard-split union covers every top-level test file exactly once.

## 4. Inputs, outputs, storage and dependencies

- **Inputs:** the 33 files under `tests/fixtures/` (§7.1 support table); `tmp_path` / `tempfile` directories; the env forced by `tests/conftest.py`.
- **Code under test:** `backend.*` modules owned by WS-1…WS-7 ([../01-architecture/backend-api.md](../01-architecture/backend-api.md), [../01-architecture/backend-workers-and-orchestration.md](../01-architecture/backend-workers-and-orchestration.md), [../05-subsystems/acquisition-and-collectors.md](../05-subsystems/acquisition-and-collectors.md), [../05-subsystems/publication-and-catalog.md](../05-subsystems/publication-and-catalog.md), [../05-subsystems/personalized-jobs-and-customer-app-services.md](../05-subsystems/personalized-jobs-and-customer-app-services.md), [../01-architecture/domain-model.md](../01-architecture/domain-model.md), [../01-architecture/security-and-auth.md](../01-architecture/security-and-auth.md), [../02-deployment/ci-cd.md](../02-deployment/ci-cd.md)).
  - **`scripts/` imports:** 28 test files import WS-3 `scripts/` modules as the `scripts.*` package; `test_company_website_consensus.py` and `test_known_company_websites.py` insert `scripts/` on `sys.path`.
  - **`tests.*` cross-imports:** `test_phase_a_rc019.py` and `test_phase_e_personalized_jobs_intelligence.py` import `_seed_catalog` from `tests.test_phase_c_personalized_jobs`. Those tests break if that file is renamed.
  - **Import resolution** of `scripts.*` and `tests.*` depends on the repository root being on `sys.path`. Every documented command uses `python -m pytest` from the root, which provides that (inference; not executed).
- **Storage:** SQLite files and local object storage under temp dirs only. No Turso: `TURSO_DATABASE_URL` is blank, and `create_test_backend` rejects a non-blank one. No R2/S3: the S3 keys are blank.
- **Outputs:** pytest exit status and the `-ra` summary. No artefacts are committed. CI uploads nothing for backend jobs.
- **External dependencies:** `pytest`, `requests` (patched), and `requirements-linux.txt` packages. No network by design (§6).

## 5. Important call and data flows

1. **Env first.** pytest imports `tests/conftest.py` before any test module. The module-level loop at L29–30 writes `_SAFE_TEST_ENV` (L10–26) into `os.environ`, so `backend.config` reads test values on first import:
   - `RUNR_ENV=test`, `RUNR_TEST_MODE=1`
   - `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED=false` (L13)
   - `DATABASE_BACKEND=sqlite`, `OBJECT_STORAGE_BACKEND=local`, `RUNR_DISABLE_QUOTAS=1`
   - blank `TURSO_*`, `DEEPSEEK/GEMINI/GOOGLE_API_KEY`, `S3_*`
2. **Per-test isolation.** The autouse fixture `_reset_career_profile_memory_stores` (L38–60) calls the four `_reset_*` hooks in `backend.capabilities.{career_profile_evidence,evidence_recommendation,source_text_review,cv_bullet_suggestions}` before and after each test.
3. **Network guard.** The autouse fixture `_forbid_non_loopback_http` (L63–75) monkeypatches `requests.sessions.Session.request`. Any host other than `localhost`, `localhost.localdomain`, `127.0.0.1` or `::1` raises `AssertionError("unmocked non-loopback HTTP request blocked: …")`.
4. **Backend construction.** Most stateful tests call `backend.bootstrap.create_backend` directly (`from backend import create_backend` or `from backend.bootstrap import create_backend`); see `git grep -l create_backend 58a96674 -- tests`. Only `tests/test_phase_a_rc016.py` and `tests/test_phase_a_remediation.py` use `backend.testing.create_test_backend`. That helper:
   - raises `RuntimeError` if `DATABASE_BACKEND` is not SQLite, `TURSO_DATABASE_URL` is set, `RUNR_ENV` is prod, or live network is truthy (L15–27)
   - pins the safe env, using single-space values so dotenv cannot refill them (L28–40)
   - then calls `create_backend(base_dir, storage_backend="sqlite", test_mode=True)` (L41–43)
5. **Route-surface guard.** `backend.api.routes.build_route_registry()` → `registry._routes` names → prefix assertions (§7.3).
6. **Script tests.** These import collector and publisher functions from `scripts/*` and monkeypatch fetchers. Examples: `tests/test_employer_bounded_cycles.py` L49–50 patch `scripts.master_employer_jobs_catalog.requests_fetcher` / `collect_company`. Deploy-contract tests read files under `deploy/` as text (`tests/test_rc023_vps_runtime.py`, `tests/test_production_completion_regressions.py`).

## 6. Invariants, failure handling and recovery

| Invariant | Enforcement | Limits (static observation) |
|---|---|---|
| Tests never enable live acquisition network | `tests/conftest.py` L13; `backend/testing/bootstrap.py` L21–27 | Only 2 test files use the fail-closed helper; the rest rely on conftest env |
| No unmocked outbound HTTP | `_forbid_non_loopback_http` | Patches `requests` only. Other transports (`urllib`, raw sockets, browser automation, other HTTP clients) are not intercepted (WS10-G2) |
| No remote DB / object storage / AI provider | blank `TURSO_*`, `S3_*`, AI keys in conftest | A developer `.env` could still be loaded by code paths that bypass conftest ordering; the helper's single-space values (bootstrap L28–39) exist for this reason |
| No cross-test leakage of process-global career stores | autouse reset fixture (CP-030, `c06b727e`) | Only the 4 named stores |
| Retired admin routes stay unregistered | `tests/test_customer_route_surface.py` | Runs only in `backend-full` / `check:backend:full`, not in the curated gate (WS10-G3) |
| `slow` / `external` markers separate expensive or credentialed tests | declared in `pyproject.toml` L3–6 | **Unused**: `git grep "pytest.mark.(slow\|external\|skip\|skipif\|xfail)" 58a96674 -- tests` → 0 hits. No deselection happens by default (WS10-G4) |

Failure handling: `backend-full` uses `fail-fast: false` (L57), so both shards always report. There is no retry or quarantine mechanism, and no coverage threshold. Recovery is not applicable: tests write only to temp dirs.

## 7. Relevant tests and safe verification commands

### 7.1 Full test-to-subsystem map at baseline

**Method (read-only, reproducible).** A throwaway Python script (kept outside the repo) did the following:

1. Listed `git ls-tree -r --name-only 58a96674 tests` and read every `.py` blob with `git show 58a96674:<path>`.
2. Parsed each blob with `ast.parse` only; no module was imported and no test was executed.
3. Collected from each file:
   - every `import backend.*`, `from backend[.x] import …` and `from backend import create_backend`
   - `scripts.*` imports, plus bare imports when the file inserts `scripts/` on `sys.path`
   - `tests.*` cross-imports
   - string references to `deploy/…`, `render.yaml`, `Dockerfile`, `ci.yml` and `workspace_runner`
4. Mapped each module to a workstream using `evidence-package-2026-09-13/subsystem-allocation.md`, including its per-file splits of `backend/application` and `backend/repositories`:
   - `scripts/` → WS-3
   - deploy files → WS-7
   - `workspace_runner` → WS-1
   - `backend.bootstrap` / `create_backend` / `backend.testing` are harness imports and are not counted

**Owner basis column:**
- **K**: named as a key test, or matching a key-test glob (`test_employer_*`, `test_linkedin_pipeline_*`, `test_phase_a_*`, `test_rc0NN_*`, `test_phase_c_*`, `test_phase_e_*`, `test_career_*`, `test_evidence*`, `test_assisted_apply_*`), in the allocation. Exact names win over globs.
- **J**: WS-10 judgement, where `api.routes`/`domain` imports are only a harness for the capability under test.
- **I**: majority of imported modules, with WS-5 `domain` types de-prioritised as shared models.

**Other columns:**
- **Tests** = static count of `def test_*` lines. This is not the collected pytest item count: parametrize and `subTest` are not expanded, and `tests/test_application_policy.py` generates its tests dynamically from `tests/fixtures/policy_fixtures.json`, so it shows 0.
- **Imports** are shortened to `pkg.module` below `backend.`.
- **CI shard:**
  - `full:api` / `full:non-api` = `ci.yml` `backend-full` matrix; every file is in exactly one.
  - `backend` = curated step `ci.yml` L37–46.
  - `backend(-k)` = L48–51.
  - `check:backend` = `package.json` L5.
  - Every test file is also run by `check:backend:full`.
- **Markers:** none (0 files use `slow`/`external`/`skip`/`xfail`). The Style column records `unittest.TestCase`, `parametrize` and `subTest` use instead.
- **Δ** = `git diff --name-status 848408f3 58a96674 -- tests` (A added, M modified).

<!-- TABLE -->
| Subject workstream | Test files | `def test_*` (static) | In curated `backend` / `check:backend` |
|---|---|---|---|
| WS-1 HTTP API and CLI | 4 | 133 | 1 |
| WS-2 Worker and orchestration | 2 | 43 | 1 |
| WS-3 Acquisition, collectors, publication, enrichment | 73 | 636 | 0 |
| WS-4 Application services and customer capabilities | 49 | 790 | 2 |
| WS-5 Data, storage, config, domain | 10 | 91 | 4 |
| WS-6 Integrations and security | 5 | 26 | 0 |
| WS-7 Deployment, release and CI | 4 | 26 | 0 |
| **Total** | **147** | **1745** | **8** |

#### WS-1 HTTP API and CLI (4)

| Test file | Tests | Basis | Primary imports (backend.* / scripts.*) | Other WS touched | CI shard | Style | Δ since 848408f3 |
|---|---|---|---|---|---|---|---|
| `tests/test_backend_api.py` | 119 | K | api.routes, api.server, application.assisted_apply_service, capabilities.networking, capabilities.tracker, create_backend, domain.models, orchestration, profiles.cv_profile_extraction, profiles.document_text | WS-2,WS-4,WS-5 | full:api; backend(-k); check:backend(-k) | unittest+subTest | M |
| `tests/test_bounded_loading.py` | 9 | I | api.server | — | full:non-api | unittest | — |
| `tests/test_customer_route_surface.py` | 1 | K | api.routes | — | full:non-api | pytest | A |
| `tests/test_workspace_runner.py` | 4 | K | — | — | full:non-api | unittest | — |

#### WS-2 Worker and orchestration (2)

| Test file | Tests | Basis | Primary imports (backend.* / scripts.*) | Other WS touched | CI shard | Style | Δ since 848408f3 |
|---|---|---|---|---|---|---|---|
| `tests/test_stage_adapters.py` | 14 | K | adapters.stage_adapters, connectors.company_career_sites, domain.models, storage | WS-3,WS-5 | full:non-api | unittest | — |
| `tests/test_worker_service.py` | 29 | K | application.run_services, create_backend, domain.models, orchestration, worker | WS-4,WS-5 | full:non-api; backend; check:backend | unittest+subTest | — |

#### WS-3 Acquisition, collectors, publication, enrichment (73)

| Test file | Tests | Basis | Primary imports (backend.* / scripts.*) | Other WS touched | CI shard | Style | Δ since 848408f3 |
|---|---|---|---|---|---|---|---|
| `tests/test_acquisition_audit_permissions.py` | 6 | I | acquisition.audit, acquisition.permissions, database.initialization, domain.models, repositories.sqlite_acquisition_audit, security.auth | WS-5,WS-6 | full:non-api | unittest | M |
| `tests/test_acquisition_baseline.py` | 3 | I | scripts: benchmark_acquisition_baseline | — | full:non-api | pytest | — |
| `tests/test_acquisition_mapping_contract.py` | 10 | I | acquisition.quality, acquisition.unified_mapping, capabilities.tailored_documents, connectors.ats_router | WS-4 | full:non-api | unittest+subTest | — |
| `tests/test_acquisition_quality.py` | 12 | I | acquisition.quality, acquisition.repair, application.personalized_jobs_intelligence, create_backend | WS-4 | full:non-api | unittest | — |
| `tests/test_ats_expansions.py` | 9 | I | connectors.ats_expansions | — | full:non-api | unittest+subTest | — |
| `tests/test_ats_router.py` | 5 | I | connectors.ats_router, connectors.company_career_sites | — | full:non-api | unittest+subTest | — |
| `tests/test_collection_controls.py` | 4 | I | acquisition.collection_controls, acquisition.manifest, bootstrap, connectors.ats_router | — | full:non-api | unittest | M |
| `tests/test_company_career_discovery.py` | 29 | I | adapters.stage_adapters, connectors.company_career_discovery, connectors.company_career_sites, domain.models, tools.discover_company_careers | WS-2,WS-4,WS-5 | full:non-api | unittest | — |
| `tests/test_company_csv_consolidation.py` | 4 | I | scripts: clean_master_company_url | — | full:non-api | pytest | — |
| `tests/test_company_id_backfill.py` | 7 | I | application.company_id_backfill | — | full:non-api | unittest | — |
| `tests/test_company_identity_canonicalization.py` | 5 | K | application.company_identity_canonicalization | — | full:non-api | pytest | A |
| `tests/test_company_identity_reconciliation.py` | 11 | J | application.company_reconciliation, bootstrap, domain.company_identity, domain.models | WS-5 | full:non-api | unittest | M |
| `tests/test_company_operations.py` | 9 | I | application.company_logo_adapter, application.company_operations | — | full:non-api | unittest | — |
| `tests/test_company_registry_reconciliation.py` | 11 | I | application.company_registry_reconciliation | — | full:non-api | unittest | — |
| `tests/test_company_website_consensus.py` | 12 | I | scripts: discover_websites_consensus, discover_websites_from_web_search | — | full:non-api | pytest | — |
| `tests/test_deterministic_enrichment_evaluation.py` | 8 | I | enrichment.evaluation, enrichment.fixture | — | full:non-api | unittest | — |
| `tests/test_duplicate_decisions.py` | 7 | I | application.duplicate_decisions | — | full:non-api | unittest | — |
| `tests/test_employer_bounded_cycles.py` | 3 | K | scripts: master_employer_jobs_catalog | — | full:non-api | pytest | A |
| `tests/test_employer_coverage_evidence.py` | 12 | K | acquisition.employer_coverage | — | full:non-api | pytest | A |
| `tests/test_employer_coverage_receipts.py` | 13 | K | acquisition.employer_coverage; scripts: audit_employer_coverage, master_employer_jobs_catalog | — | full:non-api | pytest | A |
| `tests/test_employer_site_fallbacks.py` | 10 | K | connectors.employer_site_fallbacks | — | full:non-api | pytest | — |
| `tests/test_employer_traversal.py` | 6 | K | connectors.ats_router; scripts: master_employer_jobs_catalog | — | full:non-api | pytest | A |
| `tests/test_enrichment_foundation.py` | 20 | I | acquisition.unified_mapping, database.connection, database.initialization, database.migrations, database.schema, enrichment.activation, enrichment.boundaries, enrichment.cache, enrichment.contracts, enrichment.fixture, enrichment.persistence, enrichment.providers, repositories.sqlite_migrations | WS-5 | full:non-api | unittest | — |
| `tests/test_generic_jsonld.py` | 1 | I | connectors.generic_jsonld | — | full:non-api | unittest | — |
| `tests/test_import_linkedin_company_logos.py` | 3 | K | scripts: import_linkedin_company_logos | — | full:non-api | pytest | A |
| `tests/test_job_board_connectors.py` | 4 | I | capabilities.reusable_packages, connectors.job_boards, repositories.sqlite_backed | WS-4,WS-5 | full:non-api | unittest+subTest | — |
| `tests/test_job_completeness_audit.py` | 4 | I | scripts: audit_job_publication_completeness | — | full:non-api | pytest | A |
| `tests/test_job_publication_completeness.py` | 43 | K | acquisition.job_publication_completeness | — | full:non-api | pytest | A |
| `tests/test_job_source_merging.py` | 7 | K | acquisition.job_source_merging | — | full:non-api | pytest | A |
| `tests/test_known_company_websites.py` | 1 | I | scripts: apply_known_company_websites | — | full:non-api | pytest | — |
| `tests/test_linkedin_company_enrichment_pipeline.py` | 22 | I | scripts: linkedin_company_enrichment_pipeline | — | full:non-api | unittest | — |
| `tests/test_linkedin_company_id_browser_resolution.py` | 5 | I | scripts: run_linkedin_company_id_resolution | — | full:non-api | pytest | — |
| `tests/test_linkedin_pipeline_performance.py` | 6 | K | scripts: master_linkedin_jobs_catalog | — | full:non-api | pytest | A |
| `tests/test_linkedin_pipeline_shutdown.py` | 7 | K | scripts: master_linkedin_jobs_catalog | — | full:non-api | pytest | A |
| `tests/test_master_employer_jobs_catalog.py` | 36 | I | scripts: build_master_jobs_catalog, master_employer_jobs_catalog | — | full:non-api | param | — |
| `tests/test_master_linkedin_jobs_catalog.py` | 67 | I | scripts: master_linkedin_jobs_catalog | — | full:non-api | param | M |
| `tests/test_master_linkedin_jobs_url_catalog.py` | 18 | I | scripts: master_linkedin_jobs_url_catalog | — | full:non-api | pytest | — |
| `tests/test_observation_store_integration.py` | 3 | I | acquisition.producer_adapters, bootstrap | — | full:non-api | pytest | — |
| `tests/test_phase_a_acquisition.py` | 2 | K | acquisition.manifest | — | full:non-api | unittest | — |
| `tests/test_phase_a_persistence.py` | 1 | K | acquisition.manifest, bootstrap | — | full:non-api | unittest | — |
| `tests/test_phase_a_rc016.py` | 4 | K | acquisition.manifest, bootstrap, repositories.sqlite_acquisition, testing (uses `backend.testing`) | — | full:non-api | pytest | — |
| `tests/test_phase_a_rc017.py` | 4 | K | acquisition.publication, bootstrap; scripts: master_linkedin_jobs_catalog | — | full:non-api | pytest | — |
| `tests/test_phase_a_rc018.py` | 5 | K | application, create_backend, worker | WS-2,WS-4 | full:non-api | unittest | M |
| `tests/test_phase_a_rc019.py` | 4 | K | bootstrap; tests: test_phase_c_personalized_jobs | — | full:non-api | unittest | — |
| `tests/test_phase_a_rc020.py` | 7 | K | api.server, application, application.customer_tasks, create_backend, worker | WS-1,WS-2,WS-4 | full:non-api | unittest | — |
| `tests/test_phase_a_rc021.py` | 6 | K | api.routes, api.server, domain.models, storage | WS-1,WS-5 | full:non-api | unittest | — |
| `tests/test_phase_a_remediation.py` | 7 | K | acquisition.manifest, bootstrap, testing (uses `backend.testing`) | — | full:non-api | unittest+subTest | — |
| `tests/test_phase_a_routes.py` | 2 | K | api.routes | WS-1 | full:non-api | unittest | — |
| `tests/test_phase_a_safety_defaults.py` | 5 | K | acquisition.manifest, bootstrap, worker | WS-2 | full:non-api | unittest | — |
| `tests/test_phase_a_scheduler.py` | 2 | K | bootstrap | — | full:non-api | unittest | M |
| `tests/test_phase_b_catalog.py` | 9 | I | acquisition.manifest, acquisition.phase_b, api.routes, bootstrap, connectors.bounded_probe | WS-1 | full:non-api | unittest | — |
| `tests/test_phase_f_company_enrichment.py` | 25 | I | application.company_enrichment, application.company_logo, bootstrap; tests: test_phase_f_company_profiles | — | full:non-api | unittest | M |
| `tests/test_phase_f_company_profiles.py` | 2 | J | bootstrap, domain.models | WS-5 | full:non-api | unittest | — |
| `tests/test_phase_g_applicant_competition.py` | 7 | I | acquisition.manifest, acquisition.phase_g, bootstrap; tests: test_phase_c_personalized_jobs | — | full:non-api | unittest | — |
| `tests/test_producer_adapters.py` | 5 | I | acquisition.producer_adapters; scripts: master_employer_jobs_catalog, master_linkedin_jobs_catalog | — | full:non-api | pytest | M |
| `tests/test_producer_state_delivery.py` | 1 | K | application.source_eligibility_manifest, repositories.sqlite_acquisition; scripts: master_employer_jobs_catalog, master_linkedin_jobs_catalog, publish_producer_states | — | full:non-api | pytest | A |
| `tests/test_product_completion_wave.py` | 3 | I | repositories.sqlite_acquisition | — | full:non-api | unittest | — |
| `tests/test_production_completion_regressions.py` | 11 | I | acquisition.job_publication_completeness; scripts: master_employer_jobs_catalog, master_linkedin_jobs_catalog, publish_producer_states; deploy/: run-acquisition-source.sh | WS-7 | full:non-api | pytest | A |
| `tests/test_public_contract.py` | 6 | I | acquisition.public_contract | — | full:non-api | unittest | — |
| `tests/test_publication_policy_rollback.py` | 5 | I | acquisition.manifest, acquisition.publication, bootstrap | — | full:non-api | unittest | M |
| `tests/test_publish_existing_catalog.py` | 2 | K | bootstrap; scripts: publish_existing_catalog | — | full:non-api | pytest | A |
| `tests/test_rc006_resolution_safety.py` | 8 | K | application.company_enrichment_resolution; scripts: linkedin_company_enrichment_pipeline, run_linkedin_company_id_resolution | — | full:non-api | pytest | — |
| `tests/test_rc009_normalization_publication.py` | 2 | K | acquisition.phase_b, acquisition.producer_adapters, bootstrap | — | full:non-api | pytest | — |
| `tests/test_rc010_first_acquisition_slice.py` | 1 | K | acquisition.producer_adapters, api.routes, bootstrap | WS-1 | full:non-api | pytest | — |
| `tests/test_rc011_employer_outcomes.py` | 11 | K | scripts: master_employer_jobs_catalog | — | full:non-api | pytest | — |
| `tests/test_rc012_employer_concurrency.py` | 6 | K | scripts: master_employer_jobs_catalog | — | full:non-api | pytest | M |
| `tests/test_rc023_producer_state_paths.py` | 9 | K | scripts: master_employer_jobs_catalog, master_linkedin_jobs_catalog, run_manifested_employer, run_manifested_linkedin; deploy/: acquisition-data-manifest.json | WS-7 | full:non-api | pytest | M |
| `tests/test_rc026_benchmark.py` | 5 | K | scripts: acquisition_state_backup, benchmark_acquisition_full_state, master_employer_jobs_catalog | — | full:non-api | pytest | — |
| `tests/test_rc029_wave_manifest.py` | 3 | K | application.expansion_wave_manifest, application.source_eligibility_manifest | — | full:non-api | pytest | — |
| `tests/test_real_job_data_audit.py` | 4 | I | scripts: audit_real_job_data | — | full:non-api | pytest | A |
| `tests/test_reprocessing.py` | 7 | I | acquisition, acquisition.quality, acquisition.reprocessing, bootstrap, database.connection | WS-5 | full:non-api | unittest | — |
| `tests/test_source_eligibility_manifest.py` | 9 | I | application.source_eligibility_manifest; scripts: run_manifested_employer, run_manifested_linkedin | — | full:non-api | param | — |
| `tests/test_unified_acquisition_pipeline.py` | 3 | I | acquisition.quality, acquisition.reprocessing, acquisition.unified_mapping, bootstrap | — | full:non-api | unittest | — |

#### WS-4 Application services and customer capabilities (49)

| Test file | Tests | Basis | Primary imports (backend.* / scripts.*) | Other WS touched | CI shard | Style | Δ since 848408f3 |
|---|---|---|---|---|---|---|---|
| `tests/test_aa03_application_package.py` | 21 | I | application.assisted_apply_package_service, create_backend, domain.application_package | WS-5 | full:non-api | unittest+subTest | — |
| `tests/test_aa213_preparation.py` | 8 | J | api.routes, create_backend, domain.assisted_apply_preparation | WS-1,WS-5 | full:non-api | unittest | — |
| `tests/test_application_binding.py` | 27 | I | capabilities.profile_matching, domain.models | WS-5 | full:non-api | unittest | — |
| `tests/test_assisted_apply_connection_service.py` | 6 | K | application.assisted_apply_service, create_backend, domain.assisted_apply | WS-5 | full:non-api; backend; check:backend | unittest+subTest | — |
| `tests/test_assisted_apply_corrections.py` | 7 | K | application.assisted_apply_correction_service, application.assisted_apply_package_service, create_backend | — | full:non-api | unittest | — |
| `tests/test_assisted_apply_document_grants.py` | 5 | K | create_backend | — | full:non-api | unittest | — |
| `tests/test_assisted_apply_launch_prepare.py` | 9 | K | api.routes, create_backend, domain.models | WS-1,WS-5 | full:non-api | unittest | — |
| `tests/test_assisted_apply_package_routes.py` | 2 | K | api.routes | WS-1 | full:non-api | unittest | — |
| `tests/test_assisted_apply_telemetry.py` | 5 | K | api.routes, application.assisted_apply_telemetry_service | WS-1 | full:non-api | unittest | M |
| `tests/test_assisted_apply_tracker_confirmation.py` | 2 | K | create_backend | — | full:non-api | unittest | — |
| `tests/test_backend_application.py` | 43 | K | application.services, capabilities.networking, create_backend, domain.models, domain.phase0_contracts, orchestration, profiles.cv_text, storage | WS-2,WS-5 | full:non-api; backend; check:backend | unittest | — |
| `tests/test_baseline_cv_replacement.py` | 44 | I | application.baseline_cv_replacement_service, domain.models | WS-5 | full:non-api | unittest | — |
| `tests/test_candidate_evidence.py` | 35 | I | capabilities.candidate_evidence, domain.candidate_evidence | WS-5 | full:non-api | unittest | — |
| `tests/test_career_memory.py` | 20 | K | capabilities.candidate_evidence, domain.candidate_evidence, domain.models | WS-5 | full:non-api | unittest | — |
| `tests/test_career_profile_evidence.py` | 17 | K | capabilities.career_profile_evidence, domain.career_profile_evidence | WS-5 | full:non-api | pytest | — |
| `tests/test_career_profiles.py` | 7 | K | domain.models | WS-5 | full:non-api | unittest | — |
| `tests/test_cp041r.py` | 22 | I | domain.candidate_evidence, evidence.review_service | WS-5 | full:non-api | unittest | — |
| `tests/test_cp042r.py` | 12 | J | api.routes, domain.candidate_evidence, evidence.review_service | WS-1,WS-5 | full:non-api | unittest | — |
| `tests/test_cp043r_evidence.py` | 16 | J | api.routes, capabilities.source_processing, domain.candidate_evidence, domain.source_processing | WS-1,WS-5 | full:non-api | unittest | — |
| `tests/test_cp044r.py` | 38 | J | api.routes, domain.candidate_evidence, evidence.review_service | WS-1,WS-5 | full:non-api | unittest | — |
| `tests/test_cp044r_confirmation_journey.py` | 27 | I | domain.candidate_evidence, evidence.review_service | WS-5 | full:non-api | unittest | — |
| `tests/test_cp046r_production_gate.py` | 4 | J | api.routes, capabilities.source_processing | WS-1 | full:non-api | pytest | — |
| `tests/test_cv_bullet_suggestions.py` | 45 | I | capabilities.cv_bullet_suggestions, domain.cv_bullet_suggestion | WS-5 | full:non-api | unittest | — |
| `tests/test_document_text.py` | 12 | I | profiles.document_text | — | full:non-api | unittest | — |
| `tests/test_evidence.py` | 12 | K | domain.evidence | WS-5 | full:non-api | param | — |
| `tests/test_evidence_library.py` | 20 | K | domain.models, evidence_library.service | WS-5 | full:non-api | unittest | — |
| `tests/test_evidence_questions.py` | 19 | K | domain.candidate_evidence, evidence.question_service | WS-5 | full:non-api | unittest | — |
| `tests/test_evidence_recommendation.py` | 14 | K | capabilities.evidence_recommendation, capabilities.source_text_review, career_memory.service, domain.evidence_recommendation, domain.models, domain.source_text_review | WS-5 | full:non-api | unittest | — |
| `tests/test_evidence_review.py` | 23 | K | domain.candidate_evidence, evidence.review_service | WS-5 | full:non-api | unittest | — |
| `tests/test_gemini_extraction.py` | 11 | I | domain.source_processing, profiles.document_text, profiles.gemini_extraction | WS-5 | full:non-api | unittest | — |
| `tests/test_manual_url_ingestion.py` | 6 | I | capabilities.tailored_documents | — | full:non-api | unittest | — |
| `tests/test_master_cv.py` | 7 | K | api.routes, domain.models, master_cv.service | WS-1,WS-5 | full:non-api | pytest | — |
| `tests/test_motivation_letters.py` | 36 | I | capabilities.tailored_documents | — | full:non-api | unittest | — |
| `tests/test_networking_referrals.py` | 20 | I | capabilities.networking, domain.models | WS-5 | full:non-api | unittest | — |
| `tests/test_phase_c_feed_performance_security.py` | 2 | K | application.acquisition_scheduler, bootstrap; tests: test_phase_c_personalized_jobs | WS-3 | full:non-api | unittest | — |
| `tests/test_phase_c_personalized_jobs.py` | 4 | K | application.acquisition_scheduler, bootstrap, domain.models | WS-3,WS-5 | full:non-api | unittest | — |
| `tests/test_phase_d_jobs_cutover.py` | 3 | K | application.acquisition_scheduler, application.personalized_jobs_service, bootstrap; tests: test_phase_c_personalized_jobs | WS-3 | full:non-api | unittest | M |
| `tests/test_phase_e_job_intelligence_async.py` | 6 | K | application.personalized_jobs_intelligence, bootstrap; tests: test_phase_c_personalized_jobs | — | full:non-api | unittest | — |
| `tests/test_phase_e_personalized_jobs_intelligence.py` | 2 | K | bootstrap; tests: test_phase_c_personalized_jobs | — | full:non-api | unittest | — |
| `tests/test_phase_i_production_rollout.py` | 6 | K | application.production_rollout, bootstrap | — | full:non-api | unittest | — |
| `tests/test_reusable_package_services.py` | 2 | I | capabilities.reusable_packages | — | full:non-api | unittest | — |
| `tests/test_review_service.py` | 48 | I | domain.candidate_evidence, evidence.review_service | WS-5 | full:non-api | unittest | — |
| `tests/test_source_processing_integration.py` | 6 | I | capabilities.source_processing, domain.source_processing | WS-5 | full:non-api | unittest | — |
| `tests/test_source_processing_pipeline.py` | 16 | J | api.server, capabilities.source_processing, create_backend, domain.candidate_evidence, domain.source_processing | WS-1,WS-5 | full:non-api | unittest | — |
| `tests/test_source_text_review.py` | 24 | J | capabilities.source_text_review, domain.source_processing, domain.source_text_review | WS-5 | full:non-api | unittest | — |
| `tests/test_tailored_document_generation.py` | 40 | K | capabilities.tailored_documents | — | full:non-api | unittest | — |
| `tests/test_title_filter.py` | 2 | I | capabilities.tailored_documents, domain.phase0_contracts | WS-5 | full:non-api | unittest | — |
| `tests/test_tracker_gmail_integration.py` | 4 | I | capabilities.tracker | — | full:non-api | unittest | — |
| `tests/test_work_experience.py` | 23 | I | domain.models, work_experience.service | WS-5 | full:non-api | unittest | — |

#### WS-5 Data, storage, config, domain (10)

| Test file | Tests | Basis | Primary imports (backend.* / scripts.*) | Other WS touched | CI shard | Style | Δ since 848408f3 |
|---|---|---|---|---|---|---|---|
| `tests/test_application_policy.py` | 0 | I | domain.application_package, domain.application_policy | — | full:non-api | unittest | — |
| `tests/test_database_connection.py` | 19 | K | database.connection | — | full:non-api | unittest+subTest | — |
| `tests/test_database_migrations.py` | 6 | K | database.connection, database.initialization, database.migrations, database.schema, repositories.sqlite_migrations | — | full:non-api | unittest | — |
| `tests/test_env_config.py` | 12 | K | config | — | full:non-api; backend; check:backend | unittest+subTest | — |
| `tests/test_job_dedupe.py` | 4 | I | domain.job_identity | — | full:non-api; backend; check:backend | unittest | — |
| `tests/test_object_storage.py` | 13 | K | domain.models, storage | — | full:non-api | unittest+subTest | — |
| `tests/test_personalized_jobs_contracts.py` | 11 | K | domain.candidate_evidence, domain.models, domain.personalized_jobs_contracts, domain.pipeline_jobs | — | full:non-api | unittest | — |
| `tests/test_phase0_contracts.py` | 15 | K | domain.phase0_contracts | — | full:non-api; backend; check:backend | unittest | — |
| `tests/test_run_eta.py` | 2 | I | domain.models, domain.run_eta | — | full:non-api | unittest | — |
| `tests/test_sqlite_repositories.py` | 9 | K | domain.models, repositories.sqlite_backed | — | full:non-api; backend; check:backend | unittest | — |

#### WS-6 Integrations and security (5)

| Test file | Tests | Basis | Primary imports (backend.* / scripts.*) | Other WS touched | CI shard | Style | Δ since 848408f3 |
|---|---|---|---|---|---|---|---|
| `tests/test_career_url_discovery_security.py` | 2 | K | api.server, create_backend | WS-1 | full:non-api | unittest | M |
| `tests/test_creem_integration.py` | 2 | K | integrations.creem | — | full:non-api | unittest | — |
| `tests/test_log_privacy.py` | 4 | K | domain.models, repositories.sqlite_backed, security.redaction, worker.logging_config | WS-1,WS-2,WS-5 | full:non-api | unittest | — |
| `tests/test_phase_h_runr_pro.py` | 5 | K | api.server, application.personalized_jobs_service, bootstrap, config.plans | WS-1,WS-4,WS-5 | full:non-api | unittest | — |
| `tests/test_scrapeops_integration.py` | 13 | K | integrations.scrapeops | — | full:non-api | unittest | — |

#### WS-7 Deployment, release and CI (4)

| Test file | Tests | Basis | Primary imports (backend.* / scripts.*) | Other WS touched | CI shard | Style | Δ since 848408f3 |
|---|---|---|---|---|---|---|---|
| `tests/test_acquisition_runtime_manifest.py` | 3 | K | application.source_eligibility_manifest | WS-3 | full:non-api | pytest | — |
| `tests/test_rc022_build_release_contract.py` | 6 | K | deployment.release_contract | — | full:non-api | pytest | — |
| `tests/test_rc023_vps_runtime.py` | 5 | K | deploy/: acquisition.env.example, deploy.sh, setup.sh, start.sh | — | full:non-api | pytest | M |
| `tests/test_rc024_backup_restore.py` | 12 | K | scripts: acquisition_state_backup, master_employer_jobs_catalog, master_linkedin_jobs_catalog | WS-3 | full:non-api | pytest | M |

#### Support files: conftest and fixtures (34)

| Path | Consumers (static grep of basename / dir name in `tests/*.py`) | Δ since 848408f3 |
|---|---|---|
| `tests/conftest.py` | autouse for all tests; imports capabilities.career_profile_evidence, capabilities.cv_bullet_suggestions, capabilities.evidence_recommendation, capabilities.source_text_review (WS-4) | — |
| `tests/fixtures/ambiguous_source_ownership.csv` | test_master_linkedin_jobs_catalog.py | — |
| `tests/fixtures/employer_coverage/connector_families.json` | test_employer_coverage_evidence.py, test_employer_coverage_receipts.py | A |
| `tests/fixtures/lifecycle_transitions.json` | test_career_memory.py, test_master_linkedin_jobs_catalog.py | — |
| `tests/fixtures/linkedin_company_alias.html` | test_master_linkedin_jobs_catalog.py | — |
| `tests/fixtures/linkedin_job_detail.html` | test_linkedin_pipeline_performance.py, test_linkedin_pipeline_shutdown.py, test_master_linkedin_jobs_catalog.py, test_producer_adapters.py +1 | — |
| `tests/fixtures/linkedin_job_search_challenge.html` | test_master_linkedin_jobs_catalog.py | — |
| `tests/fixtures/linkedin_job_search_compact_valid.html` | test_master_linkedin_jobs_catalog.py | — |
| `tests/fixtures/linkedin_job_search_company_scoped.html` | test_linkedin_pipeline_performance.py, test_master_linkedin_jobs_catalog.py | — |
| `tests/fixtures/linkedin_job_search_no_results.html` | test_linkedin_pipeline_performance.py, test_linkedin_pipeline_shutdown.py, test_master_linkedin_jobs_catalog.py, test_rc023_producer_state_paths.py | — |
| `tests/fixtures/linkedin_job_search_suspicious_empty.html` | test_master_linkedin_jobs_catalog.py | — |
| `tests/fixtures/linkedin_job_search_valid.html` | test_linkedin_pipeline_performance.py, test_master_linkedin_jobs_catalog.py, test_rc023_producer_state_paths.py | — |
| `tests/fixtures/linkedin_retry_sequence.json` | test_master_linkedin_jobs_catalog.py | — |
| `tests/fixtures/package_schema_fixtures.json` | test_aa03_application_package.py | — |
| `tests/fixtures/policy_fixtures.json` | test_application_policy.py | — |
| `tests/fixtures/rc002/generic_job_malformed.html` | test_acquisition_baseline.py | — |
| `tests/fixtures/rc002/generic_job_valid.html` | test_acquisition_baseline.py | — |
| `tests/fixtures/rc002/generic_listing.html` | test_acquisition_baseline.py | — |
| `tests/fixtures/rc002/greenhouse_payload.json` | test_acquisition_baseline.py | — |
| `tests/fixtures/rc002/interrupted_run.json` | test_acquisition_baseline.py | — |
| `tests/fixtures/rc002/lever_payload.json` | test_acquisition_baseline.py | — |
| `tests/fixtures/rc002/recruitee_payload.json` | test_acquisition_baseline.py | — |
| `tests/fixtures/rc002/workday_payload.json` | test_acquisition_baseline.py | — |
| `tests/fixtures/rc002/workload_profiles.json` | test_acquisition_baseline.py | — |
| `tests/fixtures/rc003_application_registry.json` | test_company_registry_reconciliation.py | — |
| `tests/fixtures/rc003_company_registry.csv` | test_company_registry_reconciliation.py | — |
| `tests/fixtures/rc003_shared_organization_dispositions.json` | test_company_registry_reconciliation.py | — |
| `tests/fixtures/rc004_company_id_backfill.csv` | test_company_id_backfill.py | — |
| `tests/fixtures/rc005_linkedin_pagination.json` | test_source_eligibility_manifest.py | — |
| `tests/fixtures/rc005_source_eligibility.csv` | test_producer_state_delivery.py, test_source_eligibility_manifest.py | — |
| `tests/fixtures/rc006_mostly_blocked.json` | test_rc006_resolution_safety.py | — |
| `tests/fixtures/rc009_cross_source_identity.json` | test_rc009_normalization_publication.py | — |
| `tests/fixtures/rc025_operational_dashboard.json` | **none at baseline** — only consumer was removed `test_acquisition_analytics.py` (REMOVED in `dd47acf9`); orphan admin-retirement residue | — |
| `tests/fixtures/rc030_local_jobs_seed.py` | none — manual disposable seed script (`python tests/fixtures/rc030_local_jobs_seed.py DATA_DIR`, L177), cited by `docs/RC_A_HANDOFF.md`; not collected by pytest | — |
<!-- /TABLE -->

### 7.2 Test infrastructure

- **Pytest config (WS-7 owns `pyproject.toml`):** `[tool.pytest.ini_options]` `testpaths=["tests"]`, markers `slow` (declared, unused) and `external` (declared, unused), `addopts="-ra"` (`pyproject.toml` L1–7, cited above in §2).
- **`tests/conftest.py` safe env:** the module-level loop (L29–30) writing `_SAFE_TEST_ENV` (L10–26) forces `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED=false` at L13, and the autouse fixture `_forbid_non_loopback_http` (L64–75) blocks any `requests` call to a non-loopback host.
- **`backend/testing/**` helpers:** `backend/testing/__init__.py` re-exports `create_test_backend`; `backend/testing/bootstrap.py` L12–43 is a fail-closed factory (rejects non-SQLite, a set `TURSO_DATABASE_URL`, `RUNR_ENV=prod`, or live-network truthy) used by exactly 2 tests (`test_phase_a_rc016.py`, `test_phase_a_remediation.py`; §7.1 marks these `(uses backend.testing)`). All other stateful tests call `backend.bootstrap.create_backend` directly (42 files, `git grep -l create_backend 58a96674 -- 'tests/test_*.py'` = 42) or `unittest.TestCase` (101 of 147 files use `unittest.TestCase`/`TestCase`, `git grep -l -E "unittest.TestCase|\(TestCase\)" 58a96674 -- 'tests/test_*.py'` = 101).
- No `tests/__init__.py` or `scripts/__init__.py` exists at the baseline (`git cat-file -e` fails for both); pytest's rootdir-relative collection and the `scripts.*`/`tests.*` imports in §7.1 depend on running `pytest`/`python -m pytest` from the repository root (implicit namespace packages).

### 7.3 Changes since `848408f3`

`git diff --name-status 848408f3 58a96674 -- tests` (191 lines; 17 M, 16 A test files + 1 A fixture, 4 D):

- **Removed (4, all by admin/analytics retirement commit `dd47acf9`):** `test_acquisition_analytics.py`, `test_admin_job_import_dashboard.py`, `test_product_analytics.py`, and `test_enrichment_operations.py` — the last was **deleted by `dd47acf9` itself**, not by a separate commit; `git log --oneline --diff-filter=D -1 58a96674 -- tests/test_enrichment_operations.py` → `dd47acf9 Complete acquisition delivery and remove admin surfaces` (same commit as the other three).
- **Added (16 test files + 1 fixture):** `test_company_identity_canonicalization.py` (`d44d3c0f`), `test_customer_route_surface.py` (`dd47acf9`), `test_employer_bounded_cycles.py` (`5890085f`), `test_employer_coverage_evidence.py` (`5890085f`), `test_employer_coverage_receipts.py` (`13ccb9a7`), `test_employer_traversal.py` (`5890085f`), `test_import_linkedin_company_logos.py` (`8c27ac4e`), `test_job_completeness_audit.py` (`652d7ea8`), `test_job_publication_completeness.py` (`652d7ea8`), `test_job_source_merging.py` (`652d7ea8`), `test_linkedin_pipeline_performance.py` (`a9e9f33b`), `test_linkedin_pipeline_shutdown.py` (`819d33e4`), `test_producer_state_delivery.py` (`dd47acf9`), `test_production_completion_regressions.py` (`50b8f7c4`), `test_publish_existing_catalog.py` (`914503de`), `test_real_job_data_audit.py` (`e7be355a`); fixture `tests/fixtures/employer_coverage/connector_families.json` (`13ccb9a7`). Commit subjects/dates: `git log --oneline 58a96674 -- <path>` (first entry, most recent).
- **Modified (17):** `test_acquisition_audit_permissions.py`, `test_assisted_apply_telemetry.py`, `test_backend_api.py`, `test_career_url_discovery_security.py`, `test_collection_controls.py`, `test_company_identity_reconciliation.py`, `test_master_linkedin_jobs_catalog.py`, `test_phase_a_rc018.py`, `test_phase_a_scheduler.py`, `test_phase_d_jobs_cutover.py`, `test_phase_f_company_enrichment.py`, `test_producer_adapters.py`, `test_publication_policy_rollback.py`, `test_rc012_employer_concurrency.py`, `test_rc023_producer_state_paths.py`, `test_rc023_vps_runtime.py`, `test_rc024_backup_restore.py` (marked `M` in §7.1's Δ column).
- 147 top-level test files at the baseline vs. 135 at `848408f3` (`git ls-tree --name-only 848408f3 tests | grep -c '^tests/test_.*\.py$'` = 135); net +12 matches 16 added − 4 removed.

### 7.4 Admin retirement guard

`tests/test_customer_route_surface.py` (added by `dd47acf9`, the same commit that removed the 4 admin/analytics test files above) is the single-test regression guard for the admin-surface retirement:

```python
# tests/test_customer_route_surface.py:1-13
from backend.api.routes import build_route_registry

def test_route_registry_excludes_removed_admin_surfaces():
    registry = build_route_registry()
    route_names = {route.name for route in registry._routes}
    assert not any(
        name.startswith(("admin.dashboard", "admin.users", "admin.tokens", "admin.secrets", "admin.analytics"))
        for name in route_names
    )
    assert {"admin.billing", "admin.settings", "admin.account.delete"} <= route_names
```

This matches C7(a)/N-17 in `phase-1-delta-audit-2026-09-13.md` L35: unregistered handler bodies for `dashboard`/`users`/`tokens`/`secrets`/`analytics/events` remain in `backend/api/routes/admin.py`, and this test is the only static assertion that they stay unregistered. It runs only in `full:non-api` / `check:backend:full` (§7.1 CI shard column) — it is **not** in the curated `backend` gate or `check:backend`, so a regression here would not block a normal PR unless `backend-full` is also required.

### 7.5 Confirmation question — has the full suite ever been run at the baseline?

**No recorded full-suite run at this exact baseline (`58a96674`) exists. Answer: UNKNOWN, and U11 in `contradictions-and-unknowns.md` L39 stays open** ("Full backend suite result at the baseline (handoff ran focused selections only)"; would resolve it: `npm run check:backend:full`, not executed here per the brief). Evidence considered:

| Source | What it records | SHA it ran against |
|---|---|---|
| `docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md` L82–88 | "Focused release selection: 56 passed, 116 deselected, 5 subtests passed"; `test_producer_state_delivery.py` 1 passed; targeted admin-surface API checks 3 passed, 116 deselected; ruff passed; "**No broad suite was rerun**" (L88) | Dated 2026-09-11; the doc's own release marker is `5dfdd1066d8bcba4a958f3d95e98dc6b7dbe8553` (§ Release and deployment). `5dfdd106` is an ancestor of the baseline, 3 commits and 2 days before `58a96674` (`git log --oneline` between them: `dd47acf9`→`d44d3c0f`→`9ba1d551`→`5dfdd106`, i.e. `5dfdd106` sits between `9ba1d551` and `d44d3c0f`; not the baseline SHA). **Confirmed: not a full-suite run, and not at this exact baseline.** |
| Root `.npm-test-log.txt` (untracked, in `job-automation/Linkedin Jobs Scrapper`, mtime 2026-09-10 16:24) | `node --test "src/**/*.test.js"`; tail: `suites 4`, `pass 170`, `fail 0` | **Frontend**, not backend. No SHA recorded in the log; mtime (2026-09-10) predates the baseline commit `58a96674` (2026-09-13 11:00) by 3 days — SHA UNKNOWN, but temporally it cannot be a baseline run. |
| Root `.pub-test-log.txt` (untracked, mtime 2026-09-10 16:23) | `9 passed in 21.18s` | Backend, but a narrow pytest selection (9 items), not the full 147-file suite. SHA UNKNOWN (no marker in the log); mtime predates the baseline. |
| Root `.pub-regression-log.txt` (untracked, mtime 2026-09-10 19:34) | `25 passed, 4 subtests passed in 53.39s` | Same: narrow selection, SHA UNKNOWN, predates the baseline. |
| Root `.combined-check-log.txt` (untracked, mtime 2026-09-10 19:44) | `65 passed, 8 subtests passed in 71.39s` | Same: narrow selection (65 of 1,745 static `def test_*`), SHA UNKNOWN, predates the baseline. |
| Untracked `docs/reports/RUNR_PRODUCTION_COMPLETION_REPORT_2026-09-12.md` (`job-automation/Linkedin Jobs Scrapper`) L182–186 | "Company enrichment tests: 18 passed. Production regression tests: 10 passed. … Broader backend run: **152 passed and 2 unrelated existing tracker-test failures** (`test_tracker_api` and `test_tracker_ats_detail_returns_persisted_read_only_diagnostics`)" | Report's own §"Exact changed source paths" states the source delta is committed as `4a1b1df55b9dbac9745d29d1916a85fe9575a114` (2026-09-12 23:42), an ancestor of the baseline (one commit before `58a96674`: `4a1b1df5`→`58a96674` "Resolve SQLite row company matches", 2026-09-13 11:00). Both named tracker tests (`test_backend_api.py:4711`, `:5674`) exist unchanged at `4a1b1df5` and at `58a96674`. **This is the closest documentary evidence to the baseline — one commit prior — but "152 passed" is far short of 1,745 static `def test_*` (or even a full 147-file collection), so it reads as a "broader" targeted run, not a `check:backend:full` collection. It is dated for `4a1b1df5`, not `58a96674`, and this package cannot determine node counts for either from the report text alone.** |
| Untracked `docs/reports/CHAT_CHANGES_AND_PRODUCTION_REGRESSION_REPORT_2026-09-12.md` | No pytest pass/fail summary found (`grep -n -i "test\|ruff"` returns only prose mentions of "tests" and "publisher and audit tooling, tests"); records the API's Render deploy attempts as `pre_deploy_failed` | Not a test-run record |

No document claims to have executed `pytest` (bare) or `npm run check:backend:full` against `58a96674` or lists ≥147 collected items / ≈1,745 test IDs. The nearest-SHA evidence (`4a1b1df5`, one commit before baseline) is a 152-item "broader" run with 2 pre-existing unrelated failures in tracker tests, not a full-suite run, and it predates the baseline by one commit that touched only company-logo code (`58a96674` = `Resolve SQLite row company matches`, unrelated to tracker tests). **Conclusion: the full backend suite has never been documented as run at `58a96674` specifically, and — on the evidence read — not conclusively at any single fixed SHA either. UNKNOWN stands; do not treat any of the counts above as a full-suite baseline result.**

### 7.6 Tests only on the unmerged feature branch — UNMERGED

Per the brief, these exist only on `feature/admin-analytics-final-production` (read via `git show ce3718b0:<path>`, never checked out) and are **absent from the baseline** (`git cat-file -e 58a96674:<path>` fails for each):

| File | UNMERGED — ticket | Why it is broken / out of scope at the baseline |
|---|---|---|
| `tests/test_linkedin_germany_adaptive.py` | T04 | `git show ce3718b0:tests/test_linkedin_germany_adaptive.py` L9 does `sys.path.insert(0, …/"Jobs-Urls")` then `from linkedin_germany_adaptive import (…)` (L12) — a module that has never been tracked in this repository (`Jobs-Urls/` is excluded by `pyproject.toml` `[tool.ruff] extend-exclude` L20 and is not under version control at any inspected SHA); the import fails at collection. Introduced by commit `0d7f2b5c` on `feature/admin-analytics-final-production` (2026-09-08), the same commit `contradictions-and-unknowns.md` §3 "Resolved" (L50) already notes as broken and not on the baseline. |
| `tests/test_scrapeops_conclusive_transport.py` | T04 | Imports `from scripts.linkedin_company_enrichment_pipeline import FetchResponse, PipelineMetrics, StateStore` and `from scripts.run_scrapeops_conclusive_test import CreditBudget, classify_usable_linkedin_response, execute_tier_ladder, select_conclusive_sample` — both `scripts/` modules exist only on `ce3718b0` (T04's exact-paths list names both as "absent from baseline"); collection fails against the baseline `scripts/` tree. Also introduced by `0d7f2b5c`. |
| `tests/test_employer_final_focused.py` | T01 | Exists only on `temp/runr-employer-final @ 6ea7f460` (T01's exact-paths list), not on `feature/admin-analytics-final-production` and not on the baseline; 10 `def test_*`, imports only stdlib + `pytest` (no `backend`/`scripts` import at top level — it exercises the employer producer through the T01 patch files listed in the ticket, which themselves are also absent from the baseline). |

Both `feature/admin-analytics-final-production`-branch files were **added** by `0d7f2b5c` and diverge from the baseline in `git diff --name-status 58a96674 ce3718b0 -- tests` as `A` (confirmed: they are additions relative to the baseline, i.e. genuinely absent there, not modified copies). Neither file, nor `tests/test_employer_final_focused.py`, is counted anywhere in §7.1 or the 147/181 totals in §2/§7.1 — those totals are baseline-only.

### 7.7 Frontend and extension tests (WS-8 / WS-9 — counts only)

Frontend and extension test ownership and content belong to WS-8 and WS-9. WS-10 records only counts, taken read-only from the baseline tree, for cross-reference:

| Area | Count | Source |
|---|---|---|
| Frontend co-located unit tests (`frontend/src/**/*.test.js`) | 31 | `git ls-tree -r --name-only 58a96674 frontend/src \| grep -c '\.test\.js$'` |
| Frontend Playwright e2e specs (`frontend/e2e/**`) | 4 | `git ls-tree -r --name-only 58a96674 frontend/e2e \| wc -l`; not run in CI (`ci.yml` has no frontend e2e job); one spec (`admin-operations-console.spec.ts`) targets deleted admin routes and is retired residue (C7(b)) |
| Browser-extension tests (`apps/browser-extension/tests/**`) | 37 | `git ls-tree -r --name-only 58a96674 apps/browser-extension/tests \| wc -l`; run by CI jobs `assisted-apply-extension` / `-edge` via `check:all` / `check:edge` + `test:e2e:edge` (`ci.yml` L111–176) |
| `packages/**` test/spec files | 0 | `git ls-tree -r --name-only 58a96674 packages \| grep -c '\.test\.\|\.spec\.'` |

See [../01-architecture/frontend-app.md](../01-architecture/frontend-app.md) (WS-8, frontend structure and its 31 unit tests / 4 e2e specs) and [../05-subsystems/assisted-apply.md](../05-subsystems/assisted-apply.md) (WS-9, the extension's 37 tests and the never-submit boundary) for content. Neither doc existed in this worktree at the time of writing this file (not yet committed by WS-8/WS-9); the links are per the tree plan (`recommended-documentation-tree.md` L28, L52) and should resolve once those workstreams commit.


## 8. Historical decisions and supporting commits

`git log --oneline 58a96674 -- tests backend/testing` has 239 commits total; the ones most relevant to the suite's current shape:

| Short SHA | Subject |
|---|---|
| `07df74d6` | production skill bug md |
| `c06b727e` | fix(cp-030): complete integration stabilization — introduced the autouse career-profile memory reset fixture in `conftest.py` |
| `9113a426` | [CP-036R] Complete traceable tailored CV bullet generation |
| `c7bf109b` | feat: deploy jobs catalog and portal rollout — earliest commit touching `backend/testing/bootstrap.py` in this history slice |
| `bdd58615` | feat: add product outcome analytics and wave planning — added `tests/fixtures/rc030_local_jobs_seed.py` |
| `13ccb9a7` | feat(employer): per-company coverage receipts and offline completeness report |
| `5890085f` | fix(employer): correct coverage evidence and collector traversal gaps |
| `652d7ea8` | feat(acquisition): add source-independent job publication completeness contract |
| `a9e9f33b` | perf(linkedin): pipeline search+detail and bound concurrency |
| `819d33e4` | perf(linkedin): verify correctness, shutdown/resume, and bounded-cycle cursor |
| `dd47acf9` | Complete acquisition delivery and remove admin surfaces — removed 4 test files (§7.3), added `test_customer_route_surface.py` and `test_producer_state_delivery.py` |
| `9ba1d551` | linkedin-producer: correct apply-destination, Easy Apply evidence, and stable evidence interface |
| `d44d3c0f` | production: restore canonical publication chain — added `test_company_identity_canonicalization.py` |
| `50b8f7c4` | fix acquisition rotation incremental publishing and display feed — added `test_production_completion_regressions.py` |
| `8c27ac4e` | Import LinkedIn company logos into catalog profiles — added `test_import_linkedin_company_logos.py`; last commit touching `tests/` before the baseline |

`848408f3` (the WS-10 diff baseline for §7.3) is `docs: record acquisition repairs and provider spending stop`, itself preceded by `9113a426`/`c06b727e`/`07df74d6` in the same history.

## 9. Current implementation status

| Capability | Classification | Verification note |
|---|---|---|
| Curated `backend` CI gate (7 files + filtered API test) | VERIFIED (scope: static — job defined and wired in `ci.yml` L18–51; runs on every PR and push to `main`/`deployment/render-turso-r2`) | Not executed by this package |
| `backend-full` two-shard full suite in CI | VERIFIED (scope: static — job defined in `ci.yml` L53–88; the shard split is a disjoint partition of all 147 top-level files, confirmed by construction: `api` = `test_backend_api.py`, `non-api` = every other `test_*.py` at depth 1) | Not executed; whether it has ever passed at this SHA is UNKNOWN (§7.5) |
| `docker` job gated on `backend-full` | VERIFIED (scope: static — `ci.yml` L181–185 `needs:` list read directly; it names only `backend`, `frontend`, `assisted-apply-extension`, `assisted-apply-extension-edge`) that this gate does **not** exist | `docker` can build and the workflow can go green even if `backend-full` is red or still running |
| `test_customer_route_surface.py` admin-retirement guard | VERIFIED (scope: static — single assertion read in full, §7.4; it runs in `full:non-api`/`check:backend:full` only, not in the curated gate) | Guard's *effectiveness* against a future regression in the curated-gate-only path is PARTIAL: a regression that only breaks the curated 7 files would surface immediately, but a regression that only re-registers an admin route would surface only when `backend-full`/`check:backend:full` runs |
| `slow`/`external` pytest markers | PARTIAL (scope: static — declared in `pyproject.toml` L3–6, zero usages found in `tests/` at the baseline) | No mechanism currently relies on them; removing the declarations would change nothing observable today |
| Full-suite pass/fail at the baseline (`58a96674`) | UNKNOWN | §7.5; no documentary record found at this exact SHA or, on the evidence read, at any single fixed SHA |
| `backend/testing.create_test_backend` fail-closed guard | VERIFIED (scope: static — 4 explicit `RuntimeError` guards read in full, `bootstrap.py` L15–27) | Used by only 2 of 147 test files; not a suite-wide guarantee — the suite-wide guarantee is `tests/conftest.py`'s env + HTTP-guard fixtures (also VERIFIED by the same method) |
| Test-to-workstream ownership mapping (§7.1) | VERIFIED (scope: static — AST-parsed imports over all 147 files plus `subsystem-allocation.md`'s explicit key-test lists; 34 of 147 files (23%) required WS-10 judgement (`I`/`J` basis) because import majority or harness-vs-subject ambiguity, not a stated key-test list) | Judgement calls are marked `I`/`J` per row in §7.1; a different, defensible split exists for those 34 |

### Deployment evidence

Documentary only, not verified live: `docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md` (2026-09-11, records a "focused release selection", not a full-suite result, against a commit — `5dfdd106` — that is not the current baseline); untracked `docs/reports/RUNR_PRODUCTION_COMPLETION_REPORT_2026-09-12.md` (records a 152-passed "broader backend run" with 2 named pre-existing tracker-test failures, against `4a1b1df5`, one commit before the baseline); untracked root `.npm-test-log.txt`/`.pub-test-log.txt`/`.pub-regression-log.txt`/`.combined-check-log.txt` (narrow selections, no SHA recorded in any log, mtimes 2026-09-10, three days before the baseline commit). None of these constitutes a full-suite CI run record for `58a96674`. LIVE-PRODUCTION test status is out of scope for this doc and remains UNKNOWN per the common brief.

## 10. Confirmed gaps and unresolved questions

| ID | Gap / question | Notes |
|---|---|---|
| U11 (carried) | Full backend suite result at the baseline | **Stays open.** §7.5 found no full-suite record at `58a96674`, and — on the documentary evidence read — no unambiguous full-suite record at any single fixed SHA nearby either. `npm run check:backend:full` (or bare `pytest`) would resolve it; not executed here per the brief. |
| WS10-G1 | 34 of 147 test files (23%) required WS-10 judgement rather than a stated key-test-list match to assign a subject workstream (§7.1 basis `I`/`J`) | Not a defect — the allocation package names key tests illustratively, not exhaustively. Flagging so a future synthesis (WS-12) doesn't treat every §7.1 ownership cell as equally authoritative. |
| WS10-G2 | `_forbid_non_loopback_http` patches only `requests.sessions.Session.request` | A test using `urllib`, raw sockets, a browser-automation driver, or another HTTP client would not be caught by this guard. No evidence any test does this at the baseline (not exhaustively checked — would need a full grep for such usages, out of scope for this pass). |
| WS10-G3 | `test_customer_route_surface.py` runs only in `full:non-api`/`check:backend:full`, not the curated `backend` gate or `check:backend` | A PR that only runs the curated gate would not catch a re-registration of a retired admin route. |
| WS10-G4 | `slow`/`external` markers declared but unused (0 hits) | Either dead configuration or an unfulfilled intent to mark long-running/credentialed tests; either way nothing currently filters on them. |
| WS10-G5 | `tests/fixtures/rc025_operational_dashboard.json` has no consumer at the baseline | Its only consumer, `test_acquisition_analytics.py`, was removed by `dd47acf9` (§7.3); the fixture itself was not removed. Orphaned admin/analytics-retirement residue, parallel to C7 in `contradictions-and-unknowns.md`. |
| T01, T04 (carried) | Three tests exist only on unmerged branches (§7.6) | Ticket disposition (accept/reject per-file) is WS-3's; WS-10 records only that they are absent from the baseline and why they'd fail to collect if copied in as-is. |
| C7(a)/N-17 (carried) | Admin-route residue that `test_customer_route_surface.py` guards against | Owner WS-1; WS-10's role is only the guard test itself (§7.4). |

## 11. Agent context and remaining work

**(a) Proposed agent context packet for future work on `tests/**` or `backend/testing/**`:**
- Required reading: this file; `tests/conftest.py`; `backend/testing/bootstrap.py`; `pyproject.toml` `[tool.pytest.ini_options]`; `.github/workflows/ci.yml` `backend`/`backend-full` jobs; `package.json` `check:backend*` scripts; the owning subsystem doc for whatever `backend/**` module is under test (§7.1 links).
- Allowed paths: `tests/**`, `backend/testing/**` only, unless the task explicitly also touches the subsystem under test (in which case follow that subsystem's ownership).
- Tests to run (not executed by WS-10; listed as the safe verification commands for a future session with a working `.venv`): `.venv\Scripts\python.exe -m pytest -q <changed test file>`; for a full local check, `npm run check:backend` (curated) then `npm run check:backend:full` (full, slower); `python -m ruff check backend tests workspace_runner.py` before either.
- Prohibited changes: editing any file outside `tests/**`/`backend/testing/**` under this task; adding live-network calls or non-loopback HTTP in any test (would trip `_forbid_non_loopback_http` and violate the safety posture in §6); removing or weakening `test_customer_route_surface.py`'s assertions without an explicit ticket to un-retire admin surfaces; running acquisition scripts against live providers from a test.

**(b) Registry proposal:**

| Subsystem id | Name | Owned globs | Primary doc | Test globs | Owner WS |
|---|---|---|---|---|---|
| WS-10 | Backend test suite | `tests/**`, `backend/testing/**` | `docs/reverse-engineering/04-testing/test-suite-map.md` | `tests/test_*.py`, `tests/conftest.py` | WS-10 |

**(c) Gap/ticket candidates:** WS10-G1…WS10-G5 above (table §10); no new ticket is proposed for U11 — it is carried forward as-is per the brief ("U11 stays open unless proven").

