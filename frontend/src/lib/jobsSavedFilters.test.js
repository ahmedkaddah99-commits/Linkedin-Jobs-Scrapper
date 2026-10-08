import assert from "node:assert/strict";
import test from "node:test";
import { buildPersonalizedJobsQuery, filtersFromSavedSearch, toPersonalizedJobsFilterPayload } from "./personalizedJobsApi.js";

test("saved company selection restores its stable ID, label and sort", () => {
  const filters = filtersFromSavedSearch({ filters: { company_id: "company-a", company_label: "Acme Labs", sort: "least_competitive" } });
  assert.equal(filters.companyId, "company-a");
  assert.equal(filters.companyLabel, "Acme Labs");
  assert.equal(filters.sort, "least_competitive");
  const query = new URLSearchParams(buildPersonalizedJobsQuery(filters));
  assert.equal(query.get("company_id"), "company-a");
  assert.equal(query.has("role"), false);
  const saved = toPersonalizedJobsFilterPayload(filters);
  assert.equal(saved.company_id, "company-a");
  assert.equal(saved.company_label, "Acme Labs");
  assert.equal(saved.sort, "least_competitive");
});
