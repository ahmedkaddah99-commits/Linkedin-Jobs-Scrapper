import { useEffect, useMemo, useRef, useState } from "react";
import { getCvShowcaseEntitlements, CV_SHOWCASE_SCENES } from "../../lib/cvFeatureShowcase.js";
import { logPersonalizedEvent } from "../../lib/personalizedAnalytics.js";

function EvidencePill({ children, tone = "blue" }) {
  return <span className={["cv-showcase-pill", `cv-showcase-pill--${tone}`].join(" ")}>{children}</span>;
}

function RelevantJobsDemo() {
  return (
    <div className="cv-showcase-demo cv-showcase-demo--jobs" aria-label="Miniature job screening demonstration">
      <div className="cv-demo-toolbar"><span className="cv-demo-dot" /><span>Recommended for your profile</span><small>5 checks</small></div>
      <div className="cv-demo-job cv-demo-job--featured"><div className="cv-demo-company-mark">A</div><div className="cv-demo-job__copy"><strong>Product Operations Manager</strong><span>Aurora Labs · Berlin / hybrid</span><div className="cv-demo-checks"><EvidencePill tone="teal">Strong profile alignment</EvidencePill><EvidencePill>Appears eligible</EvidencePill></div></div><b>94%</b></div>
      <div className="cv-demo-checklist"><span><i>✓</i> Role relevance</span><span><i>✓</i> Language requirements</span><span><i>✓</i> Location</span><span><i>✓</i> Experience</span></div>
      <div className="cv-demo-hidden"><span className="material-symbols-outlined">visibility_off</span><div><strong>Hidden · possible conflict</strong><small>Authorization not confirmed</small></div><span className="cv-demo-arrow">→</span></div>
    </div>
  );
}

function MatchExplanationDemo() {
  return (
    <div className="cv-showcase-demo cv-showcase-demo--match" aria-label="Miniature match explanation demonstration">
      <div className="cv-demo-match-column"><small>JOB REQUIREMENTS</small><div className="cv-demo-evidence-row"><span>Operations experience</span><b>→</b><EvidencePill>From the job description</EvidencePill></div><div className="cv-demo-evidence-row"><span>Analytics</span><b>→</b><EvidencePill>From the job description</EvidencePill></div><div className="cv-demo-evidence-row"><span>SQL preferred</span><b>→</b><EvidencePill tone="orange">Not confirmed</EvidencePill></div></div>
      <div className="cv-demo-match-divider"><span>↔</span></div>
      <div className="cv-demo-match-column cv-demo-match-column--profile"><small>YOUR PROFILE</small><div className="cv-demo-profile-line"><span className="material-symbols-outlined">work_history</span><div><strong>Product operations</strong><small>From your CV</small></div></div><div className="cv-demo-profile-line"><span className="material-symbols-outlined">insights</span><div><strong>Analytics</strong><small>From your CV</small></div></div><div className="cv-demo-profile-line cv-demo-profile-line--muted"><span className="material-symbols-outlined">help</span><div><strong>SQL</strong><small>Inferred by Runr · estimated match</small></div></div></div>
    </div>
  );
}

function ApplicationPreparationDemo() {
  return (
    <div className="cv-showcase-demo cv-showcase-demo--documents" aria-label="Miniature tailored application demonstration">
      <div className="cv-demo-doc cv-demo-doc--cv"><div className="cv-demo-doc__top"><span className="material-symbols-outlined">description</span><strong>Tailored CV</strong><EvidencePill tone="teal">Ready for your review</EvidencePill></div><div className="cv-demo-doc__line cv-demo-doc__line--strong" /><div className="cv-demo-doc__line" /><div className="cv-demo-doc__line cv-demo-doc__line--short" /><div className="cv-demo-doc__chips"><EvidencePill>Experience</EvidencePill><EvidencePill>Achievements</EvidencePill></div></div>
      <div className="cv-demo-doc cv-demo-doc--letter"><div className="cv-demo-doc__top"><span className="material-symbols-outlined">mail</span><strong>Motivation letter</strong></div><div className="cv-demo-doc__line cv-demo-doc__line--strong" /><div className="cv-demo-doc__line" /><div className="cv-demo-doc__line" /><div className="cv-demo-doc__line cv-demo-doc__line--short" /><div className="cv-demo-grounded"><span className="material-symbols-outlined">verified</span>Grounded in your profile</div></div>
      <div className="cv-demo-doc-footer"><span className="material-symbols-outlined">tune</span>Tailored to the role · no invented claims</div>
    </div>
  );
}

