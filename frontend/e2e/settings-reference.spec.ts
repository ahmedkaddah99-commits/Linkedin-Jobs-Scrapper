import { test, expect } from "playwright/test";

test("reference settings preserve Jobs and expose subscription and coming-soon emails", async ({ page }) => {
  let reads = 0;
  const writes: string[] = [];
  await page.route("**/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== "GET") writes.push(path);
    if (path.endsWith("/billing/subscription")) {
      reads++;
      return route.fulfill({ json: { plan_id: "free", plan: { display_name: "Runr Free" }, subscription: {} } });
    }
    if (path.endsWith("/settings")) return route.fulfill({ json: { profile: {}, account: { email: "test@example.com" } } });
    if (path.endsWith("/personalized-jobs/preferences")) return route.fulfill({ json: { preferences: { job_functions: ["Engineering"], countries: ["Germany"] } } });
    return route.fulfill({ json: {} });
  });
  await page.goto("/jobs");
  await page.getByRole("link", { name: "Open settings", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(page).toHaveURL(/\/jobs$/);
  await expect(dialog.getByText("Runr Free", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Contact Support")).toHaveCount(0);
  await dialog.getByRole("button", { name: "Refresh Status" }).click();
  await expect.poll(() => reads).toBe(2);
  await page.screenshot({ path: `test-results/settings-subscriptions-${test.info().project.name}.png` });
  await dialog.getByRole("button", { name: "Job Alerts Preference", exact: true }).click();
  await expect(dialog.getByText("Coming soon", { exact: true })).toHaveCount(4);
  await expect(dialog.getByRole("switch", { name: "Enable Instant Job Alerts" })).toBeDisabled();
  await expect(dialog.getByRole("switch", { name: "Enable Digest Job Alerts" })).toBeDisabled();
  await expect(dialog.getByRole("combobox")).toHaveCount(2);
  for (const select of await dialog.getByRole("combobox").all()) await expect(select).toBeDisabled();
  await page.screenshot({ path: `test-results/settings-alerts-${test.info().project.name}.png` });
  expect(await dialog.evaluate(el => el.scrollWidth <= el.clientWidth)).toBeTruthy();
  const badge = dialog.locator(".runr-settings-alert .runr-coming-soon").first();
  expect(await badge.evaluate(el => getComputedStyle(el).backgroundColor)).toBe("rgb(255, 245, 204)");
  await dialog.getByRole("button", { name: /Email Providers/ }).click();
  await expect(dialog.getByRole("button", { name: "Connect email provider" })).toBeDisabled();
  await dialog.getByRole("button", { name: "Login & Security" }).click();
  await expect(dialog.getByRole("button", { name: "Manage security" })).toBeVisible();
  await expect(dialog.getByText("Personal Details", { exact: true })).toHaveCount(0);
  await expect(dialog.getByText("Assisted Apply browser connection")).toHaveCount(0);
  expect(writes).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Open settings", exact: true })).toBeFocused();
});

test("subscription comparison uses real offers and checkout payload", async ({ page }) => {
  let checkout;
  await page.route("https://app.userunr.com/**", async route => {
    const url = new URL(route.request().url());
    const response = await page.request.get(`http://127.0.0.1:4173${url.pathname}${url.search}`);
    await route.fulfill({ response });
  });
  await page.route("**/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/billing/plans")) return route.fulfill({ json: { plans: [
      { plan_id: "free", display_name: "Runr Free", quotas: { cv_exports_per_month: 2 } },
      { plan_id: "runr_pro", display_name: "Runr Pro", quotas: { cv_exports_per_month: -1 }, offers: [
        { offer_id: "one_month", display_name: "Monthly", price: 39.99 },
        { offer_id: "three_months", display_name: "Quarterly", price: 89.99 },
        { offer_id: "one_week", display_name: "Weekly", price: 17.99 },
      ] },
    ] } });
    if (path.endsWith("/billing/subscription")) return route.fulfill({ json: { plan_id: "free", plan: { display_name: "Runr Free" } } });
    if (path.endsWith("/billing/checkout")) {
      checkout = route.request().postDataJSON();
      return route.fulfill({ status: 503, json: { error: { message: "Creem product_id is not configured: PRIVATE" } } });
    }
    return route.fulfill({ json: {} });
  });
  await page.goto("https://app.userunr.com/pricing");
  const comparison = page.getByRole("region", { name: "Subscription plans" });
  await expect(comparison.getByRole("heading", { name: "Monthly" })).toBeVisible();
  await expect(comparison.getByRole("heading", { name: "Quarterly" })).toBeVisible();
  await expect(comparison.getByRole("heading", { name: "Weekly" })).toBeVisible();
  await expect(comparison.getByText("Your Current Plan")).toBeVisible();
  await comparison.locator("article").filter({ has: page.getByRole("heading", { name: "Quarterly" }) }).getByRole("button", { name: "Upgrade Now" }).click();
  await expect.poll(() => checkout).toMatchObject({ plan_id: "runr_pro", offer_id: "three_months", source_page: "/pricing" });
  await expect(page.getByText("Unable to start checkout.", { exact: true })).toBeVisible();
  await expect(page.getByText(/Creem|PRIVATE|Workspaces|Runner credits|Runs \/ month/)).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: `test-results/settings-pricing-${test.info().project.name}.png`, fullPage: true });
});
