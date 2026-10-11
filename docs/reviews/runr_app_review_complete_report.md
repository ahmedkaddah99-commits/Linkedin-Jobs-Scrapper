# Runr App Review: Complete Status, Clarifications, and Implementation Plan

Date: 2026-06-23

This is the consolidated source of truth for every issue in the timestamped Runr app review. It combines:

- what is implemented;
- what is only partially implemented;
- answers to the clarification and investigation questions;
- the recommended implementation approach for unfinished work;
- the original scope guardrails.

## Status definitions

- **Implemented locally**: code exists in the current working tree and passed local validation, but is not deployed.
- **Partially implemented**: some required behavior exists, but acceptance criteria remain incomplete.
- **Clarified only**: investigation is complete; behavior must not change without approval.
- **Pending**: approved implementation has not started.
- **Protected**: explicitly outside the approved scope.

## Deployment status

As of June 22, 2026:

- production frontend, API, and worker are deployed from commit `d33b071`;
- the changes described as **Implemented locally** are uncommitted working-tree changes;
- local frontend lint/build passes;
- focused route-parent, run-focus, ETA, ATS detail, Career Memory, and tracker-description tests pass;
- no local change in this report is claimed as fixed in production.

## Complete issue matrix

| Issue | Status | Result |
|---|---|---|
| R1-01 Dashboard accuracy | Clarified only | Metric, triggers, action behavior, and replacement copy documented |
| R1-02 Run-start feedback | Implemented locally | Real validation/queueing phases, truthful animation, and duplicate prevention |
| R1-03 Remove QA checklist | Implemented locally | User-facing checklist removed; included/excluded review data retained |
| R1-04 Focus active progress | Implemented locally | Stable hash anchor, one-time focus guard, and reduced-motion handling |
| R1-05 Truthful ETA | Implemented locally | Server-derived range from matching persisted run and stage history |
| R1-06 Remove Quick Apply sentence | Implemented locally | Exact requested sentence removed |
| R1-07 Collapse Inbox Sync | Implemented locally | Compact status/control with expandable configuration |
| R1-08 Status-card filtering | Implemented locally | Cards and status dropdown share one filter state |
| R1-09 Copy full description | Implemented locally | Full stored text, explicit missing-data error, successful-copy feedback, tests |
| R1-10 Edit CV identity | Clarified only | Current source and save behavior documented |
| R1-11 Sticky CV preview | Implemented locally | Desktop sticky preview and mobile Editor/Preview toggle |
| R2-01 Structured bullet editing | Implemented locally | Structured list model, keyboard editing, nesting, HTML, and DOCX list levels |
| R2-02 Experience population/layout | Implemented locally | Canonical fields, aliases, stable IDs, labels, grouping, and empty states |
| R2-03 Sidebar step-back | Implemented locally | Query-aware explicit parent registry with unsaved-change interception |
| R2-04 ATS diagnosis | Clarified only | Production case and scoring limitations documented |
| R2-05 Compact ATS details | Implemented locally | Compact tracker control and read-only ATS detail route |
| R2-06 OCR support | Implemented locally | Page-level fallback, rotation, confidence, async processing, warnings, and status UI |
| R2-07 Remove asset types | Implemented locally | New legacy uploads blocked; old records remain readable |
| R2-08 Guided-review logic | Clarified only | Current fixed logic and completeness rules documented |
| R2-09 Remove duplicate header actions | Implemented locally | Edit CV and Manage documents buttons removed |
| R2-10 Sources/Advanced behavior | Clarified only | Current storage and downstream integration gap documented |
| R2-11 Fact-grounded generator | Implemented locally | Versioned facts, source provenance, confirmation, grounded outputs, and quality gates |

# Part I: Implemented locally

## R1-03: Remove the visible Filtering QA Checklist

Implemented:

- removed the complete user-facing `Filtering QA Checklist` component;
- removed cards for suitable jobs, unsuitable jobs, rejection reasons, and language audit;
- retained Included Jobs and Excluded Jobs;
- did not change backend stage data, review data, filtering behavior, or logging.

Primary file:

- `frontend/src/pages/RunDetailPage.jsx`

