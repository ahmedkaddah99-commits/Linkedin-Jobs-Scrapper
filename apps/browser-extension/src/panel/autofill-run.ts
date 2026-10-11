import {
  executeAddRepeatedRow,
  executeEnhancedSelection,
  executeNativeValueAction,
  type DeclarativeAction,
  type NativeValueAction,
} from "@runr/ats-core/declarative-actions";
import {
  controlResolver,
  inspectApplicationForm,
  type GenericInspection,
} from "@runr/ats-core/generic-inspector";
import {
  planApplicationFill,
  type ApplicationFillPlan,
  type CandidateProfile,
  type FillPolicy,
} from "@runr/ats-core/generic-planner";
import type { DetectedApplicationField } from "@runr/ats-core/field-intent";

/**
 * One autofill pass: inspect, plan, execute, verify.
 *
 * Execution goes through the centralized executor, which writes the value,
 * emits the events frameworks listen for, and reads the value back. A field is
 * only reported filled when that readback agreed — a write that the page
 * rejected or rewrote is reported as needing review, never as done.
 */

export type RunStage = "detecting" | "filling" | "complete";

export type FieldOutcome = "filled" | "needs_review" | "manual" | "kept";

export interface FieldResult {
  fieldId: string;
  label: string;
  intent: string;
  outcome: FieldOutcome;
  reason?: string;
}

export interface AutofillRunState {
  stage: RunStage;
  detectedCount: number;
  results: FieldResult[];
  /** Populated once the run completes. */
  reviewCount: number;
  filledCount: number;
}

export interface AutofillRunOptions {
  document: Document;
  url: string;
  profile: CandidateProfile;
  policy: FillPolicy;
  onProgress?: (state: AutofillRunState) => void;
}

/** Groups repeated-section results the way the reference captures show them. */
export function summariseRepeats(fields: DetectedApplicationField[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const field of fields) {
    if (field.repeatIndex === undefined) continue;
    const kind = field.intent.split(".")[0]!;
    counts.set(kind, Math.max(counts.get(kind) ?? 0, field.repeatIndex + 1));
  }
  return counts;
}

function outcomeReason(outcome: FieldOutcome, reasons: string[]): string | undefined {
  const first = reasons.find((reason) => reason.trim().length > 0);
  if (outcome === "filled") return undefined;
  return first;
}

/**
 * Resolves a planner field id back to the live control.
 *
 * Ids are derived from the control's own id/name, so the mapping is rebuilt
 * from the inspection rather than assumed — a form that re-rendered between
 * inspection and execution simply fails to resolve, and the field is reported
 * for review instead of being written to the wrong control.
 */
function resolverFor(document: Document, inspection: GenericInspection): (fieldId: string) => Element | null {
  return controlResolver(document, inspection);
}

/** Upper bound on rows Runr will create, so a runaway page cannot be spammed. */
const MAX_CREATED_ROWS = 8;

/**
 * Adds repeated rows until each section can hold the profile.
 *
 * Only grows, never removes: a row the candidate added stays even when the
 * profile has fewer entries. Stops as soon as the page declines to add one.
 */
async function growRepeatedSections(
  document: Document,
  url: string,
  inspection: GenericInspection,
  profile: CandidateProfile,
): Promise<number> {
  const wanted: Array<{ kind: "experience" | "education"; needed: number }> = [
    { kind: "experience", needed: profile.workExperiences.length },
    { kind: "education", needed: profile.education.length },
  ];

  let created = 0;
  for (const { kind, needed } of wanted) {
    if (needed <= 1) continue;
    const section = inspection.sections.find((candidate) => candidate.kind === kind);
    if (!section) continue;

    for (let attempt = 0; attempt < MAX_CREATED_ROWS; attempt += 1) {
      const fresh = inspectApplicationForm({ document, url });
      const present = new Set(
        fresh.fields
          .filter((field) => field.intent.startsWith(`${kind}.`))
          .map((field) => field.repeatIndex ?? 0),
      ).size;
      if (present >= needed) break;

      const heading = Array.from(document.querySelectorAll<HTMLElement>("h1, h2, h3, h4, legend"))
        .find((element) => (element.textContent || "").replace(/\s+/gu, " ").trim() === section.heading);
      const root = heading?.parentElement ?? document.body;
      if (!root) break;

      const outcome = await executeAddRepeatedRow(document, root);
      if (outcome.status !== "applied") break;
      created += 1;
    }
  }
  return created;
}

