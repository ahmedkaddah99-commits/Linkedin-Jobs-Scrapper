// CP-041R: Question state — shown inline after confirmation
export const QUESTION_STATE = {
  ASKED: "asked",
  ANSWERED: "answered",
  SKIPPED: "skipped",
};

// CP-044R: Career Evidence continuous journey — one action per screen.
// Reads canonical evidence records and returns the single next primary action.
//
// Lifecycle states (simplified — mapping/questions are inline during review):
//   source    — No verified sources selected; add/upload a source.
//   processing— Source(s) selected but evidence not yet extracted.
//   review    — Evidence extracted but not yet confirmed/rejected.
//               Mapping and missing-detail questions happen inline.
//   ready     — All steps complete; profile ready for tailoring.

export const LIFECYCLE_STATE = {
  SOURCE: "source",
  PROCESSING: "processing",
  REVIEW: "review",
  READY: "ready",
};

export const STATE_LABELS = {
  [LIFECYCLE_STATE.SOURCE]: "Add source evidence",
  [LIFECYCLE_STATE.PROCESSING]: "Processing evidence",
  [LIFECYCLE_STATE.REVIEW]: "Confirm evidence",
  [LIFECYCLE_STATE.READY]: "Ready to use",
};

export const STATE_DESCRIPTIONS = {
  [LIFECYCLE_STATE.SOURCE]:
    "Upload or select a source document to begin building your career evidence profile.",
  [LIFECYCLE_STATE.PROCESSING]:
    "Extracting evidence from your selected sources. This happens automatically.",
  [LIFECYCLE_STATE.REVIEW]:
    "Review, confirm, and map evidence from your sources. Questions appear inline.",
  [LIFECYCLE_STATE.READY]:
    "Your career evidence profile is complete and ready for tailoring applications.",
};

export const STATE_PRIMARY_ACTION = {
  [LIFECYCLE_STATE.SOURCE]: "Upload source",
  [LIFECYCLE_STATE.PROCESSING]: "View progress",
  [LIFECYCLE_STATE.REVIEW]: "Confirm evidence",
  [LIFECYCLE_STATE.READY]: "View profile",
};

export const LIFECYCLE_ORDER = [
  LIFECYCLE_STATE.SOURCE,
  LIFECYCLE_STATE.PROCESSING,
  LIFECYCLE_STATE.REVIEW,
  LIFECYCLE_STATE.READY,
];
// CP-039R: Source processing sub-states for compact UI display.
export const SOURCE_PROCESSING_STATE = {
  QUEUED: "queued",
  PROCESSING: "processing",
  COMPLETED: "completed",
  EMPTY: "empty",
  TIMEOUT: "timeout",
  FAILED: "failed",
};

export const SOURCE_PROCESSING_LABELS = {
  [SOURCE_PROCESSING_STATE.QUEUED]: "Queued",
  [SOURCE_PROCESSING_STATE.PROCESSING]: "Processing",
  [SOURCE_PROCESSING_STATE.COMPLETED]: "Extracted",
  [SOURCE_PROCESSING_STATE.EMPTY]: "No content found",
  [SOURCE_PROCESSING_STATE.TIMEOUT]: "Timed out",
  [SOURCE_PROCESSING_STATE.FAILED]: "Failed",
};

export const SOURCE_PROCESSING_DESCRIPTIONS = {
  [SOURCE_PROCESSING_STATE.QUEUED]: "Waiting to process...",
  [SOURCE_PROCESSING_STATE.PROCESSING]: "Gemini is extracting text and evidence...",
  [SOURCE_PROCESSING_STATE.COMPLETED]: "",
  [SOURCE_PROCESSING_STATE.EMPTY]: "No extractable content found in the source.",
  [SOURCE_PROCESSING_STATE.TIMEOUT]: "Processing timed out. You can retry.",
  [SOURCE_PROCESSING_STATE.FAILED]: "Processing failed. You can retry.",
};


// CP-040R: Evidence review actions
export const REVIEW_ACTION = {
  CONFIRM: "confirm",
  REJECT: "reject",
  EDIT: "edit",
};

export const REVIEW_ACTION_LABELS = {
  [REVIEW_ACTION.CONFIRM]: "Confirm",
  [REVIEW_ACTION.REJECT]: "Reject",
  [REVIEW_ACTION.EDIT]: "Edit",
};

/**
 * Compute canonical readiness from evidence items (CP-040R).
 * Replaces legacy memory-spike counters with canonical evidence statuses.
 */
export function computeCanonicalReadiness(evidenceItems = []) {
  const total = evidenceItems.length;
  const confirmed = evidenceItems.filter((ev) => ev && ev.status === "confirmed").length;
  const rejected = evidenceItems.filter((ev) => ev && ev.status === "rejected").length;
  const needsReview = evidenceItems.filter(
    (ev) => ev && (ev.status === "needs_review" || ev.status === "reviewed"),
  ).length;
  const merged = evidenceItems.filter((ev) => ev && ev.status === "merged").length;

  const mapped = evidenceItems.filter(
    (ev) =>
      ev &&
      ev.experience_mapping &&
      ev.experience_mapping.experience_id,
  ).length;
  const mappedReady = evidenceItems.filter(
    (ev) =>
      ev &&
      ev.status === "confirmed" &&
      ev.experience_mapping &&
      ev.experience_mapping.experience_id,
  ).length;

  const actionable = Math.max(total - merged - rejected, 0);
  const readinessRatio = actionable > 0
    ? Math.round((mappedReady / actionable) * 100) / 100
    : 0;

  return {
    total,
    confirmed,
    rejected,
    merged,
    needsReview,
    mapped,
    mappedReady,
    readinessRatio,
    isReady: readinessRatio >= 0.9 && needsReview === 0,
    computedFrom: "canonical_evidence",
    legacyCountersExcluded: true,
  };
}


