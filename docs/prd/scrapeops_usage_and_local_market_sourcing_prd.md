# ScrapeOps Usage And Local-Market Sourcing PRD

## Problem Statement

The current company career site acquisition flow is not economically safe enough for daily user traffic.

From the user's perspective, the failure is simple:

- the system can burn through ScrapeOps credits very quickly
- the user cannot see usage attributed to their own account
- the source scope is too broad because global company-site inventories are merged into the run even when the user only wants one local market
- the current `company_site_max_jobs_per_site=10` behavior is not clearly explained, so users cannot tell whether jobs are skipped
- expensive scraping happens before enough locality filtering is applied
- there is no plan-aware protection layer that limits expensive runs for smaller accounts while allowing larger plans to use broader access

This is now a product problem, not just an implementation detail:

1. daily usage will make shared ScrapeOps spend unpredictable
2. users cannot understand or govern their own consumption
3. global company career sites produce many irrelevant requests for local-market job seekers
4. the current acquisition strategy uses costly ScrapeOps options too early and too often

## Solution

Add a usage-governed company-site sourcing system with four pillars:

1. per-user ScrapeOps usage accounting tied to Clerk user identity
2. a more efficient ScrapeOps-only acquisition strategy that preserves practical result quality while reducing unnecessary credit burn
3. local-market-first company-site sourcing so international companies are scraped only in the market the workspace targets
4. plan-aware company and run limits enforced by user ID, with unlimited access for higher tiers

The product should make ScrapeOps usage visible, attributable, bounded, and intentionally scoped.

## Product Goals

- Make ScrapeOps usage measurable per Clerk user, per run, and per workspace.
- Reduce credit burn without materially reducing useful job discovery.
- Prevent global company-site crawling when the user only wants a local market.
- Make acquisition caps explicit so users understand when the system stops following additional jobs.
- Enforce user-tier limits safely for smaller plans while preserving broader access for premium tiers.
- Support daily usage without requiring manual backend inspection to understand spend.
- Give users a pre-run estimate of expected runner-credit consumption before they launch broad company-site runs.

## Non-Goals

- Replacing ScrapeOps with the archived custom scraper.
- Building a full billing system with invoicing and payment collection in this phase.
- Guaranteeing mathematically identical results across live third-party websites on every run.
- Supporting every possible global market-resolution edge case in the first release.

## Current-State Clarifications

- The current company-site path uses ScrapeOps only.
- The active request profile currently enables JavaScript rendering and residential proxies together, which is one of the most expensive request combinations.
- The current company-site source merges user-entered sites with a broad discovered company-site inventory.
- The current `company_site_max_jobs_per_site` cap limits how many discovered job links are followed for one site during one run.
- In practical terms, if a site exposes more relevant openings than the cap, the rest are not followed in that run unless the product explicitly supports pagination, continuation, or a higher cap.
- This cap is currently a recall-reducing behavior and should not remain the default steady-state product behavior.

## User Stories

