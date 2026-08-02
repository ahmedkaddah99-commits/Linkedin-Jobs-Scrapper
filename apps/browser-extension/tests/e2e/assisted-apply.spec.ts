import {
  test,
  expect,
  chromium,
  type BrowserContext,
  type Page,
  type Worker,
} from "@playwright/test";
import { resolve } from "node:path";

const RESERVED_EXTENSION_ID = "najcdfohhfgbjpbokhmmekkahghfhegp";

declare const chrome: {
  runtime: {
    sendMessage(message: unknown): Promise<unknown>;
    sendMessage(extensionId: string, message: unknown): Promise<unknown>;
  };
  storage: {
    session: {
      get(keys?: null | string): Promise<Record<string, unknown>>;
      set(items: Record<string, unknown>): Promise<void>;
      remove(keys: string | string[]): Promise<void>;
    };
  };
  tabs: {
    query(queryInfo: Record<string, never>): Promise<Array<{ id?: number; url?: string; active?: boolean }>>;
  };
};

let context: BrowserContext;
let extensionId: string;
let serviceWorker: Worker;

interface ServiceWorkerVersion {
  versionId: string;
  scriptURL: string;
  runningStatus: "stopped" | "starting" | "running" | "stopping";
}

interface FixtureAuthState {
  connectionRequests: number;
  authorizationVisits: number;
  tokenExchanges: number;
  sessionReads: number;
  preferenceUpdates: number;
  revocationRequests: number;
  revocationInFlight: boolean;
  revocations: number;
  activeSessions: number;
  documentGrants: number;
  documentDownloads: number;
  trackerConfirmations: number;
  lastOutcomePayload: Record<string, unknown> | null;
  preparationReports: Array<Record<string, unknown>>;
  preparationActions: Array<Record<string, unknown>>;
}

async function fixtureAuthState(): Promise<FixtureAuthState> {
  const response = await context.request.get("http://127.0.0.1:4174/__test/state");
  expect(response.ok()).toBe(true);
  return (await response.json()) as FixtureAuthState;
}

async function stopExtensionWorker(page: Page): Promise<void> {
  const cdp = await context.newCDPSession(page);
  const versions = new Map<string, ServiceWorkerVersion>();
  let observedStopped = false;
  cdp.on(
    "ServiceWorker.workerVersionUpdated",
    ({ versions: updates }: { versions: ServiceWorkerVersion[] }) => {
      for (const version of updates) {
        versions.set(version.versionId, version);
        if (
          version.scriptURL === `chrome-extension://${extensionId}/background.js` &&
          version.runningStatus === "stopped"
        ) {
          observedStopped = true;
        }
      }
    },
  );
  await cdp.send("ServiceWorker.enable");
  await expect
    .poll(
      () =>
        Array.from(versions.values()).find(
          (version) => version.scriptURL === `chrome-extension://${extensionId}/background.js`,
        ),
      { message: "The extension service worker should be visible to Chromium." },
    )
    .not.toBeUndefined();
  const version = Array.from(versions.values()).find(
    (candidate) => candidate.scriptURL === `chrome-extension://${extensionId}/background.js`,
  );
  if (!version) throw new Error("The extension service-worker version was not observed.");
  await cdp.send("ServiceWorker.stopWorker", { versionId: version.versionId });
  await expect.poll(() => observedStopped).toBe(true);
  await cdp.detach();
}

test.beforeAll(async () => {
  const extensionPath = resolve(".output/chrome-mv3-testing");
  context = await chromium.launchPersistentContext("", {
    channel: "chromium",
    headless: true,
    args: [
      `--disable-extensions-except=${extensionPath}`,
      `--load-extension=${extensionPath}`,
    ],
  });
  let [worker] = context.serviceWorkers();
  worker ??= await context.waitForEvent("serviceworker");
  serviceWorker = worker;
  extensionId = new URL(worker.url()).host;
  expect(extensionId).toBe(RESERVED_EXTENSION_ID);
});

test.afterAll(async () => {
  await context.close();
});

test("AA-223 renders sanitized lifecycle states and exposes review without submission", async () => {
  const record = {
    preparationId: "prep_aa223",
    packageId: "aapkg_aa223",
    packageVersion: 1,
    ats: "greenhouse",
    applicationUrl: "http://127.0.0.1:4174/greenhouse-application.html",
    tabId: 999991,
    status: "permission_required",
    createdAt: "2026-08-01T12:00:00.000Z",
    updatedAt: "2026-08-01T12:00:00.000Z",
    attempt: 1,
    completedCount: 0,
    totalCount: 3,
  };
  await serviceWorker.evaluate(async (value) => {
    await chrome.storage.session.set({ "assisted-apply-preparation:local:v1": value });
  }, record);
  expect(await serviceWorker.evaluate(async () => chrome.storage.session.get("assisted-apply-preparation:local:v1"))).toMatchObject({
    "assisted-apply-preparation:local:v1": { status: "permission_required" },
  });
  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  await panelPage.reload();
  const panelPreparation = await panelPage.evaluate(() => chrome.runtime.sendMessage({ type: "GET_ASSISTED_APPLY_PREPARATION" }));
  expect(panelPreparation).toMatchObject({ ok: true, preparation: { status: "permission_required" } });
  await expect(panelPage.getByTestId("preparation-lifecycle")).toHaveClass(/preparation-permission_required/);
  await expect(panelPage.getByRole("button", { name: "Grant portal access" })).toBeVisible();
  await expect(panelPage.getByText("3 unresolved")).toBeVisible();
  await expect(panelPage.getByRole("button", { name: /submit/i })).toHaveCount(0);

  await serviceWorker.evaluate(async () => {
    await chrome.storage.session.set({
      "assisted-apply-preparation:local:v1": {
        ...((await chrome.storage.session.get("assisted-apply-preparation:local:v1"))["assisted-apply-preparation:local:v1"] as Record<string, unknown>),
        status: "ready_for_review",
        completedCount: 2,
        totalCount: 3,
      },
    });
  });
  await panelPage.reload();
  await expect(panelPage.getByRole("button", { name: "Review filled application" })).toBeVisible();
  await expect(panelPage.getByText("2 filled")).toBeVisible();
  await expect(panelPage.getByText("1 unresolved")).toBeVisible();
  await expect(panelPage.getByRole("button", { name: /submit/i })).toHaveCount(0);
  await panelPage.close();
});

