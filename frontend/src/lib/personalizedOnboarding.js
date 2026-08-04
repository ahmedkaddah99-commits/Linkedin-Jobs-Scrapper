export const ONBOARDING_STEPS = Object.freeze([
  { id: "goals", label: "Job goals", shortLabel: "Goals" },
  { id: "cv", label: "Main CV", shortLabel: "CV" },
  { id: "eligibility", label: "Eligibility", shortLabel: "Eligibility" },
  { id: "answers", label: "Application answers", shortLabel: "Answers" },
  { id: "reveal", label: "Your results", shortLabel: "Results" },
]);

export function getNextOnboardingStep(step) {
  return Math.min(ONBOARDING_STEPS.length - 1, Number(step || 0) + 1);
}

export function getPreviousOnboardingStep(step) {
  return Math.max(0, Number(step || 0) - 1);
}

