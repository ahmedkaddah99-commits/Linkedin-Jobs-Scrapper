import assert from "node:assert/strict";
import test from "node:test";

import {
  buildCvStudioHtml,
  buildWorkspacePreviewState,
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

test("workspace PDF preview omits availability and keeps education concise", () => {
  const state = buildWorkspacePreviewState(
    {
      name: "Ahmed Kaddah",
      role_title: "Product Owner",
      email: "ahmed@example.com",
      summary: "Builds structured product workflows.",
      competencies: ["Product Ownership", "AI Workflow Design"],
      languages: ["English - C1"],
      education: [
        {
          degree_title: "M.A. Entrepreneurship and Innovation",
          institution: "Katholische Universitaet Eichstaett-Ingolstadt",
          thesis_title: "Master Thesis: Strategic Opportunity Discovery Framework",
          thesis_bullets: [
            "This detailed thesis method should stay out of the compact rendered education section.",
          ],
        },
      ],
    },
    { cv_template: "plain", include_photo: false },
  );

  const html = buildCvStudioHtml(state);

  assert.doesNotMatch(html, /Available immediately|Availability|Verfuegbarkeit/);
  assert.match(html, /M\.A\. Entrepreneurship and Innovation/);
  assert.match(html, /Master Thesis: Strategic Opportunity Discovery Framework/);
  assert.doesNotMatch(html, /detailed thesis method/);
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

test("photo mode without resolved image omits the photo slot", () => {
  const html = buildCvStudioHtml({
    templateId: "plain",
    name: "Ahmed Kaddah",
    headline: "Operations Leader",
    email: "ahmed@example.com",
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
  });

  assert.doesNotMatch(html, /Optional photo|Optionales Foto|cv-photo-placeholder/);
  assert.doesNotMatch(html, /<div class="[^"]*photo[^"]*">/);
  assert.match(html, /Ahmed Kaddah/);
  assert.doesNotMatch(html, /Kaddah Ahmed/);
});

test("plain resume preview keeps resolved photo in the right header column", () => {
  const html = buildCvStudioHtml({
    templateId: "plain",
    name: "Ahmed Kaddah",
    headline: "Operations Leader",
    email: "ahmed@example.com",
    location: "Erlangen, Germany",
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

  assert.match(
    html,
    /<header class="plain-resume-head has-photo">\s*<div class="plain-resume-identity">[\s\S]*?<div class="plain-resume-contact">[\s\S]*?<\/div>\s*<\/div>\s*<div class="cv-photo-shell plain-resume-photo">/,
  );
});
