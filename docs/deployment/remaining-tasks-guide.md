# Remaining deployment tasks guide

Last updated: 2026-06-18.

This guide covers what is left after the local deployment-readiness work. Follow the tasks in order. Do not skip ahead: later steps depend on credentials, URLs, DNS records, and successful health checks from earlier steps.

## Current status

Already done in code:

- Local SQLite and Turso/libSQL database abstraction.
- Repeatable database migration runner.
- Environment validation for local vs production.
- Render deployment files: `Dockerfile`, `.dockerignore`, `render.yaml`, `deploy/start.sh`.
- Health endpoints: `/health/live` and `/health/ready`.
- S3-compatible object storage abstraction for local and R2/S3.
- Durable object keys for uploaded CVs and generated artifacts.
- Frontend API base URL handling.
- Deployment documentation.
- Focused backend/API/frontend verification.

Not done yet:

- Real Turso production database.
- Real Turso development branch/database.
- Real R2/S3 bucket and credentials.
- Render services created from the repo.
- Production environment variables in Render.
- Custom domain DNS.
- Docker build verification on a running Docker engine.
- Real cloud smoke test.
- Clean source-control commit structure.

## Recommended final architecture

Use:

- Render for frontend/API/worker hosting.
- Turso for SQLite-compatible production database.
- Cloudflare R2 or another S3-compatible object store for uploaded CVs and generated files.
- GitHub as the source of truth.

Do not rely on Render local disk for customer files. Render disk should be treated as disposable runtime cache. The app now stores durable file references in object storage.

For your budget: Render Free Tier is acceptable for private testing, but customer-facing use should use at least an always-on paid Render web service. Sleeping free services are not a good customer experience.

## Phase 1: Prepare source control

Goal: get the current working tree into a reviewable branch before connecting cloud automation.

1. Create a deployment branch:

   ```bash
   git switch -c deployment/render-turso-r2
   ```

2. Review current changes:

   ```bash
   git status --short
   git diff --stat
   ```

3. Do not commit secrets, local data, generated artifacts, or private user config.

4. Recommended commit chunks:

   - database/libSQL/migrations
   - env validation/runtime config
   - object storage
   - Render/Docker/CI
   - docs/tests

5. Push the branch:

   ```bash
   git push -u origin deployment/render-turso-r2
   ```

Blocking output you need before continuing:

- GitHub branch URL.
- Confirmation that no secret files were committed.

## Phase 2: Create Turso databases

Goal: create separate production and development databases.

Use Turso CLI from WSL or a Unix-like shell if possible. On Windows PowerShell, `turso` will not be available unless you installed a Windows binary yourself. The official Windows path is WSL.

1. Enter WSL from PowerShell:

   ```powershell
   wsl
   ```

2. Install Turso CLI inside WSL if `turso` is not found:

   ```bash
   curl -sSfL https://get.tur.so/install.sh | bash
   source ~/.bashrc
   turso
   ```

3. Authenticate.

   Browser login:

   ```bash
   turso auth login
   ```

   Headless/manual token login:

   ```bash
   turso config set token "<PASTE_NEW_TURSO_ACCESS_TOKEN_HERE>"
   ```

   Do not paste real Turso tokens into Git, docs, chat, screenshots, or issue trackers. If a token is exposed, revoke it and create a new one before continuing.

4. Verify authentication:

   ```bash
   turso db list
   ```

5. Create production database:

   ```bash
   turso db create runr-prod --wait
   ```

6. Create development database from production:

   ```bash
   turso db create runr-dev --from-db runr-prod --wait
   ```

   Alternative: if you want the dev DB to start empty, create it normally:

   ```bash
   turso db create runr-dev --wait
   ```

7. Get URLs:

   ```bash
   turso db show --url runr-prod
   turso db show --url runr-dev
   ```

8. Create DB tokens:

   ```bash
   turso db tokens create runr-prod
   turso db tokens create runr-dev
   ```

Important: Turso branches/databases are separate. Schema/data movement is your responsibility through migrations or explicit copy/branch workflows.

Blocking output you need before continuing:

- `RUNR_PROD_TURSO_DATABASE_URL`
- `RUNR_PROD_TURSO_AUTH_TOKEN`
- `RUNR_DEV_TURSO_DATABASE_URL`
- `RUNR_DEV_TURSO_AUTH_TOKEN`

## Phase 3: Create Cloudflare R2 bucket

Goal: create durable object storage for CV uploads and generated documents.

1. In Cloudflare dashboard, go to:

   `Storage & databases > R2 > Overview`

2. Create a bucket, for example:

   ```text
   runr-prod-artifacts
   ```

3. Create an R2 S3-compatible API token:

   - Permission: Object Read & Write.
   - Scope: specific bucket only.
   - Bucket: `runr-prod-artifacts`.

4. Copy credentials immediately. You will not be able to view the secret again.

5. Find your R2 S3 endpoint:

   ```text
   https://<ACCOUNT_ID>.r2.cloudflarestorage.com
   ```

Blocking output you need before continuing:

- `S3_ENDPOINT_URL`
- `S3_ACCESS_KEY_ID`
- `S3_SECRET_ACCESS_KEY`
- `S3_BUCKET`

