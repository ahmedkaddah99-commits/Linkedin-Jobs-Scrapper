import { useState } from "react";
import type { ApplicationJobContext, ApplicationPageDetection } from "@runr/ats-core/application-context";
import { matchVerdict, type ProfileCompleteness, type ResumeMatch } from "@runr/ats-core/resume-match";
import type { AutofillRunState, FieldResult } from "./autofill-run";

export type PanelTab = "autofill" | "resume" | "profile";

export interface AssistantPanelProps {
  job: ApplicationJobContext | null;
  detection: ApplicationPageDetection;
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
  onPrimaryAction: () => void;
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

function FieldRow({ result }: { result: FieldResult }) {
  const done = result.outcome === "filled" || result.outcome === "kept";
  return (
    <li className={`field-row field-${result.outcome}`} data-testid={`runr-field-${result.outcome}`}>
      <span className={done ? "glyph glyph-done" : "glyph glyph-attention"} aria-hidden="true">
        {done ? "✓" : "!"}
      </span>
      <span className="field-label">{result.label}</span>
    </li>
  );
}

function ProgressBlock({ run }: { run: AutofillRunState }) {
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
            {review.map((result) => <FieldRow key={result.fieldId} result={result} />)}
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
}: AssistantPanelProps) {
  const [tab, setTab] = useState<PanelTab>("autofill");
  const [showKeywords, setShowKeywords] = useState(false);

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
          <button type="button" className="icon-button" onClick={onReport} data-testid="runr-panel-report">
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
          ["resume", "Resume Score"],
          ["profile", "Profile"],
        ] as const).map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="tab"
            className="tab"
            aria-selected={tab === value}
            onClick={() => setTab(value)}
            data-testid={`runr-panel-tab-${value}`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="body" role="tabpanel">
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

        {tab === "autofill" && run ? <ProgressBlock run={run} /> : null}

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
                  <p className="job-title">{matchVerdict(resumeMatch.score)} Resume Match</p>
                  <p className="job-meta" data-testid="runr-panel-keyword-count">
                    Matches {resumeMatch.matchedKeywords.length} of{" "}
                    {resumeMatch.matchedKeywords.length + resumeMatch.missingKeywords.length} keywords
                  </p>
                </div>
              </div>
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
            <p className="empty" data-testid="runr-panel-resume-empty">
              Runr needs this posting's description to score your resume. Open the job posting first.
            </p>
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
              <button type="button" className="icon-button" onClick={onCopyProfile} data-testid="runr-panel-copy-profile">
                Copy profile details
              </button>
            </div>
          ) : (
            <p className="empty" data-testid="runr-panel-profile-empty">
              Connect your Runr account to see your profile here.
            </p>
          )
        ) : null}
      </div>

      <footer className="footer">
        {
          <button
            type="button"
            className="primary"
            onClick={onPrimaryAction}
            disabled={busy || Boolean(primaryBlockedReason)}
            data-testid="runr-panel-primary"
          >
            {busy ? "Autofilling…" : "Autofill This Page"}
          </button>
        }
        <p className="footer-note" data-testid="runr-panel-footer-note">
          {primaryBlockedReason ||
            `${detection.fillableFieldCount} fields detected on ${providerLabel(detection.provider)}.`}
        </p>
      </footer>
    </section>
  );
}
