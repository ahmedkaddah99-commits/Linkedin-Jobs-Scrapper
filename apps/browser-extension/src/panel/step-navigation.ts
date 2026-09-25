import { authorizeIntermediateActivation } from "@runr/ats-core";

type NavigationControl = HTMLButtonElement | HTMLInputElement;

export type IntermediateNavigationTarget = {
  stepper: HTMLOListElement;
  control: NavigationControl;
  currentStep: HTMLElement;
  nextStep: HTMLElement;
  currentStepLabel: string;
  nextStepLabel: string;
  currentIndex: number;
  stepLabels: string[];
};

export type IntermediateNavigationResult =
  | { status: "advanced"; nextStepLabel: string }
  | { status: "refused"; reason?: string }
  | { status: "unverified"; nextStepLabel: string };

type OrderedStepper = {
  stepper: HTMLOListElement;
  steps: HTMLElement[];
  labels: string[];
  activeIndex: number;
};

const TERMINAL_WORDING = /\b(?:apply|submit|finish|complete|final|finalize|finalise|register|create account)\b/iu;
const ADVANCE_WORDING = /\b(?:continue|next)\b/iu;
const TERMINAL_STATE_ATTRIBUTES = [
  "data-final-step",
  "data-terminal",
  "data-final-submit",
  "data-submit-application",
];
const STEP_TRANSITION_TIMEOUT_MS = 1_500;

function normalizedText(value: string | null | undefined): string {
  return (value || "").replace(/\s+/gu, " ").trim();
}

function isSetStateAttribute(element: Element): boolean {
  return TERMINAL_STATE_ATTRIBUTES.some((name) => {
    if (!element.hasAttribute(name)) return false;
    const value = normalizedText(element.getAttribute(name)).toLowerCase();
    return value !== "false" && value !== "0";
  });
}

function isHidden(element: Element, document: Document): boolean {
  let current: Element | null = element;
  while (current) {
    if (current.hasAttribute("hidden") || current.hasAttribute("inert") ||
        current.getAttribute("aria-hidden") === "true") return true;
    try {
      const style = document.defaultView?.getComputedStyle(current);
      if (style?.display === "none" || style?.visibility === "hidden" || style?.visibility === "collapse") return true;
    } catch {
      return true;
    }
    current = current.parentElement;
  }
  return false;
}

function isStepper(element: Element): element is HTMLOListElement {
  if (element.tagName !== "OL") return false;
  return element.classList.contains("application-stepper") ||
    element.hasAttribute("data-application-stepper") ||
    /\bstep\b/iu.test(element.getAttribute("aria-label") || "");
}

function orderedStepper(document: Document): OrderedStepper | null {
  const steppers = Array.from(document.querySelectorAll("ol")).filter(
    (element): element is HTMLOListElement => isStepper(element) && !isHidden(element, document),
  );
  if (steppers.length !== 1) return null;

  const stepper = steppers[0]!;
  const steps = Array.from(stepper.children).filter(
    (child): child is HTMLElement => child.tagName === "LI",
  );
  const labels = steps.map((step) => normalizedText(step.textContent));
  const activeIndexes = steps.flatMap((step, index) =>
    step.getAttribute("aria-current") === "step" ? [index] : [],
  );
  if (steps.length < 2 || labels.some((label) => !label) || activeIndexes.length !== 1) return null;
  const activeIndex = activeIndexes[0]!;
  if (activeIndex >= steps.length - 1) return null;
  if (isHidden(steps[activeIndex]!, document) || isHidden(steps[activeIndex + 1]!, document)) return null;
  return { stepper, steps, labels, activeIndex };
}

function controlDescription(control: NavigationControl): string {
  const inputValue = control instanceof HTMLInputElement ? control.value : "";
  return [
    control.getAttribute("aria-label"),
    control.getAttribute("title"),
    inputValue,
    control.textContent,
    control.id,
    control.getAttribute("name"),
    control.getAttribute("data-action"),
  ].map(normalizedText).filter(Boolean).join(" ");
}

