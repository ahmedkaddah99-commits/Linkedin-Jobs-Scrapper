# Runr Wave 1 Integration Ledger

Base: `0068a5f740d379e896d8f6831c3fa5fc63d434b9`
Integrator branch: `integration/wave-1`

## Recovery verification

All six expected recovery commits exist, are reachable from their named
branches, match their `origin/recovery/*` refs, and their dedicated worktrees
were clean at inspection time.

| Unit | Recovery branch | Commit | Push status | Provisional migration | Final reservation | Worktree |
| --- | --- | --- | --- | --- | --- | --- |
| 01 collection controls | `recovery/01-collection-controls` | `6b2e59aaf5b0f7588b53426c62e2e5a4492cf840` | Pushed; origin matches | `050_collection_controls` | `050_collection_controls` | clean |
| 02 enrichment operations | `recovery/02-enrichment-operations` | `00dfb95e7611277cbcccbce5277c5b7e7131f225` | Pushed; origin matches | `050_enrichment_operations` | `051_enrichment_operations` | clean |
| 03 deterministic evaluation | `recovery/03-deterministic-evaluation` | `e77add5036cca5c4561cd78305a61afe35f19127` | Pushed; origin matches | none | none | clean |
| 04 publication rollback | `recovery/04-publication-rollback` | `054b713e3a8e6ee0d2d82008a50d0aee73a943b5` plus `d571d63b011996abce24b43a03ca314ad79262a5` | Pushed; origin matches | `050_publication_policy_history` | `052_publication_policy_history` | clean |
| 05 audit permissions | `recovery/05-audit-permissions` | `0344dd452e2af0136a16dce0e97941825639bd9f` | Pushed; origin matches | `053_acquisition_audit_permissions` | `053_acquisition_audit_permissions` | clean |
| 06 company reconciliation | `recovery/06-company-reconciliation` | `5e4b846f148f0eefe5aacfd97c2f4a8da5950cfe` | Pushed; origin matches | `054_company_identity_reconciliation` | `054_company_identity_reconciliation` | clean |

## Integration progress

- Unit 01 integrated as `619c637`.
- Unit 01 focused and combined acquisition/migration tests: `32 passed`.
- Unit 01 produced no conflict-resolution commit and remains provider-neutral;
  no publication activation was introduced.
- Unit 03 integrated as `43f2152`.
- Unit 03 plus foundation/collection/migration regression tests initially
  exposed the stale `MIGRATIONS[:-1]` assumption; repaired in `f048225` to
  locate `049_enrichment_foundation` by identifier.
- After repair, the combined unit 01/03 suite is `43 passed`.
- Unit 02 integrated as `ef2ad6d`; its provisional `050_enrichment_operations`
  was centrally renumbered to `051_enrichment_operations`.
- Unit 02 integration required preserving the 01 migration and the repaired
  foundation migration test; the combined 01/02/03/migration suite is
  `50 passed`.
- Unit 04 integrated as `2b656014` plus recovered test-formatting commit
  `fd4709bb`; its provisional `050_publication_policy_history` was centrally
  renumbered to `052_publication_policy_history`.
- Unit 04 migration conflict resolution required restoring the closing SQL
  definition for `051_enrichment_operations`; repair committed as `9fbf9e19`.
- After the repair, the combined publication/enrichment/evaluation/acquisition
  and migration suite is `70 passed`.
- Unit 05 integrated as `b270d2cb`; its provisional and final migration is
  `053_acquisition_audit_permissions`.
- Unit 05 integration preserved the explicit-plan-only enrichment boundary from
  Unit 02, moved audit emission onto the durable enrichment operations, and
  repaired the conflicting legacy batch test accordingly.
- After Unit 05, the combined audit/publication/enrichment/evaluation/
  acquisition and migration suite is `78 passed`.
- Unit 06 integrated as `97fde2b1`; its provisional and final migration is
  `054_company_identity_reconciliation`.
- Unit 06 migration conflict resolution preserved migrations 050 through 053
  and kept the foundation test scoped to 049 through 051; the company
  reconciliation migration is covered by the dedicated company test.
