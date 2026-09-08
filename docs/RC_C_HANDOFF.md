# RC-C release and integration handoff

Status: offline RC-022 release/staging contract preparation. This handoff does
not claim Docker image builds, host provisioning, mixed-version staging, live
acquisition, a production migration, a Render deployment, or a GitHub push.

## Candidate and ownership

| Item | Verified value |
| --- | --- |
| C worktree | `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview-rc-c-release-integration` |
| C branch | `temp/rc-c-release-integration` |
| C starting launch commit | `b0f47788c1a5d385ae4c3c770d5cd990f586a626` |
| C current candidate | `9003fabc9fba9e2b7449d03b912d991c4bbdc873` |
| Persistent integration target | `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview` |
| Persistent target branch | `deployment/render-turso-r2` |
| Persistent target before this slice | `9003fabc9fba9e2b7449d03b912d991c4bbdc873` |
| Shared launch base | `b0f47788c1a5d385ae4c3c770d5cd990f586a626` |

C was created from the exact S0 launch commit, then fast-forwarded over the
target's documentation-only manifest commits so a later accepted C commit can
fast-forward the persistent target. A/B have no implementation commits at this
checkpoint; both remain clean at the shared launch commit and are not merged by
this handoff.

## RC-022 verification

The repository-required interpreter was verified before testing:

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' --version
# Python 3.12.7
```

The focused release/runtime regression was run from this C worktree:

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest -q tests/test_rc022_build_release_contract.py tests/test_database_migrations.py tests/test_acquisition_runtime_manifest.py tests/test_worker_service.py
# 43 passed, 4 subtests passed in 75.27s
```

The RC-022-only evidence already recorded in
`docs/RC022_BUILD_RELEASE_STAGING.md` is `6 passed`. The current combined run
also covers the migration registry, acquisition runtime-manifest validator and
worker role/service behavior.

Verified offline:

- frontend-only, API/worker-shared, worker-only and all-service path impact;
- release metadata schema `runr.release.v1`, commit/branch precedence and
  explicit `unknown` fallback;
- exact protocol compatibility `runr-contract-v1`;
- separate API and worker Dockerfiles, non-root `runr` user and retained
  browser/OCR/office dependencies;
- Render's separate API/worker images and CI Docker build selection;
- migration registry ordering and the read-only acquisition data-manifest
  validator;
- `deploy/start.sh` role selection and customer/acquisition worker role
  normalization.

Still environment-gated:

- Docker image builds: the local Docker Linux daemon was unavailable;
- Render/CI path-filter execution in the provider environment;
- isolated mixed-version staging with separate queues, object keys, secrets and
  databases/namespaces;
- host restore of the authoritative acquisition state, because the documented
  producer-state artifact is not present in the current local checkout;
- any provider, live acquisition, R2, Turso or production migration action.

## Exact runtime commands and roles

The existing entrypoint is the source of truth. It does not pull Git, build the
frontend, or run migrations for a worker.

API command:

```sh
RUNR_ENV=staging RUNR_RELEASE_BRANCH=temp/rc-c-release-integration RUNR_RELEASE_COMMIT=<candidate-sha> RUNR_RELEASE_CONTRACT_VERSION=runr-contract-v1 RUNR_MIGRATION_HEAD=058_customer_task_queue RUNR_DATA_DIR=/srv/runr/app-data RUNR_STORAGE_BACKEND=sqlite ./deploy/start.sh api
```

Customer worker command:

```sh
RUNR_ENV=staging RUNR_RELEASE_BRANCH=temp/rc-c-release-integration RUNR_RELEASE_COMMIT=<candidate-sha> RUNR_RELEASE_CONTRACT_VERSION=runr-contract-v1 RUNR_MIGRATION_HEAD=058_customer_task_queue RUNR_WORKER_VERSION=<candidate-sha> WORKER_ROLE=customer WORKER_ID=runr-staging-customer-<candidate-id> RUNR_DATA_DIR=/srv/runr/app-data RUNR_STORAGE_BACKEND=sqlite ./deploy/start.sh worker
```

Acquisition worker command:

```sh
RUNR_ENV=staging RUNR_RELEASE_BRANCH=temp/rc-c-release-integration RUNR_RELEASE_COMMIT=<candidate-sha> RUNR_RELEASE_CONTRACT_VERSION=runr-contract-v1 RUNR_MIGRATION_HEAD=058_customer_task_queue RUNR_WORKER_VERSION=<candidate-sha> WORKER_ROLE=acquisition WORKER_ID=runr-staging-acquisition-<candidate-id> RUNR_DATA_DIR=/srv/runr/app-data RUNR_STORAGE_BACKEND=sqlite ./deploy/start.sh worker
```

`customer` may claim only the customer task family; `acquisition` may claim
only the acquisition task family. Worker IDs must be unique and role-specific.

Only the API release owner runs the migration once for an isolated staging
database or namespace:

```sh
RUNR_ENV=staging RUNR_RELEASE_BRANCH=temp/rc-c-release-integration RUNR_RELEASE_COMMIT=<candidate-sha> RUNR_RELEASE_CONTRACT_VERSION=runr-contract-v1 RUNR_MIGRATION_HEAD=058_customer_task_queue ./deploy/start.sh migrate
```

The worker image and worker command must not run migrations. The registry is
applied contiguously in this order:

```text
054_company_identity_reconciliation
055_acquisition_analytics_indexes
056_phase_a_scheduler_fencing
057_phase_e_intelligence_recovery
058_customer_task_queue
```

## Input, state and artifact mounts

These mounts are the required VPS/staging contract. They were not mounted or
copied by C:

