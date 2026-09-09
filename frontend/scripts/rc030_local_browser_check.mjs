import { chromium } from "playwright";

const uiBaseUrl = String(process.env.RC030_UI_URL || "http://127.0.0.1:4173").replace(/\/+$/, "");
const apiBaseUrl = String(process.env.RC030_API_URL || "http://127.0.0.1:8765/v1").replace(/\/+$/, "");
const userToken = String(process.env.RC030_USER_TOKEN || "").trim();
const adminToken = String(process.env.RC030_ADMIN_TOKEN || "").trim();

if (!userToken || !adminToken) {
  throw new Error("RC030_USER_TOKEN and RC030_ADMIN_TOKEN are required");
}

function authHeaders(token) {
  return { authorization: "Bearer " + token };
}

async function openAuthenticatedPage(browser, token) {
  const page = await browser.newPage();
  await page.route("**/v1/**", async (route) => {
    await route.continue({ headers: { ...route.request().headers(), ...authHeaders(token) } });
  });
  return page;
}

async function verifyUserFlow(browser) {
  await fetch(apiBaseUrl + "/personalized-jobs/job-a/save", {
    method: "DELETE",
    headers: authHeaders(userToken),
  });
  const page = await openAuthenticatedPage(browser, userToken);
  await page.addInitScript(() => {
    window.__rc030OpenedUrl = null;
    window.open = (url) => {
      window.__rc030OpenedUrl = String(url || "");
      return null;
    };
  });
  await page.goto(uiBaseUrl + "/jobs/job-a", { waitUntil: "networkidle" });
  await page.locator('select[aria-label="Location"]').selectOption({ label: "Berlin" });
  await page.getByText(/Showing 1 of 1 jobs/).waitFor({ timeout: 5000 });
  await page.locator(".jobs-detail-toolbar__actions button.jobs-outline-button").filter({ hasText: "Save" }).click();
  await page.getByText("Operations Analyst saved.").waitFor({ timeout: 5000 });
  await page.locator(".jobs-detail-toolbar__actions button.jobs-primary-button").click();
  await page.getByText("The verified employer application opened in a new tab.").waitFor({ timeout: 5000 });
  await page.locator(".jobs-detail-heading button.jobs-outline-button").click();
  await page.getByRole("heading", { name: "Prepare this application with Runr" }).waitFor({ timeout: 5000 });
  const body = await page.locator("body").innerText();
  const result = {
    url: page.url(),
    title: await page.locator(".jobs-detail-heading h1").innerText(),
    company: await page.locator(".jobs-detail-heading p").innerText(),
    filtered_count_visible: body.includes("Showing 1 of 1 jobs"),
    saved_feedback_observed: true,
    apply_feedback_observed: true,
    apply_url_opened: await page.evaluate(() => window.__rc030OpenedUrl),
    preparation_panel_visible: body.includes("Prepare this application with Runr"),
    internal_fields_visible: /observation|source_ats|provenance/i.test(body),
  };
  await page.close();
  return result;
}

async function verifyAdminFlow(browser) {
  const page = await openAuthenticatedPage(browser, adminToken);
  await page.goto(uiBaseUrl + "/admin/events", { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Customer outcomes" }).waitFor({ timeout: 5000 });
  const body = await page.locator("body").innerText();
  const result = {
    url: page.url(),
    dashboard_visible: body.includes("Customer outcomes"),
    funnel_visible: body.includes("Funnel"),
    retention_visible: body.includes("Return retention by signup week"),
    feature_usage_visible: body.includes("Feature usage and return signals"),
    latency_failure_visible: body.includes("Latency and failure context"),
    environment_visible: body.includes("development:"),
  };
  await page.close();
  return result;
}

const browser = await chromium.launch({ headless: true });
try {
  const userFlow = await verifyUserFlow(browser);
  const adminFlow = await verifyAdminFlow(browser);
  const result = { user_flow: userFlow, admin_flow: adminFlow };
  if (
    !userFlow.filtered_count_visible
    || !userFlow.saved_feedback_observed
    || !userFlow.apply_feedback_observed
    || userFlow.apply_url_opened !== "https://boards.greenhouse.io/acme/jobs/a"
    || !userFlow.preparation_panel_visible
    || userFlow.internal_fields_visible
    || Object.values(adminFlow).some((value) => value === false)
  ) {
    throw new Error(JSON.stringify(result));
  }
  console.log(JSON.stringify(result));
} finally {
  await browser.close();
}
