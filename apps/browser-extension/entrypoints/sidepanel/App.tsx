import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  ApplicationCorrectionScope,
  ApplicationPackagePayload,
  AssistedApplyTabState,
  ExtensionConnectionState,
  DocumentUploadMessage,
  PackageExecutionMessage,
  PendingApplicationConfirmation,
  PanelRequest,
  TrackerConfirmationResult,
} from "@runr/extension-messages";
import { APPLICATION_CORRECTION_SCOPE_OPTIONS, isPanelResponse } from "@runr/extension-messages";
import { browser } from "wxt/browser";
import { buildReviewPanelModel, type ReviewFieldRow } from "../../src/review/panel-model";

async function send(message: PanelRequest) {
  const response: unknown = await browser.runtime.sendMessage(message);
  if (!isPanelResponse(response) || !response.ok) {
    const error = isPanelResponse(response) ? response.error : undefined;
    throw new Error(error || "Runr could not complete the extension request.");
  }
  return response;
}

async function requestTab(message: PanelRequest): Promise<AssistedApplyTabState> {
  const response = await send(message);
  if (!response.state) throw new Error("Runr could not read the active application tab.");
  return response.state;
}

async function requestConnection(message: PanelRequest): Promise<ExtensionConnectionState> {
  const response = await send(message);
  if (!response.connection) throw new Error("Runr returned an invalid connection state.");
  return response.connection;
}

async function requestPackage(message: PanelRequest): Promise<ApplicationPackagePayload> {
  const response = await send(message);
  if (!response.package) throw new Error("Runr returned an invalid application package.");
  return response.package;
}

async function executePackage(message: PanelRequest): Promise<PackageExecutionMessage> {
  const response = await send(message);
  if (!response.packageExecution) throw new Error("Runr returned an invalid fill result.");
  return response.packageExecution;
}

async function uploadDocument(message: PanelRequest): Promise<DocumentUploadMessage> {
  const response = await send(message);
  if (!response.documentUpload) throw new Error("Runr returned an invalid document result.");
  return response.documentUpload;
}

async function requestPendingConfirmation(): Promise<PendingApplicationConfirmation | null> {
  const response = await send({ type: "GET_PENDING_APPLICATION_CONFIRMATION" });
  if (!("pendingConfirmation" in response)) {
    throw new Error("Runr returned an invalid application confirmation state.");
  }
  return response.pendingConfirmation ?? null;
}

function atsLabel(ats: AssistedApplyTabState["ats"]): string {
  if (ats === "greenhouse") return "Greenhouse";
  if (ats === "lever") return "Lever";
  return "Unsupported page";
}

