import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import PreviewBadge from "../components/personalized/PreviewBadge";
import { PREVIEW_FEED_SUMMARY, PREVIEW_JOBS } from "../lib/personalizedJobs";
import { logPersonalizedEvent } from "../lib/personalizedAnalytics";
import { getNextOnboardingStep, getOnboardingAnswers, getPreviousOnboardingStep, ONBOARDING_STEPS } from "../lib/personalizedOnboarding";
import { usePersistedOnboarding } from "../lib/personalizedPreviewState";

function Field({ children, label, optional = false }) {
  return <label className="preview-onboarding-field"><span>{label}{optional ? " (optional)" : ""}</span>{children}</label>;
}

function ChipField({ options, selected, onToggle, label }) {
  return <div aria-label={label} className="preview-chip-list">{options.map((option) => <button aria-pressed={selected.includes(option)} className={["preview-chip", selected.includes(option) ? "is-selected" : ""].join(" ")} key={option} onClick={() => onToggle(option)} type="button">{selected.includes(option) ? <span className="material-symbols-outlined text-[16px]">check</span> : null}{option}</button>)}</div>;
}

function StepIntro({ step, title, children }) {
  return <div className="preview-onboarding-intro"><p className="preview-eyebrow">Step {step + 1} of {ONBOARDING_STEPS.length} · {ONBOARDING_STEPS[step].label}</p><h2>{title}</h2><p>{children}</p></div>;
}

function GoalsStep({ answers, updateAnswer }) {
  const toggle = (field, value) => updateAnswer(field, (answers[field] || []).includes(value) ? (answers[field] || []).filter((item) => item !== value) : [...(answers[field] || []), value]);
  return <><StepIntro step={0} title="What kind of work should Runr look for?">Tell us what you want next. You can change these preferences at any time.</StepIntro><div className="preview-onboarding-form"><Field label="Target job titles"><input autoFocus onChange={(event) => updateAnswer("targetRoles", event.target.value.split(",").map((item) => item.trim()).filter(Boolean))} placeholder="e.g. Product Operations Manager" value={(answers.targetRoles || []).join(", ")} /></Field><Field label="Preferred locations"><input onChange={(event) => updateAnswer("targetLocations", event.target.value.split(",").map((item) => item.trim()).filter(Boolean))} placeholder="e.g. Berlin, Remote in Germany" value={(answers.targetLocations || []).join(", ")} /></Field><div className="preview-onboarding-two-col"><Field label="Work arrangement"><ChipField label="Work arrangement" onToggle={(value) => toggle("workArrangements", value)} options={["Remote", "Hybrid", "On-site"]} selected={answers.workArrangements || []} /></Field><Field label="Seniority"><select onChange={(event) => updateAnswer("seniority", event.target.value)} value={answers.seniority || ""}><option disabled value="">Choose a level</option><option value="entry">Entry level</option><option value="mid">Mid-level</option><option value="senior">Senior</option><option value="lead">Lead</option></select></Field></div><Field label="Employment type"><ChipField label="Employment type" onToggle={(value) => toggle("employmentTypes", value)} options={["Full-time", "Part-time", "Contract"]} selected={answers.employmentTypes || []} /></Field></div></>;
}

