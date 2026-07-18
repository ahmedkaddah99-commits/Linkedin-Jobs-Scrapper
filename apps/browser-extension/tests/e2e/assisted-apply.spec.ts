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
  };
  storage: {
    session: {
      get(keys?: null): Promise<Record<string, unknown>>;
    };
  };
  tabs: {
    query(queryInfo: Record<string, never>): Promise<Array<{ id?: number; url?: string }>>;
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
  await sensitivePreference.check();
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
