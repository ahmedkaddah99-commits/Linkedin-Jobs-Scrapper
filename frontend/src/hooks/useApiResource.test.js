import assert from "node:assert/strict";
import test from "node:test";

import {
  clearApiResourceCache,
  getApiResourceCacheEntry,
  getApiResourceInFlight,
  setApiResourceCacheEntry,
  setApiResourceInFlight,
} from "./apiResourceCache.js";

test("api resource cache can be primed and cleared by key", () => {
  clearApiResourceCache();
  setApiResourceCacheEntry("quick-apply:workspaces", { workspaces: [{ id: "w1" }] }, 123);

  assert.deepEqual(getApiResourceCacheEntry("quick-apply:workspaces"), {
    data: { workspaces: [{ id: "w1" }] },
    cachedAt: 123,
  });

  clearApiResourceCache("quick-apply:workspaces");
  assert.equal(getApiResourceCacheEntry("quick-apply:workspaces"), null);
});

test("api resource cache tracks and clears in-flight requests by key", async () => {
  clearApiResourceCache();
  const pending = Promise.resolve({ ok: true });

  setApiResourceInFlight("dashboard", pending);
  assert.equal(getApiResourceInFlight("dashboard"), pending);

  await pending;
  await Promise.resolve();

  assert.equal(getApiResourceInFlight("dashboard"), null);
});

test("clearing a cache key also drops its in-flight request", () => {
  clearApiResourceCache();
  const pending = new Promise(() => {});

  setApiResourceInFlight("dashboard", pending);
  clearApiResourceCache("dashboard");

  assert.equal(getApiResourceInFlight("dashboard"), null);
});