- After Unit 06, the combined Wave 1 suite is `90 passed`.

## Dependency order

1. `050_collection_controls`: bounds acquisition requests/jobs and persists
   collection closure metadata.
2. Unit 03 deterministic evaluation: offline-only and migration-free; it
   extends the 049 enrichment contracts/fixtures without runtime activation.
3. `051_enrichment_operations`: depends on 049 enrichment evidence/cache state;
   remains report-only with zero external budgets.
4. `052_publication_policy_history`: depends on the acquisition publication
   surfaces and must preserve the current publication head.
5. `053_acquisition_audit_permissions`: wraps acquisition mutation surfaces
   with granular authorization and immutable audit recording.
6. `054_company_identity_reconciliation`: changes canonical company identity
   and reconciliation state after the authorization/audit surfaces are present.

## Integration acceptance rules

- Do not merge from recovery branches directly into production.
- Keep providers, AI, external datasets, and paid services disabled.
- Do not change publication heads or published jobs unless explicitly required;
  none of Wave 1 authorizes an automatic publication.
- After each unit: focused tests, combined regression tests, migration registry
  uniqueness/order checks, then an integration commit when repairs are needed.

## Production release baseline and recovery

- Production backend/API and worker commit before Wave 1: `0068a5f740d379e896d8f6831c3fa5fc63d434b9`.
- Production frontend commit before Wave 1: `95990b07b597723ceea826e9401d87b513158e9a`.
- Migration `049_enrichment_foundation` was applied in production; the
  production schema reported 49 applied migrations.
- Publication head before Wave 1: `acq_publication_8378ea4c5aa04ddc9362e4400bb088df`,
  updated/published `2026-08-12T00:10:53.292665+00:00`, with 163 published jobs.
- Recoverable pre-migration backup: `logical-wave1-direct-396c45deb36d95e0`,
  created `2026-08-12T18:36:46.135064+00:00` UTC, SHA-256
  `396c45deb36d95e084a745a7a22b43bdb81ba35fc6ff0c8ef66df5877444dc`,
  1,635,259 bytes, 1,490 rows across the directly modified tables. Restore
  verification passed at
  `C:\Users\ahmed\Projects_Local\runr-release-evidence\turso-prod-wave1-restore-verification.sqlite3`.

## Production deployment record

- `619c637925f9f4839723275d283ec34016869bd6` — Unit 01 collection controls;
  API and worker live. `050_collection_controls` applied.
- `43f2152296bbbf39a050056d51d43a87f6ec0849` — Unit 03 deterministic
  evaluation; migration-free API and worker live.
- `ef2ad6d3726358023418cf637235bad96accf798` — Unit 02 enrichment
  operations; API and worker live. `051_enrichment_operations` applied.
- `fd4709bb7f1aca4d992869cd423be3cb2c0a26ce` — first Unit 04 publication
  attempt; worker live but API pre-deploy failed before applying `052` because
  the recovered branch omitted the tested closing SQL-string repair.
- `6fd91cb281096d3f13147f4eb715ad0482292f11` — forward repair commit. API
  and worker live; `052_publication_policy_history`,
  `053_acquisition_audit_permissions`, and
  `054_company_identity_reconciliation` applied successfully. Render grouped
  the later integrator history into this one successful migration deploy.
- The API pre-deploy failure was diagnosed from Render logs as an unterminated
  migration SQL string, then repaired by `9fbf9e19` and the applied-051
  checksum-preserving fix `6fd91cb2`; the only redeploy was successful.
- Every post-deploy readiness check returned HTTP 200. Authenticated admin
  frontend calls recorded HTTP 200 for `/admin/acquisition/overview`,
  `/admin/acquisition/publication`, `/admin/acquisition/sources`, and
  `/admin/acquisition/connectors/capabilities`; no post-release frontend API
  failures were recorded.
- After the successful final deploy, all migrations 049 through 054 reported
  applied, the publication audit table was empty, the publication head remained
  `acq_publication_8378ea4c5aa04ddc9362e4400bb088df`, and the head contained
  163 jobs.
