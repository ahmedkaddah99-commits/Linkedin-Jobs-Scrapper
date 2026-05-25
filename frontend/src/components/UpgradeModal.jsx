import { useEffect, useState } from "react";
import { useSession } from "../context/SessionContext";
import { getApiErrorMessage } from "../lib/api";
import { logEvent } from "../lib/analytics";

const quotaLabels = {
  runs_per_month: "runs",
  applications_per_month: "applications",
  cv_exports_per_month: "CV export",
  referral_drafts_per_month: "referral draft",
  workspaces: "workspace",
};

function upgradeLabelForPlan(planId) {
  return String(planId || "").trim() === "pro" ? "Upgrade to Business" : "Upgrade to Pro";
}

function targetPlanIdForPlan(planId) {
  return String(planId || "").trim() === "pro" ? "business" : "pro";
}

export default function UpgradeModal({ quotaEvent, onClose, currentPage = "" }) {
  const { request, user } = useSession();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [promoCode, setPromoCode] = useState("");

  useEffect(() => {
    if (!quotaEvent) {
      return undefined;
    }
    const payload = {
      quota_type: quotaEvent.quota_type,
      plan_id: quotaEvent.plan_id,
      page: currentPage,
    };
    logEvent("upgrade_prompt_shown", {
      ...payload,
      user_id: user?.user_id,
    });
    request("/analytics/events", {
      method: "POST",
      body: {
        event_name: "upgrade_prompt_shown",
        ...payload,
      },
    }).catch(() => undefined);
    return undefined;
  }, [currentPage, quotaEvent, request, user?.user_id]);

  useEffect(() => {
    if (quotaEvent) {
      return;
    }
    setPromoCode("");
    setError("");
    setLoading(false);
  }, [quotaEvent]);

  if (!quotaEvent) {
    return null;
  }

  async function handleUpgrade() {
    setLoading(true);
    setError("");
    try {
      const targetPlanId = targetPlanIdForPlan(quotaEvent.plan_id);
      const payload = await request("/billing/checkout", {
        method: "POST",
        body: {
          plan_id: targetPlanId,
          promo_code: promoCode.trim().toUpperCase(),
          source_page: currentPage,
        },
      });
      window.location.assign(payload.checkout_url);
    } catch (requestError) {
      setError(getApiErrorMessage(requestError, "Unable to start checkout."));
      setLoading(false);
    }
  }

  const quotaLabel = quotaLabels[quotaEvent.quota_type] || quotaEvent.quota_type || "usage";

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-[#07111f]/55 px-4 py-6 backdrop-blur-[4px]">
      <div className="w-full max-w-xl overflow-hidden rounded-[2rem] border border-outline-variant/20 bg-surface-container-lowest shadow-soft">
        <div className="bg-[linear-gradient(135deg,rgba(var(--color-primary),0.16),rgba(var(--color-tertiary),0.08))] px-7 py-6">
          <p className="text-xs font-bold uppercase tracking-[0.28em] text-primary">Upgrade required</p>
          <h2 className="mt-3 font-headline text-3xl font-extrabold tracking-tight text-on-surface">
            You&apos;ve reached your {quotaLabel} limit on the {String(quotaEvent.plan_id || "free").toUpperCase()} plan.
          </h2>
        </div>

        <div className="space-y-5 px-7 py-6">
          <p className="text-sm leading-7 text-on-surface-variant">
            You&apos;ve used {quotaEvent.used} of {quotaEvent.limit} {quotaLabel}
            {quotaEvent.limit === 1 ? "" : "s"} this month.
          </p>

          <div className="rounded-2xl border border-outline-variant/20 bg-surface-container-low p-4">
            <div className="flex items-center justify-between text-sm">
              <span className="font-semibold text-on-surface">Current usage</span>
              <span className="text-on-surface-variant">
                {quotaEvent.used} / {quotaEvent.limit}
              </span>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-surface-container-high">
              <div
                className="h-full rounded-full bg-primary"
                style={{
                  width: `${Math.max(12, Math.min(100, (quotaEvent.used / Math.max(1, quotaEvent.limit)) * 100))}%`,
                }}
              />
            </div>
          </div>

          <label className="block space-y-2">
            <span className="text-sm font-medium text-on-surface">Promo code</span>
            <input
              className="w-full rounded-2xl border border-outline-variant/20 bg-surface-container-low px-4 py-3 font-mono uppercase text-on-surface outline-none transition-colors focus:border-primary/40"
              onChange={(event) => setPromoCode(event.target.value.toUpperCase())}
              placeholder="Optional"
              type="text"
              value={promoCode}
            />
          </label>

          {error ? (
            <p className="rounded-2xl bg-error-container px-4 py-3 text-sm text-on-error-container">
              {error}
            </p>
          ) : null}

          <div className="flex flex-wrap items-center justify-end gap-3">
            <button
              className="rounded-full border border-outline-variant/20 bg-surface-container-low px-5 py-3 text-sm font-medium text-on-surface transition-colors hover:bg-surface-container-high"
              onClick={onClose}
              type="button"
            >
              Maybe later
            </button>
            <button
              className="rounded-full bg-primary px-5 py-3 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={loading}
              onClick={handleUpgrade}
              type="button"
            >
              {loading ? "Starting checkout..." : upgradeLabelForPlan(quotaEvent.plan_id)}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
