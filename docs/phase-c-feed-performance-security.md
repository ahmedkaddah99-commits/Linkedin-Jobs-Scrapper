# Phase C feed performance and security

The Jobs feed now applies catalog filters, hidden-state predicates, stable keyset ordering, total counts, and cursor predicates in SQL. The page query uses `LIMIT page_size + 1`; Python only projects the returned page. Company and hidden Jobs paths use bounded/batch reads. GETs read cached intelligence only; a missing description, match, or priority is explicitly `pending`, while missing applicant data is `unknown`.

Public projections remove ATS/source identifiers, observation URLs, and internal provenance. `apply_url` is emitted only when it is the approved HTTP(S) job-specific URL stored on the published posting.

Run the local benchmark with:

```powershell
.venv\Scripts\python.exe scripts\benchmark_personalized_jobs.py
```

The script seeds 1,000 published jobs, warms both routes, and reports p50/p75/p95 in milliseconds. Record baseline and post-change output in the change report; production targets remain warm feed p95 <2s, warm company p95 <2s, and useful Jobs content visible <5s on Render.

Deliberate compatibility change: GET no longer creates an intelligence queue item or synchronously computes description/match/company enrichment. Worker-produced cache entries remain readable; uncached fields are pending/unknown until a worker supplies them.

## T54 feed first-content contract

- **Server phase timings.** The `GET /personalized-jobs` response carries a privacy-safe `timings` object (`store_query_ms`, `capabilities_ms`, `total_ms`, rounded to 0.1 ms) in both card and full views. It contains no user data and is additive to the existing feed contract.
- **Filter-capability cache.** `SqlitePersonalizedJobsStore.get_published_filter_capabilities` caches the aggregate per publication id (a publication's catalog is immutable, so the result is a pure function of `publication_id`), bounded to 8 entries (oldest evicted). A new publication head recomputes; this removes one full-catalog `MAX(CASE WHEN …)` scan per warm feed request without changing the returned values.
- **Bounded frontend reads.** The Jobs feed, detail, company, and load-more requests carry a 20 s timeout so every read ends in a truthful loading/empty/error/retry state; the initial feed request is `limit=25` plus cursor pagination.
- **Refresh semantics.** A filter change or retry no longer clears an already loaded feed; stale cards stay visible under an explicit `refreshing` banner and a failed refresh keeps the last verified page with a retry control.
- **Frontend readiness marks.** The frontend records `runr-jobs:*` phase marks (`session-connected`, `route-chunk`, `route-mounted`, `feed-request-start`, `feed-request-end`, `useful-render`, `interactive`); `useful-render` measures time to the first verified card page, truthful empty state, or retryable failure state. See `docs/reverse-engineering/01-architecture/frontend-app.md` §5.4.
- Local fixture evidence (T54, mocked e2e production build): useful readiness p50 338 ms / p75 504 ms / p95 785 ms desktop, p50 298 ms / p75 325 ms / p95 721 ms mobile; all far under the 5 s budget. Render-like environment timings remain a release-verification dependency.
