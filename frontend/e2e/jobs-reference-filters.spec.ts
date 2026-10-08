import { expect, test } from "playwright/test";

test("reference quick filters and drawer share multi-select criteria", async ({ page }) => {
  const feeds: URLSearchParams[] = [];
  await page.route("**/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/saved-search")) return route.fulfill({ json: { filters: { role: ["Data Analyst"] } } });
    if (url.pathname.endsWith("/filter-sets")) return route.fulfill({ json: { filter_sets: [] } });
    if (url.pathname.endsWith("/personalized-jobs")) {
      feeds.push(url.searchParams);
      return route.fulfill({ json: { jobs: [], total: 0 } });
    }
    return route.fulfill({ json: {} });
  });
  await page.goto("/jobs");
  await expect.poll(() => feeds.length).toBeGreaterThan(0);
  await page.getByRole("button", { name: /Location/ }).click();
  const location = page.getByRole("group", { name: "Location", exact: true });
  await location.getByRole("combobox").selectOption("Egypt");
  await location.getByRole("textbox", { name: "Cities or areas" }).fill("cai");
  await expect(location.getByRole("button", { name: "Cairo", exact: true })).toBeVisible();
  await location.getByRole("button", { name: "Cairo", exact: true }).click();
  await location.getByRole("button", { name: "Confirm" }).click();
  await expect.poll(() => feeds.at(-1)?.getAll("location")).toEqual(["Cairo"]);
  await page.getByRole("button", { name: /Job Function/ }).first().click();
  const functions = page.getByRole("group", { name: "Job Function", exact: true });
  await functions.getByRole("button", { name: "Finance", exact: true }).hover();
  await expect(functions.getByRole("button", { name: "Backend Engineer", exact: true })).toHaveCount(0);
  await functions.getByRole("button", { name: "Confirm", exact: true }).click();
  await page.getByRole("button", { name: /Work Model/ }).click();
  const menu = page.getByRole("group", { name: "Work Model" });
  await menu.getByLabel("Remote", { exact: true }).check();
  await menu.getByLabel("Hybrid", { exact: true }).check();
  await menu.getByRole("button", { name: "Confirm" }).click();
  await expect.poll(() => feeds.at(-1)?.getAll("work_arrangement")).toEqual(["remote", "hybrid"]);
  await page.getByRole("button", { name: /Years of Experience/ }).click();
  const years = page.getByRole("group", { name: "Years of Experience" });
  await years.getByLabel("Minimum years", { exact: true }).fill("2.5");
  await years.getByLabel("Maximum years", { exact: true }).fill("4");
  await years.getByRole("button", { name: "Confirm" }).click();
  await expect.poll(() => feeds.at(-1)?.get("required_experience_min")).toBe("2.5");
  await page.getByRole("button", { name: /All Filters/ }).click();
  const drawer = page.getByRole("dialog", { name: "All Filters" });
  await expect(drawer.getByLabel("Remote", { exact: true })).toBeChecked();
  await expect(drawer.getByLabel("Hybrid", { exact: true })).toBeChecked();
  await expect(drawer.getByLabel("Minimum years", { exact: true })).toHaveValue("2.5");
  await drawer.getByLabel("Maximum years", { exact: true }).fill("1");
  await expect(drawer.getByRole("button", { name: "Confirm", exact: true })).toBeDisabled();
  await drawer.getByLabel("Open to all experience requirements").check();
  await drawer.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect.poll(() => feeds.at(-1)?.has("required_experience_min")).toBe(false);
  await page.getByRole("button", { name: /All Filters/ }).click();
  await page.screenshot({ path: `test-results/reference-filters-${test.info().project.name}.png` });
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  await expect(page.getByRole("button", { name: /All Filters/ })).toBeFocused();
});
