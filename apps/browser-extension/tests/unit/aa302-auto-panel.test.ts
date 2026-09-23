import { describe, expect, it } from "vitest";
import { toCandidateProfile } from "../../src/panel/profile-package";

describe("approved profile-package mapping", () => {
  it("maps the approved wire fields without inventing values", () => {
    const profile = toCandidateProfile({
      schema_version: 1,
      candidate: {
        first_name: "Alex",
        last_name: "Candidate",
        full_name: "Alex Candidate",
        email: "alex@example.com",
        phone: "+491234567890",
        source: "confirmed_user_profile",
        approved: true,
        provenance: "user_profile",
      },
      answers: [{
        field_intent: "candidate.website",
        label: "Website",
        proposed_value: "https://alex.example",
        source: "profile_verified",
        sensitivity: "standard",
        scope: "global",
        confidence: 1,
        requires_review: false,
        provenance: "user_profile",
        reasons: ["Confirmed by the candidate in Runr before launch."],
      }],
      experiences: [{
        source_experience_id: "experience-1",
        role_title: "Product Analyst",
        company: "Example Co",
        period: "2022 - Present",
        location: "Berlin",
        bullets: [{
          bullet_id: "experience-1:description",
          text: "Built a reporting workflow.",
          approved_text: "Built a reporting workflow.",
          source_experience_id: "experience-1",
          provenance_id: "user_profile:experience-1",
          approved: true,
        }],
        generation_provenance: { source: "career_memory", profile_id: "" },
        provenance_confidence: "reduced",
      }],
      education: [{ institution: "Example University", degree: "MSc", period: "2020", provenance: "user_profile", confirmed: true }],
      skills: [{ value: "SQL", provenance: "user_profile", confirmed: true }],
      languages: [{ value: "English - C1", provenance: "user_profile", confirmed: true }],
      warnings: [],
    });

    expect(profile).toMatchObject({
      contact: {
        firstName: "Alex",
        lastName: "Candidate",
        website: "https://alex.example",
      },
      skills: ["SQL"],
      workExperiences: [{
        title: "Product Analyst",
        company: "Example Co",
        description: "Built a reporting workflow.",
        startDate: "2022-01",
        isCurrent: true,
      }],
      education: [{ school: "Example University", degree: "MSc", startDate: "2020-01" }],
    });
  });

  it("fails closed for malformed or unapproved payloads", () => {
    expect(toCandidateProfile({ schema_version: 1, candidate: { approved: false } })).toBeNull();
    expect(toCandidateProfile({ schema_version: 1, candidate: {}, answers: [{ field_intent: "candidate.email", value: "invented@example.com" }] })).toBeNull();
  });
});
