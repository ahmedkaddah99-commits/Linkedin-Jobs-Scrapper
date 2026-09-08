export const MATCH_VERSION_LABELS = Object.freeze({
  v1: "v1 · ATS-style",
  v2: "v2 · Semantic/evidence-aware",
});

export function selectMatchScore(match = {}, version = "v2") {
  const selected = version === "v1" ? match.v1 : match.v2;
  return selected && typeof selected === "object" ? selected : { score: null, status: "pending" };
}

export function buildEvidenceReview(match = {}) {
  const score = selectMatchScore(match, "v2");
  return {
    matched_keywords: Array.isArray(score.matched_keywords) ? score.matched_keywords : [],
    missing_keywords: Array.isArray(score.missing_keywords) ? score.missing_keywords : [],
    matched_requirements: Array.isArray(score.matched_requirements) ? score.matched_requirements : [],
    unproven_requirements: Array.isArray(score.unproven_requirements) ? score.unproven_requirements : [],
    apparent_non_matches: Array.isArray(score.apparent_non_matches) ? score.apparent_non_matches : [],
    matched_evidence: Array.isArray(score.matched_evidence) ? score.matched_evidence : [],
    missing_evidence: Array.isArray(score.missing_evidence) ? score.missing_evidence : [],
    v1_v2_difference: match.difference || { score_delta: null, summary: "Pending until both evaluators finish." },
  };
}

export function improveResumeEntitlement(job = {}) {
  const improve = job.improveResume && typeof job.improveResume === "object" ? job.improveResume : {};
  return {
    reviewAvailable: improve.review_available !== false,
    rewriteAvailable: improve.rewriting_available === true,
    tailoredDocumentsAvailable: improve.tailored_documents_available === true,
  };
}