export const STATE_INDEX = Object.fromEntries(
  LIFECYCLE_ORDER.map((state, index) => [state, index]),
);


/**
 * Resolve the current lifecycle state from canonical evidence records.
 */
export function resolveLifecycleState({
  sources = [],
  selectedSourceIds = [],
  evidenceItems = [],
  experienceLinks = [],
  pendingQuestions = [],
} = {}) {
  const normalizedSourceIds = new Set(
    (selectedSourceIds || []).map((id) => String(id || "").trim()).filter(Boolean),
  );
  const availableSources = (sources || []).filter(
    (s) => s && (s.document_id || s.asset_id || s.id),
  );

  if (availableSources.length === 0 && normalizedSourceIds.size === 0) {
    return LIFECYCLE_STATE.SOURCE;
  }

  const confirmedEvidence = (evidenceItems || []).filter(
    (ev) => ev && ev.status === "confirmed",
  );

  if (normalizedSourceIds.size === 0 && confirmedEvidence.length === 0) {
    return LIFECYCLE_STATE.SOURCE;
  }

  const allEvidence = evidenceItems || [];
  if (allEvidence.length === 0 && normalizedSourceIds.size > 0) {
    return LIFECYCLE_STATE.PROCESSING;
  }

  // CP-044R: Any unreviewed evidence → REVIEW (mapping/questions are inline)
  const needsReview = allEvidence.filter(
    (ev) => ev && (ev.status === "needs_review" || ev.status === "reviewed"),
  );
  if (needsReview.length > 0) {
    return LIFECYCLE_STATE.REVIEW;
  }

  // Mapping and questions stay visually inside REVIEW, but they still gate
  // readiness.  A confirmed item without a canonical experience ID must not
  // be presented as ready.
  const confirmedUnmapped = allEvidence.some(
    (ev) =>
      ev &&
      ev.status === "confirmed" &&
      !(ev.experience_mapping && ev.experience_mapping.experience_id),
  );
  const unresolvedQuestions = (pendingQuestions || []).some(
    (q) => q && !q.resolved && !q.dismissed && q.state !== "answered" && q.state !== "skipped",
  );
  if (confirmedUnmapped || unresolvedQuestions) {
    return LIFECYCLE_STATE.REVIEW;
  }

  // All actionable evidence is confirmed and mapped (or rejected).
  return LIFECYCLE_STATE.READY;
}

/**
 * Calculate the progress fraction (0-1) given a lifecycle state.
 */
export function lifecycleProgress(state) {
  const index = STATE_INDEX[state] ?? 0;
  return Math.min(index / (LIFECYCLE_ORDER.length - 1), 1);
}

/**
 * Get the next state after a successful action.
 */
export function nextLifecycleState(currentState) {
  const currentIndex = STATE_INDEX[currentState] ?? 0;
  const nextIndex = Math.min(currentIndex + 1, LIFECYCLE_ORDER.length - 1);
  return LIFECYCLE_ORDER[nextIndex];
}

/**
 * Derive a compact progress label.
 */
export function progressLabel(state) {
  const index = STATE_INDEX[state] ?? 0;
  return `Step ${index + 1} of ${LIFECYCLE_ORDER.length}`;
}

/**
 * Build a lifecycle summary used by the guided UI.
 */
export function buildLifecycleSummary({
  sources = [],
  selectedSourceIds = [],
  evidenceItems = [],
  experienceLinks = [],
  pendingQuestions = [],
} = {}) {
  const state = resolveLifecycleState({
    sources, selectedSourceIds, evidenceItems,
    experienceLinks, pendingQuestions,
  });

  const confirmedEvidence = (evidenceItems || []).filter(
    (ev) => ev && ev.status === "confirmed",
  );
  const mappedLinks = (experienceLinks || []).filter(
    (link) => link && (link.mapped || link.linked),
  );
  const unresolvedQuestions = (pendingQuestions || []).filter(
    (q) => q && !q.resolved && !q.dismissed,
  );

  return {
    state,
    label: STATE_LABELS[state] || STATE_LABELS[LIFECYCLE_STATE.SOURCE],
    description: STATE_DESCRIPTIONS[state] || "",
    primaryAction: STATE_PRIMARY_ACTION[state] || "",
    progress: lifecycleProgress(state),
    progressLabel: progressLabel(state),
    sourceCount: (sources || []).length,
    selectedSourceCount: (new Set((selectedSourceIds || []).map(String))).size,
    evidenceCount: (evidenceItems || []).length,
    confirmedCount: confirmedEvidence.length,
    mappedCount: mappedLinks.length,
    pendingQuestionCount: unresolvedQuestions.length,
    nextState: nextLifecycleState(state),
  };
}
