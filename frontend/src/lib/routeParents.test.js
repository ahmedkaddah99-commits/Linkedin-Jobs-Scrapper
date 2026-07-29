import assert from "node:assert/strict";
import test from "node:test";

import { resolveRouteParent } from "./routeParents.js";

test("resolves Career Assets secondary destinations to the guided flow", () => {
  assert.equal(resolveRouteParent({ pathname: "/career-evidence" }), "");
  assert.equal(resolveRouteParent({ pathname: "/career-evidence/profile_1" }), "/career-evidence");
  assert.equal(resolveRouteParent({ pathname: "/career-memory" }), "/career-evidence");
  assert.equal(resolveRouteParent({ pathname: "/career-memory/guide" }), "/career-evidence");
  assert.equal(resolveRouteParent({ pathname: "/documents", search: "?view=memory" }), "/career-evidence");
  assert.equal(resolveRouteParent({ pathname: "/documents" }), "/career-evidence");
  assert.equal(resolveRouteParent({ pathname: "/cv-studio" }), "/career-evidence");
  assert.equal(resolveRouteParent({ pathname: "/tracker/job-descriptions/review_1" }), "/tracker");
  assert.equal(resolveRouteParent({ pathname: "/job-workspaces/run_1/job_1" }), "/workspaces");
  assert.equal(resolveRouteParent({ pathname: "/runs/run_1" }), "/runs");
  assert.equal(resolveRouteParent({ pathname: "/settings/assisted-apply" }), "/settings");
});

test("uses a safe tracker return target for ATS details and stops at section roots", () => {
  assert.equal(
    resolveRouteParent({
      pathname: "/tracker/review_1/ats",
      search: "?return=%2Ftracker%3Fstatus%3Dapplied%23review-review_1",
    }),
    "/tracker?status=applied#review-review_1",
  );
  assert.equal(
    resolveRouteParent({
      pathname: "/tracker/review_1/ats",
      search: "?return=https%3A%2F%2Fevil.example",
    }),
    "/tracker",
  );
  assert.equal(resolveRouteParent({ pathname: "/tracker" }), "");
  assert.equal(resolveRouteParent({ pathname: "/career-evidence" }), "");
  assert.equal(resolveRouteParent({ pathname: "/settings" }), "");
});
