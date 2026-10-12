import { test, expect } from "playwright/test";

test("all candidates show concise details and save how well they are known", async ({ page }) => {
  const contacts = [
    { contact_id: "one", name: "Jane DoeEngineering Manager at Acme", source_kind: "linkedin_extension", linkedin_url: "https://linkedin.com/in/jane-doe/", metadata: {} },
    { contact_id: "two", name: "Sam Smith", company: "Beta", companies: [{ company_name: "Beta", role_title: "Designer | Consultant | Strategist" }], source_kind: "manual", metadata: { notes: "Met at a conference", connection_strength: "Strong" } },
  ];
  let saved;
  let updated;
  let importedUpdated;
  await page.route("**/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/referrals") && route.request().method() === "GET") return route.fulfill({ json: { contacts, meta: { returned: contacts.length } } });
    if (path.endsWith("/referrals") && route.request().method() === "POST") {
      saved = route.request().postDataJSON();
      return route.fulfill({ json: { ...saved, contact_id: "three" } });
    }
    if (path.endsWith("/referrals/two") && route.request().method() === "PUT") {
      updated = route.request().postDataJSON();
      return route.fulfill({ json: { ...updated, contact_id: "two" } });
    }
    if (path.endsWith("/referrals/one") && route.request().method() === "PUT") {
      importedUpdated = route.request().postDataJSON();
      return route.fulfill({ json: { ...importedUpdated, contact_id: "one" } });
    }
    return route.fulfill({ json: {} });
  });
  await page.goto("/refer");
  await expect(page.getByRole("navigation", { name: "Jobs navigation" }).getByRole("link", { name: /Connections$/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Jane Doe", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Add connection", exact: true })).toBeHidden();
  await page.getByRole("searchbox", { name: "Search connections" }).fill("Manager");
  await expect(page.getByRole("heading", { name: "Sam Smith" })).toHaveCount(0);
  await page.getByRole("searchbox", { name: "Search connections" }).fill("Beta");
  await expect(page.getByRole("heading", { name: "Jane Doe", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Sam Smith" })).toBeVisible();
  await page.getByRole("searchbox", { name: "Search connections" }).fill("");
  await expect(page.locator(".referral-contact").filter({ hasText: "Sam Smith" })).not.toContainText("Consultant");
  await expect(page.locator(".referral-contact").filter({ hasText: "Sam Smith" })).not.toContainText("Connected on");
  await page.getByRole("combobox", { name: "How well do you know Sam Smith?" }).selectOption("Know");
  await expect.poll(() => updated?.metadata?.connection_strength).toBe("Know");
  expect(updated.companies[0].role_title).toContain("Designer");
  await page.getByRole("combobox", { name: "How well do you know Jane Doe?" }).selectOption("LinkedIn only");
  await expect.poll(() => importedUpdated?.metadata?.connection_strength).toBe("LinkedIn only");
  expect(importedUpdated.source_kind).toBe("linkedin_extension");
  await page.getByRole("button", { name: /Add connection$/ }).click();
  const form = page.locator(".referral-panel");
  await form.getByRole("textbox", { name: "Name", exact: true }).fill("Alex Green");
  await form.getByRole("textbox", { name: "LinkedIn profile", exact: true }).fill("https://linkedin.com/in/alex-green/");
  await form.getByRole("textbox", { name: "Job title", exact: true }).fill("Engineer");
  await form.getByRole("textbox", { name: "Company", exact: true }).fill("Acme");
  await form.getByRole("textbox", { name: "Notes", exact: true }).fill("Met at the conference");
  await form.getByRole("combobox", { name: "How well do you know them?" }).selectOption("Know");
  await page.screenshot({ path: `test-results/connections-form-${test.info().project.name}.png`, fullPage: true });
  await form.getByRole("button", { name: /Add connection$/ }).click();
  await expect(page.getByRole("heading", { name: "Alex Green" })).toBeVisible();
  expect(saved.linkedin_url).toBe("https://linkedin.com/in/alex-green/");
  expect(saved.metadata).toMatchObject({ notes: "Met at the conference", connection_strength: "Know" });
  expect(saved.companies[0]).toMatchObject({ company_name: "Acme", role_title: "Engineer" });
  await page.screenshot({ path: `test-results/connections-${test.info().project.name}.png`, fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});

