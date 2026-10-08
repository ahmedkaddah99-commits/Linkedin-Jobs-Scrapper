import { useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../../context/SessionContext";
import { useApiResource } from "../../hooks/useApiResource";

const steps = [
  ["Personal information", "Contact, location, and application basics", "/profile", "person"],
  ["Upload your primary resume", "Keep your resume ready for applications and tailoring", "/documents", "upload_file"],
  ["Add job preferences", "Target roles, locations, salary, and work setup", "/profile?section=preferences", "tune"],
  ["Complete experience evidence", "Add skills and quantified outcomes for stronger matching", "/profile?section=experience", "work_history"],
  ["Connect LinkedIn for referrals", "Find people at companies you want to join", "/referrals?section=linkedin", "group_add"],
  ["Set up the Apply extension", "Autofill applications from your Runr profile", "/apply-extension", "extension"],
];

export default function AccountSetupPanel() {
  const { request } = useSession();
  const [expanded, setExpanded] = useState(false);
  const { data: settings } = useApiResource(() => request("/settings"), [], { cacheKey: "settings", staleMs: 30000 });
  const { data: preferenceData } = useApiResource(() => request("/personalized-jobs/preferences"), [], { cacheKey: "job-preferences", staleMs: 30000 });
  const profile = settings?.profile || {};
  const preferences = preferenceData?.preferences || preferenceData || {};
  const next = !profile.name || !(profile.email || settings?.account?.email) || !profile.location
    ? steps[0]
    : !preferences.target_roles?.length || !preferences.preferred_locations?.length
      ? steps[2]
      : !profile.recent_experience?.length ? steps[3] : steps[1];

  return <aside aria-label="Account setup" className="jobs-setup-rail">
    <section className="jobs-setup-card">
      <header><span className="material-symbols-outlined" aria-hidden="true">auto_awesome</span><h2>Account setup</h2></header>
      <p className="jobs-setup-card__hint">{expanded ? "Your setup shortcuts" : "Suggested next"}</p>
      <div id="jobs-setup-steps" className="jobs-setup-links">
        {(expanded ? steps : [next]).map(([title, description, to, icon]) => <Link key={to} to={to}>
          <span className="material-symbols-outlined" aria-hidden="true">{icon}</span>
          <span><strong>{title}</strong><small>{description}</small></span>
          <span className="material-symbols-outlined" aria-hidden="true">arrow_forward</span>
        </Link>)}
      </div>
      <button aria-controls="jobs-setup-steps" aria-expanded={expanded} onClick={() => setExpanded((open) => !open)} type="button">
        {expanded ? "Hide steps" : "Show all steps"}<span className="material-symbols-outlined" aria-hidden="true">{expanded ? "expand_less" : "expand_more"}</span>
      </button>
    </section>
  </aside>;
}
