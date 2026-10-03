# Runr App Review: Implementation Guide for Unfinished Issues

Date: 2026-06-22

This report covers approved issues that remain unfinished or partially implemented. Investigation-only items are listed separately and must not be implemented without approval.

## Current status summary

Implemented in the current working tree:

- R1-03: visible Run Review QA checklist removed;
- R1-06: Quick Apply sentence removed;
- R1-07: Inbox Sync collapsed behind an on-demand control;
- R1-08: status cards filter and synchronize with the tracker table;
- R1-09: full-description copy behavior and regression tests;
- R2-09: duplicate Career Memory header actions removed.

Partially implemented:

- R1-02: real submission states and duplicate-click prevention exist, but feedback is visually minimal;
- R2-06: basic OCR exists, but quality/confidence/page metadata and robust scan handling do not;
- R2-07: general upload choices were cleaned up, but the Career Memory source flow can still create a legacy master-profile asset.

## R1-02: Better run-start feedback

### Existing foundation

- Workspace actions expose validation, enqueue, success, and error messages.
- Workspace Run/Test Run buttons are disabled during submission.
- Quick Apply disables duplicate submission and shows `Starting...`.
- Workspace runs navigate to `/runs/{run_id}` after the backend creates the run.

### Implementation

Create a shared `RunStartStatus` component with backend-linked phases:

```text
validating -> enqueuing -> queued -> navigating
```

Each phase should be driven by the actual promise lifecycle. Do not use a fixed-duration animation.

Add:

- spinner/progress icon only while a phase is active;
- `aria-live="polite"` status text;
- disabled state on all equivalent submit controls;
- retained backend validation details;
- immediate transition to the existing run-detail route when the run ID exists.

Files:

- `frontend/src/hooks/useWorkspaceRunActions.js`
- `frontend/src/pages/WorkspacesPage.jsx`
- `frontend/src/pages/QuickApplyPage.jsx`
- new shared run-start component

Tests:

- one POST for repeated clicks;
- phase order follows request completion;
- error restores controls;
- final route remains `/runs/{run_id}`.

## R1-04: Focus active run progress

### Implementation

Add a stable progress section:

```jsx
<section id="run-progress" ref={progressRef} tabIndex={-1}>
```

On the first successful load of an active run:

1. focus the progress heading/status region;
2. scroll it into view;
3. use `behavior: "auto"` for reduced motion and `"smooth"` otherwise;
4. record `run_id` in a ref or session state so polling never repeats the scroll.

Support direct links such as:

```text
/runs/{run_id}#run-progress
```

Do not trigger from polling updates after the user has scrolled.

Files:

- `frontend/src/pages/RunDetailPage.jsx`
- run navigation calls in Workspace and Quick Apply

Tests:

- active entry focuses once;
- completed runs do not force focus;
- reduced motion is respected;
- refresh polling does not move the viewport.

## R1-05: Backend-derived ETA

### Backend model

Use persisted run and stage timestamps:

- `queued_at`
- `started_at`
- current stage
- `run_stage_results.started_at`
- `run_stage_results.finished_at`
- recent completed runs with the same workflow/stage type

Calculate server-side:

- recent queue-delay median;
- median duration per remaining stage;
- 20th-80th percentile range;
- elapsed time in the current stage;
- confidence based on sample count and duration variance.

Suggested payload:

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

When evidence is weak, return `state: "estimating"` rather than a fabricated countdown.

### Frontend

Show:

- `Estimated 3-7 minutes remaining`;
- `Estimating...`;
- concise copy explaining that the user may leave and return.

Completion and failure must continue to come from backend run status.

Tests:

- ETA decreases only when new backend state is received;
- low sample counts return a range or estimating state;
- reopening the route reconstructs progress from persisted run data;
- completed/failed states replace ETA.

## R1-11: Keep CV preview visible

The current left editor column is sticky; the preview is not.

### Desktop implementation

- make the preview column `position: sticky`;
- use `top` based on the fixed header;
- cap height with `calc(100vh - header - spacing)`;
- let the preview container/iframe scroll internally;
- keep editor scrolling in the page.

