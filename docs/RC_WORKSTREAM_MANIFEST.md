# Runr acquisition workstream manifest

## Producer repair integration amendment - 2026-09-09

The supplied final producer tips were verified clean and merged into C in
sequence. A's final tip is `5c100043d51e616e2de4fb595f362d951d70e30d` with
implementation `9ac2ab4182c66d1aecdb6150574fdce6012153ca`, merged as
`a10f3e4c559c8ea05c4d458135f487831797c8a5`. B's final tip is
`7f03dd89cdb2d1a1d724fb1bc221cfe8e74707fd` with implementation
`c98603a51c2775512e49ccb2d54a4adbe731ddb7`, merged as the current C tip
`3882806d44731efe1cafdf12ab11389bf9233b07`.

Both final tips descend from the earlier integrated code tip
`5cd2ece533e4e7615a8b6a7b08516014d5b82748`; B branched before C's later
documentation-only commits. The merges preserve A/B ancestry and C's
operational evidence. The exact backend gate passed 427 tests with only the
two unchanged baseline tracker failures; Ruff, compilation and diff checks
passed. The target frontend passed 170 tests and the Vite build was stamped
with candidate `466541b3...`. No repair lane consumed new live budget or
changed VPS state.

## Repair-candidate live verification amendment - 2026-09-09

Candidate `466541b3ee4a57a89f83c583f5e497b36fccdbe3` was staged on the VPS and
used for bounded diagnostic source runs. LinkedIn consumed 60 attempts on the
frozen four-company selection and remained `PARTIAL_SUSPICIOUS_EMPTY` for all
four; employer consumed 40 attempts but `--limit 0` selected all 1,574 rows,
so it is not frozen-cohort evidence. New usage is 100/200, no publication or
Turso write occurred, and acquisition remains disabled. This status is
recorded here so the manifest does not imply RC-027 acceptance.

## Current reconciliation amendment — 2026-09-09

The setup-time values below are historical. The current clean reconciliation
has verified and integrated the supplied lane tips without resetting or
copying uncommitted work:

| Item | Verified current value |
| --- | --- |
| Persistent target | `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview` |
| Target branch | `deployment/render-turso-r2` |
| C integration worktree | `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview-rc-c-release-integration` |
| C branch | `temp/rc-c-release-integration` |
| A frozen tip | `cac08985ecc3541d1b00f64fcaac28e6cbc2d427` |
| B frozen tip | `729495d56029508fc064e0ae4687cb5892dd3c38` |
| B startup-fix ancestor | `8a87df8f7abb02a46fe0249b391ffe75aa415174` |
| A merge commit in C | `4fed31be0f8d6315fecbd768fd2e69073f82519a` |
| B merge commit in C | `6d9620d19359770f0b119d2d8654445734bc96b4` |
| Combined implementation tip before this amendment | `5cd2ece533e4e7615a8b6a7b08516014d5b82748` |
| Current clean C/target tip with reconciliation evidence | `628e63afbec4425989467251d77d405d3a7064a7` |

Both lane worktrees were clean at their frozen tips. A and B are now
required to create their next repair commits from the resulting clean C
tip, using separate worktrees and captured evidence only. A owns the actual
LinkedIn producer repair; B owns the employer producer repair. C owns shared
scheduler, publication, API, configuration, migration, release and staging
contracts. Neither repair lane may consume the remaining live request budget
or change VPS state independently.

The RC-029 fixture source-name mismatch found after integration was corrected
in `5cd2ece533e4e7615a8b6a7b08516014d5b82748`; the canonical contract uses
`employer_site`, not the shorthand `employer`. The combined regression then
passed 310 tests with the two independently reproduced tracker/API baseline
failures excluded.

Historical setup status: setup manifest for the next offline workstreams; no deployment, live
acquisition, provider request, production migration, or target-branch push was
performed by this setup.

## Persistent integration destination