function CvStep({ answers, updateAnswer, onSkip }) {
  const [fileName, setFileName] = useState(answers.sourceCvName || "");
  function chooseFile(event) {
    const nextName = event.target.files?.[0]?.name || "";
    setFileName(nextName);
    if (nextName) updateAnswer("sourceCvName", nextName);
  }
  return <><StepIntro step={1} title="Bring your main CV">Runr uses your CV to understand your experience, skills and qualifications. You will be able to review the extracted information before it is used.</StepIntro><div className="preview-cv-upload"><input accept=".pdf,.doc,.docx" id="preview-cv-file" onChange={chooseFile} type="file" /><label htmlFor="preview-cv-file"><span className="material-symbols-outlined">upload_file</span><strong>{fileName || "Upload your main CV"}</strong><span>{fileName ? "Preview file selected" : "PDF or DOCX · Optional"}</span></label>{fileName ? <p className="preview-local-label"><span className="material-symbols-outlined text-[14px]">check_circle</span>{fileName} is used only in this local preview.</p> : null}</div><section className="preview-extraction-card"><div className="preview-extraction-card__heading"><span className="material-symbols-outlined">auto_awesome</span><div><p className="preview-eyebrow">Preview extraction</p><h3>What Runr would look for</h3></div><PreviewBadge /></div><p className="preview-extraction-note">This example shows the information you can review before it helps shape your job shortlist.</p><div className="preview-extraction-grid"><div><span>Experience</span><strong>Product and operations leadership</strong></div><div><span>Education</span><strong>Business and information systems</strong></div><div><span>Skills</span><strong>Planning, analytics and process design</strong></div><div><span>Languages</span><strong>English fluent · German conversational</strong></div><div><span>Contact details</span><strong>Kept ready for applications</strong></div></div></section><button className="preview-text-button" onClick={onSkip} type="button">Skip for now</button></>;
}

function EligibilityStep({ answers, updateAnswer }) {
  const toggle = (field, value) => updateAnswer(field, (answers[field] || []).includes(value) ? (answers[field] || []).filter((item) => item !== value) : [...(answers[field] || []), value]);
  return <><StepIntro step={2} title="Where can you apply?">Runr uses these answers to identify jobs that may not fit your language, location or work-authorization situation.</StepIntro><div className="preview-onboarding-form"><div className="preview-onboarding-two-col"><Field label="Work authorization"><select onChange={(event) => updateAnswer("workAuthorization", event.target.value)} value={answers.workAuthorization || "not_sure"}><option value="not_sure">I am not sure yet</option><option value="EU / EEA citizen">I can work without sponsorship</option><option value="Work permit">I have a work permit</option><option value="Needs sponsorship">I may need sponsorship</option><option value="Prefer not to say">Prefer not to say</option></select></Field><Field label="Sponsorship"><select onChange={(event) => updateAnswer("sponsorshipRequired", event.target.value)} value={answers.sponsorshipRequired || "not_sure"}><option value="not_sure">Not sure yet</option><option value="no">I do not need sponsorship</option><option value="yes">I need sponsorship</option></select></Field></div><p className="preview-form-note"><span className="material-symbols-outlined">info</span>These are your answers for this preview. Runr cannot verify work authorization or sponsorship from this screen.</p><Field label="Languages and proficiency"><ChipField label="Languages and proficiency" onToggle={(value) => toggle("languages", value)} options={["English — fluent", "German — conversational", "German — fluent", "French — conversational"]} selected={answers.languages || []} /></Field><div className="preview-onboarding-two-col"><Field label="Willingness to relocate"><select onChange={(event) => updateAnswer("relocationPreference", event.target.value)} value={answers.relocationPreference || "not_sure"}><option value="not_sure">Not sure yet</option><option>Open to Berlin or remote</option><option>Open to relocating</option><option>Only current location</option></select></Field><Field label="Minimum salary" optional><input onChange={(event) => updateAnswer("salaryExpectation", event.target.value)} placeholder="e.g. EUR 68,000" value={answers.salaryExpectation || ""} /></Field></div><div className="preview-onboarding-two-col"><Field label="Earliest start date"><select onChange={(event) => updateAnswer("earliestStartDate", event.target.value)} value={answers.earliestStartDate || "not_sure"}><option value="not_sure">Not sure yet</option><option>Immediately</option><option>Within 1 month</option><option>Within 3 months</option><option>Just exploring</option></select></Field><Field label="Maximum commute" optional><select onChange={(event) => updateAnswer("maximumCommute", event.target.value)} value={answers.maximumCommute || "not_sure"}><option value="not_sure">Not sure yet</option><option>30 minutes</option><option>45 minutes</option><option>60 minutes</option><option>Not applicable</option></select></Field></div></div></>;
}

