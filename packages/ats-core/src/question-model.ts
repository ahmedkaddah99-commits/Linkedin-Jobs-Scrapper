import type { DetectedApplicationField } from "./field-intent";

/**
 * Application question model.
 *
 * Splits detected questions into the two groups the reference experience shows:
 * *common* questions that a reusable answer can serve, and *unique* questions
 * that are specific to this posting and need evidence before anything is
 * proposed.
 */

export type QuestionClass = "common" | "unique";

export type AiQuestionEligibility =
  | "eligible"
  | "requires_user_confirmation"
  | "manual_only"
  | "unsupported";

export interface ApplicationQuestion {
  fieldId: string;
  label: string;
  intent: string;
  controlType: string;
  questionClass: QuestionClass;
  eligibility: AiQuestionEligibility;
  /** Why this eligibility was chosen, shown when a question is held back. */
  reason: string;
  required: boolean;
  options?: Array<{ label: string; value: string }>;
}

/** Intents that a reusable, profile-backed answer can serve. */
const COMMON_INTENT_PREFIXES = [
  "contact.", "location.", "profile.", "experience.", "education.",
  "preference.", "consent.", "legal.work_authorization", "legal.sponsorship",
];

/** Categories Runr must never answer, however the question is phrased. */
const NEVER_ANSWER_INTENTS = new Set([
  "demographic.race", "demographic.veteran", "demographic.disability", "demographic.gender",
  "legal.declaration", "legal.terms", "assessment", "captcha", "credential.password",
]);

/**
 * Wording that signals a question asks for a claim about the candidate that
 * only they can make. These are held for confirmation even when they look
 * answerable, because a wrong answer here is a misrepresentation.
 */
const CLAIM_PATTERNS: ReadonlyArray<RegExp> = [
  /\bhow many years\b/iu,
  /\bdo you have\b/iu,
  /\bare you (?:willing|able|currently)\b/iu,
  /\bhave you ever\b/iu,
  /\bsalary|compensation|expected pay\b/iu,
  /\bnotice period\b/iu,
  /\bcertif(?:ied|ication)\b/iu,
  /\bclearance\b/iu,
];

export function classifyQuestion(field: DetectedApplicationField): ApplicationQuestion {
  const base = {
    fieldId: field.id,
    label: field.label,
    intent: field.intent,
    controlType: field.controlType,
    required: field.required,
    options: field.options,
  };

  if (NEVER_ANSWER_INTENTS.has(field.intent) || field.manualReason) {
    return {
      ...base,
      questionClass: "common",
      eligibility: "manual_only",
      reason: "Runr never answers this on your behalf.",
    };
  }

  const isCommon = COMMON_INTENT_PREFIXES.some(
    (prefix) => field.intent === prefix || field.intent.startsWith(prefix),
  );

  if (isCommon) {
    return {
      ...base,
      questionClass: "common",
      eligibility: field.sensitivity === "sensitive" ? "requires_user_confirmation" : "eligible",
      reason: field.sensitivity === "sensitive"
        ? "Confirm this answer before it is used."
        : "Your profile already answers this.",
    };
  }

  // Unique questions: specific to this posting.
  if (CLAIM_PATTERNS.some((pattern) => pattern.test(field.label))) {
    return {
      ...base,
      questionClass: "unique",
      eligibility: "requires_user_confirmation",
      reason: "This asks for a claim about you, so Runr will not answer it unreviewed.",
    };
  }

  if (field.controlType === "textarea" || field.controlType === "text") {
    return {
      ...base,
      questionClass: "unique",
      eligibility: "eligible",
      reason: "Runr can draft an answer from the job description and your profile.",
    };
  }

  if (["select", "combobox", "radio", "checkbox", "multiselect"].includes(field.controlType)) {
    return {
      ...base,
      questionClass: "unique",
      eligibility: "requires_user_confirmation",
      reason: "Runr will not pick between these options for you.",
    };
  }

  return {
    ...base,
    questionClass: "unique",
    eligibility: "unsupported",
    reason: "Runr cannot operate this kind of control.",
  };
}

export function partitionQuestions(fields: DetectedApplicationField[]): {
  common: ApplicationQuestion[];
  unique: ApplicationQuestion[];
} {
  const questions = fields.map(classifyQuestion);
  return {
    common: questions.filter((question) => question.questionClass === "common"),
    unique: questions.filter((question) => question.questionClass === "unique"),
  };
}

export type AnswerState = "proposed" | "edited" | "accepted" | "rejected";

export interface ProposedAnswer {
  fieldId: string;
  questionLabel: string;
  value: string;
  state: AnswerState;
  /** Set only when evidence was insufficient; the panel shows this instead of a draft. */
  insufficientEvidence?: boolean;
  sources: string[];
  regenerations: number;
}

/**
 * Decides whether there is enough evidence to draft an answer at all.
 *
 * Runr must never invent a qualification, so a question whose keywords appear
 * nowhere in the candidate's own material yields no draft ??? the panel shows
 * "needs your input" rather than a plausible fabrication.
 */
export function hasSufficientEvidence(questionLabel: string, candidateCorpus: string): boolean {
  const corpus = candidateCorpus.toLowerCase();
  const terms = questionLabel
    .toLowerCase()
    .replace(/[^a-z0-9 ]/gu, " ")
    .split(/\s+/u)
    .filter((term) => term.length > 4);
  if (terms.length === 0) return false;
  const hits = terms.filter((term) => corpus.includes(term)).length;
  return hits / terms.length >= 0.34;
}

/** Applies a review decision to a proposed answer. */
export function applyAnswerDecision(
  answer: ProposedAnswer,
  decision: { type: "edit"; value: string } | { type: "accept" } | { type: "reject" } | { type: "regenerate"; value: string },
): ProposedAnswer {
  switch (decision.type) {
    case "edit":
      return { ...answer, value: decision.value, state: "edited" };
    case "accept":
      return { ...answer, state: "accepted" };
    case "reject":
      return { ...answer, state: "rejected", value: "" };
    case "regenerate":
      return { ...answer, value: decision.value, state: "proposed", regenerations: answer.regenerations + 1 };
  }
}

/**
 * Whether a saved answer may be reused for a question.
 *
 * Reuse is scoped to the exact question or a demonstrably equivalent one:
 * normalised label equality. Anything looser risks pasting an answer about one
 * employer into a question about another.
 */
export function canReuseAnswer(savedQuestionLabel: string, incomingQuestionLabel: string): boolean {
  const normalize = (value: string) =>
    value.toLowerCase().replace(/[^a-z0-9 ]/gu, " ").replace(/\s+/gu, " ").trim();
  const saved = normalize(savedQuestionLabel);
  const incoming = normalize(incomingQuestionLabel);
  return saved.length > 0 && saved === incoming;
}
