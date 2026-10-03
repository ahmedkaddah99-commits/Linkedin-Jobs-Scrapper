# Scraper source and output inventory

Recorded: 2026-09-12

## Source package basis

The producer source bundle is copied from the deployed Runr source worktree:

`C:\Users\ahmed\Projects_Local\runr-admin-linkedin-preview`

That worktree is on branch `deployment/render-turso-r2` at source snapshot commit `c25d394ab9355e4d08a058589d9e125df9ee7444`. The exact producer implementation history includes the LinkedIn catalog work beginning at `6d0fca4d` and the employer/LinkedIn bounded-cycle improvements through `5328832f`.

## Preserved outputs

The large output/state snapshot is preserved outside the source bundle:

- `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\feature-worktree-recovery\jobs-urls-source-quarantine\master linkedin jobs url\master_linkedin_jobs.csv` — 188,206 canonical rows.
- `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\feature-worktree-recovery\jobs-urls-source-quarantine\master linkedin jobs url\master_linkedin_jobs.jsonl` — 197,915 observation rows.
- `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\feature-worktree-recovery\jobs-urls-source-quarantine\master linkedin jobs url\master_employer_jobs.csv` — 2,612 rows.
- `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\feature-worktree-recovery\jobs-urls-source-quarantine\master linkedin jobs url\master_employer_jobs.jsonl` — 2,612 rows.
- `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\feature-worktree-recovery\jobs-urls-source-quarantine\master linkedin jobs url\master_jobs.csv` — 190,818 combined rows.
- `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\state\linkedin\master_linkedin_jobs_state.db` — 188,206 `jobs` rows.
- `C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\state\employer\master_employer_jobs_state.db` — 2,612 `jobs` rows.

An additional preserved copy exists under:

`C:\Users\ahmed\Projects_Local\runr-acquisition-snapshots\rc023-20260908\feature-worktree-recovery\jobs-urls-preserved\Jobs-Urls\`

## Production handoff status

The VPS source and publication release is
`4a1b1df55b9dbac9745d29d1916a85fe9575a114` on `deployment/render-turso-r2`.
The acquisition worker, customer worker, API, frontend, and the independent
LinkedIn, employer, and publisher timers are active. The legacy combined cycle
timer is disabled.

The latest bounded LinkedIn receipt succeeded at the service level: 100
requests through 100 Webshare proxies, 334 valid cards, 43 jobs written, and
43 successful detail fetches. It selected 25 of 2,272 manifest companies and
left 289 detail retries pending. Easy Apply evidence collection remains
enabled and is not a publication gate.

Current VPS durable source state: LinkedIn has 188,238 jobs, 199,645 search
cards, 18,787 company scans, and 11,896 source-company groups; employer-site
state has 2,612 jobs. The publisher database has 17,601 canonical companies,
592 canonical jobs, 648 source observations, and 592 posting versions.

The active publication head is valid under `publication_policy_v1` with 340
jobs (`acq_publication_1de0d29ca01a4d9494c5cc0aeea900c6`). This head is valid
but not yet a complete migration of the historical source catalogs because
the bounded publisher bootstrap is still incomplete. The strict-gate
rejection rows remain durable audit evidence; missing application destinations
do not hide otherwise usable display jobs.

Company enrichment has 438 profiles and 98 verified cached logos. The UI uses
a fallback mark for companies without a verified logo asset.

Render's static app shell and liveness endpoint return HTTP 200. Its readiness
endpoint currently returns HTTP 400 because the Render API's Turso connection
reports that SQL reads are blocked. The served Render static bundle is also
older than the final source push; see
`docs/reports/RUNR_PRODUCTION_COMPLETION_REPORT_2026-09-12.md` for the exact
remaining infrastructure decision.
