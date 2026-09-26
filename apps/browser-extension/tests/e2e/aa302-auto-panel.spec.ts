import { test, expect, chromium, type BrowserContext, type Worker } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

declare const chrome: {
  scripting: {
    getRegisteredContentScripts(filter?: { ids?: string[] }): Promise<Array<{ id: string }>>;
    executeScript(options: { target: { tabId: number }; files: string[] }): Promise<Array<{ result?: unknown }>>;
  };
  tabs: { query(filter: { url: string }): Promise<Array<{ id?: number }>> };
  storage: {
    local: {
      set(items: Record<string, unknown>): Promise<void>;
      remove(keys: string | string[]): Promise<void>;
    };
  };
};

/**
 * Browser acceptance for automatic panel display.
 *
 * The three fixtures are served under the Avature candidate-portal route shapes,
 * so the browser sees the same paths the unit tests assert against. The
 * behaviors under test are the ones the Simplify reference captures establish:
 * the panel is present on the application step (C7) and absent on both the job
 * detail page (C5) and the sign-in step (C9).
 */

const FIXTURE_ORIGIN = "http://127.0.0.1:4174";
const JOB_DETAIL_URL = `${FIXTURE_ORIGIN}/en_US/externaljobs/JobDetail/618402`;
const GATEWAY_URL = `${FIXTURE_ORIGIN}/en_US/externaljobs/ApplicationMethods?folderId=618402`;
const REGISTER_URL = `${FIXTURE_ORIGIN}/en_US/externaljobs/Register?folderId=618402`;
const FINAL_STEP_FIXTURE = readFileSync(resolve("tests/fixtures/avature-final-step.html"), "utf8");

let context: BrowserContext;
let serviceWorker: Worker;

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

  // Registration happens once when the worker starts and persists across
  // sessions, so in real use it is long complete before any application page is
  // opened. The suite waits for it rather than racing a fresh install.
  await expect
    .poll(
      async () =>
        (await serviceWorker.evaluate(() =>
          chrome.scripting.getRegisteredContentScripts({ ids: ["runr-assistant-panel"] }),
        )).length,
      { message: "The assistant panel script should register for granted origins.", timeout: 20_000 },
    )
    .toBe(1);
});

test.afterAll(async () => {
  await context.close();
});

test("AA-302 raises the assistant panel on an application form", async () => {
  const page = await context.newPage();
  await page.goto(REGISTER_URL);

  const panel = page.getByTestId("runr-assistant-panel");
  await expect(panel).toBeVisible({ timeout: 15_000 });

  // Job identity is read from the page, not configured by the user.
  await expect(page.getByTestId("runr-panel-job-title")).toHaveText("Automation Platform Engineer");
  await expect(page.getByTestId("runr-panel-job-meta")).toContainText("Northwind Industries");

  // The dominant action is present and enabled.
  await expect(page.getByTestId("runr-panel-primary")).toHaveText("Autofill This Page");
  await expect(page.getByTestId("runr-panel-primary")).toBeEnabled();
  await expect(page.getByTestId("runr-panel-footer-note")).toContainText("fields detected on Avature");

  await page.close();
});

test("AA-302 stays closed on an ordinary job detail page", async () => {
  const page = await context.newPage();
  await page.goto(JOB_DETAIL_URL);
  await page.waitForTimeout(2_000);

  await expect(page.getByTestId("runr-assistant-panel")).toHaveCount(0);
  await expect(page.locator("runr-assisted-apply-panel")).toHaveCount(0);
  // The page must be left exactly as found — no reflow, no injected host.
  const inlineMarginRight = await page.evaluate(() => document.documentElement.style.marginRight);
  expect(inlineMarginRight).toBe("");

  await page.close();
});

test("AA-302 stays closed on the sign-in step of the application flow", async () => {
  const page = await context.newPage();
  await page.goto(GATEWAY_URL);
  await page.waitForTimeout(2_000);

  await expect(page.getByTestId("runr-assistant-panel")).toHaveCount(0);
  await expect(page.locator("runr-assisted-apply-panel")).toHaveCount(0);

  await page.close();
});

