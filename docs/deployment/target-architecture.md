# Target Deployment Architecture

Status: implementation baseline

Date: 2026-06-18

## Objective

Run the application for personal use at low monthly cost while preserving a
direct path to an initial paid SaaS deployment.

The application remains locally developable. Production state must not depend
on a Render instance's filesystem.

## Target Topology

```text
Browser
  |
  +-- app.example.com
  |     Render Static Site
  |     React + Vite
  |
  +-- api.example.com
        Render Web Service
        Python API
          |
          +-- Turso: structured application state and job queue
          +-- Cloudflare R2: uploads and generated artifacts

Render Cron Job (initial) / Background Worker (customer stage)
  |
  +-- claims queued runs from Turso
  +-- executes scraping, OCR, browser automation, and document generation
  +-- writes durable artifacts to R2
```

## Initial Service Plan

- Frontend: Render Static Site, free.
- API: Render Starter web service, always on.
- Job execution: Render Cron Job running one queue item per invocation.
- Database: Turso Free initially; upgrade independently when usage or recovery
  requirements justify it.
- Object storage: private Cloudflare R2 bucket using the S3-compatible API.
- Authentication and billing: existing Clerk and LemonSqueezy integrations.

The expected initial infrastructure cost is approximately USD 8 per month,
excluding third-party AI, scraping, email, and billing-provider usage.

## Scaling Contract

The following boundaries must remain stable:

- API and worker use the same container image with different role commands.
- All services use `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`.
- All durable files go through the object-storage interface.
- Queue claiming and leases are stored in Turso, not process memory.
- Database schema changes are immutable, versioned migrations.
- Render configuration is versioned in `render.yaml`.

Moving from a cron poller to a continuously running Render Background Worker
must require only a Render service configuration change.

## Environment Separation

```text
Local development
  code: feature branch
  database: local SQLite or runr-dev Turso database
  objects: local object storage

Personal production
  code: main
  database: runr-prod Turso database
  objects: runr-production R2 bucket

Future staging
  code: selected release candidate
  database: runr-staging Turso database
  objects: runr-staging R2 bucket
```

Production data must not be copied into development without sanitization.

## Deliberate Deferred Work

The current API uses Python's standard-library HTTP server. A FastAPI/Uvicorn
transport is the customer-readiness target, but it is a separate contract
migration because the existing API surface is large. Turso, migrations, object
storage, containerization, and deployment configuration can be established
before that transport migration.

The object-storage foundation does not by itself migrate every current direct
filesystem write. Upload and generated-artifact call sites must be converted in
focused follow-up work with API contract tests.

## Non-Goals

- Do not use a Render persistent disk for durable application state.
- Do not commit environment secrets or cloud access tokens.
- Do not run production development directly on the hosted instance.
- Do not merge development database contents into production.
- Do not perform destructive schema changes in the same release that removes
  the application's compatibility path.
