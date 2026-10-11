> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Release process and production records (WS-7 primary)

Secondary WS-7 docs, which each cover one slice and link back here:
[render.md](render.md) · [vps-runtime-and-acquisition-timers.md](vps-runtime-and-acquisition-timers.md) · [docker.md](docker.md) · [ci-cd.md](ci-cd.md)

**Evidence classes used in all WS-7 docs**

| Class | Meaning |
|---|---|
| SOURCE | Read from the baseline tree with `git show 58a96674:<path>` or in the clean worktree at that SHA |
| DOC-TRACKED | A tracked document at the baseline that records a deployment or verification claim. Tracked does not make the claim true. |
| DOC-UNTRACKED | A file that exists only in the primary checkout's working tree. It is weaker evidence, because nothing in Git preserves it. |
| HISTORICAL | A record about commits or features that were later superseded or retired |
| UNKNOWN | Not determinable from the repository. Needs Render dashboard, logs or host inspection. |

**Nobody checked production for this document.** No Render API or dashboard, VPS, endpoint or provider was contacted. Every deployment statement here is **recorded**, never live. The live production revision is **UNKNOWN**.

---

## 1. Purpose and user-facing capabilities

WS-7 owns the path from a commit on `deployment/render-turso-r2` to running processes. It has no direct end-user feature. It makes the following possible:

- **Render (customer plane):** a static SPA (`runr-frontend`), a public HTTP API (`runr-api`) and a customer worker (`runr-worker`), all defined in `render.yaml`. See [render.md](render.md).
- **VPS (acquisition plane):** systemd units for the LinkedIn and employer collectors, the producer-state publisher and the export. Optional API, worker and frontend units also exist. See [vps-runtime-and-acquisition-timers.md](vps-runtime-and-acquisition-timers.md).
- **Container images:** `Dockerfile.api` and `Dockerfile.worker`. The root `Dockerfile` is a leftover compatibility image. See [docker.md](docker.md).
- **CI:** build and test only, with no deploy. See [ci-cd.md](ci-cd.md).
- **Release contract:** `backend/deployment/release_contract.py` defines the release metadata schema, the compatibility contract `runr-contract-v1` and an advisory map from changed paths to affected services.
- **Production records:** `RELEASE_LEDGER.md` (stale), `docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md` (2026-09-11), the untracked 2026-09-12 completion report, and the release commit pinned in `deploy/vps-runtime-contract.json`. These records contradict each other (C1, C2). §9 reconciles them.

## 2. Owned paths and governing instructions

| Path | Files | Lines | Notes |
|---|---|---|---|
| `deploy/**` | 27 | — | 7 shell scripts (`deploy.sh`, `setup.sh`, `start.sh`, `restore-acquisition-states.sh`, `run-acquisition-{cycle,publisher,source}.sh`), 1 Python validator, 3 JSON/env data files, 16 files under `deploy/systemd/` |
| `Dockerfile` / `Dockerfile.api` / `Dockerfile.worker` | 3 | 47 / 71 / 69 | See [docker.md](docker.md) |
| `.dockerignore` | 1 | 56 | |
| `render.yaml` | 1 | 242 | |
| `ecosystem.config.cjs` | 1 | 30 | PM2 (U9) |
| `.github/**` | 1 | 219 | only `.github/workflows/ci.yml` |
| `backend/deployment/**` | 2 | 1 + 169 | `__init__.py`, `release_contract.py` |
| `backend/static_server.py` | 1 | 55 | VPS/PM2 SPA server |
| `RELEASE_LEDGER.md` | 1 | 264 | stale ledger (C1) |
| `docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md` | 1 | 96 | 2026-09-11 record |
| `requirements.txt` / `requirements-linux.txt` / `requirements-dev.txt` | 3 | 81 / 82 / 4 | Linux = Windows set minus `pywin32==311` |
| `pyproject.toml` | 1 | 32 | pytest + ruff config |
| `package.json` / `package-lock.json` | 2 | 30 / 486 | root scripts (audit N-2: WS-7-owned) |
| `run_daily.ps1` | 1 | 59 | **Present at baseline.** The old U11 claim that the root scripts were absent is wrong. It is a local Windows wrapper for `workspace_runner.py run --workspace` and is referenced from `README.md:173`. |