1. As a daily user, I want my ScrapeOps usage attributed to my own Clerk account, so that consumption is understandable and governable.
2. As a daily user, I want to see how many ScrapeOps credits a run consumed, so that I can judge whether the run was worth it.
3. As a daily user, I want to see my remaining quota or plan allowance before I start a run, so that I do not trigger an expensive run blindly.
4. As a daily user, I want a run to fail fast when the shared ScrapeOps account is out of credits, so that time is not wasted on doomed work.
5. As a daily user, I want the product to scrape only the local market I targeted, so that global jobs do not waste credits.
6. As a daily user targeting Germany, I want an international company's German careers surface preferred over its global or US careers surface, so that the result set is relevant.
7. As a daily user, I want the UI to explain what the per-site job cap means, so that I know whether some jobs were intentionally skipped.
8. As a daily user, I want the product to follow all locally relevant jobs on a company site by default, so that valid jobs are not silently dropped because of an arbitrary cap.
9. As a workspace owner on a smaller plan, I want hard limits on expensive company-site runs, so that the product protects me from surprise consumption.
10. As a workspace owner on a larger plan, I want broader or unlimited company-site access, so that my plan tier unlocks more reach.
11. As an operator, I want to see ScrapeOps usage aggregated by user, workspace, run, domain, and request profile, so that cost hotspots are diagnosable.
12. As an operator, I want to see which domains and request modes consume the most credits, so that optimization work is data-driven.
13. As a maintainer, I want company-site sourcing to escalate through cheaper ScrapeOps modes before using the most expensive mode, so that credits are spent intentionally.
14. As a maintainer, I want locality checks to happen before expensive deep scraping where possible, so that irrelevant sites are rejected early.
15. As a maintainer, I want plan-aware policy enforcement keyed by Clerk user ID, so that entitlements are consistent across runs and workspaces.
16. As a maintainer, I want a clear internal record of every ScrapeOps request made on behalf of a user, so that support and audit questions can be answered without guesswork.
17. As a maintainer, I want usage reporting that distinguishes successful billed requests from failed unbilled requests, so that finance and debugging use the same truth.
18. As a product owner, I want to know whether optimization changes preserved useful job recall, so that cost savings do not silently destroy output quality.
19. As a daily user, I want to see a rough pre-run estimate in runner credits, so that I can decide whether the run is worth starting before credits are consumed.
20. As a daily user, I want a run-level runner-credit budget, so that one run cannot consume an unreasonable share of my allowance.
21. As a maintainer, I want ScrapeOps out-of-credit errors normalized into a first-class product state, so that users see a clear actionable failure instead of a vague proxy error.
22. As a maintainer, I want secrets and API keys redacted from surfaced errors and logs, so that usage and failure reporting does not leak credentials.
23. As an operator, I want domain-level efficiency reporting, so that I can identify expensive low-yield company sites and tune the source inventory.
24. As an operator, I want request-mode efficiency reporting, so that I can see whether expensive ScrapeOps options were actually necessary.
25. As a maintainer, I want strict and fallback locality policies for global-only career sites, so that local-only sourcing still behaves predictably when a company lacks a local page.
26. As a maintainer, I want emergency ceilings for pathological sites, so that removing the default `10` cap does not create unbounded crawling on broken sites.
27. As a maintainer, I want entitlement policy versioning, so that historical runs remain explainable against the plan rules that were active when they executed.
28. As an operator, I want internal usage totals reconciled against ScrapeOps account-level stats, so that per-user attribution can be trusted operationally.

## Scope

This task should cover:

- per-user ScrapeOps usage attribution tied to Clerk user identity
- usage APIs and UI surfaces for user-level and operator-level visibility
- plan and entitlement controls for company-site acquisition
- local-market-first company-site selection and filtering
- removal of the default per-site job-follow cap, with safer spend controls moved to better policy boundaries
- explicit company-count and budget semantics for companies-per-run and per-user usage
- a cheaper ScrapeOps request strategy with controlled escalation
- fail-fast behavior for out-of-credits states
- measurement needed to compare result quality before and after optimization
- pre-run runner-credit estimation and run-level budget controls
- secret-redaction and error-normalization for ScrapeOps failures
- telemetry for domain efficiency and request-mode efficiency
- reconciliation between internal usage attribution and ScrapeOps account-level totals

## Functional Requirements

### 1. Per-User Usage Attribution

- Every ScrapeOps-backed request must be attributable to:
  - Clerk user ID
  - run ID
  - workspace ID
  - stage
  - target domain
  - request mode
- The system must persist a usage ledger for both:
  - billed successful requests
  - failed or rejected requests
- The ledger must store the actual or estimated credit cost for each request.
- The ledger must support aggregation by day, run, workspace, and user.

### 2. User-Facing Usage Endpoints

