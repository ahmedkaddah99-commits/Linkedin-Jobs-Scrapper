import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import JobCard from "../components/personalized/JobCard";
import PreviewBadge from "../components/personalized/PreviewBadge";
import PreviewUpgradeModal from "../components/personalized/PreviewUpgradeModal";
import PostOnboardingProOffer from "../components/personalized/PostOnboardingProOffer";
import {
  PREVIEW_ENTITLEMENTS,
  PREVIEW_FEED_SUMMARY,
  formatPreviewTimestamp,
  getActivePreviewFilterCount,
  getFeedJobs,
} from "../lib/personalizedJobs";
import { usePreviewDispositions } from "../lib/personalizedPreviewState";
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
  return <label className="preview-filter-field"><span>{label}</span><select onChange={(event) => onChange(event.target.value)} value={value}>{options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>;
}

function ValueMetric({ label, value, tone = "blue" }) {
  return <div className={["preview-metric", `preview-metric--${tone}`].join(" ")}><span className="material-symbols-outlined">{tone === "teal" ? "verified" : tone === "orange" ? "fiber_new" : tone === "purple" ? "visibility_off" : "auto_awesome"}</span><div><strong>{value}</strong><span>{label}</span></div></div>;
}

export default function PersonalizedJobsPage() {
  const { user } = useSession();
  const [filters, setFilters] = useState(INITIAL_FILTERS);
  const [upgradeFeature, setUpgradeFeature] = useState("");
  const [feedback, setFeedback] = useState(null);
  const [jobsReadyAt, setJobsReadyAt] = useState(null);
  const { dispositions, hideJob, restoreJob, toggleSaved } = usePreviewDispositions();
  const jobs = useMemo(() => getFeedJobs({ filters, dispositions }), [dispositions, filters]);
  const activeFilterCount = getActivePreviewFilterCount(filters);

  useEffect(() => {
    logPersonalizedEvent("jobs_feed_viewed", { route: "/jobs" });
    setJobsReadyAt(Date.now());
  }, []);

  function updateFilter(name, value) {
    setFilters((current) => ({ ...current, [name]: value }));
    setFeedback(null);
    logPersonalizedEvent("jobs_filter_changed", { route: "/jobs", filterName: name });
  }

  function clearFilters() {
    setFilters(INITIAL_FILTERS);
    setFeedback({ message: "Filters cleared. Showing the full preview shortlist." });
    logPersonalizedEvent("jobs_filter_changed", { route: "/jobs", filterName: "clear_all" });
  }

  function handleSave(job) {
    const wasSaved = Boolean(dispositions.saved?.[job.id] ?? job.saved);
    toggleSaved(job.id, wasSaved);
    logPersonalizedEvent("job_saved", { route: "/jobs", jobPreviewId: job.id });
    setFeedback({ message: wasSaved ? `${job.title} was removed from your saved jobs.` : `${job.title} was saved for this preview session.` });
  }

  function handleHide(job) {
    hideJob(job.id);
    logPersonalizedEvent("job_hidden", { route: "/jobs", jobPreviewId: job.id });
    setFeedback({ message: `${job.title} is hidden for this preview session.`, actionLabel: "Undo", action: () => { restoreJob(job.id); logPersonalizedEvent("job_restored", { route: "/jobs", jobPreviewId: job.id }); setFeedback({ message: `${job.title} is back in your shortlist.` }); } });
  }

  function handleEligibilityClick() {
    logPersonalizedEvent("eligibility_filter_clicked", { route: "/jobs", featureKey: "ai_eligibility_filter" });
    if (!PREVIEW_ENTITLEMENTS.ai_eligibility_filter.available) {
      setUpgradeFeature("ai_eligibility_filter");
      return;
    }
    updateFilter("onlyEligible", !filters.onlyEligible);
  }

  return <div className="preview-page">
    <PostOnboardingProOffer feedReady={Boolean(jobsReadyAt)} jobsReadyAt={jobsReadyAt} summary={PREVIEW_FEED_SUMMARY} user={user} />
    <header className="preview-page-header">
      <div>
        <div className="preview-header-kicker"><span className="material-symbols-outlined">sparkles</span>Personalized job search</div>
        <h1>Jobs selected for you</h1>
        <p>Runr compares your preferences, eligibility and profile with each job so you can focus on the opportunities that fit best.</p>
      </div>
      <div className="preview-page-header__actions"><PreviewBadge /><Link className="preview-button preview-button--secondary" to="/onboarding"><span className="material-symbols-outlined text-[17px]">tune</span>Update preferences</Link></div>
    </header>

    <div className="preview-feed-meta"><span><span className="material-symbols-outlined">update</span>Updated {formatPreviewTimestamp(PREVIEW_FEED_SUMMARY.generatedAt)}</span><span>Based on your current profile</span><Link to="/jobs/hidden"><span className="material-symbols-outlined">visibility_off</span>{PREVIEW_FEED_SUMMARY.hiddenJobs} jobs hidden because they may not fit your eligibility preferences</Link></div>

    <section className="preview-metrics-grid" aria-label="Preview value metrics"><ValueMetric label="Jobs found for you" value={PREVIEW_FEED_SUMMARY.totalFound.toLocaleString()} tone="blue" /><ValueMetric label="Strong matches" value={PREVIEW_FEED_SUMMARY.strongMatches} tone="teal" /><ValueMetric label="Jobs hidden by eligibility" value={PREVIEW_FEED_SUMMARY.hiddenJobs} tone="purple" /><ValueMetric label="New since last update" value={PREVIEW_FEED_SUMMARY.newSinceLastVisit} tone="orange" /></section>
    <p className="preview-metric-note"><span className="material-symbols-outlined">info</span><strong>Preview data.</strong> These figures are example values for this frontend preview.</p>

    <section className="preview-filter-panel" aria-label="Job filters">
      <div className="preview-filter-search"><span className="material-symbols-outlined">search</span><input aria-label="Search jobs" onChange={(event) => updateFilter("query", event.target.value)} placeholder="Search title, company, or skill" type="search" value={filters.query} /></div>
      <div className="preview-filter-grid"><SelectFilter label="Location" onChange={(value) => updateFilter("location", value)} options={[{ label: "All locations", value: "all" }, { label: "Berlin", value: "berlin" }, { label: "Remote in Germany", value: "remote in germany" }]} value={filters.location} /><SelectFilter label="Work arrangement" onChange={(value) => updateFilter("workArrangement", value)} options={[{ label: "Any arrangement", value: "all" }, { label: "Remote", value: "remote" }, { label: "Hybrid", value: "hybrid" }, { label: "On-site", value: "onsite" }]} value={filters.workArrangement} /><SelectFilter label="Date posted" onChange={(value) => updateFilter("datePosted", value)} options={[{ label: "Any time", value: "all" }, { label: "Past 24 hours", value: "24h" }, { label: "Past 7 days", value: "7d" }, { label: "Past 30 days", value: "30d" }]} value={filters.datePosted} /><SelectFilter label="Experience level" onChange={(value) => updateFilter("experienceLevel", value)} options={[{ label: "Any experience", value: "all" }, { label: "Entry", value: "entry" }, { label: "Mid-level", value: "mid" }, { label: "Senior", value: "senior" }, { label: "Lead", value: "lead" }]} value={filters.experienceLevel} /><SelectFilter label="Salary" onChange={(value) => updateFilter("salary", value)} options={[{ label: "Any salary", value: "all" }, { label: "Salary published", value: "known" }, { label: "EUR 70k minimum", value: "70k" }]} value={filters.salary} /><SelectFilter label="Sort by" onChange={(value) => updateFilter("sort", value)} options={[{ label: "Best match", value: "best" }, { label: "Newest", value: "newest" }, { label: "Salary, when available", value: "salary" }]} value={filters.sort} /></div>
      <div className="preview-filter-footer"><button aria-pressed={filters.onlyEligible} className={["preview-toggle", filters.onlyEligible ? "is-on" : ""].join(" ")} onClick={handleEligibilityClick} type="button"><span className="preview-toggle__track"><span /></span><span>Only show jobs I qualify for</span><span className="preview-lock-label"><span className="material-symbols-outlined text-[14px]">lock</span>Pro preview</span></button><div className="preview-filter-result"><span>{jobs.length} preview examples shown</span>{activeFilterCount ? <button className="preview-link-button" onClick={clearFilters} type="button">Clear filters ({activeFilterCount})</button> : null}</div></div>
    </section>

    {feedback ? <div className="preview-feedback" role="status"><span className="material-symbols-outlined">check_circle</span><span>{feedback.message}</span>{feedback.action ? <button className="preview-feedback__action" onClick={feedback.action} type="button">{feedback.actionLabel}</button> : null}</div> : null}

    <div className="preview-feed-layout"><main className="preview-feed-list"><div className="preview-section-heading"><div><p className="preview-eyebrow">Your shortlist</p><h2>Best matches right now</h2><p className="preview-section-description">Each card shows what Runr found, why it matters and what you can do next.</p></div><span className="preview-section-count">{jobs.length}</span></div>{jobs.length ? jobs.map((job) => <JobCard isSaved={Boolean(dispositions.saved?.[job.id] ?? job.saved)} job={job} key={job.id} onHide={handleHide} onSave={handleSave} />) : <div className="preview-empty-state"><span className="material-symbols-outlined">search_off</span><h2>No jobs match these filters</h2><p>Try clearing one filter or search for a broader title, company or skill.</p><button className="preview-button preview-button--secondary" onClick={clearFilters} type="button">Clear filters</button></div>}</main></div>

    <section className="preview-next-actions" aria-label="Next steps"><div><p className="preview-eyebrow">Keep moving</p><h2>Choose what would save you the most time</h2></div><div className="preview-next-actions__grid"><article><span className="material-symbols-outlined">schedule</span><div><h3>Keep your search fresh</h3><p>Refresh saved searches automatically and surface newly discovered opportunities.</p><button className="preview-link-button" onClick={() => setUpgradeFeature("scheduled_job_searches")} type="button">Explore scheduled searches <span className="material-symbols-outlined text-[16px]">lock</span></button></div></article><article><span className="material-symbols-outlined">tune</span><div><h3>Search another direction</h3><p>Keep a different role family or location in view without losing this shortlist.</p><button className="preview-link-button" onClick={() => setUpgradeFeature("multiple_active_searches")} type="button">See multiple searches <span className="material-symbols-outlined text-[16px]">lock</span></button></div></article></div></section>

    <PreviewUpgradeModal featureKey={upgradeFeature} onClose={() => setUpgradeFeature("")} />
  </div>;
}
