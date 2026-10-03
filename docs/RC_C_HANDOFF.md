# RC-C release and integration handoff

## Repair completion checkpoint - 2026-09-10

Executable code: `2ab1da7fdd9883e86adca726335427ac91244c4b`. The preceding
current-tip labels below are historical. C integrated explicit cohort scope,
budget deferral, missing Python Playwright/Chromium, real route.request API,
safe partial/empty browser outcomes, homepage-first discovery, separate proxy
authentication, timeout observation preservation, and direct-first browser
fallback. All A/B ancestry is retained.

Verification: 222 combined producer, discovery, scheduler, worker and runtime
tests plus four subtests passed before the last two narrow changes. The latest
timeout/direct-first changes passed 65 focused producer/fallback/adapter tests.
Ruff passed. The real browser fixture extracted one job and counted one
loopback navigation under runr-acquisition and systemd restrictions. The
latest systemd fixture used code `38d59eba`, invocation
`ee76f660573d496dacff6975b165dda3`, exited 0 in 8.198 seconds. This was a
browser-runtime check, not an unattended acquisition-cycle acceptance.

The existing host unit gained only
`/etc/systemd/system/runr-acquisition-worker.service.d/30-browser-runtime.conf`
with PLAYWRIGHT_BROWSERS_PATH=/ms-playwright. It remains inactive/disabled;
customer dotenv remains unreadable to the acquisition account. Host diagnostic
code archives are under `/opt/runr/releases/rc027-*`; the service's production
code was not promoted. No Render push, production SQL or publication occurred.

The user stopped further provider-credit diagnostics. The final collector was
terminated (exit -15); no acquisition-user process remains. There are 188
confirmed attempts plus a reserved 12 with unknown actual consumption. Do not
reuse the reservation or restart a source probe. See the pilot receipt for
per-company outcomes and persistent evidence paths.

Rollback: use reviewed Git reverts of the six repair commits in reverse order,
not resets. Leave the service disabled and preserve all state, exports and
archives. The added browser-path drop-in can be removed individually followed
by daemon-reload if reverting runtime configuration; do not remove other unit
overrides or bulk-uninstall host libraries. Installed browser dependencies do
not enable or start acquisition.

## Browser runtime correction - 2026-09-10

Read-only host evidence identifies `playwright_not_installed` on St. Vincenz's
three attempted targets. The Python collector imports Playwright, while the
Linux dependency file only installs the unrelated Node/browser tooling.
The runtime correction pins Python Playwright 1.60.0 (pyee 13.0.1, greenlet
3.5.5) and installs its matching Chromium under `/ms-playwright`, readable
by the acquisition role under systemd ProtectHome. This supplies an existing
collector dependency; no new provider, service, purchase or source request is
required. Verify it using a loopback fixture before real-source acquisition.

The captured four LinkedIn organization IDs match the frozen cohort. Eight
search pages share suspicious-empty body hash
`ea12acf875ac1dffa5de9dd8f5c5a54a41cf50370705c4694aef841aa2b28a36`;
successful preceding pages do not establish authoritative absence. Keep
these partial and closure-unsafe. Employer work after the 40-request cap must
be deferred without creating synthetic scans. The new allowance remains
100/200 used; this investigation used no additional source attempts.

## Final local candidate amendment - 2026-09-09

The final clean local candidate is
`83d508b5e227ebd820588d8d05b849d39f77d7bc` in both the C integration
worktree and persistent `deployment/render-turso-r2` checkout. It is a
documentation-only descendant of the previously pinned local candidate
`b27949ebe2e63eb1ce2a76a267a2e32b2c9221fc`, which descends from the staged
repair candidate
`466541b3ee4a57a89f83c583f5e497b36fccdbe3`; it is not deployed or pushed.

## Repair-candidate live verification amendment - 2026-09-09

Candidate `466541b3ee4a57a89f83c583f5e497b36fccdbe3` was staged in the
separate VPS release directory `/opt/runr/releases/rc027-466541b3`. The
repaired LinkedIn producer ran cycle 1 for the frozen four-company selection
at 60/60 attempts: 61 valid cards, 45 detail successes, 16 pending detail
retries, 45 jobs written, and all four scans `PARTIAL_SUSPICIOUS_EMPTY`. No
valid snapshot, closure or publication resulted.

