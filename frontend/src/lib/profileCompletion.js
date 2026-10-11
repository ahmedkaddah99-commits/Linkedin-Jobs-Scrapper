const filled = (value) => typeof value === "string" && Boolean(value.trim());
const items = (value) => Array.isArray(value) ? value : [];
export function profileMissingFields(settings, preferences = {}) {
  const profile = settings?.profile || {};
  const checks = [
    ["name", filled(profile.name)], ["email", filled(profile.email || settings?.account?.email)],
    ["role title", filled(profile.role_title)], ["industry", filled(profile.industry)],
    ["location", filled(profile.location)], ["skills", items(profile.competencies).some(filled)],
    ["professional summary", filled(profile.summary)],
    ["dated experience", items(profile.recent_experience).some((role) => filled(role.title || role.role) && filled(role.company) && filled(role.start_date || role.start) && filled(role.description || role.summary))],
    ["education", items(profile.education).some((entry) => filled(entry.institution || entry.school) && filled(entry.degree))],
    ["target roles", items(preferences.target_roles).some(filled)],
    ["preferred locations", items(preferences.preferred_locations).some(filled)],
  ];
  return checks.filter(([, complete]) => !complete).map(([label]) => label);
}
