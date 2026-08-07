export const INITIAL_PERSONALIZED_JOB_FILTERS = {
  query: "",
  location: "",
  workArrangement: "all",
  employmentType: "all",
  experienceLevel: "all",
  category: "",
  datePosted: "all",
  salaryMin: "",
  salaryMax: "",
  language: "",
  workAuthorization: "",
  sponsorship: "",
  company: "",
  industry: "",
  companySize: "",
  companyStage: "",
  fundingStage: "",
  fundingMin: "",
  fundingMax: "",
  foundedYearMin: "",
  foundedYearMax: "",
  fundingYearMin: "",
  fundingYearMax: "",
  hiddenCompanies: "",
  education: "",
  preferredMajor: "",
  securityClearance: "",
  liftingRequirement: "",
  sort: "newest",
};

const DATE_POSTED_DAYS = { "24h": "1", "7d": "7", "30d": "30" };

function text(value) {
  return String(value ?? "").trim();
}

const INTERNAL_JOB_KEYS = new Set([
  "source",
  "source_ats",
  "source_observation_id",
  "observation_url",
  "original_url",
  "provenance_url",
  "provenance",
  "internal_provenance",
  "source_identifier",
  "canonical_url",
  "description_version",
  "version_id",
  "content_hash",
  "observed_at",
]);

function stripInternalJobFields(value) {
  if (Array.isArray(value)) return value.map(stripInternalJobFields);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => !INTERNAL_JOB_KEYS.has(String(key).toLowerCase()))
      .map(([key, item]) => [key, stripInternalJobFields(item)]),
  );
}

function firstValue(value) {
  if (Array.isArray(value)) return text(value[0]);
  return text(value);
}

function unknown(value, fallback = "Unknown") {
  return text(value) || fallback;
}

function normalizeArrangement(value) {
  const normalized = text(value).toLowerCase().replace(/[\s-]+/g, "_");
  if (["remote", "hybrid", "onsite", "on_site", "in_person"].includes(normalized)) {
    return normalized === "on_site" || normalized === "in_person" ? "onsite" : normalized;
  }
  return normalized || "unknown";
}

export function buildPersonalizedJobsQuery(filters = {}, { cursor = "", includeHidden = false, limit = 25, omitSort = false, view = "cards" } = {}) {
  const params = new URLSearchParams();
  const values = {
    q: filters.query,
    location: filters.location,
    work_arrangement: filters.workArrangement !== "all" ? filters.workArrangement : "",
    employment_type: filters.employmentType !== "all" ? filters.employmentType : "",
    experience_level: filters.experienceLevel !== "all" ? filters.experienceLevel : "",
    category: filters.category,
    salary_min: filters.salaryMin,
    salary_max: filters.salaryMax,
    language: filters.language,
    work_authorization: filters.workAuthorization,
    sponsorship: filters.sponsorship,
    posted_within_days: DATE_POSTED_DAYS[filters.datePosted] || "",
    company: filters.company,
    industry: filters.industry,
    company_size: filters.companySize,
    company_stage: filters.companyStage,
    funding_stage: filters.fundingStage,
    funding_min: filters.fundingMin,
    funding_max: filters.fundingMax,
    founded_year_min: filters.foundedYearMin,
    founded_year_max: filters.foundedYearMax,
    funding_year_min: filters.fundingYearMin,
    funding_year_max: filters.fundingYearMax,
    hidden_companies: filters.hiddenCompanies,
    education: filters.education,
    preferred_major: filters.preferredMajor,
    security_clearance: filters.securityClearance,
    lifting_requirement: filters.liftingRequirement,
    sort: filters.sort === "best" ? "priority" : filters.sort,
  };
  Object.entries(values).forEach(([key, value]) => {
    if (key === "sort" && omitSort) return;
    if (text(value)) params.set(key, text(value));
  });
  if (cursor) params.set("cursor", cursor);
  params.set("limit", String(Math.max(1, Math.min(100, Number(limit) || 25))));
  if (view) params.set("view", text(view));
  if (includeHidden) params.set("include_hidden", "true");
  return params.toString();
}

