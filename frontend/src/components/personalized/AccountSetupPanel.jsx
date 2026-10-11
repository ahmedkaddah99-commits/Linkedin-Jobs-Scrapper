import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../../context/SessionContext";
import { useApiResource } from "../../hooks/useApiResource";
import { getLinkedInConnectionsStatus } from "../../lib/linkedinSync";
import { profileMissingFields } from "../../lib/profileCompletion";

const ProfilePage = lazy(() => import("../../pages/ProfilePage"));
function Icon({ children }) { return <span className="material-symbols-outlined" aria-hidden="true">{children}</span>; }

export default function AccountSetupPanel({ children }) {
  const { request, user } = useSession();
  const [profileOpen, setProfileOpen] = useState(false);
  const [extension, setExtension] = useState("checking");
  const dialog = useRef(null);
  const opener = useRef(null);
  const { data: settings, loading, error, setData: setSettings } = useApiResource(() => request("/settings"), [], { cacheKey: "settings", staleMs: 30000 });
  const { data: preferenceData, loading: preferencesLoading, error: preferencesError, setData: setPreferences } = useApiResource(() => request("/personalized-jobs/preferences"), [], { cacheKey: "job-preferences", staleMs: 30000 });
  const { data: linkedin, loading: linkedinLoading, error: linkedinError, refresh: refreshLinkedin } = useApiResource(() => request("/referrals/import/status"), [], { cacheKey: "linkedin-setup-status", staleMs: 30000 });
  const preferences = preferenceData?.preferences || preferenceData || {};
  const missing = profileMissingFields(settings, preferences);
  const profileKnown = !loading && !preferencesLoading && !error && !preferencesError && settings && preferenceData;
  const linkedinDone = Number(linkedin?.connection_count) > 0 || Boolean(linkedin?.last_sync_at);

  useEffect(() => {
    let active = true;
    async function check() {
      try {
        const result = await getLinkedInConnectionsStatus();
        if (active) setExtension(result.sync?.extension_connected === true ? "connected" : "disconnected");
      } catch { if (active) setExtension("unavailable"); }
    }
    const refresh = () => { if (document.visibilityState === "visible") { check(); refreshLinkedin({ showLoading: false }).catch(() => {}); } };
    check();
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => { active = false; window.removeEventListener("focus", refresh); document.removeEventListener("visibilitychange", refresh); };
  }, [user?.user_id, refreshLinkedin]);

  useEffect(() => {
    if (!profileOpen) return;
    const element = dialog.current;
    element.showModal();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { element.close(); document.body.style.overflow = previousOverflow; opener.current?.focus(); };
  }, [profileOpen]);

  return <aside aria-label="Account setup" className="jobs-setup-rail">
    {children}
    <section className="jobs-quick-tools">
    <h2 className="jobs-quick-tools__heading">Quick access &amp; tools</h2>
    <button aria-label={profileKnown && !missing.length ? "Review your profile" : "Finish your profile"} className="jobs-compact-profile" ref={opener} onClick={() => setProfileOpen(true)} type="button">
      <Icon>person</Icon><span><strong>Your profile</strong>{profileKnown ? <small className="jobs-compact-badge">{missing.length ? `${missing.length} left` : "Complete"}</small> : null}<span className="jobs-compact-description">{profileKnown ? (missing.length ? `Finish ${missing.length} details for better matches` : "Profile and preferences complete") : "Your details and job preferences"}</span></span><Icon>{profileKnown && !missing.length ? "check_circle" : "chevron_right"}</Icon>
    </button>
    <div className="jobs-setup-features" aria-label="Powerful Runr features">
      <Link className="jobs-feature-card jobs-feature-card--linkedin" to="/referrals?section=linkedin">
        <div><Icon>group_add</Icon><strong>LinkedIn referrals</strong><Icon>{linkedinDone ? "check_circle" : "arrow_forward"}</Icon></div>
        <p>Find people who can refer you</p>
        <span>{linkedinLoading ? "Checking connection…" : linkedinError ? "Check connection" : linkedinDone ? "Connected" : "Connect LinkedIn"}</span>
      </Link>
      <Link className="jobs-feature-card jobs-feature-card--apply" to="/apply-extension">
        <div><Icon>extension</Icon><strong>Runr Apply</strong><Icon>{extension === "connected" ? "check_circle" : "arrow_forward"}</Icon></div>
        <p>Autofill applications instantly</p>
        <span>{extension === "checking" ? "Checking extension…" : extension === "connected" ? "Connected" : "Set up the extension"}</span>
      </Link>
    </div>
    {profileKnown ? <div className="jobs-profile-readiness"><span>Profile readiness</span><strong>{Math.round((11 - missing.length) / 11 * 100)}%</strong><progress aria-label="Profile readiness" max="11" value={11 - missing.length} /></div> : null}
    </section>
    {profileOpen ? <dialog aria-labelledby="profile-completion-title" className="profile-completion-dialog" onCancel={() => setProfileOpen(false)} ref={dialog}>
      <header><div><h2 id="profile-completion-title">Finish your profile</h2><p>Your details, experience and preferences, all in one place.</p></div><button aria-label="Close profile completion" onClick={() => setProfileOpen(false)} type="button"><Icon>close</Icon></button></header>
      <Suspense fallback={<p className="profile-completion-loading">Loading your profile…</p>}><ProfilePage completionFlow onSaved={(savedSettings, savedPreferences) => { setSettings(savedSettings); setPreferences(savedPreferences); }} /></Suspense>
    </dialog> : null}
  </aside>;
}
