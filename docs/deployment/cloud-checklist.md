# Cloud Provisioning Checklist

These steps require account access and production credentials.

## Turso

1. Authenticate with the Turso CLI.
2. Select a region close to the Render API region.
3. Create `runr-prod` from the final SQLite file.
4. Create `runr-dev` from a sanitized seed or an approved production snapshot.
5. Create separate expiring tokens for development and production.
6. Run the migration status command against both databases.
7. Create a point-in-time branch before each destructive migration.

## Cloudflare R2

1. Create private buckets for development and production.
2. Create scoped S3 API credentials.
3. Configure CORS only if browsers upload directly. Prefer API-mediated uploads
   initially.
4. Configure lifecycle retention for disposable intermediate files.
5. Verify upload, download, signed URL, and deletion behavior.

## Render

1. Connect the GitHub repository.
2. deploy `render.yaml` as a Blueprint.
3. Set all secret environment variables in the Render dashboard.
4. Confirm the API health check succeeds on the Render hostname.
5. Trigger the cron processor and verify a queued run is claimed.
6. Verify generated files survive API and worker redeploys because they are in
   R2.

## Domains And External Providers

1. Add `app.example.com` to the static site.
2. Add `api.example.com` to the API service.
3. Configure DNS using the values Render provides.
4. Add the frontend origin and redirect URLs to Clerk.
5. Configure Clerk and LemonSqueezy webhooks against the API domain.
6. Configure Google OAuth redirect URLs if Gmail integration is enabled.
7. Verify HTTPS, CORS, authentication, webhook signatures, and downloads.

## Cutover

1. Stop writes to the local production database.
2. Take a final backup.
3. Import the final database into Turso.
4. Run migrations.
5. Migrate durable local assets to R2.
6. Deploy using Render hostnames.
7. Run smoke tests.
8. Switch DNS.
9. Keep the old database and asset backup until the rollback window closes.
