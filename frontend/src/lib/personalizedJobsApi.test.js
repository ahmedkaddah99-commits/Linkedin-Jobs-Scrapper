import assert from "node:assert/strict";
import test from "node:test";
import { buildPersonalizedJobsQuery, toPersonalizedJobView } from "./personalizedJobsApi.js";

test("All Filters selections reach the published jobs API", () => {
  const query = new URLSearchParams(buildPersonalizedJobsQuery({
    role: ["Business Analyst"], skillsInclude: ["SQL"], employmentType: ["full_time"],
    requiredExperienceMin: 3, roleType: "ic", workArrangement: ["remote"],
  }));
  assert.deepEqual(query.getAll("role"), ["Business Analyst"]);
  assert.deepEqual(query.getAll("skills_include"), ["SQL"]);
  assert.deepEqual(query.getAll("employment_type"), ["full_time"]);
  assert.equal(query.get("required_experience_min"), "3");
  assert.equal(query.get("role_type"), "ic");
  assert.deepEqual(query.getAll("work_arrangement"), ["remote"]);
});

test("real Jobs view exposes only approved Apply URL and user-safe fields", () => {
  const view = toPersonalizedJobView({
    canonical_job_id: "job-1",
    title: "Operations Analyst",
    company: "Acme",
    apply_url: "https://jobs.greenhouse.io/acme/jobs/1",
    job_detail_url: "https://boards.example/jobs/1",
    canonical_url: "https://boards.example/jobs/1",
    source_ats: "greenhouse",
    observation_url: "https://boards.example/listing/1",
    provenance_url: "https://internal.example/observation/1",
    company_detail: { profile: { fields: { industry: { value: "Software", state: "known", provenance: { url: "https://internal.example" } } } } },
  });

  assert.equal(view.dataMode, "real");
  assert.equal(view.applyUrl, "https://jobs.greenhouse.io/acme/jobs/1");
  assert.equal(view.applicationEntryUrl, "https://jobs.greenhouse.io/acme/jobs/1");
  assert.equal(view.applicationEntryKind, "direct_apply");
  assert.equal(view.viewJobUrl, "https://boards.example/jobs/1");
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
    user_facing_url: "https://www.linkedin.com/jobs/view/3",
    job_detail_url: "https://www.linkedin.com/jobs/view/3",
  });

  assert.equal(view.applyUrl, "");
  assert.equal(view.directApplyUrl, "");
  assert.equal(view.viewJobUrl, "https://www.linkedin.com/jobs/view/3");
  assert.equal(view.applicationEntryUrl, "https://www.linkedin.com/jobs/view/3");
  assert.equal(view.applicationEntryKind, "job_detail");
});

test("View job prefers the original posting over a different application candidate", () => {
  const view = toPersonalizedJobView({
    canonical_job_id: "job-5",
    source: "linkedin",
    title: "Engineer",
    company: "Gamma",
    job_detail_url: "https://www.linkedin.com/jobs/view/5",
    user_facing_url: "https://jobs.example.com/role-5/application",
  });

  assert.equal(view.applyUrl, "");
  assert.equal(view.viewJobUrl, "https://www.linkedin.com/jobs/view/5");
  assert.equal(view.applicationEntryUrl, "https://www.linkedin.com/jobs/view/5");
});

test("Apply remains unavailable without a direct or valid job-detail URL", () => {
  const view = toPersonalizedJobView({
    canonical_job_id: "job-6",
    title: "Engineer",
    company: "Gamma",
    job_detail_url: "javascript:alert(1)",
  });

  assert.equal(view.applyUrl, "");
  assert.equal(view.viewJobUrl, "");
  assert.equal(view.applicationEntryUrl, "");
  assert.equal(view.applicationEntryKind, "unavailable");
});

test("real Jobs view preserves a server-approved external Apply URL from a LinkedIn-sourced job", () => {
  const view = toPersonalizedJobView({
    canonical_job_id: "job-4",
    source: "linkedin",
    title: "Engineer",
    company: "Gamma",
    apply_url: "https://jobs.ashbyhq.com/gamma/role/application",
  });

  assert.equal(view.applyUrl, "https://jobs.ashbyhq.com/gamma/role/application");
  assert.equal(view.directApplyUrl, "https://jobs.ashbyhq.com/gamma/role/application");
});
