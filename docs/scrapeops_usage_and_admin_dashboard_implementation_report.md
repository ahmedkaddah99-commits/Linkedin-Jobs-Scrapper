# ScrapeOps Usage And Admin Dashboard Implementation Report

## Document Purpose

This report summarizes the implementation completed against:

- [ScrapeOps Usage And Local-Market Sourcing PRD](./prd/scrapeops_usage_and_local_market_sourcing_prd.md)
- the follow-up admin-only ScrapeOps operations dashboard
- the follow-up request to finish the previously partial and missing dashboard/policy items

It records what was delivered, how the system now behaves, what was verified, and what operational risks remain.

## Executive Summary

The company career site acquisition system has been moved from opaque ScrapeOps usage into a governed, measurable, plan-aware, admin-configurable system.

The delivered system now includes:

- per-user ScrapeOps usage attribution tied to authenticated user identity
- runner-credit budgeting and plan-aware limits
- user-specific policy overrides controlled by admin policy
- local-market-first company-site selection and filtering
- admin domain policies for special sites, ATS families, country overrides, request-mode ladders, and locality behavior
- ScrapeOps-only company-site execution with the legacy direct scraper inactive
- removal of the silent default `10 jobs per site` cap
- pre-run runner-credit estimation
- run progress diagnostics that expose what is being scanned and why it is slow or failing
- fail-fast ScrapeOps out-of-credit handling
- request-mode, domain, run, and day-level telemetry
- admin-only ScrapeOps dashboard with usage charts, reconciliation history, alerts, and policy editing
- scheduled in-app reconciliation snapshots and alert event generation from the worker loop

The result is that broad company-site runs are now bounded, attributable, inspectable, and configurable without code changes for the main operator controls.

## Problem Addressed

Before this work:

- ScrapeOps usage was not attributable per Clerk user.
- Broad company-site runs could consume credits without clear user, run, domain, or request-mode accounting.
- Global company-site inventories were scraped even when the user only cared about one local market.
- The default `10 jobs per site` behavior silently reduced recall.
- Operators had no clear place to control plan limits, user exceptions, special-domain behavior, reconciliation, or alerts.
- The frontend exposed weak progress and weak operational diagnostics during long-running runs.

## Delivered Scope

The completed work covers the PRD and follow-up scope:

- per-user ScrapeOps attribution
- usage APIs
- runner-credit abstraction
- local-market-first company-site sourcing
- removal of the default low jobs-per-site cap
- plan-aware company-site and runner-credit limits
- per-user admin policy overrides
- admin-configurable domain optimization policies
- pre-run runner-credit estimation
- fail-fast out-of-credit handling
- secret redaction for ScrapeOps errors
- request-mode, domain, run, and daily telemetry
- recall-vs-cost visibility at run level
- admin-only ScrapeOps dashboard
- admin policy editor
- automated in-app reconciliation snapshots and alert events
- historical usage and reconciliation charts/tables

## Backend Implementation

### 1. ScrapeOps Integration Layer

Added [backend/integrations/scrapeops.py](../backend/integrations/scrapeops.py).

This module centralizes:

- ScrapeOps endpoint definitions
- request-mode profiles and credit estimates
- runner-credit and native-credit estimation helpers
- country normalization
- proxy parameter building
- error sanitization
- out-of-credit classification
- account usage fetches
- domain-stat fetches
- policy version constant

### 2. Usage Ledger And Aggregation

Updated:

- [backend/adapters/stage_adapters.py](../backend/adapters/stage_adapters.py)
- [backend/application/services.py](../backend/application/services.py)
- [backend/application/quota.py](../backend/application/quota.py)

Every ScrapeOps-backed request now emits an analytics event with:

- user id
- workspace id
- run id
- target domain
- request mode
- billing status
- runner credits
- native ScrapeOps credits
- request stage
- optional domain policy id

Usage can now be grouped by user, workspace, run, request mode, domain, and day.

Run-level usage now includes `jobs_found` and `runner_credits_per_job` for company-career-site jobs, giving the admin dashboard a practical recall-vs-cost view.

### 3. Persistent Admin ScrapeOps Policy

Added persistent app configuration storage:

- [backend/repositories/file_backed.py](../backend/repositories/file_backed.py)
- [backend/repositories/sqlite_backed.py](../backend/repositories/sqlite_backed.py)
- [backend/bootstrap.py](../backend/bootstrap.py)

Added [backend/config/scrapeops_admin_policy.py](../backend/config/scrapeops_admin_policy.py).

The policy supports:

- plan policy limits
- per-user overrides by user id
- domain policies by domain or company-name pattern
- request-mode ladders per domain policy
- country overrides per domain policy
- locality-mode overrides per domain policy
- alert cadence, low-credit threshold, discrepancy threshold, and history window

### 4. Plan And Quota Controls

