/**
 * Frontend contract for the future personalized jobs API.
 *
 * Every value in this module is deterministic preview data. Keeping the
 * fixture and its contract together makes it easy to replace this provider
 * with a real API without moving job objects into page components.
 */

export const PERSONALIZED_JOBS_FLAG = "VITE_PERSONALIZED_JOBS_EXPERIENCE";
export const PREVIEW_DATA_MODE = "synthetic";
export const PREVIEW_DATA_LABEL = "Preview data";
export const PERSONALIZED_JOBS_DATA_MODE = "VITE_PERSONALIZED_JOBS_DATA_MODE";

export function resolvePersonalizedJobsDataMode(env = {}) {
  return String(env[PERSONALIZED_JOBS_DATA_MODE] || PREVIEW_DATA_MODE).trim().toLowerCase() === "real"
    ? "real"
    : PREVIEW_DATA_MODE;
}

export const personalizedJobsDataMode = resolvePersonalizedJobsDataMode(
  typeof import.meta !== "undefined" ? import.meta.env || {} : {},
);

export const ONBOARDING_STORAGE_KEY = "runr.personalizedJobs.onboarding";
export const DISPOSITION_STORAGE_KEY = "runr.personalizedJobs.dispositions";
export const UPGRADE_DISMISSALS_STORAGE_KEY = "runr.personalizedJobs.upgradeDismissals";
export const POST_ONBOARDING_OFFER_STORAGE_KEY = "runr.personalizedJobs.postOnboardingOffer";

/** @typedef {"synthetic" | "real"} DataMode */
/** @typedef {"eligible" | "review" | "ineligible"} EligibilityStatus */

/**
 * @typedef {Object} JobCard
 * @property {string} id
 * @property {string} title
 * @property {string} company
 * @property {string=} companyLogoUrl
 * @property {string} location
 * @property {"remote" | "hybrid" | "onsite"} workArrangement
 * @property {string} postedAt
 * @property {string} source
 * @property {string=} salary
 * @property {string} descriptionSummary
 * @property {number} matchScore
 * @property {string} matchLabel
 * @property {EligibilityStatus} eligibilityStatus
 * @property {string[]} recommendationReasons
 * @property {string[]} missingQualifications
 * @property {string[]} warningReasons
 * @property {boolean} hidden
 * @property {string=} hiddenReasonCode
 * @property {string=} hiddenReasonLabel
 * @property {boolean} saved
 * @property {string} applicationStatus
 * @property {boolean} paidInsightsAvailable
 * @property {DataMode} dataMode
 * @property {string} description
 * @property {string} experienceLevel
 * @property {string[]} matchingEvidence
 * @property {string[]} verifiedInformation
 * @property {string[]} inferredRequirements
 * @property {string[]} uncertainInformation
 */

/** @typedef {Object} JobFeedSummary
 * @property {number} totalFound
 * @property {number} strongMatches
 * @property {number} eligibleJobs
 * @property {number} hiddenJobs
 * @property {number} newSinceLastVisit
 * @property {string} generatedAt
 * @property {DataMode} dataMode
 */

/** @typedef {Object} JobPreferenceProfile
 * @property {string[]} targetRoles
 * @property {string[]} targetLocations
 * @property {string[]} workArrangements
 * @property {string} seniority
 * @property {string[]} employmentTypes
 * @property {string[]} languages
 * @property {string} workAuthorization
 * @property {boolean} sponsorshipRequired
 * @property {string} relocationPreference
 * @property {string} salaryExpectation
 * @property {string} earliestStartDate
 * @property {string} maximumCommute
 * @property {string} sourceCvName
 * @property {number} profileCompletion
 */

/** @typedef {Object} HiddenReasonGroup
 * @property {string} code
 * @property {string} label
 * @property {string} explanation
 * @property {number} count
 * @property {JobCard[]} jobs
 */

/** @typedef {Object} EntitlementPreview
 * @property {string} featureKey
 * @property {boolean} available
 * @property {string} requiredPlan
 * @property {string} explanation
 */

