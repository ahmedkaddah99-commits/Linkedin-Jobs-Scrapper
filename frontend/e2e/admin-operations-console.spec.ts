import { expect, test } from "playwright/test";

const overview = {
  jobs_found: 1789,
  current_live_jobs: 217,
  review: { approved: 15, needs_review: 3 },
  imports: { paused: false, status: "ready" },
  history: [],
  worker: { status: "ready" },
  estimated_spend_today: { known: true, credits: 0, currency: "credits" },
  last_publication: { publication_id: "pub-safe-head" },
};

function responseFor(pathname: string) {
  if (pathname.endsWith("/admin/acquisition/overview")) return overview;
  if (pathname.endsWith("/admin/acquisition/analytics")) return { read_only: true, providers_activated: false, window: { timezone: "UTC", boundary: "start inclusive, end exclusive" }, summary: {}, funnel: [], sources: [], quality: {}, enrichment: {}, publication: { current_head: { publication_id: "pub-safe-head", job_count: 217 } }, operations: [] };
  if (pathname.endsWith("/admin/acquisition/sources")) return { sources: [{ id: "source-1", name: "Official careers", company: "Runr Fixture", connector: "direct", status: "ready", max_pages: 1, jobs_found: 217 }] };
  if (pathname.endsWith("/admin/acquisition/connectors/capabilities")) return { connectors: [{ connector: "direct", target_id: "source-1", completeness_state: "bounded" }] };
  if (pathname.endsWith("/admin/acquisition/jobs")) return { jobs: [{ canonical_job_id: "job-1", title: "Operations Analyst", company: "Runr Fixture", location: "Berlin", source: "direct", publication_state: "published", apply_url: "https://example.test/apply" }], total: 1 };
  if (pathname.endsWith("/admin/acquisition/jobs/job-1")) return { job: { canonical_job_id: "job-1", title: "Operations Analyst", location_raw: "Berlin" }, company: { name: "Runr Fixture" }, apply_url: { status: "present", user_facing_url: "https://example.test/apply" }, completeness: { overall_percent: 100, critical_checks: [] }, admin: { connector: "direct", publication_status: "published" } };
  if (pathname.endsWith("/admin/acquisition/imports")) return { imports: [] };
  if (pathname.endsWith("/admin/acquisition/imports/import-1")) return { import_id: "import-1", status: "completed", source_ids: ["source-1"], scope: {}, plan: {} };
  if (pathname.endsWith("/admin/acquisition/companies")) return { companies: [{ company_id: "company-1", canonical_name: "Runr Fixture", job_count: 1, urls: [] }] };
  if (pathname.endsWith("/admin/acquisition/companies/company-1")) return { company: { company_id: "company-1", canonical_name: "Runr Fixture", job_count: 1, urls: [] } };
  if (pathname.endsWith("/admin/acquisition/duplicates")) return { clusters: [] };
  if (pathname.endsWith("/admin/acquisition/rules")) return { rules: [] };
  if (pathname.endsWith("/admin/acquisition/reprocessing/plan")) return { enabled: false };
  if (pathname.endsWith("/admin/acquisition/reprocessing")) return { runs: [] };
  if (pathname.endsWith("/admin/acquisition/publication")) return { automatic_promotion: false, current_job_count: 217, head: { publication_id: "pub-safe-head", status: "valid" }, publication_states: [] };
  if (pathname.endsWith("/admin/acquisition/live-catalog")) return { publication: { publication_id: "pub-safe-head", published_at: "2026-08-12T00:00:00Z" }, jobs: [], total: 217 };
  if (pathname.endsWith("/admin/acquisition/audit")) return { events: [], total: 0 };
  if (pathname.endsWith("/admin/enrichment/capabilities")) return { capabilities: [], providers_activated: false };
  if (pathname.endsWith("/admin/enrichment/runs")) return { runs: [] };
  if (pathname.endsWith("/admin/enrichment/plans")) return { plans: [] };
  if (pathname.endsWith("/admin/enrichment/proposals")) return { proposals: [] };
  if (pathname.endsWith("/admin/enrichment/budgets")) return { budgets: [], external_budget: 0 };
  if (pathname.endsWith("/admin/acquisition/rollout/health")) return { status: "ready", providers_enabled: false, ai_enabled: false, external_budget: 0 };
  if (pathname.endsWith("/admin/users/health")) return { status: "healthy", users: 1 };
  if (pathname.endsWith("/admin/scrapeops/usage")) return { usage: { totals: {}, by_request_mode: [], by_domain: [], by_run: [] }, reconciliation: { account_state: { status: "disabled", summary: "Provider disabled" }, discrepancy: 0 }, policy: { enabled: false }, alerts: { latest: [], series: [] } };
  if (pathname.endsWith("/admin/events")) return { events: [], meta: { total: 0, returned: 0, offset: 0, limit: 50 } };
  if (pathname.endsWith("/admin/promo-codes")) return { promo_codes: [] };
  if (pathname.endsWith("/admin/users")) return { users: [] };
  if (pathname.endsWith("/admin/tokens")) return { tokens: [] };
  if (pathname.endsWith("/admin/secrets")) return { secrets: [] };
  if (pathname.endsWith("/admin/templates")) return { templates: [] };
  if (pathname.endsWith("/admin/workers")) return { workers: [] };
  return {};
}

