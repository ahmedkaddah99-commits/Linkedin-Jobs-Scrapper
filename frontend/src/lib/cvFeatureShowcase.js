import { getPreviewEntitlement, PREVIEW_DATA_LABEL, PREVIEW_DATA_MODE } from "./personalizedJobs.js";

export const CV_SHOWCASE_SCENES = Object.freeze([
  {
    key: "relevant_jobs",
    eyebrow: "Find better opportunities",
    headline: "Focus on jobs worth your time",
    body: "Runr compares your experience, preferences and eligibility with each job before it reaches your shortlist.",
    icon: "filter_alt",
    entitlementKey: "ai_eligibility_filter",
  },
  {
    key: "match_explanations",
    eyebrow: "Understand every match",
    headline: "See why a job fits you",
    body: "Runr connects job requirements with evidence from your CV and clearly shows what may be missing or uncertain.",
    icon: "account_tree",
    entitlementKey: "full_match_explanation",
  },
  {
    key: "application_preparation",
    eyebrow: "Prepare a stronger application",
    headline: "Turn your experience into a tailored application",
    body: "Runr uses evidence from your real experience to prepare a relevant CV and motivation letter for each opportunity.",
    icon: "edit_document",
    entitlementKey: "tailored_cv",
  },
  {
    key: "assisted_apply",
    eyebrow: "Apply with less repetition",
    headline: "Spend less time filling the same forms",
    body: "Runr can reuse your verified information on supported application forms while you review every answer before submission.",
    icon: "task_alt",
    entitlementKey: "assisted_apply",
  },
]);

export const PREVIEW_CV_PROFILE = Object.freeze({
  recentRole: "Product Operations Manager",
  experienceCount: 4,
  education: "Business & information systems",
  skills: ["Planning", "Analytics", "Process design", "Stakeholder management", "SQL", "Roadmapping"],
  languages: ["English · fluent", "German · conversational"],
  contactDetails: "Ready for applications",
});

export function getCvShowcaseEntitlements(planId = "none") {
  return Object.fromEntries(
    CV_SHOWCASE_SCENES.map((scene) => [scene.key, getPreviewEntitlement(scene.entitlementKey, planId)]),
  );
}

function firstString(...values) {
  return values.map((value) => String(value || "").trim()).find(Boolean) || "";
}

function listValues(value) {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => (typeof item === "string" ? item : firstString(item?.name, item?.title, item?.label, item?.degree)))
    .map((item) => String(item || "").trim())
    .filter(Boolean);
}

export function summarizeCvProfile(profile = {}, { dataMode = PREVIEW_DATA_MODE } = {}) {
  if (dataMode === PREVIEW_DATA_MODE) {
    return { ...PREVIEW_CV_PROFILE, dataLabel: PREVIEW_DATA_LABEL };
  }
  const recentExperience = Array.isArray(profile.recent_experience) ? profile.recent_experience : [];
  const educationItems = listValues(profile.education || profile.education_items || profile.education_history);
  const skills = listValues(profile.skills || profile.competencies || profile.core_competencies);
  const languages = listValues(profile.languages || profile.language_skills);
  return {
    recentRole: firstString(
      recentExperience[0]?.title,
      recentExperience[0]?.role_title,
      profile.role_title,
      profile.headline,
    ) || "Experience ready to review",
    experienceCount: recentExperience.length || (profile.experience ? 1 : 0),
    education: educationItems[0] || "Education ready to review",
    skills: skills.slice(0, 6),
    languages: languages.slice(0, 4),
    contactDetails: [profile.email, profile.phone, profile.linkedin_url].some((value) => String(value || "").trim())
      ? "Contact details found"
      : "No contact details found",
    dataLabel: "Extracted from your CV",
  };
}

export function normalizeCvProcessingStatus(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (["ready", "completed"].includes(normalized)) return "ready";
  if (["failed", "error", "timeout"].includes(normalized)) return "error";
  if (["uploaded", "queued", "processing", "reading", "uploading"].includes(normalized)) return "reading";
  return "idle";
}