export const PREVIEW_PROFILE = Object.freeze({
  targetRoles: ["Product Operations Manager", "Operations & Insights Lead"],
  targetLocations: ["Berlin", "Remote in Germany"],
  workArrangements: ["hybrid", "remote"],
  seniority: "mid",
  employmentTypes: ["full-time"],
  languages: ["English — fluent", "German — conversational"],
  workAuthorization: "EU / EEA citizen",
  sponsorshipRequired: false,
  relocationPreference: "Open to Berlin or remote",
  salaryExpectation: "€68,000–€82,000",
  earliestStartDate: "Within 1 month",
  maximumCommute: "45 minutes",
  sourceCvName: "Alex Morgan — Product Operations CV.pdf",
  profileCompletion: 82,
});

export const PREVIEW_FEED_SUMMARY = Object.freeze({
  totalFound: 1284,
  strongMatches: 6,
  eligibleJobs: 1136,
  hiddenJobs: 148,
  newSinceLastVisit: 18,
  generatedAt: "2026-08-04T10:30:00.000Z",
  dataMode: PREVIEW_DATA_MODE,
});

const JOBS = [
  {
    id: "preview-aurora-product-ops",
    title: "Product Operations Manager",
    company: "Aurora Labs",
    companyLogoUrl: "https://images.unsplash.com/photo-1560472354-b33ff0c44a43?w=80&h=80&fit=crop",
    location: "Berlin, Germany",
    workArrangement: "hybrid",
    postedAt: "2026-08-04T08:10:00.000Z",
    source: "LinkedIn",
    salary: "€72,000–€84,000",
    descriptionSummary: "Own the operating rhythm that turns product strategy into clear, measurable execution across teams.",
    matchScore: 94,
    matchLabel: "Strong match",
    eligibilityStatus: "eligible",
    recommendationReasons: ["Product operations experience aligns", "Berlin hybrid setup fits", "Salary sits inside your range"],
    missingQualifications: [],
    warningReasons: [],
    hidden: false,
    hiddenReasonCode: "",
    hiddenReasonLabel: "",
    saved: false,
    applicationStatus: "Not started",
    paidInsightsAvailable: true,
    dataMode: PREVIEW_DATA_MODE,
    experienceLevel: "mid",
    description: "Aurora Labs is looking for a Product Operations Manager to coordinate planning, launch readiness, and feedback loops across product and customer teams. You will build lightweight systems that help teams make faster decisions and keep customers at the centre of delivery.",
    matchingEvidence: ["3+ years coordinating cross-functional product work", "Experience building repeatable operating processes", "Strong stakeholder communication evidence in your CV"],
    verifiedInformation: ["Hybrid · Berlin", "Full-time", "Posted today", "Salary range supplied by the employer"],
    inferredRequirements: ["Runr estimates that your product operations experience transfers well to this role."],
    uncertainInformation: ["The listing does not specify the exact number of years expected."],
  },
  {
    id: "preview-signal-insights",
    title: "Operations & Insights Partner",
    company: "Signal Health",
    companyLogoUrl: "https://images.unsplash.com/photo-1559757175-0eb30cd8c063?w=80&h=80&fit=crop",
    location: "Remote in Germany",
    workArrangement: "remote",
    postedAt: "2026-08-03T14:30:00.000Z",
    source: "Welcome to the Jungle",
    salary: "€66,000–€79,000",
    descriptionSummary: "Use customer and operational signals to improve how a fast-growing health platform works.",
    matchScore: 88,
    matchLabel: "Good match",
    eligibilityStatus: "eligible",
    recommendationReasons: ["Description matches your systems-thinking evidence", "Remote in Germany is a fit", "Strong overlap with stakeholder work"],
    missingQualifications: ["Direct health-tech experience is not shown"],
    warningReasons: [],
    hidden: false,
    hiddenReasonCode: "",
    hiddenReasonLabel: "",
    saved: true,
    applicationStatus: "Not started",
    paidInsightsAvailable: true,
    dataMode: PREVIEW_DATA_MODE,
    experienceLevel: "mid",
    description: "Signal Health needs an Operations & Insights Partner to connect customer feedback, team workflows, and product priorities. The title is intentionally broad; the role description emphasises operating models, experiment tracking, and clear communication across functions.",
    matchingEvidence: ["CV evidence points to operational analysis", "Your cross-team process work matches the description", "Remote preference is compatible"],
    verifiedInformation: ["Remote in Germany", "Full-time", "Posted yesterday"],
    inferredRequirements: ["Runr inferred a strong description-to-CV match even though the title is not an exact target-role match."],
    uncertainInformation: ["Health-tech experience may be preferred, but the employer does not label it as required."],
  },
  {
    id: "preview-cobalt-pipeline",
    title: "Business Operations Lead",
    company: "Cobalt Cloud",
    companyLogoUrl: "https://images.unsplash.com/photo-1551434678-e076c223a692?w=80&h=80&fit=crop",
    location: "Berlin, Germany",
    workArrangement: "hybrid",
    postedAt: "2026-08-01T09:00:00.000Z",
    source: "Ashby",
    salary: "€78,000–€92,000",
    descriptionSummary: "Lead planning and process improvements for a growing cloud infrastructure team.",
    matchScore: 86,
    matchLabel: "Good match",
    eligibilityStatus: "eligible",
    recommendationReasons: ["Your planning experience is highly relevant", "Berlin hybrid setup fits", "Already in your application pipeline"],
    missingQualifications: [],
    warningReasons: ["The salary range begins above your stated expectation"],
    hidden: false,
    hiddenReasonCode: "",
    hiddenReasonLabel: "",
    saved: false,
    applicationStatus: "CV ready",
    paidInsightsAvailable: true,
    dataMode: PREVIEW_DATA_MODE,
    experienceLevel: "lead",
    description: "Cobalt Cloud is hiring a Business Operations Lead to bring structure to annual planning, resource allocation, and operational reporting. This preview marks the role as already part of the application pipeline.",
    matchingEvidence: ["Planning and reporting experience aligns", "Cross-functional leadership evidence found", "Role seniority is close to your target"],
    verifiedInformation: ["Hybrid · Berlin", "Full-time", "Posted 3 days ago"],
    inferredRequirements: ["Runr estimates that you meet the core operating-model requirements."],
    uncertainInformation: [],
  },
  {
    id: "preview-plain-ops-coordinator",
    title: "Operations Coordinator",
    company: "Plainspoken Studio",
    location: "Hamburg, Germany",
    workArrangement: "onsite",
    postedAt: "2026-08-02T11:45:00.000Z",
    source: "Company careers",
    descriptionSummary: "Keep a small creative technology studio organised across projects, partners, and day-to-day operations.",
    matchScore: 73,
    matchLabel: "Possible match",
    eligibilityStatus: "eligible",
    recommendationReasons: ["Operations coordination experience aligns", "English-first team", "No salary was published"],
    missingQualifications: ["Salary information is missing from the listing"],
    warningReasons: ["On-site Hamburg may require a longer commute"],
    hidden: false,
    hiddenReasonCode: "",
    hiddenReasonLabel: "",
    saved: false,
    applicationStatus: "Not started",
    paidInsightsAvailable: true,
    dataMode: PREVIEW_DATA_MODE,
    experienceLevel: "mid",
    description: "Plainspoken Studio needs an Operations Coordinator for project tracking, vendor communication, and studio planning. Compensation is not included in the public listing.",
    matchingEvidence: ["Coordination and vendor-management evidence found"],
    verifiedInformation: ["On-site · Hamburg", "Full-time", "Posted 2 days ago"],
    inferredRequirements: ["Runr estimates that the role is adjacent to your target, but the commute may be a practical constraint."],
    uncertainInformation: ["Salary is not published."],
  },
  {
    id: "preview-loop-product-ops",
    title: "Product Operations Specialist",
    company: "Loop Commerce",
    location: "Remote in Germany",
    workArrangement: "remote",
    postedAt: "2026-07-29T12:00:00.000Z",
    source: "LinkedIn",
    salary: "€60,000–€70,000",
    descriptionSummary: "Support product launches, customer feedback, and internal documentation for a commerce platform.",
    matchScore: 81,
    matchLabel: "Good match",
    eligibilityStatus: "eligible",
    recommendationReasons: ["Product launch experience aligns", "Remote preference fits", "English is the primary working language"],
    missingQualifications: ["The listing asks for SQL familiarity; evidence is limited"],
    warningReasons: ["Salary range is below your preferred minimum"],
    hidden: false,
    hiddenReasonCode: "",
    hiddenReasonLabel: "",
    saved: false,
    applicationStatus: "Not started",
    paidInsightsAvailable: true,
    dataMode: PREVIEW_DATA_MODE,
    experienceLevel: "mid",
    description: "Loop Commerce is looking for a Product Operations Specialist to support launches and turn customer feedback into actionable product insights.",
    matchingEvidence: ["Product launch and documentation experience aligns", "Remote setup fits your preference"],
    verifiedInformation: ["Remote in Germany", "Full-time", "Posted 6 days ago"],
    inferredRequirements: ["Runr estimates a useful match despite limited SQL evidence."],
    uncertainInformation: [],
  },
  {
    id: "preview-lumen-german",
    title: "Senior Product Operations Manager",
    company: "Lumen Mobility",
    location: "Munich, Germany",
    workArrangement: "hybrid",
    postedAt: "2026-08-04T07:15:00.000Z",
    source: "LinkedIn",
    salary: "€80,000–€96,000",
    descriptionSummary: "Lead product operations for a mobility platform serving German-speaking customers and partners.",
    matchScore: 91,
    matchLabel: "Strong match, eligibility blocked",
    eligibilityStatus: "ineligible",
    recommendationReasons: ["Target role and experience align", "Salary range fits", "Mobility domain is adjacent"],
    missingQualifications: ["Fluent German is required for customer and partner conversations"],
    warningReasons: ["Runr could not verify fluent German from your current profile"],
    hidden: true,
    hiddenReasonCode: "language_requirement",
    hiddenReasonLabel: "Language requirement",
    saved: false,
    applicationStatus: "Not started",
    paidInsightsAvailable: true,
    dataMode: PREVIEW_DATA_MODE,
    experienceLevel: "senior",
    description: "Lumen Mobility is hiring a Senior Product Operations Manager to own launch planning and partner feedback for its German market. The posting says fluent German is required for regular customer and partner conversations.",
    matchingEvidence: ["Target role is a close match", "Senior operating-model experience aligns"],
    verifiedInformation: ["Hybrid · Munich", "Full-time", "Posted today", "Fluent German listed by the employer"],
    inferredRequirements: ["Runr inferred that conversational German in your profile is below the stated fluency requirement."],
    uncertainInformation: [],
  },
  {
    id: "preview-nova-authorization",
    title: "Operations Program Manager",
    company: "Nova Systems",
    location: "Berlin, Germany",
    workArrangement: "hybrid",
    postedAt: "2026-08-03T08:45:00.000Z",
    source: "Greenhouse",
    salary: "€75,000–€90,000",
    descriptionSummary: "Coordinate regulated infrastructure programs supporting public-sector customers across Europe.",
    matchScore: 89,
    matchLabel: "Strong match, eligibility blocked",
    eligibilityStatus: "ineligible",
    recommendationReasons: ["Program management evidence aligns", "Berlin location fits", "Salary range fits"],
    missingQualifications: ["The employer requires an active EU security clearance"],
    warningReasons: ["Work authorization / clearance requirement is not met in the preview profile"],
    hidden: true,
    hiddenReasonCode: "work_authorization",
    hiddenReasonLabel: "Work authorization",
    saved: false,
    applicationStatus: "Not started",
    paidInsightsAvailable: true,
    dataMode: PREVIEW_DATA_MODE,
    experienceLevel: "senior",
    description: "Nova Systems supports regulated public-sector programs and requires an active EU security clearance for this role. The job is otherwise closely aligned with your operating-model experience.",
    matchingEvidence: ["Program coordination experience aligns", "Berlin and salary preferences fit"],
    verifiedInformation: ["Hybrid · Berlin", "Full-time", "Posted yesterday", "Clearance requirement stated by the employer"],
    inferredRequirements: ["Runr inferred that your current work authorization profile does not include the required clearance."],
    uncertainInformation: [],
  },
  {
    id: "preview-heimdall-senior",
    title: "Head of Business Operations",
    company: "Heimdall Security",
    location: "Berlin, Germany",
    workArrangement: "hybrid",
    postedAt: "2026-08-02T06:20:00.000Z",
    source: "Company careers",
    salary: "€110,000–€135,000",
    descriptionSummary: "Set the operating strategy for a security company scaling from 80 to 200 employees.",
    matchScore: 84,
    matchLabel: "Relevant, experience gap",
    eligibilityStatus: "ineligible",
    recommendationReasons: ["Business operations domain aligns", "Berlin setup fits", "Leadership scope is adjacent"],
    missingQualifications: ["The role asks for 8+ years in business operations", "People leadership at scale is not shown"],
    warningReasons: ["Experience level is materially above your current profile"],
    hidden: true,
    hiddenReasonCode: "experience",
    hiddenReasonLabel: "Experience",
    saved: false,
    applicationStatus: "Not started",
    paidInsightsAvailable: true,
    dataMode: PREVIEW_DATA_MODE,
    experienceLevel: "lead",
    description: "Heimdall Security is looking for a Head of Business Operations to set operating strategy while the company scales. The listing asks for eight or more years of business operations experience and a track record of leading larger teams.",
    matchingEvidence: ["Business operations experience is relevant", "Berlin location fits"],
    verifiedInformation: ["Hybrid · Berlin", "Full-time", "Posted 2 days ago", "8+ years listed by the employer"],
    inferredRequirements: ["Runr inferred an experience gap based on the profile you provided for this preview."],
    uncertainInformation: [],
  },
  {
    id: "preview-atlas-location",
    title: "Operations Manager",
    company: "Atlas Foods",
    location: "Amsterdam, Netherlands",
    workArrangement: "onsite",
    postedAt: "2026-08-01T15:10:00.000Z",
    source: "Indeed",
    salary: "€70,000–€82,000",
    descriptionSummary: "Run daily operations for a fast-moving food technology hub in Amsterdam.",
    matchScore: 82,
    matchLabel: "Strong match, location blocked",
    eligibilityStatus: "ineligible",
    recommendationReasons: ["Operations management evidence aligns", "Salary range fits", "English-first environment"],
    missingQualifications: ["The role is on-site in Amsterdam"],
    warningReasons: ["The location is outside your current search area"],
    hidden: true,
    hiddenReasonCode: "location",
    hiddenReasonLabel: "Location",
    saved: false,
    applicationStatus: "Not started",
    paidInsightsAvailable: true,
    dataMode: PREVIEW_DATA_MODE,
    experienceLevel: "mid",
    description: "Atlas Foods runs its operations hub from Amsterdam and expects this Operations Manager to work on-site most days. The role is otherwise a close match for your operating experience.",
    matchingEvidence: ["Operations management evidence aligns", "Salary range fits"],
    verifiedInformation: ["On-site · Amsterdam", "Full-time", "Posted 3 days ago"],
    inferredRequirements: ["Runr inferred that Amsterdam falls outside your current preferred locations."],
    uncertainInformation: [],
  },
  {
    id: "preview-orbit-uncertain",
    title: "Customer Operations Associate",
    company: "Orbit Research",
    location: "Paris, France",
    workArrangement: "hybrid",
    postedAt: "2026-07-31T16:00:00.000Z",
    source: "Otta",
    salary: "€52,000–€64,000",
    descriptionSummary: "Help a research platform improve customer workflows, onboarding, and operational reporting.",
    matchScore: 62,
    matchLabel: "Low confidence",
    eligibilityStatus: "review",
    recommendationReasons: ["Some workflow experience overlaps", "Customer operations is adjacent"],
    missingQualifications: ["The job description is not clear about language and authorization requirements"],
    warningReasons: ["Important eligibility information is missing or ambiguous"],
    hidden: true,
    hiddenReasonCode: "uncertain_requirement",
    hiddenReasonLabel: "Uncertain requirement",
    saved: false,
    applicationStatus: "Not started",
    paidInsightsAvailable: true,
    dataMode: PREVIEW_DATA_MODE,
    experienceLevel: "entry",
    description: "Orbit Research is hiring a Customer Operations Associate. The public description covers workflows and onboarding but does not make language, authorization, or relocation expectations clear.",
    matchingEvidence: ["Workflow documentation is a partial match"],
    verifiedInformation: ["Hybrid · Paris", "Full-time", "Posted 4 days ago"],
    inferredRequirements: ["Runr cannot confidently determine whether the role is eligible from the available text."],
    uncertainInformation: ["Language requirement is not stated", "Work authorization requirement is not stated"],
  },
  {
    id: "preview-low-relevance",
    title: "Sales Development Representative",
    company: "Brightline AI",
    location: "Berlin, Germany",
    workArrangement: "onsite",
    postedAt: "2026-07-30T10:15:00.000Z",
    source: "LinkedIn",
    salary: "€48,000–€58,000",
    descriptionSummary: "Build pipeline and qualify leads for an early-stage AI sales team.",
    matchScore: 38,
    matchLabel: "Low relevance",
    eligibilityStatus: "ineligible",
    recommendationReasons: ["Berlin location fits"],
    missingQualifications: ["Sales development is not one of your target role families"],
    warningReasons: ["Role title and day-to-day work are a weak match"],
    hidden: true,
    hiddenReasonCode: "low_relevance",
    hiddenReasonLabel: "Low relevance",
    saved: false,
    applicationStatus: "Not started",
    paidInsightsAvailable: true,
    dataMode: PREVIEW_DATA_MODE,
    experienceLevel: "entry",
    description: "Brightline AI is hiring a Sales Development Representative to build pipeline and qualify leads. The listing is located in Berlin but is not aligned with your target operations roles.",
    matchingEvidence: ["Berlin location is the only direct preference match"],
    verifiedInformation: ["On-site · Berlin", "Full-time", "Posted 5 days ago"],
    inferredRequirements: ["Runr inferred low relevance from the title, responsibilities, and your target roles."],
    uncertainInformation: [],
  },
];

