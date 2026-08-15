import assert from "node:assert/strict";
import test from "node:test";
import {
  buildJobWorkspaceRoute,
  getPeopleDiscoveryStatus,
  normalizePeopleDiscoveryRun,
} from "./peopleDiscovery.js";

test("normalizes the current and legacy people discovery field names", () => {
  const run = normalizePeopleDiscoveryRun({
    run_id: "run-1",
    job_id: "job-1",
    people_discovery_status: "completed",
    context_extraction: { department: "Engineering" },
    selected_people: [{ id: "person-1", status: "confirmed" }],
    categories: {
      hiring_manager: [{ id: "person-1" }],
    },
  });

  assert.equal(run.runId, "run-1");
  assert.equal(run.jobId, "job-1");
  assert.equal(run.peopleDiscoveryStatus, "completed");
  assert.equal(run.contextExtraction.department, "Engineering");
  assert.equal(run.categories.hiring_manager.length, 1);
  assert.equal(run.selectedPeople[0].id, "person-1");
});

test("normalizes discovery status responses before polling consumes them", async () => {
  const calls = [];
  const status = await getPeopleDiscoveryStatus(
    async (path) => {
      calls.push(path);
      return { people_discovery_status: "failed", error_message: "Search failed" };
    },
    { runId: "run/1", jobId: "job/1" },
  );

  assert.equal(status.peopleDiscoveryStatus, "failed");
  assert.deepEqual(calls, ["/runs/run%2F1/jobs/by-id/job%2F1/people-discovery/status"]);
});

test("builds a finder workspace route with encoded job context", () => {
  assert.equal(
    buildJobWorkspaceRoute({
      runId: "run/1",
      jobId: "job/1",
      mode: "pre_generation",
    }),
    "/job-workspaces/run%2F1/job%2F1?mode=pre_generation",
  );
});