Total: 46 tracked files. The audit's literal-rule count of 44 plus the 2 shared files matches this.

**Governing instructions and contracts**

- Root `AGENTS.md` (25 lines) covers only interpreter checks before running tests (L13, L25). It has no deployment rules.
- `deploy/vps-runtime-contract.json` (schema `runr.vps-runtime.v1`) and `deploy/acquisition-data-manifest.json` (schema `runr.acquisition.data-manifest.v1`) are machine-read contracts.
- Existing docs, each checked against code:
  - `docs/RC022_BUILD_RELEASE_STAGING.md` (39d15b8f) **matches** `release_contract.py` and the `render.yaml` build filters. Its build-filter matrix (L54–70) agrees with `affected_services`.
  - `docs/RC023_VPS_RUNTIME.md` (e7c70a9b) is **partly stale**. L50 says `runr.target` "includes the separate acquisition worker", which has been false since `b12c69dd`.
  - `docs/deployment/render.md` (6d0ee461, 2026-07-03) is **stale**. L12 says "API and worker use the same Docker image" and it describes `previews.generation: automatic`. The baseline has separate Dockerfiles and only a worker `previews: plan: starter` (`render.yaml:183–184`).
  - `docs/deployment/runtime.md` (2026-06-21) is **stale** (single image).
  - `docs/RUNR_VPS_ACQUISITION_PLAN.md` is a 984-line plan (v2.2, 2026-09-06). It was **not checked** line by line.
  - WS-11 owns all of these docs, and they are listed for its classification (see `../06-history-and-provenance/known-gaps.md`).

## 3. Entry points and registered commands/units

| Entry point | Invoked by | Effect |
|---|---|---|
| `deploy/start.sh <role>` (L7 role, default `api`) | Render `dockerCommand`/`preDeployCommand`; systemd `runr-api`, `runr-worker`, `runr-acquisition-worker`; Docker `CMD` | Requires `${RUNR_PYTHON_BIN:-$PROJECT_DIR/.venv/bin/python}` (L15–19, exit 1 if missing). Calls `emit_release_metadata` (L21–27) and then `exec`s the role. |
| roles `api` L30–40 · `worker` L41–51 · `acquisition` L52–64 · `process-next` L65–75 · `migrate` L76–79 | — | `migrate` runs `python -m backend.database.migrate`. An unknown role exits 64 (L80–84). |
| `python -m backend.deployment.release_contract --service {frontend,api,worker} [--worker-role R]` | `deploy/start.sh:24` only | Prints one JSON line of `ReleaseMetadata` to stdout (`main`, L159–165). |
| `affected_services(paths)` | `tests/test_rc022_build_release_contract.py` **only** | Advisory. Nothing in CI, Render or the scripts calls it (`git grep release_contract` finds only `start.sh` and the test). |
| `backend/database/migrate.py` (WS-5 file) | `start.sh migrate` → Render API pre-deploy | Applies the registry. It has **no** `RUNR_MIGRATION_HEAD` comparison (C3). |
| `deploy/deploy.sh` | VPS operator | Pins Python 3.12.7, pip install, Playwright, `systemctl restart runr.target` |
| `deploy/setup.sh` | VPS operator (once) | Users, directories, venv, unit install, disables the cycle timer, enables `runr.target` |
| `deploy/restore-acquisition-states.sh` | VPS operator | Canonicalised state release plus atomic `active` symlink switch |
| `deploy/run-acquisition-{source,publisher,cycle}.sh` | systemd acquisition units | See the VPS doc |
| `.github/workflows/ci.yml` | GitHub `pull_request`, `push` to `main`/`deployment/render-turso-r2` | Test and build only |
| `npm run check*` / `pm2:*` (root `package.json`) | Developer | See [ci-cd.md](ci-cd.md) |
| `run_daily.ps1 -WorkspaceId X` | Local Windows | `workspace_runner.py --data-dir … --storage … run --workspace X`, log under `logs/` |

