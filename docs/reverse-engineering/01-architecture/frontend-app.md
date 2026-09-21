> Source: deployment/render-turso-r2 | SHA: 58a96674 | Verified: 2026-09-14

# Customer web frontend (WS-8)

Scope: the Vite/React single-page app in `frontend/`. Everything here was read statically at `58a96674`. No build, test or browser session was run in Phase 2. LIVE PRODUCTION = UNKNOWN.

---

## 1. Purpose and user-facing capabilities

The frontend is Runr's customer web app plus the public marketing site. The same bundle serves both, and the hostname decides which one renders (`frontend/src/App.jsx:18`, `frontend/src/main.jsx:12`).

| Capability | Where (entry) | Backend dependency |
|---|---|---|
| Public marketing and legal pages (home, security, terms, privacy) | `frontend/src/pages/MarketingSite.jsx` | none |
| Clerk sign-in / sign-up | `frontend/src/components/ConnectionPanel.jsx` (`SignIn`/`SignUp` from `@clerk/react`) | Clerk (external) |
| Backend session bootstrap (`/auth/me`) and plan/role merge | `frontend/src/context/SessionContext.jsx` | `admin.auth.me` |
| Jobs feed from the published catalog: filters, save, hide, applied, report, company panel, improve-resume, hidden jobs | `frontend/src/components/personalized/JobsWorkspace.jsx`, `frontend/src/pages/HiddenJobsPage.jsx` | `personalized_jobs.*` |
| Career Evidence (profiles, source upload, review journey) | `frontend/src/pages/CareerProfilesPage.jsx`, `frontend/src/pages/CareerEvidencePage.jsx` | `career_profiles.*`, `evidence_items.*`, `documents.*` |
| Master CV (entries, bullets, tailor, export) | `frontend/src/pages/MasterCvPage.jsx` | `master_cv.*` |
| Document library, CV editor, CV Studio preview | `frontend/src/pages/DocumentsPage.jsx`, `frontend/src/pages/CvEditorPage.jsx`, `frontend/src/pages/CvStudioPage.jsx`, `frontend/src/pages/ArtifactsPage.jsx` | `documents.*`, `admin.settings` |
| Workspaces, Quick Apply, runs, per-job workspace | `frontend/src/pages/WorkspacesPage.jsx`, `frontend/src/pages/QuickApplyPage.jsx`, `frontend/src/pages/RunsPage.jsx`, `frontend/src/pages/RunDetailPage.jsx`, `frontend/src/pages/JobWorkspacePage.jsx` | `workspace.*`, `documents.run_generation` |
| Application tracker (board, manual add, ATS view, JD view, Gmail integration) | `frontend/src/pages/TrackerPage.jsx`, `frontend/src/hooks/useTracker.js` | `tracker.*` |
| Referrals / LinkedIn connections CSV import | `frontend/src/pages/ReferralsPage.jsx` | `tracker.referrals*`, `tracker.outreach.post` |
| Billing: Runr Pro plans, checkout, confirm, portal, quota upgrade modal | `frontend/src/pages/PricingPage.jsx`, `frontend/src/components/UpgradeModal.jsx`, `frontend/src/pages/SettingsPage.jsx` | `admin.billing*` |
| Account settings, profile photo, account deletion, job preferences | `frontend/src/pages/SettingsPage.jsx`, `frontend/src/pages/ProfilePage.jsx` | `admin.settings*`, `documents.profile_photo_upload`, `admin.account.delete`, `personalized_jobs.preferences.*` |
| Assisted Apply extension connection approval and preferences; install guide; launch dialog | `frontend/src/pages/AssistedApplyConnectionPage.jsx`, `frontend/src/pages/ApplyExtensionSetupPage.jsx`, `frontend/src/components/AssistedApplyLaunchDialog.jsx` | `assisted_apply.web.*`, `assisted_apply.packages.*`, `assisted_apply.preparations.*` |
| Product telemetry (first-party sink and optional Firebase GA) | `frontend/src/lib/analytics.js`, `frontend/src/lib/personalizedAnalytics.js` | **unregistered** `POST /analytics/events` (404; see §6, WS8-G1) |

The frontend also ships **backend CV-render code**. `frontend/scripts/render-cv-pdf.mjs` imports `frontend/src/lib/cvStudio.js` and `frontend/src/lib/cvSocialLinks.js`, and the API and worker images run it to produce PDFs (§4.3).

## 2. Owned paths and governing instructions

`frontend/**` has 205 tracked files (`git ls-tree -r --name-only 58a96674 -- frontend | wc -l`).

| Path | Files | Notes |
|---|---|---|
| `frontend/src/pages/` | 31 | 28 routed (27 lazy plus `MarketingSite`), 3 unrouted (§3.3) |
| `frontend/src/components/` | 61 | 9 top-level; `careerMemoryBuilder/` 34; `careerProfile/` 7; `personalized/` 7; `workspaces/` 4 |
| `frontend/src/lib/` | 66 | 38 modules plus 28 `*.test.js` |
| `frontend/src/hooks/` | 10 | 7 modules plus 3 `*.test.js` |
| `frontend/src/context/` | 2 | `SessionContext.jsx`, `ThemeContext.jsx` |
| `frontend/src/data/` | 4 | taxonomies, `mockData.js`, `masterCvFixture.js` |
| `frontend/src/` root | 5 | `App.jsx`, `main.jsx`, `styles.css`, `marketing.css`, and `assets/company-enrichment-team.svg` |
| `frontend/e2e/` | 4 | Playwright specs (1 stale) |
| `frontend/scripts/` | 5 | build metadata, e2e server, production-build test, CV PDF renderer, RC-030 walkthrough |
| `frontend/screenshots/` and root `*.png` | 2 + 7 | committed screenshots (repository-artifact residue; WS-11 inventories) |
| Config | 8 | `package.json`, `package-lock.json`, `vite.config.js`, `eslint.config.js`, `playwright.config.ts`, `postcss.config.js`, `tailwind.config.js`, `index.html` |

**Governing instructions and existing docs:**
- Root `AGENTS.md` has no frontend-specific rules (grep for "frontend" finds no match).
- [docs/deployment/render.md](../../deployment/render.md): frontend static service and the `VITE_API_BASE_URL`/`VITE_API_EXTERNAL_HOSTNAME` preview derivation. I checked these against `render.yaml:15-22` and `frontend/src/lib/api.js:47-63`, and they match. Its example domain is `app.example.com`.
- [docs/PERSONALIZED_JOBS_PREVIEW.md](../../PERSONALIZED_JOBS_PREVIEW.md) describes the Jobs slice as "frontend-only" behind `VITE_PERSONALIZED_JOBS_EXPERIENCE`. This is **partly outdated**: `render.yaml:33-34` sets `VITE_PERSONALIZED_JOBS_DATA_MODE=real`, and `/jobs` reads `/personalized-jobs`.
- [docs/personalized_jobs_contracts.md](../../personalized_jobs_contracts.md) and [docs/phase-c-feed-performance-security.md](../../phase-c-feed-performance-security.md) are Jobs API contracts. They are owned by WS-4/WS-11 and were not re-verified here.
- [docs/runr-analytics-spec.md](../../runr-analytics-spec.md) (L312) proposes an "optional `POST /analytics/events`" endpoint. The endpoint is **not registered** at baseline (N-1).
- Cross-workstream docs:
  - [backend-api.md](backend-api.md) (WS-1): route registry.
  - [security-and-auth.md](security-and-auth.md) (WS-6): Clerk JWT verification.
  - [billing-and-creem.md](../05-subsystems/billing-and-creem.md) (WS-6).
  - [assisted-apply.md](../05-subsystems/assisted-apply.md) (WS-9).
  - [personalized-jobs-and-customer-app-services.md](../05-subsystems/personalized-jobs-and-customer-app-services.md) and [career-profiles-and-documents.md](../05-subsystems/career-profiles-and-documents.md) (WS-4).
  - [render.md](../02-deployment/render.md) and [ci-cd.md](../02-deployment/ci-cd.md) (WS-7).
  - [retired-features.md](../06-history-and-provenance/retired-features.md) (WS-11).

