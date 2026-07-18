import type {
  ApplicationPackageAnswer,
  ApplicationPackagePayload,
  AssistedApplyTabState,
} from "@runr/extension-messages";

export type ReviewSection = "ready" | "review" | "missing" | "manual";

export interface ReviewFieldRow extends ApplicationPackageAnswer {
  id: string;
  section: ReviewSection;
  liveAcceptance: "accepted" | "not_attempted" | "needs_review" | "manual";
}

export interface ReviewPanelModel {
  enabled: boolean;
  rows: Record<ReviewSection, ReviewFieldRow[]>;
  counts: Record<ReviewSection | "documents" | "verified", number>;
  manualControls: string[];
}

const disallowedSensitivity = new Set(["legal", "demographic"]);

function sectionFor(answer: ApplicationPackageAnswer): ReviewSection {
  if (!answer.proposedValue.trim()) return "missing";
  if (disallowedSensitivity.has(answer.sensitivity)) return "manual";
  if (answer.requiresReview || answer.source === "ai_suggestion" || answer.confidence < 0.9) {
    return "review";
  }
  return "ready";
}

export function buildReviewPanelModel(
  applicationPackage: ApplicationPackagePayload | null,
  state: AssistedApplyTabState | null,
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
        liveAcceptance: accepted
          ? "accepted"
          : section === "manual"
            ? "manual"
            : section === "review"
              ? "needs_review"
              : "not_attempted",
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
  return {
    enabled,
    rows,
    counts: {
      ready: rows.ready.length,
      review: rows.review.length,
      missing: rows.missing.length,
      manual: rows.manual.length + manualControls.length,
      documents: applicationPackage?.documents.length ?? 0,
      verified,
    },
    manualControls,
  };
}
