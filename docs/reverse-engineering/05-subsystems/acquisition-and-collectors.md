> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Acquisition and collectors (WS-3 primary)

Before changing VPS execution, read the [owner operating policy](../02-deployment/vps-acquisition-operating-policy.md). The owner requires dedicated collectors and publisher to remain enabled for unattended validation; assumed customer traffic is not a reason to disable them.

Scope: the two job **producers** (LinkedIn guest-endpoint collector, employer career-site collector), the connector/ATS layer they share with the legacy Phase A scheduler, the eligibility-manifest input contract, the VPS wrapper call graph into `scripts/`, and an inventory of all 45 `scripts/` files and 7 `data/` files. Publication, identity/logos, applicant intelligence and source-state storage are split into secondary docs:

- [publication-and-catalog.md](publication-and-catalog.md): publisher, completeness gate, source merging, combined CSV
- [company-identity-enrichment-and-logos.md](company-identity-enrichment-and-logos.md)
- [applicant-intelligence.md](applicant-intelligence.md) (Phase G, blocked)
- [../03-data/acquisition-source-state.md](../03-data/acquisition-source-state.md): producer state DBs, exports, receipts, input CSVs

Method: static reading of source at `58a96674` only. No script, test, network call or host query was run. "LIVE" is never claimed; production state is UNKNOWN.

---

## 1. Purpose and user-facing capabilities

Acquisition fills the shared job catalog that customers browse in the personalized Jobs UI (WS-4 consumes it). It is not directly user-facing: it has no registered HTTP route at the baseline (the admin acquisition routes were deleted in `dd47acf9`, see §8).

| Capability | What it does | Main code |
|---|---|---|
| LinkedIn producer | Germany-scoped LinkedIn guest search + detail collection per eligible company, resumable SQLite state, bounded request budget, Webshare proxy transport | `scripts/master_linkedin_jobs_catalog.py` (`CatalogRunner` L3188, `WebshareTransport` L920, `StateStore` L1839) wrapped by `scripts/run_manifested_linkedin.py` |
| Employer producer | Guarded CompanyEnrich domain autocomplete for missing/ambiguous website seeds, career-site discovery, ATS detection/fetch, JSON-LD and embedded-payload extraction, Playwright browser fallback, per-company coverage receipts | `backend/connectors/company_enrich_autocomplete.py`; `scripts/master_employer_jobs_catalog.py` (`run_collection`) wrapped by `scripts/run_manifested_employer.py` |
| Eligibility manifest gate | Only a versioned, hash-verified manifest may feed a collector; LinkedIn tasks need a reviewed organization association | `backend/application/source_eligibility_manifest.py` (`load_manifest` L876, `validate_manifest_for_source` L925, `materialize_source_input` L990, `require_eligibility_manifest` L1050) |
| Observation contract | Adapts producer rows (from SQLite state, never from CSV) to `runr_source_observation_v1` with deterministic idempotency keys | `backend/acquisition/producer_adapters.py` |
| Connector layer | ATS router, expansion connectors, generic JSON-LD, bounded probe, browser fallbacks, career discovery, job-board portal strategies | `backend/connectors/**` |
| Legacy Phase A scheduler | In-app, config-store-driven acquisition cycles over targets; network gated by `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED`; disabled on the VPS acquisition worker unit | `backend/application/acquisition_scheduler.py` (`PhaseAAcquisitionScheduler` L137) |
| Receipts | Per-run JSON receipt for each source/publisher run | `scripts/write_acquisition_receipt.py` |

## 2. Owned paths and governing instructions

| Path | Files | Notes |
|---|---:|---|
| `backend/acquisition/**` | 19 | contracts, quality, mapping, completeness, merging, producer adapters, Phase A/B/G primitives, repair/reprocessing |
| `backend/connectors/**` | 13 | incl. `backend/connectors/job_boards/` (3) |
| `backend/enrichment/**` | 13 | inactive offline enrichment foundation (see identity doc) |
| `backend/application/` (13 files) | 13 | `acquisition_scheduler`, `company_enrichment`, `company_enrichment_resolution`, `company_identity_canonicalization`, `company_logo`, `company_logo_adapter`, `company_id_backfill`, `company_reconciliation`, `company_registry_reconciliation`, `company_operations`, `source_eligibility_manifest`, `expansion_wave_manifest`, `duplicate_decisions` |
| `backend/repositories/sqlite_acquisition.py`, `backend/repositories/sqlite_acquisition_audit.py` | 2 | acquisition store (7,514 lines) and audit store |
| `scripts/**` | 45 | inventory §4.3 |
| `data/**` | 7 | 3 inputs + 4 generated (§4.4) |
| **Total** | **112** | matches allocation audit row 20 |

Governing documents (baseline, checked against code where noted):

| Doc | Status vs code |
|---|---|
| root `AGENTS.md` | general repository rules; not acquisition-specific |
| `docs/RUNR_VPS_ACQUISITION_PLAN.md` (v2.2, 2026-09-06) | planning document; architecture (VPS producers, Render API) matches code; ticket list not re-verified |
| `docs/ACQUISITION_RUNTIME_DATA_INVENTORY.md` | input CSV git decision matches `deploy/acquisition-data-manifest.json` `seed_inputs` (checked) |
| `docs/JOB_PUBLICATION_COMPLETENESS_CONTRACT.md` | contract for `job_publication_completeness_v1`; Easy Apply rule changed later by `a2c6fea7` (not re-checked line by line) |
| `docs/RC011_EMPLOYER_COVERAGE.md`, `docs/RC012_EMPLOYER_CONCURRENCY.md`, `docs/RC013_LINKEDIN_LIFECYCLE.md`, `docs/RC014_LINKEDIN_INCREMENTAL_REFRESH.md`, `docs/RC015_LINKEDIN_TRANSPORT_STORAGE.md`, `docs/RC023_VPS_RUNTIME.md`, `docs/RC024_BACKUP_RESTORE.md`, `docs/RC026_BENCHMARK.md` | historical ticket reports; not re-verified |
| `docs/OPENCODE_D_LINKEDIN_PERFORMANCE_HANDOFF.md`, `docs/OPENCODE_E_EMPLOYER_COMPLETENESS_HANDOFF.md`, `docs/OPENCODE_F_JOB_COMPLETENESS_HANDOFF.md` | lane handoffs merged by `bb42cfb7`/`5328832f`/`fb8dbd14`; not re-verified |
| `docs/collection-controls.md`, `docs/architecture/acquisition_audit_permissions.md` | describe `backend/acquisition/collection_controls.py` / `permissions.py`, whose admin API consumers were removed in `dd47acf9` (residue) |
| `docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md` | documentary production record (WS-7 owns); runtime claims contradict baseline units (C4, C5, N-5) |

## 3. Entry points and registered commands/units

