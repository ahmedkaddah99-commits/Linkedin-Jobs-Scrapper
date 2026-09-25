import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it } from "vitest";
import {
  DEFAULT_FILL_POLICY,
  controlResolver,
  executeNativeValueAction,
  inspectApplicationForm,
  planApplicationFill,
  planSummary,
  type ApplicationFillPlan,
  type CandidateProfile,
  type NativeValueAction,
} from "@runr/ats-core";

const fixturesDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../fixtures");
const REGISTER_URL = "https://jobs.northwind-industries.com/en_US/externaljobs/Register?folderId=618402";

function loadRegisterForm(): Document {
  const html = readFileSync(path.join(fixturesDir, "avature-register-form.html"), "utf8");
  const parsed = new DOMParser().parseFromString(html, "text/html");
  document.documentElement.replaceWith(document.importNode(parsed.documentElement, true));
  return document;
}

/** Sanitized profile. No real candidate data appears in any test. */
function testProfile(): CandidateProfile {
  return {
    contact: {
      firstName: "Alex",
      lastName: "Fixture",
      email: "alex.fixture@example.com",
      phone: "+49 30 000000",
      website: "https://example.com/alex",
    },
    locations: {
      citizenship: "Germany",
      residenceCountry: "Germany",
      state: "Bavaria",
      city: "Erlangen",
      address: "1 Example Street",
      postalCode: "91052",
    },
    skills: ["Python", "Kubernetes"],
    workExperiences: [
      { title: "Platform Engineer", company: "Example Systems", description: "Built things.", location: "Berlin", startDate: "2023-12", endDate: "2024-07", isCurrent: false },
      { title: "Automation Engineer", company: "Second Example", startDate: "2021-01", endDate: "2023-11", isCurrent: false },
    ],
    education: [
      { school: "Example University", degree: "BSc", major: "Computer Science", startDate: "2017-09", endDate: "2020-06", isCurrent: false },
    ],
    preferences: {
      gender: "Prefer not to say",
      currentTitle: "Platform Engineer",
      notificationLanguage: "English",
    },
  };
}

function planFor(policy = DEFAULT_FILL_POLICY): ApplicationFillPlan {
  const inspection = inspectApplicationForm({ document: loadRegisterForm(), url: REGISTER_URL });
  return planApplicationFill(inspection, testProfile(), policy);
}

function plannedFor(plan: ApplicationFillPlan, labelPrefix: string) {
  return plan.planned.find((field) => field.label.toLowerCase().startsWith(labelPrefix.toLowerCase()));
}

