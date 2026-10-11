import test from "node:test";
import assert from "node:assert/strict";
import { connectionDetails, filterConnections } from "./connectionDetails.js";

test("separates a known imported headline from a concatenated name", () => {
  const details = connectionDetails({ name: "Jane DoeEngineering Manager", metadata: { import_source_row: { position: "Engineering Manager" } } });
  assert.equal(details.name, "Jane Doe");
  assert.equal(details.jobTitle, "Engineering Manager");
});

test("combines independent name, company and job title filters", () => {
  const contacts = [{ name: "Jane Doe", companies: [{ company_name: "Acme", role_title: "Engineer" }] }, { name: "John Doe", companies: [{ company_name: "Acme", role_title: "Designer" }] }];
  assert.deepEqual(filterConnections(contacts, { name: "doe", company: "ACME", jobTitle: "engineer" }), [contacts[0]]);
});

test("notes and strength are independent and ambiguous names stay intact", () => {
  const details = connectionDetails({ name: "Jane Doe", relationship_note: "Met at a conference", source_kind: "manual", metadata: { connection_strength: "Strong" } });
  assert.equal(details.name, "Jane Doe");
  assert.equal(details.notes, "Met at a conference");
  assert.equal(details.strength, "Strong");
});

test("repairs legacy joined names only when the profile URL corroborates the boundary", () => {
  const details = connectionDetails({ name: "Hediye HakkakMaster’s student in Robotics", source_kind: "linkedin_extension", linkedin_url: "https://linkedin.com/in/hediye-hakkak/", metadata: { import_source_row: { position: "Hediye HakkakMaster’s student in RoboticsConnected on August 2, 2026Message" } } });
  assert.equal(details.name, "Hediye Hakkak");
  assert.equal(details.jobTitle, "Master’s student in Robotics");
});
