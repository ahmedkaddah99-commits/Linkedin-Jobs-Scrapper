# Runr Scraping Strategy Report

**Investigation date:** 2026-05-26  
**Scope:** Current workspace sources and connector implementations in Runr, ScrapeOps documentation and bounded API probes, central batch-catalog architecture, and academic/niche workspace limits.  
**Important test limitation:** The configured ScrapeOps account returns `403 Banned Account` for Proxy API and Indeed Structured Data API requests. The free Headers API and account usage endpoint work, but a successful live target fetch through ScrapeOps could not be completed with this key. Actual rejected-request cost observed was zero credits.

## Executive Summary

Runr should use a **shared job catalog populated on a schedule, with filtering and ranking at read time**, but it should not implement this as an indiscriminate full proxy crawl of every URL twice per day.

Recommended acquisition order:

1. Use public or sanctioned structured endpoints first: ATS job feeds such as Greenhouse/Lever, and direct structured services already used by the Arbeitsagentur connector.
2. Use static direct HTTP/JSON-LD collection for permitted career and academic pages where it is reliable.
3. Use ScrapeOps Proxy API only as a measured fallback, escalating `basic` -> `render_js_cheap` -> `render_js`/residential by domain policy and observed yield.
4. Use ScrapeOps Indeed Structured Data API for Indeed after account access is restored and its billing is confirmed.
5. Treat LinkedIn as exceptional: ScrapeOps documents it at 70 credits per successful request and LinkedIn's terms restrict scraping. Do not use it as a high-volume unattended batch backbone without an approved data-access basis.

The existing application is already moving toward locality selection, per-run credit budgets, and usage recording for company/academic sources. It still needs two architectural changes before central batch operation:

- A catalog schema independent of `run_jobs`, because the present storage model is run-scoped rather than a reusable global inventory.
- Actual provider-credit recording for all ScrapeOps-backed routes. Current company-site accounting estimates mode costs and does not capture documented domain-specific costs such as LinkedIn's 70-credit rate.

Current saved inventories comprise **1,414 regular-company sites** and **1,092 academic sites** (2,506 total). Using the repository's existing company-site estimator, a single full pass over both inventories is estimated at **2,506 minimum, 15,036 likely, or 50,120 maximum runner credits**. Twice-daily operation is therefore not viable on a 100,000-credit monthly account unless scope and request strategy are sharply reduced.

## Investigation Basis

### Supported Runr Sources

The workspace builder exposes or retains the following acquisition sources:

| Runr source | Product role | Current implementation evidence | Current inventory/scope |
| --- | --- | --- | ---: |
| `linkedin_jobs` | Legacy LinkedIn search | `backend/capabilities/tailored_documents/linkedin_connector.py`; hidden legacy source in workspace builder | Query driven |
| `curated_job_urls` | Exact job links pasted by user | `backend/capabilities/tailored_documents/manual_urls.py` | User supplied |
| `company_career_sites` | Regular company websites | `backend/connectors/company_career_sites.py` | 1,414 live discovered entries |
| `academic_career_sites` | Universities, departments, institutes, research portals | Same company-site engine with academic inventory | 1,092 live discovered entries |
| `job_board_collection` | Generalist/regional board search | `backend/connectors/job_boards/collector.py` and `strategies.py` | 12 implemented portals |

The multi-portal connector implements:

| Portal | Catalog classification / market signal |
| --- | --- |
| Indeed, LinkedIn, Glassdoor, ZipRecruiter, Monster, CareerBuilder | Generalist |
| Careerjet | Global/regional aggregator |
| StepStone | Germany / United Kingdom |
| Arbeitsagentur | Germany |
| Reed, Totaljobs | United Kingdom |
| JobsDB | Hong Kong / Thailand |

### Current ScrapeOps Use in the Codebase

| Area | Current behavior | Consequence |
| --- | --- | --- |
| Company and academic sites | ScrapeOps-only fetch path; default site modes `basic`, then `render_js_cheap`; detail mode `basic` | Sound escalation direction, but currently unavailable when the account cannot call Proxy API |
| Manual generic job URL | Defaults to `render_js_residential` when forced through ScrapeOps | High cost for exact links unless changed to direct/API-first escalation |
| Job board strategies | Direct HTTP first; on `403`/`429`, fallback proxy uses `residential=true` and `country=de` | A fallback request is ordinarily 10 credits for normal domains; it is not integrated with the company-site usage ledger |
| LinkedIn tailored connector | Uses `scrapeops_python_requests`; fallback can use residential + JS | High legal and provider-cost sensitivity; not appropriate as unbounded batch traffic |
| Usage/accounting layer | Records company-site estimated mode credits of 1/5/10/25 | It can undercount a domain-specific provider price, especially LinkedIn's documented 70-credit rate |
| Per-site ceiling | Default `company_site_emergency_max_job_links_per_site=8` | Despite being described as emergency protection, it limits ordinary site recall unless overridden |