No HTTP route exposes release metadata. `ReleaseMetadata` is not imported under `backend/api` or `backend/worker`. The emitted JSON therefore exists only in service logs, which matters for U1.

## 4. Inputs, outputs, storage and dependencies

**Release metadata inputs** (`release_contract.py:ReleaseMetadata.from_environment`, L104–142). `_environment_value` (L84–89) skips values that are empty or equal to `unknown`, `unset` or `none`.

| Field | Env lookup order | Default |
|---|---|---|
| `branch` | `RUNR_RELEASE_BRANCH`, `RENDER_GIT_BRANCH` (L121–125) | `unknown` |
| `commit` | `RUNR_RELEASE_COMMIT`, `RENDER_GIT_COMMIT` (L126–130) | `unknown` |
| `contract_version` | `RUNR_RELEASE_CONTRACT_VERSION` (L131–134) | `runr-contract-v1` (L13) |
| `migration_head` | `RUNR_MIGRATION_HEAD` (L135–138) | `058_customer_task_queue` (L14) |
| `worker_role` / `worker_version` | arg or `WORKER_ROLE` / `RUNR_WORKER_VERSION` | `""` |
| `schema_version` | constant `runr.release.v1` (L12) | — |

Interplay:
- `Dockerfile.api`/`.worker` bake `ENV RUNR_RELEASE_COMMIT=${ARG}` with ARG default `unknown`, and `render.yaml` passes no build args. On Render the `unknown` value is therefore skipped and `RENDER_GIT_COMMIT` wins.
- CI passes `github.sha` as a build arg (`ci.yml:198–201`), but CI images are never pushed.
- On the VPS, `deploy.sh:30` echoes `RUNR_RELEASE_COMMIT` or `git rev-parse HEAD`, but does not export it to the units.
- The acquisition receipts take `--release-commit` from `RUNR_SOURCE_VERSION` or `RUNR_RELEASE_COMMIT` (`run-acquisition-source.sh:125`). `deploy/acquisition.env.example:25` sets `RUNR_SOURCE_VERSION` as a manual placeholder.

**Service impact map** (`affected_services`, L49–81; frontend runtime paths L20–28):

| Changed path | Services |
|---|---|
| `render.yaml` | all three (returns immediately) |
| `Dockerfile.api` / `Dockerfile.worker` | api / worker |
| `frontend/scripts/render-cv-pdf.mjs`, `frontend/src/lib/cvStudio.js`, `frontend/src/lib/cvSocialLinks.js`, `frontend/package.json`, `frontend/package-lock.json` | frontend + api + worker |
| other `frontend/**` | frontend |
| `backend/**`, `requirements-linux.txt`, `workspace_runner.py`, `deploy/start.sh` | api + worker |
| `scripts/**` | worker |
| anything else (`deploy/systemd/**`, `deploy/run-acquisition-*.sh`, `requirements.txt`, docs, tests) | none. The VPS plane is not modelled (WS7-G2). |

**Dependencies on other workstreams:**
- Migrations and the registry head: `../03-data/schema-and-migrations.md` (WS-5).
- Worker roles: `../01-architecture/backend-workers-and-orchestration.md` (WS-2).
- Collectors and publisher scripts: `../05-subsystems/acquisition-and-collectors.md` and `../05-subsystems/publication-and-catalog.md` (WS-3).
- Producer state and exports: `../03-data/acquisition-source-state.md` (WS-3).
- Tests: `../04-testing/test-suite-map.md` (WS-10).

## 5. Important call/data flows

**A. Render release (as configured; whether it runs is UNKNOWN)**
```
push to deployment/render-turso-r2 (Render branch binding = dashboard setting, U3)
 └─ per service: buildFilter.paths match? ──no──► no deploy
        │yes (autoDeployTrigger: commit)
        ├─ runr-frontend: rootDir frontend → npm ci && npm run build → ./dist (render.yaml:5–7)
        ├─ runr-api: docker build Dockerfile.api → preDeployCommand ./deploy/start.sh migrate
        │     └─ start.sh:76–79 emit_release_metadata api → python -m backend.database.migrate (no head gate, C3)
        │  → dockerCommand ./deploy/start.sh api → workspace_runner.py serve-api → healthCheckPath /health/live
        └─ runr-worker: docker build Dockerfile.worker → ./deploy/start.sh worker (WORKER_ROLE=customer)
```
CI on the same push is independent. It does not gate the Render deploy: there is no required-status link in the repository, and the Render side is UNKNOWN.

