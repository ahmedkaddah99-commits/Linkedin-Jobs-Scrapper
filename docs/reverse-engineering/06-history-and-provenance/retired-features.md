> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Retired features: admin analytics dashboard

This is a secondary doc for WS-11. The primary doc is [repository-artifacts.md](repository-artifacts.md) and the gap registry is [known-gaps.md](known-gaps.md).

**Status: RETIRED/HISTORICAL. Do not restore it.** No workstream documents this dashboard as a feature. This file records only the decision, the removal, the residue that remains and the historical records.

## 1. Owner decision

| Date | Decision | Source |
|---|---|---|
| 2026-09-13 | Admin analytics are not computed on Render. No admin dashboard is planned anywhere for now. | Provenance header of `evidence-package-2026-09-13/{subsystem-allocation,contradictions-and-unknowns,recommended-documentation-tree}.md`; tree §Changes: `05-subsystems/admin-analytics-dashboard.md` removed |
| (supporting) | `render.yaml` comments at L82 and L199 say "Acquisition runs on the VPS, never on Render". | Delta audit row 31 |

Consequence: any doc, branch or stash that describes an admin analytics, admin operations or admin job-import console is historical only.

## 2. What was retired

Before the removal, the codebase had these admin-only surfaces:
- backend acquisition analytics computation (`backend/acquisition/analytics.py`) and product analytics (`backend/application/product_analytics.py`);
- admin route modules for acquisition, enrichment and job import;
- the admin job-import application service;
- enrichment operations (`backend/enrichment/operations.py`);
- an admin operations shell and router in the frontend;
- admin pages for acquisition, acquisition analytics, events, ScrapeOps and the main admin page;
- the customer-facing `DashboardPage.jsx` and `AcquisitionOperationsPage.jsx`.

The in-app routes were under `/admin/*` (for example `/admin/acquisition/*`, `/admin/events`, `/admin/job-import`) plus the customer `/dashboard`.

## 3. Removal record

| Item | Value (verified with `git show`/`git log`) |
|---|---|
| Removal commit | `dd47acf9` 2026-09-10 "Complete acquisition delivery and remove admin surfaces" |
| Size | 64 files changed, 1,219 insertions(+), 13,847 deletions(−) (`git show --stat dd47acf9`) |
| Merge into the line | `550ee00a` 2026-09-10 "Merge acquisition delivery and admin surface removal". Parents: `848408f3`, `dd47acf9`. Both are ancestors of `58a96674`. |
| Notable non-deletions | `backend/api/routes/admin.py` +1/−164; `backend/api/server.py` +0/−648; `frontend/src/App.jsx` +2/−21 (`/dashboard` now `<Navigate replace to="/jobs" />`, `frontend/src/App.jsx:229`) |
| Added guard test | `tests/test_customer_route_surface.py` (asserts that no `admin.dashboard/users/tokens/secrets/analytics` route is registered, L9–13) |
| Same commit, unrelated to admin | acquisition delivery: `deploy/run-acquisition-cycle.sh`, `deploy/systemd/runr-acquisition-cycle.{service,timer}`, `scripts/publish_producer_states.py`, `tests/test_producer_state_delivery.py` (owned by WS-7/WS-3) |

### Complete deleted-file list (27; `git show --diff-filter=D --name-only dd47acf9`)

None of these paths exists at `58a96674`.

| # | Path (REMOVED) | Area |
|---|---|---|
| 1 | `backend/acquisition/analytics.py` | acquisition analytics computation |
| 2 | `backend/api/routes/acquisition_admin.py` | admin API |
| 3 | `backend/api/routes/enrichment_admin.py` | admin API |
| 4 | `backend/api/routes/job_import_admin.py` | admin API |
| 5 | `backend/application/admin_job_import.py` | admin service |
| 6 | `backend/application/product_analytics.py` | product analytics computation |
| 7 | `backend/enrichment/operations.py` | enrichment operations (1,370 lines; omitted by the evidence package, N-4) |
| 8 | `frontend/src/admin/AdminOperationsRouter.jsx` | admin UI |
| 9 | `frontend/src/admin/AdminPlatformPages.jsx` | admin UI |
| 10 | `frontend/src/admin/adminOperations.css` | admin UI |
| 11 | `frontend/src/admin/adminRoutes.js` | admin UI |
| 12 | `frontend/src/admin/adminRoutes.test.js` | admin UI test |
| 13 | `frontend/src/components/admin/AdminOperationsShell.jsx` | admin UI |
| 14 | `frontend/src/components/admin/AdminPrimitives.jsx` | admin UI |
| 15 | `frontend/src/lib/acquisitionOperations.js` | admin UI lib (N-4) |
| 16 | `frontend/src/lib/acquisitionOperations.test.js` | admin UI lib test (N-4) |
| 17 | `frontend/src/pages/AcquisitionOperationsPage.jsx` | operations page (680 lines, N-4) |
| 18 | `frontend/src/pages/AdminAcquisitionAnalyticsPage.jsx` | admin page |
| 19 | `frontend/src/pages/AdminAcquisitionPage.jsx` | admin page |
| 20 | `frontend/src/pages/AdminEventsPage.jsx` | admin page |
| 21 | `frontend/src/pages/AdminPage.jsx` | admin page |
| 22 | `frontend/src/pages/AdminScrapeOpsPage.jsx` | admin page |
| 23 | `frontend/src/pages/DashboardPage.jsx` | customer dashboard page (976 lines, N-4); `/dashboard` redirects to `/jobs` |
| 24 | `tests/test_acquisition_analytics.py` | test |
| 25 | `tests/test_admin_job_import_dashboard.py` | test |
| 26 | `tests/test_enrichment_operations.py` | test (deleted by `dd47acf9` itself, N-4) |
| 27 | `tests/test_product_analytics.py` | test |

