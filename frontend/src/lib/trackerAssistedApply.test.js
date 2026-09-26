import test from "node:test";
import assert from "node:assert/strict";

import { assistedApplyTrackerRow } from "./trackerAssistedApply.js";

const supportedTrackerItem = {
  tracker_status: "not_applied",
  run_id: "run-123",
  job_id: "job-456",
  title: "Engineer",
  company: "VRChat",
  apply_link: "https://jobs.lever.co/vrchat/3a4d5b55-a9f2-4693-b548-dd8dce5a84ba",
};

test("makes a supported, not-applied Tracker job available for Review & Apply", () => {
  assert.deepEqual(assistedApplyTrackerRow(supportedTrackerItem), {
    ...supportedTrackerItem,
    location: "",
  });
});

test("does not offer Review & Apply for unsupported forms or missing package references", () => {
  assert.equal(assistedApplyTrackerRow({ ...supportedTrackerItem, apply_link: "https://example.com/jobs/123" }), null);
  assert.equal(assistedApplyTrackerRow({ ...supportedTrackerItem, job_id: "" }), null);
});

test("does not offer Review & Apply once a Tracker job is already applied", () => {
  assert.equal(assistedApplyTrackerRow({ ...supportedTrackerItem, tracker_status: "applied" }), null);
});