No HTTP routes. Entry points are CLI scripts invoked by VPS wrappers (WS-7 owns `deploy/**`; read here only to trace calls, closing **U13**).

### 3.1 Wrapper → script call graph (U13, static)

| Unit (WS-7) | Wrapper | Scripts called (in order) |
|---|---|---|
| `runr-acquisition-linkedin.service` (timer 02:00) | `deploy/run-acquisition-source.sh linkedin` | `deploy/validate_acquisition_runtime.py --role linkedin --allow-state-drift` (L72–76) → if ok `timeout $RUNR_SOURCE_RUN_TIMEOUT_SECONDS scripts/run_manifested_linkedin.py --manifest --output-dir --state-dir --require-existing-state --pagination-report --filters-report --mode ${RUNR_LINKEDIN_MODE:-daily} --workers 10 --detail-workers 5 --per-proxy-concurrency 1 --max-requests --max-companies [--include-single-source]` (L82–95) → `scripts/write_acquisition_receipt.py --source linkedin` (L117–126) |
| `runr-acquisition-employer.service` (02:30) | `deploy/run-acquisition-source.sh employer` | validator (same) → `scripts/run_manifested_employer.py --manifest --output-dir --state-dir --require-existing-state --limit --max-requests [--include-single-source]` (L99–106) → `scripts/write_acquisition_receipt.py --source employer` |
| `runr-acquisition-publisher.service` (04:00) | `deploy/run-acquisition-publisher.sh` | `scripts/publish_producer_states.py --manifest --linkedin-state --employer-state --data-dir --source-version [--identity-crosswalk] [--skip-status-only]` (L51–59) → `scripts/write_acquisition_receipt.py --source publisher` (L64–73) |
| `runr-acquisition-cycle.service` (02:00; not in `runr.target`) | `deploy/run-acquisition-cycle.sh` | `run-acquisition-source.sh linkedin` (L28) → `run-acquisition-source.sh employer` (L31) → `run-acquisition-publisher.sh` (L34) → `scripts/build_master_jobs_catalog.py` only if both source CSVs are non-empty (L40–46) |
| `runr-acquisition-export.service` (06:00) | none (direct `ExecStart`) | `scripts/build_master_jobs_catalog.py --linkedin-csv … --employer-csv … --output …/combined/master_jobs.csv` (L19–22); **`Wants=`/`After=runr-acquisition-cycle.service` (L3–4)**, so starting export can pull in the full combined cycle (N-5) |
| state restore (operator) | `deploy/restore-acquisition-states.sh` | `deploy/validate_acquisition_runtime.py --role all` (L48) → `scripts/canonicalize_producer_states.py --registry --linkedin-state --employer-state --output-dir` (L54–58) → symlink switch of `active` |
| `runr-acquisition-worker.service` | `deploy/start.sh acquisition` | `workspace_runner.py run-worker --worker-role acquisition`; unit sets `RUNR_ACQUISITION_SCHEDULER_DISABLED=true` (L28), which `acquisition_scheduler.py:152–157` turns into `scheduler_enabled/global_enabled/publication_enabled = False` |

Timer schedules, sandboxing and `runr.target` membership are WS-7's: [../02-deployment/vps-runtime-and-acquisition-timers.md](../02-deployment/vps-runtime-and-acquisition-timers.md).

### 3.2 Producer CLIs

| Script | Required args | Key options / defaults | Internal call |
|---|---|---|---|
| `scripts/run_manifested_linkedin.py` | `--manifest`, `--output-dir` | `--mode full` (wrapper passes `daily`), `--workers 10`, `--detail-workers 5`, `--max-requests 0`=unbounded, `--detail-refresh-hours 168`, `--volatile-refresh-hours 24`, `--company-ids`, `--max-companies`, `--require-existing-state`, `--dry-run` (L28–76) | `require_eligibility_manifest(…, SOURCE_LINKEDIN, pilot_only=not --include-single-source)` → `materialize_source_input` to `<output>/.manifest_inputs/<manifest_id>-linkedin.csv` → `CatalogRunner(RunnerConfig).run()`; dry-run injects `transport=object()` so no provider lookup (L123–126) |
| `scripts/run_manifested_employer.py` | `--manifest`, `--output-dir` | `--limit 25` (must be >0 unless `--full`), `--max-job-links 25`, `--max-pages 20`, `--max-browser-requests 10`, `--max-targets 25`, `--max-requests 0`, `--timeout 30`, `--resume` default on (L22–58) | same manifest gate → `scripts/master_employer_jobs_catalog.py:run_collection(...)` |
| `scripts/publish_producer_states.py` | `--manifest`, `--linkedin-state`, `--employer-state`, `--data-dir` | see publication doc | `run_delivery` |
| `scripts/build_master_jobs_catalog.py` | — | `--linkedin-csv`, `--employer-csv`, `--output`, generation IDs | `export_combined_catalog` |

Both manifested runners print one JSON metrics object and return 0; failures surface as exceptions (non-zero exit) that the wrapper records in the receipt.

### 3.3 Guarded CompanyEnrich autocomplete fallback (T57)

`run_collection` passes employer rows through `CompanyEnrichAutocompleteAdapter` before the employer producer rejects rows without a usable website seed. The adapter is only eligible for missing or explicitly ambiguous website/domain rows. It normalizes the required `query` parameter, accepts at most ten sanitized `name`/`domain`/`logoUrl` fields, ranks candidates against the employer's identity evidence, and accepts a domain only when the score and margin clear the ambiguity policy. Unsafe domains, ambiguous matches, missing credentials, provider errors, and exhausted budgets are deferred without inventing a URL.

The adapter has explicit request, retry, concurrency, cache, and total-attempt budgets. Its request is `GET https://api.companyenrich.com/companies/autocomplete`; the recorded intent is free with zero credit cost. It never calls the paid `/companies/enrich`, `/companies/enrich/batch`, or property-enrichment paths, and it never stores authorization headers or raw provider payloads. Dry runs do not construct or call the adapter.

An accepted domain is a homepage seed only, never a career URL. `EmployerCompany.website_provenance`, the `company_domain_provenance` export field, coverage receipts, and `CareerDiscoveryResult.provenance.homepage_seed` retain the sanitized provider decision while the existing career/ATS discovery still contributes every downstream candidate.

### 3.4 In-app entry (legacy Phase A)

`backend/application/services.py:913` constructs `PhaseAAcquisitionScheduler`; `services.py:937` `run_due_cycle`; worker polls it (`backend/worker/service.py:168–192`). Worker roles and the poll loop are WS-2's ([../01-architecture/backend-workers-and-orchestration.md](../01-architecture/backend-workers-and-orchestration.md)).

## 4. Inputs, outputs, storage and dependencies

### 4.1 Environment (names only; defaults from wrappers)

