# Application Remediation PRD
## Parallel Workstreams For Current Product Gaps

## Problem Statement

The current application works end-to-end in parts, but the product surface is still shaped too much by migration scaffolding and backend implementation details.

From the user's perspective, the biggest failures are:

- tracker email sync is not trustworthy or usable because it relies on password entry and the current connection flow is brittle
- workspace setup is confusing, too technical, and exposes many backend/runtime controls that should not be user-facing
- non-LinkedIn sources are not reliably usable from the app even though the product surface suggests broader sourcing
- the workspace targeting model is redundant and unclear because it mixes role presets, keywords, and source-specific geography concepts
- referrals are too manual and do not scale
- the current artifacts area is too technical and should be replaced with user-facing rejected-job and document-management workflows
- generated CVs and application assets are still not organized as a first-class product area

The product needs a remediation pass that fixes these issues without creating merge chaos. The work must be clustered so multiple implementation chats or agents can run in parallel with minimal overlap.

## Solution

Replace the current migration-oriented UX with four product-facing workstreams built on one short contract-alignment phase:

1. secure tracker inbox sync using Google authorization instead of password entry
2. simplified workspace builder and source configuration driven by CV-aware targeting, country selection, and user-facing filters
3. application documents and rejected-job review replacing the current technical artifacts experience
4. referral/contact ingestion and management that scales beyond manual one-by-one entry

The remediation should preserve existing backend pipeline capabilities where they still add value, but hide or restructure technical controls so the app feels like a user product rather than an orchestration console.

## Product Goals

- Make email sync feel secure and credible.
- Make workspace creation understandable in one pass.
- Make generated CVs and application assets easy to find, view, and export.
- Make rejected jobs actionable instead of invisible.
- Make referrals fast to populate and useful during job review.
- Keep the automation engine flexible in the backend while removing developer-only controls from the frontend.

## Non-Goals

- Full LinkedIn direct API integration.
- Fully automated company-site form submission across arbitrary employers.
- Broad admin-platform redesign outside the user-facing problem areas described here.
- A full prompt-engineering lab for end users.

## External Setup Items

These are not all confirmed must-haves for every implementation path, but they must be called out explicitly because they affect delivery:

- Google Cloud project setup for OAuth consent, OAuth client credentials, and Gmail API access for tracker inbox sync.
- Secure token storage for OAuth refresh/access tokens in the app's secret storage layer.
- Existing scraping infrastructure such as ScrapeOps remains relevant for source validation and custom-site health checks.
- If product later wants unified end-user authentication or delegated Google sign-in beyond inbox sync, an external auth platform such as Clerk or Auth0 is optional and should be evaluated separately. It is not required just to implement Gmail-based tracker sync.
- Vertex is not required for the remediation items in this PRD unless later AI workflow changes explicitly choose it.

## Parallel Execution Model

### Phase 0: Contract Alignment

This is the only required sequencing step before parallel work begins. It should be small and produce stable interfaces.

Required outputs:

- A `workspace configuration v2` contract that defines:
  - keyword targeting as the primary targeting method
  - country-based location targeting
  - simplified language preferences
  - visible user settings versus hidden runtime settings
- A `candidate asset` contract that defines:
  - uploaded CVs
  - generated CVs
  - other application documents
  - which asset can be bound to a workspace
- A `rejected job review` contract that defines:
  - rejection reason codes
  - human-readable explanations
  - override/requeue behavior
- A `mail connection` contract that defines:
  - provider type
  - OAuth token references
  - sync cursor/state
  - last sync result and last sync error
- A `referral relationship` contract that defines:
  - one person to many companies
  - import source metadata
  - matching rules used in review and outreach flows

Estimated scope:

- one short design/implementation pass by a single owner
- no major UI work
- mostly schema normalization, service boundaries, and payload shape agreement

### Parallel Workstreams After Phase 0

| Stream | Name | Can Run In Parallel With | Primary Ownership |
| --- | --- | --- | --- |
| A | Tracker Inbox OAuth and Email Sync | B, C, D | tracker inbox sync service, tracker integration UI |
| B | Workspace Builder Simplification and Source Reliability | A, C, D | workspace builder domain, source config UI, source validation |
| C | Application Documents and Rejected Jobs Review | A, B, D | document library, rejected jobs workflow, artifacts replacement |
| D | Referrals and Connections Import | A, B, C | referral graph, import pipeline, referrals UX |