## ScrapeOps Capability Findings

### Documented Products Applicable to Runr

| ScrapeOps capability | Applicable Runr route | Finding |
| --- | --- | --- |
| Proxy API Aggregator | Company sites, academic sites, exact links, unsupported/blocked board pages | Provides HTML/JSON target response and supports country targeting, JS rendering and residential routing. |
| Indeed Structured Data APIs | Indeed only | ScrapeOps Data API documentation lists Indeed Job Search, Job Details, and Company Jobs endpoints; it is not a general job-board API for the other Runr portals. |
| Fake Browser Headers API | Direct HTTP spiders that are permitted to crawl | Free endpoint; official docs recommend complete browser-header sets over user-agent strings alone. Live probe succeeded. |
| `json_response=true` | Every proxy-backed request that needs accounting | Returns extended proxy response metadata including request cost on successful accessible calls; use it for a credit ledger. |
| Country geotargeting | Location-specific pages, especially Germany | Standard Proxy API supports `de`, `uk`, `us` and other listed countries; residential supports broader country targeting. |
| `max_request_cost` / request optimization | Controlled fallback policy | Useful guardrail for avoiding unexpected high-cost proxy routing. |

### Published Proxy Credit Costs

ScrapeOps bills Proxy API responses returning target status `200` or `404`; the documentation states that cost depends on enabled functionality and target domain.

| Successful proxy request profile | Credits/request | Credits/1,000 requests | Cost at $9 / 25k credits | Cost at $99 / 1m credits |
| --- | ---: | ---: | ---: | ---: |
| Normal/basic request | 1 | 1,000 | $0.36 | $0.10 |
| `render_js_cheap=true` | 5 | 5,000 | $1.80 | $0.50 |
| `render_js=true` | 10 | 10,000 | $3.60 | $0.99 |
| `residential=true` | 10 | 10,000 | $3.60 | $0.99 |
| `residential=true&render_js=true` | 25 | 25,000 | $9.00 | $2.48 |
| `mobile=true&render_js=true` | 50 | 50,000 | $18.00 | $4.95 |
| LinkedIn documented domain cost | 70 | 70,000 | $25.20 | approximately $7.00 |

Notes:

- Dollar estimates are credit-equivalent costs using the published $9 and $99 plan tiers; plan selection is discrete and unused credits are not transferred.
- ScrapeOps states that LinkedIn is priced at a flat approximately $7 per 1,000 on large plans. Do not substitute Runr's generic 1/5/10/25 estimate for actual LinkedIn billing.
- The public documentation inspected did not establish a separately billable credit price for Indeed Structured Data API calls. Record the API's actual cost after account access is restored rather than assuming proxy pricing.

## Per-Route Strategy

### Source-Level Recommendation

| Source/type | Viable methods | Pros | Cons / risks | Recommended stack |
| --- | --- | --- | --- | --- |
| General boards via `job_board_collection` | Sanctioned feed/API where available; direct HTML; ScrapeOps Proxy fallback; Indeed Data API | Broad recall; one central acquisition pass serves many workspaces; structured APIs parse cheaply | Selector churn; boards may prohibit automation; anti-bot escalation can dominate spend | Per-portal Scrapy `Spider`; structured endpoint first; retry/autothrottle/cache; proxy downloader middleware only after policy-approved failure |
| LinkedIn legacy search | Existing guest endpoint; ScrapeOps Proxy; approved/licensed provider | Useful professional-role coverage | LinkedIn User Agreement restricts scripts/crawlers/scraping; ScrapeOps documents 70 credits/request; costly for list-plus-detail crawling | Disabled for central unattended crawling by default; retain only as explicitly enabled/approved source with strict budget and actual credit telemetry |
| Exact/curated URLs | Direct fetch and JSON-LD; recognized ATS endpoint; ScrapeOps fallback | User intent is high; tiny request volume; easiest to parse if JSON-LD exists | Pages may be closed, blocked or JS-only; current forced proxy default is expensive | Plain Spider/request service; direct and ATS parser first; proxy `basic`, then cheap JS only where needed |
| Regular company career sites | ATS public JSON endpoints; direct HTML/JSON-LD; ScrapeOps Proxy modes | Best source attribution and often lower duplication; ATS APIs can yield complete inventories | Thousands of heterogeneous pages; dynamic Workday-like hosts; terms differ per employer/ATS | ATS router then bounded `CrawlSpider`; domain policy table; basic -> cheap JS -> explicit escalation; country filtering before details |
| Academic and research sites | Static page/RSS/API; ATS feeds where hosted; ScrapeOps for JS-only pages | Niche listings with low competition; some simple HTML pages are cheap | Very noisy saved inventory; small yield per site; multilingual and stale vacancy pages | Demand-scoped site subscription; API/static first; proxy only for selected sites; strong relevance/date filters |

