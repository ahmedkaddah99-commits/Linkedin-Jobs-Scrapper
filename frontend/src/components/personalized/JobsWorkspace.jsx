import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import PreviewUpgradeModal from "./PreviewUpgradeModal";
import {
  PREVIEW_JOBS,
  formatPreviewDate,
  getActivePreviewFilterCount,
  getFeedJobs,
} from "../../lib/personalizedJobs";
import { logPersonalizedEvent } from "../../lib/personalizedAnalytics";
import { usePreviewDispositions } from "../../lib/personalizedPreviewState";

const INITIAL_FILTERS = {
  query: "",
  location: "all",
  workArrangement: "all",
  datePosted: "all",
  experienceLevel: "all",
  salary: "all",
  onlyEligible: false,
  sort: "best",
};

const NETWORK_PEOPLE = [
  { initials: "JM", name: "Jordan Miller", role: "Senior Recruiter", kind: "Hiring manager" },
  { initials: "SK", name: "Samira Khan", role: "Talent Partner", kind: "Hiring manager" },
  { initials: "AL", name: "Alex Lee", role: "Product Operations", kind: "University alum" },
];

function CompanyMark({ company, large = false }) {
  const color = ["#0d628c", "#0f7c74", "#6d50c7", "#c35c35", "#2b6cae"][company.length % 5];
  return <span aria-hidden="true" className={["jobs-company-mark", large ? "jobs-company-mark--large" : ""].join(" ")} style={{ "--company-color": color }}>{company.slice(0, 1)}</span>;
}

function Icon({ children, className = "", ...props }) {
  return <span className={["material-symbols-outlined", className].join(" ")} {...props}>{children}</span>;
}

function FilterPill({ icon, label, onChange, options, value }) {
  return <label className={["jobs-filter-pill", value !== "all" ? "is-active" : ""].join(" ")}>
    <Icon>{icon}</Icon>
    <span>{label}{value !== "all" ? " (1)" : ""}</span>
    <select aria-label={label} onChange={(event) => onChange(event.target.value)} value={value}>
      {options.map((option) => <option key={`${option.value}-${option.label}`} value={option.value}>{option.label}</option>)}
    </select>
    <Icon className="jobs-filter-pill__chevron">expand_more</Icon>
  </label>;
}

function JobListCard({ isSaved, job, onSave, onSelect, selected }) {
  return <article className={["jobs-list-card", selected ? "is-selected" : ""].join(" ")}>
    <button className="jobs-list-card__select" onClick={onSelect} type="button">
      <div className="jobs-list-card__company"><CompanyMark company={job.company} /><span>{job.company}</span><span className="jobs-list-card__source">{job.source}</span></div>
      <strong>{job.title}</strong>
      <div className="jobs-list-card__meta">
        <span><Icon>calendar_month</Icon>{job.experienceLevel === "mid" ? "Mid-level" : job.experienceLevel}</span>
        <span><Icon>location_on</Icon>{job.location}</span>
        <span><Icon>{job.workArrangement === "remote" ? "wifi" : job.workArrangement === "hybrid" ? "sync_alt" : "business"}</Icon>{job.workArrangement === "onsite" ? "On-site" : job.workArrangement}</span>
      </div>
    </button>
    <button aria-label={isSaved ? `Unsave ${job.title}` : `Save ${job.title}`} aria-pressed={isSaved} className={["jobs-list-card__save", isSaved ? "is-saved" : ""].join(" ")} onClick={() => onSave(job)} type="button">
      <Icon style={isSaved ? { fontVariationSettings: "'FILL' 1" } : undefined}>bookmark</Icon>
    </button>
  </article>;
}

function MatchRing({ score }) {
  const normalizedScore = Number.isFinite(score) ? Math.min(100, Math.max(0, score)) : 0;
  const scoreColor = `hsl(${normalizedScore * 1.2} 72% 45%)`;

  return <div aria-label={`Match score: ${normalizedScore} out of 100`} className="jobs-match-ring" style={{ "--match-angle": `${normalizedScore * 3.6}deg`, "--match-color": scoreColor }}><strong>{normalizedScore}</strong><span>/100</span></div>;
}

function InfoRow({ icon, label, children }) {
  return <div className="jobs-info-row"><Icon>{icon}</Icon><div><strong>{label}</strong><span>{children}</span></div></div>;
}