| Item | Verified value |
| --- | --- |
| Persistent target path | `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview` |
| Final integration branch | `deployment/render-turso-r2` |
| Upstream | `origin/deployment/render-turso-r2` |
| Remote fetch/push identity | `https://github.com/ahmedkaddah99-commits/Linkedin-Jobs-Scrapper.git` |
| HEAD at setup | `30ef992b7945ff0998704a550fdc2f893b24476f` |
| Target divergence after confirmed fetch | `0 ahead / 0 behind` |
| Common implementation base | `30ef992b7945ff0998704a550fdc2f893b24476f` |
| Manifest setup commit | `9cbc6fc1becdf44a82f500dc3c2937b61b9729b3` |
| Common launch commit | `b0f47788c1a5d385ae4c3c770d5cd990f586a626` |

The target path above is the persistent destination for final integrated code.
The VS Code target checkout is already on the final integration branch. The
historical source worktree at
`C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper`
remains a preserved source/reference worktree on
`feature/admin-analytics-final-production`; it is not an integration target.

## Reserved isolated workstreams

These sibling paths do not currently exist as registered worktrees, and the
branch names are not currently present. They are reserved for worktrees created
from the exact common launch commit after this manifest is committed:

| Lane | Branch | Reserved sibling worktree | Owner |
| --- | --- | --- | --- |
| A | `temp/rc-a-observability-growth` | `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview-rc-a-observability-growth` | Operational UI/API, coverage visibility, later analytics |
| B | `temp/rc-b-vps-runtime` | `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview-rc-b-vps-runtime` | VPS/runtime, backup/restore, benchmark and capacity preparation |
| C | `temp/rc-c-release-integration` | `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview-rc-c-release-integration` | Release/staging, migrations and serialized shared integration |

Every lane must resolve the final manifest/launch commit, verify its own
worktree path and branch, and keep runtime data outside the disposable
worktree. No lane may use the persistent target checkout as its editing
directory.

## Ownership boundaries

Ownership is based on the actual files present at the common base and the
ticket scopes in `docs/RUNR_VPS_ACQUISITION_PLAN.md`.

### Lane A — observability, operational UI/API and analytics

Lane A owns RC-025 offline dashboard/fixture work and the optional, independent
RC-030 analytics audit/implementation when its plan dependencies are met. Its
starting surfaces are:

- `backend/acquisition/analytics.py`, `backend/acquisition/audit.py`,
  `backend/acquisition/quality.py`;
- `backend/api/routes/acquisition_admin.py` and the bounded operational API
  surface;
- `frontend/src/admin/**`, `frontend/src/pages/AcquisitionOperationsPage.jsx`,
  `frontend/src/pages/AdminAcquisitionAnalyticsPage.jsx`,
  `frontend/src/pages/AdminAcquisitionPage.jsx`,
  `frontend/src/pages/AdminEventsPage.jsx`, and
  `frontend/src/pages/AdminScrapeOpsPage.jsx`;
- `frontend/src/lib/acquisitionOperations.js`, analytics helpers, and their
  focused tests;
- operational dashboard fixtures and reports under `tests/fixtures/`,
  `tests/test_acquisition_analytics.py`, relevant audit/quality tests, and
  ticket documentation.

Lane A must hand shared route, migration, release, worker-entrypoint, or
`render.yaml` changes to Lane C as a patch request. It must not change the
actual 14-table LinkedIn producer or VPS deployment files.

### Lane B — VPS/runtime, backup/restore and benchmark preparation

Lane B owns RC-023 runtime definition and authorized host preparation, RC-024
checkpoint/restore design and drills, and RC-026 benchmark/cost evidence after
its prerequisites are integrated. Its starting runtime surfaces are:

- `deploy/deploy.sh`, `deploy/setup.sh`, `deploy/start.sh`,
  `deploy/systemd/**`, and `deploy/validate_acquisition_runtime.py`;
- `scripts/benchmark_acquisition_baseline.py` and new bounded backup/restore
  or benchmark helpers;
- runtime/backup/benchmark documentation and focused tests;
- runtime role configuration only where it is isolated from the shared worker
  claim/service contract.

`backend/worker/service.py`, `backend/worker/roles.py`,
`backend/repositories/sqlite_migrations.py`, `render.yaml`, and shared API or
application entrypoints are not independently owned by B. B submits changes to
those files to C for serialized integration. VPS purchase/provisioning, live
ports, provider requests and live benchmarks remain separately authorized
actions; offline preparation does not mark RC-023/024/026 complete.

