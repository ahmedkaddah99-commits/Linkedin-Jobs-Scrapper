import assert from "node:assert/strict";
import test from "node:test";

import {
  loadTrackerShell,
  TRACKER_INTEGRATION_REQUEST_TIMEOUT_MS,
  TRACKER_REQUEST_TIMEOUT_MS,
} from "../lib/trackerLoading.js";

test("tracker shell load does not run inbox sync", async () => {
  const calls = [];
  const request = async (path, options) => {
    calls.push({ path, options });
    if (path === "/tracker") return { items: [] };
    if (path === "/tracker/email-integration") return { config: { connected: true } };
    throw new Error(`unexpected request: ${path}`);
  };

  const payload = await loadTrackerShell(request);

  assert.deepEqual(payload, {
    tracker: { items: [] },
    integration: { config: { connected: true } },
  });
  assert.deepEqual(calls.sort((left, right) => left.path.localeCompare(right.path)), [
    {
      path: "/tracker",
      options: { timeoutMs: TRACKER_REQUEST_TIMEOUT_MS },
    },
    {
      path: "/tracker/email-integration",
      options: { timeoutMs: TRACKER_INTEGRATION_REQUEST_TIMEOUT_MS },
    },
  ]);
  assert.ok(!calls.some((call) => call.path === "/tracker/email-integration/sync"));
});