- The backend must expose a user-scoped endpoint for the currently authenticated Clerk user.
- The backend must expose operator/admin endpoints for aggregate usage reporting.
- The product must support at least:
  - current plan allowance
  - credits used
  - credits remaining
  - usage by run
  - usage by date window
  - usage by request mode
  - usage by target domain
- The product must expose usage in runner credits for product-facing budgeting and estimation flows, even if backend reconciliation also retains native ScrapeOps credit data.
- The product may ingest ScrapeOps account-level usage endpoints as a reconciliation signal, but per-user attribution must come from the internal ledger because ScrapeOps does not natively know the Clerk user.

### 3. More Efficient ScrapeOps-Only Acquisition

- The company-site flow must remain ScrapeOps-only.
- The flow must not default to the most expensive ScrapeOps mode for every request.
- The acquisition strategy must support a controlled escalation ladder inside ScrapeOps, such as:
  - cheapest viable request mode first
  - escalate only when the prior mode fails or yields clearly unusable output
  - persist which mode succeeded
- The strategy must be configurable per domain or domain family.
- The product must track recall, success rate, and credit cost by request mode so optimization decisions can be validated empirically.

### 4. Local-Market-First Sourcing

- The system must prefer company career URLs aligned to the workspace's target market.
- For international companies, the system must avoid scraping irrelevant global or foreign-market pages when a local-market page can be identified confidently.
- The source inventory should support country and market metadata for company career entries.
- Before expensive deep scraping, the system should reject or deprioritize entries that clearly do not match the workspace market.
- If a company only exposes a global careers site, the system should apply an early locality filter on discovered jobs before following large numbers of detail pages.
- The product must support a strict local-only mode and a softer local-preferred mode.

### 5. Remove The Default Jobs-Per-Site Follow Cap

- The product must stop using a low arbitrary default that follows only a subset of discovered job links for a site.
- If a site exposes more relevant openings, the default behavior should be to continue following locally relevant jobs rather than truncating at `10`.
- Cost control must shift away from silent per-site truncation and toward better boundaries such as:
  - user-tier company-count limits
  - run-level credit budgets
  - local-market filtering before deep detail fetches
  - cheaper request modes before expensive escalation
  - optional safety ceilings for pathological sites
- If any emergency or policy cap still exists for pathological cases, the API and UI must make that truncation explicit.
- The system must report:
  - number of candidate jobs discovered on a site
  - number of candidate jobs followed
  - number of candidate jobs skipped and why
- The product must avoid silently implying that all site jobs were evaluated if any were not followed.

### 6. Plan-Aware Company Limits

- The system must support user-tier policies keyed by Clerk user ID.
- Policy must support at minimum:
  - maximum companies per run
  - maximum runner credits per run
  - maximum daily or monthly company-site usage budget
  - unlimited access for designated higher tiers
- Enforcement must happen before a run starts and during execution if dynamic budget thresholds are crossed.
- The UI must explain why a run or source selection was reduced when policy caps apply.

### 7. Credit-Exhaustion Handling

- The system must detect ScrapeOps out-of-credit responses immediately.
- A run should fail fast or stop the affected acquisition stage when the shared account has no remaining credits.
- The user-facing error must say that the account is out of credits rather than surfacing a vague generic proxy error.
- Secret values and API keys must never appear in surfaced error strings.

### 8. Pre-Run Runner-Credit Estimation

- Before a company-site run starts, the product must provide a rough expected cost estimate in runner credits rather than money.
- The estimate must be based on factors such as:
  - number of companies selected for the run
  - whether discovered inventory expansion is in scope
  - expected request mode ladder
  - market-filter confidence
  - any plan policy limits that would reduce scope
- The estimate should support ranges or confidence bands rather than pretending to be exact.
- The product must also show the user's remaining runner-credit allowance or budget in the same unit.

### 9. Domain And Request-Mode Efficiency Telemetry

