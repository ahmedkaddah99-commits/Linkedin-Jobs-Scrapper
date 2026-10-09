import type {
  PossibleSuccessEvidenceCategory,
  SupportedAts,
} from "@runr/extension-messages";

const FINAL_CONTROL_SELECTOR = 'button[type="submit"], input[type="submit"]';
const SUCCESS_SELECTORS: Record<SupportedAts, readonly string[]> = {
  greenhouse: [
    "#application_confirmation",
    ".application--success",
    '[data-qa="application-success"]',
    '[data-runr-application-success="true"]',
  ],
  lever: [
    ".application-confirmation",
    ".application-success",
    '[data-qa="application-success"]',
    '[data-runr-application-success="true"]',
  ],
};

export interface PossibleSuccessObserverOptions {
  document: Document;
  adapter: SupportedAts;
  initialUrl: string;
  onEvidence: (category: PossibleSuccessEvidenceCategory) => void;
  isUserInitiated?: (event: Event) => boolean;
}

export function classifyPossibleSuccess(
  document: Document,
  adapter: SupportedAts,
  initialUrl: string,
): PossibleSuccessEvidenceCategory | null {
  if (SUCCESS_SELECTORS[adapter].some((selector) => document.querySelector(selector))) {
    return "success_banner";
  }
  const current = new URL(document.location.href);
  const initial = new URL(initialUrl);
  if (/\/(?:confirmation|thanks|success)(?:\/|$)/iu.test(current.pathname)) {
    return "confirmation_page";
  }
  if (current.origin === initial.origin && current.href !== initial.href) {
    return "url_transition";
  }
  return null;
}

export function observePossibleSuccess(options: PossibleSuccessObserverOptions): () => void {
  const isUserInitiated = options.isUserInitiated ?? ((event: Event) => event.isTrusted);
  const initialEvidence = classifyPossibleSuccess(options.document, options.adapter, options.initialUrl);
  let armedAt = 0;
  let emitted = false;

  const inspect = () => {
    if (emitted || !armedAt || Date.now() - armedAt > 30_000) return;
    const category = classifyPossibleSuccess(options.document, options.adapter, options.initialUrl);
    if (!category || category === initialEvidence) return;
    emitted = true;
    options.onEvidence(category);
  };
  const onClick = (event: Event) => {
    const target = event.target;
    if (!(target instanceof Element) || !target.closest(FINAL_CONTROL_SELECTOR)) return;
    if (!isUserInitiated(event)) return;
    armedAt = Date.now();
    queueMicrotask(inspect);
  };
  const onFormAction = (event: Event) => {
    if (!armedAt || Date.now() - armedAt > 2_000) return;
    armedAt = Date.now();
    queueMicrotask(inspect);
  };
  const observer = new MutationObserver(inspect);
  options.document.addEventListener("click", onClick, true);
  options.document.addEventListener("submit", onFormAction, true);
  observer.observe(options.document.documentElement, { childList: true, subtree: true, attributes: true });
  return () => {
    options.document.removeEventListener("click", onClick, true);
    options.document.removeEventListener("submit", onFormAction, true);
    observer.disconnect();
  };
}