function terminalStateApplies(element: Element, currentStep: HTMLElement, stepper: HTMLOListElement): boolean {
  const form = "form" in element ? (element as NavigationControl).form : null;
  for (const candidate of [element, currentStep, stepper, form]) {
    if (candidate && isSetStateAttribute(candidate)) return true;
  }
  return false;
}

function candidateControls(document: Document): NavigationControl[] {
  return Array.from(document.querySelectorAll("button, input[type='submit'], input[type='button']"))
    .filter((element): element is NavigationControl =>
      element instanceof HTMLButtonElement || element instanceof HTMLInputElement,
    )
    .filter((control) => {
      if (control.disabled || control.getAttribute("aria-disabled") === "true" || isHidden(control, document)) return false;
      const description = controlDescription(control);
      return ADVANCE_WORDING.test(description) || TERMINAL_WORDING.test(description) || isSetStateAttribute(control);
    });
}

function sameTarget(left: IntermediateNavigationTarget, right: IntermediateNavigationTarget): boolean {
  return left.stepper === right.stepper && left.control === right.control &&
    left.currentStep === right.currentStep && left.nextStep === right.nextStep &&
    left.currentIndex === right.currentIndex &&
    left.currentStepLabel === right.currentStepLabel && left.nextStepLabel === right.nextStepLabel &&
    left.stepLabels.length === right.stepLabels.length &&
    left.stepLabels.every((label, index) => label === right.stepLabels[index]);
}

export function findIntermediateNavigation(document: Document): IntermediateNavigationTarget | null {
  const state = orderedStepper(document);
  if (!state) return null;
  const currentStep = state.steps[state.activeIndex]!;
  const nextStep = state.steps[state.activeIndex + 1]!;
  const currentStepLabel = state.labels[state.activeIndex]!;
  const nextStepLabel = state.labels[state.activeIndex + 1]!;
  if (terminalStateApplies(currentStep, currentStep, state.stepper) || TERMINAL_WORDING.test(currentStepLabel)) return null;

  const candidates = candidateControls(document);
  if (candidates.length !== 1) return null;
  const control = candidates[0]!;
  const description = controlDescription(control);
  if (TERMINAL_WORDING.test(description) || terminalStateApplies(control, currentStep, state.stepper)) return null;
  if (!ADVANCE_WORDING.test(description) || !control.form) return null;

  return {
    stepper: state.stepper,
    control,
    currentStep,
    nextStep,
    currentStepLabel,
    nextStepLabel,
    currentIndex: state.activeIndex,
    stepLabels: state.labels,
  };
}

export async function advanceIntermediateStep(
  document: Document,
  expected?: IntermediateNavigationTarget,
): Promise<IntermediateNavigationResult> {
  const target = expected || findIntermediateNavigation(document);
  if (!target) return { status: "refused", reason: "No verified intermediate step is available." };
  const current = findIntermediateNavigation(document);
  if (!current || !sameTarget(target, current)) {
    return { status: "refused", reason: "The step or Continue control changed. Please review the page." };
  }

  const revoke = authorizeIntermediateActivation(document, target.control, () => {
    const latest = findIntermediateNavigation(document);
    return latest !== null && sameTarget(target, latest);
  });
  if (!revoke) return { status: "refused", reason: "The submission guard is unavailable or the step changed." };

  try {
    target.control.dispatchEvent(new MouseEvent("click", {
      bubbles: true,
      cancelable: true,
    }));
  } catch (error) {
    revoke();
    return {
      status: "refused",
      reason: error instanceof Error ? `The Continue control could not be activated: ${error.message}` : "The Continue control could not be activated.",
    };
  }
  revoke();

  const deadline = Date.now() + STEP_TRANSITION_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const latest = orderedStepper(document);
    if (latest && latest.labels.length === target.stepLabels.length &&
        latest.labels.every((label, index) => label === target.stepLabels[index]) &&
        latest.activeIndex === target.currentIndex + 1 &&
        latest.labels[latest.activeIndex] === target.nextStepLabel) {
      return { status: "advanced", nextStepLabel: target.nextStepLabel };
    }
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  return { status: "unverified", nextStepLabel: target.nextStepLabel };
}
