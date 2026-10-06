import test from "node:test";
import assert from "node:assert/strict";
import { alternativeSeniority, descriptionLines, employmentTypeLabel, formatPostingAge, hasRunrDescription, seniorityFromYears } from "./jobReadingPresentation.js";

test("published Nemo v3 facts and preserved summaries are displayable", () => {
  for (const prompt_version of ["runr_description_v1", "runr_description_nemo_v2", "runr_description_nemo_v3"]) {
    const descriptionIntelligence = { prompt_version };
    assert.equal(hasRunrDescription({ descriptionIntelligence, runrSummary: { responsibilities: [{ text: "Build data pipelines", source_ids: ["p1"] }] } }), true);
    assert.equal(hasRunrDescription({ descriptionIntelligence, runrSummary: { overview: "Existing approved overview" } }), true);
    assert.equal(hasRunrDescription({ descriptionIntelligence, runrSummary: { application_details: ["Apply through the employer website"] } }), true);
    assert.equal(hasRunrDescription({ descriptionIntelligence, runrSummary: { responsibilities: [{ text: " " }, {}] } }), false);
  }
  assert.equal(hasRunrDescription({ runrSummary: { overview: "Unversioned result" } }), false);
});

test("posting age stays in hours or days", () => {
  const now = Date.parse("2026-10-02T12:00:00Z");
  assert.equal(formatPostingAge("2026-10-02T05:00:00Z", now), "7 hours ago");
  assert.equal(formatPostingAge("2026-09-25T12:00:00Z", now), "7 days ago");
  assert.equal(formatPostingAge("2026-08-31T12:00:00Z", now), "32 days ago");
  assert.equal(formatPostingAge("2026-8-31", now), "32 days ago");
  assert.equal(formatPostingAge("", now), "");
});

test("years produce a consistent seniority band", () => {
  assert.equal(seniorityFromYears(1), "Entry level");
  assert.equal(seniorityFromYears(3), "Mid level");
  assert.equal(seniorityFromYears(7), "Senior level");
  assert.equal(seniorityFromYears(10), "Lead level");
  assert.equal(seniorityFromYears("7"), null);
});

test("explicit alternative experience paths show adjacent seniority bands", () => {
  const required = [{ text: "3-4 years’ professional experience or a minimum of 2 years transferable recruiting experience.", source_ids: ["p35"] }];
  const passages = [{ id: "p35", text: required[0].text }];
  assert.equal(alternativeSeniority(required, passages), "Entry, Mid Level");
  assert.equal(alternativeSeniority([{ text: "6 years of experience or 3 years of relevant experience", source_ids: ["p1"] }], [{ id: "p1", text: "6 years of experience or 3 years of relevant experience" }]), "Mid, Senior Level");
  assert.equal(alternativeSeniority([{ text: "10 years of experience or 2 years of relevant experience", source_ids: ["p1"] }], [{ id: "p1", text: "10 years of experience or 2 years of relevant experience" }]), "Lead level");
  assert.equal(alternativeSeniority([{ text: "3 years of experience or leadership skills", source_ids: ["p1"] }], [{ id: "p1", text: "3 years of experience or leadership skills" }]), null);
});

test("employment defaults to full-time without mistaking a contract specialist for a contractor", () => {
  assert.equal(employmentTypeLabel(null, null, "Contract Specialist"), "Full-time");
  assert.equal(employmentTypeLabel(null, null, "Marketing Assistant - 12 months temporary contract"), "Contract");
  assert.equal(employmentTypeLabel(null, null, "Werkstudent Marketing"), "Working student");
  assert.equal(employmentTypeLabel("part-time", null), "Part-time");
});

test("each source line becomes one list item", () => {
  assert.deepEqual(descriptionLines([{ text: "First\n- Second" }, { text: "Third" }]), ["First", "Second", "Third"]);
});
