import { beforeEach, describe, expect, it } from "vitest";
import {
  ADAPTER_SUBMISSION_CAPABILITY_FORBIDDEN,
  ATS_ADAPTER_CAPABILITIES,
  GreenhouseAdapter,
  LeverAdapter,
  detectAtsFromUrl,
  runGreenhouseStandardFacts,
  runGreenhouseFixtureProof,
  runLeverFixtureProof,
  runLeverStandardFacts,
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

describe.each([
  ["greenhouse", GreenhouseAdapter, runGreenhouseStandardFacts],
  ["lever", LeverAdapter, runLeverStandardFacts],
] as const)("AA-07 %s native controls", (ats, Adapter, runPackage) => {
  beforeEach(() => {
    document.documentElement.dataset.runrAssistedApplyFixture = ats;
    document.body.innerHTML = `
      <form>
        <label for="headline">Headline</label>
        <input id="headline" name="headline" type="text" required>
        <label for="contact-email">Email</label>
        <input id="contact-email" name="email" type="email" required>
        <label for="contact-phone">Phone</label>
        <input id="contact-phone" name="phone" type="tel">
        <label for="about">About you</label>
        <textarea id="about" name="about" required></textarea>
        <label for="country">Country</label>
        <select id="country" name="country" required>
          <option value="">Choose</option><option value="DE">Germany</option><option value="GB">United Kingdom</option>
        </select>
        <fieldset><legend>Work authorization</legend>
          <label for="work-yes">Yes</label><input id="work-yes" name="work_auth" type="radio" value="yes" required>
          <label for="work-no">No</label><input id="work-no" name="work_auth" type="radio" value="no">
        </fieldset>
        <label for="remote">Open to remote work</label>
        <input id="remote" name="remote" type="checkbox" value="yes">
        <label for="start-date">Start date</label>
        <input id="start-date" name="start_date" type="date" required>
        <label for="rejected">Employee code</label>
        <input id="rejected" name="employee_code" pattern="[A-Z]{3}" required>
        <label for="disabled-native">Disabled answer</label>
        <input id="disabled-native" name="disabled_answer" disabled>
        <div hidden><label for="hidden-native">Hidden answer</label><input id="hidden-native" name="hidden_answer"></div>
        <button type="submit">Submit application</button>
      </form>`;
  });

  it("inspects metadata and fills every V1 native control with native events and readback", async () => {
    const adapter = new Adapter();
    const form = await adapter.inspect({ document, url: `http://127.0.0.1:4174/${ats}-application.html` });
    const country = form.fields.find((field) => field.locator.stableAttributes.id === "country")!;
    const workYes = form.fields.find((field) => field.locator.stableAttributes.id === "work-yes")!;
    const disabled = form.fields.find((field) => field.locator.stableAttributes.id === "disabled-native")!;
    const hidden = form.fields.find((field) => field.locator.stableAttributes.id === "hidden-native")!;

    expect(country).toMatchObject({
      stepId: "primary", label: "Country", normalizedLabel: "country", type: "select",
      required: true, disabled: false, hidden: false, existingValue: "",
      locator: { adapterStrategy: `${ats}-semantic-control`, stableAttributes: { id: "country", name: "country" } },
    });
    expect(country.options).toEqual([
      { label: "Choose", value: "" }, { label: "Germany", value: "DE" },
      { label: "United Kingdom", value: "GB" },
    ]);
    expect(workYes).toMatchObject({
      label: "Work authorization", normalizedLabel: "work authorization", type: "radio",
      required: true, existingValue: false, options: [
        { label: "Yes", value: "yes" }, { label: "No", value: "no" },
      ],
    });
    expect(disabled.disabled).toBe(true);
    expect(hidden.hidden).toBe(true);

    const eventLog: string[] = [];
    for (const id of ["headline", "contact-email", "contact-phone", "about", "country", "work-yes", "remote", "start-date"]) {
      const control = document.getElementById(id)!;
      for (const eventName of ["focus", "input", "change", "blur"]) {
        control.addEventListener(eventName, () => eventLog.push(`${id}:${eventName}`));
      }
    }
    const answers = [
      { fieldIntent: "application.headline", label: "Headline", proposedValue: "Computing pioneer" },
      { fieldIntent: "application.about", label: "About you", proposedValue: "I build reliable systems." },
      { fieldIntent: "application.country", label: "Country", proposedValue: "Germany" },
      { fieldIntent: "application.work_authorization", label: "Work authorization", proposedValue: "Yes" },
      { fieldIntent: "application.remote", label: "Open to remote work", proposedValue: "true" },
      { fieldIntent: "application.start_date", label: "Start date", proposedValue: "2026-08-03" },
      { fieldIntent: "application.employee_code", label: "Employee code", proposedValue: "invalid" },
      { fieldIntent: "application.disabled", label: "Disabled answer", proposedValue: "blocked" },
      { fieldIntent: "application.hidden", label: "Hidden answer", proposedValue: "blocked" },
    ];

    const result = await runPackage(
      document,
      `http://127.0.0.1:4174/${ats}-application.html`,
      `aa07-${ats}`,
      1,
      { email: "ada@example.com", phone: "+49 30 123456" },
      answers,
    );

    expect(result.executions.map((item) => item.status)).toEqual([
      "filled", "filled", "filled", "filled", "filled", "filled", "filled", "filled", "rejected",
    ]);
    expect(document.querySelector<HTMLInputElement>("#headline")!.value).toBe("Computing pioneer");
    expect(document.querySelector<HTMLInputElement>("#contact-email")!.value).toBe("ada@example.com");
    expect(document.querySelector<HTMLInputElement>("#contact-phone")!.value).toBe("+49 30 123456");
    expect(document.querySelector<HTMLTextAreaElement>("#about")!.value).toBe("I build reliable systems.");
    expect(document.querySelector<HTMLSelectElement>("#country")!.value).toBe("DE");
    expect(document.querySelector<HTMLInputElement>("#work-yes")!.checked).toBe(true);
    expect(document.querySelector<HTMLInputElement>("#remote")!.checked).toBe(true);
    expect(document.querySelector<HTMLInputElement>("#start-date")!.value).toBe("2026-08-03");
    expect(document.querySelector<HTMLInputElement>("#disabled-native")!.value).toBe("");
    expect(document.querySelector<HTMLInputElement>("#hidden-native")!.value).toBe("");
    expect(eventLog).toHaveLength(8 * 4);
    for (const id of ["headline", "contact-email", "contact-phone", "about", "country", "work-yes", "remote", "start-date"]) {
      expect(eventLog).toEqual(expect.arrayContaining([
        `${id}:focus`, `${id}:input`, `${id}:change`, `${id}:blur`,
      ]));
    }
  });
});

describe("Lever standard-facts adapter", () => {
  beforeEach(() => {
    document.documentElement.dataset.runrAssistedApplyFixture = "lever";
    document.body.innerHTML = `
      <form class="application-form">
        <label>Full name<input name="name" autocomplete="name" required></label>
        <label>Email<input name="email" type="email" required></label>
        <label>Phone<input name="phone" type="tel" required></label>
        <button type="submit">Submit application</button>
      </form>`;
  });

  it("implements the common contract and fills verified name, email, and phone", async () => {
    const adapter = new LeverAdapter();
    expect(await adapter.detect({ document, url: "http://127.0.0.1:4174/lever-application.html" })).toMatchObject({ detected: true, ats: "lever" });
    const events: string[] = [];
    document.querySelector<HTMLInputElement>('input[name="email"]')!.addEventListener("input", () => events.push("input"));
    let submissions = 0;
    document.querySelector("form")!.addEventListener("submit", (event) => { event.preventDefault(); submissions += 1; });

    const result = await runLeverFixtureProof(document, "http://127.0.0.1:4174/lever-application.html", {
      fullName: "Ada Lovelace",
      email: "ada@example.com",
      phone: "+44 20 7946 0958",
    });

    expect(result.executions.map((execution) => execution.status)).toEqual(["filled", "filled", "filled"]);
    expect(document.querySelector<HTMLInputElement>('input[name="name"]')!.value).toBe("Ada Lovelace");
    expect(document.querySelector<HTMLInputElement>('input[name="email"]')!.value).toBe("ada@example.com");
    expect(document.querySelector<HTMLInputElement>('input[name="phone"]')!.value).toBe("+44 20 7946 0958");
    expect(events).toEqual(["input"]);
    expect(submissions).toBe(0);
    expect(result.inspection.manualReasons).toContain("final_submission");
  });

  it("preserves existing values and reports validation rejection separately from readback", async () => {
    const name = document.querySelector<HTMLInputElement>('input[name="name"]')!;
    name.value = "Existing Person";
    const email = document.querySelector<HTMLInputElement>('input[name="email"]')!;
    email.setCustomValidity("Portal rejected this email");

    const result = await runLeverFixtureProof(document, "http://127.0.0.1:4174/lever-application.html", {
      fullName: "Ada Lovelace",
      email: "ada@example.com",
      phone: "+44 20 7946 0958",
    });

    expect(result.executions[0]).toMatchObject({ status: "preserved_existing", acceptedValue: "Existing Person" });
    expect(result.executions[1]).toMatchObject({ status: "rejected", acceptedValue: "ada@example.com", validationMessage: "Portal rejected this email" });
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

describe("AA-04 Greenhouse package-backed standard facts", () => {
  it("fills and verifies empty name, email, and phone fields while preserving an existing value", async () => {
    document.documentElement.dataset.runrAssistedApplyFixture = "greenhouse";
    document.body.innerHTML = `
      <form>
        <label for="first">Legal first name</label><input id="first" name="first_name" required>
        <label for="last">Legal last name</label><input id="last" name="last_name" value="Portal Restored" required>
        <label for="email-aa04">Email</label><input id="email-aa04" name="email" type="email" required>
        <label for="phone">Phone number</label><input id="phone" name="phone" type="tel" required>
        <button id="submit-aa04" type="submit">Submit application</button>
      </form>`;
    const eventLog: string[] = [];
    for (const id of ["first", "email-aa04", "phone"]) {
      const control = document.getElementById(id)!;
      for (const eventName of ["focus", "input", "change", "blur"]) {
        control.addEventListener(eventName, () => eventLog.push(`${id}:${eventName}`));
      }
    }
    let submissions = 0;
    document.querySelector("form")!.addEventListener("submit", (event) => {
      event.preventDefault();
      submissions += 1;
    });

    const result = await runGreenhouseStandardFacts(
      document,
      "http://127.0.0.1:4174/greenhouse-application.html",
      "aapkg_owned_aa04",
      2,
      { firstName: "Ada", lastName: "Lovelace", email: "ada@example.com", phone: "+49 30 123456" },
    );

    expect(result.executions.map((item) => [item.fieldLabel, item.status])).toEqual([
      ["Legal first name", "filled"],
      ["Legal last name", "preserved_existing"],
      ["Email", "filled"],
      ["Phone number", "filled"],
    ]);
    expect(document.querySelector<HTMLInputElement>("#first")!.value).toBe("Ada");
    expect(document.querySelector<HTMLInputElement>("#last")!.value).toBe("Portal Restored");
    expect(document.querySelector<HTMLInputElement>("#email-aa04")!.value).toBe("ada@example.com");
    expect(document.querySelector<HTMLInputElement>("#phone")!.value).toBe("+49 30 123456");
    expect(eventLog).toEqual([
      "first:focus", "first:input", "first:change", "first:blur",
      "email-aa04:focus", "email-aa04:input", "email-aa04:change", "email-aa04:blur",
      "phone:focus", "phone:input", "phone:change", "phone:blur",
    ]);
    expect(submissions).toBe(0);
  });
});

describe("AA-13 frame, shadow-root, and semantic fallback boundaries", () => {
  it("fills accessible native controls and reports inaccessible/custom boundaries as manual", async () => {
    document.documentElement.dataset.runrAssistedApplyFixture = "greenhouse";
    document.body.innerHTML = `
      <label for="top-answer">Top answer</label><input id="top-answer">
      <iframe id="same-frame" title="Same-origin section"></iframe>
      <iframe id="cross-frame" title="Third-party section"></iframe>
      <div id="open-host"></div>
      <closed-question data-runr-shadow-root="closed" aria-label="Closed question"></closed-question>
      <div role="textbox" aria-label="Custom salary widget"></div>`;

    const sameFrame = document.querySelector<HTMLIFrameElement>("#same-frame")!;
    const frameDocument = sameFrame.contentDocument!;
    frameDocument.body.innerHTML = '<label for="frame-answer">Frame answer</label><input id="frame-answer">';
    const crossFrame = document.querySelector<HTMLIFrameElement>("#cross-frame")!;
    Object.defineProperty(crossFrame, "contentDocument", { configurable: true, value: null });
    const openRoot = document.querySelector<HTMLElement>("#open-host")!.attachShadow({ mode: "open" });
    openRoot.innerHTML = '<label for="shadow-answer">Shadow answer</label><input id="shadow-answer">';

    const adapter = new GreenhouseAdapter();
    const form = await adapter.inspect({ document, url: "http://127.0.0.1:4174/greenhouse-application.html" });
    const frameField = form.fields.find((field) => field.label === "Frame answer")!;
    const shadowField = form.fields.find((field) => field.label === "Shadow answer")!;
    expect(frameField.stepId).toContain("same-origin-frame");
    expect(shadowField.stepId).toContain("open-shadow");
    expect(form.fields.filter((field) => field.classification === "manual").map((field) => field.manualReason))
      .toEqual(expect.arrayContaining(["cross_origin_frame", "closed_shadow_root", "unsupported_custom_control"]));

    const matches = await adapter.match(form, {
      id: "aa13-matrix",
      version: 1,
      candidate: {},
      answers: [
        { fieldIntent: "application.frame", label: "Frame answer", proposedValue: "frame value" },
        { fieldIntent: "application.shadow", label: "Shadow answer", proposedValue: "shadow value" },
      ],
    });
    for (const match of matches.filter((candidate): candidate is ApprovedFieldMatch => candidate.action === "fill")) {
      expect((await adapter.fill(match)).status).toBe("filled");
    }
    expect(frameDocument.querySelector<HTMLInputElement>("#frame-answer")!.value).toBe("frame value");
    expect(openRoot.querySelector<HTMLInputElement>("#shadow-answer")!.value).toBe("shadow value");
    const manualMatches = matches.filter((match) => match.action === "manual_only");
    expect(manualMatches.find((match) => match.fieldLabel === "Third-party section")?.reasons[0])
      .toContain("does not request access");
    expect(manualMatches.find((match) => match.fieldLabel === "Custom salary widget")?.reasons[0])
      .toContain("does not authorize generic filling");
  });
});
