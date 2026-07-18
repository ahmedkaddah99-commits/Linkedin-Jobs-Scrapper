import { detectAtsFromUrl } from "@runr/ats-core";
import {
  isExactGreenhouseFixtureUrl,
  isFixtureInspectionMessage,
  isFixtureProofMessage,
  isPanelRequest,
  type AssistedApplyTabState,
  type ContentRequest,
  type FixtureInspectionMessage,
  type PanelResponse,
} from "@runr/extension-messages";
import { browser, type Browser } from "wxt/browser";
import { defineBackground } from "wxt/utils/define-background";
import {
  BrowserAuthStorage,
  BrowserCryptoPort,
  BrowserIdentityPort,
  RunrAssistedApplyApi,
} from "../src/auth/browser-ports";
import { ExtensionConnectionService } from "../src/auth/connection-service";
import { assistedApplyRuntimeConfig } from "../src/auth/config";
import { isExactSidePanelSender } from "../src/auth/trusted-sender";
import { readTabState, removeTabState, writeTabState } from "../src/state/tab-state";

const FIXTURE_EMAIL = "candidate@example.com";
const runtimeConfig = assistedApplyRuntimeConfig();
const connectionService = new ExtensionConnectionService({
  identity: new BrowserIdentityPort(),
  api: new RunrAssistedApplyApi(runtimeConfig.apiBaseUrl),
  crypto: new BrowserCryptoPort(),
  storage: new BrowserAuthStorage(),
  clock: { now: () => Date.now() },
  frontendOrigin: runtimeConfig.frontendOrigin,
  extensionVersion: browser.runtime.getManifest().version,
});

function now(): string {
  return new Date().toISOString();
}

function isLocalFixtureUrl(url: string | undefined): boolean {
  return import.meta.env.MODE === "testing" && isExactGreenhouseFixtureUrl(url);
}

async function resolveTargetTab(): Promise<Browser.tabs.Tab | null> {
  const [active] = await browser.tabs.query({ active: true, currentWindow: true });
  if (active?.id != null && active.url && !active.url.startsWith("chrome-extension://")) {
    return active;
  }

  if (import.meta.env.MODE === "testing") {
    const tabs = await browser.tabs.query({});
    return tabs.find((tab) => isLocalFixtureUrl(tab.url)) ?? null;
  }
  return active?.id != null ? active : null;
}

async function injectPageRunner(tabId: number): Promise<FixtureInspectionMessage> {
  const results = await browser.scripting.executeScript({
    target: { tabId },
    files: ["/application-form.js"],
  });
  const inspection: unknown = results[0]?.result;
  if (!isFixtureInspectionMessage(inspection)) {
    throw new Error("The page runner returned an invalid inspection result.");
  }
  return inspection;
}

function baseState(tab: Browser.tabs.Tab): AssistedApplyTabState {
  const url = tab.url || "";
  const detection = detectAtsFromUrl(url);
  return {
    tabId: tab.id as number,
    url,
    ats: detection.ats,
    status: detection.detected ? "recognized" : "unsupported",
    fixtureAvailable: false,
    fieldCount: 0,
    manualReasons: [],
    execution: null,
    updatedAt: now(),
  };
}

async function refreshTabState(tab: Browser.tabs.Tab): Promise<AssistedApplyTabState> {
  if (tab.id == null) throw new Error("The active tab has no identifier.");
  let state = baseState(tab);
  if (!state.ats && !isLocalFixtureUrl(tab.url)) {
    await writeTabState(state);
    return state;
  }

  try {
    const inspection = await injectPageRunner(tab.id);
    state = {
      ...state,
      ats: inspection.ats,
      status: inspection.fixtureAvailable ? "fixture_ready" : "recognized",
      fixtureAvailable: inspection.fixtureAvailable,
      fieldCount: inspection.fieldCount,
      manualReasons: inspection.manualReasons,
      updatedAt: now(),
    };
  } catch {
    state = {
      ...state,
      status: state.ats ? "recognized" : "error",
      errorCode: state.ats ? "permission_required" : "page_unavailable",
      updatedAt: now(),
    };
    console.warn("Runr Assisted Apply could not inspect the tab.");
  }
  await writeTabState(state);
  return state;
}

