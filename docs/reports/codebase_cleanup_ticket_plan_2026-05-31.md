# Codebase Cleanup Ticket Plan - 2026-05-31

This plan turns the codebase cleanliness review into independently grabbable tickets.

Use one chat per ticket unless a ticket says it must run in this chat. Prompts are written to be pasted directly into a fresh agent chat.

## Execution Waves

### Wave 0 - Human decision

- T01 decides the artifact/source-control policy. Do this first because it affects cleanup commands and avoids deleting real user data by accident.

### Wave 1 - Can run in parallel after T01 starts or completes

- T02 repository hygiene implementation
- T03 fast test and lint command baseline
- T04 current architecture and agent context docs
- T05 frontend bundle hygiene

T02 should not delete local files without explicit human approval. It can update ignore rules and document safe cleanup commands.

### Wave 2 - Backend API extraction foundation

- T06 must complete before T07-T10.

### Wave 3 - Can run in parallel after T06

- T07 workspace, template, run, and worker API route extraction
- T08 document, upload, export, and CV API route extraction
- T09 tracker, referrals, Gmail, and people-discovery API route extraction
- T10 admin, billing, settings, analytics, and webhook API route extraction

These tickets can run in parallel only after T06 creates stable route modules and a low-conflict registration pattern. Each chat must stay inside its assigned route domain.

### Wave 4 - Backend service and repository cleanup

- T11 service protocols and application facade boundaries
- T12 split BackendApplication into domain services
- T13 split SQLite repositories and migration ownership

T11 blocks T12 and T13. T12 and T13 can run in parallel after T11 if they avoid editing the same files outside agreed import boundaries.

### Wave 5 - Frontend maintainability

- T14 WorkspacesPage hook/component extraction

T14 can run in parallel with Waves 2-4 because it is frontend-only, but it should wait for T03 so it has stable frontend verification commands.

### Wave 6 - Final integration

- T00 final integration check in this chat. Run this only after all selected tickets are merged or applied.

## T00 - Final Integration Check

Type: HITL

Blocked by: all selected cleanup tickets.

Can run in parallel: no.

What to build:

Perform the final review in this existing chat after the cleanup work is done. Verify the working tree, source boundaries, route extraction, frontend build, backend tests, docs, and remaining hotspots.

Acceptance criteria:

- [ ] `git status --short` is understood and contains no accidental generated/runtime noise.
- [ ] Fast backend tests pass.
- [ ] Frontend build passes without avoidable chunk warnings.
- [ ] Main hotspot files are materially smaller or have clear follow-up tickets.
- [ ] No route/service extraction broke documented API behavior.
- [ ] Final report lists remaining risks and exact next tickets.

Prompt to give this chat:

```text
All selected cleanup tickets from docs/reports/codebase_cleanup_ticket_plan_2026-05-31.md are done. Please do the final integration check now. Review git status, run the agreed backend/frontend verification commands, inspect the remaining biggest files and generated artifacts, and give me a concise final pass/fail report with remaining cleanup tickets if needed.
```

## T01 - Decide Source-Control Artifact Policy

Type: HITL

Blocked by: none.

Can run in parallel: no, do first.

What to build:

Create a short source-control policy that decides which generated docs, local user assets, logs, datasets, archives, and fixtures belong in git.

Acceptance criteria:

- [ ] Policy names paths that are source, fixtures, generated outputs, local runtime data, or archive data.
- [ ] Policy explicitly handles `Archive/`, `backend/config/outputs/`, `generated_docs/`, `test-CV/`, `user_config/profile_photos/`, `user_config/candidate_assets/`, root `node_modules/`, logs, `.runr_*`, `.backend_*`, and stage output JSON files.
- [ ] Policy says whether cleanup should use `git rm --cached`, file moves, or ignore-only changes.
- [ ] No data is deleted as part of this ticket.

Prompt:

```text
Use the current repo. Create a short source-control artifact policy for this project. Do not delete or untrack anything yet. Classify source files, fixtures, generated outputs, runtime data, local user data, and archives. Cover Archive/, backend/config/outputs/, generated_docs/, test-CV/, user_config/profile_photos/, user_config/candidate_assets/, root node_modules/, logs, .runr_*, .backend_*, and stage output JSON files. Save the policy under docs/architecture or docs/reports and include exact safe cleanup recommendations for a follow-up chat.
```

## T02 - Implement Repository Hygiene Guardrails

Type: AFK, with no destructive file deletion.

Blocked by: T01.

Can run in parallel: yes, with T03-T05 after T01 policy exists.

What to build:

Update ignore rules and add safe cleanup scripts or documented commands so generated/runtime files stop polluting status and search.

