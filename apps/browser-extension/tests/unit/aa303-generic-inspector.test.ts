import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  classifyFieldIntent,
  inspectApplicationForm,
  repeatedInstances,
  sensitivityFor,
  type DetectedApplicationField,
  type GenericInspection,
} from "@runr/ats-core";

const fixturesDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../fixtures");

function loadFixture(name: string): Document {
  const html = readFileSync(path.join(fixturesDir, name), "utf8");
  const parsed = new DOMParser().parseFromString(html, "text/html");
  document.documentElement.replaceWith(document.importNode(parsed.documentElement, true));
  return document;
}

function inspectFixture(name: string, url: string): GenericInspection {
  return inspectApplicationForm({ document: loadFixture(name), url });
}

function intentOf(inspection: GenericInspection, label: string): string | undefined {
  return inspection.fields.find((field) => field.label.toLowerCase().startsWith(label.toLowerCase()))?.intent;
}

function fieldOf(inspection: GenericInspection, label: string): DetectedApplicationField | undefined {
  return inspection.fields.find((field) => field.label.toLowerCase().startsWith(label.toLowerCase()));
}

const REGISTER_URL = "https://jobs.northwind-industries.com/en_US/externaljobs/Register?folderId=618402";

describe("AA-303 intent classification", () => {
  it("reads intent from the visible label", () => {
    expect(classifyFieldIntent({ label: "First Name *", controlType: "text" }).intent).toBe("contact.first_name");
    expect(classifyFieldIntent({ label: "Postal Code *", controlType: "text" }).intent).toBe("location.postal_code");
    expect(classifyFieldIntent({ label: "Country / Region of residence *", controlType: "select" }).intent)
      .toBe("location.residence_country");
  });

  it("resolves the same label differently by section", () => {
    // "Start Date" appears in both repeated blocks on the captured form.
    expect(classifyFieldIntent({ label: "Start Date", controlType: "month", section: "experience" }).intent)
      .toBe("experience.start_date");
    expect(classifyFieldIntent({ label: "Start Date", controlType: "month", section: "education" }).intent)
      .toBe("education.start_date");
  });

  it("infers the section from the nearest heading when none is supplied", () => {
    expect(classifyFieldIntent({ label: "School", controlType: "text", sectionHeading: "Education details" }).intent)
      .toBe("education.school");
  });

  it("falls back to attributes with lower confidence than a label match", () => {
    const labelled = classifyFieldIntent({ label: "Email *", controlType: "email" });
    const attributeOnly = classifyFieldIntent({ label: "", controlType: "text", name: "email" });
    expect(labelled.intent).toBe("contact.email");
    expect(attributeOnly.intent).toBe("contact.email");
    expect(attributeOnly.confidence).toBeLessThan(labelled.confidence);
  });

  it("classifies unmatched controls by shape instead of dropping them", () => {
    const free = classifyFieldIntent({ label: "Describe a time you led a project", controlType: "textarea" });
    expect(free.intent).toBe("question.free_text");
    expect(free.confidence).toBeLessThan(0.5);
    expect(classifyFieldIntent({ label: "Some bespoke question", controlType: "select" }).intent).toBe("question.select");
    expect(classifyFieldIntent({ label: "Some bespoke toggle", controlType: "checkbox" }).intent).toBe("question.boolean");
  });

  it("marks controls that must never be auto-filled", () => {
    for (const [label, reason] of [
      ["CAPTCHA response", "captcha"],
      ["Password", "credential"],
      ["I certify this declaration is accurate", "legal_declaration"],
      ["Accept terms and conditions", "legal_terms"],
      ["Coding assessment", "assessment"],
    ] as const) {
      expect(classifyFieldIntent({ label, controlType: "text" }).manualReason).toBe(reason);
    }
  });

  it("grades sensitivity so review rules have something to act on", () => {
    expect(sensitivityFor("contact.email")).toBe("personal");
    expect(sensitivityFor("demographic.gender")).toBe("sensitive");
    expect(sensitivityFor("legal.sponsorship")).toBe("sensitive");
    expect(sensitivityFor("demographic.disability")).toBe("high_risk");
    expect(sensitivityFor("experience.title")).toBe("normal");
  });
});

