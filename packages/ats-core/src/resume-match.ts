import type { CandidateProfile } from "./generic-planner";

/**
 * Explainable resume/job keyword match.
 *
 * The score is deliberately simple and fully inspectable: every point traces to
 * a keyword the user can see in the matched or missing list. Nothing is learned,
 * weighted opaquely, or rounded into a number whose derivation cannot be shown.
 */

export const RESUME_MATCH_ALGORITHM_VERSION = "1.0.0";

export interface ResumeMatchEvidence {
  keyword: string;
  source: "resume" | "profile" | "job";
  confidence: number;
}

export interface ResumeMatch {
  score: number;
  algorithmVersion: string;
  matchedKeywords: string[];
  missingKeywords: string[];
  evidence: ResumeMatchEvidence[];
  explanation: string;
}

/** Terms too common to distinguish one posting from another. */
const STOP_WORDS = new Set([
  "and", "the", "for", "with", "you", "your", "our", "are", "will", "that", "this", "have", "has", "from",
  "not", "job", "role", "team", "work", "working", "years", "year", "experience", "including", "ability",
  "strong", "excellent", "good", "new", "using", "use", "used", "well", "able", "must", "should", "who",
  "what", "when", "where", "how", "all", "any", "can", "may", "more", "most", "other", "such", "than",
  "them", "they", "their", "there", "these", "those", "into", "over", "under", "about", "across", "within",
  "und", "der", "die", "das", "ein", "eine", "wir", "auf", "den", "des", "mit", "als", "fur",
]);

/**
 * Synonyms folded onto one canonical term so a resume saying "k8s" scores
 * against a posting saying "kubernetes".
 */
const SYNONYMS: Readonly<Record<string, string>> = {
  k8s: "kubernetes",
  js: "javascript",
  ts: "typescript",
  postgres: "postgresql",
  "node.js": "nodejs",
  node: "nodejs",
  golang: "go",
  ml: "machine-learning",
  ai: "artificial-intelligence",
  cicd: "ci/cd",
  "ci-cd": "ci/cd",
  gcp: "google-cloud",
  aws: "amazon-web-services",
};

export function canonicalKeyword(value: string): string {
  const token = value.toLowerCase().trim().replace(/^[-./]+|[-./]+$/gu, "");
  return SYNONYMS[token] ?? token;
}

export function tokenizeForMatch(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9+#./ -]/gu, " ")
    .split(/\s+/u)
    .map(canonicalKeyword)
    .filter((token) => token.length >= 2 && token.length <= 32 && !STOP_WORDS.has(token) && !/^\d+$/u.test(token));
}

/**
 * Picks the job keywords worth scoring against.
 *
 * Frequency is used only to rank, never as a weight in the score: a term
 * repeated ten times still counts once, so a posting cannot inflate its own
 * match by repetition.
 */
