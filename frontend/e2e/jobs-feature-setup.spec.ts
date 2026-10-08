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
  await expect(popup.getByRole("heading", { name: "Preferences", exact: true })).toBeVisible();
  await popup.getByLabel("Upload resume", { exact: true }).setInputFiles({ name: "resume.txt", mimeType: "text/plain", buffer: Buffer.from("Resume evidence") });
  await expect(popup.getByText("resume.txt uploaded. Your resume is available in Documents.")).toBeVisible();
  expect(resumeUploaded).toBe(true);
  await popup.getByLabel("Role title", { exact: true }).fill("Business Analyst");
  await popup.getByLabel(/Target roles/).fill("Business Analyst, Operations Analyst");
  await popup.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect.poll(() => settings.profile['role_title']).toBe("Business Analyst");
  await expect.poll(() => preferences.target_roles).toEqual(["Business Analyst", "Operations Analyst"]);
  await expect(popup.getByText(/Everything saved/).last()).toBeVisible();
  await popup.evaluate((element) => { element.scrollTop = 0; });
  await page.screenshot({ path: testInfo.outputPath("profile-popup.png") });
  await popup.getByRole("button", { name: "Close profile completion" }).click();
  await expect(popup).toHaveCount(0);
  await expect(rail.getByRole("link", { name: /Runr Apply/ })).toBeVisible();
  await rail.getByRole("button", { name: "Finish your profile" }).click();
  await expect(page.getByRole("dialog").getByLabel("Role title", { exact: true })).toHaveValue("Business Analyst");
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