**B. VPS release (operator-driven, recorded in the handoff and report)**
```
operator: git checkout <sha> in /opt/runr (not scripted)
 └─ deploy/deploy.sh: .env + .env.acquisition present (L9–12) → Python 3.12.7 (L14–23)
     → sudo pip install -r requirements-linux.txt (L34) → playwright chromium (L35–36)
     → systemctl daemon-reload; restart runr.target (L37–38)
 (frontend rebuild is a separate manual step, L41–47; migrations are not run on the VPS:
  contract "migration_owner": "api-pre-deploy-only", vps-runtime-contract.json:7)
```
`deploy.sh` does not re-copy unit files. Only `setup.sh:86–99` copies them, so a unit change in Git reaches systemd only after `setup.sh` is re-run or the files are copied by hand (WS7-G4).

**C. Where records come from.** The ledger was written by integrators per wave (commits `e49bbdc1`…`8d10ff7f`). The handoff was committed as `d487315b` and then `c25d394a` "Clarify deployed runtime revision". The 2026-09-12 report was never committed; ticket T06 plans to commit it byte-identical under `docs/reports/`.

## 6. Invariants, failure handling and recovery

| Invariant | Enforced by | Evidence |
|---|---|---|
| Runtime interpreter is the project venv | `start.sh:15–19` exit 1; Dockerfiles create `/app/.venv` | `Dockerfile.api:41–44`, `Dockerfile.worker:41–45`. The 2026-09-12 report L165–166 names the earlier missing-venv failure as a root cause (DOC-UNTRACKED). |
| Only the Render API runs migrations | `render.yaml:52` `preDeployCommand` on api only; the worker has none; contract L7 | SOURCE |
| Contract compatibility is exact equality to `runr-contract-v1` | `are_release_contracts_compatible` L151–156 | SOURCE. Not called at runtime (test only). |
| Release metadata never claims an unknown value | `_environment_value` filters `unknown`, `unset`, `none` | `test_release_metadata_uses_render_commit_without_claiming_unknown_values` |
| Migration head is consistent with the registry | **nothing** | C3: `render.yaml:76–77,193–194` and `release_contract.py:14` say 058; `backend/repositories/sqlite_migrations.py:3543` is `060_publication_latest_observation_index` |
| Acquisition never runs on Render | env switches `render.yaml:84–91,201–208`; worker role pinned `customer` (L217–218) | SOURCE (config only) |
| Failed pre-deploy blocks the API deploy | Render platform semantics | HISTORICAL: ledger L105–115 records a failed `052` pre-deploy at `fd4709bb` repaired forward by `6fd91cb2` |

Recovery:
- **Render:** the repository has no scripted rollback. The ledger records only forward repair (L108–115).
- **VPS:** state rollback goes through `restore-acquisition-states.sh`, which builds an immutable `versions/<id>` and switches the `active` symlink (L64–67). Checkpoints come from `scripts/acquisition_state_backup.py` (WS-3 file; RC-024), which nothing in `deploy/` invokes (WS7-G11).
- **Database:** the ledger L90–95 records a logical pre-migration backup for Wave 1 (HISTORICAL). No backup step exists in `render.yaml` or `start.sh migrate`.

## 7. Relevant tests and safe verification commands