## 3. Entry points and routes

### 3.1 Build and tooling

| Item | Fact (file:line) |
|---|---|
| Runtime deps | `react`/`react-dom` ^18.3.1, `react-router-dom` ^6.30.1, `@clerk/react` ^6.6.4, `recharts` ^3.8.1, `@tansuasici/country-state-city` (`frontend/package.json`) |
| Dev deps | `vite` ^5.4.19, `@vitejs/plugin-react`, `eslint` ^9 with `eslint-plugin-react-hooks`, `tailwindcss` ^3, `postcss`, `autoprefixer`, `playwright` ^1.60 |
| Scripts | `dev`=vite; `test`=`node --test "src/**/*.test.js"`; `check`=test, then `eslint src --max-warnings=0`, then `vite build`; `build`=`node scripts/write-release-metadata.mjs && vite build`; `test:production-build`; `test:e2e`=`playwright test` |
| Vite | `frontend/vite.config.js:31-47`: dev server `127.0.0.1:4173`, proxies `/v1` and `/health` to `127.0.0.1:8000`. The plugin `emit-production-jobs-build-config` (L18-29) writes `dist/runr-build-config.json` `{jobs:{dataMode, replaceLegacyJobsNav}}` |
| Release metadata | `frontend/scripts/write-release-metadata.mjs` writes `public/runr-release.json` (`runr.release.v1`, service `frontend`, branch/commit/contract version) |
| ESLint | `frontend/eslint.config.js`: only `no-undef` is enforced; `react-hooks/exhaustive-deps` is off; ignores `dist/**` |
| `node --test` | 31 co-located `frontend/src/**/*.test.js`, plus `frontend/scripts/production-build.test.mjs`, which asserts the built config is `{dataMode:"real", replaceLegacyJobsNav:true}` |
| Playwright | `frontend/playwright.config.ts`: `testDir ./e2e`, projects `desktop-chromium` (1280x900) and `mobile-chromium` (390x844). `webServer` = `node scripts/serve-production-e2e.mjs`, which builds with `VITE_E2E_AUTH=1`, `VITE_E2E_ADMIN=1`, Jobs real mode, then runs `vite preview` on 4173 |
| Firebase | `frontend/src/lib/analytics.js:66-70` dynamically imports `firebase/app` and `firebase/analytics`. `firebase` is **not declared** in `frontend/package.json`, but `node_modules/firebase` exists in `frontend/package-lock.json` (WS8-G3) |

**Env var names** (names only; `frontend/.env.local` is local and was not read):
- Build-time client env:
  - `VITE_API_BASE_URL` and `VITE_API_EXTERNAL_HOSTNAME` (`frontend/src/lib/api.js:47-63`; fallback `/v1`).
  - `VITE_CLERK_PUBLISHABLE_KEY` (`frontend/src/main.jsx:10`).
  - `VITE_PERSONALIZED_JOBS_EXPERIENCE`, `VITE_PERSONALIZED_JOBS_DATA_MODE` and `VITE_REPLACE_LEGACY_JOBS_NAV` (`frontend/src/lib/personalizedJobsConfig.js`, `frontend/vite.config.js:8-16`).
  - `VITE_ENABLE_ASSISTED_APPLY_PREPARATION` (`frontend/src/lib/assistedApplyPreparation.js:10`; only the literal `"true"` enables it).
  - `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, `VITE_FIREBASE_STORAGE_BUCKET`, `VITE_FIREBASE_MESSAGING_SENDER_ID`, `VITE_FIREBASE_APP_ID` and `VITE_FIREBASE_MEASUREMENT_ID` (`frontend/src/lib/analytics.js:2-10`).
  - Test-only: `VITE_E2E_AUTH` (`frontend/src/App.jsx:44`) and `VITE_E2E_ADMIN` (`frontend/src/context/SessionContext.jsx:18`).
- Node scripts:
  - `RUNR_RELEASE_BRANCH`, `RUNR_RELEASE_COMMIT`, `RUNR_RELEASE_CONTRACT_VERSION`, `RENDER_GIT_BRANCH` and `RENDER_GIT_COMMIT` (write-release-metadata).
  - `PLAYWRIGHT_BASE_URL` and `CI` (playwright config).
  - `CV_PDF_BROWSER_EXECUTABLE`, `CHROME_PATH` and `EDGE_PATH` (`frontend/scripts/render-cv-pdf.mjs:47-49`).
  - `RC030_UI_URL`, `RC030_API_URL`, `RC030_USER_TOKEN` and `RC030_ADMIN_TOKEN` (`frontend/scripts/rc030_local_browser_check.mjs:3-6`).
- Render sets `VITE_API_BASE_URL`, `VITE_API_EXTERNAL_HOSTNAME` (fromService), `VITE_CLERK_PUBLISHABLE_KEY` (sync:false), `RUNR_RELEASE_BRANCH`, `RUNR_RELEASE_CONTRACT_VERSION`, the three Jobs flags and `VITE_ENABLE_ASSISTED_APPLY_PREPARATION` (sync:false) (`render.yaml:15-39`). **No `VITE_FIREBASE_*` keys are set**, so in a Render build Firebase analytics resolves to `null` (`frontend/src/lib/analytics.js:145-148`).

### 3.2 Bootstrap

`frontend/src/main.jsx:50-67` picks one of four render paths:
1. `VITE_E2E_AUTH=1`: `ClerkProvider` with a dummy test key, then `BrowserTestSessionProvider`, which sets a fixed `e2e-user` and token `e2e-token`.
2. Clerk key present: `ClerkProvider afterSignOutUrl="/sign-in"`, then `AppFrame` (`BrowserRouter` › `ThemeProvider` › `App`).
3. No key, on a public marketing path (not `app.userunr.com`): `AppFrame` without Clerk.
4. Otherwise: the "Clerk Configuration Missing" message.

`App` wraps `AppRoutes` in `SessionProvider` (`frontend/src/App.jsx:313-320`).

### 3.3 Router table

**Top level: `AppRoutes`** (`frontend/src/App.jsx:289-311`)

| Path | Host condition | Element | Guard |
|---|---|---|---|
| `/` | `app.userunr.com` | `ProtectedAppRoute` | Clerk signed-in |
| `/` | any other host | `MarketingSite page="home"` | public |
| `/how-it-works` | other host | redirect `/#how-it-works` | public |
| `/pricing` | other host | redirect `/#pricing` | public (**shadows the in-app `/pricing`**, WS8-G2) |
| `/security`, `/terms`, `/terms-and-conditions`, `/user-agreement`, `/privacy` | other host | `MarketingSite` (security/terms/privacy) | public |
| `/sign-in/*`, `/sign-up/*` | any | `PublicAuthRoute` → `ConnectionPanel` | Clerk `Show when="signed-out"`, else redirect `/` |
| `*` | any | `ProtectedAppRoute` | `Show when="signed-in"` with fallback `RedirectToSignIn`; bypassed when `VITE_E2E_AUTH=1` (L270-277) |

