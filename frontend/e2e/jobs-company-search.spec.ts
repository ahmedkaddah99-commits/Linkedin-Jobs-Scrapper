import { expect, test } from "playwright/test";

test("company selection works without a function and saved filters survive reload", async ({ page }) => {
  let sets: any[] = [];
  let active: any = {};
  const feeds: URLSearchParams[] = [];
  await page.route("**/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    if (url.pathname.endsWith("/personalized-jobs/companies")) {
      return route.fulfill({ json: { companies: url.searchParams.get("q")?.toLowerCase().includes("acme") ? [{ company_id: "company-a", name: "Acme Labs" }, { company_id: "company-b", name: "Acme Energy" }] : [] } });
    }
    if (url.pathname.endsWith("/saved-search")) return route.fulfill({ json: active });
    if (url.pathname.endsWith("/filter-sets")) {
      if (method === "POST") {
        const body = route.request().postDataJSON();
        const saved = { ...body, filter_set_id: body.filter_set_id || `set-${sets.length + 1}` };
        sets = [saved, ...sets.filter((s) => s.filter_set_id !== saved.filter_set_id)];
        active = { ...saved, active_filter_set_id: saved.filter_set_id };
        return route.fulfill({ json: saved });
      }
      return route.fulfill({ json: { filter_sets: sets } });
    }
    if (url.pathname.endsWith("/activate")) {
      const id = url.pathname.split("/").at(-2);
      active = { ...sets.find((s) => s.filter_set_id === id), active_filter_set_id: id };
      return route.fulfill({ json: active });
    }
    if (method === "DELETE" && url.pathname.includes("/filter-sets/")) {
      const id = url.pathname.split("/").at(-1);
      sets = sets.filter((s) => s.filter_set_id !== id);
      if (active.active_filter_set_id === id) active = {};
      return route.fulfill({ json: { deleted: true } });
    }
    if (url.pathname.endsWith("/personalized-jobs")) {
      feeds.push(url.searchParams);
      return route.fulfill({ json: { jobs: [{ canonical_job_id: "job-a", company: "Acme Labs", title: "Company-only role" }], total: 1, filters: { company_id: url.searchParams.get("company_id"), sort: url.searchParams.get("sort") } } });
    }
    return route.fulfill({ json: {} });
  });
  await page.goto("/jobs");
  const search = page.getByRole("combobox", { name: "Search job title or company" });
  await search.fill("acme");
  await expect(page.getByRole("option", { name: "Acme Labs" })).toBeVisible();
  await search.press("ArrowDown");
  await search.press("Enter");
  await expect(page.locator(".jobs-list-card")).toHaveCount(1);
  await expect(search).toHaveValue("Acme Labs");
  expect(feeds.at(-1)?.get("company_id")).toBe("company-a");
  expect(feeds.at(-1)?.has("role")).toBe(false);
  const bounds = await search.boundingBox();
  const filters = await page.locator(".jobs-search-bar").boundingBox();
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(filters!.y);
  if (!await page.getByRole("button", { name: "Add saved filter" }).isVisible()) await page.getByRole("button", { name: "Saved filters", exact: true }).click();
  await page.getByRole("button", { name: "Add saved filter" }).click();
  await page.getByRole("textbox", { name: "Filter name" }).fill("Acme jobs");
  await page.getByRole("button", { name: "Save current filters", exact: true }).click();
  await expect(page.getByRole("button", { name: "Activate Acme jobs" })).toHaveAttribute("aria-pressed", "true");
  await page.screenshot({ path: `test-results/company-search-${test.info().project.name}.png`, fullPage: true });
  await search.fill("acme");
  await page.getByRole("option", { name: "Acme Energy" }).click();
  await page.getByRole("button", { name: "Add saved filter" }).click();
  await page.getByRole("textbox", { name: "Filter name" }).fill("Energy jobs");
  await page.getByRole("button", { name: "Save current filters", exact: true }).click();
  await expect(page.getByRole("button", { name: "Activate Energy jobs" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Activate Acme jobs" }).click();
  await expect(page.getByRole("button", { name: "Activate Acme jobs" })).toHaveAttribute("aria-pressed", "true");
  await page.reload();
  await expect(page.locator(".jobs-list-card")).toHaveCount(1);
  await expect(search).toHaveValue("Acme Labs");
  if (!await page.getByRole("button", { name: "Edit Acme jobs" }).isVisible()) await page.getByRole("button", { name: "Saved filters", exact: true }).click();
  await page.getByRole("button", { name: "Edit Acme jobs" }).click();
  await page.getByRole("textbox", { name: "Filter name" }).fill("Acme saved");
  await page.getByRole("button", { name: "Update saved filter", exact: true }).click();
  await expect(page.getByRole("button", { name: "Activate Acme saved" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Delete Acme saved" }).click();
  await expect(page.getByRole("button", { name: "Activate Acme saved" })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("button", { name: "Choose Job Function", exact: true })).toBeVisible();
});

test("unmatched company text shows an empty suggestion state without searching the catalog", async ({ page }) => {
  let feedReads = 0;
  await page.route("**/v1/**", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/personalized-jobs")) feedReads++;
    return route.fulfill({ json: url.pathname.endsWith("/companies") ? { companies: [] } : {} });
  });
  await page.goto("/jobs");
  await page.getByRole("combobox", { name: "Search job title or company" }).fill("unknown company");
  await expect(page.getByText("No matching companies" )).toBeVisible();
  expect(feedReads).toBe(0);
});
