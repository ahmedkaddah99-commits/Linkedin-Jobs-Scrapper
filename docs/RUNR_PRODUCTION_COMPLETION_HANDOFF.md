# Runr production completion handoff

Verification date: 2026-09-11

## Release and deployment

- Repository: `deployment/render-turso-r2`
- Runtime release commit deployed to production: `5dfdd1066d8bcba4a958f3d95e98dc6b7dbe8553`
- Acquisition/admin integration ancestor: `550ee00a50b7f5538359a21c5b6a02227efac9ce`
- Integrated delivery commit: `dd47acf9`
- VPS: `runr-vps` / `vmd205749`, release root `/opt/runr`
- VPS acquisition release marker: `5dfdd1066d8bcba4a958f3d95e98dc6b7dbe8553`

Render production services are live on the final commit:

| Service | Render service | Live deployment | Revision |
| --- | --- | --- | --- |
| API | `srv-d8q47dh194ac73df0acg` | `dep-dahik167bikc73ebn2c0` | `5dfdd1066d8bcba4a958f3d95e98dc6b7dbe8553` |
| Worker | `srv-d8s24fkm0tmc739t4h10` | `dep-dahik16k1f9s73feoe60` | `5dfdd1066d8bcba4a958f3d95e98dc6b7dbe8553` |
| Frontend | `srv-d8q47dh194ac73df0a8g` | `dep-dahik1afngtc739si9lg` | `5dfdd1066d8bcba4a958f3d95e98dc6b7dbe8553` |

`https://runr-api.onrender.com/health/live` returned `{"status":"ok"}`.

## Runtime ownership and controls

- Render API/worker acquisition scheduling and enrichment are disabled.
- The unattended acquisition owner is the VPS systemd timer.
- `runr-acquisition-cycle.timer`: enabled and active; observed next run `2026-09-11 02:02:17 UTC`.
- `runr-acquisition-worker.service`: disabled and inactive.
- Cycle service loads `/opt/runr/.env.acquisition` and the protected optional provider file `/opt/runr/.env.acquisition.provider`.
- Live network flag is reset to `false` after the pilot.
- Effective bounded caps are 12 total, 6 LinkedIn, and 6 employer-site attempts per cycle.
- Company enrichment is disabled (`RUNR_COMPANY_ENRICHMENT_ENABLED=0`).
- Authoritative source state remains separate and preserved at:
  - `/srv/runr/state/rc027-linkedin-6e9a1e9301ffca644aca916aad6fc8827e4a792d/master_linkedin_jobs_state.db`
  - `/srv/runr/state/rc027-employer-6e9a1e9301ffca644aca916aad6fc8827e4a792d/master_employer_jobs_state.db`
- Eligibility manifest: `source-eligibility-7f416ec6ebbcb936-84d00936bacc`; hash `6bfcba5c01985402d2d1278e8b726baa8e4ac3332e6527be40bc433ab663e447`.

## Bounded live source evidence

The frozen four-company cohort was run twice. The four companies were NOVENTI Health SE, helmag, St. Vincenz Kliniken, and MALZERS Backstube GmbH & Co. KG.

- LinkedIn cycle 1: run `run_20260910T211157341540Z`; exactly 3 requests (2 search, 1 detail), 4 recoverable failures under the cap, no closure claim.
- Employer cycle 1: exactly 3 direct HTTP attempts; all 4 companies remained partial under the cap; 1 durable job was persisted and the export completed.
- LinkedIn cycle 2/restart: run `run_20260910T211328321551Z`; exactly 3 requests (2 search), recoverable partial outcome.
- Employer cycle 2/restart: exactly 3 direct HTTP attempts; all 4 companies remained partial; 1 durable job persisted and export completed.
- Total live source attempts: 12. No unbounded source run was performed.

The LinkedIn collector used 100 configured Webshare proxies. The current ScrapeOps account snapshot was 50,000,000 plan credits, 25,041,300 used, 24,958,700 remaining, zero active concurrency, and a 25-concurrency limit; renewal was reported as `2026-09-16T20:35:06.000Z`.

## Shared Turso publication evidence

The producer bridge wrote to the shared Turso database (`RUNR_ENV=production`, `DATABASE_BACKEND=turso`), not a VPS-local SQLite publication database.

- Delivery report: `/srv/runr/exports/acquisition-live-ab1a6a32/producer-state-delivery.json` (23,391,497 bytes)
- Bridge result: `BRIDGE_OK`
- Bridge cycle: `acq_cycle_818f17433ea047c6b2c86f949cdbdd58`
- Cycle status: `degraded` with `partial_source_coverage`; lease released.
- Publication: `acq_publication_5ff941b21ea84b78af39a4a5cb508b3c`
- Publication head now points to that publication.
- Eligible acquisition targets: 7,421; active tasks represented in the producer cycle: 7,407.
- Current producer-cycle task status: 37 partial, 7,370 pending. Pending means the company has not yet produced durable source state; it is not treated as confirmed empty.
- Source-backed delivery in this cycle: LinkedIn 22 observations across 4 partial companies; employer 1 observation across 4 partial companies.
- Current-cycle rejection reasons: 140 `listing_fallback_application_url`, 1 `insufficient_description`, 1 `missing_location`.
- Total Turso counts after publication: 1,426 canonical companies, 299 canonical jobs, 3,669 source observations, 1,105 posting versions, 14 publications, 1,754 publication jobs, and 142 persisted job rejections.

The strict publication v2 gate is active. LinkedIn view/detail/listing URLs are not treated as application destinations; rejected rows remain durable evidence with reasons.

## Object storage

An authorized bounded R2 write/read/delete readiness probe passed in 2,380.29 ms using the configured S3-compatible R2 credentials. The probe object was deleted after verification.

## Customer surface

- Customer route surface is `/jobs` backed by the authenticated `/v1/personalized-jobs` API path.
- The frontend build passed and the deployed frontend is on the final revision.
- An unauthenticated browser check reached the Clerk sign-in screen at `https://app.userunr.com/`.
- No logged-in browser session was available, so authenticated Jobs API payloads and customer-facing job-card examples could not be visually verified without bypassing authentication. This is the only remaining evidence gap; sign-in is required to close it.

## Verification performed

- Focused release selection: 56 passed, 116 deselected, 5 subtests passed.
- Final bridge regression: `tests/test_producer_state_delivery.py` — 1 passed.
- Targeted admin-surface API checks: 3 passed, 116 deselected, 5 subtests.
- Targeted Ruff checks passed.
- Frontend production build passed; Vite transformed 427 modules.
- `deploy/run-acquisition-cycle.sh` shell syntax check passed.
- No broad suite was rerun; verification stayed scoped to changed surfaces and live deployment evidence.

## Durable implementation notes

- LinkedIn backup compatibility accepts the current 15-table state and the preserved 14-table legacy state.
- Employer backup compatibility accepts the current 4-table state and the preserved 2-table legacy state.
- Producer state reaches the shared catalog through the single canonical normalization/publication bridge; no disconnected public table was introduced.
- Partial and failed source outcomes remain retryable and do not erase the other source or close postings without explicit completeness evidence.
- Admin dashboard/data/analytics backend and frontend surfaces were removed; customer billing/settings/account/webhook surfaces remain.
