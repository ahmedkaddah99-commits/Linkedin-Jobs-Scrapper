# Runr: Render to Contabo migration report

Prepared 9 October 2026. This is a migration assessment, not a deployment or a new live ticket backlog.

## Recommendation

Move the customer API and customer worker to a dedicated Contabo VPS using the existing Dockerfiles. Build images in GitHub Actions, store them in GitHub Container Registry (GHCR), and deploy immutable image digests. Use Docker Compose for service definitions and Caddy for HTTPS and routing. Keep Turso, R2, Clerk, Creem and the existing acquisition VPS initially. Serve the frontend through Caddy if the goal is to leave Render completely; retaining Render's static hosting temporarily is a smaller first step.

Runr does not need a rewrite to leave Render. It needs a reliable replacement for the platform services Render currently supplies. A single VPS can replace the declared customer compute, but it does not reproduce multi-host failover. Blue/green deployment protects releases; it does not protect against loss of the server.

Prefer a separate customer VPS initially. Putting customer requests, document rendering and acquisition on one host makes resource contention and host outages affect everything. Consolidation should follow measured capacity testing.

## Evidence and limits

Reviewed local `render.yaml`, `Dockerfile.api`, `Dockerfile.worker`, `deploy/start.sh`, `.github/workflows/ci.yml`, customer systemd units, health routes, release metadata code and deployment/data/security documentation. Current files take precedence over September documentation: for example, the local Blueprint now declares migration `075_catalog_storage_retention`, while the older Render document describes `058_customer_task_queue`.

The checkout has existing uncommitted changes, including database and acquisition/publication work. They were not modified. This assessment does not establish which of those changes are deployed.

Render's dashboard/API, the actual invoice, Contabo account, live DNS and host capacity were not inspected. Service configuration below is repository evidence, not proof of live service state. Official provider documentation was checked online; account-specific prices, add-ons, region, taxes and entitlements still require reconciliation.

## What is actually moving

| Component | Repository evidence | Migration treatment |
|---|---|---|
| Frontend | Static Vite SPA; `npm ci && npm run build`; `frontend/dist`; SPA rewrite | Publish a versioned static build and serve through Caddy, or retain static hosting temporarily |
| API | Docker; Frankfurt; legacy Starter plan; `start.sh api` | Run existing API image behind HTTPS proxy |
| Customer worker | Docker; Frankfurt; legacy Standard plan; customer role; capacity one | Run existing worker image privately with queue/heartbeat monitoring |
| Migrations | API pre-deploy runs `start.sh migrate` | Add a serialized one-shot migration stage before release activation |
| Acquisition | Blueprint explicitly disables acquisition on customer services; VPS systemd tooling exists | Keep existing acquisition execution, state and timers intact |
| Database | Turso/libSQL | Keep same authoritative database for production; isolate staging |
| Binary artifacts | R2 over S3-compatible API | Keep same buckets/keys and signed-download behavior |
| Identity and billing | Clerk and Creem | Keep providers; update endpoints and allowed origins as needed |
| Other providers | DeepSeek, ScrapeOps, Google tracker OAuth | Preserve required configuration and verify new-host connectivity |

No Render Postgres, Redis/Key Value, persistent disk, or Render cron service is declared in this Blueprint. Do not add replacements merely because Render offers them. Runr's existing queue should be retained; this migration does not establish a need for Redis.

## Render benefits and their replacements

Render builds your container **from your Dockerfile**; the app's dependencies and start behavior are already defined by Runr. You can run those same images elsewhere. Render also handles the surrounding build and release lifecycle. [Docker documentation](https://render.com/docs/docker).

