export function matchScore(value) {
  return typeof value === "number" && Number.isFinite(value) ? `${Math.round(value)}%` : "—";
}

export function matchLabel(match = {}) {
  if (match.state === "needs_profile") return "Complete your profile";
  if (match.state === "pending") return "Match being prepared";
  if (typeof match.score !== "number") return "Insufficient information";
  return match.label || "Profile match";
}

export const MATCH_DIMENSIONS = ["experience_level", "skill", "industry_experience"];