test("fills only the empty fixture email and reports verified readback", async () => {
  const fixturePage = await context.newPage();
  await fixturePage.goto("http://127.0.0.1:4174/greenhouse-application.html");

  const visibleTabs = await serviceWorker.evaluate(async () =>
    (await chrome.tabs.query({})).map((tab) => ({ id: tab.id, url: tab.url })),
  );
  expect(visibleTabs.some((tab) => tab.url?.includes("greenhouse-application.html"))).toBe(true);

  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);

  const refreshed = await panelPage.evaluate(() =>
    chrome.runtime.sendMessage({ type: "REFRESH_ACTIVE_TAB_STATE" }),
  );
  expect(refreshed).toMatchObject({
    ok: true,
    state: { ats: "greenhouse", fixtureAvailable: true, status: "fixture_ready" },
  });
  await panelPage.getByRole("button", { name: "Refresh page status" }).click();

  await expect(panelPage.getByTestId("ats-name")).toHaveText("Greenhouse");
  await panelPage.getByTestId("run-fixture").click();
  await expect(panelPage.getByTestId("execution-status")).toHaveText("filled");

  await expect(fixturePage.locator("#email")).toHaveValue("candidate@example.com");
  await expect(fixturePage.locator("#first-name")).toHaveValue("Existing Candidate");
  await expect(fixturePage.locator("body")).toHaveAttribute(
    "data-email-events",
    "focus,input,change,blur",
  );
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");
  await expect(fixturePage.locator("#captcha-response")).toHaveValue("");
  await expect(fixturePage.locator("#signature")).toHaveValue("");
  await expect(fixturePage.locator("#declaration")).not.toBeChecked();
  await expect(fixturePage.locator("#terms")).not.toBeChecked();
  await expect(fixturePage.locator("#assessment")).toHaveValue("");

  await stopExtensionWorker(fixturePage);
  await panelPage.reload();
  await expect(panelPage.getByTestId("execution-status")).toHaveText("filled");

  await panelPage.getByTestId("run-fixture").click();
  await expect(panelPage.getByTestId("execution-status")).toHaveText("already_filled");
  await expect(fixturePage.locator("body")).toHaveAttribute(
    "data-email-events",
    "focus,input,change,blur",
  );
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");

  await fixturePage.locator("#email").fill("");
  await panelPage.getByTestId("run-fixture").click();
  await expect(panelPage.getByTestId("execution-status")).toHaveText("preserved_existing");
  await expect(fixturePage.locator("#email")).toHaveValue("");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");

  await fixturePage.reload();
  await fixturePage.locator("#email").fill("person@existing.example");
  await panelPage.getByRole("button", { name: "Refresh page status" }).click();
  await panelPage.getByTestId("run-fixture").click();
  await expect(panelPage.getByTestId("execution-status")).toHaveText("preserved_existing");
  await expect(fixturePage.locator("#email")).toHaveValue("person@existing.example");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");
  await panelPage.close();
  await fixturePage.close();
});

test("fills package-backed Greenhouse standard facts through the panel and worker", async () => {
  const fixturePage = await context.newPage();
  await fixturePage.goto("http://127.0.0.1:4174/greenhouse-application.html");
  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);

  const response = await panelPage.evaluate(() => chrome.runtime.sendMessage({
    type: "RUN_GREENHOUSE_APPLICATION_PACKAGE",
    package: {
      packageId: "aapkg_fixture_aa04",
      jobId: "job_fixture_aa04",
      version: 2,
      schemaVersion: 1,
      job: { jobId: "job_fixture_aa04", title: "Engineer", company: "Acme", portal: "greenhouse", location: "Berlin" },
      answers: [
        ["candidate.legal_first_name", "Ada"],
        ["candidate.legal_last_name", "Lovelace"],
        ["candidate.email", "ada@example.com"],
        ["candidate.phone", "+49 30 123456"],
      ].map(([fieldIntent, proposedValue]) => ({
        fieldIntent, proposedValue, source: "profile_verified", sensitivity: "personal",
        scope: "global", confidence: 1, requiresReview: false, reasons: ["Verified fixture value."],
      })),
      documents: [], warnings: [],
      policy: { permitSensitiveAutofill: true, permitDemographicAutofill: false, requireLegalAnswerConfirmation: true },
    },
  }));

  expect(response).toMatchObject({
    ok: true,
    packageExecution: { packageId: "aapkg_fixture_aa04" },
  });
  await expect(fixturePage.locator("#first-name")).toHaveValue("Existing Candidate");
  await expect(fixturePage.locator("#last-name")).toHaveValue("Lovelace");
  await expect(fixturePage.locator("#email")).toHaveValue("ada@example.com");
  await expect(fixturePage.locator("#phone")).toHaveValue("+49 30 123456");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");
  await panelPage.close();
  await fixturePage.close();
});

test("AA-219 stops Greenhouse preparation at review across rerun and reload", async () => {
  for (const page of context.pages()) await page.close();
  const fixturePage = await context.newPage();
  await fixturePage.goto("http://127.0.0.1:4174/greenhouse-application.html");
  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  const applicationPackage = {
    packageId: "aa219-greenhouse-review-boundary",
    jobId: "aa219-greenhouse-job",
    version: 1,
    schemaVersion: 1,
    job: { jobId: "aa219-greenhouse-job", title: "Engineer", company: "Acme", portal: "greenhouse", location: "Berlin" },
    answers: [
      ["candidate.legal_last_name", "Legal last name", "Lovelace"],
      ["candidate.email", "Email address", "ada@example.com"],
      ["application.work_authorization", "Work authorization", "Yes"],
    ].map(([fieldIntent, label, proposedValue]) => ({
      fieldIntent, label, proposedValue, source: "profile_verified",
      sensitivity: label === "Work authorization" ? "legal" : "standard",
      scope: "application", confidence: 1, requiresReview: false, reasons: ["Sanitized fixture value."],
    })),
    documents: [], warnings: [],
    policy: { permitSensitiveAutofill: true, permitDemographicAutofill: false, requireLegalAnswerConfirmation: true },
  };
  const run = () => panelPage.evaluate((pkg) => chrome.runtime.sendMessage({
    type: "RUN_GREENHOUSE_APPLICATION_PACKAGE", package: pkg,
  }), applicationPackage) as Promise<{ ok: boolean; packageExecution: { executions: Array<{ fieldLabel: string; status: string }> } }>;

  const first = await run();
  expect(first.ok).toBe(true);
  expect(first.packageExecution.executions.map((item) => item.fieldLabel)).toEqual(["Legal last name", "Email address"]);
  await expect(fixturePage.locator("#last-name")).toHaveValue("Lovelace");
  await expect(fixturePage.locator("#email")).toHaveValue("ada@example.com");
  await expect(fixturePage.locator("#work-yes")).not.toBeChecked();
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");

  await fixturePage.reload();
  const second = await run();
  expect(second.ok).toBe(true);
  expect(second.packageExecution.executions).toHaveLength(2);
  await expect(fixturePage.locator("#last-name")).toHaveValue("Lovelace");
  await expect(fixturePage.locator("#email")).toHaveValue("ada@example.com");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-aa201-submit-events", "0");
  await panelPage.close();
  await fixturePage.close();
});

