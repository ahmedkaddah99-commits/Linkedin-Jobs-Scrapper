import assert from "node:assert/strict";
import test from "node:test";

import { loadTrackerShell } from "../lib/trackerLoading.js";

test("tracker shell load does not run inbox sync", async () => {
  const calls = [];
  const request = async (path) => {
    calls.push(path);
    if (path === "/tracker") return { items: [] };
    if (path === "/tracker/email-integration") return { config: { connected: true } };
    throw new Error(`unexpected request: ${path}`);
  };

  const payload = await loadTrackerShell(request);

  assert.deepEqual(payload, {
    tracker: { items: [] },
    integration: { config: { connected: true } },
  });
  assert.deepEqual(calls.sort(), ["/tracker", "/tracker/email-integration"].sort());
  assert.ok(!calls.includes("/tracker/email-integration/sync"));
});