describe("AA-303 Avature form inspection", () => {
  it("detects every contact control with the right intent", () => {
    const inspection = inspectFixture("avature-register-form.html", REGISTER_URL);
    expect(intentOf(inspection, "Email")).toBe("contact.email");
    expect(intentOf(inspection, "First Name")).toBe("contact.first_name");
    expect(intentOf(inspection, "Last Name")).toBe("contact.last_name");
    expect(intentOf(inspection, "Phone Number")).toBe("contact.phone");
    expect(intentOf(inspection, "Country/Region of citizenship")).toBe("location.citizenship");
    expect(intentOf(inspection, "Postal Code")).toBe("location.postal_code");
    expect(intentOf(inspection, "Current / Last position title")).toBe("profile.current_title");
    expect(intentOf(inspection, "Gender")).toBe("demographic.gender");
  });

  it("captures required flags and select options", () => {
    const inspection = inspectFixture("avature-register-form.html", REGISTER_URL);
    const email = fieldOf(inspection, "Email");
    expect(email?.required).toBe(true);
    expect(email?.controlType).toBe("email");

    const gender = fieldOf(inspection, "Gender");
    expect(gender?.controlType).toBe("select");
    expect(gender?.options?.map((option) => option.value)).toContain("undisclosed");

    const website = fieldOf(inspection, "Website");
    expect(website?.required).toBe(false);
  });

  it("recognises the enhanced multi-select used for skills", () => {
    const inspection = inspectFixture("avature-register-form.html", REGISTER_URL);
    const skills = inspection.fields.find((field) => field.intent === "profile.skills");
    expect(skills).toBeDefined();
    expect(skills?.controlType).toBe("multiselect");
  });

  it("identifies document controls by role", () => {
    const inspection = inspectFixture("avature-register-form.html", REGISTER_URL);
    expect(intentOf(inspection, "CV / Resume")).toBe("document.cv");
    expect(intentOf(inspection, "Cover Letter")).toBe("document.cover_letter");
    expect(inspection.fields.filter((field) => field.intent === "document.supporting").length).toBe(2);
  });

  it("classifies consent and preference questions rather than lumping them together", () => {
    const inspection = inspectFixture("avature-register-form.html", REGISTER_URL);
    expect(intentOf(inspection, "Please choose your notification language")).toBe("preference.notification_language");
    expect(intentOf(inspection, "Interested in company communications")).toBe("consent.communications");
    expect(intentOf(inspection, "Visibility as candidate")).toBe("consent.visibility");
    expect(intentOf(inspection, "Make my data accessible")).toBe("consent.data_sharing");
  });

  it("groups the repeated sections it found", () => {
    const inspection = inspectFixture("avature-register-form.html", REGISTER_URL);
    const headings = inspection.sections.map((section) => section.heading);
    expect(headings).toEqual(expect.arrayContaining(["Work experience", "Education details", "Attachments"]));
    expect(inspection.sections.find((section) => section.heading === "Work experience")?.kind).toBe("experience");
    expect(inspection.sections.find((section) => section.heading === "Education details")?.kind).toBe("education");
  });

  it("separates experience fields from education fields with identical labels", () => {
    const inspection = inspectFixture("avature-register-form.html", REGISTER_URL);
    const startDates = inspection.fields.filter((field) => field.label.startsWith("Start Date"));
    expect(startDates).toHaveLength(2);
    expect(startDates.map((field) => field.intent).sort())
      .toEqual(["education.start_date", "experience.start_date"]);

    const descriptions = inspection.fields.filter((field) => field.label.startsWith("Description"));
    expect(descriptions.map((field) => field.intent).sort())
      .toEqual(["education.description", "experience.description"]);
  });

  it("reports no unsupported controls on a fully readable form", () => {
    const inspection = inspectFixture("avature-register-form.html", REGISTER_URL);
    expect(inspection.unsupported).toEqual([]);
  });
});