### Board-by-Board Route Assessment

In the cost column, `basic / cheap JS` gives Proxy API cost per 1,000 successful normal-domain requests at the $99/1m credit tier. LinkedIn uses its documented domain rate instead.

| Platform | Current route | Recommended method priority | Proxy cost / 1k | Main cons and legal/operational concern | Live ScrapeOps probe |
| --- | --- | --- | ---: | --- | --- |
| Indeed | Direct HTML with residential fallback | ScrapeOps Indeed Structured Data API; avoid brittle raw HTML once billing is validated | $0.10 / $0.50 for raw proxy; Data API TBD | Indeed terms restrict automated scraping/data mining without written permission; structured provider access still needs usage review | Structured and raw proxy calls rejected at account level (`403`) |
| LinkedIn | Guest jobs HTML/API; proxy fallback | Approved/licensed source only; no routine full-catalog crawl | approximately $7.00 documented domain rate | Explicit scraping restriction and very high credit cost | Proxy call rejected at account level (`403`) |
| Arbeitsagentur | Direct JSON search and detail requests | Retain direct structured connector, with endpoint-usage/legal review and caching | $0 recommended; $0.10 if proxy unnecessarily used | Current endpoint/API-key usage should be operationally reviewed before production scaling | Proxy rejected; direct control returned 10 offers in 1.314 s |
| StepStone | Direct HTML with residential fallback | Direct only where permitted; measured proxy fallback after policy review | $0.10 / $0.50 | Regional value but dynamic/anti-bot changes and terms review required | Proxy call rejected (`403`) |
| Glassdoor | Generic HTML parser with residential fallback | Licensed/feed route preferred; proxy only as approved experiment | $0.10 / $0.50 | High anti-bot/terms risk and fragile HTML extraction | Proxy call rejected (`403`) |
| ZipRecruiter | Generic HTML parser with residential fallback | Prefer approved integration/feed; otherwise low-volume tested fallback | $0.10 / $0.50 | Geography mismatch for current European focus; selector churn | Proxy call rejected (`403`) |
| Monster | Generic HTML parser with residential fallback | Only activate per target market after yield validation | $0.10 / $0.50 | Low known incremental yield until measured; terms review | Proxy call rejected (`403`) |
| CareerBuilder | Generic HTML parser with residential fallback | Only activate per target market after yield validation | $0.10 / $0.50 | Primarily US relevance; terms review | Proxy call rejected (`403`) |
| Careerjet | Generic HTML parser with residential fallback | Candidate aggregator source after result-quality trial | $0.10 / $0.50 | Cross-source duplicates; require canonicalization | Proxy call rejected (`403`) |
| Reed | Generic HTML parser with residential fallback | Enable only for UK-targeted workspaces | $0.10 / $0.50 | Irrelevant for non-UK workspaces; terms review | Proxy call rejected (`403`) |
| Totaljobs | Generic HTML parser with residential fallback | Enable only for UK-targeted workspaces | $0.10 / $0.50 | Irrelevant for non-UK workspaces; terms review | Proxy call rejected (`403`) |
| JobsDB | Generic HTML parser with residential fallback | Enable only for Hong Kong/Thailand-targeted workspaces | $0.10 / $0.50 | Irrelevant for European workspaces; terms review | Proxy call rejected (`403`) |

### Company and Academic Route Detail

The saved regular inventory contains detected ATS-host candidates, including 16 Workday, 4 Personio, 3 Recruitee, 1 Lever and 1 SmartRecruiters URL by simple host matching. The academic inventory contains at least 3 Workday and 3 Personio candidates by the same check. This is enough to justify an ATS-routing step before generic proxy fetching.

| Site shape | First route | Fallback | Why |
| --- | --- | --- | --- |
| Greenhouse board | Official public Job Board GET endpoint | Basic proxy only if employer's presentation page is separately needed | Direct control returned JSON with 489 jobs; API is structured and documented publicly |
| Lever published postings | Published postings API | Basic proxy presentation page fallback | Direct control returned JSON with 390 postings; API is structured and documented publicly |
| Workday, Personio, Recruitee, SmartRecruiters or other detected ATS | Domain-specific documented/public endpoint where verified; otherwise bounded direct discovery | Basic then cheap-JS proxy using per-domain evidence | Prevents paying to render pages that already expose data endpoints |
| Static employer careers page | Direct HTML and JSON-LD parser | Basic proxy; cheap JS only after empty/static failure | ABB direct control returned usable HTML and job-related content |
| JS-only academic portal | Direct probe then proxy cheap JS | Full JS only for selected high-yield institutions | Universität Graz direct response appeared to contain a shell rather than job links |
| Exact job detail blocked directly | Direct/API parser first | Proxy with smallest mode that produces title/description | Siemens detail returned direct `403`; this is a good fallback candidate after proxy access is fixed |