| Mount | Access | Contents and owner |
| --- | --- | --- |
| `/srv/runr/shared/inputs` | read-only to workers | committed seeds plus RC-005 manifest and raw sidecar |
| `/srv/runr/state/linkedin` | read/write acquisition owner only | authoritative 14-table LinkedIn state and checkpoints |
| `/srv/runr/state/employer` | read/write acquisition owner only | employer producer state |
| `/srv/runr/state/enrichment` | read/write only for explicit enrichment | RC-006b resolver state; not first-start input |
| `/srv/runr/exports` | write acquisition/export owner; read publication step | bounded materializations and generation manifests |
| `/srv/runr/backups` | write backup owner; restricted read | immutable SQLite/object/checkpoint backup generations |
| `/srv/runr/app-data` | disposable application cache only | local cache, not durable Turso or customer artifact authority |

Turso/database and R2 credentials are injected by secret name and role scope;
they are not files in these mounts. Customer OAuth, document, email and billing
secrets must not be inherited by acquisition/browser processes.

## State/output separation blocker

The current `scripts/run_manifested_linkedin.py` and
`scripts/run_manifested_employer.py` accept one `--output-dir`. The low-level
producers create their SQLite state below that output directory, while the
runtime manifest specifies separate `/srv/runr/state/*` and
`/srv/runr/exports/*` roots. This command is therefore only a dry-run contract
example, not proof of the production mount layout:

```sh
python scripts/run_manifested_linkedin.py --manifest /srv/runr/shared/inputs/SOURCE_ELIGIBILITY_MANIFEST_RC005_RECONCILED.json --output-dir /srv/runr/exports/linkedin --mode validate --dry-run
```

The narrow proposal for B/producer ownership is an explicit state-dir
parameter/configuration in the producer wrappers and tests, preserving the
14-table producer behavior while placing `master_*_jobs_state.db` under the
role-owned state mount and materializations under exports. An alternative is a
reviewed state/output co-location contract, but it must then replace the
current split-root claim. C does not rewrite the producer in this release-only
slice or silently use a symlink. RC-024 host verification is blocked until the
owner accepts one option and supplies a committed regression.

## Version compatibility and staging isolation

The compatibility contract is `runr-contract-v1`; metadata is
`runr.release.v1`; the current migration head is `058_customer_task_queue`.
Release commit/branch values come from explicit `RUNR_RELEASE_*` values first,
then Render values, and otherwise remain visibly `unknown`. A previous/current
image pair is compatible only when both advertise the exact same contract.

No new Render service, provider namespace, bucket, queue or environment group
is introduced by this handoff. If staging infrastructure is authorized, use
distinct names/prefixes such as:

```text
runr-staging-api
runr-staging-customer-worker
runr-staging-acquisition-worker
runr-staging-turso
runr-staging-r2/<candidate-sha>/
runr-staging-customer-queue
runr-staging-acquisition-queue
```

Set `RUNR_PRIVATE_TEST_DEPLOYMENT=true`, `RUNR_ENV=staging`, unique worker IDs,
the candidate branch/SHA, the exact contract version and migration head above,
and staging-only Turso/R2, billing/email/OAuth/Clerk/ScrapeOps/DeepSeek and
analytics targets. Offline contract checks keep live networking, enrichment
and provider credentials disabled. A real-source pilot is RC-027 and requires
its separate authorization.

When Docker is available, build both runtime images from one clean candidate:

```sh
docker build --file Dockerfile.api --build-arg RUNR_RELEASE_COMMIT=<candidate-sha> --build-arg RUNR_RELEASE_BRANCH=temp/rc-c-release-integration --build-arg RUNR_RELEASE_SERVICE=api --tag runr-api:<candidate-sha> .
docker build --file Dockerfile.worker --build-arg RUNR_RELEASE_COMMIT=<candidate-sha> --build-arg RUNR_RELEASE_BRANCH=temp/rc-c-release-integration --build-arg RUNR_RELEASE_SERVICE=worker --tag runr-worker:<candidate-sha> .
```

The five required synthetic/private mixed-version checks are: previous API and
worker against the backward-compatible schema; new API with previous worker
for queue/status/artifact/signed-download behavior; new worker with previous
API for disjoint role claims; frontend-only metadata without worker restart;
and rejection of `runr-contract-v0` before any task claim. No result is claimed
until the external staging environment exists and the exact candidate/image
digests are recorded.

## Dependency checkpoints and integration procedure

- RC-023/024/025 must be accepted before RC-026; RC-026 must be accepted before
  RC-027; RC-027 is the pilot baseline before RC-028/029.
- B must provide a freeze message and exact clean committed tip before C merges
  B's runtime/backup/benchmark slice. C merges sequentially, preserves
  ancestry, resolves inspected conflicts, runs combined tests and reports the
  accepted SHA.
- A follows the same freeze/merge/test procedure. C owns conflicts in shared
  routes, the migration registry, worker entrypoints, `render.yaml` and release
  files.
- The persistent target is advanced only from its own clean checkout using
  `git merge --ff-only <accepted-c-sha>` after verifying the target tip is an
  ancestor. No force-update, squash or default cherry-pick is permitted.
- GitHub push is deferred to RC-033. Since `render.yaml` uses
  `autoDeployTrigger: commit`, a target push is a deployment trigger and is not
  part of a routine integration checkpoint.

## Rollback and blockers

Before target advancement, rollback is to leave the target unchanged. A
committed C documentation/integration slice is reversed with a reviewed
`git revert`, never a reset on a checked-out branch. Temporary worktrees are
removed only after clean status and commit preservation are verified, without
`--force`.

Current blockers are the unavailable Docker Linux daemon, the absent documented
approximately 3.48 GB 14-table LinkedIn state, the producer state/output
separation decision, and the absence of authorized staging namespaces,
credentials, R2 CORS, host or live-pilot infrastructure. No external
infrastructure was created.