function AnswersStep({ answers, updateAnswer }) {
  const toggle = (field, value) => updateAnswer(field, (answers[field] || []).includes(value) ? (answers[field] || []).filter((item) => item !== value) : [...(answers[field] || []), value]);
  return <><StepIntro step={3} title="Make applications less repetitive">Save answers that employers commonly ask for. Runr can reuse them when preparing applications, while you remain in control.</StepIntro><div className="preview-onboarding-form"><div className="preview-onboarding-two-col"><Field label="Notice period"><select onChange={(event) => updateAnswer("noticePeriod", event.target.value)} value={answers.noticePeriod || "not_sure"}><option value="not_sure">Not sure yet</option><option>Available immediately</option><option>1 month</option><option>2 months</option><option>3 months</option></select></Field><Field label="Salary expectation" optional><input onChange={(event) => updateAnswer("applicationSalary", event.target.value)} placeholder="e.g. EUR 75,000" value={answers.applicationSalary || ""} /></Field></div><Field label="Willingness to travel" optional><ChipField label="Willingness to travel" onToggle={(value) => toggle("travel", value)} options={["Rarely", "Sometimes", "Frequently"]} selected={answers.travel || []} /></Field><div className="preview-onboarding-two-col"><Field label="LinkedIn URL" optional><input onChange={(event) => updateAnswer("linkedin", event.target.value)} placeholder="linkedin.com/in/your-name" value={answers.linkedin || ""} /></Field><Field label="Portfolio or personal website" optional><input onChange={(event) => updateAnswer("portfolio", event.target.value)} placeholder="yourwebsite.com" value={answers.portfolio || ""} /></Field></div><Field label="Common application answer" optional><textarea onChange={(event) => updateAnswer("motivation", event.target.value)} placeholder="Why are you interested in your next role?" rows="3" value={answers.motivation || ""} /></Field><p className="preview-form-note"><span className="material-symbols-outlined">lightbulb</span>These answers stay in this local preview and are not sent through analytics.</p></div></>;
}

function RevealStep({ onViewJobs, onAdjustPreferences }) {
  return <div className="preview-result-reveal"><div className="preview-result-reveal__spark"><span className="material-symbols-outlined">auto_awesome</span></div><PreviewBadge /><p className="preview-eyebrow">Your personalized search is ready</p><h2>We found 1,284 jobs based on your preferences.</h2><p className="preview-result-reveal__intro">Runr has already separated the strongest opportunities from jobs that may not fit your requirements.</p><div className="preview-result-cards"><div><strong>{PREVIEW_FEED_SUMMARY.strongMatches}</strong><span>Strong matches</span></div><div><strong>{PREVIEW_FEED_SUMMARY.eligibleJobs.toLocaleString()}</strong><span>Jobs that appear eligible</span></div><div><strong>{PREVIEW_FEED_SUMMARY.hiddenJobs}</strong><span>Jobs hidden by eligibility preferences</span></div><div><strong>{PREVIEW_FEED_SUMMARY.newSinceLastVisit}</strong><span>New jobs since last update</span></div></div><div className="preview-result-examples"><span className="material-symbols-outlined">check_circle</span><p><strong>First opportunity to explore:</strong> {PREVIEW_JOBS[0].title} at {PREVIEW_JOBS[0].company} · estimated {PREVIEW_JOBS[0].matchScore}% match based on the current preview profile.</p></div><div className="preview-result-actions"><button className="preview-button preview-button--primary preview-button--large" onClick={onViewJobs} type="button">View my jobs <span className="material-symbols-outlined">arrow_forward</span></button><button className="preview-text-button" onClick={onAdjustPreferences} type="button">Adjust my preferences</button></div><p className="preview-result-footnote">Preview data. These figures are example values for this frontend preview.</p></div>;
}

