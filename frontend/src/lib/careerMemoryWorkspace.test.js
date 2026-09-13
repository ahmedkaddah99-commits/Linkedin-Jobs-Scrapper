import assert from "node:assert/strict";
import test from "node:test";

import {
  LEGACY_TAB_MAP,
  MEMORY_BUILDER_TABS,
} from "./careerMemoryWorkspace.js";

// CP-035: Primary navigation is exactly 7 lifecycle destinations.
test("MEMORY_BUILDER_TABS contains all seven lifecycle destinations in order", () => {
  const ids = MEMORY_BUILDER_TABS.map((tab) => tab.id);
  const labels = MEMORY_BUILDER_TABS.map((tab) => tab.label);

  assert.deepStrictEqual(ids, [
    "overview",
    "sources",
    "review_evidence",
    "career_timeline",
    "evidence_library",
    "use_for_application",
    "settings",
  ]);

  assert.deepStrictEqual(labels, [
    "Overview",
    "Sources",
    "Review evidence",
    "Career timeline",
    "Evidence library",
    "Use for application",
    "Settings",
  ]);
});

// CP-035: Old tab IDs removed.
test("MEMORY_BUILDER_TABS does not contain old Build / Career Profile / Advanced IDs", () => {
  const ids = MEMORY_BUILDER_TABS.map((tab) => tab.id);
  assert.ok(!ids.includes("build"), "build tab should be removed");
  assert.ok(!ids.includes("memory_bank"), "memory_bank tab should be removed");
  assert.ok(!ids.includes("advanced"), "advanced tab should be removed");
});

// CP-035: Legacy tab map redirects correctly.
test("LEGACY_TAB_MAP maps old tab IDs to new canonical IDs", () => {
  assert.equal(LEGACY_TAB_MAP.build, "overview");
  assert.equal(LEGACY_TAB_MAP.memory_bank, "evidence_library");
  assert.equal(LEGACY_TAB_MAP.sources, "sources");
  assert.equal(LEGACY_TAB_MAP.advanced, "settings");
  assert.equal(Object.keys(LEGACY_TAB_MAP).length, 4);
});

// CP-035: Each canonical tab maps to a valid destination ID.
test("LEGACY_TAB_MAP values are all valid MEMORY_BUILDER_TABS IDs", () => {
  const validIds = new Set(MEMORY_BUILDER_TABS.map((tab) => tab.id));
  for (const value of Object.values(LEGACY_TAB_MAP)) {
    assert.ok(validIds.has(value), `${value} must be a valid tab ID`);
  }
});