The employer diagnostic used 40 attempts but is not frozen-cohort acceptance:
the wrapper's `--limit 0` selects all 1,574 eligible rows. It processed the
full manifest under budget, recorded 1,573 partial and one source-failed
status, zero jobs and zero publication. This invocation is retained as
diagnostic evidence and must not be described as the required four-company
cycle. New live usage is 100/200 attempts, with 100 remaining; the earlier
pilot's 190/200 remains a separate historical allowance. No Turso write,
migration, R2 object write or customer service change was made.

## Producer repair integration amendment - 2026-09-09

The supplied final producer tips were verified clean and merged into C with
ancestry-preserving, non-squashed merges. A's final tip
`5c100043d51e616e2de4fb595f362d951d70e30d` (implementation
`9ac2ab4182c66d1aecdb6150574fdce6012153ca`) was merged as
`a10f3e4c559c8ea05c4d458135f487831797c8a5`. B's final tip
`7f03dd89cdb2d1a1d724fb1bc221cfe8e74707fd` (implementation
`c98603a51c2775512e49ccb2d54a4adbe731ddb7`) was then merged as the code
integration tip `3882806d44731efe1cafdf12ab11389bf9233b07`. B branched from
`5cd2ece533e4e7615a8b6a7b08516014d5b82748`, before C's later documentation
commits; no C evidence was discarded.

The exact merged backend gate collected 429 tests: **427 passed and 2
failed**. The failures are unchanged from the untouched target baseline:
`BackendApiTests.test_tracker_api` expects the legacy motivation-letter ZIP
filename, and
`BackendApiTests.test_tracker_ats_detail_returns_persisted_read_only_diagnostics`
expects two ATS history rows but receives none. Ruff, `compileall` and
`git diff --check` passed. The persistent target was advanced only after this
verification.

The target dependency tree passed all **170 frontend tests** and a Vite
production build stamped with the exact candidate SHA. The C worktree's
interrupted-install dependency tree produced an environment-only React loader
failure; it was not used for acceptance. No lockfile changed.

## Reconciliation amendment - 2026-09-09

The supplied A and B tips were verified clean and integrated sequentially into
C. The combined implementation baseline before this amendment is
`e28aa5f2e065848679d2302841dbe1bde36be8cd`, with A merged as
`4fed31be0f8d6315fecbd768fd2e69073f82519a` and B merged as
`6d9620d19359770f0b119d2d8654445734bc96b4`. The RC-029 fixture source-name
mismatch was corrected in `5cd2ece533e4e7615a8b6a7b08516014d5b82748`.
Target, C, A and B are clean; A and B are both based on this same baseline
for their next captured-evidence-only producer repairs.

The merged regression command passed **310 tests, 22 subtests**, with only the
two independently reproduced pre-existing tracker/API tests excluded. The
clean target baseline reproduced those two failures exactly:

- `BackendApiTests.test_tracker_api`: expected the generated motivation-letter
  filename, received `Cover letter.txt`.
- `BackendApiTests.test_tracker_ats_detail_returns_persisted_read_only_diagnostics`:
  expected two persisted ATS attempts, received an empty history.

The integrated frontend passed **170 unit tests** and a Vite production build
with explicit release metadata for `deployment/render-turso-r2` and candidate
`e28aa5f2`. The locked install attempt `npm ci --no-audit --no-fund` stalled in
the Windows environment; ESLint's locked binary was therefore unavailable in
this checkout. The lockfile was not changed.

The VPS acquisition boundary was exercised on `runr-vps` / `vmd205749`:

- `/opt/runr/.env.acquisition` is `root:runr-acquisition`, mode `0640`; the
  acquisition user can read it, but cannot read `/opt/runr/.env`.
- The installed unit uses only `/opt/runr/.env.acquisition`, sets
  `RUNR_SKIP_PROJECT_DOTENV=1`, and keeps `RUNR_ACQUISITION_MAX_REQUESTS=0`,
  `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED=false` and
  `RUNR_ENABLE_LIVE_NETWORKING_DISCOVERY=false`.
