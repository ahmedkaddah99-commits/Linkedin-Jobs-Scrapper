import { beforeEach, describe, expect, it } from "vitest";
import {
  ADAPTER_SUBMISSION_CAPABILITY_FORBIDDEN,
  ATS_ADAPTER_CAPABILITIES,
  GreenhouseAdapter,
  detectAtsFromUrl,
  runGreenhouseFixtureProof,
  type ApprovedFieldMatch,
} from "@runr/ats-core";

function renderFixture(emailValue = ""): void {
  document.documentElement.dataset.runrAssistedApplyFixture = "greenhouse";
  document.body.innerHTML = `
    <form id="application-form">
      <label for="first-name">First name</label>
      <input id="first-name" name="first_name" value="Existing Candidate" required>
      <label for="email">Email address</label>
      <input id="email" name="email" type="email" value="${emailValue}" required>
      <input id="disabled" name="disabled" disabled>
      <input id="hidden" name="hidden" type="hidden">
      <label for="captcha">CAPTCHA response</label>
      <input id="captcha" name="g-recaptcha-response">
      <label for="signature">Signature</label>
      <input id="signature" name="signature">
      <label for="declaration">I certify this declaration is accurate</label>
      <input id="declaration" name="declaration" type="checkbox">
      <label for="terms">Accept terms and conditions</label>
      <input id="terms" name="terms" type="checkbox">
      <label for="assessment">Coding assessment</label>
      <textarea id="assessment" name="assessment"></textarea>
      <button id="submit" type="submit">Submit application</button>
    </form>
  `;
}

describe("ATS detection and submission guardrail", () => {
  it("recognizes only owned Greenhouse and supported Lever hosts", () => {
    expect(detectAtsFromUrl("https://boards.greenhouse.io/acme/jobs/1").ats).toBe("greenhouse");
    expect(detectAtsFromUrl("https://job-boards.greenhouse.io/acme/jobs/1").ats).toBe("greenhouse");
    expect(detectAtsFromUrl("https://jobs.lever.co/acme/1").ats).toBe("lever");
    expect(detectAtsFromUrl("https://jobs.eu.lever.co/acme/1").ats).toBe("lever");
    expect(detectAtsFromUrl("https://boards.greenhouse.io.evil.example/jobs/1").ats).toBeNull();
    expect(detectAtsFromUrl("http://boards.greenhouse.io/acme/jobs/1").ats).toBeNull();
  });

  it("has no final submission capability in the adapter contract", () => {
    expect(ADAPTER_SUBMISSION_CAPABILITY_FORBIDDEN).toBe(true);
    expect(ATS_ADAPTER_CAPABILITIES).not.toContain("submit");
    expect(ATS_ADAPTER_CAPABILITIES).not.toContain("submitApplication");
  });
});