| Test (WS-10 owns; see `../04-testing/test-suite-map.md`) | Covers | Static note |
|---|---|---|
| `tests/test_rc022_build_release_contract.py` (75 lines; 6 tests) | `affected_services`, metadata env precedence, contract equality, Dockerfile invariants, render/CI image selection | Consistent with baseline sources |
| `tests/test_rc023_vps_runtime.py` (99 lines; 6 tests) | `vps-runtime-contract.json` keys, env boundary, systemd hardening, setup/deploy pins, journald, target | **L99 asserts `"runr-acquisition-worker.service" in target`. `b12c69dd` (2026-09-11 19:26) removed that unit from `runr.target`, and the test was last changed in `d44d3c0f` (18:40 the same day, an ancestor). Static inference: this test fails at baseline. Not executed (WS7-G1).** |
| `tests/test_rc024_backup_restore.py` (358 lines) | `scripts/acquisition_state_backup.py` checkpoint, restore, lease and prune | Library/CLI level. No deploy unit is involved. |
| `tests/test_acquisition_runtime_manifest.py` (119 lines) | `deploy/validate_acquisition_runtime.py:validate_manifest` | |
| `tests/test_production_completion_regressions.py` | reads `deploy/run-acquisition-source.sh` (L15), e.g. the watchdog | |

Safe verification commands. **These were not executed in Phase 2.** They need a local venv and are offline.
```
.venv\Scripts\python.exe -m pytest -q tests/test_rc022_build_release_contract.py tests/test_rc023_vps_runtime.py tests/test_rc024_backup_restore.py tests/test_acquisition_runtime_manifest.py tests/test_production_completion_regressions.py
.venv\Scripts\python.exe -m backend.deployment.release_contract --service api        # prints metadata; no network
git grep -n "RUNR_MIGRATION_HEAD\|DEFAULT_MIGRATION_HEAD" 58a96674 -- render.yaml backend
git show 58a96674:backend/repositories/sqlite_migrations.py | grep -oE '"0[0-9]{2}_[a-z0-9_]+"' | tail -1
git rev-list --count 5dfdd106..58a96674   # 44
git rev-list --count 4a1b1df5..58a96674   # 7
git rev-list --count 9ba1d551..58a96674   # 40
git rev-list --count 3c5e609a..58a96674   # 250
```

## 8. Historical decisions and supporting commits

| Commit | Date | Subject | Relevance |
|---|---|---|---|
| `aae3028f` | 2026-05-18 | Linux Production Setup + Clerk's JWT | first `deploy/` and systemd setup |
| `c7bf7cbd` | 2026-06-18 | deoployment prep initial setup | Render/Docker/CI foundation |
| `cff506b4` | 2026-06-20 | Run CI on Render deployment branch | CI push trigger for `deployment/render-turso-r2` |
| `6d0ee461` | 2026-07-03 | Enable Render PR previews | previews (now only the worker `previews.plan`) |
| `e49bbdc1`…`8d10ff7f` | 2026-08-12/13 | chore: record … | `RELEASE_LEDGER.md` entries, ending at the Wave 3 hold |
| `39d15b8f` | 2026-09-08 | RC-022 separate release and runtime contracts | `Dockerfile.api`/`.worker`, `release_contract.py`, migration head 058 |
| `b4f8147f`, `e7c70a9b` | 2026-09-09 | prepare systemd VPS contract; isolate acquisition service account | `vps-runtime-contract.json`, `runr-acquisition` user |
| `da565e94` | 2026-09-10 | move acquisition to VPS role and pin 24h UTC schedule | export service/timer added; Render acquisition disabled |
| `dd47acf9` | 2026-09-10 | Complete acquisition delivery and remove admin surfaces | admin retirement (see `../06-history-and-provenance/retired-features.md`) |
| `15f58623` | 2026-09-10 | install Python browser runtime and preserve partial outcomes | Docker/VPS Playwright |
| `d487315b`, `c25d394a` | 2026-09-11 | Document production completion evidence; Clarify deployed runtime revision | handoff doc |
| `a35a5e8c` | 2026-09-11 | release: pin integrated acquisition contract | contract and data-manifest commit set to `9ba1d551` |
| `b12c69dd` | 2026-09-11 | runtime: keep legacy acquisition worker disabled | removed acquisition worker from `runr.target` |
| `c85f7275` | 2026-09-12 | enable bounded live acquisition services | `LIVE_NETWORK_ENABLED=true` in linkedin/employer units; timeout `infinity`→`2h` (C4) |
| `963c8f21` | 2026-09-12 | separate scraper completion from publisher start | removed `ExecStartPost` publisher trigger |
| `00132ebe` | 2026-09-12 | keep api launcher executable | `deploy/start.sh` mode bit |
| `5a7f9627` | 2026-09-12 | bound source runs with a finite watchdog | `RUNR_SOURCE_RUN_TIMEOUT_SECONDS=900` |
| `4a1b1df5` | 2026-09-12 | (VPS release recorded by the untracked report) | 7 commits behind baseline |

