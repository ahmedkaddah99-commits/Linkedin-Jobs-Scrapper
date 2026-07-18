import { describe, expect, it } from "vitest";
import { assistedApplyRuntimeConfig } from "../../src/auth/config";

describe("Assisted Apply runtime configuration", () => {
  it("targets the deployed Runr API, frontend, and Chrome Web Store URL in production", () => {
    expect(assistedApplyRuntimeConfig("production")).toEqual({
      apiBaseUrl: "https://runr-api.onrender.com/v1",
      frontendOrigin: "https://app.userunr.com",
      chromeWebStoreUrl: "https://chromewebstore.google.com/detail/runr-assisted-apply/najcdfohhfgbjpbokhmmekkahghfhegp",
    });
  });

  it("keeps testing traffic on the loopback fixture server", () => {
    expect(assistedApplyRuntimeConfig("testing")).toEqual({
      apiBaseUrl: "http://127.0.0.1:4174",
      frontendOrigin: "http://127.0.0.1:4174",
      chromeWebStoreUrl: "http://127.0.0.1:4174/assisted-apply",
    });
  });
});