describe("AA-304 deterministic fill planning", () => {
  beforeEach(() => {
    loadRegisterForm();
  });

  it("plans profile-backed answers for ordinary controls", () => {
    const plan = planFor();
    expect(plannedFor(plan, "First Name")).toMatchObject({ disposition: "fill", proposedValue: "Alex" });
    expect(plannedFor(plan, "Email")).toMatchObject({ disposition: "fill", proposedValue: "alex.fixture@example.com" });
    expect(plannedFor(plan, "Postal Code")).toMatchObject({ disposition: "fill", proposedValue: "91052" });
  });

  it("resolves a select answer to the option the control actually offers", () => {
    const plan = planFor({ ...DEFAULT_FILL_POLICY, permitSensitiveAutofill: true });
    // Profile says "Prefer not to say"; the control's value for it is "undisclosed".
    expect(plannedFor(plan, "Gender")).toMatchObject({ disposition: "fill", proposedValue: "undisclosed" });
  });

  it("routes a select answer to review when no option matches", () => {
    const inspection = inspectApplicationForm({ document: loadRegisterForm(), url: REGISTER_URL });
    const profile = testProfile();
    profile.preferences.gender = "Something the form does not offer";
    const plan = planApplicationFill(inspection, profile, { ...DEFAULT_FILL_POLICY, permitSensitiveAutofill: true });
    const gender = plan.planned.find((field) => field.intent === "demographic.gender");
    expect(gender?.disposition).toBe("review");
    expect(gender?.reasons.join(" ")).toMatch(/none of the available options/iu);
  });

  it("holds sensitive answers for confirmation unless the user permits them", () => {
    const guarded = planFor();
    expect(guarded.planned.find((field) => field.intent === "demographic.gender")?.disposition).toBe("review");
    expect(guarded.planned.find((field) => field.intent === "location.citizenship")?.disposition).toBe("review");

    const permitted = planFor({ ...DEFAULT_FILL_POLICY, permitSensitiveAutofill: true });
    expect(permitted.planned.find((field) => field.intent === "location.citizenship")?.disposition).toBe("fill");
  });

  it("never plans an action for a control that needs the user", () => {
    const plan = planFor();
    const manual = plan.planned.filter((field) => field.disposition === "manual");
    for (const field of manual) {
      expect(plan.actions.some((action) => "fieldId" in action && action.fieldId === field.fieldId)).toBe(false);
    }
  });

  it("keeps an answer the candidate already typed", () => {
    const inspection = inspectApplicationForm({ document: loadRegisterForm(), url: REGISTER_URL });
    document.querySelector<HTMLInputElement>("#first-name")!.value = "Already Here";
    const reinspected = inspectApplicationForm({ document, url: REGISTER_URL });
    const plan = planApplicationFill(reinspected, testProfile(), DEFAULT_FILL_POLICY);

    const firstName = plan.planned.find((field) => field.intent === "contact.first_name");
    expect(firstName?.disposition).toBe("skip");
    expect(firstName?.reasons.join(" ")).toMatch(/existing answer was kept/iu);
    expect(inspection.fields.length).toBeGreaterThan(0);
  });

  it("replaces an existing answer only when the user asked for it", () => {
    document.querySelector<HTMLInputElement>("#first-name")!.value = "Already Here";
    const inspection = inspectApplicationForm({ document, url: REGISTER_URL });
    const target = inspection.fields.find((field) => field.intent === "contact.first_name")!;
    const plan = planApplicationFill(inspection, testProfile(), {
      ...DEFAULT_FILL_POLICY,
      replaceFieldIds: [target.id],
    });
    expect(plan.planned.find((field) => field.intent === "contact.first_name")?.disposition).toBe("fill");
  });

  it("formats dates for the control in front of it", () => {
    const plan = planFor();
    // The fixture uses month controls; the profile stores YYYY-MM.
    const start = plan.planned.find((field) => field.intent === "experience.start_date");
    expect(start).toMatchObject({ disposition: "fill", proposedValue: "2023-12" });
  });

  it("maps each repeated block to its own profile entry", () => {
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
    const inspection = inspectApplicationForm({ document, url: REGISTER_URL });
    const plan = planApplicationFill(inspection, testProfile(), DEFAULT_FILL_POLICY);

    const titles = plan.planned.filter((field) => field.intent === "experience.title");
    expect(titles.map((field) => field.proposedValue)).toEqual(["Platform Engineer", "Automation Engineer"]);
  });

  it("drives enhanced list controls through the enhanced-selection action", () => {
    const plan = planFor();
    const skills = plan.planned.find((field) => field.intent === "profile.skills");
    expect(skills?.disposition).toBe("fill");

    // Skills take several values; each is verified by the executor.
    const action = plan.actions.find(
      (candidate) => candidate.type === "select_enhanced_options" && candidate.fieldId === skills!.fieldId,
    );
    expect(action).toMatchObject({ type: "select_enhanced_options", values: ["Python", "Kubernetes"] });
  });

  it("says plainly when the profile has no answer", () => {
    const plan = planFor();
    const visibility = plan.planned.find((field) => field.intent === "consent.visibility");
    expect(visibility?.disposition).toBe("review");
    expect(visibility?.reasons.join(" ")).toMatch(/no answer for this yet/iu);
  });

  it("leaves document controls to the document flow", () => {
    const plan = planFor();
    expect(plan.planned.find((field) => field.intent === "document.cv")?.disposition).toBe("skip");
  });

  it("summarises the plan for the progress display", () => {
    const summary = planSummary(planFor());
    expect(summary.fill).toBeGreaterThan(0);
    expect(summary.review).toBeGreaterThan(0);
    expect(summary.fill + summary.review + summary.manual + summary.skip)
      .toBe(planFor().planned.length);
  });
});

describe("AA-304 execution through the centralized executor", () => {
  it("writes every planned action and verifies it read back", () => {
    const document_ = loadRegisterForm();
    const inspection = inspectApplicationForm({ document: document_, url: REGISTER_URL });
    const plan = planApplicationFill(inspection, testProfile(), DEFAULT_FILL_POLICY);

    // Resolve planner field ids back to the real controls.
    const resolve = controlResolver(document_, inspection);

    // Enhanced selections run through their own asynchronous executor.
    const nativeActions = plan.actions.filter((action): action is NativeValueAction =>
      action.type !== "add_repeatable_section" &&
      action.type !== "upload_document" &&
      action.type !== "propose_intermediate_navigation" &&
      action.type !== "select_enhanced_options" &&
      action.type !== "select_combobox_option");

    expect(nativeActions.length).toBeGreaterThan(5);
    const results = nativeActions.map((action) => executeNativeValueAction(document_, action, resolve));
    const applied = results.filter((result) => result.status === "applied");

    expect(applied.length).toBe(nativeActions.length);
    expect(document_.querySelector<HTMLInputElement>("#first-name")!.value).toBe("Alex");
    expect(document_.querySelector<HTMLInputElement>("#email")!.value).toBe("alex.fixture@example.com");
    expect(document_.querySelector<HTMLInputElement>("#postal-code")!.value).toBe("91052");
  });

  it("refuses to operate the terminal control even if one is passed in", () => {
    const document_ = loadRegisterForm();
    const result = executeNativeValueAction(
      document_,
      { type: "fill_text", fieldId: "continue-application", value: "x" },
      (id) => document_.getElementById(id),
    );
    expect(result.status).toBe("rejected");
  });
});
