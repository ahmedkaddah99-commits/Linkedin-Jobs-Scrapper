import assert from "node:assert/strict";
import test from "node:test";

import {
  LIFECYCLE_STATE,
  LIFECYCLE_ORDER,
  STATE_INDEX,
  STATE_LABELS,
  STATE_PRIMARY_ACTION,
  applyCanonicalJourneyState,
  buildLifecycleSummary,
  lifecycleProgress,
  nextLifecycleState,
  progressLabel,
  resolveLifecycleState,
} from "./careerEvidenceFlow.js";

test("canonical journey advances when evidence is not mirrored into settings", () => {
  const settingsDerived = buildLifecycleSummary({
    sources: [{ document_id: "doc_1" }],
    selectedSourceIds: ["doc_1"],
    evidenceItems: [],
  });
  assert.equal(settingsDerived.state, LIFECYCLE_STATE.PROCESSING);
  assert.equal(
    applyCanonicalJourneyState(settingsDerived, {
      state: "review",
      next_review: { evidence: { evidence_id: "ev_1", status: "needs_review" } },
    }).state,
    LIFECYCLE_STATE.REVIEW,
  );
});

test("canonical question and ready states override stale settings", () => {
  const summary = buildLifecycleSummary({
    sources: [{ document_id: "doc_1" }],
    selectedSourceIds: ["doc_1"],
  });
  assert.equal(applyCanonicalJourneyState(summary, { state: "question" }).state, LIFECYCLE_STATE.REVIEW);
  assert.equal(applyCanonicalJourneyState(summary, { state: "ready" }).state, LIFECYCLE_STATE.READY);
});

// CP-038R: Lifecycle order is deterministic and fixed.
test("LIFECYCLE_ORDER has four visible states in the seamless sequence", () => {
  assert.deepStrictEqual(LIFECYCLE_ORDER, [
    "source",
    "processing",
    "review",
    "ready",
  ]);
  assert.equal(LIFECYCLE_ORDER.length, 4);
});

test("STATE_INDEX maps every lifecycle state to its ordinal", () => {
  assert.equal(STATE_INDEX.source, 0);
  assert.equal(STATE_INDEX.processing, 1);
  assert.equal(STATE_INDEX.review, 2);
  assert.equal(STATE_INDEX.ready, 3);
});

test("every state has a label and primary action", () => {
  for (const state of LIFECYCLE_ORDER) {
    assert.ok(STATE_LABELS[state], `${state} must have a label`);
    assert.ok(STATE_PRIMARY_ACTION[state], `${state} must have a primary action`);
  }
});

// CP-038R: State resolver returns SOURCE when no sources exist.
test("resolveLifecycleState returns source when no sources and no evidence", () => {
  assert.equal(resolveLifecycleState({}), LIFECYCLE_STATE.SOURCE);
  assert.equal(
    resolveLifecycleState({ sources: [], selectedSourceIds: [], evidenceItems: [] }),
    LIFECYCLE_STATE.SOURCE,
  );
});

// CP-038R: State resolver returns SOURCE when sources exist but none selected.
test("resolveLifecycleState returns source when sources available but none selected", () => {
  const sources = [{ document_id: "doc_1", display_name: "CV.pdf" }];
  assert.equal(
    resolveLifecycleState({ sources, selectedSourceIds: [], evidenceItems: [] }),
    LIFECYCLE_STATE.SOURCE,
  );
});


// CP-038R: State resolver returns PROCESSING when sources selected but no evidence.
test("resolveLifecycleState returns processing when sources selected but no evidence", () => {
  const sources = [{ document_id: "doc_1" }];
  assert.equal(
    resolveLifecycleState({ sources, selectedSourceIds: ["doc_1"], evidenceItems: [] }),
    LIFECYCLE_STATE.PROCESSING,
  );
});

// CP-038R: Evidence needs review → review state.
test("resolveLifecycleState returns review when evidence needs review", () => {
  const evidence = [{ evidence_id: "ev_1", status: "needs_review", text: "Skill" }];
  assert.equal(
    resolveLifecycleState({
      sources: [{ document_id: "doc_1" }],
      selectedSourceIds: ["doc_1"],
      evidenceItems: evidence,
    }),
    LIFECYCLE_STATE.REVIEW,
  );
});

// CP-038R: Confirmed evidence without mapping → mapping state.
test("confirmed but unmapped evidence remains in inline review", () => {
  const evidence = [{ evidence_id: "ev_1", status: "confirmed", text: "Led team" }];
  assert.equal(
    resolveLifecycleState({
      sources: [{ document_id: "doc_1" }],
      selectedSourceIds: ["doc_1"],
      evidenceItems: evidence,
      experienceLinks: [],
    }),
    LIFECYCLE_STATE.REVIEW,
  );
});

// CP-038R: Mapped evidence with pending questions → follow_up.
test("pending questions remain in inline review", () => {
  const evidence = [{ evidence_id: "ev_1", status: "confirmed", experience_mapping: { experience_id: "exp_1" } }];
  const links = [{ link_id: "lnk_1", evidence_id: "ev_1", mapped: true }];
  const questions = [{ question_id: "q_1", resolved: false, dismissed: false }];
  assert.equal(
    resolveLifecycleState({
      sources: [{ document_id: "doc_1" }],
      selectedSourceIds: ["doc_1"],
      evidenceItems: evidence,
      experienceLinks: links,
      pendingQuestions: questions,
    }),
    LIFECYCLE_STATE.REVIEW,
  );
});