**Guards inside `ProtectedAppRoute` → `AuthenticatedApp`** (`frontend/src/App.jsx:167-268`):
- Any `/admin` or `/admin/*` path redirects to `/` (L208-212). This is admin-retirement residue guarding.
- Pages render only when `hasAuthenticatedSession(status, user)` holds, which requires a successful `/auth/me`. Otherwise `BackendConnectionPanel` ("Runr is temporarily unavailable" plus Retry) renders.
- Each route sits inside `RouteErrorBoundary` and `Suspense`.
- "Jobs flag" below means `personalizedJobsExperienceEnabled`.

**App routes** (`frontend/src/App.jsx:221-259`)

| Route | Component / behaviour | Line |
|---|---|---|
| `/` | `HomePage` (reachable only where the top-level `/` is not marketing, i.e. `app.userunr.com`) | 221 |
| `/home` | redirect `/` | 222 |
| `/onboarding` | `PersonalizedOnboardingPage` if Jobs flag and data mode ≠ real; else redirect `/jobs` (**Render config = real, so it redirects**) | 223 |
| `/jobs` | `PersonalizedJobsPage` (renders `JobsWorkspace`) if Jobs flag; else `/` | 224 |
| `/matches` | redirect `/jobs` | 225 |
| `/jobs/hidden` | `HiddenJobsPage` (Jobs flag) | 226 |
| `/jobs/:jobId` | `PersonalizedJobDetailPage` (Jobs flag) | 227 |
| `/career-profiles` | redirect `/career-evidence` | 228 |
| `/dashboard` | **redirect `/jobs`** (the old Dashboard page was removed in `dd47acf9`) | 229 |
| `/workspaces` | `WorkspacesPage` | 230 |
| `/quick-apply` | `QuickApplyPage` | 231 |
| `/runs`, `/runs/:runId` | `RunsPage`, `RunDetailPage` | 232-233 |
| `/job-workspaces/:runId/:jobId` | `JobWorkspacePage` | 234 |
| `/review-queue` | redirect `/tracker` | 235 |
| `/tracker` | `TrackerPage` | 236 |
| `/tracker/:reviewId/ats` | `TrackerAtsPage` | 237 |
| `/tracker/job-descriptions/:reviewId` | `JobDescriptionPage` | 238 |
| `/documents/assets/:assetId/edit` | `CvEditorPage` | 239 |
| `/documents` | `DocumentsPage` | 240 |
| `/master-cv` | `MasterCvPage` | 241 |
| `/career-assets` | `ArtifactsPage` (imported as `CareerAssetsPage`) | 242 |
| `/career-evidence` | `CareerProfilesPage` | 243 |
| `/career-evidence/:profileId` | `CareerEvidencePage` | 244 |
| `/career-memory`, `/career-memory/guide`, `/documents/ai-canvas-guide` | redirect `/career-evidence` | 245-247 |
| `/cv-studio` | `CvStudioPage` | 248 |
| `/artifacts` | redirect `/career-assets` | 249 |
| `/referrals`, `/refer` | `ReferralsPage` | 250, 252 |
| `/services` | redirect `/refer` | 251 |
| `/referrals/linkedin-csv-guide` | `LinkedInConnectionsGuidePage` | 253 |
| `/settings` | `SettingsPage` | 254 |
| `/profile` | `ProfilePage` | 255 |
| `/settings/assisted-apply` | `AssistedApplyConnectionPage` | 256 |
| `/apply-extension` | `ApplyExtensionSetupPage` | 257 |
| `/pricing` | `PricingPage` (effectively only on `app.userunr.com`; WS8-G2) | 258 |
| `*` | redirect `/` | 259 |

**Unrouted pages** (no import found by `git grep`):
- `frontend/src/pages/ReviewQueuePage.jsx` (1,233 lines; `/review-queue` redirects instead)
- `frontend/src/pages/CareerUrlDiscoveryPage.jsx`
- `frontend/src/pages/DocumentAICanvasGuidePage.jsx`

**Navigation:** `frontend/src/components/AppShell.jsx` defines the sidebar nav: when the personalized Jobs experience is on, `personalizedNavItems` is the legacy sidebar with a Jobs entry (Workspaces, Jobs, Quick Apply, Runs, Tracker, Career Assets, Referrals, Account, Pricing); otherwise it is the legacy sidebar unchanged. When `retireLegacyJobsNavigation` (`VITE_REPLACE_LEGACY_JOBS_NAV` plus real Jobs data mode, set for production/e2e builds) is on, `userNavItems` filters the legacy `Workspaces` and `Runs` entries out of the rendered sidebar; the admin/administrator distinction was removed from this map by commit `4dcdda39`, so the filtered list is what every authenticated user sees. `frontend/src/lib/routeParents.js` maps child routes to parents.

### 3.4 Module summary (lib 66, components 61, hooks 10)

| Module group | Files | Role |
|---|---|---|
| API and session | `frontend/src/lib/api.js`, `frontend/src/lib/sessionState.js`, `frontend/src/hooks/useApiResource.js`, `frontend/src/hooks/apiResourceCache.js`, `frontend/src/lib/deployVersion.js` | fetch client, session state machine, cached resource hook, release-version check |
| Telemetry | `frontend/src/lib/analytics.js`, `frontend/src/lib/personalizedAnalytics.js`, `frontend/src/lib/personalizedAnalyticsPayload.js` | first-party sink and Firebase (§5.5) |
| Jobs | `frontend/src/lib/personalizedJobs.js`, `frontend/src/lib/personalizedJobsApi.js`, `frontend/src/lib/personalizedJobsConfig.js`, `frontend/src/lib/personalizedJobIntelligence.js`, `frontend/src/lib/personalizedOnboarding.js`, `frontend/src/lib/personalizedPreviewState.js`, `frontend/src/lib/postOnboardingOffer.js`, `frontend/src/data/jobSearchTaxonomy.js`, `frontend/src/data/jobMoreFilterTaxonomy.js`, `frontend/src/components/personalized/` | feed normalization, flags, filters, synthetic preview data, offer logic |
| Career evidence / memory | `frontend/src/lib/careerEvidenceFlow.js`, `frontend/src/lib/careerMemoryBuilder.js`, `frontend/src/lib/careerMemoryWorkspace.js`, `frontend/src/lib/careerProfileSources.js`, `frontend/src/lib/sourceProcessingPolling.js`, `frontend/src/components/careerMemoryBuilder/` (34), `frontend/src/components/careerProfile/` (7) | evidence journey UI |
| CV / documents | `frontend/src/lib/cvStudio.js`, `frontend/src/lib/cvSocialLinks.js`, `frontend/src/lib/cvUpload.js`, `frontend/src/lib/masterCv.js`, `frontend/src/lib/cvFeatureShowcase.js`, `frontend/src/components/CvExportPreview.jsx`, `frontend/src/components/workspaces/` | CV HTML building (shared with backend PDF render), upload, master CV model |
| Workspaces / runs | `frontend/src/hooks/useWorkspaceRunActions.js`, `frontend/src/hooks/useWorkspaceCvAssets.js`, `frontend/src/hooks/workspaceCvAssetState.js`, `frontend/src/hooks/useWorkspaceCityOptions.js`, `frontend/src/lib/runProgressFocus.js`, `frontend/src/lib/locationOptions.js` | run creation, CV asset binding |
| Tracker / referrals | `frontend/src/hooks/useTracker.js`, `frontend/src/lib/trackerLoading.js`, `frontend/src/lib/trackerDescription.js`, `frontend/src/lib/trackerAssistedApply.js`, `frontend/src/lib/peopleDiscovery.js`, `frontend/src/lib/linkedinSync.js` | board state, Gmail integration, referral discovery |
| Assisted Apply | `frontend/src/lib/assistedApplyConnection.js`, `frontend/src/lib/assistedApplyDocuments.js`, `frontend/src/lib/assistedApplyLaunch.js`, `frontend/src/lib/assistedApplyPreparation.js`, `frontend/src/lib/supportedAssistedApplyUrl.js` | connection-request approval, package/preparation payloads, supported-URL gate |
| Misc | `frontend/src/lib/formatters.js`, `frontend/src/lib/auth.js`, `frontend/src/lib/routeParents.js`, `frontend/src/context/ThemeContext.jsx`, `frontend/src/data/mockData.js` | formatting, `isAdminUser` (unused), theme |

