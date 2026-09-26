import type { DeclarativeAction } from "./declarative-actions";
import type { DetectedApplicationField } from "./field-intent";
import type { GenericInspection } from "./generic-inspector";

/**
 * Provider-neutral fill planning.
 *
 * Turns an inspection plus a candidate profile into declarative actions. This
 * module decides *what* should be written; it never touches the DOM itself ???
 * execution stays in the centralized executor, which is what keeps the
 * submission boundary enforceable in one place.
 */

export const PLANNER_VERSION = "1.0.0";

export interface WorkExperience {
  title?: string;
  company?: string;
  description?: string;
  location?: string;
  startDate?: string;
  endDate?: string;
  isCurrent?: boolean;
}

export interface EducationEntry {
  school?: string;
  degree?: string;
  major?: string;
  description?: string;
  location?: string;
  startDate?: string;
  endDate?: string;
  isCurrent?: boolean;
}

export interface CandidateProfile {
  contact: {
    titlePrefix?: string;
    firstName?: string;
    lastName?: string;
    fullName?: string;
    email?: string;
    phone?: string;
    website?: string;
    linkedin?: string;
    github?: string;
    portfolio?: string;
  };
  locations: {
    citizenship?: string;
    residenceCountry?: string;
    state?: string;
    city?: string;
    address?: string;
    postalCode?: string;
  };
  skills: string[];
  workExperiences: WorkExperience[];
  education: EducationEntry[];
  preferences: {
    gender?: string;
    workAuthorization?: string;
    sponsorship?: string;
    relocation?: string;
    currentTitle?: string;
    currentCompany?: string;
    summary?: string;
    noticePeriod?: string;
    notificationLanguage?: string;
  };
}

export interface FillPolicy {
  /** Leave a control alone when it already holds a value. */
  preserveExistingValues: boolean;
  /** Allow filling fields graded `sensitive` (citizenship, sponsorship, gender). */
  permitSensitiveAutofill: boolean;
  /** Field ids the user has explicitly asked Runr to overwrite. */
  replaceFieldIds?: string[];
}

export const DEFAULT_FILL_POLICY: FillPolicy = {
  preserveExistingValues: true,
  permitSensitiveAutofill: false,
};

export type PlannedDisposition = "fill" | "review" | "manual" | "skip";

export interface PlannedField {
  fieldId: string;
  intent: string;
  label: string;
  proposedValue: string;
  disposition: PlannedDisposition;
  reasons: string[];
}

export interface ApplicationFillPlan {
  actions: DeclarativeAction[];
  planned: PlannedField[];
  plannerVersion: string;
}

function normalize(value: string): string {
  return value.replace(/\s+/gu, " ").trim().toLowerCase();
}

/** Formats an ISO-ish date for the control type in front of us. */
function dateValueFor(raw: string, controlType: string): string | null {
  const match = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/u.exec(raw.trim());
  if (!match) return null;
  const [, year, month, day] = match;
  if (controlType === "month") return `${year}-${month}`;
  if (controlType === "date") return day ? `${year}-${month}-${day}` : `${year}-${month}-01`;
  return raw.trim();
}

/** Resolves a proposed value against a control's own option list. */
function optionValueFor(field: DetectedApplicationField, proposed: string): string | null {
  if (!field.options?.length) return proposed;
  const wanted = normalize(proposed);
  const exact = field.options.find((option) => option.value === proposed);
  if (exact) return exact.value;
  const byLabel = field.options.find((option) => normalize(option.label) === wanted);
  if (byLabel) return byLabel.value;
  const byValue = field.options.find((option) => normalize(option.value) === wanted);
  if (byValue) return byValue.value;
  // Yes/no questions are frequently phrased as boolean-ish options.
  const booleanish = /^(yes|true|no|false)$/u.test(wanted)
    ? field.options.find((option) => normalize(option.label).startsWith(wanted.startsWith("y") || wanted === "true" ? "yes" : "no"))
    : undefined;
  return booleanish?.value ?? null;
}

