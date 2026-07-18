import { detectAtsFromUrl } from "@runr/ats-core";
import {
  isExactGreenhouseFixtureUrl,
  isExactLeverFixtureUrl,
  isFixtureInspectionMessage,
  isPackageExecutionMessage,
  isDocumentUploadMessage,
  isContentRuntimeEvent,
  isPanelRequest,
  isTrackerConfirmationResult,
  type ApplicationPackagePayload,
  type ApplicationPackageDocumentMeta,
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
import {
  hasAllOptionalHostPermissions,
  hasPortalPermission,
  requestPortalPermission,
  requestAllOptionalHostPermissions,
  missingPortalPermissions,
} from "../src/permissions/host-permissions";
import {
  clearPendingConfirmation,
  readPendingConfirmation,
  readTabPackage,
  readTabState,
  readUploadedDocuments,
  recordUploadedDocument,
  removeTabState,
  writePendingConfirmation,
  writeTabPackage,
  writeTabState,
} from "../src/state/tab-state";

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

async function injectPageRunner(tabId: number, installControlledBridge = false): Promise<FixtureInspectionMessage> {
  if (installControlledBridge) {
    await browser.scripting.executeScript({
      target: { tabId },
      files: ["/controlled-field-bridge.js"],
      world: "MAIN",
    });
  }
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

async function runGreenhousePackage(applicationPackage: ApplicationPackagePayload, replaceFieldIntents: string[] = []) {
  const tab = await resolveTargetTab();
  if (tab?.id == null) throw new Error("No inspectable browser tab is active.");
  const detection = detectAtsFromUrl(tab.url || "");
  if (detection.ats !== "greenhouse" && !isLocalFixtureUrl(tab.url)) {
    throw new Error("This application package can only fill a detected Greenhouse page.");
  }
  if (applicationPackage.job.portal && applicationPackage.job.portal !== "greenhouse") {
    throw new Error("The bound application package is not for Greenhouse.");
  }
  await injectPageRunner(tab.id, true);
  const command: ContentRequest = {
    type: "CONTENT_RUN_GREENHOUSE_APPLICATION_PACKAGE",
    package: applicationPackage,
    replaceFieldIntents,
  };
  const raw: unknown = await browser.tabs.sendMessage(tab.id, command);
  if (!isPackageExecutionMessage(raw) || raw.packageId !== applicationPackage.packageId) {
    throw new Error("The Greenhouse runner returned an invalid package result.");
  }
  return raw;
}

async function runLeverPackage(applicationPackage: ApplicationPackagePayload, replaceFieldIntents: string[] = []) {
  const tab = await resolveTargetTab();
  if (tab?.id == null) throw new Error("No inspectable browser tab is active.");
  const detection = detectAtsFromUrl(tab.url || "");
  if (detection.ats !== "lever" && !isExactLeverFixtureUrl(tab.url)) {
    throw new Error("This application package can only fill a detected Lever page.");
  }
  if (applicationPackage.job.portal && applicationPackage.job.portal !== "lever") {
    throw new Error("The bound application package is not for Lever.");
  }
  await injectPageRunner(tab.id, true);
  const command: ContentRequest = { type: "CONTENT_RUN_LEVER_APPLICATION_PACKAGE", package: applicationPackage, replaceFieldIntents };
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
    /assisted-apply/extension/packages?package_id=,
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

function parseDocumentGrant(value: unknown, expected: ApplicationPackageDocumentMeta) {
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
      metadata.documentId !== expected.documentId ||
      !Number.isInteger(metadata.documentVersion) || Number(metadata.documentVersion) < 1 ||
      metadata.documentVersion !== expected.documentVersion ||
      metadata.documentKind !== expected.documentKind ||
      metadata.fileName !== expected.fileName ||
      metadata.mimeType !== expected.mimeType ||
      !((metadata.mimeType === "application/pdf" && expected.fileName.toLowerCase().endsWith(".pdf")) ||
        (metadata.mimeType === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" &&
          expected.fileName.toLowerCase().endsWith(".docx"))) ||
      !Number.isInteger(metadata.size) || Number(metadata.size) < 1 || Number(metadata.size) > 10 * 1024 * 1024 ||
      typeof metadata.sha256Hex !== "string" || !/^[0-9a-f]{64}$/u.test(metadata.sha256Hex)) {
    throw new Error("Runr returned invalid document grant metadata.");
  }
  return {
    grantToken: record.grantToken,
    documentId: metadata.documentId as string,
    documentVersion: metadata.documentVersion as number,
    documentKind: expected.documentKind,
    fileName: metadata.fileName as string,
    mimeType: expected.mimeType,
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

async function uploadSelectedDocument(applicationPackage: ApplicationPackagePayload, documentId: string) {
  const tab = await resolveTargetTab();
  if (tab?.id == null) throw new Error("No inspectable browser tab is active.");
  if (applicationPackage.job.portal !== "greenhouse" && applicationPackage.job.portal !== "lever") {
    throw new Error("The selected document is not bound to a supported application portal.");
  }
  const liveAts = detectAtsFromUrl(tab.url || "").ats ||
    (isExactGreenhouseFixtureUrl(tab.url) ? "greenhouse" : isExactLeverFixtureUrl(tab.url) ? "lever" : null);
  if (liveAts !== applicationPackage.job.portal) {
    throw new Error("The selected document package does not match the active application portal.");
  }
  const selected = applicationPackage.documents.find((item) => item.documentId === documentId);
  if (!selected) {
    throw new Error("Select a fixed-version document from this application package.");
  }
  const sessionToken = await currentSessionToken();
  const api = new RunrAssistedApplyApi(runtimeConfig.apiBaseUrl);
  const grant = parseDocumentGrant(await api.request(
    "/assisted-apply/extension/document-grants",
    "POST",
    { package_id: applicationPackage.packageId, document_id: documentId },
    sessionToken,
  ), selected);
  let bytes = await api.downloadDocument(sessionToken, grant.grantToken, grant.mimeType);
  try {
    if (bytes.byteLength !== grant.size) throw new Error("The downloaded document size did not match its grant.");
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes.slice().buffer));
    const sha256Hex = Array.from(digest, (value) => value.toString(16).padStart(2, "0")).join("");
    digest.fill(0);
    if (sha256Hex !== grant.sha256Hex) throw new Error("The downloaded document hash did not match its grant.");
    await injectPageRunner(tab.id);
    const command: ContentRequest = {
      type: "CONTENT_UPLOAD_SELECTED_DOCUMENT",
      ats: applicationPackage.job.portal,
      packageId: applicationPackage.packageId,
      documentId: grant.documentId,
      documentVersion: grant.documentVersion,
      documentKind: grant.documentKind,
      fileName: grant.fileName,
      mimeType: grant.mimeType,
      base64Bytes: bytesToBase64(bytes),
    };
    const result: unknown = await browser.tabs.sendMessage(tab.id, command);
    if (!isDocumentUploadMessage(result) || result.documentId !== grant.documentId ||
        result.documentVersion !== grant.documentVersion ||
        result.documentKind !== grant.documentKind ||
        result.telemetry.adapter !== applicationPackage.job.portal) {
      throw new Error("The application runner returned an invalid document result.");
    }
    void api.request(
      "/assisted-apply/extension/telemetry",
      "POST",
      {
        schemaVersion: result.telemetry.schemaVersion,
        adapter: result.telemetry.adapter,
        adapterVersion: result.telemetry.adapterVersion,
        lifecycleStage: result.telemetry.lifecycleStage,
        aggregateOutcome: result.telemetry.aggregateOutcome,
        errorCategory: result.telemetry.errorCategory,
      },
      sessionToken,
    ).catch(() => console.warn("Runr Assisted Apply could not record bounded upload health telemetry."));
    if (result.status === "uploaded") {
      await recordUploadedDocument(tab.id, result.documentId, result.documentVersion);
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
    if (isContentRuntimeEvent(message)) {
      const tabId = sender.tab?.id;
      if (sender.id !== browser.runtime.id || tabId == null || sender.frameId !== 0) return undefined;
      const applicationPackage = await readTabPackage(tabId);
      const liveAdapter = detectAtsFromUrl(sender.tab?.url || sender.url || "").ats;
      if (!applicationPackage || applicationPackage.packageId !== message.evidence.packageId ||
          applicationPackage.version !== message.evidence.packageVersion ||
          applicationPackage.job.portal !== message.evidence.adapter ||
          (liveAdapter !== message.evidence.adapter && !isLocalFixtureUrl(sender.tab?.url))) {
        return undefined;
      }
      const pending = {
        ...message.evidence,
        uploadedDocuments: await readUploadedDocuments(tabId),
      };
      await writePendingConfirmation(tabId, pending);
      return { ok: true, pendingConfirmation: pending };
    }
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
      if (message.type === "CHECK_PORTAL_PERMISSION") {
        const granted = await hasPortalPermission(message.portal);
        return { ok: true, permissionGranted: granted };
      }
      if (message.type === "REQUEST_PORTAL_PERMISSION") {
        const granted = await requestPortalPermission(message.portal);
        return { ok: true, permissionGranted: granted };
      }
      if (message.type === "CHECK_ALL_OPTIONAL_PERMISSIONS") {
        const allGranted = await hasAllOptionalHostPermissions();
        const missing = allGranted ? [] : await missingPortalPermissions();
        return { ok: true, permissionGranted: allGranted, missingPortalPermissions: missing };
      }
      if (message.type === "REQUEST_ALL_OPTIONAL_PERMISSIONS") {
        const granted = await requestAllOptionalHostPermissions();
        const missing = granted ? [] : await missingPortalPermissions();
        return { ok: true, permissionGranted: granted, missingPortalPermissions: missing };
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
      if (message.type === "GET_PENDING_APPLICATION_CONFIRMATION") {
        const tab = await resolveTargetTab();
        if (tab?.id == null) throw new Error("No application tab is active.");
        return { ok: true, pendingConfirmation: await readPendingConfirmation(tab.id) };
      }
      if (message.type === "RESPOND_TO_APPLICATION_CONFIRMATION") {
        const tab = await resolveTargetTab();
        if (tab?.id == null) throw new Error("No application tab is active.");
        const pending = await readPendingConfirmation(tab.id);
        if (!pending || JSON.stringify(pending) !== JSON.stringify(message.evidence)) {
          throw new Error("This application confirmation is no longer pending.");
        }
        const api = new RunrAssistedApplyApi(runtimeConfig.apiBaseUrl);
        const result = await api.request(
          "/assisted-apply/extension/application-outcomes",
          "POST",
          {
            package_id: pending.packageId,
            package_version: pending.packageVersion,
            adapter: pending.adapter,
            adapter_version: pending.adapterVersion,
            evidence_category: pending.evidenceCategory,
            decision: message.decision,
            uploaded_documents: pending.uploadedDocuments.map((document) => ({
              document_id: document.documentId,
              document_version: document.documentVersion,
            })),
          },
          await currentSessionToken(),
        );
        if (!isTrackerConfirmationResult(result)) {
          throw new Error("Runr returned an invalid Tracker confirmation result.");
        }
        await clearPendingConfirmation(tab.id);
        return { ok: true, trackerConfirmation: result };
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
                reasons: [...answer.reasons, explicit_user_correction:],
              }
            : answer),
        };
        await writeTabPackage(tab.id, updatedPackage);
        return { ok: true, package: updatedPackage };
      }
      if (message.type === "UPLOAD_SELECTED_DOCUMENT") {
        return {
          ok: true,
          documentUpload: await uploadSelectedDocument(message.package, message.documentId),
        };
      }
      if (message.type === "RUN_GREENHOUSE_APPLICATION_PACKAGE") {
        return { ok: true, packageExecution: await runGreenhousePackage(message.package, message.replaceFieldIntents) };
      }
      if (message.type === "RUN_LEVER_APPLICATION_PACKAGE") {
        return { ok: true, packageExecution: await runLeverPackage(message.package, message.replaceFieldIntents) };
      }
      const state =
        message.type === "RUN_GREENHOUSE_FIXTURE_PROOF"
          ? await (async () => {
              const mod = await import("../src/fixture-runner");
              return mod.runFixtureProof({
                resolveTargetTab,
                refreshTabState,
                readTabState,
                writeTabState,
                injectPageRunner,
                now,
              });
            })()
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