import { Link } from "react-router-dom";
import { formatPreviewDate } from "../../lib/personalizedJobs";

function EligibilityPill({ job }) {
  const eligible = job.eligibilityStatus === "eligible";
  return (
    <span className={["preview-status-pill", eligible ? "preview-status-pill--eligible" : "preview-status-pill--warning"].join(" ")}>
      <span className="material-symbols-outlined text-[15px]">{eligible ? "check_circle" : "visibility_off"}</span>
      {eligible ? "You qualify" : job.hiddenReasonLabel || "Needs review"}
    </span>
  );
}

export default function JobCard({ job, isSaved, onSave, onHide }) {
  return (
    <article className="preview-job-card">
      <div className="preview-job-card__topline">
        <div className="preview-company-mark" aria-hidden="true">
          {job.company.slice(0, 1)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Link className="preview-job-card__title" to={`/jobs/${job.id}`}>
              {job.title}
            </Link>
            {job.applicationStatus !== "Not started" ? <span className="preview-mini-pill">{job.applicationStatus}</span> : null}
          </div>
          <p className="preview-job-card__company">{job.company}</p>
        </div>
        <button
            aria-label={isSaved ? `Unsave ${job.title}` : `Save ${job.title}`}
          aria-pressed={isSaved}
          className={["preview-icon-button", isSaved ? "is-active" : ""].join(" ")}
          onClick={() => onSave(job)}
          title={isSaved ? "Unsave job" : "Save job"}
          type="button"
        >
          <span className="material-symbols-outlined" style={isSaved ? { fontVariationSettings: "'FILL' 1" } : undefined}>bookmark</span>
        </button>
      </div>

      <div className="preview-job-card__meta">
        <span><span className="material-symbols-outlined">location_on</span>{job.location}</span>
        <span><span className="material-symbols-outlined">{job.workArrangement === "remote" ? "wifi" : job.workArrangement === "hybrid" ? "sync_alt" : "business"}</span>{job.workArrangement === "onsite" ? "On-site" : job.workArrangement}</span>
        <span><span className="material-symbols-outlined">schedule</span>{formatPreviewDate(job.postedAt)}</span>
        {job.salary ? <span><span className="material-symbols-outlined">payments</span>{job.salary}</span> : <span><span className="material-symbols-outlined">payments</span>Salary not published</span>}
      </div>

      <p className="preview-job-card__summary">{job.descriptionSummary}</p>

      <div className="preview-job-card__score-row">
        <div>
          <span className="preview-match-score">{job.matchScore}%</span>
          <span className="preview-match-label">Estimated match</span>
          <small className="preview-match-context">Based on your current profile</small>
        </div>
        <EligibilityPill job={job} />
      </div>

      <div className="preview-job-card__reasons">
        {job.recommendationReasons.slice(0, 3).map((reason) => (
          <span key={reason}><span className="material-symbols-outlined">check</span>{reason}</span>
        ))}
        {job.missingQualifications.slice(0, 2).map((reason) => (
          <span className="is-warning" key={reason}><span className="material-symbols-outlined">info</span>{reason}</span>
        ))}
        {job.uncertainInformation.slice(0, 1).map((reason) => (
          <span className="is-uncertain" key={reason}><span className="material-symbols-outlined">help_outline</span>{reason}</span>
        ))}
      </div>

      <div className="preview-job-card__footer">
        <button aria-label={`Hide ${job.title}`} className="preview-text-button preview-text-button--muted" onClick={() => onHide(job)} title="Hide job from this preview" type="button">
          Hide
        </button>
        <Link className="preview-button preview-button--secondary" to={`/jobs/${job.id}`}>
          View details
        </Link>
        <Link className="preview-button preview-button--primary" to={`/jobs/${job.id}?prepare=1`}>
          Prepare application
          <span className="material-symbols-outlined text-[17px]">arrow_forward</span>
        </Link>
      </div>
    </article>
  );
}
