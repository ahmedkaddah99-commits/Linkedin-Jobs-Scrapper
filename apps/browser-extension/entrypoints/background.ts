import { detectAtsFromUrl, uploadFieldIntentFor } from "@runr/ats-core";
import {
  isExactGreenhouseFixtureUrl,
  isExactLeverFixtureUrl,
  isFixtureInspectionMessage,
  isPackageExecutionMessage,
  isApplicationPackagePayload,
  ASSISTED_APPLY_PREPARATION_PROTOCOL,
  ASSISTED_APPLY_PREPARATION_MAX_AGE_MS,
  isDocumentUploadMessage,
  isContentRuntimeEvent,
  isPanelRequest,
  isRunrWebLaunchRequest,
  isTrackerConfirmationResult,
  type ApplicationPackagePayload,
  type AssistedApplyTabState,
  type ContentRequest,
  type FixtureInspectionMessage,
  type PanelResponse,
  type PreparationPanelState,
  type AssistedApplyPreparationMessage,
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
import { isExactRunrWebSender, isExactSidePanelSender } from "../src/auth/trusted-sender";
import { comparableApplicationUrl, preparedApplicationUrlMatches } from "../src/application-url";
import {
  isFreshPreparationCommand,
  isWebPreparationCommand,
  preparationCommandFingerprint,
} from "../src/preparation/external-command";
import { preparationProgressResult } from "../src/preparation/report";
import { parseDocumentGrant } from "../src/documents/grant-validation";
import {
  hasAllOptionalHostPermissions,
  hasPortalPermission,
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
import {
  canActivateExactPreparationTab,
  canRetryPreparation,
  classifyPreparationTabChange,
  hasActivePreparation,
  readPreparationLocalRecord,
  writePreparationLocalRecord,
  type PreparationLocalRecord,
  type PreparationLocalStatus,
} from "../src/preparation/local-session";

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

async function runGreenhousePackageOnTab(tabId: number, applicationPackage: ApplicationPackagePayload, replaceFieldIntents: string[] = []) {
  const tab = await browser.tabs.get(tabId);
  const detection = detectAtsFromUrl(tab.url || "");
  if (detection.ats !== "greenhouse" && !isLocalFixtureUrl(tab.url)) {
    throw new Error("This application package can only fill a detected Greenhouse page.");
  }
  if (applicationPackage.job.portal && applicationPackage.job.portal !== "greenhouse") {
    throw new Error("The bound application package is not for Greenhouse.");
  }
  await injectPageRunner(tabId, true);
  const command: ContentRequest = {
    type: "CONTENT_RUN_GREENHOUSE_APPLICATION_PACKAGE",
    package: applicationPackage,
    replaceFieldIntents,
  };
  const raw: unknown = await browser.tabs.sendMessage(tabId, command);
  if (!isPackageExecutionMessage(raw) || raw.packageId !== applicationPackage.packageId) {
    throw new Error("The Greenhouse runner returned an invalid package result.");
  }
  return raw;
}

async function runLeverPackageOnTab(tabId: number, applicationPackage: ApplicationPackagePayload, replaceFieldIntents: string[] = []) {
  const tab = await browser.tabs.get(tabId);
  const detection = detectAtsFromUrl(tab.url || "");
  if (detection.ats !== "lever" && !isExactLeverFixtureUrl(tab.url)) {
    throw new Error("This application package can only fill a detected Lever page.");
  }
  if (applicationPackage.job.portal && applicationPackage.job.portal !== "lever") {
    throw new Error("The bound application package is not for Lever.");
  }
  await injectPageRunner(tabId, true);
  const command: ContentRequest = { type: "CONTENT_RUN_LEVER_APPLICATION_PACKAGE", package: applicationPackage, replaceFieldIntents };
  const raw: unknown = await browser.tabs.sendMessage(tabId, command);
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
  const response = await api.getApplicationPackage(sessionToken, packageId);
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

async function runGreenhousePackage(applicationPackage: ApplicationPackagePayload, replaceFieldIntents: string[] = []) {
  const tab = await resolveTargetTab();
  if (tab?.id == null) throw new Error("No inspectable browser tab is active.");
  return runGreenhousePackageOnTab(tab.id, applicationPackage, replaceFieldIntents);
}

async function runLeverPackage(applicationPackage: ApplicationPackagePayload, replaceFieldIntents: string[] = []) {
  const tab = await resolveTargetTab();
  if (tab?.id == null) throw new Error("No inspectable browser tab is active.");
  return runLeverPackageOnTab(tab.id, applicationPackage, replaceFieldIntents);
}

async function waitForRunrOpenedApplicationTab(applicationUrl: string): Promise<Browser.tabs.Tab> {
  const expected = comparableApplicationUrl(applicationUrl);
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const tabs = await browser.tabs.query({});
    const matchingTab = tabs.find((tab) => {
      if (tab.id == null || !tab.url || tab.url.startsWith("chrome-extension://")) return false;
      try {
        return comparableApplicationUrl(tab.url) === expected;
      } catch {
        return false;
      }
    });
    if (matchingTab) return matchingTab;
    await new Promise<void>((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("Runr could not find the application tab that it opened.");
}

async function bindRunrWebLaunch(
  bindingId: string,
  applicationUrl: string,
): Promise<{ ok: true; packageId: string }> {
  // Locate the user-opened employer tab before consuming the short-lived binding.
  // A transient tab/load failure therefore remains retryable during the binding TTL.
  const tab = await waitForRunrOpenedApplicationTab(applicationUrl);
  const detected = detectAtsFromUrl(tab.url || "");
  const ats = detected.ats || (isExactGreenhouseFixtureUrl(tab.url) ? "greenhouse" :
    isExactLeverFixtureUrl(tab.url) ? "lever" : null);
  if (!ats) {
    throw new Error("The opened job page is not a supported Greenhouse or Lever application.");
  }
  const applicationPackage = await bindPackageFromApi(bindingId);
  const preparedApplicationUrl = (applicationPackage.job as ApplicationPackagePayload["job"] & { url?: unknown }).url;
  if (!preparedApplicationUrlMatches(preparedApplicationUrl, applicationUrl)) {
    throw new Error("The opened application URL does not match the prepared Runr package.");
  }
  if (applicationPackage.job.portal !== ats) {
    throw new Error("The opened application page does not match the prepared Runr package.");
  }
  await writeTabPackage(tab.id as number, applicationPackage);
  await refreshTabState(tab);
  return { ok: true, packageId: applicationPackage.packageId };
}

async function preparationApiRequest(path: string, body: Record<string, unknown>): Promise<unknown> {
  const token = await currentSessionToken();
  const api = new RunrAssistedApplyApi(runtimeConfig.apiBaseUrl);
  return api.request(path, "POST", body, token);
}

async function reportPreparationFromExtension(
  message: AssistedApplyPreparationMessage,
  type: "permission_required" | "accepted",
): Promise<void> {
  await preparationApiRequest("/assisted-apply/extension/preparations/report", {
    preparation_id: message.preparationId,
    package_id: message.packageId,
    message_id: `${message.messageId}:${type}`,
    type,
    result: type === "accepted"
      ? { status: "accepted" }
      : { status: "needs_attention", code: "permission_required" },
  });
}

async function reportPreparationProgress(
  message: Extract<AssistedApplyPreparationMessage, { source: "web" }>,
  type: "progress" | "ready_for_review",
  completed: number,
  total: number,
): Promise<void> {
  await preparationApiRequest("/assisted-apply/extension/preparations/report", {
    preparation_id: message.preparationId,
    package_id: message.packageId,
    message_id: `${message.messageId}:${type}`,
    type,
    result: preparationProgressResult(type, completed, total),
  });
}

async function reportPreparationNeedsAttention(
  message: Extract<AssistedApplyPreparationMessage, { source: "web" }>,
  code: "document_unavailable" | "navigation_blocked" | "validation_failed",
): Promise<void> {
  await preparationApiRequest("/assisted-apply/extension/preparations/report", {
    preparation_id: message.preparationId,
    package_id: message.packageId,
    message_id: `${message.messageId}:needs_attention:${code}`,
    type: "needs_attention",
    result: { status: "needs_attention", code },
  });
}

const preparationReadyWaiters = new Map<number, () => void>();

async function waitForPreparationTabReady(tabId: number, applicationUrl: string): Promise<void> {
  const current = await browser.tabs.get(tabId);
  if (current.url && comparableApplicationUrl(current.url) !== comparableApplicationUrl(applicationUrl)) {
    throw new Error("The preparation tab navigated away before readiness.");
  }
  await new Promise<void>((resolve, reject) => {
    let settled = false;
    const finish = (error?: unknown) => {
      if (settled) return;
      settled = true;
      browser.tabs.onUpdated.removeListener(listener);
      preparationReadyWaiters.delete(tabId);
      error ? reject(error) : resolve();
    };
    const listener = (updatedTabId: number, changeInfo: { status?: string; url?: string }) => {
      if (updatedTabId !== tabId) return;
      if (changeInfo.url && comparableApplicationUrl(changeInfo.url) !== comparableApplicationUrl(applicationUrl)) {
        finish(new Error("The preparation tab navigated away before readiness."));
      } else if (changeInfo.status === "complete") {
        void browser.tabs.get(tabId).then((tab) => {
          if (tab.discarded || !tab.url || comparableApplicationUrl(tab.url) !== comparableApplicationUrl(applicationUrl)) {
            finish(new Error("The preparation tab was discarded or changed before readiness."));
          } else if (preparationReadyWaiters.has(tabId)) {
            // The content-script handshake completes the promise.
          }
        }).catch(finish);
      }
    };
    browser.tabs.onUpdated.addListener(listener);
    preparationReadyWaiters.set(tabId, () => finish());
    if (current.status === "complete" && current.url === applicationUrl) {
      // The injection below will produce the handshake without a polling loop.
    }
    setTimeout(() => finish(new Error("The preparation content-script readiness handshake timed out.")), 10_000);
  });
}

async function updatePreparationLocalStatus(status: PreparationLocalStatus): Promise<PreparationLocalRecord | null> {
  const record = await readPreparationLocalRecord();
  if (!record) return null;
  const updated = { ...record, status, updatedAt: now() };
  await writePreparationLocalRecord(updated);
  return updated;
}

function preparationPanelState(record: PreparationLocalRecord | null): PreparationPanelState {
  if (!record) return { status: "idle" as const, ats: null, completedCount: 0, totalCount: 0 };
  const status = (record.status === "starting" || record.status === "waiting_ready"
    ? "queued"
    : record.status === "preparing"
      ? "preparing"
      : record.status === "ready_for_review"
        ? "ready_for_review"
        : record.status === "review_activated"
          ? "review_activated"
        : record.status === "closed" || record.status === "discarded" || record.status === "navigation_mismatch"
          ? "interrupted"
          : record.status === "failed"
            ? "needs_attention"
            : record.status) as PreparationPanelState["status"];
  const reason = record.status === "permission_required" ? "Grant portal access, then retry preparation."
    : record.status === "auth_lost" ? "Reconnect Runr before retrying preparation."
      : record.status === "closed" ? "The prepared application tab was closed."
        : record.status === "discarded" ? "The prepared application tab was discarded."
          : record.status === "navigation_mismatch" ? "The prepared application tab changed location."
            : record.status === "expired" ? "This preparation expired; retry only with a still-valid package."
              : record.status === "failed" ? "Preparation needs attention before retry."
                : undefined;
  return { status, ats: record.ats, completedCount: record.completedCount, totalCount: record.totalCount, ...(reason ? { reason } : {}) };
}

async function panelPreparationAction(action: "retry" | "cancel" | "activate") {
  const record = await readPreparationLocalRecord();
  if (!record) throw new Error("No local preparation is available; start a new preparation from Runr.");
  if (action === "activate") {
    const tab = await browser.tabs.get(record.tabId).catch(() => null);
    if (!canActivateExactPreparationTab(record, tab)) throw new Error("The exact prepared tab is unavailable; retry is required.");
    await browser.tabs.update(record.tabId, { active: true });
    await applyPreparationExtensionAction({ preparationId: record.preparationId, packageId: record.packageId } as Extract<AssistedApplyPreparationMessage, { source: "web" }>, "activate");
    await updatePreparationLocalStatus("review_activated");
  } else if (action === "cancel") {
    await applyPreparationExtensionAction({ preparationId: record.preparationId, packageId: record.packageId } as Extract<AssistedApplyPreparationMessage, { source: "web" }>, "cancel");
    await updatePreparationLocalStatus("cancelled");
  } else {
    if (!canRetryPreparation(record)) throw new Error("Retry is unavailable for this preparation or the bounded attempt limit was reached.");
    await applyPreparationExtensionAction({ preparationId: record.preparationId, packageId: record.packageId } as Extract<AssistedApplyPreparationMessage, { source: "web" }>, "retry");
    await writePreparationLocalRecord({ ...record, status: "retry_required", updatedAt: now() });
    const result = await startPreparationCommand({
      protocol: ASSISTED_APPLY_PREPARATION_PROTOCOL,
      protocolVersion: 1,
      type: "start",
      source: "web",
      messageId: `panel-retry-${Date.now()}`,
      preparationId: record.preparationId,
      packageId: record.packageId,
      emittedAt: now(),
      capabilities: { adapters: ["greenhouse", "lever"], capabilities: ["fill"] },
    }, { forceNewTab: true, attempt: record.attempt + 1 });
    if (!result.ok) throw new Error(result.error || "Retry requires attention.");
  }
  return preparationPanelState(await readPreparationLocalRecord());
}

async function applyPreparationExtensionAction(
  message: Extract<AssistedApplyPreparationMessage, { source: "web" }>,
  action: "activate" | "cancel" | "retry",
): Promise<void> {
  await preparationApiRequest("/assisted-apply/extension/preparations/action", {
    preparation_id: message.preparationId,
    package_id: message.packageId,
    action,
  });
}

async function startPreparationCommand(
  message: Extract<AssistedApplyPreparationMessage, { type: "start" }>,
  options: { forceNewTab?: boolean; attempt?: number } = {},
): Promise<PreparationCommandResponse> {
  const existing = await readPreparationLocalRecord();
  if (hasActivePreparation(existing)) {
    return { ok: false, preparationId: message.preparationId, packageId: message.packageId, status: "busy", error: "Another preparation is already active." };
  }
  const connection = await connectionService.getConnection();
  if (connection.status !== "connected" || !connection.session || Date.parse(connection.session.expiresAt) <= Date.now()) {
    await updatePreparationLocalStatus("auth_lost");
    throw new Error("Runr extension connection is missing or expired.");
  }
  const applicationPackage = await fetchPackageFromApi(message.packageId);
  if (!isApplicationPackagePayload(applicationPackage) || applicationPackage.packageId !== message.packageId) {
    throw new Error("Runr returned an invalid or unassociated application package.");
  }
  const portal = applicationPackage.job.portal;
  if ((portal !== "greenhouse" && portal !== "lever") || !message.capabilities.adapters.includes(portal) ||
      !message.capabilities.capabilities.includes("fill")) {
    throw new Error("Preparation capabilities do not match the bound application package.");
  }
  const applicationUrl = (applicationPackage.job as ApplicationPackagePayload["job"] & { url?: unknown }).url;
  if (typeof applicationUrl !== "string" || !applicationUrl || (import.meta.env.MODE !== "testing" && !applicationUrl.startsWith("https://"))) {
    throw new Error("The bound application package has no safe application URL.");
  }
  const permissionGranted = await hasPortalPermission(portal);
  if (!permissionGranted) {
    await writePreparationLocalRecord({
      preparationId: message.preparationId, packageId: message.packageId, packageVersion: applicationPackage.version,
      ats: portal, applicationUrl, status: "permission_required", tabId: -1,
      createdAt: now(), updatedAt: now(), attempt: 1, completedCount: 0, totalCount: 0,
      lastMessageId: message.messageId,
    });
    await reportPreparationFromExtension(message, "permission_required");
    return { ok: false, preparationId: message.preparationId, packageId: message.packageId, status: "permission_required", permissionGranted: false };
  }
  const acceptedReport = reportPreparationFromExtension(message, "accepted");
  const expected = comparableApplicationUrl(applicationUrl);
  const tabs = await browser.tabs.query({});
  let tab = options.forceNewTab ? undefined : tabs.find((candidate) => {
    if (candidate.id == null || !candidate.url) return false;
    try { return comparableApplicationUrl(candidate.url) === expected; } catch { return false; }
  });
  if (!tab) tab = await browser.tabs.create({ url: applicationUrl, active: false });
  if (tab.id == null) throw new Error("Runr could not create or resume the application tab.");
  const localRecord: PreparationLocalRecord = {
    preparationId: message.preparationId, packageId: message.packageId, packageVersion: applicationPackage.version,
    ats: portal, applicationUrl, tabId: tab.id, windowId: tab.windowId,
    status: "waiting_ready", createdAt: now(), updatedAt: now(), attempt: options.attempt ?? 1,
    completedCount: 0, totalCount: applicationPackage.answers.length + applicationPackage.documents.length,
    lastMessageId: message.messageId,
  };
  await writePreparationLocalRecord(localRecord);
  await writeTabPackage(tab.id, applicationPackage);
  const readyPromise = waitForPreparationTabReady(tab.id, applicationUrl);
  await injectPageRunner(tab.id, true);
  await readyPromise;
  await acceptedReport;
  await updatePreparationLocalStatus("preparing");
  const execution = portal === "greenhouse"
    ? await runGreenhousePackageOnTab(tab.id, applicationPackage)
    : await runLeverPackageOnTab(tab.id, applicationPackage);
  const completedFields = execution.executions.filter((result) =>
    result.status === "filled" || result.status === "already_filled" || result.status === "preserved_existing").length;
  let completedDocuments = 0;
  for (const document of applicationPackage.documents) {
    const upload = await uploadSelectedDocumentOnTab(tab.id, applicationPackage, document.documentId);
    if (upload.status !== "uploaded") {
      throw new Error("A selected application document could not be attached and verified.");
    }
    completedDocuments += 1;
  }
  const completedCount = completedFields + completedDocuments;
  const totalCount = Math.max(completedCount, execution.reviewFieldCount ?? completedCount, 1);
  await reportPreparationProgress(message, "progress", completedCount, totalCount);
  await reportPreparationProgress(message, "ready_for_review", completedCount, totalCount);
  await writePreparationLocalRecord({ ...(await readPreparationLocalRecord() ?? localRecord), status: "ready_for_review", completedCount, totalCount, updatedAt: now() });
  return { ok: true, preparationId: message.preparationId, packageId: message.packageId, ats: portal, permissionGranted: true, status: "ready_for_review" };
}

async function handlePreparationCommand(
  message: Extract<AssistedApplyPreparationMessage, { source: "web" }>,
): Promise<PreparationCommandResponse> {
  if (!isFreshPreparationCommand(message)) throw new Error("The preparation command is stale or has an invalid timestamp.");
  const fingerprint = preparationCommandFingerprint(message);
  const existing = preparationCommandReplay.get(message.messageId);
  if (existing) {
    if (existing.expiresAt > Date.now() && existing.fingerprint === fingerprint) return existing.response;
    throw new Error("The preparation command was replayed or reused with different content.");
  }
  let response: PreparationCommandResponse;
  if (message.type === "start") {
    try {
      response = await startPreparationCommand(message);
    } catch (error) {
      const text = error instanceof Error ? error.message : String(error);
      if (/connection|session|authenticate/iu.test(text)) {
        await updatePreparationLocalStatus("auth_lost");
        response = { ok: false, preparationId: message.preparationId, packageId: message.packageId, status: "auth_lost", error: "Extension authentication is unavailable; explicit retry is required." };
      } else {
        const code = /document|upload|grant|attach|hash/iu.test(text)
          ? "document_unavailable"
          : /navigat|url|tab|page|portal/iu.test(text)
            ? "navigation_blocked"
            : "validation_failed";
        await updatePreparationLocalStatus("failed");
        await reportPreparationNeedsAttention(message, code).catch(() => {
          console.warn("Runr Assisted Apply could not persist a sanitized attention report.");
        });
        response = {
          ok: false,
          preparationId: message.preparationId,
          packageId: message.packageId,
          status: "needs_attention",
          error: "Preparation stopped safely before review; explicit retry is required.",
        };
      }
    }
  } else if (message.type === "retry") {
    const localRecord = await readPreparationLocalRecord();
    if (!localRecord) {
      response = { ok: false, preparationId: message.preparationId, packageId: message.packageId, status: "retry_required", error: "Local browser ownership was lost; start a new explicit preparation." };
      preparationCommandReplay.set(message.messageId, { fingerprint, response, expiresAt: Date.now() + ASSISTED_APPLY_PREPARATION_MAX_AGE_MS });
      return response;
    }
    if (!canRetryPreparation(localRecord)) {
      response = { ok: false, preparationId: message.preparationId, packageId: message.packageId, status: "retry_required", error: "The bounded preparation retry limit has been reached or the session is still active." };
      preparationCommandReplay.set(message.messageId, { fingerprint, response, expiresAt: Date.now() + ASSISTED_APPLY_PREPARATION_MAX_AGE_MS });
      return response;
    }
    await applyPreparationExtensionAction(message, "retry");
    await writePreparationLocalRecord({ ...localRecord, status: "retry_required", updatedAt: now() });
    try {
      response = await startPreparationCommand({
        protocol: message.protocol,
        protocolVersion: message.protocolVersion,
        type: "start",
        source: "web",
        messageId: message.messageId,
        preparationId: message.preparationId,
        packageId: message.packageId,
        emittedAt: message.emittedAt,
        capabilities: { adapters: ["greenhouse", "lever"], capabilities: ["fill"] },
      }, { forceNewTab: true, attempt: localRecord.attempt + 1 });
      response = { ...response, status: "retrying" };
    } catch (error) {
      await updatePreparationLocalStatus("retry_required");
      response = {
        ok: false,
        preparationId: message.preparationId,
        packageId: message.packageId,
        status: "retry_required",
        error: /package|expired|unavailable/iu.test(error instanceof Error ? error.message : String(error))
          ? "The approved application package is unavailable or expired; create a new package."
          : "Explicit retry could not be completed; review authentication, permission, or ATS state.",
      };
    }
  } else if (message.type === "review_activate") {
    const record = await readPreparationLocalRecord();
    const tab = record ? await browser.tabs.get(record.tabId).catch(() => null) : null;
    if (!canActivateExactPreparationTab(record, tab)) {
      if (record?.status === "ready_for_review") await updatePreparationLocalStatus(tab ? "navigation_mismatch" : "closed");
      response = { ok: false, preparationId: message.preparationId, packageId: message.packageId, status: "retry_required", error: "The exact session-owned review tab is unavailable or no longer matches." };
      preparationCommandReplay.set(message.messageId, { fingerprint, response, expiresAt: Date.now() + ASSISTED_APPLY_PREPARATION_MAX_AGE_MS });
      return response;
    }
    if (!record) throw new Error("The preparation ownership record disappeared.");
    await browser.tabs.update(record.tabId, { active: true });
    await applyPreparationExtensionAction(message, "activate");
    await updatePreparationLocalStatus("review_activated");
    response = { ok: true, preparationId: message.preparationId, packageId: message.packageId, status: "activated" };
  } else {
    await updatePreparationLocalStatus("cancelled");
    await applyPreparationExtensionAction(message, "cancel");
    response = { ok: true, preparationId: message.preparationId, packageId: message.packageId, status: "cancelled" };
  }
  preparationCommandReplay.set(message.messageId, { fingerprint, response, expiresAt: Date.now() + ASSISTED_APPLY_PREPARATION_MAX_AGE_MS });
  return response;
}

async function currentSessionToken(): Promise<string> {
  const value = await authStorage.readSessionSecret();
  if (!value || typeof value !== "object" || Array.isArray(value) ||
      typeof (value as { sessionToken?: unknown }).sessionToken !== "string") {
    throw new Error("Connect the extension to Runr before using a document.");
  }
  return (value as { sessionToken: string }).sessionToken;
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

async function uploadSelectedDocumentOnTab(
  tabId: number,
  applicationPackage: ApplicationPackagePayload,
  documentId: string,
) {
  const tab = await browser.tabs.get(tabId);
  if (tab.id == null) throw new Error("No inspectable browser tab is available.");
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
    {
      package_id: applicationPackage.packageId,
      document_id: documentId,
      adapter: applicationPackage.job.portal,
      upload_field_intent: uploadFieldIntentFor(applicationPackage.job.portal, selected.documentKind),
    },
    sessionToken,
  ), selected, uploadFieldIntentFor(applicationPackage.job.portal, selected.documentKind));
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
      uploadFieldIntent: grant.uploadFieldIntent,
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
      "/assisted-apply/telemetry/events",
      "POST",
      {
        schemaVersion: result.telemetry.schemaVersion,
        adapter: result.telemetry.adapter,
        adapterVersion: result.telemetry.adapterVersion,
        lifecycleStage: result.telemetry.lifecycleStage,
        aggregateOutcome: result.telemetry.aggregateOutcome,
        errorCategory: result.telemetry.errorCategory,
      },
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

async function uploadSelectedDocument(applicationPackage: ApplicationPackagePayload, documentId: string) {
  const tab = await resolveTargetTab();
  if (tab?.id == null) throw new Error("No inspectable browser tab is active.");
  return uploadSelectedDocumentOnTab(tab.id, applicationPackage, documentId);
}

type InactiveFixtureSpikeRequest = {
  type: "AA201_START_INACTIVE_FIXTURE_SPIKE";
  ats: "greenhouse" | "lever";
  packageId: string;
  packageVersion: number;
  applicationUrl: string;
  candidate: { firstName?: string; lastName?: string; fullName?: string; email?: string; phone?: string };
  answers: Array<{ fieldIntent: string; label: string; proposedValue: string }>;
  document: {
    documentId: string;
    documentVersion: number;
    documentKind: "cv" | "cover_letter" | "supporting_document";
    fileName: string;
    mimeType: string;
    base64Bytes: string;
  };
};

type InactiveFixtureSpikeActivation = {
  type: "AA201_ACTIVATE_INACTIVE_FIXTURE_TAB";
  tabId: number;
};

const inactiveSpikeCompletionWaiters = new Map<number, (value: unknown) => void>();

function isInactiveSpikeRequest(value: unknown): value is InactiveFixtureSpikeRequest {
  return import.meta.env.MODE === "testing" && Boolean(value) && typeof value === "object" &&
    (value as { type?: unknown }).type === "AA201_START_INACTIVE_FIXTURE_SPIKE";
}

function isInactiveSpikeActivation(value: unknown): value is InactiveFixtureSpikeActivation {
  return import.meta.env.MODE === "testing" && Boolean(value) && typeof value === "object" &&
    (value as { type?: unknown }).type === "AA201_ACTIVATE_INACTIVE_FIXTURE_TAB" &&
    Number.isInteger((value as { tabId?: unknown }).tabId);
}

async function waitForFixtureTabReady(tabId: number, applicationUrl: string): Promise<void> {
  const tabReady = new Promise<void>((resolve, reject) => {
    const listener = (updatedTabId: number, changeInfo: { status?: string }) => {
      if (updatedTabId !== tabId || changeInfo.status !== "complete") return;
      browser.tabs.onUpdated.removeListener(listener);
      void browser.tabs.get(tabId).then((readyTab) => {
        if (readyTab.url !== applicationUrl) reject(new Error("AA-201 fixture tab URL changed before readiness."));
        else resolve();
      }).catch(reject);
    };
    browser.tabs.onUpdated.addListener(listener);
    void browser.tabs.get(tabId).then((tab) => {
      if (tab.url && tab.url !== "about:blank" && tab.url !== applicationUrl) {
        reject(new Error("AA-201 fixture tab URL changed before readiness."));
        return;
      }
      if (tab.status === "complete" && tab.url === applicationUrl) {
        browser.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    }).catch(reject);
  });
  await tabReady;
}

async function runInactiveFixtureSpike(request: InactiveFixtureSpikeRequest): Promise<unknown> {
  const tab = await browser.tabs.create({ url: request.applicationUrl, active: false });
  if (tab.id == null) throw new Error("AA-201 could not create a fixture tab.");
  const tabId = tab.id;
  await waitForFixtureTabReady(tabId, request.applicationUrl);

  const completion = new Promise<unknown>((resolve) => inactiveSpikeCompletionWaiters.set(tabId, resolve));
  const ready = await new Promise<unknown>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("AA-201 content-script readiness handshake timed out.")), 10_000);
    const listener = (message: unknown, sender: { tab?: { id?: number } }) => {
      if (sender.tab?.id !== tabId || !message || typeof message !== "object" ||
          (message as { type?: unknown }).type !== "AA201_INACTIVE_FIXTURE_READY") return;
      clearTimeout(timer);
      browser.runtime.onMessage.removeListener(listener);
      resolve(message);
    };
    browser.runtime.onMessage.addListener(listener);
    void browser.scripting.executeScript({ target: { tabId }, files: ["/inactive-fixture-spike.js"] })
      .catch((error: unknown) => {
        clearTimeout(timer);
        browser.runtime.onMessage.removeListener(listener);
        reject(error);
      });
  });
  const result = await browser.tabs.sendMessage(tabId, {
    type: "AA201_RUN_INACTIVE_FIXTURE",
    ats: request.ats,
    packageId: request.packageId,
    packageVersion: request.packageVersion,
    candidate: request.candidate,
    answers: request.answers,
    document: request.document,
  });
  const reported = await Promise.race([
    completion,
    new Promise((_, reject) => setTimeout(() => reject(new Error("AA-201 completion report timed out.")), 10_000)),
  ]);
  inactiveSpikeCompletionWaiters.delete(tabId);
  return { tabId, active: false, ready, response: result, completion: reported };
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

  browser.runtime.onMessageExternal.addListener((message, sender, sendResponse) => {
    if (!isExactRunrWebSender(sender, runtimeConfig.frontendOrigin)) {
      return undefined;
    }
    if (isWebPreparationCommand(message)) {
      void handlePreparationCommand(message)
        .then(sendResponse)
        .catch((error: unknown) => sendResponse({
          ok: false,
          error: error instanceof Error ? error.message : "Runr could not handle the preparation command.",
        }));
      return true;
    }
    if (message && typeof message === "object" &&
        (message as { protocol?: unknown }).protocol === ASSISTED_APPLY_PREPARATION_PROTOCOL) {
      sendResponse({ ok: false, error: "Runr rejected the invalid or unsupported preparation command." });
      return false;
    }
    if (!isRunrWebLaunchRequest(message)) return undefined;
    if (import.meta.env.MODE !== "testing" && !message.applicationUrl.startsWith("https://")) {
      return undefined;
    }
    void bindRunrWebLaunch(message.bindingId, message.applicationUrl)
      .then(sendResponse)
      .catch((error: unknown) => sendResponse({
        ok: false,
        error: error instanceof Error ? error.message : "Runr could not bind this application package.",
      }));
    return true;
  });

  browser.runtime.onMessage.addListener(async (
    message: unknown,
    sender,
  ): Promise<PanelResponse | undefined> => {
    if (message && typeof message === "object" &&
        (message as { type?: unknown }).type === "ASSISTED_APPLY_CONTENT_READY") {
      const tabId = sender.tab?.id;
      if (sender.id === browser.runtime.id && tabId != null) preparationReadyWaiters.get(tabId)?.();
      return { ok: true };
    }
    if (import.meta.env.MODE === "testing" && message && typeof message === "object" &&
        (message as { type?: unknown }).type === "AA201_INACTIVE_FIXTURE_READY") {
      return { ok: true };
    }
    if (import.meta.env.MODE === "testing" && message && typeof message === "object" &&
        (message as { type?: unknown }).type === "AA201_INACTIVE_FIXTURE_COMPLETED") {
      const tabId = sender.tab?.id;
      if (tabId != null) inactiveSpikeCompletionWaiters.get(tabId)?.(message);
      return { ok: true };
    }
    if (isInactiveSpikeRequest(message)) {
      return { ok: true, spike: await runInactiveFixtureSpike(message) } as PanelResponse;
    }
    if (isInactiveSpikeActivation(message)) {
      const tab = await browser.tabs.get(message.tabId);
      if (!tab.url?.startsWith("http://127.0.0.1:4174/")) throw new Error("AA-201 may activate only a locally owned fixture tab.");
      await browser.tabs.update(message.tabId, { active: true });
      return { ok: true, tabId: message.tabId, active: true } as PanelResponse;
    }
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
      if (message.type === "GET_ASSISTED_APPLY_PREPARATION") {
        return { ok: true, preparation: preparationPanelState(await readPreparationLocalRecord()) };
      }
      if (message.type === "RETRY_ASSISTED_APPLY_PREPARATION") {
        return { ok: true, preparation: await panelPreparationAction("retry") };
      }
      if (message.type === "CANCEL_ASSISTED_APPLY_PREPARATION") {
        return { ok: true, preparation: await panelPreparationAction("cancel") };
      }
      if (message.type === "ACTIVATE_ASSISTED_APPLY_PREPARATION") {
        return { ok: true, preparation: await panelPreparationAction("activate") };
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
        // The sidepanel owns the user gesture and performs permissions.request().
        // The service worker only verifies the resulting grant and updates local state.
        const granted = await hasPortalPermission(message.portal);
        const localPreparation = await readPreparationLocalRecord();
        if (granted && localPreparation?.status === "permission_required" && localPreparation.ats === message.portal) {
          await writePreparationLocalRecord({ ...localPreparation, status: "retry_required", updatedAt: now() });
        }
        return { ok: true, permissionGranted: granted };
      }
      if (message.type === "CHECK_ALL_OPTIONAL_PERMISSIONS") {
        const allGranted = await hasAllOptionalHostPermissions();
        const missing = allGranted ? [] : await missingPortalPermissions();
        return { ok: true, permissionGranted: allGranted, missingPortalPermissions: missing };
      }
      if (message.type === "REQUEST_ALL_OPTIONAL_PERMISSIONS") {
        const granted = await hasAllOptionalHostPermissions();
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
                reasons: [...answer.reasons, `explicit_user_correction:${message.scope}`],
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
    void readPreparationLocalRecord().then(async (record) => {
      if (record?.tabId === tabId && !["cancelled", "closed", "discarded"].includes(record.status)) {
        await updatePreparationLocalStatus("closed");
      }
    });
    void removeTabState(tabId);
  });
  browser.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    void readPreparationLocalRecord().then(async (record) => {
      if (!record || record.tabId !== tabId) return;
      const status = classifyPreparationTabChange(record, changeInfo, tab.url);
      if (status) await updatePreparationLocalStatus(status);
    });
  });
});

type PreparationCommandResponse = {
  ok: boolean;
  preparationId?: string;
  packageId?: string;
  ats?: "greenhouse" | "lever";
  permissionGranted?: boolean;
  status?: "permission_required" | "accepted" | "ready_for_review" | "activated" | "cancelled" | "retrying" | "busy" | "retry_required" | "auth_lost" | "needs_attention";
  error?: string;
};

const preparationCommandReplay = new Map<string, {
  fingerprint: string;
  response: PreparationCommandResponse;
  expiresAt: number;
}>();
