import { useEffect, useState } from "react";
import { Link, Navigate, useParams, useSearchParams } from "react-router-dom";
import PreviewBadge from "../components/personalized/PreviewBadge";
import PreviewUpgradeModal from "../components/personalized/PreviewUpgradeModal";
import { PREVIEW_JOBS, formatPreviewDate } from "../lib/personalizedJobs";
import { logPersonalizedEvent } from "../lib/personalizedAnalytics";
import { usePreviewDispositions, loadUpgradeDismissals } from "../lib/personalizedPreviewState";

function DetailLabel({ children, tone = "verified" }) {
  return <span className={["preview-detail-label", `preview-detail-label--${tone}`].join(" ")}>{children}</span>;
}

function DetailList({ items, tone = "verified" }) {
  return <ul className={["preview-detail-list", `preview-detail-list--${tone}`].join(" ")}>{items.map((item) => <li key={item}><span className="material-symbols-outlined">{tone === "verified" ? "check_circle" : tone === "inferred" ? "auto_awesome" : "info"}</span>{item}</li>)}</ul>;
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
  const isSaved = Boolean(dispositions.saved?.[jobId] || job?.saved);
  const isHidden = Boolean(job?.hidden && !isRestored) || isLocallyHidden;

  useEffect(() => {
    if (job) logPersonalizedEvent("job_detail_viewed", { route: `/jobs/${job.id}`, jobPreviewId: job.id });
  }, [job]);

  if (!job) return <Navigate replace to="/jobs" />;

  function handleSave() {
    toggleSaved(job.id);
    logPersonalizedEvent("job_saved", { route: `/jobs/${job.id}`, jobPreviewId: job.id });
    setFeedback(isSaved ? "Removed from your saved jobs." : "Saved to your jobs list.");
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
    setFeedback("This job is hidden for the preview session. You can undo it from Hidden jobs.");
  }

  function locked(featureKey) {
    logPersonalizedEvent("locked_feature_clicked", { route: `/jobs/${job.id}`, jobPreviewId: job.id, featureKey });
    if (!loadUpgradeDismissals()[featureKey]) setUpgradeFeature(featureKey);
  }

  return (
    <div className="preview-page preview-detail-page">
      <div className="preview-detail-back"><Link to="/jobs"><span className="material-symbols-outlined text-[18px]">arrow_back</span>Back to jobs</Link><PreviewBadge /></div>
      <header className="preview-detail-header">
        <div className="preview-company-mark preview-company-mark--large" aria-hidden="true">{job.company.slice(0, 1)}</div>
        <div className="min-w-0 flex-1"><div className="preview-header-kicker">{job.source} <span>·</span> {formatPreviewDate(job.postedAt)}</div><h1>{job.title}</h1><p>{job.company} · {job.location} · {job.workArrangement}</p></div>
        <button aria-label={isSaved ? "Unsave job" : "Save job"} className={["preview-icon-button preview-icon-button--large", isSaved ? "is-active" : ""].join(" ")} onClick={handleSave} type="button"><span className="material-symbols-outlined" style={isSaved ? { fontVariationSettings: "'FILL' 1" } : undefined}>bookmark</span></button>
      </header>

      <div className="preview-detail-actions">
        <button className="preview-button preview-button--primary" onClick={() => setPreparing(true)} type="button">Prepare application <span className="material-symbols-outlined text-[17px]">arrow_forward</span></button>
        <button className="preview-button preview-button--secondary" onClick={handleHideOrRestore} type="button">{isHidden ? "Show in feed" : "Hide job"}</button>
        <span className="preview-detail-action-note"><span className="material-symbols-outlined">science</span>All decisions on this page are preview-only.</span>
      </div>
      {feedback ? <div className="preview-feedback" role="status"><span className="material-symbols-outlined">check_circle</span>{feedback}</div> : null}

      <div className="preview-detail-layout">
        <main className="preview-detail-main">
          <section className="preview-detail-card preview-detail-card--status">
            <div><DetailLabel tone={job.eligibilityStatus === "eligible" ? "verified" : "warning"}>{job.eligibilityStatus === "eligible" ? "Eligibility looks good" : job.hiddenReasonLabel || "Eligibility needs review"}</DetailLabel><h2>{job.matchScore}% <span>estimated match</span></h2><p>Based on your current profile, preferences, and the text available in this preview listing.</p></div>
            <div className="preview-detail-score-ring" style={{ "--score": `${job.matchScore * 3.6}deg` }}><strong>{job.matchScore}</strong><span>/100</span></div>
          </section>

          <section className="preview-detail-card"><div className="preview-detail-card__heading"><span className="material-symbols-outlined">description</span><div><p className="preview-eyebrow">Verified job information</p><h2>About the role</h2></div></div><p className="preview-detail-description">{job.description}</p><div className="preview-verified-grid">{job.verifiedInformation.map((item) => <span key={item}><span className="material-symbols-outlined">check_circle</span>{item}</span>)}</div></section>

          <section className="preview-detail-card"><div className="preview-detail-card__heading"><span className="material-symbols-outlined">insights</span><div><p className="preview-eyebrow">Runr&apos;s inference</p><h2>Why this job surfaced</h2></div><button className="preview-lock-button" onClick={() => locked("full_match_explanation")} type="button"><span className="material-symbols-outlined text-[15px]">lock</span>See full explanation</button></div><DetailList items={job.matchingEvidence} /><div className="preview-inference-callout"><span className="material-symbols-outlined">auto_awesome</span><p>{job.inferredRequirements[0] || "Runr found evidence that this role is relevant to your current profile."}</p></div></section>

          {(job.missingQualifications.length || job.uncertainInformation.length) ? <section className="preview-detail-card"><div className="preview-detail-card__heading"><span className="material-symbols-outlined">rule</span><div><p className="preview-eyebrow">Review before applying</p><h2>Missing or uncertain</h2></div></div>{job.missingQualifications.length ? <><DetailLabel tone="warning">Potential gap</DetailLabel><DetailList items={job.missingQualifications} tone="warning" /></> : null}{job.uncertainInformation.length ? <><DetailLabel tone="uncertain">Not clear from the listing</DetailLabel><DetailList items={job.uncertainInformation} tone="uncertain" /></> : null}<p className="preview-detail-footnote">These are Runr&apos;s inferences from the preview text, not definite employer statements.</p></section> : null}
        </main>

        <aside className="preview-detail-sidebar">
          <section className="preview-side-card preview-side-card--accent"><p className="preview-eyebrow">Application preparation</p><h2>Turn this match into a next step</h2><p>Start with a role-specific checklist, then use your strongest evidence where it matters.</p><button className="preview-button preview-button--primary preview-button--full" onClick={() => setPreparing(true)} type="button">{preparing ? "Preparation started" : "Start preparing"}<span className="material-symbols-outlined text-[17px]">arrow_forward</span></button></section>
          <section className="preview-side-card"><div className="preview-side-card__heading"><span className="material-symbols-outlined">auto_awesome</span><h2>Paid application tools</h2></div><button className="preview-feature-row" onClick={() => locked("tailored_cv")} type="button"><span><strong>Tailored CV</strong><small>Emphasise the evidence this role needs.</small></span><span className="material-symbols-outlined">lock</span></button><button className="preview-feature-row" onClick={() => locked("tailored_motivation_letter")} type="button"><span><strong>Motivation letter</strong><small>Connect your experience to this role.</small></span><span className="material-symbols-outlined">lock</span></button><button className="preview-feature-row" onClick={() => locked("assisted_apply")} type="button"><span><strong>Assisted Apply</strong><small>Reduce repetitive application form filling.</small></span><span className="material-symbols-outlined">lock</span></button></section>
          {preparing ? <section className="preview-side-card preview-preparation-card"><div className="preview-side-card__heading"><span className="material-symbols-outlined">checklist</span><h2>Preparation checklist</h2></div><label><input defaultChecked type="checkbox" /> Review the role&apos;s must-have requirements</label><label><input type="checkbox" /> Choose two matching evidence points</label><label><input type="checkbox" /> Confirm your application answers</label><p>Free preview step — document generation remains locked until you choose a plan.</p></section> : null}
        </aside>
      </div>
      <PreviewUpgradeModal featureKey={upgradeFeature} onClose={() => setUpgradeFeature("")} />
    </div>
  );
}

