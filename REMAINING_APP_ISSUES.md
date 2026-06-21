# Runr App Issue Tracker

Use this file as the main source of truth for Runr app issues, including open issues, resolved issues, screenshots, reproduction notes, and resolution history.

## Table of Contents

[Go up](#table-of-contents)

- [Templates](#templates)
  - [Open Issue Template](#open-issue-template)
  - [Persistent After Attempted Fix Template](#persistent-after-attempted-fix-template)
  - [Resolved Issue Template](#resolved-issue-template)
- [Resolved Issues](#resolved-issues)
  - [Resolved Issue #3: Quick Apply Requires a Configured Workspace](#resolved-issue-3-quick-apply-requires-a-configured-workspace)
  - [Resolved Issue #4: System-Created Workspaces Should Not Appear as User Workspaces](#resolved-issue-4-system-created-workspaces-should-not-appear-as-user-workspaces)
  - [Resolved Issue #5: Missing Workspace Delete Button](#resolved-issue-5-missing-workspace-delete-button)
  - [Resolved Issue #6: Missing Workspace QA Checklist](#resolved-issue-6-missing-workspace-qa-checklist)
  - [Resolved Issue #7: Runs QA Checklist Needed for Filtering Quality](#resolved-issue-7-runs-qa-checklist-needed-for-filtering-quality)
  - [Resolved Issue #8: ATS QA Testing Is Unclear and May Not Guarantee ATS Passing](#resolved-issue-8-ats-qa-testing-is-unclear-and-may-not-guarantee-ats-passing)
  - [Resolved Issue #9: Application Tracker Takes Too Long to Load](#resolved-issue-9-application-tracker-takes-too-long-to-load)
- [Issues Not Yet Resolved](#issues-not-yet-resolved)
  - [Issue #10: Workspace Workflow Is Slow, Under-Validated, and Produces Poor CV Outputs](#issue-10-workspace-workflow-is-slow-under-validated-and-produces-poor-cv-outputs)
  - [Issue #1: Reset Error / Tool Keeps Refreshing](#issue-1-reset-error--tool-keeps-refreshing)
  - [Issue #2: Dashboard Takes 25-30 Seconds to Load](#issue-2-dashboard-takes-25-30-seconds-to-load)

## Templates

[Go up](#table-of-contents)

Copy the rendered block below when adding a new issue or moving an issue to resolved.

Standard rule for all new issues: add a `[Go up](#table-of-contents)` link directly below every new section heading and issue heading.

Standard sorting rule: keep issues ordered from smallest to largest by original issue number within each issue section.

Original issue number rule: keep the original issue number in every issue heading, including after an issue is moved to `Resolved Issues`. Resolved headings must use `Resolved Issue #N: Short Title`, where `#N` is the original issue number.

External stack rule: if an issue may involve infrastructure, hosting, auth, database, routing, caching, CDN, DNS, or environment variables, document the relevant non-code systems explicitly. Do not treat Render, Cloudflare, Turso, OAuth providers, email providers, or similar services as code-only problems.

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

### Persistent After Attempted Fix Template

[Go up](#table-of-contents)

#### Issue #N: Short Title

[Go up](#table-of-contents)

**Status:** Persistent after attempted fix

**Priority:** Critical / High / Medium / Low

**Area:** Frontend / Backend / Billing / Auth / Deployment / Data / Other

**Environment:** Local / Render / Cloudflare / Turso / Mobile / Desktop / Other

**Current user report:**

Describe what still happens after the attempted fix.

**What changed after the attempted fix:**

Describe what improved, disappeared, or changed, even if the issue remains.

**What still fails:**

Describe the remaining user-facing problem.

**Previous attempted fix:**

Date, owner, commit/PR/branch, and summary of the attempted fix.

**Why the issue is still open:**

Explain the evidence that proves the previous fix did not fully resolve the issue.

**External stack to check:**

List any relevant systems outside the codebase, such as Render, Cloudflare, Turso, OAuth providers, DNS, CDN/cache settings, background job services, or environment variables. Write `None known yet` only after checking.

**Next investigation plan:**

1. Step one
2. Step two
3. Step three

**Screenshots / evidence:**

![Screenshot 1](screenshots/issue-name-1.png)

**Resolution rule:**

Do not move this issue back to resolved until it has been verified in the same environment where the user reported the persistent behavior.

---

### Resolved Issue Template

[Go up](#table-of-contents)

#### Resolved Issue #N: Short Title

[Go up](#table-of-contents)

**Original issue:** Issue #N

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

#### Resolved Issue #3: Quick Apply Requires a Configured Workspace

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

#### Resolved Issue #4: System-Created Workspaces Should Not Appear as User Workspaces

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

#### Resolved Issue #5: Missing Workspace Delete Button

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

#### Resolved Issue #6: Missing Workspace QA Checklist

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

#### Resolved Issue #7: Runs QA Checklist Needed for Filtering Quality

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

#### Resolved Issue #8: ATS QA Testing Is Unclear and May Not Guarantee ATS Passing

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

#### Resolved Issue #9: Application Tracker Takes Too Long to Load

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

#### Issue #10: Workspace Workflow Is Slow, Under-Validated, and Produces Poor CV Outputs

[Go up](#table-of-contents)

**Status:** Local fix implemented; production timing verification pending

**Priority:** Critical

**Area:** Frontend / Backend / Workspace / CV Upload / CV Templates / Test Runs / Performance

**Environment:** Deployed app and local reproduction needed; reported from desktop browser recording

**URL or screen:** Workspace creation, CV upload, CV template selection, workspace CV loading, and workspace test run

**What happens:**

The workspace workflow is too slow and permits invalid setup. Uploading and loading a text-based CV takes far longer than expected, workspace creation can proceed without a selected country, most CV templates produce poor PDF output, and test runs take a long time to start before failing.

**What should happen:**

Text-based CV upload and load should be near-instant for a normal 2-page document, required workspace fields should block creation until complete, CV templates should produce normal readable PDFs, and test runs should start quickly or fail fast with a clear error.

**Steps to reproduce:**

1. Open the workspace flow.
2. Upload a text-based CV with no photos.
3. Create or edit a workspace without selecting a country.
4. Review available CV templates and generated PDF output.
5. Open the workspace CV after upload.
6. Start a test run.

**Reported problems, solution, and success criteria:**

1. **CV upload takes too long for a text-based CV.**
   **Solution:** Measure the upload path end to end before changing behavior: browser upload time, API request time, file parsing time, storage/database write time, and any AI/document processing triggered synchronously. Keep the upload endpoint responsible only for accepting, validating, extracting text, and saving the CV. Move expensive enrichment, scoring, or regeneration work behind an explicit later action or background job.
   **Success criteria:** A normal 2-page text CV uploads and returns a usable workspace document state in under 2 seconds on local dev and under 5 seconds on the deployed app. The issue notes include the measured root cause, such as slow parsing, synchronous AI work, storage latency, database latency, or duplicate frontend requests.

2. **Workspace can be created without selecting a country.**
   **Solution:** Treat country as a required field in both frontend validation and backend/API validation. Mark every required workspace field with `*`, disable or reject submit while required fields are missing, and return field-level errors from the backend if a client bypasses the UI.
   **Success criteria:** The country field visibly shows as required, creating a workspace without a country is blocked in the UI, the API rejects missing country with a clear validation error, and an automated check covers the missing-country case.

3. **All CV templates except `Plain` should be removed or replaced.**
   **Solution:** Delete or hide the current non-Plain templates if they rely on React-rendered layouts that waste space or export poorly to PDF. Keep `Plain` as the reliable baseline, then add only simple ATS-friendly document templates that render like normal CVs. Photo upload should be shown only when the selected template supports photos.
   **Success criteria:** Non-Plain templates that produce poor PDFs are no longer selectable. Any remaining or replacement template exports to a readable PDF with normal spacing, no broken formatting, and no unexpected blank space. The photo control appears only for templates with explicit photo support.

4. **Opening/loading a text-only CV takes far too long.**
   **Solution:** Separate CV display from expensive processing. Cache extracted CV text and structured fields after upload, render the saved parsed result immediately, and avoid re-parsing or regenerating documents on every workspace view. Add timing logs around CV fetch, parse, and render to prove where the delay was.
   **Success criteria:** Opening an already-uploaded 2-page text CV renders the saved content in under 1 second locally and under 3 seconds on the deployed app. Reloading the workspace does not trigger duplicate parse/generation calls for the same CV unless the CV changed.

5. **Test run takes an incredibly long time to start and then fails.**
   **Solution:** Add a preflight validation step before starting the test run: required workspace fields, CV availability, selected country, selected job sources/search settings, auth/session state, and backend worker/API readiness. Start the run only after preflight passes, and fail fast with a specific actionable error when setup is invalid. Measure queue/start latency separately from run execution latency.
   **Success criteria:** A valid workspace test run leaves the starting state within 5 seconds or shows a clear queued/running state with progress. An invalid workspace fails preflight in under 2 seconds with the exact missing requirement. Test run failures include a user-visible reason and enough backend log context to debug the failing step.

**Notes / clues:**

The user explicitly requested the root cause for the slow CV upload, not only a symptom fix. Do not mark the performance parts resolved without timings that explain why the delay happened.

Ponytail direction for the implementation: remove poor templates before adding replacements, use existing validation paths before adding new abstractions, and keep upload/view paths limited to the minimum synchronous work needed for the user to continue.

**Local fix implemented on 2026-06-21:**

- CV upload now skips OCR for workspace/master CV assets and returns `timings_ms` for body read, multipart parsing, text extraction, profile parsing, asset storage, metadata persistence, and total upload time.
- Workspace CV listing/preview now prefers cached `source_text` metadata before re-reading or extracting from the original uploaded file.
- Workspace creation and run preflight now reject missing country through backend `field_errors`, while the frontend marks required fields with `*` and blocks saving without a country.
- CV template options now expose only `Plain`; legacy template IDs normalize to `plain`; photo toggles are hidden/disabled when the effective template does not support photos.
- Test-run start now surfaces top-level validation errors before source-specific details so invalid workspaces fail fast with the missing requirement.

**Verification completed locally:**

- Backend/API checks cover Plain-only template options, legacy template normalization, missing-country save validation, deleted-CV run preflight, and CV-upload timing payload.
- Frontend check passed with ESLint and production Vite build.

**Verification still required before moving to resolved:**

- Measure a real 2-page text CV upload locally and on the deployed app, then record before/after timings and the dominant slow step.
- Measure opening an already-uploaded text CV locally and on the deployed app.
- Measure valid and invalid test-run start latency locally and on the deployed app.

**Screenshots / evidence:**

User-provided issue card: `issue #10`, titled `Workspace workflow`.

User-provided recording: `c:\Users\ahmed\Videos\Captures\runr. frontend and 10 more pages - School - Microsoft Edge 2026-06-21 17-31-12.mp4`

**Resolution rule:**

Do not move this issue to resolved until each numbered success criterion above is verified. Performance fixes must include measured before/after timings for upload, CV load, and test-run start.

---

#### Issue #1: Reset Error / Tool Keeps Refreshing

[Go up](#table-of-contents)

**Status:** Persistent after attempted fix

**Priority:** Critical

**Area:** Frontend / Auth / Deployment / Performance

**Environment:** Deployed app; likely Render plus Cloudflare and backend/API session path

**Current user report:**

The previous visible `api connection` error no longer appears, but every section still takes a very long time to load. The app still feels like it is repeatedly loading or refreshing during normal use.

**What changed after the attempted fix:**

The explicit connection error appears to be hidden or reduced. This means the first attempted fix may have improved the visible error state, but it did not resolve the underlying slow loading or refresh behavior.

**What still fails:**

Every major section is still slow to load on the deployed version, making the tool difficult to use. The user experience is still consistent with repeated app/session refreshes or repeated blocking API checks.

**Previous attempted fix:**

2026-06-20, Codex local changes. The session provider was changed to preserve the last successful authenticated session during `/auth/me` refreshes, and `App.jsx` was changed so an existing authenticated user keeps the current route mounted during reconnect/session checks.

2026-06-21, Codex local changes. Shared frontend API resources now dedupe in-flight requests by cache key and separate background `refreshing` from blocking `loading`, reducing duplicate route/data fetches during navigation, Strict Mode remounts, polling, and repeated refresh actions.

**Why the issue is still open:**

User feedback after the attempted fix says: "The error does not show but every section takes a very long time to load." That means the visible reset error may have been addressed, but the deployed app still has the practical problem of slow section loading and possible background refresh behavior.

**External stack to check:**

Render deployment and backend service responsiveness, Cloudflare routing/caching/proxy behavior for `app.userunr.com`, Turso database latency/query performance, deployed environment variables for auth/session/API URLs, and any production-only auth cookie/session behavior.

**Next investigation plan:**

1. Test the deployed app with browser devtools open and record which requests run when switching sections.
2. Check whether `/auth/me` or other bootstrap/session endpoints repeat on every route or section change.
3. Compare deployed Render API timings with local timings to separate frontend state issues from Render, Cloudflare, or Turso latency.
4. Inspect backend logs during navigation to see whether the app is reauthenticating, rebuilding user state, or retrying failed requests.
5. Only mark resolved after the deployed app keeps sections mounted and loads them quickly without repeated connection or session refresh behavior.

**Screenshots / evidence:**

User screenshot note: "The error does not show but every section takes a very long time to load."

Original issue screenshot note: the tool kept resetting itself by checking the `api connection`, causing constant refreshes on the deployed version.

**Resolution rule:**

Do not move this issue back to resolved until the deployed version is verified, not just the local frontend build.

---

#### Issue #2: Dashboard Takes 25-30 Seconds to Load

[Go up](#table-of-contents)

**Status:** Persistent after attempted fix

**Priority:** High

**Area:** Frontend / Backend / Data Loading / Deployment / Database

**Environment:** Deployed app; likely Render API plus Turso database and Cloudflare route

**Current user report:**

The dashboard still takes a very long time to load. It also appears to be loading and refreshing at the same time.

**What changed after the attempted fix:**

The dashboard code was changed so the page shell can render while analytics load in the background. This may have changed the visible loading state, but it did not make the deployed dashboard feel fast or stable.

**What still fails:**

Dashboard loading is still slow enough to be a user-facing issue. The page may be triggering overlapping loading and refresh states, or it may be waiting on slow production API/database work despite the frontend shell rendering earlier.

**Previous attempted fix:**

2026-06-20, Codex local changes. `DashboardPage.jsx` was changed so `loading && !data` no longer returns a full `DashboardSkeleton`; the page shell, navigation actions, action plan fallback, and empty chart states render while `/dashboard` analytics load in the background.

2026-06-21, Codex local changes. The dashboard now loads `/dashboard?mode=summary` first for fast cards and recent runs, then refreshes full `/dashboard` analytics in the background. The backend summary mode skips the expensive tracker/review/job-set analytics pass, and shared API resource request deduplication prevents overlapping dashboard refreshes.

**Why the issue is still open:**

User feedback after the attempted fix says: "still takes a very long time to load. also looks like its loading and refreshing at the same time." The frontend loading presentation changed, but production dashboard performance and refresh behavior remain unresolved.

**External stack to check:**

Render API response time for `/dashboard`, Turso query latency and query shape for dashboard analytics, Cloudflare proxy/cache behavior, deployed frontend API base URL, Render cold starts or sleeping services, and any production environment variables that change data loading behavior.

**Next investigation plan:**

1. Measure the deployed `/dashboard` request duration in browser devtools and Render logs.
2. Confirm whether the dashboard triggers duplicate `/dashboard` requests during initial load or refresh.
3. Profile backend dashboard data collection to identify slow queries, sequential calls, retries, or expensive aggregation.
4. Check Turso query performance and whether indexes or query limits are missing for dashboard analytics.
5. Decide whether the correct fix is frontend request deduplication, backend endpoint optimization, cached/precomputed dashboard metrics, or deployment/database configuration changes.
6. Only mark resolved after the deployed dashboard opens quickly and does not visibly load and refresh at the same time.

**Screenshots / evidence:**

User screenshot note: "still takes a very long time to load. aslo looks like its loading and refreshing at the same time"

Original issue screenshot note: dashboard took about 25 seconds to load, refreshes also took a long time, and there was not enough data to justify that much loading time.

**Resolution rule:**

Do not move this issue back to resolved until the deployed dashboard is measured and verified. A local build passing is not enough for this issue.