Updated [backend/config/plans.py](../backend/config/plans.py).

Policy controls now cover:

- `runner_credits_per_month`
- `company_sites_per_run`
- `runner_credits_per_run`

The runtime quota overrides now use the effective admin policy, not only the static plan defaults.

### 5. Company-Site Acquisition Redesign

Updated [backend/connectors/company_career_sites.py](../backend/connectors/company_career_sites.py).

Delivered behavior:

- ScrapeOps-only execution path
- inactive archived direct-fetch path for future experiments
- request-mode escalation ladder instead of unconditional expensive residential JS
- local-market-first site scope planning
- `local_preferred` and `strict_local_only` modes
- admin domain policies applied during both pre-run scope planning and runtime scraping
- per-domain request-mode and country override support
- candidate discovery metrics and locality filtering
- emergency ceilings for pathological sites
- explicit reporting of discovered, followed, skipped, and keyword-filtered candidate jobs
- fail-fast stop when ScrapeOps is out of credits
- sanitized failure strings that do not leak the ScrapeOps key

Important behavior change:

- the old default `company_site_max_jobs_per_site=10` recall cap is no longer the default runtime behavior
- all locally relevant candidate jobs are followed unless an explicit policy or emergency ceiling applies

### 6. Source Validation And Pre-Run Estimation

Updated:

- [backend/application/services.py](../backend/application/services.py)
- [backend/api/server.py](../backend/api/server.py)

`/workspace-builder/source-validation` now returns:

- company-site scope planning
- company-site policy snapshot
- active admin domain policy count
- runner-credit estimate ranges
- ScrapeOps account state
- run overrides derived from effective admin policy

Users see runner-credit estimates, not money estimates.

### 7. Scheduled Reconciliation And Alerts

Updated [backend/worker/service.py](../backend/worker/service.py).

The worker now periodically calls ScrapeOps maintenance. The backend records reconciliation snapshots and emits alert events when:

- ScrapeOps is out of credits
- remaining credits fall below the configured threshold
- internal native-credit accounting differs from remote ScrapeOps usage beyond the configured discrepancy threshold
- the reconciliation cycle itself fails

This is in-app event-based alerting. It does not send external email or Slack notifications.

## API Changes

Updated [backend/api/server.py](../backend/api/server.py).

Added or extended:

- `GET /scrapeops/usage`
  - user-scoped usage summary
- `GET /admin/scrapeops/usage`
  - admin dashboard payload with usage, policy, usage series, reconciliation, reconciliation history, and alerts
- `GET /admin/scrapeops/policy`
  - admin-only current ScrapeOps policy
- `PUT /admin/scrapeops/policy`
  - admin-only policy update
- `POST /admin/scrapeops/reconciliation/run`
  - admin-only forced reconciliation snapshot and alert evaluation
- `GET /billing/subscription`
  - includes ScrapeOps policy and usage context
- run customer view payload
  - includes ScrapeOps run usage summary
- source validation response
  - includes company-site policy and runner-credit estimate data

All admin ScrapeOps routes require admin access.

## Frontend Implementation

### 1. User-Facing Usage And Budget Visibility

Updated:

- [frontend/src/pages/SettingsPage.jsx](../frontend/src/pages/SettingsPage.jsx)
- [frontend/src/pages/WorkspacesPage.jsx](../frontend/src/pages/WorkspacesPage.jsx)
- [frontend/src/pages/RunDetailPage.jsx](../frontend/src/pages/RunDetailPage.jsx)

Delivered user-facing behavior:

- Settings shows runner-credit allowance and company-site policy limits
- Workspace validation shows pre-run runner-credit estimate context
- Run detail shows ScrapeOps usage/progress context:
  - runner credits consumed
  - candidate jobs discovered/followed/skipped
  - keyword-filtered jobs
  - locality mode
  - access method
  - recent failures

### 2. Admin-Only ScrapeOps Dashboard

Updated [frontend/src/pages/AdminScrapeOpsPage.jsx](../frontend/src/pages/AdminScrapeOpsPage.jsx).

Added route in [frontend/src/App.jsx](../frontend/src/App.jsx).

Updated [frontend/src/pages/AdminPage.jsx](../frontend/src/pages/AdminPage.jsx) to link to it.

Dashboard capabilities now include:

- account health summary
- remote account used/remaining credit visibility
- internal runner/native credit totals
- billed vs failed request summary
- reconciliation delta
- daily usage chart
- alert list and alert trend
- reconciliation history
- policy JSON editor
- forced reconciliation action
- filters by user, workspace, run, usage date window, and reconciliation date
- breakdown tables for request mode, domain, and run
- run-level `jobs_found` and `runner_credits_per_job`
- raw or tabular remote domain stats from ScrapeOps

Access protection:

- route is wrapped in `RequireAdminRoute`
- non-admin users are redirected away
- admin navigation entry is only visible to admin users
- backend routes also enforce admin access

## PRD Requirement Coverage

### Fully Delivered

- Per-user ScrapeOps usage attribution tied to authenticated identity
- User-scoped usage endpoint
- Admin aggregate usage endpoint
- Runner-credit budgeting model
- Company-site local-market-first scope planning
- Strict and soft locality modes
- Removal of the default silent low jobs-per-site cap
- Pre-run runner-credit estimation in runner credits
- Plan-aware companies-per-run and runner-credit-per-run limits
- User-id-based admin overrides for larger/custom plans
- Fail-fast ScrapeOps out-of-credit handling
- Secret redaction in surfaced ScrapeOps failures
- Request-mode and domain telemetry
- Admin-only ScrapeOps dashboard
- Policy version stamping in progress and policy payloads
- Reconciliation against ScrapeOps account usage
- Domain-specific optimization strategy
- Recall-vs-cost measurement at run level
- Admin override behavior for locality special cases
- Standalone admin policy editing surface
- Automated in-app reconciliation snapshots and alert events
- Historical usage and reconciliation trend views

### Partially Delivered

No PRD item remains partially delivered after this pass.

### Not Delivered In This Pass

No requested PRD item remains undelivered after this pass.

The remaining limitations are operational rather than missing PRD scope:

- Alerts are stored as admin dashboard events; they are not sent to email, Slack, or another external notification channel.
- The policy editor is a JSON editor with backend normalization; it is not yet a field-by-field form editor.
- Remote ScrapeOps usage reconciliation depends on the provider account usage endpoint availability.

## Testing And Verification

Verification completed:

- `python -m py_compile backend/integrations/scrapeops.py backend/config/scrapeops_admin_policy.py backend/connectors/company_career_sites.py backend/application/services.py backend/api/server.py backend/adapters/stage_adapters.py backend/capabilities/tailored_documents/runtime.py backend/worker/service.py backend/repositories/file_backed.py backend/repositories/sqlite_backed.py backend/bootstrap.py`
- `python -m unittest tests.test_company_career_discovery tests.test_backend_api tests.test_stage_adapters`
- `npm --prefix frontend run build`

Additional targeted test coverage was added in:

- [tests/test_backend_api.py](../tests/test_backend_api.py)
- [tests/test_company_career_discovery.py](../tests/test_company_career_discovery.py)

The test work covered:

- source validation policy and estimate responses
- subscription ScrapeOps usage summary payloads
- run customer-view ScrapeOps usage payloads
- admin ScrapeOps policy save/load
- admin dashboard usage, policy, trend, reconciliation, and alert payloads
- forced reconciliation alert generation
- locality-aware scope planning
- domain-policy request-mode and country overrides
- removal of the legacy implicit `10` jobs-per-site default
- admin/backend compatibility for usage reporting

Frontend build passed. Vite still reports pre-existing chunk-size warnings.

## Key Engineering Decisions

### 1. Product-Facing Credits Use Runner Credits

The implementation separates:

- native ScrapeOps credit estimates
- runner credits used for product policy, budgeting, and UI

This keeps user messaging stable even if the external provider model changes later.

### 2. Cost Control Moved Upstream

Instead of suppressing recall with a silent low cap, cost control is now enforced through:

- locality trimming
- company-count limits
- runner-credit budgets
- request-mode escalation
- domain-specific policy
- emergency ceilings

This is a better policy boundary than stopping after 10 jobs without telling the user.

### 3. Admin And User Surfaces Were Split

Regular users get:

- personal allowance visibility
- pre-run estimate context
- run-level progress/usage context

Operators get:

- account-level usage
- policy editing
- reconciliation
- alerts
- domain and mode breakdowns
- trend views

## Remaining Risks And Follow-Up Opportunities

1. The first production domain-policy set still needs operational tuning based on real ScrapeOps success rates.
2. The admin policy editor is powerful but low-level; a safer form-based editor would reduce operator mistakes.
3. External alert delivery would be useful if ScrapeOps credits are business-critical.
4. Local-market confidence heuristics are stronger than before, but third-party career sites can still expose weak URL/text locality signals.
5. Reconciliation can differ from ScrapeOps billing if provider credit accounting changes or if requests happen outside this application.

## Conclusion

This implementation changes the ScrapeOps company-site system from an expensive black box into a governed acquisition layer with:

- scoped locality behavior
- per-user attribution
- plan-aware controls
- user-id overrides
- domain-specific optimization
- credit budgeting
- operator reconciliation
- in-app alerts
- admin-only monitoring and policy management

The PRD outcome is now fully delivered in-app: ScrapeOps usage is visible, attributable, bounded, configurable, and operationally diagnosable while preserving the ScrapeOps-only sourcing direction.
