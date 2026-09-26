> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Backend HTTP API and CLI (WS-1)

Primary doc for the stdlib HTTP server (`backend/api/**`) and the single CLI entry point `workspace_runner.py`. Worker *behaviour* behind `run-worker`/`process-next` is WS-2's doc [`backend-workers-and-orchestration.md`](backend-workers-and-orchestration.md). Auth internals are WS-6's [`security-and-auth.md`](security-and-auth.md). Customer service logic behind the routes is WS-4's [`../05-subsystems/personalized-jobs-and-customer-app-services.md`](../05-subsystems/personalized-jobs-and-customer-app-services.md). Records are in WS-5's [`domain-model.md`](domain-model.md), and tests in WS-10's [`../04-testing/test-suite-map.md`](../04-testing/test-suite-map.md).

All claims are static reads of `58a96674` (tests not executed; see §7). "LIVE PRODUCTION = UNKNOWN."

---

## 1. Purpose and user-facing capabilities

- **One JSON/HTTP API process** (`ThreadingHTTPServer` + `BaseHTTPRequestHandler`, no framework) serving:
  - the Runr web app (Clerk JWT bearer),
  - the Assisted Apply Chrome extension (exact-origin extension sessions),
  - provider webhooks (Clerk, Creem),
  - public health/readiness probes and local signed-object downloads.
- **Capability groups exposed** (route counts from the registry, §3):
  - health/status (4);
  - Assisted Apply web and extension endpoints (27);
  - personalized jobs feed (13);
  - customer billing/auth/settings/account/webhooks (10, residing in `routes/admin.py`);
  - Career Profiles and Career Evidence family (105);
  - documents/CV upload/ATS export (11);
  - tracker/referrals/outreach/Google OAuth callback (14);
  - workspaces/builder/templates/runs/workers (24);
  - local storage signed objects (1).
- **CLI** `workspace_runner.py` (24 subcommands): starts the API (`serve-api`) and runs workers (`run-worker`, `process-next`). It also offers operator/local-admin commands for users, tokens, secrets, workspaces, runs, and career-URL discovery.
- **Not a capability:** the admin dashboard/analytics/users/tokens/secrets HTTP API was RETIRED in `dd47acf9` (merged by `550ee00a`). Only residue remains (§9, §10). WS-11 owns `06-history-and-provenance/retired-features.md`.

## 2. Owned paths and governing instructions

| Path | Files | Lines @58a96674 | Role |
|---|---:|---:|---|
| `backend/api/__init__.py` | 1 | 3 | re-exports `serve_api` |
| `backend/api/server.py` | 1 | 9,367 | handler class, CORS/auth helpers, shared payload builders, `serve_api` |
| `backend/api/telemetry.py` | 1 | 127 | per-request `RequestTelemetry` (log-only) |
| `backend/api/routes/` | 31 | 6,429 | `__init__.py` (wiring), `registry.py`, `route_support.py`, 28 domain modules (27 wired + `career_evidence_fixture.py` test-only) |
| **`backend/api/**` total** | **34** | **19,013** (with `wc`) | |
| `workspace_runner.py` | 1 | 400 | CLI, 24 subcommands |

Governing instructions and specs:
- **`AGENTS.md` (root).** Repo-wide agent rules; no API-specific section.
- **`docs/architecture/api_route_extraction.md`.** Route-module conventions (`register_routes`, `ApiRouteContext`, `/v1` normalization).
  - Checked against code: registry/handler rules match.
  - Its module-ownership list is **stale**: it still says `admin.py` owns "analytics, users, secrets" (see WS1-G6).
- **`docs/deployment/runtime.md`.** Role `api` → `workspace_runner.py serve-api` on `0.0.0.0:$PORT` (runtime.md:40). This matches `deploy/start.sh:29-39`. Deployment itself is WS-7.
- **`docs/assisted-apply/runr-assisted-apply-ticket-pack.md` and `docs/architecture/assisted_apply_*`.** Protocol history for the extension routes. The subsystem doc is WS-9 `05-subsystems/assisted-apply.md`.
- **Env contract.** `backend/config/env_schema.py`:
  - `RENDER_FRONTEND_EXTERNAL_HOSTNAME` (:188) and `RUNR_ASSISTED_APPLY_EXTENSION_ORIGINS` (:193);
  - production rejects a wildcard in `BACKEND_ALLOWED_ORIGINS` (:416-418);
  - production requires exact extension origins (:422-432).
  - Owner: WS-7.

## 3. Entry points and registered routes/commands

### 3.1 Process entry

| Entry | Code | Notes |
|---|---|---|
| `python workspace_runner.py [--data-dir .backend_data] [--storage sqlite\|file] [--log-level] serve-api [--host 127.0.0.1] [--port 8000]` | `workspace_runner.py:178-191` | Calls `validate_environment()` (:183), then `serve_api(...)`. |
| `backend.api.serve_api` | `backend/api/server.py:9343-9367` | Runs `load_project_dotenv()` and `validate_environment()` again, then `create_backend(data_dir, storage_backend)`. Parses `BACKEND_ALLOWED_ORIGINS` (`route_support.py:128-137`) and `RUNR_ASSISTED_APPLY_EXTENSION_ORIGINS` (`route_support.py:140-149`; a wildcard or non-extension value raises `ValueError` at startup). Then `ThreadingHTTPServer((host, port), build_handler(...)).serve_forever()`. |
| Container role `api` | `deploy/start.sh:29-39` | `--host ${RUNR_API_HOST:-0.0.0.0} --port ${PORT:-8000}`; `Dockerfile.api:59` copies `workspace_runner.py`. |

### 3.2 Registration and dispatch

1. **Registry build.** `server.py:8629` `build_handler` calls `build_route_registry()` once per server (`routes/__init__.py:36-70`).
   - It calls 27 `register_routes(registry)` functions in a fixed order: system, assisted_apply ×6, acquisition_catalog, admin, career_profiles, master_cv, application_bindings, career_evidence, cv_bullet_suggestions, motivation_letters, career_profile_evidence, evidence_recommendation, source_text_review, storage, career_memory, evidence_items, evidence_questions, documents, evidence, evidence_library, tracker, work_experiences, workspace.
   - `career_evidence_fixture.py` is **not** wired. Only tests import it (`tests/test_cp042r.py:172`).
2. **Route model.** `registry.py:158-167` `ApiRoute(method, name, handler, auth_required, matcher)`.
   - `exact()` (:177-195) matches the whole segment tuple.
   - `prefix()` (:197-228) matches a leading tuple; `{param}` placeholders accept any non-empty segment. Default `auth_required=True`.
3. **Request parsing.** `server.py:8908-8913` strips the trailing `/`, splits segments, and drops a leading `v1` (`route_support.py:61-64`). So `/v1/x` and `/x` are equivalent. Query comes from `parse_qs`.
4. **Dispatch.** `do_GET/do_POST/do_PUT/do_DELETE` (`server.py:9193-9335`) each call `_dispatch_route(method, …, auth_required=False)` first, then `auth_required=True`.
   - `RouteRegistry.dispatch` (`registry.py:230-241`) walks routes **in registration order**. It skips routes whose `auth_required` differs from the pass, sets `handler._matched_route_name`, and calls the handler.
   - A handler returning `False` falls through to the next match. `None` or `True` ends dispatch.
   - With no match: 404 `{"error":{"code":"not_found"}}`. POST/PUT read and discard the body first (`server.py:9241`, `:9278`).
5. **`auth_required` is only a dispatch-pass partition, not enforcement.** Each handler must call `_auth_context()`/`require_identity()`/`require_scope()`/an extension-session check itself (§4.2).
6. **`do_OPTIONS`** (`server.py:9176-9191`) applies the origin policy and returns 204 with CORS headers.
7. **No `do_PATCH`/`do_HEAD`.** `BaseHTTPRequestHandler` answers those methods with 501 and no CORS headers (WS1-G1).

### 3.3 Complete registered route table

**Derivation.** A read-only Python `ast` script (no imports of Runr code) read `git show 58a96674:backend/api/routes/__init__.py`, took the `register_routes` call order inside `build_route_registry`, and extracted each `registry.exact/prefix(...)` call in every wired module. The fields are method, segments, handler, `auth_required` (default `True`), `name`, and line. The script was run once in a scratch directory and not committed; the snippet is in §7.

**Totals.**

| Measure | Count |
|---|---|
| Routes | 207 (62 exact, 145 prefix) |
| By method | GET 74, POST 86, PUT 23, PATCH 3, DELETE 21 |
| `auth_required` | False 26, True 181 |
| Modules | 27 |

**Reading the table:**
- Order = dispatch order within an auth pass.
- Path pattern `/*` = prefix match; `{x}` = any non-empty segment; all paths also answer under `/v1`.
- The "Pass" column is `auth_required`: `no` = public pass, where the handler does its own auth or none.

