import { expect, test } from "playwright/test";

test("posting navigation retains the filtered paginated list without another feed query", async ({ page }) => {
  const feeds: string[] = [];
  const job = (id: string) => ({ canonical_job_id: id, company: "Acme", title: `Analyst ${id}`, user_state: "none", description_intelligence: { state: "available", prompt_version: "runr_description_nemo_v3" }, runr_summary: { overview: "Analyze business processes." } });
  await page.route("**/v1/**", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/personalized-jobs")) {
      feeds.push(url.search);
      const second = url.searchParams.has("cursor");
      return route.fulfill({ json: { jobs: [job(second ? "second" : "first")], total: 2, next_cursor: second ? null : "page-two", evaluation: { state: "available" } } });
    }
    if (url.pathname.endsWith("/first")) return route.fulfill({ json: job("first") });
    if (url.pathname.endsWith("/save")) return route.fulfill({ json: {} });
    return route.fulfill({ json: {} });
  });
  await page.goto("/jobs");
  await page.getByRole("button", { name: "Choose Job Function", exact: true }).click();
  const input = page.getByRole("textbox", { name: "Other job functions", exact: true });
  await input.fill("Business Analyst");
  await input.press("Enter");
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(page.locator(".jobs-list-card")).toHaveCount(2);
  expect(feeds).toHaveLength(2);
  await page.getByRole("button", { name: /Analyst first/ }).first().click();
  await expect(page.getByRole("heading", { name: "Analyst first" })).toBeVisible();
  await expect(page.getByText("Analyze business processes.", { exact: true })).toBeVisible();
  expect(feeds).toHaveLength(2);
  await page.locator(".jobs-detail-toolbar").getByRole("button", { name: /Save$/ }).click();
  await expect(page.locator(".jobs-detail-toolbar").getByRole("button", { name: /Saved$/ })).toBeVisible();
  await page.getByRole("button", { name: /Back to jobs/ }).click();
  await expect(page.locator(".jobs-list-card")).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Unsave Analyst first" })).toBeVisible();
  expect(feeds).toHaveLength(2);
  await page.getByRole("button", { name: /Analyst first/ }).first().click();
  await expect(page.getByText("Analyze business processes.", { exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.locator(".jobs-list-card")).toHaveCount(2);
  expect(feeds).toHaveLength(2);
  await page.getByLabel("Sort jobs").selectOption("least_competitive");
  await expect.poll(() => feeds.filter((query) => !new URLSearchParams(query).has("cursor")).length).toBe(2);
  expect(new URLSearchParams(feeds[2]).get("sort")).toBe("least_competitive");
});

test("a direct posting link loads details without querying the feed", async ({ page }) => {
  const feeds: string[] = [];
  const companyRequests: string[] = [];
  await page.route("**/v1/**", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.includes("/personalized-jobs/companies/")) companyRequests.push(url.pathname);
    if (url.pathname.endsWith("/personalized-jobs")) feeds.push(url.search);
    if (url.pathname.endsWith("/direct")) return route.fulfill({ json: { canonical_job_id: "direct", title: "Direct posting", company: "Acme", company_id: "acme", company_profile: { fields: { description: { state: "known", value: "Acme builds useful tools." } } }, description_intelligence: { state: "available", prompt_version: "runr_description_nemo_v3" }, runr_summary: { overview: "Direct posting details." } } });
    return route.fulfill({ json: {} });
  });
  await page.goto("/jobs/direct");
  await expect(page.getByRole("heading", { name: "Direct posting" })).toBeVisible();
  await expect(page.getByText("Direct posting details.", { exact: true })).toBeVisible();
  await expect(page.getByText("Acme builds useful tools.", { exact: true })).toBeVisible();
  expect(companyRequests).toHaveLength(0);
  expect(feeds).toHaveLength(0);
  await page.getByRole("button", { name: /Back to jobs/ }).click();
  await expect(page.getByRole("button", { name: "Choose Job Function", exact: true })).toBeVisible();
  expect(feeds).toHaveLength(0);
});