Production verification after deployment:

1. Open a completed run.
2. Confirm no QA checklist appears.
3. Confirm Included Jobs and Excluded Jobs remain populated.
4. Confirm the customer-view API still returns stage and rejection data.

## R1-06: Remove the Quick Apply sentence

Implemented:

- removed `EXACT JOB LINKS ONLY. NO COMPANY-SITE CRAWLING OR MOTIVATION LETTERS.`;
- left Quick Apply controls, URL handling, run creation, and navigation unchanged.

Primary file:

- `frontend/src/pages/QuickApplyPage.jsx`

## R1-07: Collapse Email Inbox Sync

Implemented:

- added a compact **Inbox Sync** control;
- collapsed state shows connection state;
- shows connected email when available;
- shows last sync time when available;
- shows pending-review count when available;
- provides Connect or Configure action;
- expanded state retains Google connection, sync, settings, detections, and disconnect controls.

Primary file:

- `frontend/src/pages/TrackerPage.jsx`

Remaining production verification:

- connection and OAuth flow must be exercised with a real user session;
- Google OAuth cannot be fully verified through static credentials alone.

## R1-08: Make status summary cards filter the table

Implemented:

- each status card is now a button;
- clicking filters the tracker table;
- clicking the active card clears the status filter;
- selected state uses `aria-pressed` and visible styling;
- status dropdown and cards share the same state;
- counts use the same query, workspace, and source filter scope as the table.

Primary file:

- `frontend/src/pages/TrackerPage.jsx`

## R1-09: Copy the full job description

Implemented:

- copy source is the stored `full_description` field;
- no title, teaser, excerpt, or DOM-text fallback is used;
- paragraph and list line breaks are normalized;
- escaped persisted line breaks are restored;
- success appears only after Clipboard API success;
- missing full description produces a clear error;
- **Open description** remains available;
- multi-paragraph regression tests were added.

Files:

- `frontend/src/lib/trackerDescription.js`
- `frontend/src/lib/trackerDescription.test.js`
- `frontend/src/pages/TrackerPage.jsx`
- `frontend/src/pages/JobDescriptionPage.jsx`

Validated:

- focused Node tests pass;
- frontend lint and production build pass.

## R2-09: Remove Career Memory header actions

Implemented:

- removed **Edit a CV**;
- removed **Manage documents**;
- retained **Continue guided interview**;
- did not change CV Studio, Asset Library, or guided-review logic.

Files:

- `frontend/src/components/careerMemoryBuilder/MemoryBuilderHeader.jsx`
- `frontend/src/components/careerMemoryBuilder/CareerMemoryBuilderPage.jsx`
- `frontend/src/pages/ArtifactsPage.jsx`

# Part II: Implemented locally

All items in this section were completed on June 23, 2026. The detailed approach below is retained as the implementation rationale. Production remains unchanged until this local batch is deployed.

## R1-02: Better run-start feedback

### What already exists

- Workspace actions report validation, enqueue, success, and errors.
- Workspace Run/Test Run buttons are disabled during submission.
- Quick Apply prevents duplicate submission and shows `Starting...`.
- Workspace runs navigate to `/runs/{run_id}` after backend creation.
- The required route is already preserved.

### Best completion approach

Create one shared run-start state model:

```text
validating -> enqueuing -> queued -> navigating
```

Each phase must follow the real request lifecycle, not a timer.

Add:

- `aria-live="polite"` state text;
- phase-specific spinner or progress icon;
- shared duplicate-submission lock across equivalent controls;
- retained validation details;
- immediate navigation when the backend returns the run ID.

Files:

- `frontend/src/hooks/useWorkspaceRunActions.js`
- `frontend/src/pages/WorkspacesPage.jsx`
- `frontend/src/pages/QuickApplyPage.jsx`
- new shared `RunStartStatus` component

Tests:

- rapid repeated clicks issue one POST;
- phases change only when the corresponding request resolves;
- errors unlock controls;
- destination remains `/runs/{run_id}`.

## R1-11: Keep the CV preview visible

### What already exists