## User Stories

1. As a job seeker, I want to connect my inbox with Google sign-in, so that I never have to enter my email password into the app.
2. As a job seeker, I want tracker email sync to clearly show connection status, sync status, and failures, so that I trust what the tracker is doing.
3. As a job seeker, I want workspace setup to ask for a CV first, so that the rest of the setup feels personalized to my profile.
4. As a job seeker, I want to select an existing CV or upload a new one for a workspace, so that each workspace is tied to the right baseline.
5. As a job seeker, I want a single keyword-driven targeting model, so that I am not confused by overlapping target-role and target-keyword concepts.
6. As a job seeker, I want the app to suggest keywords and forbidden title terms from my CV, so that setup is faster and smarter by default.
7. As a job seeker, I want to choose countries instead of LinkedIn geography IDs, so that location targeting makes sense across all sources.
8. As a job seeker, I want to select from multiple source types including LinkedIn, curated URLs, company career sites, and major job boards, so that I am not blocked by one source.
9. As a job seeker, I want pasted URLs and company-site sources validated before a run starts, so that I do not discover broken inputs only after the job pipeline fails.
10. As a job seeker, I want technical runtime controls hidden from the frontend, so that the workspace builder only shows choices I can understand and benefit from.
11. As a job seeker, I want prompt customization to be structured and understandable, so that I can review defaults and override them deliberately when needed.
12. As a job seeker, I want generated CVs to appear in a dedicated documents area, so that I can view and export them without hunting through artifacts.
13. As a job seeker, I want certificates, recommendation letters, and motivation letters stored with my CVs, so that all application assets live in one place.
14. As a job seeker, I want to bulk export selected application documents, so that I can apply outside the platform quickly.
15. As a job seeker, I want to see which jobs were rejected and why, so that I can correct filters instead of losing good opportunities silently.
16. As a job seeker, I want to override a rejected decision and send a job back into the generation flow, so that the system does not permanently block good matches.
17. As a job seeker, I want rejected-job feedback to lead me back to the relevant workspace settings, so that I can fix future filtering mistakes.
18. As a job seeker, I want to import LinkedIn connection exports, so that populating referrals is fast and low-friction.
19. As a job seeker, I want one contact to be associated with multiple companies, so that referral opportunities reflect real career history.
20. As a job seeker, I want the review flow to show who can refer me at a company, so that I can prioritize warm paths.
21. As a job seeker, I want referral entry to be easier even when I do it manually, so that I am not forced into repetitive data entry.
22. As a job seeker, I want motivation letters to be created and managed alongside my other application assets, so that document handling is centralized.
23. As a product owner, I want the reusable-packages workspace option removed from the frontend if it does not add real user value, so that the workspace flow stays focused and understandable.
24. As a developer, I want these remediation items split into low-conflict workstreams, so that multiple chats or agents can implement them safely in parallel.

## Workstream A: Tracker Inbox OAuth and Email Sync

### Scope

- Replace password/app-password based email connection with Google authorization for Gmail inbox sync.
- Preserve tracker sync behavior that converts email events into tracker status updates.
- Keep manual tracker status updates available.

### Requirements

- Remove the password field from the user-facing tracker email connection flow.
- Replace provider-driven IMAP credential entry with a Google sign-in / OAuth authorization flow for Gmail.
- Store OAuth token references securely and never expose raw tokens back to the client.
- Preserve sync outcomes already supported by the tracker:
  - email confirmed
  - interview invited
  - rejected
- Show clear connection state, last sync state, and failure state in the tracker UI.
- Support disconnect/revoke behavior.
- Keep non-Gmail providers out of scope for the first secure replacement unless product explicitly funds a broader mail-provider abstraction.

### Implementation Decisions

- Build a mail-provider abstraction that supports `google_oauth` as the first provider instead of `password_imap`.
- Separate authorization, token storage, and mailbox sync into distinct modules.
- Treat mailbox sync as a background-safe operation with persisted cursors/checkpoints.
- Do not couple Gmail authorization to a full replacement of the app's main authentication system.

### Testing Decisions

- Test authorization-state transitions separately from mailbox-message matching.
- Test tracker status updates using mailbox-message fixtures, not provider internals.
- Test disconnect and reconnect behavior.
- Add API tests for connect, callback/finalize, sync, and disconnect flows.

### Parallel Safety