export async function runAutofill(options: AutofillRunOptions): Promise<AutofillRunState> {
  const { document, url, profile, policy, onProgress } = options;

  const state: AutofillRunState = {
    stage: "detecting",
    detectedCount: 0,
    results: [],
    reviewCount: 0,
    filledCount: 0,
  };
  onProgress?.({ ...state, results: [...state.results] });

  const inspection = inspectApplicationForm({ document, url });
  state.detectedCount = inspection.fields.length;
  state.stage = "filling";
  onProgress?.({ ...state, results: [...state.results] });

  // Grow repeated sections to hold the profile before planning, so the extra
  // rows are inspected and filled in the same pass.
  const created = await growRepeatedSections(document, url, inspection, profile);
  const currentInspection = created > 0 ? inspectApplicationForm({ document, url }) : inspection;
  if (created > 0) {
    state.detectedCount = currentInspection.fields.length;
    onProgress?.({ ...state, results: [...state.results] });
  }

  const plan: ApplicationFillPlan = planApplicationFill(currentInspection, profile, policy);
  const resolve = resolverFor(document, currentInspection);
  const actionsByField = new Map(
    plan.actions
      .filter((action): action is Extract<DeclarativeAction, { fieldId: string }> => "fieldId" in action)
      .map((action) => [action.fieldId, action]),
  );

  for (const planned of plan.planned) {
    let outcome: FieldOutcome;
    let reasons = planned.reasons;

    if (planned.disposition === "manual") {
      outcome = "manual";
    } else if (planned.disposition === "skip") {
      outcome = "kept";
    } else if (planned.disposition === "review") {
      outcome = "needs_review";
    } else {
      const action = actionsByField.get(planned.fieldId);
      if (!action) {
        outcome = "needs_review";
        reasons = ["Runr could not operate this control."];
      } else if (action.type === "select_enhanced_options") {
        const execution = await executeEnhancedSelection(document, action, resolve);
        if (execution.status === "applied") {
          outcome = "filled";
        } else {
          outcome = "needs_review";
          reasons = [execution.rejected?.length
            ? `This control did not offer: ${execution.rejected.join(", ")}.`
            : execution.status === "rejected"
              ? "Runr will not operate this control."
              : "The page did not keep this selection."];
        }
      } else {
        const execution = executeNativeValueAction(document, action as NativeValueAction, resolve);
        if (execution.status === "applied") {
          outcome = "filled";
        } else {
          outcome = "needs_review";
          reasons = [execution.status === "rejected"
            ? "Runr will not operate this control."
            : "The page did not keep this value."];
        }
      }
    }

    state.results.push({
      fieldId: planned.fieldId,
      label: planned.label,
      intent: planned.intent,
      outcome,
      reason: outcomeReason(outcome, reasons),
    });
    onProgress?.({ ...state, results: [...state.results] });
  }

  // Anything the page hides from Runr is reported, never counted as handled.
  for (const item of inspection.unsupported) {
    state.results.push({
      fieldId: `unsupported-${item.reason}-${state.results.length}`,
      label: item.detail,
      intent: "unknown",
      outcome: "manual",
      reason: item.detail,
    });
  }

  state.filledCount = state.results.filter((result) => result.outcome === "filled").length;
  state.reviewCount = state.results.filter(
    (result) => result.outcome === "needs_review" || result.outcome === "manual",
  ).length;
  state.stage = "complete";
  onProgress?.({ ...state, results: [...state.results] });
  return state;
}