| Variable | Default (source) | Consumer |
|---|---|---|
| `RUNR_ACQUISITION_MANIFEST` | `/srv/runr/shared/inputs/SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json` | source + publisher wrappers |
| `RUNR_ACQUISITION_STATE_ROOT` / `EXPORT_ROOT` / `RECEIPT_ROOT` / `LOCK_ROOT` | `/srv/runr/state`, `/srv/runr/exports`, `$export/receipts`, `$state/locks` | wrappers |
| `RUNR_ACQUISITION_MAX_REQUESTS` | **110** (`run-acquisition-source.sh:20`, `run-acquisition-cycle.sh:6`, `acquisition.env.example:43`) | wrappers (total-cap check) |
| `RUNR_LINKEDIN_MAX_REQUESTS` / `RUNR_EMPLOYER_MAX_REQUESTS` | **100** / **10** (`run-acquisition-source.sh:27,35`; `acquisition.env.example:45–46`) | passed as `--max-requests` |
| `RUNR_LINKEDIN_MAX_COMPANIES` / `RUNR_EMPLOYER_MAX_COMPANIES` | 25 / 10 (`run-acquisition-source.sh:28,36`) | `--max-companies` / `--limit` |
| `RUNR_SOURCE_RUN_TIMEOUT_SECONDS` | 900 (L21) | `timeout --foreground` watchdog |
| `RUNR_ACQUISITION_INCLUDE_SINGLE_SOURCE` | 1 (L19) | `--include-single-source` (disables pilot-only filter) |
| `RUNR_LINKEDIN_{MODE,WORKERS,DETAIL_WORKERS,PER_PROXY_CONCURRENCY,PAGINATION_REPORT,FILTERS_REPORT}` | daily/10/5/1/shared-inputs JSON | LinkedIn runner |
| `RUNR_LINKEDIN_PIPELINE` | `1` (`0` disables pipelining; `master_linkedin_jobs_catalog.py:4523`) | LinkedIn runner |
| `WEBSHARE_PROXY_{URL,USERNAME,PASSWORD,HOST,PORT}`, `WEBSHARE_PROXIES`, `WEBSHARE_PROXY_FILE`, `WEBSHARE_API_KEY` | none | `master_linkedin_jobs_catalog.py:817–871`; `master_employer_jobs_catalog.py:660–668` |
| `RUNR_SOURCE_VERSION` / `RUNR_RELEASE_COMMIT` | — | receipts, employer `source_version` (`master_employer_jobs_catalog.py:2028`) |
| `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED` | `false` example (`acquisition.env.example:39`); **`true` in `runr-acquisition-{linkedin,employer}.service:17`**; `false` on Render (`render.yaml:84,201`) and in tests (`tests/conftest.py:13`) | see §6.1 |
| `RUNR_ACQUISITION_SCHEDULER_DISABLED` | unset; `true` in worker unit | `acquisition_scheduler.py:154` |

### 4.2 Data flow artefacts

| Artefact | Producer | Location (VPS default) | Detail |
|---|---|---|---|
| Eligibility manifest + raw sidecar | `scripts/build_source_eligibility_manifest.py` (offline) | `/srv/runr/shared/inputs/` (not in git) | [../03-data/acquisition-source-state.md](../03-data/acquisition-source-state.md) |
| Staged per-source CSV | runners | `<export>/<source>/.manifest_inputs/` | regenerated each run |
| LinkedIn state DB `master_linkedin_jobs_state.db` | LinkedIn runner | `/srv/runr/state/linkedin/` | tables `runs`, `company_scans`, `search_cards`, `jobs`, `job_company_observations`, `detail_queue`, `collection_cursor`, `company_scan_schedule`, … (`master_linkedin_jobs_catalog.py:1887–2029`) |
| Employer state DB `master_employer_jobs_state.db` | employer runner | `/srv/runr/state/employer/` | `companies`, `jobs`, `coverage_receipts`, `collection_cursor`, `company_scan_schedule` (`master_employer_jobs_catalog.py:1277–1293`) |
| Source CSV exports + `*_metrics.json` | runners | `/srv/runr/exports/{linkedin,employer}/` | consumed only by `build_master_jobs_catalog.py` |
| Receipts `<source>-latest.json`, `-latest-metrics.json`, `-validation.json` | wrappers + `write_acquisition_receipt.py` | `/srv/runr/exports/receipts/` | |
| Catalog DB rows | publisher | `$RUNR_DATA_DIR/backend.sqlite3` or Turso per `DATABASE_BACKEND` | schema: WS-5 [../03-data/schema-and-migrations.md](../03-data/schema-and-migrations.md) |

### 4.3 `scripts/` inventory (all 45)

Class legend: **RUNTIME** = called by a baseline VPS wrapper/unit; **PRODUCER-LIB** = producer implementation imported by a runtime entry; **OPS** = manual operator command that writes state/DB/storage; **NET-OPS** = manual command that performs provider/web requests; **AUDIT** = read-only/offline report; **BENCH** = offline benchmark; **PREP** = offline input/manifest preparation; **DEV** = developer tooling unrelated to acquisition runtime. Tests = baseline test files referencing the script name (`git grep`).

