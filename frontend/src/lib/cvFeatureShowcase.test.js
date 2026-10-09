import assert from "node:assert/strict";
import test from "node:test";
import {
  CV_SHOWCASE_SCENES,
  getCvShowcaseEntitlements,
  normalizeCvProcessingStatus,
  summarizeCvProfile,
} from "./cvFeatureShowcase.js";
import { resolvePersonalizedJobsDataMode } from "./personalizedJobs.js";

test("CV showcase contains four candidate-facing outcomes", () => {
  assert.deepEqual(CV_SHOWCASE_SCENES.map((scene) => scene.key), [
    "relevant_jobs",
    "match_explanations",
    "application_preparation",
    "assisted_apply",
  ]);
  CV_SHOWCASE_SCENES.forEach((scene) => {
    assert.ok(scene.headline);
    assert.ok(scene.body);
    assert.ok(scene.entitlementKey);
  });
});

test("real CV processing statuses remain truthful and bounded", () => {
  assert.equal(normalizeCvProcessingStatus("queued"), "reading");
  assert.equal(normalizeCvProcessingStatus("processing"), "reading");
  assert.equal(normalizeCvProcessingStatus("ready"), "ready");
  assert.equal(normalizeCvProcessingStatus("failed"), "error");
  assert.equal(normalizeCvProcessingStatus("unknown"), "idle");
});

test("preview CV summary is deterministic and clearly labelled", () => {
  const summary = summarizeCvProfile({}, { dataMode: "synthetic" });
  assert.equal(summary.dataLabel, "Preview data");
  assert.equal(summary.recentRole, "Product Operations Manager");
  assert.equal(summary.skills.length, 6);
});

test("real CV summary uses safe categories without exposing CV text", () => {
  const summary = summarizeCvProfile({
    recent_experience: [{ title: "Operations Lead" }],
    education: [{ degree: "MBA" }],
    competencies: ["Analytics", "SQL", "Process design"],
    languages: ["English — fluent"],
    email: "candidate@example.com",
    source_text: "private CV contents should never be shown here",
  }, { dataMode: "real" });
  assert.equal(summary.dataLabel, "Extracted from your CV");
  assert.equal(summary.recentRole, "Operations Lead");
  assert.equal(summary.education, "MBA");
  assert.equal(summary.skills.join(","), "Analytics,SQL,Process design");
  assert.equal(Object.values(summary).includes("private CV contents should never be shown here"), false);
});

test("entitlement labels are sourced from the existing configuration", () => {
  const free = getCvShowcaseEntitlements("none");
  const pro = getCvShowcaseEntitlements("pro");
  assert.equal(free.relevant_jobs.available, false);
  assert.equal(free.relevant_jobs.requiredPlan, "Pro");
  assert.equal(pro.relevant_jobs.available, true);
});

test("data mode defaults to preview and accepts explicit real mode", () => {
  assert.equal(resolvePersonalizedJobsDataMode({}), "synthetic");
  assert.equal(resolvePersonalizedJobsDataMode({ VITE_PERSONALIZED_JOBS_DATA_MODE: "real" }), "real");
  assert.equal(resolvePersonalizedJobsDataMode({ VITE_PERSONALIZED_JOBS_DATA_MODE: "anything-else" }), "synthetic");
});