function requiredString(value, field) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`Preview contract: ${field} must be a non-empty string.`);
  }
}

export function validateJobCard(job) {
  if (!job || typeof job !== "object") {
    throw new Error("Preview contract: job must be an object.");
  }
  ["id", "title", "company", "location", "workArrangement", "postedAt", "source", "descriptionSummary", "matchLabel", "applicationStatus", "dataMode"].forEach((field) => requiredString(job[field], field));
  if (!Number.isFinite(job.matchScore) || job.matchScore < 0 || job.matchScore > 100) {
    throw new Error("Preview contract: matchScore must be between 0 and 100.");
  }
  if (!Array.isArray(job.recommendationReasons) || !Array.isArray(job.missingQualifications) || !Array.isArray(job.warningReasons)) {
    throw new Error("Preview contract: reason fields must be arrays.");
  }
  if (typeof job.hidden !== "boolean" || typeof job.saved !== "boolean" || typeof job.paidInsightsAvailable !== "boolean") {
    throw new Error("Preview contract: hidden, saved, and paidInsightsAvailable must be booleans.");
  }
  if (!["synthetic", "real"].includes(job.dataMode)) {
    throw new Error("Preview contract: dataMode must be synthetic or real.");
  }
  return job;
}

export const PREVIEW_JOBS = Object.freeze(JOBS.map((job) => validateJobCard(Object.freeze(job))));

