# AI Document Catalog - 2026-05-27

**Created date:** 2026-05-27  
**Catalog scope:** Project-owned Markdown documents that contain PRDs, user stories, epics, issue drafts, implementation reports, strategy reports, or product/technical specs.  
**Primary AI entry folder:** `docs/reports/`

This catalog intentionally leaves the original files in place. Moving source PRDs and reports would risk breaking existing links. Future AI agents should start here, then open the linked source document.

## Current Reports Folder

| Dated title | Type | Source path | Notes |
|---|---|---|---|
| Runr Reports Hub - 2026-05-27 | Hub README | [README.md](./README.md) | Entry point and folder rules. |
| AI Document Catalog - 2026-05-27 | Catalog | [ai_document_catalog_2026-05-27.md](./ai_document_catalog_2026-05-27.md) | This file. |
| Runr Scraping P1 Work And Efficiency Report - 2026-05-27 | Implementation and efficiency report | [runr_scraping_p1_work_and_efficiency_report_2026-05-27.md](./runr_scraping_p1_work_and_efficiency_report_2026-05-27.md) | Summary of the scraping work completed in the 2026-05-27 Codex session. |
| Worker Architecture & Reliability Audit - 2026-05-27 | Technical audit and implementation report | [worker_architecture_reliability_audit_2026-05-27.md](./worker_architecture_reliability_audit_2026-05-27.md) | Worker architecture, failure analysis, scale/database assessment, and structured worker logging implementation. |

## Source PRDs And User Stories

| Dated catalog title | Source file | Type | What it contains | AI usage note |
|---|---|---|---|---|
| Product Requirements Document - cataloged 2026-05-27 | [../prd/product_requirements_document.md](../prd/product_requirements_document.md) | PRD | Prioritized product requirements with acceptance criteria. | Use for general product backlog and workspace-level requirements. |
| Application Remediation PRD - cataloged 2026-05-27 | [../prd/application_remediation_parallel_workstreams_prd.md](../prd/application_remediation_parallel_workstreams_prd.md) | PRD and workstream plan | User stories, requirements, risks, and recommended delivery sequence for remediation streams. | Use when touching broad app reliability, workflow, or user-facing remediation work. |
| ScrapeOps Usage And Local-Market Sourcing PRD - cataloged 2026-05-27 | [../prd/scrapeops_usage_and_local_market_sourcing_prd.md](../prd/scrapeops_usage_and_local_market_sourcing_prd.md) | PRD | ScrapeOps usage governance, local-market sourcing, plan-aware limits, and acceptance criteria. | Use as the source PRD for ScrapeOps policy, usage attribution, budgets, and sourcing behavior. |
| Referral, Tracker, Workspace, Documents, And ATS Gate PRD - cataloged 2026-05-27 | [../prd/referral_tracker_workspace_prd.md](../prd/referral_tracker_workspace_prd.md) | PRD and epic pack | Referral import, tracker, Gmail, workspace navigation, documents, and ATS gate user stories. | Use for referral/tracker/document/ATS gate scope. |
| Referral Tracker Confidence Pass PRD - cataloged 2026-05-27 | [../prd/referral_tracker_confidence_pass_prd.md](../prd/referral_tracker_confidence_pass_prd.md) | Verification PRD | Follow-on confidence pass, coverage matrix, verification requirements, and hardening stories. | Use when validating the referral tracker PRD implementation. |
| Workspace Run Progress Visibility PRD - cataloged 2026-05-27 | [../prd/workspace_run_progress_visibility_prd.md](../prd/workspace_run_progress_visibility_prd.md) | PRD | User stories and acceptance criteria for live run progress visibility. | Use when changing progress snapshots, long-running run feedback, or acquisition telemetry. |
| Workspace Automation Navigation Issue Drafts - cataloged 2026-05-27 | [../prd/workspace_automation_nav_issue_drafts.md](../prd/workspace_automation_nav_issue_drafts.md) | Epic/issue draft pack | Multiple issue drafts with acceptance criteria for workspace automation navigation. | Use as implementation-ticket source material, not as a canonical PRD. |
| Phase 0 Contract Alignment - cataloged 2026-05-27 | [../prd/phase0_contract_alignment.md](../prd/phase0_contract_alignment.md) | Alignment record | Concrete outputs of Phase 0 from the remediation PRD. | Use for contract and domain alignment context. |
| PRD Folder README - cataloged 2026-05-27 | [../prd/README.md](../prd/README.md) | PRD index | Older PRD folder index. | Superseded as the primary AI entry point by this catalog, but still useful for historical context. |

## Source Reports, Specs, And Deliverables

| Dated catalog title | Source file | Type | What it contains | AI usage note |
|---|---|---|---|---|
| Runr Scraping Strategy Report - 2026-05-26 | [../scraping_strategy_report_2026-05-26.md](../scraping_strategy_report_2026-05-26.md) | Strategy report | Scraping source inventory, ScrapeOps cost model, live probe limitations, and recommended acquisition order. | Use before changing scraping architecture, proxy strategy, or source scheduling. |
| ScrapeOps Usage And Admin Dashboard Implementation Report - cataloged 2026-05-27 | [../scrapeops_usage_and_admin_dashboard_implementation_report.md](../scrapeops_usage_and_admin_dashboard_implementation_report.md) | Implementation report | Delivered ScrapeOps usage/admin dashboard behavior, verification, and operational risks. | Use before modifying ScrapeOps admin, policy, budget, or dashboard features. |
| Runr Analytics Spec - cataloged 2026-05-27 | [../runr-analytics-spec.md](../runr-analytics-spec.md) | Technical/product spec | Analytics data sources, event ideas, dashboard metrics, and tracking considerations. | Use for analytics schema, event, and reporting work. |
| Runr Monetization Deliverables - cataloged 2026-05-27 | [../runr-monetization-deliverables.md](../runr-monetization-deliverables.md) | Deliverables bundle | Large combined monetization deliverables and code/reference material. | Large file. Open only when monetization context is needed. |

## Root Orientation Documents

| Dated catalog title | Source file | Type | What it contains | AI usage note |
|---|---|---|---|---|
| Repository README - cataloged 2026-05-27 | [../../README.md](../../README.md) | Setup/orientation | General repository setup and run instructions. | Use for local setup and high-level app orientation. |
| Architecture Overview - cataloged 2026-05-27 | [../../ARCHITECTURE.md](../../ARCHITECTURE.md) | Architecture doc | System architecture context. | Use before cross-cutting backend/frontend changes. |
| Clerk Setup - cataloged 2026-05-27 | [../../CLERK_SETUP.md](../../CLERK_SETUP.md) | Setup doc | Clerk authentication setup. | Use for auth configuration work. |

## Search Method Used

The catalog was built from:

```text
rg --files -g "*.md" -g "!node_modules/**" -g "!test CV/**" -g "!test-CV/**"
rg -n -i "\bprd\b|user stor|epic|report|deliverable|requirement|acceptance criteria" docs README.md ARCHITECTURE.md CLERK_SETUP.md
```

## Exclusions

- `node_modules/**`: dependency documentation, not project planning material.
- `test CV/**` and `test-CV/**`: sample CV/template research notes, not canonical product documentation.
- Generated runtime files and user-specific artifacts.
