import assert from "node:assert/strict";
import test from "node:test";

import {
  clearApiResourceCache,
  getApiResourceCacheEntry,
  setApiResourceCacheEntry,
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
