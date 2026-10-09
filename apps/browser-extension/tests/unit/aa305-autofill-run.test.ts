import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { installSubmissionGuard } from "@runr/ats-core";
import { runAutofill, type AutofillRunState } from "../../src/panel/autofill-run";
import { advanceIntermediateStep, findIntermediateNavigation } from "../../src/panel/step-navigation";
import { isoMonth, parsePeriod, toCandidateProfile } from "../../src/panel/profile-package";

const fixturesDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../fixtures");
const REGISTER_URL = "https://jobs.northwind-industries.com/en_US/externaljobs/Register?folderId=618402";

function loadRegisterForm(): Document {
  const html = readFileSync(path.join(fixturesDir, "avature-register-form.html"), "utf8");
  const parsed = new DOMParser().parseFromString(html, "text/html");
  document.documentElement.replaceWith(document.importNode(parsed.documentElement, true));
  return document;
}

function loadNavigationFixture(name: string): Document {
  const html = readFileSync(path.join(fixturesDir, name), "utf8");
  const parsed = new DOMParser().parseFromString(html, "text/html");
  document.body.innerHTML = parsed.body.innerHTML;
  return document;
}

/** Shaped like the backend profile package. Sanitized throughout. */
function profilePackagePayload() {
  return {
    schema_version: 1,
    candidate: {
      first_name: "Alex",
      last_name: "Fixture",
      full_name: "Alex Fixture",
      email: "alex.fixture@example.com",
      phone: "+49 30 000000",
      source: "confirmed_user_profile",
      approved: true,
      provenance: "user_profile",
    },
    answers: [
      ...[
        ["candidate.city", "Erlangen", "City"],
        ["candidate.postal_code", "91052", "Postal code"],
        ["candidate.state", "Bavaria", "State"],
        ["candidate.address", "1 Example Street", "Address"],
        ["candidate.country", "Germany", "Country"],
        ["candidate.current_title", "Platform Engineer", "Current title"],
        ["candidate.website", "https://example.com/alex", "Website"],
      ].map(([field_intent, proposed_value, label]) => ({
        field_intent, proposed_value, label, source: "profile_verified",
        sensitivity: "standard", scope: "global", confidence: 1,
        requires_review: false, provenance: "user_profile", reasons: ["confirmed"],
      })),
    ],
    experiences: [
      {
        role_title: "Platform Engineer",
        company: "Example Systems",
        location: "Berlin",
        period: "December 2023 - July 2024", source_experience_id: "experience-1",
        bullets: [{ bullet_id: "experience-1:description", text: "Built and ran deployment tooling.", approved_text: "Built and ran deployment tooling.", source_experience_id: "experience-1", provenance_id: "user_profile:experience-1", approved: true }],
        generation_provenance: { source: "career_memory", profile_id: "" },
        provenance_confidence: "reduced",
      },
    ],
    education: [{ institution: "Example University", degree: "BSc", period: "2017 - 2020", provenance: "user_profile", confirmed: true }],
    skills: [{ value: "Python", provenance: "user_profile", confirmed: true }, { value: "Kubernetes", provenance: "user_profile", confirmed: true }],
    languages: [],
    warnings: [],
  };
}