Query: `git log --oneline 58a96674 -- deploy render.yaml Dockerfile Dockerfile.api Dockerfile.worker backend/deployment .github RELEASE_LEDGER.md docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md`

## 9. Current implementation status

| Capability | Classification |
|---|---|
| Release metadata emission at every `start.sh` role | VERIFIED (scope: static — `start.sh:21–27` calls `release_contract` before every `exec`; `main` L159–165 prints JSON) |
| Contract version `runr-contract-v1` shared by render.yaml, Dockerfiles, VPS contract | VERIFIED (scope: static string match in `render.yaml:27–28,74–75,191–192`, `Dockerfile.api:14`, `Dockerfile.worker:14`, `vps-runtime-contract.json:7`) |
| Path-to-service impact map (`affected_services`) | IMPLEMENTED-UNVERIFIED. Library function, test-only caller. It does not drive Render (the build filters do) and does not cover the VPS. |
| Runtime compatibility check between old and new images | PARTIAL. The function exists, but no runtime caller. |
| Migration-head gate (`RUNR_MIGRATION_HEAD` vs registry) | UNKNOWN. No gate exists in code, and no doc or ticket plans one, so intent is unknown (C3). |
| Render API pre-deploy migration | VERIFIED (scope: static — `render.yaml:52` → `start.sh:76–79` → `backend.database.migrate`) |
| Scripted VPS deploy (`deploy.sh`) | IMPLEMENTED-UNVERIFIED |
| Scripted rollback (Render or VPS code release) | UNKNOWN. Absent from the tree and no plan is cited; any rollback would be a manual dashboard or host action (WS7-G13). |
| VPS state rollback (`restore-acquisition-states.sh`) | IMPLEMENTED-UNVERIFIED |
| `RELEASE_LEDGER.md` as the current release record | RETIRED/HISTORICAL. Stale since 2026-08-13 (C1). |
| Handoff doc as the current production record | RETIRED/HISTORICAL. Accurate only as a 2026-09-11 record; 44 commits behind. |
| `run_daily.ps1` local workspace run | IMPLEMENTED-UNVERIFIED |

### Deployment evidence (documentary records only; none is a live check)

| # | Record | Class | Scope | Revision | Date | Key lines |
|---|---|---|---|---|---|---|
| R1 | `RELEASE_LEDGER.md` "Wave 3 deployment hold" | DOC-TRACKED, HISTORICAL | Render ×3 | last live `3c5e609a`; `d969f43b` "Build blocked" (pipeline minutes); `055` not applied | 2026-08-13 | L245–264 (L250–253). Also L154 (`3c5e609a` push), L182–185 (Render API key 401) |
| R2 | `docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md` | DOC-TRACKED | Render API/worker/frontend "live"; `/health/live` ok; VPS acquisition marker | `5dfdd106` (L8, L12, table L14–20) | 2026-09-11 | Ownership L26–33; verification L82–88 (focused selection 56 passed; "No broad suite was rerun") |
| R3 | `deploy/vps-runtime-contract.json` `release.commit` | SOURCE (config, pinned by `a35a5e8c`) | approved VPS release | `9ba1d551` (L6) | 2026-09-11 | Placeholders L12, L29 (C9). The same SHA is in `deploy/acquisition-data-manifest.json:4`. |
| R4 | `docs/reports/RUNR_PRODUCTION_COMPLETION_REPORT_2026-09-12.md` (primary checkout, untracked, 196 lines) | DOC-UNTRACKED | "VPS acquisition path is deployed and running" | `4a1b1df5` (L7–8, L192–194) | 2026-09-12 | Legacy combined timer disabled; independent timers enabled (L45–46). At 21:45–21:50 UTC: Render `/health/live` 200, `/health/ready` **400** (Turso "SQL read operations are forbidden"), frontend bundle predates final push (L145–157). |

