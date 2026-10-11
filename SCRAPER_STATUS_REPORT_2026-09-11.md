# LinkedIn and company-URL scraper status

**Evidence captured:** 2026-09-11, 10:11-10:15 UTC (12:11-12:15 Europe/Berlin)

**Scope:** read-only source inspection, read-only Turso queries, read-only Render checks, and read-only VPS inspection. Neither scraper was started and no implementation code or production data was changed.

## Executive result

The two scrapers are **not currently operating as a continuous, complete production feed**.

The deployed application/runtime exists and the data path to Turso exists, but the daily acquisition cycle is failing and the latest published catalog is degraded/stale rather than a fresh complete result.

## Current live facts

### VPS and scheduler

- Host: `vmd205749`, alias `runr-vps`.
- Capacity observed: 6 vCPU, 11,960 MiB RAM, no swap, 193 GB filesystem with 31 GB used.
- At capture time: 11,098 MiB free and 11,233 MiB available; no acquisition process was running.
- `runr-acquisition-cycle.timer`: enabled and active; scheduled daily at approximately 02:00 UTC with up to five minutes of random delay.
- `runr-acquisition-cycle.service`: failed on the last run at 02:04:12 UTC with exit status 2.
- `runr-acquisition-worker.service`: disabled and inactive by design; the timer/oneshot is the source-collection trigger.
- Last scheduled cycle error:

  `FileNotFoundError: Jobs-Urls/linkedin_endpoint_pagination_validation.json`

  The deployed `/opt/runr` has no `/opt/runr/Jobs-Urls` directory. The manifested LinkedIn runner still defaults to that relative evidence path, and the cycle wrapper does not provide an absolute replacement.

- Because the LinkedIn runner failed before collection, the cycle's combined export then failed because `/srv/runr/exports/linkedin/master_linkedin_jobs.csv` did not exist.

### LinkedIn scraper

- The deployed producer is `scripts/master_linkedin_jobs_catalog.py`, invoked by `scripts/run_manifested_linkedin.py`.
- `scripts/master_linkedin_jobs_url_catalog.py` is a separate older URL-catalog implementation; it was not substituted for the deployed 14/15-table producer.
- The deployed producer has resumable SQLite state, search-page and detail-attempt checkpoints, ownership validation, retry/budget handling, bounded workers, detail queues, and a rotating collection cursor.
- It is not currently producing a fresh scheduled result because the required pagination evidence file is missing from the deployed runtime path.
- The last successful bounded pilot evidence was not a continuous production run. It used a small authorized cohort and was explicitly partial/incomplete.

### Company URL/employer scraper

- The deployed employer runner processed only 4 of 5,135 eligible companies before consuming its `RUNR_EMPLOYER_MAX_REQUESTS=6` budget.
- It persisted 1 employer job and deferred 5,131 companies. The run reported 6 direct HTTP attempts, 2 peak in-flight requests, and `final_export_completed=true` for that source output.
- This is a bounded slice, not complete company coverage. It cannot provide all required employer jobs at that cap in one daily cycle.
- The collector does preserve partial/failure evidence and does not falsely classify incomplete sites as complete or empty.

### Turso and Runr delivery

The production Turso database is reachable and has a publication head, but that head is degraded:

- Head publication: `acq_publication_5ff941b21ea84b78af39a4a5cb508b3c`.
- Latest producer-state cycle: `acq_cycle_818f17433ea047c6b2c86f949cdbdd58`, status `degraded`, error `partial_source_coverage`.
- Latest cycle tasks: 39 `partial`, 7,368 `pending` (7,407 tasks in that cycle).
- Latest cycle observations: 22 LinkedIn and 1 Softgarden observation.
- Head publication job count: 47.
- Current database totals: 1,428 canonical companies, 299 canonical jobs, 3,669 source observations, 1,105 posting versions, 7,421 acquisition targets, 50 cycles, 7,583 tasks, 14 publications, and 142 rejections.
- The head was updated on 2026-09-11 around 02:04 UTC, but its own cycle metrics report zero fresh requests/observations and a degraded publication. It must not be interpreted as proof of a fresh complete scrape.
- `https://runr-api.onrender.com/health/live` returned `{"status":"ok"}` and the frontend returned HTTP 200.
- The personalized-jobs API correctly required authentication when probed without a bearer token. An authenticated user feed/UI job-display check was not possible in this session.

