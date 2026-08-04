import { useEffect, useState } from "react";
import { Link, Navigate, useParams, useSearchParams } from "react-router-dom";
import PreviewBadge from "../components/personalized/PreviewBadge";
import PreviewUpgradeModal from "../components/personalized/PreviewUpgradeModal";
import ProvenanceTag from "../components/personalized/ProvenanceTag";
import { PREVIEW_JOBS, formatPreviewDate } from "../lib/personalizedJobs";
import { logPersonalizedEvent } from "../lib/personalizedAnalytics";
import { usePreviewDispositions } from "../lib/personalizedPreviewState";

function DetailLabel({ children, tone = "verified" }) {
  return <span className={["preview-detail-label", `preview-detail-label--${tone}`].join(" ")}>{children}</span>;
}

function DetailList({ items, tone = "verified", provenance }) {
  return <ul className={["preview-detail-list", `preview-detail-list--${tone}`].join(" ")}>{items.map((item) => <li key={item}><span className="material-symbols-outlined">{tone === "verified" ? "check_circle" : tone === "inferred" ? "auto_awesome" : "info"}</span><span>{item}</span>{provenance ? <ProvenanceTag kind={provenance.kind}>{provenance.label}</ProvenanceTag> : null}</li>)}</ul>;
}

function PreparationTool({ actionLabel, children, icon, locked, onClick, title }) {
  return <article className="preview-preparation-tool"><span className="preview-preparation-tool__icon material-symbols-outlined">{icon}</span><div><div className="preview-preparation-tool__title"><h3>{title}</h3>{locked ? <ProvenanceTag kind="preview">Preview</ProvenanceTag> : null}</div><p>{children}</p>{locked ? <button className="preview-link-button" onClick={onClick} type="button">{actionLabel}<span className="material-symbols-outlined text-[16px]">lock</span></button> : <button className="preview-link-button" onClick={onClick} type="button">{actionLabel}<span className="material-symbols-outlined text-[16px]">arrow_forward</span></button>}</div></article>;
}