function NetworkCard({ icon, locked, onClick, subtitle, title, tone }) {
  return <button className={["jobs-network-card", locked ? "is-locked" : "", tone ? `jobs-network-card--${tone}` : ""].join(" ")} onClick={onClick} type="button">
    <span className="jobs-network-card__badge"><Icon>{locked ? "lock" : icon}</Icon></span>
    <strong>{title}</strong>
    <span>{subtitle}</span>
    <em>{locked ? "Sync network" : "View connections"} <Icon>arrow_forward</Icon></em>
  </button>;
}

function ReferralSection({ onOpenNetwork }) {
  return <section className="jobs-section jobs-referral-section">
    <div className="jobs-section__heading"><div><h3>Get referred to this company</h3><p>See people who can refer or advise you</p></div><button className="jobs-text-link" onClick={() => onOpenNetwork("hiring")} type="button">Manage network <Icon>arrow_forward</Icon></button></div>
    <div className="jobs-network-grid">
      <NetworkCard icon="work" onClick={() => onOpenNetwork("hiring")} subtitle="Recruiters & hiring leads" title="People hiring for this team" tone="purple" />
      <NetworkCard icon="school" onClick={() => onOpenNetwork("alumni")} subtitle="From your saved profile" title="Alumni from your school" tone="blue" />
      <NetworkCard locked onClick={() => onOpenNetwork("direct")} subtitle="Unlock your connections" title="Direct contacts" />
      <NetworkCard locked onClick={() => onOpenNetwork("warm")} subtitle="Unlock your connections" title="Warm intros" />
    </div>
  </section>;
}

function HiringManagersModal({ mode, onClose }) {
  const [tab, setTab] = useState(mode === "alumni" ? "alumni" : mode);
  const locked = tab === "direct" || tab === "warm";
  const tabLabel = { hiring: "Hiring managers", alumni: "University alumni", direct: "Direct contacts", warm: "Warm intros" };
  return <div className="jobs-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section aria-label="Company network" aria-modal="true" className="jobs-network-modal" role="dialog">
      <header className="jobs-network-modal__tabs">
        {Object.keys(tabLabel).map((key) => <button className={tab === key ? "is-active" : ""} key={key} onClick={() => setTab(key)} type="button">{tabLabel[key]}{key !== "hiring" && key !== "alumni" ? <Icon>lock</Icon> : <small>{key === "hiring" ? "3" : "2"}</small>}</button>)}
        <button aria-label="Close network dialog" className="jobs-modal-close" onClick={onClose} type="button"><Icon>close</Icon></button>
      </header>
      <div className="jobs-network-modal__body">
        {locked ? <div className="jobs-network-lock"><span className="jobs-network-lock__icon"><Icon>group</Icon><Icon>lock</Icon></span><h3>Sync your network to unlock {tab === "direct" ? "Direct Contacts" : "Warm Intros"}</h3><p>Get full access to all connections and networking features.</p><button className="jobs-primary-button" onClick={onClose} type="button">Sync Network</button></div> : <>
          {tab === "alumni" ? <div className="jobs-network-context">Showing alumni from <strong>your current profile</strong><button className="jobs-text-link" onClick={() => setTab("alumni")} type="button">+ Add education</button></div> : null}
          {NETWORK_PEOPLE.filter((person) => tab === "alumni" ? person.kind === "University alum" : person.kind === "Hiring manager").map((person) => <article className="jobs-person-card" key={person.name}><span className="jobs-person-avatar">{person.initials}</span><div><strong>{person.name} <Icon>linkedin</Icon></strong><span>{person.role}</span></div><button className="jobs-text-link" onClick={onClose} type="button">Stand out with a message <Icon>arrow_forward</Icon></button><footer><Icon>keyboard_arrow_down</Icon>View paths</footer></article>)}
        </>}
      </div>
    </section>
  </div>;
}

function CompanyOverview({ job, onOpenNetwork }) {
  return <div className="jobs-company-overview">
    <div className="jobs-company-overview__hero"><CompanyMark company={job.company} large /><div><h2>{job.company}</h2><div className="jobs-company-actions"><button className="jobs-outline-button" type="button"><Icon>language</Icon>Website</button><button aria-label="Company on X" className="jobs-round-button" type="button">X</button><button aria-label="Company on LinkedIn" className="jobs-round-button" type="button"><Icon>linkedin</Icon></button></div></div><button className="jobs-text-link" type="button">View company profile <Icon>arrow_forward</Icon></button></div>
    <p className="jobs-company-description">{job.company} builds products and services that help modern teams make better decisions and deliver work with more clarity. This company overview is a concise Runr profile based on the employer’s public information.</p>
    <div className="jobs-company-stats"><div><span>Company size</span><strong>201–500</strong></div><div><span>Company stage</span><strong>Growth</strong></div><div><span>Headquarters</span><strong>Berlin, Germany</strong></div><div><span>Founded</span><strong>2018</strong></div></div>
    <ReferralSection onOpenNetwork={onOpenNetwork} />
    <section className="jobs-section"><h3>Benefits</h3><div className="jobs-benefits"><span><Icon>check</Icon>Remote work options</span><span><Icon>check</Icon>Flexible work hours</span><span><Icon>check</Icon>Learning budget</span></div></section>
  </div>;
}

