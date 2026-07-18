import { describe, expect, it } from "vitest";
import { assistedApplyRuntimeConfig } from "../../src/auth/config";

describe("Assisted Apply runtime configuration", () => {
  it("targets the deployed Runr API and frontend in production", () => {
    expect(assistedApplyRuntimeConfig("production")).toEqual({
      apiBaseUrl: "https://runr-api.onrender.com/v1",
      frontendOrigin: "https://app.userunr.com",
    });
  });

  it("keeps testing traffic on the loopback fixture server", () => {
    expect(assistedApplyRuntimeConfig("testing")).toEqual({
      apiBaseUrl: "http://127.0.0.1:4174",
      frontendOrigin: "http://127.0.0.1:4174",
    });
  });
});
