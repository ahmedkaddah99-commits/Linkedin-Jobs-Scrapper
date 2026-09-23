import { createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import {
  classifyApplicationPage,
  extractApplicationJobContext,
  type ApplicationJobContext,
  type ApplicationPageDetection,
} from "@runr/ats-core/application-context";
import { isPanelResponse } from "@runr/extension-messages";
import { browser } from "wxt/browser";
import { defineUnlistedScript } from "wxt/utils/define-unlisted-script";
import AssistantPanel from "../src/panel/AssistantPanel";
import { runAutofill, type AutofillRunState } from "../src/panel/autofill-run";
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
  document.documentElement.style.marginRight = `${PANEL_WIDTH_PX}px`;

  handle = { host, root: createRoot(container), previousMarginRight };
  return handle;
}

function notify(type: string): void {
  void browser.runtime.sendMessage({ type }).catch(() => undefined);
}

let runState: AutofillRunState | null = null;
let busy = false;
let runError = "";
let candidateProfile: CandidateProfile | null = null;
let resumeMatch: ResumeMatch | null = null;
let completeness: ProfileCompleteness | null = null;

async function startAutofill(detection: ApplicationPageDetection, job: ApplicationJobContext | null): Promise<void> {
  if (busy) return;
  busy = true;
  runError = "";
  render(detection, job);

  try {
    const response: unknown = await browser.runtime.sendMessage({ type: "ASSISTED_APPLY_PANEL_PROFILE" });
    if (!isPanelResponse(response) || !response.ok || !response.profilePackage) {
      const detail = isPanelResponse(response) ? response.error : undefined;
      runError = detail === "not_connected"
        ? "Connect your Runr account to autofill this application."
        // Surface what actually went wrong rather than one catch-all message.
        : `Runr could not load your profile.${detail ? ` ${detail}` : ""}`;
      return;
    }
    const profile = toCandidateProfile(response.profilePackage);
    if (!profile) {
      runError = "Runr could not read your profile.";
      return;
    }
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

/**
 * Copies the profile as plain text.
 *
 * This is the fallback for pages Runr cannot fill: rather than a broken panel,
 * the candidate gets their own details in one paste.
 */
async function copyProfileToClipboard(): Promise<void> {
  if (!candidateProfile) return;
  const { contact, locations } = candidateProfile;
  const lines = [
    ["Name", [contact.firstName, contact.lastName].filter(Boolean).join(" ") || contact.fullName],
    ["Email", contact.email],
    ["Phone", contact.phone],
    ["City", locations.city],
    ["Country", locations.residenceCountry],
    ["Postal code", locations.postalCode],
    ["Current title", candidateProfile.preferences.currentTitle],
  ]
    .filter(([, value]) => Boolean(value))
    .map(([label, value]) => `${label}: ${value}`);
  try {
    await navigator.clipboard.writeText(lines.join("\n"));
  } catch {
    // Clipboard access can be denied; the panel simply does nothing.
  }
}

function render(detection: ApplicationPageDetection, job: ApplicationJobContext | null): void {
  const current = ensureHost();
  const origin = window.location.origin;
  current.root.render(
    createElement(AssistantPanel, {
      detection,
      job,
      collapsed,
      run: runState,
      busy,
      error: runError || undefined,
      resumeMatch,
      completeness,
      onTailorResume: () => notify("ASSISTED_APPLY_PANEL_TAILOR_RESUME"),
      onCopyProfile: () => void copyProfileToClipboard(),
      onCollapsedChange: (value: boolean) => {
        collapsed = value;
        document.documentElement.style.marginRight = value
          ? current.previousMarginRight
          : `${PANEL_WIDTH_PX}px`;
        writeCollapsed(origin, value);
        render(detection, job);
      },
      onPrimaryAction: () => void startAutofill(detection, job),
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
  render(detection, extractApplicationJobContext({ document, url }, detection, new Date().toISOString()));
}

declare global {
  interface Window {
    __runrAssistantPanelInstalled?: boolean;
  }
}

export default defineUnlistedScript(async () => {
  if (window.__runrAssistantPanelInstalled) return;
  window.__runrAssistantPanelInstalled = true;

  // Installed before anything else runs: every synthetic activation from this
  // point on is refused unless Runr explicitly authorized it.
  const initial = await bootstrap(window.location.origin);
  currentPreferences = initial.preferences;
  collapsed = initial.collapsed;

  evaluate();

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