- field edits rebuild the preview HTML immediately;
- desktop already uses two columns;
- the editor column is currently sticky;
- the preview is a real HTML iframe.

### Missing behavior

- the preview column itself is not sticky;
- the preview iframe is fixed at a tall page height instead of scrolling within the viewport;
- mobile has no explicit Editor/Preview toggle.

### Best completion approach

Desktop:

- make the preview column sticky;
- position it below the fixed app header;
- cap it to the viewport height;
- give the preview container internal scrolling;
- leave the editor in normal page flow.

Mobile:

- add an accessible Editor/Preview segmented control;
- render one mode at a time;
- preserve unsaved state while switching.

Tests:

- preview stays visible while editor content scrolls;
- iframe content updates after editing;
- mobile only displays the selected pane;
- keyboard focus remains predictable.

## R2-01: Structured bullet-list editing

### What already exists

- generated CV data can contain arrays of bullet strings;
- HTML preview renders bullet arrays as `<ul>/<li>`;
- DOCX output writes bullet paragraphs;
- the browser editor converts arrays to newline text.

### Missing behavior

- list structure is lost in the editor model;
- no indent/outdent levels;
- Enter does not behave like a list editor;
- DOCX currently prefixes a bullet character instead of using a shared structured hierarchy.

### Best completion approach

Adopt a canonical list model:

```json
{
  "items": [
    {"id": "item_1", "text": "Improved reporting speed", "level": 0},
    {"id": "item_2", "text": "Automated validation", "level": 1}
  ]
}
```

Editor behavior:

- Enter creates the next bullet;
- Enter on empty bullet exits the list;
- Tab/Shift+Tab indent and outdent;
- toolbar actions mirror keyboard actions;
- stable item IDs prevent focus loss.

Migration:

- convert arrays of strings;
- convert newline text;
- remove legacy dash/bullet prefixes safely.

Rendering:

- nested HTML lists;
- native DOCX list levels;
- PDF generated from the same semantic structure.

## R2-02: Fix Experience population and layout

### What already exists

- generated `role_title` maps to editor `title`;
- company, period, and bullets are mapped;
- multiple experience blocks are supported;
- preview updates from editor state.

### Missing behavior

- location is dropped;
- dates are collapsed into one unstructured period;
- fields rely on placeholders rather than visible labels;
- array index is used as entry identity;
- aliases are not normalized comprehensively;
- empty values can produce unclear geometry.

### Best completion approach

Define one canonical entry:

```json
{
  "id": "experience_1",
  "title": "...",
  "company": "...",
  "start_date": "...",
  "end_date": "...",
  "period": "...",
  "location": "...",
  "achievements": []
}
```

Normalize:

- `role_title`, `role`, `title`;
- `start_date`, `end_date`, `period`;
- `location`, `location_raw`;
- `bullets`, `bulletsText`, `achievements`.

UI:

- use visible labels;
- support explicit dates and location;
- use stable IDs;
- show explicit empty states;
- enforce usable minimum control widths.

Files:

- backend tracker CV seed adapter;
- `frontend/src/lib/cvStudio.js`;
- `frontend/src/pages/CvStudioPage.jsx`.

## R2-06: Robust OCR for scanned Career Assets

### What already exists

- DOCX native extraction;
- PDF native-text extraction;
- PDF OCR fallback when native text is empty;
- image OCR for common image formats;
- Tesseract and German language data are installed in the production Docker image;
- tests cover native PDFs, empty scanned PDFs, and a mocked OCR fallback.

### Missing behavior

- insufficient native text does not trigger OCR;
- no page-level extraction record;
- no OCR confidence;
- no rotation/orientation correction;
- no low-resolution warning;
- no mixed native/OCR page handling;
- no visible extraction quality in Asset Library;
- no realistic rotated, low-resolution, or multi-page fixtures.

### Best completion approach

Store page-level extraction:

```json
{
  "pages": [
    {
      "page": 1,
      "method": "ocr",
      "text": "...",
      "confidence": 0.82,
      "rotation": 90
    }
  ],
  "status": "ready_with_warnings"
}
```

Pipeline:

1. perform native extraction per page;
2. evaluate text density and printability;
3. OCR only insufficient pages;
4. detect/correct orientation;
5. preprocess low-resolution scans;
6. aggregate confidence and failed-page counts;
7. expose queued, processing, ready, warning, and failed states.

The Asset Library should display extraction method, confidence, warnings, and failed-page count.

## R2-07: Remove inappropriate reusable asset types

### What is implemented locally

- general upload choices no longer offer Master Career Profile;
- general upload choices no longer offer Motivation Letter;
- helper copy no longer advertises those types;
- existing records remain visible with legacy labels;
- job-specific motivation-letter behavior is untouched.

### What remains

Career Memory Sources can still upload a detailed CV using the legacy `master_career_profile` type.

### Best completion approach

- upload detailed source documents as normal supporting documents;
- allow selection of an existing baseline/detailed CV;
- reject new general `master_career_profile` and `motivation_letter` uploads in the backend;
- continue to read and download legacy records;
- provide a migration that maps legacy records to supported types without deleting source files.

Tests:

- deprecated types cannot be newly created;
- legacy records remain readable;
- motivation letters remain available only in job/application context.

# Part III: Implemented locally from the approved approach

## R1-04: Focus the active run-progress section

Status: **Implemented locally**.

The Run Detail page now has a stable progress target:

```jsx
<section id="run-progress" ref={progressRef} tabIndex={-1}>
```

When an active run first loads:

1. focus the status heading;
2. scroll the progress section into view;
3. use automatic scrolling for reduced motion;
4. record that focus already happened for the run;
5. never refocus because of polling.

Support `/runs/{run_id}#run-progress`.

New runs open with this hash. A per-run focus claim prevents polling from moving the viewport again.

Tests:

- active run focuses once;
- completed run does not force focus;
- polling does not move the viewport;
- reduced-motion preference is respected.

## R1-05: Show a truthful backend-derived ETA

Status: **Implemented locally**.

The server now uses persisted run data:

- queue delay from `queued_at` to `started_at`;
- duration per workflow stage;
- current stage and elapsed time;
- recent completed runs with matching workflow/stage types.

Backend response:

```json
{
  "eta": {
    "state": "estimated",
    "remaining_seconds_low": 180,
    "remaining_seconds_high": 420,
    "confidence": "medium",
    "sample_count": 12,
    "calculated_at": "..."
  }
}
```

Rules:

- use a range instead of false precision;
- return `estimating` when evidence is weak;
- calculate on the server;
- do not run a client-only countdown;
- completion/failure remains based on persisted run status.

UI copy:

```text
Estimated 3-7 minutes remaining.
You can leave this page and return later; progress is saved.
```

The UI shows `Estimating remaining time...` until at least three comparable samples exist. It does not run a client countdown.

## R2-03: Active sidebar section steps back

Status: **Implemented locally**.

An explicit parent-route registry now handles:

```text
/career-memory/guide            -> /documents?view=memory
/documents?view=memory          -> /documents
/cv-studio                      -> /documents
/tracker/job-descriptions/:id   -> /tracker
/job-workspaces/:run/:job       -> /workspaces
/runs/:run                      -> /runs
```

When the active section is clicked:

- navigate to its explicit parent;
- repeat until section root;
- do nothing at root;
- do not use browser history;
- preserve unsaved-change warnings.

The resolver must include query parameters because Asset Library and Career Memory share `/documents`.

Career Memory registers both SPA navigation and browser-unload warnings while its legacy settings form is dirty.

## R2-05: Move ATS details out of tracker rows

Status: **Implemented locally**.

Tracker rows now use a compact control:

```text
ATS 15% · Blocked
```

The dedicated route is:

```text
/tracker/{review_id}/ats
```

Detail view should include:

- overall score and target;
- gate state;
- attempt history;
- missing/present criteria;
- CV asset and artifact identifiers;
- job-description identifier and extraction state;
- language/extraction warnings;
- read-only recommendations.

Preserve tracker state in URL parameters and return to a row anchor.

This work must not alter ATS scoring.

The detail endpoint only reports persisted data and explicitly states that it does not recalculate the score.

## R2-11: Replace the Career Memory generator