describe("Greenhouse fixture proof", () => {
  beforeEach(() => renderFixture());

  it("fills an empty verified email with the expected events and readback", async () => {
    const email = document.querySelector<HTMLInputElement>("#email")!;
    const events: string[] = [];
    for (const name of ["focus", "input", "change", "blur"]) {
      email.addEventListener(name, () => events.push(name));
    }
    let submissions = 0;
    document.querySelector("form")!.addEventListener("submit", (event) => {
      event.preventDefault();
      submissions += 1;
    });

    const result = await runGreenhouseFixtureProof(
      document,
      "http://127.0.0.1:4174/greenhouse-application.html",
      "candidate@example.com",
    );

    expect(result.execution?.status).toBe("filled");
    expect(result.execution?.acceptedValue).toBe("candidate@example.com");
    expect(email.value).toBe("candidate@example.com");
    expect(events).toEqual(["focus", "input", "change", "blur"]);
    expect(document.querySelector<HTMLInputElement>("#first-name")!.value).toBe("Existing Candidate");
    expect(submissions).toBe(0);
    expect(result.manualReasons).toEqual(
      expect.arrayContaining([
        "final_submission",
        "captcha",
        "signature",
        "legal_declaration",
        "legal_terms",
        "assessment",
      ]),
    );
  });

  it("is idempotent and does not dispatch the fill lifecycle twice", async () => {
    const email = document.querySelector<HTMLInputElement>("#email")!;
    let inputEvents = 0;
    email.addEventListener("input", () => {
      inputEvents += 1;
    });

    const first = await runGreenhouseFixtureProof(
      document,
      "http://127.0.0.1:4174/greenhouse-application.html",
      "candidate@example.com",
    );
    const second = await runGreenhouseFixtureProof(
      document,
      "http://127.0.0.1:4174/greenhouse-application.html",
      "candidate@example.com",
    );

    expect(first.execution?.status).toBe("filled");
    expect(second.execution?.status).toBe("already_filled");
    expect(inputEvents).toBe(1);
  });

  it("preserves a pre-existing browser, ATS, or user value", async () => {
    renderFixture("person@existing.example");
    const result = await runGreenhouseFixtureProof(
      document,
      "http://127.0.0.1:4174/greenhouse-application.html",
      "candidate@example.com",
    );

    expect(result.execution?.status).toBe("preserved_existing");
    expect(document.querySelector<HTMLInputElement>("#email")!.value).toBe(
      "person@existing.example",
    );
  });

  it("does not approve disabled or hidden email controls for execution", async () => {
    const email = document.querySelector<HTMLInputElement>("#email")!;
    email.disabled = true;
    let result = await runGreenhouseFixtureProof(
      document,
      "http://127.0.0.1:4174/greenhouse-application.html",
      "candidate@example.com",
    );
    expect(result.execution).toBeNull();
    expect(email.value).toBe("");

    email.disabled = false;
    email.hidden = true;
    result = await runGreenhouseFixtureProof(
      document,
      "http://127.0.0.1:4174/greenhouse-application.html",
      "candidate@example.com",
    );
    expect(result.execution).toBeNull();
    expect(email.value).toBe("");
  });

  it("treats a control inside a CSS-hidden ancestor as hidden", async () => {
    const email = document.querySelector<HTMLInputElement>("#email")!;
    const wrapper = document.createElement("div");
    wrapper.style.display = "none";
    email.replaceWith(wrapper);
    wrapper.append(email);

    const result = await runGreenhouseFixtureProof(
      document,
      "http://127.0.0.1:4174/greenhouse-application.html",
      "candidate@example.com",
    );

    expect(result.execution).toBeNull();
    expect(email.value).toBe("");
  });

  it("preserves a field the user clears after Runr filled it", async () => {
    const email = document.querySelector<HTMLInputElement>("#email")!;
    const first = await runGreenhouseFixtureProof(
      document,
      "http://127.0.0.1:4174/greenhouse-application.html",
      "candidate@example.com",
    );
    email.value = "";
    email.dispatchEvent(new Event("input", { bubbles: true }));

    const second = await runGreenhouseFixtureProof(
      document,
      "http://127.0.0.1:4174/greenhouse-application.html",
      "candidate@example.com",
    );

    expect(first.execution?.status).toBe("filled");
    expect(second.execution?.status).toBe("preserved_existing");
    expect(email.value).toBe("");
  });

  it("keeps every manual, hidden, disabled, and unknown field non-fillable", async () => {
    const adapter = new GreenhouseAdapter();
    const form = await adapter.inspect({
      document,
      url: "http://127.0.0.1:4174/greenhouse-application.html",
    });
    const matches = await adapter.match(form, {
      id: "guardrail-test",
      version: 1,
      candidate: { email: "candidate@example.com" },
    });

    for (const field of form.fields) {
      if (
        field.classification === "manual" ||
        field.hidden ||
        field.disabled ||
        field.type === "unknown"
      ) {
        expect(matches.find((match) => match.detectedFieldId === field.id)?.action).not.toBe(
          "fill",
        );
      }
    }
  });

  it("rejects forged approved matches for every manual-only control", async () => {
    const adapter = new GreenhouseAdapter();
    const form = await adapter.inspect({
      document,
      url: "http://127.0.0.1:4174/greenhouse-application.html",
    });
    const manualFields = form.fields.filter((field) => field.classification === "manual");

    expect(manualFields.map((field) => field.manualReason)).toEqual(
      expect.arrayContaining([
        "final_submission",
        "captcha",
        "signature",
        "legal_declaration",
        "legal_terms",
        "assessment",
        "unsupported_control",
      ]),
    );

    for (const field of manualFields) {
      const forgedMatch: ApprovedFieldMatch = {
        detectedFieldId: field.id,
        fieldLabel: field.label,
        fieldIntent: "forged.manual.answer",
        proposedValue: "must-not-run",
        confidence: 1,
        source: "profile_verified",
        sensitivity: "standard",
        action: "fill",
        reasons: ["Hostile test message"],
      };
      expect((await adapter.fill(forgedMatch)).status).toBe("rejected");
    }

    expect(document.querySelector<HTMLInputElement>("#captcha")!.value).toBe("");
    expect(document.querySelector<HTMLInputElement>("#signature")!.value).toBe("");
    expect(document.querySelector<HTMLInputElement>("#declaration")!.checked).toBe(false);
    expect(document.querySelector<HTMLInputElement>("#terms")!.checked).toBe(false);
    expect(document.querySelector<HTMLTextAreaElement>("#assessment")!.value).toBe("");
  });

  it("rejects email-labelled checkbox, radio, date, file, and unrelated text controls", async () => {
    document.querySelector("form")!.insertAdjacentHTML(
      "afterbegin",
      `
        <label for="email-checkbox">Email checkbox</label>
        <input id="email-checkbox" name="email" type="checkbox">
        <label for="email-radio">Email radio</label>
        <input id="email-radio" name="email" type="radio">
        <label for="email-date">Email date</label>
        <input id="email-date" name="email" type="date">
        <label for="email-file">Email file</label>
        <input id="email-file" name="email" type="file">
      `,
    );
    const adapter = new GreenhouseAdapter();
    const form = await adapter.inspect({
      document,
      url: "http://127.0.0.1:4174/greenhouse-application.html",
    });
    const matches = await adapter.match(form, {
      id: "type-confusion-test",
      version: 1,
      candidate: { email: "candidate@example.com" },
    });

    const hostileIds = ["email-checkbox", "email-radio", "email-date", "email-file"];
    for (const controlId of hostileIds) {
      const field = form.fields.find(
        (candidate) => candidate.locator.stableAttributes.id === controlId,
      )!;
      expect(matches.find((match) => match.detectedFieldId === field.id)?.action).not.toBe(
        "fill",
      );
      const forgedMatch: ApprovedFieldMatch = {
        detectedFieldId: field.id,
        fieldLabel: field.label,
        fieldIntent: "candidate.email",
        proposedValue: "must-not-run",
        confidence: 1,
        source: "profile_verified",
        sensitivity: "personal",
        action: "fill",
        reasons: ["Hostile type-confusion test"],
      };
      expect((await adapter.fill(forgedMatch)).status).toBe("rejected");
    }

    const firstName = form.fields.find(
      (field) => field.locator.stableAttributes.id === "first-name",
    )!;
    const forgedFirstName: ApprovedFieldMatch = {
      detectedFieldId: firstName.id,
      fieldLabel: firstName.label,
      fieldIntent: "candidate.email",
      proposedValue: "must-not-run",
      confidence: 1,
      source: "profile_verified",
      sensitivity: "personal",
      action: "fill",
      reasons: ["Hostile unrelated-text test"],
    };
    expect((await adapter.fill(forgedFirstName)).status).toBe("rejected");
    expect(document.querySelector<HTMLInputElement>("#first-name")!.value).toBe(
      "Existing Candidate",
    );
  });

  it("rejects a control repurposed or replaced after inspection", async () => {
    let adapter = new GreenhouseAdapter();
    let form = await adapter.inspect({
      document,
      url: "http://127.0.0.1:4174/greenhouse-application.html",
    });
    let matches = await adapter.match(form, {
      id: "live-mutation-test",
      version: 1,
      candidate: { email: "candidate@example.com" },
    });
    let approved = matches.find(
      (match): match is ApprovedFieldMatch => match.action === "fill",
    )!;
    let email = document.querySelector<HTMLInputElement>("#email")!;
    email.type = "checkbox";

    expect((await adapter.fill(approved)).status).toBe("rejected");
    expect(email.checked).toBe(false);

    renderFixture();
    adapter = new GreenhouseAdapter();
    form = await adapter.inspect({
      document,
      url: "http://127.0.0.1:4174/greenhouse-application.html",
    });
    matches = await adapter.match(form, {
      id: "live-manual-test",
      version: 1,
      candidate: { email: "candidate@example.com" },
    });
    approved = matches.find(
      (match): match is ApprovedFieldMatch => match.action === "fill",
    )!;
    email = document.querySelector<HTMLInputElement>("#email")!;
    email.name = "g-recaptcha-response";

    expect((await adapter.fill(approved)).status).toBe("rejected");
    expect(email.value).toBe("");

    renderFixture();
    adapter = new GreenhouseAdapter();
    form = await adapter.inspect({
      document,
      url: "http://127.0.0.1:4174/greenhouse-application.html",
    });
    matches = await adapter.match(form, {
      id: "live-replacement-test",
      version: 1,
      candidate: { email: "candidate@example.com" },
    });
    approved = matches.find(
      (match): match is ApprovedFieldMatch => match.action === "fill",
    )!;
    email = document.querySelector<HTMLInputElement>("#email")!;
    const replacement = email.cloneNode(true) as HTMLInputElement;
    email.replaceWith(replacement);

    expect((await adapter.fill(approved)).status).toBe("rejected");
    expect(replacement.value).toBe("");
  });

  it("refuses to execute without the explicit fixture marker", async () => {
    delete document.documentElement.dataset.runrAssistedApplyFixture;
    const result = await runGreenhouseFixtureProof(
      document,
      "https://boards.greenhouse.io/acme/jobs/1",
      "candidate@example.com",
    );
    expect(result.fixtureAvailable).toBe(false);
    expect(result.execution).toBeNull();
  });
});
