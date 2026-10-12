export function billingMessage(error, fallback = "Payments are temporarily unavailable. Please try again later.") {
  const message = String(error?.message || error || "");
  if (/creem|product[_ ]?id|api[_ ]?key|configur|rollout|signature|customer[_ ]?id|provider|https?:\/\//i.test(message)) return fallback;
  return message || fallback;
}

export function billingFeatures(plans) {
  const paid = plans.find(plan => plan.plan_id === "runr_pro");
  const free = plans.find(plan => plan.plan_id === "free");
  return [
    { label: "AI Resume Customization", quota: "cv_exports_per_month" },
    { label: "AI Cover Letter", quota: "cv_exports_per_month" },
    { label: "Application Autofill", quota: "applications_per_month" },
    { label: "Referral Drafts", quota: "referral_drafts_per_month" },
  ].map(row => ({ ...row, paid: paid?.quotas?.[row.quota], free: free?.quotas?.[row.quota] }));
}
