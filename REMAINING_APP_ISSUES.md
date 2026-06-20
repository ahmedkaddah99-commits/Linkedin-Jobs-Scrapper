# Runr App Issue Tracker

Use this file as the main source of truth for Runr app issues, including open issues, resolved issues, screenshots, reproduction notes, and resolution history.

## Table of Contents

[Go up](#table-of-contents)

- [Templates](#templates)
  - [Open Issue Template](#open-issue-template)
  - [Resolved Issue Template](#resolved-issue-template)
- [Resolved Issues](#resolved-issues)
  - [Resolved Issue: Reset Error / Tool Keeps Refreshing](#resolved-issue-reset-error--tool-keeps-refreshing)
  - [Resolved Issue: Dashboard Takes 25-30 Seconds to Load](#resolved-issue-dashboard-takes-25-30-seconds-to-load)
  - [Resolved Issue: Quick Apply Requires a Configured Workspace](#resolved-issue-quick-apply-requires-a-configured-workspace)
  - [Resolved Issue: System-Created Workspaces Should Not Appear as User Workspaces](#resolved-issue-system-created-workspaces-should-not-appear-as-user-workspaces)
  - [Resolved Issue: Missing Workspace Delete Button](#resolved-issue-missing-workspace-delete-button)
  - [Resolved Issue: Missing Workspace QA Checklist](#resolved-issue-missing-workspace-qa-checklist)
  - [Resolved Issue: Runs QA Checklist Needed for Filtering Quality](#resolved-issue-runs-qa-checklist-needed-for-filtering-quality)
  - [Resolved Issue: ATS QA Testing Is Unclear and May Not Guarantee ATS Passing](#resolved-issue-ats-qa-testing-is-unclear-and-may-not-guarantee-ats-passing)
  - [Resolved Issue: Application Tracker Takes Too Long to Load](#resolved-issue-application-tracker-takes-too-long-to-load)
- [Issues Not Yet Resolved](#issues-not-yet-resolved)

## Templates

[Go up](#table-of-contents)

Copy the rendered block below when adding a new issue or moving an issue to resolved.

Standard rule for all new issues: add a `[Go up](#table-of-contents)` link directly below every new section heading and issue heading.

Standard sorting rule: keep issues ordered from smallest to largest by original issue number within each issue section.

---

### Open Issue Template

[Go up](#table-of-contents)

#### Issue: Short Title

[Go up](#table-of-contents)

**Status:** Open

**Priority:** High / Medium / Low

**Area:** Frontend / Backend / Billing / Auth / Deployment / Data / Other

**Environment:** Local / Render / Mobile / Desktop / Other

**URL or screen:** Where this happens

**What happens:**

Describe the current behavior.

**What should happen:**

Describe the expected behavior.

**Steps to reproduce:**

1. Step one
2. Step two
3. Step three

**Screenshots:**

![Screenshot 1](screenshots/issue-name-1.png)

![Screenshot 2](screenshots/issue-name-2.png)

**Notes / clues:**

Errors, logs, suspected cause, related commits, or other clues.

**Fix idea:**

Optional possible solution.

---

### Resolved Issue Template

[Go up](#table-of-contents)

#### Resolved Issue: Short Title

[Go up](#table-of-contents)

**Original issue:** Link to the original issue section or issue number.

**Status:** Resolved

**Priority at time of fix:** Critical / High / Medium / Low

**Area:** Frontend / Backend / Billing / Auth / Deployment / Data / Other

**Environment fixed in:** Local / Render / Mobile / Desktop / Other

**Resolved date:** YYYY-MM-DD

**Resolved by:** Name / commit / PR / branch

**What was broken:**

Describe the original user-facing problem.

**How it was resolved:**

Describe the fix that was shipped.

**Verification:**

1. Step used to verify the fix
2. Step used to verify the fix
3. Step used to verify the fix

**Screenshots / evidence:**

![Resolved screenshot](screenshots/resolved-issue-name.png)

**Remaining follow-up:**

List any non-blocking cleanup, monitoring, or related work that remains.

---

## Resolved Issues

[Go up](#table-of-contents)

<!-- Move fixed issues here and fill out the resolved issue template. -->

#### Resolved Issue: Reset Error / Tool Keeps Refreshing

[Go up](#table-of-contents)

**Original issue:** Issue #1

**Status:** Resolved

**Priority at time of fix:** Critical

**Area:** Frontend / Auth / Deployment

**Environment fixed in:** Local frontend build; ready for Render deployment

**Resolved date:** 2026-06-20

**Resolved by:** Codex local changes

**What was broken:**

The frontend treated every authenticated API session check as a blocking connection state. When `/auth/me` re-ran or briefly failed after a user was already authenticated, the session provider cleared the current user and changed status away from `connected`. `App.jsx` then replaced the current route with the `Connecting to Runr API` panel, unmounting workspace screens and deleting unsaved in-memory work.

**How it was resolved:**

Session checks now preserve the last successful authenticated session. Once a backend session has succeeded, later refreshes keep the app mounted while `/auth/me` runs in the background, and transient refresh failures keep the last user/session instead of clearing the route. The app route gate now treats an existing authenticated user as enough to keep rendering the current workspace screen during reconnect/session checks.

**Verification:**

1. Ran `node --test frontend/src/lib/sessionState.test.js`; verified authenticated sessions stay mounted during refresh and are preserved after refresh failure.
2. Ran `npm --prefix frontend run check`; ESLint and production Vite build passed.
3. Reviewed the auth/bootstrap flow in `frontend/src/context/SessionContext.jsx` and `frontend/src/App.jsx` to confirm the connection panel is only shown before any authenticated session exists.

**Screenshots / evidence:**

No screenshot captured locally.

**Remaining follow-up:**

Deploy to Render and confirm `https://app.userunr.com/` no longer switches between `Connecting to Runr API` and workspace screens during normal authenticated use.

---

#### Resolved Issue: Dashboard Takes 25-30 Seconds to Load

[Go up](#table-of-contents)

**Original issue:** Issue #2

**Status:** Resolved

**Priority at time of fix:** High

**Area:** Frontend / Data Loading

**Environment fixed in:** Local frontend build; ready for Render deployment

**Resolved date:** 2026-06-20

**Resolved by:** Codex local changes

**What was broken:**

The dashboard treated the full `/dashboard` analytics payload as a first-render requirement. Slow analytics/data collection caused the whole dashboard to show a full-page skeleton instead of a usable page shell.

**How it was resolved:**

The dashboard now renders the page shell, navigation actions, action plan fallback, and empty chart states immediately. The slow dashboard analytics request runs in the background with a scoped loading notice, so the full page is no longer blocked by the initial payload.

**Verification:**

1. Ran `npm --prefix frontend run check`; ESLint and production Vite build passed.
2. Reviewed `frontend/src/pages/DashboardPage.jsx` to confirm `loading && !data` no longer returns the full `DashboardSkeleton`.
3. Confirmed the dashboard still shows clear loading feedback while `/dashboard` is pending.

**Screenshots / evidence:**

No screenshot captured locally.

**Remaining follow-up:**

Deploy to Render and measure real production `/dashboard` response time separately; this fix makes the page usable while slow analytics are still loading.

---

#### Resolved Issue: Quick Apply Requires a Configured Workspace

[Go up](#table-of-contents)

**Original issue:** Issue #3

**Status:** Resolved

**Priority at time of fix:** High

**Area:** Frontend / Backend / Product Flow

**Environment fixed in:** Local

**Resolved date:** 2026-06-20

**Resolved by:** Codex local changes

**What was broken:**

Quick Apply rendered a blocking empty state unless at least one eligible configured workspace existed. The API also required `workspace_id`, so a new user with no configured workspace could not submit a quick application.

**How it was resolved:**

Quick Apply now initializes and renders without a selected workspace. When no workspace is selected, the submit payload omits `workspace_id`; the API creates or reuses a hidden per-user internal Quick Apply workspace and runs the existing quick-apply workflow against it.

**Verification:**

1. Ran `npm --prefix frontend run check`.
2. Ran `python -m py_compile backend\api\server.py backend\api\routes\workspace.py tests\test_backend_api.py`.
3. Ran the targeted omitted-`workspace_id` unittest with local Turso env cleared; it passed.

**Screenshots / evidence:**

Not captured.

**Remaining follow-up:**

Verify the deployed Render environment after release.

#### Resolved Issue: System-Created Workspaces Should Not Appear as User Workspaces

[Go up](#table-of-contents)

**Original issue:** Issue #4

**Status:** Resolved

**Priority at time of fix:** Medium

**Area:** Frontend / Data / Workspace Management

**Environment fixed in:** Local

**Resolved date:** 2026-06-20

**Resolved by:** Codex local changes

**What was broken:**

The Workspaces page treated internal/system-created records as normal user workspaces, including legacy fixture names such as `Builder Workspace`, `API Workspace`, and `API Custom Workspace`.

**How it was resolved:**

The Workspaces page now filters the user-facing list to exclude records marked with existing internal/system signals (`workspace_type`, metadata flags, system creator, quick-apply builder mode) and the known legacy fixture names. The internal Quick Apply workspace is created with `workspace_type: internal` and metadata `internal: true`.

**Verification:**

1. Ran `npm --prefix frontend run check`.
2. Confirmed backend syntax with `python -m py_compile backend\api\server.py backend\api\routes\workspace.py tests\test_backend_api.py`.
3. Confirmed the new omitted-workspace Quick Apply API path creates an internal workspace.

**Screenshots / evidence:**

Not captured.

**Remaining follow-up:**

Verify against deployed data to catch any additional legacy internal workspace names not present in the issue notes.

#### Resolved Issue: Missing Workspace Delete Button

[Go up](#table-of-contents)

**Original issue:** Issue #5

**Status:** Resolved

**Priority at time of fix:** Medium

**Area:** Frontend / Backend / Workspace Management

**Environment fixed in:** Local

**Resolved date:** 2026-06-20

**Resolved by:** Codex local changes

**What was broken:**

Workspace deletion existed in the focused workspace footer and the backend already supported `DELETE /workspaces/{id}`, but the main row action area near `Open`, `Run`, `Test Run`, and `Set Schedule` did not show a clear delete action.

**How it was resolved:**

Added a row-level `Delete` button next to the existing workspace actions. It uses the existing `deleteWorkspace` handler, including the confirmation prompt and delete-in-progress state.

**Verification:**

1. Ran `npm --prefix frontend run check`.
2. Confirmed the existing delete handler still calls `DELETE /workspaces/{id}` and prompts before deleting.
3. Confirmed backend syntax with `python -m py_compile backend\api\server.py backend\api\routes\workspace.py tests\test_backend_api.py`.

**Screenshots / evidence:**

Not captured.

**Remaining follow-up:**

Verify the button placement visually in deployed UI after release.

---

#### Resolved Issue: Missing Workspace QA Checklist

[Go up](#table-of-contents)

**Original issue:** Issue #6

**Status:** Resolved

**Priority at time of fix:** Medium

**Area:** Frontend / QA / Product Validation

**Environment fixed in:** Local frontend build; ready for Render deployment

**Resolved date:** 2026-06-20

**Resolved by:** Codex local changes

**What was broken:**

The workspace detail screen had settings, actions, schedule controls, and documents, but no explicit QA checklist for validating whether a workspace produces good results.

**How it was resolved:**

The focused workspace view now shows a small `Workspace QA Checklist` panel. It covers targeting effectiveness, job source scraping effectiveness, automation option accuracy, and automation effectiveness, using saved workspace settings and existing Test Run flow as the evidence path.

**Verification:**

1. Ran `npm --prefix frontend run check`; ESLint and production Vite build passed.
2. Reviewed `frontend/src/pages/WorkspacesPage.jsx` to confirm the checklist is visible on the focused workspace screen.
3. Confirmed the checklist uses existing workspace data and Test Run review flow rather than adding a broad QA system.

**Screenshots / evidence:**

No screenshot captured locally.

**Remaining follow-up:**

Deploy to Render and have QA validate a real workspace by opening Workspaces, selecting a workspace, running Test Run, and comparing the run review against the checklist.

---

#### Resolved Issue: Runs QA Checklist Needed for Filtering Quality

[Go up](#table-of-contents)

**Original issue:** Issue #7

**Status:** Resolved

**Priority at time of fix:** High

**Area:** Frontend / Backend / Runs / QA / Data Quality

**Environment fixed in:** Local frontend build and backend unit checks; ready for Render deployment

**Resolved date:** 2026-06-20

**Resolved by:** Codex local changes

**What was broken:**

The run review page showed included and excluded jobs, but did not provide an explicit QA checklist for confirming that suitable jobs were kept, unsuitable jobs were rejected, and rejection reasons matched the real blocker. Customer-facing language reason extraction could also pick the wrong language when a note mentioned both German and French.

**How it was resolved:**

The run detail page now shows a `Filtering QA Checklist` above included/excluded jobs, including suitable-job review, unsuitable-job review, rejection reason coverage, and a dedicated language rejection audit. Backend customer language extraction now chooses the earliest actual language mention in the reason text, preventing a German requirement from being mislabeled as French when both words appear in a note.

**Verification:**

1. Ran `npm --prefix frontend run check`; ESLint and production Vite build passed.
2. Ran `node scripts/run-python.cjs -m pytest -q tests/test_backend_api.py::BackendApiTests::test_run_customer_view_uses_first_language_mention_in_rejection_reason`; passed.
3. Ran `node scripts/run-python.cjs -m pytest -q tests/test_tailored_document_generation.py -k language_rules`; passed.

**Screenshots / evidence:**

No screenshot captured locally.

**Remaining follow-up:**

Deploy to Render and have QA inspect a completed run with language rejections to compare the job posting text against the displayed German/French rejection reason.

---

#### Resolved Issue: ATS QA Testing Is Unclear and May Not Guarantee ATS Passing

[Go up](#table-of-contents)

**Original issue:** Issue #8

**Status:** Resolved

**Priority at time of fix:** High

**Area:** Career Assets / ATS / QA

**Environment fixed in:** Local backend and frontend checks; ready for deployment

**Resolved date:** 2026-06-20

**Resolved by:** Codex local changes

**What was broken:**

The ATS generation loop already blocked final CV export when the best score stayed below the 90% target, but the tracker only showed a high-level badge, score, and pass count. Users could see that 3 passes ran without understanding whether ATS passed or failed, why the score stayed below target, or what changed between passes.

**How it was resolved:**

ATS attempt history now records a section-level change summary for each scored pass, including the initial draft and later summary, skills, experience, or education changes. The tracker ATS card now shows pass/fail state, best score versus target, pass count, stop reason, missing requirements, warning text, and an expandable pass audit. The wording now states that 3 ATS passes are a capped optimization effort, not a guarantee of passing.

**Verification:**

1. Ran `python -m unittest tests.test_tailored_document_generation.TailoredDocumentGenerationTests.test_generate_docs_for_job_stops_when_score_stalls_and_keeps_best_attempt tests.test_tailored_document_generation.TailoredDocumentGenerationTests.test_generate_docs_for_job_blocks_after_third_scored_attempt`; both ATS audit metadata checks passed.
2. Ran `npm run check --prefix frontend`; ESLint and production Vite build passed.
3. Reviewed `frontend/src/pages/TrackerPage.jsx` to confirm tracker ATS results now explain pass/fail, score reached, pass audit details, and why 3 passes can still fail.

**Screenshots / evidence:**

No screenshot captured locally.

**Remaining follow-up:**

Deploy and verify the tracker card against a real generated CV whose best ATS score remains below 90%.

---

#### Resolved Issue: Application Tracker Takes Too Long to Load

[Go up](#table-of-contents)

**Original issue:** Issue #9

**Status:** Resolved

**Priority at time of fix:** High

**Area:** Frontend / Tracker / Gmail Sync

**Environment fixed in:** Local frontend build; ready for Render deployment

**Resolved date:** 2026-06-20

**Resolved by:** Codex local changes

**What was broken:**

Opening the tracker automatically called `/tracker/email-integration/sync` whenever Gmail was connected. That slow inbox sync blocked the initial tracker loader, so the route could look stuck for up to about a minute.

**How it was resolved:**

The tracker initial load now fetches only `/tracker` and `/tracker/email-integration`. Gmail sync remains available through the explicit `Sync Inbox` button, and the inbox copy was updated to match that behavior.

**Verification:**

1. Ran `node --test frontend/src/hooks/useTracker.test.js`; verified the tracker shell loader does not call `/tracker/email-integration/sync`.
2. Ran `npm --prefix frontend run check`; ESLint and production Vite build passed.
3. Reviewed `frontend/src/hooks/useTracker.js` and `frontend/src/lib/trackerLoading.js` to confirm route entry loads tracker shell data only.

**Screenshots / evidence:**

No screenshot captured locally.

**Remaining follow-up:**

Deploy to Render and measure the production `/tracker` load separately from explicit inbox sync duration.

---

## Issues Not Yet Resolved

[Go up](#table-of-contents)

<!-- Add issues below this line. -->