| Benefit | Runr relevance | Contabo replacement / work |
|---|---|---|
| Managed Docker build and caching | API and worker use it | Actions Buildx builds, cache and GHCR publishing; pull images on VPS instead of compiling on production |
| Git-triggered deployment and path filters | Declared for all three services | Release workflow restricted to approved branch/revision, after required CI; preserve affected-service filters |
| Static site build and delivery | Frontend uses it | CI frontend build; versioned artifacts, compression and cache rules; a global CDN is a separate addition |
| Custom domains and automatic TLS | Frontend domain declared; API uses Render hostname | Own API domain, DNS and Caddy certificate issuance/renewal |
| Pre-deploy commands | Database migration configured | Serialized migration job with failure gate, credentials and a retained receipt |
| Health-gated releases | API uses `/health/live` | Candidate startup plus readiness gate before proxy switch; keep old API available |
| Release overlap and graceful shutdown | API 60 seconds; worker 300 seconds | Blue/green API deployment, draining, matching stop grace periods and worker lease tests |
| Restart/recovery | Platform operation | Docker restart policy, enabled Docker daemon, external liveness supervision and reboot test |
| Deploy history and rollback | Platform feature | Release manifest with commit, image digests, configuration version and previous release; tested rollback script |
| Secrets and generated service variables | Blueprint uses both | Separate protected runtime environment files, restricted deployment access, explicit hostname/release variables |
| Private networking | Platform capability; queue/database are external | Compose private network; expose proxy only; worker has no public port |
| Logs, metrics and alerts | Platform capability | Extend Grafana Alloy to container logs, API errors/latency, worker heartbeat/queue age and host resource alarms |
| Preview environments | Worker preview plan declared; complete preview usage unknown | Optional isolated staging deployment with separate database, storage and provider configuration |
| Infrastructure as code | Blueprint | Versioned Compose, proxy config, release workflow and host setup/runbook |
| Managed host maintenance/security | Platform responsibility | OS/container updates, firewall, SSH policy, Docker security, recovery and maintenance ownership |
| Scaling | Available; no autoscaling declaration found | Manual capacity increase first; replicas require queue semantics testing and sufficient database capacity |

Render's release lifecycle and health checks are documented in [Deploys](https://render.com/docs/deploys) and [Health checks](https://render.com/docs/health-checks). Static sites include managed delivery and TLS in [Static sites](https://render.com/docs/static-sites). Availability of previews, logging and other features depends on plan; do not assume every advertised feature is currently used.

