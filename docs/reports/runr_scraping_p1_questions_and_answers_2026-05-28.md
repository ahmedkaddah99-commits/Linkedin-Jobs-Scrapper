# Runr Scraping P1 Questions And Answers - 2026-05-28

**Related report:** `docs/reports/runr_scraping_p1_work_and_efficiency_report_2026-05-27.md`

## Verbatim Question Transcription

```text
I have a couple of questions I want you to transcribe all of them and listen to me the way that I say them. Don't change or alter the words because it can change the meaning because it's a lot of specific words. Number one, regarding the evaluation summary section, it says that 137 tests have been passed and 19 tests have failed and compile all our tests. What exactly are the tests that were done to ensure that this new addition to the source code has been passed? What exactly are those tests? Also, for the ScrapOps health check, what does this do and what's the point of it? For the company proxy credit code, it says that ABB is target recorded as API credit equal to 1. Why equal 1? And what is the user's ledger and where is it and what's the point of it? For the broad fallback probe, it says indeed Germany direct request returned therefore 403 error. And it says that the residential proxy fallback is actually for the build credits are actually 10. Is this the cap or what's the point and why did it even fail? Because supposedly there is ScrapOps API guarantee, that's what I understood. So I'm not getting to our one. What is it and what's the point of it? Recall cap evidence. If this for seniors and if it's hit the cap, what is the point and what is the info log emitted and what does the info log say and where is it in the source code? And also is this something specific to seniors or is this, or would something like this apply to all major companies because we have a lot of URLs in their carrier site. Now for the work completed section. ScreenOps proxy API, I think we already answered it, or I already asked this question, but why the JSON response is equal to true? Are those the alternative logs? And is this a line that's written in the .env file, or what's the point of having it here? Can you tell me which file is it in? And if I turn it to false, what will happen? If I state it, keep it at true and hit production, what will happen? Will the full freeze become so massive that I'm not able to run, or what's the issue exactly here? Also, what's the point of the five-second timeout when it comes to this? For the ATS route section on the same section, it says that the ATS router has been added, and it supports the connection of Greenhouse, Lever, Workday, Personio, the Canadian smart equity database. Everything. Are there any major ones that I left out? And what does this do to all the career company URLs that already have? Also, you see that one important indication is that no super greenhouse or lever inventor URL was found in the local equity database. So, what exactly do you need here for it to work? Do you mean that no companies use Greenhouse or lever, or what's the point of this? And why does the Inventory code remain blocked and what is in the inventory code? Now, the actual credit reporting is fine, I just still also want to know where exactly is it. And it's written, is it written in JSON or is it written in some sort of data where I can then use an endpoint and surface it and put it in the admin facing dashboard, or how would this work? Also, I don't see a user ID here. Why? I mean, even when it comes to credit reporting, there should be user ID and there is already a collector setup that should connect the user ID to the consumption of the scraper specifically. The board fallback in LinkedIn telemetry, what is this exactly? What's the point of it? And also when you say no live LinkedIn proxy was made during testing, what is this exactly and why was it happening? The dynamic data schedule, does this use to schedule the workday runs or what's the point of this schedule? To make sure that the API for the scraper keeps working efficiently, what's the point? Also, the yield behavior, is this the data that we get for each company site that is scraped or what is it exactly? And also, can it be surfaced or is it already recorded in a data-friendly document where I can surface this data and see it? Also, the account, the user ID, it should be linked to this. Otherwise, I would not know who is causing the issue and why the issue is being caused. The recall classification, why was it changed the name and what exactly does it do? Now for the efficiency analysis, what exactly did you do to... measure this efficiency. I wanted to elaborate and explain it more of what this would mean for the user that would use this tool daily. I also want to know the logic of how you were able to calculate the credits per day. The new operating model, dig a bit deeper and explain to me, first of all, I want the high level of what is this and what does it do, and where is it, and what does it consist of. Also when for the efficiency by source type, when you see that the best case is that the zero proxy credits are used, does this by proxy mean residential IPs so that we don't get blocked by the boss, or what is the meaning here exactly? Also for the ones that no credit savings yet, except better login route ingredients, I want you to also explain why is this the case. The academic sites, do you mean that the sites that don't produce anything, you would focus on them less because it says large savings by avoiding inactive entry and measuring actual credits. What does this exactly mean and how does it practically transform so when the user is using the tool? Also why is the one expensive? I don't see it expensive. Check the later runs, didn't take a lot of credit freely and it produced a couple of charts. So why is really LinkedIn flagged as the one or the only one that's specific? So far my experience with the Carissa is that they are much, much more expensive than LinkedIn is. And for the remaining, the frequency opportunities are also explained in detail, what is each of those and what is needed to be done for them to be also utilized.
```

