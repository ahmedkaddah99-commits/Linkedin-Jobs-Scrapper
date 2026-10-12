import { billingFeatures } from "../lib/billingPresentation";

function allowance(value) {
  return Number(value) === -1 ? "Unlimited" : Number(value) > 0 ? String(value) : "—";
}

export default function SubscriptionComparison({ plans, currentPlanId, actionState, onUpgrade, onManage }) {
  const paid = plans.find(plan => plan.plan_id === "runr_pro");
  const free = plans.find(plan => plan.plan_id === "free");
  const features = billingFeatures(plans);
  const offers = [...(paid?.offers || [])].sort((a, b) => {
    const order = { one_month: 0, three_months: 1, one_week: 2 };
    return (order[a.offer_id] ?? 3) - (order[b.offer_id] ?? 3);
  });
  const labels = { one_month: "Monthly", three_months: "Quarterly", one_week: "Weekly" };
  const periods = { one_month: "month", three_months: "3 months", one_week: "week" };
  return <><section className="runr-plan-comparison" aria-label="Subscription plans">
    <div className="runr-plan-paid">
      <div className="runr-plan-offers">{offers.map(offer => <article key={offer.offer_id} className={offer.offer_id === "three_months" ? "is-popular" : ""}>
        {offer.offer_id === "three_months" ? <span className="runr-plan-popular">MOST POPULAR</span> : null}
        <h2>{labels[offer.offer_id] || offer.display_name}</h2>
        <p className="runr-plan-price">{new Intl.NumberFormat("en-US", { style: "currency", currency: offer.currency || paid.currency || "USD" }).format(Number(offer.price || 0))}<small>/{periods[offer.offer_id] || offer.display_name}</small></p>
        <button type="button" disabled={Boolean(actionState.loadingPlanId) || actionState.managing} onClick={() => currentPlanId === "runr_pro" ? onManage() : onUpgrade("runr_pro", offer.offer_id)}>{actionState.loadingPlanId ? "Preparing checkout…" : actionState.managing ? "Opening…" : currentPlanId === "runr_pro" ? "Manage subscription" : "Upgrade Now"}</button>
      </article>)}</div>
      <h3>All features included in <strong>{paid?.display_name || "Runr Pro"}</strong></h3>
      {features.map(row => <div className="runr-plan-feature" key={row.label}><span>{row.label}</span><strong>{allowance(row.paid)}</strong></div>)}
      <div className="runr-plan-feature"><span>Automatic Email Alerts</span><span className="runr-coming-soon">Coming soon</span></div>
    </div>
    {free ? <div className="runr-plan-free"><div className="runr-plan-free-heading"><h2>Free Plan</h2><p className="runr-plan-price">$0.00</p>{currentPlanId === "free" ? <span className="runr-plan-current">Your Current Plan</span> : <span>Free access</span>}</div><div className="runr-plan-feature-spacer" />{features.map(row => <div className="runr-plan-feature" key={row.label}><span className="runr-plan-mobile-label">{row.label}</span><strong>{allowance(row.free)}</strong></div>)}<div className="runr-plan-feature"><span className="runr-plan-mobile-label">Automatic Email Alerts</span><span className="runr-coming-soon">Coming soon</span></div></div> : null}
  </section><section className="runr-plan-shared"><h2>Accessible to All Plans</h2><p>Tools to make your job search easier and faster.</p><div>{["Job Board Access", "Job Match Scores", "Advanced Job Filtering", "Job Tracking", "Company Insights", "Connection Directory"].map(feature => <span key={feature}>{feature}<i aria-hidden="true">✓</i></span>)}</div></section></>;
}
