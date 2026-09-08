# Current RC status and next steps

Date: 2026-09-07

Branch: `deployment/render-turso-r2`

HEAD: `e7662c63082d605d8ae6de090d3a04a55bba6556`

This is an offline integration handoff. No commit, reset, clean, merge, push,
deploy, production migration, browser session, or acquisition/provider request
was performed. The working tree was already dirty and was preserved.

## Environment and verification result

The repository-mandated interpreter was checked before Python work:

```text
C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe --version
Python 3.12.7
```

The actual 14-table producer remains `scripts/master_linkedin_jobs_catalog.py`.
`master_linkedin_jobs_url_catalog.py` was not substituted for it. The RC-013
retry, lifecycle, suspicious-empty, and ownership fixtures remain in the
working tree and are covered by the producer-focused tests.

### Bounded backend regression

The combined offline command covered identity, eligibility, adapters, both
producers, normalization/publication, scheduler and lifecycle, worker roles,
intelligence recovery, customer task handling, storage, migrations, and SQLite
repositories. It used the shared Python interpreter above and selected these
tests:

```text
tests/test_company_registry_reconciliation.py
tests/test_company_id_backfill.py
tests/test_source_eligibility_manifest.py
tests/test_rc006_resolution_safety.py
tests/test_producer_adapters.py
tests/test_phase_b_catalog.py
tests/test_rc009_normalization_publication.py
tests/test_rc010_first_acquisition_slice.py
tests/test_observation_store_integration.py
tests/test_employer_site_fallbacks.py
tests/test_rc011_employer_outcomes.py
tests/test_rc012_employer_concurrency.py
tests/test_master_employer_jobs_catalog.py
tests/test_master_linkedin_jobs_catalog.py
tests/test_phase_a_acquisition.py
tests/test_phase_a_scheduler.py
tests/test_phase_a_rc016.py
tests/test_phase_a_rc017.py
tests/test_phase_a_rc018.py
tests/test_phase_a_rc019.py
tests/test_phase_a_rc020.py
tests/test_phase_a_rc021.py
tests/test_object_storage.py
tests/test_database_migrations.py
tests/test_worker_service.py
tests/test_sqlite_repositories.py
```

Result: **255 passed, 8 subtests passed in 60.98s**.

This verifies the current RC-016 behavior rather than reopening the failures
reported during RC-016. RC-017's current reconciliation behavior also passed.
`git diff --check` passed (only normal Git line-ending warnings were emitted).

### Frontend and dependency verification

`frontend/node_modules` was incomplete, so the repository lockfile workflow was
used: `npm ci` in `frontend/`. It installed 722 packages and audited 723. npm
reported 19 advisories (2 low, 4 moderate, 11 high, 2 critical), including the
deprecated/vulnerable `next@15.4.6` package. No audit fix or dependency upgrade
was run.

Results:

- `npm test`: **167 passed, 0 failed**, 4 suites.
- `npm run build`: **passed**; Vite transformed 1,148 modules and built in
  16.24 seconds.
- `frontend/src/lib/api.test.js` includes the signed-object test proving that a
  fully-qualified signed URL is fetched without a Runr bearer token. The full
  frontend suite also covers retry and status polling behavior.
- `frontend/src/hooks/useTracker.js`, the customer-task route, and the
  Artifacts/Tracker pages retain queued task status polling. The backend
  exposes task status for queued bulk export and email sync rather than making
  the UI treat acceptance as completion.

The production build is a local artifact only; it was not deployed.

## Exact remaining API failures

The focused current-worktree command was:

```text
pytest -q --disable-warnings tests/test_backend_api.py \
  -k "test_tracker_api or test_tracker_ats_detail_returns_persisted_read_only_diagnostics"
```

Result: **2 failed, 123 deselected in 9.98s**.

1. `BackendApiTests.test_tracker_api` (`tests/test_backend_api.py:5305`):
   expected `Admin_Engineer_ACMEAPI_MotivationLetter.txt` in the bulk-export
   ZIP, received `Cover letter.txt`.
2. `BackendApiTests.test_tracker_ats_detail_returns_persisted_read_only_diagnostics`
   (`tests/test_backend_api.py:6216`): expected two persisted ATS attempts,
   received an empty `attempt_history`.

