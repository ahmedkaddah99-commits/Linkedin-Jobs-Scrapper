import { expect, test } from "playwright/test";

const job = {
  canonical_job_id: "job-profile", company_id: "company-profile", company: "Acme",
  title: "Business Analyst", location: "Berlin", employment_type: "full_time", experience_level: "entry",
  work_arrangement: "hybrid", canonical_url: "https://employer.example/jobs/1", user_facing_url: "https://employer.example/jobs/1",
  apply_url: "https://employer.example/apply/1", application_method: "direct_apply",
  description: "ORIGINAL EMPLOYER TEXT MUST NEVER BE RENDERED",
  original_posting: { description: "ORIGINAL EMPLOYER TEXT MUST NEVER BE RENDERED" },
  description_intelligence: { state: "available", prompt_version: "runr_description_nemo_v3" },
  runr_summary: { overview: "Analyze business processes.", responsibilities: [{ text: "Document requirements." }], required_qualifications: [{ text: "SQL knowledge." }] },
  match_intelligence: { state: "available", score: 72, label: "Good match", coverage: 3,
    dimensions: {
      experience_level: { label: "Experience Level", score: 100, explanation: "Relevant dated work matches the entry level." },
      skill: { label: "Skill", score: 54, explanation: "Required and preferred skills are assessed from the saved profile.", mappings: [{ name: "SQL", status: "supported", profile_evidence: "Created SQL reports", job_evidence: "SQL knowledge required" }] },
      industry_experience: { label: "Industry Exp.", score: 49, explanation: "Profile industry alignment." },
    } },
};

test.beforeEach(async ({ page }) => {
  await page.route("**/v1/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/saved-search')) return route.fulfill({ json: { filters: { role: ['Business Analyst'] } } });
    if (path.endsWith('/personalized-jobs')) return route.fulfill({ json: { jobs: [job], filters: { role: ['Business Analyst'] }, total: 1, evaluation: { state: 'available' } } });
    if (path.endsWith('/job-profile')) return route.fulfill({ json: job });
    if (path.includes('/companies/')) return route.fulfill({ json: { name: 'Acme', profile: { fields: {} } } });
    return route.fulfill({ json: {} });
  });
});

test("cards open a profile-scored detail with external posting and no embedded original", async ({ page }, testInfo) => {
  const details: string[] = [];
  page.on('request', (request) => { if (new URL(request.url()).pathname.endsWith('/job-profile')) details.push(request.url()); });
  await page.goto('/jobs');
  await page.getByRole('button', { name: 'Choose Job Function', exact: true }).click();
  await page.getByRole('textbox', { name: 'Other job functions', exact: true }).fill('Business Analyst');
  await page.getByRole('textbox', { name: 'Other job functions', exact: true }).press('Enter');
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page.locator('.jobs-list-card')).toHaveCount(1);
  await expect(page.locator('.jobs-list-card')).toContainText('72%');
  await expect(page.locator('.jobs-detail-panel')).toHaveCount(0);
  expect(details).toHaveLength(0);
  await page.screenshot({ path: `../data/audit/profile_job_matching_2026-10-07/cards-${testInfo.project.name}.png`, fullPage: true });
  await page.getByRole('button', { name: /Business Analyst/ }).first().click();
  await expect(page).toHaveURL(/\/jobs\/job-profile$/);
  await expect(page.getByRole('heading', { name: 'Business Analyst' })).toBeVisible();
  await expect(page.getByLabel('Profile job match')).toContainText('Experience Level');
  await expect(page.getByLabel('Profile job match')).toContainText('100%');
  await expect(page.getByLabel('Profile job match')).toContainText('54%');
  await expect(page.getByLabel('Profile job match')).toContainText('49%');
  await expect(page.getByRole('link', { name: 'View employer posting' })).toHaveAttribute('href', 'https://employer.example/jobs/1');
  await expect(page.getByRole('link', { name: 'View employer posting' })).toHaveAttribute('target', '_blank');
  await expect(page.locator('body')).not.toContainText('ORIGINAL EMPLOYER TEXT');
  await expect(page.getByRole('radio')).toHaveCount(0);
  await page.getByText('Skill', { exact: true }).click();
  await expect(page.getByText('Created SQL reports', { exact: false })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: `../data/audit/profile_job_matching_2026-10-07/detail-${testInfo.project.name}.png`, fullPage: true });
  await page.getByRole('button', { name: 'Back to jobs' }).click();
  await expect(page.locator('.jobs-list-card')).toBeVisible();
});