Container restart policies handle exited processes. An unhealthy-but-running container needs an explicit monitoring/recovery policy; marking it unhealthy alone does not implement Render-style recovery. [Docker restart policies](https://docs.docker.com/engine/containers/start-containers-automatically/).

## What already exists, and what is missing

**Reusable:** separate API/worker images, role-based startup, migration entrypoint, release metadata, CI tests and cached image builds, customer systemd units with restart/resource/security settings, acquisition state backup/restore tooling, and Grafana Cloud Alloy infrastructure.

**Missing from the reviewed CI:** image publishing and VPS deployment. Its Docker jobs use `push: false`, and the Docker job does not depend on `backend-full`. A production release must wait for all required suites, including the full backend checks. Current Blueprint auto-deploy triggers are `commit`, so CI-gated activation needs to be made explicit in the replacement workflow.

**Missing as a complete migration package:** reviewed production Compose definition, HTTPS proxy configuration, frontend artifact publication, serialized migration/deployment orchestration, blue/green activation, customer application monitoring, rollback automation and a rehearsed host recovery procedure.

The native customer systemd units are a viable alternative to Docker, but they do not prove production readiness. Their memory ceilings are 4 GB for API and 12 GB for worker; these are limits, not measured RAM consumption. Their dependency ordering is not a database migration or application readiness gate. Choose one supervisor per workload.

## Configuration and compatibility work

1. **Establish an owned API hostname**, such as `api.userunr.com`. The existing `runr-api.onrender.com` hostname cannot be transferred to Contabo. Inventory clients that use it, including any distributed extension configuration, before shutting it down.
   The extension already contains these hostnames in `apps/browser-extension/src/auth/config.ts`, `wxt.config.ts`, `src/panel/script-registration.ts` and `scripts/verify-manifest.mjs`. Update runtime URLs, host permissions, allowed origins, exclusion rules and verification fixtures together; distribute an updated extension and account for users still running the old version.
2. **Rebuild the frontend with the new API endpoint.** `VITE_API_BASE_URL` currently points at the Render API `/v1` URL. Vite settings are build-time values; changing a runtime environment file will not fix an already-built frontend. Audit the `VITE_API_EXTERNAL_HOSTNAME` path too.
3. **Resolve frontend domain discrepancies.** The Blueprint declares `userunr.com`, while CORS and frontend code reference `app.userunr.com`. Verify live DNS and routing for apex, app and www instead of assuming one is obsolete.
4. **Replace generated Render metadata.** Explicitly supply `RUNR_RELEASE_COMMIT`, `RUNR_RELEASE_BRANCH`, contract version and image service metadata. Audit fallbacks to `RENDER_GIT_COMMIT`, `RENDER_GIT_BRANCH`, `RENDER_EXTERNAL_HOSTNAME` and `RENDER_FRONTEND_EXTERNAL_HOSTNAME`. Keep the current release branch names initially unless their contracts and automation are changed together.
5. **Preserve role boundaries.** Customer worker remains `WORKER_ROLE=customer`, with a unique worker ID and intended capacity. Preserve disabled live acquisition, discovery and company enrichment switches on customer compute.
6. **Preserve database/storage semantics.** Keep `DATABASE_BACKEND=turso` and R2 configuration. The simultaneous `RUNR_STORAGE_BACKEND=sqlite` setting is an existing application contract, not evidence that production data can be replaced by a local SQLite file.
7. **Transfer configuration securely.** Compare live API and worker environment-variable names against the Blueprint; dashboard-only overrides may exist. Keep Turso/R2/Clerk/Creem/provider/OAuth secrets out of Git, images, build logs and this report. Copy only required secrets to each role. Frontend builds receive public Vite values only.
8. **Update identity, billing and OAuth routing.** Verify Clerk origins and webhook delivery, Creem webhook and checkout return URLs, `APP_FRONTEND_ORIGIN`/`FRONTEND_ORIGIN`, Google OAuth redirect URI, exact browser-extension origins and CORS. Preserve webhook bodies/signatures and query strings through the proxy. Verify actual externally registered paths, including `/v1` routing.
9. **Retain document dependencies.** The images include Node 22, Chromium/Playwright, LibreOffice, OCR and fonts. API also retains document rendering compatibility paths. Test both roles; removing these dependencies is separate optimization work.
10. **Resolve Python reproducibility.** Repository instructions require Python 3.12.7, while Docker uses floating `python:3.12-slim-bookworm` and CI specifies `3.12`. Pin and verify the approved patch version as part of the release pipeline; do not assume a rebuilt image has the required interpreter.

## Proposed deployment flow

`approved Git SHA → required CI → build API/worker + frontend → publish immutable artifacts → VPS pulls → migration → candidate checks → proxy activation → worker handover → receipt`

Build off-host to avoid acquisition/customer traffic competing with Chromium dependency installation and image compilation. GitHub documents the [image publishing workflow](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images). Restrict registry and SSH permissions, verify the host key, serialize deployment jobs and retain known-good image digests.

Use a private Compose network, Caddy on public ports 80/443, API internal port 8000, and a worker without published ports. Persist Caddy certificate state and required runtime data with suitable ownership for the images' UID 10001. Separate API/worker writable directories; inventory `.backend_data` for durable files before deciding which paths are disposable. Configure log rotation, disk alerts and safe image cleanup that retains rollback images. Caddy supports [automatic HTTPS](https://caddyserver.com/docs/automatic-https).

For the frontend, deploy complete versioned builds atomically. Preserve SPA fallback, serve actual assets with correct content types, avoid caching HTML/version checks, and cache hashed assets. Keep old hashed assets accessible during release overlap so open tabs can still load them. Backend routes must never fall through to `index.html`.

Run migrations once per release under a deployment lock. Migration failure stops activation. Backward-compatible schema changes allow the old API to serve during deployment. Code rollback does not undo a database migration; destructive schema changes require a separate restore/compatibility plan. Render has the same distinction: [Rollbacks](https://render.com/docs/rollbacks).

Use `/health/live` for lightweight liveness and `/health/ready` for release readiness. The reviewed readiness route checks Turso reads and production backend configuration. `?probe=1` additionally writes/reads/deletes database and object-storage probes: use it deliberately during acceptance, not as a frequent unauthenticated public monitor. Confirm effective paths through the proxy.

Do not overlap old/new customer workers blindly. Test existing task leases, heartbeats, recovery and idempotency. Drain the old worker with the current 300-second grace period, then transfer ownership according to verified queue behavior. Give the API its 60-second grace period and test requests during proxy switching.

## Host size and costs

For a **separate customer host**, a provisional starting target is 4 vCPU and 8 GB RAM with NVMe storage. This is an engineering estimate, not a measured minimum: concurrent Chromium/LibreOffice tasks, image sizes, old/new API overlap and disk use need benchmarking. An all-in-one host with acquisition needs fresh measurements; no exact size is justified from this review. Measure peak RSS, CPU saturation, OOM events, disk growth, API p95 latency and queue age under representative workloads before committing to a plan.

Render's declared plans correspond to 0.5 CPU/512 MB for Starter and 1 CPU/2 GB for Standard. See [official compute plans](https://render.com/docs/compute-plans). Public pricing search results indicate approximately $7 + $25/month for that declared pair, but this is **not the verified Runr bill**. Additional replicas, upgraded live plans, workspace fees, bandwidth and build usage can change it. Reconcile [Render pricing](https://render.com/pricing) with the invoice before estimating savings.

Contabo's current public catalog varies by currency, region and product; its pricing page could not be fully fetched in this review. Use the actual order quote from [Contabo pricing](https://contabo.com/en-us/pricing/), including VAT, setup fees, billing term, backup add-on and any networking/region charges. Verify the selected plan's fair-use policy rather than treating unlimited traffic as unlimited guaranteed throughput. [Traffic policy](https://help.contabo.com/en/support/solutions/articles/103000271195-are-there-any-bandwidth-or-traffic-limits-at-contabo/).

Compare: **removed Render charges − incremental VPS, backup, registry/CI, monitoring/CDN and operations costs**. If acquisition VPS spend already exists, it is baseline cost; only an upgrade or additional customer host is incremental. Turso, R2, Clerk, Creem and provider usage remain. Include a short period of overlapping Render/VPS billing for migration and rollback.

## Operations required before cutover

- Host: supported Linux, SSH keys, restricted administrative access, firewall, working time synchronization, security updates and a reviewed reboot/maintenance process. Check Docker-published ports against firewall rules; only the proxy should be public.
- Application: resource limits, correct proxy headers/timeouts/upload sizes, worker restart and stale-task recovery, separate customer/acquisition roles, container and daemon startup after reboot.
- Monitoring: external HTTPS uptime, API error/latency, certificate expiry, worker heartbeat, queue age/failures, CPU/RAM/OOM, disk/inodes and backup freshness. Existing Alloy acquisition dashboards need customer-service additions and a tested alert destination.
- Recovery: encrypted off-host configuration backup, recoverable images/frontend artifacts, Turso backup/export recovery, R2 retention/recovery, and existing producer state checkpoints. Test restoration on a clean host and record recovery time/data-loss objectives.

Contabo's optional Auto Backup retains up to ten daily backups off-server and restores the whole VPS; it does not back up external Turso/R2 services. Provider snapshots are useful before host changes, but independent recoverable artifacts/configuration are still needed. [Contabo Auto Backup](https://docs.contabo.com/docs/servers-hosting/vps-auto-backup/).

## Ordered migration and acceptance

| Stage | Required work | Exit evidence |
|---|---|---|
| 1. Inventory | Reconcile live services, bill, revisions, env names, domains, callbacks, local durable files and host headroom | Sanitized inventory and agreed budget/availability target |
| 2. Delivery setup | Add publish/release workflow, Compose, proxy, env template, migration lock, rollback and host setup | Exact commit and digests; reproducible build; all required CI passes |
| 3. Isolated staging | Separate Turso database/storage namespace; test identity and billing configuration; production acquisition off | Login, catalog/jobs, task lifecycle, uploads, CV/cover letter/PDF download, signed storage, billing/webhook and OAuth checks |
| 4. Failure rehearsal | Failed image start, migration failure, worker interruption, API switch, proxy reload, reboot and clean-host restore | Old release survives failed activation; no lost/duplicate tasks; documented rollback and recovery time |
| 5. Production canary | Deploy candidate privately; verify production connectivity and allowed bounded probes; save backups | Ready checks, schema/contract compatibility, capacity and monitored application checks |
| 6. Cutover | Freeze competing releases; drain Render customer worker; activate VPS worker/API; rebuild frontend; change DNS/callbacks | Correct service revision, external HTTPS/CORS/auth, webhook delivery and successful customer task |
| 7. Observe and retire | Monitor a representative usage window; keep rollback available; then stop/delete billed Render compute | Stable queue/latency/error rates; no Render-hostname clients/webhooks remaining; invoice reconciliation |

DNS propagation can send requests to both hosts. Keep both API versions compatible with the shared database and preserve old endpoints until clients and integrations have transitioned. A rollback switches routing and worker ownership together and restores the matching configuration; it does not start both worker fleets indiscriminately. Avoid simultaneously changing acquisition runtime or moving the database.

If the existing acquisition host is chosen later, use [VPS verification](vps-predeployment-verification.md): `/opt/runr` is documented as a deployed directory without Git, and `deploy/deploy.sh` is not an immutable release installer. Do not overlay it with a customer release. Preserve acquisition code/state and verify installed file identity; adding customer services must not casually restart shared acquisition targets.

The migration is ready only when a customer can sign in, retrieve jobs, complete an asynchronous task, generate/download documents and exercise billing integrations on the new host, and a failed deployment plus worker interruption plus host restore have been demonstrated. A successful container start alone is insufficient.

## Remaining decisions

The account-specific work needed to finalize the plan is: reconcile the actual Render bill and live service settings; confirm whether Contabo means a new customer VPS or the existing acquisition host; measure host capacity; choose the final API/frontend domains; and agree on acceptable downtime and restore targets. None of these prevents preparing the deployment package, but they determine final sizing and cutover details.

The essential replacement is **CI builds + registry + controlled deployment + HTTPS + migration gates + health checks + worker handover + monitoring + tested recovery**. With those in place, Runr can leave Render without losing the operational features its current architecture depends on.
