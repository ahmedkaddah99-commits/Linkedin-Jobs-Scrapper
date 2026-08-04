export const POST_ONBOARDING_OFFER_SOURCE = "post_onboarding_jobs_ready";
export const PERSONAL_VALUE_NOTIFICATION_MODE = "personal_value";
export const POST_ONBOARDING_NOTIFICATION_DELAY_MS = 350;
export const POST_ONBOARDING_MODAL_DELAY_MS = 850;
export const POST_ONBOARDING_NOTIFICATION_DURATION_MS = 8000;

// Mirrors the current backend billing catalog for the synthetic preview.
// A live /billing/plans response replaces these values when available.
export const PREVIEW_PRO_PLANS = Object.freeze([
  Object.freeze({ plan_id: "launch", display_name: "Launch", price_eur: 15 }),
  Object.freeze({ plan_id: "momentum", display_name: "Momentum", price_eur: 25 }),
  Object.freeze({ plan_id: "scale", display_name: "Scale", price_eur: 79 }),
]);

export function isPaidPlan(planId) {
  return !["", "none", "free"].includes(String(planId || "").trim().toLowerCase());
}

export function getPersonalValueSummary(summary, dataMode) {
  const totalFound = Number(summary?.totalFound || 0);
  const strongMatches = Number(summary?.strongMatches || 0);
  const hiddenJobs = Number(summary?.hiddenJobs || 0);
  const preview = String(dataMode || summary?.dataMode || "synthetic") !== "real";
  return {
    headline: `Your first search found ${totalFound.toLocaleString()} jobs, including ${strongMatches} strong matches.`,
    supporting: `Runr separated ${hiddenJobs.toLocaleString()} jobs that may not fit your eligibility preferences.`,
    isPreview: preview,
  };
}

export function getNotificationCopy(summary, dataMode) {
  const value = getPersonalValueSummary(summary, dataMode);
  return {
    title: "Your personalized job search is ready",
    supporting: `${Number(summary?.totalFound || 0).toLocaleString()} jobs found · ${Number(summary?.hiddenJobs || 0).toLocaleString()} unsuitable jobs separated`,
    previewLabel: value.isPreview ? "Preview data" : "",
    mode: PERSONAL_VALUE_NOTIFICATION_MODE,
  };
}

export function getOfferEligibility({ onboardingState, offerState, planId, featureEnabled = true }) {
  if (!featureEnabled || !onboardingState?.completed || !offerState?.eligible) return false;
  if (offerState.offerShown || offerState.offerDismissed || offerState.upgradeCtaSelected) return false;
  return !isPaidPlan(planId);
}

export function getPlanPriceLabel(plan) {
  const price = Number(plan?.price_eur);
  if (!Number.isFinite(price)) return "Price unavailable";
  return `€${price.toLocaleString()} / month`;
}
