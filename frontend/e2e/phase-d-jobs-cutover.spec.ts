import { expect, test } from "playwright/test";

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
  await page.route("**/v1/personalized-jobs/job-a", (route) => route.fulfill({ json: job }));
  await page.route("**/v1/personalized-jobs/companies/company-a", (route) => route.fulfill({ json: { name: "Acme Labs", job_count: 1, profile: { fields: {} } } }));
  await page.route("**/v1/personalized-jobs/job-a/*", (route) => route.fulfill({ json: { state: "ok" } }));
});

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
  await page.getByRole("button", { name: "Full job posting" }).click();
  await expect(page.getByText("Original Posting")).toBeVisible();

  const performance = await page.evaluate(() => {
    const navigation = performance.getEntriesByType("navigation")[0];
    return { domContentLoadedMs: navigation?.domContentLoadedEventEnd || null, loadMs: navigation?.loadEventEnd || null };
  });
  console.log(`jobs-production-performance ${JSON.stringify(performance)}`);
  await testInfo.attach("jobs-production-performance.json", { body: JSON.stringify(performance, null, 2), contentType: "application/json" });

  for (const width of [375, 1366, 1920]) {
    await page.setViewportSize({ width, height: width === 375 ? 844 : 1000 });
    await page.screenshot({ path: `../screenshots/phase-d-jobs-${width}.png`, fullPage: true });
  }
});
