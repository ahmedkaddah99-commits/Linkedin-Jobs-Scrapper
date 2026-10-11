import { test, expect } from "playwright/test";

test("connections have separate searchable fields and editable profile, notes and strength", async ({ page }) => {
  const contacts = [
    { contact_id: "one", name: "Jane DoeEngineering Manager at Acme", source_kind: "linkedin_extension", linkedin_url: "https://linkedin.com/in/jane-doe/", metadata: {} },
    { contact_id: "two", name: "Sam Smith", company: "Beta", companies: [{ company_name: "Beta", role_title: "Designer" }], source_kind: "manual", metadata: { notes: "Met at a conference", connection_strength: "Strong" } },
  ];
  let saved;
  await page.route("**/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/referrals") && route.request().method() === "GET") return route.fulfill({ json: { contacts, meta: { returned: contacts.length } } });
    if (path.endsWith("/referrals") && route.request().method() === "POST") {
      saved = route.request().postDataJSON();
      return route.fulfill({ json: { ...saved, contact_id: "three" } });
    }
    return route.fulfill({ json: {} });
  });
  await page.goto("/refer");
  await expect(page.getByRole("link", { name: /Connection$/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Jane Doe", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Add connection", exact: true })).toBeHidden();
  await page.getByRole("searchbox", { name: "Job title", exact: true }).fill("Manager");
  await expect(page.getByRole("heading", { name: "Sam Smith" })).toHaveCount(0);
  await page.getByRole("searchbox", { name: "Company", exact: true }).fill("Beta");
  await expect(page.getByRole("heading", { name: "Jane Doe", exact: true })).toHaveCount(0);
  await page.getByRole("searchbox", { name: "Job title", exact: true }).fill("");
  await expect(page.getByRole("heading", { name: "Sam Smith" })).toBeVisible();
  await page.getByRole("searchbox", { name: "Company", exact: true }).fill("");
  await page.getByRole("button", { name: /Add connection$/ }).click();
  const form = page.locator(".referral-panel");
  await form.getByRole("textbox", { name: "Name", exact: true }).fill("Alex Green");
  await form.getByRole("textbox", { name: "LinkedIn profile", exact: true }).fill("https://linkedin.com/in/alex-green/");
  await form.getByRole("textbox", { name: "Job title", exact: true }).fill("Engineer");
  await form.getByRole("textbox", { name: "Company", exact: true }).fill("Acme");
  await form.getByRole("textbox", { name: "Notes", exact: true }).fill("Met at the conference");
  await form.getByRole("combobox", { name: "Connection strength" }).selectOption("Familiar");
  await page.screenshot({ path: `test-results/connections-form-${test.info().project.name}.png`, fullPage: true });
  await form.getByRole("button", { name: /Add connection$/ }).click();
  await expect(page.getByRole("heading", { name: "Alex Green" })).toBeVisible();
  expect(saved.linkedin_url).toBe("https://linkedin.com/in/alex-green/");
  expect(saved.metadata).toMatchObject({ notes: "Met at the conference", connection_strength: "Familiar" });
  expect(saved.companies[0]).toMatchObject({ company_name: "Acme", role_title: "Engineer" });
  await page.screenshot({ path: `test-results/connections-${test.info().project.name}.png`, fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});

