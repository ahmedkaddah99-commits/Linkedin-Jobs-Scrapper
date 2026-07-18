import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["line"], ["html", { open: "never" }]],
  use: {
    trace: "retain-on-failure",
  },
  webServer: {
    command: "node tests/fixture-server.mjs",
    port: 4174,
    reuseExistingServer: true,
    timeout: 15_000,
  },
});