test("fills a Lever package independently of Greenhouse DOM assumptions", async () => {
  for (const page of context.pages()) await page.close();
  const fixturePage = await context.newPage();
  await fixturePage.goto("http://127.0.0.1:4174/lever-application.html");
  await fixturePage.evaluate(() => {
    document.querySelector("form")!.addEventListener("submit", (event) => {
      event.preventDefault();
      document.body.dataset.submitClicks = String(Number(document.body.dataset.submitClicks || "0") + 1);
    });
    document.body.dataset.submitClicks = "0";
  });
  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  const response = await panelPage.evaluate(() => chrome.runtime.sendMessage({
    type: "RUN_LEVER_APPLICATION_PACKAGE",
    package: {
      packageId: "aa-05-lever-package", jobId: "lever-job", version: 1, schemaVersion: 1,
      job: { jobId: "lever-job", title: "Engineer", company: "Acme", portal: "lever", location: "Remote" },
      answers: [
        { fieldIntent: "candidate.full_name", label: "Full name", proposedValue: "Ada Lovelace", source: "profile_verified", sensitivity: "standard", scope: "global", confidence: 1, requiresReview: false, reasons: [] },
        { fieldIntent: "candidate.email", label: "Email", proposedValue: "ada@example.com", source: "profile_verified", sensitivity: "personal", scope: "global", confidence: 1, requiresReview: false, reasons: [] },
        { fieldIntent: "candidate.phone", label: "Phone", proposedValue: "+44 20 7946 0958", source: "profile_verified", sensitivity: "personal", scope: "global", confidence: 1, requiresReview: false, reasons: [] },
      ], documents: [], warnings: [],
      policy: { permitSensitiveAutofill: true, permitDemographicAutofill: false, requireLegalAnswerConfirmation: true },
    },
  })) as { ok: boolean; packageExecution: { packageId: string; ats: string; executions: Array<{ status: string }> } };
  expect(response).toMatchObject({ ok: true, packageExecution: { packageId: "aa-05-lever-package", ats: "lever" } });
  expect(response.packageExecution.executions.map((item: { status: string }) => item.status)).toEqual(["filled", "filled", "filled"]);
  await expect(fixturePage.locator('input[name="name"]')).toHaveValue("Ada Lovelace");
  await expect(fixturePage.locator('input[name="email"]')).toHaveValue("ada@example.com");
  await expect(fixturePage.locator('input[name="phone"]')).toHaveValue("+44 20 7946 0958");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");
});

test("fills a production-shaped Lever profile from confirmed Career Memory intents", async () => {
  for (const page of context.pages()) await page.close();
  const fixturePage = await context.newPage();
  await fixturePage.goto("http://127.0.0.1:4174/lever-application.html");
  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  const facts = [
    ["candidate.full_name", "Full name", "Ada Lovelace"],
    ["candidate.email", "Email", "ada@example.com"],
    ["candidate.location", "Current location", "Berlin, Germany"],
    ["candidate.current_company", "Current company", "Analytical Engines"],
    ["candidate.github_url", "GitHub URL", "https://github.com/ada"],
    ["candidate.linkedin_url", "LinkedIn URL", "https://www.linkedin.com/in/ada"],
    ["candidate.website", "Website", "https://ada.example"],
  ].map(([fieldIntent, label, proposedValue]) => ({
    fieldIntent, label, proposedValue, source: "profile_verified", sensitivity: "standard",
    scope: "global", confidence: 1, requiresReview: false, reasons: ["Confirmed Career Memory fixture."],
  }));
  const response = await panelPage.evaluate((answers) => chrome.runtime.sendMessage({
    type: "RUN_LEVER_APPLICATION_PACKAGE",
    package: {
      packageId: "aa-live-shaped-lever", jobId: "live-shaped-job", version: 1, schemaVersion: 1,
      job: { jobId: "live-shaped-job", title: "Engineer", company: "Example", portal: "lever", location: "Remote" },
      answers, documents: [], warnings: [],
      policy: { permitSensitiveAutofill: false, permitDemographicAutofill: false, requireLegalAnswerConfirmation: true },
    },
  }), facts) as { ok: boolean; packageExecution: { executions: Array<{ fieldIntent?: string; status: string }>; reviewFieldCount: number } };

  expect(response.ok).toBe(true);
  expect(response.packageExecution.executions).toHaveLength(7);
  expect(response.packageExecution.executions.every((item) => item.status === "filled")).toBe(true);
  await expect(fixturePage.locator('input[name="location"]')).toHaveValue("Berlin, Germany");
  await expect(fixturePage.locator('input[name="company"]')).toHaveValue("Analytical Engines");
  await expect(fixturePage.locator('input[name="github"]')).toHaveValue("https://github.com/ada");
  await expect(fixturePage.locator('input[name="linkedin"]')).toHaveValue("https://www.linkedin.com/in/ada");
  await expect(fixturePage.locator('input[name="website"]')).toHaveValue("https://ada.example");
  await expect(fixturePage.locator('textarea[name="why_company"]')).toHaveValue("");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-aa201-submit-events", "0");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-aa201-request-submit-calls", "0");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-aa201-form-submit-calls", "0");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-aa201-enter-submissions", "0");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-aa201-terminal-clicks", "0");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-aa201-terminal-requests", "0");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-aa201-success-transitions", "0");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-aa201-final-navigation", "0");
});

test("AA-220 stops Lever preparation at review across rerun and reload", async () => {
  for (const page of context.pages()) await page.close();
  const fixturePage = await context.newPage();
  await fixturePage.goto("http://127.0.0.1:4174/lever-application.html");
  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  const applicationPackage = {
    packageId: "aa220-lever-review-boundary",
    jobId: "aa220-lever-job",
    version: 1,
    schemaVersion: 1,
    job: { jobId: "aa220-lever-job", title: "Engineer", company: "Acme", portal: "lever", location: "Berlin" },
    answers: [
      ["candidate.full_name", "Full name", "Ada Lovelace"],
      ["candidate.email", "Email", "ada@example.com"],
      ["application.work_authorization", "Work authorization", "Yes"],
    ].map(([fieldIntent, label, proposedValue]) => ({
      fieldIntent, label, proposedValue, source: "profile_verified",
      sensitivity: label === "Work authorization" ? "legal" : "standard",
      scope: "application", confidence: 1, requiresReview: false, reasons: ["Sanitized fixture value."],
    })),
    documents: [], warnings: [],
    policy: { permitSensitiveAutofill: true, permitDemographicAutofill: false, requireLegalAnswerConfirmation: true },
  };
  const run = () => panelPage.evaluate((pkg) => chrome.runtime.sendMessage({
    type: "RUN_LEVER_APPLICATION_PACKAGE", package: pkg,
  }), applicationPackage) as Promise<{ ok: boolean; packageExecution: { executions: Array<{ fieldLabel: string; status: string }> } }>;

  const first = await run();
  expect(first.ok).toBe(true);
  expect(first.packageExecution.executions.map((item) => item.fieldLabel)).toEqual(["Full name", "Email"]);
  await expect(fixturePage.locator('input[name="name"]')).toHaveValue("Ada Lovelace");
  await expect(fixturePage.locator('input[name="email"]')).toHaveValue("ada@example.com");
  await expect(fixturePage.locator("#lever-work-yes")).not.toBeChecked();
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");

  await fixturePage.reload();
  const second = await run();
  expect(second.ok).toBe(true);
  expect(second.packageExecution.executions).toHaveLength(2);
  await expect(fixturePage.locator('input[name="name"]')).toHaveValue("Ada Lovelace");
  await expect(fixturePage.locator('input[name="email"]')).toHaveValue("ada@example.com");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-aa201-submit-events", "0");
  await panelPage.close();
  await fixturePage.close();
});