export default function App() {
  const testingFixtureBuild = import.meta.env.MODE === "testing";
  const [state, setState] = useState<AssistedApplyTabState | null>(null);
  const [connection, setConnection] = useState<ExtensionConnectionState | null>(null);
  const [error, setError] = useState("");
  const [connectionError, setConnectionError] = useState("");
  const [busy, setBusy] = useState(false);
  const [connectionBusy, setConnectionBusy] = useState(false);
  const [applicationPackage, setApplicationPackage] = useState<ApplicationPackagePayload | null>(null);
  const [packageBusy, setPackageBusy] = useState(false);
  const [packageExecution, setPackageExecution] = useState<PackageExecutionMessage | null>(null);
  const [documentUpload, setDocumentUpload] = useState<DocumentUploadMessage | null>(null);
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingApplicationConfirmation | null>(null);
  const [trackerConfirmation, setTrackerConfirmation] = useState<TrackerConfirmationResult | null>(null);
  const reviewModel = useMemo(
    () => buildReviewPanelModel(applicationPackage, state),
    [applicationPackage, state],
  );

  const load = useCallback(async (refresh = false) => {
    setBusy(true);
    setError("");
    try {
      setState(
        await requestTab({ type: refresh ? "REFRESH_ACTIVE_TAB_STATE" : "GET_ACTIVE_TAB_STATE" }),
      );
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load(false);
    setConnectionBusy(true);
    void requestConnection({ type: "GET_EXTENSION_CONNECTION" })
      .then(setConnection)
      .catch((nextError: unknown) => {
        setConnectionError(nextError instanceof Error ? nextError.message : String(nextError));
      })
      .finally(() => setConnectionBusy(false));
    setPackageBusy(true);
    void requestPackage({ type: "GET_BOUND_APPLICATION_PACKAGE" })
      .then(setApplicationPackage)
      .catch(() => setApplicationPackage(null))
      .finally(() => setPackageBusy(false));
  }, [load]);

  useEffect(() => {
    const refresh = () => void requestPendingConfirmation().then(setPendingConfirmation).catch(() => undefined);
    refresh();
    const interval = window.setInterval(refresh, 1000);
    return () => window.clearInterval(interval);
  }, []);

  async function respondToPossibleSuccess(decision: "confirmed" | "declined"): Promise<void> {
    if (!pendingConfirmation) return;
    setPackageBusy(true);
    setError("");
    try {
      const response = await send({
        type: "RESPOND_TO_APPLICATION_CONFIRMATION",
        decision,
        evidence: pendingConfirmation,
      });
      if (!response.trackerConfirmation) throw new Error("Runr returned an invalid Tracker result.");
      setTrackerConfirmation(response.trackerConfirmation);
      setPendingConfirmation(null);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setPackageBusy(false);
    }
  }

  async function updateConnection(message: PanelRequest): Promise<void> {
    setConnectionBusy(true);
    setConnectionError("");
    try {
      setConnection(await requestConnection(message));
    } catch (nextError) {
      setConnectionError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setConnectionBusy(false);
    }
  }

  async function savePreferences(
    permitSensitiveAutofill: boolean,
    permitDemographicAutofill: boolean,
  ): Promise<void> {
    await updateConnection({
      type: "UPDATE_ASSISTED_APPLY_PREFERENCES",
      permitSensitiveAutofill,
      permitDemographicAutofill,
    });
  }

  async function runFixture(): Promise<void> {
    setBusy(true);
    setError("");
    try {
      setState(await requestTab({ type: "RUN_GREENHOUSE_FIXTURE_PROOF" }));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy(false);
    }
  }

  async function fillApplicationPackage(replaceFieldIntents: string[] = []): Promise<void> {
    if (!applicationPackage) return;
    setPackageBusy(true);
    setError("");
    try {
      setPackageExecution(await executePackage({
        type: applicationPackage.job.portal === "lever"
          ? "RUN_LEVER_APPLICATION_PACKAGE" : "RUN_GREENHOUSE_APPLICATION_PACKAGE",
        package: applicationPackage,
        replaceFieldIntents,
      }));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setPackageBusy(false);
    }
  }

  async function uploadSelectedDocument(documentId: string): Promise<void> {
    if (!applicationPackage) return;
    setPackageBusy(true);
    setError("");
    setDocumentUpload(null);
    try {
      setDocumentUpload(await uploadDocument({
        type: "UPLOAD_SELECTED_DOCUMENT",
        package: applicationPackage,
        documentId,
      }));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setPackageBusy(false);
    }
  }

  return (
    <main className="panel-shell">
      <header className="panel-header">
        <div className="runr-mark" aria-hidden="true">R</div>
        <div>
          <p className="eyebrow">Runr</p>
          <h1>Assisted Apply</h1>
        </div>
      </header>

      <section className="boundary" aria-label="Submission boundary">
        <strong>Review-first by design</strong>
        <p>Runr may fill supported fields. You review the form and submit it yourself.</p>
      </section>

      {pendingConfirmation ? (
        <section className="connection-card" aria-label="Confirm application outcome" data-testid="application-confirmation">
          <p className="eyebrow">Possible application success</p>
          <h2>Did you submit this application?</h2>
          <p>Runr observed a possible success signal after your action. Confirm before anything is added to Tracker.</p>
          <div className="button-row">
            <button type="button" disabled={packageBusy} onClick={() => void respondToPossibleSuccess("confirmed")}>
              Yes, add to Tracker
            </button>
            <button className="secondary" type="button" disabled={packageBusy}
              onClick={() => void respondToPossibleSuccess("declined")}>
              No, do not add
            </button>
          </div>
        </section>
      ) : trackerConfirmation ? (
        <p className="boundary" role="status" data-testid="tracker-confirmation-result">
          {trackerConfirmation.decision === "confirmed"
            ? trackerConfirmation.duplicate
              ? "This application was already in Tracker."
              : "Application added to Tracker."
            : "Application was not added to Tracker."}
        </p>
      ) : null}

      <section className="connection-card" aria-busy={connectionBusy}>
        <div className="status-heading">
          <div>
            <p className="eyebrow">Runr account</p>
            <h2>
              {connection?.status === "connected"
                ? connection.session?.displayName || connection.session?.email || "Connected"
                : "Connect Assisted Apply"}
            </h2>
          </div>
          <span
            className={`status-chip connection-${connection?.status || "loading"}`}
            data-testid="connection-status"
          >
            {connection?.status || "loading"}
          </span>
        </div>

        <div className="capability-disclosure">
          <p>When connected, Runr can:</p>
          <ul>
            <li>Use the reviewed profile answers and documents in your Runr account.</li>
            <li>Fill supported fields only after you launch an application from Runr.</li>
            <li>Show uncertain, sensitive, and missing answers for your review.</li>
          </ul>
          <p>
            Runr cannot submit the form, solve CAPTCHA, sign declarations, accept legal terms,
            or complete assessments.
          </p>
        </div>

        {connectionError ? <p className="error" role="alert">{connectionError}</p> : null}
        {connection?.warning ? <p className="warning" role="status">{connection.warning}</p> : null}

        {connection?.status === "connected" ? (
          <>
            {connection.session?.email && connection.session.displayName ? (
              <p className="account-detail">{connection.session.email}</p>
            ) : null}
            <fieldset className="preference-list" disabled={connectionBusy}>
              <legend>Optional sensitive-data preferences</legend>
              <label>
                <input
                  type="checkbox"
                  checked={connection.preferences.permitSensitiveAutofill}
                  onChange={(event) =>
                    void savePreferences(
                      event.currentTarget.checked,
                      connection.preferences.permitDemographicAutofill,
                    )
                  }
                />
                <span>
                  <strong>Permit sensitive-answer autofill</strong>
                  <small>Runr still applies context, scope, and review policy.</small>
                </span>
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={connection.preferences.permitDemographicAutofill}
                  onChange={(event) =>
                    void savePreferences(
                      connection.preferences.permitSensitiveAutofill,
                      event.currentTarget.checked,
                    )
                  }
                />
                <span>
                  <strong>Permit demographic-answer autofill</strong>
                  <small>Off by default and applied only when explicitly enabled.</small>
                </span>
              </label>
              <p className="locked-policy">Legal answers always require your confirmation.</p>
            </fieldset>
            <button
              className="secondary danger"
              type="button"
              onClick={() => void updateConnection({ type: "DISCONNECT_RUNR" })}
              disabled={connectionBusy}
              data-testid="disconnect-runr"
            >
              {connectionBusy ? "Disconnecting…" : "Disconnect from Runr"}
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={() => void updateConnection({ type: "CONNECT_RUNR" })}
            disabled={connectionBusy}
            data-testid="connect-runr"
          >
            {connectionBusy ? "Connecting…" : "Connect to Runr"}
          </button>
        )}
      </section>

      {connection?.status === "connected" && applicationPackage ? (
        <section className="package-card">
          <div className="status-heading">
            <div>
              <p className="eyebrow">Application package</p>
              <h2>{applicationPackage.job.title || "Untitled role"}</h2>
            </div>
            <span className="status-chip status-recognized">v{applicationPackage.version}</span>
          </div>
          <dl>
            <div><dt>Company</dt><dd data-testid="package-company">{applicationPackage.job.company || "Unknown"}</dd></div>
            <div><dt>ATS</dt><dd data-testid="package-portal">{applicationPackage.job.portal || "Unknown"}</dd></div>
            <div><dt>Location</dt><dd>{applicationPackage.job.location || "Not specified"}</dd></div>
            <div><dt>Answers</dt><dd>{applicationPackage.answers.length} ready</dd></div>
            <div><dt>Documents</dt><dd>{applicationPackage.documents.length} available</dd></div>
            {applicationPackage.warnings.length > 0 ? (
              <div><dt>Warnings</dt><dd>{applicationPackage.warnings.join(", ")}</dd></div>
            ) : null}
          </dl>
          {applicationPackage.job.portal === "greenhouse" || applicationPackage.job.portal === "lever" ? (
            <button type="button" data-testid="fill-package" disabled={packageBusy}
              onClick={() => void fillApplicationPackage()}>
              {packageBusy ? "Filling and verifying…" : "Fill verified standard facts"}
            </button>
          ) : null}
        </section>
      ) : connection?.status === "connected" && !applicationPackage ? (
        <section className="package-card muted">
          <p className="eyebrow">Application package</p>
          <p>Launch a job from Runr to review and fill this application.</p>
        </section>
      ) : null}

      {connection?.status === "connected" && applicationPackage ? (
        <section className="review-workspace" aria-label="Application review">
          <div className="progress-summary" aria-label="Application progress">
            {(["verified", "review", "missing", "manual", "documents"] as const).map((key) => (
              <div key={key}><strong>{reviewModel.counts[key]}</strong><span>{key}</span></div>
            ))}
          </div>
          {!reviewModel.enabled ? (
            <p className="warning" role="status" data-testid="review-disabled">
              This package does not match the active supported application tab. Review controls are disabled.
            </p>
          ) : null}
          {(["ready", "review", "missing", "manual"] as const).map((section) => (
            <section className={`review-section section-${section}`} key={section}>
              <div className="section-title">
                <h2>{section.charAt(0).toUpperCase() + section.slice(1)}</h2>
                <span>{reviewModel.rows[section].length}</span>
              </div>
              {reviewModel.rows[section].length ? (
                <ul>{reviewModel.rows[section].map((row) => (
                  <EvidenceRow
                    row={row}
                    key={row.id}
                    onSave={async (correctedValue, scope) => {
                      if (!applicationPackage) return;
                      setPackageBusy(true);
                      setError("");
                      try {
                        setApplicationPackage(await requestPackage({
                          type: "SAVE_APPLICATION_CORRECTION",
                          package: applicationPackage,
                          fieldIntent: row.fieldIntent,
                          correctedValue,
                          scope,
                        }));
                      } catch (nextError) {
                        setError(nextError instanceof Error ? nextError.message : String(nextError));
                        throw nextError;
                      } finally {
                        setPackageBusy(false);
                      }
                    }}
                  />
                ))}</ul>
              ) : <p className="muted">No fields in this section.</p>}
              {section === "manual" && reviewModel.manualControls.length ? (
                <ul className="manual-controls">
                  {reviewModel.manualControls.map((reason) => <li key={reason}>{reason.replaceAll("_", " ")}</li>)}
                </ul>
              ) : null}
            </section>
          ))}
          <section className="review-section section-documents">
            <div className="section-title"><h2>Documents</h2><span>{applicationPackage.documents.length}</span></div>
            {applicationPackage.documents.length ? (
              <ul>{applicationPackage.documents.map((document, index) => (
                <li className="document-row" key={document.documentId || `${document.documentKind}:${index}`}>
                  <strong>{document.documentKind}</strong>
                  <span>{document.fileName || document.mimeType} · v{document.documentVersion}</span>
                  {(["cv", "cover_letter", "supporting_document"] as const).includes(document.documentKind) ? (
                    <button type="button" disabled={packageBusy}
                      data-testid={`upload-${document.documentKind}`}
                      onClick={() => void uploadSelectedDocument(document.documentId)}>
                      {packageBusy ? "Uploading and verifying…" : `Upload selected ${document.documentKind.replaceAll("_", " ")}`}
                    </button>
                  ) : null}
                  {documentUpload?.documentId === document.documentId ? (
                    <p role="status" data-testid="document-upload-status">
                      {documentUpload.status}: {documentUpload.reasons.join(" ")}
                    </p>
                  ) : null}
                </li>
              ))}</ul>
            ) : <p className="muted">No documents selected.</p>}
          </section>
        </section>
      ) : null}

      {packageExecution ? (
        <section className="result-card" data-testid="package-execution-result">
          <p className="eyebrow">Verified package results</p>
          <h2>{packageExecution.executions.length} fields checked</h2>
          <ul>{packageExecution.executions.map((result, index) => (
            <li key={`${result.fieldLabel}-${index}`}>
              <strong>{result.fieldLabel}</strong>: {result.status}
              {result.status === "preserved_existing" && result.fieldIntent ? (
                <button type="button" className="secondary replace-answer"
                  data-testid={`replace-${result.fieldIntent}`}
                  disabled={packageBusy}
                  onClick={() => void fillApplicationPackage([result.fieldIntent!])}>
                  Replace with Runr answer
                </button>
              ) : null}
            </li>
          ))}</ul>
        </section>
      ) : null}

      {error ? <p className="error" role="alert">{error}</p> : null}

      <section className="status-card" aria-busy={busy}>
        <div className="status-heading">
          <div>
            <p className="eyebrow">Current page</p>
            <h2 data-testid="ats-name">{state ? atsLabel(state.ats) : "Inspecting…"}</h2>
          </div>
          <span className={`status-chip status-${state?.status || "loading"}`}>
            {state?.status.replaceAll("_", " ") || "loading"}
          </span>
        </div>

        {testingFixtureBuild && state?.fixtureAvailable ? (
          <div className="fixture-proof">
            <p>
              Local AA-01 fixture found. This proof uses the non-production value
              <code>candidate@example.com</code>.
            </p>
            <button
              type="button"
              onClick={() => void runFixture()}
              disabled={busy}
              data-testid="run-fixture"
            >
              {busy ? "Checking…" : "Fill and verify fixture email"}
            </button>
          </div>
        ) : (
          <p className="muted">
            {state?.ats
              ? "Portal recognized. Real package-backed filling arrives in a later ticket."
              : "Open a supported application page, then refresh this panel."}
          </p>
        )}

        <button
          className="secondary"
          type="button"
          onClick={() => void load(true)}
          disabled={busy}
        >
          Refresh page status
        </button>
      </section>

      {state?.execution ? (
        <section className="result-card" data-testid="execution-result">
          <p className="eyebrow">Verified field result</p>
          <h2>{state.execution.fieldLabel}</h2>
          <dl>
            <div><dt>Status</dt><dd data-testid="execution-status">{state.execution.status}</dd></div>
            <div><dt>Accepted value</dt><dd>{state.execution.acceptedValue || "None"}</dd></div>
            <div><dt>Source</dt><dd>Local verified fixture package</dd></div>
          </dl>
        </section>
      ) : null}

      {state?.manualReasons.length ? (
        <section className="manual-card">
          <p className="eyebrow">Manual-only controls observed</p>
          <ul>
            {state.manualReasons.map((reason) => (
              <li key={reason}>{reason.replaceAll("_", " ")}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <footer>
        No CAPTCHA solving, declarations, assessments, signatures, terms acceptance,
        or final submission capability exists in this build.
      </footer>
    </main>
  );
}

function EvidenceRow({
  row,
  onSave,
}: {
  row: ReviewFieldRow;
  onSave: (correctedValue: string, scope: ApplicationCorrectionScope) => Promise<void>;
}) {
  const [reviewed, setReviewed] = useState(false);
  const [editing, setEditing] = useState(false);
  const [correctedValue, setCorrectedValue] = useState(row.proposedValue);
  const [scope, setScope] = useState<ApplicationCorrectionScope>("application");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState("");
  return (
    <li className="evidence-row" data-testid={`field-${row.section}`}>
      <div className="field-heading">
        <strong>{row.label || row.fieldIntent}</strong>
        <span className={`acceptance acceptance-${row.liveAcceptance}`}>
          {row.liveAcceptance.replaceAll("_", " ")}
        </span>
      </div>
      <p className="proposed-answer">{row.proposedValue || "No answer available"}</p>
      <dl className="field-evidence">
        <div><dt>Source</dt><dd>{row.source.replaceAll("_", " ")}</dd></div>
        <div><dt>Scope</dt><dd>{row.scope.replaceAll("_", " ")}</dd></div>
        <div><dt>Confidence</dt><dd>{Math.round(row.confidence * 100)}%</dd></div>
        <div><dt>Review</dt><dd>{row.requiresReview ? "Required" : "Not required"}</dd></div>
      </dl>
      {row.reasons.length ? <p className="field-reason">{row.reasons.join(" ")}</p> : null}
      {row.section === "review" ? (
        <div className="field-actions">
          <button type="button" onClick={() => setReviewed(true)} aria-pressed={reviewed}>
            {reviewed ? "Reviewed" : "Review answer"}
          </button>
          <button className="secondary" type="button" onClick={() => setReviewed(false)} disabled={!reviewed}>
            Clear review
          </button>
        </div>
      ) : null}
      <div className="field-actions correction-actions">
        <button className="secondary" type="button" onClick={() => setEditing((value) => !value)}>
          {editing ? "Cancel correction" : "Correct answer"}
        </button>
      </div>
      {editing ? (
        <div className="correction-editor">
          <label>
            <span>Corrected answer</span>
            <input value={correctedValue} onChange={(event) => setCorrectedValue(event.currentTarget.value)} />
          </label>
          <label>
            <span>Use this correction for</span>
            <select value={scope} onChange={(event) => setScope(event.currentTarget.value as ApplicationCorrectionScope)}>
              {APPLICATION_CORRECTION_SCOPE_OPTIONS.map((option) => (
                <option value={option.value} key={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={saving || !correctedValue.trim()}
            onClick={() => {
              setSaving(true);
              setSaved("");
              void onSave(correctedValue, scope)
                .then(() => {
                  setSaved(scope === "do_not_save" ? "Applied without saving." : "Correction applied at the selected scope.");
                  setEditing(false);
                })
                .catch(() => undefined)
                .finally(() => setSaving(false));
            }}
          >
            {saving ? "Applying…" : "Apply correction"}
          </button>
        </div>
      ) : null}
      {saved ? <p className="correction-saved" role="status">{saved}</p> : null}
    </li>
  );
}
