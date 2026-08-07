import { Link } from "react-router-dom";
import { useSession } from "../context/SessionContext";

function Icon({ children }) {
  return <span className="material-symbols-outlined" aria-hidden="true">{children}</span>;
}

const setupSteps = [
  ["Personal information", "Contact, location, and application basics", "/profile", true],
  ["Upload your primary resume", "Used for matching and resume tailoring", "/documents", true],
  ["Add job preferences", "Target roles, locations, salary, and work setup", "/profile?section=preferences", false],
  ["Complete experience evidence", "Add skills and quantified outcomes for stronger v2 matching", "/profile?section=experience", false],
];

const focusItems = [
  ["Complete your job preferences", "Improve ranking across Matches and Jobs.", "/profile?section=preferences", "5 min"],
  ["Review your strongest matches", "Prioritize jobs using v1 and v2 evidence.", "/matches", "View matches"],
  ["Follow up on active applications", "Keep your application pipeline moving.", "/tracker", "Open tracker"],
];

export default function HomePage() {
  const { user } = useSession();
  const displayName = String(user?.display_name || user?.email || "there").split(/[ @]/)[0];
  return <div className="runr-home">
    <header className="runr-home__hero">
      <div><span className="runr-eyebrow">Your search, today</span><h1>Good to see you, {displayName}</h1><p>Build one complete profile, then use it to discover, evaluate, and prepare stronger applications.</p></div>
      <div><Link className="runr-button runr-button--secondary" to="/profile"><Icon>person</Icon>Complete profile</Link><Link className="runr-button" to="/jobs"><Icon>search</Icon>Find jobs</Link></div>
    </header>

    <section className="runr-setup-card">
      <div className="runr-setup-card__intro"><span className="runr-setup-card__spark"><Icon>auto_awesome</Icon></span><div><span className="runr-eyebrow">Your Runr foundation</span><h2>Finish account setup for better matches</h2><p>Runr uses your profile to rank jobs, prepare applications, tailor resumes, and power autofill. Add the missing details once and every workflow gets stronger.</p></div><div className="runr-setup-progress"><strong>2 of 4</strong><span>steps complete</span><i><b /></i></div></div>
      <div className="runr-setup-steps">{setupSteps.map(([title, copy, to, complete], index) => <Link className={complete ? "is-complete" : ""} key={title} to={to}><span>{complete ? <Icon>check</Icon> : index + 1}</span><div><strong>{title}</strong><small>{copy}</small></div><em>{complete ? "Complete" : <><span>Continue</span><Icon>arrow_forward</Icon></>}</em></Link>)}</div>
    </section>

    <section className="runr-home__stats" aria-label="Search overview">
      <article><span><Icon>auto_awesome</Icon></span><div><strong>New matches</strong><small>Ranked from your profile</small></div><Link to="/matches">Review</Link></article>
      <article><span><Icon>bookmark</Icon></span><div><strong>Saved jobs</strong><small>Your shortlist in one place</small></div><Link to="/jobs">Open</Link></article>
      <article><span><Icon>description</Icon></span><div><strong>Career documents</strong><small>CVs, motivation letters, Master CV</small></div><Link to="/documents">Manage</Link></article>
      <article><span><Icon>history</Icon></span><div><strong>Application tracker</strong><small>Follow-ups and outcomes</small></div><Link to="/tracker">View</Link></article>
    </section>

    <div className="runr-home__grid">
      <section className="runr-home-card"><div className="runr-home-card__heading"><div><span className="runr-eyebrow">Recommended next</span><h2>Focus for today</h2></div></div><div className="runr-focus-list">{focusItems.map(([title, copy, to, meta], index) => <Link key={title} to={to}><span>{index + 1}</span><div><strong>{title}</strong><small>{copy}</small></div><em>{meta}</em><Icon>arrow_forward</Icon></Link>)}</div></section>
      <section className="runr-home-card runr-home-card--accent"><span className="runr-eyebrow">How matching works</span><h2>Two scores, one clearer decision</h2><p>v1 checks ATS-style keyword alignment. v2 adds semantic and evidence-aware matching from your profile.</p><div className="runr-score-demo"><span className="is-medium"><strong>63</strong><small>v1</small></span><span className="is-strong"><strong>82</strong><small>v2</small></span></div><Link className="runr-button runr-button--secondary" to="/profile?section=experience">Strengthen profile evidence</Link></section>
    </div>
  </div>;
}
