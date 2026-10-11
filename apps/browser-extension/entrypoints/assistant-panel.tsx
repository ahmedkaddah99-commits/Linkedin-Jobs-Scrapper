import { createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import {
  classifyApplicationPage,
  extractApplicationJobContext,
  type ApplicationJobContext,
  type ApplicationPageDetection,
} from "@runr/ats-core/application-context";
import { installSubmissionGuard } from "@runr/ats-core";
import { isPanelResponse, type ApplicationPackagePayload } from "@runr/extension-messages";
import { inspectApplicationForm, controlResolver } from "@runr/ats-core/generic-inspector";
import { profileDetails, type ProfileDetail } from "../src/panel/profile-details";
import { attachDocument, type DocumentRole } from "@runr/ats-core/generic-upload";
import { browser } from "wxt/browser";
import { defineUnlistedScript } from "wxt/utils/define-unlisted-script";
import AssistantPanel from "../src/panel/AssistantPanel";
import { runAutofill, type AutofillRunState } from "../src/panel/autofill-run";
import { advanceIntermediateStep, findIntermediateNavigation } from "../src/panel/step-navigation";
import { computeResumeMatch, profileCompleteness, type ProfileCompleteness, type ResumeMatch } from "@runr/ats-core/resume-match";
import type { CandidateProfile } from "@runr/ats-core/generic-planner";
import { toCandidateProfile } from "../src/panel/profile-package";
import { isExcludedPanelUrl } from "../src/panel/script-registration";
import { PANEL_CSS, PANEL_WIDTH_PX } from "../src/panel/panel-styles";
import {
  DEFAULT_PANEL_MOUNT_PREFERENCES,
  shouldMountPanel,
  type PanelMountPreferences,
} from "../src/panel/mount-decision";

/**
 * The in-page assistant panel.
 *
 * Built as an unlisted script and registered at runtime with
 * `scripting.registerContentScripts` rather than declared in the manifest. That
 * keeps registration reconciled against the origins actually granted, and keeps
 * `verify-manifest.mjs`'s "no declared content scripts" assertion true — see
 * `src/panel/script-registration.ts`.
 */

const HOST_TAG = "runr-assisted-apply-panel";
const REEVALUATE_DEBOUNCE_MS = 250;
const URL_POLL_MS = 500;
function pageMargin(): string { return window.innerWidth <= 600 ? "0px" : `${PANEL_WIDTH_PX}px`; }

interface PanelHandle {
  host: HTMLElement;
  root: Root;
  previousMarginRight: string;
}

type PanelBootstrapResponse = {
  ok: true;
  panelBootstrap: {
    autoOpenOnApplicationPage: boolean;
    collapsed: boolean;
  };
};

let handle: PanelHandle | null = null;
let collapsed = false;
let lastSignature = "";
let currentPreferences: PanelMountPreferences = DEFAULT_PANEL_MOUNT_PREFERENCES;

/**
 * Reads preferences and collapse state through the service worker. Extension
 * storage is restricted to trusted contexts, so a content script that reads it
 * directly always fails and silently falls back to defaults — which would mean
 * ignoring a user who turned automatic display off.
 */
async function bootstrap(origin: string): Promise<{ preferences: PanelMountPreferences; collapsed: boolean }> {
  const fallback = { preferences: DEFAULT_PANEL_MOUNT_PREFERENCES, collapsed: false };
  try {
    const response: unknown = await browser.runtime.sendMessage({
      type: "ASSISTED_APPLY_PANEL_BOOTSTRAP",
      origin,
    });
    if (!response || typeof response !== "object" ||
        (response as { ok?: unknown }).ok !== true ||
        !(response as Partial<PanelBootstrapResponse>).panelBootstrap) return fallback;
    const bootstrap = (response as PanelBootstrapResponse).panelBootstrap;
    return {
      preferences: { autoOpenOnApplicationPage: bootstrap.autoOpenOnApplicationPage },
      collapsed: bootstrap.collapsed,
    };
  } catch {
    return fallback;
  }
}

function writeCollapsed(origin: string, collapsed: boolean): void {
  void browser.runtime
    .sendMessage({ type: "ASSISTED_APPLY_PANEL_SET_COLLAPSED", origin, collapsed })
    .catch(() => undefined);
}

function unmountPanel(): void {
  if (!handle) return;
  const current = handle;
  handle = null;
  current.root.unmount();
  current.host.remove();
  document.documentElement.style.marginRight = current.previousMarginRight;
}

function ensureHost(): PanelHandle {
  if (handle) return handle;
  const host = document.createElement(HOST_TAG);
  host.setAttribute("data-runr-assisted-apply", "panel");
  const shadow = host.attachShadow({ mode: "open" });
  const style = document.createElement("style");
  style.textContent = PANEL_CSS;
  const container = document.createElement("div");
  shadow.append(style, container);
  document.documentElement.append(host);

  // Reflow the page the way a browser side panel does, remembering the previous
  // inline value so unmounting leaves the page exactly as it was found.
  const previousMarginRight = document.documentElement.style.marginRight;
  document.documentElement.style.marginRight = pageMargin();

  handle = { host, root: createRoot(container), previousMarginRight };
  return handle;
}

function notify(type: string): void {
  void browser.runtime.sendMessage({ type }).catch(() => undefined);
}

let runState: AutofillRunState | null = null;
let busy = false;
let runError = "";
let navigationBusy = false;
let navigationMessage = "";
let candidateProfile: CandidateProfile | null = null;
let resumeMatch: ResumeMatch | null = null;
let completeness: ProfileCompleteness | null = null;
let profileLoading = false;
let profileError = "";
let applicationPackage: ApplicationPackagePayload | null = null;
let requestedProfileUrl = "";
let profileRequest: Promise<boolean> | null = null;
let savedAnswers: ProfileDetail[] = [];
let manualJobDescription = "";

function renderCurrent(): void {
  if (!handle) return;
  const url = window.location.href;
  const detection = classifyApplicationPage({ document, url });
  const job = extractApplicationJobContext({ document, url }, detection, new Date().toISOString());
  resumeMatch = candidateProfile && job?.description ? computeResumeMatch(job.description, candidateProfile) : null;
  render(detection, job);
}

function loadProfile(): Promise<boolean> {
  if (profileRequest) return profileRequest;
  profileLoading = true;
  profileError = "";
  renderCurrent();
  profileRequest = (async () => {
    try {
      const response: unknown = await browser.runtime.sendMessage({ type: "ASSISTED_APPLY_PANEL_PROFILE" });
      const profile = isPanelResponse(response) && response.ok ? toCandidateProfile(response.profilePackage) : null;
      if (!profile) {
        candidateProfile = null;
        savedAnswers = [];
        completeness = null;
        resumeMatch = null;
        profileError = isPanelResponse(response) && response.error === "not_connected"
          ? "Connect Runr to use your saved details."
          : "Couldn't load your profile. Try refreshing it.";
        return false;
      }
      candidateProfile = profile;
      savedAnswers = isPanelResponse(response) && response.profilePackage ? response.profilePackage.answers
        .filter((answer) => Boolean(answer.proposed_value.trim()))
        .map((answer) => ({ section: "Saved answer", label: answer.label, value: answer.proposed_value })) : [];
      completeness = profileCompleteness(profile);
      return true;
    } catch {
      candidateProfile = null;
      savedAnswers = [];
      completeness = null;
      resumeMatch = null;
      profileError = "Couldn't load your profile. Try refreshing it.";
      return false;
    } finally {
      profileLoading = false;
      profileRequest = null;
      renderCurrent();
    }
  })();
  return profileRequest;
}

async function loadApplicationPackage(): Promise<void> {
  const url = window.location.href;
  try {
    const response: unknown = await browser.runtime.sendMessage({ type: "ASSISTED_APPLY_PANEL_PACKAGE" });
    if (url !== window.location.href) return;
    applicationPackage = isPanelResponse(response) && response.ok ? response.package ?? null : null;
  } catch { applicationPackage = null; }
  renderCurrent();
}

async function startAutofill(detection: ApplicationPageDetection, job: ApplicationJobContext | null): Promise<void> {
  if (busy || navigationBusy) return;
  busy = true;
  const applicationUrl = window.location.href;
  runError = "";
  navigationMessage = "";
  render(detection, job);

  try {
    if (!await loadProfile() || !candidateProfile) {
      runError = profileError;
      return;
    }
    const profile = candidateProfile;
    if (window.location.href !== applicationUrl) { runError = "The application page changed. Autofill this page again."; return; }
    candidateProfile = profile;
    completeness = profileCompleteness(profile);
    // Scoring needs the posting text; application steps rarely carry it, so the
    // Resume Score tab stays empty rather than showing a meaningless number.
    resumeMatch = job?.description ? computeResumeMatch(job.description, profile) : null;

    await runAutofill({
      document,
      url: window.location.href,
      profile,
      policy: { preserveExistingValues: true, permitSensitiveAutofill: false },
      onProgress: (state) => {
        runState = state;
        render(detection, job);
      },
    });
  } catch (error) {
    runError = error instanceof Error ? error.message : "Runr could not complete the autofill.";
  } finally {
    busy = false;
    render(detection, job);
  }
}

async function continueToNextStep(detection: ApplicationPageDetection, job: ApplicationJobContext | null): Promise<void> {
  if (busy || navigationBusy) return;
  const target = findIntermediateNavigation(document);
  if (!target) {
    navigationMessage = "Runr could not verify an intermediate step. Continue manually after reviewing the page.";
    render(detection, job);
    return;
  }

  navigationBusy = true;
  navigationMessage = "";
  render(detection, job);
  try {
    const result = await advanceIntermediateStep(document, target);
    if (result.status === "advanced") {
      runState = null;
      runError = "";
      navigationMessage = `Advanced to ${result.nextStepLabel}. Autofill the next step when you are ready.`;
    } else if (result.status === "unverified") {
      navigationMessage = `Continue was activated, but Runr could not verify ${result.nextStepLabel}. Review the page and continue manually.`;
    } else {
      navigationMessage = "Review this page, then continue on the application form.";
    }
  } catch {
    navigationMessage = "Runr could not verify the next step. Review the page and continue manually.";
  } finally {
    navigationBusy = false;
    render(detection, job);
  }
}

/**
 * Copies the profile as plain text.
 *
 * This is the fallback for pages Runr cannot fill: rather than a broken panel,
 * the candidate gets their own details in one paste.
 */
async function copyProfileToClipboard(): Promise<void> {
  if (!candidateProfile) return;
  const lines = profileDetails(candidateProfile).map((row) => `${row.section} · ${row.label}: ${row.value}`);
  try {
    await navigator.clipboard.writeText(lines.join("\n"));
  } catch {
    runError = "Couldn't copy your profile. Copy individual details from the Profile tab.";
    renderCurrent();
  }
}

function render(detection: ApplicationPageDetection, job: ApplicationJobContext | null): void {
  const current = ensureHost();
  const origin = window.location.origin;
  const description = job?.description || manualJobDescription;
  resumeMatch = candidateProfile && description ? computeResumeMatch(description, candidateProfile) : null;
  current.root.render(
    createElement(AssistantPanel, {
      detection,
      job,
      collapsed,
      run: runState,
      busy,
      error: runError || undefined,
      canContinueToNextStep: runState?.stage === "complete" && findIntermediateNavigation(document) !== null,
      continuingToNextStep: navigationBusy,
      navigationMessage: navigationMessage || undefined,
      resumeMatch,
      completeness,
      profile: candidateProfile,
      profileLoading,
      profileError,
      applicationPackage,
      savedAnswers,
      onScoreDescription: (description: string) => { manualJobDescription = description.slice(0, 50000).trim(); renderCurrent(); },
      onAttachLocalDocument: async (role: DocumentRole, file: File, replace: boolean) => {
        if (file.size > 20 * 1024 * 1024) return "Choose a file smaller than 20 MB.";
        if (!/\.(pdf|docx)$/iu.test(file.name)) return "Choose a PDF or Word (.docx) file.";
        const applicationUrl = window.location.href;
        const bytes = new Uint8Array(await file.arrayBuffer());
        if (window.location.href !== applicationUrl) return "The application page changed. Choose the file again on this page.";
        const inspection = inspectApplicationForm({ document, url: window.location.href });
        const outcome = attachDocument(document, inspection, { role, fileName: file.name,
          mimeType: file.type || (file.name.toLowerCase().endsWith(".pdf") ? "application/pdf" : "application/vnd.openxmlformats-officedocument.wordprocessingml.document"), bytes }, { preserveExisting: !replace });
        if (outcome.status === "uploaded") return `${file.name} attached. Check the upload on the application form.`;
        if (outcome.status === "preserved_existing") return "A file is already attached. Select Replace to use this version.";
        if (outcome.status === "ambiguous") return "More than one upload field matches. Choose the field on the application form.";
        return "Couldn't attach this file here. Upload it on the application form.";
      },
      onRefreshProfile: () => { void loadProfile(); void loadApplicationPackage(); },
      onOpenDocuments: () => notify("ASSISTED_APPLY_PANEL_DOCUMENTS"),
      onEditProfile: () => notify("ASSISTED_APPLY_PANEL_EDIT_PROFILE"),
      onOpenTracker: () => notify("ASSISTED_APPLY_PANEL_TRACKER"),
      onReviewDocuments: () => notify("ASSISTED_APPLY_PANEL_OPEN_SETTINGS"),
      onFocusField: (fieldId: string) => {
        const inspection = inspectApplicationForm({ document, url: window.location.href });
        const element = controlResolver(document, inspection)(fieldId);
        if (element instanceof HTMLElement) {
          element.scrollIntoView({ behavior: "smooth", block: "center" });
          element.focus({ preventScroll: true });
        } else { runError = "This field has changed. Autofill again to refresh the review list."; renderCurrent(); }
      },
      onTailorResume: () => notify("ASSISTED_APPLY_PANEL_TAILOR_RESUME"),
      onCopyProfile: () => void copyProfileToClipboard(),
      onCollapsedChange: (value: boolean) => {
        collapsed = value;
        document.documentElement.style.marginRight = value
          ? current.previousMarginRight
          : pageMargin();
        writeCollapsed(origin, value);
        render(detection, job);
      },
      onPrimaryAction: () => void startAutofill(detection, job),
      onContinueToNextStep: () => void continueToNextStep(detection, job),
      onOpenSettings: () => notify("ASSISTED_APPLY_PANEL_OPEN_SETTINGS"),
      onReport: () => notify("ASSISTED_APPLY_PANEL_REPORT"),
    }),
  );
}

function evaluate(): void {
  const url = window.location.href;
  // Broad host access means this script also loads on Runr's own web surfaces.
  // The panel must never mount there.
  if (isExcludedPanelUrl(url)) {
    unmountPanel();
    return;
  }
  const detection = classifyApplicationPage({ document, url });
  const decision = shouldMountPanel(detection, currentPreferences);

  const signature = `${url}|${detection.kind}|${detection.fillableFieldCount}|${decision.mount}`;
  if (signature === lastSignature) return;
  lastSignature = signature;

  void browser.runtime
    .sendMessage({
      type: "ASSISTED_APPLY_PAGE_DETECTED",
      detection: {
        kind: detection.kind,
        provider: detection.provider,
        confidence: detection.confidence,
        fillableFieldCount: detection.fillableFieldCount,
      },
      url,
    })
    .catch(() => undefined);

  // Autofill can turn previously empty controls into non-fillable values. Keep
  // the review surface mounted for the current application context so the
  // completed/applied/review results remain visible after the write.
  const keepMounted = Boolean(
    handle && detection.kind !== "job_detail" && detection.kind !== "application_gateway",
  );
  if (!decision.mount && !keepMounted) {
    unmountPanel();
    return;
  }
  if (!decision.mount) return;
  if (requestedProfileUrl !== url) {
    requestedProfileUrl = url;
    manualJobDescription = "";
    applicationPackage = null;
    runState = null;
    runError = "";
    navigationMessage = "";
    render(detection, extractApplicationJobContext({ document, url }, detection, new Date().toISOString()));
    void loadProfile();
    void loadApplicationPackage();
  } else render(detection, extractApplicationJobContext({ document, url }, detection, new Date().toISOString()));
}

declare global {
  interface Window {
    __runrAssistantPanelInstalled?: boolean;
  }
}

export default defineUnlistedScript(async () => {
  if (window.__runrAssistantPanelInstalled) return;
  window.__runrAssistantPanelInstalled = true;

  // The panel is independently runtime-registered, so it must install the L3
  // guard itself instead of assuming the side-panel form runner was injected.
  const submissionGuard = installSubmissionGuard(document);
  void submissionGuard;

  // Installed before anything else runs: every synthetic activation from this
  // point on is refused unless Runr explicitly authorized it.
  const initial = await bootstrap(window.location.origin);
  currentPreferences = initial.preferences;
  collapsed = initial.collapsed;

  evaluate();
  window.addEventListener("focus", () => {
    if (handle && !busy) { void loadProfile(); void loadApplicationPackage(); }
  });
  window.addEventListener("resize", () => {
    if (handle && !collapsed) document.documentElement.style.marginRight = pageMargin();
  });

  // Application forms render late, grow as repeater rows are added, and move
  // between steps without a full navigation. Re-evaluate on all three.
  let timer: number | undefined;
  const scheduleEvaluate = () => {
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(evaluate, REEVALUATE_DEBOUNCE_MS);
  };

  new MutationObserver(scheduleEvaluate).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
  window.addEventListener("popstate", scheduleEvaluate);
  window.addEventListener("hashchange", scheduleEvaluate);

  let lastUrl = window.location.href;
  window.setInterval(() => {
    if (window.location.href !== lastUrl) {
      lastUrl = window.location.href;
      scheduleEvaluate();
    }
  }, URL_POLL_MS);
});
