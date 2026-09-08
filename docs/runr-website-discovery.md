# Runr Website Discovery Report

Generated on 2026-06-24 from repository inspection only.

Scope note: this report is based on source code, checked-in documentation, configuration, route definitions, UI text, and non-secret asset metadata. Real environment values, databases, logs, and user data were not inspected.

## 1. Executive summary

Runr is already a substantial authenticated web application, but it does not yet have a public marketing website. The current Vite/React frontend protects the main application behind Clerk authentication; unauthenticated visitors are routed to sign-in/sign-up flows rather than an indexable product story. This is the largest website gap.

The strongest confirmed product story is not "generic AI job search". It is an operations workspace for job seekers: build sourcing workspaces, run job discovery or Quick Apply workflows, screen and rank jobs, generate application documents, track applications, and manage referral outreach from one app.

The product has enough functionality for a serious public website, but the website should avoid unverified claims. The repository does not confirm customer outcomes, testimonials, compliance certifications, search-volume data, enterprise readiness, or final production pricing. Several areas need founder confirmation before public launch, especially brand spelling, pricing, legal documents, and which feature set is safe to market.

The recommended website architecture is a separate static marketing site in the same repository, preferably Astro, deployed on the root domain while the existing app remains on an app subdomain. This keeps SEO/public content separate from the authenticated SPA, avoids adding unnecessary backend complexity, and lets the product app continue evolving independently.

### Repository structure reviewed

Top-level structure found during the audit:

| Area | Evidence | Website relevance |
| --- | --- | --- |
| Backend app | `backend/`, `workspace_runner.py`, `pyproject.toml`, `requirements*.txt` | API, auth, billing, runs, artifacts, documents, tracker, referrals, admin |
| Frontend app | `frontend/`, `frontend/src/App.jsx`, `frontend/package.json` | Main user experience, route map, UI copy, brand treatment |
| Documentation | `README.md`, `ARCHITECTURE.md`, `docs/architecture/current_system.md`, `docs/deployment/*`, `docs/security/*` | Product explanation, deployment assumptions, trust evidence |
| Deployment | `render.yaml`, `deploy/` | Current production architecture and domain assumptions |
| Assets | `frontend/*.png`, `screenshots/*.png`, `image.png`, `user_config/*` | Screenshot inventory and missing brand assets |
| Generated/user data | `generated_docs/`, `Jobs-Urls/`, `logs/`, `.backend_data/`, `.backend_storage/`, `user_config/` | Not suitable as marketing source without review |

### Frameworks and major dependencies

| Layer | Confirmed stack | Evidence |
| --- | --- | --- |
| Frontend | React 18, Vite 5, React Router 6, Clerk React, Recharts, Tailwind CDN, custom CSS | `frontend/package.json`, `frontend/index.html`, `frontend/src/App.jsx` |
| Backend | Python 3.11, custom API server/routes, SQLite local default, Turso production option, object storage local/S3/R2 | `pyproject.toml`, `backend/api/server.py`, `backend/config/env_schema.py`, `render.yaml` |
| Auth | Clerk frontend/backend session flow; API tokens for backend access | `frontend/src/main.jsx`, `frontend/src/context/SessionContext.jsx`, `backend/security/auth.py`, `backend/integrations/clerk.py` |
| Billing | Creem checkout, portal, webhooks, promo codes, quotas | `backend/config/plans.py`, `frontend/src/pages/PricingPage.jsx`, `docs/deployment/creem.md` |
| AI/provider integrations | DeepSeek and ScrapeOps are configured as provider dependencies; live networking discovery is feature-flagged | `README.md`, `backend/config/env_schema.py`, `backend/capabilities/networking/discovery.py` |

## 2. What Runr is

### One sentence

Runr is an authenticated job-search operations app that helps candidates turn job sources, exact job links, career assets, application documents, tracking, and referral outreach into one repeatable workflow.

Claim status: partly confirmed by routes and UI; "job-search operations" is inferred positioning.

### Short paragraph

Runr helps job seekers create sourcing workspaces, run job discovery or Quick Apply workflows, review job matches, generate tailored CV/application documents, track application status, and manage referral outreach. The current app is built around an authenticated dashboard rather than a public website.

Claim status: confirmed by `frontend/src/App.jsx`, page components under `frontend/src/pages/`, API routes under `backend/api/routes/`, and workflow documentation.

### Non-technical explanation

Runr gives a job seeker one place to organize their search. Instead of keeping job links, CV versions, referral contacts, generated documents, and application updates in separate tools, the app groups those steps into workspaces and tracked runs.

Claim status: inferred from confirmed functionality.

### Technical explanation

Runr is a React/Vite frontend backed by a Python API and worker system. Users authenticate through Clerk, create or use workspaces, trigger queued or synchronous runs, persist run/job/artifact/review data, upload candidate assets, generate document exports, and manage billing through Creem. Local development uses SQLite and local object storage; production configuration requires Turso and S3-compatible object storage.

Claim status: confirmed by `README.md`, `ARCHITECTURE.md`, `backend/config/env_schema.py`, `render.yaml`, and route files.

### Description for a potential customer

Runr helps you run a structured job search: collect opportunities, decide which ones deserve attention, generate application materials, keep your tracker current, and organize referral follow-up.

Claim status: confirmed/inferred. Do not add outcome promises such as "get hired faster" without evidence.

### Description for an investor or business partner

Runr is building an operating layer for high-intent job seekers, combining job sourcing, application document generation, application tracking, quota-based monetization, and referral workflow support in a single authenticated product.

Claim status: inferred business framing from confirmed product surface and billing code.

### Main problem Runr solves

Confirmed problem from UI and docs: job seekers have fragmented workflows across job boards, employer sites, CV files, generated documents, spreadsheets, inboxes, and referral contacts.

### Current solution offered

Confirmed solution: an authenticated app with workspaces, Quick Apply, run management, a tracker, career assets, CV Studio, referrals, settings, pricing, and admin operations.

### Product category

Inferred: job-search automation, application workflow management, and candidate operations software.

### Main user journey

1. Sign in or create an account through Clerk.
2. Add profile/settings and career assets.
3. Create a workspace for recurring sourcing, or use Quick Apply for an exact job URL.
4. Run the workflow.
5. Review included/rejected jobs and generated artifacts.
6. Generate, export, or edit documents.
7. Track application status.
8. Use referral/contact tools to support outreach.
9. Monitor usage and billing.

### Core value proposition

Inferred: Runr turns a scattered job search into a structured workflow with reusable workspaces, generated documents, tracking, and referral support.

### Strongest product differentiator

Confirmed differentiator: the app combines workspace-based sourcing, exact-link Quick Apply, tailored document generation, application tracking, and referral/contact workflow in one product.

Inferred differentiator: Runr is more operational than a simple resume editor or spreadsheet tracker.

### Clearest reason someone would choose Runr

Inferred: a serious job seeker wants one repeatable system for applying, tracking, and following up instead of manually stitching together spreadsheets, job-board tabs, AI writing tools, and contact lists.

### Likely alternatives or competitors

Not confirmed from the current repository.

Reasonable comparison categories:

- Spreadsheets and Notion-style personal trackers.
- Job application trackers.
- Resume/CV tailoring tools.
- Browser automation or job-application automation tools.
- General AI writing assistants.
- Manual use of job boards and employer career pages.

Named competitor claims require separate market research.

### What Runr does not currently do

Confirmed or not found:

- No public marketing homepage in the active frontend.
- No confirmed teams, organizations, invitations, or multi-seat collaboration UI.
- No confirmed employer/recruiter-facing product.
- No confirmed native mobile app.
- No confirmed public API documentation site.
- No confirmed testimonials, customer logos, or case studies.
- No confirmed legal pages in the frontend.
- No confirmed self-service account deletion UI.
- No confirmed compliance certifications.

## 3. Confirmed product facts

### Product identity

| Topic | Confirmed evidence | Finding |
| --- | --- | --- |
| Product name | `frontend/src/components/AppShell.jsx`, documentation | App shell renders `runr.` lowercase with a period. Docs often use `Runr`. Official capitalization is not settled from repo alone. |
| Tagline | `frontend/src/components/AppShell.jsx` | App shell subtitle says `High Performance Ops`. It appears to be an app-shell tagline, not necessarily final marketing copy. |
| Logo | `frontend/src/components/AppShell.jsx`, asset scan | The app uses a CSS-built brand mark. No dedicated SVG/PNG product logo was found for marketing use. |
| Favicon | `frontend/index.html`, asset scan | No favicon file or favicon link was found. |
| Typography | `frontend/index.html`, `frontend/src/styles.css` | Google font: Plus Jakarta Sans. Material Symbols Outlined is loaded for icons. |
| Icon style | App components | Material Symbols Outlined icon ligatures are used widely. |
| Brand colors | `frontend/index.html`, `frontend/src/styles.css` | Main palette includes teal primary `#14B8A6`, pale surfaces, dark text, and a dark theme. |
| Visual style | App screenshots and CSS | Dashboard-like authenticated app with rounded panels, soft shadows, dense forms, charts, and operational cards. |
| Component library | `frontend/package.json`, source scan | No formal design-system package found. UI is custom React/Tailwind/CSS. |
| Tone of voice | App page copy | Direct, operational, workflow-oriented. Examples: "what needs attention today", "job-search operating rhythm", "Browse workspaces as simple rows." |
| Public metadata | `frontend/index.html` | Title is `runr. frontend`. No meta description, canonical, Open Graph, Twitter cards, favicon, manifest, or structured data found. |

### Product surface

Confirmed app pages:

- Dashboard.
- Workspaces.
- Quick Apply.
- Runs and run detail.
- Job workspace detail.
- Tracker.
- Tracker ATS view.
- Job description view.
- Career Assets/Documents.
- Career Memory guide.
- CV Studio.
- Referrals.
- LinkedIn CSV guide.
- Settings.
- Pricing.
- Admin.
- Admin events.
- Admin ScrapeOps usage.

### Data model and core objects

Confirmed tables/models include users, workspaces, workflow templates, runs, run job sets, blobs, artifacts, reviews, application status history, candidate assets, candidate documents, workspace/run document bindings, API tokens, secrets, analytics events, billing records, subscriptions, and quotas.

