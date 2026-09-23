/**
 * Provider-neutral field model.
 *
 * Field identity is derived from what a human would read ??? the label, the
 * surrounding section heading, ARIA text, the placeholder, the control type ???
 * never from a provider's numeric control ids. That rule is what lets one
 * inspector serve Greenhouse, Lever, Avature, and an employer-hosted portal
 * nobody has written an adapter for.
 */

export type FieldSensitivity = "normal" | "personal" | "sensitive" | "high_risk";

export type ApplicationControlType =
  | "text" | "textarea" | "email" | "tel" | "url" | "number"
  | "select" | "combobox" | "multiselect"
  | "radio" | "checkbox"
  | "date" | "month"
  | "file" | "custom" | "unknown";

export type FieldIntent =
  // Contact
  | "contact.title_prefix" | "contact.first_name" | "contact.last_name" | "contact.full_name"
  | "contact.email" | "contact.phone" | "contact.website" | "contact.linkedin"
  | "contact.github" | "contact.portfolio"
  // Location
  | "location.citizenship" | "location.residence_country" | "location.state"
  | "location.city" | "location.address" | "location.postal_code"
  // Profile
  | "profile.current_title" | "profile.current_company" | "profile.summary"
  | "profile.skills" | "profile.languages"
  // Repeated work experience
  | "experience.title" | "experience.company" | "experience.description"
  | "experience.location" | "experience.start_date" | "experience.end_date" | "experience.is_current"
  // Repeated education
  | "education.school" | "education.degree" | "education.major" | "education.description"
  | "education.location" | "education.start_date" | "education.end_date" | "education.is_current"
  // Documents
  | "document.cv" | "document.cover_letter" | "document.supporting"
  // Preferences
  | "preference.notification_language" | "preference.relocation"
  | "preference.notice_period" | "preference.salary" | "preference.start_date"
  // Legal and demographic
  | "legal.work_authorization" | "legal.sponsorship" | "legal.declaration" | "legal.terms"
  | "demographic.gender" | "demographic.race" | "demographic.veteran" | "demographic.disability"
  // Consent
  | "consent.data_sharing" | "consent.communications" | "consent.visibility"
  // Catch-alls
  | "question.free_text" | "question.select" | "question.boolean"
  | "assessment" | "captcha" | "credential.password" | "unknown";

export type ManualOnlyReason =
  | "final_submission" | "captcha" | "signature" | "legal_declaration" | "legal_terms"
  | "assessment" | "credential" | "cross_origin_frame" | "closed_shadow_root"
  | "unsupported_custom_control" | "demographic_disallowed" | "ambiguous_intent";

/**
 * How to find the control again.
 *
 * Carried verbatim from the DOM because the field `id` is normalised for
 * stability and cannot be reversed ??? a control with `id="firstName"` yields
 * `field-firstname`, which `getElementById` will not match.
 */
export interface FieldLocator {
  elementId?: string;
  name?: string;
  automationId?: string;
}

export interface DetectedApplicationField {
  id: string;
  locator: FieldLocator;
  intent: FieldIntent;
  label: string;
  controlType: ApplicationControlType;
  required: boolean;
  currentValue: string;
  options?: Array<{ label: string; value: string }>;
  sectionId?: string;
  repeatIndex?: number;
  sensitivity: FieldSensitivity;
  /** Human-readable notes on why this intent was chosen, for review and audit. */
  sourceEvidence: string[];
  confidence: number;
  manualReason?: ManualOnlyReason;
}

/**
 * Intent rules, evaluated in order. The first match wins, so more specific
 * patterns must precede more general ones ??? `contact.first_name` before any
 * rule that merely looks for "name".
 */
interface IntentRule {
  intent: FieldIntent;
  pattern: RegExp;
  sensitivity?: FieldSensitivity;
  /** Restricts the rule to a section, so `Start Date` resolves differently
   *  inside work experience than inside education. */
  section?: "experience" | "education";
  controlTypes?: ApplicationControlType[];
  manualReason?: ManualOnlyReason;
}