### Small-screen implementation

Use an accessible Editor/Preview segmented control. Do not render two compressed columns.

The existing state already rebuilds preview HTML immediately after field edits.

Tests:

- preview wrapper has sticky desktop behavior;
- iframe remains visible while editor scrolls;
- mobile only shows the selected mode;
- editing updates `srcDoc`.

## R2-01: Structured bullet-list editing

### Canonical model

Replace editor-only newline strings with structured list data:

```json
{
  "items": [
    {"id": "...", "text": "Improved reporting speed", "level": 0},
    {"id": "...", "text": "Automated validation", "level": 1}
  ]
}
```

Accept legacy arrays of strings and dash-prefixed text through a migration adapter.

### Editor behavior

Implement a focused list editor:

- Enter creates the next item;
- Enter on an empty item exits the list;
- Tab/Shift+Tab indent and outdent;
- toolbar actions create/remove/indent/outdent;
- keyboard and buttons expose accessible labels.

### Rendering

- HTML preview renders nested `<ul>` structures.
- DOCX uses paragraph list levels instead of manually prefixing a bullet character.
- PDF inherits the same HTML list structure.

Tests:

- keyboard continuation and exit;
- indent bounds;
- legacy migration;
- save/reload round trip;
- equivalent HTML and DOCX hierarchy.

## R2-02: Experience data binding and layout

### Canonical entry

Define one adapter-backed structure:

```json
{
  "id": "...",
  "title": "...",
  "company": "...",
  "start_date": "...",
  "end_date": "...",
  "period": "...",
  "location": "...",
  "achievements": []
}
```

Normalize existing aliases including:

- `role_title`, `role`, `title`;
- `start_date`, `end_date`, `period`;
- `location`, `location_raw`;
- `bullets`, `bulletsText`, `achievements`.

### UI

- label every field visibly;
- add location and explicit date fields;
- assign stable entry IDs instead of array-index identity;
- show "No title", "No company", or "No achievements yet" rather than blank geometry;
- prevent controls from shrinking below usable widths.

Files:

- backend tracker CV seed adapter;
- `frontend/src/lib/cvStudio.js`;
- `frontend/src/pages/CvStudioPage.jsx`.

Tests:

- multiple entries;
- long company/title values;
- missing fields;
- generated JSON aliases;
- reorder/edit without cross-entry corruption.

## R2-03: Active sidebar section steps back

Create an explicit route-parent registry instead of browser history:

```text
/career-memory/guide       -> /documents?view=memory
/documents?view=memory     -> /documents
/cv-studio                 -> /documents
/tracker/job-descriptions/:id -> /tracker
/job-workspaces/:run/:job  -> /workspaces
/runs/:run                 -> /runs
```

When an active main sidebar item is clicked:

- navigate to the registered parent;
- at section root, do nothing;
- preserve or invoke unsaved-change blockers before navigation.

The resolver must inspect pathname and search parameters because Career Memory and Asset Library share `/documents`.

Tests:

- every nested route has a parent;
- repeated clicks reach root then become idempotent;
- navigation never leaves the section;
- unsaved edits block or confirm.

## R2-05: Move ATS details out of tracker rows

### Tracker row

Replace the large panel with one compact control:

```text
ATS 15% · Blocked
```

### Detail route

Add:

```text
/tracker/{review_id}/ats
```

The detail response should include:

- run, job, CV asset, generated artifact, and description identifiers;
- overall score and target;
- gate and attempt history;
- missing/present criteria;
- extraction/language warnings;
- scorer version;
- non-destructive recommendations.

Preserve tracker state in URL query parameters and record the row anchor:

```text
/tracker?status=not_applied&source=all#review-{id}
```

Do not modify scoring in this work.

Tests:

- tracker rows remain bounded in height;
- one-click detail navigation;
- return restores filters and scroll;
- score payload is read-only.

## R2-06: Robust OCR for Career Assets

### Existing capability

General PDF/image uploads can fall back to Tesseract OCR, and production images include Tesseract with German language data.

### Missing capability

