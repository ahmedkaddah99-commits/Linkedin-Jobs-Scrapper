# Runr App Review: Clarifications and Investigation Findings

Date: 2026-06-22

This report answers the review items that require explanation or diagnosis before implementation. It is based on the current code, the two recordings, and read-only production checks against Render and Turso.

## R1-01: What "Improve dashboard accuracy" means

### Current definition

The count is a tracker data-quality defect count:

```text
unknown application statuses
+ submitted applications missing an application date
+ tracker records with an unknown source
```

It counts defective fields, not unique applications. One tracker row can increase the count more than once.

The dashboard confidence percentage is:

```text
100 * max(0, 1 - issue_count / max(1, tracker_item_count * 2))
```

### Triggering conditions

The action is eligible when `issue_count > 0`. It is low priority and is last in the candidate action list, so it may not appear if six higher-priority actions already occupy the action plan.

### What "Clean up tracker" currently does

It only navigates to `/tracker`. It does not:

- prefilter incomplete rows;
- identify the affected fields;
- automatically repair data;
- recalculate or modify records.

### Recommended replacement copy

- Title: **Fix incomplete tracker data**
- Body: **{count} missing or unclear tracker fields reduce dashboard reporting confidence. Review unknown statuses, missing application dates, and unknown sources.**
- Action: **Review incomplete fields**

The UI should call the number "fields" or "data issues", not "items".

## R1-10: Which CV "Edit CV" opens

### Current source

Tracker's **Edit CV** does not open the generated DOCX/PDF artifact itself.

It builds an editable browser profile from the generated CV fields stored on the exact tracker job:

- `cv_professional_summary`
- `cv_professional_experience`
- `cv_skills`
- `cv_education`
- `cv_strategic_initiatives`

Missing values are supplemented from the user's saved profile. The resulting seed is passed to CV Studio through browser `localStorage`.

### Identity and lifetime

- The source tracker row has `run_id` and `job_id`.
- Those identifiers are not included in the CV Studio seed.
- No generated document/artifact ID is included.
- The seed expires after 10 minutes and is consumed once.
- CV Studio shows a human-readable role/company label but not durable artifact identity.

### Save behavior

- Draft edits autosave to a browser-wide CV Studio session in `localStorage`.
- **Print / Save PDF** exports the current browser draft.
- **Save Design Defaults** writes reusable template settings to `/settings`.
- It does not update the original generated CV, tracker job data, DOCX, or PDF.

### Required UI clarification

The header should show:

```text
Editing generated CV draft
Job: {title} at {company}
Run: {run_id}
Job ID: {job_id}
Source artifact: {artifact_id or "structured run data"}
```

The save actions should be renamed to distinguish:

- **Save job CV draft**
- **Save as new generated artifact**
- **Save design defaults**

No job-specific save should be added until a durable artifact/version model is approved.

## R2-04: ATS scoring diagnosis

### Recorded production case

- Run ID: `run_23aaf4bd981e4b91`
- Job ID: `4431658322`
- Company: Deutsche Post und DHL
- Job: Sortierer für Briefe in Hennigsdorf (m/w/d)
- Best score: 15%
- Target: 90%
- Attempts: 2 of 3
- Stop reason: `score_stalled`
- CV mode: `aggressive_customization`

### CV artifact/version scored

The scorer used:

- workspace CV asset: `asset_765bc74b756a4c93`
- display name: `Ahmed Kaddah CV.docx`
- content SHA-256: `7a8d4b472d949c488c067300b383b855ba6621c745275c6dd6d75fcc4e45abb7`
- extracted source length: 6,988 characters
- extraction method: DOCX native text
- run binding: `workspace_cv`
- two generated CV drafts were scored; both received 15%, so the first remained the stored best draft

The generated artifacts were the job-specific CV DOCX and PDF associated with run `run_23aaf4bd981e4b91` and job `4431658322`; the ATS gate remained blocked unless explicitly overridden.

### Job-description version scored

The scorer used the `full_description` stored on the generated job row. It was not a complete job description. It contained only a short listing teaser: title, company, location, and posting-age text.

Consequences:

- substantive duties and requirements were absent;
- the text contained character-encoding corruption;
- the scorer inferred requirements that were not present in the stored text;
- there is no persisted description content hash or extraction-version ID.

This is the strongest diagnosed cause of unreliable scoring in the recorded case.

### Actual scoring formula

There is no deterministic formula or weighting table.

The backend sends the source CV, up to 6,000 characters of the job description, and the structured tailored CV to DeepSeek. The model returns:

- one integer score from 0 to 100;
- missing requirements;
- improvement actions;
- a rationale.

The backend only clamps the returned score to the range 0-100. It does not calculate weighted skill, experience, education, language, title, or keyword components.

Therefore:

- no exact component-level numeric breakdown exists;
- the score is model judgment, not a reproducible ATS formula;
- it is not strictly exact-keyword based, although wording and keyword overlap influence the model;
- the overall score is capped at 100;
- the input job description is capped at 6,000 characters.

### Meaning of "Pass 2/3" and gate states

`Pass 2/3` means the second scored CV draft out of a maximum of three attempts.

The loop stops when:

- score reaches at least 90: `target_reached`;
- all configured attempts are used: `max_attempts_reached`;
- a later score does not improve: `score_stalled`.

Export gate behavior:

- score >= target: `passed`, final export allowed;
- below target while more attempts remain: `scoring`, final export blocked;
- attempts exhausted or score stalled: `blocked`, manual export override allowed;
- user accepts warning: `exported_anyway`, export allowed without changing the score.

### Recorded-case score evidence

Attempt 1 scored 15%. Attempt 2 also scored 15%, so processing stopped as stalled.

The stored rationale says the CV evidence is centered on strategy, analytics, transformation, and operations leadership, while the job is a manual mail-sorting role. The scorer reported missing mail handling, sorting, warehouse, physical-task, and scheduling evidence.

There is no numeric component score. A truthful qualitative reading is:

- role/title alignment: very weak;
- direct task evidence: absent;
- industry/operational adjacency: limited;
- transferable process and operations evidence: present;
- language/schedule requirements: unknown because the stored job description is incomplete.

### Cache, extraction, and language findings

- Stale CV cache: no evidence; the run is bound to a specific CV asset and content hash.
- Failed CV extraction: no; DOCX extraction succeeded without warnings.
- Failed job extraction: effectively yes; the stored description is only a teaser.
- Language mismatch: yes; the job text/title is German while the generated CV output is English.
- Missing fields: yes; the stored job description lacks real duties and requirements.
- Character encoding: broken German characters are present in stored job text and generated paths.

### Is 90% realistically attainable?

Current production evidence says no.

Across 26 production generated jobs with ATS scores:

- minimum: 15
- median: 45
- mean: 45
- maximum: 72
- jobs at or above 90: 0
- observed pass rate: 0%
- score-stalled jobs: 10

Tests demonstrate 90+ only with mocked scorer responses. There is no live evidence that the current scorer/data pipeline can reach 90.

### Required diagnostic work before scoring changes

Add a versioned ATS assessment record containing:

- CV asset ID and content hash;
- generated CV artifact/version ID;
- job-description content hash and extraction method;
- scorer model and prompt version;
- deterministic component inputs;
- model response;
- component scores;
- unsupported inferred requirements;
- language and extraction-quality warnings.

Do not change the 90% target, weights, or CV content strategy until this data exists.

## R2-08: Current Career Memory guided-review logic

### How the next question is selected

It is not dynamically selected.

The default flow is a fixed five-step `story_recovery` questionnaire:

1. previous problem;
2. change made;
3. beneficiary;
4. outcome;
5. estimated impact.

Other fixed question sets can be started from "Next Best Actions". **Continue guided interview** only switches back to the Build tab; it does not calculate the next best question from source data or memory quality.

### What source data is read

The UI knows:

- uploaded asset metadata;
- whether a baseline CV exists;
- selected asset IDs;
- manually imported long-form text;
- existing memory cards.

The selected source documents are not parsed into facts for question selection. Imported source text does not automatically skip answered questions.

### What currently constitutes "complete"

The top-level checklist is complete when it has:

- one baseline CV;
- three achievement/project stories;
- two memories containing a metric;
- one project memory;
- one motivation memory or at least 60 characters of motivation notes.

A single memory card is considered ready when required text, change/ownership, beneficiary, outcome/reason, and normally a metric are present.

These are count-based heuristics, not semantic completeness checks.

### Facts versus generated wording

They are not cleanly separated.

Each card stores:

- raw note;
- loosely structured answers;
- generated CV bullet;
- generated cover-letter angle;
- status and missing-detail text.

The current generator is client-side string assembly. It can include questionnaire wording in `rawNote`, and regenerated wording is not backed by an immutable fact/version layer.

### How progress and missing items are calculated

Progress is based on the fixed checklist thresholds above.

Missing card details are derived from empty fields and the presence of any numeric-looking text. Source confidence and semantic evidence are not evaluated.

### When the flow ends or revisits weak memories

The flow ends after the fifth fixed question and shows a draft card.

Weak memories are revisited only when the user chooses **Improve** or **Add metric**. There is no automatic review schedule, contradiction detection, provenance check, or weak-memory prioritization.

## R2-10: Sources and Advanced tabs

### What a source record currently represents

A source is an uploaded candidate asset such as a baseline CV, certification, recommendation letter, or supporting document.

The UI stores selected asset IDs. It does not create fact-level provenance records linking a sentence or metric to a source page, paragraph, or confidence score.

### Do source edits update existing memories?

No.

Updating or replacing a source document does not:

- invalidate memories derived from it;
- regenerate memory cards;
- flag changed or contradictory facts;
- update existing wording.

### Advanced fields

- **Imported long-form profile text**: manually imported detailed career context.
- **Imported achievement highlights**: broad achievement notes not split into cards.
- **Additional bullet bank**: uncurated bullet fragments.
- **Professional hurdles and transition context**: narrative career-change or challenge context.
- **Motivation-letter notes**: reusable motivation and preference text.

These values are user-authored/imported text. They are not clearly distinguished from model-generated notes in the persisted settings schema.

### Do Sources and Advanced values affect tailoring?

They are saved to user document settings and may be copied into run overrides depending on personalization scope:

- selected assets: selected/full scope;
- advanced text and generated cards: full scope.

However, the document-generation backend does not currently read these Career Memory keys. They therefore do not presently have a demonstrated effect on CV tailoring or motivation-letter generation.

This integration gap should be resolved only after the fact/provenance model is approved.

## Production visibility notes

- Render API, frontend, and worker services were reachable.
- Production was still deployed at commit `d33b071`.
- Turso was queried read-only through the project virtual environment.
- The current working-tree UI changes are not deployed and are not claimed as production fixes.