**No import found (static grep, possibly dead):**
- Components: `EvidenceStatus`, `PagePlaceholder`, `CareerMemoryBuilder`, `CVBulletSuggestionsPanel`, `EvidenceRecommendationPanel`, `SourceTextReviewPanel`, `JobCard`, `PostOnboardingProOffer`, `PreviewUpgradeModal`, `ProvenanceTag`.
- Libs imported only by tests: `assistedApplyLaunch`, `auth`, `personalizedJobIntelligence`, `sourceProcessingPolling`, `trackerAssistedApply`, `masterCvFixture` (WS8-G4).

## 4. Inputs, outputs, storage and dependencies

### 4.1 API client (`frontend/src/lib/api.js`)

- **Base URL.** `resolveDefaultApiBaseUrl` (L47-63) tries `VITE_API_BASE_URL` first, then `https://${VITE_API_EXTERNAL_HOSTNAME}/v1`, then `/v1`. It rejects unresolved `${...}` placeholders. A user override is persisted in `localStorage` `runr.api.baseUrl` (L3-5, L69-86).
- **Auth.** `SessionContext.getAccessToken` calls Clerk `getToken({ template: "runr_backend" })` (`frontend/src/lib/api.js:8`, `frontend/src/context/SessionContext.jsx:117-122`). `apiRequest` (L485-592) sends `Authorization: Bearer`, but never on absolute URLs such as signed R2/S3 object URLs (L500-505).
- **Request handling.** JSON bodies are serialized unless the body is `FormData` or a blob. `timeoutMs` uses an `AbortController`.
- **Errors.** Errors normalize to `{status, code, details, payload}` (L409-429). A `402` with `error:"quota_exceeded"` dispatches the `runr:quota-exceeded` window event, which `UpgradeModalHost` catches (`frontend/src/App.jsx:97-120`).
- **Retries.** `apiRequestWithRetry` (L460-483) retries on 408/429/502/503/504 and network TypeErrors, up to 5 retries and 30 s total. A duplicate unexported `legacyApiRequestWithRetry` (L146-200, "retained from the bad merge") is dead code.
- **Diagnostics.** Requests taking ≥5 s, and failed requests, are logged to the console and then POSTed with a raw `fetch` to `/analytics/events` (L243-281). The payload uses path shapes with ids redacted (`diagnosticPathShape`, L220-230). The call is fire-and-forget (`.catch(() => {})`), and the path is excluded to avoid loops (L245).

### 4.2 Frontend call → registered route name

Route names come from `backend/api/routes/*.py` `register_routes`, dispatched via `backend/api/server.py` `_dispatch_route` (L8929-8940). An unmatched path gets `404 not_found "Route not found."` (for example the POST branch around L9236-9251). Prefix routes can be shared by several registrations; which handler actually answers is WS-1's concern ([backend-api.md](backend-api.md)). All paths are relative to `/v1`.

| Frontend path(s) (method) | Caller(s) | Registered name (file:line) |
|---|---|---|
| `/auth/me` GET | `frontend/src/context/SessionContext.jsx:167,209` | `admin.auth.me` (`backend/api/routes/admin.py:25`) |
| `/billing/plans` GET | `PricingPage.jsx:66`, `PostOnboardingProOffer.jsx:257` | `admin.billing.plans` (admin.py:24, no auth) |
| `/billing/subscription` GET | `PricingPage.jsx:76`, `SettingsPage.jsx:576`, `ProfilePage.jsx` | `admin.billing` prefix (admin.py:26) |
| `/billing/checkout`, `/billing/checkout/confirm`, `/billing/portal` POST | `PricingPage.jsx:137,184,206`, `UpgradeModal.jsx:61`, `SettingsPage.jsx:695`, `PostOnboardingProOffer.jsx:356` | `admin.billing.post` prefix (admin.py:30) |
| `/settings` GET / PUT | Settings, CvStudio, Artifacts, CareerEvidence, QuickApply, Workspaces, Profile | `admin.settings` / `admin.settings.put` (admin.py:28,31) |
| `/account` DELETE | `SettingsPage.jsx:711` | `admin.account.delete` (admin.py:32) |
| `/personalized-jobs?…` GET, `/personalized-jobs/{id}` GET | `JobsWorkspace.jsx` | `personalized_jobs.read` / `personalized_jobs.job.read` (`backend/api/routes/acquisition_catalog.py:10,20`) |
| `/personalized-jobs/{id}/{save,hide,restore,applied,report,improve-resume}` POST; `/save` DELETE | `JobsWorkspace.jsx:493-576`, `HiddenJobsPage.jsx:38,50` | `personalized_jobs.job.action` / `.job.delete` (acquisition_catalog.py:21-22) |
| `/personalized-jobs/saved-search` PUT, `/hidden` GET, `/companies/{id}` GET, `/preferences` GET/PUT | JobsWorkspace, HiddenJobsPage, ProfilePage | `personalized_jobs.saved_search.write`, `.hidden.read`, `.company.read_prefix`, `.preferences.*` (acquisition_catalog.py:11-19) |
| `/documents?…`, `/documents/assets/{id}`, `/documents/upload`, `/documents/bulk-export` | Documents, Artifacts, CareerEvidence, CareerProfiles, CvEditor, QuickApply, Workspaces, Onboarding, `CareerProfileSourceSelector.jsx` | `documents.documents{,.post,.put,.delete}` prefix (`backend/api/routes/documents.py:80-87`) |
| `/cv-upload` POST | `frontend/src/lib/cvUpload.js:32` | `documents.cv_upload` (documents.py:82) |
| `/profile-photo-upload` POST (URL via `resolvePath`) | `SettingsPage.jsx` | `documents.profile_photo_upload` (documents.py:83) |
| `/master-cv`, `/master-cv/{entries,bullets/{id},tailor,export}` | `MasterCvPage.jsx` | `master_cv.*` (`backend/api/routes/master_cv.py:32-43`) |
| `/career-profiles`, `/career-profiles/{id}` | CareerProfilesPage, CareerEvidencePage | `career_profiles.*` (`backend/api/routes/career_profiles.py:25-33`) |
| `/evidence-items/{next-review,ready-actions,journey-state}` GET; `/{review-action,confirm-inspect,answer-enrich,skip-question}` POST | `CareerEvidencePage.jsx` | `evidence_items.*` exact (`backend/api/routes/evidence_items.py:46-63`) |
| `/evidence-items/{process-sources,generate,migrate}` POST, `/evidence-items`, `/outputs` GET | CareerEvidencePage, `FactGroundedMemoryWorkspace.jsx` | `evidence_items.get/post` prefix (evidence_items.py:66-67); handled at evidence_items.py:254,319,358,437 |
| `/evidence-items/questions` GET | `EvidenceQuestions.jsx:18` | `evidence_questions.get` (`backend/api/routes/evidence_questions.py:28`) |
| `/tracker?view=board`, `/tracker/{id}`, `/tracker/manual`, `/tracker/bulk`, `/tracker/email-integration{,/sync,/google/start,/detections/*}` | `useTracker.js`, `trackerLoading.js`, TrackerPage, TrackerAtsPage, JobDescriptionPage, ReferralsPage | `tracker.tracker{,.post,.put,.delete}` prefix (`backend/api/routes/tracker.py:31-42`); OAuth callback `tracker.google.callback` (tracker.py:29, backend-to-browser) |
| `/referrals?…`, `/referrals/{import,import/status,outreach-status,outreach-statuses}` | `ReferralsPage.jsx` | `tracker.referrals{,.post,.put,.delete}` (tracker.py:30,35,39,41) |
| `/workspaces?…`, `/workspaces/{id}`, `/workspaces/{id}/schedule` | Workspaces, Artifacts, CareerProfiles, QuickApply, `WorkspaceSchedule.jsx` | `workspace.workspaces{,.post,.put,.delete}` (`backend/api/routes/workspace.py:23,34,41,44`) |
| `/workspace-builder/{catalog,source-validation}` | QuickApply, Workspaces, `useWorkspaceRunActions.js:88` | `workspace.builder{,.post}` (workspace.py:24,36) |
| `/runs` POST, `/runs/{id}` GET, `/runs/{id}/{cancel,customer-view}` | `useWorkspaceRunActions.js:155`, RunsPage, RunDetailPage | `workspace.runs{,.post}` (workspace.py:29,38). `runs` prefixes are also registered by `documents.run_generation` (documents.py:85) and `tracker.people_discovery{,.post}` (tracker.py:33,37) |
| `/quick-apply/runs` POST | `QuickApplyPage.jsx` | `workspace.quick_apply` (workspace.py:35) |
| `/assisted-apply/connection[?request_id]` GET | `AssistedApplyConnectionPage.jsx:135` via `assistedApplyConnection.js:107-112` | `assisted_apply.web.connection.get` (`backend/api/routes/assisted_apply.py:67`) |
| `/assisted-apply/connection-requests/{id}/{approve,reject}` POST | AssistedApplyConnectionPage `:153,177` | `assisted_apply.web.connection_requests.action` (assisted_apply.py:74) |
| `/assisted-apply/preferences` PUT | AssistedApplyConnectionPage `:197` | `assisted_apply.web.preferences.update` (assisted_apply.py:81) |
| `/assisted-apply/packages/{prepare,launch}` POST | `AssistedApplyLaunchDialog.jsx:84,93` | `assisted_apply.packages.{prepare,launch}` (`backend/api/routes/assisted_apply_packages.py:38,45`) |
| `/assisted-apply/preparations` POST, `/{id}` | `AssistedApplyLaunchDialog.jsx:97` | `assisted_apply.preparations.{create,read,action}` (`backend/api/routes/assisted_apply_preparations.py:19-21`) |
| Unrouted pages only: `/review-queue`, `/runs/{id}/reviews`, `/outreach/*-draft` (ReviewQueuePage); `/career-url-discovery/run` (CareerUrlDiscoveryPage) | — | `workspace.review_queue`, `tracker.outreach.post`, `workspace.career_url_discovery` (registered; the callers are unreachable UI) |
| **`/analytics/events` POST** | `frontend/src/lib/analytics.js:125`, `frontend/src/lib/api.js:267` | **UNREGISTERED → 404, errors swallowed (N-1)**. The handler body in `backend/api/routes/admin.py` (~L239) is not in `register_routes` (admin.py:23-33) |

