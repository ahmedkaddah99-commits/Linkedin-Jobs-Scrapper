import { expect, test, type Page } from "playwright/test";

const job = {
  canonical_job_id: "job-a",
  company: "Acme Labs",
  company_id: "company-a",
  title: "Operations Analyst",
  location: "Berlin",
  description: "Operations role with reporting and cross-functional coordination.",
  work_arrangement: "hybrid",
  employment_type: "full_time",
  experience_level: "mid",
  apply_url: "https://jobs.greenhouse.io/acme/jobs/1",
  source_ats: "greenhouse",
  observation_url: "https://boards.example/listing/1",
  provenance_url: "https://internal.example/observation/1",
  evaluation: { state: "available" },
  match_intelligence: {
    state: "available",
    v1: { score: 62, missing_keywords: ["German"] },
    v2: { score: 78, missing_keywords: ["German"] },
    difference: { score_delta: 16, summary: "v2 includes evidence-aware support." },
    improve_resume: { review_available: true, rewriting_available: false },
  },
  runr_summary: { overview: "Operations role", main_responsibilities: ["Coordinate reporting"] },
  structured_description: { responsibilities: ["Coordinate reporting"], requirements: ["SQL"] },
  original_posting: { description: "Operations role" },
  applicant_intelligence: { state: "unknown" },
  company_detail: { entity_kind: "employer", profile: { fields: {} } },
  languages: ["English"],
  user_state: "none",
};

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.open = ((url: string) => {
      (window as unknown as { __runrApplyUrl?: string }).__runrApplyUrl = url;
      return null;
    }) as typeof window.open;
  });
  await page.route("**/v1/personalized-jobs/saved-search", (route) => route.fulfill({ json: { filters: {} } }));
  await page.route("**/v1/personalized-jobs?**", (route) => route.fulfill({ json: { jobs: [{ ...job, match_intelligence: { state: "pending" } }], total: 1, evaluation: { state: "partial" }, filter_capabilities: {} } }));
  const userState = { value: "none" };
  await page.route("**/v1/personalized-jobs/job-a", (route) => route.fulfill({ json: { ...job, user_state: userState.value } }));
  await page.route("**/v1/personalized-jobs/companies/company-a", (route) => route.fulfill({ json: { name: "Acme Labs", job_count: 1, profile: { fields: {} } } }));
  await page.route("**/v1/personalized-jobs/job-a/*", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/hide")) userState.value = "hidden";
    if (path.endsWith("/restore")) userState.value = "none";
    if (path.endsWith("/applied")) userState.value = "applied";
    if (path.endsWith("/save") && route.request().method() === "POST") userState.value = "saved";
    if (path.endsWith("/save") && route.request().method() === "DELETE") userState.value = "none";
    return route.fulfill({ json: { state: "ok" } });
  });
});

function percentile(runs: number[], fraction: number): number | null {
  if (!runs.length) return null;
  const ordered = [...runs].sort((a, b) => a - b);
  const position = Math.min(ordered.length - 1, Math.round((ordered.length - 1) * fraction));
  return ordered[position];
}

interface UsefulRun {
  deviceClass: string | null;
  documentLoadMs: number | null;
  feedRequestMs: number | null;
  mode: string;
  phase: string | null;
  revision: string | null;
  usefulMs: number | null;
}

