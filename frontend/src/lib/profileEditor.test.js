import test from "node:test";
import assert from "node:assert/strict";
import { profileWithResumeDefaults, readyResume, educationRecord } from "./profileEditor.js";

const asset = (date, parsed, status = "ready") => ({ asset_kind: "workspace_cv", updated_at: date, metadata: { status, parsed_profile: parsed } });
test("latest ready resume fills missing fields without overwriting saved edits", () => {
  const settings = { profile: { name: "Edited name", education: [], competencies: [] }, profile_edited_fields: ["competencies"], candidate_assets: [asset("2025", { name: "Old" }), asset("2026", { name: "From CV", education: [{ degree_title: "MSc" }], competencies: ["SQL"] }), asset("2027", { name: "Pending" }, "processing")] };
  assert.equal(readyResume(settings).updated_at, "2026");
  const profile = profileWithResumeDefaults(settings);
  assert.equal(profile.name, "Edited name");
  assert.equal(profile.education[0].degree_title, "MSc");
  assert.deepEqual(profile.competencies, []);
  assert.deepEqual(settings.profile.education, []);
});
test("canonical education retains degree and dates from uploaded CV", () => {
  assert.deepEqual(educationRecord({ degree_title: "MBA", institution: "School", period: "2020–2022" }), { degree_title: "MBA", institution: "School", period: "2020–2022", field: "", start_date: "", end_date: "" });
});
