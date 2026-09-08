# Phase C feed performance and security

The Jobs feed now applies catalog filters, hidden-state predicates, stable keyset ordering, total counts, and cursor predicates in SQL. The page query uses `LIMIT page_size + 1`; Python only projects the returned page. Company and hidden Jobs paths use bounded/batch reads. GETs read cached intelligence only; a missing description, match, or priority is explicitly `pending`, while missing applicant data is `unknown`.

Public projections remove ATS/source identifiers, observation URLs, and internal provenance. `apply_url` is emitted only when it is the approved HTTP(S) job-specific URL stored on the published posting.

Run the local benchmark with:

```powershell
.venv\Scripts\python.exe scripts\benchmark_personalized_jobs.py
```

The script seeds 1,000 published jobs, warms both routes, and reports p50/p95 in milliseconds. Record baseline and post-change output in the change report; production targets remain warm feed p95 <2s, warm company p95 <2s, and useful Jobs content visible <5s on Render.

Deliberate compatibility change: GET no longer creates an intelligence queue item or synchronously computes description/match/company enrichment. Worker-produced cache entries remain readable; uncached fields are pending/unknown until a worker supplies them.