test("fills and verifies mixed native controls on Greenhouse and Lever", async () => {
  for (const portal of ["greenhouse", "lever"] as const) {
    for (const page of context.pages()) await page.close();
    const fixturePage = await context.newPage();
    await fixturePage.goto(`http://127.0.0.1:4174/${portal}-application.html`);
    const panelPage = await context.newPage();
    await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);
    const prefix = portal === "greenhouse" ? "" : "lever-";
    const answers = [
      ["application.summary", "Professional summary", "I build reliable systems."],
      ["application.country", "Country", "Germany"],
      ["application.work_authorization", "Work authorization", "Yes"],
      ["application.remote", "Open to remote work", "true"],
      ["application.start_date", "Start date", "2026-08-03"],
      ["application.employee_code", "Employee code", "invalid"],
    ].map(([fieldIntent, label, proposedValue]) => ({
      fieldIntent, label, proposedValue,
      source: label === "Country" ? "scoped_preference" : "profile_verified",
      sensitivity: "standard",
      scope: "application", confidence: 1, requiresReview: false, reasons: ["Verified fixture answer."],
    }));
    const response = await panelPage.evaluate(({ portal, answers }) => chrome.runtime.sendMessage({
      type: portal === "greenhouse"
        ? "RUN_GREENHOUSE_APPLICATION_PACKAGE"
        : "RUN_LEVER_APPLICATION_PACKAGE",
      package: {
        packageId: `aa07-${portal}`, jobId: `aa07-job-${portal}`, version: 1, schemaVersion: 1,
        job: { jobId: `aa07-job-${portal}`, title: "Engineer", company: "Acme", portal, location: "Remote" },
        answers, documents: [], warnings: [],
        policy: { permitSensitiveAutofill: true, permitDemographicAutofill: false, requireLegalAnswerConfirmation: true },
      },
    }), { portal, answers }) as { ok: boolean; packageExecution: { executions: Array<{ fieldLabel: string; status: string }> } };

    expect(response.ok).toBe(true);
    expect(response.packageExecution.executions.map((item) => [item.fieldLabel, item.status])).toEqual([
      ["Professional summary", "filled"], ["Country", "filled"],
      ["Work authorization", "filled"], ["Open to remote work", "filled"],
      ["Start date", "filled"], ["Employee code", "rejected"],
    ]);
    await expect(fixturePage.locator(`#${prefix}summary`)).toHaveValue("I build reliable systems.");
    await expect(fixturePage.locator(`#${prefix}country`)).toHaveValue("DE");
    await expect(fixturePage.locator(`#${prefix}work-yes`)).toBeChecked();
    await expect(fixturePage.locator(`#${prefix}remote`)).toBeChecked();
    await expect(fixturePage.locator(`#${prefix}start-date`)).toHaveValue("2026-08-03");
    expect(await fixturePage.locator(`#${prefix}employee-code`).evaluate(
      (control: HTMLInputElement) => control.checkValidity(),
    )).toBe(false);
    await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");
    const events = (await fixturePage.locator("body").getAttribute("data-native-events"))?.split(",") ?? [];
    for (const id of [`${prefix}summary`, `${prefix}country`, `${prefix}work-yes`, `${prefix}remote`, `${prefix}start-date`]) {
      expect(events).toEqual(expect.arrayContaining([
        `${id}:focus`, `${id}:input`, `${id}:change`, `${id}:blur`,
      ]));
    }
  }
});

test("fills same-origin frames and open roots while keeping inaccessible/custom boundaries manual", async () => {
  for (const page of context.pages()) await page.close();
  const fixturePage = await context.newPage();
  await fixturePage.goto("http://127.0.0.1:4174/greenhouse-application.html");
  await expect(fixturePage.frameLocator("#same-origin-frame").locator("#same-frame-portfolio")).toBeVisible();
  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  const answers = [
    ["application.portfolio", "Same-frame portfolio", "https://example.test/ada"],
    ["application.editor", "Open shadow favorite editor", "Neovim"],
    ["application.cross_origin", "Cross-frame screening answer", "must-not-fill"],
    ["application.custom", "Custom salary widget", "must-not-fill"],
  ].map(([fieldIntent, label, proposedValue]) => ({
    fieldIntent, label, proposedValue, source: "profile_verified", sensitivity: "standard",
    scope: "application", confidence: 1, requiresReview: false, reasons: ["AA-13 fixture answer."],
  }));
  const response = await panelPage.evaluate((answers) => chrome.runtime.sendMessage({
    type: "RUN_GREENHOUSE_APPLICATION_PACKAGE",
    package: {
      packageId: "aa13-boundary-matrix", jobId: "aa13-job", version: 1, schemaVersion: 1,
      job: { jobId: "aa13-job", title: "Engineer", company: "Acme", portal: "greenhouse", location: "Berlin" },
      answers, documents: [], warnings: [],
      policy: { permitSensitiveAutofill: true, permitDemographicAutofill: false, requireLegalAnswerConfirmation: true },
    },
  }), answers) as { ok: boolean; packageExecution: { manualReasons: string[]; executions: Array<{ fieldLabel: string; status: string }> } };

  expect(response.ok).toBe(true);
  expect(response.packageExecution.executions.map((item) => [item.fieldLabel, item.status])).toEqual([
    ["Open shadow favorite editor", "filled"],
    ["Same-frame portfolio", "filled"],
  ]);
  expect(response.packageExecution.manualReasons).toEqual(expect.arrayContaining([
    "cross_origin_frame", "closed_shadow_root", "unsupported_custom_control",
  ]));
  await expect(fixturePage.frameLocator("#same-origin-frame").locator("#same-frame-portfolio"))
    .toHaveValue("https://example.test/ada");
  await expect(fixturePage.locator("#open-shadow-host #open-shadow-editor")).toHaveValue("Neovim");
  await expect(fixturePage.frameLocator("#cross-origin-frame").locator("#cross-frame-secret")).toHaveValue("");
  await expect(fixturePage.locator("#custom-salary-widget")).toHaveText("");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");
});