| # | Route name | Method | Kind | Path pattern | Module:line `handler` | Pass (auth_required) |
|---:|---|---|---|---|---|---|
| 1 | `system.status` | GET | exact | `/` | system.py:13 `_get_service_status` | no |
| 2 | `system.health` | GET | exact | `/health` | system.py:14 `_get_health` | no |
| 3 | `system.health.live` | GET | exact | `/health/live` | system.py:15 `_get_liveness` | no |
| 4 | `system.health.ready` | GET | exact | `/health/ready` | system.py:16 `_get_readiness` | no |
| 5 | `assisted_apply.extension.connection_requests.create` | POST | exact | `/assisted-apply/extension/connection-requests` | assisted_apply.py:31 `_create_extension_connection_request` | no |
| 6 | `assisted_apply.extension.token.exchange` | POST | exact | `/assisted-apply/extension/token` | assisted_apply.py:38 `_exchange_extension_authorization` | no |
| 7 | `assisted_apply.extension.session.verify` | POST | exact | `/assisted-apply/extension/session/verify` | assisted_apply.py:45 `_verify_extension_session` | no |
| 8 | `assisted_apply.extension.session.delete` | DELETE | exact | `/assisted-apply/extension/session` | assisted_apply.py:52 `_delete_extension_session` | no |
| 9 | `assisted_apply.extension.preferences.update` | PUT | exact | `/assisted-apply/extension/preferences` | assisted_apply.py:59 `_update_extension_preferences` | no |
| 10 | `assisted_apply.web.connection.get` | GET | exact | `/assisted-apply/connection` | assisted_apply.py:67 `_get_web_connection` | yes |
| 11 | `assisted_apply.web.connection_requests.action` | POST | prefix | `/assisted-apply/connection-requests/*` | assisted_apply.py:74 `_handle_web_connection_action` | yes |
| 12 | `assisted_apply.web.preferences.update` | PUT | exact | `/assisted-apply/preferences` | assisted_apply.py:81 `_update_web_preferences` | yes |
| 13 | `assisted_apply.web.sessions.delete` | DELETE | prefix | `/assisted-apply/sessions/*` | assisted_apply.py:88 `_delete_owned_web_session` | yes |
| 14 | `assisted_apply.extension.linkedin_connections.sync` | POST | exact | `/assisted-apply/extension/linkedin-connections` | assisted_apply_linkedin.py:10 `_sync_linkedin_connections` | no |
| 15 | `assisted_apply.packages.create` | POST | exact | `/assisted-apply/packages` | assisted_apply_packages.py:31 `_create_package` | yes |
| 16 | `assisted_apply.packages.prepare` | POST | exact | `/assisted-apply/packages/prepare` | assisted_apply_packages.py:38 `_prepare_package` | yes |
| 17 | `assisted_apply.packages.launch` | POST | exact | `/assisted-apply/packages/launch` | assisted_apply_packages.py:45 `_launch_package` | yes |
| 18 | `assisted_apply.extension.packages.bind` | POST | exact | `/assisted-apply/extension/packages/bind` | assisted_apply_packages.py:54 `_bind_package` | no |
| 19 | `assisted_apply.extension.packages.get` | GET | exact | `/assisted-apply/extension/packages` | assisted_apply_packages.py:61 `_get_package_for_extension` | no |
| 20 | `assisted_apply.extension.packages.post` | POST | exact | `/assisted-apply/extension/packages` | assisted_apply_packages.py:68 `_get_package_for_extension_post` | no |
| 21 | `assisted_apply.extension.document_grants.create` | POST | exact | `/assisted-apply/extension/document-grants` | assisted_apply_packages.py:75 `_create_document_grant` | no |
| 22 | `assisted_apply.extension.document_grants.download` | POST | exact | `/assisted-apply/extension/document-grants/download` | assisted_apply_packages.py:82 `_download_document_grant` | no |
| 23 | `assisted_apply.extension.corrections.create` | POST | exact | `/assisted-apply/extension/corrections` | assisted_apply_packages.py:89 `_save_correction` | no |
| 24 | `assisted_apply.extension.standard_answers.create` | POST | exact | `/assisted-apply/extension/standard-answers` | assisted_apply_packages.py:96 `_save_exact_standard_answer` | no |
| 25 | `assisted_apply.extension.application_outcomes.create` | POST | exact | `/assisted-apply/extension/application-outcomes` | assisted_apply_packages.py:103 `_respond_to_application_outcome` | no |
| 26 | `assisted_apply.preparations.create` | POST | exact | `/assisted-apply/preparations` | assisted_apply_preparations.py:19 `_create` | yes |
| 27 | `assisted_apply.preparations.read` | GET | prefix | `/assisted-apply/preparations/*` | assisted_apply_preparations.py:20 `_read` | yes |
| 28 | `assisted_apply.preparations.action` | POST | prefix | `/assisted-apply/preparations/*` | assisted_apply_preparations.py:21 `_action` | yes |
| 29 | `assisted_apply.extension.preparations.report` | POST | exact | `/assisted-apply/extension/preparations/report` | assisted_apply_preparations.py:22 `_report` | no |
| 30 | `assisted_apply.extension.preparations.action` | POST | exact | `/assisted-apply/extension/preparations/action` | assisted_apply_preparations.py:23 `_extension_action` | no |
| 31 | `assisted_apply.telemetry.events.receive` | POST | exact | `/assisted-apply/telemetry/events` | assisted_apply_telemetry.py:44 `_receive_telemetry_events` | no |
| 32 | `personalized_jobs.read` | GET | exact | `/personalized-jobs` | acquisition_catalog.py:10 `_handle_get` | yes |
| 33 | `personalized_jobs.preferences.read` | GET | exact | `/personalized-jobs/preferences` | acquisition_catalog.py:11 `_handle_preferences` | yes |
| 34 | `personalized_jobs.preferences.write` | PUT | exact | `/personalized-jobs/preferences` | acquisition_catalog.py:12 `_handle_preferences` | yes |
| 35 | `personalized_jobs.preferences.patch` | PATCH | exact | `/personalized-jobs/preferences` | acquisition_catalog.py:13 `_handle_preferences` | yes |
| 36 | `personalized_jobs.saved_search.read` | GET | exact | `/personalized-jobs/saved-search` | acquisition_catalog.py:14 `_handle_saved_search` | yes |
| 37 | `personalized_jobs.saved_search.write` | PUT | exact | `/personalized-jobs/saved-search` | acquisition_catalog.py:15 `_handle_saved_search` | yes |
| 38 | `personalized_jobs.saved_search.post` | POST | exact | `/personalized-jobs/saved-search` | acquisition_catalog.py:16 `_handle_saved_search` | yes |
| 39 | `personalized_jobs.hidden.read` | GET | exact | `/personalized-jobs/hidden` | acquisition_catalog.py:17 `_handle_hidden` | yes |
| 40 | `personalized_jobs.report` | POST | exact | `/personalized-jobs/report` | acquisition_catalog.py:18 `_handle_report_without_job` | yes |
| 41 | `personalized_jobs.company.read_prefix` | GET | prefix | `/personalized-jobs/companies/{company_id}/*` | acquisition_catalog.py:19 `_handle_company` | yes |
| 42 | `personalized_jobs.job.read` | GET | prefix | `/personalized-jobs/*` | acquisition_catalog.py:20 `_handle_job_or_feed` | yes |
| 43 | `personalized_jobs.job.action` | POST | prefix | `/personalized-jobs/*` | acquisition_catalog.py:21 `_handle_job_action` | yes |
| 44 | `personalized_jobs.job.delete` | DELETE | prefix | `/personalized-jobs/*` | acquisition_catalog.py:22 `_handle_job_delete` | yes |
| 45 | `admin.billing.plans` | GET | exact | `/billing/plans` | admin.py:24 `_handle_get` | no |
| 46 | `admin.auth.me` | GET | exact | `/auth/me` | admin.py:25 `_handle_get` | yes |
| 47 | `admin.billing` | GET | prefix | `/billing/*` | admin.py:26 `_handle_get` | yes |
| 48 | `admin.scrapeops` | GET | prefix | `/scrapeops/*` | admin.py:27 `_handle_get` | yes |
| 49 | `admin.settings` | GET | exact | `/settings` | admin.py:28 `_handle_get` | yes |
| 50 | `admin.webhooks.clerk` | POST | exact | `/webhooks/clerk` | admin.py:29 `_handle_post` | no |
| 51 | `admin.webhooks.creem` | POST | exact | `/webhooks/creem` | admin.py:30 `_handle_post` | no |
| 52 | `admin.billing.post` | POST | prefix | `/billing/*` | admin.py:31 `_handle_post` | yes |
| 53 | `admin.settings.put` | PUT | exact | `/settings` | admin.py:32 `_handle_put` | yes |
| 54 | `admin.account.delete` | DELETE | exact | `/account` | admin.py:33 `_handle_delete` | yes |
| 55 | `career_profiles.list` | GET | prefix | `/career-profiles/*` | career_profiles.py:25 `_handle_list_get` | yes |
| 56 | `career_profiles.create` | POST | prefix | `/career-profiles/*` | career_profiles.py:26 `_handle_create` | yes |
| 57 | `career_profiles.get` | GET | prefix | `/career-profiles/{profile_id}/*` | career_profiles.py:27 `_handle_get` | yes |
| 58 | `career_profiles.update` | PUT | prefix | `/career-profiles/{profile_id}/*` | career_profiles.py:30 `_handle_update` | yes |
| 59 | `career_profiles.delete` | DELETE | prefix | `/career-profiles/{profile_id}/*` | career_profiles.py:33 `_handle_delete` | yes |
| 60 | `career_profiles.bind` | POST | prefix | `/career-profiles/{profile_id}/bind/*` | career_profiles.py:36 `_handle_bind` | yes |
| 61 | `career_profiles.unbind` | DELETE | prefix | `/career-profiles/{profile_id}/bind/*` | career_profiles.py:39 `_handle_unbind` | yes |
| 62 | `career_profiles.bind_baseline_cv` | POST | prefix | `/career-profiles/{profile_id}/baseline-cv/*` | career_profiles.py:42 `_handle_bind_baseline_cv` | yes |
| 63 | `career_profiles.unbind_baseline_cv` | DELETE | prefix | `/career-profiles/{profile_id}/baseline-cv/*` | career_profiles.py:45 `_handle_unbind_baseline_cv` | yes |
| 64 | `career_profiles.rebind_review` | POST | prefix | `/career-profiles/{profile_id}/rebind-review/*` | career_profiles.py:48 `_handle_rebind_review` | yes |
| 65 | `career_profiles.rebind_confirm` | POST | prefix | `/career-profiles/{profile_id}/rebind-confirm/*` | career_profiles.py:51 `_handle_rebind_confirm` | yes |
| 66 | `career_profiles.baseline_cv_replacement_preview` | POST | prefix | `/career-profiles/{profile_id}/baseline-cv-replacement-preview/*` | career_profiles.py:54 `_handle_baseline_cv_replacement_preview` | yes |
| 67 | `career_profiles.baseline_cv_replacement_confirm` | POST | prefix | `/career-profiles/{profile_id}/baseline-cv-replacement-confirm/*` | career_profiles.py:57 `_handle_baseline_cv_replacement_confirm` | yes |
| 68 | `master_cv.get` | GET | exact | `/master-cv` | master_cv.py:32 `_handle_get` | yes |
| 69 | `master_cv.update` | PUT | exact | `/master-cv` | master_cv.py:33 `_handle_update` | yes |
| 70 | `master_cv.export` | GET | exact | `/master-cv/export` | master_cv.py:34 `_handle_export` | yes |
| 71 | `master_cv.tailor` | POST | exact | `/master-cv/tailor` | master_cv.py:35 `_handle_tailor` | yes |
| 72 | `master_cv.entries.create` | POST | exact | `/master-cv/entries` | master_cv.py:36 `_handle_create_entry` | yes |
| 73 | `master_cv.entries.update` | PATCH | prefix | `/master-cv/entries/*` | master_cv.py:37 `_handle_update_entry` | yes |
| 74 | `master_cv.entries.delete` | DELETE | prefix | `/master-cv/entries/*` | master_cv.py:38 `_handle_delete_entry` | yes |
| 75 | `master_cv.bullets.create` | POST | prefix | `/master-cv/entries/*` | master_cv.py:39 `_handle_create_bullet` | yes |
| 76 | `master_cv.bullets.update` | PATCH | prefix | `/master-cv/bullets/*` | master_cv.py:40 `_handle_update_bullet` | yes |
| 77 | `master_cv.bullets.delete` | DELETE | prefix | `/master-cv/bullets/*` | master_cv.py:41 `_handle_delete_bullet` | yes |
| 78 | `master_cv.bullets.guidance` | GET | prefix | `/master-cv/bullets/*` | master_cv.py:42 `_handle_guidance` | yes |
| 79 | `master_cv.bullets.improve` | POST | prefix | `/master-cv/bullets/*` | master_cv.py:43 `_handle_improve` | yes |
| 80 | `application_bindings.list` | GET | prefix | `/career-profiles/{profile_id}/application-bindings/*` | application_bindings.py:20 `_handle_list` | yes |
| 81 | `application_bindings.create` | POST | prefix | `/career-profiles/{profile_id}/application-bindings/*` | application_bindings.py:24 `_handle_create` | yes |
| 82 | `application_bindings.get` | GET | prefix | `/career-profiles/{profile_id}/application-bindings/{binding_id}/*` | application_bindings.py:28 `_handle_get` | yes |
| 83 | `application_bindings.delete` | DELETE | prefix | `/career-profiles/{profile_id}/application-bindings/{binding_id}/*` | application_bindings.py:32 `_handle_delete` | yes |
| 84 | `career_evidence.list` | GET | prefix | `/career-profiles/{profile_id}/evidence/*` | career_evidence.py:15 `_handle_list` | yes |
| 85 | `career_evidence.create` | POST | prefix | `/career-profiles/{profile_id}/evidence/*` | career_evidence.py:17 `_handle_create` | yes |
| 86 | `career_evidence.get` | GET | prefix | `/career-profiles/{profile_id}/evidence/{evidence_id}/*` | career_evidence.py:19 `_handle_get` | yes |
| 87 | `career_evidence.update` | PUT | prefix | `/career-profiles/{profile_id}/evidence/{evidence_id}/*` | career_evidence.py:21 `_handle_update` | yes |
| 88 | `career_evidence.delete` | DELETE | prefix | `/career-profiles/{profile_id}/evidence/{evidence_id}/*` | career_evidence.py:23 `_handle_delete` | yes |
| 89 | `career_evidence.links.list` | GET | prefix | `/career-profiles/{profile_id}/evidence/{evidence_id}/links/*` | career_evidence.py:25 `_handle_list_links` | yes |
| 90 | `career_evidence.links.create` | POST | prefix | `/career-profiles/{profile_id}/evidence/{evidence_id}/links/*` | career_evidence.py:27 `_handle_create_link` | yes |
| 91 | `career_evidence.links.confirm` | POST | prefix | `/career-profiles/{profile_id}/evidence/{evidence_id}/links/{link_id}/confirm/*` | career_evidence.py:29 `_handle_confirm_link` | yes |
| 92 | `career_evidence.links.dismiss` | DELETE | prefix | `/career-profiles/{profile_id}/evidence/{evidence_id}/links/{link_id}/*` | career_evidence.py:32 `_handle_dismiss_link` | yes |
| 93 | `career_evidence.suggest_links` | POST | prefix | `/career-profiles/{profile_id}/evidence/{evidence_id}/suggest-links/*` | career_evidence.py:35 `_handle_suggest_links` | yes |
| 94 | `career_evidence.suggest_all` | POST | prefix | `/career-profiles/{profile_id}/evidence/suggest-all/*` | career_evidence.py:37 `_handle_suggest_all` | yes |
| 95 | `cv_bullet_suggestions.generate` | POST | prefix | `/career-profiles/{profile_id}/cv-bullet-suggestions/*` | cv_bullet_suggestions.py:31 `_handle_generate` | yes |
| 96 | `cv_bullet_suggestions.list` | GET | prefix | `/career-profiles/{profile_id}/cv-bullet-suggestions/*` | cv_bullet_suggestions.py:38 `_handle_list` | yes |
| 97 | `cv_bullet_suggestions.get` | GET | prefix | `/career-profiles/{profile_id}/cv-bullet-suggestions/{suggestion_id}/*` | cv_bullet_suggestions.py:45 `_handle_get` | yes |
| 98 | `cv_bullet_suggestions.action` | PUT | prefix | `/career-profiles/{profile_id}/cv-bullet-suggestions/{suggestion_id}/actions/*` | cv_bullet_suggestions.py:52 `_handle_action` | yes |
| 99 | `cv_bullet_suggestions.accepted` | GET | prefix | `/career-profiles/{profile_id}/cv-bullet-suggestions-accepted/*` | cv_bullet_suggestions.py:60 `_handle_accepted` | yes |
| 100 | `motivation_letters.generate` | POST | exact | `/motivation-letters` | motivation_letters.py:26 `_handle_generate` | yes |
| 101 | `career_profile_evidence.list` | GET | prefix | `/career-profiles/{profile_id}/evidence/*` | career_profile_evidence.py:26 `_handle_list_evidence` | yes |
| 102 | `career_profile_evidence.get` | GET | prefix | `/career-profiles/{profile_id}/evidence/{evidence_id}/*` | career_profile_evidence.py:33 `_handle_get_evidence` | yes |
| 103 | `career_profile_evidence.verify` | POST | prefix | `/career-profiles/{profile_id}/evidence/{evidence_id}/verify/*` | career_profile_evidence.py:40 `_handle_verify` | yes |
| 104 | `career_profile_evidence.reject` | POST | prefix | `/career-profiles/{profile_id}/evidence/{evidence_id}/reject/*` | career_profile_evidence.py:47 `_handle_reject` | yes |
| 105 | `career_profile_evidence.defer` | POST | prefix | `/career-profiles/{profile_id}/evidence/{evidence_id}/defer/*` | career_profile_evidence.py:54 `_handle_defer` | yes |
| 106 | `career_profile_evidence.edit` | PUT | prefix | `/career-profiles/{profile_id}/evidence/{evidence_id}/edit/*` | career_profile_evidence.py:61 `_handle_edit` | yes |
| 107 | `evidence_recommendation.generate` | POST | prefix | `/career-profiles/{profile_id}/evidence-recommendations/*` | evidence_recommendation.py:17 `_handle_generate` | yes |
| 108 | `evidence_recommendation.get` | GET | prefix | `/career-profiles/{profile_id}/evidence-recommendations/{recommendation_id}/*` | evidence_recommendation.py:24 `_handle_get` | yes |
| 109 | `evidence_recommendation.set_match_status` | PUT | prefix | `/career-profiles/{profile_id}/evidence-recommendations/{recommendation_id}/matches/{match_id}/*` | evidence_recommendation.py:31 `_handle_set_match_status` | yes |
| 110 | `source_review.get` | GET | prefix | `/career-profiles/{profile_id}/sources/{source_id}/review/*` | source_text_review.py:21 `_handle_get_review` | yes |
| 111 | `source_review.update` | PUT | prefix | `/career-profiles/{profile_id}/sources/{source_id}/review/*` | source_text_review.py:26 `_handle_update_review` | yes |
| 112 | `source_review.confirm` | POST | prefix | `/career-profiles/{profile_id}/sources/{source_id}/confirm/*` | source_text_review.py:31 `_handle_confirm_review` | yes |
| 113 | `source_review.reject` | POST | prefix | `/career-profiles/{profile_id}/sources/{source_id}/reject/*` | source_text_review.py:36 `_handle_reject_review` | yes |
| 114 | `source_review.list` | GET | prefix | `/career-profiles/{profile_id}/sources/*` | source_text_review.py:41 `_handle_list_sources` | yes |
| 115 | `source_review.verified_texts` | GET | prefix | `/career-profiles/{profile_id}/verified-texts/*` | source_text_review.py:46 `_handle_verified_texts` | yes |
| 116 | `storage.objects` | GET | prefix | `/storage/objects/*` | storage.py:23 `_handle_get` | no |
| 117 | `career_memory.get` | GET | prefix | `/career-memory/*` | career_memory.py:16 `_handle_get` | yes |
| 118 | `career_memory.post` | POST | prefix | `/career-memory/*` | career_memory.py:17 `_handle_post` | yes |
| 119 | `evidence_items.next_review` | GET | exact | `/evidence-items/next-review` | evidence_items.py:46 `_handle_next_review` | yes |
| 120 | `evidence_items.readiness` | GET | exact | `/evidence-items/readiness` | evidence_items.py:48 `_handle_readiness` | yes |
| 121 | `evidence_items.ready_actions` | GET | exact | `/evidence-items/ready-actions` | evidence_items.py:50 `_handle_ready_actions` | yes |
| 122 | `evidence_items.journey_state` | GET | exact | `/evidence-items/journey-state` | evidence_items.py:52 `_handle_journey_state` | yes |
| 123 | `evidence_items.review_action` | POST | exact | `/evidence-items/review-action` | evidence_items.py:55 `_handle_review_action` | yes |
| 124 | `evidence_items.clear_spikes` | POST | exact | `/evidence-items/clear-spikes` | evidence_items.py:57 `_handle_clear_spikes` | yes |
| 125 | `evidence_items.confirm_inspect` | POST | exact | `/evidence-items/confirm-inspect` | evidence_items.py:59 `_handle_confirm_inspect` | yes |
| 126 | `evidence_items.answer_enrich` | POST | exact | `/evidence-items/answer-enrich` | evidence_items.py:61 `_handle_answer_enrich` | yes |
| 127 | `evidence_items.skip_question` | POST | exact | `/evidence-items/skip-question` | evidence_items.py:63 `_handle_skip_question` | yes |
| 128 | `evidence_items.get` | GET | prefix | `/evidence-items/*` | evidence_items.py:66 `_handle_get` | yes |
| 129 | `evidence_items.post` | POST | prefix | `/evidence-items/*` | evidence_items.py:67 `_handle_post` | yes |
| 130 | `evidence_items.put` | PUT | prefix | `/evidence-items/*` | evidence_items.py:68 `_handle_put` | yes |
| 131 | `evidence_questions.get` | GET | prefix | `/evidence-items/questions/*` | evidence_questions.py:28 `_handle_get_question` | yes |
| 132 | `evidence_questions.answer` | POST | prefix | `/evidence-items/questions/{question_id}/answer/*` | evidence_questions.py:32 `_handle_answer` | yes |
| 133 | `evidence_questions.skip` | POST | prefix | `/evidence-items/questions/{question_id}/skip/*` | evidence_questions.py:36 `_handle_skip` | yes |
| 134 | `evidence_questions.dismiss` | POST | prefix | `/evidence-items/questions/{question_id}/dismiss/*` | evidence_questions.py:40 `_handle_dismiss` | yes |
| 135 | `evidence_questions.recalculate` | POST | prefix | `/evidence-items/questions/recalculate/*` | evidence_questions.py:44 `_handle_recalculate` | yes |
| 136 | `evidence_questions.history` | GET | prefix | `/evidence-items/questions/history/*` | evidence_questions.py:48 `_handle_history` | yes |
| 137 | `documents.cv` | GET | exact | `/cv` | documents.py:77 `_handle_get` | yes |
| 138 | `documents.cv_upload_status` | GET | prefix | `/cv-upload/*` | documents.py:78 `_handle_get` | yes |
| 139 | `documents.contracts` | GET | prefix | `/contracts/*` | documents.py:79 `_handle_get` | yes |
| 140 | `documents.documents` | GET | prefix | `/documents/*` | documents.py:80 `_handle_get` | yes |
| 141 | `documents.documents.post` | POST | prefix | `/documents/*` | documents.py:81 `_handle_post` | yes |
| 142 | `documents.cv_upload` | POST | exact | `/cv-upload` | documents.py:82 `_handle_post` | yes |
| 143 | `documents.profile_photo_upload` | POST | exact | `/profile-photo-upload` | documents.py:83 `_handle_post` | yes |
| 144 | `documents.ats` | POST | prefix | `/ats/*` | documents.py:84 `_handle_post` | yes |
| 145 | `documents.run_generation` | POST | prefix | `/runs/*` | documents.py:85 `_handle_post` | yes |
| 146 | `documents.documents.put` | PUT | prefix | `/documents/*` | documents.py:86 `_handle_put` | yes |
| 147 | `documents.documents.delete` | DELETE | prefix | `/documents/*` | documents.py:87 `_handle_delete` | yes |
| 148 | `evidence.list_states` | GET | prefix | `/evidence-states/*` | evidence.py:22 `_handle_list_states` | yes |
| 149 | `evidence.list` | GET | prefix | `/evidence/*` | evidence.py:26 `_handle_list_evidence` | yes |
| 150 | `evidence.create` | POST | prefix | `/evidence/*` | evidence.py:30 `_handle_create_evidence` | yes |
| 151 | `evidence.get` | GET | prefix | `/evidence/{evidence_id}/*` | evidence.py:34 `_handle_get_evidence` | yes |
| 152 | `evidence.update` | PUT | prefix | `/evidence/{evidence_id}/*` | evidence.py:38 `_handle_update_evidence` | yes |
| 153 | `evidence.transition` | POST | prefix | `/evidence/{evidence_id}/transition/*` | evidence.py:42 `_handle_transition` | yes |
| 154 | `evidence.history` | GET | prefix | `/evidence/{evidence_id}/history/*` | evidence.py:46 `_handle_list_history` | yes |
| 155 | `evidence.delete` | DELETE | prefix | `/evidence/{evidence_id}/*` | evidence.py:50 `_handle_delete_evidence` | yes |
| 156 | `evidence_library.list` | GET | prefix | `/career-profiles/{profile_id}/experiences/{experience_id}/evidence/*` | evidence_library.py:16 `_handle_list` | yes |
| 157 | `evidence_library.create` | POST | prefix | `/career-profiles/{profile_id}/experiences/{experience_id}/evidence/*` | evidence_library.py:23 `_handle_create` | yes |
| 158 | `evidence_library.get` | GET | prefix | `/career-profiles/{profile_id}/experiences/{experience_id}/evidence/{evidence_id}/*` | evidence_library.py:30 `_handle_get` | yes |
| 159 | `evidence_library.update` | PUT | prefix | `/career-profiles/{profile_id}/experiences/{experience_id}/evidence/{evidence_id}/*` | evidence_library.py:37 `_handle_update` | yes |
| 160 | `evidence_library.delete` | DELETE | prefix | `/career-profiles/{profile_id}/experiences/{experience_id}/evidence/{evidence_id}/*` | evidence_library.py:44 `_handle_delete` | yes |
| 161 | `tracker.google.callback` | GET | exact | `/tracker/email-integration/google/callback` | tracker.py:29 `_handle_get` | no |
| 162 | `tracker.referrals` | GET | prefix | `/referrals/*` | tracker.py:30 `_handle_get` | yes |
| 163 | `tracker.tracker` | GET | prefix | `/tracker/*` | tracker.py:31 `_handle_get` | yes |
| 164 | `tracker.rejected_jobs` | GET | prefix | `/rejected-jobs/*` | tracker.py:32 `_handle_get` | yes |
| 165 | `tracker.people_discovery` | GET | prefix | `/runs/*` | tracker.py:33 `_handle_get` | yes |
| 166 | `tracker.tracker.post` | POST | prefix | `/tracker/*` | tracker.py:34 `_handle_post` | yes |
| 167 | `tracker.referrals.post` | POST | prefix | `/referrals/*` | tracker.py:35 `_handle_post` | yes |
| 168 | `tracker.outreach.post` | POST | prefix | `/outreach/*` | tracker.py:36 `_handle_post` | yes |
| 169 | `tracker.people_discovery.post` | POST | prefix | `/runs/*` | tracker.py:37 `_handle_post` | yes |
| 170 | `tracker.rejected_jobs.post` | POST | prefix | `/rejected-jobs/*` | tracker.py:38 `_handle_post` | yes |
| 171 | `tracker.referrals.put` | PUT | prefix | `/referrals/*` | tracker.py:39 `_handle_put` | yes |
| 172 | `tracker.tracker.put` | PUT | prefix | `/tracker/*` | tracker.py:40 `_handle_put` | yes |
| 173 | `tracker.referrals.delete` | DELETE | prefix | `/referrals/*` | tracker.py:41 `_handle_delete` | yes |
| 174 | `tracker.tracker.delete` | DELETE | prefix | `/tracker/*` | tracker.py:42 `_handle_delete` | yes |
| 175 | `work_experiences.list` | GET | prefix | `/career-profiles/{profile_id}/experiences/*` | work_experiences.py:20 `_handle_list` | yes |
| 176 | `work_experiences.create` | POST | prefix | `/career-profiles/{profile_id}/experiences/*` | work_experiences.py:22 `_handle_create` | yes |
| 177 | `work_experiences.get` | GET | prefix | `/career-profiles/{profile_id}/experiences/{experience_id}/*` | work_experiences.py:24 `_handle_get` | yes |
| 178 | `work_experiences.update` | PUT | prefix | `/career-profiles/{profile_id}/experiences/{experience_id}/*` | work_experiences.py:26 `_handle_update` | yes |
| 179 | `work_experiences.delete` | DELETE | prefix | `/career-profiles/{profile_id}/experiences/{experience_id}/*` | work_experiences.py:28 `_handle_delete` | yes |
| 180 | `work_experiences.extract` | POST | prefix | `/career-profiles/{profile_id}/experiences/extract/*` | work_experiences.py:30 `_handle_extract` | yes |
| 181 | `work_experiences.merge_suggestions` | GET | prefix | `/career-profiles/{profile_id}/experiences/merge-suggestions/*` | work_experiences.py:32 `_handle_merge_suggestions` | yes |
| 182 | `work_experiences.confirm_merge` | POST | prefix | `/career-profiles/{profile_id}/experiences/merge-suggestions/{suggestion_id}/confirm/*` | work_experiences.py:34 `_handle_confirm_merge` | yes |
| 183 | `work_experiences.dismiss_merge` | POST | prefix | `/career-profiles/{profile_id}/experiences/merge-suggestions/{suggestion_id}/dismiss/*` | work_experiences.py:38 `_handle_dismiss_merge` | yes |
| 184 | `workspace.workspaces` | GET | prefix | `/workspaces/*` | workspace.py:23 `_handle_get` | yes |
| 185 | `workspace.builder` | GET | prefix | `/workspace-builder/*` | workspace.py:24 `_handle_get` | yes |
| 186 | `workspace.templates` | GET | prefix | `/workflow-templates/*` | workspace.py:25 `_handle_get` | yes |
| 187 | `workspace.connectors` | GET | prefix | `/connectors/*` | workspace.py:26 `_handle_get` | yes |
| 188 | `workspace.generations` | GET | prefix | `/generations/*` | workspace.py:27 `_handle_get` | yes |
| 189 | `workspace.renderers` | GET | prefix | `/renderers/*` | workspace.py:28 `_handle_get` | yes |
| 190 | `workspace.runs` | GET | prefix | `/runs/*` | workspace.py:29 `_handle_get` | yes |
| 191 | `workspace.review_queue` | GET | prefix | `/review-queue/*` | workspace.py:30 `_handle_get` | yes |
| 192 | `workspace.artifacts` | GET | prefix | `/artifacts/*` | workspace.py:31 `_handle_get` | yes |
| 193 | `workspace.workers` | GET | prefix | `/workers/*` | workspace.py:32 `_handle_get` | yes |
| 194 | `workspace.career_url_discovery` | POST | prefix | `/career-url-discovery/*` | workspace.py:33 `_handle_post` | yes |
| 195 | `workspace.workspaces.post` | POST | prefix | `/workspaces/*` | workspace.py:34 `_handle_post` | yes |
| 196 | `workspace.quick_apply` | POST | prefix | `/quick-apply/*` | workspace.py:35 `_handle_post` | yes |
| 197 | `workspace.builder.post` | POST | prefix | `/workspace-builder/*` | workspace.py:36 `_handle_post` | yes |
| 198 | `workspace.templates.post` | POST | prefix | `/workflow-templates/*` | workspace.py:37 `_handle_post` | yes |
| 199 | `workspace.runs.post` | POST | prefix | `/runs/*` | workspace.py:38 `_handle_post` | yes |
| 200 | `workspace.workers.post` | POST | prefix | `/workers/*` | workspace.py:39 `_handle_post` | yes |
| 201 | `workspace.builder.put` | PUT | prefix | `/workspace-builder/*` | workspace.py:40 `_handle_put` | yes |
| 202 | `workspace.workspaces.put` | PUT | prefix | `/workspaces/*` | workspace.py:41 `_handle_put` | yes |
| 203 | `workspace.templates.put` | PUT | prefix | `/workflow-templates/*` | workspace.py:42 `_handle_put` | yes |
| 204 | `workspace.runs.put` | PUT | prefix | `/runs/*` | workspace.py:43 `_handle_put` | yes |
| 205 | `workspace.workspaces.delete` | DELETE | prefix | `/workspaces/*` | workspace.py:44 `_handle_delete` | yes |
| 206 | `workspace.templates.delete` | DELETE | prefix | `/workflow-templates/*` | workspace.py:45 `_handle_delete` | yes |
| 207 | `workspace.runs.delete` | DELETE | prefix | `/runs/*` | workspace.py:46 `_handle_delete` | yes |

