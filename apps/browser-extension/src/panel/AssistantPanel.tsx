import { useState } from "react";
import type { ApplicationJobContext, ApplicationPageDetection } from "@runr/ats-core/application-context";
import { matchVerdict, type ProfileCompleteness, type ResumeMatch } from "@runr/ats-core/resume-match";
import type { AutofillRunState, FieldResult } from "./autofill-run";
import type { CandidateProfile } from "@runr/ats-core/generic-planner";
import type { ApplicationPackagePayload } from "@runr/extension-messages";
import ProfileQuickCopy from "./ProfileQuickCopy";
import LocalDocumentPicker from "./LocalDocumentPicker";
import ApplicationWorkspace from "./ApplicationWorkspace";
import { workspaceRequest } from "./workspace";
import type { DocumentRole } from "@runr/ats-core/generic-upload";
import type { ProfileDetail } from "./profile-details";

export type PanelTab = "autofill" | "resume" | "profile" | "documents" | "answers";

export interface AssistantPanelProps {
  job: ApplicationJobContext | null;
  detection: ApplicationPageDetection;
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
  onPrimaryAction: () => void;
  onContinueToNextStep: () => void;
  canContinueToNextStep: boolean;
  continuingToNextStep: boolean;
  navigationMessage?: string;
  onOpenSettings: () => void;
  onReport: () => void;
  /** Set when the primary action cannot run yet; renders in place of the CTA note. */
  primaryBlockedReason?: string;
  run: AutofillRunState | null;
  busy: boolean;
  error?: string;
  resumeMatch: ResumeMatch | null;
  completeness: ProfileCompleteness | null;
  onTailorResume: () => void;
  onCopyProfile: () => void;
  profile?: CandidateProfile | null;
  profileLoading?: boolean;
  profileError?: string;
  onRefreshProfile?: () => void;
  applicationPackage?: ApplicationPackagePayload | null;
  onOpenDocuments?: () => void;
  onEditProfile?: () => void;
  onOpenTracker?: () => void;
  onReviewDocuments?: () => void;
  onFocusField?: (fieldId: string) => void;
  onAttachLocalDocument?: (role: DocumentRole, file: File, replace: boolean) => Promise<string>;
  savedAnswers?: ProfileDetail[];
  onScoreDescription?: (description: string) => void;
}

const PROVIDER_LABELS: Record<string, string> = {
  greenhouse: "Greenhouse",
  lever: "Lever",
  workday: "Workday",
  icims: "iCIMS",
  taleo: "Oracle Recruiting",
  smartrecruiters: "SmartRecruiters",
  ashby: "Ashby",
  bamboohr: "BambooHR",
  jobvite: "Jobvite",
  recruitee: "Recruitee",
  avature: "Avature",
  generic: "this employer's portal",
  unknown: "this employer's portal",
};

export function providerLabel(provider: string): string {
  return PROVIDER_LABELS[provider] ?? "this employer's portal";
}

/**
 * Formats a posting date the way the reference captures show it — a short
 * locale date, not the raw source string. Returns null when the value cannot be
 * parsed, so an unrecognised format is omitted rather than shown raw.
 */
export function formatPostedAt(value: string | undefined): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleDateString();
}

function initialFor(employer: string): string {
  const letter = employer.trim().charAt(0);
  return letter ? letter.toUpperCase() : "R";
}

function FieldRow({ result, onFocusField }: { result: FieldResult; onFocusField?: (fieldId: string) => void }) {
  const done = result.outcome === "filled" || result.outcome === "kept";
  return (
    <li className={`field-row field-${result.outcome}`} data-testid={`runr-field-${result.outcome}`}>
      <span className={done ? "glyph glyph-done" : "glyph glyph-attention"} aria-hidden="true">
        {done ? "✓" : "!"}
      </span>
      <span className="field-label">{result.label}</span>
      {!done && onFocusField && !result.fieldId.startsWith("unsupported-") ? <button type="button" className="icon-button" onClick={() => onFocusField(result.fieldId)} aria-label={`Go to ${result.label}`}>Review</button> : null}
    </li>
  );
}