function JobOverview({ job, onOpenNetwork, onPrepare }) {
  return <div className="jobs-overview-grid">
    <main className="jobs-overview-main">
      <div className="jobs-detail-heading"><span className="jobs-season-pill">{formatPreviewDate(job.postedAt)}</span><h1>{job.title}</h1><p>{job.company} · {job.source}</p><div className="jobs-detail-heading__actions"><button className="jobs-outline-button" onClick={() => onPrepare()} type="button"><Icon>auto_awesome</Icon>Prepare</button><button aria-label="Share job" className="jobs-round-button" type="button"><Icon>share</Icon></button><button aria-label="Report job" className="jobs-round-button" type="button"><Icon>flag</Icon></button></div></div>
      <div className="jobs-company-inline"><CompanyMark company={job.company} large /><div><h2>{job.company}</h2><p>{job.experienceLevel === "mid" ? "Growing team" : "Hiring team"} · {job.location}</p></div></div>
      <p className="jobs-role-summary">{job.descriptionSummary}</p>
      <div className="jobs-info-grid"><InfoRow icon="payments" label="Salary">{job.salary || "No salary listed"}</InfoRow><InfoRow icon="work_history" label="Job type">Full-time</InfoRow><InfoRow icon="location_on" label="Location">{job.location}</InfoRow><InfoRow icon={job.workArrangement === "remote" ? "wifi" : "business"} label="Workplace">{job.workArrangement === "onsite" ? "On-site" : job.workArrangement}</InfoRow></div>
      <section className="jobs-section"><div className="jobs-section__heading"><div><h3>Category</h3><p>How this role is grouped</p></div></div><div className="jobs-category-card"><Icon>trending_up</Icon><div><strong>Operations & Strategy</strong><span>Business Operations</span></div><small>1</small></div></section>
      <section className="jobs-section"><div className="jobs-section__heading"><div><h3>Required skills</h3><p>Skills that your profile highlights</p></div></div><div className="jobs-skill-list">{job.matchingEvidence.slice(0, 3).map((skill) => <span key={skill}><Icon>check_circle</Icon>{skill.split(" ").slice(0, 3).join(" ")}</span>)}</div></section>
      <ReferralSection onOpenNetwork={onOpenNetwork} />
      <section className="jobs-section jobs-description"><h3>Job description</h3><p>{job.description}</p><h3>Responsibilities</h3><ul><li>Build clear operating rhythms across product and customer teams.</li><li>Turn research and operational signals into useful recommendations.</li><li>Partner with stakeholders to improve planning and execution.</li></ul><h3>Requirements</h3><ul>{job.matchingEvidence.slice(0, 4).map((item) => <li key={item}>{item}</li>)}</ul></section>
    </main>
    <aside className="jobs-overview-side"><div className="jobs-segmented-control"><button className="is-active" type="button">Summary</button><button type="button">Full job posting</button></div><section className="jobs-match-card"><div className="jobs-match-card__top"><MatchRing score={job.matchScore} /><div><strong>{job.matchLabel}</strong><p>Based on your current profile and the employer’s description.</p><button className="jobs-text-link" type="button">Improve your match <Icon>arrow_forward</Icon></button></div></div><div className="jobs-match-card__versions"><span>v1</span><span>v2</span></div></section><section className="jobs-side-network"><h3>Get referred to {job.company}</h3><p>Connections can help your application get noticed.</p><ReferralSection onOpenNetwork={onOpenNetwork} /></section></aside>
  </div>;
}

