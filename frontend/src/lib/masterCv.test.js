import assert from "node:assert/strict";
import test from "node:test";
import { createMasterCvFixture } from "../data/masterCvFixture.js";
import {
  addMasterCvAchievement,
  countMasterCvExtraEvidence,
  findMasterCvBullet,
  flattenMasterCvBullets,
  getMasterCvGuidance,
  shouldShowMasterCvIntro,
  visibleMasterCvBullets,
} from "./masterCv.js";

test("introduction dialog is shown until this session marks it as seen", () => {
  assert.equal(shouldShowMasterCvIntro(null), true);
  assert.equal(shouldShowMasterCvIntro(""), true);
  assert.equal(shouldShowMasterCvIntro("1"), false);
});

test("fixture supports work and project entries without sharing mutable state", () => {
  const first = createMasterCvFixture();
  const second = createMasterCvFixture();
  const entries = first.sections.flatMap((section) => section.entries);

  assert.equal(entries.filter((entry) => entry.kind === "work").length, 2);
  assert.equal(entries.filter((entry) => entry.kind === "project").length, 1);
  first.sections[0].entries[0].bullets[0].text = "Changed locally";
  assert.notEqual(first.sections[0].entries[0].bullets[0].text, second.sections[0].entries[0].bullets[0].text);
});

test("extra evidence view filters bullets while preserving the full view", () => {
  const masterCv = createMasterCvFixture();
  const firstEntry = masterCv.sections[0].entries[0];

  assert.equal(visibleMasterCvBullets(firstEntry, "all").length, 3);
  assert.deepEqual(visibleMasterCvBullets(firstEntry, "extra").map((bullet) => bullet.id), ["northstar-workshops"]);
  assert.equal(countMasterCvExtraEvidence(masterCv), 4);
});

test("bullet selection resolves work and project evidence for the guidance panel", () => {
  const masterCv = createMasterCvFixture();
  const bullets = flattenMasterCvBullets(masterCv);
  const workBullet = findMasterCvBullet(masterCv, "northstar-onboarding");
  const projectBullet = findMasterCvBullet(masterCv, "talent-sponsorship");

  assert.equal(bullets.length, 9);
  assert.equal(workBullet.entryId, "northstar-senior-pm");
  assert.equal(projectBullet.sectionId, "projects");
  assert.equal(getMasterCvGuidance(workBullet).checks[2].state, "pass");
  assert.equal(getMasterCvGuidance(projectBullet).checks[2].state, "warn");
});

test("inline achievement composer adds clearly marked extra evidence to any entry", () => {
  const masterCv = createMasterCvFixture();
  const workDraft = addMasterCvAchievement(masterCv, "northstar-senior-pm", "Coached a new squad through its first customer discovery cycle.", "draft-work");
  const projectDraft = addMasterCvAchievement(workDraft, "talent-marketplace", "Ran a pilot retro that clarified the next experiment.", "draft-project");

  const workBullet = findMasterCvBullet(projectDraft, "draft-work");
  const projectBullet = findMasterCvBullet(projectDraft, "draft-project");
  assert.equal(workBullet.extra, true);
  assert.equal(projectBullet.extra, true);
  assert.equal(projectBullet.entryId, "talent-marketplace");
  assert.equal(addMasterCvAchievement(projectDraft, "missing-entry", "Ignored"), projectDraft);
});