function AssistedApplyDemo() {
  return (
    <div className="cv-showcase-demo cv-showcase-demo--form" aria-label="Miniature assisted apply demonstration">
      <div className="cv-demo-form-header"><span className="material-symbols-outlined">business</span><div><strong>Employer application</strong><small>Review before submission</small></div><EvidencePill tone="teal">Ready for your review</EvidencePill></div>
      <div className="cv-demo-form-grid"><label>Name<input readOnly value="Alex Morgan" /></label><label>Contact details<input readOnly value="alex@example.com" /></label><label>LinkedIn<input readOnly value="linkedin.com/in/alex" /></label><label>Work authorization<select aria-label="Work authorization" defaultValue="review"><option value="review">Review answer</option></select></label></div>
      <div className="cv-demo-form-footer"><span><i>✓</i> 4 verified fields reused</span><button type="button">Review answers</button></div>
    </div>
  );
}

function SceneDemo({ sceneKey }) {
  if (sceneKey === "relevant_jobs") return <RelevantJobsDemo />;
  if (sceneKey === "match_explanations") return <MatchExplanationDemo />;
  if (sceneKey === "application_preparation") return <ApplicationPreparationDemo />;
  return <AssistedApplyDemo />;
}

function ProcessingStatus({ status, dataLabel }) {
  const isReady = status === "ready";
  const isError = status === "error";
  return (
    <div aria-live="polite" className={["cv-showcase-status", isReady ? "is-ready" : "", isError ? "is-error" : ""].join(" ")} role="status">
      <span className="material-symbols-outlined">{isReady ? "check_circle" : isError ? "error" : "autorenew"}</span>
      <div><strong>{isReady ? "Your CV is ready" : isError ? "We could not finish reading this CV" : "Reading your CV"}</strong><span>{isReady ? "Review the extracted information below, or keep exploring how Runr uses your profile." : isError ? "Retry the extraction to continue." : "Runr is identifying your experience, skills and qualifications."}</span></div>
      {dataLabel ? <small>{dataLabel}</small> : null}
    </div>
  );
}