Acceptance criteria:

- [ ] `.gitignore` covers runtime logs, root `node_modules/`, generated docs, local stage outputs, local databases, temp folders, and user asset outputs according to T01.
- [ ] If tracked generated files exist, the ticket documents exact `git rm --cached` commands but does not delete local files unless the user explicitly requested it.
- [ ] `rg --files` and `git status --short` become easier to interpret.
- [ ] README or a runbook explains where generated artifacts should live.

Prompt:

```text
Implement repository hygiene guardrails based on the artifact policy in docs. Update .gitignore and add a short cleanup runbook. Do not delete user data. If generated files are already tracked, document safe git rm --cached commands instead of running destructive cleanup unless explicitly approved. Verify with git status --short and a scoped rg --files command that future generated/runtime noise is ignored.
```

## T03 - Add Fast Test, Lint, and Check Baseline

Type: AFK.

Blocked by: none.

Can run in parallel: yes.

What to build:

Create reliable fast verification commands for humans and AI agents.

Acceptance criteria:

- [ ] Backend tests have markers or a documented subset so a fast check completes quickly.
- [ ] Add Python lint/format tooling, preferably Ruff, with minimal config.
- [ ] Add frontend lint/check script or document why build is the only frontend check for now.
- [ ] Root scripts or README expose `check`, `check:backend`, and `check:frontend` equivalents.
- [ ] Full `pytest` timeout risk is documented with the slow tests isolated or marked.

Prompt:

```text
Add a fast verification baseline. Inspect existing Python and frontend tooling first. Add or document backend fast tests, pytest markers if needed, Ruff lint/format config if practical, and root/package scripts or README commands for check:backend and check:frontend. Do not do broad formatting churn. Verify the new fast commands run locally and report any slow/full-suite command that still needs work.
```

## T04 - Create Current Architecture and Agent Context Docs

Type: AFK.

Blocked by: none.

Can run in parallel: yes.

What to build:

Create a concise current-system guide that replaces scattered dated reports as the first stop for humans and AI agents.

Acceptance criteria:

- [ ] Add `docs/architecture/current_system.md` or equivalent.
- [ ] Document entrypoints, backend layers, frontend layers, data storage, generated artifact locations, and common commands.
- [ ] Link to durable docs and mark dated reports as historical.
- [ ] Include "where to change what" guidance for API routes, application services, stage adapters, repositories, and frontend pages.

Prompt:

```text
Create a current architecture and agent context document. Use README.md, ARCHITECTURE.md, docs/reports, and a light code scan. Save a concise durable guide under docs/architecture/current_system.md or similar. It should tell a human or AI agent where to change API routes, services, repositories, stage adapters, frontend pages, generated artifacts, and verification commands. Do not rewrite old reports except to link from an index if helpful.
```

## T05 - Reduce Frontend Bundle Warnings

Type: AFK.

Blocked by: none.

Can run in parallel: yes.

What to build:

Reduce avoidable Vite chunk warnings, especially large country-data chunks and the workspace page bundle.

Acceptance criteria:

- [ ] `npm --prefix frontend run build` passes.
- [ ] Avoidable chunks over 500 kB are reduced or intentionally documented.
- [ ] Country/state/city data is dynamically loaded or manually chunked where practical.
- [ ] No user-facing workflow changes unless required for lazy loading.

Prompt:

```text
Investigate the frontend Vite build chunk warnings. Focus on large country/state/city data chunks and WorkspacesPage bundle size. Make conservative changes such as dynamic imports or manualChunks. Preserve behavior. Run npm --prefix frontend run build and report before/after chunk warnings and any remaining intentional large chunks.
```

## T06 - Build API Route Extraction Foundation

Type: AFK.

Blocked by: T02 preferred, but can start after T01 if needed.

Can run in parallel: no. This blocks T07-T10.

What to build:

Create a low-conflict route-module structure around `backend/api/server.py` without moving every endpoint yet.

Acceptance criteria:

- [ ] Shared request/response helpers are extractable or wrapped without changing behavior.
- [ ] Route modules can register handlers by domain.
- [ ] Existing API tests still pass for a small representative subset.
- [ ] Follow-up route extraction tickets can mostly edit separate files.
- [ ] `backend/api/server.py` starts shrinking or has clear delegation points.

Prompt:

```text
Create the foundation for splitting backend/api/server.py into route modules. Do not attempt to move every route. Add a small route registration/delegation pattern that preserves current behavior and makes it possible for separate chats to own separate route files. Extract only shared helpers needed for the pattern. Run focused API tests that prove existing routing, auth, and error handling still work. Keep changes small and document how follow-up chats should add route modules without touching each other.
```

