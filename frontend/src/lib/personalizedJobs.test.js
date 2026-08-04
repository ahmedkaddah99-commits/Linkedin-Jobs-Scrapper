import assert from "node:assert/strict";
import test from "node:test";
import {
  HIDDEN_REASON_DEFINITIONS,
  PREVIEW_FEED_SUMMARY,
  PREVIEW_JOBS,
  getFeedJobs,
  getHiddenReasonGroups,
  isPersonalizedJobsExperienceEnabled,
  validateJobCard,
} from "./personalizedJobs.js";
import { getNextOnboardingStep, getPreviousOnboardingStep, ONBOARDING_STEPS } from "./personalizedOnboarding.js";

test("feature flag accepts explicit truthy values and stays off by default", () => {
  assert.equal(isPersonalizedJobsExperienceEnabled({}), false);
  assert.equal(isPersonalizedJobsExperienceEnabled({ VITE_PERSONALIZED_JOBS_EXPERIENCE: "1" }), true);
  assert.equal(isPersonalizedJobsExperienceEnabled({ VITE_PERSONALIZED_JOBS_EXPERIENCE: "true" }), true);
  assert.equal(isPersonalizedJobsExperienceEnabled({ VITE_PERSONALIZED_JOBS_EXPERIENCE: "0" }), false);
});

test("preview contract is validated and visibly synthetic", () => {
  assert.equal(PREVIEW_JOBS.length, 11);
  PREVIEW_JOBS.forEach((job) => assert.equal(validateJobCard(job).dataMode, "synthetic"));
  assert.equal(PREVIEW_FEED_SUMMARY.dataMode, "synthetic");
});

test("onboarding navigation is bounded", () => {
  assert.equal(ONBOARDING_STEPS.length, 5);
  assert.equal(getPreviousOnboardingStep(0), 0);
  assert.equal(getNextOnboardingStep(ONBOARDING_STEPS.length - 1), 4);
  assert.equal(getNextOnboardingStep(1), 2);
});

test("feed filters and sorts preview jobs", () => {
  const eligible = getFeedJobs({ filters: { onlyEligible: true } });
  assert.ok(eligible.length > 0);
  assert.ok(eligible.every((job) => job.eligibilityStatus === "eligible"));

  const newest = getFeedJobs({ filters: { sort: "newest" } });
  assert.equal(newest[0].id, "preview-aurora-product-ops");

  const salarySorted = getFeedJobs({ filters: { sort: "salary" } });
  assert.equal(salarySorted[0].id, "preview-cobalt-pipeline");
});

test("hidden jobs group by understandable reason", () => {
  const groups = getHiddenReasonGroups();
  assert.equal(groups.length, Object.keys(HIDDEN_REASON_DEFINITIONS).length);
  assert.deepEqual(groups.map((group) => group.code), [
    "language_requirement",
    "work_authorization",
    "experience",
    "location",
    "low_relevance",
    "uncertain_requirement",
  ]);
  assert.ok(groups.every((group) => group.jobs.length === group.count));
});

test("local preview restore makes an originally hidden job available without an API call", () => {
  const restored = getFeedJobs({
    dispositions: { restored: { "preview-lumen-german": true } },
  });
  assert.ok(restored.some((job) => job.id === "preview-lumen-german"));
});
