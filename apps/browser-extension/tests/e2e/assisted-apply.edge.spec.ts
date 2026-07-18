import { test, expect, chromium, type BrowserContext, type Worker } from "@playwright/test";
import { resolve } from "node:path";

const RESERVED_EXTENSION_ID = "najcdfohhfgbjpbokhmmekkahghfhegp";

declare const chrome: {
  runtime: { sendMessage(message: unknown): Promise<unknown>; };
  storage: { session: { get(keys?: null): Promise<Record<string, unknown>>; set(items: Record<string, unknown>): Promise<void>; }; };
  tabs: { query(queryInfo: Record<string, never>): Promise<Array<{ id?: number; url?: string }>>; };
};

let context: BrowserContext;
let extensionId: string;
let serviceWorker: Worker;

interface FixtureAuthState {
  connectionRequests: number; authorizationVisits: number; tokenExchanges: number;
  sessionReads: number; preferenceUpdates: number; revocationRequests: number;
  revocationInFlight: boolean; revocations: number; activeSessions: number;
  documentGrants: number; documentDownloads: number; trackerConfirmations: number;
  lastOutcomePayload: Record<string, unknown> | null;
}

async function fixtureAuthState(): Promise<FixtureAuthState> {
  const response = await context.request.get("http://127.0.0.1:4174/__test/state");
  expect(response.ok()).toBe(true);
  return (await response.json()) as FixtureAuthState;
}

test.beforeAll(async () => {
  const extensionPath = resolve(".output/edge-mv3-testing");
  context = await chromium.launchPersistentContext("", {
    channel: "msedge", headless: true,
    args: [`--disable-extensions-except=${extensionPath}`, `--load-extension=${extensionPath}`],
  });
  let [worker] = context.serviceWorkers();
  worker ??= await context.waitForEvent("serviceworker");
  serviceWorker = worker;
  extensionId = new URL(worker.url()).host;
  expect(extensionId).toBe(RESERVED_EXTENSION_ID);
});

test.afterAll(async () => { await context.close(); });

test("Edge: fixture email fill", async () => {
  const fixturePage = await context.newPage();
  await fixturePage.goto("http://127.0.0.1:4174/greenhouse-application.html");
  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  await expect(panelPage.getByTestId("connection-status")).not.toHaveText("loading");
  await panelPage.getByTestId("run-fixture").click();
  await expect(panelPage.getByTestId("execution-status")).toHaveText("filled");
  await expect(fixturePage.locator("#email")).toHaveValue("candidate@example.com");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");
  await panelPage.close(); await fixturePage.close();
});

test("Edge: connect/disconnect", async () => {
  for (const page of context.pages()) await page.close();
  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  await expect(panelPage.getByTestId("connection-status")).toHaveText("disconnected");
  await panelPage.getByTestId("connect-runr").click();
  await expect(panelPage.getByTestId("connection-status")).toHaveText("connected");
  await panelPage.getByTestId("disconnect-runr").click();
  await expect(panelPage.getByTestId("connection-status")).toHaveText("disconnected");
  await panelPage.close();
});

test("Edge: Greenhouse package", async () => {
  for (const page of context.pages()) await page.close();
  const fixturePage = await context.newPage();
  await fixturePage.goto("http://127.0.0.1:4174/greenhouse-application.html");
  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  await expect(panelPage.getByTestId("connection-status")).not.toHaveText("loading");
  const response = await panelPage.evaluate(() => chrome.runtime.sendMessage({
    type: "RUN_GREENHOUSE_APPLICATION_PACKAGE",
    package: {
      packageId: "edge-pkg-gh", jobId: "edge-job-gh", version: 1, schemaVersion: 1,
      job: { jobId: "edge-job-gh", title: "Engineer", company: "Acme", portal: "greenhouse", location: "Berlin" },
      answers: [["candidate.legal_last_name", "Edge"]].map(([f, v]) => ({ fieldIntent: f, proposedValue: v, source: "profile_verified", sensitivity: "personal", scope: "global", confidence: 1, requiresReview: false, reasons: [] })),
      documents: [], warnings: [],
      policy: { permitSensitiveAutofill: true, permitDemographicAutofill: false, requireLegalAnswerConfirmation: true },
    },
  }));
  expect(response).toMatchObject({ ok: true });
  await expect(fixturePage.locator("#last-name")).toHaveValue("Edge");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");
  await panelPage.close(); await fixturePage.close();
});

test("Edge: Lever package", async () => {
  for (const page of context.pages()) await page.close();
  const fixturePage = await context.newPage();
  await fixturePage.goto("http://127.0.0.1:4174/lever-application.html");
  await fixturePage.evaluate(() => { document.body.dataset.submitClicks = "0"; });
  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  const response = await panelPage.evaluate(() => chrome.runtime.sendMessage({
    type: "RUN_LEVER_APPLICATION_PACKAGE",
    package: {
      packageId: "edge-pkg-lv", jobId: "edge-job-lv", version: 1, schemaVersion: 1,
      job: { jobId: "edge-job-lv", title: "Engineer", company: "Acme", portal: "lever", location: "Remote" },
      answers: [{ fieldIntent: "candidate.full_name", label: "Full name", proposedValue: "Edge Test", source: "profile_verified", sensitivity: "standard", scope: "global", confidence: 1, requiresReview: false, reasons: [] }],
      documents: [], warnings: [],
      policy: { permitSensitiveAutofill: true, permitDemographicAutofill: false, requireLegalAnswerConfirmation: true },
    },
  }));
  expect(response).toMatchObject({ ok: true });
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");
  await panelPage.close(); await fixturePage.close();
});

