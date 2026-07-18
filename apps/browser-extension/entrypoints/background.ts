import { detectAtsFromUrl } from "@runr/ats-core";
import {
  isExactGreenhouseFixtureUrl,
  isExactLeverFixtureUrl,
  isFixtureInspectionMessage,
  isFixtureProofMessage,
  isPackageExecutionMessage,
  isDocumentUploadMessage,
  isPanelRequest,
  type ApplicationPackagePayload,
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
import { readTabPackage, readTabState, removeTabState, writeTabPackage, writeTabState } from "../src/state/tab-state";

const FIXTURE_EMAIL = "candidate@example.com";
const runtimeConfig = assistedApplyRuntimeConfig();
const authStorage = new BrowserAuthStorage();
const connectionService = new ExtensionConnectionService({
  identity: new BrowserIdentityPort(),
  api: new RunrAssistedApplyApi(runtimeConfig.apiBaseUrl),
  crypto: new BrowserCryptoPort(),
  storage: authStorage,
  clock: { now: () => Date.now() },
  frontendOrigin: runtimeConfig.frontendOrigin,
  extensionVersion: browser.runtime.getManifest().version,
});

function now(): string {
  return new Date().toISOString();
}

function isLocalFixtureUrl(url: string | undefined): boolean {
  return import.meta.env.MODE === "testing" &&
    (isExactGreenhouseFixtureUrl(url) || isExactLeverFixtureUrl(url));
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

async function runGreenhousePackage(applicationPackage: ApplicationPackagePayload) {
  const tab = await resolveTargetTab();
  if (tab?.id == null) throw new Error("No inspectable browser tab is active.");
  const detection = detectAtsFromUrl(tab.url || "");
  if (detection.ats !== "greenhouse" && !isLocalFixtureUrl(tab.url)) {
    throw new Error("This application package can only fill a detected Greenhouse page.");
  }
  if (applicationPackage.job.portal && applicationPackage.job.portal !== "greenhouse") {
    throw new Error("The bound application package is not for Greenhouse.");
  }
  await injectPageRunner(tab.id);
  const command: ContentRequest = {
    type: "CONTENT_RUN_GREENHOUSE_APPLICATION_PACKAGE",
    package: applicationPackage,
  };
  const raw: unknown = await browser.tabs.sendMessage(tab.id, command);
  if (!isPackageExecutionMessage(raw) || raw.packageId !== applicationPackage.packageId) {
    throw new Error("The Greenhouse runner returned an invalid package result.");
  }
  return raw;
}

async function runLeverPackage(applicationPackage: ApplicationPackagePayload) {
  const tab = await resolveTargetTab();
  if (tab?.id == null) throw new Error("No inspectable browser tab is active.");
  const detection = detectAtsFromUrl(tab.url || "");
  if (detection.ats !== "lever" && !isExactLeverFixtureUrl(tab.url)) {
    throw new Error("This application package can only fill a detected Lever page.");
  }
  if (applicationPackage.job.portal && applicationPackage.job.portal !== "lever") {
    throw new Error("The bound application package is not for Lever.");
  }
  await injectPageRunner(tab.id);
  const command: ContentRequest = { type: "CONTENT_RUN_LEVER_APPLICATION_PACKAGE", package: applicationPackage };
  const raw: unknown = await browser.tabs.sendMessage(tab.id, command);
  if (!isPackageExecutionMessage(raw) || raw.packageId !== applicationPackage.packageId) {
    throw new Error("The Lever runner returned an invalid package result.");
  }
  return raw;
}

async function fetchPackageFromApi(
  packageId: string,
): Promise<ApplicationPackagePayload> {
  const connection = await connectionService.getConnection();
  if (connection.status !== "connected" || !connection.session) {
    throw new Error("Connect the extension to Runr before fetching an application package.");
  }
  const api = new RunrAssistedApplyApi(runtimeConfig.apiBaseUrl);
  const sessionToken = await currentSessionToken();
  const response = await api.request(
    `/assisted-apply/extension/packages?package_id=${encodeURIComponent(packageId)}`,
    "GET",
    undefined,
    sessionToken,
  );
  if (!response || typeof response !== "object" || Array.isArray(response)) {
    throw new Error("Runr returned an invalid application package.");
  }
  return response as ApplicationPackagePayload;
}

async function bindPackageFromApi(
  bindingId: string,
): Promise<ApplicationPackagePayload> {
  const connection = await connectionService.getConnection();
  if (connection.status !== "connected" || !connection.session) {
    throw new Error("Connect the extension to Runr before binding an application package.");
  }
  const api = new RunrAssistedApplyApi(runtimeConfig.apiBaseUrl);
  const sessionToken = await currentSessionToken();
  const response = await api.request(
    "/assisted-apply/extension/packages/bind",
    "POST",
    { binding_id: bindingId },
    sessionToken,
  );
  if (!response || typeof response !== "object" || Array.isArray(response)) {
    throw new Error("Runr returned an invalid application package.");
  }
  return response as ApplicationPackagePayload;
}

async function currentSessionToken(): Promise<string> {
  const value = await authStorage.readSessionSecret();
  if (!value || typeof value !== "object" || Array.isArray(value) ||
      typeof (value as { sessionToken?: unknown }).sessionToken !== "string") {
    throw new Error("Connect the extension to Runr before using a document.");
  }
  return (value as { sessionToken: string }).sessionToken;
}

function parseDocumentGrant(value: unknown, expectedDocumentId: string) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Runr returned an invalid document grant.");
  }
  const record = value as Record<string, unknown>;
  const file = record.file;
  if (!file || typeof file !== "object" || Array.isArray(file)) {
    throw new Error("Runr returned invalid document metadata.");
  }
  const metadata = file as Record<string, unknown>;
  if (typeof record.grantToken !== "string" || record.grantToken.length < 20 ||
      metadata.documentId !== expectedDocumentId ||
      !Number.isInteger(metadata.documentVersion) || Number(metadata.documentVersion) < 1 ||
      typeof metadata.fileName !== "string" || !metadata.fileName.toLowerCase().endsWith(".pdf") ||
      metadata.mimeType !== "application/pdf" ||
      !Number.isInteger(metadata.size) || Number(metadata.size) < 1 || Number(metadata.size) > 10 * 1024 * 1024 ||
      typeof metadata.sha256Hex !== "string" || !/^[0-9a-f]{64}$/u.test(metadata.sha256Hex)) {
    throw new Error("Runr returned invalid document grant metadata.");
  }
  return {
    grantToken: record.grantToken,
    documentId: metadata.documentId as string,
    documentVersion: metadata.documentVersion as number,
    fileName: metadata.fileName as string,
    mimeType: "application/pdf" as const,
    size: metadata.size as number,
    sha256Hex: metadata.sha256Hex as string,
  };
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

async function uploadGreenhouseCv(applicationPackage: ApplicationPackagePayload, documentId: string) {
  const tab = await resolveTargetTab();
  if (tab?.id == null) throw new Error("No inspectable browser tab is active.");
  if (applicationPackage.job.portal !== "greenhouse") {
    throw new Error("The selected CV is not bound to a Greenhouse application.");
  }
  const selected = applicationPackage.documents.find((item) => item.documentId === documentId);
  if (!selected || selected.documentKind !== "cv" || selected.mimeType !== "application/pdf") {
    throw new Error("Select the fixed-version PDF CV from this application package.");
  }
  const sessionToken = await currentSessionToken();
  const api = new RunrAssistedApplyApi(runtimeConfig.apiBaseUrl);
  const grant = parseDocumentGrant(await api.request(
    "/assisted-apply/extension/document-grants",
    "POST",
    { package_id: applicationPackage.packageId, document_id: documentId },
    sessionToken,
  ), documentId);
  let bytes = await api.downloadDocument(sessionToken, grant.grantToken);
  try {
    if (bytes.byteLength !== grant.size) throw new Error("The downloaded CV size did not match its grant.");
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes.slice().buffer));
    const sha256Hex = Array.from(digest, (value) => value.toString(16).padStart(2, "0")).join("");
    digest.fill(0);
    if (sha256Hex !== grant.sha256Hex) throw new Error("The downloaded CV hash did not match its grant.");
    await injectPageRunner(tab.id);
    const command: ContentRequest = {
      type: "CONTENT_UPLOAD_GREENHOUSE_CV",
      packageId: applicationPackage.packageId,
      documentId: grant.documentId,
      documentVersion: grant.documentVersion,
      fileName: grant.fileName,
      mimeType: grant.mimeType,
      base64Bytes: bytesToBase64(bytes),
    };
    const result: unknown = await browser.tabs.sendMessage(tab.id, command);
    if (!isDocumentUploadMessage(result) || result.documentId !== grant.documentId ||
        result.documentVersion !== grant.documentVersion) {
      throw new Error("The Greenhouse runner returned an invalid document result.");
    }
    return result;
  } finally {
    bytes.fill(0);
    bytes = new Uint8Array();
  }
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
      if (message.type === "BIND_APPLICATION_PACKAGE") {
        const tab = await resolveTargetTab();
        if (tab?.id == null) throw new Error("No application tab is available for package binding.");
        const applicationPackage = await bindPackageFromApi(message.bindingId);
        const state = await getState(false);
        if (!state.ats || applicationPackage.job.portal !== state.ats) {
          throw new Error("The application package does not match the active supported portal.");
        }
        await writeTabPackage(tab.id, applicationPackage);
        return { ok: true, package: applicationPackage };
      }
      if (message.type === "GET_BOUND_APPLICATION_PACKAGE") {
        const tab = await resolveTargetTab();
        if (tab?.id == null) throw new Error("No application tab is active.");
        const applicationPackage = await readTabPackage(tab.id);
        if (!applicationPackage) throw new Error("No application package is bound to this tab.");
        return { ok: true, package: applicationPackage };
      }
      if (message.type === "REFETCH_APPLICATION_PACKAGE") {
        return { ok: true, package: await fetchPackageFromApi(message.packageId) };
      }
      if (message.type === "SAVE_APPLICATION_CORRECTION") {
        const connection = await connectionService.getConnection();
        if (connection.status !== "connected" || !connection.session) {
          throw new Error("Connect the extension to Runr before saving a correction.");
        }
        const api = new RunrAssistedApplyApi(runtimeConfig.apiBaseUrl);
        const sessionToken = await currentSessionToken();
        await api.request(
          "/assisted-apply/extension/corrections",
          "POST",
          {
            package_id: message.package.packageId,
            field_intent: message.fieldIntent,
            corrected_value: message.correctedValue,
            scope: message.scope,
          },
          sessionToken,
        );
        const tab = await resolveTargetTab();
        if (tab?.id == null) throw new Error("No application tab is active.");
        const updatedPackage: ApplicationPackagePayload = {
          ...message.package,
          answers: message.package.answers.map((answer) => answer.fieldIntent === message.fieldIntent
            ? {
                ...answer,
                proposedValue: message.correctedValue.trim(),
                source: "scoped_preference",
                scope: message.scope,
                reasons: [...answer.reasons, `explicit_user_correction:${message.scope}`],
              }
            : answer),
        };
        await writeTabPackage(tab.id, updatedPackage);
        return { ok: true, package: updatedPackage };
      }
      if (message.type === "UPLOAD_GREENHOUSE_CV") {
        return {
          ok: true,
          documentUpload: await uploadGreenhouseCv(message.package, message.documentId),
        };
      }
      if (message.type === "RUN_GREENHOUSE_APPLICATION_PACKAGE") {
        return { ok: true, packageExecution: await runGreenhousePackage(message.package) };
      }
      if (message.type === "RUN_LEVER_APPLICATION_PACKAGE") {
        return { ok: true, packageExecution: await runLeverPackage(message.package) };
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
