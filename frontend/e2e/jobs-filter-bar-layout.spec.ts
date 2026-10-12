import { expect, test } from "playwright/test";

test("jobs toolbar stays in one desktop row with usable filters and search", async ({ page }, info) => {
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
    for (const name of ["Location", "Job Function", "Job Type", "Experience Level", "Work Model", "Date Posted", "Industry", "Years of Experience"]) {
      await expect(bar.getByRole("button", { name: new RegExp(name) })).toBeVisible();
    }
    if (width > 800) {
      const geometry = await bar.evaluate((node) => {
        const bounds = node.getBoundingClientRect();
        const children = [...node.children].filter((child) => getComputedStyle(child).display !== "none").map((child) => child.getBoundingClientRect());
        return { height: bounds.height, centers: children.map((rect) => rect.y + rect.height / 2), right: Math.max(...children.map((rect) => rect.right)), viewport: innerWidth };
      });
      expect(geometry.height).toBeLessThan(60);
      expect(Math.max(...geometry.centers) - Math.min(...geometry.centers)).toBeLessThan(2);
      expect(geometry.right).toBeLessThanOrEqual(geometry.viewport);
    }
  }
  await bar.getByRole("button", { name: /All Filters/ }).click();
  await expect(page.getByRole("dialog", { name: "All Filters" })).toBeVisible();
});