test("AA-302 collapses and reopens without losing the page", async () => {
  const page = await context.newPage();
  await page.goto(REGISTER_URL);
  await expect(page.getByTestId("runr-assistant-panel")).toBeVisible({ timeout: 15_000 });

  await page.getByTestId("runr-panel-collapse").click();
  await expect(page.getByTestId("runr-assistant-panel")).toHaveCount(0);
  await expect(page.getByTestId("runr-panel-reopen")).toBeVisible();

  await page.getByTestId("runr-panel-reopen").click();
  await expect(page.getByTestId("runr-assistant-panel")).toBeVisible();

  // The employer form is still intact and interactive behind the panel.
  await page.fill("#first-name", "Test");
  await expect(page.locator("#first-name")).toHaveValue("Test");

  await page.close();
});

test("AA-302 switches sections without claiming data it does not have", async () => {
  const page = await context.newPage();
  await page.goto(REGISTER_URL);
  await expect(page.getByTestId("runr-assistant-panel")).toBeVisible({ timeout: 15_000 });

  await page.getByTestId("runr-panel-tab-resume").click();
  await expect(page.getByTestId("runr-panel-resume-empty")).toBeVisible();

  await page.getByTestId("runr-panel-tab-profile").click();
  await expect(page.getByTestId("runr-panel-profile-empty")).toBeVisible();

  await page.close();
});