export const HIDDEN_REASON_DEFINITIONS = Object.freeze({
  language_requirement: {
    label: "Language requirement",
    explanation: "The listing asks for a language level that is not verified in your current preview profile.",
  },
  work_authorization: {
    label: "Work authorization",
    explanation: "The employer appears to require authorization or clearance that is not present in your preview profile.",
  },
  experience: {
    label: "Experience",
    explanation: "The role asks for substantially more experience or leadership scope than your current preview profile shows.",
  },
  location: {
    label: "Location",
    explanation: "The location or work arrangement is outside your current preview preferences.",
  },
  low_relevance: {
    label: "Low relevance",
    explanation: "The title and responsibilities are not close enough to your target roles for the recommended feed.",
  },
  uncertain_requirement: {
    label: "Uncertain requirement",
    explanation: "The public job text is missing important eligibility details, so Runr cannot confidently recommend it.",
  },
});

export function getHiddenReasonGroups(jobs = PREVIEW_JOBS) {
  return Object.entries(HIDDEN_REASON_DEFINITIONS)
    .map(([code, definition]) => {
      const matchingJobs = jobs.filter((job) => job.hidden && job.hiddenReasonCode === code);
      return {
        code,
        label: definition.label,
        explanation: definition.explanation,
        count: matchingJobs.length,
        jobs: matchingJobs,
      };
    })
    .filter((group) => group.jobs.length > 0);
}

