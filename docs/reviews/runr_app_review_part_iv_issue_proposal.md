# Runr App Review Part IV: Solution and Implementable Issue Proposal

Date: 2026-06-23

Status: Proposed for review. No GitHub issues have been created.

Source: `docs/reviews/runr_app_review_complete_report.md`, Part IV.

## Proposed decisions

Approval of this proposal means approving these product and domain decisions:

1. Dashboard "accuracy" is renamed to **reporting confidence** and remains a count of defective tracker fields, not applications.
2. Dashboard cleanup opens a prefiltered tracker view that identifies the exact incomplete fields. Missing application dates and source attribution become editable.
3. CV Studio uses a durable job-specific draft. Draft state is mutable, while explicitly saved and published versions are immutable.
4. Publishing from CV Studio creates new artifacts and never overwrites the original generated CV.
5. ATS scoring remains unchanged until versioned production diagnostics are collected and reviewed.
6. ATS component diagnostics are evidence coverage measurements, not hidden weights and not a replacement final score.
7. Career Memory is rebuilt around immutable, versioned facts with source provenance. Generated CV and letter wording references fact versions but cannot mutate them.
8. Career Memory question selection is deterministic and testable. An LLM may phrase a question, but it does not decide priority.
9. Advanced text fields become explicit manual sources. Raw text blobs are not passed directly into document generation.
10. Each run freezes the Career Fact version IDs it used so generated artifacts remain reproducible.

## Proposed domain models

### Tracker data-quality issue

Each tracker row receives canonical issue codes calculated by the backend:

```json
{
  "data_quality_issues": [
    {
      "code": "unknown_status",
      "field": "application_status",
      "label": "Choose an application status"
    },
    {
      "code": "missing_application_date",
      "field": "application_date",
      "label": "Add the application date"
    },
    {
      "code": "unknown_source",
      "field": "source_attribution",
      "label": "Choose an application source"
    }
  ]
}
```

`source_attribution` is user-editable analytics attribution. It does not overwrite the technical ingestion source stored on the job.

### Job CV draft and versions

```text
job_cv_draft
  draft_id
  user_id
  run_id
  job_id
  source_artifact_id | null
  source_kind = artifact | structured_run_data
  current_revision
  current_payload

job_cv_version
  version_id
  draft_id
  version_number
  parent_version_id | null
  content_hash
  payload
  publication_artifact_ids
  created_at
```

Autosave updates the current draft with optimistic concurrency. **Save job CV draft** creates an immutable version. **Save as new generated artifact** publishes an immutable version to new DOCX/PDF artifacts.

### ATS assessment

```text
ats_assessment
  assessment_id
  user_id
  run_id
  job_id
  cv_asset_id
  cv_content_hash
  generated_draft_hash
  generated_artifact_id | null
  job_description_hash
  job_description_extraction_version
  scorer_model
  scorer_prompt_version
  target_score
  input_warnings

ats_attempt
  assessment_id
  attempt_number
  score
  raw_model_response
  normalized_response
  grounded_requirement_evidence
  component_coverage
```

Component coverage is calculated from validated requirement evidence. It does not feed the current ATS gate.

### Career Facts

```text
career_source
  source_id
  user_id
  kind = asset | manual_note | legacy_import
  asset_id | null
  content_hash
  extraction_version
  status

career_fact_group
  group_id
  user_id
  kind = role | project | achievement | motivation

career_fact_version
  fact_version_id
  fact_id
  version_number
  group_id
  type = context | action | tool | stakeholder | outcome | metric | motivation
  value
  certainty = confirmed | estimated | uncertain
  status = active | stale | rejected
  destinations = cv | letter | interview
  supersedes_version_id | null

career_fact_source
  fact_version_id
  source_id
  document_id | null
  page | null
  quote_hash
  bounded_excerpt

career_output_version
  output_version_id
  output_type = cv_bullet | letter_angle
  fact_version_ids
  text
  generator_version
  validation_result
```

A fact edit creates a new fact version. A wording edit creates a new output version. Neither operation mutates the other.

## Proposed issue breakdown

### 1. Route dashboard data-quality actions to an incomplete tracker view

- **Type:** AFK
- **Blocked by:** None
- **Review items covered:** R1-01

#### What to build

Replace the misleading dashboard copy and make both dashboard data-quality actions open `/tracker?quality=incomplete`. Calculate canonical issue codes on tracker rows in the backend, apply the URL-driven filter in Tracker, and visibly label every affected field.

#### Acceptance criteria