- Its local object/cache roots were moved from the protected evidence tree to
  `/var/lib/runr/acquisition-data/{objects,cache}`. The parent log directory
  was minimally changed to `0751` so the dedicated log directory remains
  writable only by `runr-acquisition`.
- Start, restart and stop were exercised. Start and restart returned success;
  the service stayed active with `NRestarts=0` and `ExecMainStatus=0`. Journal
  evidence showed the scheduler kill switch blocked acquisition and zero
  collector/source lines. The unit was stopped afterward and remains
  disabled. Rollback copies are under
  `/var/lib/runr/rollback/rc027-boundary-20260909/`.

Production R2 was used only for the explicitly authorized immutable RC-027
receipt and its signed range read. The configured Turso URL/token still points
to the production database and no production SQL write or migration was made.
No isolated Turso namespace, dedicated R2 credential, or bucket CORS control
is available in the configured environment, so those gates remain explicit
external blockers. Render read-only visibility remains API/worker
`30ef992b7945ff0998704a550fdc2f893b24476f`, frontend
`7251ae297c55f7f6a4524181cdafb4648f7fdcde`, with API health HTTP 200; the
local candidate was not deployed.

The provider check was repeated by key name only: the authoritative env has
`TURSO_AUTH_TOKEN` and `TURSO_DATABASE_URL`, but no `TURSO_PLATFORM_TOKEN` or
`TURSO_ORG`; it has the existing S3/R2, Render and Webshare key names. The
configured Turso token can query the production database, while the prior
Turso organization-management probe returned HTTP 401. Turso's current API
documentation describes personal-account or organization database creation,
but requires a Platform API bearer token, account/organization slug and an
existing group. The precise blocker is therefore management credential and
namespace scope; this record does not infer that the Hobby plan itself forbids
a staging database.

The bounded RC-027 LinkedIn state also has a verified SQLite Online Backup
checkpoint and restore. Source
`/srv/runr/state/rc027-linkedin-6e9a1e9301ffca644aca916aad6fc8827e4a792d/master_linkedin_jobs_state.db`
was `770048` bytes with SHA-256
`ed94c1cd30095c3544adccabb028072b327885ccaf2e48630d3d4945213a59d5` and
SQLite integrity `ok`. Checkpoint
`linkedin-20260909T201035631862Z-e6d35734a371` produced a `770048` byte backup
with SHA-256
`d445e6c1a2dfb45d189c3ced3351406f867f49f3264f5375b07f078f26659356`.
Local and R2 restores were validated in new directories; the persistent local
checkpoint is under
`C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc027-20260909\offhost-linkedin\offhost-linkedin-20260909\`,
and the R2 keys are under
`rc027/checkpoints/linkedin/linkedin-20260909T201035631862Z-e6d35734a371/`.
This is pilot-overlay evidence, not acceptance of the preserved historical
state or replacement-host recovery.

The signed-URL CORS probe is explicitly negative: `GET` with origin
`https://app.userunr.com` returned `206` without any
`Access-Control-Allow-*` header, and `OPTIONS` returned `403` without CORS
headers. Server-side R2 object, HEAD, signing and range behavior passed, but
browser direct-download behavior is not verified.

Operator walkthrough for the current safe state:

1. Confirm `systemctl is-active runr-api runr-worker runr-frontend` and
   `systemctl is-enabled runr-acquisition-worker`.
2. Inspect acquisition health and kill-switch decisions with
   `journalctl -u runr-acquisition-worker` without printing environment values.
3. Review the manifest and raw sidecar under `/srv/runr/shared/inputs`, then
   inspect acquisition state, exports and staging SQLite under the candidate
   paths in `docs/RC027_LIVE_PILOT_RECEIPT_20260909.md`.
4. Treat partial/failed source results as unknown coverage; do not publish or
   close postings until both source snapshots are valid and closure-safe.
5. Use the admin analytics page only with an authenticated staging origin once
   one is provisioned; its read-only dashboard is not evidence of a live
   publication until the Jobs page returns the published rows.

## Current RC-027 amendment — 2026-09-09

