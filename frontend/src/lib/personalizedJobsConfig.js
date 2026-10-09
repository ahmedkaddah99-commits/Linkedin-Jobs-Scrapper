export const PERSONALIZED_JOBS_FLAG = "VITE_PERSONALIZED_JOBS_EXPERIENCE";
export const PERSONALIZED_JOBS_DATA_MODE = "VITE_PERSONALIZED_JOBS_DATA_MODE";
export const RETIRE_LEGACY_JOBS_NAV = "VITE_REPLACE_LEGACY_JOBS_NAV";
export const PREVIEW_DATA_MODE = "synthetic";

export function resolvePersonalizedJobsDataMode(env = {}) {
  return String(env[PERSONALIZED_JOBS_DATA_MODE] || PREVIEW_DATA_MODE).trim().toLowerCase() === "real"
    ? "real"
    : PREVIEW_DATA_MODE;
}

export function isPersonalizedJobsExperienceEnabled(env = {}) {
  const value = String(env[PERSONALIZED_JOBS_FLAG] || "").trim().toLowerCase();
  return value === "1" || value === "true" || value === "on";
}

export function shouldRetireLegacyJobsNavigation(env = {}) {
  const value = String(env[RETIRE_LEGACY_JOBS_NAV] || "").trim().toLowerCase();
  const enabled = value === "1" || value === "true" || value === "on";
  return enabled && resolvePersonalizedJobsDataMode(env) === "real";
}

export const personalizedJobsDataMode = resolvePersonalizedJobsDataMode(
  typeof import.meta !== "undefined" ? import.meta.env || {} : {},
);

export const personalizedJobsExperienceEnabled = isPersonalizedJobsExperienceEnabled(
  typeof import.meta !== "undefined" ? import.meta.env || {} : {},
);

export const retireLegacyJobsNavigation = shouldRetireLegacyJobsNavigation(
  typeof import.meta !== "undefined" ? import.meta.env || {} : {},
);