export default function PersonalizedJobDetailPage() {
  const { jobId } = useParams();
  const [searchParams] = useSearchParams();
  const job = PREVIEW_JOBS.find((item) => item.id === jobId);
  const [upgradeFeature, setUpgradeFeature] = useState("");
  const [preparing, setPreparing] = useState(searchParams.get("prepare") === "1");
  const [feedback, setFeedback] = useState("");
  const { dispositions, hideJob, restoreJob, toggleSaved } = usePreviewDispositions();
  const isRestored = Boolean(dispositions.restored?.[jobId]);
  const isLocallyHidden = Boolean(dispositions.hidden?.[jobId]);
  const isSaved = Boolean(dispositions.saved?.[jobId] ?? job?.saved);
  const isHidden = Boolean(job?.hidden && !isRestored) || isLocallyHidden;

  useEffect(() => {
    if (job) logPersonalizedEvent("job_detail_viewed", { route: `/jobs/${job.id}`, jobPreviewId: job.id });
  }, [job]);

  if (!job) return <Navigate replace to="/jobs" />;

  function handleSave() {
    toggleSaved(job.id, isSaved);
    logPersonalizedEvent("job_saved", { route: `/jobs/${job.id}`, jobPreviewId: job.id });
    setFeedback(isSaved ? "Removed from your saved jobs." : "Saved to your jobs list for this preview session.");
  }

  function handleHideOrRestore() {
    if (isHidden) {
      restoreJob(job.id);
      logPersonalizedEvent("job_restored", { route: `/jobs/${job.id}`, jobPreviewId: job.id });
      setFeedback("This job is shown in your feed for the preview session.");
      return;
    }
    hideJob(job.id);
    logPersonalizedEvent("job_hidden", { route: `/jobs/${job.id}`, jobPreviewId: job.id });
    setFeedback("This job is hidden for the preview session. You can restore it from Hidden jobs.");
  }

  function locked(featureKey) {
    logPersonalizedEvent("locked_feature_clicked", { route: `/jobs/${job.id}`, jobPreviewId: job.id, featureKey });
    setUpgradeFeature(featureKey);
  }

  return <div className="preview-page preview-detail-page">
    <div className="preview-detail-back"><Link to="/jobs"><span className="material-symbols-outlined text-[18px]">arrow_back</span>Back to jobs</Link><PreviewBadge /></div>
    <header className="preview-detail-header"><div className="preview-company-mark preview-company-mark--large" aria-hidden="true">{job.company.slice(0, 1)}</div><div className="min-w-0 flex-1"><div className="preview-header-kicker">{job.source} <span>·</span> {formatPreviewDate(job.postedAt)}</div><h1>{job.title}</h1><p>{job.company} · {job.location} · {job.workArrangement === "onsite" ? "On-site" : job.workArrangement}</p></div><button aria-label={isSaved ? "Unsave job" : "Save job"} aria-pressed={isSaved} className={["preview-icon-button preview-icon-button--large", isSaved ? "is-active" : ""].join(" ")} onClick={handleSave} type="button"><span className="material-symbols-outlined" style={isSaved ? { fontVariationSettings: "'FILL' 1" } : undefined}>bookmark</span></button></header>

    <div className="preview-detail-actions"><button className="preview-button preview-button--primary" onClick={() => setPreparing(true)} type="button">Prepare an application <span className="material-symbols-outlined text-[17px]">arrow_forward</span></button><button className="preview-button preview-button--secondary" onClick={handleHideOrRestore} type="button">{isHidden ? "Show in feed" : "Hide job"}</button><span className="preview-detail-action-note"><span className="material-symbols-outlined">science</span>Preview actions stay local and do not change your production profile.</span></div>
    {feedback ? <div className="preview-feedback" role="status"><span className="material-symbols-outlined">check_circle</span>{feedback}</div> : null}

    {preparing ? <section className="preview-preparation-panel" id="application-preparation"><div className="preview-preparation-panel__header"><div><p className="preview-eyebrow">Application preparation</p><h2>See what Runr can prepare for this role</h2><p>Explore the tools first. A preview does not generate a document or submit an application.</p></div><PreviewBadge /></div><div className="preview-preparation-grid"><PreparationTool actionLabel="Unlock tailored CVs" icon="description" locked onClick={() => locked("tailored_cv")} title="Tailored CV">Emphasize the experience and skills most relevant to this position.</PreparationTool><PreparationTool actionLabel="Unlock motivation letters" icon="edit_note" locked onClick={() => locked("tailored_motivation_letter")} title="Tailored motivation letter">Create a job-specific letter grounded in your real career evidence.</PreparationTool><PreparationTool actionLabel="Review saved answers" icon="question_answer" onClick={() => setFeedback("Your saved answers stay in this preview until you choose to use them.")} title="Saved application answers">Reuse verified answers instead of completing the same questions repeatedly.</PreparationTool><PreparationTool actionLabel="Unlock Assisted Apply" icon="touch_app" locked onClick={() => locked("assisted_apply")} title="Assisted Apply">Help fill supported employer forms while you review every answer.</PreparationTool></div><p className="preview-preparation-panel__note"><span className="material-symbols-outlined">info</span>Preview only: no CV, letter or application has been generated yet.</p></section> : null}

    <div className="preview-detail-layout"><main className="preview-detail-main"><section className="preview-detail-card preview-detail-card--status"><div><div className="preview-detail-status-line"><DetailLabel tone={job.eligibilityStatus === "eligible" ? "verified" : "warning"}>{job.eligibilityStatus === "eligible" ? "Appears eligible" : job.hiddenReasonLabel || "Eligibility needs review"}</DetailLabel><ProvenanceTag kind="preview">Preview data</ProvenanceTag></div><h2>{job.matchScore}% <span>estimated match</span></h2><p>Based on your current profile and the information available in this preview listing. It is not a hiring prediction.</p></div><div className="preview-detail-score-ring" style={{ "--score": `${job.matchScore * 3.6}deg` }}><strong>{job.matchScore}</strong><span>/100</span></div></section>

      <section className="preview-detail-card"><div className="preview-detail-card__heading"><span className="material-symbols-outlined">description</span><div><p className="preview-eyebrow">What the employer shared</p><h2>About the role</h2></div><ProvenanceTag kind="employer">From the job description</ProvenanceTag></div><details className="preview-description-details" open><summary>Read the role description</summary><p className="preview-detail-description">{job.description}</p></details><div className="preview-verified-grid">{job.verifiedInformation.map((item) => <span key={item}><span className="material-symbols-outlined">check_circle</span>{item}</span>)}<span><span className="material-symbols-outlined">payments</span>{job.salary || "Salary not published"}</span></div><p className="preview-detail-footnote"><ProvenanceTag kind={job.salary ? "employer" : "uncertain"}>{job.salary ? "From the job description" : "Not confirmed"}</ProvenanceTag>{job.salary ? " Salary information appears in the listing." : " The employer did not publish salary information."}</p></section>

      <section className="preview-detail-card"><div className="preview-detail-card__heading"><span className="material-symbols-outlined">insights</span><div><p className="preview-eyebrow">Why Runr recommended it</p><h2>What appears relevant</h2></div><ProvenanceTag kind="profile">From your profile</ProvenanceTag><button className="preview-lock-button" onClick={() => locked("full_match_explanation")} type="button"><span className="material-symbols-outlined text-[15px]">lock</span>See full explanation</button></div><DetailList items={job.matchingEvidence} provenance={{ kind: "profile", label: "From your profile" }} /><div className="preview-inference-callout"><span className="material-symbols-outlined">auto_awesome</span><div><ProvenanceTag kind="inference">Inferred by Runr</ProvenanceTag><p>{job.inferredRequirements[0] || "Runr found evidence that this role is relevant to your current profile."}</p><small>The employer did not explicitly confirm this conclusion.</small></div></div></section>

      {(job.missingQualifications.length || job.uncertainInformation.length) ? <section className="preview-detail-card"><div className="preview-detail-card__heading"><span className="material-symbols-outlined">rule</span><div><p className="preview-eyebrow">Review before applying</p><h2>What needs a closer look</h2></div></div>{job.missingQualifications.length ? <><DetailLabel tone="warning">Missing from your profile</DetailLabel><DetailList items={job.missingQualifications} tone="warning" provenance={{ kind: "missing", label: "Missing from your profile" }} /></> : null}{job.uncertainInformation.length ? <><DetailLabel tone="uncertain">Not confirmed</DetailLabel><DetailList items={job.uncertainInformation} tone="uncertain" provenance={{ kind: "uncertain", label: "Not confirmed" }} /></> : null}<p className="preview-detail-footnote">These are gaps or uncertainties to review, not definite employer conclusions.</p></section> : null}
    </main>

    <aside className="preview-detail-sidebar"><section className="preview-side-card preview-side-card--accent"><p className="preview-eyebrow">Your next step</p><h2>Prepare an application for this role</h2><p>Review the evidence first, then choose the paid tools that would save you the most editing and form-filling time.</p><button className="preview-button preview-button--primary preview-button--full" onClick={() => setPreparing(true)} type="button">{preparing ? "Preparation open" : "Explore preparation"}<span className="material-symbols-outlined text-[17px]">arrow_forward</span></button></section><section className="preview-side-card"><div className="preview-side-card__heading"><span className="material-symbols-outlined">verified</span><h2>Before you apply</h2></div><p>Check the employer details, review anything not confirmed, and decide whether the role fits your real situation.</p><Link className="preview-link-button" to="/jobs/hidden">Review hidden jobs <span className="material-symbols-outlined text-[16px]">arrow_forward</span></Link></section></aside></div>
    <PreviewUpgradeModal featureKey={upgradeFeature} onClose={() => setUpgradeFeature("")} />
  </div>;
}