- The system must track efficiency metrics by target domain and by ScrapeOps request mode.
- At minimum this telemetry must support:
  - requests made
  - billed runner credits
  - jobs discovered
  - jobs followed
  - jobs accepted after filtering
  - locality match rate
  - success and failure rates
- The product must make it easy to identify domains that consume credits with little local-market value.

### 10. Locality Fallback Policy

- The system must support explicit locality policies for companies that do not expose a clean local-market page.
- These policies must distinguish at least:
  - strict local-only behavior
  - local-preferred behavior with controlled fallback to global pages
  - admin override behavior for special cases
- The chosen locality policy must be visible in run metadata and diagnostics.

### 11. Emergency Ceilings For Pathological Sites

- Removing the default `10` jobs-per-site cap must not create unbounded crawling on broken or pathological company pages.
- The system must support hidden or policy-level emergency ceilings for pathological cases such as:
  - infinite pagination behavior
  - recursive listing loops
  - duplicate-heavy job surfaces
  - extremely large irrelevant archives
- These ceilings must be treated as defensive guardrails, not as the normal product behavior.
- If an emergency ceiling is triggered, the run must record that fact explicitly.

### 12. Policy Versioning And Usage Reconciliation

- Entitlement policies must be versioned so historical runs can be explained against the policy state active at execution time.
- Internal per-user usage attribution must be periodically reconcilable against ScrapeOps account-level totals.
- Reconciliation discrepancies must be observable by operators.

## Solution Design Requirements

- Introduce an internal ScrapeOps usage ledger as the source of truth for per-user attribution.
- Introduce a user entitlement model that can map Clerk user IDs to plan policies.
- Introduce a company-site source policy layer responsible for locality, caps, and escalation strategy.
- Introduce a market-aware company-site inventory model so the system can distinguish local and global career surfaces.
- Introduce a runner-credit abstraction for user-facing estimation, budgeting, and plan enforcement.
- Introduce acquisition telemetry that measures:
  - billed credits
  - unbilled failures
  - success rate
  - jobs discovered
  - jobs followed
  - jobs accepted after filtering
  - locality match rate
- Introduce redaction and normalization for ScrapeOps-originated error messages before they reach user-facing surfaces.

## Implementation Decisions

- Per-user usage attribution must be implemented in the backend, not inferred from ScrapeOps alone.
- Clerk user identity is the policy anchor for usage, caps, and entitlements.
- The first release should optimize within ScrapeOps rather than adding any non-ScrapeOps scraping path.
- Result quality should be protected through an empirical regression harness and domain-level metrics, not through an absolute promise of identical output on live external sites.
- Local-market filtering should happen as early as practical, before expensive job-detail fetching.
- The discovered company-site inventory should evolve from a flat list into a market-aware inventory with explicit locality metadata where possible.
- User-facing plan controls should be policy-driven, not hard-coded in UI logic.
- Default spend control should not depend on dropping jobs after they were already discovered on a relevant company site.
- Any remaining emergency ceilings for pathological pages must be explicit in both backend payloads and frontend copy.
- Pre-run estimation should be shown in runner credits, not money.
- Out-of-credit and similar ScrapeOps failures should be normalized into product-level error categories before they reach the UI.
- Secret-bearing upstream URLs must be sanitized before persistence, logging, or display.
- Internal usage should be reconcilable with ScrapeOps account-level stats, but Clerk-scoped attribution remains an internal responsibility.
- Out-of-credit states must be treated as a first-class product condition, not as a generic connector failure.

## Acceptance Criteria