function experienceValue(entry: WorkExperience | undefined, intent: string): string | undefined {
  if (!entry) return undefined;
  switch (intent) {
    case "experience.title": return entry.title;
    case "experience.company": return entry.company;
    case "experience.description": return entry.description;
    case "experience.location": return entry.location;
    case "experience.start_date": return entry.startDate;
    case "experience.end_date": return entry.endDate;
    case "experience.is_current": return entry.isCurrent === undefined ? undefined : entry.isCurrent ? "Yes" : "No";
    default: return undefined;
  }
}

function educationValue(entry: EducationEntry | undefined, intent: string): string | undefined {
  if (!entry) return undefined;
  switch (intent) {
    case "education.school": return entry.school;
    case "education.degree": return entry.degree;
    case "education.major": return entry.major;
    case "education.description": return entry.description;
    case "education.location": return entry.location;
    case "education.start_date": return entry.startDate;
    case "education.end_date": return entry.endDate;
    case "education.is_current": return entry.isCurrent === undefined ? undefined : entry.isCurrent ? "Yes" : "No";
    default: return undefined;
  }
}

function profileValue(profile: CandidateProfile, field: DetectedApplicationField): string | undefined {
  const { intent, repeatIndex } = field;

  if (intent.startsWith("experience.")) {
    return experienceValue(profile.workExperiences[repeatIndex ?? 0], intent);
  }
  if (intent.startsWith("education.")) {
    return educationValue(profile.education[repeatIndex ?? 0], intent);
  }

  switch (intent) {
    case "contact.title_prefix": return profile.contact.titlePrefix;
    case "contact.first_name": return profile.contact.firstName;
    case "contact.last_name": return profile.contact.lastName;
    case "contact.full_name":
      return profile.contact.fullName ||
        [profile.contact.firstName, profile.contact.lastName].filter(Boolean).join(" ") || undefined;
    case "contact.email": return profile.contact.email;
    case "contact.phone": return profile.contact.phone;
    case "contact.website": return profile.contact.website;
    case "contact.linkedin": return profile.contact.linkedin;
    case "contact.github": return profile.contact.github;
    case "contact.portfolio": return profile.contact.portfolio;

    case "location.citizenship": return profile.locations.citizenship;
    case "location.residence_country": return profile.locations.residenceCountry;
    case "location.state": return profile.locations.state;
    case "location.city": return profile.locations.city;
    case "location.address": return profile.locations.address;
    case "location.postal_code": return profile.locations.postalCode;

    case "profile.current_title": return profile.preferences.currentTitle;
    case "profile.current_company": return profile.preferences.currentCompany;
    case "profile.summary": return profile.preferences.summary;
    case "profile.skills": return profile.skills.length ? profile.skills.join(", ") : undefined;

    case "preference.notification_language": return profile.preferences.notificationLanguage;
    case "preference.relocation": return profile.preferences.relocation;
    case "preference.notice_period": return profile.preferences.noticePeriod;

    case "legal.work_authorization": return profile.preferences.workAuthorization;
    case "legal.sponsorship": return profile.preferences.sponsorship;
    case "demographic.gender": return profile.preferences.gender;

    default: return undefined;
  }
}

function actionFor(field: DetectedApplicationField, value: string): DeclarativeAction | null {
  switch (field.controlType) {
    case "text": case "email": case "tel": case "url": case "number":
      return { type: "fill_text", fieldId: field.id, value };
    case "textarea":
      return { type: "fill_text", fieldId: field.id, value };
    case "select":
      return { type: "select", fieldId: field.id, value };
    case "date": case "month":
      return { type: "set_date", fieldId: field.id, value };
    case "checkbox":
      return { type: "set_checkbox", fieldId: field.id, checked: /^(yes|true|on|1)$/u.test(normalize(value)) };
    case "radio":
      return { type: "set_radio", fieldId: field.id, checked: true };
    default:
      return null;
  }
}

/**
 * Builds the fill plan.
 *
 * The ordering of the guards is the policy: manual-only controls are refused
 * before anything else is considered, existing values are protected next, and
 * only then is a value proposed. A field with no confident intent is routed to
 * review rather than filled on a guess.
 */