Evidence: `backend/database/schema.py`, `backend/repositories/sqlite_migrations.py`.

### Integrations

Confirmed integration surfaces:

- Clerk auth and webhooks.
- Creem checkout, portal, webhooks, promo codes.
- ScrapeOps provider configuration and admin usage/policy screen.
- DeepSeek provider configuration for AI-assisted extraction/generation workflows.
- Google OAuth for tracker email integration.
- Turso production database option.
- Cloudflare R2/S3-compatible object storage option.
- Firebase Analytics optional frontend analytics configuration.

Evidence: `backend/config/env_schema.py`, `render.yaml`, `backend/integrations/`, `frontend/src/pages/TrackerPage.jsx`, `frontend/src/lib/analytics.js`.

## 4. Inferred product positioning

### Positioning statement

Runr is best positioned as a job-search operations workspace for serious candidates who want a repeatable system for sourcing, applying, tracking, and following up.

Status: inferred from the app. This phrase is not confirmed as official positioning.

### Suggested category language

- Primary: job-search operating workspace.
- Secondary: application workflow automation.
- Supporting: tailored CV/document generation, application tracking, referral outreach management.

Status: inferred.

### Strong website angle

The public site should lead with the complete workflow, not with AI alone. AI/provider features exist, but the app's clearer distinction is workflow orchestration across workspaces, runs, documents, tracker, and referrals.

Status: inferred from feature breadth.

### Differentiator language that is safe with current evidence

Safe:

- "Create sourcing workspaces and Quick Apply runs."
- "Generate and manage application documents."
- "Track applications and follow-up status."
- "Import LinkedIn connection exports for referral matching."
- "Manage usage and subscription from the app."

Needs validation:

- "Automates your entire job search."
- "Finds the best jobs for you."
- "Compliant job scraping."
- "Works with every job board."
- "Guaranteed to improve response rates."
- "Enterprise-grade security."

## 5. Missing information

The following should not be guessed in website copy:

| Missing item | Why it matters | Current repository status |
| --- | --- | --- |
| Official brand spelling | Public nav, logo, domain, title tags | App says `runr.`; docs say `Runr`. Not confirmed from the current repository. |
| Final tagline | Hero and metadata | `High Performance Ops` exists in app shell but may be internal. Not confirmed from the current repository. |
| Founder-approved ICP | Homepage targeting | Job seeker is clear; specific persona is not. Not confirmed from the current repository. |
| Final pricing policy | Pricing page and CTAs | Plan amounts exist, but Creem setup docs show remaining setup. |
| Trial/free plan strategy | Conversion CTA | `none` plan has zero quota. "Start free" is not currently supported as a useful product promise. |
| Customer proof | Trust section | No testimonials, logos, case studies, or metrics found. |
| Legal documents | Footer and signup trust | No Privacy, Terms, Cookie, DPA, or account deletion pages found. |
| Compliance posture | Security page | No certifications or formal legal/security assessments found. |
| Public product screenshots | Hero and feature visuals | Existing screenshots are internal/stale or potentially not marketing-ready. |
| Support process | Support page/footer | App shell has a Support control, but no route or handler was found. |
| Documentation strategy | Help center | App shell has Documentation control, but no route or handler was found. |
| Launch domain plan | SEO, auth redirects, CORS | Deployment docs suggest app/api origins, but final public site/root domain strategy needs confirmation. |

> Not confirmed from the current repository.

## 6. Target audiences

| User type | Who they are | Main objective | Main frustration | Feature they care about most | Benefit Runr gives them | Likely objection | CTA | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Active job seeker | Candidate actively applying to jobs | Run a structured job search | Too many jobs, tabs, files, and tracker updates | Workspaces, Quick Apply, Tracker, Documents | One workflow for applying and tracking | "Will this save time without adding complexity?" | Create account | Confirmed/inferred |
| Exact-job applicant | Candidate who already has a job URL | Generate tailored materials for a specific role | Rewriting CV/cover material manually | Quick Apply | Fast path from job link to document run | "Will it understand this posting?" | Try Quick Apply | Confirmed/inferred |
| High-volume applicant | Candidate applying across many sources | Find, screen, and process many opportunities | Manual sourcing and prioritization | Workspaces, Runs, quotas | Repeatable sourcing and review flow | "Will sources be reliable and within limits?" | Build a workspace | Inferred |
| Referral-focused candidate | Candidate using network contacts | Find and track contacts related to applications | LinkedIn exports and outreach status are hard to connect to jobs | Referrals, LinkedIn CSV import, outreach drafts | Referral matching and status tracking | "Will my contacts stay private?" | Import connections CSV | Confirmed/inferred |
| Career asset maintainer | Candidate with multiple CV/profile assets | Maintain reusable source material | CV versions and facts drift | Career Assets, Career Memory, CV Studio | Central source material and editable output | "Will it make claims I did not provide?" | Upload career assets | Confirmed/inferred |
| Admin/operator | Internal operator or founder/admin | Monitor users, billing, events, ScrapeOps usage, secrets | Operational complexity | Admin pages | Internal control and observability | Not a public customer segment | Sign in to admin | Confirmed |
| Investor/partner | Business stakeholder | Understand product, market, trust posture | Needs clarity without app access | Public website, product pages, security page | Clear narrative and roadmap | "Is this production-ready and defensible?" | Book a call/contact | Inferred |

### Recommended primary website audience

Primary: active job seekers who are serious enough to manage a pipeline, tailor documents, and follow up with referrals.

### Secondary audiences

- High-volume applicants.
- Career switchers or international applicants managing multiple CV styles.
- Referral-focused candidates.
- Investors/partners evaluating the product.

### Audiences that should not dominate the homepage

- Admin/operators.
- Employers/recruiters.
- Enterprise teams.
- Developers/API users.

These audiences are either internal, not supported by current UI, or not confirmed from the current repository.

### Landing page recommendation

Runr does not need many audience pages at launch. Recommended launch structure:

- One strong homepage for serious job seekers.
- One product/how-it-works page.
- One pricing page after pricing is confirmed.
- Later audience pages for "Quick Apply", "Job-search workspace", and "Referral tracking" if analytics show demand.

## 7. User roles

| Role | Evidence | Capabilities | Website relevance |
| --- | --- | --- | --- |
| Signed-out visitor | `frontend/src/App.jsx` public routes | Can access `/sign-in/*` and `/sign-up/*`; protected app redirects to sign-in. | Current app has no public marketing experience. |
| Authenticated user | `ProtectedAppRoute`, session context, routes | Can access dashboard, workspaces, Quick Apply, runs, tracker, documents, referrals, settings, pricing. | Primary customer. |
| Admin user | `RequireAdminRoute`, `frontend/src/lib/auth.js` | Can access `/admin`, `/admin/events`, `/admin/scrapeops`. Role is based on `user.role === "admin"`. | Internal only. |
| API token roles | `backend/security/auth.py` | Role defaults exist for admin, editor, reviewer, viewer scopes. | Not a public marketing focus unless public API is later created. |
| Workspace owner | `docs/security/runr_data_ownership.md`, backend models | Workspace/run access is scoped by ownership and user id for non-admins. | Useful trust signal. |

Not found:

- Teams or organizations.
- Invitations.
- Shared workspaces for multiple users.
- Employer/recruiter roles.

## 8. Main user journeys

### Account access journey

1. Visitor opens app route.
2. If signed out, Clerk sign-in/sign-up is shown.
3. Frontend retrieves a Clerk backend token using the `runr_backend` template.
4. Frontend calls `/auth/me`.
5. App renders authenticated routes.

Evidence: `frontend/src/App.jsx`, `frontend/src/main.jsx`, `frontend/src/context/SessionContext.jsx`.

Gaps:

- No public onboarding route found.
- Password recovery/email verification behavior is delegated to Clerk configuration and is not confirmed from repo.

### Workspace sourcing journey

1. User opens Workspaces.
2. User creates a workspace with source, targeting, automation, and baseline CV settings.
3. User runs the workspace or schedules it.
4. Backend creates a run and worker stages process jobs/artifacts.
5. User reviews results in run detail, tracker, or documents.

Evidence: `frontend/src/pages/WorkspacesPage.jsx`, `backend/api/routes/workspace.py`, `backend/orchestration/`, `backend/bootstrap.py`.

### Quick Apply journey

1. User opens Quick Apply.
2. User pastes an exact job posting URL.
3. User chooses baseline CV and generation mode.
4. User starts a run.
5. User reviews/generated documents from the run.

Evidence: `frontend/src/pages/QuickApplyPage.jsx`, `backend/api/routes/workspace.py`.

### Tracker journey

1. User opens Tracker.
2. User searches, filters, and updates application rows.
3. User edits statuses, notes, email confirmation, job descriptions, and generated documents.
4. User can use Gmail sync detections when configured.

Evidence: `frontend/src/pages/TrackerPage.jsx`, `backend/api/routes/tracker.py`.

### Career assets and CV journey

1. User uploads CV or supporting assets.
2. App stores candidate assets/documents.
3. User uses Career Assets, Career Memory, and CV Studio to manage or edit output.
4. User exports documents or packages.

Evidence: `frontend/src/pages/ArtifactsPage.jsx`, `frontend/src/pages/CvStudioPage.jsx`, `backend/api/routes/documents.py`, `backend/api/routes/career_memory.py`.

### Referral journey

1. User manually creates referral contacts or imports LinkedIn connections CSV.
2. Runr matches contacts to application companies.
3. User tracks outreach status and can draft outreach.

Evidence: `frontend/src/pages/ReferralsPage.jsx`, `frontend/src/pages/LinkedInConnectionsGuide.jsx`, `backend/api/routes/tracker.py`, `backend/capabilities/networking/`.

### Billing journey

1. User opens Pricing.
2. App fetches plans and subscription state.
3. User starts Creem checkout or billing portal.
4. App confirms signed checkout return and/or waits for webhook sync.

Evidence: `frontend/src/pages/PricingPage.jsx`, `backend/config/plans.py`, `backend/api/routes/admin.py`, `docs/deployment/creem.md`.

