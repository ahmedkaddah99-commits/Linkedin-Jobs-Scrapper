import assert from "node:assert/strict";
import test from "node:test";
import {
  HIDDEN_REASON_DEFINITIONS,
  PREVIEW_FEED_SUMMARY,
  PREVIEW_JOBS,
  getActivePreviewFilterCount,
  getFeedJobs,
  getHiddenReasonGroups,
  getPreviewUpgradeCopy,
  isPersonalizedJobsExperienceEnabled,
  validateJobCard,
} from "./personalizedJobs.js";
import { getNextOnboardingStep, getOnboardingAnswers, getPreviousOnboardingStep, ONBOARDING_STEPS } from "./personalizedOnboarding.js";
import { buildPersonalizedEventProperties } from "./personalizedAnalyticsPayload.js";
import { restorePreviewDisposition } from "./personalizedPreviewState.js";

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

test("onboarding starts with explicit role and location choices", () => {
  const answers = getOnboardingAnswers();
  assert.deepEqual(answers.targetRoles, []);
  assert.deepEqual(answers.targetLocations, []);
  const saved = getOnboardingAnswers({ targetLocations: ["Berlin"], sourceCvName: "preview.pdf" });
  assert.deepEqual(saved.targetLocations, ["Berlin"]);
  assert.equal(saved.sourceCvName, "preview.pdf");
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

test("active filter count and clearable filters are deterministic", () => {
  assert.equal(getActivePreviewFilterCount({}), 0);
  assert.equal(getActivePreviewFilterCount({ query: "Berlin", location: "berlin", sort: "newest", onlyEligible: true }), 4);
});

test("upgrade copy changes with the clicked feature", () => {
  assert.equal(getPreviewUpgradeCopy("ai_eligibility_filter").title, "Stop reviewing jobs you cannot apply for");
  assert.equal(getPreviewUpgradeCopy("tailored_cv").cta, "Unlock tailored CVs");
  assert.notEqual(getPreviewUpgradeCopy("ai_eligibility_filter").body, getPreviewUpgradeCopy("assisted_apply").body);
});

test("preview restore is a local disposition change", () => {
  let fetchCalls = 0;
  const previousFetch = globalThis.fetch;
  globalThis.fetch = () => { fetchCalls += 1; };
  const restored = restorePreviewDisposition({ hidden: { job: true }, saved: { job: true } }, "job");
  globalThis.fetch = previousFetch;
  assert.equal(fetchCalls, 0);
  assert.equal(restored.hidden.job, undefined);
  assert.equal(restored.restored.job, true);
});

test("personalized analytics allow only non-sensitive context", () => {
  const properties = buildPersonalizedEventProperties({ route: "/jobs", featureKey: "tailored_cv", jobPreviewId: "preview-job", onboardingStep: "cv", salaryExpectation: "secret", cvText: "secret" });
  assert.deepEqual(properties, {
    route: "/jobs",
    feature_key: "tailored_cv",
    job_preview_id: "preview-job",
    filter_name: undefined,
    onboarding_step: "cv",
    data_mode: "synthetic",
  });
});