export default function PersonalizedOnboardingPage() {
  const navigate = useNavigate();
  const { state, update } = usePersistedOnboarding();
  const [activeStep, setActiveStep] = useState(Math.min(4, Math.max(0, state.step || 0)));
  const [started, setStarted] = useState(false);
  const [stepError, setStepError] = useState("");
  const answers = useMemo(() => getOnboardingAnswers(state.answers), [state.answers]);

  useEffect(() => {
    if (!started) {
      setStarted(true);
      logPersonalizedEvent("onboarding_started", { route: "/onboarding", onboardingStep: ONBOARDING_STEPS[activeStep].id });
    }
  }, [activeStep, started]);

  useEffect(() => {
    logPersonalizedEvent("onboarding_step_viewed", { route: "/onboarding", onboardingStep: ONBOARDING_STEPS[activeStep].id });
  }, [activeStep]);

  function updateAnswer(field, valueOrUpdater) {
    update((current) => {
      const currentValue = current.answers?.[field] ?? answers[field];
      const nextValue = typeof valueOrUpdater === "function" ? valueOrUpdater(currentValue) : valueOrUpdater;
      return { ...current, answers: { ...current.answers, [field]: nextValue } };
    });
  }

  function validateStep() {
    if (activeStep === 0 && !(answers.targetRoles || []).length) return "Add at least one target job title so Runr knows what to look for.";
    if (activeStep === 0 && !(answers.targetLocations || []).length) return "Add at least one preferred location, or enter a remote location.";
    return "";
  }

  function goTo(nextStep) {
    const bounded = Math.min(4, Math.max(0, nextStep));
    if (bounded > activeStep) {
      const error = validateStep();
      if (error) {
        setStepError(error);
        return;
      }
      logPersonalizedEvent("onboarding_step_completed", { route: "/onboarding", onboardingStep: ONBOARDING_STEPS[activeStep].id });
    }
    setStepError("");
    setActiveStep(bounded);
    update((current) => ({ ...current, step: bounded }));
  }

  function finish() {
    update((current) => ({ ...current, step: 4, completed: true }));
    logPersonalizedEvent("onboarding_completed", { route: "/onboarding", onboardingStep: "reveal" });
    navigate("/jobs");
  }

  function adjustPreferences() {
    setStepError("");
    setActiveStep(0);
    update((current) => ({ ...current, step: 0, completed: false }));
  }

  const stepContent = activeStep === 0 ? <GoalsStep answers={answers} updateAnswer={updateAnswer} /> : activeStep === 1 ? <CvStep answers={answers} onSkip={() => goTo(2)} updateAnswer={updateAnswer} /> : activeStep === 2 ? <EligibilityStep answers={answers} updateAnswer={updateAnswer} /> : activeStep === 3 ? <AnswersStep answers={answers} updateAnswer={updateAnswer} /> : <RevealStep onAdjustPreferences={adjustPreferences} onViewJobs={finish} />;

  return <div className="preview-onboarding-page"><header className="preview-onboarding-header"><Link className="preview-onboarding-brand" to="/"><span className="shell-brand-mark"><span /><span /><span /></span><span>runr.</span></Link><div><PreviewBadge /><Link className="preview-onboarding-exit" to="/">Exit onboarding</Link></div></header><div aria-label="Onboarding progress" className="preview-onboarding-progress">{ONBOARDING_STEPS.map((step, index) => <button aria-current={activeStep === index ? "step" : undefined} className={["preview-progress-step", activeStep === index ? "is-active" : "", activeStep > index ? "is-complete" : ""].join(" ")} key={step.id} onClick={() => index <= activeStep && goTo(index)} type="button"><span>{index < activeStep ? <span className="material-symbols-outlined text-[15px]">check</span> : index + 1}</span><small>{step.shortLabel}</small></button>)}</div><main className="preview-onboarding-card"><div className="preview-onboarding-card__content">{stepContent}{stepError ? <p aria-live="polite" className="preview-form-error" role="alert"><span className="material-symbols-outlined">error</span>{stepError}</p> : null}</div>{activeStep < 4 ? <div className="preview-onboarding-footer"><button className="preview-text-button" disabled={activeStep === 0} onClick={() => goTo(getPreviousOnboardingStep(activeStep))} type="button"><span className="material-symbols-outlined text-[17px]">arrow_back</span>Back</button><button className="preview-button preview-button--primary" onClick={() => goTo(getNextOnboardingStep(activeStep))} type="button">Continue <span className="material-symbols-outlined text-[17px]">arrow_forward</span></button></div> : null}</main><p className="preview-onboarding-safe-note"><span className="material-symbols-outlined text-[16px]">lock</span>Your progress is saved locally for this preview. It does not update your production profile.</p></div>;
}
