# RC-014 LinkedIn incremental detail refresh

The LinkedIn producer now separates frequent card/disappearance scans from bounded durable detail refresh.

## Implemented contract

- New jobs, changed card evidence, reactivated jobs and durable-expired details enqueue detail refresh.
- Unchanged jobs reuse durable detail within the configured seven-day default window.
- Applicant/freshness fields become explicitly `STALE` after the one-day volatile window while retaining their observation timestamp; the current endpoint does not provide a separate volatile-only request.
- Cache-hit metrics record refresh reasons, avoided requests and stale volatile rows. Provider credits/cost are reported when the transport exposes them.
- Cache hits advance the current run and company-scan identity and observation timestamp, so reused details remain attributable to the scan that saw the current card.
- Source disappearance reconciliation runs from the search scan regardless of whether detail was fetched.

## Focused verification

Existing producer tests cover fresh reuse, volatile staleness, durable expiry, changed-card refresh, failed refresh freshness preservation, source disappearance and current-scan attribution. The suite was not executed because the repository-required `.venv\Scripts\python.exe` is absent. No network request was made.

## Rollback

Reverse only the RC-014 cache-policy and cache-hit attribution hunks in `scripts/master_linkedin_jobs_catalog.py` and their focused assertions in `tests/test_master_linkedin_jobs_catalog.py`, plus this document. Preserve unrelated dirty changes in both files; no data migration was added.
