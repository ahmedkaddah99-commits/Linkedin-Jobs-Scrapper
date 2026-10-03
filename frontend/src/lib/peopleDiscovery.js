const DEFAULT_DISCOVERY_STATUS = "not_started";

function firstValue(payload, ...keys) {
  for (const key of keys) {
    const value = payload?.[key];
    if (value !== undefined && value !== null && value !== "") {
      return value;
    }
  }
  return "";
}

export const PEOPLE_DISCOVERY_STEPS = [
  "Reading selected job",
  "Generating search hypotheses",
  "Searching public profiles - pass 1",
  "Reviewing matches",
  "Refining search terms",
  "Searching public profiles - pass 2",
  "Ranking likely people",
];

export const PEOPLE_CATEGORY_CONFIG = [
  {
    id: "hiring_manager",
    title: "Likely Hiring Managers",
    emptyState:
      "We could not confidently identify two people for this category. You can continue without them or run a broader search.",
  },
  {
    id: "potential_colleague",
    title: "Potential Team Members",
    emptyState:
      "We could not confidently identify two people for this category. You can continue without them or run a broader search.",
  },
  {
    id: "executive",
    title: "Senior Leaders",
    emptyState:
      "We could not confidently identify two people for this category. You can continue without them or run a broader search.",
  },
];

/**
 * @typedef {"hiring_manager" | "potential_colleague" | "executive"} PeopleCategory
 */

/**
 * @typedef {Object} ConfidenceBreakdown
 * @property {number} companyMatch
 * @property {number} titleCategoryMatch
 * @property {number} departmentFunctionMatch
 * @property {number} locationRegionMatch
 * @property {number} seniorityFit
 * @property {number} businessUnitRelevance
 * @property {number} profileFreshness
 * @property {number} sourceReliability
 * @property {number} evidenceQuality
 * @property {number} total
 * @property {"High" | "Medium" | "Low"} label
 */

/**
 * @typedef {Object} SearchHypothesis
 * @property {string} id
 * @property {number} passIndex
 * @property {PeopleCategory} category
 * @property {string} titleQuery
 * @property {string} keywordQuery
 * @property {string[]} locationModifiers
 * @property {number} confidenceBeforeSearch
 * @property {string} explanation
 * @property {string} discoveredQuery
 * @property {string} lane
 */

/**
 * @typedef {Object} PublicProfileCandidate
 * @property {string} id
 * @property {number} passIndex
 * @property {PeopleCategory} category
 * @property {string} name
 * @property {string} title
 * @property {string} company
 * @property {string} location
 * @property {string} profileUrl
 * @property {string} source
 * @property {string} searchQuery
 * @property {string[]} evidenceSnippets
 * @property {string} matchSummary
 * @property {string} lane
 */

/**
 * @typedef {Object} RelevantPerson
 * @property {string} id
 * @property {PeopleCategory} category
 * @property {string} name
 * @property {string} title
 * @property {string} company
 * @property {string} location
 * @property {string} profileUrl
 * @property {string} source
 * @property {number} confidence
 * @property {"High" | "Medium" | "Low"} confidenceLabel
 * @property {string} reasoningNote
 * @property {string[]} evidenceSnippets
 * @property {string[]} caveats
 * @property {string[]} searchQueries
 * @property {string} discoveredSearchQuery
 * @property {string} regionScopeCaveat
 * @property {ConfidenceBreakdown | null} confidenceBreakdown
 * @property {"unreviewed" | "confirmed" | "rejected" | "saved_for_outreach"} status
 */

/**
 * @typedef {Object} PeopleDiscoveryRun
 * @property {string} runId
 * @property {string} workspaceId
 * @property {string} jobId
 * @property {string} company
 * @property {string} jobTitle
 * @property {"not_started" | "running" | "completed" | "failed" | "not_configured"} peopleDiscoveryStatus
 * @property {Object} contextExtraction
 * @property {SearchHypothesis[]} searchHypotheses
 * @property {PublicProfileCandidate[]} publicProfileCandidates
 * @property {{ hiring_manager: RelevantPerson[], potential_colleague: RelevantPerson[], executive: RelevantPerson[] }} categories
 * @property {Object[]} passes
 * @property {Object} provider
 * @property {string[]} warnings
 * @property {RelevantPerson[]} selectedPeople
 * @property {string} error
 * @property {string} lastStartedAt
 * @property {string} lastCompletedAt
 * @property {string} lastUpdatedAt
 */

