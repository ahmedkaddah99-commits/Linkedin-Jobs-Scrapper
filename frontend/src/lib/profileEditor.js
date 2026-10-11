export const profileSections = ["personal", "education", "experience", "skills", "employment", "preferences"];
export const profileSectionLabels = { personal: "Personal", education: "Education", experience: "Work experience", skills: "Skills", employment: "Equal employment", preferences: "Preferences" };
export const list = value => Array.isArray(value) ? value : [];

export function readyResume(settings) {
  return list(settings?.candidate_assets).filter(asset => asset.asset_kind === "workspace_cv" && asset.metadata?.parsed_profile && (asset.metadata?.cv_processing?.status || asset.metadata?.status) === "ready")
    .sort((a, b) => String(b.metadata?.processed_at || b.updated_at || b.created_at || "").localeCompare(String(a.metadata?.processed_at || a.updated_at || a.created_at || "")))[0];
}

// Read persisted extraction only. Never download or parse a document on page load.
export function profileWithResumeDefaults(settings) {
  const profile = { ...(settings?.profile || {}) };
  const parsed = readyResume(settings)?.metadata?.parsed_profile || {};
  for (const [key, value] of Object.entries(parsed)) {
    if (!(key in profile) || ((profile[key] === "" || (Array.isArray(profile[key]) && !profile[key].length)) && !list(settings?.profile_edited_fields).includes(key))) profile[key] = value;
  }
  return profile;
}

export function educationRecord(entry) {
  return { ...entry, degree_title: entry.degree_title || entry.degree || "", institution: entry.institution || entry.school || "", field: entry.field || entry.field_of_study || "", start_date: entry.start_date || "", end_date: entry.end_date || "", period: entry.period || entry.graduation_year || "" };
}

export const employmentQuestions = [
  ["us_work_authorized", "Are you authorized to work in the US?", ["Yes", "No", "Decline to state"]],
  ["requires_sponsorship", "Will you now or in the future require sponsorship for employment visa status?", ["Yes", "No", "Decline to state"]],
  ["disability", "Do you have a disability?", ["Yes", "No", "Decline to state"]],
  ["veteran", "Are you a veteran?", ["Yes", "No", "Decline to state"]],
  ["gender", "What is your gender?", ["Male", "Female", "Non-binary", "Decline to state"]],
  ["lgbtq", "Do you identify as LGBTQ+?", ["Yes", "No", "Decline to state"]],
];
