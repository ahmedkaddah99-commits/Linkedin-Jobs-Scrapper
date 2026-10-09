# Runr Scraping P1 Work And Efficiency Report - 2026-05-27

**Report date:** 2026-05-27  
**Work session:** Codex implementation session for Runr Scraping P1 tasks  
**Source strategy document:** [Runr Scraping Strategy Report - 2026-05-26](../scraping_strategy_report_2026-05-26.md)  
**Related PRD:** [ScrapeOps Usage And Local-Market Sourcing PRD](../prd/scrapeops_usage_and_local_market_sourcing_prd.md)

## Executive Summary

The scraping system was changed from broad, mostly proxy-backed acquisition toward a measured, demand-gated, API-first setup.

The most important result is that Runr no longer needs to treat the full saved inventory as the normal crawl unit. The system now has:

- a ScrapeOps Proxy API health gate before paid proxy-backed routes
- direct Greenhouse and Lever ATS API routing before proxy fallback
- actual ScrapeOps credit recording from `json_response=true` metadata
- a shared usage ledger for company sites, academic sites, board fallbacks, manual proxy fetches, and LinkedIn proxy fallback
- board fallback and LinkedIn proxy telemetry
- demand-gated site state for company and academic sources
- visible recall caps through `company_site_max_job_links_per_site` and `capped_sites`

## Validation Summary

Focused backend verification passed:

```text
137 passed, 19 subtests passed
compileall passed
git diff --check -- backend tests passed
```

Live or bounded evidence collected during the session:

| Evidence item | Result |
|---|---|
| ScrapeOps health check | Healthy response from configured account. |
| Company proxy credit probe | ABB target recorded `sops_api_credits=1` and wrote a usage-ledger row. |
| Board fallback probe | Indeed Germany direct request returned `403`; residential proxy fallback recorded `billed_credits_actual=10`. |
| Demand-gating dry run | Five saved inventory sites, zero network requests, correct state transitions. |
| Recall-cap evidence | Siemens saved inventory URL hit cap with `capped_sites` populated and the INFO log emitted. |

## Work Completed

### 1. ScrapeOps Proxy API Health Gate

Added `check_scrapeops_proxy_health()` and `require_scrapeops_proxy_health()` in `backend/integrations/scrapeops.py`.

Behavior:

- sends one minimal ScrapeOps Proxy API request
- uses `json_response=true`
- uses a 5-second timeout
- distinguishes banned account, insufficient credits, timeout/network failure, and healthy state
- raises human-readable user-facing messages
- records paid health-check usage when a usage callback is supplied

### 2. ATS Router

Added `backend/connectors/ats_router.py`.

Supported detection:

- Greenhouse
- Lever
- Workday
- Personio
- Recruitee
- SmartRecruiters

Direct structured API routing is implemented for Greenhouse and Lever. Workday, Personio, Recruitee, and SmartRecruiters are detected but intentionally fall through to the proxy path until structured API fetchers are implemented.

Important limitation: no saved Greenhouse or Lever inventory URL was found in the local repo/database, so the required live Greenhouse/Lever inventory probe remains blocked.

### 3. Actual Credit Recording

ScrapeOps proxy requests now use `json_response=true` and parse actual billed credits from `sops_api_credits`.

The usage ledger records:

- `source_id`
- `target_url`
- `method`
- `request_mode`
- `target_status_code`
- `provider_status_code`
- `latency_ms`
- `billed_credits_actual`
- `billed_credits_estimated`
- `usable_job_count`
- `error_category`
- `recorded_at`

LinkedIn target domains now emit a warning before proxy use because documented cost is 70 credits/request.

### 4. Board Fallback And LinkedIn Telemetry

Job board proxy fallback now records actual ScrapeOps spend into the same ledger.

LinkedIn proxy fallback now:

- warns before the request
- uses ScrapeOps `json_response=true`
- records actual billed credits
- logs the actual cost after the request

No live LinkedIn proxy request was made during testing.

### 5. Demand-Gated Site Scheduler

Added `site_source_policy` with these valid states:

- `hot`
- `selected`
- `low_yield`
- `paused`
- `pending`

Scheduled crawling now proceeds only for `hot` and `selected` sites unless a workspace explicitly triggers a source. Sites with `low_yield`, `paused`, or `pending` are skipped in the shared schedule.

Yield behavior:

- `jobs_found > 0`: resets zero-yield count
- `low_yield` plus yield recovery: returns to `selected`
- three consecutive zero-yield runs: transitions to `low_yield`

### 6. Recall Cap Reclassification

Renamed:

```text
company_site_emergency_max_job_links_per_site
```

to:

```text
company_site_max_job_links_per_site
```

The old key still works and emits a deprecation warning.

The default cap is now `25`, and the API response exposes `capped_sites` entries:

```json
{
  "url": "https://example.com/careers",
  "links_fetched": 25,
  "cap_value": 25
}
```

## Efficiency Analysis

### Baseline Before This Work

The saved inventory contains:

| Inventory | Count |
|---|---:|
| Regular company sites | 1,414 |
| Academic sites | 1,092 |
| Total | 2,506 |

The 2026-05-26 strategy report estimated one full pass over all saved company and academic sites at:

| Scenario | Credits per full pass |
|---|---:|
| Minimum | 2,506 |
| Likely | 15,036 |
| Maximum | 50,120 |

Twice-daily operation was therefore estimated at:

| Scenario | Credits per day |
|---|---:|
| Minimum | 5,012 |
| Likely | 30,072 |
| Maximum | 100,240 |

The likely monthly cost would be roughly:

```text
30,072 credits/day * 30 days = 902,160 credits/month
```

That is not viable on a 100,000-credit/month account.

### New Operating Model

The new shared schedule cost is no longer tied directly to all 2,506 saved sites. It is tied to the active set:

```text
active_sites = hot_sites + selected_sites
daily_credits ~= active_sites * likely_credits_per_site * runs_per_day
```

Using the previous likely average:

```text
likely_credits_per_site = 15,036 / 2,506 ~= 6 credits/site/pass
runs_per_day = 2
daily_credits ~= active_sites * 12
```

Estimated scheduled crawling cost:

| Active scheduled sites | Estimated daily credits | Estimated monthly credits | Reduction vs old likely monthly |
|---:|---:|---:|---:|
| 25 | 300 | 9,000 | about 99.0% |
| 100 | 1,200 | 36,000 | about 96.0% |
| 250 | 3,000 | 90,000 | about 90.0% |
| 500 | 6,000 | 180,000 | about 80.0% |

### Efficiency By Source Type

| Source type | New behavior | Efficiency impact |
|---|---|---|
| Greenhouse | Direct public API before proxy | Best case: 0 proxy credits. |
| Lever | Direct public API before proxy | Best case: 0 proxy credits. |
| Workday | Detected but structured fetch not implemented | No credit savings yet except better logging/routing readiness. |
| Personio | Detected but structured fetch not implemented | No credit savings yet except better logging/routing readiness. |
| Recruitee | Detected but structured fetch not implemented | No credit savings yet except better logging/routing readiness. |
| SmartRecruiters | Detected but structured fetch not implemented | No credit savings yet except better logging/routing readiness. |
| Generic company sites | Demand-gated, capped, health-gated, ledger-recorded | Large savings by avoiding inactive inventory and measuring actual credits. |
| Academic sites | Same shared company-site engine | Large savings by avoiding inactive inventory and measuring actual credits. |
| Job boards | Direct request first, proxy only on fallback | Spend is now visible and attributed; fallback remains paid. |
| LinkedIn | Warning plus ledger on proxy fallback | Still expensive at documented 70 credits/request; now visible and auditable. |
| Manual/generic URL ingestion | Health-gated and ledger-recorded when proxy-backed | Safer and measurable, but not inherently cheaper unless fewer proxy requests are made. |

## What Is More Efficient Now

1. The full saved inventory is no longer the default crawl unit.
2. Greenhouse and Lever can bypass ScrapeOps entirely.
3. Low-yield sites can age out of frequent crawling after three zero-yield runs.
4. Paused and pending sites do not consume scheduled crawl credits.
5. Actual credits are recorded from ScrapeOps metadata, so premium-domain overruns can be detected.
6. Board fallback and LinkedIn proxy requests are no longer invisible.
7. Recall caps are transparent to the API and user-facing run payload.

## Remaining Efficiency Opportunities

1. Implement direct structured fetchers for Workday, Personio, Recruitee, and SmartRecruiters.
2. Add budget alerts using `get_spend_by_source(since)`.
3. Add source-level yield reports that combine `usable_job_count` with actual credits.
4. Promote proven high-yield sources to `hot`; keep everything else `selected` only when a workspace needs it.
5. Add a weekly low-yield crawl lane instead of skipping low-yield sources indefinitely.
6. Continue avoiding LinkedIn as unattended batch infrastructure unless budget and data-access basis are explicitly approved.

## Important Caveats

- The ATS router live evidence for Greenhouse and Lever is blocked until real saved Greenhouse/Lever inventory URLs exist.
- The recall cap default increased from 8 to 25. This improves recall but can increase per-site request count on large sites.
- Actual ScrapeOps costs may vary by target domain; the ledger now records the real provider value so future analysis should use ledger data, not estimates.

## Primary Files Changed

| Area | Main files |
|---|---|
| ScrapeOps integration | `backend/integrations/scrapeops.py` |
| ATS routing | `backend/connectors/ats_router.py`, `backend/connectors/company_career_sites.py` |
| Company/academic acquisition | `backend/connectors/company_career_sites.py`, `backend/adapters/stage_adapters.py` |
| Job board fallback | `backend/connectors/job_boards/strategies.py`, `backend/connectors/job_boards/collector.py` |
| LinkedIn/manual telemetry | `backend/capabilities/tailored_documents/linkedin_connector.py`, `backend/capabilities/tailored_documents/manual_urls.py` |
| Repository ledger and policy state | `backend/repositories/sqlite_backed.py`, `backend/repositories/__init__.py`, `backend/bootstrap.py` |
| API cap reporting | `backend/api/server.py` |
| Workspace cap setting | `backend/orchestration/workspace_builder.py`, `backend/capabilities/tailored_documents/runtime.py` |

## Tests Added Or Extended

| Test file | Coverage |
|---|---|
| `tests/test_scrapeops_integration.py` | Health check, envelope parsing, actual credit extraction, usage records. |
| `tests/test_ats_router.py` | ATS detection, Greenhouse/Lever normalization, proxy skip behavior. |
| `tests/test_job_board_connectors.py` | Board fallback actual-credit ledger emission. |
| `tests/test_sqlite_repositories.py` | Usage ledger, spend aggregation, site-source policy transitions. |
| `tests/test_company_career_discovery.py` | Recall cap behavior and `capped_sites`. |
| `tests/test_stage_adapters.py` | Deprecated cap key compatibility, stage result `capped_sites`, policy wiring. |
| `tests/test_backend_api.py` | API exposes `capped_sites` in run payloads. |