Public-pass routes and how each authenticates itself:

| Routes | Authentication |
|---|---|
| system (#1-4) | none |
| `admin.billing.plans` (#45) | none |
| webhooks #50-51 | signature: `verify_clerk_webhook` (`admin.py:214`) and `verify_creem_webhook_signature` (`admin.py:220`) |
| `storage.objects` (#116) | HMAC-signed URL via `verify_signed_download` (`storage.py:30-47`) |
| `tracker.google.callback` (#161) | OAuth state |
| Assisted Apply extension routes (#5-9, 14, 18-25, 29-31) | extension session token bound to an exact extension origin, in the route module (e.g. `_authenticate_extension_session` in `assisted_apply_packages.py`); internals in WS-6/WS-9 |

### 3.4 CLI subcommands (`workspace_runner.py`)

Global flags (:70-72):
- `--data-dir` (default `.backend_data`)
- `--storage {sqlite,file}`
- `--log-level`

Every command runs `validate_environment()` (:183). Every command except `serve-api` builds `create_backend(...)` (:193). JSON output goes through `_print_json` → `redact_sensitive_data` (:37-38).

| # | Subcommand | Parser line | Key flags | Action (application method) |
|---:|---|---:|---|---|
| 1 | `list-workspaces` | 75 | – | `list_workspaces` (plain text) |
| 2 | `list-templates` | 76 | – | `list_workflow_templates` |
| 3 | `list-connectors` | 77 | – | `list_connectors` |
| 4 | `list-generations` | 78 | – | `list_generations` |
| 5 | `list-renderers` | 79 | – | `list_renderers` |
| 6 | `list-users` | 80 | – | `list_users` (prints emails, not redacted) |
| 7 | `discover-career-urls` | 81-85 | args from `backend/tools/discover_company_careers.py` | `run_from_args` |
| 8 | `list-workers` | 86-89 | `--limit --offset --status` | `list_workers` |
| 9 | `create-user` | 91-96 | `--email` (req), `--role {admin,editor,reviewer,viewer}`, `--workspace*` | `upsert_user` |
| 10 | `list-tokens` | 98-100 | `--user-id` (req), `--include-inactive` | `list_api_tokens` |
| 11 | `create-token` | 102-106 | `--user-id --name` (req), `--scope*`, `--expires-at` | `issue_api_token`; prints raw `access_token` |
| 12 | `bootstrap-dev-auth` | 108-114 | `--email admin@runr.local`, `--display-name`, `--token-name` | admin user + token; prints raw token and `api_base_url` `http://127.0.0.1:8000/v1` (:290) |
| 13 | `revoke-token` | 116-117 | `--token-id` | `revoke_api_token` |
| 14 | `list-secrets` | 119-120 | `--workspace-id` | `list_secrets` (public dicts) |
| 15 | `set-secret` | 122-129 | `--name` (req), `--provider {stored,env}`, `--value`, `--env-var-name` | `upsert_secret` (value passed on argv, WS1-G9) |
| 16 | `delete-secret` | 131-132 | `--secret-id` | `delete_secret` |
| 17 | `list-runs` | 134-137 | `--limit --status --workspace-id` | `list_runs` |
| 18 | `run` | 139-145 | `--workspace` (req), `--dry-run`, `--queue`, `--max-attempts`, `--override-json`, `--set k=v*` | `start_run(execute=not dry/queue, enqueue=queue, requested_by="workspace_runner")` |
| 19 | `cancel-run` | 147-148 | `--run-id` | `cancel_run` |
| 20 | `retry-run` | 150-151 | `--run-id` | `retry_run` |
| 21 | `resume-run` | 153-154 | `--run-id` | `resume_run` |
| 22 | `process-next` | 156-164 | `--no-auto-retry --worker-id --lease-seconds 60 --worker-role {WORKER_ROLES}` (default env `RUNR_WORKER_ROLE` or `customer`) | `WorkerService.process_next` → WS-2 |
| 23 | `run-worker` | 166-176 | as above, plus `--max-runs 0` and `--sleep-seconds 5.0` | `WorkerService.run_loop` → WS-2 |
| 24 | `serve-api` | 178-180 | `--host 127.0.0.1 --port 8000` | `serve_api` |

The parser defines **24** subcommands (`git show 58a96674:workspace_runner.py | grep -c "add_parser("` = 24). The "22" in the evidence package, audit row 33 and the Phase 2 brief comes from a single-line grep (`add_parser("name"` = 22) that misses the two calls whose name is on the next line: `discover-career-urls` (:81-84) and `bootstrap-dev-auth` (:108-111). See WS1-G11.


`_runtime_worker_id` (:41-65): in `RUNR_ENV` prod/production, it appends `_<hostname>_<pid>` to a configured worker id. An empty id becomes `cli_worker_<8 hex>`.

## 4. Inputs, outputs, storage and dependencies

### 4.1 Inputs/outputs at the HTTP layer
- **Inputs:**
  - JSON bodies via `_read_json_body` (`server.py:8899-8906`); must be a JSON object; the raw body is cached per request.
  - Size-limited bodies via `_read_limited_body` (:8873-8897); over the limit raises `RequestBodyTooLargeError` → 413.
  - Multipart via `_parse_multipart_file` (:1342).
- **Outputs:**
  - `_send_json` (:8765), `_send_no_content`, `_send_html`, and `_send_file` (reads the whole file into memory, :8988).
  - `_send_bytes` (`Cache-Control: no-store`).
  - `_send_redirect`, a 302 to a signed object-storage URL with `X-Runr-Storage-Redirect` (:9014-9042), used by `_send_portable_download` when storage `supports_direct_download` (:9044-9070).
  - All responses include CORS headers when the origin is allowed.
  - Response writes are no-ops after a client disconnect or once a response has started.
- **Error envelope:** `{"error":{"code","message"[,"details"]}}`. The quota error is the exception: `{"error":"quota_exceeded",…}` with 402 (:8851-8862).

### 4.2 Auth, CORS and extension-origin handling (HTTP layer only)

| Concern | Code | Behaviour |
|---|---|---|
| Browser origin allow-list | `_cors_origin` `server.py:8721-8734` | Origin allowed if `allow_all_origins` (`*` in `BACKEND_ALLOWED_ORIGINS`), in the normalized allow-list, the `RENDER_FRONTEND_EXTERNAL_HOSTNAME` origin (:8626-8628), **or any loopback host** (`route_support.py:115-120`), in all environments (WS1-G8). |
| Origin enforcement | `_enforce_origin_policy` :8760-8763 | A present but disallowed `Origin` raises `PermissionError` → 403 `forbidden` on OPTIONS/GET/PUT/DELETE and on POST. Exception: POST `/webhooks/clerk` and `/webhooks/creem` skip the check (:9232-9234). Requests without `Origin` pass. |
| Extension origins | :8725-8731, :8736-8746 | A `chrome-extension://<32 a-p>` origin is allowed **only** if it is in `RUNR_ASSISTED_APPLY_EXTENSION_ORIGINS` **and** the path is `/assisted-apply/extension/*` or exactly `/assisted-apply/telemetry/events`. Extension origins in `BACKEND_ALLOWED_ORIGINS` are dropped (`route_support.py:134`). |
| Originless extension calls | `_request_client_origin` :8950-8961 | On extension paths, when Chrome omits `Origin`, the `X-Runr-Extension-Origin` header is used. A non-extension origin on an extension path returns `""`. Session binding is enforced downstream (WS-6/WS-9). |
| CORS headers | :8748-8758 | Allow-Headers `Authorization, Content-Type, X-Runr-Document-Grant, X-Runr-Extension-Origin`; Allow-Methods `GET, POST, PUT, DELETE, OPTIONS` (no PATCH); Max-Age 600; `Vary: Origin`. |
| Bearer resolution | `_auth_context` :9091-9108 → `_resolve_auth_context` :7824 | Missing token → `PermissionError("Missing bearer token.")`. Clerk JWT vs legacy API token, with a process cache (:7734-7792). Inactive user → error. Cached per request. |
| Guards | :9110-9159 | `_require_identity`; `_require_clerk_identity` (auth method `clerk_jwt` and JWT authorized party ∈ allowed origins); `_require_scope`; `_require_acquisition_permission`; `_require_admin` (role `admin` + `TOKEN_SCOPE_ADMIN`; still present, only referenced by `ApiRouteContext.require_acquisition_permission` fallback `registry.py:125-133` and admin residue); `_require_workspace_access`; `_require_run_access`. |
| 401 vs 403 | `_is_unauthorized_permission_error` `route_support.py:43-58` | A `PermissionError` whose message contains token/session/JWT fragments → 401 with `WWW-Authenticate: Bearer`; otherwise 403. |

### 4.3 Exception → status mapping (identical in each `do_*`, `server.py:9205-9224` etc.)

| Exception | Status | Code |
|---|---|---|
| client disconnect errors | none (logged) | – |
| `PermissionError` (auth-like message) | 401 | `unauthorized` |
| `PermissionError` (other) | 403 | `forbidden` |
| `QuotaExceededError` | 402 | `quota_exceeded` |
| `KeyError` | 404 | `not_found` |
| `BackendValidationError` | 400 | `exc.error_code`, `details` |
| `AtsExportBlockedError` | 400 | `ats_export_blocked` |
| `RequestBodyTooLargeError` | 413 | `request_too_large` (POST only) |
| `ValueError` | 400 | `bad_request` |
| any other `Exception` | 500 | `internal_error`, message = `str(exc)` (WS1-G4) |

### 4.4 Dependencies
- **Application object.** `backend.bootstrap.create_backend` (`server.py:84`, `:9352`) supplies the services, repositories, `object_storage` and `analytics_store`. Service internals are covered by WS-4/WS-5; database and storage internals by the WS-5 domain model and the storage docs.
- **Integrations** imported by `server.py`:
  - `backend.integrations.clerk` (:172) and `backend.integrations.creem` (:183), for webhooks and checkout;
  - `backend.config.plans` (:87);
  - `backend.application.quota` (:51);
  - `backend.storage` (:171);
  - `backend.worker` (:191), used by the `workers` route.
- **Route-module coupling.** `admin.py`, `documents.py`, `storage.py`, `tracker.py` and `workspace.py` are marked `# ruff: noqa: F821`. They call `bind_server_globals` (`route_support.py:152-159`) at request time, which copies **every** `backend.api.server` global into the module. So their bodies use server helpers without importing them, and `server.py` imports `backend.api.routes` at the same time (`server.py:28`). This circular coupling is WS1-G5.
- **Observability.** `_finish_request_log` (`server.py:8678-8707`) logs JSON `api_request_timing` (method, id-redacted route shape from `_route_shape` :8643-8676, route name, status, duration, bytes, disconnect) to logger `backend.api.http`. `backend/api/telemetry.py` `RequestTelemetry.emit` logs to `backend.api.telemetry` (telemetry.py:82). Both are **log-only**; neither writes `analytics_events`.
- **`analytics_events` writers still live in code.**
  - API handlers call `application.emit_event` for `checkout_started` (`admin.py:307`), `account_deleted` (`admin.py:472`) and workspace-builder source validation (tested at `tests/test_backend_api.py:2581`, `:2658`).
  - The worker-side writer is `backend/adapters/stage_adapters.py` (WS-2/WS-5).
  - The HTTP ingestion endpoint `POST /analytics/events` is **not** registered (§9).

## 5. Important call/data flows

1. **Server start:** `workspace_runner.py:main` → `backend/api/__init__.py` `serve_api` → `server.py:serve_api` → `create_backend` → `build_handler` → `build_route_registry` → `ThreadingHTTPServer.serve_forever` (one thread per connection, no graceful-shutdown hook).
2. **Authenticated GET** (e.g. `GET /v1/personalized-jobs`):
   - `do_GET` → `_begin_request` → `_enforce_origin_policy` → `_parse_request` (drop `v1`);
   - public pass (no match) → auth pass → `personalized_jobs.read` (`acquisition_catalog.py:10`) → the handler calls `require_identity` → service (WS-4) → `_send_json`;
   - `_finish_request_log`.
3. **Extension call** (e.g. `POST /assisted-apply/extension/packages`):
   - `_cors_origin` allows only the exact extension origin on that path;
   - public pass → `assisted_apply_packages.py:68` `_get_package_for_extension_post` → extension-session authentication + Runr Pro check → payload.
4. **Webhook:** `POST /webhooks/creem` → origin check skipped → `admin.py:218-235` verifies `creem-signature` → `server.py:_handle_creem_webhook_event` (:8389).
5. **Local signed download:** `GET /storage/objects/<key>?expires&signature&download` → `storage.py:_handle_get` → `verify_signed_download` → `_send_bytes`. S3/R2 signed URLs bypass the API (`storage.py:21-22`).
6. **Prefix fall-through example:** the auth-pass GET prefixes `/runs/*` are `tracker.people_discovery` (#165) and `workspace.runs` (#190); POST `/runs/*` is tried in the order documents (#145) → tracker (#169) → workspace (#199). Each handler returns `False` when its sub-path does not match (the modules have 4 `return False` each).

## 6. Invariants, failure handling and recovery

- **I1 Registration order is semantic.** Overlapping prefixes resolve by order and by handlers returning `False`. Handlers that always return `True` (no `return False`) shadow later overlapping routes:
  - in `career_evidence.py`, `work_experiences.py`, `application_bindings.py`, `evidence.py`, `evidence_library.py`, `evidence_questions.py`;
  - e.g. `career_evidence.list/create` (#84-85) precede `career_profile_evidence.*` (#101-106) on the same `/career-profiles/{id}/evidence/*` shapes, and `work_experiences.get` (#177) precedes `merge_suggestions` (#181) (WS1-G3).
- **I2 Public pass first.** A public route can never be shadowed by an auth route. A public prefix would capture auth routes; only `storage.objects` is a public prefix, scoped to `/storage/objects`.
- **I3 Extension origins must be exact.** A wildcard or malformed value makes `serve_api` fail at startup (`route_support.py:142-148`). Production env validation adds the same rule (`env_schema.py:422-432`).
- **I4 The origin check precedes routing.** Except webhooks, a disallowed `Origin` never reaches a handler.
- **I5 One response per request.** `_response_started`/`_client_disconnected` guards (:8766, :8791, …). Disconnects are swallowed and logged (tests `tests/test_backend_api.py:430`, `:444`).
- **I6 Removed admin surfaces stay unregistered.** Guard `tests/test_customer_route_surface.py:4-13` asserts that no route name starts with `admin.dashboard|admin.users|admin.tokens|admin.secrets|admin.analytics`, and that `admin.billing`, `admin.settings` and `admin.account.delete` exist. `tests/test_backend_api.py:1109-1116` asserts `GET /dashboard` → 404.
- **I7 Failure/recovery.**
  - Unhandled exceptions → 500 per request; the process keeps serving.
  - Readiness `GET /health/ready` (`system.py:31-100`) raises (→ 500) when the database, object storage or production targets (libSQL/Turso, S3-compatible) are missing, and runs write probes.
  - There is no in-process retry. Restarts are the platform's (WS-7).
- **Account deletion** is a soft delete. It sets `is_active=False` and metadata `account_deleted_at`, cancels subscriptions, and emits `account_deleted` (`admin.py:454-492`). After that, `_auth_context` rejects the inactive user (`server.py:9099-9100`).
- **Checkout gate** fails closed: `phase_i_config(... "checkout_gate_enabled", False)` must be truthy (`admin.py:266-269`).
- **Career URL discovery over the API** is disabled: `POST /career-url-discovery/run` raises `PermissionError` (`workspace.py:381-382`). The CLI `discover-career-urls` remains.

## 7. Relevant tests and safe verification commands (not executed in Phase 2)

| Test | What it covers (by name/line) |
|---|---|
| `tests/test_backend_api.py` (5,776 lines, 119 `def test`) | HTTP-level handler via `build_handler`: bearer required (:484); Clerk vs legacy auth (:490, :507, :533); loopback/Render/disallowed CORS (:556, :566, :579); extension CORS exact and path-limited (:592); originless extension header (:621); extension-origin config rejects wildcards (:634); Clerk authorized-party guard (:647); extension connection exchange (:680); run/queue resources (:949); removed `/dashboard` 404 (:1109); workspace/builder/quick-apply; billing subscription with ScrapeOps usage (:2693); account delete (:2719); settings; CV upload limits/disconnects (:3214, :3225) |
| `tests/test_customer_route_surface.py` (13 lines) | Registry guard against the removed admin names (I6) |
| `tests/test_workspace_runner.py` (76 lines, 4 tests) | Only `_runtime_worker_id` (:7, :25, :36, :56). No parser/subcommand coverage (WS1-G7) |
| `tests/test_phase_a_routes.py` | Registry dispatch with a fake handler (catalog read-only) |
| `tests/test_assisted_apply_telemetry.py`, `tests/test_aa213_preparation.py` | Assisted Apply telemetry/preparation routes |
| `tests/test_master_cv.py`, `tests/test_phase_b_catalog.py`, `tests/test_phase_a_rc020.py`, `tests/test_phase_a_rc021.py`, `tests/test_career_url_discovery_security.py`, `tests/test_cp046r_production_gate.py`, `tests/test_rc010_first_acquisition_slice.py`, `tests/test_source_processing_pipeline.py` | Other tests that construct `build_handler`/`build_route_registry` |
| `tests/test_cp042r.py` | Registers the unwired `career_evidence_fixture` routes directly |
| `frontend/src/lib/analytics.test.js:42`, `frontend/src/lib/api.test.js:154` | Still assert that the frontend posts to `/analytics/events` (WS-8/WS-10) |

Safe verification commands (require a venv; **not executed in Phase 2**):
```bash
python -m pytest tests/test_backend_api.py tests/test_customer_route_surface.py tests/test_workspace_runner.py tests/test_phase_a_routes.py -q
python workspace_runner.py --help            # lists subcommands (needs env validation to pass)
git grep -n "segment_params\|query_params" 58a96674 -- backend/api/routes   # WS1-G2 evidence
git grep -n "'analytics'\|\"analytics\"" 58a96674 -- backend/api/routes      # only admin.py:239 (dead)
```
Route-table regeneration (read-only, no Runr imports). This is the script used for §3.3:
```python
import ast, subprocess
show = lambda p: subprocess.check_output(["git","show",f"58a96674:{p}"]).decode()
init = ast.parse(show("backend/api/routes/__init__.py"))
mods = {a.asname: n.module.rsplit(".",1)[1] for n in init.body if isinstance(n, ast.ImportFrom)
        and n.module.startswith("backend.api.routes.") for a in n.names if a.name == "register_routes"}
fn = next(n for n in init.body if isinstance(n, ast.FunctionDef) and n.name == "build_route_registry")
order = [mods[s.value.func.id] for s in fn.body if isinstance(s, ast.Expr) and getattr(s.value.func, "id", "") in mods]
for m in order:
    reg = next(f for f in ast.parse(show(f"backend/api/routes/{m}.py")).body if getattr(f, "name", "") == "register_routes")
    for c in (c for c in ast.walk(reg) if isinstance(c, ast.Call) and getattr(c.func, "attr", "") in ("exact", "prefix")):
        kw = {k.arg: ast.literal_eval(k.value) for k in c.keywords}
        print(ast.literal_eval(c.args[0]), c.func.attr, "/".join(ast.literal_eval(c.args[1])), kw.get("name"), kw.get("auth_required", True), f"{m}.py:{c.lineno}")
```

**Static path check (2026-09-14).** Every backticked repo path in this doc was checked with `git cat-file -e 58a96674:<path>`. The only non-resolving items are intentional: the deleted modules `backend/api/routes/acquisition_admin.py`, `enrichment_admin.py` and `job_import_admin.py` (REMOVED in `dd47acf9`); other workstreams' Phase 2 docs and this doc (not at baseline); short forms `routes/__init__.py` and `routes/admin.py` (= `backend/api/routes/...`, present); and route segments, route names or globs that are not file paths.
## 8. Historical decisions and supporting commits

`git log --oneline 58a96674 -- backend/api workspace_runner.py` (selected, newest first):

| SHA | Subject | Relevance |
|---|---|---|
| `dd47acf9` | Complete acquisition delivery and remove admin surfaces | Deleted `routes/acquisition_admin.py` (579), `enrichment_admin.py` (287) and `job_import_admin.py` (352). Also `admin.py` +1/−164, `server.py` −648, `assisted_apply_telemetry.py` −16 (removed admin-only `GET /assisted-apply/telemetry/operator-report`), `routes/__init__.py` −6 |
| `550ee00a` | Merge acquisition delivery and admin surface removal | Brings `dd47acf9` into the baseline line |
| `7251ae29` | feat(acquisition): reconcile producers inputs and runtime data | Last pre-removal change to the API and CLI |
| `619f24da`, `5b900167`, `4b339616`, `f63832ab` | perf: document library / run payload / auth session slimming | Document and auth hot paths |
| `ef78e256`, `0bdbfb04`, `6675338c` | Master CV backend / payload / workspace CV editor | `master_cv.py` routes (incl. the PATCH routes, WS1-G1) |
| `12f342fb`, `06a4cb17`, `fe314047`, `9a62e81b`, `fa5e4d3a`, `d99bf062`, `8b3587e1` | Admin/acquisition dashboards and consoles | **RETIRED** by `dd47acf9` |
| `c8c85f07` | fix: fail closed Creem checkout gate by default | Checkout invariant (§6) |
| `5a91380e` | reconstruct Phase I offline rollout evidence and disable career discovery API | API career discovery disabled |
| `5e674e1e` | fix: migrate Creem billing to Runr Pro | Billing offers/product ids |
| `92760a3a` | feat: sync LinkedIn connections from browser tab | `assisted_apply_linkedin.py` |
| `2e56d028` | Complete Assisted Apply foundation through AA-221 | Extension route family |
| `863a6d81`, `57c9936e`, `d8748aed`, `6761718e`, `c7cbb3ca`, `b197a928`, `93ed9290` | [CP-014], [CP-013], [CP-017], [CP-015], [CP-028], [CP-033R], [CP-010] | Added the modules affected by WS1-G2 and WS1-G3 |
| `fa5f32cb`, `ec49b716`, `c7bf7cbd`, `d6018c3e` | CLI evolution (workspace modularization, ScrapeOps, deployment prep, Render/Turso/R2 fixes) | `workspace_runner.py` |

**Changes since `848408f3`** (`git diff --numstat 848408f3 58a96674 -- backend/api workspace_runner.py`): `backend/api` +1/−2,052 across 7 files; `workspace_runner.py` unchanged.

| File | + | − |
|---|---:|---:|
| `backend/api/server.py` | 0 | 648 |
| `backend/api/routes/acquisition_admin.py` (deleted) | 0 | 579 |
| `backend/api/routes/job_import_admin.py` (deleted) | 0 | 352 |
| `backend/api/routes/enrichment_admin.py` (deleted) | 0 | 287 |
| `backend/api/routes/admin.py` | 1 | 164 |
| `backend/api/routes/assisted_apply_telemetry.py` | 0 | 16 |
| `backend/api/routes/__init__.py` | 0 | 6 |

The three deleted modules are absent at `58a96674` (intentionally; label REMOVED).

## 9. Current implementation status

| Capability | Classification |
|---|---|
| `serve-api` startup path | VERIFIED (static: `workspace_runner.py:178-191` → `server.py:9343-9367`; `deploy/start.sh:29-39` role `api`) |
| Route registry build, ordered two-pass dispatch, 404 fallback, `/v1` normalization | VERIFIED (static: `routes/__init__.py:36-70`, `registry.py:230-241`, `server.py:9193-9335`, `route_support.py:61-64`) |
| Complete route surface (207 routes / 27 modules) | VERIFIED (static AST extraction at 58a96674, §3.3) |
| CORS allow-list, extension-origin exact/path-limited policy, webhook origin bypass | VERIFIED (static: `server.py:8721-8763`, `:9232-9234`; covering tests exist but were not run) |
| Exception → HTTP status mapping, disconnect handling | VERIFIED (static: `server.py:9205-9335`) |
| Health/liveness/readiness | VERIFIED (static: `system.py:13-16` registered, handlers reachable in the public pass) |
| Customer billing plans/subscription/checkout/portal, `auth/me`, settings GET/PUT, `scrapeops/usage`, account delete, Clerk/Creem webhooks (`routes/admin.py` registered set) | VERIFIED (static: `admin.py:24-33` registered; matching branches at :42, :46, :70, :82, :108, :213, :218, :261, :325, :336, :382, :454). Functional behaviour: WS-4/WS-6 |
| Personalized jobs API (`/personalized-jobs*`, #32-44) | VERIFIED (static registration `acquisition_catalog.py:10-22`); authenticated payloads UNKNOWN (U10) |
| Assisted Apply web and extension routes (#5-31) at baseline | VERIFIED (static registration); functional internals are WS-9/WS-6 |
| `POST /assisted-apply/extension/profile-package` (`_get_profile_package_for_extension`) | UNKNOWN. UNMERGED (feature/admin-analytics-final-production @ ce3718b0), commit `0d7f2b5c`, +38 lines in `assisted_apply_packages.py`; absent at baseline; review ticket T03 |
| Documents, tracker, workspace, master CV (non-PATCH) routes | IMPLEMENTED-UNVERIFIED (registered; handlers reachable; tests exist, not run) |
| PATCH routes (`personalized_jobs.preferences.patch`, `master_cv.entries.update`, `master_cv.bullets.update`) | PARTIAL (static: registered, but no `do_PATCH` in `server.py` → 501 over HTTP; CORS omits PATCH; frontend uses PUT for preferences and no PATCH call found in `frontend/src`) |
| Career Evidence family using `context.segment_params`/`context.query_params` (`application_bindings`, `career_evidence`, `career_profile_evidence`, `evidence`, `evidence_library`, `evidence_questions`, `work_experiences`) | PARTIAL (static: the attributes do not exist on frozen `ApiRouteContext` `registry.py:71-77`, so the handler hits `AttributeError` → 500 once reached; the frontend calls `/career-profiles/{id}/evidence` at `frontend/src/components/careerProfile/CareerProfileEvidenceReview.jsx:26,42`; not executed) |
| Career evidence fixture routes (`/fixtures/career-evidence/*`) | IMPLEMENTED-UNVERIFIED (test-only; not wired in `build_route_registry`) |
| Request timing and telemetry logs | VERIFIED (static: `server.py:8678-8707`, `telemetry.py:53-82`; log-only) |
| CLI: 24 subcommands, redacted JSON output | VERIFIED (static: `workspace_runner.py:75-180`) |
| CLI worker commands (`process-next`, `run-worker`) | VERIFIED (static flag definitions); behaviour → WS-2 |
| Admin dashboard/users/tokens/secrets HTTP bodies in `admin.py` (GET :102 `dashboard`, :113/:127/:132 `users`, :154 `tokens`, :177/:196 `secrets`; POST :346/:351 `users`, :363 `secrets`; PUT :430 `users`, :436 `secrets`; DELETE :494/:500 `users`, :505 `secrets`) | RETIRED/HISTORICAL (unreachable: no registered matcher, e.g. `/users` and `/secrets` match no route → 404) |
| `POST /analytics/events` body (`admin.py:239-259`) | RETIRED/HISTORICAL (unreachable: no POST matcher for `analytics/events`; the frontend still posts to it, `frontend/src/lib/analytics.js:125` and `frontend/src/lib/api.js:267`, errors swallowed → 404) |
| `server.py` `_dashboard_payload` (:7358), `_dashboard_analytics_payload` (:7143), `_empty_dashboard_analytics` (:7310) and `_dashboard_*` helpers (:6355-7411) | RETIRED/HISTORICAL (dead: the only external caller is the unregistered `admin.py:105`; helpers called only inside that chain) |
| `_database_query_rows` "Admin reporting" helper (`server.py:8598-8608`) | UNKNOWN (no caller check performed beyond this module; candidate residue) |
| Admin route modules `acquisition_admin`/`enrichment_admin`/`job_import_admin`, operator-report route | RETIRED/HISTORICAL (deleted in `dd47acf9`). The feature branch `ce3718b0` still contains them (`git diff --stat 58a96674 ce3718b0 -- backend/api`: +2,109/−385 across 15 files). UNMERGED; must not be restored |

### Deployment evidence (documentary only)
- `docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md:75-78` (records Render `5dfdd106`):
  - the customer surface is `/jobs`, backed by the authenticated `/v1/personalized-jobs`;
  - an unauthenticated check reached Clerk sign-in;
  - authenticated Jobs API payloads were **not** verified (U10).
- The same handoff reports "Targeted admin-surface API checks: 3 passed" (documentary, not re-run).
- `render.yaml:98-105` declares `BACKEND_ALLOWED_ORIGINS`, `RUNR_ASSISTED_APPLY_EXTENSION_ORIGINS` and `RENDER_FRONTEND_EXTERNAL_HOSTNAME` for the API service (values not copied).
- None of this establishes current live state.

## 10. Confirmed gaps and unresolved questions

| ID | Gap / question | Evidence | Owner |
|---|---|---|---|
| **U7** (reformulated per audit N-1) | Owner decision: **(a) delete** the dead `POST /analytics/events` body (`admin.py:239-259`) and the dashboard residue (`admin.py:102-106`, `server.py:6355-7411`), plus the frontend emitter (`frontend/src/lib/analytics.js:125`, `frontend/src/lib/api.js:245,267`) and its tests (`analytics.test.js:42`, `api.test.js:154`); **or (b) re-register** a customer telemetry route. Option (b) needs a new route name outside the `admin.analytics` prefix blocked by `tests/test_customer_route_surface.py:9-11`, or a guard update. It would also revive `analytics_events` HTTP writes (WS-5 database impact). Today the endpoint 404s silently. WS-1 takes no position. | §9 rows; audit N-1 | Owner (WS-1 backend, WS-8 frontend, WS-5 table) |
| **U10** | Authenticated `/v1/personalized-jobs` payloads not verified in a signed-in browser. At the HTTP layer, routes #32-44 are registered and require identity inside handlers. Closing it needs a signed-in check; this is out of Phase 2 scope (no live calls). | handoff :78 | WS-4 (functional), owner sign-in |
| **C7(a)** | Admin residue bodies remain in `admin.py`. The guard test only asserts non-registration. | §9 | WS-1 / WS-11 |
| **WS1-G1** | PATCH routes registered (`acquisition_catalog.py:13`, `master_cv.py:37`, `master_cv.py:40`), but the handler has no `do_PATCH` and CORS Allow-Methods omits PATCH, so HTTP PATCH → 501. Either add `do_PATCH` (+CORS) or convert the routes to PUT/POST. | `server.py:8751`, `:9176-9335` | WS-1 |
| **WS1-G2** | Seven route modules read `context.segment_params`/`context.query_params`, which `ApiRouteContext` (`registry.py:71-77`) does not define. Expected result: 500 `internal_error` on these routes, including the evidence review called by the frontend. No test imports these modules at HTTP level. Verify by running a request test, then fix by adding parsed params to the context or rewriting the handlers. | `git grep segment_params` (§7) | WS-1 (+WS-10 test) |
| **WS1-G3** | Prefix shadowing: `career_evidence.*` (#84-94) captures `career_profile_evidence.*` (#101-106) shapes; `work_experiences.get/create` (#175-177) capture `extract`/`merge-suggestions` (#180-183). `evidence_items.get/post` (#128-129) precede `evidence_questions.*`; they return `False` at the end, but whether they claim `questions/...` first is unverified. | §3.3 order, §6 I1 | WS-1 |
| **WS1-G4** | 500 responses echo `str(exc)` to clients (`server.py:9224`, `:9264`, `:9299`, `:9333`). Possible internal detail leakage. | §4.3 | WS-6 review |
| **WS1-G5** | `bind_server_globals` injects all `server.py` globals into 5 route modules at request time (hidden circular dependency, `noqa: F821`). This blocks further extraction and static analysis. | `route_support.py:152-159` | WS-1 |
| **WS1-G6** | `docs/architecture/api_route_extraction.md` module-ownership list is stale (admin analytics/users/secrets). | §2 | WS-11 (doc owner) |
| **WS1-G7** | No CLI parser tests: `tests/test_workspace_runner.py` covers only `_runtime_worker_id`. | §7 | WS-10 |
| **WS1-G8** | Loopback origins are always CORS-allowed, including production (`server.py:8732`). Confirm this is intended. | §4.2 | WS-6 |
| **WS1-G9** | `set-secret --value` and `create-token`/`bootstrap-dev-auth` expose secret material via argv/stdout. Acceptable for a local operator tool; document or add stdin input. | `workspace_runner.py:129`, `:263`, `:280-292` | WS-6 |
| **WS1-G10** | Residue helper `_database_query_rows` ("Admin reporting", `server.py:8598`) may be dead after the admin removal; caller check pending. | §9 | WS-1 |
| **WS1-G11** | Erratum: `workspace_runner.py` has 24 subcommands, not 22 (brief, evidence package, audit row 33). Single-line grep undercount. | §3.4 | WS-12 / evidence errata |
| **T03** | Unmerged extension `profile-package` POST route (`ce3718b0`/`0d7f2b5c`) needs the never-submit review before any scoped PR. | §9 | WS-9 (route: WS-1) |

## Agent context and remaining work

**(a) Proposed agent context packet (WS-1 HTTP API and CLI)**
- **Required reading:**
  - this doc;
  - `backend/api/routes/registry.py`, `backend/api/routes/__init__.py`, `backend/api/routes/route_support.py`;
  - `backend/api/server.py:8611-9367` (handler, CORS, auth guards, dispatch, `serve_api`);
  - `workspace_runner.py`;
  - `docs/architecture/api_route_extraction.md` (noting WS1-G6);
  - [`security-and-auth.md`](security-and-auth.md) for auth internals.
- **Allowed paths:** `backend/api/**`, `workspace_runner.py`, matching tests (`tests/test_backend_api.py`, `tests/test_customer_route_surface.py`, `tests/test_workspace_runner.py`, `tests/test_phase_a_routes.py`) with WS-10 coordination.
- **Tests to run:**
  - `python -m pytest tests/test_backend_api.py tests/test_customer_route_surface.py tests/test_workspace_runner.py tests/test_phase_a_routes.py -q`;
  - plus the module-specific tests of any touched route file (e.g. `tests/test_master_cv.py`, `tests/test_assisted_apply_telemetry.py`).
- **Prohibited:**
  - re-registering or restoring the retired admin dashboard/users/tokens/secrets/acquisition/enrichment/job-import surfaces;
  - merging `feature/admin-analytics-final-production`;
  - weakening the extension-origin exactness or the webhook signature checks;
  - wildcard origins in production;
  - editing registration order without re-running the route table and the guard test;
  - resolving U7 without the owner's decision;
  - deployments or live provider calls.

**(b) Registry proposal**

| Subsystem id | Name | Owned globs | Primary doc | Test globs | Owner WS |
|---|---|---|---|---|---|
| `backend-api` | HTTP API and CLI | `backend/api/**`, `workspace_runner.py` | `docs/reverse-engineering/01-architecture/backend-api.md` | `tests/test_backend_api.py`, `tests/test_customer_route_surface.py`, `tests/test_workspace_runner.py`, `tests/test_phase_a_routes.py` | WS-1 |

**(c) Gap/ticket candidates** (not created):
1. **WS1-G2 + WS1-G3.** Fix route params (`segment_params`/`query_params`) and prefix shadowing in the Career Evidence route family, with HTTP-level tests. Highest user impact, because the frontend evidence review calls them.
2. **WS1-G1.** Add `do_PATCH` + CORS PATCH, or migrate the PATCH routes to PUT.
3. **U7 cleanup** (after the owner decision): remove the dead `admin.py` bodies, the `server.py` dashboard helpers (and `_database_query_rows` if confirmed dead), and the frontend `/analytics/events` emitter and tests. Keep the guard test.
4. **WS1-G5.** Replace `bind_server_globals` with explicit imports from extracted helper modules.
5. **WS1-G7.** CLI parser smoke tests (24 subcommands, flag defaults).
6. **WS1-G4/G8/G9.** Security review items, routed to WS-6.

## T49 implementation amendment (2026-09-23)

The Assisted Apply extension now has a dedicated approved profile-package route:

- `POST /v1/assisted-apply/extension/profile-package` is registered as
  `assisted_apply.extension.profile_package.post`.
- The body is intentionally an empty strict object. Unknown fields are rejected;
  the endpoint does not accept profile data from the extension.
- The request must carry an extension session token and the exact configured
  extension `Origin`, and the account must have Runr Pro access.
- The response is schema version `1` and is assembled by the existing
  `_profile_package_sections` service boundary. It contains only the approved
  candidate, profile-verified answers, confirmed career-memory experiences and
  education, confirmed skills/languages, and warnings. No new store or
  migration is introduced.

The route is a body-bearing POST so browser requests preserve the extension
origin during session verification. The service worker calls it and validates
the response before returning a typed `PanelResponse`; the page/panel never
receives the session token or an unvalidated backend payload.