- A signed-in user can retrieve their own ScrapeOps usage summary through an authenticated endpoint backed by Clerk identity.
- A signed-in user can retrieve their own usage and allowance summary in runner credits through an authenticated endpoint backed by Clerk identity.
- An operator can retrieve aggregate ScrapeOps usage across users, workspaces, runs, domains, and request modes.
- Every ScrapeOps request made during company-site acquisition can be attributed to a Clerk user and run.
- A run detail view shows ScrapeOps credits consumed for that run.
- A pre-run flow shows a rough expected cost range in runner credits before the user starts a broad company-site run.
- The product can enforce different company-site limits for different users based on plan policy.
- A higher-tier user can be configured for unlimited or materially broader company-site access.
- Company-site acquisition no longer defaults every request to the most expensive ScrapeOps mode when cheaper modes can achieve acceptable results.
- The system records whether a site required escalation from a cheaper request mode to a more expensive one.
- For international companies, the system prefers local-market career surfaces when those can be identified.
- In strict local-only mode, foreign-market company pages are skipped unless they can still yield locally matching jobs through explicit policy.
- When a site exposes more candidate jobs than the configured cap, the user can see that truncation occurred.
- By default, the system does not stop at `10` followed jobs for an otherwise relevant company site.
- If any jobs are not followed because of an emergency ceiling or policy guardrail, the system explains exactly why.
- When ScrapeOps credits are exhausted, the run stops quickly with a clear out-of-credits message.
- User-facing errors do not leak the ScrapeOps API key.
- Operators can inspect domain-level and request-mode efficiency metrics to identify low-yield spend.
- Historical runs remain explainable against the entitlement policy version active at the time.
- Internal usage totals can be reconciled against ScrapeOps account-level totals within an acceptable discrepancy threshold.

## Testing Decisions

- Tests must verify externally visible behavior, not internal implementation details.
- The usage ledger must be tested through observable attribution outcomes:
  - correct user mapping
  - correct run mapping
  - correct aggregation totals
  - correct handling of billed versus unbilled requests
- Runner-credit estimation must be tested through observable ranges and plan-budget enforcement, not exact implementation formulas.
- Policy enforcement must be tested through behavior:
  - allowed user can start broad run
  - capped user is reduced or blocked
  - unlimited user bypasses the cap policy
- Local-market sourcing must be tested with representative company-site fixtures covering:
  - local-only company
  - international company with local career page
  - international company with only global page
  - ambiguous location signals
- Escalation strategy tests must verify that:
  - cheaper modes are attempted first
  - expensive modes are only used when needed
  - telemetry records the final mode and cost
- The removal of the default per-site follow cap must be tested so relevant jobs are not silently dropped after discovery.
- Any remaining emergency ceiling behavior must be tested so the API and UI payloads report discovered-versus-followed counts and skip reasons correctly.
- Error-normalization tests must verify that out-of-credit states are classified clearly and that API keys or secret-bearing URLs are never surfaced.
- Reconciliation tests must verify that internal usage summaries can be compared with account-level ScrapeOps totals and that discrepancies are surfaced.
- Regression tests must compare optimized acquisition against a baseline fixture set to ensure useful discovery quality does not collapse during cost optimization.
- Prior art should follow the repo's existing backend API tests, stage integration tests, and workflow runtime tests for persistent run state and user-facing payloads.

## Out of Scope

- End-user self-service plan purchase, checkout, or subscription management.
- Full enterprise billing export pipelines.
- Perfect geographic certainty for every external job page on the public web.
- Solving all company-site discovery quality issues in the same task.
- Reintroducing the custom local scraper into the active execution path.

## Further Notes

- The current `jobs per site` cap is not merely a display preference. It affects acquisition breadth and can suppress valid jobs if the site exposes more openings than the configured follow limit.
- The PRD direction is to remove that cap as the normal default and replace it with smarter cost controls earlier in the acquisition path.
- The target outcome is not "scrape fewer pages" in isolation. The target outcome is "spend credits only where the probability of useful local-market output is high."
- Because users are expected to run this daily, the system needs both preventive controls before runs and post-run usage visibility after runs.
- The first release should favor operational safety and explainability over aggressive breadth.
- Product-facing spend communication should use runner credits rather than money, even if internal operations still reconcile against native ScrapeOps credits and billing.
