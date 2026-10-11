import { expect, test } from "playwright/test";

test("feature cards remain visible and profile completion opens in one popup", async ({ page }, testInfo) => {
  const settings = { profile: { name: "Ahmed", email: "ahmed@example.com", location: "Berlin" }, account: {} };
  const preferences = { target_roles: ["Analyst"], preferred_locations: ["Berlin"] };
  let resumeUploaded = false;
  await page.route("**/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/documents/upload")) {
      const url = new URL(route.request().url());
      resumeUploaded = route.request().method() === "POST" && url.searchParams.get("asset_kind") === "workspace_cv" && Boolean(route.request().postDataBuffer()?.includes(Buffer.from("Resume evidence")));
      return route.fulfill({ json: {} });
    }
    if (path.endsWith("/settings")) {
      if (route.request().method() === "PUT") Object.assign(settings, route.request().postDataJSON());
      return route.fulfill({ json: settings });
    }
    if (path.endsWith("/personalized-jobs/preferences")) {
      if (route.request().method() === "PUT") Object.assign(preferences, route.request().postDataJSON());
      return route.fulfill({ json: { preferences } });
    }
    if (path.endsWith("/referrals/import/status")) return route.fulfill({ json: { connection_count: 3, last_sync_at: "2026-10-08T12:00:00Z" } });
    return route.fulfill({ json: {} });
  });
  await page.goto("/jobs");
  const rail = page.getByRole("complementary", { name: "Account setup" });
  await expect(rail.getByRole("link", { name: /LinkedIn referrals/ })).toBeVisible();
  await expect(rail.getByRole("link", { name: /Runr Apply/ })).toBeVisible();
  await expect(rail.getByText("Connected", { exact: true })).toBeVisible();
  await expect(rail.getByRole("progressbar", { name: "Profile readiness" })).toHaveAttribute("value", "5");
  if (testInfo.project.name === "desktop-chromium") await expect(rail.getByRole("complementary", { name: "Saved filters" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("feature-cards.png") });
  await rail.getByRole("button", { name: "Finish your profile" }).click();
  const popup = page.getByRole("dialog", { name: "Finish your profile" });
  await expect(popup).toBeVisible();
  await expect(popup.getByRole("heading", { name: "Personal details", exact: true })).toBeVisible();
  await expect(popup.getByRole("heading", { name: "Preferences", exact: true })).toHaveCount(0);
  await popup.getByLabel("Upload resume", { exact: true }).setInputFiles({ name: "resume.txt", mimeType: "text/plain", buffer: Buffer.from("Resume evidence") });
  await expect(popup.getByText("resume.txt uploaded. Your resume is available in Documents.")).toBeVisible();
  expect(resumeUploaded).toBe(true);
  await popup.getByLabel("Role title", { exact: true }).fill("Business Analyst");
  await popup.getByRole("button", { name: "Next", exact: false }).click();
  await expect(popup.getByRole("heading", { name: "Education", exact: true })).toBeVisible();
  await popup.getByRole("button", { name: "Add education" }).click();
  await popup.getByLabel("Institution", { exact: true }).fill("Example University");
  await popup.getByRole("button", { name: "Back", exact: true }).click();
  await expect(popup.getByLabel("Role title", { exact: true })).toHaveValue("Business Analyst");
  await expect(page).toHaveURL(/\/jobs$/);
  await popup.getByRole("button", { name: "Next", exact: false }).click();
  await expect(popup.getByLabel("Institution", { exact: true })).toHaveValue("Example University");
  await popup.getByRole("button", { name: "Next", exact: false }).click();
  await popup.getByRole("button", { name: "Add experience", exact: false }).first().click();
  await popup.getByLabel("Company", { exact: true }).fill("Example Company");
  await popup.getByRole("button", { name: "Next", exact: false }).click();
  await popup.getByRole("button", { name: "Next", exact: true }).click();
  await popup.getByRole("button", { name: "Next", exact: true }).click();
  await popup.getByLabel("Target roles", { exact: true }).fill("Business Analyst");
  await popup.getByLabel("Target roles", { exact: true }).press("Enter");
  await popup.getByLabel("Target roles", { exact: true }).fill("Operations Analyst");
  await popup.getByLabel("Target roles", { exact: true }).press("Enter");
  await popup.getByRole("button", { name: "Remove Analyst", exact: true }).click();
  await popup.getByRole("button", { name: "Save and close", exact: true }).click();
  await expect.poll(() => settings.profile['role_title']).toBe("Business Analyst");
  await expect.poll(() => preferences.target_roles).toEqual(["Business Analyst", "Operations Analyst"]);
  await expect(popup).toHaveCount(0);
  expect(settings.profile['education'][0].institution).toBe("Example University");
  expect(settings.profile['recent_experience'][0].company).toBe("Example Company");
  await expect(page).toHaveURL(/\/jobs$/);
  await expect(rail.getByRole("link", { name: /Runr Apply/ })).toBeVisible();
  await rail.getByRole("button", { name: "Finish your profile" }).click();
  await expect(page.getByRole("dialog").getByLabel("Role title", { exact: true })).toHaveValue("Business Analyst");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("profile-popup.png") });
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("feature checkmarks reflect real connections and disappear when disconnected", async ({ page }) => {
  let linkedinConnected = false;
  await page.addInitScript(() => {
    Object.defineProperty(window, "chrome", { configurable: true, value: { runtime: { sendMessage: (_id, _message, callback) => callback({ ok: true, sync: { extension_connected: true } }) } } });
  });
  await page.route("**/v1/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/referrals/import/status")) return route.fulfill({ json: { connection_count: linkedinConnected ? 4 : 0, last_sync_at: "" } });
    return route.fulfill({ json: {} });
  });
  await page.goto("/jobs");
  const rail = page.getByRole("complementary", { name: "Account setup" });
  const linkedin = rail.getByRole("link", { name: /LinkedIn referrals/ });
  const apply = rail.getByRole("link", { name: /Runr Apply/ });
  await expect(apply.getByText("Connected", { exact: true })).toBeVisible();
  await expect(apply.getByText("check_circle", { exact: true })).toHaveCount(1);
  await expect(linkedin.getByText("Connect LinkedIn", { exact: true })).toBeVisible();
  await expect(linkedin.getByText("check_circle", { exact: true })).toHaveCount(0);
  linkedinConnected = true;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(linkedin.getByText("Connected", { exact: true })).toBeVisible();
  await expect(linkedin.getByText("check_circle", { exact: true })).toHaveCount(1);
  await page.evaluate(() => { window.chrome.runtime.sendMessage = (_id, _message, callback) => callback({ ok: true, sync: { extension_connected: false } }); window.dispatchEvent(new Event("focus")); });
  await expect(apply.getByText("Set up the extension", { exact: true })).toBeVisible();
  await expect(apply.getByText("check_circle", { exact: true })).toHaveCount(0);
});