## Phase 4: Prepare local development env

Goal: local app points to dev Turso and local object storage unless you intentionally test R2.

Create or update local `dev.env` from `dev.env.example`.

Recommended local dev values:

```env
APP_ENV=development
DATABASE_BACKEND=turso
TURSO_DATABASE_URL=<RUNR_DEV_TURSO_DATABASE_URL>
TURSO_AUTH_TOKEN=<RUNR_DEV_TURSO_AUTH_TOKEN>

OBJECT_STORAGE_BACKEND=local
OBJECT_STORAGE_LOCAL_ROOT=.backend_storage/objects
OBJECT_STORAGE_CACHE_ROOT=.backend_storage/cache

FRONTEND_ORIGIN=http://localhost:5173
API_BASE_URL=http://127.0.0.1:8000
```

Then run:

```bash
python -m backend.database.migrate --status
python -m backend.database.migrate
python -m backend.database.migrate --status
```

Blocking output you need before continuing:

- Migration status output shows no checksum errors.
- Local app starts.
- Local login/API flow still works.

## Phase 5: Create Render services

Goal: Render owns runtime infrastructure from `render.yaml`.

1. Push your branch to GitHub.

2. In Render, create a new Blueprint from your GitHub repo.

3. Confirm Render detects `render.yaml` at repo root.

4. Services expected from the blueprint:

   - Static frontend service.
   - Docker API/web service.
   - Docker Standard background worker (`runr-worker`) for queued work.

5. Configure the API service as paid/always-on before offering to customers. Free is acceptable only for private testing.

6. Confirm the API service health check path is:

   ```text
   /health/ready
   ```

Blocking output you need before continuing:

- Render API service URL.
- Render frontend URL.
- Render background worker exists.

## Phase 6: Add Render environment variables

Goal: production services use production Turso and R2.

Set these on both the Render API and worker services:

```env
RUNR_ENV=production
DATABASE_BACKEND=turso
TURSO_DATABASE_URL=<RUNR_PROD_TURSO_DATABASE_URL>
TURSO_AUTH_TOKEN=<RUNR_PROD_TURSO_AUTH_TOKEN>

OBJECT_STORAGE_BACKEND=r2
S3_ENDPOINT_URL=<S3_ENDPOINT_URL>
S3_ACCESS_KEY_ID=<S3_ACCESS_KEY_ID>
S3_SECRET_ACCESS_KEY=<S3_SECRET_ACCESS_KEY>
S3_BUCKET=<S3_BUCKET>
S3_REGION=auto

OBJECT_STORAGE_CACHE_ROOT=/tmp/runr-object-cache
```

Set workload-provider secrets on both API and worker when queued work uses them:

```env
DEEPSEEK_API_KEY=<if used>
SCRAPEOPS_API_KEY=<if used>
```

Set API-only application and web-provider secrets on the API:

```env
CLERK_SECRET_KEY=<if used>
CLERK_WEBHOOK_SECRET=<if used>
CREEM_API_KEY=<creem_live_or_test_key_for_this_environment>
CREEM_WEBHOOK_SECRET=<creem_webhook_secret_for_this_environment>
CREEM_LAUNCH_PRODUCT_ID=<creem_product_id_for_launch>
CREEM_MOMENTUM_PRODUCT_ID=<creem_product_id_for_momentum>
CREEM_SCALE_PRODUCT_ID=<creem_product_id_for_scale>
RUNR_SECRET_KEY=<generate strong random value>
LOCAL_OBJECT_STORAGE_SIGNING_SECRET=<not used for r2, but safe to set anyway>
```

For frontend static service:

```env
VITE_API_BASE_URL=https://<your-render-api-host>/v1
```

Later, after custom domain:

```env
VITE_API_BASE_URL=https://api.<your-domain>/v1
```

Blocking output you need before continuing:

- Render deploy completes.
- API service does not crash at startup.
- `/health/live` returns 200.
- `/health/ready` returns 200.

## Phase 7: Run production migrations

Goal: production Turso has the expected schema.

Preferred: let the `runr-api` Render pre-deploy command run
`./deploy/start.sh migrate`. Do not configure migrations on `runr-worker`.

Manual verification:

```bash
RUNR_ENV=production \
DATABASE_BACKEND=turso \
TURSO_DATABASE_URL=<RUNR_PROD_TURSO_DATABASE_URL> \
TURSO_AUTH_TOKEN=<RUNR_PROD_TURSO_AUTH_TOKEN> \
OBJECT_STORAGE_BACKEND=r2 \
S3_ENDPOINT_URL=<S3_ENDPOINT_URL> \
S3_ACCESS_KEY_ID=<S3_ACCESS_KEY_ID> \
S3_SECRET_ACCESS_KEY=<S3_SECRET_ACCESS_KEY> \
S3_BUCKET=<S3_BUCKET> \
python -m backend.database.migrate --status
```

If status is clean, apply:

```bash
python -m backend.database.migrate
```

Do not run destructive SQL manually in production.

Blocking output you need before continuing:

- Production migration status is clean.
- No checksum mismatch.
- No failed migration.

