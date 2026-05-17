const DEFAULT_DISCOVERY_STATUS = "not_started";

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
 * @property {"not_started" | "running" | "completed" | "failed"} peopleDiscoveryStatus
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
  const categories = normalized.categories && typeof normalized.categories === "object" ? { ...normalized.categories } : {};
  for (const category of PEOPLE_CATEGORY_CONFIG) {
    categories[category.id] = Array.isArray(categories[category.id]) ? categories[category.id] : [];
  }
  return {
    runId: String(normalized.runId || ""),
    workspaceId: String(normalized.workspaceId || ""),
    jobId: String(normalized.jobId || job.job_id || job.jobId || ""),
    company: String(normalized.company || job.company || ""),
    jobTitle: String(normalized.jobTitle || job.title || ""),
    peopleDiscoveryStatus: String(normalized.peopleDiscoveryStatus || DEFAULT_DISCOVERY_STATUS),
    contextExtraction:
      normalized.contextExtraction && typeof normalized.contextExtraction === "object"
        ? { ...normalized.contextExtraction }
        : {},
    searchHypotheses: Array.isArray(normalized.searchHypotheses) ? normalized.searchHypotheses : [],
    publicProfileCandidates: Array.isArray(normalized.publicProfileCandidates)
      ? normalized.publicProfileCandidates
      : [],
    categories,
    passes: Array.isArray(normalized.passes) ? normalized.passes : [],
    provider: normalized.provider && typeof normalized.provider === "object" ? normalized.provider : {},
    warnings: Array.isArray(normalized.warnings) ? normalized.warnings : [],
    selectedPeople: Array.isArray(normalized.selectedPeople) ? normalized.selectedPeople : [],
    error: String(normalized.error || ""),
    lastStartedAt: String(normalized.lastStartedAt || ""),
    lastCompletedAt: String(normalized.lastCompletedAt || ""),
    lastUpdatedAt: String(normalized.lastUpdatedAt || ""),
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
      return buildMockPeopleDiscoveryRun({ runId, jobId, job });
    }
    throw error;
  }
}

export async function getPeopleDiscoveryStatus(request, { runId, jobId }) {
  return request(
    `/runs/${encodeURIComponent(runId)}/jobs/by-id/${encodeURIComponent(jobId)}/people-discovery/status`,
  );
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

function buildMockPeopleDiscoveryRun({ runId, jobId, job = {} }) {
  const company = String(job.company || "Target Company");
  const location = String(job.location || job.location_raw || "Berlin, Germany");
  const title = String(job.title || "Selected Role");
  const categoryState = {
    hiring_manager: [
      {
        id: "mock-hiring-manager-1",
        category: "hiring_manager",
        name: "Alex Schmidt",
        title: "Director of Operations DACH",
        company,
        location,
        profileUrl: "https://www.linkedin.com/in/mock-alex-schmidt",
        source: "public_profile_search",
        confidence: 76,
        confidenceLabel: "Medium",
        reasoningNote:
          "Likely relevant because the public title and company match the role context, but the remit appears broader than one local team.",
        evidenceSnippets: ["Director of Operations DACH", company, location],
        caveats: ["Their remit may be broader than the exact team or country for this role."],
        searchQueries: [`${company} Director Operations DACH LinkedIn`],
        discoveredSearchQuery: `${company} Director Operations DACH LinkedIn`,
        regionScopeCaveat: "Their remit may be broader than the exact team or country for this role.",
        confidenceBreakdown: null,
        status: "unreviewed",
      },
    ],
    potential_colleague: [
      {
        id: "mock-colleague-1",
        category: "potential_colleague",
        name: "Mina Keller",
        title,
        company,
        location,
        profileUrl: "https://www.linkedin.com/in/mock-mina-keller",
        source: "public_profile_search",
        confidence: 68,
        confidenceLabel: "Medium",
        reasoningNote:
          "Potential match because this person appears to work in the same function and location, but the exact reporting line is not confirmed.",
        evidenceSnippets: [title, company, location],
        caveats: ["Confidence is based on public profile signals rather than confirmed org-chart data."],
        searchQueries: [`${company} ${title} LinkedIn`],
        discoveredSearchQuery: `${company} ${title} LinkedIn`,
        regionScopeCaveat: "",
        confidenceBreakdown: null,
        status: "unreviewed",
      },
    ],
    executive: [
      {
        id: "mock-executive-1",
        category: "executive",
        name: "Lena Vogt",
        title: "VP Operations Europe",
        company,
        location,
        profileUrl: "https://www.linkedin.com/in/mock-lena-vogt",
        source: "public_profile_search",
        confidence: 61,
        confidenceLabel: "Medium",
        reasoningNote:
          "Potential match because this leader appears connected to the same function, though the scope is likely regional rather than role-specific.",
        evidenceSnippets: ["VP Operations Europe", company, "Regional scope"],
        caveats: ["Their remit may be broader than the exact team or country for this role."],
        searchQueries: [`${company} VP Operations Europe LinkedIn`],
        discoveredSearchQuery: `${company} VP Operations Europe LinkedIn`,
        regionScopeCaveat: "Their remit may be broader than the exact team or country for this role.",
        confidenceBreakdown: null,
        status: "unreviewed",
      },
    ],
  };
  return normalizePeopleDiscoveryRun({
    runId,
    workspaceId: "",
    jobId,
    company,
    jobTitle: title,
    peopleDiscoveryStatus: "completed",
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
    categories: categoryState,
    passes: [],
    provider: { search: "mock", query_planner: "mock", resolver: "mock" },
    warnings: ["Using frontend mock data because the people-discovery endpoint is not available."],
    selectedPeople: [],
    error: "",
    lastStartedAt: "",
    lastCompletedAt: "",
    lastUpdatedAt: new Date().toISOString(),
  });
}
