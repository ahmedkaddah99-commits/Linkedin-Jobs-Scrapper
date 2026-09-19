# Runr production completion report

Recorded: 2026-09-12

## Executive status

The VPS acquisition path is deployed and running on release
`4a1b1df55b9dbac9745d29d1916a85fe9575a114`. The LinkedIn and employer
collectors use bounded rotating cohorts, Webshare proxy routing where
configured, resumable SQLite state, and independent systemd timers. The
publisher uses incremental source checkpoints and a bounded row batch; it does
not replay the 188k-row catalog on every cycle.

The current valid publication head is:

- publication: `acq_publication_1de0d29ca01a4d9494c5cc0aeea900c6`
- published jobs: 340
- canonical jobs: 592
- source observations: 648
- posting versions: 592
- canonical companies: 17,601
- publication status: valid; the source cycle is degraded only because the
  selected source cohorts are partial

This is not yet the requested “all historical jobs displayed” result. The
VPS source state contains 188,238 LinkedIn jobs and 2,612 employer-site jobs,
but the publisher bootstrap remains incomplete by design. The preserved
historical exports were not replayed into the publication database because
that would create a large, uncontrolled Turso write/read workload. The next
safe completion step is measured, resumable bootstrap batches with a
published count checkpoint after each batch.

## What was fixed

### Acquisition and VPS runtime

- LinkedIn rotates a finite company cohort instead of replaying the full
  manifest. The latest successful cohort selected 25 of 2,272 manifest
  companies and advanced the cursor from 25 to 50.
- Employer-site acquisition uses the same bounded schedule/checkpoint model.
- Both source wrappers have a finite watchdog (`RUNR_SOURCE_RUN_TIMEOUT_SECONDS=900`)
  so a browser hang cannot hold the service indefinitely.
- The Docker images now create and use `/app/.venv`, matching the launcher
  contract that previously caused Render pre-deploy failures.
- The legacy combined acquisition timer remains disabled. The independent
  LinkedIn, employer, and publisher timers are enabled and active.
- The VPS acquisition worker, customer worker, API, and frontend were left
  running.

### Publication and policy

- Publisher reads are rowid/checkpoint bounded and limited to changed source
  companies plus a bounded bootstrap window.
- LinkedIn and employer company identities are reconciled through the
  canonical identity crosswalk before jobs are published.
- `publication_policy_v1` keeps core job checks and records strict-gate
  rejection evidence, but a missing or unsafe application destination no
  longer hides an otherwise usable job from the display catalog.
- Easy Apply evidence collection was not removed from scraping. It remains
  an observed field, not a publication gate.

### Runr jobs UI

- The frontend requests an initial page of 25 jobs and follows the backend
  cursor for more pages.
- The automatic 720px `IntersectionObserver` prefetch was removed. Loading
  more jobs is explicit, so the browser cannot silently request the entire
  catalog.
- Filter query names are normalized to the backend contract, including
  `sort_by` and `posted_within_days`; unsupported legacy date/sort fields are
  not sent.
- The source card path includes company identity/logo data and retains a
  fallback mark when no verified image asset is available.

### Company and logo enrichment

- The VPS provider is `webshare_linkedin`; it does not require the paid
  ScrapeOps company provider for public LinkedIn company pages.
- Public LinkedIn company pages and logo assets are fetched through the
  configured Webshare proxy. Non-LinkedIn company URLs delegate to the
  official-site provider.
- Official-site extraction accepts JSON-LD logo values, Open Graph/Twitter
  images, and the free public CompanyEnrich logo endpoint, with image
  validation and placeholder rejection.
- The current VPS database has 438 company profiles and 98 verified cached
  logo objects. The remaining profiles have no verified fetched image; the UI
  fallback is therefore necessary. This is partial logo asset coverage, not a
  claim that every company has a source logo.

## Live source evidence

### LinkedIn

Latest durable receipt: 2026-09-12 21:13:09–21:14:57 UTC.

