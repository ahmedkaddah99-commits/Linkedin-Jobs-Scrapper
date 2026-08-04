import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import PreviewBadge from "../components/personalized/PreviewBadge";
import { PREVIEW_FEED_SUMMARY, getHiddenReasonGroups } from "../lib/personalizedJobs";
import { logPersonalizedEvent } from "../lib/personalizedAnalytics";
import { usePreviewDispositions } from "../lib/personalizedPreviewState";

function HiddenJobRow({ job, onReport, onRestore }) {
  return (
    <div className="preview-hidden-job">
      <div className="preview-company-mark preview-company-mark--small" aria-hidden="true">{job.company.slice(0, 1)}</div>
      <div className="min-w-0 flex-1">
        <Link className="preview-hidden-job__title" to={`/jobs/${job.id}`}>{job.title}</Link>
        <p>{job.company} · {job.location} · Estimated match {job.matchScore}%</p>
      </div>
      <div className="preview-hidden-job__actions">
        <button className="preview-text-button preview-text-button--muted" onClick={() => onReport(job)} type="button">Report incorrect</button>
        <button className="preview-button preview-button--secondary" onClick={() => onRestore(job)} type="button">Show this job</button>
      </div>
    </div>
  );
}

export default function HiddenJobsPage() {
  const [openGroup, setOpenGroup] = useState("language_requirement");
  const [reportedJob, setReportedJob] = useState("");
  const [preferenceNote, setPreferenceNote] = useState("");
  const { dispositions, restoreJob } = usePreviewDispositions();
  const groups = useMemo(() => getHiddenReasonGroups().map((group) => ({ ...group, jobs: group.jobs.filter((job) => !dispositions.restored?.[job.id]) })).filter((group) => group.jobs.length), [dispositions.restored]);
  const locallyHidden = Object.keys(dispositions.hidden || {});

  function handleRestore(job) {
    restoreJob(job.id);
    logPersonalizedEvent("job_restored", { route: "/jobs/hidden", jobPreviewId: job.id });
    setPreferenceNote(`${job.title} is now shown in your feed for this preview session.`);
  }

  function handleReport(job) {
    setReportedJob(job.id);
    setPreferenceNote("Thanks — this report stays local to the preview and is not sent to a backend yet.");
  }

  function handlePreferenceChange(group, value) {
    setPreferenceNote(`${group.label} preference set to “${value}” locally for this preview. No production profile field was changed.`);
  }

  return (
    <div className="preview-page">
      <header className="preview-page-header">
        <div>
          <div className="preview-header-kicker"><span className="material-symbols-outlined">visibility_off</span>Eligibility review</div>
          <h1>Hidden jobs</h1>
          <p>Runr keeps jobs that look promising but do not currently fit your eligibility preferences out of the main feed. You stay in control.</p>
        </div>
        <div className="preview-page-header__actions"><PreviewBadge /><Link className="preview-button preview-button--secondary" to="/jobs"><span className="material-symbols-outlined text-[17px]">arrow_back</span>Back to jobs</Link></div>
      </header>

      <section className="preview-hidden-summary">
        <div className="preview-hidden-summary__icon"><span className="material-symbols-outlined">filter_alt</span></div>
        <div><p className="preview-eyebrow">A cleaner feed</p><h2>{PREVIEW_FEED_SUMMARY.hiddenJobs} jobs hidden by your eligibility preferences</h2><p>Showing {groups.reduce((total, group) => total + group.jobs.length, 0)} representative hidden jobs in this deterministic preview.</p></div>
        <PreviewBadge />
      </section>

      {preferenceNote ? <div className="preview-feedback" role="status"><span className="material-symbols-outlined">info</span>{preferenceNote}</div> : null}
      {reportedJob ? <p className="sr-only" aria-live="polite">Report recorded for {reportedJob}</p> : null}

      <section className="preview-hidden-groups">
        <div className="preview-section-heading"><div><p className="preview-eyebrow">Understand the decision</p><h2>Why jobs were hidden</h2></div><span className="preview-section-count">{groups.length} reasons</span></div>
        {groups.map((group) => {
          const isOpen = openGroup === group.code;
          return (
            <article className={["preview-hidden-group", isOpen ? "is-open" : ""].join(" ")} key={group.code}>
              <button aria-expanded={isOpen} className="preview-hidden-group__header" onClick={() => { setOpenGroup(isOpen ? "" : group.code); logPersonalizedEvent("hidden_jobs_opened", { route: "/jobs/hidden", featureKey: group.code }); }} type="button">
                <span className="preview-hidden-group__marker"><span className="material-symbols-outlined">{group.code === "language_requirement" ? "translate" : group.code === "location" ? "location_on" : group.code === "experience" ? "trending_up" : group.code === "low_relevance" ? "low_priority" : "help"}</span></span>
                <span className="min-w-0 flex-1 text-left"><strong>{group.label}</strong><span>{group.explanation}</span></span>
                <span className="preview-hidden-group__count">{group.count}</span>
                <span className="material-symbols-outlined">{isOpen ? "expand_less" : "expand_more"}</span>
              </button>
              {isOpen ? (
                <div className="preview-hidden-group__body">
                  <div className="preview-preference-row">
                    <label><span>Change this preview preference</span><select defaultValue="Current preference" onChange={(event) => handlePreferenceChange(group, event.target.value)}><option>Current preference</option><option>More flexible</option><option>Strict</option></select></label>
                    <span className="preview-local-label"><span className="material-symbols-outlined text-[14px]">lock_open</span>Local preview only</span>
                  </div>
                  {group.jobs.map((job) => <HiddenJobRow job={job} key={job.id} onReport={handleReport} onRestore={handleRestore} />)}
                </div>
              ) : null}
            </article>
          );
        })}
      </section>

      {locallyHidden.length ? (
        <section className="preview-side-card preview-local-hides">
          <div className="preview-side-card__heading"><span className="material-symbols-outlined">undo</span><h2>Recently hidden by you</h2></div>
          <p>These local preview actions are separate from eligibility filtering. Restore them whenever you change your mind.</p>
          <Link className="preview-link-button" to="/jobs">Undo from the jobs feed <span className="material-symbols-outlined text-[16px]">arrow_forward</span></Link>
        </section>
      ) : null}
    </div>
  );
}

