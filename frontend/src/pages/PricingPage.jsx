import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { getApiErrorMessage } from "../lib/api";

const quotaLabels = {
  runs_per_month: "Runs / month",
  applications_per_month: "Applications / month",
  cv_exports_per_month: "CV exports / month",
  referral_drafts_per_month: "Referral drafts / month",
  runner_credits_per_month: "Runner credits / month",
  workspaces: "Workspaces",
};

function formatQuotaValue(value) {
  return Number(value) === -1 ? "Unlimited" : String(value ?? "0");
}

function formatUsageLimit(limit) {
  return Number(limit) === -1 ? "Unlimited" : String(limit ?? 0);
}

function formatDateTime(value) {
  const normalizedValue = String(value || "").trim();
  if (!normalizedValue) return "Not available";
  const parsed = new Date(normalizedValue);
  if (Number.isNaN(parsed.getTime())) return normalizedValue;
  return parsed.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function normalizeBillingPlanId(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return ["launch", "momentum", "scale", "pro", "business", "runr_pro"].includes(normalized)
    ? "runr_pro"
    : "free";
}

function buildFeatureRows(plans) {
  const keys = Object.keys(
    plans.reduce((accumulator, plan) => ({ ...accumulator, ...(plan.quotas || {}) }), {}),
  );
  return keys.map((quotaType) => ({
    quotaType,
    label: quotaLabels[quotaType] || quotaType,
  }));
}

export default function PricingPage() {
  const { request, refreshSession, user } = useSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const [actionState, setActionState] = useState({ loadingPlanId: "", managing: false, error: "" });
  const [selectedOfferId, setSelectedOfferId] = useState("one_month");
  const [checkoutConfirmationState, setCheckoutConfirmationState] = useState("idle");
  const [checkoutConfirmationError, setCheckoutConfirmationError] = useState("");
  const [promoCode, setPromoCode] = useState("");
  const {
    data: plansPayload,
    loading: plansLoading,
    error: plansError,
    refresh: refreshPlans,
  } = useApiResource(() => request("/billing/plans"), [request], {
    cacheKey: "billing:plans",
    staleMs: Infinity,
    backgroundRefresh: false,
  });
  const {
    data: subscriptionPayload,
    loading: subscriptionLoading,
    error: subscriptionError,
    refresh: refreshSubscription,
  } = useApiResource(() => request("/billing/subscription"), [request], {
    cacheKey: "billing:subscription",
    staleMs: 300000,
    backgroundRefresh: true,
  });

  const plans = Array.isArray(plansPayload?.plans) ? plansPayload.plans : [];
  const currentPlanId = normalizeBillingPlanId(subscriptionPayload?.plan_id || user?.plan_id);
  const checkoutState = String(searchParams.get("checkout") || "").trim();
  const checkoutPlanId = String(searchParams.get("plan_id") || "").trim();
  const checkoutOfferId = String(searchParams.get("offer_id") || "one_month").trim();
  const checkoutQueryString = searchParams.toString();
  const hasSignedCheckoutReturn = checkoutQueryString.includes("signature=");
  const checkoutPlan = plans.find((plan) => String(plan.plan_id || "").trim() === checkoutPlanId);
  const currentPlan = plans.find((plan) => String(plan.plan_id || "").trim() === currentPlanId);
  const currentPlanName = String(currentPlan?.display_name || subscriptionPayload?.plan?.display_name || currentPlanId).trim();
  const checkoutOffer = checkoutPlan?.offers?.find((offer) => String(offer.offer_id || "") === checkoutOfferId);
  const checkoutPlanName = String(
    checkoutPlan && checkoutOffer
      ? `${checkoutPlan.display_name} · ${checkoutOffer.display_name}`
      : checkoutPlan?.display_name || checkoutPlanId || currentPlanName,
  ).trim();
  const showCheckoutSuccess = checkoutState === "success";
  const checkoutConfirmed = showCheckoutSuccess && checkoutPlanId && currentPlanId === checkoutPlanId;
  const checkoutSynced = checkoutConfirmed || checkoutConfirmationState === "confirmed";
  const subscriptionDetails = subscriptionPayload?.subscription || {};
  const subscriptionStatus = String(subscriptionDetails.status || (currentPlanId === "free" ? "inactive" : "active")).trim();
  const displayedSubscriptionStatus = checkoutSynced
    ? subscriptionStatus
    : hasSignedCheckoutReturn
      ? "confirming"
      : "sync pending";
  const usageQuotas = subscriptionPayload?.usage?.quotas || {};
  const usageSummaryRows = [
    "runner_credits_per_month",
    "runs_per_month",
    "applications_per_month",
    "workspaces",
  ].map((quotaType) => ({
    quotaType,
    label: quotaLabels[quotaType] || quotaType,
    quota: usageQuotas[quotaType] || { used: 0, limit: 0 },
  }));
  const featureRows = buildFeatureRows(plans);

  useEffect(() => {
    if (!showCheckoutSuccess) {
      setCheckoutConfirmationState("idle");
      setCheckoutConfirmationError("");
      return;
    }
    let cancelled = false;
    const wait = (milliseconds) => new Promise((resolve) => {
      window.setTimeout(resolve, milliseconds);
    });

    async function confirmCheckout() {
      setCheckoutConfirmationError("");
      setCheckoutConfirmationState(hasSignedCheckoutReturn ? "confirming" : "awaiting_webhook");
      if (hasSignedCheckoutReturn) {
        try {
          await request("/billing/checkout/confirm", {
            method: "POST",
            body: { query_string: checkoutQueryString },
          });
        } catch (requestError) {
          if (!cancelled) {
            setCheckoutConfirmationError(
              getApiErrorMessage(requestError, "Runr could not confirm the checkout return yet."),
            );
            setCheckoutConfirmationState("awaiting_webhook");
          }
        }
      }
      for (let attempt = 0; attempt < 10; attempt += 1) {
        const payload = await refreshSubscription().catch(() => null);
        const nextPlanId = normalizeBillingPlanId(payload?.plan_id);
        if (checkoutPlanId && nextPlanId === checkoutPlanId) {
          await refreshSession().catch(() => undefined);
          if (!cancelled) {
            setCheckoutConfirmationState("confirmed");
          }
          return;
        }
        await wait(2000);
      }
      if (!cancelled) {
        setCheckoutConfirmationState("awaiting_webhook");
      }
    }

    confirmCheckout();
    return () => {
      cancelled = true;
    };
  }, [
    checkoutPlanId,
    checkoutQueryString,
    hasSignedCheckoutReturn,
    refreshSession,
    refreshSubscription,
    request,
    showCheckoutSuccess,
  ]);

  async function handleUpgrade(planId, offerId = "one_month") {
    setActionState({ loadingPlanId: planId, managing: false, error: "" });
    try {
      const payload = await request("/billing/checkout", {
        method: "POST",
        body: {
          plan_id: planId,
          offer_id: offerId,
          promo_code: promoCode.trim().toUpperCase(),
          source_page: "/pricing",
        },
      });
      window.location.assign(payload.checkout_url);
    } catch (requestError) {
      setActionState({
        loadingPlanId: "",
        managing: false,
        error: getApiErrorMessage(requestError, "Unable to start checkout."),
      });
    }
  }

  async function handleManageSubscription() {
    setActionState({ loadingPlanId: "", managing: true, error: "" });
    try {
      const payload = await request("/billing/portal", {
        method: "POST",
        body: {},
      });
      window.location.assign(payload.portal_url);
    } catch (requestError) {
      setActionState({
        loadingPlanId: "",
        managing: false,
        error: getApiErrorMessage(requestError, "Unable to open the billing portal."),
      });
    }
  }

  async function handleRefreshBilling() {
    await Promise.all([
      refreshSubscription().catch(() => undefined),
      refreshSession().catch(() => undefined),
    ]);
  }

  const isLoading = plansLoading || subscriptionLoading;
  const combinedError = actionState.error || plansError || subscriptionError;

  return (
    <div className="space-y-8">
      <section className="rounded-[2rem] border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-soft md:p-10">
        <p className="text-xs font-bold uppercase tracking-[0.28em] text-primary">Pricing</p>
        <div className="mt-4 flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="font-headline text-[2.35rem] font-extrabold leading-tight tracking-tight text-on-surface">
              Pick the plan that fits your job-search operating rhythm.
            </h1>
          </div>
          <Link
            className="inline-flex items-center gap-2 rounded-full border border-outline-variant/20 bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
            to="/settings"
          >
            <span className="material-symbols-outlined text-[18px]">monitoring</span>
            Account usage
          </Link>
        </div>
      </section>

      {combinedError ? (
        <div className="rounded-2xl border border-error/20 bg-error-container px-5 py-4 text-sm text-on-error-container">
          {combinedError}
        </div>
      ) : null}

      {showCheckoutSuccess ? (
        <section className="rounded-[1.5rem] border border-primary/20 bg-primary/10 p-5 text-primary">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div className="flex gap-3">
              <span className="material-symbols-outlined text-[24px]">check_circle</span>
              <div>
                <h2 className="font-headline text-xl font-bold tracking-tight">Payment successful</h2>
                <p className="mt-1 text-sm leading-6">
                  {checkoutConfirmed || checkoutConfirmationState === "confirmed"
                    ? `You are subscribed to ${checkoutPlanName}.`
                    : checkoutConfirmationState === "awaiting_webhook"
                      ? `Payment received. Waiting for billing sync for ${checkoutPlanName}.`
                      : subscriptionLoading
                    ? `Confirming your ${checkoutPlanName} subscription...`
                    : `Payment received. Confirming your ${checkoutPlanName} subscription...`}
                </p>
                {checkoutConfirmationError ? (
                  <p className="mt-1 text-xs leading-5 text-primary/80">{checkoutConfirmationError}</p>
                ) : null}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                className="inline-flex items-center justify-center gap-2 rounded-full border border-primary/20 bg-surface-container-lowest px-4 py-2 text-sm font-semibold text-primary transition-colors hover:bg-surface-container-low"
                onClick={handleRefreshBilling}
                type="button"
              >
                <span className="material-symbols-outlined text-[18px]">refresh</span>
                Refresh
              </button>
              <button
                className="inline-flex items-center justify-center gap-2 rounded-full border border-primary/20 bg-surface-container-lowest px-4 py-2 text-sm font-semibold text-primary transition-colors hover:bg-surface-container-low"
                onClick={() => setSearchParams({})}
                type="button"
              >
                <span className="material-symbols-outlined text-[18px]">close</span>
                Dismiss
              </button>
            </div>
          </div>
          <div className="mt-5 grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-xl border border-primary/15 bg-surface-container-lowest p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-on-surface-variant">Plan</p>
              <p className="mt-2 font-headline text-lg font-bold text-on-surface">{checkoutSynced ? currentPlanName : checkoutPlanName}</p>
            </div>
            <div className="rounded-xl border border-primary/15 bg-surface-container-lowest p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-on-surface-variant">Status</p>
              <p className="mt-2 font-semibold capitalize text-on-surface">{displayedSubscriptionStatus.replace("_", " ")}</p>
            </div>
            <div className="rounded-xl border border-primary/15 bg-surface-container-lowest p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-on-surface-variant">Period start</p>
              <p className="mt-2 font-semibold text-on-surface">
                {checkoutSynced ? formatDateTime(subscriptionDetails.current_period_start) : "Sync pending"}
              </p>
            </div>
            <div className="rounded-xl border border-primary/15 bg-surface-container-lowest p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-on-surface-variant">Renews / ends</p>
              <p className="mt-2 font-semibold text-on-surface">
                {checkoutSynced ? formatDateTime(subscriptionDetails.current_period_end) : "Sync pending"}
              </p>
            </div>
          </div>
          <div className="mt-3 grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
            {usageSummaryRows.map(({ quotaType, label, quota }) => (
              <div className="rounded-xl border border-primary/15 bg-surface-container-lowest p-4" key={quotaType}>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-on-surface-variant">{label}</p>
                <p className="mt-2 font-semibold text-on-surface">
                  {checkoutSynced ? `${Number(quota.used || 0)} / ${formatUsageLimit(quota.limit)}` : "Sync pending"}
                </p>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="rounded-[1.5rem] border border-outline-variant/20 bg-surface-container-lowest p-5 shadow-soft">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-sm font-semibold text-on-surface">Promo code</p>
            <p className="mt-1 text-sm text-on-surface-variant">
              If you have a code, add it here and it will be prefilled in checkout.
            </p>
          </div>
          <div className="w-full md:max-w-sm">
            <input
              className="w-full rounded-full border border-outline-variant/20 bg-surface-container-low px-4 py-3 font-mono uppercase text-on-surface outline-none transition-colors focus:border-primary/40"
              onChange={(event) => setPromoCode(event.target.value.toUpperCase())}
              placeholder="SUMMER10"
              type="text"
              value={promoCode}
            />
          </div>
        </div>
      </section>

      {isLoading ? (
        <div className="grid gap-6 lg:grid-cols-2">
          {Array.from({ length: 2 }).map((_, index) => (
            <div
              className="h-[20rem] animate-pulse rounded-[2rem] border border-outline-variant/20 bg-surface-container-low"
              key={`pricing-skeleton-${index + 1}`}
            />
          ))}
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          {plans.map((plan) => {
            const planId = String(plan.plan_id || "").trim();
            const isCurrentPlan = planId === currentPlanId;
            const isPaidPlan = planId === "runr_pro";
            const planQuotas = plan.quotas || {};
            const offers = Array.isArray(plan.offers) ? plan.offers : [];
            const activeOfferId = offers.some((offer) => String(offer.offer_id || "") === selectedOfferId)
              ? selectedOfferId
              : String(offers[0]?.offer_id || "one_month");
            const activeOffer = offers.find((offer) => String(offer.offer_id || "") === activeOfferId);
            return (
              <section
                className={[
                  "relative overflow-hidden rounded-[2rem] border p-7 shadow-soft transition-transform",
                  isCurrentPlan
                    ? "border-primary/30 bg-surface-container-lowest"
                    : "border-outline-variant/20 bg-surface-container-lowest",
                ].join(" ")}
                key={planId}
              >
                <div className="absolute inset-x-0 top-0 h-28 bg-[linear-gradient(135deg,rgba(var(--color-primary),0.14),transparent_70%)]" />
                <div className="relative z-10">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-on-surface">{plan.display_name}</p>
                      <div className="mt-3 flex items-end gap-2">
                        <span className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">
                          {activeOffer ? `$${Number(activeOffer.price || 0).toFixed(2)}` : "$0.00"}
                        </span>
                        <span className="pb-1 text-sm text-on-surface-variant">
                          {activeOffer?.billing_type === "onetime" ? "total" : "every period"}
                        </span>
                      </div>
                    </div>
                    {isCurrentPlan ? (
                      <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-bold uppercase tracking-[0.2em] text-primary">
                        Current
                      </span>
                    ) : null}
                  </div>

                  <div className="mt-6 space-y-3">
                    {featureRows.map((row) => (
                      <div className="flex items-center justify-between gap-4 text-sm" key={`${planId}-${row.quotaType}`}>
                        <span className="text-on-surface-variant">{row.label}</span>
                        <span className="font-semibold text-on-surface">
                          {formatQuotaValue(planQuotas[row.quotaType])}
                        </span>
                      </div>
                    ))}
                  </div>

                  <div className="mt-7 flex flex-col gap-3">
                    {isPaidPlan && offers.length ? (
                      <div className="grid grid-cols-3 gap-2" role="group" aria-label="Runr Pro duration">
                        {offers.map((offer) => {
                          const offerId = String(offer.offer_id || "");
                          const isSelected = offerId === activeOfferId;
                          return (
                            <button
                              className={[
                                "rounded-xl border px-2 py-2 text-xs font-semibold transition-colors",
                                isSelected
                                  ? "border-primary bg-primary/10 text-primary"
                                  : "border-outline-variant/20 text-on-surface-variant hover:bg-surface-container-low",
                              ].join(" ")}
                              key={offerId}
                              onClick={() => setSelectedOfferId(offerId)}
                              type="button"
                            >
                              {offer.display_name}
                              <span className="mt-1 block text-[11px] font-normal">
                                ${Number(offer.price || 0).toFixed(2)}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    ) : null}
                    {isCurrentPlan && isPaidPlan ? (
                      <button
                        className="rounded-full bg-primary px-5 py-3 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                        disabled={actionState.managing}
                        onClick={handleManageSubscription}
                        type="button"
                      >
                        {actionState.managing ? "Opening portal..." : "Manage subscription"}
                      </button>
                    ) : null}
                    {!isCurrentPlan && isPaidPlan ? (
                      <button
                        className="rounded-full bg-primary px-5 py-3 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                        disabled={Boolean(actionState.loadingPlanId)}
                        onClick={() => handleUpgrade(planId, activeOfferId)}
                        type="button"
                      >
                        {actionState.loadingPlanId === planId ? "Preparing checkout..." : `Upgrade to ${plan.display_name}`}
                      </button>
                    ) : null}
                  </div>
                </div>
              </section>
            );
          })}
        </div>
      )}

      {!isLoading && plans.length ? (
        <section className="overflow-hidden rounded-[2rem] border border-outline-variant/20 bg-surface-container-lowest shadow-soft">
          <div className="border-b border-outline-variant/10 px-7 py-5">
            <h2 className="font-headline text-xl font-bold tracking-tight text-on-surface">
              Feature comparison
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="bg-surface-container-low">
                  <th className="px-7 py-4 font-semibold text-on-surface">Quota</th>
                  {plans.map((plan) => (
                    <th className="px-7 py-4 font-semibold text-on-surface" key={`head-${plan.plan_id}`}>
                      {plan.display_name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {featureRows.map((row) => (
                  <tr className="border-t border-outline-variant/10" key={`row-${row.quotaType}`}>
                    <td className="px-7 py-4 text-on-surface-variant">{row.label}</td>
                    {plans.map((plan) => (
                      <td className="px-7 py-4 font-medium text-on-surface" key={`${row.quotaType}-${plan.plan_id}`}>
                        {formatQuotaValue((plan.quotas || {})[row.quotaType])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <div className="flex justify-end">
        <button
          className="rounded-full border border-outline-variant/20 bg-surface-container-low px-4 py-2 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
          onClick={() => {
            refreshPlans().catch(() => undefined);
            refreshSubscription().catch(() => undefined);
          }}
          type="button"
        >
          Refresh pricing
        </button>
      </div>
    </div>
  );
}
