export function buildPersonalizedEventProperties(context = {}) {
  return {
    route: context.route || (typeof window !== "undefined" ? window.location.pathname : ""),
    feature_key: context.featureKey,
    job_preview_id: context.jobPreviewId,
    filter_name: context.filterName,
    onboarding_step: context.onboardingStep,
    data_mode: "synthetic",
  };
}
