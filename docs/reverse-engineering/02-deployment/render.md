> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Render (customer plane)

Secondary WS-7 doc. Release records, evidence classes and C1–C3 are in the primary doc: [release-process-and-production-records.md](release-process-and-production-records.md). Image details are in [docker.md](docker.md).

**Nothing in this doc was checked against Render.** The Render dashboard and API were not contacted. Every statement describes `render.yaml` (242 lines) at the baseline. Deployments are "recorded" only, and live state is UNKNOWN.

## 1. Purpose

`render.yaml` is a Render Blueprint that declares the customer-facing plane:
- the static SPA
- the public API
- one customer-role queue worker

Comments at `render.yaml:82–83` and `render.yaml:199–200` state "Acquisition runs on the VPS, never on Render".

## 2. Owned paths

`render.yaml` (WS-7). Build inputs referenced from it: `Dockerfile.api`, `Dockerfile.worker`, `deploy/start.sh` (WS-7), `frontend/**` (WS-8), `backend/**` (WS-1…WS-6), `scripts/**` (WS-3), `workspace_runner.py` (WS-1).

## 3. Services

| | `runr-frontend` | `runr-api` | `runr-worker` |
|---|---|---|---|
| Lines | 2–43 | 45–159 | 161–242 |
| Type / runtime | `web` / `static` | `web` / `docker` | `worker` / `docker` |
| Plan / region | (not set) / — | `starter` / `frankfurt` (L48–49) | `standard` / `frankfurt` (L164–165) |
| Build | `rootDir: frontend`; `npm ci && npm run build`; publish `./dist` (L5–7) | `./Dockerfile.api` (L50) | `./Dockerfile.worker` (L166) |
| Start | SPA rewrite `/*` → `/index.html` (L40–43) | `./deploy/start.sh api` (L51) | `./deploy/start.sh worker` (L167) |
| Pre-deploy | — | `./deploy/start.sh migrate` (L52) | — (the worker never migrates) |
| Health check | — | `/health/live` (L66) | — |
| `autoDeployTrigger` | `commit` (L12) | `commit` (L67) | `commit` (L182) |
| `maxShutdownDelaySeconds` | — | 60 (L68) | 300 (L185) |
| Previews | — | — | `previews: plan: starter` (L183–184) |
| Custom domain | `userunr.com` (L13–14) | — | — |

### buildFilter paths (deploy only when a changed path matches)

