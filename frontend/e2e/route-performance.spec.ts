import { expect, test, type Page } from "playwright/test";

const routes = [
  ["home", "/"],
  ["jobs", "/jobs"],
  ["tracker", "/tracker"],
  ["documents", "/documents"],
  ["career-evidence", "/career-evidence"],
  ["career-assets", "/career-assets"],
  ["refer", "/refer"],
  ["settings", "/settings"],
] as const;

const job = {
  canonical_job_id: "job-a",
  company: "Fixture Company",
  company_id: "company-a",
  title: "Operations Analyst",
  location: "Berlin",
  description: "Fixture description",
  apply_url: "https://jobs.example/apply",
  evaluation: { state: "available" },
};

async function installFixture(page: Page) {
  await page.route("**/v1/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/personalized-jobs/saved-search")) return route.fulfill({ json: { filters: {} } });
    if (path.endsWith("/personalized-jobs")) return route.fulfill({ json: { jobs: [job], total: 1, evaluation: { state: "available" }, filter_capabilities: {} } });
    if (path.endsWith("/tracker")) return route.fulfill({ json: { items: [] } });
    if (path.endsWith("/documents")) return route.fulfill({ json: { documents: [], groups: [] } });
    if (path.endsWith("/career-profiles")) return route.fulfill({ json: [] });
    if (path.endsWith("/workspaces")) return route.fulfill({ json: { workspaces: [] } });
    if (path.endsWith("/referrals")) return route.fulfill({ json: { contacts: [], meta: { returned: 0 } } });
    if (path.endsWith("/billing/subscription")) return route.fulfill({ json: { plan_id: "free" } });
    if (path.endsWith("/settings")) return route.fulfill({ json: { account: {}, profile: {}, documents: {} } });
    return route.fulfill({ json: {} });
  });
}

function quantile(values: number[], fraction: number) {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.ceil((sorted.length - 1) * fraction)];
}

test("critical real-mode routes reach a useful card or empty state within the provisional budget", async ({ page }, testInfo) => {
  await installFixture(page);
  const results = [];
  for (const [route, path] of routes) {
    const samples = [];
    for (let index = 0; index < 3; index += 1) {
      await page.goto(path, { waitUntil: "domcontentloaded" });
      await page.waitForFunction((name) => performance.getEntriesByName(`runr-route:${name}:useful-render`, "mark").length > 0, route, { timeout: 10000 });
      const result = await page.evaluate((name) => {
        const ready = performance.getEntriesByName(`runr-route:${name}:useful-render`, "mark").at(-1) as PerformanceMark & { detail?: { state?: string } };
        return { durationMs: Math.round(ready.startTime), state: ready.detail?.state || "unknown" };
      }, route);
      expect(result.state, `${route} must not pass through an error or mount-only state`).toMatch(/^(content|empty)$/);
      samples.push({ ...result, mode: index === 0 ? "cold" : "warm-cache" });
    }
    const times = samples.map((sample) => sample.durationMs);
    const summary = { route, samples, p50: quantile(times, 0.5), p75: quantile(times, 0.75), p95: quantile(times, 0.95) };
    results.push(summary);
    expect(summary.p95, `${route}: readiness regression; inspect route-performance.json`).toBeLessThan(5000);
  }
  const report = { project: testInfo.project.name, results };
  console.log(`route-readiness ${JSON.stringify(report)}`);
  await testInfo.attach("route-performance.json", { body: JSON.stringify(report, null, 2), contentType: "application/json" });
});
