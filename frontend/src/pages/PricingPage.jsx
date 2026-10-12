import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { billingMessage } from "../lib/billingPresentation";
import SubscriptionComparison from "../components/SubscriptionComparison";
import "../settings.css";

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

export default function PricingPage() {
  const { request, refreshSession, user } = useSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const [actionState, setActionState] = useState({ loadingPlanId: "", managing: false, error: "" });
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
              billingMessage(requestError, "Runr could not confirm the checkout return yet."),
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
        error: billingMessage(requestError, "Unable to start checkout."),
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
        error: billingMessage(requestError, "Unable to open the billing portal."),
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
  const combinedError = actionState.error || (plansError || subscriptionError ? billingMessage(plansError || subscriptionError) : "");

  return (
    <div className="runr-pricing-page">
      <section className="runr-pricing-heading">
        <p className="text-xs font-bold uppercase tracking-[0.28em] text-primary">Pricing</p>
        <div className="mt-4 flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="font-headline text-[2.35rem] font-extrabold leading-tight tracking-tight text-on-surface">
              Get more from your job search with Runr Pro
            </h1>
          </div>

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

        </section>
      ) : null}

      {isLoading ? <p role="status">Loading plans…</p> : plans.length ? <SubscriptionComparison plans={plans} currentPlanId={currentPlanId} actionState={actionState} onUpgrade={handleUpgrade} onManage={handleManageSubscription} /> : null}

      <details className="runr-pricing-promo"><summary>Have a promo code?</summary><label>Promo code<input value={promoCode} onChange={event => setPromoCode(event.target.value.toUpperCase())} /></label></details>
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
