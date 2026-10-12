import { useClerk, useUser } from "@clerk/react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { useApiResource } from "../hooks/useApiResource";
import { billingMessage } from "../lib/billingPresentation";
import "../settings.css";

export default function SettingsPage({ onClose }) {
  const navigate = useNavigate();
  const { request, disconnect, refreshSession, user } = useSession();
  const { user: clerkUser } = useUser();
  const { openUserProfile } = useClerk();
  const [tab, setTab] = useState("subscriptions");
  const [billingPortalState, setBillingPortalState] = useState({ loading: false, error: "" });
  const dialogRef = useRef(null);
  const close = () => onClose ? onClose() : navigate("/jobs");
  function manageAccount() {
    dialogRef.current.close();
    close();
    requestAnimationFrame(() => openUserProfile());
  }
  useEffect(() => { const dialog = dialogRef.current; dialog.showModal(); return () => dialog.close(); }, []);
  const settings = useApiResource(() => request("/settings"), [request], { cacheKey: "settings", staleMs: 30000 });
  const preferences = useApiResource(() => request("/personalized-jobs/preferences"), [request], { cacheKey: "job-preferences", staleMs: 30000 });
  const { data: subscriptionData, loading: usageLoading, error: usageError, refresh: refreshSubscription } = useApiResource(() => request("/billing/subscription"), [request], { cacheKey: "billing:subscription", staleMs: 300000 });
  async function refreshUsage() { await Promise.all([refreshSubscription(), refreshSession()]); }
  async function handleManageBilling() {
    setBillingPortalState({ loading: true, error: "" });
    try {
      const payload = await request("/billing/portal", { method: "POST", body: {} });
      if (!payload.portal_url) throw new Error("Unable to open your subscription. Please try again.");
      window.location.assign(payload.portal_url);
    } catch (error) { setBillingPortalState({ loading: false, error: billingMessage(error) }); }
  }
  const currentPlanId = subscriptionData?.plan_id || "free";
  const currentPlanName = subscriptionData?.plan?.display_name || "Free";
  const subscriptionDetails = subscriptionData?.subscription || {};
  const hasBillingPortalAccess = Boolean(subscriptionDetails.creem_customer_id || subscriptionDetails.creem_subscription_id);
  const tabs = [["login", "person", "Login & Security"], ["subscriptions", "account_balance_wallet", "Subscriptions"], ["alerts", "notifications", "Job Alerts Preference"], ["email", "mail", "Email Providers"]];
  const pref = preferences.data?.preferences || preferences.data || {};
  const chips = [pref.target_roles, pref.job_functions, pref.employment_types, pref.work_arrangements, pref.experience_levels, pref.preferred_locations, pref.countries].flat().filter(value => typeof value === "string" && value);
  return <dialog ref={dialogRef} className="runr-settings-dialog" aria-labelledby="settings-title" onCancel={close} onClick={event => { if (event.target === event.currentTarget) close(); }}>
    <div className="runr-settings-layout">
      <nav className="runr-settings-menu" aria-label="Settings sections">
        <div>{tabs.map(([id, icon, label]) => <button key={id} type="button" aria-current={tab === id ? "page" : undefined} onClick={() => setTab(id)}><span aria-hidden="true" className="material-symbols-outlined">{icon}</span>{label}{id === "email" ? <small className="runr-coming-soon">Coming soon</small> : null}</button>)}</div>
        <div className="runr-settings-footer"><a href="https://userunr.com/privacy" target="_blank" rel="noreferrer"><span className="material-symbols-outlined">description</span>Privacy Policy</a><button type="button" onClick={disconnect}><span className="material-symbols-outlined">logout</span>Log Out</button></div>
      </nav>
      <section className="runr-settings-content">
        <header><h1 id="settings-title">{tabs.find(([id]) => id === tab)[2]}</h1><button aria-label="Close settings" type="button" onClick={close}><span className="material-symbols-outlined">close</span></button></header>
        {tab === "subscriptions" ? <>
          <h2>Current Plan</h2>
          {usageLoading ? <p role="status">Loading subscription…</p> : usageError ? <p role="alert">{billingMessage(usageError, "Unable to load your subscription. Please try again.")}</p> : <div className="runr-settings-plan"><div className="runr-settings-plan-heading"><strong>{currentPlanName}</strong><Link to="/pricing" onClick={onClose}>View Detail</Link><a href="https://userunr.com/terms-and-conditions" target="_blank" rel="noreferrer">Terms and Conditions</a></div><div className="runr-settings-plan-action"><p>{currentPlanId === "free" ? "Unlock more features with Runr Pro" : `Subscription status: ${subscriptionDetails.status || "Not available"}`}</p>{hasBillingPortalAccess ? <button type="button" disabled={billingPortalState.loading} onClick={handleManageBilling}>{billingPortalState.loading ? "Opening…" : "Manage subscription"}</button> : <Link to="/pricing" onClick={onClose}>Upgrade Now</Link>}</div></div>}
          {billingPortalState.error ? <p role="alert">{billingPortalState.error}</p> : null}
          <div className="runr-settings-refresh"><h3>Not Seeing Your Updated Subscription?</h3><p>If you’ve completed your payment or changed your subscription but don’t see the latest status, refresh your subscription to see the latest status.</p><button type="button" disabled={usageLoading} onClick={() => refreshUsage().catch(() => undefined)}>Refresh Status</button></div>
        </> : null}
        {tab === "alerts" ? <><div className="runr-settings-chips">{[...new Set(chips)].map(chip => <span key={chip}>{chip.replaceAll("_", " ")}</span>)}<Link to="/jobs" onClick={onClose}><span className="material-symbols-outlined">edit</span>Filters</Link></div><p className="runr-settings-coming-note">Automatic emails <span className="runr-coming-soon">Coming soon</span></p>{[["Instant Job Alerts", "Be the first to apply — get fresh, tailored job alerts within an hour of posting.", ["Up to 1 alert/day", "Up to 2 alerts/day", "Up to 5 alerts/day", "Unlimited"]], ["Digest Job Alerts", "Receive a curated list of matching job opportunities in a single email, delivered daily or weekly.", ["Daily", "Weekly"]]].map(([title, description, options]) => <section className="runr-settings-alert" key={title}><h2>{title}<span className="runr-coming-soon">Coming soon</span></h2><div><label>Enable {title}<small>{description}</small></label><button type="button" role="switch" aria-label={`Enable ${title}`} aria-checked="false" disabled className="runr-settings-switch"><span /></button></div><div><label htmlFor={title}>Job Alerts Frequency</label><select id={title} disabled defaultValue={options[0]}>{options.map(option => <option key={option}>{option}</option>)}</select></div></section>)}</> : null}
        {tab === "email" ? <><h2>Automatic emails <span className="runr-coming-soon">Coming soon</span></h2><p className="runr-settings-coming-note">Connect an email provider to receive job alerts when this feature becomes available.</p><button type="button" disabled className="runr-settings-provider">Connect email provider</button></> : null}
        {tab === "login" ? <section className="runr-settings-security">
          <h2>Account</h2>
          <div className="runr-settings-security-row"><div><strong>Email Address</strong><p>{clerkUser?.primaryEmailAddress?.emailAddress || settings.data?.account?.email || user?.email || ""}</p></div><button type="button" onClick={manageAccount}>Manage account</button></div>
          <h2>Security</h2>
          <div className="runr-settings-security-row"><div><strong>Password & Sign-in Methods</strong><p>Manage your password, connected accounts and account security.</p></div><button type="button" onClick={manageAccount}>Manage security</button></div>
        </section> : null}

      </section>
    </div>
  </dialog>;
}
