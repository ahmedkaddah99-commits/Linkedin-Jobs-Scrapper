# Runr Production Surfaces

Use this reference only after `production-debug` is invoked and provider-specific details are needed.

## Environment Source

Primary backend env file for local diagnostics: `user_config/.env`.

Frontend env can be separate: `frontend/.env.local`.

Do not print values. Key presence is enough.

## Providers

Render:

- Required key: `RENDER_API_KEY`.
- Check services: `GET https://api.render.com/v1/services?limit=20`.
- Expected resources: `runr-api`, `runr-worker`, `runr-frontend`.
- Check logs: `GET https://api.render.com/v1/logs` with `ownerId`, `resource`, `startTime`, `endTime`, `limit`.
- Use RFC3339 timestamps for logs.

Turso/libSQL:

- Required keys: `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`.
- Use `backend.database.connection.connect_database(...)`.
- Important tables for run bugs: `runs`, `run_stage_results`, `run_job_sets`, `run_jobs`, `artifacts`, `reviews`, `run_document_bindings`.

Cloudflare R2/S3:

- Required keys: `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`.
- Safe probe: write/read/delete a tiny object under `diagnostics/`.
- For artifact bugs, verify the object key from artifact metadata/path if present.

Clerk:

- Required keys: `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY`, `CLERK_WEBHOOK_SECRET`.
- Read-only checks: JWKS fetch from publishable-key issuer, `/v1/users?limit=1`.
- Browser/session bugs still need a browser token or frontend diagnostics.

ScrapeOps:

- Required key: `SCRAPEOPS_API_KEY`.
- Read-only usage endpoint: `backend.integrations.scrapeops.fetch_account_usage`.
- Proxy health may need a longer timeout than 8 seconds.

DeepSeek:

- Required key: `DEEPSEEK_API_KEY`.
- Safe probe: tiny chat completion with max tokens <= 5.

Creem:

- Required keys: `CREEM_API_KEY`, `CREEM_WEBHOOK_SECRET`, `CREEM_LAUNCH_PRODUCT_ID`, `CREEM_MOMENTUM_PRODUCT_ID`, `CREEM_SCALE_PRODUCT_ID`.
- Base URL depends on test/live key; see `backend.integrations.creem._creem_api_base_url`.
- Read-only check: `/discounts/search` without stale `page` or `limit` query fields.

Google OAuth:

- Required config: `TRACKER_GOOGLE_OAUTH_CLIENT_ID`, `TRACKER_GOOGLE_OAUTH_CLIENT_SECRET`, `TRACKER_GOOGLE_OAUTH_REDIRECT_URI`.
- Static config can be checked locally.
- Live account access requires a user OAuth token/session flow.

## Run Invariants

Document generation runs:

- Must not complete if selected input jobs exist and no usable generated document exists.
- Usable means no `doc_generation_error` and either a generated document path (`cv_docx` or `tailored_cv_docx`) or a matching generated document artifact.

Queued/running runs:

- A queued run must be claimable by a live worker.
- A running run must have recent worker heartbeat or be recovered/requeued/failed.

Frontend `Failed to fetch`:

- Needs browser Network and Console evidence unless backend logs clearly show API outage.
- Check deployed frontend API base URL and API CORS/health.
