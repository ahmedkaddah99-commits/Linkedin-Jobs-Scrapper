import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { getApiErrorMessage } from "../lib/api";

const quotaLabels = {
  runs_per_month: "Runs / month",
  applications_per_month: "Applications / month",
  cv_exports_per_month: "CV exports / month",
  referral_drafts_per_month: "Referral drafts / month",
  workspaces: "Workspaces",
};

function formatQuotaValue(value) {
  return Number(value) === -1 ? "Unlimited" : String(value ?? "0");
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
  const { request, user } = useSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const checkoutRefreshStartedRef = useRef(false);
  const [actionState, setActionState] = useState({ loadingPlanId: "", managing: false, error: "" });
  const [promoCode, setPromoCode] = useState("");
  const {
    data: plansPayload,
    loading: plansLoading,
    error: plansError,
    refresh: refreshPlans,
  } = useApiResource(() => request("/billing/plans"), [request]);
  const {
    data: subscriptionPayload,
    loading: subscriptionLoading,
    error: subscriptionError,
    refresh: refreshSubscription,
  } = useApiResource(() => request("/billing/subscription"), [request]);

  const plans = Array.isArray(plansPayload?.plans) ? plansPayload.plans : [];
  const currentPlanId = String(subscriptionPayload?.plan_id || user?.plan_id || "free").trim() || "free";
  const checkoutState = String(searchParams.get("checkout") || "").trim();
  const checkoutPlanId = String(searchParams.get("plan_id") || "").trim();
  const checkoutPlan = plans.find((plan) => String(plan.plan_id || "").trim() === checkoutPlanId);
  const currentPlan = plans.find((plan) => String(plan.plan_id || "").trim() === currentPlanId);
  const currentPlanName = String(currentPlan?.display_name || subscriptionPayload?.plan?.display_name || currentPlanId).trim();
  const checkoutPlanName = String(checkoutPlan?.display_name || checkoutPlanId || currentPlanName).trim();
  const showCheckoutSuccess = checkoutState === "success";
  const featureRows = buildFeatureRows(plans);

  useEffect(() => {
    if (checkoutState !== "success") {
      checkoutRefreshStartedRef.current = false;
      return;
    }
    if (checkoutRefreshStartedRef.current) {
      return;
    }
    checkoutRefreshStartedRef.current = true;
    refreshSubscription().catch(() => undefined);
  }, [checkoutState, refreshSubscription]);

  async function handleUpgrade(planId) {
    setActionState({ loadingPlanId: planId, managing: false, error: "" });
    try {
      const payload = await request("/billing/checkout", {
        method: "POST",
        body: {
          plan_id: planId,
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
            View usage
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
                  {subscriptionLoading
                    ? `Confirming your ${checkoutPlanName} subscription...`
                    : `You are subscribed to ${currentPlanName}.`}
                </p>
              </div>
            </div>
            <button
              className="inline-flex items-center justify-center gap-2 rounded-full border border-primary/20 bg-surface-container-lowest px-4 py-2 text-sm font-semibold text-primary transition-colors hover:bg-surface-container-low"
              onClick={() => setSearchParams({})}
              type="button"
            >
              <span className="material-symbols-outlined text-[18px]">close</span>
              Dismiss
            </button>
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
        <div className="grid gap-6 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <div
              className="h-[20rem] animate-pulse rounded-[2rem] border border-outline-variant/20 bg-surface-container-low"
              key={`pricing-skeleton-${index + 1}`}
            />
          ))}
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          {plans.map((plan) => {
            const planId = String(plan.plan_id || "").trim();
            const isCurrentPlan = planId === currentPlanId;
            const isPaidPlan = Number(plan.price_eur || 0) > 0;
            const planQuotas = plan.quotas || {};
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
                          €{plan.price_eur}
                        </span>
                        <span className="pb-1 text-sm text-on-surface-variant">/ month</span>
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
                        onClick={() => handleUpgrade(planId)}
                        type="button"
                      >
                        {actionState.loadingPlanId === planId ? "Preparing checkout..." : `Upgrade to ${plan.display_name}`}
                      </button>
                    ) : null}
                    {isCurrentPlan && !isPaidPlan ? (
                      <p className="rounded-2xl bg-primary/10 px-4 py-3 text-sm text-primary">
                        You&apos;re on the free plan. Upgrade to unlock higher monthly limits.
                      </p>
                    ) : null}
                    {!isCurrentPlan && !isPaidPlan ? (
                      <p className="rounded-2xl border border-outline-variant/20 bg-surface-container-low px-4 py-3 text-sm text-on-surface-variant">
                        Free remains available as your baseline workspace.
                      </p>
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