## 9. Complete feature inventory

| Feature | What it does | Who can use it | User benefit | Route/screen | Code location | Maturity | Public website? | Suggested customer-facing description | Limitations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Clerk sign-in/sign-up | Authenticates users through Clerk components | Signed-out users | Account access | `/sign-in/*`, `/sign-up/*` | `frontend/src/App.jsx`, `frontend/src/main.jsx` | Functional but provider-config dependent | Yes | Secure account access with Clerk-powered authentication | Exact auth methods, password reset, and verification rules are configured outside repo |
| Session bridge | Gets Clerk backend token and loads `/auth/me` | Authenticated users | Connects frontend identity to backend permissions | App-wide | `frontend/src/context/SessionContext.jsx` | Functional | No | N/A | Depends on Clerk token template |
| Dashboard | Shows action plan, funnel, strategy, weekly summary, data fixes, aging, source effectiveness | Authenticated users | See what needs attention | `/`, `/dashboard` redirect | `frontend/src/pages/DashboardPage.jsx`, `/dashboard` API | Functional but data-dependent | Yes | See the job-search pipeline and next actions in one dashboard | Empty until workflows/tracker data exist |
| Workspace builder | Creates recurring sourcing workspaces with targeting, source, automation, and CV settings | Authenticated users | Repeatable sourcing workflow | `/workspaces` | `frontend/src/pages/WorkspacesPage.jsx`, `backend/api/routes/workspace.py` | Functional but complex | Yes | Build reusable job-search workspaces for recurring sourcing | Requires baseline CV and source setup; source reliability varies |
| Workflow templates | Provides starter flows such as search/apply, curated intake, blended sources, board collection | Authenticated users | Faster workspace setup | Workspaces/API | `backend/bootstrap.py`, `backend/orchestration/seeded_workspaces.py` | Functional | Maybe | Start from proven workflow templates | Template naming may be too technical for website |
| Quick Apply | Runs a workflow from an exact job posting URL | Authenticated users | Fast application path | `/quick-apply` | `frontend/src/pages/QuickApplyPage.jsx` | Functional | Yes | Paste a job link and generate application materials | Depends on URL accessibility and provider configuration |
| Runs list | Lists planned, queued, running, completed, failed, cancelled runs | Authenticated users | Monitor automation work | `/runs` | `frontend/src/pages/RunsPage.jsx` | Functional | Maybe | Track every job-search run from one place | Internal terminology may need simplification |
| Run detail/customer view | Shows run status, progress, included/rejected jobs, artifacts, reviews | Authenticated users | Understand results and take next action | `/runs/:runId` | `frontend/src/pages/RunDetailPage.jsx` | Functional | Yes, as screenshot/content | Review what each run found and produced | Can feel technical |
| Job workspace detail | Job-specific workspace view | Authenticated users | Manage a specific job output | `/job-workspaces/:runId/:jobId` | `frontend/src/App.jsx`, page component | Functional/unclear from route only | Maybe | Continue work on a specific job | Needs UX review before marketing |
| Tracker | Tracks application rows, statuses, notes, detections, generated documents | Authenticated users | Manage application pipeline | `/tracker` | `frontend/src/pages/TrackerPage.jsx`, `backend/api/routes/tracker.py` | Functional but dense | Yes | Keep application status, notes, documents, and follow-up in one tracker | Complex UI; terminology needs polish |
| Tracker kanban/table views | Displays applications by status and table views | Authenticated users | Faster pipeline review | `/tracker` | `frontend/src/pages/TrackerPage.jsx` | Functional | Yes | View your search as a pipeline | Needs responsive/accessibility verification |
| Gmail email sync | Connects Google email integration and imports application status detections | Authenticated users with Google config | Reduces manual tracker updates | `/tracker` plus callback | `frontend/src/pages/TrackerPage.jsx`, `backend/api/routes/tracker.py` | Functional but provider/review dependent | Maybe later | Sync inbox signals into application tracking | Requires Google OAuth setup and privacy/legal clarity |
| ATS assessment | Shows present/missing criteria and recommendations for a tracked job | Authenticated users | Improve application completeness | `/tracker/:reviewId/ats` | `frontend/src/pages/TrackerAtsPage.jsx` | Functional/data-dependent | Maybe | Check application materials against job criteria | Avoid claiming guaranteed ATS success |
| Job description view | Shows stored job description for a tracker row | Authenticated users | Reference posting details | `/tracker/job-descriptions/:reviewId` | `frontend/src/pages/JobDescriptionPage.jsx` | Functional | No | N/A | Not a standalone marketing feature |
| Career Assets/Documents | Uploads and manages CV/source files, filters assets, exports documents | Authenticated users | Centralize career material | `/documents` | `frontend/src/pages/ArtifactsPage.jsx`, `backend/api/routes/documents.py` | Functional | Yes | Keep CVs and career assets available for generated applications | Asset privacy/legal needs clear copy |
| Candidate document upload | Uploads CV/supporting files and polls processing | Authenticated users | Reuse source material | `/documents`, `/settings`, `/quick-apply` | `backend/api/routes/documents.py` | Functional | Yes | Upload career material once and reuse it across workflows | Supported file types and parsing quality need public clarification |
| Career Memory | Extracts/maintains facts and generates grounded outputs | Authenticated users | Reduce repeated profile rewriting | `/career-memory/guide`, documents/settings flows | `backend/api/routes/career_memory.py`, `backend/career_memory/` | Functional but early/unclear UX | Maybe | Build a career memory from your own source documents | Must avoid overclaiming fact accuracy |
| Career Memory guide | Explains how to use Career Memory | Authenticated users | In-app help | `/career-memory/guide` | `frontend/src/pages/DocumentAICanvasGuide.jsx` | Functional | Can inform website/help copy | Learn how source files improve generated application documents | Authenticated only today |
| CV Studio | Edits profile/design defaults and prints/saves PDF from browser | Authenticated users | Customize CV output | `/cv-studio` | `frontend/src/pages/CvStudioPage.jsx` | Functional but likely beta | Maybe later | Edit and preview CV output before export | Browser print/PDF flow may not feel polished |
| Tailored document generation | Generates CV/application packages from job and profile context | Authenticated users | Faster application preparation | Workspaces, Quick Apply, Runs, Documents | `backend/capabilities/tailored_documents/` | Functional/provider-dependent | Yes | Generate tailored application documents from your profile and target role | Quality depends on source material and provider setup |
| Bulk export | Bundles selected documents for download | Authenticated users | Export packages efficiently | `/documents`, tracker | `backend/api/routes/documents.py` | Functional | Maybe | Export selected application documents together | Export gate can block or warn |
| ATS export gate | Evaluates export readiness and can block/warn | Authenticated users | Reduce low-quality exports | `/documents` | `frontend/src/pages/ArtifactsPage.jsx`, `backend/api/routes/documents.py` | Functional | Maybe | Review export readiness before sending | Do not present as compliance or ATS guarantee |
| Referrals | Manages referral contacts and outreach status | Authenticated users | Organize networking | `/referrals` | `frontend/src/pages/ReferralsPage.jsx` | Functional | Yes | Track referral contacts alongside applications | Needs privacy-focused copy |
| LinkedIn CSV import | Imports user-exported LinkedIn connections CSV for referral matching | Authenticated users | Turns existing network export into searchable contacts | `/referrals`, `/referrals/linkedin-csv-guide` | `frontend/src/pages/ReferralsPage.jsx`, `LinkedInConnectionsGuide.jsx` | Functional | Yes, carefully | Upload your own LinkedIn connections export for referral matching | Do not imply official LinkedIn API partnership |
| Outreach drafts | Drafts referral/hiring-manager outreach | Authenticated users | Faster follow-up | `/referrals`, tracker API | `backend/capabilities/networking/outreach.py` | Functional | Maybe | Draft outreach from application and contact context | Needs review before sending |
| Target contact discovery | Discovers relevant people using live search/AI when enabled | Authenticated users | Find possible contacts | Tracker modal/API | `backend/capabilities/networking/discovery.py` | Experimental/feature-flagged | No at launch | N/A | Disabled by default; uses live external services |
| Pricing/subscription | Displays plans, starts checkout, manages billing portal | Authenticated users | Upgrade and manage quotas | `/pricing` | `frontend/src/pages/PricingPage.jsx`, `backend/config/plans.py` | Functional but setup-dependent | Yes after confirmation | Choose a plan based on monthly usage needs | Creem product IDs/setup must be verified before public pricing |
| Quotas/usage | Enforces and displays usage limits | Authenticated users/admin | Understand usage limits | `/settings`, `/pricing` | `backend/config/plans.py`, billing services | Functional | Yes | See monthly run, application, export, referral, and workspace limits | "No subscription" has zero quota |
| Promo codes | Admin creates/manages Creem promo codes | Admin | Acquisition/discount tooling | `/admin` | `frontend/src/pages/AdminPage.jsx`, admin API | Functional/internal | No | N/A | Internal only |
| Admin users/tokens/secrets | Manages users, API tokens, secrets | Admin | Operational control | `/admin` | `frontend/src/pages/AdminPage.jsx`, `backend/api/routes/admin.py` | Functional/internal | No | N/A | Do not market |
| Analytics events | Tracks/admin reviews analytics events | Admin | Product analytics | `/admin/events` | `frontend/src/pages/AdminEventsPage.jsx`, `/analytics/events` | Functional/internal | No | N/A | Consent/legal posture missing |
| ScrapeOps usage dashboard | Reviews provider usage, alerts, policy | Admin | Cost/provider control | `/admin/scrapeops` | `frontend/src/pages/AdminScrapeOpsPage.jsx` | Functional/internal | No | N/A | Internal only |
| Support control | Top-ribbon Support button | Authenticated users | Intended support access | App shell | `frontend/src/components/AppShell.jsx` | Placeholder/unclear | Needs website support page | N/A | No route/handler found |
| Documentation control | Top-ribbon Documentation button | Authenticated users | Intended docs access | App shell | `frontend/src/components/AppShell.jsx` | Placeholder/unclear | Needs docs/help page | N/A | No route/handler found |
| Notifications control | Icon button in shell | Authenticated users | Intended alerts | App shell | `frontend/src/components/AppShell.jsx` | Placeholder/unclear | No | N/A | No clear notification behavior found |
| Legal pages | Privacy/terms/cookie/account deletion | Public/users | Legal trust | None found | Not found | Missing | Yes, required | N/A | Must be created before broad launch |
| Teams/invitations | Multi-user collaboration | Not found | N/A | None found | Not found | Missing | No | N/A | Do not claim team support |

