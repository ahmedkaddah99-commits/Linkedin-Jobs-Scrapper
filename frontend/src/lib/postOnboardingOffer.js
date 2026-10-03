export const POST_ONBOARDING_OFFER_SOURCE = "post_onboarding_jobs_ready";
export const PERSONAL_VALUE_NOTIFICATION_MODE = "personal_value";
export const POST_ONBOARDING_NOTIFICATION_DELAY_MS = 350;
export const POST_ONBOARDING_MODAL_DELAY_MS = 850;
export const POST_ONBOARDING_NOTIFICATION_DURATION_MS = 8000;

export const PREVIEW_PRO_PLANS = Object.freeze([
  Object.freeze({
    plan_id: "runr_pro",
    display_name: "Runr Pro",
    offers: Object.freeze([
      Object.freeze({ offer_id: "one_week", display_name: "1 week", price: 19.99, currency: "USD" }),
      Object.freeze({ offer_id: "one_month", display_name: "1 month", price: 39.99, currency: "USD" }),
      Object.freeze({ offer_id: "three_months", display_name: "3 months", price: 89.99, currency: "USD" }),
    ]),
  }),
]);

export function normalizeOfferPlanId(planId) {
  const normalized = String(planId || "").trim().toLowerCase();
  return ["runr_pro", "pro", "launch", "momentum", "scale", "business"].includes(normalized)
    ? "runr_pro"
    : "free";
}

export function isPaidPlan(planId) {
  return normalizeOfferPlanId(planId) === "runr_pro";
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
  const offers = Array.isArray(plan?.offers) ? plan.offers : [];
  if (offers.length) {
    return offers
      .map((offer) => `USD ${Number(offer.price || 0).toFixed(2)} / ${offer.display_name || "period"}`)
      .join(" · ");
  }
  const price = Number(plan?.price_eur);
  if (!Number.isFinite(price)) return "Price unavailable";
  return `EUR ${price.toLocaleString()} / month`;
}
