import type { CandidateProfile } from "@runr/ats-core/generic-planner";

export interface ProfileDetail { label: string; value: string; section: string }

/** The same profile that powers autofill, formatted for individual copy actions. */
export function profileDetails(profile: CandidateProfile): ProfileDetail[] {
  const rows: ProfileDetail[] = [];
  const add = (section: string, label: string, value: string | undefined) => {
    if (value?.trim()) rows.push({ section, label, value: value.trim() });
  };
  const { contact, locations, preferences } = profile;
  add("Contact", "Name", contact.fullName || [contact.firstName, contact.lastName].filter(Boolean).join(" "));
  for (const [label, value] of Object.entries({ Email: contact.email, Phone: contact.phone, LinkedIn: contact.linkedin, Website: contact.website, GitHub: contact.github, Portfolio: contact.portfolio })) add("Contact", label, value);
  for (const [label, value] of Object.entries({ Address: locations.address, City: locations.city, State: locations.state, "Postal code": locations.postalCode, Country: locations.residenceCountry })) add("Location", label, value);
  add("About", "Current role", preferences.currentTitle);
  add("About", "Current company", preferences.currentCompany);
  add("About", "Summary", preferences.summary);
  add("About", "Skills", profile.skills.join(", "));
  profile.workExperiences.forEach((entry, index) => {
    const section = `Experience ${index + 1}`;
    add(section, "Role", entry.title);
    add(section, "Company", entry.company);
    add(section, "Dates", [entry.startDate, entry.isCurrent ? "Present" : entry.endDate].filter(Boolean).join(" – "));
    add(section, "Description", entry.description);
  });
  profile.education.forEach((entry, index) => {
    const section = `Education ${index + 1}`;
    add(section, "School", entry.school);
    add(section, "Degree", entry.degree);
    add(section, "Dates", [entry.startDate, entry.isCurrent ? "Present" : entry.endDate].filter(Boolean).join(" – "));
  });
  return rows;
}
