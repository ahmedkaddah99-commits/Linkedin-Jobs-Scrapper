import { beforeEach, describe, expect, it } from "vitest";
import {
  LeverAdapter,
  runLeverStandardFacts,
  planLeverApplication,
  type ApplicationPackage,
} from "@runr/ats-core";

function packageFor(answers: ApplicationPackage["answers"] = []): ApplicationPackage {
  return {
    id: "aa220-lever-package",
    version: 1,
    candidate: { fullName: "Ada Lovelace", email: "ada@example.com" },
    answers,
  };
}

describe("AA-220 Lever adapter contract", () => {
  beforeEach(() => {
    document.documentElement.dataset.runrAssistedApplyFixture = "lever";
    document.body.innerHTML = `
      <form>
        <label for="name">Full name</label>
        <input id="name" name="name" autocomplete="name" required>
        <label for="sensitive">Work authorization</label>
        <input id="sensitive" name="work_authorization">
        <button id="final-submit" type="submit">Submit application</button>
      </form>`;
  });

  it("detects, inspects, and plans only declarative non-terminal actions", async () => {
    const plan = await planLeverApplication(
      document,
      "https://jobs.lever.co/example/1",
      packageFor(),
    );

    expect(plan.actions).toEqual([
      expect.objectContaining({ type: "fill_text", value: "Ada Lovelace" }),
    ]);
    expect(plan.actions.some((action) => action.type === "propose_intermediate_navigation")).toBe(false);
    expect(plan.actions.some((action) => action.type === "upload_document")).toBe(false);
    expect(plan.actions.some((action) => /submit|terminal/iu.test(action.type))).toBe(false);
    expect(plan.manualReasons).toContain("final_submission");
    expect(plan.stopsAtReview).toBe(true);
    expect(plan.unresolved.some((item) => /repeatable experience\/education/iu.test(item))).toBe(true);
    expect(document.querySelector<HTMLInputElement>("#name")!.value).toBe("");
  });

  it("preserves nonempty values and leaves sensitive answers unresolved", async () => {
    document.querySelector<HTMLInputElement>("#name")!.value = "Existing Name";
    const plan = await planLeverApplication(
      document,
      "https://jobs.lever.co/example/1",
      packageFor([
        { fieldIntent: "application.work_authorization", label: "Work authorization", proposedValue: "Yes" },
      ]),
    );

    expect(plan.actions).toEqual([]);
    expect(plan.unresolved).toEqual(expect.arrayContaining([
      expect.stringContaining("Full name"),
      expect.stringContaining("Work authorization"),
    ]));
    expect(document.querySelector<HTMLInputElement>("#name")!.value).toBe("Existing Name");
  });

  it("fails closed outside a confirmed Lever page", async () => {
    delete document.documentElement.dataset.runrAssistedApplyFixture;
    const adapter = new LeverAdapter();
    const detection = await adapter.detect({ document, url: "https://boards.greenhouse.io/example/jobs/1" });
    expect(detection.ats).toBe("greenhouse");
    const plan = await planLeverApplication(document, "https://boards.greenhouse.io/example/jobs/1", packageFor());
    expect(plan.actions).toEqual([]);
    expect(plan.stopsAtReview).toBe(true);
  });

  it("matches confirmed Career Memory facts to common Lever profile controls by intent", async () => {
    document.body.innerHTML = `
      <form>
        <label>Current location <input name="location"></label>
        <label>Current company <input name="company"></label>
        <label>GitHub URL <input name="github"></label>
        <label>Other website <input name="website"></label>
        <label>Why this company? <textarea name="why"></textarea></label>
        <button type="submit">Submit application</button>
      </form>`;
    const result = await runLeverStandardFacts(
      document,
      "https://jobs.lever.co/example/1/apply",
      "career-memory-package",
      1,
      {},
      [
        { fieldIntent: "candidate.location", label: "Current location", proposedValue: "Berlin, Germany" },
        { fieldIntent: "candidate.current_company", label: "Current company", proposedValue: "Analytical Engines" },
        { fieldIntent: "candidate.github_url", label: "GitHub URL", proposedValue: "https://github.com/ada" },
        { fieldIntent: "candidate.website", label: "Website", proposedValue: "https://ada.example" },
      ],
    );

    expect(result.executions.map((item) => [item.fieldIntent, item.status])).toEqual([
      ["candidate.location", "filled"],
      ["candidate.current_company", "filled"],
      ["candidate.github_url", "filled"],
      ["candidate.website", "filled"],
    ]);
    expect(document.querySelector<HTMLInputElement>('input[name="location"]')!.value).toBe("Berlin, Germany");
    expect(document.querySelector<HTMLInputElement>('input[name="website"]')!.value).toBe("https://ada.example");
    expect(document.querySelector<HTMLTextAreaElement>('textarea[name="why"]')!.value).toBe("");
  });

  it("fills the nested controls used by the live Lever application layout", async () => {
    document.body.innerHTML = `
      <form>
        <li class="application-question"><label><div class="application-label">Full name<span class="required">*</span></div><div class="application-field"><input type="text" data-qa="name-input" name="name" required></div></label></li>
        <li class="application-question"><label><div class="application-label">Email<span class="required">*</span></div><div class="application-field"><input name="email" data-qa="email-input" type="email" required></div></label></li>
        <li class="application-question"><label><div class="application-label">Phone</div><div class="application-field"><input type="text" data-qa="phone-input" name="phone"></div></label></li>
        <li class="application-question" data-qa="structured-contact-location-question"><label><div class="application-label">Current location</div><div class="application-field"><input class="location-input" data-qa="location-input" id="location-input" type="text" name="location"><input id="selected-location" type="hidden" name="selectedLocation"><div class="dropdown-results"></div></div></label></li>
        <li class="application-question"><label><div class="application-label">Current company</div><div class="application-field"><input type="text" data-qa="org-input" name="org"></div></label></li>
        <li class="application-question"><label><div class="application-label">LinkedIn URL</div><div class="application-field"><input type="text" name="urls[LinkedIn]"></div></label></li>
        <li class="application-question"><label><div class="application-label">GitHub URL</div><div class="application-field"><input type="text" name="urls[GitHub]"></div></label></li>
        <li class="application-question"><label><div class="application-label">Portfolio URL</div><div class="application-field"><input type="text" name="urls[Portfolio]"></div></label></li>
        <li class="application-question"><label><div class="application-label">Other website</div><div class="application-field"><input type="text" name="urls[Other]"></div></label></li>
        <li class="application-question custom-question"><div><div class="application-label full-width textarea"><div class="text">Why this position?<span class="required">*</span></div></div><div class="application-field full-width required-field"><textarea class="card-field-input" name="cards[question][field]" required></textarea></div></div></li>
        <button type="submit">Submit application</button>
      </form>`;
    const locationInput = document.querySelector<HTMLInputElement>("#location-input")!;
    locationInput.addEventListener("input", () => {
      const results = document.querySelector<HTMLElement>(".dropdown-results")!;
      if (results.childElementCount) return;
      const option = document.createElement("button");
      option.type = "button";
      option.setAttribute("data-qa", "location-option");
      option.textContent = "Berlin, Germany";
      option.addEventListener("click", () => {
        locationInput.value = "Berlin, Germany";
        document.querySelector<HTMLInputElement>("#selected-location")!.value = "Berlin, Germany";
      });
      results.append(option);
    });
    const result = await runLeverStandardFacts(
      document,
      "https://jobs.lever.co/example/1/apply",
      "live-lever-package",
      1,
      { fullName: "Ada Lovelace", email: "ada@example.com", phone: "+44 20 7946 0958" },
      [
        { fieldIntent: "candidate.location", label: "Current location", proposedValue: "Berlin, Germany" },
        { fieldIntent: "candidate.current_company", label: "Current company", proposedValue: "Analytical Engines" },
        { fieldIntent: "candidate.linkedin_url", label: "LinkedIn URL", proposedValue: "https://linkedin.example/ada" },
        { fieldIntent: "candidate.github_url", label: "GitHub URL", proposedValue: "https://github.example/ada" },
        { fieldIntent: "candidate.portfolio_url", label: "Portfolio URL", proposedValue: "https://portfolio.example/ada" },
        { fieldIntent: "candidate.website", label: "Other website", proposedValue: "https://ada.example" },
      ],
    );

    expect(result.executions.map((item) => [item.fieldIntent, item.status])).toEqual([
      ["candidate.full_name", "filled"],
      ["candidate.email", "filled"],
      ["candidate.phone", "filled"],
      ["candidate.location", "filled"],
      ["candidate.current_company", "filled"],
      ["candidate.linkedin_url", "filled"],
      ["candidate.github_url", "filled"],
      ["candidate.portfolio_url", "filled"],
      ["candidate.website", "filled"],
    ]);
    expect(document.querySelector<HTMLTextAreaElement>("textarea.card-field-input")!.value).toBe("");
    expect(document.querySelector<HTMLInputElement>("#selected-location")!.value).toBe("Berlin, Germany");
  });

  it("reuses an exact approved non-sensitive question answer", async () => {
    document.body.innerHTML = `
      <form>
        <label>Why this position? *<textarea name="why" required></textarea></label>
        <button type="submit">Submit application</button>
      </form>`;
    const result = await runLeverStandardFacts(
      document,
      "https://jobs.lever.co/example/1/apply",
      "saved-answer-package",
      1,
      {},
      [{ fieldIntent: "question.exact.safe", label: "why this position?", proposedValue: "I enjoy reliable systems." }],
    );
    expect(result.executions).toEqual([
      expect.objectContaining({ fieldIntent: "question.exact.safe", status: "filled" }),
    ]);
    expect(document.querySelector<HTMLTextAreaElement>('textarea[name="why"]')!.value).toBe("I enjoy reliable systems.");
  });
});