export default function JobsWorkspace({ initialJobId = "" }) {
  const [searchParams] = useSearchParams();
  const [filters, setFilters] = useState(INITIAL_FILTERS);
  const [selectedJobId, setSelectedJobId] = useState(initialJobId || searchParams.get("job") || "");
  const [activeTab, setActiveTab] = useState("overview");
  const [upgradeFeature, setUpgradeFeature] = useState("");
  const [networkModal, setNetworkModal] = useState("");
  const [preparing, setPreparing] = useState(searchParams.get("prepare") === "1");
  const [feedback, setFeedback] = useState("");
  const { dispositions, hideJob, restoreJob, toggleSaved } = usePreviewDispositions();
  const jobs = useMemo(() => getFeedJobs({ filters, dispositions }), [dispositions, filters]);
  const activeFilterCount = getActivePreviewFilterCount(filters);
  const selectedJob = PREVIEW_JOBS.find((job) => job.id === selectedJobId) || jobs[0];
  const isHidden = selectedJob ? Boolean((selectedJob.hidden && !dispositions.restored?.[selectedJob.id]) || dispositions.hidden?.[selectedJob.id]) : false;
  const isSaved = selectedJob ? Boolean(dispositions.saved?.[selectedJob.id] ?? selectedJob.saved) : false;

  useEffect(() => {
    logPersonalizedEvent(initialJobId ? "job_detail_viewed" : "jobs_feed_viewed", { route: initialJobId ? `/jobs/${initialJobId}` : "/jobs", jobPreviewId: initialJobId || undefined });
  }, [initialJobId]);

  useEffect(() => {
    if (!selectedJobId && jobs[0]) setSelectedJobId(jobs[0].id);
    if (selectedJobId && jobs.length && !jobs.some((job) => job.id === selectedJobId) && !initialJobId) setSelectedJobId(jobs[0].id);
  }, [initialJobId, jobs, selectedJobId]);

  if (initialJobId && !PREVIEW_JOBS.some((job) => job.id === initialJobId)) return <Navigate replace to="/jobs" />;

  function updateFilter(name, value) {
    setFilters((current) => ({ ...current, [name]: value }));
    setFeedback("");
    logPersonalizedEvent("jobs_filter_changed", { route: "/jobs", filterName: name });
  }

  function clearFilters() {
    setFilters(INITIAL_FILTERS);
    setFeedback("Filters cleared.");
  }

  function saveJob(job) {
    const saved = Boolean(dispositions.saved?.[job.id] ?? job.saved);
    toggleSaved(job.id, saved);
    setFeedback(saved ? `${job.title} removed from saved jobs.` : `${job.title} saved.`);
    logPersonalizedEvent("job_saved", { route: "/jobs", jobPreviewId: job.id });
  }

  function toggleHide() {
    if (!selectedJob) return;
    if (isHidden) {
      restoreJob(selectedJob.id);
      setFeedback("This job is back in your shortlist.");
    } else {
      hideJob(selectedJob.id);
      setFeedback("This job is hidden. You can restore it from Hidden jobs.");
    }
  }

  function openNetwork(mode) {
    setNetworkModal(mode);
    logPersonalizedEvent("network_feature_clicked", { route: "/jobs", featureKey: mode });
  }

  function prepareApplication() {
    setPreparing(true);
    setFeedback("Application preparation opened for this preview role.");
  }

  return <div className="jobs-experience">
    <section className="jobs-search-bar" aria-label="Job search filters">
      <label className="jobs-search-input"><Icon>search</Icon><input aria-label="Search jobs" onChange={(event) => updateFilter("query", event.target.value)} placeholder="Search title, company, or skill" type="search" value={filters.query} /></label>
      <FilterPill icon="location_on" label="Location" onChange={(value) => updateFilter("location", value)} options={[{ label: "All locations", value: "all" }, { label: "Berlin", value: "berlin" }, { label: "Remote in Germany", value: "remote in germany" }]} value={filters.location} />
      <FilterPill icon="work_outline" label="Job type" onChange={(value) => updateFilter("workArrangement", value)} options={[{ label: "Any workplace", value: "all" }, { label: "Remote", value: "remote" }, { label: "Hybrid", value: "hybrid" }, { label: "On-site", value: "onsite" }]} value={filters.workArrangement} />
      <FilterPill icon="stairs" label="Experience level" onChange={(value) => updateFilter("experienceLevel", value)} options={[{ label: "Any experience", value: "all" }, { label: "Entry", value: "entry" }, { label: "Mid-level", value: "mid" }, { label: "Senior", value: "senior" }, { label: "Lead", value: "lead" }]} value={filters.experienceLevel} />
      <FilterPill icon="category" label="Category" onChange={() => undefined} options={[{ label: "All categories", value: "all" }, { label: "Operations & strategy", value: "all" }]} value="all" />
      <FilterPill icon="tune" label="More filters" onChange={(value) => updateFilter("datePosted", value)} options={[{ label: "Any time", value: "all" }, { label: "Past 24 hours", value: "24h" }, { label: "Past 7 days", value: "7d" }, { label: "Salary published", value: "30d" }]} value={filters.datePosted} />
      <button className="jobs-search-link" onClick={() => setFeedback("Search saved to your Runr workspace.")} type="button"><Icon>favorite</Icon>Save search</button>
      {activeFilterCount ? <button className="jobs-search-link jobs-search-link--muted" onClick={clearFilters} type="button">Clear all filters</button> : null}
    </section>

    {feedback ? <div className="jobs-feedback" role="status"><Icon>check_circle</Icon>{feedback}<button aria-label="Dismiss" onClick={() => setFeedback("")} type="button"><Icon>close</Icon></button></div> : null}

    <div className="jobs-workspace">
      <aside className="jobs-list-panel">
        <div className="jobs-list-panel__header"><strong>Showing {jobs.length} of {PREVIEW_JOBS.length} jobs</strong><label><span className="jobs-switch"><input checked={filters.sort === "newest"} onChange={(event) => updateFilter("sort", event.target.checked ? "newest" : "best")} type="checkbox" /><span /></span>Most recent</label></div>
        <div className="jobs-list-panel__body">
          {jobs.length ? jobs.map((job) => <JobListCard isSaved={Boolean(dispositions.saved?.[job.id] ?? job.saved)} job={job} key={job.id} onSave={saveJob} onSelect={() => { setSelectedJobId(job.id); setActiveTab("overview"); }} selected={selectedJob?.id === job.id} />) : <div className="jobs-empty"><Icon>search_off</Icon><strong>No jobs match</strong><span>Clear a filter to see more roles.</span><button className="jobs-outline-button" onClick={clearFilters} type="button">Clear filters</button></div>}
        </div>
      </aside>

      <section className="jobs-detail-panel">
        {selectedJob ? <>
          <div className="jobs-detail-toolbar"><div className="jobs-detail-tabs"><button className={activeTab === "overview" ? "is-active" : ""} onClick={() => setActiveTab("overview")} type="button">Overview</button><button className={activeTab === "company" ? "is-active" : ""} onClick={() => setActiveTab("company")} type="button">Company</button></div><div className="jobs-detail-toolbar__actions">{initialJobId ? <Link className="jobs-back-link" to="/jobs"><Icon>arrow_back</Icon>Back to jobs</Link> : null}<button className="jobs-text-link" onClick={() => setFeedback("This preview role has not been marked as applied.")} type="button">Already applied?</button><button className={isSaved ? "jobs-outline-button is-selected" : "jobs-outline-button"} onClick={() => saveJob(selectedJob)} type="button"><Icon style={isSaved ? { fontVariationSettings: "'FILL' 1" } : undefined}>bookmark</Icon>{isSaved ? "Saved" : "Save"}</button><button className="jobs-primary-button" onClick={prepareApplication} type="button"><Icon>bolt</Icon>Apply</button></div></div>
          <div className="jobs-detail-scroll">
            {activeTab === "company" ? <CompanyOverview job={selectedJob} onOpenNetwork={openNetwork} /> : <JobOverview job={selectedJob} onOpenNetwork={openNetwork} onPrepare={prepareApplication} />}
            {preparing ? <section className="jobs-preparation-panel"><div><span className="jobs-eyebrow">Application preparation</span><h2>Make this application easier with Runr</h2><p>Preview the tools Runr can use to tailor your CV, motivation letter, and application answers for this role.</p></div><div className="jobs-preparation-actions"><button className="jobs-outline-button" onClick={() => setUpgradeFeature("tailored_cv")} type="button"><Icon>description</Icon>Tailored CV</button><button className="jobs-outline-button" onClick={() => setUpgradeFeature("tailored_motivation_letter")} type="button"><Icon>edit_note</Icon>Motivation letter</button></div></section> : null}
          </div>
        </> : <div className="jobs-empty jobs-empty--detail"><Icon>work_off</Icon><strong>Select a job</strong><span>Choose a role from the shortlist to see details.</span></div>}
      </section>
    </div>
    <PreviewUpgradeModal featureKey={upgradeFeature} onClose={() => setUpgradeFeature("")} />
    {networkModal ? <HiringManagersModal mode={networkModal} onClose={() => setNetworkModal("")} /> : null}
  </div>;
}