- [ ] Dashboard action title is **Fix incomplete tracker data**.
- [ ] Body says `{count} missing or unclear tracker fields reduce dashboard reporting confidence. Review unknown statuses, missing application dates, and unknown sources.`
- [ ] Action label is **Review incomplete fields**.
- [ ] Dashboard and Tracker use the same backend issue definitions.
- [ ] `/tracker?quality=incomplete` shows only rows with at least one data-quality issue.
- [ ] Each filtered row shows issue chips for status, application date, and/or source.
- [ ] The count is labelled as fields or data issues, never items or applications.
- [ ] Existing tracker filters compose with the quality filter and Clear removes it from the URL.
- [ ] Backend API and frontend filter tests cover rows with one and multiple issue codes.

#### Out of scope

- Automatic repair.
- Changing the confidence formula.

---

### 2. Repair missing tracker dates and source attribution inline

- **Type:** AFK
- **Blocked by:** Issue 1
- **Review items covered:** R1-01

#### What to build

Make every reported tracker defect repairable. Reuse the status dropdown, add an application-date editor, and add canonical source-attribution choices. Persist the values for both run-backed and external tracker rows, then recalculate dashboard data quality and source effectiveness.

#### Acceptance criteria

- [ ] Unknown status is resolved through the existing status control.
- [ ] Submitted applications without a date expose a date editor.
- [ ] Application date persists in review metadata or the external application record.
- [ ] Unknown source exposes canonical attribution choices: LinkedIn, company site, Arbeitsagentur, referral, recruiter, and other.
- [ ] Source attribution is stored separately from the immutable technical ingestion source.
- [ ] Dashboard source effectiveness prefers user attribution and falls back to the technical source.
- [ ] Saving a repaired field removes its issue code without a full browser reload.
- [ ] Dashboard issue count and confidence reflect the repaired values after refresh.
- [ ] API tests cover authorization, validation, run-backed rows, and external rows.

#### Out of scope

- Inferring an application date or source without user confirmation.

---

### 3. Open and autosave a durable job-specific CV Studio draft

- **Type:** AFK
- **Blocked by:** None
- **Review items covered:** R1-10

#### What to build

Replace Tracker's transient browser seed with a server-owned job CV draft. Opening **Edit CV** resolves the authenticated review, run, job, and preferred generated CV artifact on the backend, creates or reopens the draft, and routes CV Studio by `draft_id`.

#### Acceptance criteria

- [ ] A draft is owned by one user and bound to one run and job.
- [ ] The source artifact/document ID is stored when available; otherwise the source is labelled `structured_run_data`.
- [ ] CV Studio displays job title, company, run ID, job ID, source artifact, and draft revision.
- [ ] Draft content is initialized from the job-specific generated fields with existing profile fallbacks.
- [ ] Autosave persists server-side using optimistic concurrency.
- [ ] A stale browser write receives a conflict response and cannot overwrite a newer revision silently.
- [ ] Browser storage is only a draft-scoped recovery cache, not the canonical state.
- [ ] Reopening the same Tracker job restores its own draft; drafts from other jobs cannot leak into it.
- [ ] Authorization tests prevent access through another user's draft, run, or artifact ID.
- [ ] Existing Settings-to-CV-Studio behavior remains available for non-job design work.

---

### 4. Publish a CV Studio draft as a new immutable artifact version

- **Type:** AFK
- **Blocked by:** Issue 3
- **Review items covered:** R1-10

#### What to build

Add explicit **Save job CV draft** and **Save as new generated artifact** actions. Saving creates an immutable draft version. Publishing renders new DOCX/PDF artifacts from that version and records lineage to the source version and original artifact.

#### Acceptance criteria

- [ ] **Save job CV draft** creates an immutable version with a content hash.
- [ ] **Save as new generated artifact** publishes a saved version, not anonymous browser state.
- [ ] Published artifacts receive new IDs and never overwrite existing files or artifact records.
- [ ] Artifact metadata records run ID, job ID, draft ID, version ID, parent version, and original source artifact.
- [ ] Existing rendering functions are reused for DOCX/PDF output.
- [ ] Tracker and Documents expose the new version while keeping older versions downloadable.
- [ ] **Save design defaults** remains separate and changes only reusable template settings.
- [ ] Publishing the same unchanged version is idempotent or clearly creates an intentional new publication.
- [ ] Tests verify lineage, immutability, rendering, authorization, and preservation of the original artifact.

---

### 5. Persist versioned ATS assessments and input-quality warnings

- **Type:** AFK
- **Blocked by:** None
- **Review items covered:** R2-04

