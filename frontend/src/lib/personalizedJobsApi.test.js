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
  assert.equal(view.source, undefined);
  assert.equal(view.observation_url, undefined);
  assert.equal(view.companyDetail.provenance_url, undefined);
  assert.equal(view.companyProfile.fields.industry.provenance, undefined);
});