Baseline evidence was established without changing this checkout by exporting
committed HEAD `e7662c6` into an isolated temporary copy and running the same
focused command. It reproduced both failures exactly: **2 failed, 123
deselected in 7.83s**. The current RC-021 diff adds object-storage/download
handling and frontend credential behavior, but has no hunk changing the
custom-generated filename or `_tracker_ats_detail_payload` history source.
Therefore these are independent committed-HEAD baseline failures, not RC-021
regressions. They remain follow-up defects; they were not silently labeled
unrelated merely because they are outside the storage ticket.

No source fix was justified in this pass. The follow-up should first correct
the expected document-name contract and then trace the persisted metadata key
(`ats_attempt_history`) through artifact read-only diagnostics. It should add
focused regressions before changing the shared API.

## RC-021 storage and browser operational handoff

Offline evidence is in `docs/RC021_PORTABLE_ARTIFACT_STORAGE.md`,
`tests/test_phase_a_rc021.py`, `tests/test_object_storage.py`, and the selected
backend API download/export tests. The focused storage result was **13 passed,
4 subtests passed**; the combined RC-018--021/storage result was **35 passed,
4 subtests**. The implementation checks:

- ownership before signing in the API route and object-storage descriptor;
- expiry and signature validation for local signed downloads;
- allowed MIME types and the configured maximum size in
  `backend/storage/policy.py`;
- content-hash object keys and stored SHA-256 metadata for immutable content;
- bounded materialization cache bytes and age;
- direct S3/R2 redirects when direct storage is enabled, with local fallback;
- API response accounting through `object_storage_bytes_shifted` and the
  redirect headers.

### Required R2 CORS configuration

Apply this to the R2 bucket only after replacing the two placeholders with the
actual deployed origins. Do not use `*` for production origins:

```json
[
  {
    "AllowedOrigins": [
      "https://<production-frontend-origin>",
      "https://<staging-frontend-origin>"
    ],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": ["Range", "Content-Type", "Accept"],
    "ExposeHeaders": [
      "Accept-Ranges",
      "Content-Length",
      "Content-Disposition",
      "Content-Type",
      "ETag"
    ],
    "MaxAgeSeconds": 600
  }
]
```

If the browser extension fetches R2 directly, add its exact
`chrome-extension://<extension-id>` origin as a third `AllowedOrigins` entry
after the extension ID is fixed. The configuration is **pending external R2
administration** and has not been claimed as deployed or live-tested.

### Deployed-browser verification procedure

Run this only against an isolated staging artifact after R2 CORS is applied:

1. Record the frontend/API revision, exact frontend origin, R2 bucket policy
   revision, and test user IDs. Create an artifact owned by user A with a safe
   MIME type and known byte size.
2. With user A, request the API download endpoint. Verify ownership is checked
   before signing, the API response is a redirect to the R2 host, the signed
   URL has a bounded expiry, and the response contains no API bearer token in
   the `Location` value.
3. Follow the signed URL from the browser without an `Authorization` header.
   Verify CORS, `Content-Disposition` filename, `Content-Type`, exact size,
   and direct download behavior. Repeat with an empty API/local materialization
   cache on a second host.
4. With user B, try user A's API endpoint and signed URL. Expect denial. Try a
   tampered and an expired URL and expect object-store denial.
5. Submit forbidden MIME and over-limit fixtures through the API and verify
   rejection before signing. Verify object keys contain the content hash and
   do not reuse a mutable path. Exercise cache age/byte pruning and confirm
   the protected current object is retained.
6. Confirm API logs report `object_storage_bytes_shifted` and that the
   download response exposes the redirect/byte headers. Record browser,
   network, and API evidence with no customer document contents.

No step above was run live in this integration pass.

## Ticket status

The statuses below distinguish offline implementation/evidence from external
deployment, provider authorization, data approval, and live acceptance.

