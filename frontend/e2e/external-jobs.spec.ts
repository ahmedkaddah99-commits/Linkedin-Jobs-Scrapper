import { test, expect } from "playwright/test";

test("URL import opens the shared reader and blocked scraping permits manual completion", async ({ page }) => {
  const job = { canonical_job_id: "import_example", title: "Software Engineer", company: "Example",
    location: "Berlin", employment_type: "full_time", experience_level: "mid", work_arrangement: "onsite",
    canonical_url: "https://example.com/jobs/1", job_detail_url: "https://example.com/jobs/1", external_job: true, enrichment_state: "available",
    description_intelligence: { state: "available", prompt_version: "runr_description_nemo_v3" },
    runr_summary: { overview: "Build reliable software.", responsibilities: [{ text: "Maintain customer services." }] },
    original_posting: { description_text: "Responsibilities and requirements for this software engineering position." } };
  let imported = false;
  let blocked = false;
  await page.route("**/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/personalized-jobs/import")) {
      const body = route.request().postDataJSON();
      if (blocked && !body.manual) return route.fulfill({ json: { state: "manual_required", message: "Unable to fetch this job from the URL. Complete the job details below.", fields: { url: body.url, title: "Software Engineer", company: "Example", description: "" } } });
      if (body.manual) expect(body.description.length).toBeGreaterThanOrEqual(100);
      imported = true;
      return route.fulfill({ json: { state: "available", job } });
    }
    if (path.endsWith("/personalized-jobs/external")) return route.fulfill({ json: { jobs: imported ? [job] : [], total: imported ? 1 : 0 } });
    if (path.endsWith("/personalized-jobs/import_example")) return route.fulfill({ json: job });
    return route.fulfill({ json: {} });
  });
  await page.goto("/external-jobs");
  await page.getByRole("textbox", { name: "Job URL", exact: true }).fill("https://example.com/jobs/1");
  await page.getByRole("button", { name: "Add job", exact: true }).click();
  await expect(page.locator(".jobs-reading h1")).toHaveText("Software Engineer");
  await expect(page.getByText("Build reliable software.", { exact: true })).toBeVisible();
  await expect(page.locator(".jobs-detail-toolbar a.jobs-primary-button")).toHaveAttribute("href", job.canonical_url);
  await page.screenshot({ path: `test-results/external-jobs-${test.info().project.name}.png`, fullPage: true });
  await page.getByRole("button", { name: /Back to external jobs$/ }).click();
  blocked = true;
  await page.getByRole("textbox", { name: "Job URL", exact: true }).fill("https://example.com/blocked");
  await page.getByRole("button", { name: "Add job", exact: true }).click();
  await expect(page.getByText(/Unable to fetch this job from the URL/)).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Job title", exact: true })).toHaveValue("Software Engineer");
  await page.getByRole("textbox", { name: "Job description", exact: true }).fill("Responsibilities: Build software and maintain customer services. Requirements: Three years of software experience and Python skills. Full-time role in Berlin.");
  await page.getByRole("button", { name: "Save job", exact: true }).click();
  await expect(page.locator(".jobs-reading h1")).toHaveText("Software Engineer");
});