const INTENT_RULES: ReadonlyArray<IntentRule> = [
  // Manual-only controls first: these must never be filled regardless of label.
  { intent: "captcha", pattern: /captcha|recaptcha|hcaptcha|i am not a robot/u, manualReason: "captcha", sensitivity: "high_risk" },
  { intent: "credential.password", pattern: /^password|passwort|confirm password/u, manualReason: "credential", sensitivity: "high_risk" },
  { intent: "assessment", pattern: /assessment|coding test|skills test|aptitude/u, manualReason: "assessment", sensitivity: "high_risk" },
  { intent: "legal.declaration", pattern: /declaration|i declare|i certify|certify that|accuracy of|signature|sign here/u, manualReason: "legal_declaration", sensitivity: "high_risk" },
  { intent: "legal.terms", pattern: /terms and conditions|accept terms|privacy policy|data protection notice/u, manualReason: "legal_terms", sensitivity: "high_risk" },

  // Section-scoped date and boolean rules, before the generic ones.
  { intent: "experience.start_date", pattern: /start date|from date|von/u, section: "experience" },
  { intent: "experience.end_date", pattern: /end date|to date|bis/u, section: "experience" },
  { intent: "experience.is_current", pattern: /current position|currently work|present position/u, section: "experience" },
  { intent: "experience.title", pattern: /job title|position title|^title$|role/u, section: "experience" },
  { intent: "experience.company", pattern: /company|employer|organisation|organization/u, section: "experience" },
  { intent: "experience.description", pattern: /description|responsibilities|achievements/u, section: "experience" },
  { intent: "experience.location", pattern: /location|city/u, section: "experience" },

  { intent: "education.start_date", pattern: /start date|from date/u, section: "education" },
  { intent: "education.end_date", pattern: /end date|to date|graduation/u, section: "education" },
  { intent: "education.is_current", pattern: /current study|currently stud|present study/u, section: "education" },
  { intent: "education.school", pattern: /school|university|college|institution/u, section: "education" },
  { intent: "education.degree", pattern: /degree|qualification/u, section: "education" },
  { intent: "education.major", pattern: /major|field of study|subject|course/u, section: "education" },
  { intent: "education.description", pattern: /description/u, section: "education" },
  { intent: "education.location", pattern: /location|city/u, section: "education" },

  // Documents.
  { intent: "document.cv", pattern: /\b(cv|resume|r??sum??|lebenslauf|curriculum vitae)\b/u, controlTypes: ["file"] },
  { intent: "document.cover_letter", pattern: /cover letter|motivation letter|anschreiben/u, controlTypes: ["file"] },
  { intent: "document.supporting", pattern: /additional document|supporting document|certificate|attachment|other document/u, controlTypes: ["file"] },

  // Contact.
  { intent: "contact.title_prefix", pattern: /^title$|salutation|anrede/u, controlTypes: ["select", "combobox"] },
  { intent: "contact.first_name", pattern: /first name|given name|forename|vorname|preferred name/u },
  { intent: "contact.last_name", pattern: /last name|family name|surname|nachname/u },
  { intent: "contact.full_name", pattern: /full name|^name$|your name/u },
  { intent: "contact.email", pattern: /e-?mail/u },
  { intent: "contact.phone", pattern: /phone|mobile|telephone|telefon/u },
  { intent: "contact.linkedin", pattern: /linkedin/u },
  { intent: "contact.github", pattern: /github/u },
  { intent: "contact.portfolio", pattern: /portfolio/u },
  { intent: "contact.website", pattern: /website|personal site|homepage/u },

  // Location. Citizenship is asked as a proxy for work eligibility, so it is
  // treated as sensitive rather than ordinary contact data.
  { intent: "location.citizenship", pattern: /citizenship|nationality|staatsangeh/u, sensitivity: "sensitive" },
  { intent: "location.residence_country", pattern: /country.*residence|residence.*country|country\/region|^country$/u },
  { intent: "location.postal_code", pattern: /postal code|post code|zip code|plz/u },
  { intent: "location.state", pattern: /state|province|county|region|bundesland/u },
  { intent: "location.city", pattern: /^city$|town|ort/u },
  { intent: "location.address", pattern: /street address|address|adresse|strasse/u },

  // Profile.
  { intent: "profile.current_title", pattern: /current.*position title|last position title|current title|current role/u },
  { intent: "profile.current_company", pattern: /current employer|current company/u },
  { intent: "profile.skills", pattern: /skills|kenntnisse/u },
  { intent: "profile.languages", pattern: /languages|sprachen/u },
  { intent: "profile.summary", pattern: /summary|about you|profile summary|professional summary/u },

  // Preferences.
  { intent: "preference.notification_language", pattern: /notification language|preferred language|correspondence language/u },
  { intent: "preference.relocation", pattern: /relocat|willing to move/u },
  { intent: "preference.notice_period", pattern: /notice period|availability|available from/u },
  { intent: "preference.salary", pattern: /salary|compensation|expected pay|gehalt/u, sensitivity: "sensitive" },
  { intent: "preference.start_date", pattern: /start date|earliest start|available start/u },

  // Legal and demographic.
  { intent: "legal.work_authorization", pattern: /work authorization|authorized to work|right to work|work permit|eligible to work/u, sensitivity: "sensitive" },
  { intent: "legal.sponsorship", pattern: /sponsorship|visa|require.*sponsor/u, sensitivity: "sensitive" },
  { intent: "demographic.gender", pattern: /gender|geschlecht/u, sensitivity: "sensitive" },
  { intent: "demographic.race", pattern: /race|ethnicity|ethnic origin/u, sensitivity: "high_risk" },
  { intent: "demographic.veteran", pattern: /veteran|military service/u, sensitivity: "high_risk" },
  { intent: "demographic.disability", pattern: /disability|disabled|handicap|schwerbehind/u, sensitivity: "high_risk" },

  // Consent.
  { intent: "consent.data_sharing", pattern: /make my data accessible|share my (data|profile)|data accessible to|talent (pool|community)/u, sensitivity: "sensitive" },
  { intent: "consent.communications", pattern: /communications|newsletter|news|marketing|interested in .* news/u },
  { intent: "consent.visibility", pattern: /visibility as candidate|profile visibility|visible to recruiters/u },
];

