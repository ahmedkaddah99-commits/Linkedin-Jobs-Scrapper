import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useSession } from "../../context/SessionContext";
import { useApiResource } from "../../hooks/useApiResource";
import { getApiErrorMessage } from "../../lib/api";
import {
  getNotificationCopy,
  getPersonalValueSummary,
  getPlanPriceLabel,
  isPaidPlan,
  PERSONAL_VALUE_NOTIFICATION_MODE,
  POST_ONBOARDING_MODAL_DELAY_MS,
  POST_ONBOARDING_NOTIFICATION_DELAY_MS,
  POST_ONBOARDING_NOTIFICATION_DURATION_MS,
  POST_ONBOARDING_OFFER_SOURCE,
  PREVIEW_PRO_PLANS,
} from "../../lib/postOnboardingOffer";
import {
  loadPostOnboardingOfferState,
  loadUserOnboardingState,
  updatePostOnboardingOfferState,
} from "../../lib/personalizedPreviewState";
import { personalizedJobsDataMode } from "../../lib/personalizedJobs";
import { logPersonalizedEvent } from "../../lib/personalizedAnalytics";

function useReducedMotion() {
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!mediaQuery) return undefined;
    const update = () => setReducedMotion(mediaQuery.matches);
    update();
    mediaQuery.addEventListener?.("change", update);
    return () => mediaQuery.removeEventListener?.("change", update);
  }, []);

  return reducedMotion;
}

function PostOnboardingNotification({ copy, onDismiss, onExpire }) {
  const [paused, setPaused] = useState(false);
  const [remaining, setRemaining] = useState(POST_ONBOARDING_NOTIFICATION_DURATION_MS);
  const startedAtRef = useRef(0);

  useEffect(() => {
    if (paused) return undefined;
    startedAtRef.current = Date.now();
    const timeoutId = window.setTimeout(onExpire, remaining);
    return () => {
      const elapsed = Date.now() - startedAtRef.current;
      setRemaining((current) => Math.max(0, current - elapsed));
      window.clearTimeout(timeoutId);
    };
  }, [onExpire, paused, remaining]);

  return (
    <div
      aria-atomic="true"
      aria-live="polite"
      className="post-onboarding-notification"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setPaused(false);
      }}
      onFocus={() => setPaused(true)}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      role="status"
    >
      <span aria-hidden="true" className="post-onboarding-notification__icon material-symbols-outlined">verified</span>
      <div className="post-onboarding-notification__copy">
        <strong>{copy.title}</strong>
        <span>{copy.supporting}</span>
        {copy.previewLabel ? <small>{copy.previewLabel}</small> : null}
      </div>
      <button aria-label="Dismiss personalized jobs notification" className="post-onboarding-notification__close" onClick={onDismiss} type="button">
        <span aria-hidden="true" className="material-symbols-outlined">close</span>
      </button>
    </div>
  );
}

function PlanOption({ plan, selected, onSelect }) {
  const planId = String(plan.plan_id || "").trim();
  return (
    <button
      aria-checked={selected}
      className={["post-onboarding-plan", selected ? "is-selected" : ""].join(" ")}
      onClick={() => onSelect(planId)}
      role="radio"
      type="button"
    >
      <span className="post-onboarding-plan__radio" aria-hidden="true"><span /></span>
      <span className="post-onboarding-plan__copy">
        <strong>{plan.display_name || planId}</strong>
        <small>{getPlanPriceLabel(plan)}</small>
      </span>
      {selected ? <span aria-hidden="true" className="material-symbols-outlined post-onboarding-plan__check">check</span> : null}
    </button>
  );
}

function Benefit({ title, children, icon }) {
  return (
    <li className="post-onboarding-benefit">
      <span aria-hidden="true" className="material-symbols-outlined">{icon}</span>
      <span><strong>{title}</strong><small>{children}</small></span>
    </li>
  );
}