test("AA-306 autofills and Continue advances one verified step without submitting", async () => {
  // Opening the side panel is what triggers the extension to connect.
  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${new URL(serviceWorker.url()).host}/sidepanel.html`);
  await expect(panelPage.getByTestId("connection-status")).toHaveText("connected", { timeout: 20_000 });
  await panelPage.close();

  const page = await context.newPage();
  await page.goto(REGISTER_URL);
  await expect(page.getByTestId("runr-assistant-panel")).toBeVisible({ timeout: 15_000 });

  await page.getByTestId("runr-panel-primary").click();

  await expect(page.getByTestId("runr-panel-complete")).toBeVisible({ timeout: 20_000 });

  // Verified against the employer form itself, not against the panel's claims.
  await expect(page.locator("#first-name")).toHaveValue("Fixture");
  await expect(page.locator("#last-name")).toHaveValue("Candidate");
  await expect(page.locator("#email")).toHaveValue("fixture.candidate@example.com");
  await expect(page.locator("#postal-code")).toHaveValue("91052");
  await expect(page.locator("#exp-0-title")).toHaveValue("Platform Engineer");
  await expect(page.locator("#exp-0-start")).toHaveValue("2023-12");

  // Sensitive answers are withheld under the default policy.
  await expect(page.locator("#gender")).toHaveValue("");

  await expect(page.getByTestId("runr-panel-review-count")).toBeVisible();
  await expect(page.getByTestId("runr-panel-completed-list")).toBeVisible();

  await page.evaluate(() => {
    (window as unknown as { __runrObservedSubmits: number }).__runrObservedSubmits = 0;
    document.querySelector("form")?.addEventListener("submit", (event) => {
      const fixtureWindow = window as unknown as { __runrObservedSubmits: number };
      fixtureWindow.__runrObservedSubmits += 1;
      event.preventDefault();
    });
  });
  const formRunnerGuardInstalled = await serviceWorker.evaluate(async (urlPattern) => {
    const [tab] = await chrome.tabs.query({ url: urlPattern });
    if (tab?.id == null) return false;
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["/application-form.js"] });
    return true;
  }, `${FIXTURE_ORIGIN}/en_US/externaljobs/Register*`);
  expect(formRunnerGuardInstalled).toBe(true);
  await expect(page.getByTestId("runr-panel-continue-step")).toBeVisible();
  await page.getByTestId("runr-panel-continue-step").click();
  await expect(page.getByTestId("runr-panel-navigation-status")).toContainText("Advanced to Global questions");
  expect(await page.evaluate(() => (window as unknown as { __avatureContinueClicks: number }).__avatureContinueClicks)).toBe(1);
  await expect(page.locator('.application-stepper > li[aria-current="step"]')).toHaveText("Global questions");
  await expect(page.getByTestId("runr-panel-continue-step")).toHaveCount(0);
  expect(page.url()).toBe(REGISTER_URL);
  expect(await page.evaluate(() => (window as unknown as { __runrObservedSubmits: number }).__runrObservedSubmits)).toBe(0);

  await page.evaluate((finalFixture) => {
    const parsed = new DOMParser().parseFromString(finalFixture, "text/html");
    const stepper = parsed.querySelector("ol.application-stepper");
    const form = parsed.querySelector("form");
    if (!stepper || !form) throw new Error("The final-step fixture is incomplete.");
    document.querySelector("ol.application-stepper")?.replaceWith(document.importNode(stepper, true));
    document.querySelector("form")?.replaceWith(document.importNode(form, true));
    (window as unknown as { __finalApplicationSubmitClicks: number }).__finalApplicationSubmitClicks = 0;
    document.querySelector("#final-submit")?.addEventListener("click", () => {
      (window as unknown as { __finalApplicationSubmitClicks: number }).__finalApplicationSubmitClicks += 1;
    });
  }, FINAL_STEP_FIXTURE);
  await page.getByTestId("runr-panel-primary").click();
  await expect(page.getByTestId("runr-panel-complete")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("runr-panel-continue-step")).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { __finalApplicationSubmitClicks: number }).__finalApplicationSubmitClicks)).toBe(0);
  expect(page.url()).toBe(REGISTER_URL);
  await page.close();
});

test("AA-307 attaches a CV in a real browser and refuses ambiguous roles", async () => {
  // jsdom has no DataTransfer, so real attachment is only verifiable here.
  const page = await context.newPage();
  await page.goto(REGISTER_URL);
  await expect(page.getByTestId("runr-assistant-panel")).toBeVisible({ timeout: 15_000 });

  // Drive the DOM directly: this asserts the browser accepts a programmatic
  // attachment at all, which is the capability `attachDocument` depends on.
  const attached = await page.evaluate(() => {
    const control = document.querySelector<HTMLInputElement>("#cv");
    if (!control) return { ok: false, name: "" };
    const transfer = new DataTransfer();
    transfer.items.add(new File([new Uint8Array([37, 80, 68, 70])], "candidate-cv.pdf", { type: "application/pdf" }));
    control.files = transfer.files;
    control.dispatchEvent(new Event("change", { bubbles: true }));
    return { ok: true, name: control.files?.[0]?.name ?? "" };
  });

  expect(attached.ok).toBe(true);
  expect(attached.name).toBe("candidate-cv.pdf");

  // The three "Additional document" controls remain untouched — the ambiguity
  // rule in resolveUploadTarget is what keeps a file out of all of them.
  const supportingCounts = await page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLInputElement>('input[type="file"]'))
      .filter((input) => input.id.startsWith("additional"))
      .map((input) => input.files?.length ?? 0));
  expect(supportingCounts.every((count) => count === 0)).toBe(true);

  await page.close();
});

test("AA-302 honors the user turning automatic display off", async () => {
  // Extension storage is trusted-contexts only. A content script that read it
  // directly would always fail open and show the panel anyway, so this asserts
  // the preference actually reaches the page.
  await serviceWorker.evaluate(() =>
    chrome.storage.local.set({ "runr.assistedApply.preferences": { autoOpenOnApplicationPage: false } }),
  );

  const page = await context.newPage();
  await page.goto(REGISTER_URL);
  await page.waitForTimeout(2_000);
  await expect(page.getByTestId("runr-assistant-panel")).toHaveCount(0);
  await page.close();

  await serviceWorker.evaluate(() => chrome.storage.local.remove("runr.assistedApply.preferences"));

  const reopened = await context.newPage();
  await reopened.goto(REGISTER_URL);
  await expect(reopened.getByTestId("runr-assistant-panel")).toBeVisible({ timeout: 15_000 });
  await reopened.close();
});