- Production configuration verification: company enrichment is `0`, live
  networking discovery is `false`, provider budgets remain zero, and no
  enrichment evidence was written. `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED`
  remains a pre-existing Render configuration value of `true`; the scheduler
  produced no-op cycles and no external collection occurred during Wave 1.
  This configuration drift remains an explicit release defect for follow-up.

## Wave 2 complete acquisition dashboard

- Incoming feature branch: `feature/complete-acquisition-dashboard`.
- Verified implementation commit: `06a4cb174e5331bc07645b7e1dabf534d96e161e`.
- Base verification: `2b87bfc5ca8e5b73a95ea924fa73df64692b53a7` is an ancestor;
  the diff contains only the authorized acquisition API, application service,
  frontend dashboard/navigation, frontend operation helper/test, and admin
  dashboard regression test files.
- No migration was added; no migration identifier was reserved or applied.
- Focused backend and Wave 1 regression suite: `94 passed`.
- Frontend suite: `157 passed`; ESLint passed; Vite production build passed.
- Ruff passed. The full Python suite remains unclaimed because the submitted
  validation timed out; the focused release suite is green.
- Pre-release backup artifact re-hash and restore verification were repeated:
  `logical-wave1-direct-396c45deb36d95e0`, timestamp
  `2026-08-12T18:36:46.135064Z`, SHA-256
  `396c45deb36d95e084a745a7a22b43bdb81ba35fc6ff0c8ef66df5877444dc`;
  restore counts matched the recorded 49-migration baseline. Since this unit
  is migration-free, no production migration operation is required.

## Wave 2 production verification

- Production branch push: `3c5e609a` (`06a4cb17` plus the integration ledger).
- API readiness: `https://runr-api.onrender.com/health/ready` returned HTTP 200
  with production Turso/libSQL and R2 configured.
- Frontend: `https://app.userunr.com` served the new dashboard bundle
  (`assets/index-BygCU6S-.js`) and rendered the expanded navigation.
- Worker: authenticated Overview read model reported `Online` / `ONLINE`.
- Authenticated routes tested: overview, sources, imports and import detail,
  jobs, job inspection, companies and company inspection, enrichment, data
  quality, duplicates, publication, live catalog, and audit.
- State coverage: loading indicators were observed during slow reads; empty
  results were verified with an unmatched source filter and the empty duplicate
  queue; partial/unknown values were visible in company and enrichment views;
  no authenticated request rendered an error alert.
- Jobs source filter: `source=n26_greenhouse` returned a normal result; an
  unmatched source returned the explicit empty state and no SQLite/no-such-table
  error. Pagination moved from page 1 to page 2 while preserving query state;
  inspection opened and Escape closed without losing the URL filters.
- Publication safety: the page remained manual-only; no preview, publish, undo,
  restore, import, enrichment, duplicate, or reconciliation mutation was sent.
- Publication head before and after: `acq_publication_8378ea4c5aa04ddc9362e4400bb088df`,
  163 jobs, unchanged.
- Desktop browser evidence was captured at the connected browser viewport
  `1272x549`, including the expanded navigation and Overview read model.
  The connected browser surface exposes no viewport resize/device-emulation
  capability, so an independent 390px mobile browser run remains outstanding;
  the responsive horizontal navigation and mobile drawer behavior are covered
  by the shipped responsive classes and local build, but not live device
  emulation.
- Render control-plane deploy IDs/logs could not be queried because the
  configured `RENDER_API_KEY` returned HTTP 401. Live API readiness, the new
  frontend asset, authenticated dashboard routes, and worker Online state were
  used as deployment evidence.

## Wave 3 read-only acquisition analytics

- Implementation branch: `feature/admin-analytics-final-production`.
- Implementation commit: `12f342fb8964685682e264188a971d03b88a4af9`.
- Verified base: `6a01d2cc24ed68bc0dabd1805ee37b51fdf709a0`, the current
  `deployment/render-turso-r2` production history before this integration.
