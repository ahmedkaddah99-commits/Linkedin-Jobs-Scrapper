import type { CandidateProfile } from "@runr/ats-core/generic-planner";
import { isProfilePackagePayload, type ProfilePackagePayload } from "@runr/extension-messages";

/**
 * Maps the extension-authenticated profile package onto the provider-neutral
 * CandidateProfile consumed by the generic planner.
 *
 * The backend response contains only facts already confirmed in Runr. This
 * module reshapes those facts; malformed or absent values stay absent so the
 * planner routes them to review instead of inventing an answer.
 */

function text(value: string): string {
  return value.trim();
}

function optional(value: string): string | undefined {
  const trimmed = text(value);
  return trimmed.length ? trimmed : undefined;
}

/** Split a `start - end` period into ISO year-month bounds. */
export function parsePeriod(period: string): { startDate?: string; endDate?: string; isCurrent?: boolean } {
  const raw = period.trim();
  if (!raw) return {};
  const [startRaw = "", endRaw = ""] = raw.split(/\s+[-–—]\s+/u);
  const isCurrent = /present|current|now|heute/iu.test(endRaw);
  return {
    startDate: isoMonth(startRaw),
    endDate: isCurrent ? undefined : isoMonth(endRaw),
    isCurrent: endRaw ? isCurrent : undefined,
  };
}

const MONTH_NAMES = [
  "january", "february", "march", "april", "may", "june",
  "july", "august", "september", "october", "november", "december",
];

export function isoMonth(value: string): string | undefined {
  const raw = value.trim();
  if (!raw) return undefined;

  const iso = /^(\d{4})-(\d{1,2})(?:-\d{1,2})?$/u.exec(raw);
  if (iso) return `${iso[1]}-${String(Number(iso[2])).padStart(2, "0")}`;

  const named = /^([A-Za-z]{3,})\s+(\d{4})$/u.exec(raw);
  if (named) {
    const index = MONTH_NAMES.findIndex((month) => month.startsWith(named[1]!.toLowerCase()));
    if (index >= 0) return `${named[2]}-${String(index + 1).padStart(2, "0")}`;
  }

  const yearOnly = /^(\d{4})$/u.exec(raw);
  if (yearOnly) return `${yearOnly[1]}-01`;

  return undefined;
}

export function toCandidateProfile(payload: unknown): CandidateProfile | null {
  if (!isProfilePackagePayload(payload)) return null;
  const record: ProfilePackagePayload = payload;
  const candidate = record.candidate;

  const answerFor = (intent: string): string | undefined =>
    optional(record.answers.find((answer) => text(answer.field_intent) === intent)?.proposed_value ?? "");

  const workExperiences = record.experiences
    .map((entry) => {
      const description = entry.bullets
        .map((bullet) => text(bullet.approved_text))
        .filter(Boolean)
        .join("\n");
      return {
        title: optional(entry.role_title),
        company: optional(entry.company),
        location: optional(entry.location),
        description: description || undefined,
        ...parsePeriod(entry.period),
      };
    })
    .filter((entry) => entry.title || entry.company);

  const education = record.education
    .map((entry) => ({
      school: optional(entry.institution),
      degree: optional(entry.degree),
      ...parsePeriod(entry.period),
    }))
    .filter((entry) => entry.school || entry.degree);

  return {
    contact: {
      firstName: optional(candidate.first_name),
      lastName: optional(candidate.last_name),
      fullName: optional(candidate.full_name),
      email: optional(candidate.email),
      phone: optional(candidate.phone),
      website: answerFor("candidate.website"),
      linkedin: answerFor("candidate.linkedin_url"),
      github: answerFor("candidate.github_url"),
      portfolio: answerFor("candidate.portfolio_url"),
    },
    locations: {
      citizenship: answerFor("candidate.citizenship"),
      residenceCountry: answerFor("candidate.country"),
      state: answerFor("candidate.state"),
      city: answerFor("candidate.city") ?? answerFor("candidate.location"),
      address: answerFor("candidate.address"),
      postalCode: answerFor("candidate.postal_code"),
    },
    skills: record.skills.map((item) => text(item.value)).filter(Boolean),
    workExperiences,
    education,
    preferences: {
      gender: answerFor("candidate.gender"),
      workAuthorization: answerFor("application.work_authorization"),
      sponsorship: answerFor("application.sponsorship"),
      relocation: answerFor("application.relocation"),
      currentTitle: answerFor("candidate.current_title"),
      currentCompany: answerFor("candidate.current_company"),
      summary: answerFor("candidate.professional_summary"),
      noticePeriod: answerFor("application.notice_period"),
      notificationLanguage: answerFor("candidate.languages"),
    },
  };
}