async function collectUsefulReadiness(page: Page, runs = 5): Promise<UsefulRun[]> {
  const collected: UsefulRun[] = [];
  for (let index = 0; index < runs; index += 1) {
    await page.goto("/jobs", { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => performance.getEntriesByName("runr-jobs:useful-render", "mark").length > 0, undefined, { timeout: 15000 });
    collected.push(await page.evaluate((mode: string) => {
      const mark = performance.getEntriesByName("runr-jobs:useful-render", "mark").pop();
      const detail = (mark as PerformanceMark & { detail?: Record<string, unknown> })?.detail || {};
      const navigation = performance.getEntriesByType("navigation")[0];
      return {
        phase: String(detail.phase || "useful-render"),
        deviceClass: detail.deviceClass === undefined ? null : String(detail.deviceClass),
        mode,
        revision: detail.revision === undefined ? null : String(detail.revision),
        usefulMs: mark ? Math.round(mark.startTime) : null,
        feedRequestMs: detail.durationMs === undefined && detail.feedRequestMs === undefined ? null : Number(detail.feedRequestMs ?? detail.durationMs),
        documentLoadMs: navigation?.loadEventEnd || null,
      };
    }, index === 0 ? "cold" : "warm"));
  }
  return collected;
}

test("Jobs production cutover is responsive, keyboard-accessible, truthful, and read-only for acquisition", async ({ page }, testInfo) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/jobs/job-a");
  await expect.poll(() => page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches)).toBe(true);
  await expect(page.getByRole("heading", { name: "Operations Analyst" })).toBeVisible();
  await expect(page.getByText(/Some job fields are unknown|still being evaluated|available intelligence/i)).toBeVisible();
  await expect(page.getByRole("link", { name: "Workspaces" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Runs" })).toHaveCount(0);
  await expect(page.locator("body")).not.toContainText("greenhouse");
  await expect(page.locator("body")).not.toContainText("observation");
  await expect(page.locator("body")).not.toContainText("internal.example");
  await expect(page.locator("body")).not.toContainText("1,284");

  const saveButton = page.locator(".jobs-detail-toolbar__actions button").filter({ hasText: "Save" }).first();
  const applyButton = page.locator(".jobs-detail-toolbar__actions button").filter({ hasText: "Apply" }).first();
  await saveButton.focus();
  await expect(page.locator(":focus")).toHaveAccessibleName(/Save/);
  await expect(applyButton).toBeEnabled();
  await applyButton.click();
  await expect.poll(() => page.evaluate(() => (window as unknown as { __runrApplyUrl?: string }).__runrApplyUrl)).toBe("https://jobs.greenhouse.io/acme/jobs/1");

  await saveButton.click();
  await expect(page.locator(".jobs-detail-toolbar__actions button").filter({ hasText: "Saved" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Hide job" }).click();
  await expect(page.getByRole("button", { name: "Restore job" })).toBeVisible();
  await page.getByRole("button", { name: "Restore job" }).click();
  await expect(page.getByRole("button", { name: "Hide job" })).toBeVisible();
  await page.getByRole("button", { name: "Already applied?" }).click();
  await expect(page.getByRole("button", { name: "Already applied" })).toBeDisabled();
  await page.getByRole("button", { name: "Report job" }).click();
  await expect(page.getByRole("dialog", { name: "Report incorrect filtering" })).toBeVisible();
  await page.getByRole("button", { name: "Send report" }).click();
  await expect(page.locator(".jobs-feedback")).toContainText("report");

  await page.getByRole("button", { name: "Company" }).click();
  await expect(page.getByRole("heading", { name: "Acme Labs" })).toBeVisible();
  await page.getByRole("button", { name: "Overview" }).click();
  await page.getByRole("button", { name: "Employer job description" }).click();
  await expect(page.getByText("Original Posting")).toBeVisible();

  const performance = await page.evaluate(() => {
    const navigation = performance.getEntriesByType("navigation")[0];
    return { domContentLoadedMs: navigation?.domContentLoadedEventEnd || null, loadMs: navigation?.loadEventEnd || null };
  });
  console.log(`jobs-production-performance ${JSON.stringify(performance)}`);
  await testInfo.attach("jobs-production-performance.json", { body: JSON.stringify(performance, null, 2), contentType: "application/json" });

  // Useful Jobs readiness percentiles (p50/p75/p95): time to the first
  // verified card page, truthful empty state, or retryable failure state —
  // measured per reload, not document `load` alone. The current browser
  // project (desktop-chromium or mobile-chromium) labels the device class.
  const usefulRuns = await collectUsefulReadiness(page);
  const usefulTimes = usefulRuns.map((run) => run.usefulMs).filter((value): value is number => value !== null);
  const usefulReadiness = {
    project: testInfo.project.name,
    runs: usefulRuns,
    usefulReadinessMs: { p50: percentile(usefulTimes, 0.5), p75: percentile(usefulTimes, 0.75), p95: percentile(usefulTimes, 0.95), samples: usefulTimes.length },
  };
  console.log(`jobs-useful-readiness ${JSON.stringify(usefulReadiness)}`);
  await testInfo.attach("jobs-useful-readiness.json", { body: JSON.stringify(usefulReadiness, null, 2), contentType: "application/json" });
  expect(usefulReadiness.usefulReadinessMs.p95).toBeLessThan(5000);

  for (const width of [375, 1366, 1920]) {
    await page.setViewportSize({ width, height: width === 375 ? 844 : 1000 });
    await page.screenshot({ path: `../screenshots/phase-d-jobs-${width}.png`, fullPage: true });
  }
});