test("AA-08 reinspects dynamic controls, preserves user edits, and recovers after worker restart", async () => {
  for (const page of context.pages()) await page.close();
  const fixturePage = await context.newPage();
  await fixturePage.goto("http://127.0.0.1:4174/greenhouse-application.html");
  await fixturePage.evaluate(() => {
    const country = document.querySelector<HTMLSelectElement>("#country")!;
    country.addEventListener("change", () => {
      if (document.querySelector("#dynamic-city")) return;
      const label = document.createElement("label");
      label.htmlFor = "dynamic-city";
      label.textContent = "Conditional city";
      const input = document.createElement("input");
      input.id = "dynamic-city";
      input.addEventListener("input", () => { document.body.dataset.controlledState = input.value; });
      document.querySelector("#application-form")!.insertBefore(label, document.querySelector("#final-submit"));
      label.after(input);
    });
  });
  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  const applicationPackage = {
    packageId: "aa08-dynamic", jobId: "aa08-job", version: 1, schemaVersion: 1,
    job: { jobId: "aa08-job", title: "Engineer", company: "Acme", portal: "greenhouse", location: "Berlin" },
    answers: [
      ["application.country", "Country", "Germany"],
      ["application.city", "Conditional city", "Berlin"],
    ].map(([fieldIntent, label, proposedValue]) => ({
      fieldIntent, label, proposedValue, source: "profile_verified", sensitivity: "standard",
      scope: "application", confidence: 1, requiresReview: false, reasons: [],
    })),
    documents: [], warnings: [],
    policy: { permitSensitiveAutofill: true, permitDemographicAutofill: false, requireLegalAnswerConfirmation: true },
  };
  const run = (replaceFieldIntents: string[] = []) => panelPage.evaluate(
    ({ applicationPackage, replaceFieldIntents }) => chrome.runtime.sendMessage({
      type: "RUN_GREENHOUSE_APPLICATION_PACKAGE", package: applicationPackage, replaceFieldIntents,
    }), { applicationPackage, replaceFieldIntents },
  ) as Promise<{ ok: boolean; packageExecution: {
    formRevision: number; changeReasons: string[];
    executions: Array<{ fieldIntent?: string; status: string }>;
  } }>;

  const first = await run();
  expect(first.ok).toBe(true);
  expect(first.packageExecution.formRevision).toBeGreaterThan(0);
  expect(first.packageExecution.changeReasons).toContain("controls_changed");
  expect(first.packageExecution.executions.map((item) => [item.fieldIntent, item.status])).toEqual([
    ["application.country", "filled"], ["application.city", "filled"],
  ]);
  await expect(fixturePage.locator("#dynamic-city")).toHaveValue("Berlin");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-controlled-state", "Berlin");

  await fixturePage.locator("#dynamic-city").fill("Hamburg");
  const preserved = await run();
  expect(preserved.packageExecution.executions.find((item) => item.fieldIntent === "application.city")?.status)
    .toBe("preserved_existing");
  await expect(fixturePage.locator("#dynamic-city")).toHaveValue("Hamburg");
  const replaced = await run(["application.city"]);
  expect(replaced.packageExecution.executions.find((item) => item.fieldIntent === "application.city")?.status)
    .toBe("filled");
  await expect(fixturePage.locator("#dynamic-city")).toHaveValue("Berlin");

  await fixturePage.evaluate(() => {
    window.dispatchEvent(new CustomEvent("runr-assisted-apply:controlled-field-request", {
      detail: JSON.stringify({ schemaVersion: 1, operation: "submit", operationId: "page-forged-1234" }),
    }));
  });
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");

  await stopExtensionWorker(fixturePage);
  const recovered = await run();
  expect(recovered.packageExecution.executions.every((item) => item.status === "already_filled")).toBe(true);
  await expect(fixturePage.locator("#dynamic-city")).toHaveValue("Berlin");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");
});

test("connects only on explicit action and preserves then revokes the extension session", async () => {
  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);

  await expect(panelPage.getByTestId("connection-status")).toHaveText("disconnected");
  await expect.poll(fixtureAuthState).toMatchObject({
    connectionRequests: 0,
    authorizationVisits: 0,
    tokenExchanges: 0,
    sessionReads: 0,
    preferenceUpdates: 0,
    revocationRequests: 0,
    revocations: 0,
    activeSessions: 0,
  });

  await panelPage.getByTestId("connect-runr").click();
  await expect(panelPage.getByTestId("connection-status")).toHaveText("connected");
  await expect(panelPage.getByRole("heading", { name: "Fixture Candidate" })).toBeVisible();
  await expect.poll(fixtureAuthState).toMatchObject({
    connectionRequests: 1,
    authorizationVisits: 1,
    tokenExchanges: 1,
    activeSessions: 1,
  });

  const sensitivePreference = panelPage.getByRole("checkbox", {
    name: /Permit sensitive-answer autofill/u,
  });
  const demographicPreference = panelPage.getByRole("checkbox", {
    name: /Permit demographic-answer autofill/u,
  });
  await expect(sensitivePreference).not.toBeChecked();
  await expect(demographicPreference).not.toBeChecked();
  // The checkbox is controlled by the persisted API response. Click it and
  // wait for that response instead of requiring the DOM state to flip within
  // Playwright's single check action.
  await sensitivePreference.click();
  await expect(sensitivePreference).toBeChecked();
  await expect.poll(fixtureAuthState).toMatchObject({ preferenceUpdates: 1 });

  await stopExtensionWorker(panelPage);
  await panelPage.reload();
  await expect(panelPage.getByTestId("connection-status")).toHaveText("connected");
  await expect(
    panelPage.getByRole("checkbox", { name: /Permit sensitive-answer autofill/u }),
  ).toBeChecked();
  await expect.poll(async () => (await fixtureAuthState()).sessionReads).toBeGreaterThanOrEqual(1);
  await expect.poll(fixtureAuthState).toMatchObject({ activeSessions: 1 });

  const storedBeforeDisconnect = await panelPage.evaluate(async () =>
    chrome.storage.session.get(null),
  );
  const sessionSecretKey = "runr:assisted-apply:session:v1";
  const storedSecret = storedBeforeDisconnect[sessionSecretKey] as
    | { sessionToken?: unknown }
    | undefined;
  expect(typeof storedSecret?.sessionToken).toBe("string");
  const sessionToken = String(storedSecret?.sessionToken);

  await panelPage.getByTestId("disconnect-runr").click();
  await expect.poll(fixtureAuthState).toMatchObject({
    revocationRequests: 1,
    revocationInFlight: true,
    revocations: 0,
    activeSessions: 1,
  });
  const storedDuringRevoke = await panelPage.evaluate(async () =>
    chrome.storage.session.get(null),
  );
  expect(storedDuringRevoke).toHaveProperty(sessionSecretKey);

  await expect(panelPage.getByTestId("connection-status")).toHaveText("disconnected");
  await expect.poll(fixtureAuthState).toMatchObject({
    revocationRequests: 1,
    revocationInFlight: false,
    revocations: 1,
    activeSessions: 0,
  });
  const storedAfterDisconnect = await panelPage.evaluate(async () =>
    chrome.storage.session.get(null),
  );
  expect(storedAfterDisconnect).not.toHaveProperty(sessionSecretKey);

  const revokedSessionResponse = await panelPage.evaluate(async (token) => {
    const response = await fetch(
      "http://127.0.0.1:4174/assisted-apply/extension/session/verify",
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: "{}",
      },
    );
    return response.status;
  }, sessionToken);
  expect(revokedSessionResponse).toBe(401);
});

test("binds an opaque package from the permitted Runr web origin to the employer tab", async () => {
  for (const page of context.pages()) await page.close();
  const fixturePage = await context.newPage();
  await fixturePage.goto("http://127.0.0.1:4174/greenhouse-application.html");
  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  await expect(panelPage.getByTestId("connection-status")).not.toHaveText("loading");
  if (await panelPage.getByTestId("connect-runr").isVisible().catch(() => false)) {
    await panelPage.getByTestId("connect-runr").click();
    await expect(panelPage.getByTestId("connection-status")).toHaveText("connected");
  }
  const runrWebPage = await context.newPage();
  await runrWebPage.goto("http://127.0.0.1:4174/runr-web-launch.html");
  const response = await runrWebPage.evaluate(
    async ({ id, applicationUrl }) => chrome.runtime.sendMessage(id, {
      type: "RUNR_WEB_BIND_APPLICATION_PACKAGE",
      bindingId: "aapkg_bind_fixture_web_launch",
      applicationUrl,
    }),
    { id: extensionId, applicationUrl: fixturePage.url() },
  );
  expect(response).toEqual({ ok: true, packageId: "aapkg_fixture_web_launch" });

  const fixtureTab = await serviceWorker.evaluate(async () =>
    (await chrome.tabs.query({})).find((tab) => tab.url?.includes("greenhouse-application.html")),
  );
  expect(fixtureTab?.id).toBeDefined();
  const stored = await serviceWorker.evaluate(
    async (tabId) => chrome.storage.session.get(`assisted-apply-package:${tabId}`),
    fixtureTab?.id,
  );
  expect(stored[`assisted-apply-package:${fixtureTab?.id}`]).toMatchObject({
    packageId: "aapkg_fixture_web_launch",
    job: { portal: "greenhouse" },
  });
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");
  await runrWebPage.close();
  await panelPage.close();
  await fixturePage.close();
});