export function buildJobWorkspaceRoute({
  runId,
  jobId,
  mode = "context_only",
  sourceStage = "",
  reasonSummary = "",
}) {
  const params = new URLSearchParams();
  if (mode) params.set("mode", mode);
  if (sourceStage) params.set("source_stage", sourceStage);
  if (reasonSummary) params.set("reason_summary", reasonSummary);
  const query = params.toString();
  return `/job-workspaces/${encodeURIComponent(runId || "")}/${encodeURIComponent(jobId || "")}${query ? `?${query}` : ""}`;
}

export function normalizePeopleDiscoveryRun(payload, job = {}) {
  const normalized = payload && typeof payload === "object" ? { ...payload } : {};
  const rawCategories = firstValue(normalized, "categories", "category_results");
  const categories = rawCategories && typeof rawCategories === "object" ? { ...rawCategories } : {};
  for (const category of PEOPLE_CATEGORY_CONFIG) {
    categories[category.id] = Array.isArray(
      firstValue(categories, category.id, category.id.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase())),
    )
      ? firstValue(categories, category.id, category.id.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase()))
      : [];
  }
  return {
    runId: String(firstValue(normalized, "runId", "run_id") || ""),
    workspaceId: String(firstValue(normalized, "workspaceId", "workspace_id") || ""),
    jobId: String(firstValue(normalized, "jobId", "job_id") || job.job_id || job.jobId || ""),
    company: String(firstValue(normalized, "company", "company_name") || job.company || ""),
    jobTitle: String(firstValue(normalized, "jobTitle", "job_title", "title") || job.title || ""),
    peopleDiscoveryStatus: String(
      firstValue(normalized, "peopleDiscoveryStatus", "people_discovery_status", "status")
        || DEFAULT_DISCOVERY_STATUS,
    ),
    contextExtraction:
      firstValue(normalized, "contextExtraction", "context_extraction")
      && typeof firstValue(normalized, "contextExtraction", "context_extraction") === "object"
        ? { ...firstValue(normalized, "contextExtraction", "context_extraction") }
        : {},
    searchHypotheses: Array.isArray(firstValue(normalized, "searchHypotheses", "search_hypotheses"))
      ? firstValue(normalized, "searchHypotheses", "search_hypotheses")
      : [],
    publicProfileCandidates: Array.isArray(
      firstValue(normalized, "publicProfileCandidates", "public_profile_candidates"),
    )
      ? firstValue(normalized, "publicProfileCandidates", "public_profile_candidates")
      : [],
    categories,
    passes: Array.isArray(firstValue(normalized, "passes")) ? firstValue(normalized, "passes") : [],
    provider: firstValue(normalized, "provider") && typeof firstValue(normalized, "provider") === "object"
      ? firstValue(normalized, "provider")
      : {},
    warnings: Array.isArray(firstValue(normalized, "warnings")) ? firstValue(normalized, "warnings") : [],
    selectedPeople: Array.isArray(firstValue(normalized, "selectedPeople", "selected_people"))
      ? firstValue(normalized, "selectedPeople", "selected_people")
      : [],
    error: String(firstValue(normalized, "error", "error_message") || ""),
    lastStartedAt: String(firstValue(normalized, "lastStartedAt", "last_started_at") || ""),
    lastCompletedAt: String(firstValue(normalized, "lastCompletedAt", "last_completed_at") || ""),
    lastUpdatedAt: String(firstValue(normalized, "lastUpdatedAt", "last_updated_at") || ""),
  };
}

export function normalizeJobWorkspacePayload(payload) {
  const normalized = payload && typeof payload === "object" ? { ...payload } : {};
  const job = normalized.job && typeof normalized.job === "object" ? { ...normalized.job } : {};
  return {
    ...normalized,
    job,
    selected_relevant_people: Array.isArray(normalized.selected_relevant_people)
      ? normalized.selected_relevant_people
      : [],
    relevant_people_discovery: normalizePeopleDiscoveryRun(
      normalized.relevant_people_discovery,
      job,
    ),
  };
}