export const PREVIEW_ENTITLEMENTS = Object.freeze({
  ai_eligibility_filter: { featureKey: "ai_eligibility_filter", available: false, requiredPlan: "Pro", explanation: "Runr checks language, authorization, location, and experience before a job reaches your recommended feed." },
  full_match_explanation: { featureKey: "full_match_explanation", available: false, requiredPlan: "Pro", explanation: "See the evidence behind every match, including which parts of your CV map to the employer's description." },
  semantic_matching: { featureKey: "semantic_matching", available: false, requiredPlan: "Pro", explanation: "Compare the meaning of your experience with the whole job description, even when titles differ." },
  tailored_cv: { featureKey: "tailored_cv", available: false, requiredPlan: "Pro", explanation: "Start with a CV shaped around this job's priorities instead of editing from scratch." },
  tailored_motivation_letter: { featureKey: "tailored_motivation_letter", available: false, requiredPlan: "Pro", explanation: "Create a focused motivation letter using the role's language and your strongest evidence." },
  scheduled_job_searches: { featureKey: "scheduled_job_searches", available: false, requiredPlan: "Pro", explanation: "Let Runr refresh your personalized search on a schedule and surface new matches for you." },
  assisted_apply: { featureKey: "assisted_apply", available: false, requiredPlan: "Pro", explanation: "Prepare an application package and get help with repetitive application fields." },
  multiple_active_searches: { featureKey: "multiple_active_searches", available: false, requiredPlan: "Pro", explanation: "Keep separate personalized searches active for different role families or locations." },
});

