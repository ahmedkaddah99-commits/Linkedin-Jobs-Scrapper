import { logEvent } from "./analytics";

export function logPersonalizedEvent(eventName, context = {}) {
  logEvent(eventName, {
    route: context.route || window.location.pathname,
    feature_key: context.featureKey,
    job_preview_id: context.jobPreviewId,
    filter_name: context.filterName,
    onboarding_step: context.onboardingStep,
    data_mode: "synthetic",
  });
}

