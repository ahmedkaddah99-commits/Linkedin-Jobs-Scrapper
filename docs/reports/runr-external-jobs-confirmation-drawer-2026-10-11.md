# External jobs confirmation drawer — 11 October 2026

## Delivered

- Quick access & tools is rendered only in recommended Jobs, including when viewing a recommended job. External jobs uses the full available width.
- Adding a URL opens a modal drawer from the right with extracted, editable details. Save job confirms the details and opens the existing shared Jobs reader. Cancel creates no job.
- Preview does not persist the posting. It uses Nemo to separate title, company, location, job type, experience level and work model. Unknown metadata stays blank; supported employer-labelled metadata is retained.
- The Siemens/Avature parser reads the job heading and labelled company/location fields, and separates the description from the metadata article. It distinguishes the Full-time job type from Permanent contract duration.
- Extraction uses readable source labels, an explicit response shape and checked source evidence. A successfully extracted posting receives no false unrecognized-job message.
- Fetch failure opens the same drawer, preserves extracted fields and uses a short message. Bounds and backend job validation remain enforced. Structured postings in other languages retain verified provenance through a bounded server-side check.
- Confirmation respects edits for existing private or catalog URLs. Private URL identity is stable, so re-saving a posting updates it instead of creating another entry.
- Migration `080_external_job_preview_quota` separates preview and Save counters, each limited to 20 per account per UTC day.

## Deployed and synced

Application revision: `4a2e8ce5ee8e63971bceea8b4ccbe6cc05d7b50d`.

Branch: `release/external-jobs-2026-10-11`. Both the feature branch and release branch were pushed. API and worker serve `/srv/runr/releases/external-jobs-4a2e8ce5`; frontend release metadata matches. The existing shared SQLite database is at migration 080. Public readiness and both customer services are healthy.

Entry: <https://app.userunr.com/external-jobs>. Evidence directory: `/srv/runr/ops/external-jobs-4a2e8ce5/`.

## Verification

- Final release branch: 33 focused backend tests passed, 118 deselected, and 7 subtests passed.
- Frontend release branch: 178 tests passed, ESLint passed and production build passed.
- Desktop and mobile drawer tests passed. They check confirmation before persistence, absence of Quick access & tools, populated metadata, shared reader navigation and blocked-fetch manual completion. Screenshots were inspected; on mobile, the drawer fills the screen and Save remains outside the scrolling fields.
- Authenticated production verification passed with the exact URL `https://jobs.siemens.com/en_US/externaljobs/JobDetail/524459`: title beginning Advanced Digital Engineer, company Siemens AG, Erlangen location, full-time / mid / onsite tags, no false warning, confirmation and a real Nemo-generated description.
- Production verification also passed scraping, shared reader API, Save, external list, owner isolation, non-job/manual fallback and retired Quick Apply endpoint checks. All temporary users, tokens, posting snapshots and probe HTML were removed.

Local browser checks use mocked API responses; production API checks use actual services and provider calls. The Siemens Save request took about 100 seconds while enrichment completed; the drawer displays Saving job during this work. A full repository suite was not run for this follow-up.