### Recommended Scrapy/Downloader Configuration

Runr is currently requests-based, not Scrapy-based. For a shared scheduled catalog, introduce a crawler service or adapter while preserving the workspace/worker APIs.

| Route class | Spider shape | Middleware/settings | Data handling |
| --- | --- | --- | --- |
| JSON APIs and ATS feeds | Plain `scrapy.Spider` issuing JSON requests | `AUTOTHROTTLE_ENABLED`; ETag/Last-Modified if exposed; conservative per-domain concurrency; retry transient `5xx` only | Parse into normalized `job_current`; store source payload hash |
| Static permitted career pages | Bounded `CrawlSpider` with job-detail allow rules | HTTP cache for discovery pages; browser headers where permitted; obey applicable terms/robots policy | Discover links, then fetch changed/new details only |
| ScrapeOps fallback | Custom downloader middleware selecting mode by `source_policy` | Add `json_response=true`, `country`, `max_request_cost`; persist status and `sops_api_credits`; forbid unbudgeted escalation | Every request emits a usage-ledger record |
| Dynamic JS pages | Same spider through proxy middleware | Begin with `render_js_cheap=true`; full JS/residential only after measured failure and domain allow-list | Record which mode first generated usable job content |
| Restricted/high-cost boards | Separate disabled-by-default connector | Require feature flag, approval record, and hard credit cap | Never silently turn on during a broad workspace crawl |

Suggested request-mode policy for a normal company/academic page:

| Attempt | Condition | ScrapeOps mode | Credits for normal successful page |
| ---: | --- | --- | ---: |
| 0 | Permitted public endpoint or stable static page | Direct / ATS API | 0 |
| 1 | Direct blocked or chosen ScrapeOps-only domain | `basic` with country target | 1 |
| 2 | HTML returned but no usable links and domain is approved for JS | `render_js_cheap=true` | 5 |
| 3 | Known high-yield domain failed cheap JS | `render_js=true` | 10 |
| 4 | Exceptional approved anti-bot case only | residential + JS or provider optimization with cap | 25+ |

## Batch Catalog and Storage Architecture

### Recommendation: Shared Batch Catalog Plus Targeted Refresh

Use a hybrid schedule:

- Crawl high-yield structured feeds and newly changed sources once or twice daily.
- Run more frequent incremental checks only for priority sources where new postings disappear quickly and access is permitted.
- Refresh exact user-pasted URLs immediately because their volume is small and intent is high.
- Do not crawl low-yield academic or niche inventories daily merely because they exist in the saved list; schedule them when selected by workspaces or when historical yield justifies continued monitoring.
- Filter and rank from the shared catalog at read time; do not repeat upstream acquisition per workspace.

### Batch vs On-Demand

| Dimension | Shared scheduled catalog | Per-user on-demand scraping |
| --- | --- | --- |
| Upstream load | One acquisition can serve every workspace; strong dedupe opportunity | Repeats identical requests across users and wastes provider credits |
| Query latency | Fast read/rank path | User waits on unreliable third-party fetches |
| Cost predictability | Budgetable by scheduler and route policy | Demand spikes can create unbounded proxy spend |
| Freshness | Limited by schedule unless priority refresh exists | Potentially freshest on request |
| Storage | Requires catalog, versions and expiry handling | Smaller persistent catalog if little is retained |
| Failure behavior | Failed source does not block every user query | External failure appears directly in UX |
| Privacy/personalization | Ranking can use workspace preferences without sending them upstream | Queries may reveal user-specific targeting upstream more often |
| Best fit for Runr | Default for boards, company sites and academic inventory | Exact pasted URLs and explicit user refresh action |

### Do Not Store a Full Copy Per Workspace

The existing `run_jobs` storage is appropriate for workflow results and audit history, but not for a shared daily corpus. A catalog avoids multiplying unchanged job descriptions by runs and users.

Recommended logical schema:

| Table | Purpose | Core fields |
| --- | --- | --- |
| `source` | One monitored origin/strategy | `source_id`, `source_kind`, `platform`, `base_url`, `country_codes`, `ats_type`, `access_method`, `terms_review_status`, `is_active` |
| `source_policy` | Spend and access rules | `source_id/domain_pattern`, `direct_allowed`, `scrapeops_modes`, `country`, `max_request_cost`, `crawl_interval`, `workspace_demand_required` |
| `crawl_run` | Batch execution record | `crawl_run_id`, `scheduled_at`, `started_at`, `finished_at`, `status`, `request_count`, `credit_count`, `jobs_seen`, `jobs_changed` |
| `crawl_request` | Cost/reliability evidence | `crawl_run_id`, `source_id`, `target_url_hash`, `method`, `mode`, `status_code`, `latency_ms`, `billed_credits`, `usable_result`, `error_category` |
| `job_current` | Canonical current listing | `job_id`, `source_id`, `external_job_id`, `canonical_url`, `title`, `company_id`, `location_id`, `employment_type`, `posted_at`, `expires_at`, `last_seen_at`, `status`, `description_text`, `content_hash` |
| `job_version` | Material changes only | `job_id`, `observed_at`, `content_hash`, changed normalized fields or compressed raw-payload pointer |
| `company` / `location` | Normalization dimensions | normalized names, aliases, country/region/city, coordinates where available |
| `workspace_job_match` | Read-time or cached ranking decision | `workspace_id`, `job_id`, `score`, `ranked_at`, `category`, `hidden_reason`, `dismissed_at`, `applied_at` |