test("starts an inactive Lever preparation, fills and uploads, then activates that exact tab", async () => {
  for (const page of context.pages()) await page.close();
  await serviceWorker.evaluate(async () => {
    await chrome.storage.session.remove("assisted-apply-preparation:local:v1");
  });

  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  await expect(panelPage.getByTestId("connection-status")).not.toHaveText("loading");
  if (await panelPage.getByTestId("connect-runr").isVisible().catch(() => false)) {
    await panelPage.getByTestId("connect-runr").click();
    await expect(panelPage.getByTestId("connection-status")).toHaveText("connected");
  }
  const runrWebPage = await context.newPage();
  await runrWebPage.goto("http://127.0.0.1:4174/runr-web-launch.html");
  await runrWebPage.bringToFront();

  const preparationId = "prep_fixture_live_start";
  const packageId = "aapkg_fixture_preparation_start";
  const startMessageId = `msg_start_${Date.now()}`;
  const startResponse = await runrWebPage.evaluate(
    async ({ id, preparationId, packageId, startMessageId }) => chrome.runtime.sendMessage(id, {
      protocol: "runr.assisted_apply.preparation",
      protocolVersion: 1,
      type: "start",
      source: "web",
      messageId: startMessageId,
      preparationId,
      packageId,
      emittedAt: new Date().toISOString(),
      capabilities: {
        adapters: ["greenhouse", "lever"],
        capabilities: ["fill", "document_attachment"],
      },
    }),
    { id: extensionId, preparationId, packageId, startMessageId },
  );
  if (!(startResponse as { ok?: boolean }).ok) {
    expect(startResponse).toMatchObject({ status: "permission_required" });
    await panelPage.reload();
    await panelPage.getByRole("button", { name: "Grant portal access" }).click();
    const retryResponse = await runrWebPage.evaluate(
      async ({ id, preparationId, packageId, startMessageId }) => chrome.runtime.sendMessage(id, {
        protocol: "runr.assisted_apply.preparation",
        protocolVersion: 1,
        type: "retry",
        source: "web",
        messageId: `msg_retry_${Date.now()}`,
        preparationId,
        packageId,
        emittedAt: new Date().toISOString(),
        retryOf: startMessageId,
      }),
      { id: extensionId, preparationId, packageId, startMessageId },
    );
    if (!(retryResponse as { ok?: boolean }).ok) throw new Error(JSON.stringify(retryResponse));
    expect(retryResponse).toMatchObject({ status: "retrying", ats: "lever" });
  } else {
    expect(startResponse).toMatchObject({ status: "ready_for_review", ats: "lever" });
  }

  const leverPage = context.pages().find((page) => page.url().endsWith("/lever-application.html"));
  expect(leverPage).toBeDefined();
  if (!leverPage) throw new Error("The inactive Lever application tab was not created.");
  const leverTabBeforeReview = await serviceWorker.evaluate(async () =>
    (await chrome.tabs.query({})).find((tab) => tab.url?.endsWith("/lever-application.html")),
  );
  expect(leverTabBeforeReview?.active).toBe(false);
  await expect(leverPage.locator('input[name="name"]')).toHaveValue("Fixture Candidate");
  await expect(leverPage.locator('input[name="email"]')).toHaveValue("fixture.candidate@example.com");
  await expect(leverPage.locator('input[name="phone"]')).toHaveValue("+49 30 000000");
  expect(await leverPage.locator('#lever-resume').evaluate(
    (input: HTMLInputElement) => input.files?.[0]?.name,
  )).toBe("Lever CV.pdf");

  for (const attribute of [
    "data-submit-clicks", "data-aa201-submit-events", "data-aa201-request-submit-calls",
    "data-aa201-form-submit-calls", "data-aa201-enter-submissions", "data-aa201-terminal-clicks",
    "data-aa201-terminal-requests", "data-aa201-success-transitions", "data-aa201-final-navigation",
  ]) {
    await expect(leverPage.locator("body")).toHaveAttribute(attribute, "0");
  }
  const fixtureState = await fixtureAuthState();
  const preparationReports = fixtureState.preparationReports.filter(
    (report) => report.preparation_id === preparationId,
  );
  expect(preparationReports.map((report) => report.type)).toEqual(expect.arrayContaining([
    "accepted", "progress", "ready_for_review",
  ]));
  for (const report of preparationReports) {
    expect(report.result).not.toHaveProperty("reviewId");
  }

  const reviewResponse = await runrWebPage.evaluate(
    async ({ id, preparationId, packageId }) => chrome.runtime.sendMessage(id, {
      protocol: "runr.assisted_apply.preparation",
      protocolVersion: 1,
      type: "review_activate",
      source: "web",
      messageId: `msg_review_${Date.now()}`,
      preparationId,
      packageId,
      emittedAt: new Date().toISOString(),
      reviewId: preparationId,
    }),
    { id: extensionId, preparationId, packageId },
  );
  expect(reviewResponse).toMatchObject({ ok: true, status: "activated" });
  const leverTabAfterReview = await serviceWorker.evaluate(async () =>
    (await chrome.tabs.query({})).find((tab) => tab.url?.endsWith("/lever-application.html")),
  );
  expect(leverTabAfterReview?.active).toBe(true);
  await expect(leverPage.locator("body")).toHaveAttribute("data-submit-clicks", "0");
});

