import { expect, test } from "playwright/test";

const job = {
  canonical_job_id: "job-a",
  company: "Acme Labs",
  company_id: "company-a",
  title: "Operations Analyst",
  location: "Berlin",
  description: "Operations role",
  work_arrangement: "remote",
  employment_type: "full_time",
  experience_level: "entry",
  apply_url: "https://example.test/apply",
  canonical_url: "https://example.test/job",
  version: 1,
  description_version: { id: "version-job-a", number: 1, content_hash: "hash-job-a" },
  description_intelligence: { state: "available", provider: "deterministic_grounded", prompt_version: "phase_e_summary_v1" },
  runr_summary: { overview: "Operations role", main_responsibilities: ["Coordinate reporting"], essential_requirements: ["SQL"], preferred_qualifications: ["German"] },
  structured_description: { responsibilities: ["Coordinate reporting"], requirements: ["SQL"], skills: ["SQL"], languages: ["German"] },
  original_posting: { version_number: 1, content_hash: "hash-job-a", description: "Operations role" },
  match_intelligence: {
    state: "available",
    v1: { score: 62, matched_keywords: ["SQL"], missing_keywords: ["German"], matched_requirements: ["SQL"], unproven_requirements: ["German"], apparent_non_matches: [], formula: { requirement_coverage: 0.6, keyword_coverage: 0.4 } },
    v2: { score: 78, matched_keywords: ["SQL"], missing_keywords: ["German"], matched_requirements: ["SQL"], unproven_requirements: ["German"], apparent_non_matches: [], matched_evidence: [{ requirement: "SQL", evidence: "Built SQL reports" }], missing_evidence: [{ requirement: "German", reason: "No verified language evidence" }], formula: { semantic_requirement_coverage: 0.45, evidence_coverage: 0.2 } },
    difference: { score_delta: 16, summary: "v2 found evidence-aware support that exact ATS matching did not count." },
    improve_resume: { review_available: true, rewriting_available: false, tailored_documents_available: false },
  },
  evaluation: { state: "available" },
  applicant_intelligence: { state: "unknown" },
  priority: { state: "pending", score: null },
  company_detail: { entity_kind: "employer", profile: { fields: {} } },
  languages: ["German"],
  user_state: "none",
};

test.beforeEach(async ({ page }) => {
  await page.route("**/v1/dashboard", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) }));
  await page.route("**/v1/analytics/events", (route) => route.fulfill({ status: 204, body: "" }));
  await page.route("**/v1/personalized-jobs/saved-search", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ filters: {} }) }));
  await page.route("**/v1/personalized-jobs?**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ jobs: [job], total: 1, evaluation: { state: "available" }, filter_capabilities: {} }) }));
  await page.route("**/v1/personalized-jobs/job-a", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(job) }));
});

test("desktop job intelligence selector and Free evidence review are accessible", async ({ page }, testInfo) => {
  await page.goto("/jobs/job-a");
  await expect(page.getByRole("heading", { name: "Runr Summary" })).toBeVisible();
  await expect(page.getByRole("radio", { name: /v1/ })).toBeVisible();
  await expect(page.getByRole("radio", { name: /v2/ })).toBeVisible();
  await expect(page.getByLabel(/v1 score 62; v2 score 78/)).toBeVisible();
  await page.getByRole("button", { name: /Improve resume/ }).click();
  await expect(page.getByRole("dialog", { name: "Improve Resume" })).toContainText("Matched keywords");
  await expect(page.getByRole("dialog", { name: "Improve Resume" })).toContainText("Missing evidence");
  await expect(page.getByRole("dialog")).toContainText("Never claim experience you cannot verify");
  await page.screenshot({ path: `screenshots/phase-e-job-intelligence-${testInfo.project.name}.png`, fullPage: true });
});