/** Intents whose answers must never be auto-filled without explicit user action. */
const HIGH_RISK_INTENTS = new Set<FieldIntent>([
  "demographic.race", "demographic.veteran", "demographic.disability",
  "legal.declaration", "legal.terms", "assessment", "captcha", "credential.password",
]);

export function sensitivityFor(intent: FieldIntent): FieldSensitivity {
  if (HIGH_RISK_INTENTS.has(intent)) return "high_risk";
  const rule = INTENT_RULES.find((candidate) => candidate.intent === intent);
  if (rule?.sensitivity) return rule.sensitivity;
  if (intent.startsWith("demographic.") || intent.startsWith("legal.") || intent.startsWith("consent.")) {
    return "sensitive";
  }
  if (intent.startsWith("contact.") || intent.startsWith("location.")) return "personal";
  return "normal";
}

export function normalizeFieldLabel(value: string): string {
  return value
    .replace(/[???*]+/gu, " ")
    .replace(/\(\s*required\s*\)/giu, " ")
    .replace(/\s+/gu, " ")
    .trim()
    .toLowerCase();
}

export interface IntentClassification {
  intent: FieldIntent;
  confidence: number;
  sensitivity: FieldSensitivity;
  sourceEvidence: string[];
  manualReason?: ManualOnlyReason;
}

export interface IntentSignals {
  label: string;
  controlType: ApplicationControlType;
  /** Section the control sits in, when the form groups repeated blocks. */
  section?: "experience" | "education" | string;
  ariaLabel?: string;
  placeholder?: string;
  name?: string;
  autocomplete?: string;
  /** Nearest heading above the control, used to disambiguate repeated labels. */
  sectionHeading?: string;
}

/**
 * Chooses a field intent from human-readable signals.
 *
 * Confidence reflects how the match was reached: an explicit label match is
 * worth more than a match against a `name` attribute, and a control-type-only
 * fallback is worth least. Callers use it to decide what needs review.
 */
export function classifyFieldIntent(signals: IntentSignals): IntentClassification {
  const evidence: string[] = [];
  const label = normalizeFieldLabel(signals.label);
  const heading = normalizeFieldLabel(signals.sectionHeading || "");
  const section = signals.section ??
    (/work experience|employment history|berufserfahrung/u.test(heading) ? "experience"
      : /education|ausbildung|studium/u.test(heading) ? "education"
        : undefined);

  const secondary = normalizeFieldLabel(
    [signals.ariaLabel, signals.placeholder, signals.name, signals.autocomplete].filter(Boolean).join(" "),
  );

  for (const rule of INTENT_RULES) {
    if (rule.section && rule.section !== section) continue;
    if (rule.controlTypes && !rule.controlTypes.includes(signals.controlType)) continue;

    const labelMatch = label.length > 0 && rule.pattern.test(label);
    const secondaryMatch = !labelMatch && secondary.length > 0 && rule.pattern.test(secondary);
    if (!labelMatch && !secondaryMatch) continue;

    evidence.push(
      labelMatch
        ? `Label "${signals.label.trim()}" matched the ${rule.intent} rule.`
        : `Attributes matched the ${rule.intent} rule; the visible label did not.`,
    );
    if (rule.section) evidence.push(`Control sits in the ${rule.section} section.`);

    const confidence = labelMatch ? (rule.section ? 0.95 : 0.9) : 0.6;
    return {
      intent: rule.intent,
      confidence,
      sensitivity: rule.sensitivity ?? sensitivityFor(rule.intent),
      sourceEvidence: evidence,
      manualReason: rule.manualReason,
    };
  }

  // No rule matched. Fall back to a shape-based question intent so the field is
  // still offered for review rather than dropped silently.
  const fallback: FieldIntent =
    signals.controlType === "checkbox" || signals.controlType === "radio" ? "question.boolean"
      : signals.controlType === "select" || signals.controlType === "combobox" || signals.controlType === "multiselect"
        ? "question.select"
        : "question.free_text";

  return {
    intent: fallback,
    confidence: 0.3,
    sensitivity: "normal",
    sourceEvidence: [
      signals.label.trim()
        ? `No intent rule matched "${signals.label.trim()}"; classified by control shape.`
        : "Control has no readable label; classified by control shape.",
    ],
  };
}
