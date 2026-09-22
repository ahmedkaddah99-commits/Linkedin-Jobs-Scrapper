import { describe, expect, it } from "vitest";
import {
  attachDocument,
  computeResumeMatch,
  executeAddRepeatedRow,
  executeEnhancedSelection,
  inspectApplicationForm,
  matchVerdict,
  profileCompleteness,
  resolveUploadTarget,
  verifyRepeatedRowGrowth,
  type CandidateProfile,
} from "@runr/ats-core";

function setBody(html: string): Document {
  document.documentElement.replaceWith(document.createElement("html"));
  document.documentElement.innerHTML = `<head></head><body>${html}</body>`;
  return document;
}

const URL_UNDER_TEST = "https://jobs.example.com/apply";

function profile(overrides: Partial<CandidateProfile> = {}): CandidateProfile {
  return {
    contact: { firstName: "Alex", lastName: "Fixture", email: "alex@example.com", phone: "+49 30 000000" },
    locations: { city: "Erlangen", residenceCountry: "Germany", postalCode: "91052" },
    skills: ["Python", "Kubernetes"],
    workExperiences: [{ title: "Platform Engineer", company: "Example Systems", description: "Ran Kubernetes clusters." }],
    education: [{ school: "Example University", degree: "BSc", major: "Computer Science" }],
    preferences: { currentTitle: "Platform Engineer" },
    ...overrides,
  };
}

describe("AA-307 enhanced list controls", () => {
  it("selects several values in a native multi-select and verifies each", async () => {
    const doc = setBody(`
      <label for="skills">Skills</label>
      <select id="skills" multiple>
        <option value="python">Python</option>
        <option value="kubernetes">Kubernetes</option>
        <option value="rust">Rust</option>
      </select>`);
    const result = await executeEnhancedSelection(
      doc,
      { type: "select_enhanced_options", fieldId: "skills", values: ["Python", "Kubernetes"] },
      (id) => doc.getElementById(id),
    );

    expect(result.status).toBe("applied");
    expect(result.applied).toEqual(["Python", "Kubernetes"]);
    const selected = Array.from(doc.querySelector<HTMLSelectElement>("#skills")!.selectedOptions).map((o) => o.value);
    expect(selected).toEqual(["python", "kubernetes"]);
  });

  it("reports the values a control never offered instead of counting them applied", async () => {
    const doc = setBody(`
      <select id="skills" multiple>
        <option value="python">Python</option>
      </select>`);
    const result = await executeEnhancedSelection(
      doc,
      { type: "select_enhanced_options", fieldId: "skills", values: ["Python", "Kubernetes"] },
      (id) => doc.getElementById(id),
    );
    expect(result.status).toBe("needs_attention");
    expect(result.applied).toEqual(["Python"]);
    expect(result.rejected).toEqual(["Kubernetes"]);
  });

  it("drives an ARIA combobox with its own listbox", async () => {
    const doc = setBody(`
      <div id="country" role="combobox" aria-controls="country-list" aria-expanded="false" tabindex="0"></div>
      <ul id="country-list" role="listbox">
        <li role="option" data-value="DE">Germany</li>
        <li role="option" data-value="HU">Hungary</li>
      </ul>`);
    // Mirror a real widget: choosing an option marks it selected.
    for (const option of Array.from(doc.querySelectorAll("[role='option']"))) {
      option.addEventListener("click", () => option.setAttribute("aria-selected", "true"));
    }

    const result = await executeEnhancedSelection(
      doc,
      { type: "select_enhanced_options", fieldId: "country", values: ["Germany"] },
      (id) => doc.getElementById(id),
    );
    expect(result.status).toBe("applied");
    expect(doc.querySelector("[data-value='DE']")!.getAttribute("aria-selected")).toBe("true");
  });

  it("refuses a control whose options never match", async () => {
    const doc = setBody(`
      <div id="country" role="combobox" aria-controls="country-list" tabindex="0"></div>
      <ul id="country-list" role="listbox"><li role="option">Belgium</li></ul>`);
    const result = await executeEnhancedSelection(
      doc,
      { type: "select_enhanced_options", fieldId: "country", values: ["Germany"] },
      (id) => doc.getElementById(id),
    );
    expect(result.status).toBe("unresolved");
    expect(result.rejected).toEqual(["Germany"]);
  });

  it("never operates a terminal control", async () => {
    const doc = setBody(`<button id="go" type="submit">Submit application</button>`);
    const result = await executeEnhancedSelection(
      doc,
      { type: "select_enhanced_options", fieldId: "go", values: ["x"] },
      (id) => doc.getElementById(id),
    );
    expect(result.status).toBe("rejected");
  });
});

