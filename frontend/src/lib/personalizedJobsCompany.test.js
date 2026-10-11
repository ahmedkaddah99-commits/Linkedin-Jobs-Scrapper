import assert from "node:assert/strict";
import test from "node:test";
import { companyProfileField, companyProfileIsUnverified } from "./personalizedJobsApi.js";

test("unverified company state stays visibly unknown until a field is known", () => {
  const unknownProfile = { fields: { industry: { state: "unknown", value: null } } };
  assert.equal(companyProfileIsUnverified(unknownProfile), true);
  assert.deepEqual(companyProfileField(unknownProfile, "industry"), {
    value: "Unknown",
    state: "unknown",
    provenance: {},
    verifiedAt: "",
  });
});

test("a verified company field exits the unverified illustration state", () => {
  const profile = { fields: { industry: { state: "known", value: "Enterprise Software", verified_at: "2026-08-06" } } };
  assert.equal(companyProfileIsUnverified(profile), false);
  assert.deepEqual(companyProfileField(profile, "industry"), {
    value: "Enterprise Software",
    state: "known",
    provenance: {},
    verifiedAt: "2026-08-06",
  });
});

test("unknown employee-like fields do not fabricate company facts", () => {
  const profile = { fields: { employees: { value: 5000 }, leadership: { value: "A named person" } } };
  assert.equal(companyProfileIsUnverified(profile), true);
  assert.equal(companyProfileField(profile, "company_size").value, "Unknown");
  assert.equal(companyProfileField(profile, "leadership_type").value, "Unknown");
});

test("public company provenance is reduced to verified-state metadata", () => {
  const profile = {
    fields: {
      website: {
        state: "known",
        value: "https://acme.example",
        provenance: { source: "official_company_website", url: "https://acme.example/about" },
      },
    },
  };
  const field = companyProfileField(profile, "website");
  assert.equal(field.value, "https://acme.example");
  assert.deepEqual(field.provenance, { source: "official_company_website", url: "https://acme.example/about" });
});