## Short Correction On The Test Count

The report does **not** say 19 tests failed. It says:

```text
137 passed, 19 subtests passed
compileall passed
git diff --check -- backend tests passed
```

So the intended meaning is: 137 tests passed, plus 19 parameterized `subTest` checks passed. A `subTest` is one test method that runs multiple input cases. It is not a failed test.

I reran the focused scraping-related subset on 2026-05-28:

```text
python -m unittest tests.test_scrapeops_integration tests.test_ats_router tests.test_job_board_connectors tests.test_sqlite_repositories tests.test_company_career_discovery tests.test_stage_adapters -v
Ran 49 tests in 2.663s
OK
```

Full `unittest discover tests -v` did not finish inside the 3-minute command window, so this Q&A should not be read as a fresh full-suite green result.

## Tests That Prove The P1 Additions

The new scraping additions are mainly covered by these tests:

| Test file | What it proves |
|---|---|
| `tests/test_scrapeops_integration.py` | Proxy requests always ask for `json_response=true`; ScrapeOps envelopes expose `sops_api_credits`; usage records keep actual and estimated credits; health check detects healthy, banned, out-of-credit, and 401 cases. |
| `tests/test_ats_router.py` | ATS detection for Greenhouse, Lever, Workday, Personio, Recruitee, SmartRecruiters; Greenhouse and Lever API normalization; unsupported ATS falls through; company-site scraping skips proxy when ATS API results exist. |
| `tests/test_job_board_connectors.py` | Job-board fallback records actual ScrapeOps credits into the ledger. |
| `tests/test_sqlite_repositories.py` | `scrapeops_usage_ledger` persists actual credits and aggregates spend by source; `site_source_policy` transitions selected -> low_yield -> selected; run `user_id` migration works. |
| `tests/test_company_career_discovery.py` | Company-site parsing, local-market filtering, no silent 10-job cap, recall cap reporting through `capped_sites`, domain policy request modes/country, navigation-link filtering. |
| `tests/test_stage_adapters.py` | Deprecated cap key still works, company-site stage passes proxy settings, stage persists `capped_sites`, policy/yield wiring into the stage. |
| `tests/test_backend_api.py` | API exposes `capped_sites`, ScrapeOps usage in billing/run/customer view, source-validation estimates, admin ScrapeOps policy/dashboard/reconciliation endpoints. |

`compileall` is different from behavior tests. It compiles Python files to bytecode and catches syntax-level breakage. `git diff --check -- backend tests` checks whitespace problems such as trailing spaces.

## ScrapeOps Health Check

The health check is in `backend/integrations/scrapeops.py`:

- `check_scrapeops_proxy_health()`
- `require_scrapeops_proxy_health()`

It sends one small ScrapeOps Proxy API request to `https://httpbin.org/get` with `json_response=true` and a 5-second timeout. The point is to fail before a paid scraping run starts if the account is clearly unusable.

It checks:

- missing API key
- banned account
- insufficient credits
- timeout/network failure
- proxy unavailable
- healthy proxy response

It does **not** guarantee that Indeed, LinkedIn, Siemens, ABB, Workday, or any other target site will succeed. It only proves the shared ScrapeOps account can make a basic proxy request right now.

The 5-second timeout is intentionally short because this is a gate, not the actual crawl. If this tiny check hangs, the run should fail fast instead of making the user wait for a doomed scrape.

## ABB `sops_api_credits=1`

The ABB probe recorded `sops_api_credits=1` because the provider response said that the successful ABB request cost 1 ScrapeOps API credit. This was a normal/basic proxy request, and the code's basic mode estimate is also 1 credit.

This is not a hardcoded ABB rule. The value comes from ScrapeOps response metadata when `json_response=true` is used. The code parses it in `parse_proxy_response_envelope()` and writes it through `build_proxy_usage_record()`.