describe("AA-305 profile package mapping", () => {
  it("maps confirmed facts onto the planner's profile shape", () => {
    const profile = toCandidateProfile(profilePackagePayload())!;
    expect(profile.contact.firstName).toBe("Alex");
    expect(profile.contact.email).toBe("alex.fixture@example.com");
    expect(profile.locations.postalCode).toBe("91052");
    expect(profile.preferences.currentTitle).toBe("Platform Engineer");
    expect(profile.skills).toEqual(["Python", "Kubernetes"]);
  });

  it("turns a written period into month bounds the controls accept", () => {
    const profile = toCandidateProfile(profilePackagePayload())!;
    expect(profile.workExperiences[0]).toMatchObject({
      title: "Platform Engineer",
      company: "Example Systems",
      startDate: "2023-12",
      endDate: "2024-07",
      isCurrent: false,
    });
  });

  it("reads the month formats portals actually write", () => {
    expect(isoMonth("December 2023")).toBe("2023-12");
    expect(isoMonth("Dec 2023")).toBe("2023-12");
    expect(isoMonth("2023-12")).toBe("2023-12");
    expect(isoMonth("2023-1")).toBe("2023-01");
    expect(isoMonth("2023")).toBe("2023-01");
    expect(isoMonth("whenever")).toBeUndefined();
  });

  it("marks an open-ended period as current instead of inventing an end date", () => {
    expect(parsePeriod("January 2024 - Present")).toMatchObject({ startDate: "2024-01", isCurrent: true });
    expect(parsePeriod("January 2024 - Present").endDate).toBeUndefined();
  });

  it("returns null for a payload it cannot read", () => {
    expect(toCandidateProfile(null)).toBeNull();
    expect(toCandidateProfile("nope")).toBeNull();
  });
});

describe("AA-305 autofill run", () => {
  it("inspects, fills, and verifies the values landed in the page", async () => {
    const document_ = loadRegisterForm();
    const profile = toCandidateProfile(profilePackagePayload())!;

    const state = await runAutofill({
      document: document_,
      url: REGISTER_URL,
      profile,
      policy: { preserveExistingValues: true, permitSensitiveAutofill: false },
    });

    expect(state.stage).toBe("complete");
    expect(state.detectedCount).toBeGreaterThan(25);
    expect(state.filledCount).toBeGreaterThan(5);

    // Verified against the DOM, not against the plan.
    expect(document_.querySelector<HTMLInputElement>("#first-name")!.value).toBe("Alex");
    expect(document_.querySelector<HTMLInputElement>("#email")!.value).toBe("alex.fixture@example.com");
    expect(document_.querySelector<HTMLInputElement>("#postal-code")!.value).toBe("91052");
    expect(document_.querySelector<HTMLInputElement>("#exp-0-start")!.value).toBe("2023-12");
  });

  it("reports progress through detecting and filling before completing", async () => {
    const document_ = loadRegisterForm();
    const stages: AutofillRunState["stage"][] = [];
    await runAutofill({
      document: document_,
      url: REGISTER_URL,
      profile: toCandidateProfile(profilePackagePayload())!,
      policy: { preserveExistingValues: true, permitSensitiveAutofill: false },
      onProgress: (state) => {
        if (stages[stages.length - 1] !== state.stage) stages.push(state.stage);
      },
    });
    expect(stages).toEqual(["detecting", "filling", "complete"]);
  });

  it("never fills a control that needs the user", async () => {
    const document_ = loadRegisterForm();
    const state = await runAutofill({
      document: document_,
      url: REGISTER_URL,
      profile: toCandidateProfile(profilePackagePayload())!,
      policy: { preserveExistingValues: true, permitSensitiveAutofill: false },
    });
    // Gender is sensitive and the policy withholds it.
    const gender = state.results.find((result) => result.intent === "demographic.gender");
    expect(gender?.outcome).toBe("needs_review");
    expect(document_.querySelector<HTMLSelectElement>("#gender")!.value).toBe("");
  });

  it("keeps an answer the candidate already typed", async () => {
    const document_ = loadRegisterForm();
    document_.querySelector<HTMLInputElement>("#first-name")!.value = "Typed By Hand";
    const state = await runAutofill({
      document: document_,
      url: REGISTER_URL,
      profile: toCandidateProfile(profilePackagePayload())!,
      policy: { preserveExistingValues: true, permitSensitiveAutofill: false },
    });
    expect(state.results.find((result) => result.intent === "contact.first_name")?.outcome).toBe("kept");
    expect(document_.querySelector<HTMLInputElement>("#first-name")!.value).toBe("Typed By Hand");
  });

  it("counts fields needing review the way the panel reports them", async () => {
    const state = await runAutofill({
      document: loadRegisterForm(),
      url: REGISTER_URL,
      profile: toCandidateProfile(profilePackagePayload())!,
      policy: { preserveExistingValues: true, permitSensitiveAutofill: false },
    });
    const counted = state.results.filter(
      (result) => result.outcome === "needs_review" || result.outcome === "manual",
    ).length;
    expect(state.reviewCount).toBe(counted);
    expect(state.reviewCount).toBeGreaterThan(0);
  });
});