export default function CvCapabilityShowcase({
  dataMode,
  initialScene = 0,
  planId = "none",
  processingStatus,
  onComplete,
  onSceneChange,
  onSkip,
}) {
  const [sceneIndex, setSceneIndex] = useState(Math.min(CV_SHOWCASE_SCENES.length - 1, Math.max(0, Number(initialScene) || 0)));
  const [paused, setPaused] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const showcaseRef = useRef(null);
  const viewedScenesRef = useRef(new Set());
  const onSceneChangeRef = useRef(onSceneChange);
  const entitlements = useMemo(() => getCvShowcaseEntitlements(planId), [planId]);
  const scene = CV_SHOWCASE_SCENES[sceneIndex];
  const entitlement = entitlements[scene.key];
  onSceneChangeRef.current = onSceneChange;

  useEffect(() => {
    const mediaQuery = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!mediaQuery) return undefined;
    const updateMotion = () => setReducedMotion(mediaQuery.matches);
    updateMotion();
    mediaQuery.addEventListener?.("change", updateMotion);
    return () => mediaQuery.removeEventListener?.("change", updateMotion);
  }, []);

  useEffect(() => {
    function handleVisibilityChange() {
      setPaused(document.visibilityState !== "visible");
    }
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, []);

  useEffect(() => {
    onSceneChangeRef.current?.(sceneIndex);
    if (viewedScenesRef.current.has(scene.key)) return;
    viewedScenesRef.current.add(scene.key);
    logPersonalizedEvent("cv_feature_scene_viewed", { onboardingStep: "cv", dataMode, sceneKey: scene.key, extractionStatus: processingStatus });
  }, [dataMode, processingStatus, scene.key, sceneIndex]);

  useEffect(() => {
    if (paused || reducedMotion) return undefined;
    const timer = window.setInterval(() => {
      setSceneIndex((current) => {
        if (current >= CV_SHOWCASE_SCENES.length - 1) {
          onComplete?.();
          return 0;
        }
        return current + 1;
      });
    }, 3600);
    return () => window.clearInterval(timer);
  }, [onComplete, paused, reducedMotion]);

  function moveTo(nextIndex, progression = "manual") {
    const bounded = (nextIndex + CV_SHOWCASE_SCENES.length) % CV_SHOWCASE_SCENES.length;
    setPaused(true);
    setSceneIndex(bounded);
    logPersonalizedEvent("cv_feature_scene_advanced", { onboardingStep: "cv", dataMode, sceneKey: CV_SHOWCASE_SCENES[bounded].key, progression, extractionStatus: processingStatus });
    if (bounded === 0 && sceneIndex === CV_SHOWCASE_SCENES.length - 1) onComplete?.();
  }

  function handleSkip() {
    logPersonalizedEvent("cv_feature_showcase_skipped", { onboardingStep: "cv", dataMode, sceneKey: scene.key, extractionStatus: processingStatus, showcaseSkipped: true });
    onSkip?.();
  }

  function handleFocus(event) {
    if (event.type === "focusin") setPaused(true);
    if (event.type === "focusout" && !event.currentTarget.contains(event.relatedTarget)) setPaused(false);
  }

  return (
    <section className="cv-showcase" ref={showcaseRef} onFocusIn={handleFocus} onFocusOut={handleFocus}>
      <div className="cv-showcase__copy">
        <div className="cv-showcase-kicker"><span className="material-symbols-outlined">{scene.icon}</span><span>How Runr uses your profile</span></div>
        <p className="preview-eyebrow">{scene.eyebrow}</p>
        <h3>{scene.headline}</h3>
        <p className="cv-showcase__body">{scene.body}</p>
        <div className="cv-showcase__controls">
          <button aria-label="Previous capability" className="cv-showcase-control" onClick={() => moveTo(sceneIndex - 1)} type="button"><span className="material-symbols-outlined">arrow_back</span><span>Previous</span></button>
          <div aria-label="Capability progress" className="cv-showcase-progress" role="tablist">{CV_SHOWCASE_SCENES.map((item, index) => <button aria-label={`Show ${item.eyebrow.toLowerCase()}`} aria-selected={sceneIndex === index} className={sceneIndex === index ? "is-active" : ""} key={item.key} onClick={() => moveTo(index)} role="tab" type="button" />)}</div>
          <button aria-label="Next capability" className="cv-showcase-control" onClick={() => moveTo(sceneIndex + 1)} type="button"><span>Next</span><span className="material-symbols-outlined">arrow_forward</span></button>
        </div>
        <div className="cv-showcase__meta"><span>{sceneIndex + 1} of {CV_SHOWCASE_SCENES.length}</span><button className="cv-showcase-skip" onClick={handleSkip} type="button">Skip showcase</button>{paused ? <span className="cv-showcase-paused"><span className="material-symbols-outlined">pause</span>Paused</span> : null}</div>
        {!entitlement.available ? <div className="cv-showcase-pro"><span>Runr Pro</span><small>{entitlement.explanation}</small></div> : null}
      </div>
      <div className="cv-showcase__visual"><SceneDemo sceneKey={scene.key} /><ProcessingStatus dataLabel={dataMode === "synthetic" ? "Preview extraction" : "Live extraction"} status={processingStatus} /></div>
    </section>
  );
}