async function getState(refresh: boolean): Promise<AssistedApplyTabState> {
  const tab = await resolveTargetTab();
  if (tab?.id == null) throw new Error("No inspectable browser tab is active.");
  if (!refresh) {
    const stored = await readTabState(tab.id);
    if (stored && stored.url === (tab.url || "")) return stored;
  }
  return refreshTabState(tab);
}

async function runFixtureProof(): Promise<AssistedApplyTabState> {
  if (import.meta.env.MODE !== "testing") {
    throw new Error("Fixture execution is not included in production builds.");
  }
  const tab = await resolveTargetTab();
  if (tab?.id == null) throw new Error("No inspectable browser tab is active.");
  const current = await readTabState(tab.id) ?? (await refreshTabState(tab));
  const liveUrl = tab.url || "";
  if (
    !isLocalFixtureUrl(liveUrl) ||
    current.url !== liveUrl ||
    !current.fixtureAvailable
  ) {
    throw new Error("Fixture execution is allowed only on the explicit local Greenhouse fixture.");
  }

  await injectPageRunner(tab.id);
  const command: ContentRequest = {
    type: "CONTENT_RUN_GREENHOUSE_FIXTURE_PROOF",
    proposedEmail: FIXTURE_EMAIL,
  };
  const result: unknown = await browser.tabs.sendMessage(tab.id, command);
  if (!isFixtureProofMessage(result) || !result.execution) {
    throw new Error("No verified email match was executable on the fixture.");
  }

  const state: AssistedApplyTabState = {
    ...current,
    ats: result.ats,
    status: "fixture_verified",
    fixtureAvailable: result.fixtureAvailable,
    fieldCount: result.fieldCount,
    manualReasons: result.manualReasons,
    execution: {
      fieldLabel: result.execution.fieldLabel,
      status: result.execution.status,
      acceptedValue: result.execution.acceptedValue,
      reasons: result.execution.reasons,
    },
    errorCode: undefined,
    updatedAt: now(),
  };
  await writeTabState(state);
  return state;
}

export default defineBackground(() => {
  void connectionService.initialize().catch(() => {
    console.warn("Runr Assisted Apply could not restrict extension storage access.");
  });

  browser.action.onClicked.addListener(async (tab) => {
    if (tab.id == null) return;
    const state = await refreshTabState(tab);
    const enabled = state.ats !== null;
    await browser.sidePanel.setOptions({ tabId: tab.id, path: "sidepanel.html", enabled });
    if (enabled) await browser.sidePanel.open({ tabId: tab.id });
  });

  browser.runtime.onMessage.addListener(async (
    message: unknown,
    sender,
  ): Promise<PanelResponse | undefined> => {
    if (
      !isExactSidePanelSender(
        sender,
        browser.runtime.id,
        browser.runtime.getURL("/sidepanel.html"),
      )
    ) {
      return undefined;
    }
    if (!isPanelRequest(message)) return undefined;
    try {
      if (message.type === "GET_EXTENSION_CONNECTION") {
        return { ok: true, connection: await connectionService.getConnection() };
      }
      if (message.type === "CONNECT_RUNR") {
        return { ok: true, connection: await connectionService.connect() };
      }
      if (message.type === "DISCONNECT_RUNR") {
        return { ok: true, connection: await connectionService.disconnect() };
      }
      if (message.type === "UPDATE_ASSISTED_APPLY_PREFERENCES") {
        return {
          ok: true,
          connection: await connectionService.updatePreferences({
            permitSensitiveAutofill: message.permitSensitiveAutofill,
            permitDemographicAutofill: message.permitDemographicAutofill,
          }),
        };
      }
      const state =
        message.type === "RUN_GREENHOUSE_FIXTURE_PROOF"
          ? await runFixtureProof()
          : await getState(message.type === "REFRESH_ACTIVE_TAB_STATE");
      return { ok: true, state };
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : String(error) };
    }
  });

  browser.tabs.onRemoved.addListener((tabId) => {
    void removeTabState(tabId);
  });
});