export function countPersonalizedJobFilters(filters = {}) {
  return [
    ["location", filters.location],
    ["workArrangement", filters.workArrangement !== "all" ? filters.workArrangement : ""],
    ["employmentType", filters.employmentType !== "all" ? filters.employmentType : ""],
    ["experienceLevel", filters.experienceLevel !== "all" ? filters.experienceLevel : ""],
    ["category", filters.category],
    ["datePosted", filters.datePosted !== "all" ? filters.datePosted : ""],
    ["salaryMin", filters.salaryMin],
    ["salaryMax", filters.salaryMax],
    ["language", filters.language],
    ["workAuthorization", filters.workAuthorization],
    ["sponsorship", filters.sponsorship],
    ["company", filters.company],
    ["industry", filters.industry],
    ["companySize", filters.companySize],
    ["companyStage", filters.companyStage],
    ["fundingStage", filters.fundingStage],
    ["fundingMin", filters.fundingMin],
    ["fundingMax", filters.fundingMax],
    ["foundedYearMin", filters.foundedYearMin],
    ["foundedYearMax", filters.foundedYearMax],
    ["fundingYearMin", filters.fundingYearMin],
    ["fundingYearMax", filters.fundingYearMax],
    ["hiddenCompanies", filters.hiddenCompanies],
    ["education", filters.education],
    ["preferredMajor", filters.preferredMajor],
    ["securityClearance", filters.securityClearance],
    ["liftingRequirement", filters.liftingRequirement],
  ].filter(([, value]) => text(value)).length;
}

export function toPersonalizedJobsFilterPayload(filters = {}) {
  const query = {};
  const values = {
    q: filters.query,
    location: filters.location,
    work_arrangement: filters.workArrangement !== "all" ? filters.workArrangement : "",
    employment_type: filters.employmentType !== "all" ? filters.employmentType : "",
    experience_level: filters.experienceLevel !== "all" ? filters.experienceLevel : "",
    category: filters.category,
    salary_min: filters.salaryMin,
    salary_max: filters.salaryMax,
    language: filters.language,
    work_authorization: filters.workAuthorization,
    sponsorship: filters.sponsorship,
    posted_within_days: DATE_POSTED_DAYS[filters.datePosted] || "",
    company: filters.company,
    industry: filters.industry,
    company_size: filters.companySize,
    company_stage: filters.companyStage,
    funding_stage: filters.fundingStage,
    funding_min: filters.fundingMin,
    funding_max: filters.fundingMax,
    founded_year_min: filters.foundedYearMin,
    founded_year_max: filters.foundedYearMax,
    funding_year_min: filters.fundingYearMin,
    funding_year_max: filters.fundingYearMax,
    hidden_companies: filters.hiddenCompanies,
    education: filters.education,
    preferred_major: filters.preferredMajor,
    security_clearance: filters.securityClearance,
    lifting_requirement: filters.liftingRequirement,
  };
  Object.entries(values).forEach(([key, value]) => {
    if (text(value)) query[key] = text(value);
  });
  return query;
}

