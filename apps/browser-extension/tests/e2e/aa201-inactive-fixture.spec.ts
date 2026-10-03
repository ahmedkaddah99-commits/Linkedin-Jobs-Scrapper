import { test, expect, chromium, type BrowserContext, type Page, type Worker } from "@playwright/test";
import { resolve } from "node:path";

const RESERVED_EXTENSION_ID = "najcdfohhfgbjpbokhmmekkahghfhegp";
const DUMMY_PDF_BASE64 = Buffer.from("%PDF-1.4\n% AA-201 sanitized dummy\n%%EOF\n", "utf8").toString("base64");

declare const chrome: {
  runtime: { sendMessage(message: unknown): Promise<unknown> };
  tabs: {
    get(tabId: number): Promise<{ id?: number; url?: string; active?: boolean; status?: string }>;
  };
};

interface SpikeResponse {
  ok: boolean;
  spike: {
    tabId: number;
    active: boolean;
    ready: { type: string; url: string };
    response: { execution: { inspection: unknown; executions: Array<{ status: string }> }; upload: { status: string } };
    completion: { type: string; packageId: string; upload: { status: string } };
  };
}

let context: BrowserContext;
let serviceWorker: Worker;
let extensionId: string;
let controlPage: Page;

async function runSpike(ats: "greenhouse" | "lever"): Promise<SpikeResponse> {
  controlPage = await context.newPage();
  await controlPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  const listenerProbe = await controlPage.evaluate(() => chrome.runtime.sendMessage({ type: "GET_EXTENSION_CONNECTION" }));
  if (!listenerProbe || typeof listenerProbe !== "object") throw new Error("AA-201 extension listener probe returned no response.");
  return controlPage.evaluate(async ({ ats: requestedAts, pdf }) => chrome.runtime.sendMessage({
    type: "AA201_START_INACTIVE_FIXTURE_SPIKE",
    ats: requestedAts,
    packageId: `aa201-inactive-${requestedAts}`,
    packageVersion: 1,
    applicationUrl: `http://127.0.0.1:4174/${requestedAts}-application.html`,
    candidate: requestedAts === "greenhouse"
      ? { firstName: "Ada", lastName: "Lovelace", email: "ada.aa201@example.test", phone: "+49 30 123456" }
      : { fullName: "Ada Lovelace", email: "ada.aa201@example.test", phone: "+49 30 123456" },
    answers: requestedAts === "greenhouse"
      ? [
          ["candidate.legal_first_name", "First name", "Ada"],
          ["candidate.legal_last_name", "Last name", "Lovelace"],
          ["candidate.email", "Email", "ada.aa201@example.test"],
          ["candidate.phone", "Phone", "+49 30 123456"],
        ].map(([fieldIntent, label, proposedValue]) => ({ fieldIntent, label, proposedValue }))
      : [
          ["candidate.full_name", "Full name", "Ada Lovelace"],
          ["candidate.email", "Email", "ada.aa201@example.test"],
          ["candidate.phone", "Phone", "+49 30 123456"],
        ].map(([fieldIntent, label, proposedValue]) => ({ fieldIntent, label, proposedValue })),
    document: {
      documentId: `aa201-${requestedAts}-dummy-cv`,
      documentVersion: 1,
      documentKind: "cv",
      fileName: "AA-201-dummy-CV.pdf",
      mimeType: "application/pdf",
      base64Bytes: pdf,
    },
  }), { ats, pdf: DUMMY_PDF_BASE64 }) as Promise<SpikeResponse>;
}

async function fixturePage(ats: "greenhouse" | "lever"): Promise<Page> {
  const page = context.pages().find((candidate) => candidate.url().includes(`${ats}-application.html`));
  if (!page) throw new Error(`AA-201 ${ats} fixture page was not created.`);
  return page;
}