| Ticket | Implementation/status | Current evidence | Pending action and real dependency |
|---|---|---|---|
| RC-001 | Verified offline | Baseline contract, handoff, current combined matrix | Record deployed state and source-of-truth revisions when authorized. |
| RC-002 | Verified offline | `BASELINE_METRICS.*`, baseline tests | Replace proposed capacity/cost targets with measured approved workload evidence before RC-026/027. |
| RC-003 | Verified offline, review incomplete | Registry fixtures/tests and identity handoff | Review application/shared-organization dispositions and owner decisions. |
| RC-004 | Verified offline, dry-run only | Backfill report and backfill tests | Approve mappings and apply bounded data waves. |
| RC-005 | Verified offline | Manifest artifacts/tests and handoff | Prove runtime manifest consumption and source-task replacement in staging. |
| RC-006a | Verified offline | Resolution-safety fixtures/tests | Keep resolver controls and review gates in the release. |
| RC-006b | Not started / external | No provider authorization or live enrichment evidence | Provider authorization and bounded enrichment remain pending; not a prerequisite for RC-022. |
| RC-007 | Verified offline | Export-separation report and producer tests | Integrate the selected release and verify the deployed export path. |
| RC-008 | Verified offline | Adapter report, `tests/test_producer_adapters.py`, combined matrix | Runtime adapter wiring and staging proof remain pending. |
| RC-009 | Verified offline | Normalization/publication report and tests | Staging/live publication, expiry, and user-journey evidence remain pending. |
| RC-010 | Verified offline fixture/API slice | `tests/test_rc010_first_acquisition_slice.py` | Browser/server and real-source staging acceptance remain pending. |
| RC-011 | Verified offline | Employer outcome fixtures/tests | Live employer challenge/timeout behavior and coverage denominator remain pending. |
| RC-012 | Verified offline | Concurrency/transport tests; current matrix | Live request accounting and measured limits remain pending. |
| RC-013 | Verified offline | Actual 14-table producer tests, retry/ambiguous ownership/suspicious-empty/lifecycle fixtures, producer handoff | No live LinkedIn scan was authorized; staging scan acceptance remains pending. |
| RC-014 | Verified offline | Incremental-refresh evidence/tests | Real detail-refresh savings and staging cycle remain pending. |
| RC-015 | Verified offline | Transport/storage evidence/tests | VPS checkpoint/transport performance and recovery evidence remain pending. |
| RC-016 | Verified current integration | `tests/test_phase_a_rc016.py` and scheduler tests passed in the 255-test matrix | Deployed scheduler ownership and live worker evidence remain pending. |
| RC-017 | Verified current integration | `tests/test_phase_a_rc017.py` and migration/publication tests passed | Staging publication/expiry and recovery drills remain pending. |
| RC-018 | Verified offline/current | `docs/RC018_WORKER_ROLES.md`, tests, and combined matrix | Release image separation and deployed role/claim verification move to RC-022/023. |
| RC-019 | Verified offline/current | `docs/RC019_INTELLIGENCE_RECOVERY.md`, tests, and combined matrix | Live recovery/heartbeat and resource limits remain pending. |
| RC-020 | Verified offline/current | `docs/RC020_CUSTOMER_TASK_QUEUE.md`, tests, frontend suite | Two independent baseline API failures remain follow-up work; no RC-020/021 regression was demonstrated. |
| RC-021 | Verified offline/current | Storage tests, selected API tests, frontend signed-URL test, 167 frontend tests, successful production build | R2 CORS, deployed browser behavior, empty-cache host, and external object-store evidence remain pending. |
| RC-022 | Implemented offline; final acceptance pending | `docs/RC022_BUILD_RELEASE_STAGING.md`, `tests/test_rc022_build_release_contract.py`, separate Dockerfiles, Render filters, CI image jobs; focused suite passed 6/6 | Docker daemon image builds, path-filter execution, and mixed-version isolated staging remain pending. No deploy or RC-006b prerequisite was required. |
| RC-023 | **First genuinely unfinished ticket**; not started | Offline requirements are defined in the plan | Resource selection, VPS provisioning, clean-host setup, and live port/service checks depend on RC-002/018 and authorization. |
| RC-024 | Not started | Scope only; existing 3.48 GB state is recorded in the plan | Design may proceed offline; actual checkpoint/restore/ownership drills depend on RC-015/016/023. |
| RC-025 | Not started | Scope only | Offline dashboard fixtures can proceed after the status contract; live acceptance depends on RC-005/016/018/019. |
| RC-026 | Not started | Scope only | Wait for RC-012/014/015/021/024/025 and comparable measured state before claiming benchmark/cost evidence. |
| RC-027 | Not started | Scope only | Requires RC-010--017, RC-019, RC-022--026 and explicit real-source staging authorization. |
| RC-028 | Not started | Scope only | Requires RC-027 and production authorization; Gate A and Gate B remain separate. |
| RC-029 | Not started | Scope only | Requires RC-005, RC-026, RC-028 Gate A, and RC-006 only for cohorts needing enrichment. |
| RC-030 | Not started / optional P2 | Scope only | Can follow RC-022/025; must remain independent of hosting migration success. |
| RC-031 | Not started / trigger-based P2 | Scope only | Only start when RC-024/026/028 evidence triggers horizontal capacity work. |
| RC-032 | Not started | Scope only | Final runbook/acceptance depends on RC-028/029; RC-030/031 only if enabled. |