## 4. Residue at baseline (C7 with N-1 applied)

| ID | Residue | Evidence (file:line at `58a96674`) | Classification | Owner WS | Owner doc |
|---|---|---|---|---|---|
| C7(a) | Unregistered handler bodies in `backend/api/routes/admin.py`: `dashboard` L102 (calls `_dashboard_payload` at L105), `users` L113/127/132, `tokens` L154, `secrets` L177/196, POST `analytics/events` L239, plus POST/PUT/DELETE `users`/`secrets` branches (L346, L351, L363, L430) | `register_routes` L23–33 registers only `admin.billing.plans`, `admin.auth.me`, `admin.billing`, `admin.scrapeops`, `admin.settings`, `admin.webhooks.{clerk,creem}`, `admin.billing.post`, `admin.settings.put`, `admin.account.delete` | RETIRED-RESIDUE (dead code, 404) | WS-1 | `01-architecture/backend-api.md` |
| C7(a) / N-1 | `backend/api/server.py` `_dashboard_payload` L7358 → `_dashboard_analytics_payload` L7143 (call at L7366). The only caller is the dead `admin.py:105`. | `git grep -n _dashboard_payload 58a96674 -- backend` | RETIRED-RESIDUE | WS-1 | `01-architecture/backend-api.md` |
| C7(b) | `frontend/e2e/admin-operations-console.spec.ts` mocks and targets the deleted `/admin/acquisition/*` routes (from L15) | spec L1–25 | RETIRED-RESIDUE (stale e2e) | WS-8 | `01-architecture/frontend-app.md` |
| C7(c) | Migration `055_acquisition_analytics_indexes` | `backend/repositories/sqlite_migrations.py:3516` | RETAINED BY DESIGN: migrations are append-only, so do not delete it | WS-5 | `03-data/schema-and-migrations.md` |
| C7(d) | `backend/config/scrapeops_admin_policy.py`, still imported by `backend/application/services.py:29–32` and used at L685–700 and L1724 | — | Live code with an "admin" name. Whether it is residue is for WS-5/WS-4 to decide. | WS-5 (consumer WS-4) | `03-data/schema-and-migrations.md` / `05-subsystems/personalized-jobs-and-customer-app-services.md` |
| C7(e) | Admin-dashboard docs (§6 below) | — | HISTORICAL | WS-11 | this file; [repository-artifacts.md](repository-artifacts.md) |
| N-1 | Frontend emitters: `frontend/src/lib/analytics.js:125` and `frontend/src/lib/api.js:267` POST `/analytics/events` fire-and-forget and swallow errors. The endpoint is not registered, so every call gets a 404. | The code comment at `analytics.js:124` reads "Analytics must never delay or fail the user action" | RETIRED-RESIDUE (dead client call) | WS-8 | `01-architecture/frontend-app.md` |

**Not residue. Do not remove these as part of the retirement:**
- **N-10:** the registered prefix `admin.scrapeops` (`admin.py:27`) serves the customer endpoint `scrapeops/usage` (`admin.py:82`). It is not an admin-only surface.
- **Worker-side analytics:** `backend/adapters/stage_adapters.py` (around L143–161) uses `analytics_store.emit_event` and `record_scrapeops_usage` to write `analytics_events`. This is live and separate from the dashboard (WS-2 / WS-5).
- **The open question U7** (delete the dead endpoint and emitter, or re-register them) belongs to the owner. See [known-gaps.md](known-gaps.md).

## 5. Retired branches, commits and stash (clean-slate report §7)

| Record | Detail | Relation to baseline | Disposition |
|---|---|---|---|
| `c62e2637` | 2026-08-16 "fix: expose LinkedIn company enrichment in admin". Contained in `feature/admin-analytics-final-production` and `codex/master-linkedin-jobs-url`. | Not an ancestor of `58a96674` | HISTORICAL retired admin work. Kept in `ARCH\git-preservation.bundle`. Not restored. |
| `ce3718b0` | 2026-09-08 merge at the tip of `feature/admin-analytics-final-production` | Not an ancestor; 16 ahead / 179 behind | HISTORICAL. The branch is reference only (`UNMERGED (feature/admin-analytics-final-production @ ce3718b0)`). Non-admin commits on it (`0d7f2b5c`) are covered by T03/T04/T05, not by restoring the admin work. |
| stash@{1} `6de233dd` | Retired admin work. Its untracked files were identical inside stash@{2}. | — | Exported as a patch plus `stashes-0-1-3-4.bundle`, then dropped 2026-09-14T00:40Z (clean-slate §4, §8) |
| `origin/feature/admin-operations-console` | Old admin operations console branch | Ancestor, 0 ahead / 243 behind (N-8) | HISTORICAL |
| Retained worktrees with admin names (`runr-admin-job-import-dashboard`, `runr-opencode-a-remove-admin`, …) | Local checkouts | — | Retired under T14. Only the names are historical. |