Recommended indexes:

| Table | Index |
| --- | --- |
| `job_current` | unique `(source_id, external_job_id)` where present |
| `job_current` | unique or partial unique `(source_id, canonical_url)` |
| `job_current` | `(status, posted_at DESC)`, `(last_seen_at DESC)`, `(company_id, status)`, `(location_id, status)` |
| `job_current` | full-text index on `title` and `description_text`, or external search index only once query load requires it |
| `workspace_job_match` | unique `(workspace_id, job_id)` and `(workspace_id, category, score DESC)` |
| `crawl_request` | `(source_id, occurred_at DESC)` and `(method, mode, occurred_at DESC)` for spend/yield reporting |

### Deduplication Strategy

1. Preserve provider identity first: `(source_id, external_job_id)` is the strongest key.
2. Canonicalize URLs by removing known tracking parameters and normalizing hosts/paths.
3. Use employer requisition ID when extracted from ATS data to merge presentation URLs for the same employer posting.
4. Build cross-source candidate clusters with normalized title, company, location and posting date; do not destructively merge distinct source applications without confidence.
5. Retain source links in an association table so users can choose an apply route and provenance remains auditable.

The current `title_company_signature` fallback can collapse two distinct requisitions with the same title at one employer, particularly across locations. It is acceptable as a duplicate hint, but should not be the final catalog uniqueness constraint.

### Catalog Lifecycle

| Event | Handling |
| --- | --- |
| Listing first seen | Insert `job_current`; create initial version; eligible for ranking |
| Unchanged listing seen again | Update `last_seen_at`; avoid storing another full description |
| Description/title/location changed | Append `job_version`; update current row |
| Absent from source for consecutive scheduled checks | Mark `possibly_closed`, then `closed` using source-specific grace period |
| Closed/stale listing | Remove from new recommendations but retain minimal audit/version data per retention policy |

## Scale and Cost Model

### Model Assumptions

These estimates are planning figures, not a provider quote:

- One stored job observation/version, normalized text plus indexes, averages **8 KB** in the primary database.
- The system retains **90 days** of active/history data; unchanged revisits update `last_seen_at` rather than store duplicate descriptions.
- A well-routed acquisition mix averages **0.25 upstream requests per listing**: one result-page/API request per roughly 20 listings plus detail refresh for 20% of listings. Poor routing can approach one or more requests per listing.
- Infrastructure ranges include managed PostgreSQL, crawler workers, queue/log/backup overhead, and an optional search tier at large scale; they exclude LLM usage and ScrapeOps credits.

### Catalog Infrastructure Envelope

| New/observed listings per day | 90-day primary data at 8 KB/version | Suggested serving shape | Estimated infra/month excluding ScrapeOps |
| ---: | ---: | --- | ---: |
| 10,000 | 7.2 GB | Managed Postgres, one scheduled worker, native full-text search | $50-$150 |
| 100,000 | 72 GB | HA Postgres or equivalent, worker pool, queue, stronger monitoring/search | $200-$700 |
| 1,000,000 | 720 GB | Partitioned/HA database, separate search/index tier, autoscaled workers, object archival | $1,500-$6,000 |

At the larger tiers, keep raw response bodies or historical payload blobs in object storage rather than hot relational rows. Actual cost will depend primarily on retention, replicas, search technology and how often descriptions change.

### Proxy Spend Sensitivity

Under the `0.25 requests/listing` assumption:

| Listings/day | Proxy requests/day | Credits/month: basic | Credits/month: cheap JS | Credits/month: residential + JS |
| ---: | ---: | ---: | ---: | ---: |
| 10,000 | 2,500 | 75,000 | 375,000 | 1,875,000 |
| 100,000 | 25,000 | 750,000 | 3,750,000 | 18,750,000 |
| 1,000,000 | 250,000 | 7,500,000 | 37,500,000 | 187,500,000 |

At $99 per one million published credits, the credit-equivalent monthly expense is approximately:

| Listings/day | Basic | Cheap JS | Residential + JS |
| ---: | ---: | ---: | ---: |
| 10,000 | $7.43 | $37.13 | $185.63 |
| 100,000 | $74.25 | $371.25 | $1,856.25 |
| 1,000,000 | $742.50 | $3,712.50 | $18,562.50 |

