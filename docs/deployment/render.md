# Render deployment

`render.yaml` defines three services:

| Service | Render type | Plan | Region | Purpose |
| --- | --- | --- | --- | --- |
| `runr-frontend` | Static site | Free | Global CDN | Builds and serves the Vite frontend. |
| `runr-api` | Docker web service | Starter | Frankfurt | Runs the public API without free-tier sleep. |
| `runr-process-next` | Docker cron job | Starter | Frankfurt | Processes one queued run every five minutes. |

The API and cron job use the same Docker image. A future continuous worker can use `./deploy/start.sh worker` without changing application code.

## Deployment prerequisite

The Blueprint runs this before each API deploy:

```bash
./deploy/start.sh migrate
```

The command targets the committed repeatable migration runner. Do not create the
Render Blueprint until Turso and R2 credentials are configured for both the API
and cron services.

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

API:

```dotenv
BACKEND_ALLOWED_ORIGINS=https://app.example.com
TURSO_DATABASE_URL=libsql://...
TURSO_AUTH_TOKEN=...
CLERK_SECRET_KEY=sk_live_...
CLERK_PUBLISHABLE_KEY=pk_live_...
CLERK_WEBHOOK_SECRET=whsec_...
```

Populate LemonSqueezy, ScrapeOps, DeepSeek, Gemini, and Google OAuth values when those features are enabled. Use production credentials, not local development keys.

The cron service needs the same Turso and workload-provider credentials as the API. Render services do not implicitly share environment variables, so verify both services after any credential rotation.

## Validate the first deployment

1. Confirm `https://<api-service>.onrender.com/health/ready` returns HTTP 200.
2. Open the frontend and confirm browser requests target `/v1` on the API service.
3. Sign in through Clerk and call an authenticated endpoint.
4. Queue a run and verify the cron job claims it within five minutes.
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
2. Set API `BACKEND_ALLOWED_ORIGINS` to `https://app.example.com`.
3. Add the frontend domain to Clerk's allowed origins and redirect URLs.
4. Configure Clerk and LemonSqueezy webhook URLs against `https://api.example.com/v1/...`.
5. Set `TRACKER_GOOGLE_OAUTH_REDIRECT_URI` to the production callback URL if Google integration is enabled.

## Scaling path

- Replace the cron service with a Render Background Worker using `./deploy/start.sh worker` when five-minute polling is insufficient.
- Increase the API and worker plans independently when CPU or memory metrics justify it.
- Keep Turso and object storage external to Render so API instances remain disposable and horizontally scalable.
- Do not attach a persistent disk for shared uploads or generated documents; a disk binds data to one service instance.

Changing service plans or replacing cron with a worker is a Render configuration change. The role-based image avoids an application-code change for that transition.
