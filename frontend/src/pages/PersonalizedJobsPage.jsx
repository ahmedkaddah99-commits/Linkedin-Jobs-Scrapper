import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import JobCard from "../components/personalized/JobCard";
import PreviewBadge from "../components/personalized/PreviewBadge";
import PreviewUpgradeModal from "../components/personalized/PreviewUpgradeModal";
import {
  PREVIEW_ENTITLEMENTS,
  PREVIEW_FEED_SUMMARY,
  getFeedJobs,
} from "../lib/personalizedJobs";
import { usePreviewDispositions, loadUpgradeDismissals } from "../lib/personalizedPreviewState";
import { logPersonalizedEvent } from "../lib/personalizedAnalytics";

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

function SelectFilter({ label, onChange, options, value }) {
  return (
    <label className="preview-filter-field">
      <span>{label}</span>
      <select onChange={(event) => onChange(event.target.value)} value={value}>
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  );
}

function ValueMetric({ label, value, tone = "blue" }) {
  return (
    <div className={["preview-metric", `preview-metric--${tone}`].join(" ")}>
      <span className="material-symbols-outlined">{tone === "teal" ? "verified" : tone === "orange" ? "filter_alt" : "auto_awesome"}</span>
      <div>
        <strong>{value}</strong>
        <span>{label}</span>
      </div>
    </div>
  );
}

