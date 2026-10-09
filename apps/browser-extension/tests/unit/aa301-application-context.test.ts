import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  APPLICATION_CONTEXT_ALGORITHM_VERSION,
  classifyApplicationPage,
  detectApplicationProvider,
  extractApplicationJobContext,
  extractKeywords,
  jobIdFromUrl,
  normalizeJobTitle,
} from "@runr/ats-core";

const fixturesDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../fixtures");

/**
 * Loads a fixture into the live jsdom document so `getComputedStyle` ??? and
 * therefore the visibility rules the classifier depends on ??? behaves the same
 * way it does in a real page.
 */
function loadFixture(name: string): Document {
  const html = readFileSync(path.join(fixturesDir, name), "utf8");
  const parsed = new DOMParser().parseFromString(html, "text/html");
  document.documentElement.replaceWith(document.importNode(parsed.documentElement, true));
  return document;
}

const AVATURE_JOB_DETAIL_URL = "https://jobs.northwind-industries.com/en_US/externaljobs/JobDetail/618402";
const AVATURE_GATEWAY_URL = "https://jobs.northwind-industries.com/en_US/externaljobs/ApplicationMethods?folderId=618402";
const AVATURE_REGISTER_URL = "https://jobs.northwind-industries.com/en_US/externaljobs/Register?folderId=618402";

describe("AA-301 provider identity", () => {
  it("identifies employer-hosted Avature portals from the route shape", () => {
    // The observed Siemens URLs are a public example of the employer-hosted
    // Avature route shape. No employer is special-cased.
    const identity = detectApplicationProvider("https://jobs.siemens.com/en_US/externaljobs/JobDetail/514376");
    expect(identity.provider).toBe("avature");
    expect(identity.employerSlug).toBe("siemens");
    expect(identity.marker).toBe("avature:siemens/514376");
  });

  it("identifies the same portal on an unrelated employer", () => {
    const identity = detectApplicationProvider(AVATURE_REGISTER_URL);
    expect(identity.provider).toBe("avature");
    expect(identity.employerSlug).toBe("northwind-industries");
    expect(identity.marker).toBe("avature:northwind-industries/618402");
  });

  it("identifies shared provider hosts", () => {
    expect(detectApplicationProvider("https://boards.greenhouse.io/acme/jobs/4012345").provider).toBe("greenhouse");
    expect(detectApplicationProvider("https://jobs.lever.co/acme/1a2b3c").provider).toBe("lever");
    expect(detectApplicationProvider("https://acme.wd1.myworkdayjobs.com/en-US/careers").provider).toBe("workday");
    expect(detectApplicationProvider("https://careers-acme.icims.com/jobs/1234/login").provider).toBe("icims");
    expect(detectApplicationProvider("https://acme.taleo.net/careersection/x/jobdetail.ftl").provider).toBe("taleo");
    expect(detectApplicationProvider("https://jobs.smartrecruiters.com/Acme/74400").provider).toBe("smartrecruiters");
    expect(detectApplicationProvider("https://jobs.ashbyhq.com/acme/1a2b").provider).toBe("ashby");
    expect(detectApplicationProvider("https://acme.bamboohr.com/careers/42").provider).toBe("bamboohr");
    expect(detectApplicationProvider("https://jobs.jobvite.com/acme/job/oX0").provider).toBe("jobvite");
    expect(detectApplicationProvider("https://acme.recruitee.com/o/engineer").provider).toBe("recruitee");
    expect(detectApplicationProvider("https://acme.avature.net/careers/JobDetail/9").provider).toBe("avature");
  });

  it("reports no provider for unrelated pages and non-HTTPS URLs", () => {
    expect(detectApplicationProvider("https://news.example.com/article/1").provider).toBe("unknown");
    expect(detectApplicationProvider("http://jobs.example.com/en_US/externaljobs/Register").provider).toBe("unknown");
  });

  it("reads job identifiers from every observed route shape", () => {
    expect(jobIdFromUrl(AVATURE_REGISTER_URL)).toBe("618402");
    expect(jobIdFromUrl(AVATURE_JOB_DETAIL_URL)).toBe("618402");
    expect(jobIdFromUrl("https://boards.greenhouse.io/acme/jobs/4012345")).toBe("4012345");
    expect(jobIdFromUrl("https://news.example.com/article")).toBeUndefined();
  });
});

