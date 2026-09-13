import assert from "node:assert/strict";
import test from "node:test";

import {
  loadTrackerShell,
  loadTrackerIntegration,
  TRACKER_INTEGRATION_REQUEST_TIMEOUT_MS,
  TRACKER_REQUEST_TIMEOUT_MS,
} from "../lib/trackerLoading.js";

test("tracker shell loads only the lightweight board payload", async () => {
  const calls = [];
  const request = async (path, options) => {
    calls.push({ path, options });
    if (path === "/tracker?view=board") return { items: [] };
    throw new Error(`unexpected request: ${path}`);
  };

  const payload = await loadTrackerShell(request);

  assert.deepEqual(payload, {
    tracker: { items: [] },
    integration: null,
  });
  assert.deepEqual(calls, [
    {
      path: "/tracker?view=board",
      options: { timeoutMs: TRACKER_REQUEST_TIMEOUT_MS },
    },
  ]);
  assert.ok(!calls.some((call) => call.path === "/tracker/email-integration"));
});

test("tracker integration is loaded only when the inbox control is opened", async () => {
  const calls = [];
  const request = async (path, options) => {
    calls.push({ path, options });
    return { config: { connected: true } };
  };

  const payload = await loadTrackerIntegration(request);

  assert.deepEqual(payload, { config: { connected: true } });
  assert.deepEqual(calls, [
    {
      path: "/tracker/email-integration",
      options: { timeoutMs: TRACKER_INTEGRATION_REQUEST_TIMEOUT_MS },
    },
  ]);
});
