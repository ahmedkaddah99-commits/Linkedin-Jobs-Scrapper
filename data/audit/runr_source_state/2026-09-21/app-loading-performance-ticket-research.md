# App loading performance ticket research — 2026-09-21

Research State: **Current**

## Decision

Create one cross-subsystem parent issue whose only outcome is an app-wide loading-performance program, with independently executable children for each critical surface. Create the first child for the authenticated Jobs first-content path represented by the supplied `/jobs` screenshot.

Implementation can start now. The repository contains a bounded Jobs feed, an offline benchmark, an existing e2e flow, and request diagnostics. It does not contain a current authenticated production timing baseline, so the first child must instrument and measure the real critical path before claiming a particular frontend, API, database, or deployment root cause.

## User evidence

- Supplied screenshot captured 2026-09-21 at `https://app.userunr.com/jobs` shows the Jobs shell rendered while `Loading the shared jobs catalog...` remains visible, with `Showing 0 of 0 jobs` and a `Loading jobs` state.
- The screenshot demonstrates a user-visible loading problem but contains no elapsed time or network trace. It is not, by itself, evidence that the backend query, session bootstrap, bundle, or network is the sole cause.

## Repository evidence at baseline

Baseline SHA: `30c8d5f1641951148de3e30f44165e8e69fb764e` on `deployment/render-turso-r2`.

- `frontend/src/context/SessionContext.jsx:147-194,196-202` performs authenticated `/auth/me` session bootstrap and only exposes `isConnected` after that request succeeds.
- `frontend/src/App.jsx:174-190` preloads Jobs route chunks on idle, with a 2-second idle timeout or a 1.2-second fallback timeout. `frontend/src/App.jsx:214-227` renders the lazy Jobs routes behind `Suspense`.
- `frontend/src/components/personalized/JobsWorkspace.jsx:392-428` waits for `isConnected`, adds a 150 ms timer, clears the existing feed with `setFeed(null)`, then requests `/personalized-jobs?...` with `limit=25` and `view=cards`.
- `frontend/src/components/personalized/JobsWorkspace.jsx:434-453` requests the selected job detail after the feed establishes a selected job; company details are deferred until the Company tab at `:460-470`.
- `frontend/src/lib/personalizedJobsApi.js:84-167` builds bounded filter/cursor queries and caps the client page size at 100.
- `backend/api/routes/acquisition_catalog.py:176-190` maps the feed request to `get_personalized_jobs` with filters, cursor, bounded limit, plan, and card view.
- `backend/application/personalized_jobs_service.py:1290-1449` merges preferences/saved search/explicit filters, calls the store, computes pagination, dispositions, filter capabilities, and card projections. The card path avoids the heavier intelligence projection.
- `backend/repositories/sqlite_personalized_jobs.py:1172-1254` performs publication lookup, filtered count, keyset-paginated row query, and `LIMIT page_size + 1`; `:1293-1305` computes filter capabilities returned with the feed.
- `frontend/src/lib/api.js:11,232-270,485-592` has a 5-second slow-request threshold and privacy-bounded diagnostic logging, but the current evidence does not show route-ready, feed-ready, or phase-level field metrics.
- `frontend/e2e/phase-d-jobs-cutover.spec.ts:88-93` records document navigation `DOMContentLoaded` and `load` timings, but does not measure authenticated session-ready, Jobs-feed-request, first-card-render, or useful-content-ready timings.
- `docs/phase-c-feed-performance-security.md` records an existing local target of warm feed p95 `<2s`, warm company p95 `<2s`, and useful Jobs content visible `<5s` on Render. It is a backend warm-path contract, not an app-wide loading SLO.
- `docs/reverse-engineering/01-architecture/frontend-app.md:299,423` records that authenticated real Jobs payloads were not visually verified in the prior audit. `docs/reverse-engineering/01-architecture/backend-api.md:534` likewise records authenticated payloads as unknown at that baseline.

## Offline baseline run

Required interpreter verified: `.venv\\Scripts\\python.exe` reports Python 3.12.7.

Command:

```powershell
.venv\\Scripts\\python.exe scripts/benchmark_personalized_jobs.py
```

Result: 1,000 seeded jobs, 30 warm iterations; feed p50 `509.34 ms`, feed p95 `1,079.71 ms`; company p50 `122.0 ms`, company p95 `266.35 ms`.

Focused correctness/security command:

```powershell
.venv\\Scripts\\python.exe -m pytest -q tests/test_phase_c_feed_performance_security.py tests/test_phase_c_personalized_jobs.py
```

Result: `6 passed in 11.54s`.

These are local SQLite results and must not be presented as production latency.

## Recommended performance standard

Use a two-layer contract:

1. **User-facing field/lab quality:** track Core Web Vitals at the 75th percentile, segmented by mobile and desktop: LCP `<=2.5s`, INP `<=200ms`, and CLS `<=0.1`. Use both lab tests and privacy-safe real-user monitoring; the browser `load` event is not an adequate proxy for useful app readiness.
2. **Runr route readiness:** add custom marks/measures for navigation start, app shell rendered, Clerk/session connected, critical API request start/first byte/end, first useful content rendered, and route interactive. For `/jobs`, define feed-ready as the first verified page of cards or an explicit empty/error state, not merely the React route mounting. Keep the existing warm feed p95 `<2s` contract and useful-content `<5s` contract as route-specific guardrails, then set budgets for the other critical routes from measured baselines.

Use the Navigation Timing, Resource Timing, and User Timing APIs for phase data, and enforce representative lab budgets in CI. Treat field data as the release truth for the 75th percentile. Avoid logging tokens, CV data, query text, job descriptions, or customer identifiers.

Official references consulted 2026-09-21:

- `https://web.dev/articles/vitals` — Core Web Vitals thresholds and 75th-percentile evaluation.
- `https://web.dev/articles/user-centric-performance-metrics` — lab plus field measurement and custom metrics.
- `https://web.dev/articles/optimize-ttfb` — TTFB is upstream of FCP/LCP; `<=0.8s` is a rough guide, not a Runr acceptance criterion by itself.
- `https://developer.mozilla.org/en-US/docs/Web/Performance/Guides/Navigation_and_resource_timings` — navigation/resource timing APIs.
- `https://developer.mozilla.org/en-US/docs/Web/API/Performance_API/User_timing` — application-specific marks and measures.

## Research boundaries and handoff

- No live authenticated browser session, Render trace, production API timing, Turso query plan, deployment inspection, or provider request was performed by this research pass.
- The first child should collect those timings in an approved environment, optimize only measured critical-path contributors, preserve truthful loading/error/empty states, and add regression coverage.
- Future children should cover the app shell/session bootstrap, route chunk and asset delivery, each major API/data read path, deployment/cache headers, and shared RUM/CI budgets. They should be linked under the parent rather than folded into the Jobs child.
