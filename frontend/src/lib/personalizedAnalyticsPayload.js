export function buildPersonalizedEventProperties(context = {}) {
  const properties = {
    route: context.route || (typeof window !== "undefined" ? window.location.pathname : ""),
    feature_key: context.featureKey,
    job_preview_id: context.jobPreviewId,
    filter_name: context.filterName,
    onboarding_step: context.onboardingStep,
    data_mode: context.dataMode || "synthetic",
  };
  if (context.sceneKey !== undefined) properties.scene_key = context.sceneKey;
  if (context.progression !== undefined) properties.progression = context.progression;
  if (context.extractionStatus !== undefined) properties.extraction_status = context.extractionStatus;
  if (context.showcaseSkipped !== undefined) properties.showcase_skipped = context.showcaseSkipped;
  if (context.notificationMode !== undefined) properties.notification_mode = context.notificationMode;
  if (context.selectedPlanId !== undefined) properties.selected_plan_id = context.selectedPlanId;
  if (context.offerSource !== undefined) properties.offer_source = context.offerSource;
  if (context.readyToNotificationMs !== undefined) properties.ready_to_notification_ms = context.readyToNotificationMs;
  if (context.notificationToModalMs !== undefined) properties.notification_to_modal_ms = context.notificationToModalMs;
  if (context.reducedMotion !== undefined) properties.reduced_motion = context.reducedMotion;
  if (context.offerOutcome !== undefined) properties.offer_outcome = context.offerOutcome;
  return properties;
}
