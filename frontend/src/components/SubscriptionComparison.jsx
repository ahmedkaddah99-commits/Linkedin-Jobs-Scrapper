import { Link } from "react-router-dom";

export default function SubscriptionComparison({ plans, currentPlanId, featureRows, actionState, onUpgrade, onManage }) {
  const paid = plans.find(plan => plan.plan_id === "runr_pro");
  const free = plans.find(plan => plan.plan_id === "free");
  const offers = [...(paid?.offers || [])].sort((a, b) => {
    const order = { one_month: 0, three_months: 1, one_week: 2 };
    return (order[a.offer_id] ?? 3) - (order[b.offer_id] ?? 3);
  });
  return <section className="runr-plan-comparison" aria-label="Subscription plans">
    <div className="runr-plan-paid">
      <div className="runr-plan-offers">{offers.map(offer => <article key={offer.offer_id}>
        <h2>{offer.display_name}</h2>
        <p className="runr-plan-price">${Number(offer.price || 0).toFixed(2)}<small> / {offer.billing_type === "onetime" ? "total" : offer.display_name}</small></p>
        <button type="button" disabled={Boolean(actionState.loadingPlanId) || actionState.managing} onClick={() => currentPlanId === "runr_pro" ? onManage() : onUpgrade("runr_pro", offer.offer_id)}>{actionState.loadingPlanId ? "Preparing checkout…" : actionState.managing ? "Opening…" : currentPlanId === "runr_pro" ? "Manage subscription" : "Upgrade Now"}</button>
      </article>)}</div>
      <h3>All features included in <strong>{paid?.display_name || "Runr Pro"}</strong></h3>
      {featureRows.map(row => <div className="runr-plan-feature" key={row.quotaType}><span>{row.label}</span><strong>{Number(paid?.quotas?.[row.quotaType]) === -1 ? "Unlimited" : String(paid?.quotas?.[row.quotaType] ?? 0)}</strong></div>)}
      <div className="runr-plan-feature"><span>Automatic email alerts</span><span className="runr-coming-soon">Coming soon</span></div>
    </div>
    {free ? <div className="runr-plan-free"><div className="runr-plan-free-heading"><h2>{free.display_name}</h2><p className="runr-plan-price">$0.00</p>{currentPlanId === "free" ? <span className="runr-plan-current">Your Current Plan</span> : <Link to="/settings">View subscription</Link>}</div><div className="runr-plan-feature-spacer" />{featureRows.map(row => <div className="runr-plan-feature" key={row.quotaType}><span className="runr-plan-mobile-label">{row.label}</span><strong>{Number(free.quotas?.[row.quotaType]) === -1 ? "Unlimited" : String(free.quotas?.[row.quotaType] ?? 0)}</strong></div>)}<div className="runr-plan-feature"><span className="runr-plan-mobile-label">Automatic email alerts</span><span className="runr-coming-soon">Coming soon</span></div></div> : null}
  </section>;
}
