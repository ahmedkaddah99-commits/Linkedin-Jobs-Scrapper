import { describe, expect, it } from "vitest";
import {
  applyAnswerDecision,
  canReuseAnswer,
  classifyQuestion,
  hasSufficientEvidence,
  inspectApplicationForm,
  partitionQuestions,
  type DetectedApplicationField,
  type ProposedAnswer,
} from "@runr/ats-core";

function field(overrides: Partial<Omit<DetectedApplicationField, "intent">> & { intent?: string }): DetectedApplicationField {
  return {
    id: "field-x",
    locator: { elementId: "x" },
    label: "A question",
    controlType: "textarea",
    required: false,
    currentValue: "",
    sensitivity: "normal",
    sourceEvidence: [],
    confidence: 0.5,
    ...overrides,
    intent: (overrides.intent ?? "question.free_text") as DetectedApplicationField["intent"],
  };
}

describe("AA-308 question classification", () => {
  it("treats profile-backed fields as common questions", () => {
    for (const intent of ["contact.email", "location.city", "experience.title", "preference.relocation"]) {
      expect(classifyQuestion(field({ intent })).questionClass).toBe("common");
    }
  });

  it("treats posting-specific free text as a unique question Runr may draft", () => {
    const question = classifyQuestion(field({
      intent: "question.free_text",
      label: "Why do you want to work here?",
      controlType: "textarea",
    }));
    expect(question.questionClass).toBe("unique");
    expect(question.eligibility).toBe("eligible");
  });

  it("holds questions that ask for a claim about the candidate", () => {
    for (const label of [
      "How many years of Kubernetes experience do you have?",
      "Do you have a security clearance?",
      "Are you willing to relocate?",
      "What is your expected salary?",
    ]) {
      const question = classifyQuestion(field({ intent: "question.free_text", label }));
      expect(question.eligibility).toBe("requires_user_confirmation");
      expect(question.reason).toMatch(/claim about you|confirm/iu);
    }
  });

  it("never offers to answer categories Runr must not answer", () => {
    for (const intent of [
      "demographic.race", "demographic.veteran", "demographic.disability", "demographic.gender",
      "legal.declaration", "legal.terms", "assessment", "captcha", "credential.password",
    ]) {
      expect(classifyQuestion(field({ intent })).eligibility).toBe("manual_only");
    }
  });

  it("will not pick between options on a unique question", () => {
    const question = classifyQuestion(field({
      intent: "question.select",
      label: "Which office would you prefer?",
      controlType: "select",
    }));
    expect(question.questionClass).toBe("unique");
    expect(question.eligibility).toBe("requires_user_confirmation");
  });

  it("holds sensitive common questions for confirmation", () => {
    const question = classifyQuestion(field({ intent: "legal.sponsorship", sensitivity: "sensitive" }));
    expect(question.questionClass).toBe("common");
    expect(question.eligibility).toBe("requires_user_confirmation");
  });

  it("splits a real form into common and unique groups", () => {
    document.documentElement.replaceWith(document.createElement("html"));
    document.documentElement.innerHTML = `<head></head><body>
      <label for="a">First Name</label><input id="a">
      <label for="b">Email</label><input id="b" type="email">
      <label for="c">Why are you a good fit for this role?</label><textarea id="c"></textarea>
      <label for="d">Describe your proudest project</label><textarea id="d"></textarea>
    </body>`;
    const inspection = inspectApplicationForm({ document, url: "https://jobs.example.com/apply" });
    const { common, unique } = partitionQuestions(inspection.fields);

    expect(common.map((q) => q.intent)).toEqual(expect.arrayContaining(["contact.first_name", "contact.email"]));
    expect(unique).toHaveLength(2);
    expect(unique.every((q) => q.eligibility === "eligible")).toBe(true);
  });
});

describe("AA-308 evidence and answer review", () => {
  const corpus = "Platform engineer. Ran Kubernetes clusters and built deployment tooling for payment services.";

  it("requires the candidate's own material to support a draft", () => {
    expect(hasSufficientEvidence("Describe your Kubernetes deployment experience", corpus)).toBe(true);
  });

  it("refuses to draft when nothing in the profile supports the question", () => {
    expect(hasSufficientEvidence("Describe your veterinary surgery accreditation", corpus)).toBe(false);
    expect(hasSufficientEvidence("", corpus)).toBe(false);
  });

  it("moves an answer through edit, regenerate, accept, and reject", () => {
    const initial: ProposedAnswer = {
      fieldId: "field-c",
      questionLabel: "Why are you a good fit?",
      value: "First draft.",
      state: "proposed",
      sources: ["profile"],
      regenerations: 0,
    };

    const edited = applyAnswerDecision(initial, { type: "edit", value: "My words." });
    expect(edited).toMatchObject({ value: "My words.", state: "edited" });

    const regenerated = applyAnswerDecision(edited, { type: "regenerate", value: "Second draft." });
    expect(regenerated).toMatchObject({ value: "Second draft.", state: "proposed", regenerations: 1 });

    expect(applyAnswerDecision(regenerated, { type: "accept" }).state).toBe("accepted");

    const rejected = applyAnswerDecision(regenerated, { type: "reject" });
    expect(rejected).toMatchObject({ state: "rejected", value: "" });
  });

  it("reuses a saved answer only for the same question", () => {
    expect(canReuseAnswer("Why do you want to work here?", "why do you want to work here?")).toBe(true);
    expect(canReuseAnswer("Why do you want to work here?", "Why do you want to work at Acme?")).toBe(false);
    expect(canReuseAnswer("", "Anything")).toBe(false);
  });
});