test("Edge: CV upload", async () => {
  for (const page of context.pages()) await page.close();
  const fixturePage = await context.newPage();
  await fixturePage.goto("http://127.0.0.1:4174/greenhouse-application.html");
  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  await expect(panelPage.getByTestId("connection-status")).not.toHaveText("loading");
  if (await panelPage.getByTestId("connect-runr").isVisible().catch(() => false)) {
    await panelPage.getByTestId("connect-runr").click();
  }
  const response = await panelPage.evaluate(() => chrome.runtime.sendMessage({
    type: "UPLOAD_SELECTED_DOCUMENT",
    documentId: "cv_version_7",
    package: {
      packageId: "edge-pkg-cv", jobId: "edge-job-cv", version: 1, schemaVersion: 1,
      job: { jobId: "edge-job-cv", title: "Engineer", company: "Acme", portal: "greenhouse", location: "Berlin" },
      answers: [],
      documents: [{ documentId: "cv_version_7", documentVersion: 7, documentKind: "cv", mimeType: "application/pdf", fileName: "Candidate CV.pdf" }],
      warnings: [],
      policy: { permitSensitiveAutofill: false, permitDemographicAutofill: false, requireLegalAnswerConfirmation: true },
    },
  }));
  expect(response).toMatchObject({ ok: true, documentUpload: { status: "uploaded" } });
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");
  await panelPage.close(); await fixturePage.close();
});
test("Edge: tracker confirmation", async () => {
  for (const page of context.pages()) await page.close();
  const fixturePage = await context.newPage();
  await fixturePage.goto("http://127.0.0.1:4174/greenhouse-application.html");
  const panelPage = await context.newPage();
  await panelPage.goto("chrome-extension://" + extensionId + "/sidepanel.html");
  await expect(panelPage.getByTestId("connection-status")).not.toHaveText("loading");
  if (await panelPage.getByTestId("connect-runr").isVisible().catch(() => false)) {
    await panelPage.getByTestId("connect-runr").click();
  }
  const pkg = { packageId: "edge-pkg-tr", jobId: "edge-job-tr", version: 1, schemaVersion: 1, job: { jobId: "edge-job-tr", title: "Engineer", company: "Acme", portal: "greenhouse", location: "Berlin" }, answers: [], documents: [], warnings: [], policy: { permitSensitiveAutofill: false, permitDemographicAutofill: false, requireLegalAnswerConfirmation: true } };
  await panelPage.evaluate(async (pkg) => { const tabs = await chrome.tabs.query({}); const tab = tabs.find(c => c.url?.includes("greenhouse-application.html")); if (tab?.id == null) throw new Error("Fixture tab missing."); await chrome.storage.session.set({ ["assisted-apply-package:" + tab.id]: pkg }); return chrome.runtime.sendMessage({ type: "RUN_GREENHOUSE_APPLICATION_PACKAGE", package: pkg }); }, pkg);
  const before = await fixtureAuthState();
  await fixturePage.locator("form").evaluate(f => { f.noValidate = true; });
  await fixturePage.locator("#final-submit").click();
  await expect(panelPage.getByTestId("application-confirmation")).toBeVisible();
  await panelPage.getByRole("button", { name: "Yes, add to Tracker" }).click();
  await expect(panelPage.getByTestId("tracker-confirmation-result")).toHaveText("Application added to Tracker.");
  const after = await fixtureAuthState();
  expect(after.trackerConfirmations).toBe(before.trackerConfirmations + 1);
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "1");
  await panelPage.close(); await fixturePage.close();
});

test("Edge: review panel", async () => {
  for (const page of context.pages()) await page.close();
  const fixturePage = await context.newPage();
  await fixturePage.goto("http://127.0.0.1:4174/greenhouse-application.html");
  const panelPage = await context.newPage();
  await panelPage.goto("chrome-extension://" + extensionId + "/sidepanel.html");
  await expect(panelPage.getByTestId("connection-status")).not.toHaveText("loading");
  if (await panelPage.getByTestId("connect-runr").isVisible().catch(() => false)) {
    await panelPage.getByTestId("connect-runr").click();
  }
  await panelPage.evaluate(async () => {
    const tabs = await chrome.tabs.query({});
    const tab = tabs.find(c => c.url?.includes("greenhouse-application.html"));
    if (tab?.id == null) throw new Error("Fixture tab missing.");
    await chrome.storage.session.set({ ["assisted-apply-package:" + tab.id]: { packageId: "edge-rvw-pkg", jobId: "edge-rvw-job", version: 1, schemaVersion: 1, job: { jobId: "edge-rvw-job", title: "Engineer", company: "Acme", portal: "greenhouse", location: "Berlin" }, answers: [], documents: [{ documentId: "cv_v1", documentVersion: 1, documentKind: "cv", mimeType: "application/pdf", fileName: "cv.pdf" }], warnings: [], policy: { permitSensitiveAutofill: false, permitDemographicAutofill: false, requireLegalAnswerConfirmation: true } } });
  });
  await panelPage.reload();
  await expect(panelPage.getByText("Engineer")).toBeVisible({ timeout: 5000 });
  await expect(panelPage.getByText("Ready")).toBeVisible();
  await expect(panelPage.getByText("Documents")).toBeVisible();
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");
  await panelPage.close(); await fixturePage.close();
});