export const PREVIEW_UPGRADE_COPY = Object.freeze({
  ai_eligibility_filter: {
    title: "Stop reviewing jobs you cannot apply for",
    body: "Runr checks language, authorization, location and experience requirements before showing jobs as eligible.",
    cta: "See Runr Pro",
  },
  full_match_explanation: {
    title: "Understand exactly why this job fits",
    body: "See which requirements your profile supports, what may be missing and which details Runr could not confirm.",
    cta: "Unlock match insights",
  },
  tailored_cv: {
    title: "Turn this match into a tailored CV",
    body: "Runr highlights the experience and skills most relevant to this position while keeping your information truthful.",
    cta: "Unlock tailored CVs",
  },
  tailored_motivation_letter: {
    title: "Create a letter for this specific opportunity",
    body: "Runr connects the employer's needs with evidence from your real experience instead of producing a generic letter.",
    cta: "Unlock motivation letters",
  },
  assisted_apply: {
    title: "Spend less time repeating application details",
    body: "Runr helps fill supported application forms while keeping you in control of the final submission.",
    cta: "Unlock Assisted Apply",
  },
  multiple_active_searches: {
    title: "Search for another career direction",
    body: "Create another saved search for a different role, location or set of preferences.",
    cta: "Unlock multiple job searches",
  },
  scheduled_job_searches: {
    title: "Keep your job search working in the background",
    body: "Runr can refresh your saved searches automatically and surface newly discovered opportunities.",
    cta: "Unlock scheduled searches",
  },
  semantic_matching: {
    title: "Understand exactly why this job fits",
    body: "See which requirements your profile supports, what may be missing and which details Runr could not confirm.",
    cta: "Unlock match insights",
  },
});