Discrete plans, large-volume provider pricing, domain premiums and Data API pricing change actual invoices. More importantly, these numbers show why ATS/API-first extraction is a product requirement, not just an implementation optimization.

### Existing Full-Inventory Company/Academic Scenario

The current estimator applies the following planning band to company-site acquisition: one basic request per selected site minimum; approximately 6 credits/site likely where a target country is supplied; up to 20 credits/site for local-preferred traversal.

| Inventory pass | Selected sites | Minimum credits | Likely credits | Maximum planning bound |
| --- | ---: | ---: | ---: | ---: |
| Regular company inventory | 1,414 | 1,414 | 8,484 | 28,280 |
| Academic inventory | 1,092 | 1,092 | 6,552 | 21,840 |
| Both once/day | 2,506 | 2,506 | 15,036 | 50,120 |
| Both twice/day | 2,506 x 2 | 5,012/day | 30,072/day | 100,240/day |
| Both twice/day for 30 days | - | 150,360 | 902,160 | 3,007,200 |

This estimator also omits domain-specific premiums and can be optimistic if detail crawling or JS escalation expands. Use it to bound runs, not to authorize an unlimited full crawl.

## Academic and Niche Workspace Limits

### Critical Distinction

A cap on **jobs shown to one workspace** improves UX and limits ranking/materialization storage, but it does **not** reduce central scraping requests if the shared catalog still crawls every source. To reduce upstream load, Runr must also cap or demand-gate **sites monitored** and their refresh cadence.

### Recommended Caps

Use two controls, both visible to users:

| Control | Free/default workspace | Pro workspace | Business/admin policy | Effect |
| --- | ---: | ---: | ---: | --- |
| Selected academic sites actively monitored for a workspace when not already in shared hot catalog | 10 | 50 | 250 soft limit, overrideable | Directly reduces low-yield crawl requests |
| Selected niche company sites actively monitored when not in shared hot catalog | 10 | 75 | 500 soft limit, overrideable | Directly reduces crawl requests |
| Academic matches shown in the default results view per refresh window | 25 | 75 | Configurable | Improves feed focus; no acquisition savings by itself |
| Niche-company matches shown in the default results view per refresh window | 50 | 150 | Configurable | Improves feed focus; no acquisition savings by itself |

These site caps are intentionally conservative until yield telemetry exists. A source with proven useful output can move into the shared hot catalog and no longer consume per-workspace duplicate crawling.

### Example Reduction

If a workspace selects 25 academic plus 50 niche-company sites, its uncached selected scope is 75 rather than all 2,506 saved sites:

| Scope | Sites | Estimated likely credits per crawl | Reduction vs full saved inventory |
| --- | ---: | ---: | ---: |
| All current regular + academic inventory | 2,506 | 15,036 | - |
| Selected 75-site scope | 75 | 450 | 97.0% fewer selected sites/likely credits |

Twice daily for 30 days, the 75-site scope estimates to 27,000 likely credits rather than 902,160. Shared hot-catalog reuse reduces incremental per-workspace spend further.

### Filtering and UX Rules

Recommended decision order:

1. Remove closed/stale and duplicate listings.
2. Apply target country/city, permitted work arrangement and hard rejection criteria.
3. Compute relevance score and source confidence.
4. Allocate a results mix: general sources first, then the top academic and niche results up to the visible caps.
5. Preserve overflow in a retrievable filtered view rather than silently discarding it.

Required interface language:

- State the source-monitoring limit before a run: for example, "This workspace monitors 10 selected academic sites on your plan; choose which sites to prioritize."
- State result truncation after ranking: for example, "Showing the top 25 academic matches; 14 additional matches are available under Academic results."
- State when an emergency crawl ceiling was hit and that unexamined openings may exist.

Do not label a source as fully searched when `company_site_emergency_max_job_links_per_site` truncated candidate detail retrieval.

## Integration Recommendations for the Existing Application

### Immediate Blockers and Corrections

| Priority | Change | Reason |
| --- | --- | --- |
| P0 | Resolve ScrapeOps account ban with ScrapeOps or test with an enabled paid account, then rerun the live matrix | Current proxy-backed company and academic paths cannot execute successfully |
| P0 | Fail source validation before starting proxy-only stages if a minimal Proxy API health check returns account-level `403` | Prevents users launching runs that are guaranteed to fail |
| P1 | Capture actual ScrapeOps response metadata/cost, rather than assigning only mode-estimated credits | Necessary for LinkedIn/domain premiums and financial reconciliation |
| P1 | Route recognised ATS hosts to public/documented JSON feeds before generic company-site crawling | Largest controllable cost and completeness improvement |
| P1 | Extend usage telemetry to board fallbacks and LinkedIn routes, not only company-site execution | Otherwise total account spend cannot be attributed accurately |
| P1 | Reclassify or expose the default 8-link company-site ceiling as a normal recall cap unless it is made genuinely exceptional | Users otherwise assume complete coverage |
| P2 | Add global catalog tables and workspace-match tables; retain `run_jobs` for workflow audit results | Enables scrape once, serve many model |
| P2 | Add demand/yield scheduler with site states such as `hot`, `selected`, `low_yield`, `paused` | Avoids repeatedly crawling thousands of irrelevant sites |

