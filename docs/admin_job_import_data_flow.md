# Admin Job Import data flow

This map is intentionally tied to the existing Runr boundaries. The browser
only calls protected API routes; it never calls a source, ScrapeOps, Turso or
R2 directly.

```text
Clerk administrator
        |
        v
frontend /admin/job-import
        |
        v
Runr API (admin job-import routes)
  - validates source manifest, scope, idempotency and bounded budgets
  - stores the queued import in Turso/libSQL
        |
        v
Runr worker
  - claims the queued import once
  - reuses Phase A acquisition request accounting and source connectors
  - uses direct Greenhouse/Lever APIs where configured
  - uses the existing ScrapeOps-backed company-site connector only for
    server-owned web-import sources that require it
        |
        +--> Phase B normalization and direct-Apply/rejection rules
        |       |
        |       +--> canonical jobs, companies, immutable posting versions,
        |       |    source observations, lifecycle and duplicate relationships
        |       |    in Turso/libSQL
        |       |
        |       +--> rejection evidence and admin review decisions in Turso
        |
        +--> company enrichment / intelligence remain worker-owned; existing
             logo objects use the current object-storage boundary (R2 in prod)
        |
        v
admin review -> server-side filters -> approve/reject audit events
        |
        v
publication preview (staging publication, no public-head change)
        |
        v
explicit publish -> previous-head reference + new valid publication head
        |
        +--> customer Jobs API reads the valid publication head from Turso
        +--> frontend Jobs pages read the protected Jobs API
        +--> undo restores the previous valid publication head
```

## Verified deployment roles

- Render runs the static frontend, Docker API and continuous Docker worker.
- Turso/libSQL is the production structured store (`DATABASE_BACKEND=turso`)
  for users, acquisition, catalog, review and publication state.
- ScrapeOps is a server-side proxy/rendering and credit-accounting integration
  for existing scraping paths; Greenhouse and Lever remain direct APIs.
- Cloudflare R2 is configured through the existing S3-compatible object-storage
  boundary for protected logos and other existing object assets. Ordinary job
  fields remain structured database data.
- Clerk authenticates the frontend and the API enforces the administrator role.
- `app.userunr.com` is the authenticated frontend domain and
  `api.userunr.com` is the customer/API domain; Render's `render.yaml` keeps
  their allowed-origin and environment wiring together.

## Internal job contract

Source connectors may provide only the fields they actually observed. Phase B
normalizes the stable identity, company, title, location, description,
source-specific external ID, source ATS, official HTTPS Apply URL and
application method. Turso stores the canonical job, immutable posting version,
source observation, lifecycle, duplicate/repost relationships, review state,
publication decisions and audit references. R2 stores only existing object
assets and evidence references, never filterable job fields. Enrichment,
intelligence, applicant state and company profiles remain optional and use
explicit unknown/pending states. The admin surface may show internal evidence
under Advanced details; the customer surface exposes only the public catalog
projection and the official Apply URL.

Production imports remain paused by default. The dashboard can calculate and
display the exact bounded plan while the first real import still requires
explicit approval.