Current local SQLite evidence in `.backend_data/backend.sqlite3` has this row:

```text
source_id=careers.abb
request_mode=basic
target_status_code=200
provider_status_code=200
billed_credits_actual=1
billed_credits_estimated=1
run_id=live_probe_task3_2026_05_27
source=codex_validation
```

The `user_id` is empty for that row because it was a Codex validation probe, not an authenticated user run.

## Usage Ledger

There are two related storage paths:

1. `scrapeops_usage_ledger` table in SQLite.
2. `analytics_events` rows with `event_name='scrapeops_request'` and JSON payloads.

The ledger schema is in `backend/repositories/sqlite_backed.py`. It stores:

- `ledger_id`
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
- `user_id`
- `workspace_id`
- `run_id`
- `route`
- `source`

The default local database path is `.backend_data/backend.sqlite3`, created by `backend/bootstrap.py`.

The point of the ledger is attribution and auditability: who caused proxy spend, from which run/workspace/source, with which request mode, for which target, and how many actual credits ScrapeOps charged.

## User ID Attribution

The report table omitted `user_id`, but the current schema includes it.

In real worker runs, `_build_scrapeops_usage_callback()` in `backend/adapters/stage_adapters.py` pulls `context.run.normalized_user_id` or `context.run.user_id` and writes it into both:

- `scrapeops_usage_ledger.user_id`
- `analytics_events.user_id`

The report's live probe rows have empty `user_id` because they were manual validation rows with `source=codex_validation`, not user-launched jobs. That is why the report evidence table does not show a user ID.

Authenticated usage is already surfaceable through:

- `GET /scrapeops/usage`
- `GET /admin/scrapeops/usage`
- `GET /billing/subscription`
- run customer view payloads

The admin dashboard frontend is `frontend/src/pages/AdminScrapeOpsPage.jsx`.

## Board Fallback Probe And The `10` Credits

The board fallback probe means:

1. Try the job board directly first.
2. If direct access is blocked, for example target status `403` or `429`, call ScrapeOps Proxy API.
3. Record the real ScrapeOps cost in the same usage ledger.

For Indeed Germany, the direct request returned `403`, so the code used a residential ScrapeOps fallback. The recorded `billed_credits_actual=10` is not a cap. It is the actual cost of that single successful residential fallback request.

The request mode is defined in `backend/connectors/job_boards/strategies.py`; `residential` is configured as 10 native/runner credits in `backend/integrations/scrapeops.py`.

The current local ledger contains:

```text
source_id=indeed
request_mode=residential
target_status_code=200
provider_status_code=200
billed_credits_actual=10
run_id=live_probe_task4_2026_05_27
source=codex_validation
```

Why did the direct request fail? Because Indeed returned `403` to the direct HTTP request. ScrapeOps is not a universal guarantee that every target site will allow every request. It is a proxy service with paid request modes. Sites can still block, accounts can still be unhealthy, and some domains can still require different strategies or legal/product approval.

## Recall Cap Evidence

This was about **Siemens**, not "seniors." The behavior is not Siemens-specific.

The cap applies to company and academic career site scraping generally. If a career site exposes many job links, the scraper follows only up to `company_site_max_job_links_per_site` links for that site. The current default injected by runtime/source validation is 25.

The point is to prevent one large career site from burning a large number of proxy requests in one run. It also makes incomplete recall visible through `capped_sites`, so the user/admin can see that the site had more jobs than were fetched.

The INFO log is emitted in `backend/connectors/company_career_sites.py`:

```text
Job link cap reached for %s: retrieved %s links, cap is %s. Additional jobs on this site were not fetched. Increase company_site_max_job_links_per_site to fetch more.
```

The API payload exposes entries like:

```json
{
  "url": "https://example.com/careers",
  "links_fetched": 25,
  "cap_value": 25
}
```

So yes, this applies to major companies too if their career sites expose more links than the configured cap.

## `json_response=true`

`json_response=true` is not an `.env` setting. The `.env` file only stores `SCRAPEOPS_API_KEY` for this behavior.

The code adds `json_response=true` in `backend/integrations/scrapeops.py`:

- `build_proxy_params()`
- `check_scrapeops_proxy_health()`