## Compute-limit assessment

The runtime is bounded, but VPS-plan compliance is not fully proven.

Configured acquisition service guardrails are `CPUQuota=300%`, `MemoryHigh=9G`, `MemoryMax=12G`, and `TasksMax=512`. Current API/customer processes were approximately 96 MB RSS each, and the host had substantial free RAM. The failed acquisition unit exposed no persisted `MemoryCurrent` or `MemoryPeak` value after exit.

The repository's runtime contract explicitly leaves provider plan limits and monthly price unknown. The offline benchmark measured peak RSS for a synthetic/local workload, not live VPS capacity, provider retries, Turso contention, or customer overlap. Therefore the evidence supports “bounded by systemd guardrails,” not “proven safe for the purchased VPS plan under full continuous workload.”

## Technical extraction method and memory

### What the employer collector supports

The deployed waterfall is conditional and bounded:

1. Detect a recognized ATS and call its public structured endpoint/feed.
2. Try direct employer content and embedded JSON where applicable.
3. Parse JSON-LD/static HTML job evidence.
4. Use bounded Playwright rendering only when the earlier paths do not produce an accepted result; capture same-origin XHR/Fetch JSON and rendered job links.
5. Preserve the provider, endpoint, transport, extraction method, raw-content hash, request counts, status, completeness, and failure evidence.

The code can identify an ATS from a recognizable target URL, but a generic employer site still requires at least a bounded probe. There is no universal way to know the site's supported extraction interface without making a request or using a previously recorded site-specific result.

### What is remembered

There is a useful extraction audit trail, but not a true adaptive “preferred method” cache:

- Per-job fields include `source_provider`, `discovery_method`, `extraction_method`, `extraction_endpoint`, `transport`, and `raw_content_hash`.
- Per-company state stores the collection result, coverage outcome, target outcomes, request accounting, and failure evidence in durable SQLite state.
- Coverage receipts distinguish complete, partial, blocked, failed, unsupported, and confirmed-zero outcomes. Incomplete snapshots are not closure-safe.
- On future retries, the collector can resume/skip successful state and use the durable cursor, but it does not maintain a separate learned rule such as “this domain always works with JSON-LD, skip browser.” A retry may repeat the bounded waterfall when the prior result is partial or needs revalidation.

### Machine-memory logging

There is **no continuous RAM/RSS log for the scraper runtime**. The current implementation has:

- systemd cgroup accounting and hard ceilings;
- journald retention limits (1 GB system, 256 MB runtime, 14 days);
- offline benchmark-only peak-RSS/workspace monitoring.

The benchmark's `_ResourceMonitor` is not connected to the production daily cycle. A production memory log/alert remains outstanding.

## Remaining work before continuous high-efficiency operation

1. Repair the deployed LinkedIn pagination-evidence path by staging the evidence file in the runtime or passing an absolute runtime path; then prove the wrapper and all required manifest inputs exist on the VPS.
2. Reconcile the live-network kill switch with the timer's intended role. The current acquisition env has `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED=false` and `RUNR_ACQUISITION_SCHEDULER_DISABLED=true`, while the scheduled wrapper still attempted employer direct requests. This boundary needs an explicit operational decision and verification.
3. Choose a coverage policy for 5,135 employer targets. Six requests per daily cycle can only be a rotating slice; it cannot deliver full coverage quickly without a measured cursor schedule, source prioritization, and approved larger request budget.
4. Run at least two fresh scheduled cycles after the path fix and verify both source outputs, request counts, closure/completeness outcomes, Turso publication freshness, and the authenticated Runr Jobs feed.
5. Add/enable production telemetry for per-cycle RSS peak, cgroup memory, CPU time, request/response counts, failure reason, and last-success timestamp; alert when the timer fails or no fresh publication is created.
6. Measure the real VPS workload, provider retry/cost behavior, Turso contention, and customer overlap. Current documents leave these values unknown.

## Deployment mismatch to keep in mind

The current IDE checkout is `feature/admin-analytics-final-production` at `ce3718b0` and is not the deployed runtime tip. Render and the VPS deployed `5dfdd1066d8bcba4a958f3d95e98dc6b7dbe8553` from the separate clean checkout/branch `deployment/render-turso-r2`.