The branch `temp/opencode-a-remove-admin` / worktree `runr-opencode-a-remove-admin` was the planned removal lane. `docs/OPENCODE_C_HANDOFF.md` L18 and L127 record that it had "no commits yet". The removal actually landed through `dd47acf9`.

## 6. Stale admin-dashboard docs to treat as HISTORICAL

These docs have not been edited. This table is a classification only; see the full corpus table in [repository-artifacts.md](repository-artifacts.md).

| Path (verified present at baseline) | Admin content | Classification |
|---|---|---|
| `docs/scrapeops_usage_and_admin_dashboard_implementation_report.md` (2026-05-25, 410 lines) | Whole doc: "follow-up admin-only ScrapeOps operations dashboard"; frontend implementation sections | HISTORICAL. Customer ScrapeOps usage parts may still describe `scrapeops/usage` (N-10); check against WS-6/WS-1 before relying on them. |
| `docs/admin_job_import_data_flow.md` (2026-08-07, 82 lines) | Whole doc: flow from `frontend /admin/job-import` to protected API; the service `backend/application/admin_job_import.py` is deleted | HISTORICAL (describes removed code) |
| `docs/admin_operations_console_parity.md` (2026-08-13, 15 lines) | Whole doc: checklist for `AdminOperationsShell` and admin routes (deleted) | HISTORICAL |
| `docs/RC_C_HANDOFF.md` (647 lines) | L215–217 only, step 5: "Use the admin analytics page only with an authenticated staging origin…" | Section HISTORICAL; the rest is classified in the primary doc |
| `docs/OPENCODE_F_JOB_COMPLETENESS_HANDOFF.md` (224 lines) | L164 "The deleted admin dashboard is not a dependency", L219 "A (admin removal)" | Mentions only. They confirm the removal; nothing to retire. |
| `docs/runr-monetization-deliverables.md` (25,361 lines) | Verbatim code snapshot including `AdminPage`/`AdminEventsPage` routes (around L13371–13487) and the admin analytics snapshot (around L8156). The header already says "historical rollout snapshot". | HISTORICAL (whole doc) |
| `docs/collection-controls.md` (2026-08-12) | "Admin source imports accept a server-validated `scope`…" (admin import surface) | HISTORICAL/PARTIAL. WS-3 must check whether the `scope` validation still exists without the admin route. |
| `docs/RC_CURRENT_STATUS_AND_NEXT_STEPS.md` | L491 lists `backend/application/admin_job_import.py` (deleted) | Section HISTORICAL |

## 7. Implementation status

| Capability | Classification |
|---|---|
| Admin analytics dashboard (UI + API + computation) | RETIRED/HISTORICAL (static: the 27 files above are absent at `58a96674`; no admin analytics route in `admin.py` `register_routes` L23–33) |
| Customer `/dashboard` page | RETIRED/HISTORICAL (static: `frontend/src/App.jsx:229` redirects to `/jobs`) |
| `POST /analytics/events`, `GET /dashboard` API | RETIRED/HISTORICAL. The bodies are dead residue (static: no matching registration; guard test `tests/test_customer_route_surface.py`). |
| Worker-side `analytics_events` writes | Not retired; out of scope here (WS-2/WS-5) |

**Deployment evidence (documentary only):** no production record claims that an admin dashboard is deployed after `550ee00a`. `docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md` (WS-7) records Render `5dfdd106`, which descends from `550ee00a`. LIVE PRODUCTION = UNKNOWN.

**Safe verification commands (not executed in Phase 2):**
- `git show --diff-filter=D --name-only dd47acf9`
- `node scripts/run-python.cjs -m pytest -q tests/test_customer_route_surface.py`

## Agent context and remaining work

**(a) Context packet**
- **Required reading:** this file; `backend/api/routes/admin.py` L23–33.
- **Allowed:** documenting residue.
- **Tests:** `tests/test_customer_route_surface.py`.
- **Prohibited:** restoring any §3 path; cherry-picking `c62e2637`/`ce3718b0` admin content; re-registering admin routes without an owner decision; deleting migration 055.

**(b) Registry row:** covered by the WS-11 row in the primary doc.

**(c) Gaps and candidates**
- **C7(a)–(e):** carried; see [known-gaps.md](known-gaps.md).
- **U7 (N-1):** carried.
- **WS11-G1:** `docs/collection-controls.md` describes an admin import `scope` contract whose admin route was removed. Whether the contract survives is unverified (WS-3).
- **Cleanup-ticket candidate (owner decision required):** delete the dead `admin.py` bodies and `server.py` dashboard helpers, the stale e2e spec and the frontend emitter.