## 10. Route map

| Route | Page purpose | Authentication required | User roles | Main action | Current status |
| --- | --- | --- | --- | --- | --- |
| `/sign-in/*` | Sign in | No | Signed-out | Authenticate with Clerk | Functional |
| `/sign-up/*` | Create account | No | Signed-out | Register with Clerk | Functional |
| `/` | Dashboard | Yes | Authenticated | Review action plan and funnel | Functional |
| `/dashboard` | Redirect to dashboard | Yes | Authenticated | Redirect to `/` | Functional redirect |
| `/workspaces` | Workspace management | Yes | Authenticated | Create/run/schedule workspace | Functional |
| `/quick-apply` | Exact job URL workflow | Yes | Authenticated | Paste URL and start run | Functional |
| `/runs` | Runs list | Yes | Authenticated | Filter/open/delete runs | Functional |
| `/runs/:runId` | Run detail | Yes | Authenticated | Review run progress and jobs | Functional |
| `/job-workspaces/:runId/:jobId` | Job-specific workspace | Yes | Authenticated | Work on a job from a run | Functional/needs UX review |
| `/review-queue` | Legacy review route | Yes | Authenticated | Redirect to tracker | Redirects to `/tracker` |
| `/tracker` | Application tracker | Yes | Authenticated | Update applications and follow-up | Functional but dense |
| `/tracker/:reviewId/ats` | ATS assessment | Yes | Authenticated | Review criteria and recommendations | Functional/data-dependent |
| `/tracker/job-descriptions/:reviewId` | Job description detail | Yes | Authenticated | Read/copy job description | Functional |
| `/documents` | Career assets/documents | Yes | Authenticated | Upload, filter, export assets | Functional |
| `/career-memory` | Legacy career memory route | Yes | Authenticated | Redirect to documents memory view | Redirects |
| `/career-memory/guide` | Career Memory guide | Yes | Authenticated | Learn source document guidance | Functional |
| `/documents/ai-canvas-guide` | Legacy guide route | Yes | Authenticated | Redirect to Career Memory guide | Redirects |
| `/cv-studio` | CV editor/studio | Yes | Authenticated | Edit/preview/print CV | Functional but likely beta |
| `/artifacts` | Legacy artifacts route | Yes | Authenticated | Redirect to documents | Redirects |
| `/referrals` | Referral management | Yes | Authenticated | Import/manage contacts and outreach | Functional |
| `/referrals/linkedin-csv-guide` | LinkedIn CSV import guide | Yes | Authenticated | Follow CSV export/upload guide | Functional |
| `/settings` | Profile/settings/usage | Yes | Authenticated | Upload profile assets and save settings | Functional |
| `/pricing` | Authenticated pricing/billing | Yes | Authenticated | Upgrade/manage subscription | Functional but setup-dependent |
| `/admin` | Admin console | Yes | Admin | Manage users/tokens/secrets/billing | Functional/internal |
| `/admin/events` | Admin event log | Yes | Admin | Review analytics events | Functional/internal |
| `/admin/scrapeops` | ScrapeOps usage/policy | Yes | Admin | Monitor and configure provider policy | Functional/internal |
| `*` | Unknown route | Yes | Authenticated | Redirect to dashboard | Functional redirect |

Backend public/non-auth endpoint findings:

- Public health/system routes: `/`, `/health`, `/health/live`, `/health/ready`.
- Public billing/catalog route: `/billing/plans`.
- Public webhook routes: `/webhooks/clerk`, `/webhooks/creem`.
- Public Google callback route: `/tracker/email-integration/google/callback`.

Evidence: `backend/api/routes/system.py`, `backend/api/routes/admin.py`, `backend/api/routes/tracker.py`.

## 11. Current UX audit

| Issue | Evidence | User impact | Severity | Recommended fix | Effort estimate |
| --- | --- | --- | --- | --- | --- |
| No public marketing homepage | `frontend/src/App.jsx` protects app routes; only sign-in/sign-up are public | New visitors cannot understand product before auth; poor SEO | Critical | Build separate public website or public marketing routes | Medium |
| App title says `runr. frontend` | `frontend/index.html` | Looks unfinished in browser tabs/search previews | High | Replace with product-grade title and metadata | Very small |
| No meta description/Open Graph/favicon | `frontend/index.html`, asset scan | Weak search/social sharing; unprofessional launch | High | Add metadata, favicon set, OG image, manifest | Small |
| Brand capitalization inconsistent | App shell uses `runr.`; docs use `Runr` | Confusing brand system and copy | High | Founder chooses canonical spelling and logo usage | Very small decision; medium design work |
| Support and Documentation controls do not route anywhere | `frontend/src/components/AppShell.jsx` | Users see dead-end controls | High | Add routes/links or remove controls until ready | Small |
| Legal pages missing | Frontend route scan | Blocks trustworthy public launch and privacy-sensitive features | High | Create Privacy, Terms, Cookie, account deletion, data processing pages | Medium/large with legal review |
| Pricing is authenticated only | `/pricing` route sits behind `ProtectedAppRoute` | Visitors cannot evaluate pricing publicly | High | Create public pricing page after pricing is confirmed | Medium |
| Pricing setup may be incomplete | `CREEM_REMAINING_STEPS.md`, `backend/config/plans.py` empty default product IDs | Checkout may fail if provider products are not configured | High | Verify test/live Creem product IDs, checkout, webhooks | Medium |
| "Start free" would be misleading today | `none` plan quotas are all zero | Visitor expects usable free product but gets no capacity | High | Avoid "Start free" unless a real free/trial plan is created | Very small decision |
| Scraping/legal posture needs careful wording | `docs/scraping_strategy_report_2026-05-26.md` warns on terms/source policy | Risky claims could damage trust or create legal exposure | High | Market workflow benefits, not blanket scraping/compliance claims | Small copy/legal review |
| Onboarding is not obvious | No dedicated onboarding route found | First-time users may land in a complex app without setup guidance | High | Add guided first-run setup for CV, workspace, Quick Apply | Medium |
| Major pages are very dense | `WorkspacesPage.jsx`, `TrackerPage.jsx`, `SettingsPage.jsx` are large multifunctional pages | Users may miss key actions; mobile complexity risk | Medium | Split complex tasks into guided flows and progressive detail | Large |
| Route terminology drifts | Documents/Career Assets/Artifacts/Career Memory; Review Queue redirects | Users may not understand object names | Medium | Standardize IA labels and redirect strategy | Medium |
| Notifications icon lacks clear behavior | App shell control found; behavior not obvious | Creates expectation of alerts | Medium | Implement notifications or hide until ready | Small/medium |
| Screenshots are stale/not marketing-ready | `frontend/current-shell.png` shows disconnected backend panel and icon ligatures as text | Poor public first impression if reused | Medium | Capture clean production-like screenshots with sample data | Small |
| Admin/internal features are visible in code and app nav for admins | Admin routes | Marketing could accidentally overemphasize operator concerns | Medium | Keep admin out of public narrative | Very small |
| Accessibility not fully verified | Some aria labels found, but no audit report | Potential usability/legal issue | Medium | Run automated and manual accessibility checks before launch | Medium |
| Mobile UX not verified | Responsive classes exist but no full mobile audit found | Marketing claims about mobile usability would be unsupported | Medium | Test app and website at mobile breakpoints | Small/medium |
| Error handling is generic in route boundary | `RouteErrorBoundary` copy | Users may not know recovery path | Low | Improve page-specific recovery/help paths | Small |
| Career URL Discovery page appears unrouted | `frontend/src/pages/CareerUrlDiscoveryPage.jsx` not routed in `App.jsx` | Feature discoverability/status unclear | Low | Remove, route, or mark internal | Small |

## 12. Website goals

Primary website goals:

1. Explain Runr clearly before authentication.
2. Convert serious job seekers to sign up or request access.
3. Build trust for a privacy-sensitive workflow involving CVs, job applications, email, and contacts.
4. Clarify pricing and usage limits once billing setup is confirmed.
5. Provide public help/legal pages needed for launch.
6. Create an SEO-indexable surface separate from the authenticated app.

Secondary goals:

- Give investors/partners a concise product narrative.
- Reduce support burden with help docs and account deletion/privacy instructions.
- Establish a brand system that can be reused in app screenshots and ads.

Non-goals for launch:

- Marketing admin tools.
- Public API docs.
- Enterprise/team pages.
- Blog-heavy content engine before core pages exist.

## 13. Recommended sitemap

### Launch sitemap

| Page | URL | Priority | Reason |
| --- | --- | --- | --- |
| Homepage | `/` | Required | Public product story and primary conversion |
| Product / How it works | `/product` or `/how-it-works` | Required | Explains workspaces, Quick Apply, documents, tracker, referrals |
| Pricing | `/pricing` | Required after pricing confirmation | Lets visitors evaluate plans before auth |
| Security / Trust | `/security` | Required | CV/contact/email data requires trust explanation |
| Help | `/help` | Required | App shell already promises documentation/support |
| Contact | `/contact` | Required | Support/sales/founder contact path |
| Privacy policy | `/privacy` | Required | Legal/privacy launch requirement |
| Terms of service | `/terms` | Required | Legal launch requirement |
| Cookie policy | `/cookies` | Required if analytics/cookies used | Consent and tracking transparency |
| Account deletion | `/account-deletion` | Required | Data rights and app-store-style expectation |

### Later sitemap

| Page | URL | Priority | Reason |
| --- | --- | --- | --- |
| Use cases | `/use-cases` | Later | Split by Quick Apply, sourcing workspaces, referrals |
| Docs | `/docs` | Soon | Public user documentation |
| Changelog | `/changelog` | Later | Product momentum |
| Blog/resources | `/resources` | Later | SEO content after positioning is proven |
| Status | `/status` | Later | Useful when product has active users and incidents |
| About | `/about` | Later | Founder/company trust after core product pages |

