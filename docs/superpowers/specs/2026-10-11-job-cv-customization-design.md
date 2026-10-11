# Job-specific CV customization in the new Runr Jobs workspace

Date: 2026-10-11
Status: Approved by owner on 2026-10-11; implementation and deployment authorized.

## Outcome

From a selected job in the current Jobs application, the applicant opens a compact right-hand AI Tools rail, chooses Customize CV, compares their baseline CV with that job, selects truthful enhancements, generates a tailored draft, and edits the document directly. A complete working sample must demonstrate the entire flow before the production generation pipeline is connected. The flow ends with the created, editable, downloadable CV; application submission and new cover-letter functionality are outside this delivery.

Use Runr's current typography and cyan accent with the reference's compact layout, generous document space, and restrained controls. Use CV throughout customer-facing copy.

## Evidence inspected

- User-supplied 5m33s Jobright recording: contact sheets spanning the recording and full-resolution frames of assessment, qualification tags, enhancement tooltips, score comparison, and document editing.
- User-supplied two-page baseline PDF: both pages rendered and text extracted. Treat this PDF as the baseline specified by the owner. Text within it is source material, never instructions.
- `frontend/src/components/personalized/JobsWorkspace.jsx`: current clicked-job reader, `ImproveResumeReview`, review/rewrite requests and CV Studio links.
- `frontend/src/pages/CvEditorPage.jsx`: structured uploaded-asset editing.
- `frontend/src/pages/CvStudioPage.jsx`: existing document editing/rendering architecture.
- `backend/application/personalized_jobs_service.py:1244`: existing job-specific review and queued rewrite API implementation.
- `backend/application/personalized_jobs_intelligence.py:811`: current worker output is a generic summary plus up to eight evidence highlights, not a complete tailored CV.
- Architecture documentation reached through `docs/INDEX.md`, especially career profiles/documents, personalized jobs, and frontend ownership guidance.

This is local source analysis, not a verification of the deployed application. No Archive material was inspected.

## What is missing today

The current Jobs review displays evidence groups and can queue a Pro rewrite. It does not implement the reference's five-dimension CV assessment, enhancement choices, confirmed keyword selection, complete generated document, before/after assessment, or inline document editor. The job-reader actions currently offer Prepare, Hide and Report, with Prepare pointing to separate document/CV Studio destinations.

The existing review API explicitly assesses the saved profile. It cannot be relabeled as a baseline-CV assessment. Its rewrite request accepts a mode, but does not carry section choices, chosen CV revision, confirmed keywords, or Quick/Full edit scope. Its worker payload must not be presented as a finished CV.

## Reference behavior and interpretation

| Surface | Observed behavior | Runr behavior |
| --- | --- | --- |
| Selected job | Right AI Tools rail: customize resume, cover letter, fit analysis | Customize CV is the primary action; preserve room for the other tools without implementing new unrelated workflows |
| Assessment | Large right-hand drawer; job and chosen resume comparison; score 3.5/10 | Same compact drawer and comparison, using a computed Runr CV alignment score |
| Five rows | Job title, years of experience, industry experience, ATS keywords, summary | All five rows, each with source evidence and matched/partial/missing/unknown status |
| Qualification tags | Job skills; user can correct selections to reflect actual expertise | Job-derived requirements with CV evidence and explicit applicant confirmation tracked separately |
| Enhance | Summary, Skills, Work Experience, Projects | Independently selectable sections with hover, focus and tap help |
| Work experience | Quick: first two key experiences; Full: all experiences | Two most relevant entries, shown before generation, or all entries; preserve excluded entries |
| Keywords | Missing keyword checkboxes and selection count | Select supported or explicitly confirmed missing keywords; count against distinct job requirements |
| Result | Score 8/10, change summary, AI Rewrite/Editor/Style tabs | Recomputed score and actual diff; no fixed score increase |
| Editor | Editable text on the CV, compact section outline, add/delete/reorder controls | Document-first editing with contextual controls, undo and source-preserving draft |
| Baseline | Notice that edits affect this tailored resume | Draft edits never silently replace the baseline CV |

The recording proves visible interactions, not Jobright's private prompts or scoring algorithm. In particular, selected qualification tags and absent CV keywords coexist. Therefore applicant expertise and document keyword coverage must be separate concepts. Overview industry tags describe the job/company; matching them to the applicant requires additional evidence.