### Lane C — release, staging, migrations and integration

Lane C owns RC-022 release/staging completion, release evidence, staging
contracts, migration ordering and the final integration of A/B changes. Its
shared-file ownership includes:

- `Dockerfile*`, `.github/workflows/ci.yml`, `render.yaml`,
  `backend/deployment/**`, `frontend/package.json`, and release metadata;
- `backend/repositories/sqlite_migrations.py` and migration-related tests;
- shared integration surfaces including `backend/api/server.py`,
  `backend/application/services.py`,
  `backend/application/run_services.py`, `backend/worker/service.py`, route
  registries, and common worker/queue entrypoints;
- `docs/RC022_BUILD_RELEASE_STAGING.md`, release ledgers, integration status
  handoffs and combined regression evidence;
- serialized staging/pilot and release changes for RC-027, RC-028, RC-029 and
  RC-032, subject to their actual plan gates.

Lane C is the only lane that resolves overlapping hunks, assigns migration
identifiers, or changes the common release contract. A/B changes to shared
files must arrive as a narrowly scoped patch request with tests and no
wholesale file replacement.

The actual LinkedIn producer remains owned by its completed RC-013/014/015
lineage. No lane may replace `scripts/master_linkedin_jobs_catalog.py` with
`scripts/master_linkedin_jobs_url_catalog.py`.

## Current ticket/dependency map

RC-022 is implemented offline at the common base. Its remaining evidence is
Docker-capable image building, path-filter execution and isolated mixed-version
staging; it does not require RC-006b. RC-023 is the first genuinely unfinished
ticket in the current status handoff.

| Ticket | Plan scope/status at launch | Actual dependency and next offline action |
| --- | --- | --- |
| RC-023 | VPS runtime; not started | Depends on RC-002 and RC-018. B may prepare pinned runtime, systemd/Compose choice, resource/port/credential contract; provisioning and live checks remain authorized operations. |
| RC-024 | Checkpoint, restore and single-owner state; not started | Depends on RC-015, RC-016 and RC-023. B may design backup/checkpoint/restore and ownership tests; use SQLite Online Backup/`VACUUM INTO` with a quiesced owner, never a raw live DB copy. |
| RC-025 | Operational visibility and coverage dashboard; not started | Depends on RC-005, RC-016, RC-018 and RC-019. A may build offline status/partial/failure/coverage fixtures and UI/API behavior. |
| RC-026 | Full-state benchmark/cost tuning; not started | Depends on RC-012, RC-014, RC-015, RC-021, RC-024 and RC-025. B waits for comparable integrated state and approved live samples before claiming capacity or cost evidence. |
| RC-027 | Controlled staging pilot; not started | Depends on RC-010–017, RC-019 and RC-022–026. C coordinates only after both collectors, recovery, runtime and release contracts are integrated; real sources require explicit authorization. |
| RC-028 | Paid-worker cutover/rollback; not started | Depends on RC-027 and production authorization. Gate A acquisition and Gate B customer migration remain separate. |
| RC-029 | Full eligible list in controlled waves; not started | Depends on RC-005, RC-026 and RC-028 Gate A; RC-006 only for cohorts needing enrichment. Requires declared manifests, budgets and stop conditions. |
| RC-030 | Optional P2 product analytics; not started | Depends on RC-022 and RC-025. A may perform the read-only audit/offline contract while keeping it independent of hosting migration success. |
| RC-031 | Trigger-based horizontal capacity; not started | Depends on RC-024, RC-026 and RC-028. Do not start unless measured queue/recovery/capacity evidence triggers it. |
| RC-032 | Final operational handover; not started | Depends on RC-028 and RC-029; RC-030/031 only if enabled. C coordinates the final evidence/runbook integration. |

Integration checkpoints:

1. Launch A/B/C only from the exact launch commit recorded below.
2. A and B may develop non-overlapping offline slices; C receives reviewed
   patches one at a time and updates the integrated target base.