test.beforeEach(async ({ page }) => {
  await page.route("http://127.0.0.1:*/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith("/analytics/events") && request.method() === "POST") {
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    expect(request.method(), `unexpected production-like mutation to ${request.url()}`).toBe("GET");
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(responseFor(url.pathname)) });
  });
});

test("canonical admin routes remain in one shell without automatic mutations", async ({ page }) => {
  const externalReads: string[] = [];
  page.on("request", (request) => {
    const pathname = new URL(request.url()).pathname;
    if (pathname.endsWith("/admin/scrapeops/usage") || pathname.endsWith("/admin/promo-codes")) externalReads.push(pathname);
  });
  const routes = [
    "/admin", "/admin/analytics?range=24h&timezone=UTC", "/admin/acquisition/sources",
    "/admin/acquisition/imports", "/admin/acquisition/imports/import-1", "/admin/acquisition/jobs",
    "/admin/acquisition/jobs/job-1?source=direct", "/admin/acquisition/companies",
    "/admin/acquisition/companies/company-1", "/admin/acquisition/enrichment", "/admin/acquisition/data-quality",
    "/admin/acquisition/rules", "/admin/acquisition/reprocessing", "/admin/acquisition/duplicates",
    "/admin/acquisition/publication", "/admin/acquisition/live-catalog", "/admin/acquisition/audit",
    "/admin/system", "/admin/provider-policy", "/admin/events", "/admin/promotions", "/admin/access",
  ];
  for (const route of routes) {
    await page.goto(route);
    await expect(page.locator('nav[aria-label="Admin operations navigation"]')).toHaveCount(1);
    await expect(page.locator(".admin-sidebar")).toHaveCount(1);
    await expect(page.getByText("This page could not be displayed")).toHaveCount(0);
  }
  expect(externalReads, "provider and billing reads must be explicitly requested").toEqual([]);
});

test("legacy admin URLs redirect safely", async ({ page }) => {
  await page.goto("/admin/acquisition/analytics?range=30d&timezone=Europe%2FBerlin&token=secret");
  await expect(page).toHaveURL(/\/admin\/analytics\?range=30d&timezone=Europe%2FBerlin$/);
  await page.goto("/admin/job-import?canonical_job_id=job-1&token=secret");
  await expect(page).toHaveURL(/\/admin\/acquisition\/jobs\/job-1$/);
  await page.goto("/admin/scrapeops?workspace_id=w1&write=true");
  await expect(page).toHaveURL(/\/admin\/provider-policy\?workspace_id=w1$/);
});

test("desktop, tablet, and mobile console states are visible", async ({ page }, testInfo) => {
  for (const viewport of [{ width: 1440, height: 900 }, { width: 768, height: 1024 }, { width: 375, height: 812 }]) {
    await page.setViewportSize(viewport);
    await page.goto("/admin");
    await expect(page.getByRole("heading", { name: "Operations overview" })).toBeVisible();
    if (viewport.width <= 820) {
      await page.getByRole("button", { name: "Open navigation" }).click();
      await expect(page.locator(".admin-sidebar--mobile-open")).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(page.locator(".admin-sidebar--mobile-open")).toHaveCount(0);
      await page.waitForTimeout(250);
    }
    await page.screenshot({ path: `screenshots/admin-console-${viewport.width}x${viewport.height}-${testInfo.project.name}.png`, fullPage: true });
  }
});

test("command palette, empty, error, and unknown-route states preserve the shell", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.locator('nav[aria-label="Admin operations navigation"]')).toHaveCount(1);
  await page.evaluate(() => document.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true })));
  await expect(page.getByRole("dialog", { name: "Admin command palette" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Admin command palette" })).toHaveCount(0);

  await page.unroute("http://127.0.0.1:*/v1/**");
  await page.route("http://127.0.0.1:*/v1/admin/acquisition/jobs?**", (route) => route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ detail: "Forbidden" }) }));
  await page.goto("/admin/acquisition/jobs");
  await expect(page.locator('nav[aria-label="Admin operations navigation"]')).toHaveCount(1);
  await expect(page.getByText(/Forbidden|could not be loaded/i)).toBeVisible();

  await page.goto("/admin/does-not-exist");
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
  await expect(page.locator('nav[aria-label="Admin operations navigation"]')).toHaveCount(1);
});