export default function PersonalizedJobsPage() {
  const [filters, setFilters] = useState(INITIAL_FILTERS);
  const [upgradeFeature, setUpgradeFeature] = useState("");
  const [feedback, setFeedback] = useState("");
  const { dispositions, hideJob, toggleSaved } = usePreviewDispositions();
  const filterInitialized = useRef(false);
  const jobs = useMemo(() => getFeedJobs({ filters, dispositions }), [dispositions, filters]);

  useEffect(() => {
    logPersonalizedEvent("jobs_feed_viewed", { route: "/jobs" });
  }, []);

  useEffect(() => {
    if (!filterInitialized.current) {
      filterInitialized.current = true;
      return;
    }
    logPersonalizedEvent("jobs_filter_changed", { route: "/jobs", filterName: "jobs_feed_filters" });
  }, [filters]);

  function updateFilter(name, value) {
    setFilters((current) => ({ ...current, [name]: value }));
    setFeedback("");
  }

  function handleSave(job) {
    toggleSaved(job.id);
    logPersonalizedEvent("job_saved", { route: "/jobs", jobPreviewId: job.id });
    setFeedback(`${job.title} ${dispositions.saved?.[job.id] || job.saved ? "removed from" : "saved to"} your list.`);
  }

  function handleHide(job) {
    hideJob(job.id);
    logPersonalizedEvent("job_hidden", { route: "/jobs", jobPreviewId: job.id });
    setFeedback(`${job.title} is hidden for this preview session. You can undo it from Hidden jobs.`);
  }

  function handleEligibilityClick() {
    logPersonalizedEvent("eligibility_filter_clicked", { route: "/jobs", featureKey: "ai_eligibility_filter" });
    if (!PREVIEW_ENTITLEMENTS.ai_eligibility_filter.available && !loadUpgradeDismissals().ai_eligibility_filter) {
      setUpgradeFeature("ai_eligibility_filter");
      return;
    }
    updateFilter("onlyEligible", !filters.onlyEligible);
  }

  return (
    <div className="preview-page">
      <header className="preview-page-header">
        <div>
          <div className="preview-header-kicker"><span className="material-symbols-outlined">sparkles</span>Personalized job search</div>
          <h1>Jobs selected for you</h1>
          <p>Runr compares your preferences, eligibility, and profile evidence with job descriptions so your next application starts with a better shortlist.</p>
        </div>
        <div className="preview-page-header__actions">
          <PreviewBadge />
          <Link className="preview-button preview-button--secondary" to="/onboarding">
            <span className="material-symbols-outlined text-[17px]">tune</span>
            Update preferences
          </Link>
        </div>
      </header>

      <div className="preview-feed-meta">
        <span><span className="material-symbols-outlined">update</span>Updated just now</span>
        <span>Based on your current profile</span>
        <Link to="/jobs/hidden"><span className="material-symbols-outlined">visibility_off</span>{PREVIEW_FEED_SUMMARY.hiddenJobs} jobs hidden by your eligibility preferences</Link>
      </div>

      <section className="preview-metrics-grid" aria-label="Preview value metrics">
        <ValueMetric label="Jobs analyzed today" value="1,284" tone="blue" />
        <ValueMetric label="Unsuitable jobs filtered" value="148" tone="teal" />
        <ValueMetric label="Application documents prepared this week" value="12" tone="orange" />
      </section>
      <p className="preview-metric-note"><span className="material-symbols-outlined">info</span>Preview data. These metrics are deterministic examples until the matching and analytics services are connected.</p>

      <section className="preview-filter-panel" aria-label="Job filters">
        <div className="preview-filter-search">
          <span className="material-symbols-outlined">search</span>
          <input aria-label="Search jobs" onChange={(event) => updateFilter("query", event.target.value)} placeholder="Search title, company, or skill" type="search" value={filters.query} />
        </div>
        <div className="preview-filter-grid">
          <SelectFilter label="Location" onChange={(value) => updateFilter("location", value)} options={[{ label: "All locations", value: "all" }, { label: "Berlin", value: "berlin" }, { label: "Remote in Germany", value: "remote in germany" }]} value={filters.location} />
          <SelectFilter label="Work arrangement" onChange={(value) => updateFilter("workArrangement", value)} options={[{ label: "Any arrangement", value: "all" }, { label: "Remote", value: "remote" }, { label: "Hybrid", value: "hybrid" }, { label: "On-site", value: "onsite" }]} value={filters.workArrangement} />
          <SelectFilter label="Date posted" onChange={(value) => updateFilter("datePosted", value)} options={[{ label: "Any time", value: "all" }, { label: "Past 24 hours", value: "24h" }, { label: "Past 7 days", value: "7d" }, { label: "Past 30 days", value: "30d" }]} value={filters.datePosted} />
          <SelectFilter label="Experience level" onChange={(value) => updateFilter("experienceLevel", value)} options={[{ label: "Any experience", value: "all" }, { label: "Entry", value: "entry" }, { label: "Mid-level", value: "mid" }, { label: "Senior", value: "senior" }, { label: "Lead", value: "lead" }]} value={filters.experienceLevel} />
          <SelectFilter label="Salary" onChange={(value) => updateFilter("salary", value)} options={[{ label: "Any salary", value: "all" }, { label: "Salary published", value: "known" }, { label: "€70k minimum", value: "70k" }]} value={filters.salary} />
          <SelectFilter label="Sort by" onChange={(value) => updateFilter("sort", value)} options={[{ label: "Best match", value: "best" }, { label: "Newest", value: "newest" }, { label: "Salary, when available", value: "salary" }]} value={filters.sort} />
        </div>
        <div className="preview-filter-footer">
          <button aria-pressed={filters.onlyEligible} className={["preview-toggle", filters.onlyEligible ? "is-on" : ""].join(" ")} onClick={handleEligibilityClick} type="button">
            <span className="preview-toggle__track"><span /></span>
            <span>Only show jobs I qualify for</span>
            <span className="preview-lock-label"><span className="material-symbols-outlined text-[14px]">lock</span>Pro preview</span>
          </button>
          <span className="preview-filter-count">{jobs.length} preview jobs shown</span>
        </div>
      </section>

      {feedback ? <div className="preview-feedback" role="status"><span className="material-symbols-outlined">check_circle</span>{feedback}</div> : null}

      <div className="preview-feed-layout">
        <main className="preview-feed-list">
          <div className="preview-section-heading">
            <div><p className="preview-eyebrow">Your shortlist</p><h2>Best matches right now</h2></div>
            <span className="preview-section-count">{jobs.length}</span>
          </div>
          {jobs.length ? jobs.map((job) => (
            <JobCard isSaved={Boolean(dispositions.saved?.[job.id] || job.saved)} job={job} key={job.id} onHide={handleHide} onSave={handleSave} />
          )) : (
            <div className="preview-empty-state"><span className="material-symbols-outlined">search_off</span><h2>No jobs match these filters</h2><p>Try a broader search or reset a filter to see more preview jobs.</p><button className="preview-button preview-button--secondary" onClick={() => setFilters(INITIAL_FILTERS)} type="button">Reset filters</button></div>
          )}
        </main>

        <aside className="preview-feed-sidebar">
          <section className="preview-side-card preview-side-card--accent">
            <span className="material-symbols-outlined preview-side-card__icon">auto_awesome</span>
            <p className="preview-eyebrow">Next best step</p>
            <h2>Make your shortlist application-ready</h2>
            <p>Use your strongest profile evidence to prepare a focused CV and motivation letter for the jobs you choose.</p>
            <Link className="preview-button preview-button--primary preview-button--full" to="/jobs/preview-aurora-product-ops?prepare=1">Prepare an application <span className="material-symbols-outlined text-[17px]">arrow_forward</span></Link>
          </section>
          <section className="preview-side-card">
            <div className="preview-side-card__heading"><span className="material-symbols-outlined">schedule</span><h2>Keep your search fresh</h2></div>
            <p>Preview a daily refresh that looks for new matches while you focus on the applications worth your time.</p>
            <button className="preview-link-button" onClick={() => setUpgradeFeature("scheduled_job_searches")} type="button">Explore scheduled searches <span className="material-symbols-outlined text-[16px]">lock</span></button>
          </section>
          <section className="preview-side-card preview-side-card--quiet">
            <p className="preview-eyebrow">Looking for something else?</p>
            <h2>Run a separate job search</h2>
            <p>Keep another role family or location in view with multiple active searches.</p>
            <button className="preview-link-button" onClick={() => setUpgradeFeature("multiple_active_searches")} type="button">See how it works <span className="material-symbols-outlined text-[16px]">arrow_forward</span></button>
          </section>
        </aside>
      </div>

      <PreviewUpgradeModal featureKey={upgradeFeature} onClose={() => setUpgradeFeature("")} />
    </div>
  );
}

