import { Link } from "react-router-dom";
import { useState } from "react";
import { useSession } from "../context/SessionContext";

function Icon({ children }) {
  return <span className="material-symbols-outlined" aria-hidden="true">{children}</span>;
}

const setupSteps = [
  ["Personal information", "Contact, location, and application basics", "/profile", true],
  ["Upload your primary resume", "Used for matching and resume tailoring", "/documents", true],
  ["Add job preferences", "Target roles, locations, salary, and work setup", "/profile?section=preferences", false],
  ["Complete experience evidence", "Add skills and quantified outcomes for stronger v2 matching", "/profile?section=experience", false],
  ["Connect LinkedIn for referrals", "Find people at companies you want to join", "/referrals/linkedin-csv-guide", false],
  ["Set up the Apply extension", "Autofill applications from your Runr profile", "/apply-extension", false],
];

const focusItems = [
  ["Complete your job preferences", "Improve your personalized job ranking.", "/profile?section=preferences", "Continue"],
  ["Review recommended jobs", "Prioritized using v1 and v2 evidence.", "/jobs", "View jobs"],
  ["Follow up on active applications", "Keep your application pipeline moving.", "/tracker", "Open tracker"],
];

const freshJobs = [
  ["Operations & Strategy", "Based on your target roles and evidence", "/jobs"],
  ["Business Analysis", "Explore newly ranked roles in your preferred locations", "/jobs?category=Business%20Analysis"],
  ["Business & Strategy", "Compare v1 keyword fit with v2 evidence fit", "/jobs?category=Business%20%26%20Strategy"],
];

export default function HomePage() {
  const { user } = useSession();
  const [setupOpen, setSetupOpen] = useState(true);
  const displayName = String(user?.display_name || user?.email || "there").split(/[ @]/)[0];
  return <div className="runr-home">
    <header className="runr-home__hero">
      <div><span className="runr-eyebrow">Your search, today</span><h1>Good to see you, {displayName}</h1><p>Build one complete profile, then use it to discover, evaluate, and prepare stronger applications.</p></div>
      <div><button aria-expanded={setupOpen} className="runr-button runr-button--secondary" onClick={() => setSetupOpen((open) => !open)} type="button"><Icon>person</Icon>Complete setup<Icon>{setupOpen ? "expand_less" : "expand_more"}</Icon></button><Link className="runr-button" to="/jobs"><Icon>search</Icon>Find jobs</Link></div>
    </header>

    <section className="runr-setup-card">
      <button aria-expanded={setupOpen} className="runr-setup-card__intro" onClick={() => setSetupOpen((open) => !open)} type="button"><span className="runr-setup-card__spark"><Icon>auto_awesome</Icon></span><div><span className="runr-eyebrow">Your Runr foundation</span><h2>Finish account setup for better matches</h2><p>Complete your profile, connect LinkedIn referrals, and set up Apply.</p></div><div className="runr-setup-progress"><strong>2 of 6</strong><span>steps complete</span><i><b /></i></div><Icon>{setupOpen ? "expand_less" : "expand_more"}</Icon></button>
      {setupOpen ? <div className="runr-setup-steps">{setupSteps.map(([title, copy, to, complete], index) => <Link className={complete ? "is-complete" : ""} key={title} to={to}><span>{complete ? <Icon>check</Icon> : index + 1}</span><div><strong>{title}</strong><small>{copy}</small></div><em>{complete ? "Complete" : <><span>Continue</span><Icon>arrow_forward</Icon></>}</em></Link>)}</div> : null}
    </section>

    <section className="runr-home__stats" aria-label="Search overview">
      <article><span><Icon>auto_awesome</Icon></span><div><strong>Recommended jobs</strong><small>Ranked from your profile</small></div><Link to="/jobs">Review</Link></article>
      <article><span><Icon>bookmark</Icon></span><div><strong>Saved jobs</strong><small>Your shortlist in one place</small></div><Link to="/jobs">Open</Link></article>
      <article><span><Icon>description</Icon></span><div><strong>Career documents</strong><small>CVs, motivation letters, Master CV</small></div><Link to="/documents">Manage</Link></article>
      <article><span><Icon>history</Icon></span><div><strong>Application tracker</strong><small>Follow-ups and outcomes</small></div><Link to="/tracker">View</Link></article>
    </section>

    <div className="runr-home__grid">
      <section className="runr-home-card"><div className="runr-home-card__heading"><div><span className="runr-eyebrow">Recommended next</span><h2>Focus for today</h2></div></div><div className="runr-focus-list">{focusItems.map(([title, copy, to, meta], index) => <Link key={title} to={to}><span>{index + 1}</span><div><strong>{title}</strong><small>{copy}</small></div><em>{meta}</em><Icon>arrow_forward</Icon></Link>)}</div></section>
      <section className="runr-home-card runr-home-card--accent"><span className="runr-eyebrow">How matching works</span><h2>Two scores, one clearer decision</h2><p>v1 checks ATS-style keyword alignment. v2 adds semantic and evidence-aware matching from your profile.</p><div className="runr-score-demo"><span className="is-medium"><strong>63</strong><small>v1</small></span><span className="is-strong"><strong>82</strong><small>v2</small></span></div><Link className="runr-button runr-button--secondary" to="/profile?section=experience">Strengthen profile evidence</Link></section>
    </div>
    <div className="runr-home__dashboard-grid">
      <section className="runr-home-card"><div className="runr-home-card__heading"><div><span className="runr-eyebrow">Suggested rhythm</span><h2>Build weekly momentum</h2></div><Link to="/tracker">Open tracker</Link></div><div className="runr-activity-chart" aria-label="Suggested weekly job-search rhythm"><div><i style={{height:"30%"}}/><span>Mon</span></div><div><i style={{height:"52%"}}/><span>Tue</span></div><div><i style={{height:"42%"}}/><span>Wed</span></div><div><i style={{height:"78%"}}/><span>Thu</span></div><div><i style={{height:"64%"}}/><span>Fri</span></div><div><i style={{height:"88%"}}/><span>Sat</span></div><div><i style={{height:"58%"}}/><span>Sun</span></div></div><p className="runr-home-card__note">Use this cadence as a guide for reviewing, saving, and progressing opportunities. Your actual pipeline stays in Tracker.</p></section>
      <section className="runr-home-card"><div className="runr-home-card__heading"><div><span className="runr-eyebrow">Discover</span><h2>Fresh jobs</h2></div><Link to="/jobs">View all</Link></div><div className="runr-fresh-list">{freshJobs.map(([title, copy, to], index) => <Link key={title} to={to}><span>{index + 1}</span><div><strong>{title}</strong><small>{copy}</small></div><Icon>arrow_forward</Icon></Link>)}</div></section>
      <section className="runr-home-card"><div className="runr-home-card__heading"><div><span className="runr-eyebrow">Application funnel</span><h2>Move work forward</h2></div><Link to="/tracker">Manage</Link></div><div className="runr-funnel"><Link to="/jobs"><b>Discover</b><span>Find and evaluate roles</span></Link><Link to="/documents"><b>Prepare</b><span>Tailor your documents</span></Link><Link to="/tracker"><b>Track</b><span>Follow up and record outcomes</span></Link></div></section>
    </div>
  </div>;
}