Status: **Implemented locally**.

The Career Memory Build tab now uses a fact/provenance model instead of concatenating questionnaire answers and fixed prompt language.

Canonical fact:

```json
{
  "fact_id": "...",
  "subject": {
    "company": "...",
    "role": "...",
    "project": "..."
  },
  "type": "action|tool|stakeholder|outcome|metric",
  "value": "...",
  "certainty": "confirmed|estimated|uncertain",
  "sources": [
    {"asset_id": "...", "page": 2, "quote_hash": "..."}
  ],
  "created_by": "user|extraction",
  "version": 1
}
```

Workflow:

1. extract candidate facts from selected sources;
2. ask one question for the most valuable missing or ambiguous fact;
3. require confirmation for numbers and unsupported claims;
4. save immutable fact versions;
5. generate separate CV and cover-letter outputs;
6. validate grounding, grammar, repetition, and length;
7. show output beside the facts;
8. allow regenerate, shorten, technical emphasis, and edit without mutating facts.

Implemented APIs:

- `GET /career-memory`;
- `POST /career-memory/facts/extract`;
- `POST /career-memory/questions/next`;
- `POST /career-memory/facts/{fact_id}/confirm`;
- `POST /career-memory/outputs/generate`;
- `POST /career-memory/outputs/{output_id}/regenerate`.

Facts and output versions are stored immutably in Career Memory user metadata. Source signature changes stale the prior extracted version and create a new active version.

Quality gate must reject or flag:

- unsupported phrases;
- unconfirmed metrics;
- raw questionnaire text;
- repeated language;
- excessive bullet length;
- malformed company/role context;
- duplicated CV and cover-letter output.

# Part IV: Answers to clarification questions

## R1-01: What does "Improve dashboard accuracy" mean?

It is not AI accuracy.

The count is:

```text
unknown tracker statuses
+ submitted applications missing application dates
+ tracker records with an unknown source
```

It counts defective fields, not unique rows. One application can contribute multiple issues.

Dashboard confidence is:

```text
100 * max(0, 1 - issue_count / max(1, tracker_item_count * 2))
```

The action appears when `issue_count > 0`, subject to the action-plan priority limit.

**Clean up tracker** currently only navigates to `/tracker`. It does not prefilter, repair, or identify the affected records.

Recommended copy:

- Title: **Fix incomplete tracker data**
- Body: **{count} missing or unclear tracker fields reduce dashboard reporting confidence. Review unknown statuses, missing application dates, and unknown sources.**
- Action: **Review incomplete fields**

No implementation should occur until this replacement behavior is approved.

## R1-10: Which CV does "Edit CV" open?

It does not open the generated DOCX/PDF artifact directly.

It creates a browser CV Studio seed from job-specific generated fields:

- professional summary;
- professional experience;
- skills;
- education;
- strategic initiatives.

Missing values fall back to the saved user profile.

Current identity limitations:

- tracker has run ID and job ID;
- those IDs are not passed into CV Studio;
- artifact ID is not passed;
- seed is stored in browser `localStorage`;
- seed expires after 10 minutes and is consumed once.

Save behavior:

- draft autosaves to a browser-wide local session;
- Print/Save PDF exports the browser draft;
- Save Design Defaults changes reusable template settings;
- the original generated CV is not updated.

Before job-specific saving is implemented, define a durable CV draft/artifact version model.

## R2-04: Why does ATS rarely reach 90%?

### Recorded production job

- Run: `run_23aaf4bd981e4b91`
- Job: `4431658322`
- Deutsche Post und DHL
- Sortierer für Briefe in Hennigsdorf
- Best score: 15%
- Attempts: 2 of 3
- Stop: score stalled
- Mode: aggressive customization

### CV source

- asset: `asset_765bc74b756a4c93`;
- file: `Ahmed Kaddah CV.docx`;
- content hash: `7a8d4b472d949c488c067300b383b855ba6621c745275c6dd6d75fcc4e45abb7`;
- 6,988 extracted characters;
- native DOCX extraction succeeded;
- no stale-CV evidence.

### Job-description source