- Authorized scope: read-only acquisition analytics API and admin UI,
  URL-backed 24-hour/7-day/30-day windows, bounded custom timestamps, and
  read-performance indexes. No provider, AI, publication, reconciliation, or
  paid-service activation was authorized.
- Migration reserved centrally: `055_acquisition_analytics_indexes`.
  Registry verification passed: all migration identifiers are unique and in
  numeric order; `055` is additive index creation only.
- Dependencies: existing acquisition/enrichment/publication/audit/company
  tables and migrations `049` through `054`; all are present in the
  integration history and the verified production backup baseline.
- Changed paths matched the recovery report exactly: the analytics module,
  admin route/service/migration registry, two frontend route/navigation/page
  surfaces, and `tests/test_acquisition_analytics.py`.
- Integration validation: combined backend regression `98 passed in 45.28s`;
  frontend check `157 passed`, ESLint passed, Vite production build passed;
  Ruff and Python compilation passed. Full backend suite is not claimed because
  the submitted full-suite run exceeded its execution limit without a result.
- Pre-migration backup re-verification: reused
  `logical-wave1-direct-396c45deb36d95e0`, timestamp
  `2026-08-12T18:36:46.135064Z`, SHA-256
  `396c45deb36d95e084a745a7a22b43bdb81ba35fc6ff0c8ef66df5877444dc`,
  1,635,259 bytes. Restore verification artifact exists and matches the
  recorded 49-migration baseline counts. No database write has been performed
  by this integration before deployment.
- Deployment: pending production push and Render rollout.
- Smoke test: pending.
- Unresolved release visibility defect: the supplied Render API credential
  returns HTTP 401, so Render deploy IDs/logs cannot be inspected; Docker is
  unavailable locally. The reported base-commit build failure is therefore not
  source-reproducible or independently log-verifiable. Local source, Python,
  frontend, and migration checks pass; no speculative Docker/configuration
  change was made.

## RC-022 scoped release contract

- Target branch: `deployment/render-turso-r2`.
- Scoped commit: this scoped RC-022 commit; Git records the final SHA.
- Release files: separate `Dockerfile.api` and `Dockerfile.worker`, runtime
  release metadata, Render build filters, CI API/worker image builds, and the
  systemd/VPS entrypoints.
- Compatibility contract: `runr-contract-v1`; migration head recorded as
  `058_customer_task_queue`.
- Frontend-only changes rebuild the static frontend without restarting API or
  workers. Shared backend/renderer/dependency changes rebuild the affected
  runtime images.
- Offline verification: RC-022 focused suite `6 passed`; combined RC-001--021
  regression `255 passed, 8 subtests`; frontend suite `167 passed`; frontend
  production build passed; Ruff and diff checks passed.
- Docker image builds and mixed-version staging remain pending because the
  local Docker Linux daemon was unavailable. No deployment, migration, or
  provider request was performed for RC-022.

## Wave 3 deployment hold

- Production branch push completed: `deployment/render-turso-r2` points to
  `d969f43b3466e776025cad3130ecf96e63fce20a`, whose parent is the analytics
  implementation commit `12f342fb8964685682e264188a971d03b88a4af9`.
- Render accepted the auto-deploy event for `runr-api`, `runr-worker`, and
  `runr-frontend`, but each deployment for `d969f43` is `Build blocked` because
  the workspace has run out of pipeline minutes. The last live deployment for
  all three services remains `3c5e609acd9661d4f114e0f487bd9fb15f4dabbe`.
- The pre-existing API readiness endpoint still returns HTTP 200, and the
  authenticated pre-deploy live-catalog baseline still reports the unchanged
  publication head and 163 jobs. The frontend still serves the pre-analytics
  bundle `/assets/index-BygCU6S-.js`; the analytics route is not live.
- `055_acquisition_analytics_indexes` was not applied because the API
  pre-deploy/build never ran. No production database write, provider call, AI
  call, publication, or mutation was performed by Wave 3.
- Deployment smoke tests are pending the external Render pipeline-minute
  constraint. No repair or redeploy commit was created; the local source and
  release checks are green. This hold requires Render workspace authority or
  restored pipeline capacity.