export function jobKeywords(description: string, limit = 20): string[] {
  const counts = new Map<string, number>();
  for (const token of tokenizeForMatch(description)) {
    counts.set(token, (counts.get(token) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .slice(0, limit)
    .map(([token]) => token);
}

function profileCorpus(profile: CandidateProfile): string {
  return [
    profile.skills.join(" "),
    profile.preferences.summary ?? "",
    profile.preferences.currentTitle ?? "",
    ...profile.workExperiences.flatMap((entry) => [entry.title ?? "", entry.company ?? "", entry.description ?? ""]),
    ...profile.education.flatMap((entry) => [entry.degree ?? "", entry.major ?? "", entry.school ?? ""]),
  ].join(" ");
}

/**
 * Scores the candidate against a posting.
 *
 * Score is the share of the job's distinguishing keywords the candidate can
 * evidence, expressed 0-100. Resume text is preferred evidence over structured
 * profile fields, and the difference is visible in the evidence list.
 */
export function computeResumeMatch(
  jobDescription: string,
  profile: CandidateProfile,
  resumeText = "",
): ResumeMatch {
  const keywords = jobKeywords(jobDescription);
  if (keywords.length === 0) {
    return {
      score: 0,
      algorithmVersion: RESUME_MATCH_ALGORITHM_VERSION,
      matchedKeywords: [],
      missingKeywords: [],
      evidence: [],
      explanation: "This posting has no description text to match against.",
    };
  }

  const resumeTokens = new Set(tokenizeForMatch(resumeText));
  const profileTokens = new Set(tokenizeForMatch(profileCorpus(profile)));

  const matched: string[] = [];
  const missing: string[] = [];
  const evidence: ResumeMatchEvidence[] = [];

  for (const keyword of keywords) {
    if (resumeTokens.has(keyword)) {
      matched.push(keyword);
      evidence.push({ keyword, source: "resume", confidence: 1 });
    } else if (profileTokens.has(keyword)) {
      matched.push(keyword);
      evidence.push({ keyword, source: "profile", confidence: 0.8 });
    } else {
      missing.push(keyword);
      evidence.push({ keyword, source: "job", confidence: 0 });
    }
  }

  const score = Math.round((matched.length / keywords.length) * 100);
  return {
    score,
    algorithmVersion: RESUME_MATCH_ALGORITHM_VERSION,
    matchedKeywords: matched,
    missingKeywords: missing,
    evidence,
    explanation:
      `Runr took the ${keywords.length} keywords that distinguish this posting and checked each against your ` +
      `resume and profile. You can evidence ${matched.length}, so the score is ` +
      `${matched.length} of ${keywords.length}, or ${score}%. Repeating a keyword does not raise the score.`,
  };
}

export function matchVerdict(score: number): "Low" | "Fair" | "Strong" {
  if (score < 40) return "Low";
  if (score < 70) return "Fair";
  return "Strong";
}

export interface ProfileCompleteness {
  requiredTotal: number;
  completed: number;
  missing: Array<{ fieldIntent: string; label: string; reason: string }>;
  sensitivePending: string[];
  stale: string[];
}

const REQUIRED_PROFILE_FIELDS: ReadonlyArray<{ intent: string; label: string; read: (profile: CandidateProfile) => string | undefined }> = [
  { intent: "contact.first_name", label: "First name", read: (p) => p.contact.firstName },
  { intent: "contact.last_name", label: "Last name", read: (p) => p.contact.lastName },
  { intent: "contact.email", label: "Email", read: (p) => p.contact.email },
  { intent: "contact.phone", label: "Phone number", read: (p) => p.contact.phone },
  { intent: "location.city", label: "City", read: (p) => p.locations.city },
  { intent: "location.residence_country", label: "Country of residence", read: (p) => p.locations.residenceCountry },
  { intent: "location.postal_code", label: "Postal code", read: (p) => p.locations.postalCode },
  { intent: "profile.current_title", label: "Current or last job title", read: (p) => p.preferences.currentTitle },
];

/**
 * Reports what is missing, not a percentage.
 *
 * The panel shows a count and links only to the gaps, so a candidate missing two
 * fields is never sent through a full profile wizard.
 */
export function profileCompleteness(profile: CandidateProfile): ProfileCompleteness {
  const missing = REQUIRED_PROFILE_FIELDS
    .filter((field) => !field.read(profile)?.trim())
    .map((field) => ({
      fieldIntent: field.intent,
      label: field.label,
      reason: "Applications ask for this and Runr has no confirmed answer.",
    }));

  if (profile.workExperiences.length === 0) {
    missing.push({
      fieldIntent: "experience.title",
      label: "Work experience",
      reason: "Applications with an experience section cannot be filled without it.",
    });
  }

  const sensitivePending = [
    !profile.preferences.workAuthorization ? "Work authorization" : "",
    !profile.preferences.sponsorship ? "Visa sponsorship" : "",
  ].filter(Boolean);

  const requiredTotal = REQUIRED_PROFILE_FIELDS.length + 1;
  return {
    requiredTotal,
    completed: requiredTotal - missing.length,
    missing,
    sensitivePending,
    stale: [],
  };
}
