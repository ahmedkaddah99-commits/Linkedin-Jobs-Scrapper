import assert from "node:assert/strict";
import test from "node:test";

import {
  buildStructuredListMarkup,
  formatCvExperiencePeriod,
  normalizeCvListItems,
  normalizeExperienceItems,
} from "./cvStudio.js";

test("migrates legacy experience aliases and line bullets without losing fields", () => {
  const [experience] = normalizeExperienceItems([
    {
      role_title: "Analyst",
      employer: "ACME",
      location: "Berlin",
      period: "2022 - Present",
      bulletsText: "- Built reports\n• Reduced handling time",
    },
  ]);

  assert.equal(experience.title, "Analyst");
  assert.equal(experience.company, "ACME");
  assert.equal(experience.location, "Berlin");
  assert.equal(formatCvExperiencePeriod(experience), "2022 - Present");
  assert.deepEqual(
    experience.bullets.map(({ text, level }) => ({ text, level })),
    [
      { text: "Built reports", level: 0 },
      { text: "Reduced handling time", level: 0 },
    ],
  );
});

test("renders structured nested lists and escapes bullet text", () => {
  const items = normalizeCvListItems([
    { text: "Parent", level: 0 },
    { text: "Child <detail>", level: 1 },
  ]);

  assert.equal(
    buildStructuredListMarkup(items),
    "<ul><li>Parent<ul><li>Child &lt;detail&gt;</li></ul></li></ul>",
  );
});