export function planApplicationFill(
  inspection: GenericInspection,
  profile: CandidateProfile,
  policy: FillPolicy = DEFAULT_FILL_POLICY,
): ApplicationFillPlan {
  const planned: PlannedField[] = [];
  const actions: DeclarativeAction[] = [];
  const replaceIds = new Set(policy.replaceFieldIds ?? []);

  for (const field of inspection.fields) {
    const base = { fieldId: field.id, intent: field.intent, label: field.label };

    if (field.manualReason) {
      planned.push({ ...base, proposedValue: "", disposition: "manual", reasons: [`This control needs you: ${field.manualReason.replace(/_/gu, " ")}.`] });
      continue;
    }

    if (field.sensitivity === "high_risk") {
      planned.push({ ...base, proposedValue: "", disposition: "manual", reasons: ["Runr never answers this category on your behalf."] });
      continue;
    }

    if (field.controlType === "file") {
      planned.push({ ...base, proposedValue: "", disposition: "skip", reasons: ["Documents are attached separately."] });
      continue;
    }

    if (field.currentValue.trim() && policy.preserveExistingValues && !replaceIds.has(field.id)) {
      planned.push({ ...base, proposedValue: field.currentValue, disposition: "skip", reasons: ["Your existing answer was kept."] });
      continue;
    }

    const raw = profileValue(profile, field);
    if (raw === undefined || raw === "") {
      planned.push({
        ...base,
        proposedValue: "",
        disposition: "review",
        reasons: [field.confidence < 0.5
          ? "Runr could not tell what this question is asking."
          : "Your profile has no answer for this yet."],
      });
      continue;
    }

    if (field.sensitivity === "sensitive" && !policy.permitSensitiveAutofill) {
      planned.push({ ...base, proposedValue: raw, disposition: "review", reasons: ["Confirm this answer before it is used."] });
      continue;
    }

    if (field.controlType === "multiselect" || field.controlType === "combobox") {
      // Skills-style controls take several values; country-style comboboxes take
      // one. Both are driven through the enhanced-selection executor, which
      // verifies each value by reading the control back.
      const values = field.intent === "profile.skills" || field.intent === "profile.languages"
        ? raw.split(",").map((item) => item.trim()).filter(Boolean)
        : [raw];
      if (values.length === 0) {
        planned.push({ ...base, proposedValue: raw, disposition: "review", reasons: ["No values to select."] });
        continue;
      }
      actions.push({ type: "select_enhanced_options", fieldId: field.id, values });
      planned.push({ ...base, proposedValue: values.join(", "), disposition: "fill", reasons: [] });
      continue;
    }

    let value = raw;
    if (field.controlType === "date" || field.controlType === "month") {
      const formatted = dateValueFor(raw, field.controlType);
      if (!formatted) {
        planned.push({ ...base, proposedValue: raw, disposition: "review", reasons: ["The stored date is not in a format this control accepts."] });
        continue;
      }
      value = formatted;
    }

    if (field.controlType === "select" || field.controlType === "radio") {
      const resolved = optionValueFor(field, raw);
      if (resolved === null) {
        planned.push({ ...base, proposedValue: raw, disposition: "review", reasons: ["None of the available options match your answer."] });
        continue;
      }
      value = resolved;
    }

    const action = actionFor(field, value);
    if (!action) {
      planned.push({ ...base, proposedValue: value, disposition: "review", reasons: ["Runr cannot operate this kind of control automatically."] });
      continue;
    }

    actions.push(action);
    planned.push({ ...base, proposedValue: value, disposition: "fill", reasons: [] });
  }

  return { actions, planned, plannerVersion: PLANNER_VERSION };
}

/** Counts for the panel's progress summary. */
export function planSummary(plan: ApplicationFillPlan): Record<PlannedDisposition, number> {
  return plan.planned.reduce(
    (counts, field) => ({ ...counts, [field.disposition]: counts[field.disposition] + 1 }),
    { fill: 0, review: 0, manual: 0, skip: 0 } as Record<PlannedDisposition, number>,
  );
}