- service result: succeeded; source outcome: partial and recoverable
- requests: 100, using 100 Webshare proxies
- search/detail requests: 54/46 accounting requests; 334 detail refreshes
- valid cards: 334
- detail successes: 43; pending detail retries: 289
- jobs written in that run: 43
- companies selected/examined: 25
- manifest companies: 2,272; deferred: 2,247
- current LinkedIn state: 188,238 jobs, 199,645 search cards, 18,787
  company scans, 11,896 source-company groups, 50 scheduled company rows,
  and 7 recorded runs

### Employer career sites

Latest durable receipt: 2026-09-12 21:36:22–21:36:32 UTC. This was a
one-company smoke run after the prior Playwright hang, specifically to verify
the new watchdog and keep the VPS service safe.

- service result: succeeded; one company selected and one direct request
- selected company: KVH; new jobs in that slice: 0
- durable employer jobs: 2,612
- manifest tasks: 5,135; deferred after the bounded slice: 5,134
- employer export completed with 2,612 persisted/exported jobs
- employer transport remains direct-first with Webshare fallback configured

Yes, companies are being scraped/processed: LinkedIn has company scans and a
rotating company schedule; the employer collector has company targets and
career-site extraction. Company enrichment separately resolves company
profiles and logo assets.

## Live publication and display evidence

The latest publisher completed at 21:37:17 UTC and published a valid head.
It delivered 163 LinkedIn jobs and 99 employer-site jobs in its changed
source window, with zero unresolved observations. Its status is `degraded`
because 29 LinkedIn and 2 employer companies lacked closure-safe completion
evidence; degraded source coverage does not discard the valid display head.

The application policy is therefore display-first but not data-free: title,
employer, location, source/detail URL, and other available job fields are
required; application destination and Easy Apply are optional evidence. The
strict-gate rejection rows remain audit evidence.

## Render status and deviation from the intended architecture

The intended split is preserved in source configuration: acquisition and
company enrichment are disabled on Render, while the VPS owns source timers
and the publisher. Render is intended to serve the customer UI/API role.

Live checks at 2026-09-12 21:45–21:50 UTC showed:

- `https://runr-frontend.onrender.com/`: HTTP 200
- `https://runr-api.onrender.com/health/live`: HTTP 200
- `https://runr-api.onrender.com/health/ready`: HTTP 400 because the Render
  API's Turso connection returned `SQL read operations are forbidden`
- both `https://runr-frontend.onrender.com` and `https://app.userunr.com` still
  served the 20:35 UTC static bundle, which predates this final push

This is the remaining production blocker for a fully live display: the static
shell is reachable, but the Render API's database-read path is not ready, and
the currently served frontend bundle has not yet incorporated the latest
pagination/filter build. No further Turso read/write probing was performed.
Resolving it requires either restoring permitted Turso reads for the customer
API or providing an approved public read-only API path from the VPS; that
choice was not invented here because it changes infrastructure and security
boundaries.

## Root causes found

1. The Render images installed dependencies into the system interpreter while
   `deploy/start.sh` required `/app/.venv/bin/python`.
2. The earlier source cycle could hang in Playwright; the source wrapper had
   no finite watchdog.
3. Publisher identity matching did not map producer company IDs to the
   canonical identity crosswalk, so valid source rows were not delivered.
4. Bootstrap/latest-run handling left fresh source rows outside the first
   publication window.
5. The strict application-destination gate hid usable jobs.
6. Official-site enrichment treated public LinkedIn provenance as a normal
   official site and produced no usable logo coverage.
7. The frontend observer could cascade cursor requests even though the
   backend itself was paginated.

## Verification

- Python interpreter contract verified: Python 3.12.7.
- Company enrichment tests: 18 passed.
- Production regression tests: 10 passed.
- Ruff, shell syntax, and `git diff --check`: passed.
- Frontend check previously passed: 157 tests, ESLint, and Vite build.
- Broader backend run: 152 passed and 2 unrelated existing tracker-test
  failures (`test_tracker_api` and
  `test_tracker_ats_detail_returns_persisted_read_only_diagnostics`).

## Exact changed source paths

The production source delta from the prior VPS release is committed and
pushed on `deployment/render-turso-r2` as
`4a1b1df55b9dbac9745d29d1916a85fe9575a114`. The package README lists the
exact files included in the review archive. No credentials, databases, or
large catalog exports are included.