### Next-ticket decision

RC-022 is implemented offline. Its remaining acceptance requires a Docker-capable
environment and isolated mixed-version staging; those were not claimed here.
RC-023 is now the first genuinely unfinished ticket. Its runtime definition
can be prepared offline, but final acceptance requires an authorized VPS.
RC-025 fixture work and RC-030 read-only audit can also be prepared offline, but
neither should be marked complete ahead of its listed dependencies.

## Migration and runtime release handoff

The current migration registry is ordered and contiguous through:

```text
054_company_identity_reconciliation
055_acquisition_analytics_indexes
056_phase_a_scheduler_fencing
057_phase_e_intelligence_recovery
058_customer_task_queue
```

`sqlite_migrations.py` is shared by identity, acquisition, worker, intelligence,
and customer-task work. One release owner must apply migrations in registry
order. New application/worker code must tolerate the previous schema during
rollout; do not run production migrations in this pass. RC-022 must define who
runs migrations and the forward-compatible rollback limit before separate
images are released.

Runtime inputs/state that the eventual acquisition worker release must mount or
inject explicitly:

- the approved source eligibility manifest and its version/hash;
- the master input/catalog location and the producer's local state directory;
- the existing approximately 3.48 GB LinkedIn state with checkpoint/backup
  capacity, not an assumed ephemeral container filesystem;
- disposable materialization/cache storage with byte and age limits;
- Turso/database and R2 credentials by secret name, scoped to the worker role;
- a unique worker identity, role/claim settings, scheduler interval, and
  source-cycle ownership configuration.

Customer document/email secrets must not be inherited by acquisition/browser
processes. A worker must not silently fall back to laptop-relative paths or
unversioned manifests.

### Proposed release sequence

1. Freeze and record the selected commit, dirty-file ownership, manifest hash,
   migration head, image digests, environment names, and worker role contract.
2. Apply migrations once, in registry order, using the designated release
   owner; verify backward-compatible reads before enabling new writers.
3. Release API/shared contracts, then the role-specific worker image, then
   frontend flags. Keep old/new client and worker schema versions compatible
   during the rollout.
4. Start one owner per role, verify heartbeats and queue claims, and ensure no
   competing scheduler is active. Mount the approved input/state and verify
   object storage/cache paths.
5. Run offline/staging smoke tests, then the authorized staging pilot. Record
   deployed revisions separately from this branch's HEAD.

### Rollback and recovery

- Stop admitting new work for the affected role, drain or fence active claims,
  and disable the new release/feature flag.
- Restore the last compatible API/worker/frontend images and task ownership;
  do not restore an old database over newer customer writes.
- Keep immutable R2 objects and receipts. Rebuild local materialization from
  object storage when the cache is missing; do not treat a missing cache as
  data loss.
- For a failed migration, follow the migration's documented forward-compatible
  remediation. Do not delete migration rows or run an ad hoc production
  downgrade.
- For this dirty checkout, rollback means a scoped hunk/file review or
  restoring the exact pre-change copy from the owning ticket after approval;
  do not use `git reset --hard`, `git clean`, or a wholesale checkout that
  could discard another session's work.

Smoke-test expectations are: API health and version, migration head, one
role-scoped synthetic queue claim, one retry/lease expiry, one publication and
read-only customer artifact download, signed URL without API credentials,
expired/cross-user denial, frontend asset load, and no duplicate scheduler
owner. Production/provider steps remain authorization-gated.

## Changed and untracked deliverable inventory

The inventory below is the `git status --short --untracked-files=all` snapshot
for this handoff. Nothing was staged or committed.

### Modified tracked files