## T07 - Extract Workspace, Template, Run, and Worker API Routes

Type: AFK.

Blocked by: T06.

Can run in parallel: yes, with T08-T10 after T06.

What to build:

Move workspace-builder, workspace/template CRUD, run lifecycle, run resources, and worker endpoints into their assigned route module.

Acceptance criteria:

- [ ] Public behavior and `/v1` behavior remain unchanged.
- [ ] Focused backend API tests for workspaces, templates, runs, and workers pass.
- [ ] Route code no longer lives in the giant handler except for delegation.
- [ ] No unrelated document/tracker/admin routes are moved.

Prompt:

```text
Continue the API route split after T06. Own only workspace-builder, workspaces, workflow templates, runs, run job resources, and worker endpoints. Move these routes into the route module structure created by T06 while preserving auth, scopes, CORS, error responses, and /v1 compatibility. Do not touch document, tracker, referral, billing, admin, or webhook route logic except where shared helpers require it. Run the focused tests for workspace/template/run/worker API behavior.
```

## T08 - Extract Document, Upload, Export, and CV API Routes

Type: AFK.

Blocked by: T06.

Can run in parallel: yes, with T07, T09, and T10 after T06.

What to build:

Move documents, candidate assets, CV upload/profile photo upload, bulk export, ATS export gate, and CV preview related endpoints into a document route module.

Acceptance criteria:

- [ ] Existing document/upload/export API behavior remains unchanged.
- [ ] Focused tests for CV upload, profile photo upload, documents, bulk export, and ATS gate pass.
- [ ] File handling remains safe and scoped.
- [ ] No unrelated workspace/tracker/admin route logic is moved.

Prompt:

```text
Continue the API route split after T06. Own only documents, candidate assets, CV upload, profile photo upload, bulk export, ATS export gate, and CV preview/document-design endpoints. Move these routes into the route module structure while preserving behavior, auth, error shapes, and /v1 compatibility. Do not touch workspace, run, tracker, referral, billing, admin, or webhook logic except shared helper imports. Run focused API tests covering document endpoints, uploads, bulk export, and ATS gate behavior.
```

## T09 - Extract Tracker, Referrals, Gmail, and People Discovery Routes

Type: AFK.

Blocked by: T06.

Can run in parallel: yes, with T07, T08, and T10 after T06.

What to build:

Move tracker application status, rejected jobs, referrals, outreach, email/Gmail integration, Google OAuth callback, and people-discovery endpoints into route modules.

Acceptance criteria:

- [ ] Tracker/referral/Gmail behavior remains unchanged.
- [ ] Existing focused tests for tracker, Gmail, referrals, and people discovery pass.
- [ ] OAuth callback and auth-sensitive paths keep current security behavior.
- [ ] No unrelated document/admin/workspace routes are moved.

Prompt:

```text
Continue the API route split after T06. Own only tracker, rejected jobs, referrals, outreach, email integration, Gmail/Google OAuth, and people-discovery endpoints. Move them into route modules while preserving current behavior, auth, error shapes, and /v1 compatibility. Be careful with OAuth callback behavior and persisted tracker metadata. Do not touch workspace/run/document/admin/billing route logic except shared helper imports. Run focused tests for tracker, Gmail integration, referrals, and people discovery.
```

## T10 - Extract Admin, Billing, Settings, Analytics, and Webhook Routes

Type: AFK.

Blocked by: T06.

Can run in parallel: yes, with T07-T09 after T06.

What to build:

Move admin endpoints, billing/checkout, LemonSqueezy and Clerk webhooks, settings, analytics, events, users, secrets, and auth/me routes into route modules.

Acceptance criteria:

- [ ] Admin-only and scope checks remain intact.
- [ ] Webhook verification behavior remains unchanged.
- [ ] Billing checkout does not log raw promo codes or secrets.
- [ ] Focused API tests for admin, users/secrets, settings, analytics, and billing pass.
- [ ] No unrelated workspace/document/tracker routes are moved.

Prompt:

```text
Continue the API route split after T06. Own only admin, billing, settings, analytics/events, auth/me, users, secrets, Clerk webhook, and LemonSqueezy webhook endpoints. Move them into route modules while preserving auth scopes, admin checks, webhook verification, error responses, and /v1 compatibility. Do not touch workspace/run/document/tracker route logic except shared helper imports. Run focused tests for admin events, users/secrets, settings, analytics, billing, and webhooks.
```

## T11 - Add Service and Repository Boundary Protocols

Type: AFK.

Blocked by: Wave 3 preferred.

Can run in parallel: no. This blocks T12 and T13.

What to build:

Replace broad `Any` service/repository boundaries with typed protocols or small interfaces that make extraction safer.