// CP-038R: All done → ready state.
test("resolveLifecycleState returns ready when all steps complete", () => {
  const evidence = [{ evidence_id: "ev_1", status: "confirmed", experience_mapping: { experience_id: "exp_1" } }];
  const links = [{ link_id: "lnk_1", evidence_id: "ev_1", mapped: true }];
  const questions = [{ question_id: "q_1", resolved: true, dismissed: false }];
  assert.equal(
    resolveLifecycleState({
      sources: [{ document_id: "doc_1" }],
      selectedSourceIds: ["doc_1"],
      evidenceItems: evidence,
      experienceLinks: links,
      pendingQuestions: questions,
    }),
    LIFECYCLE_STATE.READY,
  );
});

// CP-038R: Dismissed questions → ready.
test("dismissed questions resolve to ready", () => {
  const evidence = [{ evidence_id: "ev_1", status: "confirmed", experience_mapping: { experience_id: "exp_1" } }];
  const links = [{ link_id: "lnk_1", evidence_id: "ev_1", mapped: true }];
  const questions = [{ question_id: "q_1", resolved: false, dismissed: true }];
  assert.equal(
    resolveLifecycleState({
      sources: [{ document_id: "doc_1" }],
      selectedSourceIds: ["doc_1"],
      evidenceItems: evidence,
      experienceLinks: links,
      pendingQuestions: questions,
    }),
    LIFECYCLE_STATE.READY,
  );
});

// CP-038R: Automatic advancement — nextLifecycleState.
test("nextLifecycleState advances through the lifecycle in order", () => {
  assert.equal(nextLifecycleState(LIFECYCLE_STATE.SOURCE), LIFECYCLE_STATE.PROCESSING);
  assert.equal(nextLifecycleState(LIFECYCLE_STATE.PROCESSING), LIFECYCLE_STATE.REVIEW);
  assert.equal(nextLifecycleState(LIFECYCLE_STATE.REVIEW), LIFECYCLE_STATE.READY);
  assert.equal(nextLifecycleState(LIFECYCLE_STATE.READY), LIFECYCLE_STATE.READY);
});

// CP-038R: Progress calculations.
test("lifecycleProgress returns correct fractions", () => {
  assert.equal(lifecycleProgress(LIFECYCLE_STATE.SOURCE), 0);
  assert.equal(lifecycleProgress(LIFECYCLE_STATE.PROCESSING), 1 / 3);
  assert.equal(lifecycleProgress(LIFECYCLE_STATE.REVIEW), 2 / 3);
  assert.equal(lifecycleProgress(LIFECYCLE_STATE.READY), 1);
});

test("progressLabel returns step-based labels", () => {
  assert.equal(progressLabel(LIFECYCLE_STATE.SOURCE), "Step 1 of 4");
  assert.equal(progressLabel(LIFECYCLE_STATE.READY), "Step 4 of 4");
});

// CP-038R: buildLifecycleSummary returns exactly one primary action.
test("buildLifecycleSummary returns one primary action for ready state", () => {
  const summary = buildLifecycleSummary({
    sources: [{ document_id: "doc_1" }],
    selectedSourceIds: ["doc_1"],
    evidenceItems: [{ evidence_id: "ev_1", status: "confirmed", experience_mapping: { experience_id: "exp_1" } }],
    experienceLinks: [{ link_id: "lnk_1", evidence_id: "ev_1", mapped: true }],
    pendingQuestions: [],
  });
  assert.equal(summary.state, LIFECYCLE_STATE.READY);
  assert.equal(summary.primaryAction, "View profile");
  assert.equal(summary.progress, 1);
  assert.ok(summary.label);
  assert.ok(summary.description);
});

// CP-038R: Empty input → source with one action.
test("buildLifecycleSummary with empty input returns source state", () => {
  const summary = buildLifecycleSummary({});
  assert.equal(summary.state, LIFECYCLE_STATE.SOURCE);
  assert.equal(summary.primaryAction, "Upload source");
});

// CP-038R: No competing tabs — only one primary action returned.
test("buildLifecycleSummary returns exactly one primaryAction string", () => {
  for (const state of LIFECYCLE_ORDER) {
    const summary = buildLifecycleSummary({
      sources: state !== "source" ? [{ document_id: "doc_1" }] : [],
      selectedSourceIds: ["source", "processing", "review"].includes(state) ? [] : ["doc_1"],
      evidenceItems: ["review", "mapping", "follow_up", "ready"].includes(state)
        ? [{ evidence_id: "ev_1", status: state === "review" ? "needs_review" : "confirmed" }]
        : [],
      experienceLinks: ["follow_up", "ready"].includes(state)
        ? [{ link_id: "lnk_1", mapped: true }]
        : [],
      pendingQuestions: state === "follow_up"
        ? [{ question_id: "q_1", resolved: false }]
        : [],
    });
    assert.equal(typeof summary.primaryAction, "string");
    assert.ok(summary.primaryAction.length > 0);
  }
});

