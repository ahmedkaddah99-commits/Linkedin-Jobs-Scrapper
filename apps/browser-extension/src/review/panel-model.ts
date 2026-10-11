import type {
  ApplicationPackageAnswer,
  ApplicationPackagePayload,
  AssistedApplyTabState,
  DocumentUploadMessage,
} from "@runr/extension-messages";

export type ReviewSection = "ready" | "review" | "missing" | "manual";

export type DocumentUploadStatus = "idle" | "uploading" | "uploaded" | "rejected" | "mismatch" | "preserved_existing";

export interface ReviewFieldRow extends ApplicationPackageAnswer {
  id: string;
  section: ReviewSection;
  liveAcceptance: "accepted" | "not_attempted" | "needs_review" | "manual";
  /** True when the form control for this field is required and currently empty. */
  requiredAndEmpty: boolean;
}

export interface DocumentRow {
  documentId: string;
  documentVersion: number;
  documentKind: string;
  fileName: string;
  mimeType: string;
  uploadStatus: DocumentUploadStatus;
  reasons: string[];
}

export interface ReviewPanelModel {
  enabled: boolean;
  rows: Record<ReviewSection, ReviewFieldRow[]>;
  counts: Record<ReviewSection | "documents" | "verified", number>;
  manualControls: string[];
  documents: DocumentRow[];
}

/**
 * Set of field intent or reason patterns that force a field into the Manual section
 * regardless of sensitivity or confidence. These match the AA-09 requirement for
 * CAPTCHA, declarations, signatures, terms, assessments, unsupported controls, and
 * disallowed sensitive answers.
 */
const MANUAL_FIELD_INTENT_PATTERNS: ReadonlyArray<RegExp> = [
  /captcha/u,
  /declaration/u,
  /signature/u,
  /terms/u,
  /assessment/u,
  /unsupported/u,
  /custom_control/u,
  /disallowed_sensitive/u,
];

function isManualByIntentOrReason(answer: ApplicationPackageAnswer): boolean {
  if (MANUAL_FIELD_INTENT_PATTERNS.some((pattern) => pattern.test(answer.fieldIntent))) {
    return true;
  }
  return answer.reasons.some((reason) =>
    MANUAL_FIELD_INTENT_PATTERNS.some((pattern) => pattern.test(reason)),
  );
}

const disallowedSensitivity = new Set(["legal", "demographic"]);

function sectionFor(answer: ApplicationPackageAnswer): ReviewSection {
  if (!answer.proposedValue.trim()) return "missing";
  if (disallowedSensitivity.has(answer.sensitivity)) return "manual";
  if (isManualByIntentOrReason(answer)) return "manual";
  if (answer.requiresReview || answer.source === "ai_suggestion" || answer.confidence < 0.9) {
    return "review";
  }
  return "ready";
}

/**
 * Infer whether a field is required from its intent and package metadata.
 * Fields with intents matching common required-answer patterns are considered
 * required when empty.
 */
function isFieldRequired(fieldIntent: string, _answers: ApplicationPackageAnswer[]): boolean {
  // Fields matching these patterns are manual-only controls (CAPTCHA, etc.)
  // and should never be flagged as required-and-empty.
  const manualIntentPatterns: ReadonlyArray<RegExp> = [
    /captcha/u,
    /signature/u,
    /terms/u,
    /declaration/u,
    /assessment/u,
    /unsupported/u,
    /custom_control/u,
  ];
  if (manualIntentPatterns.some((pattern) => pattern.test(fieldIntent))) {
    return false;
  }

  const requiredPatterns: ReadonlyArray<RegExp> = [
    /email/u,
    /phone/u,
    /name/u,
    /legal_first_name/u,
    /legal_last_name/u,
    /candidate\.\w+$/u,
    /application\.\w+$/u,
  ];
  return requiredPatterns.some((pattern) => pattern.test(fieldIntent));
}

function liveAcceptanceFor(
  section: ReviewSection,
  accepted: boolean,
): ReviewFieldRow["liveAcceptance"] {
  if (accepted) return "accepted";
  if (section === "manual") return "manual";
  if (section === "review") return "needs_review";
  return "not_attempted";
}

function documentUploadStatusFor(
  documentId: string,
  documentUpload: DocumentUploadMessage | null,
): DocumentUploadStatus {
  if (!documentUpload || documentUpload.documentId !== documentId) return "idle";
  if (documentUpload.status === "uploaded") return "uploaded";
  if (documentUpload.status === "rejected") return "rejected";
  if (documentUpload.status === "mismatch") return "mismatch";
  if (documentUpload.status === "preserved_existing") return "preserved_existing";
  return "idle";
}

export function buildReviewPanelModel(
  applicationPackage: ApplicationPackagePayload | null,
  state: AssistedApplyTabState | null,
  documentUpload: DocumentUploadMessage | null = null,
): ReviewPanelModel {
  const rows: ReviewPanelModel["rows"] = { ready: [], review: [], missing: [], manual: [] };
  if (applicationPackage) {
    applicationPackage.answers.forEach((answer, index) => {
      const section = sectionFor(answer);
      const accepted = state?.execution?.fieldLabel === answer.label &&
        ["filled", "already_filled"].includes(state.execution.status);
      rows[section].push({
        ...answer,
        id: `${answer.fieldIntent}:${index}`,
        section,
        liveAcceptance: liveAcceptanceFor(section, accepted),
        requiredAndEmpty: !answer.proposedValue.trim() && isFieldRequired(answer.fieldIntent, applicationPackage.answers),
      });
    });
  }

  const manualControls = Array.from(new Set(state?.manualReasons ?? []));
  const enabled = Boolean(
    applicationPackage &&
    state?.ats &&
    applicationPackage.job.portal === state.ats &&
    state.status !== "unsupported" &&
    state.status !== "error",
  );
  const verified = Object.values(rows).flat().filter((row) => row.liveAcceptance === "accepted").length;

  const documents: DocumentRow[] = (applicationPackage?.documents ?? []).map((doc) => ({
    documentId: doc.documentId,
    documentVersion: doc.documentVersion,
    documentKind: doc.documentKind,
    fileName: doc.fileName,
    mimeType: doc.mimeType,
    uploadStatus: documentUploadStatusFor(doc.documentId, documentUpload),
    reasons: documentUpload?.documentId === doc.documentId ? documentUpload.reasons : [],
  }));

  return {
    enabled,
    rows,
    counts: {
      ready: rows.ready.length,
      review: rows.review.length,
      missing: rows.missing.length,
      manual: rows.manual.length + manualControls.length,
      documents: documents.length,
      verified,
    },
    manualControls,
    documents,
  };
}

