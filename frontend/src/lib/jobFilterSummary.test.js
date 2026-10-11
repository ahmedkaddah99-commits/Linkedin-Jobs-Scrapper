import assert from "node:assert/strict";
import test from "node:test";
import { jobFilterSummary } from "./jobFilterSummary.js";
import { buildPersonalizedJobsQuery, toPersonalizedJobsFilterPayload, filtersFromSavedSearch } from "./personalizedJobsApi.js";

test("reference criteria survive a saved-search round trip and repeated query parameters", () => {
  const filters = { location: ["Berlin", "Hamburg"], workArrangement: ["hybrid", "remote"], experienceLevel: ["entry", "mid"], requiredExperienceMin: "2.5", requiredExperienceMax: "4", salaryMin: "0", excludedTitle: ["Sales"], excludeSecurityClearance: true, datePosted: "3d" };
  const restored = filtersFromSavedSearch({ filters: toPersonalizedJobsFilterPayload(filters) });
  const query = new URLSearchParams(buildPersonalizedJobsQuery(restored));
  assert.deepEqual(query.getAll("location"), filters.location);
  assert.deepEqual(query.getAll("work_arrangement"), filters.workArrangement);
  assert.deepEqual(query.getAll("experience_level"), filters.experienceLevel);
  assert.equal(query.get("required_experience_min"), "2.5");
  assert.equal(query.get("salary_min"), "0");
  assert.equal(query.get("posted_within_days"), "3");
  const labels = jobFilterSummary(restored).map((item) => item.label);
  assert.ok(labels.includes("Minimum annual salary: 0"));
  assert.ok(labels.includes("Exclude clearance"));
  assert.ok(labels.includes("Exclude title: Sales"));
});