- "insufficient" native text detection, not only empty text;
- page-level output and references;
- OCR confidence;
- rotation/orientation correction;
- low-resolution handling;
- asynchronous status;
- visible low-confidence/failure UI;
- realistic scan fixtures.

### Implementation

Return page records:

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

Use native extraction first. Fall back per page when text density/printability is below a threshold. Run orientation detection and preprocessing before OCR.

Move expensive OCR to a processing job and expose:

```text
uploaded -> queued -> processing -> ready | ready_with_warnings | failed
```

The Asset Library must display method, confidence, warning, and failed-page count.

Tests:

- text PDF avoids OCR;
- image-only PDF uses OCR;
- mixed PDF uses per-page fallback;
- 90/180-degree rotation;
- low-resolution scan warning;
- multi-page page references;
- unreadable scan is not marked ready.

## R2-07: Finish reusable asset-type cleanup

### Completed

- general upload choices no longer offer master career profile or motivation letter;
- legacy records remain visible with legacy labels.

### Remaining

Career Memory's Sources tab can still upload a "detailed CV" as `master_career_profile`.

Replace this with:

- selection of an existing baseline/detailed CV source; or
- upload as a normal supporting document with extraction metadata.

Do not create new `master_career_profile` records. Keep existing records read-only and migratable.

Add backend validation rejecting new general `master_career_profile` and `motivation_letter` uploads while allowing legacy reads.

Tests:

- removed types cannot be newly uploaded;
- legacy records still render/download;
- job-specific motivation-letter generation remains unaffected.

## R2-11: Fact-grounded Career Memory workflow

The current generator is client-side string concatenation. Rebuild it around facts before changing presentation.

### Domain model

```json
{
  "fact_id": "...",
  "subject": {"company": "...", "role": "...", "project": "..."},
  "type": "action|tool|stakeholder|outcome|metric",
  "value": "...",
  "certainty": "confirmed|estimated|uncertain",
  "sources": [{"asset_id": "...", "page": 2, "quote_hash": "..."}],
  "created_by": "user|extraction",
  "version": 1
}
```

Generated wording must reference fact IDs and never mutate facts.

### Workflow

1. Extract candidate facts from selected sources.
2. Ask one short question for the highest-value missing/ambiguous fact.
3. Require explicit confirmation for metrics and unsupported claims.
4. Save immutable fact versions.
5. Generate separate CV bullet and cover-letter narrative.
6. Run a quality/grounding validator.
7. Show side-by-side editable output with regenerate/shorten/emphasis actions.

### Quality gate

Reject or flag output when:

- a phrase has no supporting fact;
- a number is unconfirmed;
- prompt/question text leaks into output;
- the CV bullet exceeds configured length;
- wording repeats;
- company/role context is malformed;
- the cover-letter text duplicates the bullet.

### API boundaries

- `POST /career-memory/facts/extract`
- `POST /career-memory/questions/next`
- `POST /career-memory/facts/{id}/confirm`
- `POST /career-memory/outputs/generate`
- `POST /career-memory/outputs/{id}/regenerate`

Tests:

- no unsupported metrics;
- no prompt leakage;
- fact IDs survive regeneration;
- CV and letter outputs differ;
- edits do not mutate facts;
- source changes mark dependent facts stale.

## Investigation-only follow-up designs

These require approval before implementation:

- R1-01: add an incomplete-data tracker filter and revised copy;
- R1-10: introduce durable job-CV draft/artifact identity and save behavior;
- R2-04: versioned ATS assessment and deterministic component diagnostics;
- R2-08: dynamic question selection and semantic completeness model;
- R2-10: fact-level source provenance and actual downstream tailoring integration.

## Recommended delivery order

1. R1-02 and R1-04: run-start and progress focus.
2. R1-05: backend ETA.
3. R1-11, R2-01, R2-02: CV Studio work as one model/UI slice.
4. R2-03: route-parent navigation.
5. R2-05: compact ATS detail route without changing scoring.
6. R2-06 and remaining R2-07: ingestion and asset cleanup.
7. Approve R2-08/R2-10 domain decisions.
8. R2-11: rebuild Career Memory on the approved fact/provenance model.