export function getPreviewUpgradeCopy(featureKey) {
  return PREVIEW_UPGRADE_COPY[featureKey] || {
    title: "See what Runr can prepare for you",
    body: "Explore the next step for this job and keep control of every application decision.",
    cta: "See Runr Pro",
  };
}

export function getPreviewEntitlement(featureKey, planId = "free") {
  const entitlement = PREVIEW_ENTITLEMENTS[featureKey] || {
    featureKey,
    available: false,
    requiredPlan: "Pro",
    explanation: "This preview feature is available on Runr Pro.",
  };
  const normalizedPlanId = String(planId || "").trim().toLowerCase();
  const canonicalPlanId = ["runr_pro", "pro", "launch", "momentum", "scale", "business"].includes(normalizedPlanId)
    ? "runr_pro"
    : "free";
  const paidPlan = canonicalPlanId === "runr_pro";
  return { ...entitlement, available: entitlement.available || paidPlan };
}

export function isPersonalizedJobsExperienceEnabled(env = {}) {
  const value = String(env[PERSONALIZED_JOBS_FLAG] || "").trim().toLowerCase();
  return value === "1" || value === "true" || value === "on";
}

export const personalizedJobsExperienceEnabled = isPersonalizedJobsExperienceEnabled(
  typeof import.meta !== "undefined" ? import.meta.env || {} : {},
);

