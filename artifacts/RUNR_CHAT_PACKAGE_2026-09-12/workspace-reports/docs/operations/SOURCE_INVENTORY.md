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

The live production release is `107114620765b52a0c3f41abaf51d4cda67edfab` on the VPS. Render remains display-only; its readiness endpoint and app shell both returned HTTP 200 after the release.

The bounded LinkedIn run on 2026-09-12 completed successfully at the service level: 100 requests through 100 Webshare proxies (66 search, 34 detail), 314 valid cards, 33 jobs written, and 33 successful detail fetches. The run remained partial by design: 2,258 of 2,272 manifest companies were budget-exhausted and 214 detail retries remain pending for later bounded cycles. Easy Apply evidence collection remained enabled; it was not skipped.

Current VPS durable state after that run: LinkedIn has 188,217 jobs, 198,969 search cards, and 18,737 company scans; the employer-site state has 2,612 jobs. LinkedIn, employer, and publisher timers are enabled and active; the legacy combined cycle timer remains disabled.

Turso currently contains 18,994 canonical companies, 6,370 canonical jobs, 9,759 source observations, and 7,176 posting versions. The active publication head is valid under `publication_policy_v1` with 6,335 jobs (`acq_republish_872faf4172f4456db85b0e93984d367d`). The strict-gate rejection rows remain durable audit evidence; they were not used to hide the display-first catalog.