describe("AA-303 existing provider fixtures", () => {
  it("inspects the Greenhouse fixture and reports what it cannot read", () => {
    const inspection = inspectFixture("greenhouse-application.html", "https://boards.greenhouse.io/acme/jobs/1");

    expect(intentOf(inspection, "First name")).toBe("contact.first_name");
    expect(intentOf(inspection, "Legal last name")).toBe("contact.last_name");
    expect(intentOf(inspection, "CV / Resume")).toBe("document.cv");

    // Manual-only controls are detected, not filtered out.
    const manualReasons = inspection.fields.map((field) => field.manualReason).filter(Boolean);
    expect(manualReasons).toEqual(expect.arrayContaining(["captcha", "legal_declaration", "legal_terms", "assessment"]));

    // The fixture contains a closed shadow root, which must be reported.
    expect(inspection.unsupported.some((item) => item.reason === "closed_shadow_root")).toBe(true);
  });

  it("inspects the Lever fixture through the same generic path", () => {
    const inspection = inspectFixture("lever-application.html", "https://jobs.lever.co/acme/1a2b/apply");
    expect(intentOf(inspection, "Full name")).toBe("contact.full_name");
    expect(intentOf(inspection, "Email")).toBe("contact.email");
    expect(intentOf(inspection, "LinkedIn URL")).toBe("contact.linkedin");
    expect(intentOf(inspection, "GitHub URL")).toBe("contact.github");
    expect(intentOf(inspection, "CV / Resume")).toBe("document.cv");
  });

  it("reports a cross-origin frame instead of pretending the form is complete", () => {
    document.documentElement.replaceWith(document.createElement("html"));
    document.documentElement.innerHTML =
      "<head></head><body><label for='a'>First Name</label><input id='a'>" +
      "<iframe title='Additional questions' src='https://other.example.com/x'></iframe></body>";
    const inspection = inspectApplicationForm({ document, url: "https://jobs.example.com/apply" });
    expect(inspection.unsupported.some((item) => item.reason === "cross_origin_frame")).toBe(true);
  });
});

describe("AA-303 repeated instances", () => {
  it("returns one group per repeated block", () => {
    document.documentElement.replaceWith(document.createElement("html"));
    document.documentElement.innerHTML = `<head></head><body>
      <h2>Work experience</h2>
      <fieldset data-repeat="experience">
        <label for="t0">Job Title</label><input id="t0">
        <label for="c0">Company</label><input id="c0">
      </fieldset>
      <fieldset data-repeat="experience">
        <label for="t1">Job Title</label><input id="t1">
        <label for="c1">Company</label><input id="c1">
      </fieldset>
    </body>`;
    const inspection = inspectApplicationForm({ document, url: "https://jobs.example.com/apply" });
    const groups = repeatedInstances(inspection, "experience");

    expect(groups).toHaveLength(2);
    expect(groups[0]!.map((field) => field.intent).sort()).toEqual(["experience.company", "experience.title"]);
    expect(groups[1]!.map((field) => field.intent).sort()).toEqual(["experience.company", "experience.title"]);
  });

  it("does not assign a repeat index to a section that appears once", () => {
    document.documentElement.replaceWith(document.createElement("html"));
    document.documentElement.innerHTML = `<head></head><body>
      <h2>Work experience</h2>
      <fieldset data-repeat="experience">
        <label for="t0">Job Title</label><input id="t0">
      </fieldset>
    </body>`;
    const inspection = inspectApplicationForm({ document, url: "https://jobs.example.com/apply" });
    expect(inspection.fields.find((field) => field.intent === "experience.title")?.repeatIndex).toBeUndefined();
  });
});