function ProgressBlock({ run, onFocusField }: { run: AutofillRunState; onFocusField?: (fieldId: string) => void }) {
  if (run.stage !== "complete") {
    return (
      <div className="card" data-testid="runr-panel-progress">
        <p className="progress-title">
          {run.stage === "detecting" ? "Detecting questions & input fields" : "Filling this application…"}
        </p>
        {run.detectedCount > 0 ? (
          <p className="progress-detail" data-testid="runr-panel-detected-count">
            {run.detectedCount} fields detected
          </p>
        ) : null}
        <ul className="field-list">
          {run.results.map((result) => <FieldRow key={result.fieldId} result={result} />)}
        </ul>
      </div>
    );
  }

  const review = run.results.filter((r) => r.outcome === "needs_review" || r.outcome === "manual");
  const done = run.results.filter((r) => r.outcome === "filled" || r.outcome === "kept");

  return (
    <div className="card" data-testid="runr-panel-progress">
      <p className="progress-title" data-testid="runr-panel-complete">
        Autofill complete!{" "}
        {review.length > 0 ? (
          <span className="accent" data-testid="runr-panel-review-count">
            {review.length} field{review.length === 1 ? "" : "s"} need review
          </span>
        ) : null}
      </p>
      {review.length > 0 ? (
        <>
          <p className="section-title">Need to review({review.length})</p>
          <ul className="field-list" data-testid="runr-panel-review-list">
            {review.map((result) => <FieldRow key={result.fieldId} result={result} onFocusField={onFocusField} />)}
          </ul>
        </>
      ) : null}
      {done.length > 0 ? (
        <>
          <p className="section-title">Completed({done.length})</p>
          <ul className="field-list" data-testid="runr-panel-completed-list">
            {done.map((result) => <FieldRow key={result.fieldId} result={result} />)}
          </ul>
        </>
      ) : null}
    </div>
  );
}