describe("AA-301 page classification", () => {
  it("classifies an ordinary posting page as job detail, never an application", () => {
    const detection = classifyApplicationPage({
      document: loadFixture("avature-job-detail.html"),
      url: AVATURE_JOB_DETAIL_URL,
    });

    expect(detection.kind).toBe("job_detail");
    expect(detection.provider).toBe("avature");
    // The posting page carries a site-search box and a locale select on an
    // application-shaped route. Neither may raise the panel.
    expect(detection.fillableFieldCount).toBe(2);
    expect(detection.hasDocumentUpload).toBe(false);
    expect(detection.algorithmVersion).toBe(APPLICATION_CONTEXT_ALGORITHM_VERSION);
  });

  it("classifies the sign-in step as a gateway rather than an application", () => {
    const detection = classifyApplicationPage({
      document: loadFixture("avature-application-gateway.html"),
      url: AVATURE_GATEWAY_URL,
    });

    expect(detection.kind).toBe("application_gateway");
    expect(detection.provider).toBe("avature");
    // The password control is never counted as fillable.
    expect(detection.fillableFieldCount).toBe(1);
  });

  it("classifies the profile step as an application form with documents and repeaters", () => {
    const detection = classifyApplicationPage({
      document: loadFixture("avature-register-form.html"),
      url: AVATURE_REGISTER_URL,
    });

    expect(detection.kind).toBe("application_form");
    expect(detection.provider).toBe("avature");
    expect(detection.hasDocumentUpload).toBe(true);
    expect(detection.hasRepeatedSections).toBe(true);
    expect(detection.fillableFieldCount).toBeGreaterThanOrEqual(30);
    expect(detection.confidence).toBeGreaterThan(0.9);
  });

  it("classifies the existing Greenhouse and Lever fixtures through the generic detector", () => {
    const greenhouse = classifyApplicationPage({
      document: loadFixture("greenhouse-application.html"),
      url: "https://boards.greenhouse.io/acme/jobs/4012345",
    });
    expect(greenhouse.kind).toBe("application_form");
    expect(greenhouse.provider).toBe("greenhouse");
    expect(greenhouse.hasDocumentUpload).toBe(true);

    const lever = classifyApplicationPage({
      document: loadFixture("lever-application.html"),
      url: "https://jobs.lever.co/acme/1a2b3c/apply",
    });
    expect(lever.kind).toBe("application_form");
    expect(lever.provider).toBe("lever");
    expect(lever.hasDocumentUpload).toBe(true);
  });

  it("reports an unrelated page as unsupported", () => {
    document.documentElement.replaceWith(document.createElement("html"));
    document.documentElement.innerHTML = "<head></head><body><h1>Latest news</h1><p>No application here.</p></body>";
    const detection = classifyApplicationPage({ document, url: "https://news.example.com/article/1" });
    expect(detection.kind).toBe("unsupported");
    expect(detection.confidence).toBe(0);
  });
});

describe("AA-301 job context extraction", () => {
  it("extracts employer, job, and posting metadata from a posting page", () => {
    const pageContext = {
      document: loadFixture("avature-job-detail.html"),
      url: AVATURE_JOB_DETAIL_URL,
    };
    const detection = classifyApplicationPage(pageContext);
    const job = extractApplicationJobContext(pageContext, detection, "2026-08-15T09:00:00.000Z");

    expect(job).not.toBeNull();
    expect(job!.provider).toBe("avature");
    expect(job!.employer).toBe("Northwind Industries AG");
    expect(job!.title).toBe("Automation Platform Engineer");
    expect(job!.jobId).toBe("618402");
    expect(job!.postedAt).toBe("14-Aug-2026");
    expect(job!.employmentType).toBe("Permanent");
    expect(job!.workMode).toBe("Office/Site only");
    expect(job!.location).toBe("Erlangen, Bavaria, Germany");
    expect(job!.keywords).toEqual(expect.arrayContaining(["kubernetes", "python"]));
    expect(job!.detectedAt).toBe("2026-08-15T09:00:00.000Z");
  });

  it("carries employer and job identity onto the application step", () => {
    const pageContext = {
      document: loadFixture("avature-register-form.html"),
      url: AVATURE_REGISTER_URL,
    };
    const detection = classifyApplicationPage(pageContext);
    const job = extractApplicationJobContext(pageContext, detection, "2026-08-15T09:01:00.000Z");

    expect(job!.employer).toBe("Northwind Industries");
    expect(job!.title).toBe("Automation Platform Engineer");
    expect(job!.jobId).toBe("618402");
    expect(job!.applicationUrl).toBe(AVATURE_REGISTER_URL);
  });

  it("returns no job context for an unsupported page", () => {
    document.documentElement.replaceWith(document.createElement("html"));
    document.documentElement.innerHTML = "<head></head><body><p>Nothing here.</p></body>";
    const pageContext = { document, url: "https://news.example.com/article/1" };
    const detection = classifyApplicationPage(pageContext);
    expect(extractApplicationJobContext(pageContext, detection, "2026-08-15T09:02:00.000Z")).toBeNull();
  });
});

describe("AA-301 normalization", () => {
  it("strips gender-notation suffixes from job titles", () => {
    expect(normalizeJobTitle("Automation Platform Engineer (m/w/d)")).toBe("Automation Platform Engineer");
    expect(normalizeJobTitle("Quality Planner (w/m/d)")).toBe("Quality Planner");
    expect(normalizeJobTitle("Data Scientist (f/m/x)")).toBe("Data Scientist");
    expect(normalizeJobTitle("Product Manager (all genders)")).toBe("Product Manager");
    expect(normalizeJobTitle("Senior Engineer")).toBe("Senior Engineer");
  });

  it("drops stop words and short tokens from keyword extraction", () => {
    const keywords = extractKeywords("You will work with Kubernetes and Python for the team.");
    expect(keywords).toEqual(expect.arrayContaining(["kubernetes", "python"]));
    expect(keywords).not.toContain("the");
    expect(keywords).not.toContain("work");
  });
});
