# Render deployment

`render.yaml` defines three services:

| Service | Render type | Plan | Region | Purpose |
| --- | --- | --- | --- | --- |
| `runr-frontend` | Static site | Free | Global CDN | Builds and serves the Vite frontend. |
| `runr-api` | Docker web service | Starter | Frankfurt | Runs the public API without free-tier sleep. |
| `runr-worker` | Docker background worker | Standard | Frankfurt | Continuously claims and processes queued runs. |

The API and worker use the same Docker image with different role commands. The
worker is the only deployed queue consumer. Do not also deploy
`runr-process-next`, a queue-claiming cron job, or another worker unless queue
concurrency has been explicitly designed and tested.

## Deployment prerequisite

The Blueprint runs this before each API deploy:

```bash
./deploy/start.sh migrate
```

The command targets the committed repeatable migration runner. Migrations are
owned only by the `runr-api` pre-deploy hook; the worker must not run migrations.
Do not create or update the Render Blueprint until Turso and R2 credentials are
configured for both backend services.

## Create the Blueprint

1. Push the deployment files to the production Git branch and ensure GitHub CI passes.
2. In Render, choose **New > Blueprint** and connect this repository.
3. Select the repository's `render.yaml`.
4. Fill every environment variable marked `sync: false`.
5. Create the Blueprint and allow the first builds to complete.
6. Test the generated `onrender.com` URLs before configuring DNS.

Render is configured with `autoDeployTrigger: checksPass`, so production deploys wait for repository checks instead of deploying every commit immediately.

## Required values

Frontend:

```dotenv
VITE_API_BASE_URL=https://api.example.com/v1
VITE_CLERK_PUBLISHABLE_KEY=pk_live_...
```

API and worker shared persistence configuration:

```dotenv
RUNR_ENV=production
DATABASE_BACKEND=turso
TURSO_DATABASE_URL=libsql://...
TURSO_AUTH_TOKEN=...
OBJECT_STORAGE_BACKEND=r2
S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
S3_BUCKET=...
S3_REGION=auto
```

Workload providers used by queued runs must also be present on the worker and
rotated on both services:

```dotenv
SCRAPEOPS_API_KEY=...
DEEPSEEK_API_KEY=...
GEMINI_API_KEY=...
```

API-only web configuration includes:

```dotenv
BACKEND_ALLOWED_ORIGINS=https://runr-frontend.onrender.com,https://app.example.com
CLERK_SECRET_KEY=sk_live_...
CLERK_PUBLISHABLE_KEY=pk_live_...
CLERK_WEBHOOK_SECRET=whsec_...
```

Populate Creem and Google OAuth values on the API when those features are
enabled. Use production credentials, not local development keys. Render
services do not implicitly share environment variables.

## Validate the first deployment

1. Confirm `https://<api-service>.onrender.com/health/ready` returns HTTP 200.
2. Open the frontend and confirm browser requests target `/v1` on the API service.
3. Sign in through Clerk and call an authenticated endpoint.
4. Queue a run and verify `runr-worker` claims it without a cron delay.
5. Verify OCR, Chromium PDF rendering, and LibreOffice conversion from a real queued run.
6. Restart the API and confirm no required production data depended on its local filesystem.

## Custom domains

Use separate hostnames:

```text
app.example.com -> runr-frontend
api.example.com -> runr-api
```

For each hostname:

1. Open the Render service's **Settings > Custom Domains**.
2. Add the hostname.
3. Create the DNS records Render displays.
4. Remove conflicting `AAAA` records while verifying the domain.
5. Return to Render and verify the domain.
6. Wait for Render's managed TLS certificate, then test HTTPS.

After DNS works:

1. Set frontend `VITE_API_BASE_URL` to `https://api.example.com/v1` and redeploy the static site.
2. Set API `BACKEND_ALLOWED_ORIGINS` to include both the Render frontend URL and `https://app.example.com`.
3. Add the frontend domain to Clerk's allowed origins and redirect URLs.
4. Configure Clerk and Creem webhook URLs against `https://api.example.com/v1/...`.
5. Set `TRACKER_GOOGLE_OAUTH_REDIRECT_URI` to the production callback URL if Google integration is enabled.

## Scaling path

- Increase the API and worker plans independently when CPU or memory metrics justify it.
- The committed API plan remains Starter. While uploads and other expensive work
  remain synchronous in the API process, production may require Standard for
  sufficient memory/CPU headroom. Treat that as an explicit paid-plan decision;
  do not silently change the Blueprint plan.
- Keep Turso and object storage external to Render so API instances remain disposable and horizontally scalable.
- Do not attach a persistent disk for shared uploads or generated documents; a disk binds data to one service instance.

Changing service plans is a reviewed Render configuration and billing change.

## Migration and rollback

For every production deploy:

1. Create or verify a recoverable Turso backup/branch before a migration that
   changes data or removes compatibility.
2. Deploy `runr-api`; its pre-deploy hook applies migrations before the new API
   version receives traffic.
3. Confirm the API readiness check passes, then confirm `runr-worker` is healthy
   and claims a test run.
4. Verify migration status with the same production Turso credentials:

   ```bash
   ./deploy/start.sh migrate --status
   ```

If application verification fails, roll back the API and worker to the previous
known-good Render deploy together. Forward-compatible migrations should remain
in place. If a migration is not backward compatible, stop the worker first,
prevent new writes, restore the pre-migration Turso backup/branch, and then roll
back both services. Never run ad-hoc destructive SQL as a rollback.
