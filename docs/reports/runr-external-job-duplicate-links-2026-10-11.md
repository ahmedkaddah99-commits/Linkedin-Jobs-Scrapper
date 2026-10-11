# External job duplicate links — 11 October 2026

## Current behavior

- An already-added account-owned external URL is rejected with: “You already added this job to External jobs.”
- A URL belonging to the current published Runr catalog is rejected with: “This job is already available in Runr Jobs.”
- Both reasons appear in a short modal popup with an OK button.
- Preview and confirmation reject duplicates before scraping or AI work. Confirmation also rechecks after enrichment; an atomic new-only insert prevents concurrent requests from overwriting an existing import.
- Explicit Retry enrichment remains available for the owner's existing imports. Other users' private postings do not affect this account's duplicate checks.

## Delivery and verification

Deployed application: `96868ca039ca74ab4b3ee5d2da29d275993cc343`, branch `release/external-jobs-2026-10-11`. Feature and release branches are synced. Frontend release metadata matches; API and worker are healthy.

- 35 focused release backend checks passed, 118 deselected, and 7 subtests passed.
- 177 frontend unit tests, ESLint and production build passed.
- 4 desktop/mobile browser tests passed, including both popup reasons and a duplicate appearing while the review drawer is open.
- Authenticated live API checks rejected both an existing private URL and an actual URL from the current published catalog, for both preview and confirmation.
- Live regression checks also passed new imports, real Nemo enrichment, Siemens preview/confirmation, saving, owner isolation and manual fallback. Temporary verification users, tokens, rows and HTML were removed.

VPS evidence: `/srv/runr/ops/external-jobs-96868ca0/verification.log`. Browser checks use mocked API responses; the production checks use real services and provider calls. No full repository suite was run for this change.