### Suggested Usage Ledger Payload

Every provider request should retain:

```json
{
  "source_id": "source_or_domain_policy_id",
  "workspace_id": "optional_when_central_batch",
  "crawl_run_id": "batch_run_id",
  "target_domain": "example.org",
  "method": "scrapeops_proxy",
  "request_mode": "render_js_cheap",
  "target_status_code": 200,
  "provider_status_code": 200,
  "latency_ms": 1250,
  "billed": true,
  "billed_credits_actual": 5,
  "usable_job_count": 12,
  "error_category": ""
}
```

Central batch acquisitions may not have a single `workspace_id`; attribute them to the catalog run and later calculate workspace benefit from match usage. Do not charge the same provider request to every workspace that reads its listing.

## Legal and Operational Guardrails

This is a technical strategy, not legal advice. Before production collection, retain an approved source-policy record for each platform or domain family.

| Route | Guardrail |
| --- | --- |
| LinkedIn | Its User Agreement prohibits using scripts, robots or crawlers to scrape/copy the service; keep disabled unless access is legally approved. |
| Indeed | Its Terms restrict automated systems and scraping/data mining without permission; validate permitted use of any third-party structured-data arrangement. |
| Other third-party job boards | Review current terms and any API/feed option before enabling scheduled collection; a proxy does not create permission. |
| Employer/academic websites | Prefer published job feeds/APIs and respect site terms, robots/access rules, reasonable frequency and removal obligations. |
| Personalization | Keep CV/user attributes in Runr ranking; do not place private user data into upstream scrape queries. |
| Data retention | Store public listing data only as needed for recommendation/audit, mark expired jobs promptly, and provide source provenance. |

## Appendix A: Live Test Results

### Test Method

- Date: 2026-05-26.
- API key source: configured `SCRAPEOPS_API_KEY` in `user_config/.env`; the value was not logged or copied into this report.
- Proxy method: one GET request per target through `https://proxy.scrapeops.io/v1/` with `json_response=true`; country parameter supplied where applicable.
- Scope: bounded diagnostic requests only; no pagination, detail fan-out or bulk extraction.
- Quality measurement: whether a usable target response/body or structured result array was available. Provider-level rejection means target quality was not measurable.

### ScrapeOps Account and Feature Probes

| Probe | HTTP status | Latency | Result | Credits observed |
| --- | ---: | ---: | --- | ---: |
| Account usage before matrix | 200 | 1.698 s | Account endpoint accessible; plan reports 100,000 credits and 1 concurrent request | Used credits reported as 0 |
| Fake Browser Headers API, 2 results | 200 | 0.971 s | Returned two browser header sets | Free feature; no usage change observed |
| Indeed Structured Data Job Search | 403 | 5.842 s | Provider rejected account; no structured results | 0 usage change |
| Minimal Proxy API validation to `example.com` | 403 | 6.685 s | Provider returned account-level ban message | 0 usage change |
| Account usage after matrix | 200 | 2.026 s | Used credits still reported as 0 | 0 total observed |

The redacted provider response category for Proxy API and structured-data requests was `Banned Account`; its message states that proxy use is disabled due to the provider's free-plan account-abuse determination and directs the account owner to upgrade or contact ScrapeOps support. This is an upstream account state, not evidence that the requested job sites blocked ScrapeOps.

### Proxy Route Matrix

| Runr route / target | ScrapeOps HTTP status | Latency | Response quality | Billed cost observed |
| --- | ---: | ---: | --- | ---: |
| LinkedIn guest search | 403 | 5.117 s | No target response; account rejected | 0 |
| Indeed Germany search HTML | 403 | 5.119 s | No target response; account rejected | 0 |
| StepStone Germany search | 403 | 5.095 s | No target response; account rejected | 0 |
| Arbeitsagentur JSON search through proxy | 403 | 5.109 s | No target response; account rejected | 0 |
| Glassdoor search | 403 | 5.326 s | No target response; account rejected | 0 |
| ZipRecruiter search | 403 | 9.229 s | No target response; account rejected | 0 |
| Monster search | 403 | 19.511 s | No target response; account rejected | 0 |
| CareerBuilder search | 403 | 5.199 s | No target response; account rejected | 0 |
| Careerjet search | 403 | 5.115 s | No target response; account rejected | 0 |
| Reed search | 403 | 6.792 s | No target response; account rejected | 0 |
| Totaljobs search | 403 | 5.170 s | No target response; account rejected | 0 |
| JobsDB search | 403 | 5.500 s | No target response; account rejected | 0 |
| Regular company example: ABB careers Germany | 403 | 7.254 s | No target response; account rejected | 0 |
| Academic example: Universitaet Graz jobs | 403 | 5.144 s | No target response; account rejected | 0 |
| Curated example: Siemens exact job URL | 403 | 5.126 s | No target response; account rejected | 0 |