Pages not recommended at launch:

- Teams.
- Enterprise.
- Developers/API.
- Recruiters/employers.

Not confirmed from the current repository.

## 14. Homepage content brief

| Section | Recommended content | Claim status | Evidence/notes |
| --- | --- | --- | --- |
| Announcement bar | Only use if there is a real beta/waitlist/pricing announcement | Requires validation | No launch announcement found |
| Navigation | Product, How it works, Pricing, Security, Help, Sign in, Create account | Confirmed/inferred | Matches product needs; app has sign-in/up |
| Hero eyebrow | Job-search operations for focused candidates | Inferred | Based on workflow breadth |
| Main headline | Run your job search from one focused workspace | Inferred | Safe high-level positioning |
| Supporting text | Runr brings job sources, exact job links, career assets, generated documents, application tracking, and referral follow-up into one workflow. | Confirmed/inferred | Supported by routes/features |
| Primary CTA | Create account | Confirmed | Sign-up route exists |
| Secondary CTA | See how it works | Inferred | Website page needed |
| Hero visual | Clean dashboard/workflow screenshot with sample data | Requires validation | Existing screenshots are stale/not ready |
| Trust section | Clerk auth, workspace ownership checks, private object storage architecture, signed downloads, webhook verification, log redaction | Confirmed code exists | Must phrase as implementation signals, not certification |
| Problem section | Job search is scattered across links, documents, trackers, inbox, referrals | Inferred | Product solves these surfaces |
| Solution section | Workspaces, Quick Apply, generated documents, tracker, referrals | Confirmed | App features |
| Main benefits | Structure your search; apply with better source material; track status; follow up with contacts; monitor usage | Confirmed/inferred | Avoid outcome guarantees |
| Feature section | Workspaces, Quick Apply, Career Assets, Tracker, Referrals, Pricing/usage | Confirmed | Routes/pages exist |
| How it works | Add career assets -> create workspace or Quick Apply -> review jobs -> generate/export documents -> track/follow up | Confirmed/inferred | Main journey |
| Use cases | Exact job link, recurring sourcing, referral-led search, document management | Confirmed/inferred | Feature inventory |
| Integrations | Clerk, Creem, Google email sync, LinkedIn CSV import, ScrapeOps/DeepSeek as provider dependencies | Confirmed | Be careful: LinkedIn CSV import is not official LinkedIn integration |
| Testimonials | Do not include | Unknown | No testimonials found |
| FAQ | Pricing, data privacy, LinkedIn CSV, Gmail sync, document generation, cancellation | Inferred | Must answer from confirmed facts |
| Final CTA | Create account or Join waitlist | Requires validation | Depends on launch readiness |
| Footer | Product, Pricing, Help, Security, Contact, Privacy, Terms, Cookies, Account deletion | Confirmed need | Legal pages missing |

## 15. Draft homepage copy

Use this as a starting brief, not final founder-approved copy.

### Header

- Logo: `runr.` or founder-approved variant.
- Nav: Product, How it works, Pricing, Security, Help.
- Actions: Sign in, Create account.

### Hero

Eyebrow: Job-search operations for focused candidates.

Headline: Run your job search from one focused workspace.

Body: Runr brings job sources, exact job links, career assets, generated documents, application tracking, and referral follow-up into one repeatable workflow.

Primary CTA: Create account.

Secondary CTA: See how it works.

Claim status: confirmed/inferred.

### Problem

Your job search should not live across twenty tabs, a stale spreadsheet, renamed CV files, and half-finished follow-ups.

Claim status: inferred.

### Solution

Runr gives each search a workflow: create a sourcing workspace, paste an exact job link with Quick Apply, review the run, generate application documents, track status, and organize referral outreach.

Claim status: confirmed/inferred.

### Main benefits

- Build reusable workspaces for recurring job searches.
- Use Quick Apply when you already have the posting.
- Keep CVs and source documents close to the workflow.
- Review generated application materials before export.
- Track applications, notes, statuses, and follow-up.
- Import your own LinkedIn connections CSV for referral matching.

Claim status: confirmed/inferred.

### Trust copy

Runr uses Clerk for account access, keeps workspace/run access scoped by user ownership checks, supports signed object-download URLs, verifies configured webhooks, and includes log redaction utilities for sensitive fields.

Claim status: confirmed code exists. Do not convert this into "secure", "GDPR-compliant", or "certified" without formal review.

### Pricing copy

Do not use final public pricing copy until founder confirms the model and Creem live products are configured.

Safe interim copy: Plans are based on monthly workflow usage, including runs, applications, CV exports, referral drafts, runner credits, and workspace limits.

Claim status: confirmed by `backend/config/plans.py`.

### FAQ topics

| Question | Safe answer direction |
| --- | --- |
| Is Runr a job board? | No. It is a workflow app for managing job sources, applications, documents, tracking, and referrals. |
| Does Runr apply automatically for me? | Not confirmed from the current repository. Describe current run/document/tracker flows instead. |
| Does Runr integrate with LinkedIn? | It imports user-exported LinkedIn connections CSV for referral matching. Do not imply official LinkedIn API integration. |
| Is Gmail required? | No. Email sync appears optional and provider-config dependent. |
| Can I use it for one job link? | Yes, Quick Apply is built around exact job URLs. |
| Is there a free plan? | Not currently as a useful product plan; `none` has zero quotas. Requires founder decision. |

## 16. Additional page briefs

| Page | Objective | Target visitor | Suggested sections | Primary CTA | Required content/assets | Launch priority |
| --- | --- | --- | --- | --- | --- | --- |
| Product | Explain core workflow | Job seeker | Overview, workspaces, Quick Apply, documents, tracker, referrals, screenshots | Create account | Clean screenshots, feature copy | Required |
| How it works | Make workflow concrete | First-time visitor | 5-step journey, example run, output examples | Start with Quick Apply | Sample job/search scenario | Required |
| Pricing | Explain plans and quotas | Buyer | Plan cards, quota table, billing FAQ, cancellation policy | Choose plan | Confirmed plan terms, Creem readiness | Required after confirmation |
| Security | Build trust | Privacy-sensitive users | Auth, access controls, file storage, webhooks, redaction, responsible claims | Create account/contact | Legal/security review | Required |
| Help center | Reduce support burden | Users | Getting started, CV upload, workspace setup, Quick Apply, tracker, referrals, billing | Open app/help | Public docs | Required/small |
| Contact | Provide human path | Prospects/users | Support, billing, privacy, partnerships | Contact Runr | Contact method | Required |
| Privacy | Legal/privacy transparency | Everyone | Data collected, purposes, processors, rights, contact | N/A | Legal policy | Required |
| Terms | Contractual terms | Users | Acceptable use, billing, cancellation, limitations, scraping/source responsibility | N/A | Legal policy | Required |
| Cookie policy | Tracking transparency | Visitors | Cookies/analytics, opt-out, consent | N/A | Analytics/cookie inventory | Required if cookies/analytics used |
| Account deletion | Data rights | Users | How to request/delete account/data | Request deletion | Support workflow | Required |
| Blog/resources | SEO education | Researchers | Job-search workflow guides | Subscribe/create account | Content strategy | Later |
| Changelog | Show momentum | Existing users | Product updates | Open app | Release process | Later |
| Status | Incident transparency | Existing users | Service status | Subscribe | Monitoring provider | Later |
| About | Company trust | Investors/partners | Mission, founder, contact | Contact | Founder bio/company details | Later |

## 17. Calls to action

### Recommended launch CTAs

| CTA | Use where | Status | Notes |
| --- | --- | --- | --- |
| Create account | Header, hero, final CTA | Confirmed route | Safe if sign-up is open |
| Sign in | Header/footer | Confirmed route | Existing app route |
| See how it works | Hero secondary | Website needed | Good before users commit |
| Build a workspace | Product/workspaces section | Confirmed feature | Should link to sign-up or product section |
| Try Quick Apply | Quick Apply section | Confirmed feature | Use only if quota/onboarding supports it |
| View pricing | Header/product pages | Needs public page | Pricing must be founder-confirmed |
| Contact Runr | Footer/security/legal | Requires contact path | Needed for support/privacy |

### CTAs to avoid until validated

- Start free.
- Automate my whole job search.
- Apply to hundreds of jobs.
- Get hired faster.
- Connect LinkedIn.
- GDPR-compliant.
- Enterprise-ready.

## 18. Pricing and business-model findings

### Implemented plan configuration

| Plan id | Display name | `price_eur` | Key quotas | Status |
| --- | --- | --- | --- | --- |
| `none` | No subscription | 0 | All major monthly quotas and workspaces are 0 | Confirmed, not a usable free plan |
| `launch` | Launch | 15 | 25 runs/month, 50 applications/month, 10 CV exports/month, 25 referral drafts/month, 5000 runner credits/month, 1 workspace | Confirmed in source |
| `momentum` | Momentum | 25 | 100 runs/month, 200 applications/month, 50 CV exports/month, 100 referral drafts/month, 25000 runner credits/month, 5 workspaces | Confirmed in source |
| `scale` | Scale | 79 | Unlimited quotas represented as `-1` | Confirmed in source |

Evidence: `backend/config/plans.py`.

### Billing implementation

Confirmed:

- Creem checkout and portal endpoints exist.
- Creem webhook route exists.
- Checkout return confirmation exists.
- Promo code field exists on pricing page.
- Admin promo-code management exists.
- Plan product IDs are loaded from environment variables.
- Legacy aliases map `free -> none`, `pro -> momentum`, `business -> scale`.

Evidence: `frontend/src/pages/PricingPage.jsx`, `backend/api/routes/admin.py`, `backend/config/plans.py`, `docs/deployment/creem.md`.

### Pricing caveat

`CREEM_REMAINING_STEPS.md` says Creem test/live products, product IDs, webhooks, and checkout testing still need setup. Therefore the website should not present pricing as final production pricing until the founder confirms the model and checkout is verified end-to-end.

### Recommended pricing page approach

Recommended: display current pricing only after:

1. Founder confirms plan names, prices, quotas, currency, billing interval, taxes/VAT wording, cancellation policy, and refund policy.
2. Creem test and live product IDs are configured.
3. Checkout, portal, webhooks, and quota sync are verified.
4. Legal terms cover subscriptions.

If those are not complete, use "Join the waitlist" or "Contact us" instead of "Start free".

## 19. Trust, security, and legal findings

### Confirmed trust signals

| Signal | Evidence | Website-safe wording |
| --- | --- | --- |
| Clerk authentication | `frontend/src/main.jsx`, `backend/integrations/clerk.py` | Account access is handled through Clerk. |
| Backend token/session bridge | `frontend/src/context/SessionContext.jsx` | The app verifies authenticated sessions before accessing protected routes. |
| Role/admin route guard | `frontend/src/lib/auth.js`, `frontend/src/App.jsx` | Admin screens are restricted to admin users in the app. |
| Workspace ownership checks | `docs/security/runr_data_ownership.md` | Runr is designed to scope workspace and run access by user ownership. |
| API token hashing | `backend/security/auth.py` | API tokens are hashed before storage. |
| Secret references | `backend/security/secrets.py` | Secrets can be referenced separately rather than embedded directly. |
| Log redaction utilities | `backend/security/redaction.py` | Sensitive fields are redacted in supported logging paths. |
| Webhook signature verification | `backend/integrations/clerk.py`, `backend/integrations/creem.py` | Clerk and Creem webhook signatures are verified by backend code. |
| Signed object URLs | `backend/config/env_schema.py`, storage routes/docs | Object downloads support time-limited signed URLs. |
| Production storage/database expectations | `backend/config/env_schema.py`, `render.yaml` | Production is configured for Turso and S3/R2-compatible object storage. |

### Claims that must not be made yet

- GDPR-compliant.
- SOC 2 certified.
- ISO certified.
- HIPAA compliant.
- End-to-end encrypted.
- Fully private by design.
- Legally compliant scraping.
- Works with every job board.
- No human review needed.
- Guaranteed ATS compatibility.
- Guaranteed job-search outcomes.

Not confirmed from the current repository.

### Missing legal/privacy functionality

| Area | Current status | Risk |
| --- | --- | --- |
| Privacy policy | No route found | Required for handling CVs, contacts, email sync, analytics |
| Terms of service | No route found | Required for subscriptions and acceptable use |
| Cookie policy | No route found | Needed if analytics/cookies are used |
| Data processing information | No route found | Needed for EU/GDPR-oriented trust |
| Account deletion instructions | No route found | Users need clear data-rights path |
| Consent management | No consent UI found | Firebase/analytics/email/contact data need legal review |
| Terms acceptance | No explicit acceptance flow found | Signup legal acceptance may be missing or delegated outside app |
| Data retention policy | Not clearly found | Needed for uploaded assets, logs, generated docs, email sync |

### Security concerns requiring developer review

- Confirm CSP, HSTS, X-Frame-Options/frame-ancestors, Referrer-Policy, and Permissions-Policy headers for production.
- Confirm generic rate limiting or abuse controls beyond quota enforcement.
- Confirm privacy treatment for Firebase Analytics and backend analytics events.
- Confirm Google OAuth scopes and consent copy before marketing email sync.
- Confirm backup/restore and deletion workflows for Turso and object storage.
- Confirm CORS origins for website/app/API domain plan.
- Confirm scraping/source policy and robots/terms handling before marketing broad sourcing claims.

This is a product audit, not a formal security certification.

### Recommended footer/form links

- Privacy.
- Terms.
- Cookies.
- Security.
- Account deletion.
- Contact/support.
- Billing support.

## 20. SEO strategy

### Current SEO state

| SEO item | Current status | Evidence |
| --- | --- | --- |
| Public indexable homepage | Missing | App routes are protected |
| Page title | Weak | `runr. frontend` |
| Meta description | Missing | `frontend/index.html` |
| Canonical URL | Missing | `frontend/index.html` |
| Robots directives | Missing | No robots file found in active frontend |
| Sitemap | Missing | No sitemap found |
| Open Graph/Twitter tags | Missing | `frontend/index.html` |
| Structured data | Missing | No schema found |
| Favicon/manifest | Missing | Asset/index scan |
| Semantic headings | Present in app pages, but app is authenticated | Page components |
| Image alt text | Not fully audited | Needs website implementation |
| Public internal links | Missing | No public website |
| Localization | Not found | No i18n structure found |

### Primary search topic

Inferred: job search workflow software.

### Secondary search topics

- Job application tracker.
- Job search automation.
- Tailored CV generator.
- Application document generator.
- Referral tracking for job search.
- Job search pipeline.
- Job sourcing workspace.

No search-volume numbers are claimed.

### Likely visitor search intent

- "I need a better system for applying to jobs."
- "I need to track applications and follow-ups."
- "I need to tailor CVs for jobs."
- "I need to organize referrals and contacts."
- "I want to reduce manual job-search admin."

### Suggested homepage SEO fields

Title: `Runr - Job Search Workflow Software for Applications, Documents, and Follow-Up`

Meta description: `Runr helps serious job seekers organize sourcing workspaces, Quick Apply runs, tailored application documents, application tracking, and referral follow-up in one workflow.`

Needs founder approval.

### Suggested heading structure

- H1: Run your job search from one focused workspace.
- H2: Stop managing applications across tabs, files, and spreadsheets.
- H2: Build workflows for the way you search.
- H2: From job link to generated documents.
- H2: Track applications and referrals together.
- H2: How Runr works.
- H2: Plans for different job-search rhythms.
- H2: Frequently asked questions.

### Technical SEO fixes

- Build public static pages.
- Add `robots.txt`.
- Add XML sitemap.
- Add canonical tags.
- Add Open Graph/Twitter metadata.
- Add product/organization structured data only after legal/company details are confirmed.
- Add optimized social image.
- Add favicon and web app manifest.
- Keep authenticated app routes out of search indexing.
- Use descriptive URLs and internal links.
- Add accessible image alt text.
- Monitor Lighthouse/page speed before launch.

## 21. Design direction

### Recommended brand personality

Runr should feel focused, competent, calm, and operational. The app manages sensitive, high-effort career work, so the public site should feel more like a premium productivity tool than a playful consumer app.

### Recommended visual choices

| Element | Direction |
| --- | --- |
| Color | Keep teal as a primary accent, but add neutral depth and one restrained secondary accent to avoid a one-note palette. |
| Typography | Continue Plus Jakarta Sans or choose a similarly crisp sans. Use clear hierarchy; avoid oversized text inside product panels. |
| Layout | Dense but readable sections; product visuals should carry the page. Avoid fake dashboard cards where real screenshots work. |
| Radius | Use moderate radii, generally 8-16px on website cards/screenshots. Current app often uses very large rounded panels; marketing site can be more refined. |
| Shadows | Soft, minimal shadows for screenshots and focused cards. |
| Icon style | Use one icon family consistently. Material Symbols is consistent with app, but lucide-style icons may look sharper on marketing pages if adopted consistently. |
| Illustration | Prefer real product screenshots and annotated UI over abstract illustrations. |
| Photography | Not required at launch. If used, choose real desk/career-context imagery, not generic stock. |
| Animation | Subtle transitions, screenshot reveals, and workflow step highlighting. Avoid heavy decorative animation. |
| Screenshot presentation | Use realistic sample data, crop responsibly, and avoid exposing personal data. |
| Accessibility | Color contrast, keyboard navigation, focus states, reduced motion, semantic HTML, alt text. |

### Overall feel

Recommended: premium, focused, professional, friendly enough to reduce anxiety, but not lifestyle-oriented.

Avoid:

- Overly technical developer-product look.
- Overly playful AI-product gradients.
- Enterprise-heavy tone.
- Lifestyle influencer/job-coach aesthetic.

### Three possible design directions

| Direction | Description | Benefits | Risks | Suitability |
| --- | --- | --- | --- | --- |
| Safe and professional | Clean SaaS/productivity site, white/pale surfaces, teal accent, clear screenshots | Trustworthy, easy to build, fits current app | May feel generic if copy is weak | Best launch option |
| Distinctive and memorable | "Job-search command center" with strong workflow visuals, timeline/board motifs, sharper brand mark | More ownable and differentiated | Requires stronger visual design and screenshots | Good after brand decision |
| Bold and experimental | Immersive interactive workflow map with motion and AI/process visuals | Memorable, can signal innovation | Higher build cost, may distract from trust/legal clarity | Not recommended for first launch |

## 22. Asset inventory

| Asset | File path | Format | Resolution or size | Usable publicly? | Recommended usage | Problems |
| --- | --- | --- | --- | --- | --- | --- |
| Root screenshot duplicate | `image.png` | PNG | 1920x1040, about 512 KB | No, unless recaptured/approved | Reference only | Likely internal/stale; content needs review |
| Dashboard loading/current state | `screenshots/dashboard-loading-current-state.png` | PNG | 1920x1040, about 512 KB | No | Reference only | Loading/disconnected state is not marketing-ready |
| Current shell screenshot | `frontend/current-shell.png` | PNG | 1600x900, about 87 KB | No | Reference only | Shows disconnected backend panel and icon ligature text; stale |
| Shell short screenshot | `frontend/current-shell-short.png` | PNG | 1600x500, about 75 KB | No | Reference only | Stale/needs review |
| Shell short duplicate | `frontend/current-shell-short-2.png` | PNG | 1600x500, about 75 KB | No | Reference only | Duplicate/stale |
| Referrals screenshot | `frontend/playwright-referrals.png` | PNG | 2048x1158, about 70 KB | Maybe after review | Could inform referrals section | Needs sample-data/privacy review |
| Referrals fixed screenshot | `frontend/playwright-referrals-fixed.png` | PNG | 2048x1158, about 94 KB | Maybe after review | Could inform referrals section | Needs sample-data/privacy review |
| Referrals connected screenshot | `frontend/playwright-referrals-connected.png` | PNG | 2048x1158, about 136 KB | Maybe after review | Could inform referrals section | Needs sample-data/privacy review |
| Referrals connected wide screenshot | `frontend/playwright-referrals-connected-wide.png` | PNG | 2048x1158, about 136 KB | Maybe after review | Could inform referrals section | Needs sample-data/privacy review |
| LinkedIn logo | `user_config/linkedin_logo.png` | PNG | 1024x1024, about 69 KB | No without license review | Do not use on public site | Third-party trademark/licensing; user_config location |
| GitHub logo | `user_config/github_logo.jpg` | JPG | 1470x1445, about 89 KB | No without license review | Do not use on public site | Third-party trademark/licensing; user_config location |
| Profile image from CV | `user_config/_profile_from_cv.png` | PNG | 390x448, about 418 KB | No | Do not use | Likely private user/candidate asset |
| CSS brand mark | `frontend/src/components/AppShell.jsx` | CSS/HTML | N/A | Maybe | Basis for new logo exploration | Not a real logo asset |
| Font | Google-hosted Plus Jakarta Sans | Web font | N/A | Yes, subject to license/CDN decision | Website typography | Consider self-hosting for performance/privacy |
| Icon font | Google Material Symbols Outlined | Web font | N/A | Yes, subject to license/CDN decision | Icons | Current stale screenshot shows ligatures if font fails |