It is not an alternative log. It changes the ScrapeOps response shape from raw target HTML into a JSON envelope that includes provider metadata such as:

- target status code
- response body
- `sops_api_credits`

If it is turned off, the scraper may still receive HTML, but it loses reliable actual-credit metadata. Then usage reporting falls back to estimates or records `billed_credits_actual=None/0`, which breaks accurate cost reconciliation.

Keeping it true in production is the correct setting for credit reporting. It does make responses slightly larger because the body is wrapped inside JSON, but the ledger does not store full page bodies. It stores metadata only. The main production risk is not database bloat from `json_response=true`; the risk is broad crawl scope and expensive request modes.

## ATS Router

The router is in `backend/connectors/ats_router.py`.

It currently detects:

- Greenhouse
- Lever
- Workday
- Personio
- Recruitee
- SmartRecruiters

It implements direct structured API fetching only for:

- Greenhouse
- Lever

For Workday, Personio, Recruitee, and SmartRecruiters, it detects the ATS but intentionally falls through to the proxy path because direct structured fetchers were not implemented in P1.

Major ATS families not yet covered include at least:

- iCIMS
- Oracle Taleo / Oracle Recruiting
- SAP SuccessFactors
- Ashby
- BambooHR
- Teamtailor
- Jobvite
- Workable
- Phenom
- ADP / UKG
- Pinpoint

Current local inventory scan found:

```text
greenhouse: 0
lever: 0
workday: 19
personio: 7
recruitee: 3
smartrecruiters: 1
taleo: 1
```

So the statement "no saved Greenhouse or Lever inventory URL was found" means exactly that: in the local saved inventory files, there were zero Greenhouse and zero Lever URLs. It does **not** mean no companies use Greenhouse or Lever globally.

For a live Greenhouse/Lever probe, the system needs a saved URL such as:

```text
Company | https://boards.greenhouse.io/<board_token>
Company | https://jobs.lever.co/<company_slug>
```

The relevant inventory files are:

- `user_config/discovered_regular_company_career_sites.live.txt`
- `user_config/discovered_phd_university_career_sites.live.txt`

The "blocked" part means the live evidence probe is blocked by missing local inventory examples, not that the router code is blocked.

## Effect On Existing Company Career URLs

Existing company career URLs are not deleted or rewritten. At runtime, the company-site scraper checks each URL:

1. If it is Greenhouse or Lever and the API returns jobs, use the direct API and spend zero ScrapeOps proxy credits.
2. If it is Workday, Personio, Recruitee, or SmartRecruiters, log/detect it but fall through to generic proxy scraping for now.
3. If it is not recognized as ATS, use the normal company-site scraping path.

So this is an optimization layer before proxy fallback, not a replacement of the saved inventory.

## Actual Credit Reporting And Dashboard Surface

The data is stored in SQLite, not just in markdown or logs.

Storage:

- structured ledger table: `scrapeops_usage_ledger`
- analytics event stream: `analytics_events.payload_json`

Backend endpoints:

- `GET /scrapeops/usage` for the authenticated user's own usage
- `GET /admin/scrapeops/usage` for admin aggregate usage, with filters by user/workspace/run/date
- `GET /admin/scrapeops/policy`
- `PUT /admin/scrapeops/policy`
- `POST /admin/scrapeops/reconciliation/run`
- `GET /billing/subscription`, which includes ScrapeOps usage context

Frontend:

- `frontend/src/pages/AdminScrapeOpsPage.jsx`
- route: `/admin/scrapeops`

So yes, it is already in a data-friendly shape for an admin dashboard. The newer admin implementation report, `docs/scrapeops_usage_and_admin_dashboard_implementation_report.md`, records that this dashboard work was completed after the P1 report.

## Board Fallback And LinkedIn Telemetry

Board fallback telemetry means generic board connectors now record ScrapeOps fallback spend. For example, StepStone or Indeed can try direct HTTP first; if blocked, the fallback proxy request records actual billed credits.

LinkedIn telemetry means LinkedIn proxy fallback now:

- warns before using the proxy
- uses `json_response=true`
- records actual billed credits
- logs the billed credits after the request

