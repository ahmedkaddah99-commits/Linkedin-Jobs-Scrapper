import assert from "node:assert/strict";
import test from "node:test";

import {
  buildCvStudioHtml,
  buildWorkspacePreviewDocuments,
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

test("maps and renders uploaded reference-inspired PDF templates", () => {
  const templateIds = ["modern_minimal", "modern_sidebar", "classic_executive"];

  for (const templateId of templateIds) {
    const documents = buildWorkspacePreviewDocuments({ cv_template: templateId, include_photo: true });
    assert.equal(documents.web_cv_template, templateId);
    assert.equal(documents.web_cv_show_photo, true);

    const html = buildCvStudioHtml({
      templateId,
      name: "Alex Morgan",
      headline: "Operations Leader",
      email: "alex@example.com",
      summary: "Builds reliable teams and measurable operating systems.",
      skillsText: "Operations\nAnalytics",
      educationText: "MSc Management",
      experience: [
        {
          id: "experience-1",
          title: "Operations Manager",
          company: "Example Co",
          period: "2023 - Present",
          bullets: [{ id: "bullet-1", text: "Improved throughput.", level: 0 }],
        },
      ],
      showPhoto: true,
      photoDataUrl: "data:image/png;base64,abc",
    });

    assert.match(html, new RegExp(`template-${templateId.replaceAll("_", "-")}`));
    assert.match(html, /Candidate profile photo/);
  }
});
