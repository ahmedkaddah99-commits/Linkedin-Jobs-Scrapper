import assert from "node:assert/strict";
import test from "node:test";
import { toPersonalizedJobView } from "./personalizedJobsApi.js";

test("real Jobs view exposes only approved Apply URL and user-safe fields", () => {
  const view = toPersonalizedJobView({
    canonical_job_id: "job-1",
    title: "Operations Analyst",
    company: "Acme",
    apply_url: "https://jobs.greenhouse.io/acme/jobs/1",
    canonical_url: "https://boards.example/jobs/1",
    source_ats: "greenhouse",
    observation_url: "https://boards.example/listing/1",
    provenance_url: "https://internal.example/observation/1",
    company_detail: { profile: { fields: { industry: { value: "Software", state: "known", provenance: { url: "https://internal.example" } } } } },
  });

  assert.equal(view.dataMode, "real");
  assert.equal(view.applyUrl, "https://jobs.greenhouse.io/acme/jobs/1");
  assert.equal(view.canonicalUrl, undefined);
  assert.equal(view.source, "greenhouse");
  assert.equal(view.observation_url, undefined);
  assert.equal(view.companyDetail.provenance_url, undefined);
  assert.equal(view.companyProfile.fields.industry.provenance, undefined);
});

test("real Jobs view carries source-backed identity and verified company visual fields", () => {
  const view = toPersonalizedJobView({
    canonical_job_id: "job-2",
    source: "employer_site",
    source_job_id: "greenhouse-2",
    title: "Platform Engineer",
    company: "Beta",
    location: "Berlin",
    description: "Build and operate reliable platform services.",
    apply_url: "https://jobs.greenhouse.io/beta/jobs/2",
    company_detail: {
      profile: {
        logo_url: "https://cdn.example/beta.png",
        monogram: "BE",
      },
    },
  });

  assert.equal(view.source, "employer_site");
  assert.equal(view.sourceJobId, "greenhouse-2");
  assert.equal(view.applyUrl, "https://jobs.greenhouse.io/beta/jobs/2");
  assert.equal(view.directApplyUrl, "https://jobs.greenhouse.io/beta/jobs/2");
  assert.equal(view.companyLogoUrl, "https://cdn.example/beta.png");
  assert.equal(view.companyMonogram, "BE");
});

test("real Jobs view never exposes a LinkedIn job-detail Apply URL", () => {
  const view = toPersonalizedJobView({
    canonical_job_id: "job-3",
    source: "linkedin",
    easy_apply_status: "false",
    title: "Analyst",
    company: "Gamma",
    apply_url: "https://jobs.linkedin.com/jobs/view/3",
  });

  assert.equal(view.applyUrl, "");
  assert.equal(view.directApplyUrl, "");
});