Missing assets:

- High-resolution product logo.
- SVG logo.
- Dark and light logo variants.
- Favicon set.
- Social sharing image.
- Website hero screenshot.
- Feature screenshots with approved sample data.
- Product demo video.
- Brand guidelines.
- Public customer logos/testimonials.

## 23. Technical implementation recommendation

### Options compared

| Option | Benefits | Risks/costs | Fit |
| --- | --- | --- | --- |
| Add public routes to existing React app | Reuses current stack and deployment | SPA SEO weaker, auth/app shell coupling, larger bundle, more risk to app routing | Acceptable only for very small landing page |
| Separate Astro site in same repo | Static-first SEO, fast, low-cost, content-friendly, no backend needed, app separation | Adds one project and shared brand coordination | Recommended |
| Next.js | Strong SEO and routing, good ecosystem | Heavier than needed, more hosting/runtime choices, unnecessary complexity for static pages | Overpowered for launch |
| React static build | Familiar to current frontend | Less content-native than Astro; more manual SEO/content handling | Viable but not best |
| Plain HTML/CSS/JS | Very simple and cheap | Harder to maintain reusable pages/components as site grows | Fine for one-pager, weak for full sitemap |

### Recommended solution

Create a separate `website/` Astro project in the same repository.

Reasons:

- The site is mostly static content, screenshots, metadata, and legal/help pages.
- SEO matters more for the public website than for the authenticated app.
- No new backend is needed.
- The authenticated app can remain on `app.userunr.com`.
- The public website can live on the root domain.
- Content can be versioned with the app while keeping deployment separate.

### Suggested directory structure

```text
website/
  astro.config.mjs
  package.json
  src/
    components/
      Header.astro
      Footer.astro
      ButtonLink.astro
      FeatureGrid.astro
      ScreenshotFrame.astro
      PricingTable.astro
      SeoHead.astro
    content/
      faq/
      changelog/
      legal/
    layouts/
      BaseLayout.astro
      MarketingLayout.astro
      LegalLayout.astro
    pages/
      index.astro
      product.astro
      how-it-works.astro
      pricing.astro
      security.astro
      help.astro
      contact.astro
      privacy.astro
      terms.astro
      cookies.astro
      account-deletion.astro
  public/
    assets/
      logo.svg
      favicon.svg
      og-image.png
      screenshots/
```

### Component/content approach

- Keep design tokens in CSS variables shared from the brand palette.
- Use Astro components for headers, footers, page sections, feature cards, FAQ rows, pricing tables, and screenshot frames.
- Use Markdown/MDX only if help/legal/changelog content grows.
- Do not introduce a CMS at launch.
- Use optimized local images, WebP/AVIF variants, and explicit dimensions.

### Analytics recommendation

Use privacy-light analytics only after legal review. Prefer a low-cost, simple option such as Plausible, Umami, or server-side/static-host analytics. If Firebase Analytics is used, add consent and cookie documentation.

### Contact form recommendation

Start with a mailto link or a static form provider. Do not build a custom backend for the marketing site unless contact volume or workflow demands it.

## 24. Deployment recommendation

### Domain structure

Recommended:

- `https://userunr.com` or chosen root domain: public marketing website.
- `https://app.userunr.com`: authenticated Runr app.
- `https://api.userunr.com`: backend API.

Evidence: deployment docs/config already reference app/API-style origins.

### Hosting

Low-cost options:

- Cloudflare Pages for the Astro website.
- Render static site if staying with Render for operational simplicity.
- Netlify/Vercel as alternatives.

Do not add a marketing-site backend unless needed.

### Deployment requirements

- Preview deployments for PRs.
- Production build check for Astro.
- Static asset optimization.
- `robots.txt` and sitemap generation.
- 404 page.
- Redirects from any legacy marketing URLs.
- Environment variables only for public analytics/site config if needed.
- Separate app/API CORS and auth redirect review before launch.
- Error/performance monitoring for website and app separately.

## 25. Website launch requirements

Before launch:

1. Confirm brand spelling, logo, tagline, domain, and CTA language.
2. Create public homepage, product/how-it-works, pricing, security, help, contact, privacy, terms, cookies, account deletion pages.
3. Capture approved screenshots using fake/sample data.
4. Add SEO metadata, sitemap, robots, canonical URLs, Open Graph, favicon, and social image.
5. Confirm pricing and Creem production setup, or hide final pricing behind waitlist/contact.
6. Complete legal/privacy review for CV uploads, contacts, email sync, analytics, and subscription billing.
7. Add support/documentation routes or remove app-shell dead controls.
8. Verify primary app journey for a new user: account creation, CV upload, Quick Apply or workspace run, document output, tracker update, billing state.
9. Run accessibility, mobile, and performance checks on website and critical app screens.
10. Confirm source/scraping policy and avoid unsupported legal claims.

## 26. Application improvement roadmap

### Before promoting the website

| Recommendation | Reason | User impact | Priority | Estimated effort | Dependencies |
| --- | --- | --- | --- | --- | --- |
| Add real public marketing site | Current app is auth-gated | Visitors can understand product and convert | Critical | Medium | Brand decisions |
| Resolve pricing/Creem production setup | Billing may not be production-ready | Prevents failed checkout/trust loss | Critical | Medium | Founder plan decisions, provider setup |
| Add legal/privacy/account deletion pages | CV/contact/email data is sensitive | Builds trust and reduces legal risk | Critical | Medium/large | Legal review |
| Capture clean screenshots with sample data | Existing screenshots are stale/internal | Professional first impression | High | Small | Sample data and design review |
| Fix Support/Documentation controls | Current controls appear dead | Reduces confusion | High | Small | Help/contact pages |
| Add first-run onboarding | New users face complex app | Improves activation | High | Medium | UX decisions |
| Verify Quick Apply happy path | Likely strongest trial experience | Helps conversion | High | Medium | Provider config and quotas |
| Clarify source/scraping claims | Docs warn legal/source constraints | Avoids risky marketing | High | Small | Founder/legal review |
| Add SEO/social metadata and favicon | Current metadata is unfinished | Improves professionalism/discoverability | High | Small | Brand assets |
| Review analytics/consent | Analytics code exists | Privacy compliance and trust | High | Medium | Legal/privacy choice |

### Soon after launch

| Recommendation | Reason | User impact | Priority | Estimated effort | Dependencies |
| --- | --- | --- | --- | --- | --- |
| Simplify Workspaces UX | Page is complex and core to value | Better setup completion | High | Large | UX research |
| Simplify Tracker IA | Dense page with many actions | Faster daily use | High | Large | User testing |
| Standardize terminology | Documents/Career Assets/Artifacts drift | Reduces confusion | Medium | Medium | Founder naming decisions |
| Add help documentation | App has advanced workflows | Fewer support issues | Medium | Medium | Product docs |
| Improve error/recovery messages | Generic failures reduce confidence | Better self-service | Medium | Small/medium | Error taxonomy |
| Run accessibility audit | No full audit found | Inclusive and professional UX | Medium | Medium | Test tooling |
| Add mobile QA pass | App uses responsive classes but not verified here | Better mobile trust | Medium | Medium | Device/browser testing |
| Add data export/deletion UX | Legal/trust expectation | Better privacy control | Medium | Large | Backend deletion policy |
| Add status/incident communication | Useful after active launch | Better reliability trust | Low/medium | Small | Monitoring |

### Later improvements

| Recommendation | Reason | User impact | Priority | Estimated effort | Dependencies |
| --- | --- | --- | --- | --- | --- |
| Public docs/help center expansion | Product is workflow-heavy | Better education and SEO | Medium | Medium | Support patterns |
| Changelog | Shows product momentum | Trust for early users | Low | Small | Release process |
| Product demo video | Better conversion | Faster understanding | Medium | Medium | Polished UI/screenshots |
| Audience landing pages | SEO/conversion optimization | Better message fit | Low/medium | Medium | Analytics data |
| In-app notification implementation | Icon already creates expectation | Better workflow feedback | Low/medium | Medium | Notification design |
| Team/org features | Could expand market | Collaboration | Later | Very large | Product strategy |

## 27. Questions for the founder

### Product

1. Is the official brand `Runr`, `runr`, or `runr.`?
2. Which feature should be the hero product promise: workspaces, Quick Apply, documents, tracker, or the whole operating workflow?
3. Is Runr currently open for self-serve sign-up, invite-only, or beta access?
4. Which features are safe to market as production-ready today?
5. Should live sourcing be emphasized, or should the first website emphasize exact job links and workflow organization?

### Audience

1. Who is the primary ICP: active job seekers, high-volume applicants, career switchers, international candidates, or another segment?
2. Is the product aimed at individual users only, or are teams/coaches/agencies planned?
3. Are investors/partners a meaningful website audience for launch?

### Business model

1. Are Launch, Momentum, and Scale the final plan names?
2. Are EUR 15, EUR 25, and EUR 79 per month final public prices?
3. Will there be a real free trial or free plan?
4. What refund, cancellation, tax/VAT, and failed-payment policies should be public?
5. Should pricing be public at launch or replaced by waitlist/contact?