#### What to build

Create one durable ATS assessment per scored job and persist each attempt. Record input identities and hashes, model and prompt versions, normalized and raw responses, stop reason, and deterministic input-quality warnings.

#### Acceptance criteria

- [ ] Every scored job receives an `assessment_id`.
- [ ] The assessment stores CV asset/document identity and SHA-256.
- [ ] Each generated draft attempt stores a deterministic content hash.
- [ ] The job-description hash and extraction/version metadata are stored.
- [ ] Scorer model, system-prompt version, score-prompt version, and improvement-prompt version are explicit constants and persisted.
- [ ] Raw and normalized model responses are stored per attempt.
- [ ] Warnings detect at least: unusually short description, likely listing teaser, mojibake, missing extraction metadata, CV/job language mismatch, and CV extraction warnings.
- [ ] Existing ATS target, attempt limit, score, stopping rules, and export gate behavior remain unchanged.
- [ ] Existing attempt-history consumers remain backward compatible.
- [ ] Repository, migration, generation, and API tests cover persistence and retry behavior.

---

### 6. Add grounded ATS requirement evidence and component diagnostics

- **Type:** AFK
- **Blocked by:** Issue 5
- **Review items covered:** R2-04

#### What to build

Extend the versioned scorer response with categorized requirements and evidence quotes. Validate quotes against the stored job description and CV draft, flag unsupported inferred requirements, and calculate unweighted category coverage for diagnostics only.

#### Acceptance criteria

- [ ] Requirement categories are limited to: role/title, skills/tools, responsibilities/experience, education/certification, language, and availability/location/schedule.
- [ ] Every requirement includes a job-description evidence quote or is marked unsupported.
- [ ] Supported requirements include a CV evidence quote or are marked missing.
- [ ] Backend validation confirms evidence quotes exist in the versioned inputs after normalization.
- [ ] Unsupported inferred requirements are persisted and excluded from deterministic coverage.
- [ ] Category coverage is `supported grounded requirements / grounded requirements`; unavailable categories are reported as unavailable, not zero.
- [ ] No component weights or combined deterministic final score are introduced.
- [ ] The model's existing 0-100 score continues to drive the current gate unchanged.
- [ ] Old scorer responses remain readable through a compatibility normalizer.
- [ ] Tests cover valid evidence, hallucinated job requirements, invalid CV evidence, empty categories, and language requirements.

---

### 7. Populate the ATS detail route with versioned diagnostics

- **Type:** AFK
- **Blocked by:** Issues 5 and 6, plus the R2-05 ATS detail route
- **Review items covered:** R2-04

#### What to build

Expose assessment diagnostics through an authenticated API and render them in the dedicated ATS detail route planned by R2-05. Keep the Tracker row compact and link to the full audit.

#### Acceptance criteria

- [ ] The detail view identifies the CV version, job-description hash/version, model, prompts, target, attempts, and stop reason.
- [ ] Input-quality warnings are prominent before the score.
- [ ] Each attempt shows model score, changed sections, grounded missing requirements, unsupported inferences, and rationale.
- [ ] Component coverage is labelled diagnostic evidence coverage, not score weighting.
- [ ] The UI states when the job description is too weak for a trustworthy assessment.
- [ ] The recorded production case can be explained without claiming a recoverable weighted formula.
- [ ] API access is restricted to the owning user.
- [ ] Frontend and API tests cover complete, warning, legacy, and missing-assessment states.

---

### 8. Calibrate ATS policy from versioned production evidence

- **Type:** HITL
- **Blocked by:** Issue 7 and a representative production sample
- **Review items covered:** R2-04

#### What to build

Produce a calibration report after collecting at least 30 versioned production assessments across the main source types. Review score distribution, description quality, unsupported inference rate, language mismatch, and evidence coverage before deciding whether to retain or change the ATS target and gate.

#### Acceptance criteria

- [ ] Report separates high-quality and low-quality job descriptions.
- [ ] Report includes pass rate, score distribution, stall rate, unsupported inference rate, and category coverage.
- [ ] Report compares model score with grounded evidence coverage without treating correlation as causation.
- [ ] A human-approved decision records one of: retain current policy, change target, replace gate logic, or disable blocking for low-quality inputs.
- [ ] The decision is recorded in an ADR or approved GitHub issue before any scoring-policy implementation.

#### Out of scope

- Implementing the eventual scoring-policy change.

---

### 9. Create a versioned Career Fact store with manual fact review