Handoff infrastructure identifiers (Render service/deploy IDs, VPS host name, state-directory hashes) are intentionally **not reproduced**.

**Reconciliation**

- **C1 (ledger vs handoff).** The ledger was never updated after `8d10ff7f`. R2 supersedes R1 chronologically. The ledger's Wave 2/3 content concerns the since-retired admin dashboard (HISTORICAL).
- **C2 (three VPS SHAs).**
  - `5dfdd106` is the handoff marker.
  - `9ba1d551` is the contract pin, and it is a descendant of `5dfdd106`.
  - `4a1b1df5` is from the untracked report and is the newest.
  - The three are ancestors of the baseline at distances 44, 40 and 7.
  - Most recent recorded VPS release: `4a1b1df5` (weakest evidence class). The contract pin is a release-approval record, not a deploy record.
- **C3 (058 vs 060).** Migrations `059_company_identity_crosswalk` and `060_publication_latest_observation_index` were added after RC-022 pinned 058. `RUNR_MIGRATION_HEAD` is only echoed into log metadata, and nothing compares it with the registry. It therefore misreports the head for every release after the 059/060 commits, and nothing fails.
- **C9.** The contract still reads "record provider image identifier before purchase" (L12) and "select near the Turso region … before authorization" (L29), and `monthly_price_eur`/`provider_limits` are `null` (L30–31). `test_rc023` L24–25 *require* those two nulls, so the test entrenches the placeholders.
- **Conflicting ownership claims.** The handoff (L27–28) says the cycle timer is the owner. The report (L45–46) says the cycle timer is disabled and the independent timers are active. `setup.sh:106` disables the cycle timer. The newer SOURCE and the newer record agree; the handoff is outdated on this point (C5; see the VPS doc).
- **Post-record drift.** Render `autoDeployTrigger: commit` plus `buildFilter` means any of the 44 commits after `5dfdd106` that touched filtered paths would have triggered a deploy if the branch binding holds (U1, U3). R4 already observed a stale bundle and a failing readiness check, so "recorded live" in R2 must not be read forward.

**Classification:**
- LAST-RECORDED-PRODUCTION: Render `5dfdd106` (R2); VPS acquisition `4a1b1df5` (R4).
- LIVE-PRODUCTION: **UNKNOWN**.

## 10. Confirmed gaps and unresolved questions

| ID | Item |
|---|---|
| C1 | Ledger stale at `3c5e609a` vs handoff `5dfdd106` |
| C2 | Three VPS release SHAs (`5dfdd106` / `9ba1d551` / `4a1b1df5`) |
| C3 | Migration head 058 (render.yaml, release_contract default) vs registry 060; no gate. Co-owned with WS-5. |
| C9 | VPS contract placeholders (L12, L29, L30–31), locked in by `test_rc023` |
| U1 | Render live revision. The only in-repo signal is the stdout metadata line, which needs Render logs. There is no endpoint. |
| U2 | VPS live revision and enabled units (`systemctl list-timers`, `git -C /opt/runr rev-parse HEAD`) |
| U3 | Render branch binding (dashboard). `RUNR_RELEASE_BRANCH` is only a declared value. |
| T12 | Stale local `deployment/render-turso-r2` worktree whose working tree deletes the handoff doc (C8). Owner git hygiene; the blob is identical on the baseline. |
| T14 | The retained checkouts, including the primary checkout that holds the untracked R4 report; T06 must commit R4 first |
| WS7-G1 | `tests/test_rc023_vps_runtime.py:99` asserts the acquisition worker is in `runr.target`. `b12c69dd` removed it. Static inference: failing test (not run). |
| WS7-G2 | `affected_services` ignores VPS paths (`deploy/systemd/**`, `deploy/run-acquisition-*.sh`, `deploy/*.json`) and `requirements.txt`, and has no production caller |
| WS7-G3 | Release metadata is only printed to stdout; no queryable endpoint or file |
| WS7-G4 | `deploy.sh` never re-installs unit files; `setup.sh` never installs the export service/timer |
| WS7-G13 | No scripted rollback for Render or the VPS code release. Release selection on the VPS is a manual checkout. |
| WS7-G14 | Existing deployment docs are stale (`docs/deployment/render.md` L12, `docs/deployment/runtime.md`, `docs/RC023_VPS_RUNTIME.md:50`). WS-11 classification. |
| WS7-G15 | The ledger's last recorded Render incident was exhausted pipeline minutes (L250–251). Whether that constraint persists is UNKNOWN. |

