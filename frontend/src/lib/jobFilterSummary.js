import choices from "../../../backend/domain/job_filter_choices.json" with { type: "json" };

const labels = { excludedTitle: "Exclude title", excludedIndustry: "Exclude industry", skillsExclude: "Exclude skill", hiddenCompanies: "Exclude company", requiredExperienceMin: "Minimum years", requiredExperienceMax: "Maximum years", salaryMin: "Minimum annual salary", salaryMax: "Maximum salary", h1bSponsorship: "H1B sponsorship", excludeSecurityClearance: "Exclude clearance", excludeCitizenshipRequired: "Exclude citizenship requirement", excludeStaffingAgency: "Exclude staffing agencies" };
export function jobFilterSummary(filters = {}) {
  return Object.entries(filters).flatMap(([key, value]) => {
    if (["query", "sort", "companyId", "companyLabel"].includes(key) || value === false || value == null || value === "" || value === "all") return [];
    return (Array.isArray(value) ? value : [value]).map((item) => ({ key, value: item, label: labels[key] ? item === true ? labels[key] : `${labels[key]}: ${item}` : choices[key]?.find(([value]) => value === item)?.[1] || String(item) }));
  });
}