This amendment supersedes the earlier RC-027 blocker wording below. The
authorized `runr-vps` access, clean-host setup, systemd runtime, migration
rehearsal, service health, synthetic customer run, controlled failure fixture,
and customer-worker restart/recovery have now been verified on `vmd205749`.
The current runtime candidate is
`6e9a1e9301ffca644aca916aad6fc8827e4a792d`; the worker-log-path correction is
included. The detailed record is
`docs/RC027_LIVE_STAGING_EVIDENCE.md`.

RC-027 is still **incomplete**, but the bounded real-source pilot has now run.
Both collectors executed for the four frozen companies over two cycles on the
authorized VPS, using 190/200 source/provider/browser attempts. All source
results were partial or failed, so no snapshot was valid or closure-safe and
the integrated transport withheld staging/public publication. The exact
producer and transport receipt is
`docs/RC027_LIVE_PILOT_RECEIPT_20260909.md`.

The existing production R2 bucket was used only for one small immutable
evidence receipt under the unique RC-027 prefix, per the user's explicit
instruction. Turso production was not written. R2 object/sign/range behavior
passed; dedicated bucket isolation, CORS, authenticated UI publication and
valid source acceptance remain pending. Acquisition remains inactive and
disabled.

The persistent target checkout is clean at the code-correction tip
`16c1215d` before this documentation amendment is committed. It must be
advanced only by verified fast-forward from the resulting clean C tip; nothing
is pushed or deployed.

Current read-only deployment visibility is separate from the local candidate:
the target is clean on `deployment/render-turso-r2`, the remote-tracking
deployment ref is `30ef992b7945ff0998704a550fdc2f893b24476f`, the VPS runs
`6e9a1e9301ffca644aca916aad6fc8827e4a792d`, and the public Render frontend
advertises `7251ae297c55f7f6a4524181cdafb4648f7fdcde`. The Render management
API is now authorized through the nested `user_config\.env`; it reports live
API/worker deploy `30ef992b7945ff0998704a550fdc2f893b24476f`, and the public
Render API health endpoint returns HTTP 200. The local target remains
undeployed.

## RC-027 prior offline gate result — superseded by the live-pilot receipt

The earlier offline gate result below is retained as history. It is superseded
for current status by `docs/RC027_LIVE_PILOT_RECEIPT_20260909.md`; the host and
Webshare access blockers were cleared for the bounded run, while Turso
isolation, dedicated R2 scope, browser UI/CORS and valid publication remain
unmet.

| Item | Verified value |
| --- | --- |
| Integrated code candidate for a future pilot | `d326726acab7fffbbf59e294629b8ef002437566` |
| C integration branch | `temp/rc-c-release-integration` |
| Persistent target branch | `deployment/render-turso-r2` |
| Persistent target before this handoff amendment | `360449885d2779c91ffa03f483fdfe5ff28d1f33` |
| A frozen tip integrated | `764e292a1c090cad7a8af8ba7828b299cb50af41` |
| B frozen tip integrated | `9e1df3420efa89f8d28b06b6184d86124fd58e66` |
| Integrated merge tips | A: `8b03e8d771c5b3c9e91b5d0aaeac1e55d216b1d4`; B: `a7683dc40cda20e35d121b0c0f5668f89b47a18b` |
| Contract / migration | `runr-contract-v1` / `058_customer_task_queue` |

The recorded reconciled manifest and raw sidecar were restored read-only from
the RC-023 preservation source. Their external file hashes match the runtime
inventory, and the packet freezes four canonical-ID-sorted dual-source
companies from its 1,574 eligible entities. The full manifest remains outside
Git and is not copied into application tables.

The pilot cannot safely start because the following required runtime access or
acceptance evidence is missing:

- isolated staging Turso URL/token, R2 endpoint/bucket/prefix and credentials;
- an authorized host with the candidate installed, role mounts, and elevation;
- accepted RC-023 host, RC-024 restore, RC-025 runtime dashboard, RC-026
  comparable live/cost gates, and RC-022 image/mixed-version staging proof.

The packet records the user-authorized cumulative request, concurrency, time,
and US$5 cost limits. The repository defaults remain disabled until isolated
staging secrets and the host runtime exist. RC-006b remains separate and was
not started.
The R2 signed-download/CORS checks remain offline-only; no real bucket or
browser origin was available for live verification.