| # | Script | Class | Purpose (from docstring/args) | Tests |
|---:|---|---|---|---|
| 1 | `scripts/acquisition_state_backup.py` | OPS | SQLite Online-Backup checkpoints: backup/validate/restore/remote-restore/prune; optional `--upload` to S3/R2 | `test_rc024_backup_restore.py`, `test_rc026_benchmark.py` |
| 2 | `scripts/add_website_discovery_status_column.py` | PREP | append website-discovery status column to master CSV from JSONL logs; no web requests | — |
| 3 | `scripts/apply_company_identity_crosswalk.py` | OPS | apply reviewed crosswalk JSON to a SQLite store (`--mapping --database`) | — (store method tested elsewhere) |
| 4 | `scripts/apply_known_company_websites.py` | NET-OPS | match user website list; call CompanyEnrich free logo endpoint. **Differs on UNMERGED `0d7f2b5c` (T04)** | `test_known_company_websites.py` |
| 5 | `scripts/audit_employer_coverage.py` | AUDIT | per-company employer coverage classification from checkpoint | `test_employer_coverage_receipts.py` |
| 6 | `scripts/audit_employer_coverage_real.py` | AUDIT | same over historical state, read-only SQLite | — |
| 7 | `scripts/audit_job_publication_completeness.py` | AUDIT | offline completeness audit over JSONL records → JSON+MD | `test_job_completeness_audit.py` |
| 8 | `scripts/audit_real_job_data.py` | AUDIT | completeness audit over real producer state DBs (read-only); usage line writes `data/audit/real` (L24) | `test_real_job_data_audit.py` |
| 9 | `scripts/backfill_company_ids.py` | PREP | RC-004 canonical-ID backfill dry run / approved output copy | (module: `test_company_id_backfill.py`) |
| 10 | `scripts/benchmark_acquisition_baseline.py` | BENCH | RC-002 offline fixture baseline with request guard | `test_acquisition_baseline.py` |
| 11 | `scripts/benchmark_acquisition_full_state.py` | BENCH | RC-026 state/replay/capacity benchmark over checkpoint copies | `test_rc026_benchmark.py` |
| 12 | `scripts/benchmark_linkedin_pipeline.py` | BENCH | LinkedIn producer vs synthetic latency | — |
| 13 | `scripts/benchmark_linkedin_representative.py` | BENCH | parse/SQLite throughput vs historical state shape | — |
| 14 | `scripts/benchmark_personalized_jobs.py` | BENCH | customer Jobs/Company GET warm-path benchmark (WS-4 domain, WS-3 path owner) | — |
| 15 | `scripts/build_master_jobs_catalog.py` | RUNTIME | combined CSV projection (export unit, cycle wrapper) | `test_master_employer_jobs_catalog.py` |
| 16 | `scripts/build_rc029_wave_manifests.py` | PREP | RC-029 expansion wave manifests from RC-005 manifest | (module: `test_rc029_wave_manifest.py`) |
| 17 | `scripts/build_source_eligibility_manifest.py` | PREP | build versioned eligibility manifest + sidecar from a master snapshot | `test_source_eligibility_manifest.py`, `test_producer_state_delivery.py` |
| 18 | `scripts/canonicalize_producer_states.py` | RUNTIME (restore) | versioned canonicalized producer-state copies + `company_identity_crosswalk.json` | — (module: `test_company_identity_canonicalization.py`) |
| 19 | `scripts/clean_master_company_url.py` | PREP | consolidate/audit Master-Company-Url CSV, stdlib only | `test_company_csv_consolidation.py` |
| 20 | `scripts/discover_websites_consensus.py` | NET-OPS | Bing multi-query website consensus, JSONL checkpoints | `test_company_website_consensus.py` |
| 21 | `scripts/discover_websites_from_web_search.py` | NET-OPS | Bing website discovery + free CompanyEnrich logos | `test_company_website_consensus.py` |
| 22 | `scripts/generate_completeness_sample.py` | PREP | synthetic canonical-job sample using `company_registry_canonical.csv` IDs | — |
| 23 | `scripts/import_linkedin_company_logos.py` | NET-OPS | download/validate LinkedIn logos (Webshare), cache to object storage, write `canonical_company_profiles` | `test_import_linkedin_company_logos.py` |
| 24 | `scripts/linkedin_company_enrichment_pipeline.py` | NET-OPS | resumable LinkedIn company enrichment/identity resolution. **Differs on UNMERGED `0d7f2b5c` (T04)** | `test_linkedin_company_enrichment_pipeline.py`, `test_rc006_resolution_safety.py` |
| 25 | `scripts/master_employer_jobs_catalog.py` | PRODUCER-LIB | employer collector. **UNMERGED patch `6ea7f460` (T01)** | `test_master_employer_jobs_catalog.py`, `test_employer_bounded_cycles.py`, `test_employer_traversal.py`, `test_employer_coverage_receipts.py`, `test_producer_adapters.py` |
| 26 | `scripts/master_linkedin_jobs_catalog.py` | PRODUCER-LIB | LinkedIn guest-endpoint collector (4,563 lines) | `test_master_linkedin_jobs_catalog.py`, `test_linkedin_pipeline_performance.py`, `test_linkedin_pipeline_shutdown.py`, `test_phase_a_rc017.py` |
| 27 | `scripts/master_linkedin_jobs_url_catalog.py` | PRODUCER-LIB (legacy) | older company-scoped LinkedIn URL catalog; only its `CSV_FIELDS` is imported at runtime (`build_master_jobs_catalog.py:27`) | `test_master_linkedin_jobs_url_catalog.py` |
| 28 | `scripts/populate_free_companyenrich_logos.py` | NET-OPS | CompanyEnrich free logo URL filled in place (CSV + SQLite) | — |
| 29 | `scripts/profile_company_inputs.py` | AUDIT | read-only profiler of registry inputs | — |
| 30 | `scripts/publish_existing_catalog.py` | OPS | recheck and publish active canonical catalog without source replay | `test_publish_existing_catalog.py` |
| 31 | `scripts/publish_producer_states.py` | RUNTIME | producer-state → catalog publisher | `test_producer_state_delivery.py`, `test_production_completion_regressions.py` |
| 32 | `scripts/reconcile_company_registry.py` | AUDIT | RC-003 read-only registry reconciliation report | (module: `test_company_registry_reconciliation.py`) |
| 33 | `scripts/repair_acquisition_catalog.py` | OPS | repair pass; dry-run default, `--apply` annotations only | `test_acquisition_quality.py` |
| 34 | `scripts/report_employer_coverage_offline.py` | AUDIT | offline employer coverage report from fixtures/state | — |
| 35 | `scripts/reprocess_acquisition.py` | OPS | plan/apply rule reprocessing; `--apply --yes`, remote needs `--allow-remote-additive-rollback` | (module: `test_reprocessing.py`) |
| 36 | `scripts/run-python.cjs` | DEV | Node launcher resolving `.venv` Python (used by `package.json`) | — |
| 37 | `scripts/run_linkedin_company_id_resolution.py` | NET-OPS | resolve LinkedIn org IDs per normalized URL, SQLite checkpoint. **Differs on UNMERGED `0d7f2b5c` (T04)** | `test_linkedin_company_id_browser_resolution.py`, `test_rc006_resolution_safety.py` |
| 38 | `scripts/run_linkedin_company_sweep.py` | NET-OPS | bounded `run_due_company_enrichment` sweep with ScrapeOps LinkedIn provider | — |
| 39 | `scripts/run_manifested_employer.py` | RUNTIME | employer entry. **UNMERGED patch `6ea7f460` (T01)** | `test_rc023_producer_state_paths.py`, `test_source_eligibility_manifest.py` |
| 40 | `scripts/run_manifested_linkedin.py` | RUNTIME | LinkedIn entry | `test_rc023_producer_state_paths.py`, `test_source_eligibility_manifest.py` |
| 41 | `scripts/run_offline_enrichment_trial.py` | AUDIT | offline deterministic enrichment trial (fixtures only) | (module: `test_deterministic_enrichment_evaluation.py`) |
| 42 | `scripts/sync-agent-skills.ps1` | DEV | sync `.agents/skills` → `.cline/skills` | — |
| 43 | `scripts/sync-agent-skills.sh` | DEV | same (POSIX) | — |
| 44 | `scripts/verify_employer_browser_runtime.py` | AUDIT | exercise Python/Chromium collector against loopback fixture | — |
| 45 | `scripts/write_acquisition_receipt.py` | RUNTIME | durable per-run receipt JSON | — |