export async function fetchJobWorkspace(request, { runId, jobId }) {
  const payload = await request(
    `/runs/${encodeURIComponent(runId)}/jobs/by-id/${encodeURIComponent(jobId)}`,
  );
  return normalizeJobWorkspacePayload(payload);
}

export async function startPeopleDiscovery(request, { runId, jobId, job }) {
  try {
    const payload = await request(
      `/runs/${encodeURIComponent(runId)}/jobs/by-id/${encodeURIComponent(jobId)}/people-discovery/start`,
      { method: "POST", body: {} },
    );
    return normalizePeopleDiscoveryRun(payload, job);
  } catch (error) {
    if (error?.status === 404 || error?.code === "not_found") {
      return buildUnavailablePeopleDiscoveryRun({ runId, jobId, job });
    }
    throw error;
  }
}

export async function getPeopleDiscoveryStatus(request, { runId, jobId }) {
  const payload = await request(
    `/runs/${encodeURIComponent(runId)}/jobs/by-id/${encodeURIComponent(jobId)}/people-discovery/status`,
  );
  return {
    ...payload,
    peopleDiscoveryStatus: String(
      firstValue(payload, "peopleDiscoveryStatus", "people_discovery_status", "status")
        || DEFAULT_DISCOVERY_STATUS,
    ),
  };
}

export async function getPeopleDiscoveryResults(request, { runId, jobId, job }) {
  const payload = await request(
    `/runs/${encodeURIComponent(runId)}/jobs/by-id/${encodeURIComponent(jobId)}/people-discovery/results`,
  );
  return normalizePeopleDiscoveryRun(payload, job);
}

export async function confirmRelevantPerson(request, { runId, jobId, personId, job }) {
  const payload = await request(
    `/runs/${encodeURIComponent(runId)}/jobs/by-id/${encodeURIComponent(jobId)}/people-discovery/confirm`,
    {
      method: "POST",
      body: { person_id: personId },
    },
  );
  return normalizePeopleDiscoveryRun(payload, job);
}

export async function rejectRelevantPerson(request, { runId, jobId, personId, job }) {
  const payload = await request(
    `/runs/${encodeURIComponent(runId)}/jobs/by-id/${encodeURIComponent(jobId)}/people-discovery/reject`,
    {
      method: "POST",
      body: { person_id: personId },
    },
  );
  return normalizePeopleDiscoveryRun(payload, job);
}

export async function savePersonForOutreach(request, { runId, jobId, personId, job }) {
  const payload = await request(
    `/runs/${encodeURIComponent(runId)}/jobs/by-id/${encodeURIComponent(jobId)}/people-discovery/save-for-outreach`,
    {
      method: "POST",
      body: { person_id: personId },
    },
  );
  return normalizePeopleDiscoveryRun(payload, job);
}

export function countSelectedPeople(discoveryRun) {
  return (discoveryRun?.selectedPeople || []).filter(
    (person) => person?.status === "confirmed" || person?.status === "saved_for_outreach",
  ).length;
}

function buildUnavailablePeopleDiscoveryRun({ runId, jobId, job = {} }) {
  const company = String(job.company || "Target Company");
  const location = String(job.location || job.location_raw || "Berlin, Germany");
  const title = String(job.title || "Selected Role");
  return normalizePeopleDiscoveryRun({
    runId,
    workspaceId: "",
    jobId,
    company,
    jobTitle: title,
    peopleDiscoveryStatus: "not_configured",
    contextExtraction: {
      company,
      jobTitle: title,
      location,
      locationHint: location,
      department: "Hiring Team",
      discipline: "general",
      seniority: "manager",
      businessUnit: "",
      keywords: [title, company].filter(Boolean),
      descriptionExcerpt: "",
    },
    searchHypotheses: [],
    publicProfileCandidates: [],
    categories: { hiring_manager: [], potential_colleague: [], executive: [] },
    passes: [],
    provider: { search: "unavailable", query_planner: "unavailable", resolver: "unavailable" },
    warnings: ["People discovery endpoint is not available."],
    selectedPeople: [],
    error: "People discovery endpoint is not available.",
    lastStartedAt: "",
    lastCompletedAt: "",
    lastUpdatedAt: new Date().toISOString(),
  });
}