The only integration correction in this pass is the RC-026 resource sampler's
handling of transient SQLite journal/WAL removal (`d326726a`). It does not
create pilot data or authorize external requests.

### RC-027 rollback

No staging database, provider state, R2 object, publication, migration or host
change was created. If this offline integration is rejected, preserve the
target checkout and use reviewed `git revert` operations for the exact
documentation commits (`36044988`, `06cfae6f`, `dc1670ab`) and the sampler correction
(`d326726a`) only after checking dependent ancestry. Do not reset, clean, or
restore over the integrated A/B merges. Any later pilot rollback must first
disable new acquisition claims, retain the newest verified publication and
checkpoint, and restore only a compatible release; never delete or overwrite
the historical source state.

Status: offline RC-022/023/024/025/026 integration and RC-027 gate review.
This handoff does not claim Docker image builds, host provisioning,
mixed-version staging, live acquisition, a production migration, a Render
deployment, or a GitHub push.

## Candidate and ownership

| Item | Verified value |
| --- | --- |
| C worktree | `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview-rc-c-release-integration` |
| C branch | `temp/rc-c-release-integration` |
| C starting launch commit | `b0f47788c1a5d385ae4c3c770d5cd990f586a626` |
| C accepted release candidate before this documentation amendment | `96869170a4d5e173b08c4fb0868a7c3c5503c32f` |
| C integration tip after RC-025 merge | `6ab6f31bec0977b6db2435920942a7d885ead66d` |
| C accepted integrated A/B candidate before this handoff amendment | `0cb1bddab10ab4b572f17df8b5af2aadf38274d5` |
| C final accepted integrated tip before this handoff amendment | `9d837e2d56930715db1de22f191644531c2c00b8` |
| Persistent integration target | `C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview` |
| Persistent target branch | `deployment/render-turso-r2` |
| Persistent target before this slice | `9003fabc9fba9e2b7449d03b912d991c4bbdc873` |
| Shared launch base | `b0f47788c1a5d385ae4c3c770d5cd990f586a626` |

C was created from the exact S0 launch commit, then fast-forwarded over the
target's documentation-only manifest commits. A supplied clean tip
`7403905619c583067436ea09de178707c7aa2bad`; C merged it sequentially as
`6ca7d2ec4bcf675d9527c2b230569e46ab06c111`. B supplied clean tip
`3026d7a046fec7853e1ddf65b097c220edee775f`; C merged it sequentially as
`0cb1bddab10ab4b572f17df8b5af2aadf38274d5`. No uncommitted lane files were
copied.

## RC-022 verification

The repository-required interpreter was verified before testing:

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' --version
# Python 3.12.7
```

The focused release/runtime regression was run from this C worktree:

```powershell
& 'C:\Users\ahmed\Projects_Local\job-automation\Linkedin Jobs Scrapper\.venv\Scripts\python.exe' -m pytest -q tests/test_rc022_build_release_contract.py tests/test_database_migrations.py tests/test_acquisition_runtime_manifest.py tests/test_worker_service.py
# initial run: 43 passed, 4 subtests passed in 75.27s
# final rerun at C tip 27fff6cca858abf0ca3d84496e7aabe781f8f4b5:
# 43 passed, 4 subtests passed in 38.58s
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
- host restore of the authoritative acquisition state: the immutable restore
  source is now verified offline below, but no host transfer or restore has been
  performed;
- any provider, live acquisition, R2, Turso or production migration action.

## RC-025 integration

A's clean RC-025 tip `c5b57777785e98ebfa4b2b0a0a4f466907cb7ee7` was merged
sequentially into C as `6ab6f31bec0977b6db2435920942a7d885ead66d`.
The supplied evidence passed `27` focused backend tests and `10` frontend
acquisition-operations tests. The change is an additive read-only coverage and
health projection; it does not claim live coverage, provider health, host
capacity, or RC-026 benchmark evidence.

## Reconciled acquisition-state restore source

The prior source-worktree path in the manifest was stale, not evidence of data
loss. The verified offline restore source is:

```text
C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\feature-worktree-recovery\jobs-urls-preserved\Jobs-Urls\
```

The preservation evidence records 147 files, 9,611,859,565 bytes and zero
hash mismatches in:

```text
C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\feature-worktree-recovery\jobs-urls-preserved-verification.csv
```

The selected authoritative files were rehashed read-only during this pass:

| Artifact | Verified source | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| LinkedIn 14-table state | `...\Jobs-Urls\master linkedin jobs url\master_linkedin_jobs_state.db` | 3,479,191,552 | `26b81012177f40949b6b3ede3187860129db9fdaf3392d2195d78ac050244317` |
| Employer state | `...\Jobs-Urls\master linkedin jobs url\master_employer_jobs_state.db` | 83,841,024 | `b1eee3b449afd075d9b860f12a5880da6769fcc666473bbfe8f08e7e4cb36737` |

The original moved source directory remains separately retained at
`C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\feature-worktree-recovery\jobs-urls-source-quarantine\`.
The target checkout does not contain either authoritative database. No state
was recreated, moved, uploaded or restored by C.

## Exact runtime commands and roles

The existing entrypoint is the source of truth. It does not pull Git, build the
frontend, or run migrations for a worker.

API command:

```sh
RUNR_ENV=staging RUNR_RELEASE_BRANCH=deployment/render-turso-r2 RUNR_RELEASE_COMMIT=d326726acab7fffbbf59e294629b8ef002437566 RUNR_RELEASE_CONTRACT_VERSION=runr-contract-v1 RUNR_MIGRATION_HEAD=058_customer_task_queue RUNR_DATA_DIR=/srv/runr/app-data RUNR_STORAGE_BACKEND=sqlite ./deploy/start.sh api
```

Customer worker command:

```sh
RUNR_ENV=staging RUNR_RELEASE_BRANCH=deployment/render-turso-r2 RUNR_RELEASE_COMMIT=d326726acab7fffbbf59e294629b8ef002437566 RUNR_RELEASE_CONTRACT_VERSION=runr-contract-v1 RUNR_MIGRATION_HEAD=058_customer_task_queue RUNR_WORKER_VERSION=d326726acab7fffbbf59e294629b8ef002437566 WORKER_ROLE=customer WORKER_ID=runr-staging-customer-d326 RUNR_DATA_DIR=/srv/runr/app-data RUNR_STORAGE_BACKEND=sqlite ./deploy/start.sh worker
```

Acquisition worker command:

```sh
RUNR_ENV=staging RUNR_RELEASE_BRANCH=deployment/render-turso-r2 RUNR_RELEASE_COMMIT=d326726acab7fffbbf59e294629b8ef002437566 RUNR_RELEASE_CONTRACT_VERSION=runr-contract-v1 RUNR_MIGRATION_HEAD=058_customer_task_queue RUNR_WORKER_VERSION=d326726acab7fffbbf59e294629b8ef002437566 WORKER_ROLE=acquisition WORKER_ID=runr-staging-acquisition-d326 RUNR_DATA_DIR=/srv/runr/app-data RUNR_STORAGE_BACKEND=sqlite ./deploy/start.sh worker
```

`customer` may claim only the customer task family; `acquisition` may claim
only the acquisition task family. Worker IDs must be unique and role-specific.

Only the API release owner runs the migration once for an isolated staging
database or namespace:

```sh
RUNR_ENV=staging RUNR_RELEASE_BRANCH=deployment/render-turso-r2 RUNR_RELEASE_COMMIT=d326726acab7fffbbf59e294629b8ef002437566 RUNR_RELEASE_CONTRACT_VERSION=runr-contract-v1 RUNR_MIGRATION_HEAD=058_customer_task_queue ./deploy/start.sh migrate
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
current split-root claim. B's committed state-dir correction accepts this
option offline. RC-024 host verification remains blocked until the verified
restore is transferred through the approved backup workflow and exercised on an
authorized host.

## B runtime/producer integration and host gate