- **Type:** AFK after this proposal's model is approved
- **Blocked by:** None
- **Review items covered:** R2-08, R2-10, prerequisite for R2-11

#### What to build

Introduce the Career Source, Fact Group, immutable Fact Version, and Fact Source models. Deliver one end-to-end manual path in Career Memory where a user creates, confirms, views, supersedes, and rejects a sourced fact.

#### Acceptance criteria

- [ ] Fact versions are immutable and superseding an edit creates a new version.
- [ ] Facts support certainty, status, destination eligibility, grouping, and provenance.
- [ ] Manual user statements are represented as manual sources, not source-less facts.
- [ ] A user can create and review a fact through the existing Career Memory surface.
- [ ] Fact detail shows current value, certainty, source, prior versions, and destinations.
- [ ] Rejecting or superseding a fact does not delete its history.
- [ ] User ownership is enforced at repository, service, and API layers.
- [ ] Existing generated memory cards remain readable during migration.
- [ ] Migration and API tests cover immutability, ownership, version history, and legacy coexistence.

---

### 10. Extract candidate facts from sources and mark dependent facts stale

- **Type:** AFK
- **Blocked by:** Issue 9
- **Review items covered:** R2-08, R2-10, prerequisite for R2-11

#### What to build

Use existing extracted document text and page metadata to create reviewable candidate facts from selected sources. Accepting a candidate creates a fact version with provenance. Replacing or re-extracting source content marks dependent facts stale when the source fingerprint changes.

#### Acceptance criteria

- [ ] Extraction uses the stored candidate document text and page-level metadata; it does not reread arbitrary local paths.
- [ ] Each candidate includes type, value, certainty, bounded excerpt, page when known, and source fingerprint.
- [ ] Candidates are never eligible for generation until accepted or explicitly confirmed.
- [ ] Metrics require explicit user confirmation before they become active.
- [ ] Accepting a candidate creates immutable fact and provenance records.
- [ ] Rejecting a candidate prevents it from being silently re-added for the same source version.
- [ ] A changed source content hash or extraction version marks dependent active facts stale.
- [ ] Stale facts remain visible but are excluded from generation until reconfirmed.
- [ ] Sources UI shows extraction state, candidate count, accepted facts, and stale facts.
- [ ] Tests cover page provenance, metric confirmation, idempotent extraction, source replacement, and stale invalidation.

---

### 11. Replace the fixed Career Memory interview with deterministic next-question selection

- **Type:** AFK
- **Blocked by:** Issues 9 and 10
- **Review items covered:** R2-08, prerequisite for R2-11

#### What to build

Replace the client-side five-step progression with a backend next-question service driven by fact state. Answers create or confirm fact versions. Replace count-based readiness with destination-specific semantic readiness.

#### Selection priority

1. Resolve contradictions.
2. Reconfirm stale facts.
3. Confirm unsupported or uncertain numeric claims.
4. Fill a missing core fact in the active story.
5. Fill a missing destination-specific fact.
6. Start a new story using the existing recovery prompts.

#### Semantic readiness

- A CV story is ready when it has a confirmed action and outcome, grounded by a source or explicit user confirmation.
- A letter angle is ready when it has confirmed motivation/context plus supporting evidence.
- A numeric claim is never ready while uncertain or unconfirmed.
- Breadth goals such as additional stories remain suggestions, not proof that an individual memory is complete.

#### Acceptance criteria

- [ ] `questions/next` returns one question, its reason, target fact type/group, and blocking condition.
- [ ] The same fact state produces the same priority result.
- [ ] User answers create or confirm fact versions rather than concatenated memory-card text.
- [ ] **Continue guided interview** requests the actual next question.
- [ ] Imported source facts skip questions whose answers are already confirmed.
- [ ] Contradictions, stale facts, and uncertain metrics outrank new-story prompts.
- [ ] Progress shows CV-ready, letter-ready, needs confirmation, and stale states.
- [ ] The existing fixed question sets remain available only as empty-state recovery templates.
- [ ] Tests cover all priority branches and semantic readiness rules.

---

### 12. Migrate Advanced text into explicit manual sources

- **Type:** AFK
- **Blocked by:** Issues 9 and 10
- **Review items covered:** R2-10, prerequisite for R2-11

#### What to build

Convert each Advanced field into a versioned manual source subtype. Run the same candidate-fact review flow used for uploaded sources, make migration idempotent, and stop copying raw Advanced blobs directly into generation overrides.

#### Acceptance criteria