The stored `full_description` was only a listing teaser containing title, company, location, and posting-age text. It was not a real job description and contained encoding corruption.

The scorer nevertheless inferred requirements such as shift work and German level. Those requirements were not grounded in the stored description.

### Scoring formula

There is no deterministic formula or weighting table.

DeepSeek receives:

- source CV text;
- up to 6,000 characters of job description;
- current structured CV draft.

It returns one 0-100 score, missing requirements, recommendations, and rationale. The backend only clamps the score to 0-100.

Therefore:

- no numeric component breakdown exists;
- scoring is not reproducible;
- it is not an exact-keyword formula;
- component weights do not exist;
- the requested component-level score cannot be recovered from stored data.

### Meaning of Pass 2/3

It means the second scored draft out of three configured attempts.

Processing stops when:

- score reaches 90;
- attempts are exhausted;
- a new score fails to improve.

### Production attainability

Across 26 scored production jobs:

- minimum: 15;
- median: 45;
- mean: 45;
- maximum: 72;
- scores >= 90: 0;
- observed pass rate: 0%;
- score-stalled jobs: 10.

There is no production evidence that 90% is currently attainable.

### Best diagnostic approach

Before changing scoring, persist:

- CV content hash and artifact/version;
- job-description hash and extraction version;
- scorer model and prompt version;
- deterministic component evidence;
- model response;
- unsupported inferred requirements;
- language and extraction warnings.

Do not change the target, weights, or CV content strategy before that instrumentation exists.

## R2-08: How does the guided Career Memory review work?

The next question is not dynamically selected.

The default flow is a fixed five-step questionnaire:

1. previous problem;
2. change made;
3. beneficiary;
4. outcome;
5. estimated impact.

**Continue guided interview** only returns to the Build tab. It does not inspect source documents or choose a next-best question.

Current completeness is count-based:

- baseline CV connected;
- three achievement/project stories;
- two metrics;
- one project;
- motivation memory or 60 characters of notes.

Memory readiness is based on non-empty fields and numeric-looking text, not semantic quality or source evidence.

The flow ends after five questions. Weak memories are revisited only when the user manually chooses Improve or Add metric.

There is no:

- source-aware question skipping;
- contradiction detection;
- provenance check;
- weak-memory prioritization;
- immutable fact layer.

The redesign should not begin until the fact and completeness models are approved.

## R2-10: What do Sources and Advanced do?

Sources are uploaded candidate assets. The UI stores selected asset IDs but does not create fact-level provenance.

Changing a source does not:

- update memories;
- invalidate derived facts;
- flag contradictions;
- regenerate wording.

Advanced fields currently store:

- imported long-form profile text;
- achievement highlights;
- additional bullet fragments;
- hurdles and transition context;
- motivation-letter notes.

These values are saved into user document settings and can be copied into run overrides for selected/full personalization scopes.

However, the document-generation backend does not currently consume these Career Memory keys. There is no demonstrated effect on CV tailoring or motivation-letter generation.

Best approach:

1. approve a fact/provenance model;
2. connect source records to facts;
3. mark facts stale when sources change;
4. explicitly define which facts can feed CVs, motivation letters, or both;
5. integrate the generation backend only after those rules exist.

# Part V: Recommended delivery sequence

1. Deploy and verify the current local implementation batch.
2. Production-verify R1-04, R1-05, R2-03, R2-05, and R2-11 against real run, tracker, and candidate-asset data.
3. Deploy and verify the completed CV Studio model/UI migration for R1-11, R2-01, and R2-02.
4. Deploy and verify the completed R2-06 and R2-07 ingestion cleanup.
5. Approve the R1-01, R1-10, R2-04, R2-08, and R2-10 designs before changing those behaviors.

# Part VI: Protected scope

Do not:

- change ATS weights, target, threshold, or CV content strategy before diagnostics are approved;
- add fabricated skills, keywords, metrics, responsibilities, or experience;
- redesign the dashboard broadly;
- change Workspace/Quick Apply navigation away from the specific Run Detail route;
- alter Documents ZIP/download behavior;
- connect legacy Career Memory advanced free-text settings to downstream generation before R2-10 logic is approved.