The other WS-7 IDs (C4–C6, N-5, U8, U9, WS7-G5…G12) are in the secondary docs.

## Agent context and remaining work

**(a) Proposed agent context packet**
- **Required reading:**
  - this doc and the four secondary WS-7 docs
  - `render.yaml`, `deploy/start.sh`, `backend/deployment/release_contract.py`, `deploy/vps-runtime-contract.json`
  - `deploy/systemd/runr.target`, `deploy/setup.sh`, `deploy/deploy.sh`
  - `.github/workflows/ci.yml`
  - `docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md` (do not copy identifiers)
  - `RELEASE_LEDGER.md` L226–264
  - `docs/RC022_BUILD_RELEASE_STAGING.md`
- **Allowed paths:** the WS-7 owned paths in §2. Migration registry changes go through WS-5. Acquisition scripts under `scripts/` go through WS-3. Tests go through WS-10.
- **Tests to run:** the five files in §7 plus `npm run check:backend` for any `requirements*`/`pyproject.toml` change. For Dockerfile changes, a local `docker build -f Dockerfile.api .` / `-f Dockerfile.worker .` (no push).
- **Prohibited:**
  - no deploys, no `git push` to `deployment/render-turso-r2` without owner approval (it auto-deploys)
  - no editing Render or VPS secrets or env values
  - no running `deploy/*.sh` or acquisition wrappers against a host
  - no enabling `runr-acquisition-cycle.timer`/export timer
  - no copying service/deploy IDs, host names or state hashes into the repo
  - no restoring retired admin analytics

**(b) Registry proposal**

| subsystem id | name | owned globs | primary doc | test globs | owner WS |
|---|---|---|---|---|---|
| `deployment-release-ci` | Deployment, release and CI | `deploy/**`, `Dockerfile*`, `.dockerignore`, `render.yaml`, `ecosystem.config.cjs`, `.github/**`, `backend/deployment/**`, `backend/static_server.py`, `RELEASE_LEDGER.md`, `docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md`, `requirements*.txt`, `pyproject.toml`, `package.json`, `package-lock.json`, `run_daily.ps1` | `docs/reverse-engineering/02-deployment/release-process-and-production-records.md` | `tests/test_rc022_*.py`, `tests/test_rc023_*.py`, `tests/test_rc024_*.py`, `tests/test_acquisition_runtime_manifest.py`, `tests/test_production_completion_regressions.py` | WS-7 |

**(c) Gap and ticket candidates** (candidates only; no tickets created)
1. **Fix `test_rc023` vs `runr.target` (WS7-G1).** Decide whether the acquisition worker belongs in the target, then update the test or the unit. Acceptance: the test file passes locally.
2. **Migration-head gate (C3).** Derive `RUNR_MIGRATION_HEAD` from `MIGRATIONS[-1]`, or add a test asserting `render.yaml` equals the registry head. Update `render.yaml:77,194` and `release_contract.py:14` to `060_…`. Coordinate with WS-5.
3. **Retire or append the ledger (C1).** Add a closing section pointing to the handoff and the committed 2026-09-12 report (after T06), or mark the file HISTORICAL.
4. **Single VPS release record (C2, C9).** Update `vps-runtime-contract.json` `release.commit` to the actually deployed SHA once U2 is resolved, fill or remove the placeholders, and relax the `test_rc023` null assertions accordingly.
5. **Queryable release metadata (WS7-G3, U1).** Expose `ReleaseMetadata` via a health/version route (WS-1 route owner) so U1 can be answered without dashboard access.
6. **Extend `affected_services` to the VPS plane, or document it as Render-only (WS7-G2).**
7. **Stale deployment docs (WS7-G14):** hand to WS-11 for HISTORICAL marking.
