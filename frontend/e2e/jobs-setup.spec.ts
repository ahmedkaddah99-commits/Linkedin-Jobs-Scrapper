import { expect, test } from "playwright/test";

test("the retired home opens Jobs with compact expandable setup", async ({ page }, testInfo) => {
  await page.route("**/v1/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/settings")) return route.fulfill({ json: { profile: { name: "Ahmed", email: "ahmed@example.com", location: "Berlin" } } });
    return route.fulfill({ json: {} });
  });
  await page.goto("/home");
  await expect(page).toHaveURL(/\/jobs$/);
  await expect(page.getByRole("navigation", { name: "Jobs navigation" }).getByRole("link", { name: "Home", exact: true })).toHaveCount(0);
  const setup = page.getByRole("complementary", { name: "Account setup" });
  await expect(setup).toBeVisible();
  await expect(setup.getByRole("button", { name: "Finish your profile" })).toBeVisible();
  await expect(setup.getByRole("link", { name: /LinkedIn referrals/ })).toBeVisible();
  await expect(setup.getByRole("link", { name: /Runr Apply/ })).toBeVisible();
  const rail = await setup.boundingBox();
  const jobs = await page.locator(".jobs-workspace").boundingBox();
  expect(rail).toBeTruthy();
  expect(jobs).toBeTruthy();
  if (testInfo.project.name === "desktop-chromium") expect(rail!.x).toBeGreaterThanOrEqual(jobs!.x + jobs!.width);
  else expect(rail!.y + rail!.height).toBeLessThanOrEqual(jobs!.y);
  await page.screenshot({ path: testInfo.outputPath("setup-collapsed.png"), fullPage: true });
});

test("setup stays visible while browsing and reading jobs", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chromium", "Desktop has the persistent side column");
  const job = (id: string) => ({ canonical_job_id: id, company: "Acme", title: `Business Analyst ${id}`, user_state: "none", description_intelligence: { state: "available", prompt_version: "runr_description_nemo_v3" }, runr_summary: { overview: "Analyze business processes. ".repeat(160) } });
  await page.route("**/v1/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/personalized-jobs")) return route.fulfill({ json: { jobs: Array.from({ length: 12 }, (_, index) => job(String(index))), total: 12, next_cursor: null, evaluation: { state: "available" } } });
    if (path.endsWith("/0")) return route.fulfill({ json: job("0") });
    return route.fulfill({ json: {} });
  });
  await page.goto("/jobs");
  await page.getByRole("button", { name: "Choose Job Function", exact: true }).click();
  const input = page.getByRole("textbox", { name: "Other job functions", exact: true });
  await input.fill("Business Analyst");
  await input.press("Enter");
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(page.locator(".jobs-list-card")).toHaveCount(12);
  await expect(page.locator(".jobs-catalog-state")).toHaveCount(0);
  await page.evaluate(() => document.fonts.ready);
  const setup = page.getByRole("complementary", { name: "Account setup" });
  const before = await setup.boundingBox();
  await page.locator(".jobs-list-panel__body").evaluate((element) => { element.scrollTop = 600; });
  expect(await page.locator(".jobs-list-panel__body").evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
  expect((await setup.boundingBox())!.y).toBe(before!.y);
  await expect(setup.getByRole("button", { name: "Finish your profile" })).toBeVisible();
  await page.locator(".jobs-list-panel__body").evaluate((element) => { element.scrollTop = 0; });
  await page.screenshot({ path: testInfo.outputPath("setup-with-jobs.png") });
  await page.getByRole("button", { name: /Business Analyst 0/ }).first().click();
  await expect(page.getByRole("heading", { name: "Business Analyst 0" })).toBeVisible();
  await expect(setup.getByRole("button", { name: "Finish your profile" })).toBeVisible();
  const readerBefore = await setup.boundingBox();
  await page.locator(".jobs-detail-scroll").evaluate((element) => { element.scrollTop = 600; });
  expect(await page.locator(".jobs-detail-scroll").evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
  expect((await setup.boundingBox())!.y).toBe(readerBefore!.y);
  await page.locator(".jobs-detail-scroll").evaluate((element) => { element.scrollTop = 0; });
  await expect(setup.getByRole("link", { name: /LinkedIn referrals/ })).toBeVisible();
  await expect(setup.getByRole("link", { name: /Runr Apply/ })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("setup-expanded-with-posting.png") });
});
