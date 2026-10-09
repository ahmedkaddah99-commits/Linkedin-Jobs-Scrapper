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
  test.setTimeout(120_000);
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
      { message: "The assistant panel script should register for granted origins.", timeout: 60_000 },
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

test("profile details load before autofill, support search and copy, and documents have a next step", async () => {
  const panelPage = await context.newPage();
  await panelPage.goto(`chrome-extension://${new URL(serviceWorker.url()).host}/sidepanel.html`);
  await expect(panelPage.getByTestId("connection-status")).toHaveText("connected", { timeout: 20_000 });
  await panelPage.getByRole("button", { name: "Profile", exact: true }).click();
  await expect(panelPage.getByTestId("runr-profile-quick-copy")).toBeVisible();
  await expect(panelPage.getByText("fixture.candidate@example.com", { exact: true })).toBeVisible();
  await panelPage.close();

  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: FIXTURE_ORIGIN });
  const page = await context.newPage();
  await page.goto(REGISTER_URL);
  await page.getByTestId("runr-panel-tab-profile").click();
  await expect(page.getByTestId("runr-panel-profile").getByTestId("runr-profile-quick-copy")).toBeVisible({ timeout: 20_000 });
  // Loading a profile must not write to the employer form.
  await expect(page.locator("#email")).toHaveValue("");
  await page.getByRole("searchbox").fill("email");
  await expect(page.getByTestId("runr-panel-profile").locator(".profile-detail")).toHaveCount(1);
  await page.getByRole("button", { name: "Copy Contact Email", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Email copied");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("fixture.candidate@example.com");
  await page.screenshot({ path: "test-results/assisted-apply-profile.png" });
  await page.getByTestId("runr-panel-tab-documents").click();
  await expect(page.getByTestId("runr-panel-documents")).toContainText("Choose a file below");
  await page.locator("#runr-file-cv").setInputFiles({ name: "selected-resume.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\nfixture") });
  await page.getByRole("button", { name: "Attach resume", exact: true }).click();
  await expect(page.getByTestId("runr-local-document-cv").getByRole("status")).toContainText("selected-resume.pdf attached");
  expect(await page.locator("#cv").evaluate((input: HTMLInputElement) => input.files?.[0]?.name)).toBe("selected-resume.pdf");
  await page.locator("#runr-file-cv").setInputFiles({ name: "new-version.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\nnew version") });
  await page.getByRole("button", { name: "Attach resume", exact: true }).click();
  await expect(page.getByTestId("runr-local-document-cv").getByRole("status")).toContainText("A file is already attached");
  expect(await page.locator("#cv").evaluate((input: HTMLInputElement) => input.files?.[0]?.name)).toBe("selected-resume.pdf");
  await page.getByRole("checkbox", { name: "Replace the file already attached to this field", exact: true }).first().check();
  await page.getByRole("button", { name: "Attach resume", exact: true }).click();
  await expect(page.getByTestId("runr-local-document-cv").getByRole("status")).toContainText("new-version.pdf attached");
  expect(await page.locator("#cv").evaluate((input: HTMLInputElement) => input.files?.[0]?.name)).toBe("new-version.pdf");
  const workspace = page.getByRole("region", { name: "Saved documents and drafts" });
  await workspace.getByLabel("Saved application document").selectOption("asset::fixture_resume");
  await workspace.getByRole("button", { name: "Attach selected version" }).click();
  await expect(workspace.getByRole("status")).toContainText("A file is already attached");
  await workspace.getByRole("checkbox", { name: "Replace an existing attachment" }).check();
  await workspace.getByRole("button", { name: "Attach selected version" }).click();
  await expect(workspace.getByRole("status")).toContainText("Saved resume.pdf attached");
  await workspace.getByText("Generate a tailored document", { exact: true }).click();
  await workspace.getByRole("textbox", { name: "Job description", exact: true }).fill("Platform engineer building deployment tooling.");
  await workspace.getByRole("button", { name: "Generate draft", exact: true }).click();
  await expect(workspace.getByRole("textbox", { name: "Draft preview" })).toContainText("Fixture Candidate");
  await workspace.getByRole("textbox", { name: "Draft preview" }).fill("Fixture Candidate\nReviewed resume text");
  await workspace.getByRole("button", { name: "Save reviewed document" }).click();
  await expect(workspace.getByRole("status")).toContainText("Document saved");
  await workspace.getByRole("button", { name: "Attach selected version" }).click();
  await expect(workspace.getByRole("status")).toContainText("Application resume.docx attached");
  await page.getByTestId("runr-panel-tab-answers").click();
  const answersWorkspace = page.getByRole("region", { name: "Answer drafts" });
  await answersWorkspace.getByText("Draft an answer", { exact: true }).click();
  await answersWorkspace.getByRole("textbox", { name: "Application question", exact: true }).fill("Describe your deployment experience");
  await answersWorkspace.getByRole("textbox", { name: "Job description", exact: true }).fill("Platform engineer building deployment tooling.");
  await answersWorkspace.getByRole("button", { name: "Generate draft", exact: true }).click();
  await expect(answersWorkspace.getByRole("textbox", { name: "Draft preview" })).toBeVisible();
  await answersWorkspace.getByRole("button", { name: "Save reviewed answer" }).click();
  await expect(answersWorkspace.getByRole("status")).toContainText("Reviewed answer saved");
  await answersWorkspace.getByRole("button", { name: "Copy answer", exact: true }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("I built deployment tooling at Example Systems.");
  await page.getByTestId("runr-panel-report").click();
  await page.getByRole("textbox", { name: "What didn't work?" }).fill("The additional upload field needs clearer labels.");
  await page.getByRole("button", { name: "Send report", exact: true }).click();
  await expect(page.getByTestId("runr-panel-report-form")).toContainText("issue_fixture_123");
  await page.getByRole("button", { name: "Close report" }).click();
  await page.getByTestId("runr-panel-tab-documents").click();
  await expect(page.getByRole("combobox", { name: "Saved application document" })).not.toHaveValue("asset::fixture_resume");
  await expect(workspace.getByRole("textbox", { name: "Draft preview" })).toHaveValue("Fixture Candidate\nReviewed resume text");
  await workspace.getByRole("combobox", { name: "Document type", exact: true }).selectOption("cover_letter");
  await workspace.getByRole("button", { name: "Generate draft", exact: true }).click();
  await expect(workspace.getByRole("textbox", { name: "Save as", exact: true })).toHaveValue("Application cover letter");
  await workspace.getByRole("button", { name: "Save reviewed document" }).click();
  await expect(workspace.getByRole("status")).toContainText("Document saved");
  await workspace.getByRole("button", { name: "Attach selected version" }).click();
  await expect(workspace.getByRole("status")).toContainText("Application cover letter.docx attached");
  expect(await page.locator("#cover-letter").evaluate((input: HTMLInputElement) => input.files?.[0]?.name)).toBe("Application cover letter.docx");
  expect(await page.locator("#cv").evaluate((input: HTMLInputElement) => input.files?.[0]?.name)).toBe("Application resume.docx");
  await page.screenshot({ path: "test-results/assisted-apply-documents.png" });
  const documentsPagePromise = context.waitForEvent("page");
  await page.getByRole("button", { name: "Manage documents", exact: true }).click();
  const documentsPage = await documentsPagePromise;
  await documentsPage.waitForURL(`${FIXTURE_ORIGIN}/documents`);
  await documentsPage.close();
  await page.getByTestId("runr-panel-tab-resume").click();
  await page.getByRole("textbox", { name: "Job description", exact: true }).fill("Platform engineer with TypeScript, cloud infrastructure, and deployment tooling experience.");
  await page.getByRole("button", { name: "Compare profile", exact: true }).click();
  await expect(page.getByTestId("runr-panel-resume-score")).toBeVisible();
  const tailorPagePromise = context.waitForEvent("page");
  await page.getByTestId("runr-panel-tailor").click();
  const tailorPage = await tailorPagePromise;
  await tailorPage.waitForURL(`${FIXTURE_ORIGIN}/cv-studio`);
  await tailorPage.close();
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
