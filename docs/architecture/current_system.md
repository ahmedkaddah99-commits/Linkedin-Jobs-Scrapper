# Current System Architecture

Status: active agent context

Date: 2026-05-31

This is the first stop for current code navigation. Dated reports under `docs/reports/` are historical context unless they are linked from here or still match the source.

## Entrypoints

- Product CLI and local backend launcher: `workspace_runner.py`.
- JSON API: `backend/api/server.py`, with extracted route modules under `backend/api/routes/`.
- Background worker: `backend/worker/service.py`.
- React app routes: `frontend/src/App.jsx`.
- Assisted Apply extension shell: `apps/browser-extension/` (WXT, Manifest V3,
  TypeScript, React). Portable adapter/message contracts start under `packages/`.
- Main workspace UI: `frontend/src/pages/WorkspacesPage.jsx`.
- Local stack scripts: root `package.json`.

Common local commands:

```powershell
npm run dev
npm run dev:api
npm run dev:worker
npm run dev:ui
npm run check
npm run check:backend
npm run check:backend:api
npm run check:backend:full
npm run check:frontend
npm run check:extension
npm run check:assisted-apply
```

Install development verification tools with:

```powershell
pip install -r requirements-dev.txt
```

## Backend Shape

- `backend/bootstrap.py` constructs the default backend application and repositories.
- `backend/application/services.py` is the compatibility facade used by API, worker, CLI, and tests.
- `backend/application/domain_services.py`, `backend/application/run_services.py`, and
  `backend/application/tracker_services.py` own extracted backend domain services behind the compatibility facade.
- `backend/domain/` holds shared records and contracts such as workspaces, runs, jobs, artifacts, users, and phase contracts.
- `backend/orchestration/` owns the stage engine, workspace builder, registries, and starter templates.
- `backend/adapters/stage_adapters.py` maps workflow stages to capability modules.
- `backend/capabilities/` contains domain capability packages such as tailored documents, reusable packages, networking, tracker, and source policy.
- `backend/connectors/` owns external source and ATS connectors.
- `backend/repositories/` owns repository protocols plus SQLite and file-backed persistence. SQLite schema/bootstrap and migrations are split from concrete store classes.
- `backend/security/` owns auth and secret helpers.
- `backend/integrations/` owns third-party service wrappers such as Clerk, Creem, and ScrapeOps.

## Frontend Shape

- `frontend/src/App.jsx` declares lazy page routes and route-level auth/admin gates.
- `frontend/src/context/` owns session and theme state.
- `frontend/src/hooks/` owns reusable API/resource hooks.
- `frontend/src/lib/` owns API helpers, formatting, analytics, CV studio rendering helpers, auth helpers, and location option loading.
- `frontend/src/components/` owns shared panels and reusable UI.
- `frontend/src/pages/` owns page-level workflows. Large pages should be split into local hooks/components before broad feature work.
- `frontend/src/styles.css` is the main style surface.

## Browser Extension Shape

- `apps/browser-extension/entrypoints/background.ts` owns privileged browser APIs,
  tab coordination, and reconstructable session state.
- `apps/browser-extension/entrypoints/application-form.ts` is an isolated page
  runner injected after user action; it does not call Runr APIs directly.
- `apps/browser-extension/entrypoints/sidepanel/` owns the review-only React UI.
- `packages/ats-core/` owns portable portal detection/adapter contracts and the
  compile-time no-submit guard.
- `packages/extension-messages/` owns runtime message/state contracts.
- AA-01 is a guarded Greenhouse fixture tracer bullet only. Follow the active ticket
  ledger in `docs/reports/runr_assisted_apply_ticket_plan_2026-07-17.md`; do not treat
  fixture data as a production application package.

## Data And Artifacts

- Default local persisted backend state lives under `.backend_data/`.
- Test backend state lives under `.backend_test_tmp/` and related `.backend_*` folders.
- Generated stage outputs live under `backend/config/outputs/`.
- Generated document exports live under `generated_docs/` or user asset export folders.
- User-owned uploads and photos live under `user_config/candidate_assets/` and `user_config/profile_photos/`.
- Logs live under `logs/` or `.runr_*` / `.backend_*` files.
- External raw datasets and archives live under `Jobs-Urls/`, `Archive/`, `test CV/`, or `test-CV/` and should not be treated as active product source.

See `docs/architecture/source_control_artifact_policy.md` and `docs/architecture/repository_hygiene_runbook.md` before untracking generated files.

## Where To Change What

- API routes: extract domain route bodies into `backend/api/routes/` and wire them through `backend/api/routes/__init__.py`. `backend/api/server.py` remains the compatibility host for CORS, auth helpers, request parsing, and legacy inline routes during extraction. Keep `/v1` compatibility and existing error shapes.
- Application behavior: change `backend/application/services.py` or a capability module behind it. Keep `BackendApplication` usable as the facade.
- Stage behavior: change `backend/adapters/stage_adapters.py` for adapter wiring and `backend/capabilities/*` for capability implementation.
- Workspace builder fields and defaults: change `backend/orchestration/workspace_builder.py` and related frontend field rendering in `WorkspacesPage.jsx`.
- Repository behavior and migrations: change `backend/repositories/sqlite_backed.py` or `file_backed.py`; keep exports in `backend/repositories/__init__.py` compatible.
- Worker behavior: change `backend/worker/service.py` and focused worker tests.
- Frontend route/page behavior: change `frontend/src/pages/*`, shared hooks under `frontend/src/hooks/`, and shared helpers under `frontend/src/lib/`.
- Frontend build configuration: change `frontend/vite.config.js`.
- Browser extension shell, page execution, side panel, or manifest: change
  `apps/browser-extension/`; keep portable adapter/message contracts under
  `packages/` and preserve the no-submit boundary.
- Verification commands: change root `package.json`, `frontend/package.json`, and this document.

## Verification Baseline

- `npm run check` runs backend and frontend checks.
- `npm run check:backend` runs Ruff plus a fast pytest subset: backend application, SQLite repositories, worker service, phase contracts, and job dedupe tests.
- `npm run check:backend:api` runs the slower backend API sweep.
- `npm run check:backend:full` runs the full pytest suite and is the pre-merge sweep.
- `npm run check:frontend` runs the Vite production build. There is no separate frontend lint command yet.
- `npm run check:extension` runs extension type checks, unit tests, a production WXT
  build, and the manifest/source audit.
- `npm run check:assisted-apply` also launches the packaged MV3 extension in a
  Playwright persistent Chromium context.
- Full pytest can touch broader connector and document-generation tests and should be treated as slower than the fast local check.

## Durable References

- Root overview: `README.md`.
- Longer architecture narrative: `ARCHITECTURE.md`.
- Source-control policy: `docs/architecture/source_control_artifact_policy.md`.
- Cleanup runbook: `docs/architecture/repository_hygiene_runbook.md`.
- API route extraction guide: `docs/architecture/api_route_extraction.md`.
- Backend service/repository boundaries: `docs/architecture/backend_service_repository_boundaries.md`.
- Historical report index: `docs/reports/README.md`.
