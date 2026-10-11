import { describe, expect, it } from "vitest";
import type { CandidateProfile } from "@runr/ats-core/generic-planner";
import { profileDetails } from "../../src/panel/profile-details";

describe("profile details for manual applications", () => {
  it("includes copyable experience and education without adding missing facts", () => {
    const profile: CandidateProfile = {
      contact: { firstName: "Ada", lastName: "Lovelace", email: "ada@example.com" },
      locations: {}, skills: ["TypeScript"], preferences: {},
      workExperiences: [{ title: "Engineer", company: "Example", startDate: "2023-12", isCurrent: true, description: "Built a platform." }],
      education: [{ school: "Example University", degree: "BSc" }],
    };
    const rows = profileDetails(profile);
    expect(rows).toContainEqual({ section: "Contact", label: "Name", value: "Ada Lovelace" });
    expect(rows).toContainEqual({ section: "Experience 1", label: "Dates", value: "2023-12 – Present" });
    expect(rows).toContainEqual({ section: "Experience 1", label: "Description", value: "Built a platform." });
    expect(rows).toContainEqual({ section: "Education 1", label: "School", value: "Example University" });
    expect(rows.some((row) => row.label === "Phone" || row.label === "Country")).toBe(false);
  });
});