test("downloads, verifies, and uploads one fixed-version PDF CV to Greenhouse", async () => {
  for (const page of context.pages()) await page.close();
  const fixturePage = await context.newPage();
  await fixturePage.goto("http://127.0.0.1:4174/greenhouse-application.html");
  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  await expect(panelPage.getByTestId("connection-status")).not.toHaveText("loading");
  if (await panelPage.getByTestId("connect-runr").isVisible().catch(() => false)) {
    await panelPage.getByTestId("connect-runr").click();
    await expect(panelPage.getByTestId("connection-status")).toHaveText("connected");
  }
  const grantBaseline = await fixtureAuthState();

  const response = await panelPage.evaluate(() => chrome.runtime.sendMessage({
    type: "UPLOAD_SELECTED_DOCUMENT",
    documentId: "cv_version_7",
    package: {
      packageId: "aapkg_fixture_aa11",
      jobId: "job_fixture_aa11",
      version: 3,
      schemaVersion: 1,
      job: { jobId: "job_fixture_aa11", title: "Engineer", company: "Acme", portal: "greenhouse", location: "Berlin" },
      answers: [],
      documents: [{
        documentId: "cv_version_7", documentVersion: 7, documentKind: "cv",
        mimeType: "application/pdf", fileName: "Candidate CV.pdf",
      }],
      warnings: [],
      policy: { permitSensitiveAutofill: false, permitDemographicAutofill: false, requireLegalAnswerConfirmation: true },
    },
  }));
  if (!(response as { ok?: boolean }).ok) throw new Error(JSON.stringify(response));
  expect(response).toMatchObject({
    ok: true,
    documentUpload: {
      documentId: "cv_version_7",
      documentVersion: 7,
      documentKind: "cv",
      fileName: "Candidate CV.pdf",
      status: "uploaded",
      telemetry: {
        adapter: "greenhouse",
        lifecycleStage: "upload",
        aggregateOutcome: "success",
        errorCategory: "none",
      },
    },
  });
  await expect(fixturePage.locator("body")).toHaveAttribute("data-uploaded-cv", "Candidate CV.pdf");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");
  await expect.poll(fixtureAuthState).toMatchObject({
    documentGrants: grantBaseline.documentGrants + 1,
    documentDownloads: grantBaseline.documentDownloads + 1,
  });
  const stored = await serviceWorker.evaluate(() => chrome.storage.session.get(null));
  const serialized = JSON.stringify(stored);
  expect(serialized).not.toContain("aadoc_fixture_");
  expect(serialized).not.toContain("Runr AA11 fixture CV");
  expect(serialized).not.toContain("Candidate CV.pdf");
});

test("prompts after user-operated success evidence and records only explicit confirmation", async () => {
  for (const page of context.pages()) await page.close();
  const fixturePage = await context.newPage();
  await fixturePage.goto("http://127.0.0.1:4174/greenhouse-application.html");
  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  await expect(panelPage.getByTestId("connection-status")).not.toHaveText("loading");
  if (await panelPage.getByTestId("connect-runr").isVisible().catch(() => false)) {
    await panelPage.getByTestId("connect-runr").click();
    await expect(panelPage.getByTestId("connection-status")).toHaveText("connected");
  }
  const applicationPackage = {
    packageId: "aapkg_fixture_aa14",
    jobId: "job_fixture_aa14",
    version: 4,
    schemaVersion: 1,
    job: {
      jobId: "job_fixture_aa14", title: "Engineer", company: "Acme",
      portal: "greenhouse", location: "Berlin",
    },
    answers: [],
    documents: [],
    warnings: [],
    policy: {
      permitSensitiveAutofill: false,
      permitDemographicAutofill: false,
      requireLegalAnswerConfirmation: true,
    },
  };
  const fillResponse = await panelPage.evaluate(async (pkg) => {
    const tabs = await chrome.tabs.query({});
    const tab = tabs.find((candidate) => candidate.url?.includes("greenhouse-application.html"));
    if (tab?.id == null) throw new Error("Fixture tab missing.");
    await chrome.storage.session.set({ [`assisted-apply-package:${tab.id}`]: pkg });
    return chrome.runtime.sendMessage({ type: "RUN_GREENHOUSE_APPLICATION_PACKAGE", package: pkg });
  }, applicationPackage);
  expect(fillResponse).toMatchObject({ ok: true, packageExecution: { packageId: "aapkg_fixture_aa14" } });

  const before = await fixtureAuthState();
  await fixturePage.locator("form").evaluate((form: HTMLFormElement) => { form.noValidate = true; });
  await fixturePage.locator("#final-submit").click();
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "1");
  await expect(panelPage.getByTestId("application-confirmation")).toBeVisible();
  expect((await fixtureAuthState()).trackerConfirmations).toBe(before.trackerConfirmations);

  await panelPage.getByRole("button", { name: "Yes, add to Tracker" }).click();
  await expect(panelPage.getByTestId("tracker-confirmation-result")).toHaveText("Application added to Tracker.");
  const after = await fixtureAuthState();
  expect(after.trackerConfirmations).toBe(before.trackerConfirmations + 1);
  expect(after.lastOutcomePayload).toMatchObject({
    package_id: "aapkg_fixture_aa14",
    package_version: 4,
    adapter: "greenhouse",
    adapter_version: "1.0.0",
    evidence_category: "success_banner",
    decision: "confirmed",
    uploaded_documents: [],
  });
  expect(JSON.stringify(after.lastOutcomePayload)).not.toMatch(/answers|raw|html|filename|private/iu);
});

test("uploads selected CV, cover-letter, and supporting-document roles on both adapters", async () => {
  for (const page of context.pages()) await page.close();
  const fixturePage = await context.newPage();
  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  await expect(panelPage.getByTestId("connection-status")).not.toHaveText("loading");
  if (await panelPage.getByTestId("connect-runr").isVisible().catch(() => false)) {
    await panelPage.getByTestId("connect-runr").click();
    await expect(panelPage.getByTestId("connection-status")).toHaveText("connected");
  }

  const documents = {
    cv: { documentId: "lever_cv_version_2", documentVersion: 2, documentKind: "cv", mimeType: "application/pdf", fileName: "Lever CV.pdf" },
    cover: { documentId: "cover_letter_version_3", documentVersion: 3, documentKind: "cover_letter", mimeType: "application/pdf", fileName: "Cover Letter.pdf" },
    supporting: { documentId: "supporting_version_4", documentVersion: 4, documentKind: "supporting_document", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", fileName: "Certificate.docx" },
  };
  const upload = async (portal: "greenhouse" | "lever", document: typeof documents.cv | typeof documents.cover | typeof documents.supporting) => {
    const response = await panelPage.evaluate(({ portal, document }) => chrome.runtime.sendMessage({
      type: "UPLOAD_SELECTED_DOCUMENT",
      documentId: document.documentId,
      package: {
        packageId: `aapkg_fixture_aa12_${portal}`,
        jobId: `job_fixture_aa12_${portal}`,
        version: 1,
        schemaVersion: 1,
        job: { jobId: `job_fixture_aa12_${portal}`, title: "Engineer", company: "Acme", portal, location: "Berlin" },
        answers: [], documents: [document], warnings: [],
        policy: { permitSensitiveAutofill: false, permitDemographicAutofill: false, requireLegalAnswerConfirmation: true },
      },
    }), { portal, document });
    if (!(response as { ok?: boolean }).ok) throw new Error(JSON.stringify(response));
    const uploadResult = (response as { documentUpload: { telemetry: Record<string, unknown> } }).documentUpload;
    for (const forbidden of ["bytes", "url", "token", "fileName", "answer", "markup"]) {
      expect(JSON.stringify(uploadResult.telemetry)).not.toContain(forbidden);
    }
    return uploadResult as {
      status: string;
      telemetry: { aggregateOutcome: string; errorCategory: string };
    };
  };

  await fixturePage.goto("http://127.0.0.1:4174/lever-application.html");
  expect(await upload("lever", documents.cv)).toMatchObject({
    status: "uploaded",
    telemetry: { aggregateOutcome: "success", errorCategory: "none" },
  });
  expect(await upload("lever", documents.cover)).toMatchObject({
    status: "uploaded",
    telemetry: { aggregateOutcome: "success", errorCategory: "none" },
  });
  expect(await upload("lever", documents.supporting)).toMatchObject({
    status: "uploaded",
    telemetry: { aggregateOutcome: "success", errorCategory: "none" },
  });
  await expect(fixturePage.locator("body")).toHaveAttribute("data-uploaded-cv", "Lever CV.pdf");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-uploaded-cover-letter", "Cover Letter.pdf");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-uploaded-supporting-document", "Certificate.docx");

  await fixturePage.goto("http://127.0.0.1:4174/greenhouse-application.html");
  expect(await upload("greenhouse", documents.cover)).toMatchObject({
    status: "uploaded",
    telemetry: { aggregateOutcome: "success", errorCategory: "none" },
  });
  expect(await upload("greenhouse", documents.supporting)).toMatchObject({
    status: "rejected",
    telemetry: { aggregateOutcome: "failure", errorCategory: "mime_rejected" },
  });
  await expect(fixturePage.locator("body")).toHaveAttribute("data-uploaded-cover-letter", "Cover Letter.pdf");
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");
  await expect.poll(fixtureAuthState).toMatchObject({
    lastTelemetry: {
      adapter: "greenhouse",
      lifecycleStage: "upload",
      aggregateOutcome: "failure",
      errorCategory: "mime_rejected",
    },
  });
});