function RunrProOfferModal({ dataMode, open, plans, summary, loadingPlans, onClose, onCheckout, reducedMotion }) {
  const headingRef = useRef(null);
  const dialogRef = useRef(null);
  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [checkoutError, setCheckoutError] = useState("");
  const paidPlans = useMemo(
    () => plans.filter((plan) => String(plan.plan_id || "").trim() && Number(plan.price_eur) > 0),
    [plans],
  );

  useEffect(() => {
    if (!open) return undefined;
    const page = document.querySelector(".preview-page");
    const previousInert = page?.inert;
    const previousAriaHidden = page?.getAttribute("aria-hidden");
    const previousOverflow = document.body.style.overflow;
    if (page) {
      page.inert = true;
      page.setAttribute("aria-hidden", "true");
    }
    document.body.style.overflow = "hidden";
    requestAnimationFrame(() => headingRef.current?.focus());
    return () => {
      if (page) {
        page.inert = Boolean(previousInert);
        if (previousAriaHidden === null) page.removeAttribute("aria-hidden");
        else page.setAttribute("aria-hidden", previousAriaHidden);
      }
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    function handleKeyDown(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose("dismissed");
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = [...(dialogRef.current?.querySelectorAll("button:not(:disabled), [href], [tabindex]:not([tabindex='-1'])") || [])];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose, open]);

  useEffect(() => {
    if (!open) {
      setSelectedPlanId("");
      setCheckoutError("");
    }
  }, [open]);

  if (!open) return null;
  const valueSummary = getPersonalValueSummary(summary, dataMode);
  const preview = dataMode !== "real";

  async function handleCheckout() {
    if (!selectedPlanId) return;
    setCheckoutError("");
    try {
      await onCheckout(selectedPlanId);
    } catch (error) {
      setCheckoutError(getApiErrorMessage(error, "Unable to start checkout."));
    }
  }

  return createPortal(
    <div className="post-onboarding-modal-backdrop">
      <div
        aria-labelledby="post-onboarding-offer-title"
        aria-modal="true"
        className={["post-onboarding-modal", reducedMotion ? "is-reduced-motion" : ""].join(" ")}
        ref={dialogRef}
        role="dialog"
      >
        <button aria-label="Close Runr Pro offer" className="preview-modal-close post-onboarding-modal__close" onClick={() => onClose("dismissed")} type="button">
          <span aria-hidden="true" className="material-symbols-outlined">close</span>
        </button>
        <div className="post-onboarding-modal__layout">
          <section className="post-onboarding-modal__intro">
            <div className="post-onboarding-pro-mark"><span className="material-symbols-outlined">auto_awesome</span></div>
            <p className="preview-eyebrow">Runr Pro</p>
            <h2 id="post-onboarding-offer-title" ref={headingRef} tabIndex={-1}>Turn your shortlist into stronger applications</h2>
            <p className="post-onboarding-modal__lead">Runr Pro helps you avoid unsuitable jobs, understand every match and prepare job-specific applications using evidence from your real experience.</p>
            <ul className="post-onboarding-benefits">
              <Benefit icon="filter_alt" title="Review fewer unsuitable jobs">Check language, authorization, location and experience requirements before jobs reach your shortlist.</Benefit>
              <Benefit icon="insights" title="Understand why every job fits">See supporting evidence, missing qualifications and requirements Runr could not confirm.</Benefit>
              <Benefit icon="description" title="Prepare a tailored application">Create a relevant CV and motivation letter grounded in your verified experience.</Benefit>
              <Benefit icon="touch_app" title="Apply with less repetition">Reuse application answers and use Assisted Apply on supported employer forms while remaining in control.</Benefit>
              <Benefit icon="schedule" title="Keep your search working">Refresh saved searches automatically and follow multiple career directions.</Benefit>
            </ul>
            <div className="post-onboarding-value-summary">
              <span className="material-symbols-outlined">check_circle</span>
              <div><strong>{valueSummary.headline}</strong><small>{valueSummary.supporting}</small>{valueSummary.isPreview ? <small className="post-onboarding-preview-label">Preview data</small> : null}</div>
            </div>
          </section>

          <section className="post-onboarding-modal__plans" aria-labelledby="post-onboarding-plans-title">
            <div className="post-onboarding-plans-heading"><p className="preview-eyebrow">Choose your plan</p><h3 id="post-onboarding-plans-title">Start with the pace that fits your search</h3><p>Real Runr Pro plans from current billing configuration.</p></div>
            {loadingPlans ? <div className="post-onboarding-plans-loading" role="status"><span className="material-symbols-outlined">progress_activity</span>Loading current plans…</div> : null}
            {!loadingPlans && paidPlans.length ? <div aria-label="Runr Pro plans" className="post-onboarding-plan-list" role="radiogroup">{paidPlans.map((plan) => <PlanOption key={plan.plan_id} onSelect={(planId) => { setSelectedPlanId(planId); logPersonalizedEvent("post_onboarding_plan_selected", { dataMode, selectedPlanId: planId, offerSource: POST_ONBOARDING_OFFER_SOURCE, notificationMode: PERSONAL_VALUE_NOTIFICATION_MODE }); }} plan={plan} selected={selectedPlanId === String(plan.plan_id || "").trim()} />)}</div> : null}
            {!loadingPlans && !paidPlans.length ? <p className="post-onboarding-plans-empty">Current paid plans are unavailable. You can review the billing page and try again there.</p> : null}
            {checkoutError ? <p className="post-onboarding-checkout-error" role="alert">{checkoutError}</p> : null}
            <button className="preview-button preview-button--primary preview-button--full post-onboarding-upgrade-button" disabled={!selectedPlanId || !paidPlans.length} onClick={handleCheckout} type="button">Continue with Runr Pro <span className="material-symbols-outlined">arrow_forward</span></button>
            <button className="post-onboarding-free-button" onClick={() => onClose("free")} type="button">Continue with Free</button>
            <p className="post-onboarding-billing-note">You choose the plan before checkout. Prices and billing are handled by Runr&apos;s existing billing flow.</p>
            {preview ? <p className="post-onboarding-preview-note"><span className="material-symbols-outlined">visibility</span>Preview only — no plan change starts from this preview.</p> : null}
          </section>
        </div>
      </div>
    </div>,
    document.body,
  );
}

export default function PostOnboardingProOffer({ feedReady, jobsReadyAt, summary, user }) {
  const navigate = useNavigate();
  const { request } = useSession();
  const reducedMotion = useReducedMotion();
  const userId = String(user?.user_id || user?.clerk_user_id || user?.email || "anonymous").trim();
  const onboardingState = useMemo(() => loadUserOnboardingState(userId), [userId]);
  const [offerState, setOfferState] = useState(() => loadPostOnboardingOfferState(userId));
  const [sequenceState, setSequenceState] = useState("idle");
  const [notificationVisible, setNotificationVisible] = useState(false);
  const sequenceStartedRef = useRef(false);
  const aliveRef = useRef(true);
  const readyAtRef = useRef(jobsReadyAt || 0);
  const notificationAtRef = useRef(0);
  const focusOriginRef = useRef(null);
  const {
    data: plansPayload,
    loading: loadingPlans,
  } = useApiResource(() => request("/billing/plans"), [request], {
    cacheKey: "billing:plans",
    staleMs: Infinity,
    backgroundRefresh: false,
  });
  const {
    data: subscriptionPayload,
    loading: loadingSubscription,
    error: subscriptionError,
  } = useApiResource(() => request("/billing/subscription"), [request], {
    cacheKey: "billing:subscription",
    staleMs: 300000,
    backgroundRefresh: true,
  });
  const plans = Array.isArray(plansPayload?.plans) && plansPayload.plans.length
    ? plansPayload.plans
    : personalizedJobsDataMode === "synthetic" ? PREVIEW_PRO_PLANS : [];
  const effectiveLoadingPlans = personalizedJobsDataMode === "real" && loadingPlans;
  const currentPlanId = String(subscriptionPayload?.plan_id || user?.plan_id || "none").trim() || "none";
  const isPaid = isPaidPlan(currentPlanId);
  const billingReady = personalizedJobsDataMode === "synthetic"
    || (!loadingSubscription && (!subscriptionError || String(user?.plan_id || "none") !== "none"));
  const eligible = onboardingState.completed && offerState.eligible && !offerState.offerShown && !offerState.offerDismissed && !offerState.upgradeCtaSelected && !isPaid;
  const notificationCopy = getNotificationCopy(summary, personalizedJobsDataMode);

  useEffect(() => {
    aliveRef.current = true;
    return () => { aliveRef.current = false; };
  }, []);

  useEffect(() => {
    if (isPaid && !offerState.alreadySubscribed) {
      const next = updatePostOnboardingOfferState({ ...offerState, alreadySubscribed: true, completed: true }, userId);
      setOfferState(next);
    }
  }, [isPaid, offerState, userId]);

  useEffect(() => {
    if (!feedReady || !jobsReadyAt || !billingReady || !eligible || sequenceStartedRef.current) return undefined;
    sequenceStartedRef.current = true;
    readyAtRef.current = jobsReadyAt;
    focusOriginRef.current = document.activeElement?.closest?.("button, a, [tabindex]") || document.querySelector(".preview-page h1");
    const claimed = updatePostOnboardingOfferState({ ...offerState, offerShown: true }, userId);
    setOfferState(claimed);
    logPersonalizedEvent("post_onboarding_offer_eligible", { dataMode: personalizedJobsDataMode, offerSource: POST_ONBOARDING_OFFER_SOURCE, notificationMode: notificationCopy.mode, reducedMotion });
    logPersonalizedEvent("post_onboarding_jobs_ready", { dataMode: personalizedJobsDataMode, offerSource: POST_ONBOARDING_OFFER_SOURCE, notificationMode: notificationCopy.mode, reducedMotion });
    setSequenceState("eligible");
    window.setTimeout(() => {
      if (!aliveRef.current) return;
      notificationAtRef.current = Date.now();
      setNotificationVisible(true);
      setSequenceState("notification_visible");
      logPersonalizedEvent("post_onboarding_notification_shown", { dataMode: personalizedJobsDataMode, offerSource: POST_ONBOARDING_OFFER_SOURCE, notificationMode: notificationCopy.mode, readyToNotificationMs: Date.now() - readyAtRef.current, reducedMotion });
    }, POST_ONBOARDING_NOTIFICATION_DELAY_MS);
    window.setTimeout(() => {
      if (!aliveRef.current) return;
      setSequenceState("modal_visible");
      logPersonalizedEvent("post_onboarding_offer_shown", { dataMode: personalizedJobsDataMode, offerSource: POST_ONBOARDING_OFFER_SOURCE, notificationMode: notificationCopy.mode, readyToNotificationMs: notificationAtRef.current ? notificationAtRef.current - readyAtRef.current : POST_ONBOARDING_NOTIFICATION_DELAY_MS, notificationToModalMs: Date.now() - notificationAtRef.current, reducedMotion });
    }, POST_ONBOARDING_MODAL_DELAY_MS);
    return undefined;
  }, [billingReady, eligible, feedReady, jobsReadyAt, notificationCopy.mode, offerState, reducedMotion, userId]);

  function restoreFocus() {
    const target = focusOriginRef.current;
    if (target?.isConnected) {
      target.focus();
      return;
    }
    const heading = document.querySelector(".preview-page h1");
    if (heading) {
      heading.setAttribute("tabindex", "-1");
      heading.focus();
    }
  }

  function closeOffer(outcome) {
    const next = updatePostOnboardingOfferState({ ...offerState, offerDismissed: true, completed: true }, userId);
    setOfferState(next);
    setSequenceState("completed");
    setNotificationVisible(false);
    logPersonalizedEvent(outcome === "free" ? "post_onboarding_continue_free" : "post_onboarding_offer_dismissed", { dataMode: personalizedJobsDataMode, offerSource: POST_ONBOARDING_OFFER_SOURCE, offerOutcome: outcome, reducedMotion });
    restoreFocus();
  }

  function dismissNotification() {
    const next = updatePostOnboardingOfferState({ ...offerState, notificationDismissed: true }, userId);
    setOfferState(next);
    setNotificationVisible(false);
    logPersonalizedEvent("post_onboarding_notification_dismissed", { dataMode: personalizedJobsDataMode, offerSource: POST_ONBOARDING_OFFER_SOURCE, reducedMotion });
  }

  async function checkout(planId) {
    updatePostOnboardingOfferState({ ...offerState, upgradeCtaSelected: true, completed: true }, userId);
    logPersonalizedEvent("post_onboarding_upgrade_clicked", { dataMode: personalizedJobsDataMode, selectedPlanId: planId, offerSource: POST_ONBOARDING_OFFER_SOURCE, reducedMotion });
    if (personalizedJobsDataMode !== "real") {
      navigate("/pricing", { state: { source: POST_ONBOARDING_OFFER_SOURCE, selectedPlanId: planId } });
      return;
    }
    logPersonalizedEvent("post_onboarding_checkout_started", { dataMode: personalizedJobsDataMode, selectedPlanId: planId, offerSource: POST_ONBOARDING_OFFER_SOURCE, reducedMotion });
    const payload = await request("/billing/checkout", { method: "POST", body: { plan_id: planId, source_page: POST_ONBOARDING_OFFER_SOURCE } });
    window.location.assign(payload.checkout_url);
  }

  if (isPaid || !sequenceState || sequenceState === "idle" || sequenceState === "eligible" || sequenceState === "completed") {
    return notificationVisible ? createPortal(<PostOnboardingNotification copy={notificationCopy} onDismiss={dismissNotification} onExpire={() => setNotificationVisible(false)} />, document.body) : null;
  }

  const modal = (
    <>
      {notificationVisible ? createPortal(<PostOnboardingNotification copy={notificationCopy} onDismiss={dismissNotification} onExpire={() => setNotificationVisible(false)} />, document.body) : null}
      <RunrProOfferModal
        dataMode={personalizedJobsDataMode}
        loadingPlans={effectiveLoadingPlans}
        onCheckout={checkout}
        onClose={closeOffer}
        open={sequenceState === "modal_visible"}
        plans={plans}
        reducedMotion={reducedMotion}
        summary={summary}
      />
    </>
  );
  return modal;
}