Counts: RUNTIME 6 (incl. #18 restore), PRODUCER-LIB 3, OPS 5, NET-OPS 8, AUDIT 9, BENCH 5, PREP 6, DEV 3 = 45.

Not on the baseline (label **UNMERGED**, feature commit `0d7f2b5c` on `feature/admin-analytics-final-production`, ticket T04): `enrich_master_company_linkedin_scrapeops.py`, `enrich_pasted_companies_companyenrich.py`, `export_production_enriched_companies.py`, `import_free_company_dataset.py`, `rebuild_saved_scrapeops_report.py`, `recover_scrapeops_conclusive_partial_report.py`, `run_linkedin_company_transport_comparison.py`, `run_linkedin_germany_five_job_test.py`, `run_linkedin_germany_legacy_direct_export.py`, `run_linkedin_germany_scrapeops_legacy_export.py`, `run_scrapeops_conclusive_test.py` (all under `scripts/` on that commit). **Untracked** (feature checkout only, T11): `audit_runr_data_readiness.py` (read-only readiness audit; `DEFAULT_RUNR_ROOT` points at the stale `runr-admin-linkedin-preview` worktree, L26).

### 4.4 `data/` (7 files)

| File | Kind | Evidence |
|---|---|---|
| `data/acquisition/inputs/company_master.csv` | **INPUT** (N-3) | seed input; manifest `rows 9129, columns 82`, exact SHA-256 validated at startup (`deploy/acquisition-data-manifest.json` `seed_inputs`) |
| `data/acquisition/inputs/company_registry_canonical.csv` | **INPUT** | 17,601 rows, 42 columns, `canonical_CompanyID`; default registry for canonicalization |
| `data/acquisition/inputs/company_sources_linkedin_ids.csv` | **INPUT** | 17,601 rows, 118-column contract; eligibility-manifest source |
| `data/audit/report/completeness_audit.json`, `data/audit/report/completeness_audit.md` | GENERATED | 300 synthetic records (`generate_completeness_sample.py` + `audit_job_publication_completeness.py`, inferred from content), 2026-09-10 |
| `data/audit/real/completeness_audit_real.json`, `data/audit/real/completeness_audit_real.md` | GENERATED | `audit_real_job_data.py` output (188,206 LinkedIn records evaluated), 2026-09-10 |

Details and VPS copies: [../03-data/acquisition-source-state.md](../03-data/acquisition-source-state.md).

### 4.5 Dependencies

- Imports into acquisition: `backend.domain.job_identity.canonicalize_url` (WS-5 domain), `backend.storage.create_object_storage` (logos), `backend.repositories` base SQLite store/migrations (WS-5).
- Consumers of WS-3 code outside WS-3: `backend/application/services.py` (scheduler, enrichment, career sites), `backend/application/personalized_jobs_service.py` (Phase G ranking, `company_logo`), `backend/adapters/stage_adapters.py`, `backend/orchestration/workspace_builder.py`, `backend/bootstrap.py:8` (portal strategy IDs), `backend/capabilities/reusable_packages/support.py:16` (job-board collector), `backend/tools/discover_company_careers.py`, `backend/repositories/mysql_career_discovery.py`.
- Import direction: `scripts/` → `backend/`; `backend/connectors` import `backend/acquisition`, not the reverse (evidence package; re-confirmed by grep: no `from backend.connectors` inside `backend/acquisition`).
- External providers (names only): LinkedIn guest endpoints, employer career sites/ATS APIs, Webshare proxies, ScrapeOps (enrichment/discovery, job-board strategies), CompanyEnrich free logo endpoint, Bing web search (PREP scripts), Playwright/Chromium.

## 5. Important call/data flows

### 5.1 LinkedIn source run
1. `run-acquisition-source.sh` validates caps (L39–55: positive integers and `source_cap + other_cap <= total_cap`), takes `flock -n` on `locks/linkedin.lock` (exit 75 if busy), runs runtime validator.
2. `run_manifested_linkedin.main` → `require_eligibility_manifest` (hash + sidecar verification in `load_manifest`; LinkedIn tasks without `organization_associations` raise) → `materialize_source_input` (refuses to overwrite master snapshot).
3. `CatalogRunner.run` (`master_linkedin_jobs_catalog.py:3188`) opens `StateStore` (`--require-existing-state` fails on a missing restored DB), selects a rotating company cohort (`collection_cursor`, `company_scan_schedule`), runs search pages and detail queue with adaptive concurrency through `WebshareTransport` which stops at `max_requests` (L981).
4. Rows land in `jobs` / `job_company_observations` (`row_json`), scan status in `company_scans`; CSV/JSONL/metrics projections written to `--output-dir`.
5. Wrapper writes receipt; exit code propagates.

### 5.2 Employer source run
1. Same wrapper guard with `locks/employer.lock`.
2. `run_manifested_employer.main` → manifest gate → `run_collection` (`master_employer_jobs_catalog.py`) with the autocomplete seed gate, then `RequestAccounting`/`TransportGate` budget (`max_requests`).
3. Per company: career-target discovery (`backend/connectors/company_career_discovery.py`) receives the validated homepage seed and its provenance and returns the full bounded candidate inventory (`CareerDiscoveryResult.candidates`, deterministic order; `build_source_inventory` renders the durable dict shape). The collector (`master_employer_jobs_catalog.py:collect_company`) then traverses **every independent validated partition** — a distinct host, or a distinct ATS tenant — up to `CollectorLimits.max_targets` and the `RequestAccounting`/`TransportGate` request budget, instead of stopping at the first complete snapshot: `detect_ats`/`fetch_ats_snapshot` (`backend/connectors/ats_router.py:24,186`), expansion connectors (`ats_expansions.EXPANSION_CONNECTORS`), `fetch_generic_snapshot` (`generic_jsonld.py:208`), `extract_embedded_jobs`/`fetch_browser_snapshot` (`employer_site_fallbacks.py:232,318`). Jobs are deduplicated into one union across traversed sources (per-target `counts.duplicates_skipped`). Redundant same-host routes, rank-cutoff and budget-deferred candidates keep an explicit `deferred_reason` (`redundant_with_traversed_source`, `below_rank_cutoff`, `request_budget_exhausted`), and per-candidate disposition plus per-source job counts are persisted in `coverage.source_inventory`. Coverage receipt (`backend/acquisition/employer_coverage.py:build_coverage_receipt`) carries the same inventory on `EmployerCoverageReceipt.source_inventory` plus a `source_union` completeness block.
4. State: `companies.payload_json.coverage.outcome` (e.g. `confirmed_complete`) is what the publisher later uses for closure safety; `company_domain_provenance` and the full all-candidate `coverage.source_inventory` are preserved alongside the downstream source inventory.

### 5.3 Producer → observation contract
`producer_adapters._adapt` (L282–359): picks canonical company ID, source job ID/URL, apply URL; `_application_type` (L108–130) classifies `linkedin_job_detail`/`linkedin_easy_apply`/`linkedin_external`/`employer_ats`/`employer_site`; idempotency key = `obs_` + SHA-256 over schema version, source, company, job ID, URL, cycle, scan, content hash (L306–317); `map_job_fields` (`unified_mapping.py:401`) adds the normalized mapping. `SqliteAcquisitionTransport` (L607) forbids mixed sources/companies per batch, non-final `send` never closes a snapshot, and `send_final` requires a complete external-ID inventory (L709–740). Publication continues in [publication-and-catalog.md](publication-and-catalog.md).

### 5.4 Legacy Phase A scheduler
`PhaseAAcquisitionScheduler._phase_a_config` (L152–175): env disable, private-test forced values, per-target defaults. Dispatch calls `require_phase_a_network_permission` (`acquisition_scheduler.py:1012`) → HTTPS only, manifest-allowlisted hostname, no loopback, and **live network flag required unless a requester is injected** (`network_policy.py:35–65`). Portal targets additionally require `portal_audit_gate` (L955). Connectors imported at L27–31 and lazily `scrape_company_career_sites` at L1056.

## 6. Invariants, failure handling and recovery

### 6.1 Live-network gating (C4) — static finding
- `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED` is read only by `backend/acquisition/network_policy.py:16–18` (used by the Phase A scheduler), and by the test-bootstrap guards `backend/bootstrap.py:371` and `backend/testing/bootstrap.py:16`, which **refuse** to start a test bootstrap when it is truthy.
- `git grep` finds **no** reference to the flag (or to `network_policy`) in `scripts/master_linkedin_jobs_catalog.py`, `scripts/master_employer_jobs_catalog.py` or the manifested runners. The producers are therefore bounded by caps, locks, the watchdog and the manifest — not by this flag. The `=true` in `runr-acquisition-{linkedin,employer}.service:17` (`c85f7275`) has no effect on the producer code paths found; the handoff's "reset to false" (L31) would not have disabled producers either. Recorded as **WS3-G1**.

### 6.2 Caps (N-5)
Source defaults 110 total / 100 LinkedIn / 10 employer (wrappers and `acquisition.env.example`). Handoff L32 records effective 12 / 6 / 6; the untracked capacity report records an employer run "capped at 6 requests". The difference must come from host env overrides; the actual host values are UNKNOWN. Both wrappers fail with exit 64 on non-positive or over-total caps. `--max-requests 0` on the Python CLIs means **unbounded**; only the wrappers guarantee a positive cap.

### 6.3 Other invariants
| Invariant | Where |
|---|---|
| Collector input must be a versioned, hash-matching manifest with sidecar | `source_eligibility_manifest.load_manifest` (L876+) |
| Per-source mutual exclusion; publisher waits for both source locks (non-blocking, exit 75 "will retry") | `run-acquisition-source.sh:57–63`, `run-acquisition-publisher.sh:17–34` |
| Watchdog: source runs killed after `RUNR_SOURCE_RUN_TIMEOUT_SECONDS` (900) | `run-acquisition-source.sh:82,99` |
| Receipt always written, including validation failure (metrics = validation JSON) | L109–126 |
| Missing restored state is an error, not a fresh DB, when `--require-existing-state` | runners; wrappers always pass it |
| Observations read from durable state, never CSV exports | `producer_adapters.py` module docstring, L446–465 |
| Intermediate batch cannot authorize absence/closure | `SqliteAcquisitionTransport.send` L696–707 |
| Combined CSV never built from one source | `run-acquisition-cycle.sh:36–49`; `build_master_jobs_catalog._generation_id` raises on missing CSV |
| Producer targets use connector `producer_<source>` so the Phase G applicant gate does not block delivery | `publish_producer_states.py:536–539` |
| CompanyEnrich autocomplete is free-only, bounded, fail-closed, and never a career URL | `backend/connectors/company_enrich_autocomplete.py`; `scripts/master_employer_jobs_catalog.py` |
| Autocomplete provenance and downstream career/ATS candidates remain separate source evidence | `company_domain_provenance`; `CareerDiscoveryResult.provenance.homepage_seed`; `result.targets` |
| Employer collection is source union, not first-success selection: independent validated partitions (distinct host or ATS tenant) are traversed within the target/request budget, jobs are deduplicated into one union, and every discovered source keeps a disposition in `coverage.source_inventory` / `EmployerCoverageReceipt.source_inventory` | `master_employer_jobs_catalog.py` (`collect_company`, `_coverage_target`, `_finalize_coverage`); `backend/connectors/company_career_discovery.py` (`build_source_inventory`); `backend/acquisition/employer_coverage.py` |

Recovery: state restore via `deploy/restore-acquisition-states.sh` (refuses to replace an existing release dir; atomic symlink switch), checkpoints via `scripts/acquisition_state_backup.py`, catalog recovery via `scripts/publish_existing_catalog.py`, rule replay via `scripts/reprocess_acquisition.py`. Cycle failures in the publisher mark `recovery_required` (publication doc §6).

## 7. Relevant tests and safe verification commands (not executed in Phase 2)

| Area | Tests (baseline paths) |
|---|---|
| Producer delivery / adapters | `tests/test_producer_state_delivery.py`, `tests/test_producer_adapters.py`, `tests/test_unified_acquisition_pipeline.py`, `tests/test_acquisition_mapping_contract.py` |
| LinkedIn producer | `tests/test_master_linkedin_jobs_catalog.py`, `tests/test_linkedin_pipeline_performance.py`, `tests/test_linkedin_pipeline_shutdown.py`, `tests/test_master_linkedin_jobs_url_catalog.py` |
| Employer producer | `tests/test_master_employer_jobs_catalog.py`, `tests/test_employer_bounded_cycles.py`, `tests/test_employer_coverage_evidence.py`, `tests/test_employer_coverage_receipts.py`, `tests/test_employer_site_fallbacks.py`, `tests/test_employer_traversal.py`, `tests/test_rc011_employer_outcomes.py`, `tests/test_rc012_employer_concurrency.py` |
| Connectors | `tests/test_ats_router.py`, `tests/test_ats_expansions.py`, `tests/test_job_board_connectors.py`, `tests/test_company_enrich_autocomplete.py`, `tests/test_company_career_discovery.py`, `tests/test_career_url_discovery_security.py` |
| Manifest / runtime paths | `tests/test_source_eligibility_manifest.py`, `tests/test_rc023_producer_state_paths.py`, `tests/test_rc029_wave_manifest.py`, `tests/test_acquisition_runtime_manifest.py` (WS-7 key test) |
| Phase A scheduler / safety | `tests/test_phase_a_acquisition.py`, `tests/test_phase_a_scheduler.py`, `tests/test_phase_a_safety_defaults.py`, `tests/test_phase_a_persistence.py`, `tests/test_phase_a_remediation.py`, `tests/test_phase_a_routes.py`, `tests/test_phase_a_rc016.py`…`tests/test_phase_a_rc021.py`, `tests/test_phase_b_catalog.py` |
| Quality / repair / reprocessing | `tests/test_acquisition_quality.py`, `tests/test_reprocessing.py`, `tests/test_acquisition_baseline.py`, `tests/test_rc026_benchmark.py`, `tests/test_rc024_backup_restore.py`, `tests/test_rc009_normalization_publication.py`, `tests/test_rc010_first_acquisition_slice.py` |

`tests/conftest.py` forces `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED=false` and blocks non-loopback HTTP (test map). Safe commands (offline, no provider):

```bash
node scripts/run-python.cjs -m pytest -q tests/test_producer_state_delivery.py tests/test_source_eligibility_manifest.py tests/test_rc023_producer_state_paths.py
node scripts/run-python.cjs -m pytest -q tests/test_master_linkedin_jobs_catalog.py tests/test_linkedin_pipeline_performance.py tests/test_linkedin_pipeline_shutdown.py
node scripts/run-python.cjs -m pytest -q tests/test_master_employer_jobs_catalog.py tests/test_employer_bounded_cycles.py tests/test_employer_traversal.py tests/test_employer_coverage_receipts.py
node scripts/run-python.cjs -m pytest -q tests/test_phase_a_safety_defaults.py tests/test_phase_a_scheduler.py tests/test_ats_router.py
node scripts/run-python.cjs scripts/run_manifested_linkedin.py --help   # argparse only
git grep -n "RUNR_ACQUISITION_LIVE_NETWORK_ENABLED" 58a96674 -- scripts backend   # re-check WS3-G1
```

Never run the manifested runners without `--dry-run` outside an authorized host.

## 8. Historical decisions and supporting commits

(`git log --oneline 58a96674 -- backend/acquisition backend/connectors backend/enrichment scripts data` = 111 commits; selected.)

| Commit | Subject | Decision |
|---|---|---|
| `7251ae29` | feat(acquisition): reconcile producers inputs and runtime data | input CSVs committed; data manifest |
| `d14332db` | fix(acquisition): separate producer state from exports | `--state-dir` distinct from exports |
| `16c1215d`, `6a242e10` | enforce bounded staging source requests / cohorts, defer after budget exhaustion | fail-closed request budgets |
| `a9e9f33b`, `819d33e4` | perf(linkedin): pipeline search+detail; shutdown/resume, bounded cursor | LinkedIn pipelining |
| `13ccb9a7`, `5890085f` | employer coverage receipts; traversal gaps | employer coverage classification |
| `652d7ea8`, `6c8a34de`, `e7be355a` | job publication completeness contract; opt-in policy v2; validate vs real state | see publication doc |
| `da565e94` | feat(deploy): move acquisition to VPS role and pin 24h UTC schedule | acquisition off Render |
| `bb42cfb7`, `5328832f`, `fb8dbd14` | merge LinkedIn performance / employer completeness / job completeness lanes | |
| `dd47acf9` | Complete acquisition delivery and remove admin surfaces | deleted `backend/acquisition/analytics.py` (1,373 lines), `backend/enrichment/operations.py` (1,370 lines, N-4), admin acquisition/enrichment/job-import routes; merged by `550ee00a` |
| `a11d7b38`…`5dfdd106` | batch producer delivery transactions … avoid full cycle payload reads in producer bridge | Turso-friendly publisher |
| `9ba1d551` | linkedin-producer: correct apply-destination, Easy Apply evidence | Easy Apply retained as evidence |
| `d44d3c0f`, `3d36d8cb` | restore canonical publication chain; persist identity crosswalk before delivery | |
| `914503de`…`10711462` | bounded existing catalog publication recovery; display-first recovery | |
| `c85f7275` (deploy) | enable bounded live acquisition services | sets flag `true` in units (C4) |
| `50b8f7c4`, `35fd6396`, `badc7a3d` | rotation/incremental publishing, identity reconciliation, fresh runs during bootstrap | |
| `92bca0ac`, `4a1b1df5` | Webshare for public logos; avoid empty logo refs (`4a1b1df5` = last recorded VPS release) | |
| `a2c6fea7` | reject easy apply from display feed | Easy Apply rejected in every publication mode |
| `8c27ac4e`, `c8dd517d`, `58a96674` | import LinkedIn logos; SQLite rows in logo importer; resolve SQLite row company matches | baseline head |

## 9. Current implementation status

| Capability | Classification |
|---|---|
| Wrapper → script call graph (U13) | VERIFIED (scope: static; wrapper lines cited in §3.1 invoke the named scripts with those flags at 58a96674) |
| Manifest-gated LinkedIn producer entry | VERIFIED (scope: static; `run_manifested_linkedin.py:89–127` calls `require_eligibility_manifest` before `CatalogRunner`) |
| Manifest-gated employer producer entry | VERIFIED (scope: static; `run_manifested_employer.py:73–96`) |
| Guarded CompanyEnrich autocomplete seed fallback | IMPLEMENTED-LOCALLY-VERIFIED (fixture contract, bounded loader handoff, provenance-preserving career discovery; authorized VPS sample receipt remains external evidence) |
| LinkedIn collection behaviour (cohort rotation, detail refresh, proxy transport) | IMPLEMENTED-UNVERIFIED (large module read by structure only; tests exist, not run) |
| Employer collection behaviour (discovery, ATS, JSON-LD, browser fallback) | IMPLEMENTED-UNVERIFIED |
| Employer source-union inventory (T56: multi-source traversal, deduplicated union, durable per-source inventory/deferral receipts) | IMPLEMENTED-LOCALLY-VERIFIED (focused unit suite; authorized bounded VPS receipt remains outstanding acceptance evidence) |
| Wrapper request caps and lock/timeout guards | VERIFIED (scope: static shell logic `run-acquisition-source.sh:39–63,82,99`) |
| Producer gating by `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED` | PARTIAL (enforced only for Phase A scheduler; producers not gated — WS3-G1) |
| Observation contract + idempotent transport | VERIFIED (scope: static read of `producer_adapters.py` in full) |
| Legacy Phase A in-app scheduler | IMPLEMENTED-UNVERIFIED (disabled on VPS worker unit by env; config-store state unknown) |
| Job-board portal strategies (`backend/connectors/job_boards/**`) | IMPLEMENTED-UNVERIFIED (consumed by capabilities/bootstrap, not by the VPS producers) |
| ATS expansion connectors | PARTIAL (module docstring: "not yet in the production router"; imported by employer producer and scheduler) |
| Combined CSV export | VERIFIED (scope: static; see publication doc) |
| Scripts T04 (`0d7f2b5c`) and T11 (`audit_runr_data_readiness.py`) | PLANNED-NOT-IMPLEMENTED on baseline (UNMERGED/untracked; tickets T04, T11) |
| Employer fair scheduling/method profiles/browser reuse (`6ea7f460`) | PLANNED-NOT-IMPLEMENTED on baseline (UNMERGED, T01) |
| Admin acquisition analytics/operations UI and `backend/enrichment/operations.py` | RETIRED/HISTORICAL (`dd47acf9`) |
| `Company-Urls/` dataset (554 files) | RETIRED/HISTORICAL (exists only in `0d7f2b5c`/`ce3718b0`, absent at baseline) |

### Deployment evidence (documentary only — not live verification)
- `docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md` (baseline, 2026-09-11, Render `5dfdd106`): L27–28 cycle timer is the owner; L29 acquisition worker disabled; L31 live network flag reset to false; L32 caps 12/6/6.
- Untracked `docs/reports/RUNR_PRODUCTION_COMPLETION_REPORT_2026-09-12.md` (feature checkout, not in git; T06): VPS release `4a1b1df5`; "legacy combined acquisition timer remains disabled", independent LinkedIn/employer/publisher timers enabled (contradicts handoff L27–28, see C5); LinkedIn run 2026-09-12: 100 requests, 25 of 2,272 manifest companies, 43 jobs written, state 188,238 jobs; employer run: 1-company smoke after a Playwright hang, 2,612 durable jobs, 5,135 manifest tasks.
- Untracked `docs/reports/SCRAPER_CAPACITY_AND_EFFICIENCY_REPORT_2026-09-11.md` and `SCRAPER_STATUS_REPORT_2026-09-11.md` (feature checkout root, T06): historical run 188,206 LinkedIn rows / 271,193 requests; 2,612 employer rows / 5,132 requests; "continuous VPS sustainability is not yet proven"; no CPU/RSS telemetry.
- `docs/RC027_LIVE_PILOT_RECEIPT_20260909.md`: bounded pilot receipt (not re-read in detail).

## 10. Confirmed gaps and unresolved questions

| ID | Gap |
|---|---|
| C4 / **WS3-G1** | Live-network flag does not gate the producers at all (static grep). Either document it as Phase-A-only or add an explicit producer check; unit `=true` is cosmetic for producers. |
| N-5 | Caps 110/100/10 in source vs 12/6/6 recorded; host override UNKNOWN. Export unit `Wants=` the cycle service (WS-7 owns fix). |
| C5 | Which timers are enabled (cycle vs independent) is contradicted between handoff and untracked report; UNKNOWN on host (WS-7). |
| **WS3-G2** | Python CLIs treat `--max-requests 0` as unbounded; only wrappers enforce positive caps. Direct operator invocation can run unbounded. |
| **WS3-G3** | `RUNR_ACQUISITION_INCLUDE_SINGLE_SOURCE` defaults to 1 in the wrapper, so the "dual-source pilot" default of the runners is bypassed in the VPS path. Intentional? |
| **WS3-G4** | `scripts/master_linkedin_jobs_url_catalog.py` (1,716 lines) is legacy; only `CSV_FIELDS` is used. Candidate for field extraction/retirement decision. |
| **WS3-G5** | `scripts/` mixes RUNTIME with 8 NET-OPS scripts that can spend provider credit and 3 DEV scripts (`sync-agent-skills.*`, `run-python.cjs`) unrelated to acquisition; no manifest marks which are safe. |
| T01 | Employer patch `6ea7f460` (6 files, +1,511/−277) unmerged; conflicts with baseline `master_employer_jobs_catalog.py`. |
| T04 | 11 absent + 3 differing scripts on `0d7f2b5c`; `tests/test_linkedin_germany_adaptive.py` broken import (feature only). |
| T11 | `audit_runr_data_readiness.py` untracked with stale default root. |
| U7 | Migration `055_acquisition_analytics_indexes` residue after analytics removal (WS-5). |
| **WS3-G6** | Employer browser hang recorded 2026-09-12 (untracked report); watchdog mitigates, root cause not traced in code. |
| CLOSED (T56, 2026-09-21) | First-success source selection in `collect_company` (early `break` after the first complete snapshot; only skipped ATS tenants recorded). Replaced by bounded source union with a durable `coverage.source_inventory`; see §5.2 and §6.3. |

## Agent context and remaining work

**(a) Agent context packet — acquisition & collectors**
- Required reading: this doc; [publication-and-catalog.md](publication-and-catalog.md); [../03-data/acquisition-source-state.md](../03-data/acquisition-source-state.md); `backend/acquisition/producer_adapters.py`; `backend/application/source_eligibility_manifest.py`; `scripts/run_manifested_linkedin.py`; `scripts/run_manifested_employer.py`; `deploy/run-acquisition-source.sh` (read-only, WS-7).
- Allowed paths: `backend/acquisition/**`, `backend/connectors/**`, `backend/application/acquisition_scheduler.py`, `backend/application/source_eligibility_manifest.py`, `backend/application/expansion_wave_manifest.py`, `scripts/**` (non-DEV), `tests/test_*` listed in §7 (with WS-10).
- Tests to run: the four pytest commands in §7 plus `npm run check:backend`.
- Prohibited: running any NET-OPS or RUNTIME script without `--dry-run`/`--help`; setting `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED` true in tests; editing `deploy/**` (WS-7), migrations (WS-5), committing state DBs/exports; wholesale merge of `feature/admin-analytics-final-production` or `temp/runr-employer-final`; restoring admin acquisition surfaces.

**(b) Registry proposal**

| subsystem id | name | owned globs | primary doc | test globs | owner |
|---|---|---|---|---|---|
| `acquisition` | Acquisition, collectors, publication and enrichment | `backend/acquisition/**`, `backend/connectors/**`, `backend/enrichment/**`, `backend/application/{acquisition_scheduler,company_*,source_eligibility_manifest,expansion_wave_manifest,duplicate_decisions}.py`, `backend/repositories/sqlite_acquisition*.py`, `scripts/**`, `data/**` | `docs/reverse-engineering/05-subsystems/acquisition-and-collectors.md` | `tests/test_{producer_*,master_*_catalog,employer_*,linkedin_*,phase_a_*,phase_b_*,phase_f_*,phase_g_*,rc0*,job_*,company_*,ats_*,acquisition_*,source_eligibility_manifest,publish_existing_catalog,import_linkedin_company_logos,reprocessing,real_job_data_audit,production_completion_regressions}.py` | WS-3 |

**(c) Gap/ticket candidates**
1. WS3-G1: decide and implement/document producer live-network gating (pair with WS-7 on C4).
2. WS3-G2: make `--max-requests` required-positive in manifested runners (or explicit `--unbounded`).
3. WS3-G5: add a script classification header/manifest (RUNTIME/NET-OPS/AUDIT) and move DEV tooling out of `scripts/` ownership.
4. WS3-G4: retire or slim `master_linkedin_jobs_url_catalog.py`.
5. Execute T01, T04, T11 reviews as written in the ticket candidates.