describe("AA-307 repeated row creation", () => {
  it("reports the single add-row control for trusted activation without clicking it", () => {
    const doc = setBody(`
      <section id="experience">
        <h2>Work experience</h2>
        <fieldset data-repeat="experience"><label for="t0">Job Title</label><input id="t0"></fieldset>
        <button type="button" id="add">Add another</button>
      </section>`);
    const section = doc.getElementById("experience")!;
    let activated = false;
    doc.getElementById("add")!.addEventListener("click", () => {
      activated = true;
      const row = doc.createElement("fieldset");
      row.setAttribute("data-repeat", "experience");
      row.innerHTML = '<label for="t1">Job Title</label><input id="t1">';
      section.insertBefore(row, doc.getElementById("add"));
    });

    const outcome = executeAddRepeatedRow(doc, section);
    expect(outcome.status).toBe("needs_attention");
    expect(outcome.rowCount).toBe(1);
    expect((outcome as { reason?: string }).reason).toMatch(/trusted user activation/iu);
    expect(activated).toBe(false);
    expect(section.querySelectorAll("[data-repeat]").length).toBe(1);
  });

  it("verifies a trusted-activation row add by reading the page back", () => {
    const doc = setBody(`
      <section id="experience">
        <fieldset data-repeat="experience"><input id="t0"></fieldset>
      </section>`);
    const section = doc.getElementById("experience")!;
    const row = doc.createElement("fieldset");
    row.setAttribute("data-repeat", "experience");
    row.innerHTML = '<label for="t1">Job Title</label><input id="t1">';
    section.appendChild(row);

    const outcome = verifyRepeatedRowGrowth(1, section);
    expect(outcome.status).toBe("applied");
    expect(outcome.rowCount).toBe(2);
  });

  it("reports unresolved when the page adds nothing", () => {
    const doc = setBody(`
      <section id="experience">
        <h2>Work experience</h2>
        <fieldset data-repeat="experience"><input id="t0"></fieldset>
        <button type="button">Add another</button>
      </section>`);
    const outcome = verifyRepeatedRowGrowth(1, doc.getElementById("experience")!);
    expect(outcome.status).toBe("unresolved");
    expect((outcome as { reason?: string }).reason).toMatch(/did not add a row/iu);
  });

  it("never mistakes a submit or remove control for an add-row control", async () => {
    const doc = setBody(`
      <section id="experience">
        <fieldset data-repeat="experience"><input id="t0"></fieldset>
        <button type="button">Remove</button>
        <button type="submit">Submit application</button>
      </section>`);
    const outcome = await executeAddRepeatedRow(doc, doc.getElementById("experience")!);
    expect(outcome.status).toBe("unresolved");
    expect((outcome as { reason?: string }).reason).toMatch(/no add-row control/iu);
  });
});

/**
 * jsdom does not implement `DataTransfer`, so the attachment itself is verified
 * in a real browser (`aa302-auto-panel.spec.ts`). What is unit-testable is every
 * decision made *before* a file is handed to a control, which is where the
 * safety rules live.
 */
describe("AA-307 document attachment", () => {
  const attachment = {
    role: "cv" as const,
    fileName: "candidate-cv.pdf",
    mimeType: "application/pdf",
    bytes: new Uint8Array([37, 80, 68, 70]),
  };

  it("resolves the control whose label names the role", () => {
    const doc = setBody(`
      <label for="cv">CV / Resume *</label><input id="cv" type="file" accept=".pdf">
      <label for="cover-letter">Cover Letter</label><input id="cover-letter" type="file" accept=".pdf">`);
    const inspection = inspectApplicationForm({ document: doc, url: URL_UNDER_TEST });

    const cv = resolveUploadTarget(inspection, "cv");
    expect(cv).not.toBeNull();
    expect((cv as { field: { id: string } }).field.id).toBe("field-cv");

    const cover = resolveUploadTarget(inspection, "cover_letter");
    expect((cover as { field: { id: string } }).field.id).toBe("field-cover-letter");
  });

  it("refuses when the role has more than one candidate control", () => {
    const doc = setBody(`
      <label for="a">Additional document</label><input id="a" type="file">
      <label for="b">Additional document</label><input id="b" type="file">`);
    const inspection = inspectApplicationForm({ document: doc, url: URL_UNDER_TEST });

    expect(resolveUploadTarget(inspection, "supporting_document")).toMatchObject({ ambiguous: true, count: 2 });
    const outcome = attachDocument(doc, inspection, { ...attachment, role: "supporting_document" });
    expect(outcome.status).toBe("ambiguous");
    expect(doc.querySelector<HTMLInputElement>("#a")!.files!.length).toBe(0);
  });

  it("reports unsupported when the form has no control for the role", () => {
    const doc = setBody(`<label for="cv">CV / Resume</label><input id="cv" type="file">`);
    const inspection = inspectApplicationForm({ document: doc, url: URL_UNDER_TEST });
    expect(attachDocument(doc, inspection, { ...attachment, role: "cover_letter" }).status).toBe("unsupported");
  });

  it("refuses a file type the control does not accept", () => {
    const doc = setBody(`<label for="cv">CV / Resume</label><input id="cv" type="file" accept=".docx">`);
    const inspection = inspectApplicationForm({ document: doc, url: URL_UNDER_TEST });
    const outcome = attachDocument(doc, inspection, attachment);
    expect(outcome.status).toBe("rejected");
    expect(outcome.reasons.join(" ")).toMatch(/does not accept PDF/iu);
  });

  it("refuses a disabled control", () => {
    const doc = setBody(`<label for="cv">CV / Resume</label><input id="cv" type="file" disabled>`);
    const inspection = inspectApplicationForm({ document: doc, url: URL_UNDER_TEST });
    expect(attachDocument(doc, inspection, attachment).status).toBe("rejected");
  });

  it("reports unsupported rather than throwing where files cannot be attached", () => {
    // This is the jsdom path: no DataTransfer, so nothing is attached and the
    // caller is told plainly instead of receiving a false success.
    const doc = setBody(`<label for="cv">CV / Resume</label><input id="cv" type="file">`);
    const inspection = inspectApplicationForm({ document: doc, url: URL_UNDER_TEST });
    const outcome = attachDocument(doc, inspection, attachment);
    expect(outcome.status).toBe("unsupported");
    expect(doc.querySelector<HTMLInputElement>("#cv")!.files!.length).toBe(0);
  });
});

