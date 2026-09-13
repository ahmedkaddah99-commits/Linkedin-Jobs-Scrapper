import assert from "node:assert/strict";
import test from "node:test";
import { resolvePersonalizedJobsDataMode, shouldRetireLegacyJobsNavigation } from "./personalizedJobsConfig.js";

test("legacy navigation retirement requires real mode and its explicit flag", () => {
  assert.equal(shouldRetireLegacyJobsNavigation({}), false);
  assert.equal(
    shouldRetireLegacyJobsNavigation({ VITE_REPLACE_LEGACY_JOBS_NAV: "1" }),
    false,
  );
  assert.equal(
    shouldRetireLegacyJobsNavigation({
      VITE_REPLACE_LEGACY_JOBS_NAV: "true",
      VITE_PERSONALIZED_JOBS_DATA_MODE: "real",
    }),
    true,
  );
  assert.equal(resolvePersonalizedJobsDataMode({ VITE_PERSONALIZED_JOBS_DATA_MODE: "fixture" }), "synthetic");
});
