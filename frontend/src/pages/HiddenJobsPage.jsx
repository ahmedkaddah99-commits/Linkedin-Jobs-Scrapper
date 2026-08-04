import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import PreviewBadge from "../components/personalized/PreviewBadge";
import { PREVIEW_FEED_SUMMARY, PREVIEW_JOBS, getHiddenReasonGroups } from "../lib/personalizedJobs";
import { logPersonalizedEvent } from "../lib/personalizedAnalytics";
import { usePreviewDispositions } from "../lib/personalizedPreviewState";

function HiddenJobRow({ job, onReport, onRestore }) {
  return <div className="preview-hidden-job"><div className="preview-company-mark preview-company-mark--small" aria-hidden="true">{job.company.slice(0, 1)}</div><div className="min-w-0 flex-1"><Link className="preview-hidden-job__title" to={`/jobs/${job.id}`}>{job.title}</Link><p>{job.company} · {job.location} · Estimated match {job.matchScore}%</p></div><div className="preview-hidden-job__actions"><button aria-label={`Report incorrect filtering for ${job.title}`} className="preview-text-button preview-text-button--muted" onClick={() => onReport(job)} type="button">Report incorrect</button><button className="preview-button preview-button--secondary" onClick={() => onRestore(job)} type="button">{job.hidden ? "Show this job" : "Undo hide"}</button></div></div>;
}

function ReasonIcon({ code }) {
  return <span className="preview-hidden-group__marker"><span className="material-symbols-outlined">{code === "language_requirement" ? "translate" : code === "location" ? "location_on" : code === "experience" ? "trending_up" : code === "low_relevance" ? "low_priority" : code === "local_hidden" ? "visibility_off" : "help"}</span></span>;
}

export default function HiddenJobsPage() {
  const [openGroup, setOpenGroup] = useState("language_requirement");
  const [reportedJob, setReportedJob] = useState("");
  const [preferenceNote, setPreferenceNote] = useState("");
  const [preferenceValues, setPreferenceValues] = useState({});
  const { dispositions, restoreJob } = usePreviewDispositions();
  const locallyHiddenIds = useMemo(() => new Set(Object.keys(dispositions.hidden || {})), [dispositions.hidden]);
  const groups = useMemo(() => getHiddenReasonGroups().map((group) => ({ ...group, jobs: group.jobs.filter((job) => !dispositions.restored?.[job.id] && !locallyHiddenIds.has(job.id)) })).filter((group) => group.jobs.length), [dispositions.restored, locallyHiddenIds]);
  const locallyHiddenJobs = useMemo(() => PREVIEW_JOBS.filter((job) => locallyHiddenIds.has(job.id)), [locallyHiddenIds]);
  const hiddenCount = groups.reduce((total, group) => total + group.jobs.length, 0) + locallyHiddenJobs.length;

  useEffect(() => {
    logPersonalizedEvent("hidden_jobs_opened", { route: "/jobs" });
  }, []);

  function handleRestore(job) {
    restoreJob(job.id);
    logPersonalizedEvent("job_restored", { route: "/jobs/hidden", jobPreviewId: job.id });
    setPreferenceNote(`${job.title} is now shown in your feed for this preview session.`);
  }

  function handleReport(job) {
    setReportedJob(job.id);
    setPreferenceNote(`Thanks. Your report about ${job.title} is recorded only in this preview; it was not sent to a backend.`);
  }

  function handlePreferenceChange(group, value) {
    setPreferenceValues((current) => ({ ...current, [group.code]: value }));
    setPreferenceNote(`${group.label} is now set to “${value}” for this preview. No production profile field was changed.`);
  }

  function toggleGroup(code) {
    setOpenGroup((current) => current === code ? "" : code);
    logPersonalizedEvent("hidden_jobs_opened", { route: "/jobs/hidden", featureKey: code });
  }

  function renderGroup(group, isLocal = false) {
    const isOpen = openGroup === group.code;
    return <article className={["preview-hidden-group", isOpen ? "is-open" : ""].join(" ")} key={group.code}><button aria-expanded={isOpen} className="preview-hidden-group__header" onClick={() => toggleGroup(group.code)} type="button"><ReasonIcon code={group.code} /><span className="min-w-0 flex-1 text-left"><strong>{group.label}</strong><span>{group.explanation}</span></span><span className="preview-hidden-group__count">{group.count}</span><span className="material-symbols-outlined">{isOpen ? "expand_less" : "expand_more"}</span></button>{isOpen ? <div className="preview-hidden-group__body"><div className="preview-preference-row"><label><span>{isLocal ? "Change this preview action" : "Change this preview preference"}</span><select onChange={(event) => handlePreferenceChange(group, event.target.value)} value={preferenceValues[group.code] || "Current preference"}><option>Current preference</option><option>More flexible</option><option>Strict</option></select></label><span className="preview-local-label"><span className="material-symbols-outlined text-[14px]">lock_open</span>Local preview only</span></div>{group.jobs.map((job) => <HiddenJobRow job={job} key={job.id} onReport={handleReport} onRestore={handleRestore} />)}</div> : null}</article>;
  }

  return <div className="preview-page"><header className="preview-page-header"><div><div className="preview-header-kicker"><span className="material-symbols-outlined">visibility_off</span>Eligibility review</div><h1>Hidden jobs</h1><p>Runr keeps jobs that may not fit your language, location or work-authorization situation out of the main feed. You stay in control.</p></div><div className="preview-page-header__actions"><PreviewBadge /><Link className="preview-button preview-button--secondary" to="/jobs"><span className="material-symbols-outlined text-[17px]">arrow_back</span>Back to jobs</Link></div></header>

    <section className="preview-hidden-summary"><div className="preview-hidden-summary__icon"><span className="material-symbols-outlined">filter_alt</span></div><div><p className="preview-eyebrow">A cleaner feed</p><h2>{PREVIEW_FEED_SUMMARY.hiddenJobs} jobs hidden because they may not fit your eligibility preferences</h2><p>Showing {hiddenCount} representative hidden jobs in this preview.</p></div><PreviewBadge /></section>
    {preferenceNote ? <div className="preview-feedback" role="status"><span className="material-symbols-outlined">info</span>{preferenceNote}</div> : null}
    {reportedJob ? <p className="sr-only" aria-live="polite">Report recorded for {reportedJob}</p> : null}

    <section className="preview-hidden-groups"><div className="preview-section-heading"><div><p className="preview-eyebrow">Understand the decision</p><h2>Why jobs were hidden</h2></div><span className="preview-section-count">{groups.length + (locallyHiddenJobs.length ? 1 : 0)} reasons</span></div>{groups.map((group) => renderGroup(group))}{locallyHiddenJobs.length ? renderGroup({ code: "local_hidden", label: "Hidden by you", explanation: "These jobs were removed from your feed by a local preview action.", count: locallyHiddenJobs.length, jobs: locallyHiddenJobs }, true) : null}</section>
    <section className="preview-hidden-help preview-side-card"><div className="preview-side-card__heading"><span className="material-symbols-outlined">fact_check</span><h2>Something look wrong?</h2></div><p>Open a job, review the evidence, then report an incorrect filtering result. Reports in this preview stay local until a reporting service exists.</p><Link className="preview-link-button" to="/jobs">Return to the shortlist <span className="material-symbols-outlined text-[16px]">arrow_forward</span></Link></section>
  </div>;
}