describe("AA-307 resume match", () => {
  const description =
    "You will design Kubernetes platforms, write Python services, and own CI/CD. " +
    "Required: Kubernetes, Python, Terraform, Go, observability.";

  it("scores only what the candidate can evidence, and explains the arithmetic", () => {
    const match = computeResumeMatch(description, profile());
    expect(match.matchedKeywords).toEqual(expect.arrayContaining(["kubernetes", "python"]));
    expect(match.missingKeywords).toEqual(expect.arrayContaining(["terraform"]));
    expect(match.score).toBe(Math.round((match.matchedKeywords.length / (match.matchedKeywords.length + match.missingKeywords.length)) * 100));
    expect(match.explanation).toMatch(/of \d+/u);
    expect(match.algorithmVersion).toBe("1.0.0");
  });

  it("does not let a posting inflate its score by repetition", () => {
    const repeated = `${description} Kubernetes Kubernetes Kubernetes Kubernetes`;
    expect(computeResumeMatch(repeated, profile()).score)
      .toBe(computeResumeMatch(description, profile()).score);
  });

  it("prefers resume evidence over profile evidence and records which was used", () => {
    const match = computeResumeMatch(description, profile(), "Terraform and Go every day.");
    const terraform = match.evidence.find((item) => item.keyword === "terraform");
    expect(terraform).toMatchObject({ source: "resume", confidence: 1 });
    const kubernetes = match.evidence.find((item) => item.keyword === "kubernetes");
    expect(kubernetes?.source).toBe("profile");
  });

  it("folds common synonyms so equivalent terms score", () => {
    const match = computeResumeMatch("We run k8s at scale.", profile());
    expect(match.matchedKeywords).toContain("kubernetes");
  });

  it("returns a zero score with an explanation when there is nothing to match", () => {
    const match = computeResumeMatch("", profile());
    expect(match.score).toBe(0);
    expect(match.explanation).toMatch(/no description/iu);
  });

  it("labels the score the way the panel shows it", () => {
    expect(matchVerdict(22)).toBe("Low");
    expect(matchVerdict(55)).toBe("Fair");
    expect(matchVerdict(88)).toBe("Strong");
  });
});

describe("AA-307 profile completeness", () => {
  it("names only what is missing", () => {
    const completeness = profileCompleteness(profile({ locations: { city: "Erlangen" } }));
    expect(completeness.missing.map((item) => item.fieldIntent))
      .toEqual(expect.arrayContaining(["location.residence_country", "location.postal_code"]));
    expect(completeness.completed).toBe(completeness.requiredTotal - completeness.missing.length);
  });

  it("reports a complete profile as complete", () => {
    const completeness = profileCompleteness(profile());
    expect(completeness.missing).toEqual([]);
    expect(completeness.completed).toBe(completeness.requiredTotal);
  });

  it("flags an empty work history because forms cannot be filled without it", () => {
    const completeness = profileCompleteness(profile({ workExperiences: [] }));
    expect(completeness.missing.some((item) => item.fieldIntent === "experience.title")).toBe(true);
  });
});