```text
backend/api/routes/__init__.py
backend/api/routes/acquisition_catalog.py
backend/api/routes/documents.py
backend/api/routes/registry.py
backend/api/routes/tracker.py
backend/api/routes/workspace.py
backend/api/server.py
backend/application/acquisition_scheduler.py
backend/application/admin_job_import.py
backend/application/personalized_jobs_service.py
backend/application/run_services.py
backend/application/services.py
backend/config/env_schema.py
backend/connectors/employer_site_fallbacks.py
backend/connectors/generic_jsonld.py
backend/repositories/__init__.py
backend/repositories/contracts.py
backend/repositories/sqlite_acquisition.py
backend/repositories/sqlite_migrations.py
backend/repositories/sqlite_personalized_jobs.py
backend/storage/__init__.py
backend/storage/local.py
backend/storage/materialization.py
backend/storage/s3.py
backend/worker/__init__.py
backend/worker/service.py
deploy/start.sh
frontend/src/hooks/useTracker.js
frontend/src/lib/api.js
frontend/src/lib/api.test.js
frontend/src/pages/ArtifactsPage.jsx
frontend/src/pages/TrackerPage.jsx
render.yaml
scripts/build_master_jobs_catalog.py
scripts/master_employer_jobs_catalog.py
scripts/master_linkedin_jobs_catalog.py
tests/test_master_employer_jobs_catalog.py
tests/test_master_linkedin_jobs_catalog.py
tests/test_phase_b_catalog.py
tests/test_worker_service.py
tests/test_workspace_runner.py
workspace_runner.py
```

### Untracked reports, contracts, and source modules

```text
ACQUISITION_SOURCE_TRANSFER.md
BASELINE_AND_INPUT_CONTRACT.md
BASELINE_METRICS.json
BASELINE_METRICS.md
COMPANY_REGISTRY_RECONCILIATION.json
COMPANY_REGISTRY_RECONCILIATION.md
RC004_BACKFILL_REPORT.json
RC004_BACKFILL_REPORT.md
RC006_RESOLUTION_SAFETY.json
RC006_RESOLUTION_SAFETY.md
RC007_EXPORT_SEPARATION.json
RC007_EXPORT_SEPARATION.md
RC008_PRODUCER_ADAPTERS.json
RC008_PRODUCER_ADAPTERS.md
SOURCE_ELIGIBILITY_MANIFEST.md
SOURCE_ELIGIBILITY_MANIFEST_RC005.json
SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json
SOURCE_ELIGIBILITY_RAW_RC005.jsonl
SOURCE_ELIGIBILITY_RAW_RC005_RECONCILED.jsonl
backend/acquisition/producer_adapters.py
backend/api/routes/storage.py
backend/application/company_enrichment_resolution.py
backend/application/company_id_backfill.py
backend/application/company_registry_reconciliation.py
backend/application/customer_tasks.py
backend/application/source_eligibility_manifest.py
backend/storage/policy.py
backend/worker/roles.py
```

### Untracked ticket reports

```text
docs/RC009_NORMALIZATION_PUBLICATION.json
docs/RC009_NORMALIZATION_PUBLICATION.md
docs/RC010_FIRST_ACQUISITION_SLICE.md
docs/RC011_EMPLOYER_COVERAGE.md
docs/RC012_EMPLOYER_CONCURRENCY.md
docs/RC013_LINKEDIN_LIFECYCLE.md
docs/RC014_LINKEDIN_INCREMENTAL_REFRESH.md
docs/RC015_LINKEDIN_TRANSPORT_STORAGE.md
docs/RC018_WORKER_ROLES.md
docs/RC019_INTELLIGENCE_RECOVERY.md
docs/RC020_CUSTOMER_TASK_QUEUE.md
docs/RC021_PORTABLE_ARTIFACT_STORAGE.md
docs/RC_IDENTITY_RECONCILIATION_HANDOFF.md
docs/RC_PRODUCER_VERIFICATION_HANDOFF.md
docs/RC_CURRENT_STATUS_AND_NEXT_STEPS.md
docs/RUNR_VPS_ACQUISITION_PLAN.md
```

### Untracked scripts, fixtures, and tests

