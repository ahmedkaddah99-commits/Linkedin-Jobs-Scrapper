# External jobs delivery — 11 October 2026

## Delivered behavior

- Removed the Quick Apply page, navigation, creation endpoint and obsolete workflow builder.
- Added `/external-jobs`: paste one job URL, load it, then open the existing Jobs reader.
- Recommended and external jobs share `PersonalizedJobsPage` / `JobsWorkspace`, the reader and its actions. Further reader and CV work therefore applies to both.
- Private imported postings use the shared Nemo classification and description enrichment on demand. Existing catalog URLs retain a private snapshot of the existing posting.
- Failed fetching preserves extracted fields and offers a short message and manual completion. Non-job pages receive a distinct message; job descriptions, field lengths, metadata choices and public URLs are validated by the backend.
- Imports persist per user, support pagination, and enforce owner isolation and a daily attempt limit. Enrichment failures retain the original posting and expose Retry.

## Production release

Deployed application revision: `5db96e65ea2afb089b2323fc3fa5b62cc602b486` on `release/external-jobs-2026-10-11`.

Public entry: <https://app.userunr.com/external-jobs>.

API and worker run from `/srv/runr/releases/external-jobs-5db96e65`. Nginx serves that release's production frontend. Public release metadata matches the revision; `/health/ready` reports ready, and both customer services are active. Migration head is `079_external_jobs` on the existing shared SQLite database. Production authentication, R2 configuration and the acquisition maintenance pause are retained.

Deployment evidence: `/srv/runr/ops/external-jobs-5db96e65/`.

The deployment reused the same-day verified database backup, with integrity check `ok`, zero foreign-key violations, verified decompressed hash and complete offsite readback. Its receipt is stored as `backup-used.json`. The deploy script preserves the previous nginx configuration and service overrides for rollback.

## Verification

- Release branch: 36 focused backend tests passed, 130 deselected, and 7 subtests passed. This selection covers imports, shared enrichment, metadata validation, migrations and API import/retirement routes.
- Frontend: 178 tests passed; ESLint and production build passed.
- Browser checks: all 6 desktop/mobile tests passed for external URL import, shared reader, manual fallback and Jobs navigation.
- Authenticated live API verification passed against the exact deployed revision: public HTML scraping, real `mistralai/mistral-nemo` enrichment, full-time / mid-level / on-site tags, shared reader detail, Save, external list, owner isolation, non-job fallback, manual completion and retired Quick Apply endpoint (404).
- Live verification created temporary users, tokens and a temporary noindex posting, then removed all of them. `verification.log` records successful cleanup.
- Production verification found and corrected two issues before completion: case-sensitive content-type lookup rejecting HTML, and omission of an explicitly stated mid-level position by the model. Regression tests reproduce both. The latter correction uses exact source wording in the shared catalog validator.

The broader company-enrichment suite has 11 existing fixture failures: its seed inserts six positional values into the expanded 12-column `canonical_companies` table. Those failures happen during fixture setup. A full repository suite was not completed, and this delivery does not claim it passed.

Desktop and mobile reader checks use the local production frontend with mocked API responses; the authenticated production API check above uses real services and real provider calls. A signed-in live browser session was unavailable.