export default function AssistantPanel({
  job,
  detection,
  collapsed,
  onCollapsedChange,
  onPrimaryAction,
  onContinueToNextStep,
  canContinueToNextStep,
  continuingToNextStep,
  navigationMessage,
  onOpenSettings,
  onReport,
  primaryBlockedReason,
  run,
  busy,
  error,
  resumeMatch,
  completeness,
  onTailorResume,
  onCopyProfile,
  profile,
  profileLoading,
  profileError,
  onRefreshProfile,
  applicationPackage,
  onOpenDocuments,
  onEditProfile,
  onOpenTracker,
  onReviewDocuments,
  onFocusField,
  onAttachLocalDocument,
  savedAnswers = [],
  onScoreDescription,
}: AssistantPanelProps) {
  const [tab, setTab] = useState<PanelTab>("autofill");
  const [showKeywords, setShowKeywords] = useState(false);
  const [showReport, setShowReport] = useState(false);
  const [reportDescription, setReportDescription] = useState("");
  const [reportStatus, setReportStatus] = useState("");
  const [reportBusy, setReportBusy] = useState(false);
  const [matchDescription, setMatchDescription] = useState("");
  async function copyReport() {
    const report = [`Runr application support`, `Site: ${window.location.hostname}`, `Application site: ${providerLabel(detection.provider)}`, `Role: ${job?.title || "Unknown"}`, `Fields found: ${detection.fillableFieldCount}`, "", reportDescription.trim()].join("\n");
    try { await navigator.clipboard.writeText(report); setReportStatus("Report copied. Share it with Runr support."); }
    catch { setReportStatus("Couldn't copy. Select your description and copy it manually."); }
  }
  async function sendReport() {
    setReportBusy(true); setReportStatus("");
    try {
      const result = await workspaceRequest<{ receipt: string }>("report", {
        description: reportDescription.trim(), hostname: window.location.hostname,
        provider: detection.provider, role: (job?.title || "").slice(0, 300),
      });
      setReportStatus(`Report saved to your Runr account. Reference: ${result.receipt}`);
    } catch (error) { setReportStatus(error instanceof Error ? error.message : "Couldn't send the report. Retry or copy it."); }
    finally { setReportBusy(false); }
  }

  if (collapsed) {
    return (
      <button
        type="button"
        className="collapsed"
        data-testid="runr-panel-reopen"
        aria-label="Reopen Runr"
        onClick={() => onCollapsedChange(false)}
      >
        Runr
      </button>
    );
  }

  const postedAt = formatPostedAt(job?.postedAt);

  return (
    <section className="panel" data-testid="runr-assistant-panel" aria-label="Runr Assisted Apply">
      <header className="header">
        <span className="brand">
          <span className="brand-mark" aria-hidden="true">R</span>
          Runr
        </span>
        <span className="header-actions">
          <button type="button" className="icon-button" onClick={() => setShowReport((value) => !value)} data-testid="runr-panel-report" aria-expanded={showReport}>
            Report
          </button>
          <button
            type="button"
            className="icon-button"
            onClick={onOpenSettings}
            aria-label="Runr settings"
            data-testid="runr-panel-settings"
          >
            ⚙
          </button>
          <button
            type="button"
            className="icon-button"
            onClick={() => onCollapsedChange(true)}
            aria-label="Collapse Runr"
            data-testid="runr-panel-collapse"
          >
            ›
          </button>
        </span>
      </header>

      <div className="tabs" role="tablist" aria-label="Runr sections">
        {([
          ["autofill", "Autofill"],
          ["resume", "Match"],
          ["profile", "Profile"],
          ["documents", "Documents"],
          ["answers", "Answers"],
        ] as const).map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="tab"
            id={`runr-tab-${value}`}
            aria-controls="runr-panel-tabpanel"
            tabIndex={tab === value ? 0 : -1}
            className="tab"
            aria-selected={tab === value}
            onClick={() => setTab(value)}
            onKeyDown={(event) => {
              if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
              event.preventDefault();
              const tabs = Array.from(event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]') ?? []);
              const index = tabs.indexOf(event.currentTarget);
              const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
              const target = tabs[next];
              if (target) { setTab(target.id.replace("runr-tab-", "") as PanelTab); target.focus(); }
            }}
            data-testid={`runr-panel-tab-${value}`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="body" id="runr-panel-tabpanel" role="tabpanel" aria-labelledby={`runr-tab-${tab}`}>
        {showReport ? <div className="card" data-testid="runr-panel-report-form">
          <p className="progress-title">Report an application issue</p><label htmlFor="runr-report-description" className="job-meta">What didn't work?</label>
          <textarea id="runr-report-description" className="profile-search" rows={4} maxLength={2000} value={reportDescription} onChange={(event) => { setReportDescription(event.target.value); setReportStatus(""); }} placeholder="Which field or step needs help?" />
          <button type="button" className="primary" disabled={reportBusy || !reportDescription.trim()} onClick={() => void sendReport()}>{reportBusy ? "Sending…" : "Send report"}</button>
          <button type="button" className="icon-button" disabled={reportBusy || !reportDescription.trim()} onClick={() => void copyReport()}>Copy support report</button>
          <button type="button" className="icon-button" onClick={onReport}>Open application review</button><button type="button" className="icon-button" onClick={() => setShowReport(false)}>Close report</button>
          {reportStatus ? <p className="job-meta" role="status">{reportStatus}</p> : null}
        </div> : null}
        {tab === "autofill" ? (
          <div className="card">
            <div className="job">
              <span className="job-logo" aria-hidden="true">{initialFor(job?.employer || "")}</span>
              <div>
                <p className="job-title" data-testid="runr-panel-job-title">
                  {job?.title || "Application detected"}
                </p>
                <p className="job-meta" data-testid="runr-panel-job-meta">
                  {[job?.employer, postedAt ? `Posted on ${postedAt}` : null].filter(Boolean).join(" · ") ||
                    providerLabel(detection.provider)}
                </p>
              </div>
            </div>
          </div>
        ) : null}

        {tab === "autofill" && !run ? <div className="card setup-card">
          <p className="progress-title">{profileLoading ? "Loading your profile…" : profile ? "Ready to autofill" : "Connect your profile"}</p>
          <p className="job-meta">{profile ? "Fill this page, review the remaining fields, then continue." : profileError || "Connect Runr to use your saved details."}</p>
          {!profile && !profileLoading ? <button type="button" className="primary" onClick={onOpenSettings}>Connect Runr</button> : null}
          {onRefreshProfile && !profileLoading ? <button type="button" className="icon-button" onClick={onRefreshProfile}>Refresh profile</button> : null}
          <div className="quick-actions"><button type="button" className="icon-button" onClick={() => setTab("documents")}>Choose documents</button><button type="button" className="icon-button" onClick={() => setTab("profile")}>View profile</button></div>
        </div> : null}

        {tab === "autofill" && run ? <ProgressBlock run={run} onFocusField={onFocusField} /> : null}

        {tab === "autofill" && applicationPackage?.answers.length ? <details className="card"><summary className="progress-title">Application answers ({applicationPackage.answers.length})</summary><p className="job-meta">Review or update these answers in application review.</p><button type="button" className="icon-button" onClick={onReviewDocuments}>Open application review</button></details> : null}

        <div className="card" data-testid="runr-panel-documents" hidden={tab !== "documents"}>
          <p className="progress-title">Application documents</p>
          {applicationPackage?.documents.length ? <ul className="field-list">{applicationPackage.documents.map((doc) => <li className="document-item" key={doc.documentId}><strong>{doc.documentKind === "cv" ? "Resume" : doc.documentKind === "cover_letter" ? "Cover letter" : "Supporting document"}</strong><span className="profile-value">{doc.fileName}</span></li>)}</ul> : <p className="job-meta">Choose a file below, or select your application documents in Runr.</p>}
          {onAttachLocalDocument ? <p className="job-meta">PDF or Word (.docx), up to 20 MB.</p> : null}
          {applicationPackage?.documents.length ? <button type="button" className="primary" onClick={onReviewDocuments}>Review and attach documents</button> : null}
          <div className="quick-actions"><button type="button" className="icon-button" onClick={onOpenDocuments}>Manage documents</button><button type="button" className="icon-button" onClick={onTailorResume}>Tailor resume</button></div>
          <ApplicationWorkspace key={`documents:${window.location.href}`} mode="documents" applicationUrl={window.location.href} description={job?.description || matchDescription} onAttach={onAttachLocalDocument} />
          {onAttachLocalDocument ? <><LocalDocumentPicker role="cv" onAttach={onAttachLocalDocument} /><LocalDocumentPicker role="cover_letter" onAttach={onAttachLocalDocument} /></> : null}
        </div>

        <div className="card" data-testid="runr-panel-answers" hidden={tab !== "answers"}>
          <p className="progress-title">Saved answers</p><p className="job-meta">Find an answer, copy it, and adjust it for this application.</p>
          {profileLoading ? <p className="job-meta" role="status">Loading your answers…</p> : !profile && !applicationPackage ? <p className="job-meta">{profileError || "Connect your profile to see saved answers."}</p> : <ProfileQuickCopy answers details={[...savedAnswers, ...(applicationPackage?.answers ?? []).map((answer) => ({ section: "This application", label: answer.label, value: answer.proposedValue }))]} />}
          <button type="button" className="icon-button" onClick={applicationPackage ? onReviewDocuments : onEditProfile}>{applicationPackage ? "Edit application answers" : "Edit profile answers"}</button>
          <ApplicationWorkspace key={`answers:${window.location.href}`} mode="answers" applicationUrl={window.location.href} description={job?.description || matchDescription} />
        </div>

        {tab === "autofill" && error ? (
          <p className="empty" role="alert" data-testid="runr-panel-error">{error}</p>
        ) : null}

        {tab === "resume" ? (
          resumeMatch ? (
            <div className="card" data-testid="runr-panel-resume-score">
              <div className="score-row">
                <span className={`score-ring score-${matchVerdict(resumeMatch.score).toLowerCase()}`}>
                  {resumeMatch.score}
                </span>
                <div>
                  <p className="job-title">{matchVerdict(resumeMatch.score)} Profile Match</p>
                  <p className="job-meta" data-testid="runr-panel-keyword-count">
                    Matches {resumeMatch.matchedKeywords.length} of{" "}
                    {resumeMatch.matchedKeywords.length + resumeMatch.missingKeywords.length} keywords
                  </p>
                </div>
              </div>
              <p className="job-meta">Based on your saved profile and this job description.</p>
              <button
                type="button"
                className="icon-button"
                aria-expanded={showKeywords}
                onClick={() => setShowKeywords((value) => !value)}
                data-testid="runr-panel-keyword-toggle"
              >
                {showKeywords ? "Hide keywords" : "Show keywords"}
              </button>
              {showKeywords ? (
                <div data-testid="runr-panel-keywords">
                  <p className="section-title">Matched</p>
                  <p className="job-meta">{resumeMatch.matchedKeywords.join(", ") || "None yet"}</p>
                  <p className="section-title">Missing</p>
                  <p className="job-meta">{resumeMatch.missingKeywords.join(", ") || "None"}</p>
                  <p className="job-meta" data-testid="runr-panel-score-explanation">{resumeMatch.explanation}</p>
                </div>
              ) : null}
              <button type="button" className="primary" onClick={onTailorResume} data-testid="runr-panel-tailor">
                Tailor Resume
              </button>
            </div>
          ) : (
            <div className="card"><p className="empty" data-testid="runr-panel-resume-empty">Open the job posting or paste its description to compare your profile.</p>
              {onScoreDescription ? <><label htmlFor="runr-match-description" className="section-title">Job description</label><textarea id="runr-match-description" className="profile-search" rows={6} maxLength={50000} placeholder="Paste the job description…" value={matchDescription} onChange={(event) => setMatchDescription(event.target.value)} /><button type="button" className="primary" disabled={!profile || !matchDescription.trim()} onClick={() => onScoreDescription(matchDescription)}>Compare profile</button>{!profile ? <p className="job-meta">Connect your profile to compare it with this role.</p> : null}</> : null}
              <button type="button" className="icon-button" onClick={onTailorResume} data-testid="runr-panel-tailor">Tailor Resume</button>
            </div>
          )
        ) : null}

        {tab === "profile" ? (
          completeness ? (
            <div className="card" data-testid="runr-panel-profile">
              {completeness.missing.length === 0 ? (
                <p className="empty" data-testid="runr-panel-profile-complete">
                  Your profile has everything applications usually ask for.
                </p>
              ) : (
                <>
                  <p className="progress-title" data-testid="runr-panel-missing-count">
                    {completeness.missing.length} missing field{completeness.missing.length === 1 ? "" : "s"}
                  </p>
                  <ul className="field-list" data-testid="runr-panel-missing-list">
                    {completeness.missing.map((item) => (
                      <li className="field-row" key={item.fieldIntent}>
                        <span className="glyph glyph-attention" aria-hidden="true">!</span>
                        <span className="field-label">{item.label}</span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
              <button type="button" className="icon-button" onClick={onEditProfile}>Edit profile</button>
              {profile ? <ProfileQuickCopy profile={profile} /> : null}
            </div>
          ) : (
            <p className="empty" data-testid="runr-panel-profile-empty">
              {profileLoading ? "Loading your profile…" : profileError || "Connect your Runr account to see your profile here."}
              <button type="button" className="icon-button" onClick={onOpenSettings}>Connect Runr</button>
              {onRefreshProfile ? <button type="button" className="icon-button" onClick={onRefreshProfile} disabled={profileLoading}>Refresh profile</button> : null}
            </p>
          )
        ) : null}
      </div>

      <footer className="footer">
        {onOpenTracker ? <button type="button" className="icon-button" onClick={onOpenTracker}>Open application tracker</button> : null}
        {
          <button
            type="button"
            className="primary"
            onClick={onPrimaryAction}
            disabled={busy || continuingToNextStep || Boolean(primaryBlockedReason)}
            data-testid="runr-panel-primary"
          >
            {busy ? "Autofilling…" : "Autofill This Page"}
          </button>
        }
        {run?.stage === "complete" && canContinueToNextStep ? (
          <button
            type="button"
            className="primary"
            onClick={onContinueToNextStep}
            disabled={busy || continuingToNextStep}
            data-testid="runr-panel-continue-step"
          >
            {continuingToNextStep ? "Verifying next step" : "Continue to Next Step"}
          </button>
        ) : null}
        {navigationMessage ? (
          <p className="footer-note" role="status" data-testid="runr-panel-navigation-status">
            {navigationMessage}
          </p>
        ) : null}
        <p className="footer-note" data-testid="runr-panel-footer-note">
          {primaryBlockedReason ||
            `${detection.fillableFieldCount} fields detected on ${providerLabel(detection.provider)}.`}
        </p>
      </footer>
    </section>
  );
}