describe("T51 verified intermediate-step navigation", () => {
  it("finds one Continue control only with an explicit active step and a following step", () => {
    const document_ = loadNavigationFixture("avature-register-form.html");
    const target = findIntermediateNavigation(document_);

    expect(target).toMatchObject({
      currentStepLabel: "Profile information",
      nextStepLabel: "Global questions",
      currentIndex: 1,
    });
    expect(target?.control.id).toBe("continue-application");

    target?.currentStep.removeAttribute("aria-current");
    expect(findIntermediateNavigation(document_)).toBeNull();
  });

  it("lets terminal wording, terminal state, and ambiguous controls override Continue", () => {
    const document_ = loadNavigationFixture("avature-register-form.html");
    const control = document_.querySelector<HTMLButtonElement>("#continue-application")!;

    control.textContent = "Continue and Submit Application";
    expect(findIntermediateNavigation(document_)).toBeNull();
    control.textContent = "Continue Application";
    control.setAttribute("data-final-submit", "true");
    expect(findIntermediateNavigation(document_)).toBeNull();
    control.removeAttribute("data-final-submit");
    const second = control.cloneNode(true) as HTMLButtonElement;
    second.textContent = "Next step";
    control.after(second);
    expect(findIntermediateNavigation(document_)).toBeNull();
  });

  it("activates once and reports the exact next step after the active marker moves", async () => {
    const document_ = loadNavigationFixture("avature-register-form.html");
    const target = findIntermediateNavigation(document_)!;
    const guard = installSubmissionGuard(document_);
    const eventOffset = guard.events.length;
    target.control.addEventListener("click", (event) => {
      target.currentStep.removeAttribute("aria-current");
      target.nextStep.setAttribute("aria-current", "step");
      event.preventDefault();
    });

    const result = await advanceIntermediateStep(document_, target);

    expect(result).toEqual({ status: "advanced", nextStepLabel: "Global questions" });
    expect(guard.events.slice(eventOffset)).toEqual(["click"]);
    expect(document_.querySelector('[aria-current="step"]')?.textContent?.trim()).toBe("Global questions");
    guard.stop();
  });

  it("refuses a replaced control before activation", async () => {
    const document_ = loadNavigationFixture("avature-register-form.html");
    const target = findIntermediateNavigation(document_)!;
    let clicks = 0;
    target.control.addEventListener("click", () => { clicks += 1; });
    target.control.replaceWith(target.control.cloneNode(true));
    const guard = installSubmissionGuard(document_);
    const eventOffset = guard.events.length;

    const result = await advanceIntermediateStep(document_, target);

    expect(result.status).toBe("refused");
    expect(clicks).toBe(0);
    expect(guard.events.slice(eventOffset)).toEqual([]);
    guard.stop();
  });

  it("never activates the final-step fixture or changes its URL", async () => {
    const document_ = loadNavigationFixture("avature-final-step.html");
    const finalControl = document_.querySelector<HTMLButtonElement>("#final-submit")!;
    const initialUrl = document_.defaultView?.location.href;
    let clicks = 0;
    finalControl.addEventListener("click", () => { clicks += 1; });
    const guard = installSubmissionGuard(document_);
    const eventOffset = guard.events.length;

    const result = await advanceIntermediateStep(document_);

    expect(findIntermediateNavigation(document_)).toBeNull();
    expect(result.status).toBe("refused");
    expect(clicks).toBe(0);
    expect(guard.events.slice(eventOffset)).toEqual([]);
    expect(document_.defaultView?.location.href).toBe(initialUrl);
    guard.stop();
  });
});