No live LinkedIn proxy request was made during the P1 testing because LinkedIn is high-cost and legally/operationally sensitive. The code path was instrumented, but the report avoided spending a live LinkedIn proxy request just to prove telemetry, especially because the strategy report flagged LinkedIn as 70 credits/request.

## Demand-Gated Site Scheduler

This is the section the report calls "Demand-Gated Site Scheduler." It is not a Workday-specific scheduler and it is not a keepalive system for ScrapeOps.

It is a policy gate for company and academic site crawling. The state table is `site_source_policy`, with states:

- `hot`
- `selected`
- `low_yield`
- `paused`
- `pending`

The stage code uses it in `backend/adapters/stage_adapters.py` before calling `scrape_company_career_sites()`. The repository logic is in `backend/repositories/sqlite_backed.py`.

Shared scheduled crawling should only crawl `hot` and `selected` sources. `low_yield`, `paused`, and `pending` sources are skipped unless explicitly triggered by a workspace.

## Yield Behavior

Yield behavior is source-level state, not job data itself.

For each site URL, `site_source_policy` can record:

- `site_url`
- `site_type`
- `site_state`
- `consecutive_zero_yield_runs`
- `last_jobs_found`
- `last_crawled_at`
- `updated_at`

Rules:

- if `jobs_found > 0`, reset zero-yield count
- if the previous state was `low_yield` and jobs are found, return to `selected`
- after 3 consecutive zero-yield runs, move to `low_yield`

This can be surfaced, but it is not yet exposed as a finished user/admin endpoint in the same way ScrapeOps usage is. Right now it is in the SQLite table and repository methods such as `get_site_policy()`. A dashboard table would need a small API endpoint/query over `site_source_policy`.

User ID caveat: `site_source_policy` is source-level shared scheduling state, so it does not store `user_id`. ScrapeOps usage events do store user/run/workspace IDs. If you want to diagnose "which user caused this source to be crawled and cost credits," use the usage ledger/events. If you want "who selected/promoted this source state," that is not fully audited yet and should be added if needed.

## Recall Cap Reclassification

The old key:

```text
company_site_emergency_max_job_links_per_site
```

was renamed to:

```text
company_site_max_job_links_per_site
```

The rename happened because this is no longer only an emergency kill switch. It is a normal recall-vs-cost control.

What it does:

- limits how many discovered job detail links are followed per career site
- prevents one large company from exploding request count
- emits `capped_sites` so users/admins know recall was incomplete
- keeps the old key working with a deprecation warning

This is different from the old silent `company_site_max_jobs_per_site=10` behavior. The newer work removed the silent low 10-job default, while keeping an explicit visible link cap.

## Efficiency Analysis Method

The report's efficiency numbers are estimates, not a production measurement from thousands of live ScrapeOps requests.

Inputs:

- regular company inventory: 1,414 saved sites
- academic inventory: 1,092 saved sites
- total saved sites: 2,506

The estimator used:

- minimum: 1 credit/site/pass
- likely: about 6 credits/site/pass when target country is supplied
- maximum planning bound: about 20 credits/site/pass for local-preferred traversal

So:

```text
2,506 sites * 1 = 2,506 credits per full pass minimum
2,506 sites * 6 = 15,036 credits per full pass likely
2,506 sites * 20 = 50,120 credits per full pass maximum
```

Twice daily:

```text
15,036 likely credits/pass * 2 = 30,072 credits/day
```

Monthly:

```text
30,072 credits/day * 30 = 902,160 credits/month
```

The new model changes the formula:

```text
active_sites = hot_sites + selected_sites
daily_credits ~= active_sites * likely_credits_per_site * runs_per_day
daily_credits ~= active_sites * 6 * 2
daily_credits ~= active_sites * 12
```

For a daily user, the practical meaning is: the tool should not burn credits crawling all saved company and academic sites every time. It should crawl relevant active sources, show estimates before runs, age out zero-yield sources, and expose actual credit burn after the run.

## New Operating Model

High level: move from "scrape the whole saved inventory" to "route cheaply first, crawl only active/demanded sources, and record actual spend."

It consists of:

- ATS direct route first: `backend/connectors/ats_router.py`
- proxy health and credit envelope parsing: `backend/integrations/scrapeops.py`
- company/academic scraper with caps, domain policy, usage callbacks: `backend/connectors/company_career_sites.py`
- stage wiring for user/run/workspace attribution: `backend/adapters/stage_adapters.py`
- persistent ledger and source policy tables: `backend/repositories/sqlite_backed.py`
- source validation and usage aggregation: `backend/application/services.py`
- API endpoints: `backend/api/server.py`
- admin UI: `frontend/src/pages/AdminScrapeOpsPage.jsx`

This operating model is about cost control and attribution, not just scraping speed.

## "Zero Proxy Credits" Meaning

In the report, "proxy credits" means any ScrapeOps Proxy API credits, not only residential IPs.

Best case zero proxy credits means the scraper uses a direct public API, such as Greenhouse or Lever, and does not call ScrapeOps at all.

Residential proxy is only one ScrapeOps mode. Other proxy modes include:

- basic
- cheap JS render
- JS render
- residential
- residential JS render

## Why Some ATS Types Have No Credit Savings Yet

Workday, Personio, Recruitee, and SmartRecruiters are detected, but direct structured fetchers are not implemented yet. Because of that, detection currently improves logging and future routing readiness, but it does not yet bypass proxy requests.

To get the credit savings, each ATS needs:

- URL parsing rules
- direct API endpoint construction
- pagination handling
- job normalization
- tests with representative fixtures
- fallback behavior when direct API fails

## Academic Sites

The academic-site statement means: do not keep spending daily proxy credits on saved university/department/institute pages that repeatedly produce zero usable jobs.

Practical behavior:

- if an academic site keeps producing zero jobs, it can move to `low_yield`
- `low_yield` sites are skipped by the shared schedule
- if a user explicitly selects one, it can still be crawled
- a future weekly low-yield lane can recheck them occasionally instead of never checking again

This is how "avoid inactive inventory" becomes a product behavior: fewer dead sources are crawled automatically, and spend is concentrated where useful output is more likely.

## Why LinkedIn Is Flagged

LinkedIn is flagged because it is special on a **per-request** and legal/operational basis:

- the strategy report recorded ScrapeOps' LinkedIn cost as 70 credits/request
- LinkedIn scraping is terms-sensitive
- broad list-plus-detail crawling can multiply requests quickly

This does not mean LinkedIn will always be the largest total cost in your actual runs.

Your experience that career sites can be more expensive is valid. Career sites can cost more in aggregate because there are thousands of them, and one run may fetch many site pages and job detail pages. The report's own baseline says a full regular+academic pass is the bigger budget risk: 15,036 likely credits per pass, or 902,160 likely credits/month at twice daily.

So the correct interpretation is:

- LinkedIn is a high-cost special domain per request.
- Company/career sites are the bigger aggregate risk if broad crawling is not gated.
- The ledger should decide future optimization priority from real totals by source/domain/run.

## Remaining Efficiency Opportunities

1. Implement direct fetchers for Workday, Personio, Recruitee, and SmartRecruiters.

Needed: endpoint research, URL parsing, pagination, normalization into Runr job shape, tests, and fallback rules. This creates the same kind of zero-proxy-credit path that Greenhouse and Lever already have.

2. Add budget alerts using `get_spend_by_source(since)`.

Needed: alert thresholds, scheduled evaluation, admin notification surface, and optional external notifications. The admin dashboard now has reconciliation alerts, but source-specific budget alerts can be more granular.

3. Add source-level yield reports combining `usable_job_count` with actual credits.

Needed: persist/populate `usable_job_count` consistently, aggregate by source/domain/site, and expose a dashboard table like "credits per usable job." This would show exactly which sites are wasteful.

4. Promote proven high-yield sources to `hot`; keep everything else `selected` only when a workspace needs it.

Needed: operational rule or admin action for promotion, for example "3 recent runs with jobs_found > N and credits/job below threshold." This keeps good sources frequent and avoids making all saved inventory frequent.

5. Add a weekly low-yield crawl lane.

Needed: worker schedule lane for `low_yield` sources, a weekly cadence, and caps. This prevents low-yield sources from being skipped forever while still avoiding daily waste.

6. Avoid LinkedIn as unattended batch infrastructure unless budget and data-access basis are approved.

Needed: explicit feature flag, run-level hard cap, admin approval/audit event, and a product/legal decision about whether this source is allowed for unattended scraping.