export function formatJobDate(value, now = Date.now()) {
  const raw = text(value);
  if (!raw) return "Unknown date";
  const timestamp = Date.parse(raw);
  if (!Number.isFinite(timestamp)) return raw;
  const age = Math.max(0, now - timestamp);
  const minutes = Math.floor(age / 60000);
  if (minutes < 60) return `${Math.max(1, minutes)}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" }).format(timestamp);
}

function currencySymbol(currency) {
  const normalized = text(currency).toUpperCase();
  return { EUR: "€", USD: "$", GBP: "£", CHF: "CHF " }[normalized] || (normalized ? `${normalized} ` : "");
}

export function formatSalary(value) {
  if (!value) return "Unknown";
  if (typeof value === "string") return text(value) || "Unknown";
  if (typeof value !== "object") return "Unknown";
  const minimum = Number(value.min ?? value.minimum ?? value.lower);
  const maximum = Number(value.max ?? value.maximum ?? value.upper);
  const currency = currencySymbol(value.currency || value.currency_code);
  const formatAmount = (amount) => Number.isFinite(amount) ? `${currency}${Math.round(amount).toLocaleString()}` : "";
  if (Number.isFinite(minimum) && Number.isFinite(maximum)) return `${formatAmount(minimum)}–${formatAmount(maximum)}`;
  if (Number.isFinite(minimum)) return `${formatAmount(minimum)}+`;
  if (Number.isFinite(maximum)) return `Up to ${formatAmount(maximum)}`;
  return "Unknown";
}

function descriptionSummary(description) {
  const normalized = text(description).replace(/\s+/g, " ");
  if (!normalized) return "No verified description is available for this job.";
  return normalized.length > 190 ? `${normalized.slice(0, 187)}…` : normalized;
}

export function evaluationLabel(evaluation = {}) {
  const status = text(evaluation.status).toLowerCase();
  if (status === "eligible") return "Eligible match";
  if (status === "uncertain") return "Needs review";
  if (status === "not_evaluated") return "Not evaluated";
  const state = text(evaluation.state).toLowerCase();
  if (state === "loading") return "Evaluation loading";
  if (state === "stale") return "Evaluation stale";
  if (state === "partial") return "Partial evaluation";
  if (state === "unavailable") return "Evaluation unavailable";
  return "Evaluation unknown";
}

export function toPersonalizedJobView(job = {}) {
  const safeJob = stripInternalJobFields(job);
  const id = text(safeJob.canonical_job_id || safeJob.posting_id);
  const company = unknown(safeJob.company, "Unknown company");
  const experienceLevel = unknown(safeJob.experience_level);
  const workArrangement = normalizeArrangement(safeJob.work_arrangement);
  const description = text(safeJob.description);
  const evaluation = safeJob.evaluation && typeof safeJob.evaluation === "object" ? safeJob.evaluation : {};
  const runrSummary = safeJob.runr_summary && typeof safeJob.runr_summary === "object" ? safeJob.runr_summary : {};
  const structuredDescription = safeJob.structured_description && typeof safeJob.structured_description === "object" ? safeJob.structured_description : {};
  const originalPosting = safeJob.original_posting && typeof safeJob.original_posting === "object" ? safeJob.original_posting : {};
  const matchIntelligence = safeJob.match_intelligence && typeof safeJob.match_intelligence === "object"
    ? safeJob.match_intelligence
    : (evaluation.match_intelligence && typeof evaluation.match_intelligence === "object" ? evaluation.match_intelligence : {});
  const companyDetail = safeJob.company_detail && typeof safeJob.company_detail === "object" ? safeJob.company_detail : {};
  const companyProfile = companyDetail.profile && typeof companyDetail.profile === "object" ? companyDetail.profile : {};
  const languages = Array.isArray(safeJob.languages) ? safeJob.languages.map(text).filter(Boolean) : [];
  const unknownFields = Array.isArray(evaluation.unknown_fields) ? evaluation.unknown_fields.map(text).filter(Boolean) : [];
  const applicantIntelligence = safeJob.applicant_intelligence && typeof safeJob.applicant_intelligence === "object" ? safeJob.applicant_intelligence : {};
  const latestApplicants = applicantIntelligence.latest && typeof applicantIntelligence.latest === "object" ? applicantIntelligence.latest : {};
  const proApplicants = applicantIntelligence.pro && typeof applicantIntelligence.pro === "object" ? applicantIntelligence.pro : null;
  const exactApplicantCount = proApplicants?.latest_count;
  const applicantLabel = Number.isFinite(Number(exactApplicantCount))
    ? `${Number(exactApplicantCount).toLocaleString()} applicants`
    : text(latestApplicants.label) || (applicantIntelligence.state === "available" ? "Applicant data available in Runr Pro" : "Unknown");
  return {
    ...safeJob,
    id,
    company,
    companyDetail,
    companyProfile,
    title: unknown(safeJob.title, "Untitled job"),
    location: unknown(safeJob.location),
    experienceLevel,
    workArrangement,
    employmentType: unknown(safeJob.employment_type),
    category: unknown(safeJob.category),
    description,
    descriptionSummary: descriptionSummary(description),
    salaryLabel: formatSalary(safeJob.salary),
    languages,
    postedAt: safeJob.posted_at || safeJob.first_seen_at || safeJob.last_verified_at || "",
    lastVerifiedAt: safeJob.last_verified_at || "",
    applyUrl: text(safeJob.apply_url),
    lifecycleState: unknown(safeJob.lifecycle_state),
    userState: text(safeJob.user_state) || "none",
    evaluation,
    evaluationLabel: evaluationLabel(evaluation),
    evaluationUnknownFields: unknownFields,
    runrSummary,
    structuredDescription,
    originalPosting,
    descriptionIntelligence: safeJob.description_intelligence && typeof safeJob.description_intelligence === "object" ? safeJob.description_intelligence : {},
    matchIntelligence,
    applicantIntelligence,
    applicantLabel,
    applicantFreshness: text(applicantIntelligence.freshness?.state) || "unknown",
    applicantApplyMethod: text(applicantIntelligence.apply_method) || "unknown",
    priority: safeJob.priority && typeof safeJob.priority === "object" ? safeJob.priority : { state: "unknown", score: null },
    improveResume: matchIntelligence.improve_resume && typeof matchIntelligence.improve_resume === "object" ? matchIntelligence.improve_resume : {},
    dataMode: "real",
  };
}

export function unknownCompanyCharacteristics(characteristics = {}) {
  return {
    industry: unknown(characteristics.industry),
    size: unknown(characteristics.size),
    stage: unknown(characteristics.stage),
    fundingStage: unknown(characteristics.funding_stage),
    headquarters: unknown(characteristics.headquarters),
    foundedYear: unknown(characteristics.founded_year),
  };
}

export function companyProfileField(profile = {}, name, fallback = "Unknown") {
  const fields = profile?.fields && typeof profile.fields === "object" ? profile.fields : profile;
  const record = fields?.[name];
  if (!record || typeof record !== "object" || text(record.state).toLowerCase() !== "known" || record.value === null || record.value === undefined || record.value === "") {
    return { value: fallback, state: "unknown", provenance: record?.provenance || {}, verifiedAt: text(record?.verified_at) };
  }
  const value = Array.isArray(record.value) ? record.value.join(", ") : text(record.value);
  return { value: value || fallback, state: value ? "known" : "unknown", provenance: record.provenance || {}, verifiedAt: text(record.verified_at) };
}

export function companyProfileIsUnverified(profile = {}) {
  const fields = profile?.fields && typeof profile.fields === "object" ? profile.fields : profile;
  const names = ["website", "industry", "company_size", "headquarters", "founded_year", "company_stage", "funding_stage", "total_funding", "funding_year", "benefits", "sponsorship", "leadership_type"];
  return names.every((name) => text(fields?.[name]?.state).toLowerCase() !== "known");
}

export function filtersFromSavedSearch(payload = {}) {
  const saved = payload?.filters && typeof payload.filters === "object" ? payload.filters : {};
  return {
    ...INITIAL_PERSONALIZED_JOB_FILTERS,
    query: firstValue(saved.q || saved.search || saved.search_text || saved.query),
    location: firstValue(saved.location),
    workArrangement: firstValue(saved.work_arrangement) || "all",
    employmentType: firstValue(saved.employment_type) || "all",
    experienceLevel: firstValue(saved.experience_level || saved.experience) || "all",
    category: firstValue(saved.category),
    salaryMin: firstValue(saved.salary_min),
    salaryMax: firstValue(saved.salary_max),
    language: firstValue(saved.language || saved.languages),
    workAuthorization: firstValue(saved.work_authorization),
    sponsorship: firstValue(saved.sponsorship),
    company: firstValue(saved.company),
    industry: firstValue(saved.industry),
    companySize: firstValue(saved.company_size),
    companyStage: firstValue(saved.company_stage),
    fundingStage: firstValue(saved.funding_stage),
    fundingMin: firstValue(saved.funding_min),
    fundingMax: firstValue(saved.funding_max),
    foundedYearMin: firstValue(saved.founded_year_min),
    foundedYearMax: firstValue(saved.founded_year_max),
    fundingYearMin: firstValue(saved.funding_year_min),
    fundingYearMax: firstValue(saved.funding_year_max),
    hiddenCompanies: firstValue(saved.hidden_companies),
    education: firstValue(saved.education),
    preferredMajor: firstValue(saved.preferred_major || saved.preferred_majors),
    securityClearance: firstValue(saved.security_clearance),
    liftingRequirement: firstValue(saved.lifting_requirement || saved.physical_requirement),
    datePosted: "all",
  };
}