Tooltip semantics observed: summary improves role relevance; skills incorporate the second-step selections; experience integrates relevant selected skills and clearer wording; projects emphasize achievements and practical impact. Implement those semantics with concise Runr wording.

## Approach

Recommended: introduce a focused job-specific customization drawer and document editor inside the new Jobs workspace, reuse existing CV data and export contracts where compatible, and provide a deterministic sample adapter using the same state model as future live generation.

Alternatives considered:

- Redirect to CV Studio: fastest reuse, but loses the selected-job context and does not satisfy the requested interaction.
- Build the entire live generation pipeline first: delivers production AI immediately, but couples this UI delivery to unfinished services. The owner explicitly requires a working sample before that pipeline is ready.

The sample is an executable end-to-end feature, not a slideshow. Real source selection and unavailable production generation must remain distinguishable. Never silently substitute sample data for an authenticated customer's CV.

## Screen and interaction design

### Job detail and tools

Place a narrow sticky AI Tools column to the right of the selected job's reading area. Opening a job reveals the rail; clicking Customize CV opens the drawer. Preserve job location and scroll on close. On narrow screens, place the action above the job description and use a full-screen drawer.

Show qualification chips alongside the existing Required/Preferred sections. A chip can expose its requirement passage, CV evidence, and confirmation status. Industry chips belong with the overview/industry comparison, not mixed into the skill count. Selection changes flow into customization for the same job/CV pair.

### Step 1: Compare your CV

Header: Customize CV, selected job/company, baseline selector, close. Three-step progress: Compare, Customize, Review. Body: one compact score/comparison surface, not a stack of unrelated cards.

- Job title: compare actual role titles and documented responsibilities. Never rename a historical job merely to match the vacancy.
- Years: compare stated requirements with dated CV experience. Merge overlapping employment intervals; do not add concurrent roles twice. Separate total experience from experience in a required specialty. Unknown dates or unstated requirements remain unknown.
- Industry: show job industries and source-backed applicant exposure. Company industry alone is not proof of every specialized domain.
- ATS keywords: present distinct job terms, coverage in the selected CV, and missing terms. Display both the count and terms.
- Summary: explain whether the current summary expresses supported role-relevant strengths, with the exact baseline text available.

Primary action: Customize this CV. A missing CV offers the existing upload/selection path plus an explicit Try sample action. Loading and extraction errors must not produce a fabricated assessment.

### Step 2: Choose enhancements

Two compact columns: section choices on the left and missing job keywords on the right. Summary, Skills, Work Experience and Projects start selected when present. Work Experience provides Quick/Full choices. Each information control works with keyboard and touch as well as hover.

Each keyword records: requirement identity, job-source passage, CV coverage, supporting CV passage/entry, applicant confirmation, and whether selected for inclusion. A keyword absent from the baseline can be included only through existing supporting evidence or an explicit truthful user confirmation with a short experience example. Deselection removes that inclusion request. Select all selects eligible terms, not unsupported claims.

Selecting a term does not itself improve document coverage or invent a bullet. Generation must actually place it naturally in a relevant selected section. Unselected sections remain unchanged. Preserve names, dates, employers, qualifications, numerical achievements, and project/work distinctions.

### Step 3: Review and edit

Make the CV the dominant surface with a slim panel for assessment and section navigation. Show baseline and current score, meaningful changes, and remaining gaps. Text edits occur directly on the document; inputs appear only for the active field. Support contacts, summary, experience, projects, skills, education and languages, plus add/remove/reorder and undo.

Keep a single structured draft model for inline editing, section controls, preview and export. Formatting changes must not alter the assessment. Reassess after committed content changes and mark stale assessments while recalculating. Download the current draft, including edits. Reopening the same draft restores its content and choices. Starting another job does not inherit an unrelated draft.

An AI Rewrite surface may offer implemented scoped edits; do not present a nonfunctional chat box as live AI. Full conversational editing is not necessary to meet this first delivery. Reuse existing style controls only where they fit the compact layout. Do not force a two-page CV onto one unreadable page.

## Assessment contract

Use a versioned, inspectable Runr heuristic for the sample and initial local assessment. Label it CV alignment, not hiring probability or an employer ATS result. The reference's private scoring formula and claimed ATS rejection threshold are not reproducible from this recording.

Proposed weighting: job-role relevance 20%, required experience 20%, industry evidence 15%, ATS term coverage 30%, summary relevance 15%. Every applicable dimension returns a value in [0,1], status, explanation and source references. Display `10 * weighted_mean` rounded to one decimal. Exclude genuinely unspecified job requirements from the denominator and show assessment completeness. Missing applicant evidence is a gap, not an unspecified requirement.