Do not infer production behavior from the open local `master_employer_jobs_catalog.py` tab without first selecting the deployed revision.

## Relevant absolute paths

### Deployed release source checkout

- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\master_linkedin_jobs_catalog.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\run_manifested_linkedin.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\master_employer_jobs_catalog.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\run_manifested_employer.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\publish_producer_states.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\scripts\build_master_jobs_catalog.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\backend\application\acquisition_scheduler.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\backend\acquisition\network_policy.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\backend\acquisition\producer_adapters.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\backend\acquisition\employer_coverage.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\backend\acquisition\job_publication_completeness.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\backend\acquisition\publication.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\backend\repositories\sqlite_acquisition.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\backend\repositories\sqlite_personalized_jobs.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\backend\database\connection.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\backend\connectors\ats_router.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\backend\connectors\ats_expansions.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\backend\connectors\company_career_discovery.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\backend\connectors\company_career_sites.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\backend\connectors\employer_site_fallbacks.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\backend\connectors\generic_jsonld.py`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\deploy\run-acquisition-cycle.sh`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\deploy\systemd\runr-acquisition-cycle.service`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\deploy\systemd\runr-acquisition-cycle.timer`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\deploy\systemd\runr-acquisition-worker.service`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\deploy\acquisition-data-manifest.json`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\deploy\acquisition.env.example`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\deploy\vps-runtime-contract.json`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\render.yaml`

### Deployed evidence and verification documents

- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\docs\RUNR_PRODUCTION_COMPLETION_HANDOFF.md`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\docs\RC_CURRENT_STATUS_AND_NEXT_STEPS.md`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\docs\OPENCODE_D_LINKEDIN_PERFORMANCE_HANDOFF.md`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\docs\OPENCODE_E_EMPLOYER_COMPLETENESS_HANDOFF.md`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\docs\OPENCODE_F_JOB_COMPLETENESS_HANDOFF.md`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\docs\RC023_VPS_RUNTIME.md`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\docs\RC026_BENCHMARK.md`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\docs\RC027_LIVE_STAGING_EVIDENCE.md`
- `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview\docs\RC027_LIVE_PILOT_RECEIPT_20260909.md`

### Current IDE checkout / older or separate catalog implementation

- `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\scripts\master_linkedin_jobs_url_catalog.py`
- `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\scripts\master_employer_jobs_catalog.py`
- `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\backend\connectors\company_career_sites.py`
- `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\backend\connectors\company_career_discovery.py`
- `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\backend\connectors\ats_router.py`
- `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\backend\connectors\ats_expansions.py`
- `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\backend\connectors\employer_site_fallbacks.py`
- `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\backend\connectors\generic_jsonld.py`
- `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\backend\integrations\scrapeops.py`
- `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\docs\master_jobs_acquisition.md`
- `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\docs\scraping_strategy_report_2026-05-26.md`
- `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\tests\test_master_linkedin_jobs_url_catalog.py`
- `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\tests\test_master_employer_jobs_catalog.py`
- `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\tests\test_employer_site_fallbacks.py`
- `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\tests\test_linkedin_germany_adaptive.py`
- `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\tests\test_scrapeops_conclusive_transport.py`

### VPS-only runtime paths (not copied into the ZIP)

- `/opt/runr/deploy/run-acquisition-cycle.sh`
- `/opt/runr/.env.acquisition` — secret-bearing operational environment; excluded.
- `/etc/systemd/system/runr-acquisition-cycle.service`
- `/etc/systemd/system/runr-acquisition-cycle.timer`
- `/etc/systemd/system/runr-acquisition-worker.service`
- `/srv/runr/shared/inputs/SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json`
- `/srv/runr/state/rc027-linkedin-6e9a1e9301ffca644aca916aad6fc8827e4a792d/`
- `/srv/runr/state/rc027-employer-6e9a1e9301ffca644aca916aad6fc8827e4a792d/`
- `/srv/runr/exports/acquisition-live-ab1a6a32/producer-state-delivery.json`
- `/var/lib/runr/acquisition-data/backend.sqlite3`

## Explicit exclusions

The ZIP excludes `user_config\\.env`, provider credentials, VPS environment files, SQLite state databases, production logs, `node_modules`, `.venv`, caches, and large historical exports. These are either secret-bearing, runtime-only, or unnecessarily large for the implementation review.