Acceptance criteria:

- [ ] `BackendApplication` constructor types are more explicit.
- [ ] Repository contracts exist for the stores the application actually uses.
- [ ] No large behavior refactor is bundled into this ticket.
- [ ] Existing backend tests still pass for a representative subset.

Prompt:

```text
Add typed service/repository boundary protocols before splitting BackendApplication and sqlite_backed. Inspect backend/application/services.py, backend/repositories, and backend/bootstrap.py. Replace broad Any boundaries where practical with Protocols or clear dataclasses. Keep behavior unchanged. Do not split large services yet. Run representative backend tests to prove construction, auth, workspace, run, and repository behavior still works.
```

## T12 - Split BackendApplication Into Domain Services

Type: AFK.

Blocked by: T11 and preferably T07-T10.

Can run in parallel: yes, with T13 after T11 if import boundaries are stable.

What to build:

Move cohesive method groups out of `backend/application/services.py` into domain services while keeping a compatibility facade.

Acceptance criteria:

- [ ] `BackendApplication` remains usable by API, worker, CLI, and tests.
- [ ] At least two high-churn domains are extracted, preferably workspace/run and documents/tracker.
- [ ] Extracted services have focused tests or existing tests still cover the facade.
- [ ] `services.py` materially shrinks.

Prompt:

```text
Split BackendApplication into domain services using the boundaries from T11. Keep BackendApplication as a compatibility facade so API, worker, CLI, and tests do not need a massive rewrite. Extract cohesive domains conservatively, prioritizing workspace/run and document/tracker or the highest-friction groups you find. Preserve behavior and avoid unrelated refactors. Run focused backend application and API tests that cover the moved methods.
```

## T13 - Split SQLite Repositories and Migration Ownership

Type: AFK.

Blocked by: T11.

Can run in parallel: yes, with T12 after T11 if imports do not overlap heavily.

What to build:

Break `backend/repositories/sqlite_backed.py` into smaller store/migration modules without changing storage behavior.

Acceptance criteria:

- [ ] Public imports from `backend.repositories` remain compatible.
- [ ] Migrations are isolated or clearly grouped.
- [ ] Stores for workspaces/runs/jobs/artifacts/auth/analytics/source-policy are easier to navigate.
- [ ] SQLite repository tests pass.
- [ ] No schema behavior changes are bundled unless covered by tests.

Prompt:

```text
Refactor backend/repositories/sqlite_backed.py into smaller modules while preserving public imports through backend/repositories/__init__.py. Keep schema behavior unchanged. Isolate migrations or group them clearly, and split store classes by domain where practical. Avoid broad application-service changes. Run tests/test_sqlite_repositories.py and representative backend tests that construct the default backend.
```

## T14 - Split WorkspacesPage Into Hooks and Components

Type: AFK.

Blocked by: T03 preferred.

Can run in parallel: yes, frontend-only.

What to build:

Reduce `frontend/src/pages/WorkspacesPage.jsx` by extracting hooks/components around the workspace builder, schedule editor, CV assets, source validation, and city options.

Acceptance criteria:

- [ ] `WorkspacesPage.jsx` materially shrinks.
- [ ] Behavior and route paths remain unchanged.
- [ ] Extracted hooks/components have clear names and local ownership.
- [ ] Frontend build passes.
- [ ] No unrelated visual redesign is included.

Prompt:

```text
Refactor frontend/src/pages/WorkspacesPage.jsx for maintainability. Extract hooks and components around workspace builder form state, source validation, CV assets/uploads, schedule editing, city options, and focused workspace documents. Preserve behavior and avoid visual redesign. Keep changes scoped to frontend files. Run npm --prefix frontend run build and any frontend check command added by T03.
```

## Recommended Assignment

- Chat A: T01, then T02.
- Chat B: T03.
- Chat C: T04.
- Chat D: T05.
- Chat E: T06, then coordinate Wave 3.
- Chat F: T07 after T06.
- Chat G: T08 after T06.
- Chat H: T09 after T06.
- Chat I: T10 after T06.
- Chat J: T11 after Wave 3.
- Chat K: T12 after T11.
- Chat L: T13 after T11.
- Chat M: T14 after T03.
- This chat: T00 final integration check after all selected work is done.

## Merge Discipline For Parallel Chats

- Each chat should start by reading this ticket plan, `git status --short`, and relevant files.
- Each chat should state the files it intends to own before editing.
- Route extraction chats must not reformat unrelated regions of `backend/api/server.py`.
- Frontend extraction chat must avoid broad style changes.
- Repository cleanup chat must not delete local data without explicit human approval.
- Every chat should end with exact verification commands and results.