### Direct/Structured Control Requests

These controls do not satisfy the requested ScrapeOps live-success test; they identify viable alternatives while proxy access is blocked.

| Control target | Method/status | Latency | Observed quality | Implication |
| --- | --- | ---: | --- | --- |
| Arbeitsagentur search | Direct JSON, 200 | 1.314 s | 10 offer objects returned | Do not spend proxy credits where this direct structured route remains permitted and reliable |
| ABB careers Germany | Direct HTML, 200 | 1.085 s | Job/career signal present; 53 links | Static/direct discovery may work before proxy fallback |
| Universitaet Graz jobs | Direct HTML, 200 | 0.762 s | No visible job/link signal in returned shell | Candidate for JS/API-specific handling rather than repeated static fetches |
| Siemens exact job link | Direct HTML, 403 | 1.391 s | Blocked status; response still contained job-page signal | Candidate for controlled proxy fallback once enabled |
| Greenhouse public Job Board API control | Direct JSON, 200 | 1.534 s | `jobs` array contained 489 records | Strong API-first route for recognized Greenhouse hosts |
| Lever published postings API control | Direct JSON, 200 | 7.797 s | Root array contained 390 postings | Strong API-first route for recognized Lever hosts |

### Required Retest After ScrapeOps Access Is Restored

Repeat the proxy matrix with:

1. `json_response=true` and actual `sops_api_credits` stored per response.
2. Basic then cheap-JS comparisons only for sources that return empty or unusable basic content.
3. One LinkedIn request only after the legal/product access decision is confirmed.
4. Indeed Structured Data response shape and billing capture.
5. Domain-by-domain usable-job yield, latency, credit cost, and parse success in the internal ledger.

## Sources

### ScrapeOps Documentation

- [Proxy API Basics](https://scrapeops.io/docs/web-scraping-proxy-api-aggregator/getting-started/api-basics/)
- [Proxy Response Formats (`json_response=true`)](https://scrapeops.io/docs/web-scraping-proxy-api-aggregator/getting-started/response_formats/)
- [Proxy Request Costs and Domain Costs](https://scrapeops.io/docs/web-scraping-proxy-api-aggregator/account/request-costs/)
- [Proxy Aggregator Plans and Pricing](https://scrapeops.io/proxy-aggregator/)
- [Render JS Cheap](https://scrapeops.io/docs/web-scraping-proxy-api-aggregator/advanced-functionality/render-js-cheap/)
- [Headless Browser / `render_js`](https://scrapeops.io/docs/web-scraping-proxy-api-aggregator/advanced-functionality/headless-browser/)
- [Residential Proxies](https://scrapeops.io/docs/web-scraping-proxy-api-aggregator/advanced-functionality/residential-proxies/)
- [Country Geotargeting](https://scrapeops.io/docs/web-scraping-proxy-api-aggregator/advanced-functionality/country-geotargeting/)
- [Advanced Functionality List](https://scrapeops.io/docs/web-scraping-proxy-api-aggregator/advanced-functionality/functionality-list/)
- [Data APIs Overview](https://scrapeops.io/docs/data-api/overview/)
- [Indeed Job Search Structured Data API](https://scrapeops.io/docs/data-api/indeed-job-search-api/)
- [Fake User-Agent and Browser Headers API](https://scrapeops.io/docs/fake-user-agent-headers-api/overview/)

### Structured/ATS and Terms Sources

- [Greenhouse Job Board API](https://developers.greenhouse.io/job-board.html)
- [Lever Postings API](https://github.com/lever/postings-api)
- [LinkedIn User Agreement](https://www.linkedin.com/legal/user-agreement)
- [Indeed Terms](https://www.indeed.com/legal?hl=en_US)

### Runr Repository Evidence

- [`backend/orchestration/workspace_builder.py`](../backend/orchestration/workspace_builder.py)
- [`backend/connectors/job_boards/collector.py`](../backend/connectors/job_boards/collector.py)
- [`backend/connectors/job_boards/strategies.py`](../backend/connectors/job_boards/strategies.py)
- [`backend/connectors/company_career_sites.py`](../backend/connectors/company_career_sites.py)
- [`backend/connectors/company_career_discovery.py`](../backend/connectors/company_career_discovery.py)
- [`backend/integrations/scrapeops.py`](../backend/integrations/scrapeops.py)
- [`backend/repositories/sqlite_backed.py`](../backend/repositories/sqlite_backed.py)
- [`backend/domain/job_identity.py`](../backend/domain/job_identity.py)
