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
  await location.getByRole("combobox", { name: "Country", exact: true }).selectOption("Egypt");
  await location.getByRole("combobox", { name: "Cities or areas" }).fill("cai");
  await expect(location.getByRole("option", { name: "Cairo", exact: true })).toBeVisible();
  await location.getByRole("combobox", { name: "Cities or areas" }).press("ArrowDown");
  await location.getByRole("combobox", { name: "Cities or areas" }).press("Enter");
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
  await years.getByRole("switch").uncheck();
  await expect(years.getByLabel("Minimum years", { exact: true })).toHaveValue("0");
  await expect(years.getByLabel("Maximum years", { exact: true })).toHaveValue("0");
  const slider = years.getByLabel("Minimum years", { exact: true });
  const geometry = await slider.evaluate((node) => {
    const style = getComputedStyle(node);
    const track = getComputedStyle(node, "::-webkit-slider-runnable-track");
    const thumb = getComputedStyle(node, "::-webkit-slider-thumb");
    return { padding: style.padding, border: style.borderWidth, height: style.height, trackHeight: track.height, marginTop: thumb.marginTop };
  });
  expect(geometry.padding).toBe("0px");
  expect(geometry.border).toBe("0px");
  await page.screenshot({ path: `test-results/experience-alignment-${test.info().project.name}.png` });
  await expect(slider).toHaveAttribute("max", "10");
  await expect(slider).toHaveAttribute("step", "1");
  await expect(years.getByLabel("Maximum years", { exact: true })).toHaveAttribute("step", "1");
  const bounds = await slider.boundingBox();
  await page.mouse.move(bounds!.x + 8, bounds!.y + bounds!.height / 2);
  await page.mouse.down();
  await page.mouse.move(bounds!.x + bounds!.width / 2, bounds!.y + bounds!.height / 2, { steps: 10 });
  await page.mouse.up();
  await expect(slider).toHaveValue("0");
  await expect(years.getByLabel("Maximum years", { exact: true })).toHaveValue("5");
  await years.getByLabel("Minimum years", { exact: true }).fill("2");
  await years.getByLabel("Maximum years", { exact: true }).fill("4");
  const interval = await years.locator(".runr-range-track").evaluate((node) => ({
    start: node.style.getPropertyValue("--range-start"),
    end: node.style.getPropertyValue("--range-end"),
    paint: getComputedStyle(node, "::before").backgroundImage,
  }));
  expect(interval.start).not.toBe("0%");
  expect(interval.end).not.toBe("100%");
  expect(interval.paint).toContain("198, 209, 220");
  await page.screenshot({ path: `test-results/experience-interval-${test.info().project.name}.png` });
  await years.getByRole("button", { name: "Confirm" }).click();
  await expect.poll(() => feeds.at(-1)?.get("required_experience_min")).toBe("2");
  await page.getByRole("button", { name: /All Filters/ }).click();
  const drawer = page.getByRole("dialog", { name: "All Filters" });
  await expect(drawer.getByLabel("Remote", { exact: true })).toBeChecked();
  await expect(drawer.getByLabel("Hybrid", { exact: true })).toBeChecked();
  await expect(drawer.getByLabel("Minimum years", { exact: true })).toHaveValue("2");
  await drawer.getByRole("switch", { name: "Open to all experience requirements" }).check();
  await drawer.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect.poll(() => feeds.at(-1)?.has("required_experience_min")).toBe(false);
  await page.getByRole("button", { name: /All Filters/ }).click();
  await page.screenshot({ path: `test-results/reference-filters-${test.info().project.name}.png` });
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  await expect(page.getByRole("button", { name: /All Filters/ })).toBeFocused();
});


test("saved-filter plus opens the drawer and saves its draft", async ({ page }) => {
  let saved: any = null;
  await page.route("**/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/saved-search")) return route.fulfill({ json: {} });
    if (url.pathname.endsWith("/filter-sets")) {
      if (route.request().method() === "POST") { saved = route.request().postDataJSON(); return route.fulfill({ json: { ...saved, filter_set_id: "new" } }); }
      return route.fulfill({ json: { filter_sets: [] } });
    }
    return route.fulfill({ json: { jobs: [], total: 0 } });
  });
  await page.goto("/jobs");
  const rail = page.getByRole("button", { name: "Saved filters", exact: true });
  await expect(rail).toBeVisible();
  if (await rail.getAttribute("aria-expanded") !== "true") await rail.click();
  await page.getByRole("button", { name: "Add saved filter" }).click();
  const drawer = page.getByRole("dialog", { name: "All Filters" });
  await expect(drawer.getByRole("switch", { name: "Confirm and save" })).toBeChecked();
  await drawer.getByRole("textbox", { name: "Filter name" }).fill("New remote search");
  await drawer.getByLabel("Remote", { exact: true }).check();
  await drawer.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(drawer).toHaveCount(0);
  expect(saved.name).toBe("New remote search");
  expect(saved.filters.work_arrangement).toEqual(["remote"]);
});