test("failed preference save keeps the popup and draft available for retry", async ({ page }) => {
  let failSave = true;
  let preferences = { target_roles: ["Analyst"], preferred_locations: ["Berlin"] };
  await page.route("**/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/settings")) return route.fulfill({ json: { profile: { name: "Test user" }, account: {} } });
    if (path.endsWith("/personalized-jobs/preferences")) {
      if (route.request().method() === "PUT") {
        if (failSave) return route.fulfill({ status: 503, json: { error: "Unable to save preferences" } });
        preferences = route.request().postDataJSON();
      }
      return route.fulfill({ json: { preferences } });
    }
    return route.fulfill({ json: {} });
  });
  await page.goto("/jobs");
  await page.getByRole("button", { name: "Finish your profile" }).click();
  const popup = page.getByRole("dialog", { name: "Finish your profile" });
  await popup.getByRole("button", { name: /Preferences/ }).click();
  await popup.getByLabel("Target roles", { exact: true }).fill("Product Designer");
  await popup.getByLabel("Target roles", { exact: true }).press("Enter");
  await popup.getByRole("button", { name: "Remove Analyst", exact: true }).click();
  await popup.getByRole("button", { name: "Save and close" }).click();
  await expect(popup.getByRole("status").last()).toContainText(/save|503/i);
  await expect(popup).toBeVisible();
  await expect(popup.getByRole("button", { name: "Remove Product Designer", exact: true })).toBeVisible();
  failSave = false;
  await popup.getByRole("button", { name: "Save and close" }).click();
  await expect(popup).toHaveCount(0);
  expect(preferences.target_roles).toEqual(["Product Designer"]);
});