B's clean final tip `3026d7a046fec7853e1ddf65b097c220edee775f` was merged as
`0cb1bddab10ab4b572f17df8b5af2aadf38274d5`. The integrated producer contract
now gives both low-level producers and both manifested wrappers an explicit
`--state-dir` plus `--require-existing-state`; SQLite state remains under
`/srv/runr/state/linkedin` or `/srv/runr/state/employer`, while generations and
exports remain under `/srv/runr/exports/{linkedin,employer}`. Missing restored
state fails before SQLite creation.

The integrated role ownership is:

- API/customer services: `runr`, `/opt/runr/.env`, API loopback
  `RUNR_API_HOST=127.0.0.1`;
- acquisition worker: `runr-acquisition`, `/opt/runr/.env.acquisition`,
  `WORKER_ROLE=acquisition`, `WORKER_ID=vps_acquisition_worker`;
- customer worker: `runr`, `/opt/runr/.env`, `WORKER_ROLE=customer`,
  `WORKER_ID=vps_customer_worker`.

The disabled-acquisition settings are explicit in the acquisition environment
template: `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED=false`,
`RUNR_ENABLE_LIVE_NETWORKING_DISCOVERY=false`, and
`RUNR_ACQUISITION_MAX_REQUESTS=0`. These prevent live acquisition requests but
do not by themselves prevent the acquisition unit from being started.

The Linux/systemd host gate remains unaccepted. WSL Ubuntu systemd 255 was
available for read-only structural checks: normalized LF shell syntax passed and
`systemd-analyze verify` exited 0 for all five units. It did not have the
`/opt/runr` installation, so setup, service restart, closed-port,
ownership/permission, and synthetic-worker checks were not run. C corrected the
demonstrated setup defects in the integration tree: the Linux setup heredoc/
directory command is syntactically valid and `.env.acquisition` is installed
as `root:runr-acquisition` mode `0640`. The remaining host-gate item is that
`runr.target` wants API, customer, frontend and acquisition together; the
disabled settings stop live acquisition requests but do not make that target an
acquisition-only startup path. The integrated offline tests do not certify
host startup or secret isolation.

## C integration correction

C's focused correction is limited to `deploy/setup.sh`: it fixes the Linux
directory-command continuation and assigns the acquisition environment file to
the dedicated acquisition group. No B producer or uncommitted lane file was
copied. The correction is included in final accepted tip
`9d837e2d56930715db1de22f191644531c2c00b8` after the regression rerun.

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
docker build --file Dockerfile.api --build-arg RUNR_RELEASE_COMMIT=d326726acab7fffbbf59e294629b8ef002437566 --build-arg RUNR_RELEASE_BRANCH=deployment/render-turso-r2 --build-arg RUNR_RELEASE_SERVICE=api --tag runr-api:d326726a .
docker build --file Dockerfile.worker --build-arg RUNR_RELEASE_COMMIT=d326726acab7fffbbf59e294629b8ef002437566 --build-arg RUNR_RELEASE_BRANCH=deployment/render-turso-r2 --build-arg RUNR_RELEASE_SERVICE=worker --tag runr-worker:d326726a .
```

The five required synthetic/private mixed-version checks are: previous API and
worker against the backward-compatible schema; new API with previous worker
for queue/status/artifact/signed-download behavior; new worker with previous
API for disjoint role claims; frontend-only metadata without worker restart;
and rejection of `runr-contract-v0` before any task claim. No result is claimed
until the external staging environment exists and the exact candidate/image
digests are recorded.

## Render deployment status

`render.yaml` declares `autoDeployTrigger: commit` for the frontend, API and
worker services. The earlier HTTP `401 Unauthorized` observation is superseded:
a fresh read-only query with the nested repository `RENDER_API_KEY` returned
HTTP 200. Current live deploys are API/worker
`30ef992b7945ff0998704a550fdc2f893b24476f`, frontend
`7251ae297c55f7f6a4524181cdafb4648f7fdcde`, and the public API health endpoint
returns HTTP 200. The local target remains undeployed. No deployment was
triggered by C.

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

Current blockers are the unavailable Docker Linux daemon, the unperformed host
restore/cutover, the full-stack `runr.target` host-start scope, and the absence
of authorized staging namespaces, credentials, R2 CORS, host or live-pilot
infrastructure. The producer state/output contract is accepted offline; no
external infrastructure was created.