| Service | Paths |
|---|---|
| frontend (L8–11) | `frontend/**`, `render.yaml` |
| api (L53–65) | `backend/**`, `workspace_runner.py`, `requirements-linux.txt`, `Dockerfile.api`, `deploy/start.sh`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/scripts/render-cv-pdf.mjs`, `frontend/src/lib/cvStudio.js`, `frontend/src/lib/cvSocialLinks.js`, `render.yaml` |
| worker (L168–181) | the api set with `Dockerfile.worker` in place of `Dockerfile.api`, plus `scripts/**` |

Four observations on the filters:

1. They match `backend/deployment/release_contract.py:affected_services` for Render paths, with one difference: a change to `Dockerfile.api` alone matches only the api filter, and `affected_services` agrees.
2. Changes to `deploy/systemd/**`, `deploy/run-acquisition-*.sh`, `requirements.txt`, docs and tests trigger no Render deploy.
3. A frontend change that touches only `frontend/src/**` (not the five renderer files) redeploys the frontend only.
4. The frontend filter covers all of `frontend/**`, including `frontend/e2e/**` and tests. Test-only frontend edits therefore still rebuild the static site.

## 4. Environment variables (names only; no values for `sync: false`)

**Frontend (L15–39):**
- `VITE_API_BASE_URL`: a literal URL pointing at the Render default API hostname.
- `VITE_API_EXTERNAL_HOSTNAME`: `fromService` runr-api `RENDER_EXTERNAL_HOSTNAME`.
- `VITE_CLERK_PUBLISHABLE_KEY` (sync:false).
- `RUNR_RELEASE_BRANCH=deployment/render-turso-r2`.
- `RUNR_RELEASE_CONTRACT_VERSION=runr-contract-v1`.
- `VITE_PERSONALIZED_JOBS_EXPERIENCE=1`, `VITE_PERSONALIZED_JOBS_DATA_MODE=real`, `VITE_REPLACE_LEGACY_JOBS_NAV=1`.
- `VITE_ENABLE_ASSISTED_APPLY_PREPARATION` (sync:false; comment L37 "AA-226 pilot").

**API (L69–159):**

| Group | Names |
|---|---|
| Release | `RUNR_ENV=production`, `RUNR_RELEASE_BRANCH`, `RUNR_RELEASE_CONTRACT_VERSION`, `RUNR_MIGRATION_HEAD=058_customer_task_queue` (L76–77, **C3**) |
| Runtime | `RUNR_CUSTOMER_TASKS_ASYNC=true`, `RUNR_PRIVATE_TEST_DEPLOYMENT=false`, `DATABASE_BACKEND=turso`, `RUNR_STORAGE_BACKEND=sqlite`, `RUNR_DATA_DIR=.backend_data`, `OBJECT_STORAGE_BACKEND=r2`, `S3_REGION=auto` |
| Acquisition switches (all off) | `RUNR_ACQUISITION_LIVE_NETWORK_ENABLED=false` (L84–85), `RUNR_ENABLE_LIVE_NETWORKING_DISCOVERY=false` (L86–87), `RUNR_COMPANY_ENRICHMENT_ENABLED=0` (L90–91) |
| CORS / origins | `BACKEND_ALLOWED_ORIGINS` (literal), `RUNR_ASSISTED_APPLY_EXTENSION_ORIGINS` (sync:false), `RENDER_FRONTEND_EXTERNAL_HOSTNAME` (fromService runr-frontend) |
| Pilot | `RUNR_ENABLE_ASSISTED_APPLY_PREPARATION` (sync:false) |
| Secrets (sync:false) | `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET`, `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY`, `CLERK_WEBHOOK_SECRET`, `CREEM_API_KEY`, `CREEM_WEBHOOK_SECRET`, `SCRAPEOPS_API_KEY`, `DEEPSEEK_API_KEY`, `TRACKER_GOOGLE_OAUTH_CLIENT_ID`, `TRACKER_GOOGLE_OAUTH_CLIENT_SECRET`, `TRACKER_GOOGLE_OAUTH_REDIRECT_URI` |
| CREEM product IDs (7, sync:false, L136–149) | `CREEM_RUNR_PRO_PRODUCT_ID`, `CREEM_RUNR_PRO_WEEKLY_PRODUCT_ID`, `CREEM_RUNR_PRO_MONTHLY_PRODUCT_ID`, `CREEM_RUNR_PRO_QUARTERLY_PRODUCT_ID`, `CREEM_LAUNCH_PRODUCT_ID`, `CREEM_MOMENTUM_PRODUCT_ID`, `CREEM_SCALE_PRODUCT_ID` (billing: `../05-subsystems/billing-and-creem.md`, WS-6) |

**Worker (L186–242):**
- Shares the release, runtime and acquisition-switch groups: `RUNR_MIGRATION_HEAD=058…` (L193–194), switches off (L201–208).
- Worker-specific: `WORKER_ID=render_customer_worker` (L215–216), `WORKER_ROLE=customer` (L217–218), `RUNR_WORKER_VERSION=rc018-v1` (L219–220), `RUNR_WORKER_CAPACITY_SLOTS=1` (L221–222).
- Secrets: only `TURSO_*`, `S3_*`, `SCRAPEOPS_API_KEY`, `DEEPSEEK_API_KEY`. There are **no** Clerk, Creem or Google OAuth keys on the worker.

The env schema (48 keys) lives in `backend/config/env_schema.py` (WS-5). Its match against these names was not re-checked here.

## 5. Flows

- **Deploy:** push → filter match → build → (api) pre-deploy migrate → start → (api) health check. The full diagram is in the primary doc §5A.
- **Branch binding:** configured in the Render dashboard and not in the repo (**U3**). `RUNR_RELEASE_BRANCH` is only a value echoed into release metadata.
- **Release metadata on Render:** `Dockerfile.*` bake `RUNR_RELEASE_COMMIT=unknown` because no build args are set in `render.yaml`. `release_contract._environment_value` skips `unknown`, so metadata falls back to Render's `RENDER_GIT_COMMIT` and `RENDER_GIT_BRANCH`. Output goes to service logs only.
- **Customer worker queue:** `start.sh worker` → `workspace_runner.py run-worker --worker-role customer`. See `../01-architecture/backend-workers-and-orchestration.md` (WS-2).

## 6. Invariants and failure handling

- **Migrations only in the api pre-deploy (L52).** A pre-deploy failure blocks the api deploy. The worker deploy is independent: it has no `dependsOn`, so a worker built from a newer commit can run against an older schema if the api pre-deploy fails. The ledger records exactly this state historically (worker live, api pre-deploy failed at `fd4709bb`, `RELEASE_LEDGER.md:105–107`).
- **No acquisition on Render.** This is configuration-enforced (env switches plus `WORKER_ROLE=customer`), not code-enforced by `render.yaml` itself. Code-level enforcement belongs to WS-2/WS-3.
- **`start.sh` fails closed without `.venv`,** and both Dockerfiles create it.
- **Readiness.** The configured health check is `/health/live`, not `/health/ready`. A database-read failure can therefore pass the health check. The untracked 2026-09-12 report records `/health/live` 200 alongside `/health/ready` 400 (L147–150, DOC-UNTRACKED) (WS7-G5).

## 7. Tests and safe verification commands

- `tests/test_rc022_build_release_contract.py::test_render_and_ci_select_distinct_api_and_worker_images` (asserts `dockerfilePath` for both images and presence of `buildFilter:`).
- Not executed in Phase 2:
  ```
  git show 58a96674:render.yaml | grep -c "key: CREEM_.*PRODUCT_ID"          # 7
  git grep -n "RUNR_MIGRATION_HEAD" 58a96674 -- render.yaml                   # L76, L193
  .venv\Scripts\python.exe -m pytest -q tests/test_rc022_build_release_contract.py
  ```

## 8. History (`git log --oneline 58a96674 -- render.yaml`, selected)

| Commit | Subject |
|---|---|
| `c7bf7cbd` | deoployment prep initial setup |
| `6d0ee461` | Enable Render PR previews |
| `9fb3e644` | Allow Render Blueprint sync on Hobby workspace |
| `79f4e802` | Enable personalized jobs preview on Render |
| `5e674e1e` | fix: migrate Creem billing to Runr Pro |
| `166a9f2a` | chore: configure userunr.com as Runr frontend domain |
| `9ea734fa`, `703d6881`, `fce08bc0`, `27825052` | enrichment on Render (2026-08-15), later disabled |
| `39d15b8f` | RC-022 separate release and runtime contracts (Dockerfile split, build filters, head 058) |
| `da565e94` | move acquisition to VPS role and pin 24h UTC schedule (Render acquisition off) |
| `15f58623` | install Python browser runtime and preserve partial outcomes |

## 9. Status

| Capability | Classification |
|---|---|
| Three-service Blueprint (frontend/api/worker) | VERIFIED (scope: static — `render.yaml` parsed by reading; service names, types, Dockerfile paths, commands) |
| Path-scoped auto-deploy | VERIFIED (scope: static config at L8–12, L53–67, L168–182; Render behaviour not observed) |
| API pre-deploy migration | VERIFIED (scope: static — L52 → `deploy/start.sh:76–79`) |
| Acquisition and enrichment disabled on Render | VERIFIED (scope: static env values L84–91, L201–208, L217–218; runtime env overrides in the dashboard UNKNOWN) |
| PR preview environments | PARTIAL. Only `previews.plan` on the worker. `docs/deployment/render.md` describes `previews.generation: automatic`, which is absent. |
| Correct migration-head metadata | UNKNOWN. The value is 058 while the registry is 060 (C3). Nothing in the tree says whether a corrected value was set in the dashboard. |

### Deployment evidence (documentary only)

- **Handoff** (`docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md` L8, L14–22; DOC-TRACKED, 2026-09-11) records all three services live on `5dfdd106` and `/health/live` returning ok.
- **2026-09-12 report** (DOC-UNTRACKED, L145–157) records frontend 200, `/health/live` 200, `/health/ready` 400 (Turso read forbidden), and a stale frontend bundle.
- **Ledger** (HISTORICAL, L245–253) records `d969f43b` build blocked by exhausted pipeline minutes, with the last live revision `3c5e609a`.

## 10. Gaps

| ID | Item |
|---|---|
| C3 | `RUNR_MIGRATION_HEAD=058_customer_task_queue` at L77 and L194 vs registry 060 |
| U1 | Render live revision |
| U3 | Render branch binding |
| WS7-G5 | Health check is liveness only; readiness failures (DB) are not a deploy gate |
| WS7-G6 | No api→worker deploy ordering; a mixed schema/worker window is possible |
| WS7-G14 | `docs/deployment/render.md` stale (single image, `previews.generation`); WS-11 |

## Agent context and remaining work

- **Read:** `render.yaml`, `deploy/start.sh`, `backend/deployment/release_contract.py`, the primary doc.
- **Allowed:** `render.yaml` (WS-7). Env schema changes require WS-5; Creem product mapping requires WS-6.
- **Tests:** `tests/test_rc022_build_release_contract.py`, `tests/test_env_config.py`.
- **Prohibited:**
  - no pushes that trigger auto-deploy without owner approval
  - no values for `sync: false` keys in the repo
  - no enabling acquisition or enrichment switches on Render
- **Registry:** part of subsystem `deployment-release-ci` (see the primary doc).
- **Ticket candidates:**
  1. set `RUNR_MIGRATION_HEAD` to the registry head, or derive it (C3)
  2. consider `/health/ready` or a post-deploy readiness check (WS7-G5)
  3. document or decide preview environments
