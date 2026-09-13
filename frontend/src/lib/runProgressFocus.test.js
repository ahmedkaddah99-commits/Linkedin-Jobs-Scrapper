import assert from "node:assert/strict";
import test from "node:test";

import {
  claimRunProgressFocus,
  runProgressScrollBehavior,
  shouldFocusRunProgress,
} from "./runProgressFocus.js";

test("focuses active runs and explicit progress links but not completed runs", () => {
  assert.equal(shouldFocusRunProgress({ runStatus: "running" }), true);
  assert.equal(shouldFocusRunProgress({ runStatus: "completed" }), false);
  assert.equal(
    shouldFocusRunProgress({ hash: "#run-progress", runStatus: "completed" }),
    true,
  );
});

test("uses automatic scrolling when reduced motion is preferred", () => {
  assert.equal(runProgressScrollBehavior(true), "auto");
  assert.equal(runProgressScrollBehavior(false), "smooth");
});

test("claims focus once per active run so polling cannot move the viewport", () => {
  const focusedRunIds = new Set();
  assert.equal(
    claimRunProgressFocus(focusedRunIds, { runId: "run_1", runStatus: "running" }),
    true,
  );
  assert.equal(
    claimRunProgressFocus(focusedRunIds, { runId: "run_1", runStatus: "running" }),
    false,
  );
  assert.equal(
    claimRunProgressFocus(focusedRunIds, { runId: "run_2", runStatus: "completed" }),
    false,
  );
});
