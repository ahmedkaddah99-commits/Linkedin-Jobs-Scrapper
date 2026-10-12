import { expect, test } from "playwright/test";

test("search shares the filter actions row without adding header space", async ({ page }, info) => {
  await page.route("**/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/saved-search")) return route.fulfill({ json: { filters: { role: ["Data Analyst"] } } });
    if (path.endsWith("/filter-sets")) return route.fulfill({ json: { filter_sets: [] } });
    if (path.endsWith("/personalized-jobs")) return route.fulfill({ json: { jobs: [], total: 0 } });
    return route.fulfill({ json: {} });
  });
  await page.goto("/jobs");
  const bar = page.locator(".jobs-search-bar");
  await expect(bar.getByRole("button", { name: /All Filters/ })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  const widths = info.project.name.startsWith("mobile") ? [390] : [820, 1024, 1280, 1440, 1700, 1920, 2560];
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 });
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(bar.getByRole("combobox", { name: "Search job title or company" })).toBeVisible();
    await expect(page.locator(".jobs-top-nav .jobs-company-search")).toHaveCount(0);
    if (width > 800) {
      const row = await bar.locator(".jobs-search-bar__actions").evaluate((node) => {
        const search = node.querySelector(".jobs-company-search").getBoundingClientRect();
        const all = node.querySelector("button").getBoundingClientRect();
        return { delta: Math.abs(search.top + search.height / 2 - all.top - all.height / 2), height: node.getBoundingClientRect().height };
      });
      expect(row.delta).toBeLessThan(2);
      expect(row.height).toBeLessThan(45);
    }
    for (const name of ["Location", "Job Function", "Job Type", "Experience Level", "Work Model", "Date Posted", "Industry", "Years of Experience"]) {
      await expect(bar.getByRole("button", { name: new RegExp(name) })).toBeVisible();
    }
    if (width > 800) {
      const geometry = await bar.evaluate((node) => {
        const bounds = node.getBoundingClientRect();
        const children = [...node.children].filter((child) => getComputedStyle(child).display !== "none").map((child) => child.getBoundingClientRect());
        return { height: bounds.height, centers: children.map((rect) => rect.y + rect.height / 2), right: Math.max(...children.map((rect) => rect.right)), viewport: innerWidth };
      });
      expect(geometry.height).toBeLessThan(160);
      await expect(bar.locator(".jobs-quick-filter")).toHaveCount(8);
      const size = await bar.locator(".jobs-filter-pill").first().evaluate((node) => getComputedStyle(node).fontSize);
      expect(parseFloat(size)).toBeGreaterThanOrEqual(14);
      expect(geometry.right).toBeLessThanOrEqual(geometry.viewport);
    }
  }
  await page.setViewportSize({ width: info.project.name.startsWith("mobile") ? 390 : 1280, height: 900 });
  await page.screenshot({ path: `test-results/search-filter-row-${info.project.name}.png` });
  await bar.getByRole("button", { name: /All Filters/ }).click();
  await expect(page.getByRole("dialog", { name: "All Filters" })).toBeVisible();
});