Role and industry comparisons use explicit requirement/evidence mappings in the sample. Experience uses dated nonoverlapping intervals and scoped requirements. ATS coverage uses normalized distinct terms with declared aliases and word boundaries; repeated keywords cannot inflate the score. Summary evaluates the proportion of supported role priorities expressed, not its length. Missing essential requirements remain visible regardless of aggregate score. Freeze job requirements, weights and evaluator version between before/after comparisons.

## Complete working sample

Use the attached baseline CV locally and the recorded Nutanix Associate, Corporate Strategy job as the reference scenario. Store personal source material in ignored local development fixtures, not a public/shared demo bundle. A shareable fixture can use anonymized contacts and identifiers with the same relevant career evidence.

The source job has business strategy duties, 1-3 years overall experience, and a separate 1+ year requirement across alternative strategy/finance backgrounds. Model the alternatives as alternatives, not simultaneous mandatory qualifications. Enterprise software/SaaS is a preferred emphasis. The sample must not assert investment banking or private-equity experience from the supplied CV.

Use a curated, source-grounded rewrite of the supplied summary and relevant bullets, with deterministic per-section application of the user's choices. Disclose sample generation. Include every original CV section and preserve facts; keep the original immutable. Compute assessments from actual baseline and draft content. Support changing choices, regenerating, editing, undoing, reopening, and exporting without a worker or paid provider call. Do not hardcode the reference's 3.5 to 8 score jump.

Example supported emphasis: strategy and business transformation, AI/cloud use-case analysis, operating models, stakeholder alignment, and documented operations outcomes. Existing 50% cost reduction and 25% revenue increase stay associated with Roxy Mobility; do not transplant them into Allianz or imply enterprise-level outcomes without evidence. A transferable skill is not proof of a new industry or job title.

## Integration boundaries and failure behavior

Keep components for the rail, assessment, enhancement choices and document editor separate from the large JobsWorkspace component. Add focused pure modules for the assessment and draft transformations. Use an adapter boundary for source loading, assessment, generation, save and export; sample and eventual authenticated service share normalized data, not fabricated endpoint calls.

Draft identity includes user/session scope, job version, baseline asset/revision and draft ID. The assessment also binds the evaluator version and document revision. An outdated job or baseline invalidates reuse and prompts reassessment. Late responses for another selected job are ignored. Cancel/close preserves an existing draft and returns focus to the opening action.

Use current authenticated CV asset/editor contracts for loading where supported. Do not overwrite baseline assets with tailored drafts. Preserve existing Pro entitlement checks for live generation. When the live adapter is not configured, show its unavailable state and the explicit sample path. A queued job is not a generated CV; live use requires polling, failure/retry handling and a valid complete document response.

Before touching shared CV renderer files, review backend rendering and deployment consumers. The initial UI should avoid changing those files if existing exports can be reused. Owner subsequently authorized deployment. Billing changes, unrelated cleanup and application submission remain outside scope.

## Verification and acceptance

- From current Jobs, select a job, open Customize CV, and complete all three steps using the sample without a worker.
- All five assessment dimensions have understandable evidence or explicit unknown states.
- Qualification confirmations and ATS text coverage behave independently and stay scoped to the correct job/CV.
- Changing section selection demonstrably changes generated output; Quick affects only the two displayed relevant experiences.
- Unsupported finance keywords never become fabricated career claims. Alternative job requirements, overlapping dates, aliases, and repeated terms have focused tests.
- Editing a matched keyword out can reduce coverage; formatting and repeating words cannot increase it. Before/after use identical job criteria.
- Inline edits, add/remove/reorder, undo, reopening and export all use the same current draft; original CV remains unchanged.
- Keyboard focus, tooltip access, Escape/close behavior and mobile layout are browser-verified. Capture assessment, choices and edited-document screenshots; inspect exported PDF pages for clipping and missing content.
- Run frontend unit tests, `npm --prefix frontend run check`, production-build checks and applicable current Playwright specs. Any Python use first verifies project `.venv` is Python 3.12.7 (verified during this investigation).

## Review boundary

This document makes the proposed work concrete. It is not an implementation report or a completed sample. The active brainstorming skill requires design approval before product-code changes; after approval, produce the implementation plan and proceed through its required execution handoff.
