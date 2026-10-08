import test from "node:test";
import assert from "node:assert/strict";
import { profileMissingFields } from "./profileCompletion.js";

test("empty experience placeholders and whitespace do not complete profile setup", () => {
  const missing = profileMissingFields({ profile: { name: " ", competencies: [""], recent_experience: [{}], education: [{}] } }, { target_roles: [" "], preferred_locations: [] });
  for (const field of ["name", "skills", "dated experience", "education", "target roles", "preferred locations"]) assert.ok(missing.includes(field));
});

test("saved profile facts and account email complete setup without optional links or salary", () => {
  assert.deepEqual(profileMissingFields({ account: { email: "a@example.com" }, profile: {
    name: "Ahmed", role_title: "Analyst", industry: "Technology", location: "Berlin", competencies: ["SQL"], summary: "Business analyst",
    recent_experience: [{ role: "Analyst", company: "Acme", start: "2023-01", summary: "Improved reporting" }], education: [{ school: "University", degree: "BSc" }],
  } }, { target_roles: ["Analyst"], preferred_locations: ["Berlin"] }), []);
});