- Safe to run in parallel with all other streams after Phase 0.
- Main shared boundary is only the mail connection contract and secret storage abstraction.

## Workstream B: Workspace Builder Simplification and Source Reliability

### Scope

- Redesign workspace setup around CV selection, keyword targeting, country selection, source configuration, and simplified filters.
- Remove or hide developer-facing controls from the frontend.
- Fix end-to-end wiring for all supported sources.

### Requirements

- Evaluate the current reusable-packages workflow option and remove it from the frontend if it does not provide direct user value.
- Keep the tailored application workflow focused on:
  - sourcing jobs
  - screening jobs
  - tailoring application documents
- Require each workspace to select an existing CV or upload a new workspace CV.
- Replace the mixed target-role/target-keyword model with one keyword-first targeting system.
- Use CV context to propose initial keywords, forbidden title keywords, and language defaults.
- Replace LinkedIn geo ID with country selection that applies consistently across all sources.
- Keep job recency filters such as "posted since" visible and user-facing.
- Fix source wiring so the app can actually trigger:
  - LinkedIn search
  - curated URLs
  - company career sites
  - major job boards beyond LinkedIn
- Add pre-run validation for custom/pasted/custom-site sources, including scrapeability and presence of job listings.
- Move URL and source configuration closer together in the workspace flow instead of scattering them across unrelated sections.
- Remove candidate name and candidate email from workspace-level config because they already belong to profile/CV data.
- Simplify language preferences into user-understandable choices driven by profile and CV context.
- Keep CV template and include-photo controls available.
- Rework prompt customization into a structured stage-aware interface:
  - show the default prompt in use
  - explain what it affects
  - allow replace/restore behavior
- Hide runtime and resilience controls from the frontend, including:
  - page counts
  - AI batch sizes
  - retry counts
  - sleep/delay values
  - fallback model plumbing
  - force-regeneration toggles
  - tracker/export plumbing

### Implementation Decisions

- Introduce a workspace settings normalizer that maps the new user-facing schema to current pipeline settings.
- Keep advanced runtime settings in backend defaults or admin-level config, not the workspace builder UI.
- Consolidate source setup and source validation into one domain boundary rather than scattering source logic across page-local state.
- Treat keyword targeting, country targeting, language preferences, and forbidden-title defaults as derived-from-CV but user-editable.

### Testing Decisions

- Test workspace creation and editing with the new simplified schema.
- Test normalization from user-facing settings to run-time pipeline overrides.
- Test each source type end-to-end from workspace save to run execution.
- Test validation responses for invalid URLs, unsupportable sites, and empty job pages.

### Parallel Safety

- Safe to run in parallel with A, C, and most of D.
- Avoid overlap by assigning full ownership of workspace builder domain, source validation, and workspace UI to this stream.

## Workstream C: Application Documents and Rejected Jobs Review

### Scope

- Replace the current artifacts-first UX with two user-facing areas:
  - rejected jobs review
  - application documents / assets library

### Requirements

- Remove or fully repurpose the current Artifacts section so it no longer exposes raw JSON or technical export concepts as the primary experience.
- Add a rejected-jobs review area where users can:
  - see rejected jobs
  - see rejection reasons
  - override decisions
  - send selected jobs back into the pipeline
- Add links from rejection reasons back to relevant workspace settings so users can tune filters.
- Add an application documents area where users can:
  - browse all generated CVs
  - browse motivation/cover letters
  - browse certifications and uploaded application assets
  - preview files
  - download files
  - bulk export selected files
- Support role/job-specific motivation-letter generation and storage inside the same assets area.
- Make generated CVs visible without forcing regeneration.
- Preserve document export and packaging capabilities behind user-facing labels rather than technical artifact labels.
- Treat drag-and-drop document usage as future scope, not a blocking requirement for the remediation.

### Implementation Decisions

- Introduce a document-library read model instead of exposing raw artifact records directly.
- Keep existing artifact storage as implementation detail where possible, but add user-facing grouping:
  - generated CVs
  - generated letters
  - supporting documents
  - exported bundles
- Introduce explicit rejection reason codes and display text instead of relying on opaque filter outcomes.
- Add a requeue/regenerate action that routes through the existing run/review pipeline rather than inventing a second pipeline.

### Testing Decisions

- Test rejected-job listing and reason rendering based on review/filter outcomes.
- Test override/requeue behavior as external behavior, not internal stage plumbing.
- Test document-library listing, preview/download, and bulk export behavior.
- Test that generated CVs and uploaded assets appear in the correct groups.