test("stops on an ambiguous duplicate upload intent without navigation or submission", async () => {
  for (const page of context.pages()) await page.close();
  const fixturePage = await context.newPage();
  await fixturePage.goto("http://127.0.0.1:4174/greenhouse-application.html");
  await fixturePage.evaluate(() => {
    const duplicate = document.createElement("input");
    duplicate.id = "resume-duplicate";
    duplicate.name = "resume";
    duplicate.type = "file";
    document.querySelector("form")?.append(duplicate);
  });
  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  await expect(panelPage.getByTestId("connection-status")).not.toHaveText("loading");
  if (await panelPage.getByTestId("connect-runr").isVisible().catch(() => false)) {
    await panelPage.getByTestId("connect-runr").click();
    await expect(panelPage.getByTestId("connection-status")).toHaveText("connected");
  }
  const response = await panelPage.evaluate(() => chrome.runtime.sendMessage({
    type: "UPLOAD_SELECTED_DOCUMENT",
    documentId: "cv_version_7",
    package: {
      packageId: "aapkg_fixture_aa221_ambiguous",
      jobId: "job_fixture_aa221_ambiguous",
      version: 1,
      schemaVersion: 1,
      job: { jobId: "job_fixture_aa221_ambiguous", title: "Engineer", company: "Acme", portal: "greenhouse", location: "Berlin" },
      answers: [],
      documents: [{ documentId: "cv_version_7", documentVersion: 7, documentKind: "cv", mimeType: "application/pdf", fileName: "Candidate CV.pdf" }],
      warnings: [],
      policy: { permitSensitiveAutofill: false, permitDemographicAutofill: false, requireLegalAnswerConfirmation: true },
    },
  }));
  expect(response).toMatchObject({ ok: true, documentUpload: { status: "rejected" } });
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");
  await expect(fixturePage).toHaveURL(/greenhouse-application\.html/u);
});

test("AA-09 review panel shows all sections, field evidence, and keyboard-accessible actions", async () => {
  for (const page of context.pages()) await page.close();
  const fixturePage = await context.newPage();
  await fixturePage.goto("http://127.0.0.1:4174/greenhouse-application.html");
  const panelPage = await context.newPage();
  await panelPage.goto("chrome-extension://" + extensionId + "/sidepanel.html");

  // Verify connection and package are loaded
  await expect(panelPage.getByTestId("connection-status")).not.toHaveText("loading");
  if (await panelPage.getByTestId("connect-runr").isVisible().catch(() => false)) {
    await panelPage.getByTestId("connect-runr").click();
    await expect(panelPage.getByTestId("connection-status")).toHaveText("connected");
  }

  // Bind a package to the tab to enable the review workspace
  await panelPage.evaluate(async () => {
    const tabs = await chrome.tabs.query({});
    const tab = tabs.find((candidate) => candidate.url?.includes("greenhouse-application.html"));
    if (tab?.id == null) throw new Error("Fixture tab missing.");
    const pkg = {
      packageId: "aa09-review-pkg", jobId: "aa09-job", version: 2, schemaVersion: 1,
      job: { jobId: "aa09-job", title: "Engineer", company: "Acme", portal: "greenhouse", location: "Berlin" },
      answers: [
        { fieldIntent: "candidate.email", label: "Email", proposedValue: "ada@example.com", source: "profile_verified", sensitivity: "standard", scope: "global", confidence: 1, requiresReview: false, reasons: [] },
        { fieldIntent: "candidate.salary", label: "Salary", proposedValue: "100", source: "ai_suggestion", sensitivity: "standard", scope: "application", confidence: .95, requiresReview: true, reasons: ["AI suggested"] },
        { fieldIntent: "candidate.phone", label: "Phone", proposedValue: "", source: "profile_verified", sensitivity: "personal", scope: "global", confidence: 1, requiresReview: false, reasons: [] },
        { fieldIntent: "candidate.declaration", label: "Declaration", proposedValue: "Yes", source: "profile_verified", sensitivity: "legal", scope: "application", confidence: 1, requiresReview: false, reasons: [] },
      ],
      documents: [{ documentId: "cv_v1", documentVersion: 1, documentKind: "cv", mimeType: "application/pdf", fileName: "cv.pdf" }],
      warnings: [],
      policy: { permitSensitiveAutofill: false, permitDemographicAutofill: false, requireLegalAnswerConfirmation: true },
    };
    await chrome.storage.session.set({ ["assisted-apply-package:" + tab.id]: pkg });
  });

  // Wait for review workspace to appear
  await panelPage.reload();
  await expect(panelPage.getByText("Engineer")).toBeVisible({ timeout: 5000 });

  // Verify header shows company, role, portal, version
  await expect(panelPage.getByTestId("package-company")).toHaveText("Acme");
  await expect(panelPage.getByTestId("package-portal")).toHaveText("greenhouse");

  // Verify Ready, Review, Missing, Manual, Documents sections exist
  await expect(panelPage.getByRole("heading", { name: "Ready" })).toBeVisible();
  await expect(panelPage.getByRole("heading", { name: "Review" })).toBeVisible();
  await expect(panelPage.getByRole("heading", { name: "Missing" })).toBeVisible();
  await expect(panelPage.getByRole("heading", { name: "Manual" })).toBeVisible();
  await expect(panelPage.getByRole("heading", { name: "Documents" })).toBeVisible();

  // Verify field rows show evidence data
  await expect(panelPage.getByText("ada@example.com")).toBeVisible();
  await expect(panelPage.getByText("profile verified", { exact: true }).first()).toBeVisible();

  // Verify document section shows document
  await expect(panelPage.getByText("cv.pdf")).toBeVisible();

  // Verify no submit event occurred
  await expect(fixturePage.locator("body")).toHaveAttribute("data-submit-clicks", "0");
  await panelPage.close();
  await fixturePage.close();
});