```text
scripts/add_website_discovery_status_column.py
scripts/apply_known_company_websites.py
scripts/audit_employer_coverage.py
scripts/backfill_company_ids.py
scripts/benchmark_acquisition_baseline.py
scripts/build_source_eligibility_manifest.py
scripts/discover_websites_consensus.py
scripts/discover_websites_from_web_search.py
scripts/linkedin_company_enrichment_pipeline.py
scripts/populate_free_companyenrich_logos.py
scripts/reconcile_company_registry.py
scripts/run_linkedin_company_id_resolution.py
scripts/run_manifested_employer.py
scripts/run_manifested_linkedin.py
tests/fixtures/ambiguous_source_ownership.csv
tests/fixtures/lifecycle_transitions.json
tests/fixtures/linkedin_job_search_suspicious_empty.html
tests/fixtures/linkedin_retry_sequence.json
tests/fixtures/rc002/generic_job_malformed.html
tests/fixtures/rc002/generic_job_valid.html
tests/fixtures/rc002/generic_listing.html
tests/fixtures/rc002/greenhouse_payload.json
tests/fixtures/rc002/interrupted_run.json
tests/fixtures/rc002/lever_payload.json
tests/fixtures/rc002/recruitee_payload.json
tests/fixtures/rc002/workday_payload.json
tests/fixtures/rc002/workload_profiles.json
tests/fixtures/rc003_application_registry.json
tests/fixtures/rc003_company_registry.csv
tests/fixtures/rc003_shared_organization_dispositions.json
tests/fixtures/rc004_company_id_backfill.csv
tests/fixtures/rc005_linkedin_pagination.json
tests/fixtures/rc005_source_eligibility.csv
tests/fixtures/rc006_mostly_blocked.json
tests/fixtures/rc009_cross_source_identity.json
tests/test_acquisition_baseline.py
tests/test_company_id_backfill.py
tests/test_company_registry_reconciliation.py
tests/test_company_website_consensus.py
tests/test_known_company_websites.py
tests/test_linkedin_company_enrichment_pipeline.py
tests/test_linkedin_company_id_browser_resolution.py
tests/test_observation_store_integration.py
tests/test_phase_a_rc016.py
tests/test_phase_a_rc017.py
tests/test_phase_a_rc018.py
tests/test_phase_a_rc019.py
tests/test_phase_a_rc020.py
tests/test_phase_a_rc021.py
tests/test_producer_adapters.py
tests/test_rc006_resolution_safety.py
tests/test_rc009_normalization_publication.py
tests/test_rc010_first_acquisition_slice.py
tests/test_rc011_employer_outcomes.py
tests/test_rc012_employer_concurrency.py
tests/test_source_eligibility_manifest.py
```

Shared files such as `backend/api/server.py`,
`backend/repositories/sqlite_migrations.py`, `backend/application/services.py`,
`backend/application/run_services.py`, `backend/worker/service.py`,
`render.yaml`, and the route registries are touched by multiple ticket groups.
They need hunk-level review, not independent wholesale reverts.

## Proposed scoped commit groups

No commits were created. For the next release owner, the safe grouping is:

1. Baseline/identity/manifest: baseline contracts and metrics, company
   registry/backfill/resolution modules, RC-003--006 fixtures/reports/scripts.
2. Producer/export/adapters: RC-007--015 producer scripts, adapter modules,
   employer/LinkedIn fixtures, and their focused tests/reports. Keep the
   actual 14-table LinkedIn producer in this group.
3. Scheduler/publication: RC-016/017 acquisition scheduler, repositories,
   migrations, publication contracts, and focused tests. Serialize migration
   ownership here.
4. Worker/intelligence: RC-018/019 role, claim, recovery, input-version,
   and worker-service changes plus their tests/reports.
5. Customer tasks/storage/frontend: RC-020/021 customer-task routes, storage
   policy/materialization/S3/local behavior, API routes, frontend polling and
   signed-URL behavior, deployment env/start configuration, and focused tests.
6. This status handoff: `docs/RC_CURRENT_STATUS_AND_NEXT_STEPS.md`, kept as
   release evidence and not mixed into an unrelated source fix.

Before committing, review shared files against all five groups and preserve
the two committed-HEAD baseline API failures as explicit follow-up rather than
silently changing their contract in a storage release.

RC-022 additions in this pass are:

```text
Dockerfile.api
Dockerfile.worker
backend/deployment/__init__.py
backend/deployment/release_contract.py
docs/RC022_BUILD_RELEASE_STAGING.md
frontend/scripts/write-release-metadata.mjs
tests/test_rc022_build_release_contract.py
```

RC-022 also updates these existing release files:

```text
.github/workflows/ci.yml
.gitignore
Dockerfile
deploy/start.sh
frontend/package.json
render.yaml
docs/RC_CURRENT_STATUS_AND_NEXT_STEPS.md
```

## Branch versus deployed state

All evidence here describes the dirty local worktree at HEAD plus uncommitted
changes. It does not describe a deployed Render revision, a deployed VPS
worker, a live Turso schema, or configured R2 CORS. Those external states are
pending and must be recorded separately in a release receipt after
authorization.