### Parallel Safety

- Safe to run in parallel with A and B.
- Can run in parallel with D if D avoids modifying the same review page surfaces at the same time.
- Assign full ownership of document library, rejected-jobs views, and artifacts replacement to this stream.

## Workstream D: Referrals and Connections Import

### Scope

- Replace the current one-contact/one-company manual referral model with a scalable importable relationship graph.

### Requirements

- Support import of exported LinkedIn connections data, starting with CSV import.
- Preserve manual entry, but make it lighter-weight and faster.
- Allow one person/contact to be associated with multiple companies.
- Store whether the person can actively refer.
- Support enrichment-friendly metadata such as source, import batch, and profile link.
- Keep referral matching against jobs and companies in the review flow.
- Preserve or improve referral draft generation once the richer contact model exists.
- Keep direct LinkedIn integration out of scope unless a compliant supported approach is identified later.

### Implementation Decisions

- Move from a flat contact record toward a person-plus-company-association model.
- Build an import pipeline that normalizes LinkedIn export fields into the internal referral graph.
- Make manual entry use the same domain model as imported data instead of maintaining a second schema.
- Keep lightweight enrichment optional and non-blocking.

### Testing Decisions

- Test CSV import parsing, deduplication, and normalization.
- Test multi-company relationships for a single person.
- Test company matching behavior against review queue jobs.
- Test referral draft generation against imported and manually entered contacts.

### Parallel Safety

- Safe to run in parallel with A and B.
- Safe to run mostly in parallel with C if C owns rejected-job/document flows and D limits its review-queue changes to referral data rendering.

## Implementation Decisions

- Keep one short contract-alignment phase before parallel feature work.
- Prefer new user-facing read models over leaking raw pipeline artifacts into the UI.
- Keep backend pipeline flexibility, but hide runtime plumbing from normal workspace users.
- Use the CV as the primary personalization anchor for workspaces, keyword defaults, document defaults, and language defaults.
- Treat Google OAuth plus Gmail API as the default secure path for tracker inbox sync.
- Treat document storage and generated exports as assets in a user library, not as raw artifacts.
- Treat referrals as relationship data, not just flat notes.

## Testing Decisions

- Good tests should verify user-visible behavior and persisted outcomes, not internal implementation choices.
- API and service tests should remain the primary safety net for workspace configuration, tracker sync, referral import, and document-library behavior.
- UI tests should focus on the critical user paths:
  - connect inbox
  - create workspace
  - validate sources
  - review rejected jobs
  - browse/export documents
  - import referrals
- Similar prior-art test styles already exist in the codebase for backend API flows, tracker state updates, referral endpoints, and reusable package/document services.

## Recommended Delivery Sequence

### Phase 0

- land shared contracts and schema decisions

### Phase 1: Parallel Build

- Stream A: tracker inbox OAuth and sync
- Stream B: workspace builder simplification and source reliability
- Stream C: application documents and rejected jobs review
- Stream D: referrals and connections import

### Phase 2: Integration Pass

- connect workspace CV binding to the application-assets model
- connect rejected-job feedback links back to workspace editing
- connect richer referral matching to the updated review experience
- replace remaining "Artifacts" language in navigation and page labels

## Suggested Chat / Agent Split

If you want to split this work across separate chats right now, the safest split is:

1. Chat A: Stream A only
2. Chat B: Stream B only
3. Chat C: Stream C only
4. Chat D: Stream D only

If you only want two parallel chats, use:

1. Chat A: Stream A + Stream D
2. Chat B: Stream B + Stream C

That split keeps the highest-risk shared UI surfaces apart.

## Out of Scope

- LinkedIn direct account integration for contacts or messaging.
- Fully generalized email-provider support beyond the first secure Gmail path.
- End-user exposure of runtime tuning knobs for retries, delays, batching, and fallback internals.
- Broad redesign of automation internals that the user explicitly said can remain unchanged for now.
- Drag-and-drop document handling in the first remediation pass.

## Further Notes

- The current app already contains pieces of tracker state, referrals, artifacts, document generation, and workspace composition, so this is a remediation and re-shaping effort rather than a greenfield product build.
- Some existing functionality should remain backend-capable even when removed from the normal frontend surface.
- The purpose of this PRD is not just feature completeness. It is to make the app understandable, trustworthy, and operable by real users.