async function assertNoSubmissionSignals(page: Page): Promise<Record<string, string | null>> {
  const evidence = await page.locator("body").evaluate((body) => ({
    submitEvents: body.getAttribute("data-aa201-submit-events"),
    requestSubmitCalls: body.getAttribute("data-aa201-request-submit-calls"),
    formSubmitCalls: body.getAttribute("data-aa201-form-submit-calls"),
    enterSubmissions: body.getAttribute("data-aa201-enter-submissions"),
    terminalClicks: body.getAttribute("data-aa201-terminal-clicks"),
    terminalRequests: body.getAttribute("data-aa201-terminal-requests"),
    successTransitions: body.getAttribute("data-aa201-success-transitions"),
    finalNavigation: body.getAttribute("data-aa201-final-navigation"),
  }));
  for (const value of Object.values(evidence)) expect(value).toBe("0");
  return evidence;
}

test.beforeAll(async () => {
  const extensionPath = resolve(".output/chrome-mv3-testing");
  context = await chromium.launchPersistentContext("", {
    channel: "chromium",
    headless: true,
    args: [`--disable-extensions-except=${extensionPath}`, `--load-extension=${extensionPath}`],
  });
  let [worker] = context.serviceWorkers();
  worker ??= await context.waitForEvent("serviceworker");
  serviceWorker = worker;
  extensionId = new URL(worker.url()).host;
  expect(extensionId).toBe(RESERVED_EXTENSION_ID);
});

test.afterEach(async () => {
  for (const page of context.pages()) await page.close();
});

test.afterAll(async () => { await context.close(); });

for (const ats of ["greenhouse", "lever"] as const) {
  test(`AA-201 runs ${ats} inactive, attaches a dummy PDF, and activates the exact tab`, async () => {
    const response = await runSpike(ats);
    expect(response).toMatchObject({
      ok: true,
      spike: {
        active: false,
        ready: { type: "AA201_INACTIVE_FIXTURE_READY", url: `http://127.0.0.1:4174/${ats}-application.html` },
        response: { upload: { status: "uploaded" } },
        completion: { type: "AA201_INACTIVE_FIXTURE_COMPLETED", packageId: `aa201-inactive-${ats}`, upload: { status: "uploaded" } },
      },
    });
    const page = await fixturePage(ats);
    const tabBeforeActivation = await serviceWorker.evaluate((tabId) => chrome.tabs.get(tabId), response.spike.tabId);
    expect(tabBeforeActivation).toMatchObject({ id: response.spike.tabId, active: false, status: "complete" });

    if (ats === "greenhouse") {
      await expect(page.locator("#last-name")).toHaveValue("Lovelace");
      await expect(page.locator("#email")).toHaveValue("ada.aa201@example.test");
      await expect(page.locator("#phone")).toHaveValue("+49 30 123456");
      await expect(page.locator("#resume")).toHaveValue("C:\\fakepath\\AA-201-dummy-CV.pdf");
    } else {
      await expect(page.locator('input[name="name"]')).toHaveValue("Ada Lovelace");
      await expect(page.locator('input[name="email"]')).toHaveValue("ada.aa201@example.test");
      await expect(page.locator('input[name="phone"]')).toHaveValue("+49 30 123456");
      await expect(page.locator("#lever-resume")).toHaveValue("C:\\fakepath\\AA-201-dummy-CV.pdf");
    }
    const evidence = await assertNoSubmissionSignals(page);

    const activation = await controlPage.evaluate((tabId) => chrome.runtime.sendMessage({
      type: "AA201_ACTIVATE_INACTIVE_FIXTURE_TAB",
      tabId,
    }), response.spike.tabId) as { ok: boolean; tabId: number; active: boolean };
    expect(activation).toEqual({ ok: true, tabId: response.spike.tabId, active: true });
    await expect.poll(async () => (await serviceWorker.evaluate((tabId) => chrome.tabs.get(tabId), response.spike.tabId)).active).toBe(true);
    console.log(`AA-201 sanitized evidence ${JSON.stringify({ ats, tabId: response.spike.tabId, inactiveBeforeActivation: true, upload: "uploaded", submissionSignals: evidence })}`);
  });
}