3. Migration identifiers remain contiguous and ordered through
   `058_customer_task_queue` (`054_company_identity_reconciliation`,
   `055_acquisition_analytics_indexes`, `056_phase_a_scheduler_fencing`,
   `057_phase_e_intelligence_recovery`, `058_customer_task_queue`). C owns any
   future registry change.
4. C runs the affected focused suites plus the relevant combined regression
   after each integration; only the integrated deployment branch can receive a
   Done claim.
5. RC-027/028/029/032 remain release-gated and are not implied by offline
   worktree preparation.

## Preserved data, secrets and unrelated work

The target `git status --short --untracked-files=all` was empty before this
manifest. No stash was created, no blanket add was used, and no unrelated file
was staged. The target's ignored inventory includes caches, `frontend/node_modules`,
`frontend/dist`, `.backend_storage`, `.backend_test_tmp`, `logs`, local user
assets and the ignored `Jobs-Urls` directory. These remain in their persistent
target/source locations and are not copied into disposable worktrees.

The authoritative source inputs and available runtime evidence are preserved
outside the disposable worktrees in the locations recorded by
`docs/ACQUISITION_RUNTIME_DATA_INVENTORY.md`, including:

- `C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\Company-Urls\...`
  for source inputs and enrichment evidence (confirmed present);
- `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\feature-worktree-recovery\jobs-urls-preserved\Jobs-Urls\...`
  for the verified 147-file Jobs-Urls preservation copy, including the
  authoritative LinkedIn and employer state;
- `C:\Users\ahmed\Projects_Local\runr-release-evidence\...` for the recorded
  Turso restore-verification artifact (confirmed present).

The previously documented source-worktree path was stale. The preservation
copy has 147 files, 9,611,859,565 bytes and zero hash mismatches according to
`C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\feature-worktree-recovery\jobs-urls-preserved-verification.csv`.
The original moved directory remains under
`C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\feature-worktree-recovery\jobs-urls-source-quarantine\`.
The authoritative database files are still external restore inputs: they have
not been copied into the target or any disposable worktree.

No active SQLite database was copied during setup. Future copies must stop or
quiesce the owning writer and use the SQLite Online Backup API or an equivalent
consistent backup operation, then checksum the result; never copy a changing
`.db` file or its WAL/SHM files directly. Secrets remain environment/secret
store material and are not part of any worktree.

The source worktree remains preserved at
`C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper` on
`feature/admin-analytics-final-production`, HEAD
`ce3718b082b248030ea9bd72575b98fb02b594cf`, locally 16 commits ahead of its
remote. Its ordinary push was rejected by GitHub because its local history
contains oversized dataset blobs; that branch is not used as a workstream base
and was not rewritten. Existing prunable detached Cline worktrees listed by
`git worktree list` are unrelated and are left untouched.

## Render/GitHub deployment boundary

`render.yaml` sets `autoDeployTrigger: commit` for the linked Render services;
a commit pushed to `deployment/render-turso-r2` can trigger Render deployment.
During workstream setup and offline implementation, do not push the target
branch. The supported documented prevention is to work on the temporary branch,
push that branch only when authorized, use its Render preview/PR deployment for
verification, and merge to `deployment/render-turso-r2` only after the intended
release gate. No external service was disabled and no deployment was triggered
by this setup.

## Evidence already relevant

- RC-022 focused contract suite: `6 passed`.
- Combined RC-001–021 regression recorded in the current handoff:
  `255 passed, 8 subtests`.
- Frontend verification recorded in the handoff: `167 passed`, ESLint passed,
  and Vite production build passed.
- RC-022 Docker image builds and mixed-version staging remain pending because
  the local Docker Linux daemon was unavailable.
- Target branch was refreshed from the confirmed upstream and remains clean at
  the common implementation base. No live acquisition/provider requests,
  production migration or deployment was performed here.

## Launch commit record

The first scoped manifest commit was
`9cbc6fc1becdf44a82f500dc3c2937b61b9729b3`. The SHA-record amendment
`b0f47788c1a5d385ae4c3c770d5cd990f586a626` is the common launch commit used
by all three created worktrees. This final handoff-record commit is
documentation-only; it must not change the A/B/C launch base.