- [ ] Existing long-form profile, achievement, bullet-bank, hurdles, and motivation fields migrate without data loss.
- [ ] Each field becomes a labelled manual source with content hash and version history.
- [ ] Updating a field creates a new source version and stales dependent facts.
- [ ] Advanced UI shows source state: not processed, candidates ready, facts accepted, or stale.
- [ ] Users review extracted facts before they become active.
- [ ] Raw Advanced text is no longer treated as generated wording or passed directly to document prompts.
- [ ] The migration can be rerun safely without duplicate sources or facts.
- [ ] Legacy fields remain readable during rollout and can be removed only in a later cleanup issue.
- [ ] Tests cover all five field types, repeat migration, source edits, and no direct generation override.

---

### 13. Generate CV and letter wording from approved fact versions

- **Type:** AFK
- **Blocked by:** Issue 9
- **Review items covered:** R2-08, R2-10, R2-11

#### What to build

Generate separate CV-bullet and motivation-letter outputs from explicitly selected active fact versions. Persist output versions and grounding validation, and expose side-by-side review with regenerate, shorten, and change-emphasis actions.

#### Acceptance criteria

- [ ] Every output stores the exact fact-version IDs and generator/prompt version used.
- [ ] CV and letter outputs are generated separately and are not duplicates.
- [ ] Generated wording cannot add a number absent from the selected confirmed or estimated facts.
- [ ] Every material claim is traceable to at least one selected fact version.
- [ ] Prompt/question text leakage is rejected.
- [ ] Configured length, repetition, malformed context, and duplicate-output checks are enforced.
- [ ] Regeneration creates a new output version without mutating facts.
- [ ] User wording edits create an output revision without mutating facts.
- [ ] Stale or rejected facts cannot be selected.
- [ ] Tests cover unsupported metrics, provenance survival, output differences, regeneration, edits, and validation failures.

---

### 14. Use approved Career Facts in run personalization and generated artifacts

- **Type:** AFK
- **Blocked by:** Issues 10, 12, and 13
- **Review items covered:** R2-10, R2-11

#### What to build

Replace unused Career Memory override keys with a frozen fact snapshot consumed by the CV and motivation-letter generation backend. Define exact behavior for each personalization scope and record used fact versions on generated artifacts.

#### Personalization rules

- **Baseline CV only:** no Career Facts are added.
- **Baseline + selected assets:** include active destination-eligible facts whose provenance contains a selected asset; manually confirmed facts require an explicit include toggle.
- **Full career profile:** include all active destination-eligible confirmed facts, plus explicitly accepted estimated facts.

#### Acceptance criteria

- [ ] Starting a run resolves allowed fact versions according to personalization scope.
- [ ] The run stores an immutable snapshot of selected fact-version IDs and source fingerprints.
- [ ] CV generation receives only CV-eligible facts; motivation-letter generation receives only letter-eligible facts.
- [ ] Raw legacy Career Memory text keys are not sent to generation.
- [ ] Generated artifact metadata records fact-version IDs, source fingerprints, and generator version.
- [ ] Later fact edits do not change the historical run or artifact snapshot.
- [ ] Source changes after run start do not silently alter in-progress generation.
- [ ] Grounding validation prevents unsupported claims from reaching final artifacts.
- [ ] End-to-end tests prove that selected/full scopes affect outputs and baseline-only does not.

## Dependency and delivery sequence

```text
Tracker:
1 -> 2

CV Studio:
3 -> 4

ATS:
5 -> 6 -> 7 -> 8 (human calibration decision)

Career Memory:
9 -> 10 -> 11
     |     |
     +--> 12
9 --------> 13
10 + 12 + 13 -> 14
```

Recommended implementation order:

1. Issues 1-2: close the dashboard/tracker behavior gap.
2. Issues 3-4: establish safe CV identity and publishing.
3. Issues 5-7: collect and expose ATS evidence without changing scoring.
4. Issues 9-10: establish facts and provenance.
5. Issues 11-13: replace guided review, migrate Advanced sources, and generate grounded wording.
6. Issue 14: connect approved facts to production document generation.
7. Issue 8: make the ATS policy decision after enough production evidence exists.

## Review questions

Before creating GitHub issues or implementing code, confirm:

1. Is the 14-issue granularity acceptable, or should any slices be merged or split?
2. Should source attribution be user-editable as proposed?
3. Should CV Studio publish both DOCX and PDF, or only the format selected by the user?
4. Is the proposed semantic Career Memory readiness model acceptable?
5. Is 30 versioned ATS assessments enough for the first calibration review?
6. Which approved issue numbers should be created or implemented first?