### 4.3 CV render files shared with backend images

`render.yaml` lists the same five `frontend/` files in the `buildFilter` of both the API (L60-64) and the worker (L176-180):
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/scripts/render-cv-pdf.mjs`
- `frontend/src/lib/cvStudio.js`
- `frontend/src/lib/cvSocialLinks.js`

Consumers:
- `Dockerfile.api:56-58` and `Dockerfile.worker:55-57` COPY them.
- `backend/capabilities/tailored_documents/rendering.py:1350` invokes `render-cv-pdf.mjs`. That script imports `buildCvStudioHtml`/`buildWorkspacePreviewState` from `cvStudio.js` and renders via Playwright chromium.
- `backend/deployment/release_contract.py:22-24` pins the same paths.

**Consequence:** edits to `cvStudio.js` or `cvSocialLinks.js` redeploy and change the API and worker (WS-7 owns `render.yaml`; WS-4 owns rendering).

### 4.4 Browser storage

- `localStorage`: `runr.api.baseUrl`, plus the `runr.personalizedJobs.*` keys onboarding, dispositions, upgradeDismissals and postOnboardingOffer (`frontend/src/lib/personalizedJobs.js:15-18`).
- No other persistent client store was found.

### 4.5 Static hosting

- `render.yaml:1-43` defines `runr-frontend`: runtime static, `rootDir frontend`, `npm ci && npm run build`, publish `./dist`, `buildFilter` [`frontend/**`, `render.yaml`], `autoDeployTrigger: commit`, `domains: [userunr.com]`, SPA rewrite `/*` to `/index.html`.
- The API CORS value includes `app.userunr.com` and the onrender frontend origin (`render.yaml:99`).
- `app.userunr.com` is hard-coded in `frontend/src/App.jsx:18`, `frontend/src/main.jsx:12` and `frontend/src/pages/MarketingSite.jsx:94`, but it does not appear in the frontend `domains` (WS8-G6; WS-7 owns this).

## 5. Important call/data flows

### 5.1 Sign-in and session

1. An unauthenticated visitor on a protected path gets `ProtectedAppRoute`, whose Clerk `Show` fallback is `RedirectToSignIn` (`frontend/src/App.jsx:270-277`). `/sign-in/*` renders `ConnectionPanel` (`SignIn`, `signUpUrl="/sign-up"`).
2. Once signed in, `SessionProvider.refreshSession` (`frontend/src/context/SessionContext.jsx:147-194`) calls `apiRequest(apiBaseUrl, getAccessToken, "/auth/me")`.
3. `mergeSessionUser` (L50-79) merges backend user fields with Clerk `publicMetadata` `plan_id`/`role`; Clerk metadata wins for role.
4. On success it sets status `connected`, calls `identify(userId)` and logs `session_started`, which goes to the 404 sink. On failure `getSessionRefreshErrorState` (`frontend/src/lib/sessionState.js`) keeps the previous user if there was one; otherwise `BackendConnectionPanel` shows.
5. `disconnect` calls Clerk `signOut({redirectUrl:"/sign-in"})` (L233-242).
6. Marketing CTAs link to `https://app.userunr.com${path}` (`frontend/src/pages/MarketingSite.jsx:94`).

### 5.2 Onboarding and profile

- With the Render config (Jobs real mode), `/onboarding` redirects to `/jobs` (`frontend/src/App.jsx:223`). `PersonalizedOnboardingPage` (CV pick via `/documents?asset_kind=workspace_cv`, extraction and showcase events) is therefore reachable only in synthetic mode.
- Profile and preferences: `ProfilePage.jsx` reads `/settings`, `/billing/subscription` and `/personalized-jobs/preferences`. `SettingsPage.jsx` handles settings PUT, photo upload, billing portal and account DELETE.

### 5.3 CV, Master CV and documents

- **Master CV:** `MasterCvPage.jsx` does GET/PUT `/master-cv`, entry and bullet CRUD, `/master-cv/tailor`, and `/master-cv/export?format=`. The model helpers are in `frontend/src/lib/masterCv.js`.
- **Upload:** `lib/cvUpload.js` POSTs `/cv-upload`. Document pages upload via `/documents/upload?…` and edit assets at `/documents/assets/{id}` (`CvEditorPage.jsx`).
- **Preview and PDF:** `CvStudioPage`/`CvExportPreview` build HTML from `cvStudio.js` in the browser. The backend renders the same HTML to PDF (§4.3).
- **Career Evidence:** `CareerProfilesPage` creates or selects a profile. `CareerEvidencePage` uploads sources, POSTs `/evidence-items/process-sources`, then loops `next-review`/`ready-actions`/`journey-state` with review actions.

### 5.4 Jobs feed

`/jobs` → `PersonalizedJobsPage` → `JobsWorkspace.jsx`:
- GET `/personalized-jobs?<filters>`, with filters built from `frontend/src/data/jobSearchTaxonomy.js` and `jobMoreFilterTaxonomy.js`, normalized by `personalizedJobsApi.js`.
- Detail: `/personalized-jobs/{id}`, company panel `/personalized-jobs/companies/{company_id}`.
- Actions: save/unsave, hide/restore, applied, report, improve-resume; saved search PUT.
- Personalized events are emitted through `logPersonalizedEvent` (§5.5).
- `/jobs/hidden` → `HiddenJobsPage` (`/personalized-jobs/hidden?limit=100`).
- `AuthenticatedApp` preloads the Jobs chunks on idle (`frontend/src/App.jsx:174-190`).
- Catalog origin is out of scope here: the WS-12 data-flow doc and WS-4 own it.
- **U10:** no signed-in visual verification of real `/jobs` payloads exists (the handoff says so).

### 5.5 Telemetry (N-1, U7)

- `logEvent(name, props)` (`frontend/src/lib/analytics.js:171-191`) has two outputs:
  - (a) If a first-party sink is configured (`SessionContext.jsx:145` and test provider L42), it calls `request("/analytics/events", {POST, body:{event_name, source:"frontend_first_party", route, payload: sanitizeFirstPartyProperties(props)}})` with `.catch(() => undefined)` (L112-133). The allowlist is 41 keys (L22-64): no free text, strings trimmed to 160 chars.
  - (b) If all four required `VITE_FIREBASE_*` values are set, it calls Firebase `logEvent`; otherwise it only does a `console.debug` in DEV.
- Callers:
  - `page_view` on every authenticated navigation (`frontend/src/App.jsx:192-206`) and `session_started` (`SessionContext.jsx:134`).
  - About 30 `logPersonalizedEvent` names across 11 files: `jobs_feed_viewed`, `jobs_filter_changed`, `apply_link_opened`, `job_relevance_feedback`, `onboarding_*`, `cv_feature_showcase_*`, `post_onboarding_*`, `upgrade_cta_clicked`, `upgrade_prompt_dismissed`, `application_preparation_*`, `application_marked_applied`.
- `personalizedAnalyticsPayload.js` maps the context to `route`, `feature_key`, `job_preview_id`, `filter_name`, `onboarding_step`, `data_mode` (default `"synthetic"`), optional `job_id`, `job_count`, `filter_count`, scene/offer/timing fields and `feedback_reason_code`. `user_id` from `page_view`/`session_started` is **dropped** by the first-party allowlist but **would reach Firebase** (identify and `setUserProperties`) if it were configured.
- API diagnostics (§4.1) POST the same endpoint with `source:"frontend_api_request_diagnostic"`.
- **Destination at baseline:** every one of these POSTs gets 404, and the browser ignores the failures. No event reaches `analytics_events` from the frontend. Worker-side `emit_event` remains separate (WS-2/WS-1).

### 5.6 Tracker

`useTracker.js`:
- Board loads with `/tracker?view=board` (timeout) and `/tracker/email-integration`.
- Bulk updates, Gmail OAuth start (`/tracker/email-integration/google/start` returns a redirect URL; the callback is `tracker.google.callback`), sync, and approve/dismiss detections.
- `TrackerPage` adds manual items (`/tracker/manual`) and per-item updates. ATS and JD sub-pages read `/tracker/{reviewId}`.

### 5.7 Billing (Runr Pro)

- `PricingPage.jsx` loads `/billing/plans` and `/billing/subscription`, then POSTs `/billing/checkout {plan_id, source_page}` and navigates to the returned checkout URL.
- On return it POSTs `/billing/checkout/confirm` (L137), and `/billing/portal` opens the customer portal.
- `UpgradeModal.jsx` starts checkout from a `quota_exceeded` 402.
- CREEM/webhook side: see [billing-and-creem.md](../05-subsystems/billing-and-creem.md). **WS8-G2:** outside `app.userunr.com`, `/pricing` is the marketing anchor redirect, so the in-app pricing page is not reachable there.

### 5.8 Assisted Apply connection UI

1. The extension opens `/settings/assisted-apply?request_id=<opaque>`. `parseAssistedApplyConnectionSearch` validates the id against `^[A-Za-z0-9_-]{8,200}$` (`frontend/src/lib/assistedApplyConnection.js:1,34-44`).
2. The page GETs `/assisted-apply/connection?request_id=` and normalizes the result to `pending|connected|expired|rejected|revoked|not_found|disconnected`.
3. Approve POSTs `/assisted-apply/connection-requests/{id}/approve`. The backend must return a completion URL matching `https://<32 a-p>.chromiumapp.org/runr/connect` (`normalizeBackendCompletionUrl`, L121-140); otherwise an error shows. The page then calls `window.location.replace(completionUrl)` (`AssistedApplyConnectionPage.jsx:161-162`).
4. Reject posts `/reject`. Preferences PUT only `permit_sensitive_autofill` and `permit_demographic_autofill`; `require_legal_answer_confirmation` is forced to `true` (L45-60).
5. The UI states the boundaries "never clicks the employer's final Submit button" etc. (L18-23).
6. `/apply-extension` links to the Chrome Web Store listing for extension id `najcdfohhfgbjpbokhmmekkahghfhegp`, which is also in `assistedApplyPreparation.js`.
7. The launch dialog (`AssistedApplyLaunchDialog.jsx`) prepares and launches packages. Behind `VITE_ENABLE_ASSISTED_APPLY_PREPARATION`, it creates preparations.

Extension and protocol details: [assisted-apply.md](../05-subsystems/assisted-apply.md), [apps-and-extensions.md](apps-and-extensions.md).

## 6. Invariants, failure handling and recovery

| Invariant / behaviour | Evidence |
|---|---|
| Bearer token never sent to absolute (signed object) URLs | `frontend/src/lib/api.js:500-505`; test `api.test.js:88` |
| Telemetry must never block or fail user actions; its failures are swallowed | `analytics.js:124-125`, `api.js:266-275` |
| Diagnostics never recurse on `/analytics/events` | `api.js:243-246` |
| Placeholder or empty API base falls back safely | `api.js:15-63`; tests `api.test.js:25-60` |
| Quota 402 opens the upgrade modal globally | `api.js:419-427`, `App.jsx:97-120` |
| A route render error is contained by `RouteErrorBoundary` (keyed by path) with a reload CTA | `App.jsx:59-95,218` |
| Backend session loss keeps the last good user; otherwise shows Retry | `sessionState.js`, `App.jsx:122-165` |
| `/admin*` never renders; redirects to `/` | `App.jsx:208-212` |
| Legal-answer confirmation is always required; optional autofill categories default off | `assistedApplyConnection.js:5-9,45-60` |
| Extension completion URL restricted to chromiumapp.org `/runr/connect` | `assistedApplyConnection.js:2-3,121-140` |
| Production build must embed real Jobs mode and the retired legacy nav | `frontend/scripts/production-build.test.mjs` (not in CI) |

**Known failure mode (N-1).** Each authenticated page view, session start, personalized event, and each slow or failed API call issues a POST that returns 404. The effect is silent data loss plus extra network requests. Unit tests `frontend/src/lib/analytics.test.js:28-42` and `frontend/src/lib/api.test.js:125-154` assert that these POSTs are made, which locks in the unregistered path.

## 7. Relevant tests and safe verification commands (not executed in Phase 2)

**Unit (31, `node --test`, CI job `frontend` in `.github/workflows/ci.yml:90-109`, which runs `npm --prefix frontend run test` and `run check`):**
- `frontend/src/hooks/`: `useApiResource.test.js`, `useTracker.test.js`, `useWorkspaceCvAssets.test.js`.
- `frontend/src/lib/`: `analytics`, `api`, `assistedApplyConnection`, `assistedApplyDocuments`, `assistedApplyLaunch`, `assistedApplyPreparation`, `careerAssetsRouting`, `careerEvidenceFlow`, `careerMemoryWorkspace`, `cvFeatureShowcase`, `cvStudio`, `deployVersion`, `evidenceReview`, `masterCv`, `peopleDiscovery`, `personalizedJobIntelligence`, `personalizedJobs`, `personalizedJobsApi`, `personalizedJobsCompany`, `personalizedJobsConfig`, `postOnboardingOffer`, `routeParents`, `runProgressFocus`, `sessionState`, `sourceProcessingPolling`, `supportedAssistedApplyUrl`, `trackerAssistedApply`, `trackerDescription` (each `*.test.js`).

**Build test:** `frontend/scripts/production-build.test.mjs` (`npm run test:production-build`; not CI-wired).

**E2E (4 Playwright specs, not CI-wired):**

| Spec | Targets | State |
|---|---|---|
| `frontend/e2e/career-evidence-production.spec.ts` | `/career-evidence` (mocked API) | current |
| `frontend/e2e/phase-d-jobs-cutover.spec.ts` | `/jobs/job-a` | current |
| `frontend/e2e/phase-e-job-intelligence.spec.ts` | `/jobs/job-a` | current |
| `frontend/e2e/admin-operations-console.spec.ts` | `/admin`, `/admin/acquisition/*`, `/admin/job-import`, `/admin/scrapeops` (52 `/admin` refs) | **STALE**: those routes were deleted in `dd47acf9`, and `App.jsx:208` now redirects `/admin*`, so the spec would fail |

**Other:** `frontend/scripts/rc030_local_browser_check.mjs` is a manual local walkthrough that needs user and admin tokens (RC-030). Backend-side guard: `tests/test_customer_route_surface.py` (WS-10) asserts that the admin dashboard/analytics routes are unregistered.

**Safe verification commands (not executed):**
```
npm ci --prefix frontend
npm --prefix frontend run test
npm --prefix frontend run check                 # test + eslint + vite build
npm --prefix frontend run test:production-build
npx --prefix frontend playwright test e2e/career-evidence-production.spec.ts e2e/phase-d-jobs-cutover.spec.ts e2e/phase-e-job-intelligence.spec.ts
git grep -n '"/analytics/events"' 58a96674 -- frontend backend/api/routes
```

## 8. Historical decisions and supporting commits

195 commits touch `frontend/` up to `58a96674` (`git log --oneline 58a96674 -- frontend | wc -l`). Selected:

| SHA | Subject | Relevance |
|---|---|---|
| `50b8f7c4` | fix acquisition rotation incremental publishing and display feed | most recent frontend touch |
| `d44d3c0f` | production: restore canonical publication chain | |
| `dd47acf9` | Complete acquisition delivery and remove admin surfaces | removed admin router/pages, `DashboardPage.jsx`, `AcquisitionOperationsPage.jsx`, `lib/acquisitionOperations{,.test}.js`; added `/dashboard`→`/jobs` and the `/admin` redirect (merged by `550ee00a`) |
| `e728e364` | test: add RC-030 local browser walkthrough | `rc030_local_browser_check.mjs` |
| `bdd58615` | feat: add product outcome analytics and wave planning | current `analytics.js` first-party sink |
| `39d15b8f` | RC-022 separate release and runtime contracts | release metadata |
| `af94ef4c` | feat: add branded social links to CVs | `cvSocialLinks.js` (backend render dependency) |
| `f63832ab`, `e0ef7b14` | perf: compact / lightweight document library payload | |
| `6675338c`, `82368269`, `f672a08c` | editable workspace CV editor, preview-to-field jump, focus sync | `CvEditorPage.jsx` |
| `0f492a1c` | Remove redundant Matches navigation | `/matches`→`/jobs` |
| `c90eadfc`/`9c50cf79`, `7be2200d`/`cea106c1` | keep app subdomain on authenticated app; route marketing signups to app subdomain | host split |
| `1608a770`, `5c8b339f` | combine marketing sections; add public marketing and legal pages | `MarketingSite.jsx` |
| `ef78e256` | feat: connect Master CV to backend | |
| `ce2ac5e1` | Fix referrals workspace and enable people discovery | |
| `5e674e1e` | fix: migrate Creem billing to Runr Pro | billing UI |
| `42d4603d`, `027c976a` | Phase D Jobs production cutover; Phase E job intelligence | real-mode `/jobs`, e2e specs |
| `917e2588`, `63dfd30e` | bounded loading, retries, telemetry; restore valid frontend API module | `api.js` retry/diagnostics (and legacy duplicate) |
| `4f12b0e8`, `d6cf0db9` | CP-046R / CP-042R career evidence browser validation | Playwright config and spec |
| `0307b3e1`, `12f342fb`, `06a4cb17` | admin operations console / acquisition analytics dashboard | **RETIRED** (removed in `dd47acf9`) |

## 9. Current implementation status

| Capability | Classification |
|---|---|
| Router table and guards (§3.3) | VERIFIED (scope: static read of `frontend/src/App.jsx:167-311` and `frontend/src/main.jsx:50-67` at 58a96674; not rendered) |
| `/dashboard` → `/jobs` redirect | VERIFIED (scope: static, `App.jsx:229`) |
| API client base URL, auth header, retries, quota event | VERIFIED (scope: static read of `api.js`; unit tests exist, not run) |
| Frontend calls map to registered routes (§4.2, except analytics) | VERIFIED (scope: static match of literal paths against `register_routes` names in `backend/api/routes/*.py`; handler behaviour within prefix routes not traced) |
| Product telemetry `POST /analytics/events` (frontend first-party sink and API diagnostics) | PARTIAL: the client code is implemented, but the endpoint is unregistered (404, swallowed), so no delivery (N-1) |
| Firebase analytics | IMPLEMENTED-UNVERIFIED (inactive under `render.yaml`: no `VITE_FIREBASE_*`; the `firebase` package is undeclared) |
| Clerk sign-in / session bootstrap | IMPLEMENTED-UNVERIFIED (handoff records the Clerk sign-in screen reached, documentary) |
| Jobs feed on the real catalog (`/jobs`) | IMPLEMENTED-UNVERIFIED (authenticated payload not visually verified, U10) |
| Personalized onboarding page | IMPLEMENTED-UNVERIFIED; unreachable under Render real mode (`App.jsx:223`) |
| Career Evidence, Master CV, documents, CV editor/studio | IMPLEMENTED-UNVERIFIED |
| Workspaces, Quick Apply, runs, tracker, referrals | IMPLEMENTED-UNVERIFIED |
| Billing / Runr Pro checkout UI | IMPLEMENTED-UNVERIFIED; in-app `/pricing` shadowed on non-app hosts (WS8-G2) |
| Assisted Apply connection approval / preferences UI | IMPLEMENTED-UNVERIFIED (unit tests exist, not run) |
| Assisted Apply preparation (pilot) | IMPLEMENTED-UNVERIFIED, gated by `VITE_ENABLE_ASSISTED_APPLY_PREPARATION` (sync:false; value UNKNOWN) |
| CV render files consumed by API/worker images | VERIFIED (scope: static, `render.yaml:60-64,176-180`, `Dockerfile.api:56-58`, `Dockerfile.worker:55-57`, `rendering.py:1350`) |
| ReviewQueuePage, CareerUrlDiscoveryPage, DocumentAICanvasGuidePage | UNKNOWN (unrouted; retained code, no plan cited) |
| Frontend e2e (3 current specs) | IMPLEMENTED-UNVERIFIED (not CI-wired) |
| Admin operations console / acquisition analytics / DashboardPage | RETIRED/HISTORICAL (`dd47acf9`; residue: stale spec, `VITE_E2E_ADMIN`, `lib/auth.js` `isAdminUser`, RC-030 admin token) |
| Unmerged CV editor/perf/social-links work on the feature branch | UNMERGED (feature/admin-analytics-final-production @ ce3718b0), U5, labelled only |

### Deployment evidence (documentary only)

- `docs/RUNR_PRODUCTION_COMPLETION_HANDOFF.md` (records Render at `5dfdd106`, 44 commits behind baseline) says:
  - the frontend build passed and "the deployed frontend is on the final revision";
  - an unauthenticated browser check reached the Clerk sign-in at the app subdomain;
  - authenticated Jobs payloads were **not** visually verified (L78, U10).
- `render.yaml` config for `runr-frontend` is as described in §4.5. Whether that config is what is deployed is UNKNOWN. Render service details belong to [render.md](../02-deployment/render.md) (WS-7).

## 10. Confirmed gaps and unresolved questions

| ID | Gap | Refs |
|---|---|---|
| WS8-G1 | `frontend/src/lib/analytics.js:125` and `frontend/src/lib/api.js:267` POST the unregistered `/analytics/events` and get 404 with swallowed errors. This covers every page_view, session_started, about 30 personalized events and all slow/failed-request diagnostics. The unit tests assert the dead path. Owner decision needed: register the endpoint, or remove the client sink and tests. | N-1, U7, C7 |
| WS8-G2 | On hosts other than `app.userunr.com`, the top-level `/pricing` (marketing redirect to `/#pricing`) and `/` (MarketingSite) take precedence, so the in-app `PricingPage` and `HomePage` are unreachable. `UpgradeModal`'s default `upgrade_url` `/pricing` leads to the marketing anchor there. Static reading; needs a browser check. | new |
| WS8-G3 | `firebase` is imported dynamically but not declared in `frontend/package.json`; it appears only in `package-lock.json`. Build reproducibility risk. Firebase is inactive on Render (no `VITE_FIREBASE_*`), but it would receive `user_id` if configured. | new, U7 |
| WS8-G4 | Dead or unreachable code (static grep): 3 unrouted pages, 10 unimported components, 6 libs with only test importers, and the duplicate `legacyApiRequestWithRetry` (`api.js:146-200`). | new |
| WS8-G5 | Admin residue: `frontend/e2e/admin-operations-console.spec.ts` (stale, fails if run), `VITE_E2E_ADMIN` (`SessionContext.jsx:18`, `scripts/serve-production-e2e.mjs`), `lib/auth.js` `isAdminUser` (unused), RC-030 script requires `RC030_ADMIN_TOKEN`. Record in retired-features (WS-11). | C7(d) |
| WS8-G6 | `app.userunr.com` is hard-coded in the frontend and in API CORS, but `render.yaml` frontend `domains` lists only `userunr.com`. Where the app subdomain is mapped is UNKNOWN from the repo. | WS-7 |
| WS8-G7 | Frontend Playwright e2e and `test:production-build` are not run in CI. | test map |
| WS8-G8 | `docs/PERSONALIZED_JOBS_PREVIEW.md` still describes a frontend-only preview; baseline runs real mode. | new (WS-11 docs) |
| U10 | Authenticated `/jobs` payload and job cards not visually verified. | handoff L78 |
| U5 | Feature branch frontend commits `1bffdc21`, `85d4ddb2`, `77a19ba9`, `646ef39e`, `5574f396`, `06ace3ba`, `c62e2637`, `a579f499`, `0d7f2b5c` are UNMERGED (feature/admin-analytics-final-production @ ce3718b0). Same-subject commits exist on the baseline (`6675338c`, `82368269`, `f672a08c`, `e0ef7b14`, `f63832ab`, `af94ef4c`, `6ebc52d3`, `286f5708`). The residual `58a96674..ce3718b0` frontend diff mostly re-adds the retired admin files, plus edits to `analytics.js`, `api.js`, `personalizedJobsApi.js`, `JobsWorkspace.jsx`, `TrackerPage.jsx` and `ArtifactsPage.jsx`. Not analysed per commit. | U5 |
| — | Value of `VITE_ENABLE_ASSISTED_APPLY_PREPARATION` in any deployment (pilot AA-226). | UNKNOWN |

## Agent context and remaining work

**(a) Agent context packet: customer frontend**
- **Required reading:** this doc; `frontend/src/App.jsx`; `frontend/src/main.jsx`; `frontend/src/context/SessionContext.jsx`; `frontend/src/lib/api.js`; `frontend/package.json`; `render.yaml` (frontend block and the CV-render buildFilters); [backend-api.md](backend-api.md) for route names; [assisted-apply.md](../05-subsystems/assisted-apply.md) before touching `assistedApply*`.
- **Allowed paths:** `frontend/**` only. Do not edit the 5 CV-render files (`frontend/package.json`, `frontend/package-lock.json`, `frontend/scripts/render-cv-pdf.mjs`, `frontend/src/lib/cvStudio.js`, `frontend/src/lib/cvSocialLinks.js`) without coordinating a WS-4/WS-7 review, because they redeploy and change the API and worker.
- **Tests to run:** `npm --prefix frontend run test`; `npm --prefix frontend run check`; when touching Jobs, CV or evidence, also `npm --prefix frontend run test:production-build` and the 3 current Playwright specs.
- **Prohibited:**
  - reading or printing `frontend/.env.local` values;
  - restoring admin routes/pages (retired);
  - adding calls to unregistered backend endpoints;
  - sending the bearer token to absolute URLs;
  - weakening `require_legal_answer_confirmation` or the extension never-submit boundary;
  - deploys or `render.yaml` edits (WS-7).

**(b) Registry proposal**

| subsystem id | name | owned globs | primary doc | test globs | owner WS |
|---|---|---|---|---|---|
| `frontend-app` | Customer web frontend | `frontend/**` | `docs/reverse-engineering/01-architecture/frontend-app.md` | `frontend/src/**/*.test.js`, `frontend/scripts/*.test.mjs`, `frontend/e2e/*.spec.ts` | WS-8 |

**(c) Gap / ticket candidates**
1. Decide product-telemetry fate (WS8-G1, U7): either register a minimal `POST /analytics/events`, or delete the client sink, API diagnostics persistence and their tests.
2. Delete the stale `frontend/e2e/admin-operations-console.spec.ts` and the `VITE_E2E_ADMIN`/`isAdminUser` residue (WS8-G5).
3. Fix `/pricing` and `/` host shadowing, or route upgrade links to the app subdomain (WS8-G2), after a browser check.
4. Declare or remove the `firebase` dependency (WS8-G3).
5. Remove or route orphan pages, components and libs, and the legacy retry duplicate (WS8-G4).
6. Wire frontend Playwright (3 current specs) and `test:production-build` into CI (WS8-G7; WS-7).
7. Signed-in visual verification of `/jobs` (U10).
8. Owner decision on the unmerged feature-branch frontend commits (U5).
