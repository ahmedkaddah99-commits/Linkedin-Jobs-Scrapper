import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  DEFAULT_FILL_POLICY,
  classifyApplicationPage,
  controlResolver,
  detectApplicationProvider,
  executeNativeValueAction,
  inspectApplicationForm,
  planApplicationFill,
  resolveUploadTarget,
  type CandidateProfile,
  type NativeValueAction,
} from "@runr/ats-core";

const fixturesDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../fixtures");

function loadFixture(name: string): Document {
  const html = readFileSync(path.join(fixturesDir, name), "utf8");
  const parsed = new DOMParser().parseFromString(html, "text/html");
  document.documentElement.replaceWith(document.importNode(parsed.documentElement, true));
  return document;
}

function testProfile(): CandidateProfile {
  return {
    contact: {
      firstName: "Alex", lastName: "Fixture", fullName: "Alex Fixture",
      email: "alex.fixture@example.com", phone: "+49 30 000000",
      website: "https://example.com/alex", linkedin: "https://example.com/in/alex",
    },
    locations: { city: "Erlangen", residenceCountry: "Germany", postalCode: "91052" },
    skills: ["Python"],
    workExperiences: [{ title: "Platform Engineer", company: "Example Systems" }],
    education: [{ school: "Example University", degree: "BSc" }],
    preferences: { currentTitle: "Platform Engineer", workAuthorization: "Yes" },
  };
}

/**
 * Every provider is asserted the same way, and support means the same thing for
 * each: the page is classified as an application form, its fields are inspected
 * with correct intents, a CV control is resolvable, a plan is produced, and the
 * planned values verifiably land in the DOM. URL detection alone never counts.
 */
const PROVIDERS: ReadonlyArray<{
  provider: string;
  fixture: string;
  url: string;
  /** Control ids expected to hold values after execution. */
  expected: Record<string, string>;
}> = [
  {
    provider: "workday",
    fixture: "workday.html",
    url: "https://acme.wd1.myworkdayjobs.com/en-US/careers/job/Berlin/Engineer_R-123/apply",
    expected: { legalNameSection_firstName: "Alex", legalNameSection_lastName: "Fixture", email: "alex.fixture@example.com" },
  },
  {
    provider: "icims",
    fixture: "icims.html",
    url: "https://careers-acme.icims.com/jobs/1234/login",
    expected: { firstname: "Alex", lastname: "Fixture", email: "alex.fixture@example.com" },
  },
  {
    provider: "taleo",
    fixture: "taleo.html",
    url: "https://acme.taleo.net/careersection/x/jobapply.ftl",
    expected: { firstName: "Alex", lastName: "Fixture", emailAddress: "alex.fixture@example.com" },
  },
  {
    provider: "smartrecruiters",
    fixture: "smartrecruiters.html",
    url: "https://jobs.smartrecruiters.com/Acme/74400",
    expected: { firstName: "Alex", lastName: "Fixture", email: "alex.fixture@example.com" },
  },
  {
    provider: "ashby",
    fixture: "ashby.html",
    url: "https://jobs.ashbyhq.com/acme/1a2b/application",
    expected: { _systemfield_name: "Alex Fixture", _systemfield_email: "alex.fixture@example.com" },
  },
  {
    provider: "bamboohr",
    fixture: "bamboohr.html",
    url: "https://acme.bamboohr.com/careers/42",
    expected: { firstName: "Alex", lastName: "Fixture", email: "alex.fixture@example.com" },
  },
  {
    provider: "jobvite",
    fixture: "jobvite.html",
    url: "https://jobs.jobvite.com/acme/job/oX0/apply",
    expected: { firstName: "Alex", lastName: "Fixture", email: "alex.fixture@example.com" },
  },
  {
    provider: "recruitee",
    fixture: "recruitee.html",
    url: "https://acme.recruitee.com/o/engineer/c/new",
    expected: { candidate_name: "Alex Fixture", candidate_email: "alex.fixture@example.com" },
  },
];

describe.each(PROVIDERS)("AA-309 $provider", ({ provider, fixture, url, expected }) => {
  it("identifies the provider", () => {
    loadFixture(fixture);
    expect(detectApplicationProvider(url, document).provider).toBe(provider);
  });

  it("classifies the page as an application form", () => {
    const detection = classifyApplicationPage({ document: loadFixture(fixture), url });
    expect(detection.kind).toBe("application_form");
    expect(detection.fillableFieldCount).toBeGreaterThanOrEqual(5);
  });

  it("inspects contact fields with the right intents", () => {
    const inspection = inspectApplicationForm({ document: loadFixture(fixture), url });
    const intents = inspection.fields.map((field) => field.intent);
    expect(intents).toContain("contact.email");
    expect(intents.some((intent) => intent === "contact.first_name" || intent === "contact.full_name")).toBe(true);
    expect(intents).toContain("legal.work_authorization");
  });

  it("resolves a CV upload target", () => {
    const inspection = inspectApplicationForm({ document: loadFixture(fixture), url });
    const target = resolveUploadTarget(inspection, "cv");
    expect(target).not.toBeNull();
    expect(target).not.toHaveProperty("ambiguous");
  });

  it("never plans an action against the terminal control", () => {
    const doc = loadFixture(fixture);
    const inspection = inspectApplicationForm({ document: doc, url });
    const plan = planApplicationFill(inspection, testProfile(), DEFAULT_FILL_POLICY);
    expect(plan.actions.some((action) => "fieldId" in action && action.fieldId.includes("send"))).toBe(false);
  });

  it("fills and verifies the planned values in the DOM", () => {
    const doc = loadFixture(fixture);
    const inspection = inspectApplicationForm({ document: doc, url });
    const plan = planApplicationFill(inspection, testProfile(), DEFAULT_FILL_POLICY);

    const resolve = controlResolver(doc, inspection);
    const native = plan.actions.filter((action): action is NativeValueAction =>
      ["fill_text", "select", "set_date", "set_checkbox", "set_radio"].includes(action.type));
    expect(native.length).toBeGreaterThan(0);
    for (const action of native) executeNativeValueAction(doc, action, resolve);

    for (const [id, value] of Object.entries(expected)) {
      expect((doc.getElementById(id) as HTMLInputElement).value).toBe(value);
    }
  });
});

describe("AA-309 provider support is never claimed from a URL alone", () => {
  it("recognises a Workday host but refuses to call a posting page an application", () => {
    document.documentElement.replaceWith(document.createElement("html"));
    document.documentElement.innerHTML =
      "<head></head><body><h1>Engineer</h1><p>Apply on the next page.</p>" +
      "<label for='q'>Search</label><input id='q'></body>";
    const url = "https://acme.wd1.myworkdayjobs.com/en-US/careers";
    expect(detectApplicationProvider(url, document).provider).toBe("workday");
    expect(classifyApplicationPage({ document, url }).kind).not.toBe("application_form");
  });
});