export function getFeedJobs({
  filters = {},
  dispositions = {},
  jobs = PREVIEW_JOBS,
  referenceDate = PREVIEW_FEED_SUMMARY.generatedAt,
} = {}) {
  const query = String(filters.query || "").trim().toLowerCase();
  const location = String(filters.location || "all").toLowerCase();
  const arrangement = String(filters.workArrangement || "all").toLowerCase();
  const datePosted = String(filters.datePosted || "all").toLowerCase();
  const experience = String(filters.experienceLevel || "all").toLowerCase();
  const salary = String(filters.salary || "all").toLowerCase();
  const onlyEligible = Boolean(filters.onlyEligible);
  const referenceTime = new Date(referenceDate).getTime();
  const maxAgeMs = datePosted === "24h" ? 24 * 60 * 60 * 1000 : datePosted === "7d" ? 7 * 24 * 60 * 60 * 1000 : datePosted === "30d" ? 30 * 24 * 60 * 60 * 1000 : null;

  const visibleJobs = jobs.filter((job) => {
    const locallyHidden = Boolean(dispositions.hidden?.[job.id]);
    const locallyRestored = Boolean(dispositions.restored?.[job.id]);
    if ((job.hidden && !locallyRestored) || locallyHidden) return false;
    const haystack = [job.title, job.company, job.location, job.descriptionSummary, job.description].join(" ").toLowerCase();
    if (query && !haystack.includes(query)) return false;
    if (location !== "all" && !job.location.toLowerCase().includes(location)) return false;
    if (arrangement !== "all" && job.workArrangement !== arrangement) return false;
    if (experience !== "all" && job.experienceLevel !== experience) return false;
    if (salary === "known" && !job.salary) return false;
    if (salary === "70k" && Number.parseInt(String(job.salary || "").replace(/[^0-9]/g, ""), 10) < 70000) return false;
    if (maxAgeMs !== null && referenceTime - new Date(job.postedAt).getTime() > maxAgeMs) return false;
    if (onlyEligible && job.eligibilityStatus !== "eligible") return false;
    return true;
  });

  const sort = String(filters.sort || "best").toLowerCase();
  return visibleJobs.sort((left, right) => {
    if (sort === "newest") return new Date(right.postedAt).getTime() - new Date(left.postedAt).getTime();
    if (sort === "salary") return Number.parseInt(String(right.salary || "0").replace(/[^0-9]/g, ""), 10) - Number.parseInt(String(left.salary || "0").replace(/[^0-9]/g, ""), 10);
    return right.matchScore - left.matchScore;
  });
}

export function getActivePreviewFilterCount(filters = {}) {
  return ["query", "location", "workArrangement", "datePosted", "experienceLevel", "salary", "onlyEligible", "sort"]
    .filter((name) => {
      if (name === "query") return Boolean(String(filters[name] || "").trim());
      if (name === "onlyEligible") return Boolean(filters[name]);
      if (name === "sort") return Boolean(filters[name] && filters[name] !== "best");
      return Boolean(filters[name] && filters[name] !== "all");
    }).length;
}

export function formatPreviewTimestamp(isoDate) {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
    timeZoneName: "short",
  }).format(new Date(isoDate));
}

export function formatPreviewDate(isoDate, referenceDate = PREVIEW_FEED_SUMMARY.generatedAt) {
  const ageHours = Math.max(0, Math.round((new Date(referenceDate).getTime() - new Date(isoDate).getTime()) / (60 * 60 * 1000)));
  if (ageHours < 1) return "just now";
  if (ageHours < 24) return `${ageHours}h ago`;
  const days = Math.round(ageHours / 24);
  return `${days}d ago`;
}