### Brand

1. What is the final tagline?
2. Should the site feel more premium productivity, technical automation, or career-coach friendly?
3. Should the current teal palette be retained?
4. Do you want a new logo/wordmark before launch?

### Marketing

1. Are there any approved testimonials, logos, screenshots, demo data, or outcome metrics?
2. What claims are explicitly off-limits?
3. What primary CTA should the website use?
4. Which countries/languages should the website target first?

### Legal

1. Who will provide Privacy, Terms, Cookie, and data processing language?
2. What is the retention/deletion policy for uploaded CVs, generated documents, contacts, and email sync data?
3. What source/scraping policy should users agree to?
4. Should users accept terms during signup inside Clerk/app, website, or both?

### Launch

1. What is the final root domain?
2. Should the marketing site launch before or after app onboarding fixes?
3. What support email/contact method should be public?
4. What analytics tool is acceptable for the public website?

### Future plans

1. Are teams, coaches, agencies, employers, or public API access on the roadmap?
2. Will Runr support languages beyond English?
3. Will there be a native mobile app?
4. Should the website prepare for content marketing/blog resources?

## 28. Evidence and file references

### Primary product/app evidence

- `README.md`: local setup, entry points, workflow overview, provider setup.
- `ARCHITECTURE.md`: domain model, backend/frontend structure, API surface, data ownership concepts.
- `docs/architecture/current_system.md`: active architecture/navigation guide.
- `frontend/src/App.jsx`: frontend route map and route guards.
- `frontend/src/components/AppShell.jsx`: brand treatment, navigation, shell controls, plan badge.
- `frontend/index.html`: public metadata, fonts, Tailwind config.
- `frontend/src/styles.css`: app theme and visual tokens.
- `frontend/src/main.jsx`: Clerk provider and configuration guard.
- `frontend/src/context/SessionContext.jsx`: session/backend auth bridge.
- `frontend/src/lib/api.js`: API behavior, request diagnostics, quota event handling.
- `frontend/src/lib/analytics.js`: optional Firebase Analytics.
- `frontend/src/lib/auth.js`: admin role check.

### Page evidence

- `frontend/src/pages/DashboardPage.jsx`.
- `frontend/src/pages/WorkspacesPage.jsx`.
- `frontend/src/pages/QuickApplyPage.jsx`.
- `frontend/src/pages/RunsPage.jsx`.
- `frontend/src/pages/RunDetailPage.jsx`.
- `frontend/src/pages/TrackerPage.jsx`.
- `frontend/src/pages/TrackerAtsPage.jsx`.
- `frontend/src/pages/JobDescriptionPage.jsx`.
- `frontend/src/pages/ArtifactsPage.jsx`.
- `frontend/src/pages/CvStudioPage.jsx`.
- `frontend/src/pages/ReferralsPage.jsx`.
- `frontend/src/pages/LinkedInConnectionsGuide.jsx`.
- `frontend/src/pages/DocumentAICanvasGuide.jsx`.
- `frontend/src/pages/SettingsPage.jsx`.
- `frontend/src/pages/PricingPage.jsx`.
- `frontend/src/pages/AdminPage.jsx`.
- `frontend/src/pages/AdminEventsPage.jsx`.
- `frontend/src/pages/AdminScrapeOpsPage.jsx`.
- `frontend/src/pages/CareerUrlDiscoveryPage.jsx`.

### Backend/API evidence

- `backend/api/server.py`: API server, CORS/origin policy.
- `backend/api/routes/system.py`: health/system routes.
- `backend/api/routes/admin.py`: auth, billing, admin, analytics, settings, tokens, secrets routes.
- `backend/api/routes/workspace.py`: workspaces, workflow templates, runs, workers, Quick Apply routes.
- `backend/api/routes/tracker.py`: tracker, referrals, outreach, email integration routes.
- `backend/api/routes/documents.py`: document upload/export/CV routes.
- `backend/api/routes/career_memory.py`: career memory routes.
- `backend/database/schema.py`: core data tables.
- `backend/repositories/sqlite_migrations.py`: analytics, billing, ownership migrations.
- `backend/config/plans.py`: plans, quotas, limits, legacy aliases.
- `backend/config/env_schema.py`: required provider/environment configuration.
- `backend/security/auth.py`: API token hashing and roles/scopes.
- `backend/security/secrets.py`: secret references.
- `backend/security/redaction.py`: sensitive-field redaction.
- `backend/integrations/clerk.py`: Clerk JWT/webhook verification.
- `backend/integrations/creem.py`: Creem webhook/redirect verification.
- `backend/capabilities/networking/outreach.py`: LinkedIn CSV/referral/outreach capabilities.
- `backend/capabilities/networking/discovery.py`: feature-flagged live contact discovery.
- `backend/capabilities/tailored_documents/`: application document generation and export-related capabilities.
- `backend/career_memory/`: career memory extraction/output services.

### Deployment, billing, legal/security evidence

- `render.yaml`: current Render frontend/API/worker deployment structure and env names.
- `docs/deployment/render.md`: deployment recommendations and host separation.
- `docs/deployment/creem.md`: billing endpoint/provider setup notes.
- `CREEM_REMAINING_STEPS.md`: remaining billing setup tasks.
- `CLERK_SETUP.md`: Clerk setup notes.
- `docs/security/runr_data_ownership.md`: access ownership model.
- `docs/scraping_strategy_report_2026-05-26.md`: source/scraping risk and policy notes.

### Asset evidence

- `image.png`.
- `screenshots/dashboard-loading-current-state.png`.
- `frontend/current-shell.png`.
- `frontend/current-shell-short.png`.
- `frontend/current-shell-short-2.png`.
- `frontend/playwright-referrals.png`.
- `frontend/playwright-referrals-fixed.png`.
- `frontend/playwright-referrals-connected.png`.
- `frontend/playwright-referrals-connected-wide.png`.
- `user_config/linkedin_logo.png`.
- `user_config/github_logo.jpg`.
- `user_config/_profile_from_cv.png`.

### Confirmed, inferred, and unknown

| Topic | Confirmed | Inferred | Unknown |
| --- | --- | --- | --- |
| Brand name | App shell renders `runr.`; docs use `Runr` | Lowercase period may be preferred | Official spelling/capitalization |
| Product category | Workspaces, runs, documents, tracker, referrals exist | Job-search operations workspace | Final market category |
| Primary user | Authenticated candidate/job seeker workflows dominate | Serious active job seeker | Exact ICP and geography |
| Core value | One app covers sourcing, documents, tracking, referrals | Reduces fragmented job-search admin | Quantified outcomes |
| Pricing | Launch/Momentum/Scale and EUR amounts exist in config | Monthly subscription model | Final public pricing, taxes, trial |
| Free plan | `none` exists with zero quotas | No useful free plan today | Whether a trial/free tier will launch |
| Public website | Missing | Separate static site is best | Final domain/launch date |
| Auth | Clerk integrated | Clerk handles account lifecycle | Exact Clerk methods/policies |
| Legal | No legal pages found | Legal readiness is launch blocker | Final policies and counsel review |
| Security | Auth, ownership docs, redaction, token hashing, signed URLs, webhook verification exist | These can support trust copy | Certifications/compliance |
| Assets | Several internal screenshots found | Need new marketing screenshots | Approved visuals/logo |
| Integrations | Clerk, Creem, Google email callback, LinkedIn CSV import, ScrapeOps/DeepSeek config | Useful but should be carefully worded | Public integration positioning |
| Teams | Not found | Not supported today | Future team/org plans |
| Support/docs | Buttons exist | Public help center needed | Support process/contact |

### Website launch checklist

| Requirement | Current status | Action needed | Priority |
| --- | --- | --- | --- |
| Public homepage | Missing | Build static marketing homepage | Critical |
| Product/how-it-works page | Missing | Create workflow explanation and screenshots | Critical |
| Public pricing page | Missing; authenticated pricing exists | Confirm billing model and build public page | High |
| Legal pages | Missing | Draft/review Privacy, Terms, Cookies, account deletion | Critical |
| Security/trust page | Missing | Convert confirmed trust signals into careful public copy | High |
| Help/support page | Missing; shell controls exist | Add public help/contact and link app controls | High |
| Logo/favicon | Missing | Design/export brand asset set | High |
| SEO metadata | Weak/missing | Add title, descriptions, canonical, OG, sitemap, robots | High |
| Approved screenshots | Missing | Capture fake-data product screenshots | High |
| Pricing provider readiness | Incomplete per docs | Verify Creem products/webhooks/checkout | Critical |
| Onboarding | No dedicated route found | Add first-run setup or guided path | High |
| Analytics consent | Not found | Choose analytics and consent/privacy approach | High |
| Accessibility QA | Not documented | Run audit and fix launch blockers | Medium |
| Mobile QA | Not documented | Test website and key app screens | Medium |
| Scraping/source claims | Risk documented | Define safe marketing language | High |

### Recommended implementation plan

| Phase | Work | Output | Dependencies |
| --- | --- | --- | --- |
| 1. Founder decisions | Confirm brand, ICP, CTA, pricing, launch mode, legal owner | Approved website brief | Founder input |
| 2. Brand/assets | Create logo, favicon, social image, screenshot data plan | Website asset kit | Brand decision |
| 3. Website scaffold | Add `website/` Astro project, base layout, design tokens, SEO component | Buildable static site | Repo/package decision |
| 4. Core pages | Build homepage, product/how-it-works, pricing or waitlist, security, help, contact | Launch page set | Copy/assets/legal decisions |
| 5. Legal pages | Add Privacy, Terms, Cookies, account deletion | Public legal footer | Legal review |
| 6. App fixes | Link support/docs, verify onboarding/Quick Apply, billing setup, metadata/favicons for app | Lower-friction app handoff | Dev/provider setup |
| 7. QA | Run accessibility, mobile, Lighthouse, link checks, screenshot privacy review | Launch QA report | Completed pages |
| 8. Deploy | Publish website on root domain, keep app/API on subdomains, set redirects/sitemap | Public launch | DNS/deployment access |