## Phase 8: Configure custom domain

Goal: users access the app from your domain.

Recommended:

```text
app.<your-domain>  -> frontend
api.<your-domain>  -> API
```

You can also use root domain for frontend:

```text
<your-domain>      -> frontend
api.<your-domain>  -> API
```

Steps:

1. In Render frontend service, add the frontend custom domain.
2. In Render API service, add the API custom domain.
3. In your DNS provider, create the DNS records Render gives you.
4. Wait for certificate provisioning.
5. Update frontend env:

   ```env
   VITE_API_BASE_URL=https://api.<your-domain>/v1
   ```

6. Redeploy frontend.

Blocking output you need before continuing:

- Frontend custom domain loads over HTTPS.
- API custom domain loads `/health/live` over HTTPS.
- Frontend can call API without CORS errors.

## Phase 9: Production smoke test

Goal: verify the real system, not just deployment.

Run this checklist:

1. Open frontend custom domain.
2. Sign in.
3. Upload a CV.
4. Confirm upload succeeds.
5. Create a workspace.
6. Start a small/manual run.
7. Confirm run state changes in the UI.
8. Download generated artifact.
9. Confirm artifact survives redeploy:

   - Redeploy API service.
   - Download the same artifact again.

10. Check Render logs for errors.
11. Check Turso database has rows.
12. Check R2 bucket has objects.

Blocking output you need before considering deployment complete:

- CV upload works.
- Run creation works.
- Artifact download works after redeploy.
- `/health/ready` is green.
- No startup errors in Render logs.

## Phase 10: Cost and scaling decision

Private use:

- Render Free Tier is acceptable if sleeping is tolerable.
- Turso free/low tier is acceptable if usage is low.
- R2 low usage should be cheap.

Customer use:

- Use paid always-on Render API service.
- Keep frontend static.
- Keep database on Turso.
- Keep artifacts on R2/S3.
- Upgrade Render instance size when CPU/memory or latency requires it.
- Upgrade Turso/R2 plans when storage, request volume, or limits require it.

No code change should be required for this scale-up if the environment variables stay the same.

## Coding tasks to ask Codex after manual blockers

Use these prompts after completing the manual cloud steps.

### Prompt 1: verify cloud env and production startup

```text
I have created Turso production/dev databases, R2 bucket, and Render services.
Please verify the deployment configuration in this repo against the real env vars I provide.
Check render.yaml, Dockerfile, deploy/start.sh, backend env validation, frontend VITE_API_BASE_URL, and migration startup.
Do not change architecture unless necessary.
Run the relevant tests and give me a deploy readiness report.
```

Provide:

- Render service names.
- Render API URL.
- Render frontend URL.
- Custom domains if configured.
- Redacted env var names present in Render.

### Prompt 2: run real Turso/R2 integration smoke tests

```text
Using the production-like env vars I provide locally, run a safe integration smoke test against Turso and R2.
Verify:
1. database connection works,
2. migrations status/apply works,
3. object storage put/get/delete works with a temporary test key,
4. API readiness check works.
Do not write destructive SQL and do not touch user data except a clearly namespaced temporary smoke-test object.
```

Provide:

- Turso production or staging URL.
- R2 bucket credentials.
- Confirmation whether to test prod or staging/dev.

### Prompt 3: organize source-control commits

```text
The deployment work is implemented but the worktree is dirty.
Please inspect git status and group the changes into safe logical commits.
Do not discard any user changes.
Propose the commit plan first, then apply it if safe.
Suggested groups:
1. database/libSQL/migrations,
2. env/runtime validation,
3. object storage,
4. Render/Docker/CI,
5. docs/tests.
```

### Prompt 4: production smoke-test bugfix pass

```text
I deployed to Render and ran the production smoke test.
Here are the failing symptoms/logs: <paste logs>.
Diagnose the root cause from the codebase and implement the smallest safe fix.
Run focused tests and update deployment docs if behavior changed.
```

### Prompt 5: add staging environment

```text
Add a staging deployment path so I can test Render + Turso + R2 before production.
Use the existing architecture.
Add or update render.yaml/docs/env examples as needed.
The desired environments are:
- local development,
- staging,
- production.
Keep production and staging data isolated.
```

### Prompt 6: automate Turso dev branch/database refresh

```text
Add a safe workflow/documented command to refresh the local/dev Turso database from production or a production snapshot.
It must avoid overwriting production.
Prefer explicit confirmation and clear naming.
Update docs with the workflow and any GitHub Actions or CLI scripts needed.
```

## Final acceptance checklist

Deployment is ready for personal hosted use when:

- Code is pushed to GitHub.
- Render services exist and deploy successfully.
- Production env vars are set.
- Turso migrations are applied.
- R2 object storage works.
- Custom domain works over HTTPS.
- `/health/ready` returns 200.
- CV upload/download works after redeploy.

Deployment is ready for first customers when:

- API service is always-on paid Render tier.
- You have a staging environment or at least a dev Turso/R2 path.
- You have backup/export procedure for Turso.
- You have log/error review process.
- You have clear secret rotation procedure.
- You have tested upgrade path by changing only Render plan, not code.
